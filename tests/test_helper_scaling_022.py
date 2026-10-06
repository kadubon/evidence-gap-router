"""Portable checks for the new helper measurement inputs and independent oracle."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest.mock import patch

import pytest

from benchmarks.helper_scaling_022 import (
    _transition,
    build,
    cases,
    generated_confirmation,
    reference_helpers,
    worker,
)
from evidence_gap_router import Policy, Resources
from evidence_gap_router.router import _needed_helper_actions


@pytest.fixture(autouse=True)
def fixed_fixture_clock(monkeypatch):
    from types import SimpleNamespace

    import benchmarks.helper_scaling_022 as helpers

    monkeypatch.setattr(
        helpers, "time", SimpleNamespace(perf_counter=lambda: 0, process_time=lambda: 0)
    )


def _sequence(fixture):
    import evidence_gap_router as sdk
    from evidence_gap_router.runner import _binding_progress

    state, pool, budget, policy = (fixture[k] for k in ("state", "pool", "budget", "policy"))
    decision = sdk.plan(state, pool, budget, policy)
    after, receipt = state, None
    if decision.action is not None:
        after, receipt = _transition(
            state, decision.action, pool, budget, policy, fixture["world"], "test-step"
        )
        _binding_progress(state, after, pool, budget, policy, decision.action)
    return {"decision": decision, "after": after, "receipt": receipt}


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


@pytest.mark.parametrize("mode", ("time", "memory", "count", "semantic"))
def test_historical_worker_rejects_new_sdk_before_measurement(mode):
    with patch("tracemalloc.start", side_effect=AssertionError("new allocation measurement")):
        with pytest.raises(ValueError, match="original tag"):
            worker(cases()[0], mode)


def test_large_fixture_remains_bounded_without_worker_measurements():
    with pytest.raises(ValueError, match="bound exceeded"):
        build({**cases()[0], "depth": 65})


def test_worker_cli_refuses_current_sdk_and_emits_no_measurement_record():
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
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0 and not result.stdout
    assert "original tag" in result.stderr
