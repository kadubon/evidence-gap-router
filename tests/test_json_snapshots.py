from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CallbackView,
    CheckerPermission,
    HandlerRegistration,
    Obligation,
    PlanInput,
    Policy,
    Resources,
    State,
    dump_json,
    load_json,
    plan,
    read_json,
    run,
    start,
    step,
    write_json,
)
from evidence_gap_router.file_checks import check_data
from evidence_gap_router.jsonio import MAX_JSON_BYTES, MAX_SNAPSHOT_BYTES
from evidence_gap_router.models import Record


def test_EGR020_07_max_rows_unicode_bom_crlf_snapshot_save_reload_continue(tmp_path: Path) -> None:
    directory = tmp_path / "日本語 空白"
    directory.mkdir()
    data = directory / "注文.csv"
    dictionary = directory / "規則.json"
    raw = (
        b"\xef\xbb\xbf"
        + (
            "order_id,amount,currency\r\n" + "".join(f"注文{i},10,USD\r\n" for i in range(10_000))
        ).encode()
    )
    rules = (
        b"\xef\xbb\xbf"
        + (
            '{"description":"十進数の規則","required_columns":["order_id","amount","currency"],'
            '"primary_key":"order_id","minimum_amount":0.0000000000000000001,'
            '"allowed_currencies":["USD"]}'
        ).encode()
    )
    assert len(raw) < MAX_JSON_BYTES
    data.write_bytes(raw)
    dictionary.write_bytes(rules)
    report = check_data(data, dictionary)
    assert report["outcome"] == "satisfied"
    state = State.model_validate_json(json.dumps(report["state"]))
    serialized = dump_json(state)
    assert MAX_JSON_BYTES < len(serialized.encode()) < MAX_SNAPSHOT_BYTES
    restored = load_json(serialized, State)
    assert restored == state
    assert len(restored.attempts) == len(restored.results) == 4
    assert (
        next(e.digest for e in restored.evidence if e.id == "dataset")
        == hashlib.sha256(raw).hexdigest()
    )
    snapshot = directory / "状態 snapshot.json"
    write_json(restored, snapshot)
    saved = read_json(snapshot, State)
    assert saved == state
    policy = Policy.model_validate_json(json.dumps(report["decision"]["coverage"]["policy"]))
    budget = Budget(limits=Resources(actions=4, verifications=2))
    resumed = run(saved, (), budget, policy, {})
    assert resumed.decision.stop_reason == "satisfied"
    assert resumed.callback_calls == ()
    assert resumed.state.results == state.results
    assert sum(result.actual_resources.actions for result in resumed.state.results) == 4
    assert data.read_bytes() == raw and dictionary.read_bytes() == rules
    offline_input = PlanInput(state=state, candidates=(), budget=budget, policy=policy)
    with pytest.raises(ValueError, match="1048576"):
        dump_json(offline_input)
    with pytest.raises(ValueError, match="1048576"):
        read_json(snapshot, PlanInput)


def test_save_rejection_preserves_existing_file_without_temp_success_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = State(obligations=(Obligation(id="o", scope="s", description="d", acceptance="a"),))
    target = tmp_path / "保存.json"
    target.write_text("existing host data", encoding="utf-8")
    monkeypatch.setattr("evidence_gap_router.jsonio.MAX_SNAPSHOT_BYTES", 64)
    with pytest.raises(ValueError, match="64 byte"):
        write_json(state, target)
    assert target.read_text(encoding="utf-8") == "existing host data"
    assert tuple(tmp_path.iterdir()) == (target,)
    with pytest.raises(ValueError, match="64 byte"):
        load_json(state.model_dump_json(), State)


