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
import threading
import time
import zipfile
from dataclasses import asdict, replace
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
    strict_json,
)
from experiments.ollama.environment import (  # noqa: E402
    collect_resources,
    observe_backend,
    preflight,
    resource_gate,
    verify_inventory,
)
from experiments.ollama.harness import TrialSettings, run_trial  # noqa: E402
from experiments.ollama.prompts import (
    Answer,
    CompactReview,
    Extraction,
    Review,
    extraction_messages,  # noqa: E402
    integration_messages,
    review_messages,
    validate_output,
)
from experiments.ollama.tasks import confirmation_tasks, development_tasks  # noqa: E402

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
PROTOCOL_PATH = ROOT / "protocol.json"


def edition() -> str:
    return "024" if PROTOCOL["package_version"] == "0.2.4" else "023"


def protocol_path() -> Path:
    return PROTOCOL_PATH if edition() == "024" else ROOT / "protocol.json"


def task_edition() -> str:
    return PROTOCOL.get("task_edition", edition())


def task_pairs(phase: str) -> Any:
    return (
        development_tasks(task_edition())
        if phase == "pilot"
        else confirmation_tasks(task_edition())
    )


def trial_settings(directory: Path) -> TrialSettings | None:
    if edition() != "024":
        return None
    path = directory / "selected-settings.json"
    value = json.loads(path.read_text("utf-8")) if path.exists() else PROTOCOL["stage_limits"]
    return TrialSettings(**value)


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
    modern = edition() == "024"
    request = PROTOCOL["request"]
    if modern and any(
        not model["advertised_context_lengths"]
        or any(
            length < request["num_ctx"] for length in model["advertised_context_lengths"].values()
        )
        for model in manifest["models"]
    ):
        raise ValueError("new context length exceeds or lacks advertised model support")
    profiles = {
        model["tag"]: ModelProfile(
            tag=model["tag"],
            digest=model["digest"],
            think=False,
            thinking_values=tuple(model["supported_thinking_values_advertised"]),
            local_verified=True,
            **(
                {
                    "num_ctx": request["num_ctx"],
                    "num_predict": request["num_predict"],
                    "keep_alive": request["keep_alive"],
                    "request_wall_seconds": request[
                        "qwen_wall_seconds"
                        if model["tag"].startswith("qwen")
                        else "gemma_wall_seconds"
                    ],
                    "trial_wall_seconds": PROTOCOL["trial_limits"][
                        "qwen_wall_seconds"
                        if model["tag"].startswith("qwen")
                        else "gemma_wall_seconds"
                    ],
                }
                if modern
                else {}
            ),
        )
        for model in manifest["models"]
    }
    if set(profiles) != set(PROTOCOL["models"]):
        raise ValueError("preflight model selection differs from the protocol")
    profiles = {name: profiles[name] for name in PROTOCOL["models"]}
    owner = (
        json.loads((args.directory / "private/current-owner.json").read_text("utf-8"))
        if modern
        else None
    )
    limits = (
        Limits(
            global_wall_seconds=PROTOCOL["global_limits"]["wall_seconds"],
            socket_timeout_seconds=180,
            max_response_bytes=65536,
        )
        if not modern
        else Limits(
            global_wall_seconds=172800,
            global_calls=4000,
            global_generated_tokens=4000000,
            global_total_tokens=40000000,
            trial_wall_seconds=7200,
            trial_calls=10,
            trial_total_tokens=122880,
            request_wall_seconds=1800,
            maximum_request_wall_seconds=3600,
            socket_timeout_seconds=3600,
            connect_timeout_seconds=30,
            read_until_deadline=True,
            max_response_bytes=65536,
            max_disk_bytes=4294967296,
        )
    )
    return OllamaClient(
        args.url,
        args.directory / "calls.jsonl",
        run_id=PROTOCOL["protocol_id"],
        freeze_id=sha(protocol_path()),
        profiles=profiles,
        limits=limits,
        disk_root=args.directory,
        **({"server_epoch": owner["server_epoch"], "termination_policy": True} if owner else {}),
    )


