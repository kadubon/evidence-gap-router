"""Finite local-model trials. A/B share public run; C is a pooled reference."""

from __future__ import annotations

import hashlib
import itertools
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CallbackView,
    CheckerPermission,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
    Supersession,
    feasible_actions,
    load_json,
    observe,
    plan,
    run,
    start,
    step,
)

from .prompts import (
    Answer,
    Extraction,
    Output,
    Review,
    extraction_messages,
    integration_messages,
    review_messages,
    validate_output,
)
from .tasks import Document, PublicTask

Arm = Literal["A", "B", "C"]
RESERVATION = 4096 + 512
TRIAL_BUDGET = Budget(limits=Resources(actions=16, verifications=8, tokens=6 * RESERVATION))


class ChatClient(Protocol):
    def chat(self, **kwargs: Any) -> dict[str, Any]: ...
    def lookup(self, request_id: str) -> dict[str, Any] | None: ...
    def summary(self) -> dict[str, Any]: ...


def _json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _data(item: Evidence) -> dict[str, Any]:
    value = json.loads(item.content or "null")
    if not isinstance(value, dict):
        raise ValueError("expected structured callback evidence")
    return value


def _dependency(item: Evidence, *, verified: bool = False) -> DependencyRequirement:
    return DependencyRequirement(
        evidence_id=item.id,
        obligation_id=item.obligation_id,
        scope=item.scope,
        digest=item.digest,
        requirement="verified" if verified else "active",
    )


def _future(
    evidence_id: str, owner: str, scope: str, *, verified: bool = False
) -> DependencyRequirement:
    return DependencyRequirement(
        evidence_id=evidence_id,
        obligation_id=owner,
        scope=scope,
        requirement="verified" if verified else "active",
    )


def initial_state(task: PublicTask) -> State:
    """Only artificial raw public documents are seeded; no answer or PASS is seeded."""
    scope = task.task_id
    obligations = (
        Obligation(
            id="answer",
            description=task.question,
            scope=scope,
            acceptance="model semantic review plus exact public citation/basis checks",
        ),
        Obligation(
            id="review",
            description="observed model feedback",
            scope=scope,
            acceptance="structured feedback",
            required=False,
        ),
        Obligation(
            id="raw",
            description="original artificial documents",
            scope=scope,
            acceptance="host raw byte identity",
            required=False,
        ),
        *(
            Obligation(
                id=f"extract:{d.source_id}",
                description="literal extraction only",
                scope=scope,
                acceptance="finite output and exact source quote; not semantic correctness",
                required=False,
            )
            for d in task.documents
        ),
    )
    return State(
        obligations=obligations,
        evidence=tuple(
            Evidence(
                id=f"raw:{d.source_id}",
                obligation_id="raw",
                scope=scope,
                digest=d.digest,
                producer="host:artificial-fixture",
                content=d.text,
                source=d.source_id,
                provenance_group=d.origin,
            )
            for d in task.documents
        ),
    )


def policy_for(model_digest: str) -> Policy:
    return Policy(
        trusted_verifiers=("host:literal-citation", f"semantic:{model_digest}"),
        handlers=(
            HandlerRegistration(handler_id=f"reader:{model_digest}", roles=("investigate",)),
            HandlerRegistration(handler_id=f"integrator:{model_digest}", roles=("investigate",)),
            HandlerRegistration(handler_id=f"reviewer:{model_digest}", roles=("investigate",)),
            HandlerRegistration(
                handler_id="host:literal-citation",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id="host:literal-citation"),),
            ),
            HandlerRegistration(
                handler_id=f"authorize:{model_digest}",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id=f"semantic:{model_digest}"),),
            ),
        ),
    )


