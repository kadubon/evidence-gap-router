"""Recorded stopping semantics are independent of runner-label spelling."""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.erratum_021 import (  # noqa: E402
    analyze_directory,
    classify_stop,
    semantic_signature,
    summarize_rows,
)


def recorded_row(*, solvable=False, runner="router_stopped"):
    return {
        "task_id": "recorded-F7",
        "task": {
            "family": "F7",
            "mode": 5,
            "budget_class": "adequate",
            "solvable": solvable,
            "actions": 3,
            "verifications": 1,
        },
        "environment": {"package": "0.2.1"},
        "method": "egr",
        "variant": "original",
        "random_seed": 17,
        "status": "completed",
        "timeout": False,
        "exception": None,
        "stop_reason": runner,
        "domain_stop": "blocked",
        "oracle": {"completion": False},
        "router_satisfied": False,
        "false_satisfied": False,
        "callbacks": 1,
        "verifications": 0,
        "resource_unknown": False,
        "resource_overrun": False,
        "decision": {"action": None, "pending_verifications": 0},
        "state": {
            "evidence": [{"id": "exact-material", "digest": "declared-digest"}],
            "attempts": [{"id": "issued-one", "action": {"id": "read:exact-material"}}],
            "results": [
                {
                    "id": "receipt-one",
                    "attempt_id": "issued-one",
                    "status": "completed",
                    "actual_resources": {"actions": 1, "verifications": 0, "tokens": None},
                    "side_effects": "known",
                }
            ],
        },
    }


def test_same_known_domain_stop_has_same_classification_with_different_runner_labels():
    egr = classify_stop(recorded_row())
    baseline = classify_stop(recorded_row(runner="no_progress"))
    assert egr["runner_stop"] != baseline["runner_stop"]
    assert {k: v for k, v in egr.items() if k != "runner_stop"} == {
        k: v for k, v in baseline.items() if k != "runner_stop"
    }
    assert egr["known_correct_abstention"]


@pytest.mark.parametrize("uncertainty", ["cost", "effects", "pending", "status", "bounds"])
def test_unknown_use_effects_pending_or_result_never_become_known_safe(uncertainty):
    row = recorded_row(runner="no_progress")
    receipt = row["state"]["results"][0]
    if uncertainty == "cost":
        receipt["actual_resources"]["verifications"] = None
        row["verifications"] = None
    elif uncertainty == "effects":
        receipt["side_effects"] = "unknown"
    elif uncertainty == "pending":
        row["state"]["attempts"].append({"id": "unfinished-invocation"})
    elif uncertainty == "status":
        receipt["status"] = "unknown"
    else:
        row["resource_overrun"] = None
    classified = classify_stop(row)
    assert not classified["known_correct_abstention"]
    assert classified["uncertain_incomplete_stop"]
    assert classified["uncertainty_reasons"]


def test_unconstrained_unknown_tokens_are_not_treated_as_a_known_charge_or_a_fault():
    row = recorded_row()
    assert classify_stop(row)["known_correct_abstention"]
    row["budget"] = {"limits": {"actions": 3, "verifications": 1, "tokens": 10}}
    assert classify_stop(row)["uncertain_incomplete_stop"]
    assert row["state"]["results"][0]["actual_resources"]["tokens"] is None


def test_unperformed_check_count_is_not_an_unreceipted_pending_invocation():
    row = recorded_row()
    row["decision"]["pending_verifications"] = 4
    assert classify_stop(row)["known_correct_abstention"]


def test_solvable_task_cannot_be_correct_abstention_and_unassessed_is_not_incomplete():
    row = recorded_row(solvable=True)
    assert classify_stop(row)["erroneous_stop"]
    assert not classify_stop(row)["known_correct_abstention"]
    row["oracle"] = None
    assert classify_stop(row)["terminal_class"] == "unassessed"
    assert not classify_stop(row)["erroneous_stop"]


