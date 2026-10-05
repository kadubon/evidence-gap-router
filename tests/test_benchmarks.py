"""Generator/oracle/cluster checks; measured outcomes are not assertions of wins."""

import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.aggregate import summarize  # noqa: E402
from benchmarks.harness import World, file_oracle, oracle, trial  # noqa: E402
from benchmarks.scaling import graph_state, reference  # noqa: E402
from benchmarks.tasks import generate  # noqa: E402


def test_holdout_contains_240_distinct_material_budget_tasks_without_execution():
    tasks = generate("holdout")
    assert len(tasks) == 240
    assert all(sum(t.family == family for t in tasks) == 30 for family in {t.family for t in tasks})
    assert (
        len(
            {
                (
                    t.family,
                    t.value,
                    t.threshold,
                    t.mode,
                    t.sources,
                    t.checkers,
                    t.actions,
                    t.verifications,
                )
                for t in tasks
            }
        )
        == 240
    )
    assert {t.seed for t in tasks}.isdisjoint({t.seed for t in generate("development")})


def test_oracle_detects_numeric_precision_without_router_predicates():
    raw = b"order_id,amount,currency\nA,9007199254740992,USD\n"
    rules = (
        b'{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
        b'"minimum_amount":9007199254740993.0,"allowed_currencies":["USD"]}'
    )
    assert not file_oracle(raw, rules)
    assert file_oracle(raw, rules.replace(b"9007199254740993.0", b"9007199254740992.0"))


def test_actual_history_oracle_needs_matching_receipt_and_current_dependencies():
    task = next(t for t in generate("development") if t.family == "F4" and t.index == 3)
    world = World(task, "original")
    world.initialize()
    assert world.state.results and world.state.invalidations
    assert not oracle(world, world.state)["completion"]
    row = trial(task, "original", "fixed-feasible", 0, {})
    assert row["status"] == "completed" and row["oracle"]["completion"]
    assert row["initialization_actions"] == 4 and 3 <= row["callbacks"] <= task.actions


def test_shared_feasible_baseline_and_small_graph_reference():
    for graph in ("chain", "diamond", "branches", "cycle"):
        state, budget, policy, edges = graph_state(4, 2, graph)
        import evidence_gap_router as s

        assert (s.plan(state, (), budget, policy).stop_reason == "satisfied") == reference(edges, 4)


def test_random_repetitions_variants_are_one_parent_not_six_independent_tasks():
    task = next(t for t in generate("development") if t.family == "F6" and t.index == 1)
    row = trial(task, "original", "random-feasible", 17, {})
    variants = [json.loads(json.dumps(row)) for _ in range(6)]
    summary = summarize(variants)
    assert summary["unique_parent_tasks"] == 1
    assert summary["tables"][0]["supported_parents"] == 1
    assert summary["parents"][0]["repetitions"] == 6


def test_aggregate_keeps_failed_variants_and_unknown_cost_in_primary_denominator():
    task = next(t for t in generate("development") if t.family == "F6" and t.index == 1)
    good = trial(task, "original", "fixed-feasible", 0, {})
    failed = json.loads(json.dumps(good))
    failed.update(
        variant="reversed",
        status="exception",
        oracle=None,
        callbacks=None,
        verifications=None,
        exception="declared test failure",
        router_satisfied=False,
    )
    summary = summarize([good, failed])
    parent = summary["parents"][0]
    assert parent["completion"] == 0.5 and parent["supported"]
    assert parent["unknown_callback_cost_repetitions"] == 1
    assert summary["tables"][0]["completion_numerator"] == 1
    assert summary["tables"][0]["cluster_mean_completion_sum"] == 0.5
    assert parent["exceptions"] == 1


def test_oracle_does_not_label_router_satisfied_as_raw_truth():
    task = next(t for t in generate("development") if t.family == "F6" and t.mode == 4)
    world = World(task, "original")
    world.compute = lambda view: (
        "PASS",
        "deliberately incorrect checker used only in oracle unit test",
    )
    report = world.s.run(
        world.state,
        world.pool,
        world.budget,
        world.policy,
        {"read": world.recorded_callback, "check": world.recorded_callback},
    )
    assert report.decision.stop_reason == "satisfied"
    assert not oracle(world, report.state)["completion"]


def test_oracle_ignores_invalidated_negative_but_keeps_its_history():
    task = next(t for t in generate("development") if t.family == "F5" and t.mode == 1)
    world = World(task, "original")
    world.initialize()
    check = world.state.checks[0]
    event = world.s.Invalidation(
        id="oracle-unit-expiry",
        kind="check",
        target_id=check.id,
        obligation_id="task",
        scope=world.scope,
        reason="host expiry",
    )
    state = world.s.invalidate(world.state, event)
    report = world.s.run(
        state,
        world.pool,
        world.budget,
        world.policy,
        {"read": world.recorded_callback, "check": world.recorded_callback},
    )
    assert check in report.state.checks
    assert oracle(world, report.state)["completion"]
    assert not oracle(world, report.state)["negative_records_remaining"]