def verify_first(
    task: PublicTask,
    state: State,
    pool: tuple[ActionCandidate, ...],
    eligible: tuple[ActionCandidate, ...],
) -> ActionCandidate:
    """Strong baseline: exact checks, then unretrieved public catalogue order."""
    del pool
    issued = {attempt.action.id for attempt in state.attempts}
    choices = tuple(action for action in eligible if action.id not in issued)
    if not choices:
        raise ValueError("no unused eligible action")
    order = {document.source_id: index for index, document in enumerate(task.documents)}

    def rank(action: ActionCandidate) -> tuple[int, int, str]:
        if action.kind == "verify":
            return 0, 0, action.id
        if action.id.startswith("read:"):
            return 1, order[action.source or ""], action.id
        if action.id.startswith("integrate:"):
            # Once retrieval is complete, use every retrieved public record;
            # a smaller eligible integration subset is not the strong baseline.
            count = sum(d.obligation_id == "raw" for d in action.dependencies)
            return 2, -count, action.id
        return 2, 0, action.id

    return min(choices, key=rank)


class _Trial:
    def __init__(
        self,
        task: PublicTask,
        arm: Arm,
        model: str,
        digest: str,
        seed: int,
        client: ChatClient,
        checkpoint: Path | None,
    ) -> None:
        self.task, self.arm, self.model, self.digest, self.seed = task, arm, model, digest, seed
        self.client, self.checkpoint = client, checkpoint
        self.state = initial_state(task)
        self.policy = policy_for(digest)
        self.pool: tuple[ActionCandidate, ...] = ()
        self.calls: list[dict[str, Any]] = []
        self.fault: str | None = None
        self.runner_stop: str | None = None
        self.runner_error: str | None = None
        self.secondary_origin_results: int | None = None
        self.secondary_limit: int | None = None
        self.decisions: list[dict[str, Any]] = []
        self.trial_id = f"{task.task_id}:{arm}:{digest[:12]}:seed-{seed}"

    def save(self) -> None:
        if self.checkpoint is None:
            return
        value = self.result()
        encoded = _json(value).encode("utf-8")
        if len(encoded) > 32 * 1024 * 1024:
            raise ValueError("trial checkpoint exceeds 32 MiB")
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.checkpoint.with_name(self.checkpoint.name + ".tmp")
        with temporary.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(self.checkpoint)

    def load(self) -> None:
        if self.checkpoint is None or not self.checkpoint.exists():
            raise ValueError("resume needs an existing checkpoint")
        raw = self.checkpoint.read_bytes()
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("trial checkpoint exceeds 32 MiB")
        saved = json.loads(raw)
        for key, expected in (
            ("task_id", self.task.task_id),
            ("arm", self.arm),
            ("model", self.model),
            ("model_digest", self.digest),
            ("seed", self.seed),
        ):
            if saved.get(key) != expected:
                raise ValueError(f"resume identity mismatch: {key}")
        self.state = load_json(_json(saved["state"]), State)
        self.calls = saved["calls"]
        self.decisions = saved.get("decisions", [])
        self.fault = saved.get("fault")
        self.runner_stop = saved.get("runner_stop")
        self.runner_error = saved.get("runner_error")
        self.secondary_origin_results = saved.get("secondary_origin_results")
        self.secondary_limit = saved.get("secondary_limit")
        observed = {receipt.attempt_id for receipt in self.state.results}
        pending = tuple(attempt for attempt in self.state.attempts if attempt.id not in observed)
        if pending:
            attempt = pending[-1]
            request_id = f"{self.trial_id}:{attempt.id}"
            record = next((item for item in self.calls if item["request_id"] == request_id), None)
            if record is None:
                record = self.client.lookup(request_id)
            if record is None or record.get("unknown_consumption") or record.get("pending"):
                self.fault = "pending_or_unknown_dispatch"
                return
            record = {
                **record,
                "stage": attempt.action.id.split(":")[0],
                "stage_provenance": "host_action_id",
            }
            if all(item["request_id"] != request_id for item in self.calls):
                self.calls.append(record)
            view = CallbackView(
                action=attempt.action,
                attempt_id=attempt.id,
                basis=attempt.basis,
                obligation=next(
                    o for o in self.state.obligations if o.id == attempt.action.obligation_id
                ),
                inputs=tuple(
                    next(e for e in self.state.evidence if e.id == b.evidence_id)
                    for b in attempt.inputs
                ),
            )
            receipt = self.from_call(view, record)
            self.state = observe(self.state, receipt, self.policy)
            self.save()

    def candidates(self, state: State) -> tuple[ActionCandidate, ...]:
        self.state = state
        issued = {attempt.action.id for attempt in state.attempts}
        evidence = {item.id: item for item in state.evidence}
        superseded = {event.target_id for event in state.supersessions if event.kind == "evidence"}
        answers = tuple(
            e for e in state.evidence if e.obligation_id == "answer" and e.id not in superseded
        )
        scope, output = self.task.task_id, []
        blocked = bool(self.client.summary().get("blocked")) or self.fault in (
            "pending_or_unknown_dispatch",
            "unknown_consumption",
            "callback_exception",
        )
        llm_available = len(self.calls) < 6 and not blocked
        if self.arm != "C":
            for document in self.task.documents:
                source, owner = document.source_id, f"extract:{document.source_id}"
                extracted_id = f"extracted:{source}"
                if extracted_id not in evidence and llm_available:
                    output.append(
                        ActionCandidate(
                            id=f"read:{source}",
                            obligation_id=owner,
                            scope=scope,
                            kind="investigate",
                            handler_id=f"reader:{self.digest}",
                            produces_evidence_id=extracted_id,
                            dependencies=(_dependency(evidence[f"raw:{source}"]),),
                            source=source,
                            provenance_group=document.origin,
                            resources=Resources(actions=1, verifications=0, tokens=RESERVATION),
                        )
                    )
                if extracted_id in evidence:
                    item = evidence[extracted_id]
                    output.append(
                        ActionCandidate(
                            id=f"literal:{source}",
                            obligation_id=owner,
                            scope=scope,
                            kind="verify",
                            handler_id="host:literal-citation",
                            checker_id="host:literal-citation",
                            target_evidence_id=item.id,
                            target_digest=item.digest,
                            dependencies=(_dependency(evidence[f"raw:{source}"]),),
                            resources=Resources(actions=1, verifications=1, tokens=0),
                        )
                    )
        current = answers[-1] if answers else None
        round_number = int(current.id.split(":")[1]) if current else -1
        review = evidence.get(f"review:{round_number}") if current else None
        checked = (
            any(
                c.basis is not None and c.basis.target.evidence_id == current.id
                for c in state.checks
            )
            if current
            else False
        )
        if current is not None:
            data = _data(current)
            sources = tuple(data["retrieved_sources"])
            deps = self.material_dependencies(evidence, sources)
            if review is None and llm_available:
                output.append(
                    ActionCandidate(
                        id=f"review:{round_number}",
                        obligation_id="review",
                        scope=scope,
                        kind="investigate",
                        handler_id=f"reviewer:{self.digest}",
                        produces_evidence_id=f"review:{round_number}",
                        dependencies=(_dependency(current), *deps),
                        resources=Resources(actions=1, verifications=0, tokens=RESERVATION),
                    )
                )
            output.append(
                ActionCandidate(
                    id=f"semantic:{round_number}",
                    obligation_id="answer",
                    scope=scope,
                    kind="verify",
                    handler_id=f"authorize:{self.digest}",
                    checker_id=f"semantic:{self.digest}",
                    target_evidence_id=current.id,
                    target_digest=current.digest,
                    dependencies=(
                        *deps,
                        _dependency(review)
                        if review
                        else _future(f"review:{round_number}", "review", scope),
                    ),
                    resources=Resources(actions=1, verifications=1, tokens=0),
                )
            )
        can_integrate = current is None or (
            checked
            and review is not None
            and _data(review)["output"]["status"] != "PASS"
            and round_number < 2
        )
        if llm_available and can_integrate:
            new_round = round_number + 1
            requested = set(_data(review)["output"]["requested_sources"]) if review else set()
            subsets: tuple[tuple[str, ...], ...]
            if self.arm == "C":
                subsets = (tuple(d.source_id for d in self.task.documents),)
            else:
                catalogue = tuple(d.source_id for d in self.task.documents)
                subsets = tuple(
                    subset
                    for size in range(1, len(catalogue) + 1)
                    for subset in itertools.combinations(catalogue, size)
                )
            previous = set(_data(current)["retrieved_sources"]) if current else set()
            for subset in subsets:
                if not requested.union(previous).issubset(subset):
                    continue
                deps = self.material_dependencies(evidence, subset)
                if current is not None and review is not None:
                    deps = (*deps, _dependency(current), _dependency(review))
                output.append(
                    ActionCandidate(
                        id=f"integrate:{new_round}:{'+'.join(subset)}",
                        obligation_id="answer",
                        scope=scope,
                        kind="investigate",
                        handler_id=f"integrator:{self.digest}",
                        produces_evidence_id=f"answer:{new_round}",
                        dependencies=deps,
                        resources=Resources(actions=1, verifications=0, tokens=RESERVATION),
                    )
                )
        self.pool = tuple(action for action in output if action.id not in issued)
        return self.pool

    def material_dependencies(
        self,
        evidence: Mapping[str, Evidence],
        sources: tuple[str, ...],
    ) -> tuple[DependencyRequirement, ...]:
        dependencies = []
        for source in sources:
            dependencies.append(_dependency(evidence[f"raw:{source}"]))
            if self.arm != "C":
                item = evidence.get(f"extracted:{source}")
                dependencies.append(
                    _dependency(item, verified=True)
                    if item
                    else _future(
                        f"extracted:{source}", f"extract:{source}", self.task.task_id, verified=True
                    )
                )
        return tuple(dependencies)

    def documents(self, view: CallbackView) -> tuple[Document, ...]:
        raw = {item.id: item for item in view.inputs if item.obligation_id == "raw"}
        docs = tuple(d for d in self.task.documents if f"raw:{d.source_id}" in raw)
        if any(
            raw[f"raw:{d.source_id}"].digest != d.digest
            or raw[f"raw:{d.source_id}"].content != d.text
            for d in docs
        ):
            raise ValueError("pinned public document bytes differ")
        return docs

    def from_call(self, view: CallbackView, record: dict[str, Any]) -> Result:
        tokens = record.get("usage", {}).get("total_tokens")
        if record.get("unknown_consumption") or record.get("pending") or tokens is None:
            self.fault = "unknown_consumption"
            return view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=None),
                status="unknown",
                side_effects="unknown",
                reason=str(record.get("status", "uncertain dispatch")),
            )
        if record.get("status") != "ok":
            self.fault = str(record.get("status", "invalid_response"))
            return view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=tokens),
                status="failed",
                reason=self.fault,
            )
        if record.get("model_digest") != self.digest:
            self.fault = "model_identity_mismatch"
            return view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=tokens),
                status="failed",
                reason=self.fault,
            )
        action = view.action
        model_type: type[Output] = (
            Extraction
            if action.id.startswith("read:")
            else (Review if action.id.startswith("review:") else Answer)
        )
        parsed = record.get("parsed")
        if not isinstance(parsed, dict):
            self.fault = "schema_error"
            return view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=tokens),
                status="failed",
                reason=self.fault,
            )
        try:
            validated = validate_output(parsed, model_type)
            if isinstance(validated, Review) and any(
                source not in {d.source_id for d in self.task.documents}
                for source in validated.requested_sources
            ):
                raise ValueError("feedback requests a source outside the public catalogue")
        except ValueError:
            self.fault = "schema_error"
            return view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=tokens),
                status="failed",
                reason=self.fault,
            )
        payload: dict[str, Any] = {
            "output": validated.model_dump(mode="json"),
            "request_id": record["request_id"],
            "model_digest": self.digest,
            "related_inputs": [item.id for item in view.inputs],
            "retrieved_sources": [d.source_id for d in self.documents(view)],
        }
        if isinstance(validated, Review):
            payload["reviewed_answer_id"] = next(
                e.id for e in view.inputs if e.obligation_id == "answer"
            )
        content = _json(payload)
        item = Evidence(
            id=action.produces_evidence_id or "missing-target",
            obligation_id=action.obligation_id,
            scope=action.scope,
            digest=hashlib.sha256(_json(payload["output"]).encode("utf-8")).hexdigest(),
            producer=action.handler_id,
            content=content,
            source=action.source or f"model:{action.obligation_id}",
            provenance_group=action.provenance_group or f"model:{self.digest}",
        )
        previous = tuple(e for e in view.inputs if e.obligation_id == "answer")
        supersessions: tuple[Supersession, ...] = ()
        if isinstance(validated, Answer) and previous:
            supersessions = (
                Supersession(
                    id=f"{view.attempt_id}:replace",
                    kind="evidence",
                    target_id=previous[-1].id,
                    replacement_id=item.id,
                    reason="actual feedback-driven model revision",
                ),
            )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0, tokens=tokens),
            evidence=(item,),
            supersessions=supersessions,
        )

    def llm(self, view: CallbackView) -> Result:
        # The public runner has issued this same attempt. Persist its exact issued
        # snapshot before dispatch, without rerunning the factory or consuming cost.
        self.state = start(
            self.state,
            view.action,
            view.attempt_id,
            TRIAL_BUDGET,
            self.policy,
            candidates=self.pool,
        )
        self.save()
        docs = self.documents(view)
        extracted = tuple(
            _data(e)["output"] for e in view.inputs if e.obligation_id.startswith("extract:")
        )
        if view.action.id.startswith("read:"):
            model_type: type[Output] = Extraction
            messages = extraction_messages(self.task, docs[0])
        elif view.action.id.startswith("review:"):
            model_type = Review
            answer = next(e for e in view.inputs if e.obligation_id == "answer")
            messages = review_messages(self.task, docs, _data(answer)["output"], extracted)
        else:
            model_type = Answer
            previous = next((e for e in view.inputs if e.obligation_id == "answer"), None)
            feedback = next((e for e in view.inputs if e.obligation_id == "review"), None)
            messages = integration_messages(
                self.task,
                docs,
                extracted,
                _data(feedback)["output"] if feedback else None,
                _data(previous)["output"] if previous else None,
            )
        request_id = f"{self.trial_id}:{view.attempt_id}"
        try:
            record = self.client.chat(
                model=self.model,
                trial_id=self.trial_id,
                request_id=request_id,
                messages=messages,
                schema=model_type.model_json_schema(),
                seed=self.seed,
                metadata={
                    "task_id": self.task.task_id,
                    "arm": self.arm,
                    "stage": view.action.id.split(":")[0],
                    "attempt_id": view.attempt_id,
                    "input_ids": [e.id for e in view.inputs],
                },
                validator=lambda parsed: validate_output(parsed, model_type),
            )
        except Exception as error:
            self.fault = "callback_exception"
            receipt = view.result(
                actual_resources=Resources(actions=1, verifications=0, tokens=None),
                status="unknown",
                side_effects="unknown",
                reason=type(error).__name__,
            )
            self.state = observe(self.state, receipt, self.policy)
            self.save()
            return receipt
        record = {
            **record,
            "stage": view.action.id.split(":")[0],
            "stage_provenance": "host_action_id",
        }
        self.calls.append(record)
        # Save the completed record before observing it, so a crash can settle
        # this exact result without another model invocation.
        self.save()
        receipt = self.from_call(view, record)
        self.state = observe(self.state, receipt, self.policy)
        self.save()
        return receipt

    def literal(self, view: CallbackView) -> Result:
        extracted = next(e for e in view.inputs if e.id == view.action.target_evidence_id)
        doc = self.documents(view)[0]
        parsed = validate_output(_data(extracted)["output"], Extraction)
        assert isinstance(parsed, Extraction)
        valid = all(c.source_id == doc.source_id and c.quote in doc.text for c in parsed.claims)
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            checks=(
                view.check(
                    status="PASS" if valid else "FAIL",
                    reason="literal source quotation only; no semantic certification",
                ),
            ),
        )

    def semantic(self, view: CallbackView) -> Result:
        answer = next(e for e in view.inputs if e.id == view.action.target_evidence_id)
        review = next(e for e in view.inputs if e.obligation_id == "review")
        output = validate_output(_data(answer)["output"], Answer)
        feedback = validate_output(_data(review)["output"], Review)
        assert isinstance(output, Answer) and isinstance(feedback, Review)
        docs = {d.source_id: d for d in self.documents(view)}
        valid = _data(review)["reviewed_answer_id"] == answer.id and all(
            c.source_id in docs
            and c.version == docs[c.source_id].version
            and c.quote in docs[c.source_id].text
            for c in output.citations
        )
        status: Literal["PASS", "FAIL", "UNKNOWN"] = feedback.status if valid else "FAIL"
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            checks=(
                view.check(
                    status=status,
                    reason=_json(
                        {
                            "semantic_review": feedback.model_dump(mode="json"),
                            "literal_citations_valid": valid,
                            "review_evidence_id": review.id,
                        }
                    ),
                ),
            ),
        )

    def handlers(self) -> dict[str, Any]:
        return {
            f"reader:{self.digest}": self.llm,
            f"integrator:{self.digest}": self.llm,
            f"reviewer:{self.digest}": self.llm,
            "host:literal-citation": self.literal,
            f"authorize:{self.digest}": self.semantic,
        }

    def result(self) -> dict[str, Any]:
        superseded = {e.target_id for e in self.state.supersessions if e.kind == "evidence"}
        answers = tuple(
            e for e in self.state.evidence if e.obligation_id == "answer" and e.id not in superseded
        )
        answer = _data(answers[-1])["output"] if answers else None
        latest = answers[-1].id if answers else None
        checks = tuple(
            c for c in self.state.checks if c.basis and c.basis.target.evidence_id == latest
        )
        complete = any(c.status == "PASS" for c in checks)
        measured = tuple(r.actual_resources.tokens for r in self.state.results)
        pending = any(
            a.id not in {r.attempt_id for r in self.state.results} for a in self.state.attempts
        )
        decision = plan(self.state, (), TRIAL_BUDGET, self.policy)
        return {
            "task_id": self.task.task_id,
            "family": self.task.family,
            "arm": self.arm,
            "model": self.model,
            "model_digest": self.digest,
            "seed": self.seed,
            "trial_id": self.trial_id,
            "calls": self.calls,
            "answer": answer,
            "answer_evidence_id": latest,
            "state": self.state.model_dump(mode="json"),
            "reviews": [
                _data(e)["output"] for e in self.state.evidence if e.obligation_id == "review"
            ],
            "runner_stop": self.runner_stop,
            "runner_error": self.runner_error,
            "secondary_origin_results": self.secondary_origin_results,
            "secondary_limit": self.secondary_limit,
            "domain_stop": decision.stop_reason,
            "decisions": self.decisions,
            "router_satisfied": None if self.arm == "C" else decision.stop_reason == "satisfied",
            "system_claimed_complete": complete,
            "fault": self.fault,
            "pending": pending,
            "cost": {
                "llm_calls": len(self.calls),
                "tokens": sum(measured) if all(v is not None for v in measured) else None,
                "actions": len(self.state.results),
                "verifications": sum(
                    r.actual_resources.verifications or 0 for r in self.state.results
                ),
            },
        }