def amend_wall(args: argparse.Namespace) -> dict[str, Any]:
    """Explicitly append the authorized wall-only amendment to the original journal."""
    if args.authorization != PROTOCOL["budget_amendment"]["user_authorization"]:
        raise ValueError("amend-wall requires the exact explicit user authorization")
    if not args.amendment_id:
        raise ValueError("amend-wall requires an amendment identity")
    path = args.directory / "calls.jsonl"
    if path.stat().st_size > PROTOCOL["global_limits"]["disk_bytes"]:
        raise ClientBlocked("ledger exceeds disk envelope")
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        raise ClientBlocked("incomplete ledger tail; retain it and do not amend")
    rows = [strict_json(line.decode("utf-8")) for line in raw.splitlines()]
    if any(not isinstance(row, dict) for row in rows):
        raise ClientBlocked("ledger contains a non-object event; retain it and do not amend")
    if not rows or rows[0].get("event") != "config":
        raise ClientBlocked("ledger must retain its original config")
    if any(row.get("event") == "wall_budget_amendment" for row in rows):
        raise ClientBlocked("wall budget amendment is already recorded; no dispatch or reset")
    initial = rows[0]["config"]
    if (
        initial["run_id"] != PROTOCOL["budget_amendment"]["initial_protocol_id"]
        or initial["freeze_id"] != PROTOCOL["budget_amendment"]["initial_protocol_sha256"]
    ):
        raise ClientBlocked("initial protocol identity differs from the retained v1 segment")
    old_client = OllamaClient(
        args.url,
        path,
        run_id=initial["run_id"],
        freeze_id=initial["freeze_id"],
        profiles={name: ModelProfile(**profile) for name, profile in initial["profiles"].items()},
        limits=Limits(**initial["limits"]),
        disk_root=args.directory,
        server_version=initial["server_version"],
    )
    return old_client.amend_global_wall_budget(
        amendment_id=args.amendment_id,
        new_run_id=PROTOCOL["protocol_id"],
        new_freeze_id=sha(ROOT / "protocol.json"),
        authorization=args.authorization,
    )


