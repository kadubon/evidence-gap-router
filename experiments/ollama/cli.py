"""Explicit local experiment commands; import never invokes a model or server."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypeGuard

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.ollama.analysis import analyze, write_json  # noqa: E402
from experiments.ollama.client import (  # noqa: E402
    ClientBlocked,
    Limits,
    ModelProfile,
    OllamaClient,
)
from experiments.ollama.environment import (  # noqa: E402
    collect_resources,
    observe_backend,
    preflight,
    resource_gate,
    verify_inventory,
)
from experiments.ollama.harness import run_trial  # noqa: E402
from experiments.ollama.tasks import confirmation_tasks, development_tasks  # noqa: E402

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(
            (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )
        handle.flush()
        os.fsync(handle.fileno())


def key(phase: str, task: str, model: str, arm: str, seed: int) -> str:
    model_key = "gemma" if model.startswith("gemma") else "qwen"
    return f"{phase}-{model_key}-{task}-{arm}-{seed}"


def client_for(args: argparse.Namespace) -> OllamaClient:
    manifest = json.loads((args.directory / "preflight" / "manifest.json").read_text("utf-8"))
    if manifest["server_version"] != PROTOCOL["server"]["version"]:
        raise ValueError("this protocol requires the inspected Ollama 0.35.0 server")
    if manifest["ready_for_backend_smoke"] is not True:
        raise ValueError("actual server locality/resource preflight is incomplete")
    profiles = {
        model["tag"]: ModelProfile(
            tag=model["tag"],
            digest=model["digest"],
            think=False,
            thinking_values=tuple(model["supported_thinking_values_advertised"]),
            local_verified=True,
        )
        for model in manifest["models"]
    }
    if list(profiles) != PROTOCOL["models"]:
        raise ValueError("preflight model selection differs from the protocol")
    return OllamaClient(
        args.url,
        args.directory / "calls.jsonl",
        run_id=PROTOCOL["protocol_id"],
        freeze_id=sha(ROOT / "protocol.json"),
        profiles=profiles,
        limits=Limits(socket_timeout_seconds=180, max_response_bytes=65536),
        disk_root=args.directory,
    )


def guard(args: argparse.Namespace) -> dict[str, Any]:
    if (args.directory / "identity-violations.jsonl").exists():
        raise ClientBlocked("pinned_model_identity_violation: stop new calls")
    observation = resource_gate(args.directory, server_pid=args.server_pid)
    resources = observation["resources"]
    if args.server_pid is None or resources.get("server_alive") is not True:
        raise ClientBlocked("owned_server_liveness_unconfirmed: stop new calls")
    if not observation["safe_for_new_request"]:
        raise ClientBlocked("resource_precondition: " + ", ".join(observation["blocking_reasons"]))
    return {
        **resources,
        "raw_bytes": observation["raw_bytes"],
        "disk_free_bytes": observation["disk_free_bytes"],
    }


class BoundClient:
    """Bind phase identities while preserving the harness's exact receipt identity."""

    def __init__(
        self,
        client: OllamaClient,
        args: argparse.Namespace,
        phase: str,
        trial_key: str,
        freeze_sha: str | None = None,
    ) -> None:
        self.client, self.args, self.phase = client, args, phase
        self.trial_key, self.freeze_sha = trial_key, freeze_sha

    def chat(self, **kwargs: Any) -> dict[str, Any]:
        pre_sampling_began = time.monotonic()
        before = guard(self.args)
        inventory = verify_inventory(
            self.args.url, {kwargs["model"]: self.client.profiles[kwargs["model"]].digest}
        )
        pre_sampling_wall = time.monotonic() - pre_sampling_began
        original = kwargs["request_id"]
        kwargs["request_id"] = self.trial_key + "/" + original
        kwargs["trial_id"] = self.trial_key
        kwargs["metadata"] = {
            **kwargs.get("metadata", {}),
            "phase": self.phase,
            "formal_freeze_sha256": self.freeze_sha,
            "resources_before": before,
            "inventory_before": inventory,
            "before_sampling_wall_seconds": pre_sampling_wall,
        }
        record = self.client.chat(**kwargs)
        sampling_began = time.monotonic()
        try:
            backend = observe_backend(self.args.url, self.args.server_log)
        except (OSError, ValueError) as error:
            backend = {"observation_error": type(error).__name__}
        violations = [
            model
            for model in backend.get("loaded_models", [])
            if model["name"] not in self.client.profiles
            or model["digest"] != self.client.profiles[model["name"]].digest
        ]
        if violations:
            append(
                self.args.directory / "identity-violations.jsonl",
                {
                    "request_id": kwargs["request_id"],
                    "loaded_models": violations,
                    "known_receipt_retained": True,
                },
            )
        append(
            self.args.directory / "resources.jsonl",
            {
                "request_id": kwargs["request_id"],
                "before": before,
                "after": collect_resources(server_pid=self.args.server_pid),
                "backend_after": backend,
                "model": kwargs["model"],
                "before_sampling_wall_seconds": pre_sampling_wall,
                "sampling_wall_seconds": time.monotonic() - sampling_began,
            },
        )
        return {**record, "ledger_request_id": record["request_id"], "request_id": original}

    def lookup(self, request_id: str) -> dict[str, Any] | None:
        record = self.client.record(self.trial_key + "/" + request_id)
        return (
            None
            if record is None
            else {**record, "ledger_request_id": record["request_id"], "request_id": request_id}
        )

    def summary(self) -> dict[str, Any]:
        summary = self.client.summary()
        return {
            **summary,
            "blocked": summary["blocked"]
            or (self.args.directory / "identity-violations.jsonl").exists(),
        }


