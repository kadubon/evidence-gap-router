"""One serial, preregistered controller for the v0.2.2 local experiment."""

from __future__ import annotations

import argparse
import json
import random
import time
from collections import Counter
from pathlib import Path

from benchmarks.harness import environment, trial, validate_freeze
from benchmarks.helper_scaling_022 import cases, generated_confirmation
from benchmarks.scaling import frozen_metadata
from benchmarks.scaling import worker as proof_worker
from benchmarks.tasks import Task, digest, generate, manifest
from benchmarks.worker_limits import run_worker


def specifications() -> tuple[dict, ...]:
    """Enumerate every key before observing outcomes; shuffle within matched blocks."""
    config = manifest()
    rng = random.Random(config["execution_order"]["seed"])
    output = []

    def block(items):
        rng.shuffle(items)
        output.extend(items)

    versions = [config["baseline_version"], config["candidate_version"]]
    for task in generate("regression"):
        methods = list(config["methods"])
        if task.family in config["direct_pipeline_reference_families"]:
            methods.append("direct-pipeline")
        block(
            [
                {
                    "phase": "regression",
                    "kind": "method",
                    "version": versions[1],
                    "task": task.document(),
                    "variant": "original",
                    "method": method,
                    "seed": config["random_seeds"][0] if method == "random-feasible" else 0,
                }
                for method in methods
            ]
        )
    block([{"phase": "audit", "kind": "audit", "version": version} for version in versions])
    for graph in config["scaling"]["graphs"]:
        for size in config["scaling"]["sizes"]:
            for checkers in config["scaling"]["checkers"]:
                for mode in ("time", "count", "memory"):
                    block(
                        [
                            {
                                "phase": "scaling",
                                "kind": "proof",
                                "version": version,
                                "graph": graph,
                                "size": size,
                                "checkers": checkers,
                                "mode": mode,
                            }
                            for version in versions
                        ]
                    )
    for case in cases(config["helper_scaling"]):
        for mode in config["helper_scaling"]["modes"]:
            block(
                [
                    {
                        "phase": "scaling",
                        "kind": "helper",
                        "version": version,
                        "case": case,
                        "mode": mode,
                    }
                    for version in versions
                ]
            )
    for case in generated_confirmation(
        config["confirmation"]["seed"], config["confirmation"]["parents"]
    ):
        block(
            [
                {
                    "phase": "confirmation",
                    "kind": "helper",
                    "version": version,
                    "case": case,
                    "mode": "semantic",
                }
                for version in versions
            ]
        )
    return tuple(
        {**spec, "sequence_index": index, "spec_sha256": digest(json.dumps(spec, sort_keys=True))}
        for index, spec in enumerate(output)
    )


def execute(spec: dict, freeze_path: Path) -> dict:
    cold_begin = time.perf_counter()
    import evidence_gap_router

    cold_import = time.perf_counter() - cold_begin
    frozen = validate_freeze(freeze_path, phase="confirmation")
    if environment()["package"] != spec["version"]:
        raise ValueError("Worker interpreter does not contain the specified version")
    if spec["kind"] == "method":
        result = trial(Task(**spec["task"]), spec["variant"], spec["method"], spec["seed"], frozen)
    elif spec["kind"] == "proof":
        result = proof_worker(spec["size"], spec["checkers"], spec["graph"], spec["mode"])
    elif spec["kind"] == "helper":
        from benchmarks.helper_scaling_022 import worker

        result = worker(spec["case"], spec["mode"])
    else:
        from benchmarks.audit_022 import run_audit

        result = run_audit()
    if "cold_sdk_import_seconds" in result:
        result["cached_sdk_import_lookup_seconds"] = result.pop("cold_sdk_import_seconds")
    return {
        **result,
        **frozen_metadata(frozen),
        "spec": spec,
        "cold_sdk_import_seconds": cold_import,
        "cold_import_scope": (
            "First SDK import before freeze checks; other harness imports and "
            "interpreter startup remain in whole-worker time"
        ),
        "sdk_import_validated": evidence_gap_router.__version__ == spec["version"],
    }


