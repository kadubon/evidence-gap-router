"""Strict immutable records; policy is supplied by the host, never by evidence."""

from __future__ import annotations

import hashlib
import json
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
    contract_revision: Text = "1"

    @property
    def contract_fingerprint(self) -> str:
        return contract_fingerprint(self)


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def contract_fingerprint(obligation: Obligation) -> str:
    """Mechanical contract identity; excludes display text and routing preferences."""
    return _fingerprint(
        {
            "id": obligation.id,
            "scope": obligation.scope,
            "contract_revision": obligation.contract_revision,
            "acceptance": obligation.acceptance,
            "min_evidence": obligation.min_evidence,
            "min_provenance_groups": obligation.min_provenance_groups,
            "required_verifiers": sorted(set(obligation.required_verifiers)),
        }
    )


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


class DependencyRequirement(Record):
    evidence_id: Text
    obligation_id: Text
    scope: Text
    requirement: Literal["exists", "active", "verified"] = "active"
    digest: Digest | None = None
    contract_fingerprint: Digest | None = None


class EvidenceBinding(Record):
    evidence_id: Text
    digest: Digest
    obligation_id: Text
    scope: Text
    contract_fingerprint: Digest
    requirement: Literal["exists", "active", "verified"] = "active"


class VerificationBasis(Record):
    obligation_id: Text
    scope: Text
    contract_fingerprint: Digest
    target: EvidenceBinding
    dependencies: tuple[EvidenceBinding, ...] = ()
    checker_id: Text
    checker_revision: Text = "1"
    purpose: Literal["content", "check_resolution", "contradiction_resolution"] = "content"
    resolution_target_id: Text | None = None
    resolution_fingerprint: Digest | None = None

    @model_validator(mode="after")
    def targets(self) -> Self:
        if (self.obligation_id, self.scope, self.contract_fingerprint) != (
            self.target.obligation_id,
            self.target.scope,
            self.target.contract_fingerprint,
        ):
            raise ValueError("basis target must match its obligation, scope, and contract")
        identifiers = [d.evidence_id for d in self.dependencies]
        if len(identifiers) != len(set(identifiers)) or self.target.evidence_id in identifiers:
            raise ValueError("basis dependencies must be unique and exclude its target")
        if self.purpose == "content":
            if self.resolution_target_id is not None or self.resolution_fingerprint is not None:
                raise ValueError("content verification cannot declare a resolution")
        elif self.resolution_target_id is None or self.resolution_fingerprint is None:
            raise ValueError("resolution needs a target ID and fingerprint")
        return self


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
    basis: VerificationBasis | None = None
    legacy: bool = False

    @model_validator(mode="after")
    def binding(self) -> Self:
        if self.basis is not None and (
            self.obligation_id,
            self.scope,
            self.target_digest,
            self.verifier_id,
        ) != (
            self.basis.obligation_id,
            self.basis.scope,
            self.basis.target.digest,
            self.basis.checker_id,
        ):
            raise ValueError("check fields must match its verification basis")
        if self.legacy and self.basis is not None:
            raise ValueError("legacy checks cannot invent a verification basis")
        return self


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
    legacy: bool = False

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


class Invalidation(IdentifiedRecord):
    """Append-only host declaration; the original record and receipt stay unchanged."""

    kind: Literal["evidence", "check"]
    target_id: Text
    obligation_id: Text
    scope: Text
    reason: Text


class Resources(Record):
    """Separate integer dimensions; None means unknown, or unlimited in Budget."""

    actions: Count | None = None
    verifications: Count | None = None
    tokens: Count | None = None


class Budget(Record):
    limits: Resources


class CheckerPermission(Record):
    checker_id: Text
    revision: Text = "1"
    purposes: tuple[Literal["content", "check_resolution", "contradiction_resolution"], ...] = (
        "content",
    )


