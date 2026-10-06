"""Generator/oracle/cluster checks; measured outcomes are not assertions of wins."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.harness import file_oracle  # noqa: E402
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


@pytest.mark.parametrize(
    "method", ("egr", "fixed-feasible", "verify-first", "random-feasible", "direct-pipeline")
)
def test_historical_methods_reject_current_sdk_before_work(method, monkeypatch):
    from types import SimpleNamespace

    import benchmarks.harness as harness

    def forbidden():
        raise AssertionError("new measurement")

    monkeypatch.setattr(
        harness, "time", SimpleNamespace(perf_counter=forbidden, process_time=forbidden)
    )
    task = generate("development")[0]
    with pytest.raises(ValueError, match="original tag"):
        harness.trial(task, "original", method, 17, {})


def test_old_freeze_and_protocol_identity_remain_historical():
    protocol = json.loads((Path(__file__).parents[1] / "benchmarks/protocol.json").read_bytes())
    freeze = json.loads(
        (Path(__file__).parents[1] / "benchmarks/results/freeze-v0.2.2.json").read_bytes()
    )
    assert protocol["protocol"] == "egr-022-engineering-v1"
    assert len(freeze["candidate_package_sha256"]) == 64
