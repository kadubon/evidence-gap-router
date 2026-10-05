"""Matched synthetic comparison keeps neutral outcomes and semantic permutations."""

from evidence_gap_router.comparison import compare


def test_comparison_records_all_cases_and_permutations():
    report = compare()
    assert report["artificial_data"] is True
    assert len(report["results"]) == 9
    for row in report["results"]:
        for strategy in ("baseline", "router"):
            result = row[strategy]
            assert result["callback_calls"] <= row["budget"]["limits"]["actions"]
            assert result["verifications"] <= row["budget"]["limits"]["verifications"]
            assert result["satisfied"] + result["unresolved"] == result["required"]
        assert row["router"]["stop"] == "satisfied", row


def test_semantic_targets_survive_candidate_order_and_id_changes():
    report = compare()
    for scenario in ("A04_recheck", "A05_provenance", "dependency_recheck"):
        rows = [r for r in report["results"] if r["scenario"] == scenario]
        semantic_traces = [
            [(c["handler"], c["target"], c["produces"]) for c in r["router"]["calls"]] for r in rows
        ]
        assert semantic_traces[0] == semantic_traces[1] == semantic_traces[2]


def test_comparison_retains_no_advantage_cases_and_actual_rechecks():
    rows = compare()["results"]
    recheck = next(r for r in rows if r["scenario"] == "A04_recheck" and r["variant"] == "declared")
    assert recheck["baseline"]["calls"][0]["target"] == "first"
    assert recheck["router"]["calls"][0]["target"] == "second"
    assert recheck["baseline"]["stop"] == "budget_exhausted"
    reversed_order = next(
        r for r in rows if r["scenario"] == "A04_recheck" and r["variant"] == "reversed"
    )
    assert reversed_order["baseline"]["stop"] == reversed_order["router"]["stop"] == "satisfied"
    assert (
        reversed_order["baseline"]["callback_calls"] == reversed_order["router"]["callback_calls"]
    )
    for row in (r for r in rows if r["scenario"] == "dependency_recheck"):
        for strategy in ("baseline", "router"):
            assert row[strategy]["stop"] == "satisfied"
            assert row[strategy]["callback_calls"] == 3
            assert row[strategy]["verifications"] == 2
