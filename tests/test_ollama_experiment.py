"""Offline model-output tests; these are not live Ollama measurements."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.ollama.harness import (
    TRIAL_BUDGET,
    _Trial,
    initial_state,
    run_trial,
    verify_first,
)
from experiments.ollama.oracle import evaluate
from experiments.ollama.prompts import Answer, integration_messages
from experiments.ollama.tasks import confirmation_tasks, development_tasks

DIGEST = "a" * 64


class FakeClient:
    def __init__(
        self,
        *,
        decision: str = "yes",
        review: str = "PASS",
        request_all: bool = False,
        fault: str | None = None,
    ) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.messages: list[list[dict[str, str]]] = []
        self.decision, self.review, self.request_all, self.fault = (
            decision,
            review,
            request_all,
            fault,
        )
        self.blocked = False

    def summary(self) -> dict[str, Any]:
        return {"blocked": self.blocked}

    def lookup(self, request_id: str) -> dict[str, Any] | None:
        return self.records.get(request_id)

    def chat(self, **kwargs: Any) -> dict[str, Any]:
        request_id = kwargs["request_id"]
        assert request_id not in self.records, "a request was redispatched"
        self.messages.append(kwargs["messages"])
        body = json.loads(kwargs["messages"][1]["content"])
        documents = body["documents"]
        stage = kwargs["metadata"]["stage"]
        if stage == "read":
            doc = documents[0]
            output: dict[str, Any] = {
                "claims": [
                    {
                        "subject": "資料",
                        "value": "記載",
                        "unit": "",
                        "source_id": doc["source_id"],
                        "quote": doc["text"],
                        "status": "observed",
                    }
                ]
            }
        elif stage == "integrate":
            output = {
                "decision": self.decision,
                "answer": self.decision,
                "reasoning": "資料を照合",
                "citations": [
                    {"source_id": d["source_id"], "version": d["version"], "quote": d["text"]}
                    for d in documents
                ],
            }
        else:
            missing = [
                d["source_id"]
                for d in body["catalogue"]
                if d["source_id"] not in {doc["source_id"] for doc in documents}
            ]
            output = {
                "status": "FAIL" if self.request_all and missing else self.review,
                "feedback": "追加資料を確認" if missing else "全て照合",
                "requested_sources": missing if self.request_all else [],
            }
        kwargs["validator"](output)
        status = self.fault or "ok"
        unknown = status == "timeout"
        self.blocked = unknown
        result = {
            "request_id": request_id,
            "trial_id": kwargs["trial_id"],
            "model": kwargs["model"],
            "model_digest": DIGEST,
            "status": status,
            "parsed": output,
            "content": json.dumps(output, ensure_ascii=False),
            "thinking": "",
            "usage": {
                "prompt_tokens": None if unknown else 100,
                "generated_tokens": None if unknown else 37,
                "total_tokens": None if unknown else 137,
            },
            "unknown_consumption": unknown,
            "pending": unknown,
            "metadata": kwargs["metadata"],
        }
        self.records[request_id] = result
        return result


def trial_for(arm: str = "A", **kwargs: Any) -> tuple[dict[str, Any], FakeClient]:
    client = FakeClient(**kwargs)
    task, _ = development_tasks()[0]
    trial = run_trial(task, arm=arm, model="fake", model_digest=DIGEST, seed=17, client=client)
    return trial, client


def test_task_sets_are_distinct_balanced_and_public_gold_separate() -> None:
    confirmation, development = confirmation_tasks(), development_tasks()
    assert len(confirmation) == 24 and len(development) == 4
    assert sum(g.decision == "unknown" for _, g in confirmation) == 6
    assert {f: sum(t.family == f for t, _ in confirmation) for f in ("L1", "L2", "L3", "L4")} == {
        "L1": 6,
        "L2": 6,
        "L3": 6,
        "L4": 6,
    }
    assert len({t.question for t, _ in confirmation + development}) == 28
    assert not {d.text for t, _ in confirmation for d in t.documents}.intersection(
        d.text for t, _ in development for d in t.documents
    )
    assert all(2 <= len(t.documents) <= 4 for t, _ in confirmation)
    assert all(
        len(json.dumps(integration_messages(t, t.documents), ensure_ascii=False)) < 4096
        for t, _ in confirmation
    )
    with pytest.raises(TypeError):
        integration_messages(confirmation[0][1], ())  # type: ignore[arg-type]


def test_live_stages_cause_actual_receipts_and_feedback_revision() -> None:
    trial, client = trial_for(request_all=True)
    task, gold = development_tasks()[0]
    assert [r["metadata"]["stage"] for r in client.records.values()] == [
        "read",
        "integrate",
        "review",
        "read",
        "integrate",
        "review",
    ]
    assert [r["stage"] for r in trial["calls"]] == [
        "read",
        "integrate",
        "review",
        "read",
        "integrate",
        "review",
    ]
    assert all(r["stage_provenance"] == "host_action_id" for r in trial["calls"])
    assert trial["domain_stop"] == "satisfied" and trial["cost"]["llm_calls"] == 6
    assert trial["cost"]["tokens"] == 6 * 137
    assert len(trial["state"]["supersessions"]) == 1
    assert any(c["status"] == "FAIL" for c in trial["state"]["checks"])
    assert evaluate(task, gold, trial)["evidence_supported_completion"]
    # The revised integration really receives the prior model feedback and old answer.
    integration = json.loads(client.messages[4][1]["content"])
    assert integration["feedback"]["status"] == "FAIL"
    assert integration["previous_answer"]["decision"] == "yes"


def test_ab_share_pool_only_selection_changes_and_b_checks_then_unread_catalogue() -> None:
    a, _ = trial_for()
    b, _ = trial_for("B")
    assert a["cost"]["llm_calls"] == 3 and b["cost"]["llm_calls"] == 4
    b_ids = [attempt["action"]["id"] for attempt in b["state"]["attempts"]]
    assert b_ids[:4] == [
        "read:document-1",
        "literal:document-1",
        "read:document-2",
        "literal:document-2",
    ]
    task, _ = development_tasks()[0]
    left = _Trial(task, "A", "fake", DIGEST, 17, FakeClient(), None)
    right = _Trial(task, "B", "fake", DIGEST, 17, FakeClient(), None)
    assert left.candidates(left.state) == right.candidates(right.state)
    from evidence_gap_router import feasible_actions

    pool = left.pool
    eligible = feasible_actions(left.state, pool, TRIAL_BUDGET, left.policy)
    assert verify_first(task, left.state, tuple(reversed(pool)), tuple(reversed(eligible))) == (
        verify_first(task, left.state, pool, eligible)
    )


def test_c_gets_all_docs_without_reader_calls_and_uses_same_feedback_schema() -> None:
    trial, client = trial_for("C")
    assert trial["router_satisfied"] is None and trial["system_claimed_complete"]
    assert [r["metadata"]["stage"] for r in client.records.values()] == ["integrate", "review"]
    first = json.loads(client.messages[0][1]["content"])
    assert len(first["documents"]) == 2
    task, gold = development_tasks()[0]
    assert evaluate(task, gold, trial)["evidence_supported_completion"]


@pytest.mark.parametrize("mutation", ["flip", "missing", "fakequote", "alias", "falsepass"])
def test_oracle_rejects_wrong_or_unbound_completion(mutation: str) -> None:
    original, _ = trial_for("B")
    task, gold = development_tasks()[0]
    trial = copy.deepcopy(original)
    if mutation in ("flip", "falsepass"):
        trial["answer"]["decision"] = "no"
    elif mutation == "missing":
        trial["answer"]["citations"].pop()
    elif mutation == "fakequote":
        trial["answer"]["citations"][0]["quote"] = "存在しない引用"
    else:
        trial["answer"]["citations"][1]["source_id"] = "document-alias"
    result = evaluate(task, gold, trial)
    assert not result["evidence_supported_completion"]
    if mutation in ("flip", "falsepass"):
        assert not result["answer_correct"]


def test_model_false_pass_does_not_make_wrong_answer_correct() -> None:
    trial, _ = trial_for("B", decision="no")
    task, gold = development_tasks()[0]
    assert trial["router_satisfied"] and trial["system_claimed_complete"]
    assert not evaluate(task, gold, trial)["answer_correct"]
    assert not evaluate(task, gold, trial)["evidence_supported_completion"]


def test_known_schema_failure_keeps_actual_usage_and_unknown_freezes() -> None:
    known, _ = trial_for(fault="schema_error")
    assert known["fault"] == "schema_error"
    assert known["cost"]["tokens"] == known["cost"]["llm_calls"] * 137
    assert not known["system_claimed_complete"]
    unknown, client = trial_for(fault="timeout")
    assert len(client.records) == 1 and unknown["cost"]["tokens"] is None
    assert unknown["fault"] == "unknown_consumption"
    assert unknown["state"]["results"][0]["side_effects"] == "unknown"


def test_completed_resume_never_redispatches_and_unknown_resume_stays_blocked(
    tmp_path: Path,
) -> None:
    task, _ = development_tasks()[0]
    checkpoint = tmp_path / "trial.json"
    client = FakeClient()
    first = run_trial(
        task,
        arm="B",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
    )
    resumed = run_trial(
        task,
        arm="B",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
    )
    assert resumed["state"] == first["state"] and len(client.records) == 4
    # Simulate a process interruption after dispatch persisted, before receipt.
    saved = json.loads(checkpoint.read_text("utf-8"))
    last = saved["state"]["results"].pop()
    saved["state"]["checks"] = [
        c for c in saved["state"]["checks"] if c["id"] not in {i["id"] for i in last["checks"]}
    ]
    # This last attempt was a zero-LLM host checker, so it has no completed
    # model dispatch to recover and must remain pending without reissue.
    checkpoint.write_text(json.dumps(saved), "utf-8")
    pending = run_trial(
        task,
        arm="B",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
    )
    assert pending["pending"] and pending["fault"] == "pending_or_unknown_dispatch"
    assert len(client.records) == 4


def test_pending_completed_model_call_is_settled_once_without_generation(tmp_path: Path) -> None:
    from evidence_gap_router import start

    task, _ = development_tasks()[0]
    client = FakeClient()
    checkpoint = tmp_path / "pending.json"
    trial = _Trial(task, "C", "fake", DIGEST, 17, client, checkpoint)
    pool = trial.candidates(trial.state)
    action = pool[0]
    trial.state = start(
        trial.state, action, "host-attempt-1", TRIAL_BUDGET, trial.policy, candidates=pool
    )
    request_id = f"{trial.trial_id}:host-attempt-1"
    output = {
        "decision": "yes",
        "answer": "yes",
        "reasoning": "両条件",
        "citations": [
            {"source_id": d.source_id, "version": d.version, "quote": d.text}
            for d in task.documents
        ],
    }
    client.records[request_id] = {
        "request_id": request_id,
        "status": "ok",
        "parsed": output,
        "usage": {"total_tokens": 137},
        "unknown_consumption": False,
        "pending": False,
        "model_digest": DIGEST,
    }
    trial.save()
    result = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
    )
    assert result["domain_stop"] == "satisfied" and len(client.records) == 2
    assert len(client.messages) == 1  # Only the subsequent review was generated.


def test_six_call_bound_and_auxiliary_no_rerun_of_success(tmp_path: Path) -> None:
    failed, client = trial_for("C", review="FAIL")
    assert failed["cost"]["llm_calls"] == 6 and len(client.records) == 6
    assert not failed["system_claimed_complete"]
    task, _ = development_tasks()[0]
    checkpoint = tmp_path / "success.json"
    client = FakeClient()
    first = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
    )
    auxiliary = run_trial(
        task,
        arm="C",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
        secondary_steps=2,
    )
    assert auxiliary["state"] == first["state"] and len(client.records) == 2


def test_no_seeded_pass_or_gold_answer_and_output_schema_is_bounded() -> None:
    task, _ = development_tasks()[0]
    state = initial_state(task)
    assert not state.checks and not state.results and not state.attempts
    assert all(e.obligation_id == "raw" for e in state.evidence)
    with pytest.raises(ValueError):
        Answer.model_validate_json(
            json.dumps(
                {
                    "decision": "yes",
                    "answer": "x" * 1001,
                    "reasoning": "理由",
                    "citations": [{"source_id": "document-1", "version": "1", "quote": "原文"}],
                }
            )
        )


@pytest.mark.parametrize("change", ["contract", "invalidation", "expiry", "version", "basis"])
def test_oracle_rejects_stale_or_inapplicable_positive_history(change: str) -> None:
    trial, _ = trial_for("B")
    task, gold = development_tasks()[0]
    assert evaluate(task, gold, trial)["evidence_supported_completion"]
    state = trial["state"]
    if change == "contract":
        state["obligations"][0]["contract_revision"] = "changed"
    elif change == "invalidation":
        state["invalidations"].append(
            {
                "id": "host-invalidation",
                "kind": "evidence",
                "target_id": "raw:document-2",
                "obligation_id": "raw",
                "scope": task.task_id,
                "reason": "host withdrew the input",
            }
        )
    elif change == "expiry":
        next(e for e in state["evidence"] if e["id"] == "raw:document-2")["expired"] = True
    elif change == "version":
        trial["answer"]["citations"][0]["version"] = "obsolete"
    else:
        positive = next(c for c in state["checks"] if c["verifier_id"].startswith("semantic:"))
        positive["basis"]["dependencies"] = [
            d for d in positive["basis"]["dependencies"] if d["evidence_id"] != "raw:document-2"
        ]
    assert not evaluate(task, gold, trial)["evidence_supported_completion"]


def test_origin_aliases_cannot_supply_two_independent_witnesses() -> None:
    task, gold = development_tasks()[1]
    alias = replace(task.documents[1], origin=task.documents[0].origin)
    task = replace(task, documents=(task.documents[0], alias))
    trial = run_trial(
        task, arm="B", model="fake", model_digest=DIGEST, seed=17, client=FakeClient()
    )
    result = evaluate(task, gold, trial)
    assert result["answer_correct"] and not result["evidence_supported_completion"]
    assert "insufficient_independent_origins" in result["errors"]


def test_historical_context_is_allowed_with_current_witness_but_cannot_replace_it() -> None:
    task, gold = development_tasks()[2]
    trial = run_trial(
        task, arm="C", model="fake", model_digest=DIGEST, seed=17, client=FakeClient()
    )
    assert gold.historical_sources == ("document-1",)
    assert evaluate(task, gold, trial)["evidence_supported_completion"]
    old_only = copy.deepcopy(trial)
    old_only["answer"]["citations"] = old_only["answer"]["citations"][:1]
    scored = evaluate(task, gold, old_only)
    assert not scored["evidence_supported_completion"]
    assert "missing_witness:document-2" in scored["errors"]
    wrong_version = copy.deepcopy(trial)
    wrong_version["answer"]["citations"][1]["version"] = "1"
    assert "wrong_source_version" in evaluate(task, gold, wrong_version)["errors"]


def test_auxiliary_resumes_exact_state_and_executes_at_most_two_new_callbacks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidence_gap_router import CallbackView, Resources, Result

    def noop_literal(_self: _Trial, view: CallbackView) -> Result:
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            reason="known completed check produced no new records",
        )

    monkeypatch.setattr(_Trial, "literal", noop_literal)
    task, _ = development_tasks()[0]
    client = FakeClient()
    checkpoint = tmp_path / "no-progress.json"
    first = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
    )
    assert first["runner_stop"] == "no_progress" and first["fault"] is None
    auxiliary = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
        secondary_steps=2,
    )
    assert len(auxiliary["state"]["results"]) == len(first["state"]["results"]) + 2
    assert (
        auxiliary["state"]["results"][: len(first["state"]["results"])] == first["state"]["results"]
    )
    assert auxiliary["cost"]["tokens"] == first["cost"]["tokens"] + 137
    assert auxiliary["cost"]["llm_calls"] == 2 and not auxiliary["system_claimed_complete"]


def test_terminal_no_progress_checkpoint_resume_is_not_an_implicit_continuation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidence_gap_router import CallbackView, Resources, Result

    def noop_literal(_self: _Trial, view: CallbackView) -> Result:
        return view.result(actual_resources=Resources(actions=1, verifications=1, tokens=0))

    monkeypatch.setattr(_Trial, "literal", noop_literal)
    task, _ = development_tasks()[0]
    client = FakeClient()
    checkpoint = tmp_path / "terminal-only.json"
    original = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
    )
    assert original["runner_stop"] == "no_progress" and len(client.records) == 1
    resumed = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
    )
    assert resumed == original and len(client.records) == 1


def test_auxiliary_completed_dispatch_recovery_retains_original_two_callback_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evidence_gap_router import CallbackView, Resources, Result, start
    from experiments.ollama.prompts import Extraction, extraction_messages, validate_output

    def noop_literal(_self: _Trial, view: CallbackView) -> Result:
        return view.result(actual_resources=Resources(actions=1, verifications=1, tokens=0))

    monkeypatch.setattr(_Trial, "literal", noop_literal)
    task, _ = development_tasks()[0]
    client = FakeClient()
    checkpoint = tmp_path / "auxiliary-interrupted.json"
    primary = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
    )
    interrupted = _Trial(task, "A", "fake", DIGEST, 17, client, checkpoint)
    interrupted.load()
    interrupted.secondary_origin_results = len(interrupted.state.results)
    interrupted.secondary_limit = 2
    pool = interrupted.candidates(interrupted.state)
    action = next(a for a in pool if a.id == "read:document-2")
    interrupted.state = start(
        interrupted.state,
        action,
        "host-attempt-3",
        TRIAL_BUDGET,
        interrupted.policy,
        candidates=pool,
    )
    interrupted.save()
    # Actual fake dispatch completes in the client journal; harness observation
    # has not happened when the simulated process interruption occurs.
    client.chat(
        model="fake",
        trial_id=interrupted.trial_id,
        request_id=f"{interrupted.trial_id}:host-attempt-3",
        messages=extraction_messages(task, task.documents[1]),
        schema=Extraction.model_json_schema(),
        seed=17,
        metadata={"stage": "read"},
        validator=lambda parsed: validate_output(parsed, Extraction),
    )
    resumed = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
        secondary_steps=2,
    )
    assert len(resumed["state"]["results"]) == len(primary["state"]["results"]) + 2
    assert resumed["secondary_origin_results"] == len(primary["state"]["results"])
    assert resumed["secondary_limit"] == 2 and len(client.records) == 2
    repeated = run_trial(
        task,
        arm="A",
        model="fake",
        model_digest=DIGEST,
        seed=17,
        client=client,
        checkpoint=checkpoint,
        resume=True,
        secondary_steps=2,
    )
    assert repeated == resumed and len(client.records) == 2
    with pytest.raises(ValueError, match="allowance"):
        run_trial(
            task,
            arm="A",
            model="fake",
            model_digest=DIGEST,
            seed=17,
            client=client,
            checkpoint=checkpoint,
            resume=True,
            secondary_steps=1,
        )