def execute(
    args: argparse.Namespace,
    client: OllamaClient,
    phase: str,
    item: dict[str, Any],
    freeze_sha: str | None = None,
) -> dict[str, Any]:
    trial_key = item["key"]
    final = args.directory / "trials" / phase / (trial_key + ".json")
    if final.exists():
        saved: dict[str, Any] = json.loads(final.read_text("utf-8"))
        if (
            saved.get("formal_freeze_sha256") != freeze_sha
            or saved.get("phase") != phase
            or any(saved.get(field) != value for field, value in item.items())
        ):
            raise ValueError("saved trial identity or freeze differs; no replay")
        return saved
    tasks = development_tasks() if phase == "pilot" else confirmation_tasks()
    task = next(task for task, _gold in tasks if task.task_id == item["task_id"])
    checkpoint = args.directory / "checkpoints" / (trial_key + ".json")
    resumed = checkpoint.exists()
    began = time.monotonic()
    adapter = BoundClient(client, args, phase, trial_key, freeze_sha)
    result = run_trial(
        task,
        arm=item["arm"],
        model=item["model"],
        model_digest=client.profiles[item["model"]].digest,
        seed=item["seed"],
        client=adapter,
        checkpoint=checkpoint,
        resume=resumed,
    )
    record = {
        **item,
        "phase": phase,
        "execution": "completed",
        "trial": result,
        "formal_freeze_sha256": freeze_sha,
        "trial_wall_seconds": None if resumed else time.monotonic() - began,
        "current_controller_segment_wall_seconds": time.monotonic() - began,
        "resumed_checkpoint": resumed,
    }
    write_json(final, record)
    append(
        args.directory / "terminal-keys.jsonl",
        {
            k: record[k]
            for k in ("key", "phase", "execution", "formal_freeze_sha256", "trial_wall_seconds")
        },
    )
    print(
        json.dumps(
            {
                "key": trial_key,
                "calls": len(result["calls"]),
                "stop": result["runner_stop"],
                "fault": result["fault"],
            }
        ),
        flush=True,
    )
    return record