def unavailable_row(spec: dict, frozen: dict, reason: str) -> dict:
    old = spec["version"] == manifest()["baseline_version"]
    result = {
        "spec": spec,
        "status": "unexecuted",
        "worker_status": "unexecuted",
        "stop_reason": reason,
        "runner_stop": None,
        "domain_stop": None,
        "oracle": None,
        "false_satisfied": None,
        "callbacks": None,
        "verifications": None,
        "state": None,
        "trace": [],
        "timeout": False,
        "exception": None,
        "environment": {
            **frozen["environment"],
            "package": spec["version"],
            "package_import": None,
        },
        "implementation_commit": frozen["implementation_commit"],
        "runtime_commit": frozen["baseline_runtime_commit"]
        if old
        else frozen["implementation_commit"],
        "wheel_sha256": frozen["baseline_wheel_sha256"] if old else frozen["wheel_sha256"],
        "package_sha256": frozen["baseline_package_sha256"]
        if old
        else frozen["candidate_package_sha256"],
        "manifest_sha256": frozen["manifest_sha256"],
    }
    if spec["kind"] == "method":
        result.update(
            task=spec["task"],
            task_id=spec["task"]["id"],
            method=spec["method"],
            variant=spec["variant"],
            random_seed=spec["seed"],
            reference_only=spec["method"] == "direct-pipeline",
        )
    return result


