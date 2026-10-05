"""Portable checks for the new helper measurement inputs and independent oracle."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from benchmarks.helper_scaling_022 import (
    _sequence,
    build,
    cases,
    generated_confirmation,
    reference_helpers,
    worker,
)
from evidence_gap_router import Policy, Resources
from evidence_gap_router.router import _needed_helper_actions

SMALL = tuple(case for case in cases() if case["depth"] <= 8)


def test_manifest_enumerates_finite_39_cases_without_outcome_filtering():
    values = cases()
    assert len(values) == 39
    assert len({c["id"] for c in values}) == 39
    assert {
        (c["depth"], c["alternatives"])
        for c in values
        if c["topology"] == "chain" and c["boundary"] == "none"
    } == {
        (depth, alternatives) for depth in (4, 8, 12, 16, 24, 32, 64) for alternatives in (1, 2, 4)
    }
    assert {c["topology"] for c in values} == {"chain", "diamond", "shared", "branches", "cycle"}


@pytest.mark.parametrize("case", SMALL, ids=lambda c: c["id"])
def test_small_real_history_helper_inputs_agree_with_independent_reference(case):
    fixture = build(case)
    state = fixture["state"]
    assert len(state.attempts) == len(state.results) == fixture["initial_callbacks"]
    assert all(r.status == "completed" and r.actual_resources.actions == 1 for r in state.results)
    assert reference_helpers(fixture) == _needed_helper_actions(
        state, fixture["pool"], fixture["budget"], fixture["policy"]
    )
    outcome = _sequence(fixture)
    assert len(state.results) == fixture["initial_callbacks"]
    if outcome["decision"].action is not None:
        assert len(outcome["after"].results) == len(state.results) + 1
        assert outcome["after"].attempts[-1].action == outcome["decision"].action
        assert outcome["receipt"].actual_resources.actions == 1
    else:
        assert outcome["after"] == state
        assert outcome["receipt"] is None


def test_reference_does_not_delegate_to_sdk_plan_or_acceptance():
    fixture = build(cases()[0])
    with (
        patch("evidence_gap_router.plan", side_effect=AssertionError("delegated")),
        patch("evidence_gap_router.make_basis", side_effect=AssertionError("delegated")),
        patch("evidence_gap_router.router._Evaluation", side_effect=AssertionError("delegated")),
        patch(
            "evidence_gap_router.router._helper_actions", side_effect=AssertionError("delegated")
        ),
    ):
        assert reference_helpers(fixture) == {f"read-{i}-0" for i in range(4)}


def test_reference_rechecks_changed_authority_budget_and_candidate_scope():
    fixture = build(cases()[0])
    original = reference_helpers(fixture)
    assert original
    state, budget, policy = (fixture[k] for k in ("state", "budget", "policy"))
    fixture["policy"] = Policy(**{**policy.model_dump(), "available_handlers": ("check",)})
    assert reference_helpers(fixture) == frozenset()
    fixture["policy"] = policy
    fixture["budget"] = type(budget)(
        limits=Resources(actions=len(state.results), verifications=100)
    )
    assert reference_helpers(fixture) == frozenset()
    fixture["budget"] = budget
    pool = fixture["pool"]
    fixture["pool"] = tuple(
        type(a)(**{**a.model_dump(), "scope": "wrong"}) if a.id == "read-0-0" else a for a in pool
    )
    assert reference_helpers(fixture) == frozenset()
    fixture["pool"] = tuple(reversed(pool))
    assert reference_helpers(fixture) == original


def test_unused_seed_generator_changes_conditions_and_topology_not_only_ids():
    # This development seed is deliberately not the frozen confirmation seed.
    generated = generated_confirmation(22041, 32)
    assert generated == generated_confirmation(22041, 32)
    assert generated != generated_confirmation(22042, 32)
    assert len(generated) == 32
    assert len({json.dumps(c["parents"]) for c in generated}) >= 20
    assert {
        tuple(c["available_handlers"]) if c["available_handlers"] is not None else None
        for c in generated
    } == {None, (), ("read",), ("check",)}
    assert {c["remaining_actions"] for c in generated} >= {0, 1, 10000}
    for case in generated:
        fixture = build(case)
        assert reference_helpers(fixture) == _needed_helper_actions(
            fixture["state"], fixture["pool"], fixture["budget"], fixture["policy"]
        ), case


def test_count_records_actual_new_graph_calls_in_each_runtime_phase():
    row = worker(cases()[0], "count")
    assert row["reference_agrees"]
    assert row["repeats"] == 1 and row["warmup"] == 0
    assert row["peak_traced_python_allocation_bytes"] is None
    assert row["binding_progress"] is True
    for phase in ("plan", "start_observe", "binding_progress"):
        visits = row["visits_by_phase"][phase]
        assert visits["_HelperGraph.solve"] == 1
        assert visits["_helper_actions.<locals>.expand_action"] == row["candidate_count"]
        assert visits["_HelperGraph._consume_edge"] <= 4 * (
            row["candidate_count"] + row["dependency_incidence"]
        )
        assert visits["_Evaluation.__init__"] == 1


def test_time_and_memory_are_separate_from_count_instrumentation():
    with (
        patch("sys.setprofile", side_effect=AssertionError("profiled normal time")),
        patch("tracemalloc.start", side_effect=AssertionError("traced normal time")),
    ):
        timed = worker(cases()[0], "time")
    assert timed["warmup"] == 1 and timed["repeats"] == 10
    assert timed["visits_by_phase"] == {}
    assert all(len(samples) == 10 for samples in timed["phase_samples_seconds"].values())
    with patch("sys.setprofile", side_effect=AssertionError("profiled memory")):
        memory = worker(cases()[0], "memory")
    assert memory["peak_traced_python_allocation_bytes"] > 0
    assert memory["repeats"] == 1
    assert "not RSS" in memory["memory_scope"]


def test_large_semantic_reference_is_explicitly_unassessed_and_inputs_are_bounded():
    case = next(c for c in cases() if c["depth"] == 12 and c["alternatives"] == 1)
    row = worker(case, "semantic")
    assert row["status"] == "completed"
    assert row["reference_assessed"] is False
    assert row["reference_agrees"] is None and row["reference_helper_ids"] is None
    with pytest.raises(ValueError, match="bound exceeded"):
        build({**case, "depth": 65})
    with pytest.raises(ValueError, match="unknown helper worker mode"):
        worker(case, "invalid")


def test_worker_cli_emits_one_reproducible_json_record():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.helper_scaling_022",
            "--case-json",
            json.dumps(cases()[0]),
            "--mode",
            "semantic",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    row = json.loads(result.stdout)
    assert row["case"] == cases()[0]
    assert row["reference_agrees"] and row["callback_calls"] == 1
    assert row["initial_callbacks"] == 1
