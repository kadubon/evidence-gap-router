"""The diagnostic driver has independent properties and records actual receipts."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import audit_022  # noqa: E402
from benchmarks.audit_022 import main, run_audit  # noqa: E402


def test_public_diagnostic_matrix_meets_new_properties_with_real_costed_records():
    report = run_audit()
    assert report["sdk_version"] == "0.2.2"
    assert report["all_expected_properties_met"], [
        (r["case"], r["exception"])
        for r in report["cases"]
        if not r["independent_expected_property_met"]
    ]
    assert len(report["cases"]) == 14
    partial = next(r for r in report["cases"] if r["case"] == "partial-external-basis")
    observation = partial["observation"]
    assert not observation["independent_resolution_inputs_valid"]
    assert not observation["resolve_accepted"]
    assert observation["attempts"] == observation["results"] == observation["actual_actions"] == 2
    assert len(observation["callback_trace"]) == 2
    assert not any(r["old021_issue_reproduced"] for r in report["cases"])


def test_audit_cli_writes_readable_actual_version_metadata(tmp_path):
    path = tmp_path / "audit.json"
    assert main(["--output", str(path)]) == 0
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["sdk_version"] == "0.2.2" and report["sdk_import"]
    assert report["all_expected_properties_met"]
    assert all("independent_expected_property_met" in row for row in report["cases"])


@pytest.mark.parametrize(
    "case",
    [
        audit_022.continuation_case,
        audit_022.contract_revision_case,
        audit_022.helper_progress_case,
        audit_022.proof_case,
    ],
)
def test_positive_receipts_alone_do_not_pass_when_domain_completion_is_blocked(monkeypatch, case):
    original = audit_022.state_observation

    def blocked(*args, **kwargs):
        observation = original(*args, **kwargs)
        observation["domain_stop"] = "escalation_required"
        return observation

    monkeypatch.setattr(audit_022, "state_observation", blocked)
    observation, met = case()
    assert observation["domain_stop"] != "satisfied" and not met