def auxiliary(
    args: argparse.Namespace, client: OllamaClient, main_record: dict[str, Any], freeze_sha: str
) -> dict[str, Any]:
    """Continue only a copied predeclared no-progress checkpoint in its original budget."""
    item = {name: main_record[name] for name in ("task_id", "model", "arm", "seed")}
    item["key"] = main_record["key"] + "-aux"
    final = args.directory / "trials/auxiliary" / (item["key"] + ".json")
    if final.exists():
        saved: dict[str, Any] = json.loads(final.read_text("utf-8"))
        if (
            saved.get("formal_freeze_sha256") != freeze_sha
            or saved.get("phase") != "auxiliary"
            or any(saved.get(name) != value for name, value in item.items())
        ):
            raise ValueError("saved auxiliary identity or freeze differs; no replay")
        return saved
    result = main_record.get("trial", {})
    summary = client.summary()
    reason = None
    if (
        main_record["execution"] != "completed"
        or result.get("runner_stop") != "no_progress"
        or result.get("fault")
        or result.get("pending")
        or result.get("runner_error")
    ):
        reason = "main_not_known_no_progress"
    elif summary["blocked"]:
        reason = "pending_or_unknown_consumption"
    elif summary["started_epoch"] is None or time.time() - summary["started_epoch"] >= 14400:
        reason = "global_wall_exhausted"
    ledger_path = args.directory / "calls.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text("utf-8").splitlines()]
    auxiliary_calls = sum(
        row.get("event") == "reserve" and row.get("metadata", {}).get("phase") == "auxiliary"
        for row in ledger
    )
    if reason is None and auxiliary_calls + 2 > PROTOCOL["auxiliary"]["maximum_generation_calls"]:
        reason = "auxiliary_call_envelope_exhausted"
    trial_budget = summary["trials"].get(main_record["key"])
    if reason is None and (
        trial_budget is None
        or trial_budget["calls"] >= 6
        or time.time() - trial_budget["started_epoch"] >= 600
        or trial_budget["total_tokens"] + 4608 > 27648
    ):
        reason = "original_trial_budget_exhausted"
    if reason is None:
        try:
            guard(args)
        except ClientBlocked as error:
            reason = str(error)
    began = time.monotonic()
    continued = {}
    if reason is None:
        source = args.directory / "checkpoints" / (main_record["key"] + ".json")
        copied = args.directory / "checkpoints" / (item["key"] + ".json")
        if not source.exists():
            raise ValueError("auxiliary continuation requires the retained main checkpoint")
        if not copied.exists():
            with copied.open("xb") as handle:
                handle.write(source.read_bytes())
        task = next(task for task, _gold in confirmation_tasks() if task.task_id == item["task_id"])
        continued = run_trial(
            task,
            arm=item["arm"],
            model=item["model"],
            model_digest=client.profiles[item["model"]].digest,
            seed=item["seed"],
            client=BoundClient(client, args, "auxiliary", main_record["key"], freeze_sha),
            checkpoint=copied,
            resume=True,
            secondary_steps=PROTOCOL["auxiliary"]["maximum_extra_callbacks_per_trial"],
        )
    record = {
        **item,
        "phase": "auxiliary",
        "source_main_key": main_record["key"],
        "execution": "completed" if reason is None else "not_eligible_for_auxiliary",
        "trial": continued,
        "stop_detail": reason,
        "formal_freeze_sha256": freeze_sha,
        "trial_wall_seconds": None,
        "current_controller_segment_wall_seconds": time.monotonic() - began,
    }
    write_json(final, record)
    return record


def schedule(tasks: list[str], phase: str) -> list[dict[str, Any]]:
    rng = random.Random(PROTOCOL["schedule_seed"])
    rng.shuffle(tasks)
    result = []
    permutations = (
        ("A", "B", "C"),
        ("B", "C", "A"),
        ("C", "A", "B"),
        ("A", "C", "B"),
        ("C", "B", "A"),
        ("B", "A", "C"),
    )
    seed = PROTOCOL["development_seed" if phase == "pilot" else "seed"]
    for model in PROTOCOL["models"]:
        for number, task in enumerate(tasks):
            for arm in permutations[number % len(permutations)]:
                result.append(
                    {
                        "task_id": task,
                        "model": model,
                        "arm": arm,
                        "seed": seed,
                        "key": key(phase, task, model, arm, seed),
                    }
                )
    return result