class HandlerRegistration(Record):
    handler_id: Text
    roles: tuple[Literal["investigate", "verify", "diversify"], ...]
    checkers: tuple[CheckerPermission, ...] = ()

    def allows(self, basis: VerificationBasis) -> bool:
        return "verify" in self.roles and any(
            permission.checker_id == basis.checker_id
            and permission.revision == basis.checker_revision
            and basis.purpose in permission.purposes
            for permission in self.checkers
        )


class Policy(Record):
    trusted_verifiers: tuple[Text, ...] = ()
    executable_handlers: tuple[Text, ...] = ()
    prohibit_self_verification: bool = True
    max_pending_verifications: PositiveCount = 10
    handlers: tuple[HandlerRegistration, ...] = ()
    available_handlers: tuple[Text, ...] | None = None

    @model_validator(mode="after")
    def unique_handlers(self) -> Self:
        ids = [h.handler_id for h in self.handlers]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate handler registrations")
        return self


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
    target_evidence_id: Text | None = None
    checker_id: Text | None = None
    checker_revision: Text = "1"
    purpose: Literal["content", "check_resolution", "contradiction_resolution"] = "content"
    dependencies: tuple[DependencyRequirement, ...] = ()
    resolution_target_id: Text | None = None
    produces_evidence_id: Text | None = None

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
        if self.kind != "verify" and (
            self.checker_id is not None
            or self.purpose != "content"
            or self.resolution_target_id is not None
        ):
            raise ValueError("acquisition cannot declare checker or resolution authority")
        if self.purpose == "content" and self.resolution_target_id is not None:
            raise ValueError("content action cannot declare a resolution target")
        if self.purpose != "content" and self.resolution_target_id is None:
            raise ValueError("resolution action needs a target ID")
        dependency_ids = [d.evidence_id for d in self.dependencies]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("duplicate dependency requirements")
        if len(self.requires_evidence_ids) != len(set(self.requires_evidence_ids)):
            raise ValueError("duplicate prerequisite IDs")
        return self


