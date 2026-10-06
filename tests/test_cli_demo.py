from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from importlib.resources import files
from pathlib import Path
from typing import Any

import pytest

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    Evidence,
    HandlerRegistration,
    Obligation,
    PlanInput,
    Policy,
    Resources,
    Result,
    State,
    __version__,
)
from evidence_gap_router.cli import main
from evidence_gap_router.demo import run_cause_demo, run_demo
from evidence_gap_router.jsonio import dump_json
from evidence_gap_router.runner import CallbackView
from evidence_gap_router.runner import run as run_host_loop


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
        policy=Policy(
            handlers=(HandlerRegistration(handler_id="reader", roles=("investigate",)),),
            trusted_verifiers=("checker",),
        ),
    )


def test_demo_success_uses_two_file_acquisitions_and_bound_real_checks() -> None:
    report = run_demo()
    assert report["artificial_data"] is True
    assert report["decision"]["stop_reason"] == "satisfied"
    assert report["callback_calls"] == [
        "read-dictionary",
        "verify-quality",
        "read-csv",
        "verify-quality",
    ]
    state = report["state"]
    assert len(state["evidence"]) == 2
    assert len(state["checks"]) == 2
    assert all(check["status"] == "PASS" for check in state["checks"])
    targets = {item["digest"] for item in state["evidence"]}
    assert {check["target_digest"] for check in state["checks"]} == targets
    assert {item["producer"] for item in state["evidence"]} == {"read-csv", "read-dictionary"}
    assert {check["verifier_id"] for check in state["checks"]} == {
        "dictionary-checker",
        "orders-checker",
    }
    dataset_check = next(
        check for check in state["checks"] if check["verifier_id"] == "orders-checker"
    )
    assert dataset_check["basis"]["dependencies"][0]["evidence_id"] == "dictionary"
    assert dataset_check["basis"]["dependencies"][0]["requirement"] == "verified"
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
    assert report["decision"]["coverage"]["satisfied"] == 1
    assert report["decision"]["coverage"]["required"] == 2
    assert any(item["code"] == "check_failed" for item in report["decision"]["residuals"])


def test_demo_budget_stops_acquisition_without_claiming_verification() -> None:
    report = run_demo("budget")
    assert report["decision"]["stop_reason"] == "budget_exhausted"
    assert report["callback_calls"] == ["read-dictionary", "read-csv"]
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

    def callback(view: CallbackView) -> Any:
        calls.append(view.action.id)
        if mode == "exception":
            raise TimeoutError("external outcome unknown")
        if mode == "malformed":
            return {"status": "PASS"}
        return Result(
            id="bad",
            attempt_id=view.attempt_id,
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
    assert any("handler" in reason for reason in run.decision.exclusions[0].reasons)


def test_host_replayed_receipt_cannot_hide_a_new_callback_invocation() -> None:
    inp = request()
    receipts: list[Result] = []

    def callback(view: CallbackView) -> Result:
        if receipts:
            return receipts[0]
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(
                Evidence(
                    id="first",
                    obligation_id="o",
                    scope="s",
                    digest="a" * 64,
                    content="first material",
                    producer="reader",
                    source="source",
                    provenance_group="group",
                ),
            ),
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
    assert capsys.readouterr().out.strip() == __version__


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
            "policy": inp.policy.model_copy(
                update={
                    "handlers": (
                        HandlerRegistration(handler_id="os.system", roles=("investigate",)),
                    )
                }
            ),
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
        '{"schema_version":"3"}',
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
        value["schema_version"] = "4"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    assert main(["plan", str(path), "--json"]) == 1
    assert capsys.readouterr().err.startswith("egr:")


@pytest.mark.parametrize(
    "case,stop",
    [
        ("resolved", "satisfied"),
        ("invalid", "escalation_required"),
        ("conflict", "escalation_required"),
        ("unknown", "blocked"),
        ("provenance", "blocked"),
        ("budget", "budget_exhausted"),
    ],
)
def test_cause_materials_compute_outcomes_and_disclose_only_needed_inputs(
    case: str, stop: str
) -> None:
    report = run_cause_demo(case)
    assert report["decision"]["stop_reason"] == stop
    assert report["artificial_data"] is True
    acquisitions = [item for item in report["disclosures"] if item["handler"].startswith("read-")]
    assert len(acquisitions) == 3
    assert all(item["input_ids"] == [] for item in acquisitions)
    checks = report["state"]["checks"]
    assert all(check["basis"]["target"]["evidence_id"] for check in checks)
    if case == "resolved":
        reading = next(
            check for check in checks if check["basis"]["target"]["evidence_id"] == "reading"
        )
        assert {item["evidence_id"] for item in reading["basis"]["dependencies"]} == {
            "specification",
            "exceptions",
        }
        assert "applicable limit 20" in reading["reason"]
    elif case == "conflict":
        assert report["state"]["contradictions"]
        assert any(check["status"] == "UNKNOWN" for check in checks)
    elif case == "unknown":
        assert any(check["status"] == "UNKNOWN" for check in checks)
    elif case == "invalid":
        assert any(check["status"] == "FAIL" for check in checks)
    elif case == "provenance":
        assert any(item["code"] == "unknown_provenance" for item in report["decision"]["residuals"])


def test_cli_cause_example(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--example", "cause", "--case", "resolved", "--json"]) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["decision"]["stop_reason"] == "satisfied"


def test_json_cli_unicode_files_work_with_cp1252_stdout(tmp_path: Path) -> None:
    directory = tmp_path / "日本語 空白"
    directory.mkdir()
    data = directory / "注文 data.csv"
    data.write_text("order_id,amount,currency\n注文-一,10,USD\n", encoding="utf-8")
    dictionary = directory / "規則 rules.json"
    value = json.loads(
        files("evidence_gap_router").joinpath("data", "data_dictionary.json").read_bytes()
    )
    value["description"] = "日本語の最低金額"
    dictionary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    environment = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "evidence_gap_router.cli",
            "check-data",
            "--data",
            str(data),
            "--dictionary",
            str(dictionary),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == b""
    output = json.loads(completed.stdout.decode("ascii"))
    assert output["outcome"] == "satisfied"
    records = {item["id"]: item for item in output["state"]["evidence"]}
    assert records["dataset"]["source"] == str(data)
    assert json.loads(records["dataset"]["content"])["rows"][0]["order_id"] == "注文-一"
    assert json.loads(records["dictionary"]["content"])["description"] == "日本語の最低金額"
    # Offline planning emits declared Unicode scopes through the same ASCII
    # JSON contract. Changing the contract leaves the old checks inapplicable.
    for obligation in output["state"]["obligations"]:
        if obligation["id"] == "data-quality":
            obligation["scope"] = "注文の対象"
    request = {
        "schema_version": "3",
        "state": output["state"],
        "candidates": [],
        "budget": {"limits": {"actions": 4, "verifications": 2}},
        "policy": output["decision"]["coverage"]["policy"],
    }
    plan_file = directory / "計画 input.json"
    plan_file.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    planned = subprocess.run(
        [sys.executable, "-m", "evidence_gap_router.cli", "plan", str(plan_file), "--json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
    )
    assert planned.returncode == 2
    assert planned.stderr == b""
    decision = json.loads(planned.stdout.decode("ascii"))
    assert "注文の対象" in decision["coverage"]["scopes"]
    assert decision["stop_reason"] == "blocked"
