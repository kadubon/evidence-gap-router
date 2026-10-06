"""Separate-process dependency graph counting and uninstrumented warm timings."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

from benchmarks.harness import environment, validate_freeze
from benchmarks.tasks import digest, manifest


def graph_state(size: int, checkers: int, graph: str):
    import evidence_gap_router as s

    identifiers = tuple(f"v{i}" for i in range(checkers))
    obligations = tuple(
        s.Obligation(
            id=f"o{i}",
            scope="scaling",
            description="Bound raw integer",
            acceptance="value >= 0 with finite dependencies",
            required_verifiers=identifiers,
        )
        for i in range(size)
    )
    evidence = tuple(
        s.Evidence(
            id=f"e{i}",
            obligation_id=f"o{i}",
            scope="scaling",
            digest=digest(str(i)),
            content=str(i),
            producer="collector",
            source=f"origin{i}",
            provenance_group=f"origin{i}",
        )
        for i in range(size)
    )
    state = s.State(obligations=obligations, evidence=evidence)
    registration = s.HandlerRegistration(
        handler_id="check",
        roles=("verify",),
        checkers=tuple(s.CheckerPermission(checker_id=v) for v in identifiers),
    )
    policy = s.Policy(
        trusted_verifiers=identifiers, handlers=(registration,), max_pending_verifications=10000
    )
    checks = []
    edges = []
    for i, e in enumerate(evidence):
        if graph == "chain":
            parents = [i - 1] if i else []
        elif graph == "diamond":
            parents = sorted(set([max(0, i - 1), max(0, i - 2)])) if i else []
        elif graph == "branches":
            parents = [0] if i else []
        elif graph == "cycle":
            parents = [(i - 1) % size]
        else:
            raise ValueError("unknown graph")
        edges.extend((i, j) for j in parents)
        dependencies = tuple(
            s.DependencyRequirement(
                evidence_id=f"e{j}", obligation_id=f"o{j}", scope="scaling", requirement="verified"
            )
            for j in parents
        )
        for v in identifiers:
            action = s.ActionCandidate(
                id=f"a{i}{v}",
                obligation_id=e.obligation_id,
                scope="scaling",
                kind="verify",
                handler_id="check",
                target_evidence_id=e.id,
                target_digest=e.digest,
                checker_id=v,
                dependencies=dependencies,
                resources=s.Resources(actions=1, verifications=1),
            )
            checks.append(
                s.CheckResult(
                    id=f"c{i}{v}",
                    obligation_id=e.obligation_id,
                    scope="scaling",
                    target_digest=e.digest,
                    verifier_id=v,
                    status="PASS",
                    reason=f"parsed raw integer {int(e.content)} >= 0",
                    basis=s.make_basis(state, action),
                )
            )
    state = s.State(obligations=obligations, evidence=evidence, checks=tuple(checks))
    return state, s.Budget(limits=s.Resources()), policy, edges


def reference(edges: list[tuple[int, int]], size: int) -> bool:
    """Restricted seeds: identical parents for all checkers, no grounded alternative."""
    parents = {i: [] for i in range(size)}
    for child, parent in edges:
        parents[child].append(parent)
    memo = {}

    def valid(node, path):
        if node in path:
            return False
        if node in memo:
            return memo[node]
        result = all(valid(parent, path | {node}) for parent in parents[node])
        memo[node] = result
        return result

    return all(valid(i, set()) for i in range(size))


def worker(size: int, checkers: int, graph: str, mode: str) -> dict:
    from benchmarks.compatibility import require_original_sdk

    require_original_sdk()
    import evidence_gap_router as s
    import evidence_gap_router.router as router

    total = time.perf_counter()
    if mode == "memory":
        tracemalloc.start()
    begin = time.perf_counter()
    state, budget, policy, edges = graph_state(size, checkers, graph)
    construction = time.perf_counter() - begin
    begin = time.perf_counter()
    raw = s.dump_json(state)
    serialization = time.perf_counter() - begin
    begin = time.perf_counter()
    assert s.load_json(raw, s.State) == state
    snapshot_load = time.perf_counter() - begin
    expected = reference(edges, size)
    row = {
        "question": "Q3",
        "environment": environment(),
        "graph": graph,
        "size": size,
        "checkers": checkers,
        "mode": mode,
        "construction_seconds": construction,
        "serialization_seconds": serialization,
        "snapshot_load_seconds": snapshot_load,
        "snapshot_bytes": len(raw.encode()),
        "plan_timing_scope": (
            "Complete public plan including evaluation/index construction and dependency truth; "
            "no prebuilt or cross-call cache omitted."
        ),
        "reference_satisfied": expected,
        "reference_contract": (
            "Identical prerequisite graph for every required checker; all finite raw "
            "integers valid/current, no alternative grounded check or negative record. "
            "Pure ungrounded cycles cannot establish authority. General cyclic "
            "alternatives and negative dependency semantics belong to runtime regressions."
        ),
        "seed_record_contract": (
            "Input-only scaling graph with explicit finite PASS seed records; "
            "no callbacks or free initialization hidden in Q2."
        ),
        "timeout": False,
        "exception": None,
    }
    if mode == "count":
        counters = {}
        originals = []
        if hasattr(router, "_Evaluation"):
            for name in (
                "_base_check",
                "_evaluate_check_truth",
                "_evaluate_target_truth",
                "_compute_check",
            ):
                original = getattr(router._Evaluation, name)
                counters[name] = 0

                def counted(*args, _name=name, _original=original, **kwargs):
                    counters[_name] += 1
                    return _original(*args, **kwargs)

                originals.append((router._Evaluation, name, original))
                setattr(router._Evaluation, name, counted)
            instrument = "indexed base checks, worklist check/target steps, final memo lookups"
        else:
            original = router._trusted_check
            counters["_trusted_check"] = 0

            def counted(*args, **kwargs):
                counters["_trusted_check"] += 1
                return original(*args, **kwargs)

            originals.append((router, "_trusted_check", original))
            router._trusted_check = counted
            instrument = "recursive _trusted_check entries (different work unit)"
        try:
            decision = s.plan(state, (), budget, policy)
        finally:
            for owner, name, original in originals:
                setattr(owner, name, original)
        row.update(
            {
                "diagnostic_counts": counters,
                "recorded_checks": len(state.checks),
                "verified_dependency_edges": len(edges) * checkers,
                "instrument": instrument,
                "work_unit_limitation": (
                    "Method-specific diagnostics, no universal count speed ratio."
                ),
                "actual_satisfied": decision.stop_reason == "satisfied",
            }
        )
    elif mode == "memory":
        decision = s.plan(state, (), budget, policy)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        row.update(
            {
                "peak_traced_python_allocation_bytes": peak,
                "actual_satisfied": decision.stop_reason == "satisfied",
                "measurement": "Separate single replay with tracemalloc; not RSS or timing.",
            }
        )
    else:
        repeats = manifest()["scaling"]["warm_repeats"]
        s.plan(state, (), budget, policy)
        wall = []
        cpu = []
        for _ in range(repeats):
            start = time.perf_counter()
            cpu_start = time.process_time()
            decision = s.plan(state, (), budget, policy)
            wall.append(time.perf_counter() - start)
            cpu.append(time.process_time() - cpu_start)
        ordered = sorted(wall)
        row.update(
            {
                "warmup": 1,
                "repeats": repeats,
                "wall_samples": wall,
                "cpu_samples": cpu,
                "plan_median_seconds": statistics.median(wall),
                "plan_p95_seconds": ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))],
                "plan_cpu_median_seconds": statistics.median(cpu),
                "actual_satisfied": decision.stop_reason == "satisfied",
            }
        )
    row["reference_agrees"] = row["actual_satisfied"] == expected
    row["worker_end_to_end_seconds"] = time.perf_counter() - total
    return row


def frozen_metadata(frozen: dict) -> dict:
    measured = environment()
    old = measured["package"] == manifest()["baseline_version"]
    return {
        "environment": measured,
        "implementation_commit": frozen.get("implementation_commit"),
        "harness_commit": frozen.get("implementation_commit"),
        "runtime_commit": frozen.get("baseline_runtime_commit" if old else "implementation_commit"),
        "wheel_sha256": frozen.get("baseline_wheel_sha256" if old else "wheel_sha256"),
        "package_sha256": frozen.get(
            "baseline_package_sha256" if old else "candidate_package_sha256"
        ),
        "manifest_sha256": digest(Path(__file__).with_name("protocol.json").read_bytes()),
    }


def run(output: Path, python: str, *, smoke: bool = False, freeze_path: Path | None = None):
    if output.exists():
        raise ValueError("Scaling results already exist")
    protocol = manifest()["scaling"]
    started = time.perf_counter()
    metadata_command = [
        python,
        "-c",
        (
            "import json,sys; from pathlib import Path; "
            "from benchmarks.scaling import frozen_metadata; "
            "from benchmarks.harness import validate_freeze; "
            "print(json.dumps(frozen_metadata(validate_freeze(Path(sys.argv[1]), "
            "phase='holdout') if sys.argv[1] else {})))"
        ),
        str(freeze_path.resolve()) if freeze_path else "",
    ]
    measured = json.loads(
        subprocess.run(
            metadata_command,
            capture_output=True,
            text=True,
            check=True,
            timeout=protocol["process_timeout_seconds"],
        ).stdout
    )
    with output.open("x", encoding="utf8") as stream:
        for graph in protocol["graphs"]:
            for size in [4, 8] if smoke else protocol["sizes"]:
                for checkers in [1, 2] if smoke else protocol["checkers"]:
                    for mode in ("count", "time", "memory"):
                        begin = time.perf_counter()
                        row = {
                            **measured,
                            "question": "Q3",
                            "graph": graph,
                            "size": size,
                            "checkers": checkers,
                            "mode": mode,
                            "timeout": False,
                            "manifest_sha256": digest(
                                Path(__file__).with_name("protocol.json").read_bytes()
                            ),
                        }
                        if time.perf_counter() - started > protocol["max_total_seconds"]:
                            row.update(status="unexecuted", timeout=False)
                        else:
                            timeout = (
                                protocol["small_timing_timeout_seconds"]
                                if size <= 8 and mode == "time"
                                else protocol["process_timeout_seconds"]
                            )
                            try:
                                command = [
                                    python,
                                    "-m",
                                    "benchmarks.scaling",
                                    "worker",
                                    "--size",
                                    str(size),
                                    "--checkers",
                                    str(checkers),
                                    "--graph",
                                    graph,
                                    "--mode",
                                    mode,
                                ]
                                if freeze_path is not None:
                                    command.extend(("--freeze", str(freeze_path.resolve())))
                                result = subprocess.run(
                                    command,
                                    capture_output=True,
                                    text=True,
                                    timeout=timeout,
                                    check=True,
                                )
                                lines = result.stdout.splitlines()
                                row.update(json.loads(lines[0]))
                                row.update(json.loads(lines[-1]))
                                row["status"] = "completed"
                            except subprocess.TimeoutExpired as error:
                                if error.stdout:
                                    partial = (
                                        error.stdout.decode()
                                        if isinstance(error.stdout, bytes)
                                        else error.stdout
                                    )
                                    try:
                                        row.update(json.loads(partial.splitlines()[0]))
                                    except (ValueError, IndexError):
                                        pass
                                row.update(
                                    status="timeout",
                                    timeout=True,
                                    timeout_seconds=timeout,
                                    right_censored=True,
                                    timeout_scope=(
                                        "whole worker subprocess (startup/import/construction/"
                                        "serialization/load/reference/plan), phase unknown; "
                                        "not a plan-time lower bound"
                                    ),
                                )
                            except (subprocess.CalledProcessError, ValueError) as error:
                                partial = getattr(error, "stdout", None)
                                if partial:
                                    try:
                                        row.update(json.loads(partial.splitlines()[0]))
                                    except (ValueError, IndexError):
                                        pass
                                row.update(
                                    status="exception",
                                    exception=str(error),
                                    stderr=getattr(error, "stderr", None),
                                )
                        row["process_end_to_end_seconds"] = time.perf_counter() - begin
                        stream.write(json.dumps(row) + "\n")
                        stream.flush()


def summarize(inputs: list[Path], output: Path) -> None:
    if output.exists():
        raise ValueError("Scaling summary already exists")
    output.mkdir(parents=True)
    rows = [
        json.loads(line) for path in inputs for line in path.read_text(encoding="utf8").splitlines()
    ]
    versions = sorted({r.get("environment", {}).get("package", "unknown") for r in rows})
    summary = {
        "question": "Q3",
        "rows": len(rows),
        "versions": versions,
        "completed": sum(r["status"] == "completed" for r in rows),
        "timeout": sum(r["status"] == "timeout" for r in rows),
        "exceptions": sum(r["status"] == "exception" for r in rows),
        "unexecuted": sum(r["status"] == "unexecuted" for r in rows),
        "reference_disagreements": [r for r in rows if r.get("reference_agrees") is False],
        "indexed_work_bound_violations": [
            r
            for r in rows
            if "_evaluate_check_truth" in r.get("diagnostic_counts", {})
            and r["diagnostic_counts"]["_evaluate_check_truth"]
            > r["recorded_checks"] + r["verified_dependency_edges"]
        ],
        "limitation": (
            "Method-specific count units; no count-based universal speed ratio. Normal time, "
            "count and traced Python allocations use distinct workers. Whole-worker "
            "timeouts are right-censored with unknown phase, not plan lower bounds; "
            "failed or unexecuted cells retained."
        ),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    fields = (
        "version",
        "graph",
        "size",
        "checkers",
        "mode",
        "status",
        "plan_median_seconds",
        "plan_p95_seconds",
        "plan_cpu_median_seconds",
        "repeats",
        "construction_seconds",
        "serialization_seconds",
        "snapshot_load_seconds",
        "process_end_to_end_seconds",
        "worker_end_to_end_seconds",
        "peak_traced_python_allocation_bytes",
        "timeout_seconds",
        "right_censored",
        "exception",
        "diagnostic_counts",
        "wheel_sha256",
        "package_sha256",
        "implementation_commit",
        "manifest_sha256",
    )
    with (output / "scaling.csv").open("w", newline="", encoding="utf8") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "version": row.get("environment", {}).get("package"),
                    "diagnostic_counts": json.dumps(row.get("diagnostic_counts"), sort_keys=True),
                }
            )
    lines = [
        "# Q3 control cost",
        "",
        summary["limitation"],
        "",
        f"Rows {len(rows)}: completed {summary['completed']}, timeout {summary['timeout']}, "
        f"exceptions {summary['exceptions']}, unexecuted {summary['unexecuted']}.",
        "",
        "| Version | Graph | Targets | Checkers | Median normal plan seconds | "
        "p95 | Repeats | Whole worker outcome |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["mode"] == "time":
            lines.append(
                f"| {row.get('environment', {}).get('package', 'unknown')} | {row['graph']} | "
                f"{row['size']} | {row['checkers']} | {row.get('plan_median_seconds')} | "
                f"{row.get('plan_p95_seconds')} | {row.get('repeats')} | {row['status']} |"
            )
    lines += [
        "",
        "Construction, snapshot serialization/loading, worker startup/end-to-end, actual "
        "base/worklist/target diagnostic counts and separate peak traced Python allocations "
        "are in scaling.csv and raw JSONL. Seeds share identical parents across required "
        "checkers; the independent DFS reference is restricted to these acyclic or pure "
        "ungrounded-cycle graphs. Callback/controller end-to-end cost belongs to the "
        "separate Q1/Q2 experiment. Absolute timings depend on host load; there is no "
        "claim of an external population or LLM speedup.",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    w = commands.add_parser("worker")
    w.add_argument("--size", type=int, required=True)
    w.add_argument("--checkers", type=int, required=True)
    w.add_argument("--graph", choices=("chain", "diamond", "branches", "cycle"), required=True)
    w.add_argument("--mode", choices=("count", "time", "memory"), required=True)
    w.add_argument("--freeze", type=Path)
    r = commands.add_parser("run")
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--python", default=sys.executable)
    r.add_argument("--smoke", action="store_true")
    r.add_argument("--freeze", type=Path)
    a = commands.add_parser("summarize")
    a.add_argument("inputs", nargs="+", type=Path)
    a.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "worker":
        frozen = validate_freeze(args.freeze, phase="holdout") if args.freeze else {}
        print(json.dumps(frozen_metadata(frozen)), flush=True)
        print(json.dumps(worker(args.size, args.checkers, args.graph, args.mode)))
    elif args.command == "run":
        if args.freeze:
            validate_freeze(args.freeze, phase="development")
        run(args.output, args.python, smoke=args.smoke, freeze_path=args.freeze)
    else:
        summarize(args.inputs, args.output)


if __name__ == "__main__":
    main()
