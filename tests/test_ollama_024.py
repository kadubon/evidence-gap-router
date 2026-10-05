"""New long-request, durable receipt, termination and public-task contracts.

HTTP fixtures are local fakes, never evidence about the installed live models.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from test_ollama_client import PROFILE, SCHEMA, TAG, chat, client, fake_http, successful

from experiments.ollama import cli, ownership
from experiments.ollama.client import ClientBlocked, Limits, OllamaClient
from experiments.ollama.harness import TrialSettings
from experiments.ollama.prompts import CompactReview, integration_messages, validate_output
from experiments.ollama.tasks import calibration_tasks, confirmation_tasks, development_tasks


def modern(endpoint, directory, epoch="epoch-1", **changes):
    return OllamaClient(
        endpoint,
        directory / "requests.jsonl",
        run_id="egr-024-contract-test",
        freeze_id="a" * 64,
        profiles={TAG: PROFILE},
        limits=Limits(**changes),
        server_epoch=epoch,
        termination_policy=True,
    )


def proof(epoch="epoch-1"):
    return {
        "tree_stopped": True,
        "server_epoch": epoch,
        "proof_method": "held-native-process-handles",
        "identities": [
            {
                "pid": 11,
                "creation_filetime": 12345,
                "executable_sha256": "b" * 64,
                "executable_name": "ollama.exe",
            }
        ],
    }


def test_long_first_response_has_no_inherited_short_socket_deadline(tmp_path):
    with fake_http(successful(), delay=0.15, split_delay=0.15) as (url, received):
        result = chat(
            client(
                url,
                tmp_path,
                Limits(
                    request_wall_seconds=1, socket_timeout_seconds=0.02, read_until_deadline=True
                ),
            )
        )
        assert result["status"] == "ok" and len(received) == 1
        assert result["client_wall_seconds"] >= 0.25


def test_long_read_mode_still_enforces_independent_hard_deadline(tmp_path):
    with fake_http(successful(), delay=0.15) as (url, _):
        result = chat(
            client(url, tmp_path, Limits(request_wall_seconds=0.03, read_until_deadline=True))
        )
        assert result["status"] == "timeout" and result["unknown_consumption"]


def test_capture_before_interpretation_recovers_without_another_request(tmp_path, monkeypatch):
    with fake_http(successful()) as (url, received):
        connection = client(url, tmp_path)
        monkeypatch.setattr(
            connection, "_interpret", lambda *args: (_ for _ in ()).throw(RuntimeError("crash"))
        )
        with pytest.raises(RuntimeError):
            chat(connection)
        recovered = client(url, tmp_path)
        assert recovered.summary()["pending"] == ["request-1"]
        record = recovered.recover_receipt("request-1")
        assert record["status"] == "ok" and len(received) == 1
        assert recovered.recover_receipt("request-1") == record
        with pytest.raises(ClientBlocked):
            chat(recovered)


def test_receipt_tampering_or_torn_journal_does_not_recover(tmp_path, monkeypatch):
    with fake_http(successful()) as (url, received):
        connection = client(url, tmp_path)
        append = connection._append
        monkeypatch.setattr(
            connection,
            "_append",
            lambda r: (
                append(r) if r["event"] != "response" else (_ for _ in ()).throw(OSError("disk"))
            ),
        )
        with pytest.raises(OSError):
            chat(connection)
        capture = connection._capture_path("request-1")
        value = json.loads(capture.read_text())
        value["request_sha256"] = "0" * 64
        capture.write_text(json.dumps(value))
        with pytest.raises(ClientBlocked, match="identity"):
            client(url, tmp_path).recover_receipt("request-1")
        assert len(received) == 1
        with connection.path.open("ab") as handle:
            handle.write(b'{"event":')
        with pytest.raises(ClientBlocked):
            client(url, tmp_path)


def test_stage_cap_is_reserved_and_enforced_as_actual_request_envelope(tmp_path):
    with fake_http(successful()) as (url, received):
        connection = client(url, tmp_path)
        record = chat(connection, num_predict=3)
        reserve = connection._rows()[1]
        assert reserve["reserved_generated_tokens"] == 3
        assert reserve["reserved_total_tokens"] == 19
        assert received[0]["request"]["options"]["num_predict"] == 3
        assert record["status"] == "ok"
        with pytest.raises(ValueError):
            chat(connection, "other", num_predict=9)


def test_only_formal_empty_load_receipt_proves_zero_generation(tmp_path):
    payload = {
        "model": TAG,
        "done": True,
        "done_reason": "load",
        "message": {"role": "assistant", "content": ""},
    }
    with fake_http(payload) as (url, received):
        connection = client(url, tmp_path)
        result = connection.chat(
            model=TAG,
            trial_id="preload",
            request_id="load",
            messages=[],
            schema=SCHEMA,
            seed=17,
            preload=True,
            num_predict=1,
        )
        assert result["status"] == "loaded" and result["usage"]["total_tokens"] == 0
        assert received[0]["request"]["messages"] == []
        ordinary = chat(connection, "ordinary", "ordinary")
        assert ordinary["unknown_consumption"] is True


def test_termination_keeps_unknown_and_full_reservation_and_requires_new_epoch(tmp_path):
    with fake_http(successful(), delay=0.15) as (url, received):
        connection = modern(url, tmp_path, request_wall_seconds=0.02)
        stale = modern(url, tmp_path, request_wall_seconds=0.02)
        chat(connection)
        with pytest.raises(ClientBlocked):
            chat(connection, "new", "unstarted")
        connection.terminate_unmetered("request-1", proof())
        summary = connection.summary()
        assert summary["generated_tokens"] is None and summary["total_tokens"] is None
        assert summary["charged_generated_tokens"] == 8 and summary["charged_total_tokens"] == 24
        assert summary["reserved_total_tokens"] == 24 and summary["needs_server_epoch"]
        with pytest.raises(ClientBlocked):
            chat(connection, "new", "unstarted")
        connection.advance_server_epoch("epoch-2")
        assert not connection.summary()["blocked"]
        with pytest.raises(ClientBlocked, match="identity"):
            chat(stale, "new", "unstarted")
        with pytest.raises(ClientBlocked, match="primary"):
            chat(connection, "new", "trial-1")
        assert (
            len(received) <= 1
        )  # No new dispatch after uncertainty; reserve fsync may use the deadline.


@pytest.mark.parametrize("change", ["no_exit", "wrong_epoch", "pid_reused", "no_bound_identity"])
def test_incomplete_termination_proof_keeps_global_blocking(tmp_path, change):
    with fake_http(successful(), delay=0.15) as (url, _):
        connection = modern(url, tmp_path, request_wall_seconds=0.02)
        chat(connection)
        value = proof()
        if change == "no_exit":
            value["tree_stopped"] = False
        elif change == "wrong_epoch":
            value["server_epoch"] = "foreign"
        elif change == "pid_reused":
            value["identities"][0]["creation_filetime"] = 0
        else:
            value["identities"] = []
        before = connection.path.read_bytes()
        with pytest.raises(ClientBlocked):
            connection.terminate_unmetered("request-1", value)
        assert connection.path.read_bytes() == before and connection.summary()["blocked"]


def test_old_campaign_cannot_adopt_termination_policy(tmp_path):
    with fake_http(successful()) as (url, _):
        with pytest.raises(ValueError):
            OllamaClient(
                url,
                tmp_path / "ledger",
                run_id="egr-023-test",
                freeze_id="a",
                profiles={TAG: PROFILE},
                server_epoch="epoch",
                termination_policy=True,
            )


def test_campaign_allows_only_two_uncertain_server_recoveries(tmp_path):
    with fake_http(successful(), delay=0.15) as (url, _):
        connection = modern(url, tmp_path, request_wall_seconds=0.02)
        for number in range(3):
            request = f"uncertain-{number}"
            chat(connection, request, f"primary-{number}")
            if number == 2:
                with pytest.raises(ClientBlocked, match="termination"):
                    connection.terminate_unmetered(request, proof(f"epoch-{number + 1}"))
                break
            connection.terminate_unmetered(request, proof(f"epoch-{number + 1}"))
            connection.advance_server_epoch(f"epoch-{number + 2}")
        summary = connection.summary()
        assert summary["blocked"] and len(summary["terminated_unmetered"]) == 2
        assert summary["charged_total_tokens"] == 72 and summary["total_tokens"] is None


def test_native_ownership_rejects_pid_reuse_and_checks_late_descendants(monkeypatch):
    identities = {
        p: {
            "pid": p,
            "creation_filetime": 100 + p,
            "executable": "C:/Ollama/ollama.exe",
            "executable_sha256": "a" * 64,
        }
        for p in (11, 12, 13)
    }
    stopped = set()

    class Handle:
        def __init__(self, pid):
            self.pid = pid

        def identity(self):
            return identities[self.pid]

        def stopped(self, *args):
            return self.pid in stopped

        def terminate(self):
            stopped.add(self.pid)

        def close(self):
            pass

    monkeypatch.setattr(ownership, "_Handle", Handle)
    sequence = iter([[11, 12], [11, 12, 13], [11, 12, 13]])
    monkeypatch.setattr(ownership, "_process_tree", lambda root: next(sequence))
    owner = {"root": copy.deepcopy(identities[11]), "server_epoch": "epoch"}
    identities[11]["creation_filetime"] += 1
    with pytest.raises(ClientBlocked):
        ownership.verify_and_stop_owned(owner)
    assert not stopped
    identities[11]["creation_filetime"] -= 1
    result = ownership.verify_and_stop_owned(owner)
    assert result["tree_stopped"] and stopped == {11, 12, 13}
    assert all("executable" not in i for i in result["identities"])


def test_new_task_rules_and_minimal_witnesses_are_disjoint_from_old_inputs():
    datasets = (
        confirmation_tasks(),
        confirmation_tasks("024"),
        development_tasks("024"),
        calibration_tasks(),
    )
    ids = [{t.task_id for t, g in pairs} for pairs in datasets]
    assert all(not left & right for i, left in enumerate(ids) for right in ids[i + 1 :])
    current = datasets[1]
    assert len(current) == 24 and sum(g.decision == "unknown" for t, g in current) == 6
    for task, gold in current:
        assert "必要十分条件" in task.documents[0].text
        assert all(w.quote in task.document(w.source_id).text for w in gold.witnesses)
        messages = integration_messages(task, task.documents)
        assert "原文全体" not in messages[1]["content"]
        assert "decision" not in json.loads(messages[1]["content"])["catalogue"][0]


def test_compact_review_closed_fields_and_feedback_limit():
    value = {"status": "PASS", "reason_code": "supported", "requested_sources": [], "feedback": ""}
    assert validate_output(value, CompactReview).status == "PASS"
    for bad in (
        {**value, "feedback": "x" * 161},
        {**value, "reason_code": "maybe"},
        {**value, "gold": "yes"},
    ):
        with pytest.raises(ValueError):
            validate_output(bad, CompactReview)
    settings = TrialSettings()
    assert settings.budget.limits.tokens == 10 * (8192 + 1536)
    with pytest.raises(ValueError):
        replace(settings, calls=13)


def test_new_confirmation_profiles_never_shrink_to_eight(monkeypatch):
    protocol = json.loads((cli.ROOT / "protocol-v0.2.4.json").read_text())
    monkeypatch.setattr(cli, "PROTOCOL", protocol)
    for n in (16, 24):
        ids = set(cli.selected_parent_ids(n))
        selected = [(t, g) for t, g in confirmation_tasks("024") if t.task_id in ids]
        assert len(selected) == n and sum(g.decision == "unknown" for t, g in selected) == n // 4
    with pytest.raises(KeyError):
        cli.selected_parent_ids(8)


class _CompactFake:
    def __init__(self, *, review="PASS", first_format_fault=False, omit_optional=False):
        from test_ollama_experiment import FakeClient

        self.fake = FakeClient(review=review, fault="length" if first_format_fault else None)
        self.omit_optional = omit_optional

    def summary(self):
        return self.fake.summary()

    def lookup(self, identity):
        return self.fake.lookup(identity)

    def chat(self, **kwargs):
        original = kwargs["validator"]

        def validate(output):
            if kwargs["schema"]["title"] == "CompactReview":
                output["reason_code"] = (
                    "supported" if output["status"] == "PASS" else "wrong_decision"
                )
                if self.omit_optional:
                    output.pop("feedback", None)
            if self.omit_optional and kwargs["schema"]["title"] == "Extraction":
                for claim in output["claims"]:
                    claim.pop("unit", None)
            return original(output)

        kwargs["validator"] = validate
        if kwargs["metadata"]["stage"] == "repair":
            kwargs["metadata"] = {
                **kwargs["metadata"],
                "stage": {"Extraction": "read", "Answer": "integrate", "CompactReview": "review"}[
                    kwargs["schema"]["title"]
                ],
            }
        record = self.fake.chat(**kwargs)
        self.fake.fault = None
        return record


@pytest.mark.parametrize("arm", ["B", "C"])
def test_omitted_optional_model_fields_preserve_exact_receipt_identity(arm):
    from experiments.ollama.harness import run_trial
    from experiments.ollama.oracle import evaluate

    task, gold = development_tasks("024")[0]
    result = run_trial(
        task,
        arm=arm,
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=_CompactFake(omit_optional=True),
        settings=TrialSettings(),
    )
    review = result["reviews"][-1]
    original = result["calls"][-1]["parsed"]
    assert "feedback" not in original
    assert review == original
    scored = evaluate(task, gold, result)
    assert scored["answer_grounded_correct"] and scored["verified_supported_completion"]


def _revise_known(connection):
    stopped = {**proof(), "verified_exit_epoch": datetime.now(UTC).timestamp()}
    return connection.revise_protocol(
        run_id="egr-024-contract-revision",
        freeze_id="d" * 64,
        server_epoch="c" * 64,
        previous_owned_exit_proof=stopped,
        authorization="The user requires a new protocol after a mechanical post-freeze defect",
    )


def test_protocol_revision_preserves_exact_prefix_expenses_and_durable_clock(tmp_path):
    with fake_http(successful()) as (url, received):
        connection = modern(url, tmp_path, global_wall_seconds=172800)
        chat(connection)
        before = connection.summary()
        prefix = connection.path.read_bytes()
        anchor = connection.path.with_suffix(".clock.json").read_bytes()
        event = _revise_known(connection)
        after = connection.summary()
        assert connection.path.read_bytes().startswith(prefix)
        assert connection.path.with_suffix(".clock.json").read_bytes() == anchor
        assert event["retained_budget_state"]["started_epoch"] == before["started_epoch"]
        for field in ("calls", "started_epoch", "generated_tokens", "total_tokens"):
            assert before[field] == after[field]
        reopened = OllamaClient(
            url,
            connection.path,
            run_id="egr-024-contract-revision",
            freeze_id="d" * 64,
            profiles={TAG: PROFILE},
            limits=Limits(global_wall_seconds=172800),
            server_epoch="c" * 64,
            termination_policy=True,
        )
        assert reopened.summary()["calls"] == 1
        chat(reopened, request_id="fresh-request", trial_id="fresh-task")
        assert reopened.summary()["calls"] == 2 and len(received) == 2
        with pytest.raises(ClientBlocked):
            reopened.revise_protocol(
                run_id="third",
                freeze_id="e" * 64,
                server_epoch="f" * 64,
                previous_owned_exit_proof={**proof("c" * 64), "verified_exit_epoch": time.time()},
                authorization="Do not reset a second time",
            )


@pytest.mark.parametrize(
    "field", ["limits", "profiles", "prefix", "budget", "exit", "proof", "authorization"]
)
def test_protocol_revision_rejects_budget_identity_and_exit_tampering(tmp_path, field):
    with fake_http(successful()) as (url, _):
        connection = modern(url, tmp_path, global_wall_seconds=172800)
        chat(connection)
        event = _revise_known(connection)
        broken = copy.deepcopy(event)
        if field == "limits":
            broken["config"]["limits"]["global_calls"] += 1
        elif field == "profiles":
            broken["config"]["profiles"][TAG]["num_predict"] += 1
        elif field == "prefix":
            broken["prior_events_canonical_sha256"] = "0" * 64
        elif field == "budget":
            broken["retained_budget_state"]["calls"] = 0
        elif field == "exit":
            broken["previous_owned_exit_proof"]["verified_exit_epoch"] = 0
        elif field == "proof":
            broken["previous_owned_exit_proof"]["tree_stopped"] = False
        else:
            broken["authorization"] = ""
        rows = connection._rows()
        with pytest.raises(ClientBlocked):
            connection._effective_config([*rows[:-1], broken])


def test_protocol_revision_cannot_clear_unknown_consumption(tmp_path):
    with fake_http(successful(), delay=0.1) as (url, _):
        connection = modern(url, tmp_path, global_wall_seconds=172800, request_wall_seconds=0.02)
        assert chat(connection)["unknown_consumption"]
        before = connection.path.read_bytes()
        with pytest.raises(ClientBlocked):
            _revise_known(connection)
        assert connection.path.read_bytes() == before


def test_corrective_tasks_have_unused_material_and_exact_public_witnesses():
    old = {task.task_id for task, _ in confirmation_tasks("024")}
    new = confirmation_tasks("024r2")
    assert len(new) == 24 and not old.intersection(task.task_id for task, _ in new)
    assert sum(gold.decision == "unknown" for _, gold in new) == 6
    old_documents = {
        document.text for task, _ in confirmation_tasks("024") for document in task.documents
    }
    for task, gold in new:
        assert all(document.text not in old_documents for document in task.documents)
        assert all(int(document.version) >= 7 for document in task.documents)
        for witness in gold.witnesses:
            assert witness.quote in task.document(witness.source_id).text
            assert all(
                quote in task.document(witness.source_id).text
                for quote in witness.alternative_quotes
            )
    assert any("14時30分" in d.text for task, _ in new for d in task.documents)
    assert any("12℃" in d.text for task, _ in new for d in task.documents)


def test_corrective_rules_do_not_override_question_scope_with_internal_ids():
    for task, gold in (*development_tasks("024r2"), *confirmation_tasks("024r2")):
        rule = task.document("document-1").text
        assert rule.startswith("規則委員会の公開条項である。")
        assert task.task_id not in rule
        assert "に適用する規則。" not in rule
        target = task.question.split("対象", 1)[1].split("を", 1)[0]
        facts = "".join(document.text for document in task.documents)
        assert target in facts
        assert task.task_id == gold.task_id
        for witness in gold.witnesses:
            assert witness.quote in task.document(witness.source_id).text
    assert all(
        task.task_id.startswith("development024r2b-") for task, _ in development_tasks("024r2")
    )


def test_grounded_correct_answer_survives_reviewer_failure_and_is_not_verified_complete():
    from experiments.ollama.harness import run_trial
    from experiments.ollama.oracle import evaluate

    task, gold = development_tasks("024")[0]
    result = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=_CompactFake(review="FAIL"),
        settings=TrialSettings(),
    )
    scored = evaluate(task, gold, result)
    assert scored["answer_correct"] and scored["answer_grounded_correct"]
    assert not scored["verified_supported_completion"]


def test_one_format_repair_preserves_failed_output_and_charges_both_calls(tmp_path):
    from experiments.ollama.harness import run_trial

    task, _ = development_tasks("024")[0]
    fake = _CompactFake(first_format_fault=True)
    result = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=fake,
        checkpoint=tmp_path / "checkpoint.json",
        settings=TrialSettings(),
    )
    assert result["calls"][0]["status"] == "length"
    assert result["calls"][1]["stage"] == "repair"
    assert result["state"]["results"][0]["actual_resources"]["tokens"] == 274
    assert result["cost"]["tokens"] == sum(c["usage"]["total_tokens"] for c in result["calls"])
    count = len(fake.fake.records)
    resumed = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=fake,
        checkpoint=tmp_path / "checkpoint.json",
        settings=TrialSettings(),
        resume=True,
    )
    assert resumed == result and len(fake.fake.records) == count


def test_crash_after_paid_repair_receipt_keeps_both_calls_on_resume(tmp_path, monkeypatch):
    from experiments.ollama.harness import run_trial

    task, _ = development_tasks("024")[0]
    fake = _CompactFake(first_format_fault=True)
    original = fake.chat

    def interrupted(**kwargs):
        result = original(**kwargs)
        if kwargs["request_id"].endswith(":format-repair-1"):
            raise SystemExit("crash after durable repair response before SDK record")
        return result

    monkeypatch.setattr(fake, "chat", interrupted)
    arguments = dict(
        arm="C",
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=fake,
        checkpoint=tmp_path / "checkpoint.json",
        settings=TrialSettings(),
    )
    with pytest.raises(SystemExit):
        run_trial(task, **arguments)
    assert len(fake.fake.records) == 2
    monkeypatch.setattr(fake, "chat", original)
    resumed = run_trial(task, resume=True, **arguments)
    assert len(resumed["calls"]) == len(fake.fake.records)
    assert len({call["request_id"] for call in resumed["calls"]}) == len(resumed["calls"])
    assert resumed["calls"][1]["stage"] == "repair"
    assert resumed["cost"]["tokens"] == sum(
        call["usage"]["total_tokens"] for call in resumed["calls"]
    )


def test_monotonic_campaign_anchor_survives_wall_clock_rollback(tmp_path, monkeypatch):
    from experiments.ollama import client as transport

    with fake_http(successful()) as (url, received):
        connection = modern(url, tmp_path, global_wall_seconds=100)
        chat(connection)
        path = connection.path.with_suffix(".clock.json")
        anchor = json.loads(path.read_text())
        first = connection.summary()["started_epoch"]
        monkeypatch.setattr(transport.time, "time", lambda: first - 500)
        monkeypatch.setattr(transport.time, "monotonic", lambda: anchor["anchor_monotonic"] + 101)
        with pytest.raises(ClientBlocked, match="envelope"):
            chat(connection, "new", "new-trial")
        assert len(received) == 1
        assert connection.summary()["campaign_elapsed_seconds"] >= 101


def test_campaign_does_not_silently_reset_across_system_boots(tmp_path, monkeypatch):
    from experiments.ollama import client as transport

    with fake_http(successful()) as (url, received):
        connection = modern(url, tmp_path)
        chat(connection)
        monkeypatch.setattr(transport, "_boot_identity", lambda: "changed-boot")
        with pytest.raises(ClientBlocked, match="boot"):
            chat(connection, "new", "unstarted")
        assert len(received) == 1


def test_worker_heartbeat_records_audited_receipt_without_another_dispatch(tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        cli, "PROTOCOL", json.loads((cli.ROOT / "protocol-v0.2.4.json").read_text())
    )
    monkeypatch.setattr(cli, "guard", lambda _args: {})
    monkeypatch.setattr(cli, "verify_inventory", lambda *_args: {})
    monkeypatch.setattr(cli, "observe_backend", lambda *_args: {})
    monkeypatch.setattr(cli, "collect_resources", lambda **_kwargs: {})
    with fake_http(successful()) as (url, received):
        connection = modern(url, tmp_path)
        bound = cli.BoundClient(
            connection,
            SimpleNamespace(directory=tmp_path, url=url, server_log=None, server_pid=12),
            "development",
            "trial",
        )
        bound.chat(
            model=TAG,
            trial_id="ignored",
            request_id="call",
            messages=[{"role": "user", "content": "test"}],
            schema=SCHEMA,
            seed=17,
        )
        heartbeat = json.loads((tmp_path / "worker-heartbeat.json").read_text())
        assert heartbeat["last_completed_request_id"] == "trial/call"
        assert heartbeat["before_request_remaining"]["calls"] == connection.limits.global_calls - 1
        assert len(received) == 1


def test_only_native_console_host_descendant_is_owned(monkeypatch):
    monkeypatch.setenv("SystemRoot", "C:/Windows")
    assert ownership._owned_executable({"executable": "C:/Windows/System32/conhost.exe"})
    assert not ownership._owned_executable({"executable": "C:/unrelated/conhost.exe"})


@pytest.mark.parametrize("last_mib,blocked", [(255, False), (256, True)])
def test_sustained_swap_growth_blocks_new_dispatch_without_lowering_ram_floor(
    tmp_path, monkeypatch, last_mib, blocked
):
    from experiments.ollama import environment

    values = iter([0, 64, 128, last_mib])
    monkeypatch.setattr(
        environment,
        "collect_resources",
        lambda _pid: {
            "memory_status": "okay",
            "server_alive": True,
            "swap_used_bytes": next(values) * 1024**2,
        },
    )
    results = [
        environment.resource_gate(tmp_path, 12, require_swap_observation=True) for _ in range(4)
    ]
    assert all(r["safe_for_new_request"] for r in results[:3])
    assert results[-1]["swap_growth_observed"] is blocked
    assert ("sustained_swap_growth" in results[-1]["blocking_reasons"]) is blocked


def test_unknown_swap_is_not_reported_as_zero(tmp_path, monkeypatch):
    from experiments.ollama import environment

    monkeypatch.setattr(
        environment,
        "collect_resources",
        lambda _pid: {"memory_status": "okay", "server_alive": True, "swap_used_bytes": None},
    )
    result = environment.resource_gate(tmp_path, 12, require_swap_observation=True)
    assert not result["safe_for_new_request"]
    assert "swap_observation_unknown" in result["blocking_reasons"]


def test_corrective_development_timings_enter_forecast_without_primary_outcomes(monkeypatch):
    from experiments.ollama import cli

    monkeypatch.setattr(cli, "PROTOCOL", {"request_key_prefix": "r2-"})
    ids = (
        "warmup-cycle-3/model/read",
        "pilot-model-parent-A-seed/read",
        "r2-warmup-cycle-3/model/read",
        "r2-scope-v1-warmup-cycle-3/model/read",
        "r2-pilot-model-parent-A-seed/read",
        "confirmation-model-parent-A-seed/read",
        "r2-confirmation-model-parent-A-seed/read",
        "r2-sensitivity-strict-model-parent-A-seed/read",
        "calibration-cycle-3/model/review",
    )
    ledger = [{"event": "response", "record": {"request_id": key}} for key in ids]
    retained = cli.development_forecast_ledger(ledger)
    assert [row["record"]["request_id"] for row in retained] == list(ids[:5])


def test_formal_cold_preload_is_reserved_once_in_speed_forecast():
    model = TAG
    ledger = [
        {
            "event": "response",
            "request_id": "load",
            "record": {
                "model": model,
                "status": "loaded",
                "request_id": "load",
                "client_wall_seconds": 112,
                "durations_seconds": {},
            },
        },
        {
            "event": "response",
            "request_id": "warm",
            "record": {
                "model": model,
                "status": "ok",
                "request_id": "warm",
                "client_wall_seconds": 24,
                "durations_seconds": {"load_duration": 1},
            },
        },
    ]
    resources = [
        {
            "request_id": "warm",
            "model": model,
            "before_sampling_wall_seconds": 1,
            "sampling_wall_seconds": 2,
        }
    ]
    forecast = cli.speed_forecast(ledger, resources, [model])[model]
    assert forecast["per_request_seconds"] == 26 and forecast["once_per_model_load_seconds"] == 112


def test_new_analysis_preserves_missing_denominators_and_fresh_stop_pairs(tmp_path, monkeypatch):
    from experiments.ollama import analysis

    protocol = json.loads((cli.ROOT / "protocol-v0.2.4.json").read_text())
    task, _ = confirmation_tasks("024")[0]
    monkeypatch.setattr(
        analysis,
        "evaluate",
        lambda _t, _g, trial: {
            "oracle_assessed": True,
            "answer_correct": trial["success"],
            "answer_grounded_correct": trial["success"],
            "verified_supported_completion": trial["success"],
            "evidence_supported_completion": trial["success"],
            "grounded_abstention": False,
            "errors": [],
        },
    )
    ledger = []
    planned = []
    sensitivity = []
    for phase in ("confirmation", "sensitivity-strict", "sensitivity-bounded"):
        for arm in ("A", "B", "C") if phase == "confirmation" else ("A", "B"):
            key = phase + "-" + arm
            entry = {
                "key": key,
                "task_id": task.task_id,
                "model": TAG,
                "arm": arm,
                "seed": protocol["seed"],
            }
            (planned if phase == "confirmation" else sensitivity).append(
                entry if phase == "confirmation" else {**entry, "phase": phase}
            )
            if arm == "C":
                continue
            call = {
                "request_id": key + "/call",
                "done": True,
                "unknown_consumption": False,
                "pending": False,
                "parsed": {},
                "status": "ok",
            }
            trial = {
                "calls": [call],
                "success": arm == "A" and phase != "sensitivity-strict",
                "pending": False,
                "fault": None,
                "system_claimed_complete": False,
            }
            if phase == "sensitivity-bounded" and arm == "A":
                trial.update(
                    secondary_trigger="no_progress",
                    secondary_trigger_fault="length",
                    secondary_callbacks=2,
                )
            cli.write_json(
                tmp_path / "trials" / phase / (key + ".json"),
                {**entry, "phase": phase, "execution": "completed", "trial": trial},
            )
            ledger.extend(
                [
                    {
                        "event": "reserve",
                        "request_id": key + "/call",
                        "trial_id": key,
                        "request": {"model": TAG},
                        "reserved_total_tokens": 100,
                        "metadata": {"phase": phase},
                    },
                    {
                        "event": "response",
                        "request_id": key + "/call",
                        "record": {**call, "usage": {"generated_tokens": 10, "total_tokens": 30}},
                    },
                ]
            )
    (tmp_path / "calls.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger), encoding="utf-8"
    )
    summary = analysis.analyze(
        tmp_path,
        tmp_path / "output",
        protocol,
        frozen={"planned_trial_keys": planned, "planned_sensitivity_keys": sensitivity},
    )
    assert summary["comparisons"][TAG]["paired_assessed_parents"] == 1
    assert summary["outcomes"][TAG]["C"]["unexecuted"] == 1
    assert summary["confirmation_outcome_costs"][TAG + "/C"]["successful"]["total_tokens"] is None
    assert summary["confirmation_outcome_costs"][TAG + "/A"]["successful"]["total_tokens"] == 30
    stopped = summary["stop_sensitivity"][TAG]
    assert stopped["selectors"]["sensitivity-bounded"]["additional_callbacks"] == 2
    assert (
        stopped["recovery_minus_strict"]["A"]["metrics"]["verified_supported_completion"][
            "mean_difference"
        ]
        == 1
    )
    rows = json.loads((tmp_path / "output/scored-trials.json").read_text())
    assert next(r for r in rows if r["key"] == "confirmation-C")["answer_correct"] is None


def test_confirmation_parents_are_not_renamed_identical_inputs():
    import re

    pairs = confirmation_tasks("024")
    assert sum(g.decision != "unknown" for _, g in pairs) == 18
    for family in ("L1", "L2", "L3", "L4"):
        signatures = [
            tuple(re.sub(r"新規-L[1-4]-[1-6]", "TARGET", d.text) for d in task.documents)
            for task, _ in pairs
            if task.family == family
        ]
        assert len(set(signatures)) == 6
    selected = {
        "confirmation024-" + family + "-" + str(n)
        for family in ("L1", "L2", "L3", "L4")
        for n in (1, 2, 3, 6)
    }
    assert sum(g.decision == "unknown" for t, g in pairs if t.task_id in selected) == 4
    for task, gold in pairs:
        assert all(w.quote in task.document(w.source_id).text for w in gold.witnesses)
        assert (
            len({task.document(w.source_id).origin for w in gold.witnesses}) >= gold.minimum_origins
        )


def test_unknown_arrival_contract_depends_on_world_time_not_presence_of_a_check():
    task, gold = next(
        (t, g) for t, g in confirmation_tasks("024") if t.task_id == "confirmation024-L4-6"
    )
    assert gold.decision == "unknown"
    assert "17時00分までに到着" in task.documents[0].text
    assert "到着時刻は未記録" in task.documents[1].text
    assert "確認したこと" not in task.documents[0].text


def test_common_candidate_catalogue_does_not_force_identical_reprint_retrieval():
    from experiments.ollama.harness import _Trial

    task, _ = next((t, g) for t, g in confirmation_tasks("024") if t.task_id.endswith("L2-1"))
    for arm in ("A", "B"):
        trial = _Trial(task, arm, "fake", "a" * 64, 17, _CompactFake(), None, TrialSettings())
        pool = trial.candidates(trial.state)
        assert "read:document-3" not in {a.id for a in pool}
        assert all("raw:document-3" not in {d.evidence_id for d in a.dependencies} for a in pool)
        for changed in (
            replace(task.documents[2], text=task.documents[2].text + "追加条件も記録した。"),
            replace(task.documents[2], version="2"),
            replace(task.documents[2], origin="different-origin"),
        ):
            distinct = replace(task, documents=(*task.documents[:2], changed, *task.documents[3:]))
            other = _Trial(
                distinct, arm, "fake", "a" * 64, 17, _CompactFake(), None, TrialSettings()
            )
            assert "read:document-3" in {a.id for a in other.candidates(other.state)}


def test_explicit_request_for_known_copy_is_retained_in_common_catalogue():
    from experiments.ollama.harness import _retrieval_documents

    task, _ = next((t, g) for t, g in confirmation_tasks("024") if t.task_id.endswith("L2-1"))
    assert "document-3" in {d.source_id for d in _retrieval_documents(task, {"document-3"})}


@pytest.mark.parametrize(
    "form,changed_copy",
    [
        ("scoped_short_fact", None),
        ("equivalent_reprint", None),
        ("equivalent_reprint", "origin"),
        ("equivalent_reprint", "version"),
        ("equivalent_reprint", "content"),
    ],
)
def test_oracle_accepts_equivalent_minimal_witnesses_with_actual_bound_receipts(form, changed_copy):
    from experiments.ollama.harness import run_trial
    from experiments.ollama.oracle import evaluate

    family = "L1" if form == "scoped_short_fact" else "L2"
    task, gold = next(
        (t, g) for t, g in confirmation_tasks("024") if t.task_id.endswith(family + "-1")
    )
    if changed_copy:
        changes = {
            "origin": {"origin": "unrelated-origin"},
            "version": {"version": "2"},
            "content": {"text": task.documents[2].text.replace("は適合", "は不適合")},
        }
        other = replace(task.documents[2], **changes[changed_copy])
        task = replace(task, documents=(*task.documents[:2], other, *task.documents[3:]))
    fake = _CompactFake()
    original = fake.chat

    def changed(**kwargs):
        record = original(**kwargs)
        if kwargs["schema"]["title"] == "Answer":
            if form == "scoped_short_fact":
                record["parsed"]["citations"] = [
                    {
                        "source_id": "document-1",
                        "version": "1",
                        "quote": task.documents[0].text.split("。", 1)[0] + "。",
                    },
                    {"source_id": "document-1", "version": "1", "quote": "条件Pは真と確認した。"},
                    {"source_id": "document-2", "version": "1", "quote": "条件Qは真と確認した。"},
                ]
            else:
                record["parsed"]["citations"] = [
                    c for c in record["parsed"]["citations"] if c["source_id"] != "document-2"
                ]
            kwargs["validator"](record["parsed"])
            record["content"] = json.dumps(record["parsed"], ensure_ascii=False)
        return record

    fake.chat = changed
    result = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest="a" * 64,
        seed=17,
        client=fake,
        settings=TrialSettings(),
    )
    scored = evaluate(task, gold, result)
    assert scored["verified_supported_completion"] == (changed_copy is None), scored["errors"]
    if changed_copy:
        assert "missing_witness:document-2" in scored["errors"]
