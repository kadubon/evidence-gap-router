"""Observed subsets and unknown/censored outcomes retain distinct denominators."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.summarize_022 import render, summarize  # noqa: E402


def proof(version, *, size=4, mode="time", status="completed", **fields):
    return {
        "spec": {
            "phase": "scaling",
            "kind": "proof",
            "graph": "chain",
            "size": size,
            "checkers": 1,
            "mode": mode,
            "version": version,
        },
        "worker_status": status,
        "reference_agrees": True,
        "plan_median_seconds": 4.0 if version == "0.2.1" else 1.0,
        **fields,
    }


def helper(version, *, identifier="one", phase="scaling", mode="time", **fields):
    return {
        "spec": {
            "phase": phase,
            "kind": "helper",
            "version": version,
            "mode": mode,
            "case": {"id": identifier, "depth": 4, "alternatives": 2},
        },
        "worker_status": "completed",
        "reference_assessed": True,
        "reference_agrees": True,
        "phase_median_seconds": {"plan": 2.0, "start_observe": 1.0, "binding_progress": 0.5},
        "sequence_median_seconds": 3.5,
        **fields,
    }


def audit(version, cases, status="completed"):
    return {
        "spec": {"phase": "audit", "kind": "audit", "version": version},
        "worker_status": status,
        "cases": cases,
    }


def test_normal_time_pairs_require_matched_complete_workers_and_positive_values():
    rows = [
        proof("0.2.1"),
        proof("0.2.2"),
        proof("0.2.1", size=8, status="timeout"),
        proof("0.2.2", size=8),
        proof("0.2.1", size=12, plan_median_seconds=0),
        proof("0.2.2", size=12),
    ]
    result = summarize(rows)
    aggregate = result["paired_normal_time"]["aggregates"][0]
    assert aggregate["input_pairs_present"] == 3
    assert aggregate["both_completed_pairs"] == 2
    assert aggregate["positive_finite_ratio_pairs"] == 1
    assert aggregate["median_old_over_new_ratio"] == 4.0
    assert aggregate["noncompleted_or_missing_pairs"] == 1
    assert aggregate["completed_but_zero_or_missing_phase_pairs"] == 1
    censor = next(p for p in result["paired_normal_time"]["pairs"] if p["input"]["size"] == 8)
    assert censor["old_over_new_ratio"] is None and not censor["both_workers_completed"]
    assert censor["old_reference"] == "not_completed"


def test_reference_unassessed_is_distinct_from_disagreement_and_worker_completion():
    rows = [
        helper("0.2.1", identifier="unassessed", reference_assessed=False, reference_agrees=True),
        helper("0.2.2", identifier="unassessed", reference_assessed=False, reference_agrees=True),
        helper("0.2.1", identifier="mismatch", reference_agrees=False),
        helper("0.2.2", identifier="mismatch"),
        helper("0.2.1", identifier="fault", worker_status="exception", exception="RecursionError"),
        helper("0.2.2", identifier="fault"),
    ]
    result = summarize(rows)
    reports = {r["version"]: r for r in result["helper_scaling"]["versions"]}
    assert reports["0.2.1"]["references"] == {
        "agree": 0,
        "disagree": 1,
        "unassessed": 1,
        "not_completed": 1,
    }
    assert reports["0.2.2"]["references"]["agree"] == 2
    pairs = result["paired_normal_time"]["pairs"]
    assert any(p["old_reference"] == "disagree" and p["old_over_new_ratio"] == 1 for p in pairs)
    assert any(p["old_reference"] == "unassessed" and p["old_over_new_ratio"] == 1 for p in pairs)
    assert all(p["old_over_new_ratio"] is None for p in pairs if p["input"]["id"] == "fault")


def test_confirmation_and_scaling_same_identifier_have_separate_subsets():
    rows = [
        helper(v, phase=phase, mode="semantic" if phase == "confirmation" else "count")
        for phase in ("scaling", "confirmation")
        for v in ("0.2.1", "0.2.2")
    ]
    result = summarize(rows)
    assert result["helper_scaling"]["observed_rows"] == 2
    assert result["new_confirmation"]["observed_rows"] == 2
    assert result["paired_normal_time"]["pairs"] == []


def test_unexecuted_unavailable_resource_censors_and_exceptions_are_not_merged():
    statuses = ("unexecuted", "unavailable", "resource_limit", "timeout", "exception")
    result = summarize([proof("0.2.1", size=i + 1, status=s) for i, s in enumerate(statuses)])
    assert result["worker_statuses"] == {s: 1 for s in statuses}
    cells = result["proof_scaling"]["cells"]
    by_status = {c["versions"][0]["worker_status"]: c["versions"][0] for c in cells}
    assert by_status["resource_limit"]["right_censored"]
    assert by_status["timeout"]["right_censored"]
    assert not by_status["exception"]["right_censored"]
    assert all(c["plan_median_seconds"] is None for c in by_status.values())
    assert all(c["whole_worker_cpu_seconds"] is None for c in by_status.values())
    assert result["proof_scaling"]["versions"][0]["references"]["not_completed"] == 5


def test_audit_exceptions_and_missing_observations_are_unassessed_not_property_passes():
    cases = [
        {
            "case": "good",
            "observation": {"domain_stop": "satisfied"},
            "independent_expected_property_met": True,
            "exception": None,
        },
        {
            "case": "bad",
            "observation": {"domain_stop": "satisfied"},
            "independent_expected_property_met": False,
            "exception": None,
            "old021_issue_reproduced": True,
        },
        {
            "case": "fault",
            "observation": None,
            "independent_expected_property_met": False,
            "exception": "missing API",
        },
        {"case": "without-evidence", "independent_expected_property_met": True, "exception": None},
    ]
    result = summarize([audit("0.2.1", cases), audit("0.2.2", cases, status="unexecuted")])
    old, new = result["audit"]["versions"]
    assert old["cases_reported"] == 4
    assert old["properties_assessed"] == 2
    assert old["properties_met"] == 1 and old["properties_not_met"] == 1
    assert old["properties_unassessed"] == 2 and old["case_exceptions"] == 1
    assert old["old021_issue_reproductions"] == 1
    assert new["cases_reported"] == 0 and new["properties_assessed"] == 0
    assert new["worker_statuses"] == {"unexecuted": 1}


def test_method_specific_count_and_memory_units_are_retained_without_count_ratios():
    rows = [
        proof("0.2.1", mode="count", diagnostic_counts={"recursive": 17}, instrument="old unit"),
        proof("0.2.2", mode="count", diagnostic_counts={"edge": 9}, instrument="new unit"),
        helper(
            "0.2.1",
            mode="memory",
            peak_traced_python_allocation_bytes=123,
            peak_worker_memory_bytes=456,
            memory_metric="job_peak_private_committed_bytes",
        ),
        helper("0.2.2", mode="memory", peak_traced_python_allocation_bytes=321),
    ]
    result = summarize(rows)
    cells = result["proof_scaling"]["cells"][0]["versions"]
    assert cells[0]["diagnostic_counts"] == {"recursive": 17}
    assert cells[1]["diagnostic_counts"] == {"edge": 9}
    assert result["paired_normal_time"]["pairs"] == []
    memory = result["helper_scaling"]["cells"][0]["versions"][0]
    assert memory["peak_traced_python_allocation_bytes"] == 123
    assert memory["peak_worker_memory_bytes"] == 456
    assert memory["worker_memory_metric"] == "job_peak_private_committed_bytes"


def test_unknown_nonfinite_boolean_time_and_missing_pair_are_not_fabricated():
    rows = [
        proof("0.2.1", plan_median_seconds=float("nan")),
        proof("0.2.2"),
        proof("0.2.1", size=8, plan_median_seconds=True),
        helper("0.2.1", phase_median_seconds={"plan": float("inf")}),
        helper("0.2.2"),
    ]
    result = summarize(rows)
    assert all(
        p["old_over_new_ratio"] is None
        for p in result["paired_normal_time"]["pairs"]
        if p["kind"] == "proof" or p["metric"] == "plan"
    )
    json.dumps(result, allow_nan=False)


def test_duplicates_are_rejected_and_input_rows_are_immutable():
    row = proof("0.2.1")
    with pytest.raises(ValueError, match="duplicate"):
        summarize([row, copy.deepcopy(row)])
    before = copy.deepcopy(row)
    summarize([row])
    assert row == before
    with pytest.raises(ValueError, match="explicit version"):
        summarize([{"worker_status": "unexecuted"}])


def test_empty_rows_and_bilingual_report_do_not_claim_unexecuted_success():
    empty = summarize([])
    assert empty["observed_rows"] == 0 and empty["audit"]["versions"] == []
    rows = [helper("0.2.1", reference_assessed=False), helper("0.2.2", reference_assessed=False)]
    result = summarize(rows)
    assert "unassessed 1" in render(result)
    assert "判定不能1" in render(result, "ja")
    assert "not plan-time lower bounds" in render(result)
    with pytest.raises(ValueError, match="language"):
        render(result, "invalid")


def test_all_594_scaling_cells_64_confirmation_and_14_audits_each_are_retained():
    rows = []
    for version in ("0.2.1", "0.2.2"):
        for graph in ("chain", "diamond", "branches", "cycle"):
            for size in (4, 8, 16, 32, 64):
                for checkers in (1, 2, 3):
                    for mode in ("time", "count", "memory"):
                        row = proof(version, size=size, mode=mode)
                        row["spec"].update(graph=graph, checkers=checkers)
                        rows.append(row)
        for identifier in range(39):
            for mode in ("time", "count", "memory"):
                rows.append(helper(version, identifier=str(identifier), mode=mode))
        for identifier in range(32):
            rows.append(
                helper(version, identifier=str(identifier), phase="confirmation", mode="semantic")
            )
        rows.append(
            audit(
                version,
                [
                    {
                        "case": str(i),
                        "observation": {},
                        "exception": None,
                        "independent_expected_property_met": True,
                    }
                    for i in range(14)
                ],
            )
        )
    result = summarize(rows)
    assert result["observed_rows"] == 660
    assert result["proof_scaling"]["observed_rows"] == 360
    assert result["helper_scaling"]["observed_rows"] == 234
    assert result["new_confirmation"]["observed_rows"] == 64
    assert result["proof_scaling"]["distinct_input_modes_present"] == 180
    assert result["helper_scaling"]["distinct_input_modes_present"] == 117
    assert result["new_confirmation"]["distinct_input_modes_present"] == 32
    assert all(
        r["properties_assessed"] == r["properties_met"] == 14 for r in result["audit"]["versions"]
    )
