"""Current SDK cannot turn a historical comparison into a new performance claim."""

from unittest.mock import patch

import pytest

from evidence_gap_router import Policy, plan
from evidence_gap_router.comparison import _scenario, compare


def test_historical_comparison_stops_before_scenario_or_callback():
    with patch(
        "evidence_gap_router.comparison._scenario", side_effect=AssertionError("new comparison")
    ):
        with pytest.raises(ValueError, match="original tag"):
            compare()


@pytest.mark.parametrize("name", ("A04_recheck", "A05_provenance", "dependency_recheck"))
def test_retained_static_seed_fixture_does_not_gain_completion_authority(name):
    state, _, budget, _ = _scenario(name)
    decision = plan(state, (), budget, Policy())
    assert decision.stop_reason != "satisfied"
    assert all(not result.finite_complete for result in decision.completion)
    assert state.checks and all(c.status == "PASS" for c in state.checks)
