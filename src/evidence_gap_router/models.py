"""Strict immutable records; policy is supplied by the host, never by evidence."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(ge=1)]


class Record(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid", allow_inf_nan=False)


class IdentifiedRecord(Record):
    id: Text


class Obligation(IdentifiedRecord):
    id: Text
    description: Text
    scope: Text
    acceptance: Text
    required: bool = True
    priority: Count = 0
    min_evidence: PositiveCount = 1
    min_provenance_groups: PositiveCount = 1
    required_verifiers: tuple[Text, ...] = ()


class Evidence(IdentifiedRecord):
    id: Text
    obligation_id: Text
    scope: Text
    digest: Digest
    producer: Text
    content: str | None = None
    reference: Text | None = None
    source: Text | None = None
    provenance_group: Text | None = None
    withdrawn: bool = False
    expired: bool = False


class CheckResult(IdentifiedRecord):
    id: Text
    obligation_id: Text
    scope: Text
    target_digest: Digest
    verifier_id: Text
    status: Literal["PASS", "FAIL", "UNKNOWN"]
    reason: Text
    withdrawn: bool = False
    expired: bool = False


class Contradiction(IdentifiedRecord):
    id: Text
    obligation_id: Text
    scope: Text
    evidence_ids: tuple[Text, ...]
    reason: Text
    blocking: bool = True

    @model_validator(mode="after")
    def nonempty_targets(self) -> Self:
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("contradiction needs unique evidence targets")
        return self


class Supersession(IdentifiedRecord):
    """Explicit historical replacement, or a contradiction's checked resolution."""

    id: Text
    kind: Literal["evidence", "check", "contradiction"]
    target_id: Text
    reason: Text
    replacement_id: Text | None = None
    check_id: Text | None = None

    @model_validator(mode="after")
    def shape(self) -> Self:
        if self.kind == "contradiction":
            if self.check_id is None or self.replacement_id is not None:
                raise ValueError("contradiction resolution requires only check_id")
        elif self.replacement_id is None or self.check_id is not None:
            raise ValueError("evidence/check supersession requires only replacement_id")
        if self.replacement_id == self.target_id:
            raise ValueError("a record cannot supersede itself")
        return self


class Resources(Record):
    """Separate integer dimensions; None means unknown, or unlimited in Budget."""

    actions: Count | None = None
    verifications: Count | None = None
    tokens: Count | None = None


class Budget(Record):
    limits: Resources


class Policy(Record):
    trusted_verifiers: tuple[Text, ...] = ()
    executable_handlers: tuple[Text, ...] = ()
    prohibit_self_verification: bool = True
    max_pending_verifications: PositiveCount = 10


class ActionCandidate(IdentifiedRecord):
    id: Text
    obligation_id: Text
    scope: Text
    kind: Literal["investigate", "verify", "diversify"]
    handler_id: Text
    resources: Resources = Resources(actions=1, verifications=0)
    target_digest: Digest | None = None
    requires_evidence_ids: tuple[Text, ...] = ()
    source: Text | None = None
    provenance_group: Text | None = None

    @model_validator(mode="after")
    def resource_shape(self) -> Self:
        if self.resources.actions is not None and self.resources.actions < 1:
            raise ValueError("an action must consume at least one action")
        if self.kind == "verify" and (
            self.target_digest is None
            or self.resources.verifications is not None
            and self.resources.verifications < 1
        ):
            raise ValueError("verification needs a digest and at least one verification")
        return self


class Attempt(IdentifiedRecord):
    id: Text
    action: ActionCandidate
    retry: bool = False


