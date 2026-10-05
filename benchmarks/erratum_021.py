"""Reclassify recorded v0.2.1 raw stops without executing either runtime.

The original oracle, costs, traces and runner labels remain unchanged. This
stdlib-only code separates known incomplete domain stops, uncertain stops and
execution faults; a runner-label spelling is not an acceptance condition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

Row = dict[str, Any]
ARCHIVE_SHA256 = "9212ee2499df0b16b47b23ac3150f71b83b1db69abc85a7123a02044f4fa69a0"
DOMAIN_STOPS = {"blocked", "budget_exhausted", "escalation_required"}
MAIN_METHODS = {"egr", "fixed-feasible", "verify-first", "random-feasible"}


def classify_stop(row: Row) -> Row:
    """Classify recorded terminal semantics; never infer truth from a stop label.

    ``known_correct_abstention`` requires an explicitly unsolvable task, assessed
    incompletion, an actual domain halt and known constrained use/effects.
    Pending invocations and unknown use/effects remain uncertain, including a
    guarded escalation. Unconstrained token use is not made artificially known.
    """
    worker = row.get("worker_status", row.get("status", "unexecuted"))
    runner = row.get("runner_stop", row.get("stop_reason"))
    oracle = row.get("oracle") or {}
    completion = oracle.get("completion")
    if not isinstance(completion, bool):
        completion = None
    task = row.get("task") or {}
    solvable = task.get("solvable")
    if not isinstance(solvable, bool):
        solvable = None
    domain = row.get("domain_stop")
    state = row.get("state") or {}
    results = state.get("results", [])
    limits = (row.get("budget") or {}).get("limits")
    if not isinstance(limits, dict):
        limits = {"actions": task.get("actions"), "verifications": task.get("verifications")}
    reasons = []
    if row.get("resource_unknown"):
        reasons.append("reported_unknown_resource")
    if row.get("resource_overrun") is None and any(limit is not None for limit in limits.values()):
        reasons.append("unassessed_resource_bound")
    for dimension, limit in limits.items():
        if limit is None:
            continue
        if any((result.get("actual_resources") or {}).get(dimension) is None for result in results):
            reasons.append(f"unknown_actual_{dimension}")
        cost_field = "callbacks" if dimension == "actions" else dimension
        if row.get(cost_field) is None:
            reasons.append(f"unknown_recorded_{dimension}")
    if any(result.get("side_effects") != "known" for result in results):
        reasons.append("unknown_side_effects")
    if any(result.get("status") == "unknown" for result in results):
        reasons.append("unknown_result_status")
    if row.get("callbacks", 0) and not results:
        reasons.append("missing_receipt_effects")
    received = {result.get("attempt_id") for result in results}
    if any(attempt.get("id") not in received for attempt in state.get("attempts", [])):
        reasons.append("pending_invocation")
    fault = (
        worker in {"exception", "timeout"}
        or bool(row.get("timeout"))
        or bool(row.get("exception") or row.get("execution_error"))
    )
    overrun = row.get("resource_overrun") is True
    halt = (
        worker == "completed"
        and not fault
        and completion is False
        and not row.get("router_satisfied")
        and domain in DOMAIN_STOPS
        and (row.get("decision") or {}).get("action") is None
    )
    known = halt and solvable is False and not reasons and not overrun
    uncertain = halt and solvable is False and bool(reasons) and not overrun
    erroneous = halt and solvable is True and not overrun
    if worker in {"unsupported", "unexecuted", "resource_limit", "unavailable"}:
        terminal = worker
        fault = False
    elif fault:
        terminal = "execution_fault"
    elif completion is None or solvable is None:
        terminal = "unassessed"
    elif row.get("router_satisfied") and completion is False:
        terminal = "false_satisfied"
    elif completion:
        terminal = "completed"
    elif overrun:
        terminal = "resource_violation"
    elif known:
        terminal = "known_correct_abstention"
    elif uncertain:
        terminal = "uncertain_incomplete_stop"
    elif erroneous:
        terminal = "erroneous_stop"
    else:
        terminal = "non_domain_incomplete"
    return {
        "worker_status": worker,
        "runner_stop": runner,
        "domain_stop": domain,
        "oracle_completion": completion,
        "task_solvable": solvable,
        "terminal_class": terminal,
        "known_correct_abstention": bool(known),
        "uncertain_incomplete_stop": bool(uncertain),
        "execution_fault": bool(fault),
        "erroneous_stop": bool(erroneous),
        "uncertainty_reasons": sorted(set(reasons)),
    }


def legacy_router_stop(row: Row) -> bool:
    """Reproduce the published label predicate, including its solvable-task caveat."""
    return bool(
        row.get("status") == "completed"
        and not row.get("timeout")
        and not row.get("exception")
        and not row.get("router_satisfied")
        and row.get("stop_reason") == "router_stopped"
        and row.get("domain_stop") in DOMAIN_STOPS
    )


def semantic_signature(row: Row) -> str:
    """Compare F7 records after replacing only invocation/receipt identity values.

    Material/action IDs, scopes, authority, resource values, raw oracle outcome
    and payload remain exact. Timing and runner labels are deliberately absent.
    """
    state = row["state"]
    names = {
        record["id"]: f"invocation-{index}"
        for index, record in enumerate(state.get("attempts", []))
    }
    names.update(
        {record["id"]: f"receipt-{index}" for index, record in enumerate(state.get("results", []))}
    )

    def normalize(value, field=""):
        if isinstance(value, str):
            return names.get(value, value) if field in {"attempt_id", "record_ids"} else value
        if isinstance(value, list):
            return [normalize(item, field) for item in value]
        if isinstance(value, dict):
            opaque_record = "actual_resources" in value or ("action" in value and "id" in value)
            return {
                key: names.get(item, item)
                if key == "id" and opaque_record and isinstance(item, str)
                else normalize(item, key)
                for key, item in value.items()
            }
        return value

    material = {
        key: row.get(key)
        for key in (
            "state",
            "trace",
            "initial_trace",
            "decision",
            "domain_stop",
            "callbacks",
            "verifications",
            "resource_unknown",
            "resource_overrun",
            "oracle",
            "snapshot_resume",
        )
    }
    canonical = json.dumps(normalize(material), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def summarize_rows(rows, *, primary_seed: int = 17) -> Row:
    """Stream raw records into parent groups; do not execute a new experiment."""
    groups = defaultdict(list)
    f7 = defaultdict(dict)
    raw_count = 0
    for row in rows:
        raw_count += 1
        version, method = row["environment"]["package"], row["method"]
        original = row.get("variant") == "original" and (
            method != "random-feasible" or row.get("random_seed") == primary_seed
        )
        slim = {
            "task": row["task"],
            "task_id": row["task_id"],
            "status": row["status"],
            "original": original,
            "reference_only": row.get("reference_only", False),
            "completion": row["status"] == "completed"
            and not row.get("timeout")
            and bool((row.get("oracle") or {}).get("completion")),
            "false_satisfied": row.get("false_satisfied"),
            "legacy_router_stop": legacy_router_stop(row),
            "classification": classify_stop(row),
            "unknown_callbacks": row.get("callbacks") is None,
            "unknown_verifications": row.get("verifications") is None,
            "exception": bool(row.get("exception")) or row.get("status") == "exception",
        }
        groups[(version, method, row["task_id"])].append(slim)
        if (
            version == "0.2.1"
            and method in MAIN_METHODS
            and original
            and row["task"]["family"] == "F7"
            and row["task"]["mode"] in {4, 5}
        ):
            f7[row["task_id"]][method] = {
                "mode": row["task"]["mode"],
                "semantic_sha256": semantic_signature(row),
                "runner_stop": row["stop_reason"],
                "domain_stop": row["domain_stop"],
                "callbacks": row["callbacks"],
                "verifications": row["verifications"],
                "classification": slim["classification"],
            }
    parents = []
    for (version, method, task_id), repetitions in sorted(groups.items()):
        supported = [r for r in repetitions if r["status"] not in {"unsupported", "unexecuted"}]
        originals = [r for r in supported if r["original"]]
        if len(originals) > 1:
            raise ValueError(f"Duplicate primary trial: {version}/{method}/{task_id}")
        original = originals[0] if originals else None
        parents.append(
            {
                "version": version,
                "method": method,
                "task_id": task_id,
                "family": repetitions[0]["task"]["family"],
                "budget": repetitions[0]["task"]["budget_class"],
                "solvable": repetitions[0]["task"]["solvable"],
                "reference_only": repetitions[0]["reference_only"],
                "supported": bool(supported),
                "repetitions": len(repetitions),
                "attempted_repetitions": len(supported),
                "unsupported_repetitions": sum(r["status"] == "unsupported" for r in repetitions),
                "unexecuted_repetitions": sum(r["status"] == "unexecuted" for r in repetitions),
                "primary_completion": int(original["completion"]) if original else 0,
                "false_satisfied": any(r["false_satisfied"] is True for r in supported),
                "unassessed_repetitions": sum(r["false_satisfied"] is None for r in supported),
                "legacy_router_stop": bool(original and original["legacy_router_stop"]),
                "primary_classification": original["classification"] if original else None,
                "unknown_callback_cost_repetitions": sum(r["unknown_callbacks"] for r in supported),
                "unknown_verification_cost_repetitions": sum(
                    r["unknown_verifications"] for r in supported
                ),
                "exception_repetitions": sum(r["exception"] for r in supported),
            }
        )
    tables = []
    for dimension in ("overall", "family", "budget"):
        bins = defaultdict(list)
        for parent in parents:
            if not parent["reference_only"]:
                bins[(parent["version"], parent["method"], parent.get(dimension, "all"))].append(
                    parent
                )
        for (version, method, label), values in sorted(bins.items()):
            supported = [p for p in values if p["supported"]]
            solvable = [p for p in supported if p["solvable"]]
            stops = [p for p in supported if not p["solvable"]]
            classes = [p["primary_classification"] or {} for p in stops]
            tables.append(
                {
                    "dimension": dimension,
                    "label": label,
                    "version": version,
                    "method": method,
                    "requested_parents": len(values),
                    "supported_parents": len(supported),
                    "solvable_parents": len(solvable),
                    "completion_numerator": sum(p["primary_completion"] for p in solvable),
                    "false_satisfied_count": sum(p["false_satisfied"] for p in supported),
                    "false_satisfied_denominator": len(supported),
                    "correct_abstention_numerator": sum(p["legacy_router_stop"] for p in stops),
                    "correct_abstention_denominator": len(stops),
                    "known_correct_abstention_numerator": sum(
                        bool(c.get("known_correct_abstention")) for c in classes
                    ),
                    "uncertain_incomplete_stop_numerator": sum(
                        bool(c.get("uncertain_incomplete_stop")) for c in classes
                    ),
                    "execution_fault_numerator": sum(
                        bool(c.get("execution_fault")) for c in classes
                    ),
                    "unsupported_repetitions": sum(p["unsupported_repetitions"] for p in values),
                    "unexecuted_repetitions": sum(p["unexecuted_repetitions"] for p in values),
                    "attempted_repetitions": sum(p["attempted_repetitions"] for p in values),
                    "unassessed_false_satisfied_repetitions": sum(
                        p["unassessed_repetitions"] for p in supported
                    ),
                    "unknown_callback_cost_repetitions": sum(
                        p["unknown_callback_cost_repetitions"] for p in supported
                    ),
                    "unknown_verification_cost_repetitions": sum(
                        p["unknown_verification_cost_repetitions"] for p in supported
                    ),
                    "exception_repetitions": sum(p["exception_repetitions"] for p in supported),
                }
            )
    effects = []
    for task_id, methods in sorted(f7.items()):
        effects.append(
            {
                "task_id": task_id,
                "mode": next(iter(methods.values()))["mode"],
                "all_four_present": set(methods) == MAIN_METHODS,
                "semantics_equal": set(methods) == MAIN_METHODS
                and len({m["semantic_sha256"] for m in methods.values()}) == 1,
                "methods": methods,
            }
        )
    old_egr = {
        p["task_id"]: p
        for p in parents
        if p["version"] == "0.2.0" and p["method"] == "egr" and p["supported"]
    }
    new_egr = {
        p["task_id"]: p
        for p in parents
        if p["version"] == "0.2.1" and p["method"] == "egr" and p["supported"]
    }
    shared = set(old_egr) & set(new_egr)
    paired_solvable = [t for t in shared if old_egr[t]["solvable"] and new_egr[t]["solvable"]]
    return {
        "schema_version": "v0.2.1-erratum-1",
        "analysis_kind": "reclassification of recorded raw; no runtime trials rerun",
        "primary_seed": primary_seed,
        "raw_trial_count": raw_count,
        "unique_parent_tasks": len({p["task_id"] for p in parents}),
        "legacy_solvable_router_stop_flags": sum(
            p["legacy_router_stop"] and p["solvable"] and not p["reference_only"] for p in parents
        ),
        "parents": parents,
        "tables": tables,
        "unchanged_matched_version_primary": {
            "compatible_parents": len(shared),
            "solvable_parents": len(paired_solvable),
            "old_completion_numerator": sum(
                old_egr[t]["primary_completion"] for t in paired_solvable
            ),
            "new_completion_numerator": sum(
                new_egr[t]["primary_completion"] for t in paired_solvable
            ),
            "old_false_satisfied_parents": sum(old_egr[t]["false_satisfied"] for t in shared),
            "new_false_satisfied_parents": sum(new_egr[t]["false_satisfied"] for t in shared),
        },
        "F7_primary_trace_equivalence": effects,
        "limitations": [
            "Recorded oracle/solvability are reused; this is not a new correctness experiment.",
            "Old CPU retains unequal runner paths, tracemalloc, cold import and setup overhead.",
            "Unknown use/effects stay uncertain, rather than known safe success or zero cost.",
            "Original raw, summary, freeze and protocol are not overwritten.",
        ],
    }


def analyze_directory(directory: Path, archive: Path | None = None) -> Row:
    """Validate immutable bundle hashes and reproduce all published primary tables."""
    manifest = json.loads((directory / "MANIFEST.json").read_text(encoding="utf-8"))
    for name, entry in manifest.items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f"Invalid bundle path: {name}")
        with path.open("rb") as stream:
            actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if path.stat().st_size != entry["bytes"] or actual_hash != entry["sha256"]:
            raise ValueError(f"Original bundle bytes changed: {name}")
    archive_hash = None
    if archive is not None:
        with archive.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if archive_hash != ARCHIVE_SHA256:
            raise ValueError("Wrong official v0.2.1 raw archive")
    protocol = json.loads((directory / "benchmarks/protocol.json").read_text())

    def rows():
        for name in ("methods.jsonl", "old-version.jsonl"):
            with (directory / name).open(encoding="utf-8") as stream:
                for line in stream:
                    yield json.loads(line)

    report = summarize_rows(rows(), primary_seed=protocol["random_seeds"][0])
    published = json.loads((directory / "report/summary.json").read_text(encoding="utf-8"))

    def key(table):
        return (table["dimension"], table["label"], table["version"], table["method"])

    old_tables = {key(t): t for t in published["tables"]}
    if set(old_tables) != {key(t) for t in report["tables"]}:
        raise ValueError("Raw/published table groups differ")
    new_fields = {
        "known_correct_abstention_numerator",
        "uncertain_incomplete_stop_numerator",
        "execution_fault_numerator",
    }
    for table in report["tables"]:
        for name, value in table.items():
            if name not in new_fields and old_tables[key(table)].get(name) != value:
                raise ValueError(f"Raw/published primary mismatch: {key(table)}/{name}")
    report["provenance"] = {
        "source_archive_sha256": archive_hash,
        "expected_archive_sha256": ARCHIVE_SHA256,
        "manifest_assets_verified": len(manifest),
        "legacy_primary_tables_reproduced": True,
        "raw_sources": {name: manifest[name] for name in ("methods.jsonl", "old-version.jsonl")},
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_directory", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; never overwrite original or corrected evidence")
    report = analyze_directory(args.raw_directory, args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "raw_trial_count": report["raw_trial_count"]}))


if __name__ == "__main__":
    main()
