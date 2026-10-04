from __future__ import annotations

import json
import socket
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    Obligation,
    PlanInput,
    Policy,
    Resources,
    Result,
    State,
)
from evidence_gap_router.cli import main
from evidence_gap_router.demo import run_demo, run_host_loop
from evidence_gap_router.jsonio import dump_json


def request() -> PlanInput:
    return PlanInput(
        state=State(
            obligations=(
                Obligation(id="o", description="Read source", scope="s", acceptance="checked"),
            )
        ),
        candidates=(
            ActionCandidate(
                id="a", obligation_id="o", scope="s", kind="investigate", handler_id="reader"
            ),
        ),
        budget=Budget(limits=Resources(actions=1, verifications=1)),
        policy=Policy(executable_handlers=("reader",), trusted_verifiers=("checker",)),
    )


def test_demo_success_uses_two_file_acquisitions_and_bound_real_checks() -> None:
    report = run_demo()
    assert report["artificial_data"] is True
    assert report["decision"]["stop_reason"] == "satisfied"
    assert report["callback_calls"] == [
        "read-csv",
        "read-dictionary",
        "verify-quality",
        "verify-quality",
    ]
    state = report["state"]
    assert len(state["evidence"]) == 2
    assert len(state["checks"]) == 2
    assert all(check["status"] == "PASS" for check in state["checks"])
    targets = {item["digest"] for item in state["evidence"]}
    assert {check["target_digest"] for check in state["checks"]} == targets
    assert {item["producer"] for item in state["evidence"]} == {"csv-reader", "dictionary-reader"}
    assert {check["verifier_id"] for check in state["checks"]} == {"quality-validator"}
    dataset = next(item for item in state["evidence"] if item["id"] == "dataset")
    assert json.loads(dataset["content"])["rows"][1]["amount"] == "25"
    assert files("evidence_gap_router").joinpath("data", "orders_valid.csv").is_file()
    assert all(
        result["target_digest"] == attempt["action"]["target_digest"]
        for result, attempt in zip(state["results"], state["attempts"], strict=True)
    )


def test_demo_invalid_preserves_computed_failures() -> None:
    report = run_demo("invalid")
    assert report["decision"]["stop_reason"] == "escalation_required"
    failed = [check for check in report["state"]["checks"] if check["status"] == "FAIL"]
    assert len(failed) == 1
    assert "duplicate primary key" in failed[0]["reason"]
    assert "amount is below" in failed[0]["reason"]
    assert "currency is not" in failed[0]["reason"]
    assert report["decision"]["coverage"]["satisfied"] == 0
    assert any(item["code"] == "check_failed" for item in report["decision"]["residuals"])


def test_demo_budget_stops_acquisition_without_claiming_verification() -> None:
    report = run_demo("budget")
    assert report["decision"]["stop_reason"] == "budget_exhausted"
    assert report["callback_calls"] == ["read-csv", "read-dictionary"]
    assert report["state"]["checks"] == []
    assert report["decision"]["coverage"]["ratio"] == 0
    assert report["decision"]["remaining_resources"]["actions"] == 0


def test_local_data_changes_results_instead_of_fixture_case_label(tmp_path: Path) -> None:
    data = tmp_path / "changed.csv"
    data.write_text("order_id,amount,currency\na,-1,JPY\n", encoding="utf-8")
    report = run_demo("valid", data_path=data)
    assert report["artificial_data"] is False
    assert report["decision"]["stop_reason"] != "satisfied"
    assert any(check["status"] == "FAIL" for check in report["state"]["checks"])


@pytest.mark.parametrize("mode", ["exception", "malformed", "wrong-action"])
def test_host_callback_uncertainty_is_charged_recorded_and_not_retried(mode: str) -> None:
    inp = request()
    calls = []

    def callback(action: ActionCandidate, attempt_id: str, state: State) -> Any:
        calls.append(action.id)
        if mode == "exception":
            raise TimeoutError("external outcome unknown")
        if mode == "malformed":
            return {"status": "PASS"}
        return Result(
            id="bad",
            attempt_id=attempt_id,
            action_id="other",
            obligation_id="o",
            scope="s",
            actual_resources=Resources(actions=1, verifications=0),
        )

    additional = inp.candidates[0].model_copy(update={"id": "b"})
    run = run_host_loop(
        inp.state, (*inp.candidates, additional), inp.budget, inp.policy, {"reader": callback}
    )
    assert calls == ["a"]
    assert len(run.state.attempts) == len(run.state.results) == 1
    result = run.state.results[0]
    assert result.status == "unknown"
    assert result.actual_resources.actions == 1
    assert result.actual_resources.verifications is None
    assert result.actual_resources.tokens is None
    assert result.side_effects == "unknown"
    assert result.action_id == "a"
    assert run.decision.stop_reason == "escalation_required"
    assert any(item.code == "unknown_resource" for item in run.decision.residuals)


