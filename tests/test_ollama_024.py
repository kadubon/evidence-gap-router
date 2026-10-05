"""New long-request, durable receipt, termination and public-task contracts.

HTTP fixtures are local fakes, never evidence about the installed live models.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace

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
    def __init__(self, *, review="PASS", first_format_fault=False):
        from test_ollama_experiment import FakeClient

        self.fake = FakeClient(review=review, fault="length" if first_format_fault else None)

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


def test_only_native_console_host_descendant_is_owned(monkeypatch):
    monkeypatch.setenv("SystemRoot", "C:/Windows")
    assert ownership._owned_executable({"executable": "C:/Windows/System32/conhost.exe"})
    assert not ownership._owned_executable({"executable": "C:/unrelated/conhost.exe"})


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