class Attempt(IdentifiedRecord):
    id: Text
    action: ActionCandidate
    retry: bool = False
    basis: VerificationBasis | None = None
    registration: HandlerRegistration | None = None
    inputs: tuple[EvidenceBinding, ...] = ()
    legacy: bool = False


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
    legacy: bool = False

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
    schema_version: Literal["2"] = "2"
    obligations: tuple[Obligation, ...]
    evidence: tuple[Evidence, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    supersessions: tuple[Supersession, ...] = ()
    invalidations: tuple[Invalidation, ...] = ()
    attempts: tuple[Attempt, ...] = ()
    results: tuple[Result, ...] = ()
    legacy_schema1: str | None = None

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
            "invalidations",
            "attempts",
            "results",
        ):
            _unique(getattr(self, name), name)
        obligations = {o.id: o for o in self.obligations}
        evidence = {e.id: e for e in self.evidence}
        checks = {c.id: c for c in self.checks}
        contradictions = {c.id: c for c in self.contradictions}
        for invalidation in self.invalidations:
            invalidated = (evidence if invalidation.kind == "evidence" else checks).get(
                invalidation.target_id
            )
            if invalidated is None or (invalidated.obligation_id, invalidated.scope) != (
                invalidation.obligation_id,
                invalidation.scope,
            ):
                raise ValueError("invalidation requires an exact recorded ID/obligation/scope")
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
        bindings = [
            binding
            for c in self.checks
            if c.basis is not None
            for binding in (c.basis.target, *c.basis.dependencies)
        ]
        bindings.extend(binding for a in self.attempts for binding in a.inputs)
        for binding in bindings:
            target_evidence = evidence.get(binding.evidence_id)
            if target_evidence is None or (
                target_evidence.digest,
                target_evidence.obligation_id,
                target_evidence.scope,
            ) != (binding.digest, binding.obligation_id, binding.scope):
                raise ValueError(
                    "basis references an unrecorded or mismatched evidence ID/digest/scope"
                )
        for checked in self.checks:
            basis = checked.basis
            if basis is None or basis.purpose == "content":
                continue
            resolution_records = checks if basis.purpose == "check_resolution" else contradictions
            resolution_target = resolution_records.get(basis.resolution_target_id or "")
            if resolution_target is None or (
                resolution_target.obligation_id,
                resolution_target.scope,
            ) != (basis.obligation_id, basis.scope):
                raise ValueError("verification basis references an invalid resolution target")
        for contradiction in self.contradictions:
            for identifier in contradiction.evidence_ids:
                e = evidence.get(identifier)
                if e is None or (e.obligation_id, e.scope) != (
                    contradiction.obligation_id,
                    contradiction.scope,
                ):
                    raise ValueError("contradiction evidence target mismatch")
        superseded: set[tuple[str, str, bool, str | None]] = set()
        for event in self.supersessions:
            grounds = None if event.kind == "evidence" else event.replacement_id or event.check_id
            identity = (event.kind, event.target_id, event.legacy, grounds)
            if identity in superseded:
                raise ValueError("duplicate supersession grounds")
            superseded.add(identity)
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
            links: dict[str, set[str]] = {}
            for event in self.supersessions:
                if event.kind == kind and event.replacement_id is not None:
                    links.setdefault(event.target_id, set()).add(event.replacement_id)
            completed: set[str] = set()
            for first in links:
                stack = [(first, False)]
                visiting: set[str] = set()
                while stack:
                    current, exiting = stack.pop()
                    if exiting:
                        visiting.remove(current)
                        completed.add(current)
                    elif current in visiting:
                        raise ValueError("supersession cycle")
                    elif current not in completed:
                        visiting.add(current)
                        stack.append((current, True))
                        stack.extend((child, False) for child in links.get(current, ()))
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
            if not attempt.legacy:
                if (
                    attempt.registration is None
                    or attempt.action.kind not in attempt.registration.roles
                ):
                    raise ValueError("issued attempt needs a matching host handler registration")
                if attempt.registration.handler_id != attempt.action.handler_id:
                    raise ValueError("attempt handler registration mismatch")
                if attempt.action.kind == "verify":
                    if attempt.basis is None or not attempt.registration.allows(attempt.basis):
                        raise ValueError("issued verification needs an authorized fixed basis")
                    if (
                        attempt.basis.obligation_id,
                        attempt.basis.scope,
                        attempt.basis.target.evidence_id,
                        attempt.basis.target.digest,
                        attempt.basis.checker_id,
                        attempt.basis.checker_revision,
                        attempt.basis.purpose,
                        attempt.basis.resolution_target_id,
                    ) != (
                        attempt.action.obligation_id,
                        attempt.action.scope,
                        attempt.action.target_evidence_id,
                        attempt.action.target_digest,
                        attempt.action.checker_id,
                        attempt.action.checker_revision,
                        attempt.action.purpose,
                        attempt.action.resolution_target_id,
                    ):
                        raise ValueError("issued action and verification basis mismatch")
                    if attempt.inputs != (attempt.basis.target, *attempt.basis.dependencies):
                        raise ValueError("issued verification inputs must equal its fixed basis")
                elif attempt.basis is not None:
                    raise ValueError("acquisition attempt cannot carry verification authority")
                declared_ids = list(
                    dict.fromkeys(
                        (
                            *(d.evidence_id for d in attempt.action.dependencies),
                            *attempt.action.requires_evidence_ids,
                        )
                    )
                )
                if attempt.basis is not None:
                    declared_ids = [
                        i for i in declared_ids if i != attempt.basis.target.evidence_id
                    ]
                    disclosed = attempt.basis.dependencies
                else:
                    disclosed = attempt.inputs
                if [b.evidence_id for b in disclosed] != declared_ids:
                    raise ValueError("issued inputs must match the finite declared dependencies")
                for dependency in attempt.action.dependencies:
                    binding = next(
                        b for b in attempt.inputs if b.evidence_id == dependency.evidence_id
                    )
                    if (binding.obligation_id, binding.scope, binding.requirement) != (
                        dependency.obligation_id,
                        dependency.scope,
                        dependency.requirement,
                    ):
                        raise ValueError("issued dependency binding does not match its declaration")
                    if dependency.digest is not None and dependency.digest != binding.digest:
                        raise ValueError("issued dependency digest does not match its declaration")
                    if dependency.contract_fingerprint is not None and (
                        dependency.contract_fingerprint != binding.contract_fingerprint
                    ):
                        raise ValueError(
                            "issued dependency contract does not match its declaration"
                        )
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
            if result.legacy != issued.legacy:
                raise ValueError("result legacy status does not match its issued attempt")
            result_entries: tuple[Evidence | CheckResult | Contradiction, ...] = (
                *result.evidence,
                *result.checks,
                *result.contradictions,
            )
            for item in result_entries:
                if (item.obligation_id, item.scope) != (action.obligation_id, action.scope):
                    raise ValueError("result record does not match issued obligation/scope")
            if (
                not issued.legacy
                and action.produces_evidence_id is not None
                and any(e.id != action.produces_evidence_id for e in result.evidence)
            ):
                raise ValueError("receipt evidence does not match its declared acquisition target")
            if action.kind == "verify" and any(
                c.target_digest != action.target_digest for c in result.checks
            ):
                raise ValueError("verification result digest does not match issued target")
            if result.checks and action.kind != "verify":
                raise ValueError("reported checks require an issued verify action")
            if not issued.legacy:
                for checked in result.checks:
                    if checked.basis is None or checked.basis != issued.basis:
                        raise ValueError("receipt basis does not match the issued verification")
                if action.kind != "verify" and any(
                    event.kind != "evidence" for event in result.supersessions
                ):
                    raise ValueError(
                        "acquisition cannot supersede checks or resolve contradictions"
                    )
                for event in result.supersessions:
                    if event.legacy:
                        raise ValueError("new receipts cannot introduce legacy supersession")
                    if event.kind == "check" and action.purpose != "check_resolution":
                        raise ValueError("check supersession requires check_resolution authority")
                    if (
                        event.kind == "contradiction"
                        and action.purpose != "contradiction_resolution"
                    ):
                        raise ValueError("contradiction resolution requires dedicated authority")
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
                if not issued.legacy and event.kind in ("check", "contradiction"):
                    resolution_id = (
                        event.replacement_id if event.kind == "check" else event.check_id
                    )
                    resolution_check = checks[resolution_id or ""]
                    if (
                        resolution_check.status != "PASS"
                        or resolution_check.basis != issued.basis
                        or issued.basis is None
                        or issued.basis.resolution_target_id != event.target_id
                    ):
                        raise ValueError("resolution receipt must match the dedicated issued basis")
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


