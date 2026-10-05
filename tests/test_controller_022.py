"""Preregistered keys and failed observation retention; no formal runs."""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.controller_022 import specifications, unavailable_row  # noqa: E402
from benchmarks.tasks import manifest  # noqa: E402


def test_all_keys_are_predeclared_unique_and_deterministic():
    first = specifications()
    assert first == specifications()
    assert len({row["spec_sha256"] for row in first}) == len(first) == 1680
    assert Counter(row["phase"] for row in first) == {
        "regression": 1020,
        "audit": 2,
        "scaling": 594,
        "confirmation": 64,
    }
    assert [row["sequence_index"] for row in first] == list(range(len(first)))


def test_full_regression_pool_and_paired_scaling_blocks():
    specs = specifications()
    regression = [r for r in specs if r["phase"] == "regression"]
    for family in manifest()["families"]:
        assert len({r["task"]["id"] for r in regression if r["task"]["family"] == family}) == 30
    assert {r["variant"] for r in regression} == {"original"}
    assert {r["seed"] for r in regression if r["method"] == "random-feasible"} == {17}
    cells = [r for r in specs if r["phase"] in {"scaling", "confirmation"}]
    for index in range(0, len(cells), 2):
        a, b = cells[index : index + 2]
        assert {a["version"], b["version"]} == {"0.2.1", "0.2.2"}
        assert {
            k: v for k, v in a.items() if k not in {"version", "sequence_index", "spec_sha256"}
        } == {k: v for k, v in b.items() if k not in {"version", "sequence_index", "spec_sha256"}}


def test_unexecuted_rows_preserve_unknowns_and_correct_baseline_identity():
    spec = next(r for r in specifications() if r["kind"] == "method")
    frozen = json.loads((Path(__file__).parents[1] / "benchmarks/results/freeze.json").read_text())
    frozen["baseline_runtime_commit"] = manifest()["baseline_runtime_commit"]
    row = unavailable_row(spec, frozen, "experiment_budget_exhausted")
    assert row["oracle"] is None and row["callbacks"] is None
    assert row["worker_status"] == "unexecuted" and row["state"] is None
    assert row["task"] == spec["task"] and row["environment"]["package_import"] is None


@pytest.mark.parametrize("missing", ["worker_cpu", "worker_memory", "parent_memory"])
def test_missing_constrained_resource_observation_stops_dependent_workers(
    tmp_path, monkeypatch, missing
):
    import benchmarks.controller_022 as controller
    import benchmarks.worker_limits as limits

    frozen = json.loads((Path(__file__).parents[1] / "benchmarks/results/freeze.json").read_text())
    frozen["baseline_runtime_commit"] = manifest()["baseline_runtime_commit"]
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(frozen))
    specs = specifications()[:2]
    monkeypatch.setattr(controller, "specifications", lambda: specs)
    monkeypatch.setattr(controller, "validate_freeze", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(
        limits, "parent_resources", lambda: (0, None if missing == "parent_memory" else 1)
    )
    calls = []

    def worker(command, **kwargs):
        spec = specs[len(calls)]
        calls.append(spec)
        return {
            "worker_status": "completed",
            "stdout": json.dumps({"spec": spec, "status": "completed"}),
            "stderr": "",
            "whole_worker_cpu_seconds": None if missing == "worker_cpu" else 0.01,
            "peak_worker_memory_bytes": None if missing == "worker_memory" else 1,
        }

    monkeypatch.setattr(controller, "run_worker", worker)
    output = tmp_path / "results"
    controller.run(output, freeze_path, {"0.2.1": "old", "0.2.2": "new"})
    rows = [json.loads(line) for line in (output / "raw.jsonl").read_text().splitlines()]
    assert len(calls) == (0 if missing == "parent_memory" else 1)
    assert rows[-1]["worker_status"] == "unexecuted"
    assert rows[-1]["oracle"] is None and rows[-1]["callbacks"] is None
    assert "unavailable" in rows[-1]["stop_reason"]


def test_late_resource_cap_retains_complete_observation_with_failed_worker_status(
    tmp_path, monkeypatch
):
    import benchmarks.controller_022 as controller
    import benchmarks.worker_limits as limits

    frozen = json.loads((Path(__file__).parents[1] / "benchmarks/results/freeze.json").read_text())
    frozen["baseline_runtime_commit"] = manifest()["baseline_runtime_commit"]
    freeze_path = tmp_path / "freeze.json"
    freeze_path.write_text(json.dumps(frozen))
    spec = specifications()[0]
    monkeypatch.setattr(controller, "specifications", lambda: (spec,))
    monkeypatch.setattr(controller, "validate_freeze", lambda *args, **kwargs: frozen)
    monkeypatch.setattr(limits, "parent_resources", lambda: (0, 1))
    monkeypatch.setattr(
        controller,
        "run_worker",
        lambda *args, **kwargs: {
            "worker_status": "resource_limit",
            "stdout": json.dumps(
                {"spec": spec, "trace": ["actual"], "oracle": {"completion": True}}
            ),
            "stderr": "",
            "whole_worker_cpu_seconds": 8.1,
            "peak_worker_memory_bytes": 1,
        },
    )
    output = tmp_path / "results"
    controller.run(output, freeze_path, {"0.2.1": "old", "0.2.2": "new"})
    row = json.loads((output / "raw.jsonl").read_text())
    assert row["worker_status"] == row["status"] == "resource_limit"
    assert row["observation_complete"] and row["trace"] == ["actual"]
    assert row["oracle"] == {"completion": True} and "trace_unavailable_reason" not in row
