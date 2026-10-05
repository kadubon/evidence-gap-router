"""Main-method experiments differ only in selection through the public runner."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.aggregate import paired_costs, summarize  # noqa: E402
from benchmarks.erratum_021 import classify_stop, semantic_signature  # noqa: E402
from benchmarks.harness import World, trial  # noqa: E402
from benchmarks.tasks import generate  # noqa: E402

METHODS = ("egr", "fixed-feasible", "verify-first", "random-feasible")


def test_cost_differences_and_delay_sensitivity_keep_unknown_pairs_separate():
    a = {
        "callbacks": 2,
        "controller_wall_seconds": 0.02,
        "controller_cpu_seconds": 0.01,
        "cpu_seconds": 0.02,
    }
    b = {
        "callbacks": 3,
        "controller_wall_seconds": 0.01,
        "controller_cpu_seconds": 0.01,
        "cpu_seconds": 0.02,
    }
    result = paired_costs([(a, b), ({**a, "callbacks": None}, b)])
    assert result["metrics"]["callbacks"]["paired_parents"] == 1
    assert result["metrics"]["callbacks"]["paired_bootstrap_95_percent_interval"] == [-1, -1]
    assert result["metrics"]["controller_wall_seconds"]["paired_parents"] == 2
    assert result["delay_sensitivity"][0]["paired_parents"] == 1
    assert result["delay_sensitivity"][-1]["difference_egr_minus_baseline_seconds"] == -0.99


def test_old_ten_f7_parents_share_actions_receipts_state_stops_and_costs():
    tasks = [t for t in generate("regression") if t.family == "F7" and t.mode in {4, 5}]
    assert len(tasks) == 10
    for task in tasks:
        rows = [trial(task, "original", method, 17, {}) for method in METHODS]
        assert len({semantic_signature(r) for r in rows}) == 1
        classes = [classify_stop(r) for r in rows]
        assert len({c["terminal_class"] for c in classes}) == 1
        assert {r["runner_stop"] for r in rows} == {"router_stopped"}
        assert {r["callbacks"] for r in rows} == {1}
        if task.mode == 4:
            assert {c["terminal_class"] for c in classes} == {"uncertain_incomplete_stop"}
            assert not any(c["known_correct_abstention"] for c in classes)
            assert all(r["verifications"] is None for r in rows)
        else:
            assert {c["terminal_class"] for c in classes} == {"known_correct_abstention"}
            assert all(r["verifications"] == 0 for r in rows)


def test_all_main_methods_use_the_actual_public_run(monkeypatch):
    import evidence_gap_router as sdk

    actual = sdk.run
    calls = []

    def tracked(*args, **kwargs):
        calls.append(kwargs.get("selector"))
        return actual(*args, **kwargs)

    monkeypatch.setattr(sdk, "run", tracked)
    task = next(t for t in generate("development") if t.family == "F2" and t.index == 2)
    for method in METHODS:
        result = trial(task, "original", method, 17, {})
        assert result["status"] == "completed" and result["oracle"]["completion"]
    assert len(calls) == 4 and calls[0] is None and all(callable(s) for s in calls[1:])


def test_default_harness_trace_equivalent_to_direct_public_run():
    task = next(t for t in generate("development") if t.family == "F4" and t.mode == 0)
    row = trial(task, "original", "egr", 17, {})
    world = World(task, "original")
    try:
        world.initialize()
        report = world.s.run(
            world.state,
            world.pool,
            world.budget,
            world.policy,
            {"read": world.recorded_callback, "check": world.recorded_callback},
        )
        assert row["state"] == report.state.model_dump(mode="json")
        assert row["trace"] == world.trace and row["initial_trace"] == world.initial_trace
        assert row["runner_stop"] == report.stop_reason and row["exception"] == report.error
    finally:
        world.directory.cleanup()


def test_solvable_incomplete_stop_is_never_named_correct_abstention():
    task = next(t for t in generate("development") if t.family == "F7" and t.mode == 5)
    row = trial(task, "original", "fixed-feasible", 17, {})
    modified = json.loads(json.dumps(row))
    modified["task"]["solvable"] = True
    parent = summarize([modified])["parents"][0]
    assert parent["known_correct_abstention"] == 0 and parent["erroneous_stop"] == 1
    assert "correct_abstention" not in parent


def test_normal_trial_does_not_enable_allocation_instrumentation():
    import tracemalloc

    assert not tracemalloc.is_tracing()
    task = next(t for t in generate("development") if t.family == "F6" and t.mode == 5)
    row = trial(task, "original", "egr", 17, {})
    assert not tracemalloc.is_tracing()
    assert row["peak_traced_python_allocation_bytes"] is None