class Gap(Record):
    id: Text
    obligation_id: Text
    scope: Text
    kind: Literal[
        "missing_evidence",
        "provenance",
        "content_check",
        "failed_check",
        "unknown_check",
        "dependency",
        "contradiction",
    ]
    target_evidence_id: Text | None = None
    target_digest: Digest | None = None
    checker_id: Text | None = None
    dependency_id: Text | None = None
    purpose: Literal["content", "check_resolution", "contradiction_resolution"] = "content"
    record_ids: tuple[Text, ...] = ()
    reason: Text


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
    schema_version: Literal["2"] = "2"
    action: ActionCandidate | None
    reason: Text
    exclusions: tuple[Exclusion, ...]
    residuals: tuple[Residual, ...]
    coverage: Coverage
    remaining_resources: Resources
    stop_reason: Literal["satisfied", "budget_exhausted", "blocked", "escalation_required"] | None
    gaps: tuple[Gap, ...] = ()
    selected_gap: Gap | None = None
    pending_verifications: Count = 0


class PlanInput(Record):
    schema_version: Literal["2"] = "2"
    state: State
    candidates: tuple[ActionCandidate, ...]
    budget: Budget
    policy: Policy

    @model_validator(mode="after")
    def unique_candidates(self) -> Self:
        _unique(self.candidates, "candidate")
        return self
