"""Summarize frozen controller records without turning missing evidence into success."""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def _version(row: dict) -> str:
    value = row.get("spec", {}).get("version") or row.get("sdk_version")
    value = value or row.get("environment", {}).get("package")
    if not isinstance(value, str) or not value:
        raise ValueError("every controller row needs an explicit version")
    return value


def _status(row: dict) -> str:
    return row.get("worker_status") or row.get("status") or "unknown"


def _reference(row: dict) -> str:
    if _status(row) != "completed":
        return "not_completed"
    if row.get("reference_assessed") is False:
        return "unassessed"
    value = row.get("reference_agrees")
    if type(value) is not bool:
        return "unassessed"
    return "agree" if value else "disagree"


def _finite(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or positive and value == 0:
        return None
    return value


def _identity(row: dict) -> tuple:
    spec = row.get("spec", {})
    phase, kind = spec.get("phase", "unknown"), spec.get("kind", "unknown")
    if kind == "proof":
        inputs = {key: spec.get(key, row.get(key)) for key in ("graph", "size", "checkers")}
    elif kind == "helper":
        inputs = spec.get("case", row.get("case", {}))
    elif kind == "method":
        inputs = {key: spec.get(key) for key in ("task", "variant", "method", "seed")}
    else:
        inputs = {}
    return phase, kind, spec.get("mode", row.get("mode")), json.dumps(inputs, sort_keys=True)


def _cell(row: dict) -> dict:
    """No ratio between count units or between instrumented and normal timings."""
    spec = row.get("spec", {})
    status = _status(row)
    return {
        "version": _version(row),
        "worker_status": status,
        "reported_trial_status": row.get("status"),
        "reference_outcome": _reference(row),
        "right_censored": status in {"timeout", "resource_limit"},
        "censor_scope": "whole worker; plan phase unknown"
        if status in {"timeout", "resource_limit"}
        else None,
        "limit_exceeded": row.get("limit_exceeded"),
        "exception": row.get("exception"),
        "stderr": row.get("stderr"),
        "stop_reason": row.get("stop_reason"),
        "router_stop": row.get("router_stop"),
        "whole_worker_seconds": _finite(row.get("whole_worker_seconds")),
        "whole_worker_cpu_seconds": _finite(row.get("whole_worker_cpu_seconds")),
        "peak_worker_memory_bytes": _finite(row.get("peak_worker_memory_bytes")),
        "worker_memory_metric": row.get("memory_metric"),
        "plan_median_seconds": (
            _finite(row.get("plan_median_seconds")) if status == "completed" else None
        ),
        "phase_median_seconds": {
            key: _finite(value) for key, value in (row.get("phase_median_seconds") or {}).items()
        }
        if status == "completed"
        else None,
        "sequence_median_seconds": (
            _finite(row.get("sequence_median_seconds")) if status == "completed" else None
        ),
        "peak_traced_python_allocation_bytes": (
            _finite(row.get("peak_traced_python_allocation_bytes"))
            if status == "completed"
            else None
        ),
        "diagnostic_counts": row.get("diagnostic_counts") if status == "completed" else None,
        "visits_by_phase": row.get("visits_by_phase") if status == "completed" else None,
        "count_instrument": row.get("instrument", row.get("visit_unit_limitation")),
        "construction_seconds": _finite(row.get("construction_seconds")),
        "candidate_construction_seconds": _finite(row.get("candidate_construction_seconds")),
        "initialization_seconds": _finite(row.get("initialization_seconds")),
        "serialization_load_seconds": _finite(row.get("serialization_load_seconds")),
        "snapshot_bytes": row.get("snapshot_bytes"),
        "candidate_count": row.get("candidate_count"),
        "dependency_incidence": row.get("dependency_incidence"),
        "reachable_helper_ids": row.get("reachable_helper_ids") if status == "completed" else None,
        "reference_helper_ids": row.get("reference_helper_ids") if status == "completed" else None,
        "reference_satisfied": row.get("reference_satisfied") if status == "completed" else None,
        "actual_satisfied": row.get("actual_satisfied") if status == "completed" else None,
        "callback_calls": row.get("callback_calls") if status == "completed" else None,
        "binding_progress": row.get("binding_progress") if status == "completed" else None,
        "mode": spec.get("mode", row.get("mode")),
    }


def _group(rows: list[dict], phase: str, kind: str, versions: list[str]) -> dict:
    members = [r for r in rows if _identity(r)[:2] == (phase, kind)]
    grouped = defaultdict(list)
    for row in members:
        grouped[_identity(row)].append(row)
    totals = []
    for version in versions:
        current = [r for r in members if _version(r) == version]
        statuses = Counter(_status(r) for r in current)
        references = Counter(_reference(r) for r in current)
        totals.append(
            {
                "version": version,
                "requested_rows_present": len(current),
                "worker_statuses": dict(sorted(statuses.items())),
                "references": {
                    key: references[key]
                    for key in ("agree", "disagree", "unassessed", "not_completed")
                },
                "whole_worker_cpu_unknown_rows": sum(
                    _finite(r.get("whole_worker_cpu_seconds")) is None for r in current
                ),
                "whole_worker_memory_unknown_rows": sum(
                    _finite(r.get("peak_worker_memory_bytes")) is None for r in current
                ),
            }
        )
    return {
        "observed_rows": len(members),
        "distinct_input_modes_present": len(grouped),
        "versions": totals,
        "cells": [
            {
                "phase": key[0],
                "kind": key[1],
                "mode": key[2],
                "input": json.loads(key[3]),
                "versions": [_cell(r) for r in sorted(values, key=_version)],
            }
            for key, values in sorted(grouped.items(), key=lambda item: repr(item[0]))
        ],
    }


def _time_metrics(row: dict) -> dict:
    if row.get("spec", {}).get("kind") == "proof":
        return {"plan": row.get("plan_median_seconds")}
    return {
        **(row.get("phase_median_seconds") or {}),
        "sequence": row.get("sequence_median_seconds"),
    }


def _paired_time(rows: list[dict], versions: list[str]) -> dict:
    grouped = defaultdict(dict)
    for row in rows:
        identity = _identity(row)
        if (
            identity[0] == "scaling"
            and identity[1] in {"helper", "proof"}
            and identity[2] == "time"
        ):
            grouped[identity][_version(row)] = row
    comparisons, aggregates = [], defaultdict(list)
    if len(versions) != 2:
        return {
            "version_pair": None,
            "pairs": [],
            "aggregates": [],
            "not_comparable_reason": "exactly two explicit versions are needed",
        }
    old, new = versions
    for identity, pair in sorted(grouped.items(), key=lambda item: repr(item[0])):
        pair_complete = (
            old in pair and new in pair and all(_status(pair[v]) == "completed" for v in (old, new))
        )
        metrics = set().union(*(_time_metrics(r) for r in pair.values()))
        for metric in sorted(metrics):
            previous = _finite(_time_metrics(pair[old]).get(metric)) if old in pair else None
            current = _finite(_time_metrics(pair[new]).get(metric)) if new in pair else None
            ratio = (
                previous / current
                if pair_complete
                and previous is not None
                and current is not None
                and previous > 0
                and current > 0
                else None
            )
            reason = None
            if not pair_complete:
                reason = "one or both workers not completed or absent"
            elif ratio is None:
                reason = "one or both phase measurements missing, nonfinite or zero"
            comparisons.append(
                {
                    "kind": identity[1],
                    "input": json.loads(identity[3]),
                    "metric": metric,
                    "both_workers_completed": pair_complete,
                    "old_seconds": previous,
                    "new_seconds": current,
                    "old_over_new_ratio": ratio,
                    "ratio_unavailable_reason": reason,
                    "old_reference": _reference(pair[old]) if old in pair else "absent",
                    "new_reference": _reference(pair[new]) if new in pair else "absent",
                }
            )
            aggregates[(identity[1], metric)].append(comparisons[-1])
    return {
        "version_pair": {"old": old, "new": new},
        "pairs": comparisons,
        "aggregates": [
            {
                "kind": key[0],
                "metric": key[1],
                "input_pairs_present": len(values),
                "both_completed_pairs": sum(v["both_workers_completed"] for v in values),
                "positive_finite_ratio_pairs": sum(
                    v["old_over_new_ratio"] is not None for v in values
                ),
                "median_old_over_new_ratio": statistics.median(
                    [v["old_over_new_ratio"] for v in values if v["old_over_new_ratio"] is not None]
                )
                if any(v["old_over_new_ratio"] is not None for v in values)
                else None,
                "noncompleted_or_missing_pairs": sum(
                    not v["both_workers_completed"] for v in values
                ),
                "completed_but_zero_or_missing_phase_pairs": sum(
                    v["both_workers_completed"] and v["old_over_new_ratio"] is None for v in values
                ),
            }
            for key, values in sorted(aggregates.items())
        ],
        "scope": (
            "Descriptive paired normal-time medians for exactly matched complete workers. "
            "Censors are not lower bounds on plan time. Ratio >1 means old slower for that pair. "
            "Reference disagreement remains visible; it is not excluded to improve timing."
        ),
    }


def _audits(rows: list[dict], versions: list[str]) -> dict:
    workers = [r for r in rows if _identity(r)[:2] == ("audit", "audit")]
    reports = []
    for version in versions:
        current = [r for r in workers if _version(r) == version]
        cases = []
        for row in current:
            for case in row.get("cases", ()) if _status(row) == "completed" else ():
                assessed = (
                    isinstance(case.get("observation"), dict)
                    and case.get("exception") is None
                    and type(case.get("independent_expected_property_met")) is bool
                )
                outcome = (
                    ("met" if case["independent_expected_property_met"] else "not_met")
                    if assessed
                    else "unassessed"
                )
                cases.append(
                    {
                        "finding": case.get("finding"),
                        "case": case.get("case"),
                        "property_outcome": outcome,
                        "exception": case.get("exception"),
                        "reported_expected_property_met": case.get(
                            "independent_expected_property_met"
                        ),
                        "old021_issue_reproduced": case.get("old021_issue_reproduced"),
                        "domain_stop": (case.get("observation") or {}).get("domain_stop"),
                    }
                )
        counts = Counter(c["property_outcome"] for c in cases)
        reports.append(
            {
                "version": version,
                "worker_rows_present": len(current),
                "worker_statuses": dict(Counter(_status(r) for r in current)),
                "cases_reported": len(cases),
                "properties_assessed": counts["met"] + counts["not_met"],
                "properties_met": counts["met"],
                "properties_not_met": counts["not_met"],
                "properties_unassessed": counts["unassessed"],
                "case_exceptions": sum(c["exception"] is not None for c in cases),
                "old021_issue_reproductions": sum(
                    c["old021_issue_reproduced"] is True for c in cases
                ),
                "cases": cases,
            }
        )
    return {
        "observed_worker_rows": len(workers),
        "versions": reports,
        "scope": (
            "Fourteen fixed functional diagnostics per completed worker; "
            "not population CVEs or timing"
        ),
    }


def summarize(rows: list[dict]) -> dict:
    """Aggregate only observed rows; never synthesize success for absent keys."""
    versions = sorted(
        {_version(r) for r in rows},
        key=lambda value: tuple(
            (0, int(part)) if part.isdigit() else (1, part) for part in value.split(".")
        ),
    )
    seen = set()
    for row in rows:
        key = (_version(row), _identity(row))
        if key in seen:
            raise ValueError("duplicate version/input/mode controller rows")
        seen.add(key)
    statuses = Counter(_status(r) for r in rows)
    phases = Counter((r.get("spec", {}).get("phase", "unknown"), _status(r)) for r in rows)
    return {
        "schema": "egr-022-controller-summary-v1",
        "observed_rows": len(rows),
        "versions": versions,
        "worker_statuses": dict(sorted(statuses.items())),
        "phase_worker_statuses": [
            {"phase": phase, "worker_status": status, "rows": count}
            for (phase, status), count in sorted(phases.items())
        ],
        "proof_scaling": _group(rows, "scaling", "proof", versions),
        "helper_scaling": _group(rows, "scaling", "helper", versions),
        "new_confirmation": _group(rows, "confirmation", "helper", versions),
        "paired_normal_time": _paired_time(rows, versions),
        "audit": _audits(rows, versions),
        "scope_notes": [
            "Completed worker status is not domain completion or reference agreement.",
            "Unassessed and not-completed references are counted separately from agreement.",
            "Count units are method-specific; no count speed ratio is computed.",
            "Peak traced Python allocations are not RSS or Job private committed bytes.",
            "Construction and initialization timings are single observations, "
            "not stable percentiles.",
            "Whole-worker censors include startup/import/construction/transitions/output; "
            "their phase is unknown.",
            "Main 240-parent method regression aggregation is a separate report; "
            "this report retains its worker statuses.",
        ],
    }


def render(summary: dict, language: str = "en") -> str:
    if language not in {"en", "ja"}:
        raise ValueError("language must be en or ja")
    lines = []
    for name in ("proof_scaling", "helper_scaling", "new_confirmation"):
        group = summary[name]
        for report in group["versions"]:
            refs = report["references"]
            assessed = refs["agree"] + refs["disagree"]
            if language == "ja":
                lines.append(
                    f"{name} / {report['version']}: 観測{report['requested_rows_present']}件。"
                    f"参照一致{refs['agree']}/{assessed}、不一致{refs['disagree']}、"
                    f"判定不能{refs['unassessed']}、未完了{refs['not_completed']}。"
                )
            else:
                lines.append(
                    f"{name} / {report['version']}: "
                    f"{report['requested_rows_present']} observed records; "
                    f"reference agreement {refs['agree']}/{assessed}, "
                    f"disagreements {refs['disagree']}, "
                    f"unassessed {refs['unassessed']}, not completed {refs['not_completed']}."
                )
    for audit in summary["audit"]["versions"]:
        lines.append(
            f"audit / {audit['version']}: 独立した期待条件を満たす診断は"
            f"{audit['properties_met']}/{audit['properties_assessed']}件、"
            f"判定不能{audit['properties_unassessed']}件、例外{audit['case_exceptions']}件。"
            if language == "ja"
            else f"audit / {audit['version']}: independent expected properties met in "
            f"{audit['properties_met']}/{audit['properties_assessed']} assessed diagnostics; "
            f"unassessed {audit['properties_unassessed']}, exceptions {audit['case_exceptions']}."
        )
    lines.append(
        "速度比は両版の完了・有限正値が揃う同一入力だけで算出。打切りは全workerに対するもので、計画処理の下限ではない。"
        if language == "ja"
        else "Timing ratios use matched completed workers with finite positive measurements only. "
        "Censors apply to the whole worker and are not plan-time lower bounds."
    )
    return "\n\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-en", type=Path)
    parser.add_argument("--report-ja", type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line
    ]
    result = summarize(rows)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    for language, target in (("en", args.report_en), ("ja", args.report_ja)):
        if target is not None:
            target.write_text(render(result, language), encoding="utf-8")


if __name__ == "__main__":
    main()