def test_pending_and_unknown_actual_histories_roundtrip_and_do_not_reissue(tmp_path: Path) -> None:
    obligation = Obligation(
        id="sum", scope="例", description="inspect", acceptance="4", required_verifiers=("v",)
    )
    policy = Policy(
        trusted_verifiers=("v",),
        handlers=(
            HandlerRegistration(handler_id="read", roles=("investigate",)),
            HandlerRegistration(
                handler_id="verify",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id="v"),),
            ),
        ),
    )
    budget = Budget(limits=Resources(actions=4, verifications=2))
    acquisition = ActionCandidate(
        id="read",
        obligation_id="sum",
        scope="例",
        kind="investigate",
        handler_id="read",
        produces_evidence_id="answer",
    )

    def reader(view: CallbackView):
        from evidence_gap_router import Evidence

        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(
                Evidence(
                    id="answer",
                    obligation_id="sum",
                    scope="例",
                    digest=hashlib.sha256(b"4").hexdigest(),
                    content="4",
                    producer="read",
                    source="local",
                    provenance_group="local",
                ),
            ),
        )

    acquired = step(
        State(obligations=(obligation,)), (acquisition,), budget, policy, {"read": reader}
    ).state
    action = ActionCandidate(
        id="verify",
        obligation_id="sum",
        scope="例",
        kind="verify",
        handler_id="verify",
        checker_id="v",
        target_evidence_id="answer",
        target_digest=acquired.evidence[0].digest,
        resources=Resources(actions=1, verifications=1),
    )
    pending = start(acquired, action, "pending", budget, policy)
    path = tmp_path / "pending.json"
    write_json(pending, path)
    restored = read_json(path, State)
    resumed = run(restored, (action,), budget, policy, {"verify": lambda view: None})
    assert resumed.state == pending
    assert resumed.callback_calls == ()
    assert resumed.decision.stop_reason == "blocked"
    unknown = step(acquired, (action,), budget, policy, {"verify": lambda view: None})
    assert unknown.stop_reason == "callback_error"
    assert unknown.receipt is not None
    assert unknown.receipt.actual_resources.actions == 1
    assert unknown.receipt.actual_resources.verifications is None
    assert unknown.receipt.side_effects == "unknown"
    write_json(unknown.state, path)
    final = read_json(path, State)
    assert final == unknown.state
    assert final.results[0] == acquired.results[0]
    assert plan(final, (action,), budget, policy).stop_reason == "escalation_required"


@pytest.mark.parametrize("value", ["true", "1.0", "1e0"])
def test_exact_json_precheck_keeps_core_integer_fields_strict(value: str) -> None:
    with pytest.raises(ValueError):
        load_json('{"actions":' + value + "}", Resources)


def test_json_integer_decimal_and_depth_bounds_are_explicit() -> None:
    assert load_json('{"actions":' + "9" * 128 + "}", Resources).actions == int("9" * 128)
    for text, reason in (
        ('{"actions":' + "9" * 129 + "}", "128 digits"),
        ('{"actions":1e129}', "exponent"),
        ("[" * 65 + "0" + "]" * 65, "64 levels"),
    ):
        with pytest.raises(ValueError, match=reason):
            load_json(text, Resources)
    # JSON punctuation inside strings does not contribute to structural depth.
    state = State(
        obligations=(Obligation(id="o", scope="s", description="[{" * 100, acceptance="a"),)
    )
    assert load_json(dump_json(state), State) == state


def test_generic_sdk_serializer_preserves_existing_pydantic_datetime_uuid_support(
    tmp_path: Path,
) -> None:
    class CustomRecord(Record):
        at: datetime
        token: UUID

    record = CustomRecord(
        at=datetime(2026, 10, 5, 0, 0, tzinfo=UTC),
        token=UUID("6a46d1ae-1f93-4b21-bde0-f72c8304c243"),
    )
    text = dump_json(record)
    assert json.loads(text) == {"at": "2026-10-05T00:00:00Z", "token": str(record.token)}
    assert load_json(text, CustomRecord) == record
    path = tmp_path / "custom.json"
    write_json(record, path)
    assert read_json(path, CustomRecord) == record