def run(output: Path, freeze_path: Path, interpreters: dict[str, str]) -> None:
    from benchmarks.worker_limits import parent_resources

    if output.exists():
        raise ValueError("Result directory exists; preserve prior runs")
    frozen = validate_freeze(freeze_path, phase="confirmation")
    specs = specifications()
    config, budgets = manifest(), manifest()["budgets"]
    output.mkdir(parents=True)
    (output / "execution-manifest.json").write_text(
        json.dumps(
            {
                "protocol": config["protocol"],
                "freeze_sha256": digest(freeze_path.read_bytes()),
                "specifications": specs,
                "interpreters": interpreters,
                "budgets": budgets,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    started, parent_cpu_start = time.perf_counter(), time.process_time()
    phase_started, phase_parent_cpu_started, phase_cpu = {}, {}, Counter()
    worker_cpu, statuses, unknown_cpu, unknown_memory = 0.0, Counter(), 0, 0
    with (output / "raw.jsonl").open("x", encoding="utf-8") as stream:
        for index, spec in enumerate(specs):
            phase = spec["phase"]
            phase_started.setdefault(phase, time.perf_counter())
            phase_parent_cpu_started.setdefault(phase, time.process_time())
            _, parent_peak = parent_resources()
            remaining = min(
                budgets["overall_wall_seconds"] - (time.perf_counter() - started),
                budgets[f"{phase}_wall_seconds"] - (time.perf_counter() - phase_started[phase]),
            )
            parent_cpu = time.process_time() - parent_cpu_start
            cpu_remaining = min(
                budgets["overall_cpu_seconds"] - worker_cpu - parent_cpu,
                budgets[f"{phase}_cpu_seconds"]
                - phase_cpu[phase]
                - (time.process_time() - phase_parent_cpu_started[phase]),
            )
            reason = None
            if parent_peak is None:
                reason = "parent_working_set_unavailable"
            elif parent_peak > budgets["parent_working_set_bytes"]:
                reason = "parent_memory_budget_exhausted"
            elif remaining <= 0 or cpu_remaining <= 0:
                reason = "experiment_budget_exhausted"
            elif unknown_cpu:
                reason = "whole_worker_cpu_unavailable"
            elif unknown_memory:
                reason = "whole_worker_memory_unavailable"
            row = unavailable_row(spec, frozen, reason or "worker_not_completed")
            if reason is None:
                observation = run_worker(
                    [
                        interpreters[spec["version"]],
                        "-m",
                        "benchmarks.controller_022",
                        "worker",
                        "--freeze",
                        str(freeze_path),
                        "--spec-json",
                        json.dumps(spec),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    wall_limit_seconds=min(budgets["per_worker_wall_seconds"], remaining),
                    cpu_limit_seconds=min(budgets["per_worker_cpu_seconds"], cpu_remaining),
                    memory_limit_bytes=budgets["per_worker_memory_bytes"],
                )
                status = observation["worker_status"]
                observation_complete = False
                if observation["stdout"].strip():
                    try:
                        parsed = json.loads(observation["stdout"])
                        if not isinstance(parsed, dict) or parsed.get("spec") != spec:
                            raise ValueError("Worker output does not match the preregistered key")
                        row = parsed
                        observation_complete = True
                    except (ValueError, TypeError) as error:
                        if status == "completed":
                            status = "exception"
                        row["exception"] = f"Worker output invalid: {error}"
                elif status == "completed":
                    status = "exception"
                    row["exception"] = "Worker completed without an observation"
                row.update({k: v for k, v in observation.items() if k not in {"stdout", "stderr"}})
                row["worker_status"] = status
                row["stderr"] = observation["stderr"]
                if status != "completed":
                    row["worker_stdout"] = observation["stdout"]
                    row.update(
                        status=status,
                        timeout=status == "timeout",
                        right_censored=status in {"timeout", "resource_limit"},
                        stop_reason=f"worker_{status}",
                    )
                    if not observation_complete:
                        row["trace_unavailable_reason"] = (
                            "Worker did not return a complete observation"
                        )
                row["observation_complete"] = observation_complete
                value = observation["whole_worker_cpu_seconds"]
                if value is None:
                    unknown_cpu += 1
                else:
                    worker_cpu += value
                    phase_cpu[phase] += value
                if observation["peak_worker_memory_bytes"] is None:
                    unknown_memory += 1
            row["parent_peak_working_set_bytes"] = parent_peak
            statuses[(phase, row["worker_status"])] += 1
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
            stream.flush()
            if (index + 1) % 20 == 0 or index + 1 == len(specs):
                print(
                    json.dumps(
                        {
                            "completed_keys": index + 1,
                            "total_keys": len(specs),
                            "phase": phase,
                            "wall_seconds": time.perf_counter() - started,
                            "worker_cpu_seconds": worker_cpu,
                        }
                    ),
                    flush=True,
                )
    summary = {
        "protocol": config["protocol"],
        "requested_keys": len(specs),
        "statuses": [
            {"phase": phase, "worker_status": status, "count": count}
            for (phase, status), count in sorted(statuses.items())
        ],
        "wall_seconds": time.perf_counter() - started,
        "worker_cpu_seconds": worker_cpu,
        "parent_cpu_seconds": time.process_time() - parent_cpu_start,
        "unknown_worker_cpu_rows": unknown_cpu,
        "unknown_worker_memory_rows": unknown_memory,
        "phase_worker_cpu_seconds": dict(phase_cpu),
        "raw_sha256": digest((output / "raw.jsonl").read_bytes()),
        "execution_manifest_sha256": digest((output / "execution-manifest.json").read_bytes()),
        "freeze_sha256": digest(freeze_path.read_bytes()),
    }
    (output / "execution-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("--spec-json", required=True)
    worker.add_argument("--freeze", type=Path, required=True)
    controller = commands.add_parser("run")
    controller.add_argument("--freeze", type=Path, required=True)
    controller.add_argument("--output", type=Path, required=True)
    controller.add_argument("--old-python", required=True)
    controller.add_argument("--new-python", required=True)
    args = parser.parse_args()
    if args.command == "worker":
        print(json.dumps(execute(json.loads(args.spec_json), args.freeze), ensure_ascii=True))
    else:
        config = manifest()
        run(
            args.output,
            args.freeze,
            {
                config["baseline_version"]: args.old_python,
                config["candidate_version"]: args.new_python,
            },
        )


if __name__ == "__main__":
    main()