def run_trial(
    task: PublicTask,
    *,
    arm: Arm,
    model: str,
    model_digest: str,
    seed: int,
    client: ChatClient,
    checkpoint: Path | None = None,
    resume: bool = False,
    secondary_steps: int = 0,
) -> dict[str, Any]:
    """One finite trial, optionally resume exact known records; never redispatch pending.

    C receives all documents initially and uses fixed-stage public step issuance.
    A/B share the same public run factory, policies, callbacks and complete pools.
    Secondary continuation is an explicitly separate sensitivity, default zero.
    """
    if arm not in ("A", "B", "C") or secondary_steps not in (0, 1, 2):
        raise ValueError("invalid arm or secondary continuation bound")
    if len(model_digest) != 64 or any(c not in "0123456789abcdef" for c in model_digest):
        raise ValueError("exact model digest is required")
    trial = _Trial(task, arm, model, model_digest, seed, client, checkpoint)
    if resume:
        trial.load()
    if trial.fault in ("pending_or_unknown_dispatch", "unknown_consumption", "callback_exception"):
        trial.save()
        return trial.result()
    if (
        resume
        and secondary_steps == 0
        and (
            trial.runner_stop not in (None, "step_completed")
            or trial.secondary_origin_results is not None
        )
    ):
        # A completed terminal checkpoint is the primary outcome even if the
        # outer controller died before writing its terminal trial file.
        return trial.result()
    auxiliary_only = resume and secondary_steps > 0
    if arm == "C" and not auxiliary_only:
        # A fixed central workflow; catalogue material is never routed away from C.
        for _ in range(16 - len(trial.state.results)):
            report = step(
                trial.state,
                trial.candidates,
                TRIAL_BUDGET,
                trial.policy,
                trial.handlers(),
                selector=lambda _state, _pool, eligible: min(eligible, key=lambda a: a.id),
            )
            trial.state = report.state
            trial.decisions.append(report.decision.model_dump(mode="json"))
            trial.runner_stop = report.stop_reason
            trial.runner_error = report.error
            trial.save()
            if report.stop_reason != "step_completed":
                break
    elif not auxiliary_only:
        selector = (
            None
            if arm == "A"
            else lambda state, pool, eligible: verify_first(task, state, pool, eligible)
        )
        running = run(
            trial.state,
            trial.candidates,
            TRIAL_BUDGET,
            trial.policy,
            trial.handlers(),
            max_steps=max(1, 16 - len(trial.state.results)),
            selector=selector,
        )
        trial.state, trial.runner_stop = running.state, running.stop_reason
        trial.runner_error = running.error
        trial.decisions.extend(d.model_dump(mode="json") for d in running.decisions)
        trial.save()
    if (
        secondary_steps
        and not trial.fault
        and (trial.runner_stop == "no_progress" or trial.secondary_origin_results is not None)
    ):
        if trial.secondary_origin_results is None:
            trial.secondary_origin_results = len(trial.state.results)
            trial.secondary_limit = secondary_steps
            # Pin the total sensitivity allowance before its first dispatch.
            trial.save()
        elif trial.secondary_limit != secondary_steps:
            raise ValueError("resume cannot change the secondary callback allowance")
        completed = len(trial.state.results) - trial.secondary_origin_results
        for _ in range(max(0, secondary_steps - completed)):
            if trial.result()["pending"] or trial.client.summary().get("blocked"):
                break
            pool = trial.candidates(trial.state)
            eligible = feasible_actions(trial.state, pool, TRIAL_BUDGET, trial.policy)
            issued = {a.action.id for a in trial.state.attempts}
            unused = tuple(a for a in eligible if a.id not in issued)
            if not unused:
                break

            def continuation_selector(
                _state: State,
                _pool: tuple[ActionCandidate, ...],
                _eligible: tuple[ActionCandidate, ...],
            ) -> ActionCandidate:
                return min(_eligible, key=lambda action: action.id)

            continued = step(
                trial.state,
                pool,
                TRIAL_BUDGET,
                trial.policy,
                trial.handlers(),
                selector=continuation_selector,
            )
            trial.state, trial.runner_stop = continued.state, continued.stop_reason
            trial.runner_error = continued.error
            trial.decisions.append(continued.decision.model_dump(mode="json"))
            trial.save()
            if continued.stop_reason != "step_completed" or trial.fault:
                break
    return trial.result()