def guard(args: argparse.Namespace) -> dict[str, Any]:
    if (args.directory / "identity-violations.jsonl").exists():
        raise ClientBlocked("pinned_model_identity_violation: stop new calls")
    if edition() == "024":
        from experiments.ollama.ownership import verify_owned_alive

        owner = json.loads((args.directory / "private/current-owner.json").read_text("utf-8"))
        if args.server_pid != owner["root"]["pid"]:
            raise ClientBlocked("supplied server PID differs from the owned startup record")
        verify_owned_alive(owner)
    observation = resource_gate(
        args.directory,
        server_pid=args.server_pid,
        **(
            {
                "raw_limit_bytes": 4294967296,
                "minimum_disk_free": 5368709120,
                "require_swap_observation": True,
            }
            if edition() == "024"
            else {}
        ),
    )
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
            "execution_protocol_id": PROTOCOL["protocol_id"],
            "formal_freeze_sha256": self.freeze_sha,
            "resources_before": before,
            "inventory_before": inventory,
            "before_sampling_wall_seconds": pre_sampling_wall,
        }
        stop_heartbeat = threading.Event()
        heartbeat_start = time.monotonic()
        budget_before = self.client.summary() if edition() == "024" else {}

        def heartbeat(status: str) -> None:
            # Read no journal while its request lock is held. This observation
            # cannot change the client deadline, budget or inference process.
            if edition() != "024":
                return
            path = self.args.directory / "worker-heartbeat.json"
            temporary = path.with_suffix(".tmp")
            write_json(
                temporary,
                {
                    "phase": self.phase,
                    "current_key": self.trial_key,
                    "request_id": kwargs["request_id"],
                    "status": status,
                    "observed_epoch": time.time(),
                    "request_observed_elapsed_seconds": time.monotonic() - heartbeat_start,
                    "last_completed_request_id": (
                        budget_before.get("completed_request_ids") or [None]
                    )[-1],
                    "budget_snapshot": "audited after the returned receipt"
                    if status == "request_returned"
                    else "audited before this request; not a later settlement",
                    "before_request_remaining": {
                        "calls": self.client.limits.global_calls - budget_before["calls"],
                        "generated_tokens": self.client.limits.global_generated_tokens
                        - budget_before.get(
                            "charged_generated_tokens", budget_before["observed_generated_tokens"]
                        ),
                        "total_tokens": self.client.limits.global_total_tokens
                        - budget_before.get(
                            "charged_total_tokens", budget_before["observed_total_tokens"]
                        ),
                        "wall_seconds": self.client.limits.global_wall_seconds
                        - budget_before.get("campaign_elapsed_seconds", 0),
                    },
                },
            )
            temporary.replace(path)

        def watch() -> None:
            while not stop_heartbeat.wait(15):
                heartbeat("request_waiting")

        heartbeat("request_starting")
        observer = threading.Thread(target=watch, daemon=True)
        observer.start()
        try:
            record = self.client.chat(**kwargs)
        finally:
            stop_heartbeat.set()
            observer.join(timeout=1)
        if edition() == "024":
            budget_before = self.client.summary()
        heartbeat("request_returned")
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
        identity = self.trial_key + "/" + request_id
        record = self.client.record(identity)
        if record is None and identity in self.client.summary()["pending"]:
            record = {
                "request_id": identity,
                "status": "pending_without_receipt",
                "pending": True,
                "unknown_consumption": True,
                "usage": {"total_tokens": None},
            }
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
    tasks = task_pairs(phase)
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
        secondary_steps=2 if phase == "sensitivity-bounded" else 0,
        **({"settings": trial_settings(args.directory)} if edition() == "024" else {}),
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
    elif (
        summary["started_epoch"] is None
        or time.time() - summary["started_epoch"] >= PROTOCOL["global_limits"]["wall_seconds"]
    ):
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
        for task, _gold in confirmation_tasks(task_edition())
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
            if record.get("status") == "loaded":
                # Empty ChatHandler load receipts omit server duration counters.
                # Their full observed wall is a conservative cold-operation
                # bound, charged once per model block, not every generation.
                loads.append(float(wall))
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