def test_current_target_completion_is_distinct_from_validated_subset_goal():
    task = next(t for t in generate("development") if t.family == "F4" and t.mode == 5)
    world = World(task, "original")
    world.initialize()
    assessed = oracle(world, world.state)
    assert assessed["raw_goal_met"] and not assessed["completion"]
    assert assessed["unchecked_current_target_ids"] == ["unrelated"]


def test_resolution_reopens_and_re_resolves_with_actual_receipts():
    task = next(t for t in generate("development") if t.family == "F4" and t.index == 6)
    row = trial(task, "original", "egr", 0, {})
    assert row["status"] == "completed" and row["oracle"]["completion"], row
    assert row["initialization_actions"] == 6 and row["callbacks"] == 2
    events = row["state"]["supersessions"]
    assert len(events) == 2 and {s["target_id"] for s in events} == {"disputed"}
    assert events[0]["check_id"] != events[1]["check_id"]


def test_prohibited_self_checker_is_not_called_and_allowed_alternative_is_used():
    task = next(t for t in generate("development") if t.family == "F3" and t.mode == 2)
    row = trial(task, "original", "egr", 0, {})
    assert row["oracle"]["completion"] and row["callbacks"] == 1
    assert [r["action"]["checker_id"] for r in row["trace"]] == ["checker-1"]


def test_initially_complete_pipeline_needs_no_continuation_callbacks():
    task = next(t for t in generate("development") if t.family == "F6" and t.mode == 5)
    for method in ("egr", "fixed-feasible", "verify-first"):
        row = trial(task, "original", method, 0, {})
        assert row["oracle"]["completion"] and row["callbacks"] == 0
        assert row["initialization_actions"] == 2


def test_baseline_rejects_an_old_receipt_replayed_for_a_new_invocation():
    task = next(t for t in generate("development") if t.family == "F1" and t.index == 1)
    world = World(task, "original")
    world.initialize()
    old = world.state.results[0]
    pool = world.pool(world.state)
    action = world.s.feasible_actions(world.state, pool, world.budget, world.policy)[0]
    world.callback = lambda view: old
    updated, error = world.issue(world.state, action, world.budget, pool)
    assert error and "does not match" in error
    assert len(updated.results) == len(world.state.results) + 1
    assert updated.results[-1].status == "unknown"
    assert updated.results[-1].actual_resources.actions == 1


def test_supported_file_boundary_roundtrip_is_not_the_cli_json_bound():
    original = next(t for t in generate("development") if t.family == "F8" and t.mode == 5)
    boundary = replace(original, id="development-F8-snapshot-boundary", index=29)
    row = trial(boundary, "original", "egr", 0, {})
    assert row["oracle"]["completion"] and row["snapshot_resume"]
    assert len(json.dumps(row["state"]).encode()) > 1048576


def test_common_whole_worker_deadline_retains_unknown_outcomes_for_all_arms(tmp_path, monkeypatch):
    import subprocess

    import benchmarks.harness as harness

    protocol = harness.manifest()
    protocol["task_timeout_seconds"] = 0.001
    monkeypatch.setattr(harness, "manifest", lambda: protocol)
    requested = []

    def timed_out(command, **kwargs):
        requested.append((json.loads(kwargs["input"])["method"], kwargs["timeout"]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(harness.subprocess, "run", timed_out)
    path = tmp_path / "development-timeouts.jsonl"
    harness.run_trials("development", path, limit=1, frozen={"implementation_commit": "a" * 40})
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert {method for method, _ in requested} >= {"egr", "fixed-feasible", "direct-pipeline"}
    assert all(timeout <= 0.001 for _, timeout in requested)
    assert all(r["status"] == "timeout" and r["right_censored"] for r in rows)
    assert all(r["oracle"] is None and r["false_satisfied"] is None for r in rows)
    assert all(r["callbacks"] is None and r["implementation_commit"] == "a" * 40 for r in rows)
    assert not any(p["correct_abstention"] for p in summarize(rows)["parents"])


def test_version_pairs_keep_compatible_failed_arm_and_separate_unknown_false_satisfied():
    task = next(t for t in generate("development") if t.family == "F6" and t.index == 1)
    new = trial(task, "original", "egr", 0, {})
    old = json.loads(json.dumps(new))
    old["environment"]["package"] = "0.2.0"
    old.update(status="timeout", timeout=True, oracle=None, false_satisfied=None, callbacks=None)
    summary = summarize([new, old])
    pair = next(p for p in summary["version_comparisons"] if p["family"] == "all")
    assert pair["paired_solvable_parents"] == 1 and pair["completion_difference"] == 1
    assert pair["old_unassessed_false_satisfied_repetitions"] == 1