def test_host_mapping_restricts_execution_to_actual_registered_callbacks() -> None:
    inp = request()
    run = run_host_loop(inp.state, inp.candidates, inp.budget, inp.policy, {})
    assert run.state.attempts == ()
    assert run.callback_calls == ()
    assert run.decision.stop_reason == "blocked"
    assert "handler_unavailable" in run.decision.exclusions[0].reasons


def test_host_replayed_receipt_cannot_hide_a_new_callback_invocation() -> None:
    inp = request()
    receipts: list[Result] = []

    def callback(action: ActionCandidate, attempt_id: str, state: State) -> Result:
        if receipts:
            return receipts[0]
        receipt = Result(
            id="first-receipt",
            attempt_id=attempt_id,
            action_id=action.id,
            obligation_id=action.obligation_id,
            scope=action.scope,
            actual_resources=Resources(actions=1, verifications=0),
        )
        receipts.append(receipt)
        return receipt

    actions = (inp.candidates[0], inp.candidates[0].model_copy(update={"id": "b"}))
    run = run_host_loop(
        inp.state,
        actions,
        Budget(limits=Resources(actions=2, verifications=1)),
        inp.policy,
        {"reader": callback},
    )
    assert len(run.state.attempts) == len(run.state.results) == 2
    assert sum(result.actual_resources.actions or 0 for result in run.state.results) == 2
    assert run.state.results[1].attempt_id == run.state.attempts[1].id
    assert run.state.results[1].status == "unknown"
    assert run.state.results[1].side_effects == "unknown"
    assert run.decision.stop_reason == "escalation_required"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "0.1.0"


@pytest.mark.parametrize(
    "case,code,stop",
    [
        ("valid", 0, "satisfied"),
        ("invalid", 2, "escalation_required"),
        ("budget", 2, "budget_exhausted"),
    ],
)
def test_cli_demo_json_and_domain_exit(
    case: str, code: int, stop: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["demo", "--case", case, "--json"]) == code
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["decision"]["stop_reason"] == stop


def test_cli_plan_is_offline_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    inp = request()
    # This declaration is data. No URL is fetched and no Python name is imported.
    action = inp.candidates[0].model_copy(
        update={"source": "https://invalid.example/never-fetch", "handler_id": "os.system"}
    )
    inp = inp.model_copy(
        update={
            "candidates": (action,),
            "policy": inp.policy.model_copy(update={"executable_handlers": ("os.system",)}),
        }
    )
    path = tmp_path / "plan.json"
    before = dump_json(inp)
    path.write_text(before, encoding="utf-8")

    def no_network(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("CLI plan attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    assert main(["plan", str(path), "--json"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    decision = json.loads(output.out)
    assert decision["action"]["handler_id"] == "os.system"
    assert decision["remaining_resources"]["actions"] == 1
    assert path.read_text(encoding="utf-8") == before
    assert main(["plan", str(path), "--json"]) == 0
    assert capsys.readouterr().out == output.out


@pytest.mark.parametrize(
    "invalid",
    [
        '{"schema_version":"1","schema_version":"1"}',
        '{"schema_version":"2"}',
        '{"state":NaN}',
        '{"state":Infinity}',
        '{"state":',
        "[]",
        '"' + "a" * 1_048_576 + '"',
    ],
    ids=("duplicate-key", "schema", "nan", "infinity", "syntax", "array", "oversized"),
)
def test_cli_bad_json_has_no_stdout(
    invalid: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "bad.json"
    path.write_text(invalid, encoding="utf-8")
    assert main(["plan", str(path), "--json"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.startswith("egr:")


@pytest.mark.parametrize("mutation", ["unknown-field", "bool-count", "unknown-schema"])
def test_cli_strict_schema_rejects_coercion_and_unknown_fields(
    mutation: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    value = request().model_dump(mode="json")
    if mutation == "unknown-field":
        value["state"]["evidence_policy"] = {"trusted_verifiers": ["untrusted"]}
    elif mutation == "bool-count":
        value["budget"]["limits"]["actions"] = True
    else:
        value["schema_version"] = "2"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert main(["plan", str(path), "--json"]) == 1
    assert capsys.readouterr().err.startswith("egr:")