def development_forecast_ledger(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep paid development timings across the corrective request namespace."""
    prefix = PROTOCOL.get("request_key_prefix", "")
    return [
        row
        for row in ledger
        if row.get("event") != "response"
        or row["record"]["request_id"]
        .removeprefix(prefix)
        .startswith(("warmup", "scope-v1-warmup", "pilot"))
    ]


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
    remaining = max(
        0.0,
        PROTOCOL["global_limits"]["wall_seconds"]
        - summary.get("campaign_elapsed_seconds", time.time() - start),
    )
    guard(args)
    resource_path = args.directory / "resources.jsonl"
    resources = (
        [json.loads(line) for line in resource_path.read_text("utf-8").splitlines()]
        if resource_path.exists()
        else []
    )
    modern = edition() == "024"
    eligible_ledger = development_forecast_ledger(ledger) if modern else ledger
    forecast = speed_forecast(eligible_ledger, resources, PROTOCOL["models"])
    forecast_known = all(value["per_request_seconds"] is not None for value in forecast.values())
    remaining_calls = PROTOCOL["global_limits"]["calls"] - summary["calls"]
    remaining_generated = (
        PROTOCOL["global_limits"]["generated_tokens"] - summary["charged_generated_tokens"]
    )
    remaining_tokens = PROTOCOL["global_limits"]["total_tokens"] - summary["charged_total_tokens"]
    calls_per_trial = PROTOCOL["trial_limits"]["calls"]
    cap = (
        max(
            asdict(trial_settings(args.directory)).get(name, 0)
            for name in ("reader_cap", "integrator_cap", "reviewer_cap", "repair_cap")
        )
        if modern
        else 512
    )
    ctx = PROTOCOL["request"]["num_ctx"]
    sensitivity_calls_per_model = 8 * 2 * 2 * calls_per_trial if modern else 0
    selected = next(
        (
            n
            for n in PROTOCOL["confirmation_profiles"]
            if forecast_known
            and (n * 3 * calls_per_trial + sensitivity_calls_per_model)
            * sum(value["per_request_seconds"] for value in forecast.values())
            + sum(
                value["once_per_model_load_seconds"]
                for value in forecast.values()
                if value["once_per_model_load_seconds"] is not None
            )
            < 0.9 * remaining
            and (n * 3 * calls_per_trial + sensitivity_calls_per_model) * len(PROTOCOL["models"])
            <= remaining_calls
            and (n * 3 * calls_per_trial + sensitivity_calls_per_model)
            * len(PROTOCOL["models"])
            * cap
            <= remaining_generated
            and (n * 3 * calls_per_trial + sensitivity_calls_per_model)
            * len(PROTOCOL["models"])
            * (ctx + cap)
            <= remaining_tokens
        ),
        0,
    )
    selected_tasks = selected_parent_ids(selected)
    public = [
        asdict(task)
        for task, _gold in confirmation_tasks(task_edition())
        if task.task_id in selected_tasks
    ]
    gold = [
        asdict(score)
        for task, score in confirmation_tasks(task_edition())
        if task.task_id in selected_tasks
    ]
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
        if (
            tracked != path.read_bytes()
            if modern
            else tracked.replace(b"\r\n", b"\n") != path.read_bytes().replace(b"\r\n", b"\n")
        ):
            raise ValueError("freeze requires committed exact harness bytes")
    result = {
        "protocol_id": PROTOCOL["protocol_id"],
        "implementation_commit": commit,
        "candidate_wheel_sha256": sha(wheel),
        "candidate_package_sha256": package_fingerprint(wheel),
        "installed_runtime": installed,
        "manifest_sha256": sha(protocol_path()),
        "protocol_file": protocol_path().name,
        "harness_sha256": harness.hexdigest(),
        "harness_files": code,
        "preflight_sha256": sha(args.directory / "preflight/manifest.json"),
        "public_tasks_sha256": sha(args.directory / "frozen-public-tasks.json"),
        "evaluation_only_gold_sha256": sha(args.directory / "evaluation-only-gold.json"),
        "selected_parent_count": selected,
        "excluded_parent_ids": [
            task.task_id
            for task, _gold in confirmation_tasks(task_edition())
            if task.task_id not in selected_tasks
        ],
        "exclusion_reason": "Predeclared balanced profile chosen from speed/resource budgets",
        "remaining_wall_at_freeze_seconds": remaining,
        "original_first_reservation_epoch": start,
        "ledger_sha256_at_freeze": sha(args.directory / "calls.jsonl"),
        "remaining_calls_at_freeze": remaining_calls,
        "remaining_generated_tokens_at_freeze": remaining_generated,
        "remaining_total_tokens_at_freeze": remaining_tokens,
        "speed_only_profile_forecast_request_seconds": forecast,
        "planned_trial_keys": schedule(selected_tasks, "confirmation"),
        "planned_auxiliary_source_keys": []
        if modern
        else [
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
    if modern:
        sensitivity_tasks = [
            task_id for task_id in selected_tasks if int(task_id.rsplit("-", 1)[1]) in (1, 6)
        ]
        result["planned_sensitivity_keys"] = [
            {**item, "phase": phase}
            for phase in ("sensitivity-strict", "sensitivity-bounded")
            for item in schedule(sensitivity_tasks, phase)
            if item["arm"] in ("A", "B")
        ]
        result["selected_settings"] = asdict(trial_settings(args.directory))
        result["selected_settings_sha256"] = sha(args.directory / "selected-settings.json")
        result["trial_budget"] = trial_settings(args.directory).budget.model_dump(mode="json")
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
        or sha(protocol_path()) != frozen["manifest_sha256"]
        or (
            edition() == "024"
            and sha(args.directory / "selected-settings.json") != frozen["selected_settings_sha256"]
        )
    ):
        raise ValueError("frozen implementation or protocol changed; retain records and stop")
    halted = None
    auxiliary_sources = set(frozen["planned_auxiliary_source_keys"])
    for index, item in enumerate(frozen["planned_trial_keys"]):
        if index % 3 == 0 and halted is None:
            summary = client.summary()
            # Auxiliary callbacks consume unused calls inside the original six-call trials.
            maximum_calls = 3 * PROTOCOL["trial_limits"]["calls"]
            output_cap = PROTOCOL["request"]["num_predict"]
            total_cap = PROTOCOL["request"]["num_ctx"] + output_cap
            try:
                guard(args)
                if (
                    summary["blocked"]
                    or summary["started_epoch"] is None
                    or summary.get(
                        "campaign_elapsed_seconds", time.time() - summary["started_epoch"]
                    )
                    >= PROTOCOL["global_limits"]["wall_seconds"]
                    or summary["calls"] + maximum_calls > PROTOCOL["global_limits"]["calls"]
                    or summary.get("charged_generated_tokens", summary.get("generated_tokens"))
                    + maximum_calls * output_cap
                    > PROTOCOL["global_limits"]["generated_tokens"]
                    or summary.get("charged_total_tokens", summary.get("total_tokens"))
                    + maximum_calls * total_cap
                    > PROTOCOL["global_limits"]["total_tokens"]
                ):
                    raise ClientBlocked("whole parent block cannot fit remaining envelope")
                append(
                    args.directory / "blocks.jsonl",
                    {
                        "event": "reserve_parent_block",
                        "keys": [x["key"] for x in frozen["planned_trial_keys"][index : index + 3]],
                        "maximum_calls": maximum_calls,
                        "maximum_total_tokens": maximum_calls * total_cap,
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
            if edition() == "024" and halted == "pending_or_unknown_consumption":
                # Frozen planned-but-unstarted keys remain reconstructible by
                # analyze. Do not seal them as terminal failures: after verified
                # termination a new epoch may execute those unstarted keys.
                break
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
    if edition() == "024":
        for item in frozen["planned_sensitivity_keys"]:
            if client.summary()["blocked"]:
                break
            execute(
                args,
                client,
                item["phase"],
                {k: v for k, v in item.items() if k != "phase"},
                sha(args.freeze),
            )


def warmup(args: argparse.Namespace, client: OllamaClient) -> None:
    """Cold preload followed by two real reader/integrator/reviewer rounds."""
    from experiments.ollama.tasks import Document

    settings = trial_settings(args.directory)
    task, _ = development_tasks(task_edition())[0]
    prefix = "warmup" if args.development_cycle == 1 else f"warmup-cycle-{args.development_cycle}"
    if task_edition() == "024r2":
        prefix = "scope-v1-" + prefix
    prefix = PROTOCOL.get("request_key_prefix", "") + prefix
    for model in PROTOCOL["models"]:
        preload_id = prefix + "/" + model + "/preload"
        if client.record(preload_id) is None:
            record = BoundClient(client, args, "preload", prefix + "/" + model).chat(
                model=model,
                trial_id="unused",
                request_id="preload",
                messages=[],
                schema={"type": "object"},
                seed=PROTOCOL["development_seed"],
                preload=True,
                wall_seconds=PROTOCOL["request"]["preload_wall_seconds"],
                num_predict=1,
            )
            if record["status"] != "loaded":
                raise ClientBlocked("preload did not produce a known final load receipt")
        for repetition in range(2):
            chosen = task
            if repetition == 1:
                first = task.documents[0]
                long = Document(
                    first.source_id,
                    first.owner,
                    first.topic,
                    first.version,
                    first.origin,
                    first.text + ("参考メモ: 備品の色は判定条件に含まれない。\n" * 100),
                )
                second = task.documents[1]
                condition = "要件N" if task_edition() == "024r2" else "条件Q"
                changed = replace(
                    second, text=second.text.replace(condition + "は真", condition + "は偽")
                )
                chosen = replace(task, documents=(long, changed, *task.documents[2:]))
            extraction = answer = None
            for stage, model_type in (
                ("read", Extraction),
                ("integrate", Answer),
                ("review", CompactReview),
            ):
                identity = f"{prefix}/{model}/round-{repetition}/{stage}"
                existing = client.record(identity + "/call")
                messages = (
                    extraction_messages(chosen, chosen.documents[0])
                    if stage == "read"
                    else integration_messages(
                        chosen, chosen.documents, (extraction,) if extraction else ()
                    )
                    if stage == "integrate"
                    else review_messages(chosen, chosen.documents, answer or {}, compact=True)
                )
                record = existing or BoundClient(client, args, "warmup", identity).chat(
                    model=model,
                    trial_id=identity,
                    request_id="call",
                    messages=messages,
                    schema=model_type.model_json_schema(),
                    seed=PROTOCOL["development_seed"],
                    num_predict=settings.cap(stage),
                    metadata={"stage": stage, "warm_round": repetition},
                    validator=lambda p, typ=model_type: validate_output(p, typ),
                )
                if stage == "read":
                    extraction = record.get("parsed")
                elif stage == "integrate":
                    answer = record.get("parsed")
                print(
                    json.dumps(
                        {
                            "phase": "warmup",
                            "model": model,
                            "stage": stage,
                            "status": record["status"],
                            "wall": record["client_wall_seconds"],
                        }
                    ),
                    flush=True,
                )
                if record["unknown_consumption"]:
                    raise ClientBlocked("warm request has unknown consumption")


def calibrate(args: argparse.Namespace, client: OllamaClient) -> dict[str, Any]:
    from experiments.ollama.tasks import calibration_tasks

    bank = []
    tasks = calibration_tasks()
    kinds = (
        "correct_yes",
        "correct_no",
        "grounded_unknown",
        "wrong_answer",
        "fake_quote",
        "stale_version",
        "false_complete_insufficient",
        "irrelevant_quote",
    )
    for index in range(24):
        family = ("L1", "L2", "L3", "L4")[index // 6]
        kind = kinds[index % len(kinds)]
        number = (
            6
            if kind in ("grounded_unknown", "false_complete_insufficient")
            else 2
            if kind in ("correct_no", "stale_version")
            else 1
        )
        task, gold = next(
            (t, g) for t, g in tasks if t.family == family and t.task_id.endswith("-" + str(number))
        )
        answer = {
            "decision": gold.decision,
            "answer": "公開規則に基づく結論。",
            "reasoning": "現行規則と関連記録を用いた。",
            "citations": [
                {
                    "source_id": w.source_id,
                    "version": task.document(w.source_id).version,
                    "quote": w.quote,
                }
                for w in gold.witnesses
            ],
        }
        valid = kind.startswith("correct") or kind == "grounded_unknown"
        if kind in ("wrong_answer", "false_complete_insufficient"):
            answer["decision"] = "yes" if gold.decision != "yes" else "no"
        elif kind == "fake_quote":
            answer["citations"][0]["quote"] = "存在しない架空の引用。"
        elif kind == "stale_version":
            answer["citations"][0]["version"] = "0"
        elif kind == "irrelevant_quote":
            answer["citations"] = [
                {
                    "source_id": task.documents[-1].source_id,
                    "version": task.documents[-1].version,
                    "quote": task.documents[-1].text[-1:],
                }
            ]
        bank.append(
            {
                "case_id": index,
                "kind": kind,
                "public_task": asdict(task),
                "answer": answer,
                "evaluation_only_expected_accept": valid,
            }
        )
    write_json(args.directory / "calibration-answer-bank.json", bank)
    results = []
    for model in PROTOCOL["models"]:
        for schema_name, typ in (("old", Review), ("compact", CompactReview)):
            for cap in (512, 2048):
                for case in bank:
                    task = next(t for t, g in tasks if t.task_id == case["public_task"]["task_id"])
                    calibration_prefix = (
                        "calibration"
                        if args.development_cycle == 1
                        else f"calibration-cycle-{args.development_cycle}"
                    )
                    identity = f"{calibration_prefix}/{model}/{schema_name}/{cap}/{case['case_id']}"
                    record = client.record(identity + "/call")
                    if record is None:
                        record = BoundClient(client, args, "calibration", identity).chat(
                            model=model,
                            trial_id=identity,
                            request_id="call",
                            messages=review_messages(
                                task,
                                task.documents,
                                case["answer"],
                                compact=schema_name == "compact",
                            ),
                            schema=typ.model_json_schema(),
                            seed=PROTOCOL["development_seed"],
                            num_predict=cap,
                            metadata={
                                "stage": "review",
                                "case_id": case["case_id"],
                                "schema": schema_name,
                                "cap": cap,
                            },
                            validator=lambda p, typ=typ: validate_output(p, typ),
                        )
                    result = {
                        "model": model,
                        "schema": schema_name,
                        "cap": cap,
                        "case_id": case["case_id"],
                        "kind": case["kind"],
                        "status": record["status"],
                        "syntax_valid": record["status"] == "ok",
                        "reviewer_status": (record.get("parsed") or {}).get("status"),
                        "expected_accept": case["evaluation_only_expected_accept"],
                        "request_id": identity + "/call",
                        "length_fault": record["status"] == "length",
                        "client_wall_seconds": record["client_wall_seconds"],
                        "known_usage": record["unknown_consumption"] is False,
                    }
                    result["false_pass"] = (
                        result["reviewer_status"] == "PASS" and not result["expected_accept"]
                    )
                    results.append(result)
                    write_json(args.directory / "calibration-results.json", results)
                    print(json.dumps(result), flush=True)
                    if record["unknown_consumption"]:
                        raise ClientBlocked("calibration request has unknown consumption")
    aggregates = []
    for model in PROTOCOL["models"]:
        for schema_name in ("old", "compact"):
            for cap in (512, 2048):
                subset = [
                    r
                    for r in results
                    if (r["model"], r["schema"], r["cap"]) == (model, schema_name, cap)
                ]
                aggregates.append(
                    {
                        "model": model,
                        "schema": schema_name,
                        "cap": cap,
                        "N": len(subset),
                        "syntax_valid": sum(r["syntax_valid"] for r in subset),
                        "last20_valid": sum(r["syntax_valid"] for r in subset[-20:]),
                        "false_pass": sum(r["false_pass"] for r in subset),
                        "length_faults": sum(r["length_fault"] for r in subset),
                        "correct_unknown_cases": sum(
                            r["kind"] == "grounded_unknown" for r in subset
                        ),
                        "correct_unknown_accepted": sum(
                            r["kind"] == "grounded_unknown" and r["reviewer_status"] == "PASS"
                            for r in subset
                        ),
                        "mean_client_wall_seconds": sum(r["client_wall_seconds"] for r in subset)
                        / len(subset)
                        if subset
                        else None,
                    }
                )
    # Same compact schema/cap in every arm/model. Outcome comparisons never
    # enter this development-only syntax, false-PASS and resource choice.
    choices = [
        (cap, [r for r in aggregates if r["schema"] == "compact" and r["cap"] == cap])
        for cap in (512, 2048)
    ]
    qualified = [(cap, rows) for cap, rows in choices if all(r["last20_valid"] >= 19 for r in rows)]
    selected = (
        min(qualified, key=lambda x: (sum(r["false_pass"] for r in x[1]), x[0]))[0]
        if qualified
        else 2048
    )
    settings = {**PROTOCOL["stage_limits"], "reviewer_cap": selected}
    write_json(args.directory / "selected-settings.json", settings)
    summary = {
        "aggregates": aggregates,
        "selected_settings": settings,
        "syntax_floor_met": bool(qualified),
        "choice_used_A_minus_B": False,
    }
    write_json(args.directory / "calibration-summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    global PROTOCOL, PROTOCOL_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "preflight",
            "backend-smoke",
            "pilot",
            "amend-wall",
            "freeze",
            "live",
            "resume",
            "analyze",
            "warmup",
            "calibrate",
            "status",
            "recover-receipt",
            "recover-server",
        ),
    )
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--server-pid", type=int)
    parser.add_argument("--server-log", type=Path)
    parser.add_argument("--authorization")
    parser.add_argument("--amendment-id")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--protocol", type=Path, default=ROOT / "protocol-v0.2.4-r2.json")
    parser.add_argument("--request-id")
    parser.add_argument("--development-cycle", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--freeze", type=Path, default=ROOT / "results/freeze-v0.2.4-r2.json")
    parser.add_argument("--output", type=Path, default=ROOT / "results/v0.2.4")
    args = parser.parse_args(argv)
    PROTOCOL_PATH = args.protocol.resolve(strict=True)
    PROTOCOL = json.loads(PROTOCOL_PATH.read_text("utf-8"))
    if edition() == "024" and (args.directory / "private/current-owner.json").exists():
        owner = json.loads((args.directory / "private/current-owner.json").read_text("utf-8"))
        if args.server_pid is None:
            args.server_pid = owner["root"]["pid"]
        if args.server_log is None:
            args.server_log = Path(owner["server_log"])
    if args.command == "amend-wall":
        if not args.authorization or not args.amendment_id:
            parser.error("amend-wall requires --authorization and --amendment-id")
        print(json.dumps(amend_wall(args), ensure_ascii=False))
        return 0
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
    try:
        client = client_for(args)
    except ClientBlocked as error:
        if args.command != "status" or "ledger lock" not in str(error):
            raise
        # Observation never interrupts the owner or takes a dispatch lock. A
        # bounded tail describes the last durable event; it is not a complete
        # budget audit and cannot authorize any request.
        path = args.directory / "calls.jsonl"
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - 1048576))
            tail = handle.read(1048576)
        lines = tail.splitlines()
        if not tail.endswith(b"\n"):
            lines = lines[:-1]
        last = strict_json(lines[-1].decode("utf-8")) if lines else {}
        print(
            json.dumps(
                {
                    "controller_busy": True,
                    "observation_only": True,
                    "last_complete_event": last.get("event"),
                    "request_id": last.get("request_id"),
                    "ledger_bytes": size,
                    "budget_audited": False,
                }
            )
        )
        return 0
    if args.command == "status":
        print(json.dumps({k: v for k, v in client.summary().items() if k != "responses"}))
        return 0
    if args.command == "recover-receipt":
        if not args.request_id:
            parser.error("recover-receipt requires --request-id")
        reserve = next(
            r
            for r in client._rows()
            if r.get("event") == "reserve" and r["request_id"] == args.request_id
        )
        title = reserve["request"]["format"].get("title")
        typ = {t.__name__: t for t in (Extraction, Answer, Review, CompactReview)}.get(title)
        print(
            json.dumps(
                client.recover_receipt(
                    args.request_id, validator=(lambda p: validate_output(p, typ)) if typ else None
                )
            )
        )
        return 0
    if args.command == "recover-server":
        from experiments.ollama.ownership import start_owned, verify_and_stop_owned

        pending = client.summary()["pending"]
        if len(pending) != 1:
            raise ClientBlocked("server recovery requires exactly one frozen uncertain request")
        owner = json.loads((args.directory / "private/current-owner.json").read_text("utf-8"))
        proof = verify_and_stop_owned(owner)
        write_json(args.directory / ("termination-" + owner["server_epoch"] + ".json"), proof)
        client.terminate_unmetered(pending[0], proof)
        new_owner = start_owned(args.directory, Path(owner["root"]["executable"]))
        client.advance_server_epoch(new_owner["server_epoch"])
        print(
            json.dumps(
                {
                    "terminated_unmetered": pending,
                    "new_server_pid": new_owner["root"]["pid"],
                    "actual_usage": None,
                }
            )
        )
        return 0
    if args.command == "warmup":
        warmup(args, client)
    elif args.command == "calibrate":
        print(json.dumps(calibrate(args, client)))
    elif args.command == "backend-smoke":
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
        for item in schedule(
            [task.task_id for task, _gold in development_tasks(task_edition())], "pilot"
        ):
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