class Result(IdentifiedRecord):
    id: Text
    attempt_id: Text
    action_id: Text
    obligation_id: Text
    scope: Text
    target_digest: Digest | None = None
    status: Literal["completed", "failed", "unknown"] = "completed"
    reason: str = ""
    actual_resources: Resources
    side_effects: Literal["known", "unknown"] = "known"
    evidence: tuple[Evidence, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    supersessions: tuple[Supersession, ...] = ()

    @model_validator(mode="after")
    def actual_shape(self) -> Self:
        if self.actual_resources.actions is not None and self.actual_resources.actions < 1:
            raise ValueError("a called handler must consume at least one action")
        if self.status != "completed" and (
            self.evidence or self.checks or self.contradictions or self.supersessions
        ):
            raise ValueError("failed/unknown attempts cannot introduce acceptance records")
        return self


def _unique(records: tuple[IdentifiedRecord, ...], label: str) -> None:
    identifiers = [record.id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f"duplicate {label} IDs")


class State(Record):
    schema_version: Literal["1"] = "1"
    obligations: tuple[Obligation, ...]
    evidence: tuple[Evidence, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    supersessions: tuple[Supersession, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    results: tuple[Result, ...] = ()

    @model_validator(mode="after")
    def references(self) -> Self:
        if not any(o.required for o in self.obligations):
            raise ValueError("at least one declared required obligation is needed")
        for name in (
            "obligations",
            "evidence",
            "checks",
            "contradictions",
            "supersessions",
            "attempts",
            "results",
        ):
            _unique(getattr(self, name), name)
        obligations = {o.id: o for o in self.obligations}
        evidence = {e.id: e for e in self.evidence}
        checks = {c.id: c for c in self.checks}
        contradictions = {c.id: c for c in self.contradictions}
        entries: tuple[Evidence | CheckResult | Contradiction, ...] = (
            *self.evidence,
            *self.checks,
            *self.contradictions,
        )
        for item in entries:
            obligation = obligations.get(item.obligation_id)
            if obligation is None:
                raise ValueError(f"unknown obligation: {item.obligation_id}")
            # Scope mismatch is retained as an ineligible record, never a PASS basis.
        for check in self.checks:
            if not any(
                e.obligation_id == check.obligation_id
                and e.scope == check.scope
                and e.digest == check.target_digest
                for e in self.evidence
            ):
                raise ValueError(f"check {check.id} targets an unrecorded digest/scope")
        for contradiction in self.contradictions:
            for identifier in contradiction.evidence_ids:
                e = evidence.get(identifier)
                if e is None or (e.obligation_id, e.scope) != (
                    contradiction.obligation_id,
                    contradiction.scope,
                ):
                    raise ValueError("contradiction evidence target mismatch")
        superseded: set[tuple[str, str]] = set()
        for event in self.supersessions:
            if (event.kind, event.target_id) in superseded:
                raise ValueError("a record may be explicitly superseded only once")
            superseded.add((event.kind, event.target_id))
            if event.kind == "contradiction":
                target = contradictions.get(event.target_id)
                resolution_check = checks.get(event.check_id or "")
                if target is None or resolution_check is None or resolution_check.status != "PASS":
                    raise ValueError("contradiction resolution needs a recorded PASS")
                if (target.obligation_id, target.scope) != (
                    resolution_check.obligation_id,
                    resolution_check.scope,
                ):
                    raise ValueError("contradiction resolution target mismatch")
                if resolution_check.target_digest not in {
                    evidence[i].digest for i in target.evidence_ids
                }:
                    raise ValueError("resolution check must target involved evidence")
            else:
                records = evidence if event.kind == "evidence" else checks
                old = records.get(event.target_id)
                new = records.get(event.replacement_id or "")
                if old is None or new is None:
                    raise ValueError("supersession targets must be recorded")
                if (old.obligation_id, old.scope) != (new.obligation_id, new.scope):
                    raise ValueError("supersession cannot cross obligation/scope")
                if (
                    isinstance(old, CheckResult)
                    and isinstance(new, CheckResult)
                    and old.target_digest != new.target_digest
                ):
                    raise ValueError("check supersession cannot cross target digest")
        # Cycles would make current applicability ambiguous.
        for kind in ("evidence", "check"):
            links = {s.target_id: s.replacement_id for s in self.supersessions if s.kind == kind}
            for first in links:
                seen: set[str] = set()
                current: str | None = first
                while current in links:
                    if current in seen:
                        raise ValueError("supersession cycle")
                    if current is None:
                        break
                    seen.add(current)
                    current = links[current]
        attempts = {a.id: a for a in self.attempts}
        observed: set[str] = set()
        prior_actions: dict[str, ActionCandidate] = {}
        for attempt in self.attempts:
            if attempt.action.obligation_id not in obligations:
                raise ValueError("attempt targets unknown obligation")
            previous_action = prior_actions.get(attempt.action.id)
            if previous_action is not None:
                if previous_action != attempt.action:
                    raise ValueError("action ID collision in attempt history")
                if not attempt.retry:
                    raise ValueError("repeated action requires explicit retry attempt")
            prior_actions[attempt.action.id] = attempt.action
        for result in self.results:
            issued = attempts.get(result.attempt_id)
            if issued is None:
                raise ValueError("result has no issued attempt")
            action = issued.action
            if (result.action_id, result.obligation_id, result.scope, result.target_digest) != (
                action.id,
                action.obligation_id,
                action.scope,
                action.target_digest,
            ):
                raise ValueError("result does not match issued action/target")
            if result.attempt_id in observed:
                raise ValueError("attempt already has a result")
            observed.add(result.attempt_id)
            result_entries: tuple[Evidence | CheckResult | Contradiction, ...] = (
                *result.evidence,
                *result.checks,
                *result.contradictions,
            )
            for item in result_entries:
                if (item.obligation_id, item.scope) != (action.obligation_id, action.scope):
                    raise ValueError("result record does not match issued obligation/scope")
            if action.kind == "verify" and any(
                c.target_digest != action.target_digest for c in result.checks
            ):
                raise ValueError("verification result digest does not match issued target")
            if result.checks and action.kind != "verify":
                raise ValueError("reported checks require an issued verify action")
            if action.kind == "verify" and result.actual_resources.verifications == 0:
                raise ValueError("a called verification must consume a verification")
            if result.checks and result.actual_resources.verifications == 0:
                raise ValueError("reported checks must consume a verification")
            for name in ("evidence", "checks", "contradictions", "supersessions"):
                recorded = {i.id: i for i in getattr(self, name)}
                for item in getattr(result, name):
                    if recorded.get(item.id) != item:
                        raise ValueError("result payload differs from state history")
            for event in result.supersessions:
                targets = (
                    evidence
                    if event.kind == "evidence"
                    else (checks if event.kind == "check" else contradictions)
                )
                target_record = targets[event.target_id]
                if (target_record.obligation_id, target_record.scope) != (
                    action.obligation_id,
                    action.scope,
                ):
                    raise ValueError("result supersession does not match issued obligation/scope")
                if action.kind == "verify" and event.kind == "check":
                    check_target = checks[event.target_id]
                    if check_target.target_digest != action.target_digest:
                        raise ValueError("supersession check digest does not match issued target")
                if action.kind == "verify" and event.kind == "contradiction":
                    resolution = checks[event.check_id or ""]
                    if resolution.target_digest != action.target_digest:
                        raise ValueError("resolution check digest does not match issued target")
        pending_attempts = [a.id for a in self.attempts if a.id not in observed]
        if len(pending_attempts) > 1 or (
            pending_attempts and pending_attempts[0] != self.attempts[-1].id
        ):
            raise ValueError("single-writer history permits only its final attempt to be pending")
        return self


class Residual(Record):
    obligation_id: Text | None
    code: Text
    reason: Text
    record_ids: tuple[Text, ...] = ()
    blocking: bool = True


class Exclusion(Record):
    action_id: Text
    reasons: tuple[Text, ...]


class Coverage(Record):
    satisfied: Count
    required: PositiveCount
    ratio: Annotated[float, Field(ge=0, le=1)]
    scopes: tuple[Text, ...]
    policy: Policy


class Decision(Record):
    schema_version: Literal["1"] = "1"
    action: ActionCandidate | None
    reason: Text
    exclusions: tuple[Exclusion, ...]
    residuals: tuple[Residual, ...]
    coverage: Coverage
    remaining_resources: Resources
    stop_reason: Literal["satisfied", "budget_exhausted", "blocked", "escalation_required"] | None


class PlanInput(Record):
    schema_version: Literal["1"] = "1"
    state: State
    candidates: tuple[ActionCandidate, ...]
    budget: Budget
    policy: Policy

    @model_validator(mode="after")
    def unique_candidates(self) -> Self:
        _unique(self.candidates, "candidate")
        return self
