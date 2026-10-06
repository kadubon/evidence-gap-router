"""Main-method experiments differ only in selection through the public runner."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.aggregate import paired_costs  # noqa: E402
from benchmarks.erratum_021 import classify_stop  # noqa: E402

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


def test_synthetic_stop_classification_keeps_unknown_and_pending_separate():
    row = {
        "status": "completed",
        "runner_stop": "router_stopped",
        "domain_stop": "blocked",
        "router_satisfied": False,
        "decision": {"action": None},
        "oracle": {"completion": False},
        "task": {"solvable": False},
        "resource_overrun": False,
        "budget": {"limits": {"actions": 1, "verifications": 1}},
        "callbacks": 1,
        "verifications": 0,
        "state": {
            "attempts": [{"id": "a"}],
            "results": [
                {
                    "attempt_id": "a",
                    "side_effects": "known",
                    "actual_resources": {"actions": 1, "verifications": 0},
                }
            ],
        },
    }
    assert classify_stop(row)["known_correct_abstention"]
    row["state"]["results"][0]["actual_resources"]["verifications"] = None
    assert classify_stop(row)["uncertain_incomplete_stop"]
    row["state"]["results"] = []
    assert "pending_invocation" in classify_stop(row)["uncertainty_reasons"]