@pytest.mark.parametrize("worker", ["exception", "timeout", "unsupported", "unexecuted"])
def test_worker_failure_or_missing_execution_is_not_domain_abstention(worker):
    row = recorded_row()
    row["status"] = worker
    classified = classify_stop(row)
    assert not classified["known_correct_abstention"]
    assert not classified["uncertain_incomplete_stop"]
    assert classified["execution_fault"] == (worker in {"exception", "timeout"})


def test_handled_fault_overrun_or_available_next_action_is_not_known_correct_stop():
    for changes in (
        {"exception": "callback receipt binding fault"},
        {"resource_overrun": True},
        {"decision": {"action": {"id": "available-next-action"}}},
    ):
        row = recorded_row()
        row.update(changes)
        assert not classify_stop(row)["known_correct_abstention"]


def test_false_satisfied_or_a_separate_pipeline_is_not_correct_abstention():
    row = recorded_row()
    row.update(router_satisfied=True, false_satisfied=True)
    assert classify_stop(row)["terminal_class"] == "false_satisfied"
    assert not classify_stop(row)["known_correct_abstention"]
    row = recorded_row()
    row.update(method="direct-pipeline", reference_only=True)
    summary = summarize_rows([row])
    assert not summary["tables"]
    assert summary["parents"][0]["reference_only"]


def test_reaggregation_keeps_parent_clustering_primary_seed_and_unassessed_costs():
    egr = recorded_row()
    baseline = recorded_row(runner="no_progress")
    baseline["method"] = "fixed-feasible"
    failed = copy.deepcopy(baseline)
    failed.update(variant="reversed", status="exception", oracle=None, verifications=None)
    unsupported = copy.deepcopy(egr)
    unsupported.update(task_id="unsupported-record", status="unsupported", oracle=None)
    summary = summarize_rows([egr, baseline, failed, unsupported])
    overall = {t["method"]: t for t in summary["tables"] if t["dimension"] == "overall"}
    assert overall["egr"]["correct_abstention_numerator"] == 1
    assert overall["fixed-feasible"]["correct_abstention_numerator"] == 0
    assert overall["egr"]["known_correct_abstention_numerator"] == 1
    assert overall["fixed-feasible"]["known_correct_abstention_numerator"] == 1
    assert overall["fixed-feasible"]["attempted_repetitions"] == 2
    assert overall["fixed-feasible"]["unknown_verification_cost_repetitions"] == 1
    assert overall["egr"]["requested_parents"] == 2
    assert overall["egr"]["supported_parents"] == 1
    random = []
    for seed in (17, 31, 73):
        row = recorded_row()
        row["method"], row["random_seed"] = "random-feasible", seed
        row["stop_reason"] = "router_stopped" if seed == 17 else "no_progress"
        random.append(row)
    assert summarize_rows(random)["parents"][0]["legacy_router_stop"]


def test_semantic_signature_normalizes_invocation_ids_but_preserves_material_identity():
    old = recorded_row()
    new = copy.deepcopy(old)
    new["state"]["attempts"][0]["id"] = "different-attempt-id"
    new["state"]["results"][0]["id"] = "different-receipt-id"
    new["state"]["results"][0]["attempt_id"] = "different-attempt-id"
    new["stop_reason"] = "no_progress"
    assert semantic_signature(old) == semantic_signature(new)
    new["state"]["evidence"][0]["id"] = "wrong-exact-material"
    assert semantic_signature(old) != semantic_signature(new)


def test_factual_material_id_is_not_normalized_even_if_it_matches_an_invocation_name():
    old = recorded_row()
    old["state"]["evidence"][0]["id"] = "issued-one"
    new = copy.deepcopy(old)
    new["state"]["attempts"][0]["id"] = "another-invocation"
    new["state"]["results"][0]["attempt_id"] = "another-invocation"
    assert semantic_signature(old) == semantic_signature(new)


def test_original_bundle_manifest_cannot_redirect_outside_raw_directory(tmp_path):
    (tmp_path / "MANIFEST.json").write_text(
        json.dumps({"../different-original.jsonl": {"bytes": 0, "sha256": "untrusted"}})
    )
    with pytest.raises(ValueError, match="Invalid bundle path"):
        analyze_directory(tmp_path)
