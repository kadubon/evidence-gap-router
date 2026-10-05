"""Deterministic installed benchmark smoke; identical generator/callbacks/oracle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Only this copied benchmark package is added; the installed SDK remains in venv.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.harness import trial  # noqa: E402
from benchmarks.scaling import graph_state, reference  # noqa: E402
from benchmarks.tasks import digest, generate  # noqa: E402


def smoke() -> dict:
    import evidence_gap_router as sdk

    assert "site-packages" in str(Path(sdk.__file__).resolve()), sdk.__file__
    selected = {
        ("F1", 0),
        ("F2", 2),
        ("F3", 2),
        ("F4", 1),
        ("F4", 6),
        ("F5", 3),
        ("F6", 1),
        ("F6", 5),
        ("F7", 2),
        ("F8", 3),
        ("F8", 5),
    }
    rows = []
    for task in generate("development"):
        if (task.family, task.index) not in selected:
            continue
        for method in ("egr", "fixed-feasible", "verify-first"):
            row = trial(task, "original", method, 0, {})
            assert row["status"] == "completed", row
            assert not row["false_satisfied"], row
            assert row["snapshot_resume"], row
            if task.family in {"F2", "F3", "F4", "F6", "F8"}:
                assert row["oracle"]["completion"] == task.solvable, row
            if task.family == "F1" and method == "egr":
                assert row["oracle"]["completion"] == task.solvable, row
            if task.family == "F5":
                assert not row["oracle"]["completion"], row
            rows.append(
                {
                    "task": task.id,
                    "method": method,
                    "completion": row["oracle"]["completion"],
                    "false_satisfied": row["false_satisfied"],
                    "callbacks": row["callbacks"],
                    "verifications": row["verifications"],
                    "stop": row["domain_stop"],
                    "snapshot_resume": row["snapshot_resume"],
                }
            )
    cycles = []
    for graph in ("chain", "diamond", "branches", "cycle"):
        state, budget, policy, edges = graph_state(4, 2, graph)
        expected = reference(edges, 4)
        actual = sdk.plan(state, (), budget, policy).stop_reason == "satisfied"
        assert actual == expected
        cycles.append({"graph": graph, "accepted": actual})
    canonical = json.dumps(
        {"trials": rows, "graphs": cycles}, sort_keys=True, separators=(",", ":")
    )
    return {
        "benchmark_smoke": "passed",
        "parents": len(selected),
        "trials": len(rows),
        "outcome_sha256": digest(canonical),
        "outcomes": rows,
        "graphs": cycles,
    }


if __name__ == "__main__":
    print(json.dumps(smoke(), sort_keys=True))