def verify_installed_runtime(wheel: Path) -> dict[str, Any]:
    """Check the actual import against every runtime wheel byte, not metadata alone."""
    import pydantic
    import pydantic_core

    import evidence_gap_router as sdk
    from scripts.package_audit import package_fingerprint

    package_dir = Path(sdk.__file__).resolve().parent
    repository = ROOT.parents[1].resolve()
    if (
        sdk.__version__ != PROTOCOL["package_version"]
        or package_dir.is_relative_to(repository)
        or package_dir.parent.name != "site-packages"
    ):
        raise ValueError("freeze requires the ordinary candidate SDK outside the repository")
    fingerprint = package_fingerprint(wheel)
    with zipfile.ZipFile(wheel) as archive:
        members = [
            name
            for name in archive.namelist()
            if name.startswith("evidence_gap_router/") and not name.endswith("/")
        ]
        expected = {name.removeprefix("evidence_gap_router/") for name in members}
        actual = {
            str(path.relative_to(package_dir)).replace("\\", "/")
            for path in package_dir.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        if actual != expected:
            raise ValueError("installed SDK files differ from the candidate wheel")
        for name in members:
            path = package_dir / name.removeprefix("evidence_gap_router/")
            if path.read_bytes() != archive.read(name):
                raise ValueError("installed SDK bytes differ from the candidate wheel")
    return {
        "sdk_version": sdk.__version__,
        "sdk_import_scope": "outside-repository/site-packages",
        "python": sys.version.split()[0],
        "pydantic": pydantic.__version__,
        "pydantic_core": pydantic_core.__version__,
        "package_sha256": fingerprint,
    }


def selected_parent_ids(count: int) -> list[str]:
    if count == 0:
        return []
    mapping = PROTOCOL["profile_parent_numbers"][str(count)]
    return [
        task.task_id
        for task, _gold in confirmation_tasks()
        if int(task.task_id.rsplit("-", 1)[1]) in mapping[task.family]
    ]


def _seconds(value: object) -> TypeGuard[int | float]:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def speed_forecast(
    ledger: list[dict[str, Any]], resources: list[dict[str, Any]], models: list[str]
) -> dict[str, Any]:
    """Use observed decode/overhead maxima; charge cold load once per model block."""
    samples = {row["request_id"]: row for row in resources}
    result = {}
    for model in models:
        overheads = [
            row["before_sampling_wall_seconds"] + row["sampling_wall_seconds"]
            for row in resources
            if row.get("model") == model
            and all(
                _seconds(row.get(name))
                for name in ("before_sampling_wall_seconds", "sampling_wall_seconds")
            )
        ]
        requests: list[float] = []
        loads: list[float] = []
        unknown_load = missing_overhead = 0
        for row in ledger:
            if row.get("event") != "response" or row["record"]["model"] != model:
                continue
            record = row["record"]
            wall = record["client_wall_seconds"]
            if not _seconds(wall):
                continue
            load = (record.get("durations_seconds") or {}).get("load_duration")
            if _seconds(load) and load <= wall:
                loads.append(float(load))
                request_wall = float(wall - load)
            else:
                unknown_load += 1
                request_wall = float(wall)
            sample = samples.get(row["request_id"], {})
            observed = [
                sample.get("before_sampling_wall_seconds"),
                sample.get("sampling_wall_seconds"),
            ]
            valid = [float(value) for value in observed if _seconds(value)]
            overhead: float | None
            if len(valid) == 2:
                overhead = sum(valid)
            else:
                missing_overhead += 1
                overhead = float(max(overheads)) if overheads else None
            if overhead is not None:
                requests.append(request_wall + overhead)
        result[model] = {
            "per_request_seconds": max(requests) if requests else None,
            "once_per_model_load_seconds": max(loads) if loads else None,
            "unknown_load_records": unknown_load,
            "missing_per_request_overhead_records": missing_overhead,
            "observed_overhead_max_seconds": max(overheads) if overheads else None,
        }
    return result


def freeze(args: argparse.Namespace) -> dict[str, Any]:
    from scripts.package_audit import package_fingerprint

    ledger = [
        json.loads(line)
        for line in (args.directory / "calls.jsonl").read_text("utf-8").splitlines()
    ]
    summary = client_for(args).summary()
    if summary["blocked"] or summary["started_epoch"] is None:
        raise ClientBlocked("freeze requires known completed development dispatches")
    start = summary["started_epoch"]
    remaining = max(0.0, 14400 - (time.time() - start))
    guard(args)
    resource_path = args.directory / "resources.jsonl"
    resources = (
        [json.loads(line) for line in resource_path.read_text("utf-8").splitlines()]
        if resource_path.exists()
        else []
    )
    forecast = speed_forecast(ledger, resources, PROTOCOL["models"])
    forecast_known = all(value["per_request_seconds"] is not None for value in forecast.values())
    remaining_calls = PROTOCOL["global_limits"]["calls"] - summary["calls"]
    remaining_generated = (
        PROTOCOL["global_limits"]["generated_tokens"] - summary["generated_tokens"]
    )
    remaining_tokens = PROTOCOL["global_limits"]["total_tokens"] - summary["total_tokens"]
    selected = next(
        (
            n
            for n in (24, 16, 8)
            if forecast_known
            and n * 3 * 6 * sum(value["per_request_seconds"] for value in forecast.values())
            + sum(
                value["once_per_model_load_seconds"]
                for value in forecast.values()
                if value["once_per_model_load_seconds"] is not None
            )
            < 0.9 * remaining
            and n * 3 * 6 * len(PROTOCOL["models"]) <= remaining_calls
            and n * 3 * 6 * len(PROTOCOL["models"]) * 512 <= remaining_generated
            and n * 3 * 6 * len(PROTOCOL["models"]) * 4608 <= remaining_tokens
        ),
        0,
    )
    selected_tasks = selected_parent_ids(selected)
    public = [
        asdict(task) for task, _gold in confirmation_tasks() if task.task_id in selected_tasks
    ]
    gold = [asdict(score) for task, score in confirmation_tasks() if task.task_id in selected_tasks]
    write_json(args.directory / "frozen-public-tasks.json", public)
    write_json(args.directory / "evaluation-only-gold.json", gold)
    code = {p.name: sha(p) for p in sorted(ROOT.glob("*.py"))}
    harness = hashlib.sha256()
    for path in sorted(ROOT.glob("*.py")):
        harness.update(path.name.encode("utf-8"))
        harness.update(path.read_bytes())
    wheel = args.wheel.resolve()
    installed = verify_installed_runtime(wheel)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    for path in sorted(ROOT.glob("*.py")):
        tracked = subprocess.check_output(
            ["git", "show", f"{commit}:experiments/ollama/{path.name}"], cwd=ROOT
        )
        if tracked.replace(b"\r\n", b"\n") != path.read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("freeze requires committed exact harness bytes")
    result = {
        "protocol_id": PROTOCOL["protocol_id"],
        "implementation_commit": commit,
        "candidate_wheel_sha256": sha(wheel),
        "candidate_package_sha256": package_fingerprint(wheel),
        "installed_runtime": installed,
        "manifest_sha256": sha(ROOT / "protocol.json"),
        "harness_sha256": harness.hexdigest(),
        "harness_files": code,
        "preflight_sha256": sha(args.directory / "preflight/manifest.json"),
        "public_tasks_sha256": sha(args.directory / "frozen-public-tasks.json"),
        "evaluation_only_gold_sha256": sha(args.directory / "evaluation-only-gold.json"),
        "selected_parent_count": selected,
        "excluded_parent_ids": [
            task.task_id
            for task, _gold in confirmation_tasks()
            if task.task_id not in selected_tasks
        ],
        "exclusion_reason": "Predeclared balanced profile chosen from speed/resource budgets",
        "remaining_wall_at_freeze_seconds": remaining,
        "remaining_calls_at_freeze": remaining_calls,
        "remaining_generated_tokens_at_freeze": remaining_generated,
        "remaining_total_tokens_at_freeze": remaining_tokens,
        "speed_only_profile_forecast_request_seconds": forecast,
        "planned_trial_keys": schedule(selected_tasks, "confirmation"),
        "planned_auxiliary_source_keys": [
            item["key"]
            for item in schedule(selected_tasks, "confirmation")
            if item["arm"] in ("A", "B")
            and int(item["task_id"].rsplit("-", 1)[1])
            in PROTOCOL["auxiliary"]["selected_parent_numbers"]
        ],
        "runtime_decode": PROTOCOL["request"],
        "limits": PROTOCOL["global_limits"],
        "input_provenance": "new artificial parents, distinct from the older model-free regression",
        "no_result_based_profile_choice": True,
    }
    write_json(args.freeze, result)
    return result


def live(args: argparse.Namespace, client: OllamaClient) -> None:
    frozen = json.loads(args.freeze.read_text("utf-8"))
    current = hashlib.sha256()
    for path in sorted(ROOT.glob("*.py")):
        current.update(path.name.encode("utf-8"))
        current.update(path.read_bytes())
    if (
        current.hexdigest() != frozen["harness_sha256"]
        or sha(ROOT / "protocol.json") != frozen["manifest_sha256"]
    ):
        raise ValueError("frozen implementation or protocol changed; retain records and stop")
    halted = None
    auxiliary_sources = set(frozen["planned_auxiliary_source_keys"])
    for index, item in enumerate(frozen["planned_trial_keys"]):
        if index % 3 == 0 and halted is None:
            summary = client.summary()
            # Auxiliary callbacks consume unused calls inside the original six-call trials.
            maximum_calls = 18
            try:
                guard(args)
                if (
                    summary["blocked"]
                    or summary["started_epoch"] is None
                    or time.time() - summary["started_epoch"] >= 14400
                    or summary["calls"] + maximum_calls > 1200
                    or summary["generated_tokens"] + maximum_calls * 512 > 600000
                    or summary["total_tokens"] + maximum_calls * 4608 > 5000000
                ):
                    raise ClientBlocked("whole parent block cannot fit remaining envelope")
                append(
                    args.directory / "blocks.jsonl",
                    {
                        "event": "reserve_parent_block",
                        "keys": [x["key"] for x in frozen["planned_trial_keys"][index : index + 3]],
                        "maximum_calls": maximum_calls,
                        "maximum_total_tokens": maximum_calls * 4608,
                    },
                )
            except ClientBlocked as error:
                halted = str(error)
        if halted is None:
            primary = execute(args, client, "confirmation", item, sha(args.freeze))
            if item["key"] in auxiliary_sources:
                auxiliary(args, client, primary, sha(args.freeze))
            if client.summary()["blocked"]:
                halted = "pending_or_unknown_consumption"
        else:
            final = args.directory / "trials/confirmation" / (item["key"] + ".json")
            if not final.exists():
                write_json(
                    final,
                    {
                        **item,
                        "phase": "confirmation",
                        "trial": {},
                        "execution": "unexecuted_due_to_budget",
                        "stop_detail": halted,
                        "formal_freeze_sha256": sha(args.freeze),
                    },
                )
            if item["key"] in auxiliary_sources:
                auxiliary(args, client, json.loads(final.read_text("utf-8")), sha(args.freeze))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("preflight", "backend-smoke", "pilot", "freeze", "live", "resume", "analyze"),
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--freeze", type=Path, default=ROOT / "results/freeze-v0.2.3.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/v0.2.3")
    args = parser.parse_args(argv)
    if args.command == "preflight":
        result = preflight(
            args.url,
            args.directory / "preflight",
            server_log=args.server_log,
            owned_server_pid=args.server_pid,
        )
        canonical = args.directory / "preflight/manifest.json"
        if canonical.exists():
            raise ValueError("preflight already pinned; retain old record in this run")
        write_json(canonical, result)
        print(
            json.dumps(
                {
                    "ready": result["ready_for_backend_smoke"],
                    "blocking_reasons": result["blocking_reasons"],
                    "server_version": result["server_version"],
                    "models": [model["tag"] for model in result["models"]],
                }
            )
        )
        return 0
    if args.command == "analyze":
        frozen = json.loads(args.freeze.read_text("utf-8")) if args.freeze.exists() else None
        print(
            json.dumps(
                analyze(args.directory, args.output, PROTOCOL, frozen=frozen), ensure_ascii=False
            )
        )
        return 0
    if args.command == "freeze":
        if args.wheel is None:
            parser.error("freeze requires --wheel with the actually installed candidate")
        print(json.dumps(freeze(args), ensure_ascii=False))
        return 0
    client = client_for(args)
    if args.command == "backend-smoke":
        for model in PROTOCOL["models"]:
            identity = "backend-smoke/" + model
            if client.record(identity + "/call-1") is not None:
                continue
            record = BoundClient(client, args, "backend-smoke", identity).chat(
                model=model,
                trial_id=identity,
                request_id="call-1",
                messages=[
                    {"role": "system", "content": "指定JSONのみ返してください。"},
                    {"role": "user", "content": "okをtrueにしてください。"},
                ],
                schema={
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
                seed=PROTOCOL["development_seed"],
                metadata={"phase": "backend-smoke"},
                wall_seconds=180,
            )
            print(
                json.dumps(
                    {
                        "model": model,
                        "status": record["status"],
                        "usage": record["usage"],
                        "wall": record["client_wall_seconds"],
                    }
                ),
                flush=True,
            )
            if record["status"] != "ok":
                raise ClientBlocked("backend smoke failed; preserve response and stop")
    elif args.command == "pilot":
        for item in schedule([task.task_id for task, _gold in development_tasks()], "pilot"):
            execute(args, client, "pilot", item)
            if client.summary()["blocked"]:
                break
    else:
        live(args, client)
    summary = client.summary()
    write_json(
        args.directory / "ledger-summary.json",
        {k: v for k, v in summary.items() if k != "responses"},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
