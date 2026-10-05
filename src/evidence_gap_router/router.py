"""Pure deterministic planning and explicit single-writer state transitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from .models import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckResult,
    Coverage,
    Decision,
    Evidence,
    EvidenceBinding,
    Exclusion,
    Gap,
    HandlerRegistration,
    IdentifiedRecord,
    Obligation,
    Policy,
    Residual,
    Resources,
    Result,
    State,
    Supersession,
    VerificationBasis,
    _fingerprint,
)

DIMENSIONS = ("actions", "verifications", "tokens")


def _active_evidence(state: State, obligation: Obligation) -> tuple[Evidence, ...]:
    replaced = {s.target_id for s in state.supersessions if s.kind == "evidence"}
    return tuple(
        e
        for e in state.evidence
        if e.obligation_id == obligation.id
        and e.scope == obligation.scope
        and e.id not in replaced
        and not e.withdrawn
        and not e.expired
        and (e.content is not None or e.reference is not None)
    )


def evidence_binding(
    state: State,
    evidence_id: str,
    requirement: Literal["exists", "active", "verified"] = "active",
) -> EvidenceBinding:
    evidence = next((e for e in state.evidence if e.id == evidence_id), None)
    if evidence is None:
        raise ValueError(f"dependency_missing:{evidence_id}")
    obligation = next(o for o in state.obligations if o.id == evidence.obligation_id)
    return EvidenceBinding(
        evidence_id=evidence.id,
        digest=evidence.digest,
        obligation_id=evidence.obligation_id,
        scope=evidence.scope,
        contract_fingerprint=obligation.contract_fingerprint,
        requirement=requirement,
    )


def resolution_fingerprint(
    state: State, kind: Literal["check", "contradiction"], target_id: str
) -> str:
    records = state.checks if kind == "check" else state.contradictions
    target = next((r for r in records if r.id == target_id), None)
    if target is None:
        raise ValueError("resolution_target_missing")
    obligation = next(o for o in state.obligations if o.id == target.obligation_id)
    related = []
    if kind == "contradiction":
        conflict = next(c for c in state.contradictions if c.id == target_id)
        related = [
            evidence_binding(state, i).model_dump(mode="json") for i in conflict.evidence_ids
        ]
    return _fingerprint(
        {
            "kind": kind,
            "record": target.model_dump(mode="json"),
            "contract": obligation.contract_fingerprint,
            "related": related,
        }
    )


def _input_bindings(state: State, action: ActionCandidate) -> tuple[EvidenceBinding, ...]:
    bindings: list[EvidenceBinding] = []
    declared = {d.evidence_id: d for d in action.dependencies}
    for dependency in action.dependencies:
        if (
            action.kind == "verify"
            and dependency.evidence_id == action.target_evidence_id
            and dependency.requirement == "verified"
        ):
            raise ValueError(f"dependency_cycle:{dependency.evidence_id}")
        binding = evidence_binding(state, dependency.evidence_id, dependency.requirement)
        if (binding.obligation_id, binding.scope) != (dependency.obligation_id, dependency.scope):
            raise ValueError(f"dependency_scope_mismatch:{dependency.evidence_id}")
        if dependency.digest is not None and dependency.digest != binding.digest:
            raise ValueError(f"dependency_digest_mismatch:{dependency.evidence_id}")
        if (
            dependency.contract_fingerprint is not None
            and dependency.contract_fingerprint != binding.contract_fingerprint
        ):
            raise ValueError(f"dependency_contract_mismatch:{dependency.evidence_id}")
        bindings.append(binding)
    for identifier in action.requires_evidence_ids:
        if identifier not in declared:
            try:
                bindings.append(evidence_binding(state, identifier))
            except ValueError as error:
                raise ValueError(f"prerequisite_missing:{identifier}") from error
    return tuple(bindings)


def make_basis(state: State, action: ActionCandidate) -> VerificationBasis:
    """Pin only the target, contract and finite declared material used by the checker."""
    if action.kind != "verify":
        raise ValueError("only verification actions have a verification basis")
    if action.target_evidence_id is None:
        raise ValueError("target_evidence_id_missing")
    if action.checker_id is None:
        raise ValueError("checker_missing")
    target = evidence_binding(state, action.target_evidence_id)
    if (target.obligation_id, target.scope, target.digest) != (
        action.obligation_id,
        action.scope,
        action.target_digest,
    ):
        raise ValueError("target_digest_missing_or_stale")
    dependencies = tuple(
        d for d in _input_bindings(state, action) if d.evidence_id != target.evidence_id
    )
    fingerprint = None
    if action.purpose != "content":
        kind: Literal["check", "contradiction"] = (
            "check" if action.purpose == "check_resolution" else "contradiction"
        )
        fingerprint = resolution_fingerprint(state, kind, action.resolution_target_id or "")
        if kind == "check":
            old = next(c for c in state.checks if c.id == action.resolution_target_id)
            if (old.obligation_id, old.scope, old.target_digest) != (
                action.obligation_id,
                action.scope,
                target.digest,
            ):
                raise ValueError("resolution_target_mismatch")
        else:
            conflict = next(c for c in state.contradictions if c.id == action.resolution_target_id)
            if (conflict.obligation_id, conflict.scope) != (action.obligation_id, action.scope):
                raise ValueError("resolution_target_mismatch")
            inputs = {target.evidence_id, *(d.evidence_id for d in dependencies)}
            if target.evidence_id not in conflict.evidence_ids or not set(
                conflict.evidence_ids
            ).issubset(inputs):
                raise ValueError("resolution_related_evidence_missing")
    return VerificationBasis(
        obligation_id=action.obligation_id,
        scope=action.scope,
        contract_fingerprint=target.contract_fingerprint,
        target=target,
        dependencies=dependencies,
        checker_id=action.checker_id,
        checker_revision=action.checker_revision,
        purpose=action.purpose,
        resolution_target_id=action.resolution_target_id,
        resolution_fingerprint=fingerprint,
    )


def _binding_active(state: State, binding: EvidenceBinding) -> bool:
    obligation = next((o for o in state.obligations if o.id == binding.obligation_id), None)
    if obligation is None or obligation.scope != binding.scope:
        return False
    return obligation.contract_fingerprint == binding.contract_fingerprint and any(
        e.id == binding.evidence_id and e.digest == binding.digest
        for e in _active_evidence(state, obligation)
    )


def _registration(policy: Policy, action: ActionCandidate) -> HandlerRegistration | None:
    if policy.available_handlers is not None and action.handler_id not in policy.available_handlers:
        return None
    if policy.executable_handlers and action.handler_id not in policy.executable_handlers:
        return None
    return next((h for h in policy.handlers if h.handler_id == action.handler_id), None)


def _trusted_check(
    check: CheckResult,
    state: State,
    policy: Policy,
    visiting: frozenset[str] = frozenset(),
) -> bool:
    basis = check.basis
    if basis is None or check.legacy or check.id in visiting or check.withdrawn or check.expired:
        return False
    if check.verifier_id not in policy.trusted_verifiers or not any(
        h.allows(basis) for h in policy.handlers
    ):
        return False
    if not all(_binding_active(state, b) for b in (basis.target, *basis.dependencies)):
        return False
    target = next(e for e in state.evidence if e.id == basis.target.evidence_id)
    if policy.prohibit_self_verification and target.producer == check.verifier_id:
        return False
    if basis.purpose != "content":
        kind: Literal["check", "contradiction"] = (
            "check" if basis.purpose == "check_resolution" else "contradiction"
        )
        try:
            if (
                resolution_fingerprint(state, kind, basis.resolution_target_id or "")
                != basis.resolution_fingerprint
            ):
                return False
        except ValueError:
            return False
    path = visiting | {check.id}
    return all(
        d.requirement != "verified" or _target_verified(state, policy, d.evidence_id, path)
        for d in basis.dependencies
    )


def _valid_resolution(
    state: State, event: Supersession, policy: Policy, visiting: frozenset[str] = frozenset()
) -> bool:
    if event.legacy or event.kind == "evidence":
        return False
    identifier = event.replacement_id if event.kind == "check" else event.check_id
    check = next((c for c in state.checks if c.id == identifier), None)
    if check is None or check.status != "PASS" or check.basis is None:
        return False
    if any(
        s.kind == "check" and s.target_id == check.id and not s.legacy for s in state.supersessions
    ):
        return False
    expected = "check_resolution" if event.kind == "check" else "contradiction_resolution"
    return (
        check.basis.purpose == expected
        and check.basis.resolution_target_id == event.target_id
        and _trusted_check(check, state, policy, visiting)
    )


def _replaced_checks(
    state: State, policy: Policy, visiting: frozenset[str] = frozenset()
) -> set[str]:
    checks = {c.id: c for c in state.checks}
    return {
        s.target_id
        for s in state.supersessions
        if s.kind == "check"
        and not s.legacy
        and (checks[s.target_id].status == "PASS" or _valid_resolution(state, s, policy, visiting))
    }


def _target_checks(
    state: State, policy: Policy, evidence: Evidence, visiting: frozenset[str] = frozenset()
) -> tuple[CheckResult, ...]:
    replaced = _replaced_checks(state, policy, visiting)
    return tuple(
        c
        for c in state.checks
        if c.id not in replaced
        and (c.obligation_id, c.scope, c.target_digest)
        == (evidence.obligation_id, evidence.scope, evidence.digest)
        and (
            c.basis is not None
            and c.basis.target.evidence_id == evidence.id
            and c.basis.purpose in ("content", "check_resolution")
            and _trusted_check(c, state, policy, visiting)
            or c.legacy
            and c.status in ("FAIL", "UNKNOWN")
        )
    )


def _target_verified(
    state: State, policy: Policy, identifier: str, visiting: frozenset[str] = frozenset()
) -> bool:
    evidence = next(e for e in state.evidence if e.id == identifier)
    obligation = next(o for o in state.obligations if o.id == evidence.obligation_id)
    checks = _target_checks(state, policy, evidence, visiting)
    passes = {
        c.verifier_id
        for c in checks
        if c.status == "PASS"
        and c.basis is not None
        and c.basis.purpose in ("content", "check_resolution")
    }
    return not any(c.status in ("FAIL", "UNKNOWN") for c in checks) and (
        set(obligation.required_verifiers).issubset(passes)
        if obligation.required_verifiers
        else bool(passes)
    )


@dataclass(frozen=True)
class _Assessment:
    residuals: tuple[Residual, ...]
    satisfied: frozenset[str]
    gaps: tuple[Gap, ...]
    pending: int


def _analyze(state: State, policy: Policy) -> _Assessment:
    residuals: list[Residual] = []
    gaps: list[Gap] = []
    satisfied: set[str] = set()
    pending = 0
    for obligation in sorted(state.obligations, key=lambda o: o.id):
        current = _active_evidence(state, obligation)
        before = len(residuals)

        def add(
            code: str,
            reason: str,
            ids: Iterable[str] = (),
            blocking: bool = True,
            obligation_id: str = obligation.id,
        ) -> None:
            residuals.append(
                Residual(
                    obligation_id=obligation_id,
                    code=code,
                    reason=reason,
                    record_ids=tuple(sorted(ids)),
                    blocking=blocking,
                )
            )

        # First recorded representative stays stable when identical reposts arrive.
        ordered = list(current)
        parents = list(range(len(ordered)))

        def root(index: int, links: list[int] = parents) -> int:
            while links[index] != index:
                index = links[index]
            return index

        for index, evidence in enumerate(ordered):
            for earlier_index, earlier in enumerate(ordered[:index]):
                if earlier.digest == evidence.digest and (
                    earlier.source == evidence.source
                    or earlier.provenance_group == evidence.provenance_group
                ):
                    parents[root(index)] = root(earlier_index)
        unique: list[Evidence] = []
        duplicates: list[str] = []
        seen_components: set[int] = set()
        for index, evidence in enumerate(ordered):
            # Unknown origins cannot establish additional independent sources.
            component = root(index)
            if component in seen_components:
                duplicates.append(evidence.id)
            else:
                unique.append(evidence)
                seen_components.add(component)
        if duplicates:
            add(
                "duplicate_evidence",
                "Same content and source does not add evidence.",
                duplicates,
                False,
            )
        if len(unique) < obligation.min_evidence:
            add(
                "missing_evidence",
                f"Need {obligation.min_evidence} content/source contributions; have {len(unique)}.",
            )
            gaps.append(
                Gap(
                    id=f"evidence:{obligation.id}",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    kind="missing_evidence",
                    reason="Distinct evidence is missing.",
                )
            )
        # A source with conflicting declarations is still only one declared source.
        by_source: dict[str, set[str]] = {}
        unknown = []
        for e in current:
            if e.source is None or e.provenance_group is None:
                unknown.append(e.id)
            else:
                by_source.setdefault(e.source, set()).add(e.provenance_group)
        provenance_components: list[set[str]] = []
        for source_groups in by_source.values():
            merged = set(source_groups)
            disjoint: list[set[str]] = []
            for group_component in provenance_components:
                if merged & group_component:
                    merged |= group_component
                else:
                    disjoint.append(group_component)
            provenance_components = [*disjoint, merged]
        groups = provenance_components
        conflicting_sources = [source for source, values in by_source.items() if len(values) > 1]
        if conflicting_sources:
            add(
                "conflicting_provenance",
                "The same source declares multiple provenance groups; resolve that ambiguity.",
                conflicting_sources,
            )
        if len(groups) < obligation.min_provenance_groups:
            add(
                "insufficient_provenance",
                f"Need {obligation.min_provenance_groups} declared groups; have {len(groups)}.",
            )
            gaps.append(
                Gap(
                    id=f"provenance:{obligation.id}",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    kind="provenance",
                    reason="Declared provenance groups are missing.",
                )
            )
        if unknown:
            add(
                "unknown_provenance",
                "Missing source/provenance is retained and does not establish a group.",
                unknown,
                len(groups) < obligation.min_provenance_groups,
            )
        available = {
            c.checker_id
            for h in policy.handlers
            if "verify" in h.roles
            for c in h.checkers
            if "content" in c.purposes
        } & set(policy.trusted_verifiers)
        unavailable = set(obligation.required_verifiers) - available
        if not available or unavailable:
            add(
                "verifier_unavailable",
                "Host policy does not authorize the required verifier(s).",
                unavailable,
            )
        canonical_ids = {e.id for e in unique}
        for evidence in current:
            target_checks = _target_checks(state, policy, evidence)
            failures = [c for c in target_checks if c.status == "FAIL"]
            unknown_checks = [c for c in target_checks if c.status == "UNKNOWN"]
            # Duplicate support never increases coverage, but its actual negative
            # check is still a current issue on that exact alias ID and basis.
            canonical = evidence.id in canonical_ids
            if not canonical and not failures and not unknown_checks:
                continue
            passes = {
                c.verifier_id
                for c in target_checks
                if c.status == "PASS"
                and c.basis is not None
                and c.basis.purpose in ("content", "check_resolution")
            }
            required = set(obligation.required_verifiers) if canonical else set()
            passed = required.issubset(passes) if required else bool(passes)
            if failures:
                add(
                    "check_failed",
                    "Recorded FAIL remains active until explicitly superseded.",
                    (c.id for c in failures),
                )
            if unknown_checks:
                add(
                    "check_unknown",
                    "Recorded UNKNOWN remains active until explicitly superseded.",
                    (c.id for c in unknown_checks),
                )
            if not passed:
                add(
                    "unverified",
                    f"Missing applicable trusted validation for target {evidence.id}.",
                    (evidence.id,),
                )
            negative = {c.verifier_id for c in (*failures, *unknown_checks)}
            missing = required - passes if required else (set() if passes or negative else {None})
            for checker in sorted(missing | negative, key=lambda v: v or ""):
                records = [
                    c for c in target_checks if c.verifier_id == checker and c.status != "PASS"
                ]
                kind: Literal["content_check", "failed_check", "unknown_check"] = "content_check"
                if any(c.status == "FAIL" for c in records):
                    kind = "failed_check"
                elif records:
                    kind = "unknown_check"
                gaps.append(
                    Gap(
                        id=f"check:{obligation.id}:{evidence.id}:{checker or '*'}:{kind}",
                        obligation_id=obligation.id,
                        scope=obligation.scope,
                        kind=kind,
                        target_evidence_id=evidence.id,
                        target_digest=evidence.digest,
                        checker_id=checker,
                        purpose="content" if kind == "content_check" else "check_resolution",
                        record_ids=tuple(c.id for c in records),
                        reason="An applicable target check is missing.",
                    )
                )
                pending += 1
        for contradiction in state.contradictions:
            if (contradiction.obligation_id, contradiction.scope) != (
                obligation.id,
                obligation.scope,
            ):
                continue
            resolutions = [
                s
                for s in state.supersessions
                if s.kind == "contradiction" and s.target_id == contradiction.id
            ]
            resolved = any(_valid_resolution(state, s, policy) for s in resolutions)
            if not resolved:
                add(
                    "contradiction",
                    contradiction.reason,
                    (contradiction.id,),
                    contradiction.blocking,
                )
                if contradiction.blocking:
                    gaps.append(
                        Gap(
                            id=f"contradiction:{contradiction.id}",
                            obligation_id=obligation.id,
                            scope=obligation.scope,
                            kind="contradiction",
                            purpose="contradiction_resolution",
                            record_ids=(contradiction.id,),
                            reason=contradiction.reason,
                        )
                    )
        inactive = [
            e.id
            for e in state.evidence
            if e.obligation_id == obligation.id
            and (e.withdrawn or e.expired or e.scope != obligation.scope)
        ]
        if inactive:
            add(
                "ineligible_evidence",
                "Withdrawn, expired, or mismatched-scope evidence is excluded.",
                inactive,
                not bool(current),
            )
        if not any(r.blocking for r in residuals[before:]):
            satisfied.add(obligation.id)
    return _Assessment(tuple(residuals), frozenset(satisfied), tuple(gaps), pending)


def _resource_status(state: State, budget: Budget) -> tuple[Resources, tuple[Residual, ...]]:
    used = {name: 0 for name in DIMENSIONS}
    issues: list[Residual] = []
    attempts = {a.id: a for a in state.attempts}
    for result in state.results:
        action = attempts[result.attempt_id].action
        for name in DIMENSIONS:
            actual = getattr(result.actual_resources, name)
            limit = getattr(budget.limits, name)
            upper = getattr(action.resources, name)
            if actual is None:
                if limit is not None or upper is not None:
                    issues.append(
                        Residual(
                            obligation_id=result.obligation_id,
                            code="unknown_resource",
                            reason=f"Actual {name} consumption is unknown; further work is unsafe.",
                            record_ids=(result.id,),
                        )
                    )
            else:
                used[name] += actual
                if upper is not None and actual > upper:
                    issues.append(
                        Residual(
                            obligation_id=result.obligation_id,
                            code="resource_overrun",
                            reason=f"Actual {name} ({actual}) exceeds upper bound ({upper}).",
                            record_ids=(result.id,),
                        )
                    )
        if result.side_effects == "unknown":
            issues.append(
                Residual(
                    obligation_id=result.obligation_id,
                    code="unknown_execution",
                    reason="The host reported unknown side effects; explicit escalation is needed.",
                    record_ids=(result.id,),
                )
            )
    remaining: dict[str, int | None] = {}
    for name in DIMENSIONS:
        limit = getattr(budget.limits, name)
        remaining[name] = None if limit is None else max(0, limit - used[name])
        if limit is not None and used[name] > limit:
            issues.append(
                Residual(
                    obligation_id=None,
                    code="budget_overrun",
                    reason=f"Recorded {name} consumption exceeds the host budget.",
                )
            )
    return Resources(**remaining), tuple(issues)


def _candidate_reasons(
    state: State,
    action: ActionCandidate,
    budget: Budget,
    policy: Policy,
    remaining: Resources,
    assessment: _Assessment,
    needed_acquisition: bool = False,
    retry: bool = False,
) -> tuple[str, ...]:
    reasons: list[str] = []
    obligations = {o.id: o for o in state.obligations}
    obligation = obligations.get(action.obligation_id)
    if obligation is None:
        return ("unknown_obligation",)
    if action.scope != obligation.scope:
        reasons.append("scope_mismatch")
    if action.obligation_id in assessment.satisfied:
        reasons.append("obligation_satisfied")
    registration = _registration(policy, action)
    if registration is None:
        reasons.append("handler_unavailable")
    elif action.kind not in registration.roles:
        reasons.append("handler_role_forbidden")
    previous = [a for a in state.attempts if a.action.id == action.id]
    if previous and not retry:
        reasons.append("already_attempted")
    if previous and any(a.action != action for a in previous):
        reasons.append("action_id_collision")
    try:
        bindings = _input_bindings(state, action)
    except ValueError as error:
        bindings = ()
        reasons.append(str(error))
    for binding in bindings:
        if binding.requirement != "exists" and not _binding_active(state, binding):
            reasons.append(f"dependency_inactive:{binding.evidence_id}")
        elif binding.requirement == "verified" and not _target_verified(
            state, policy, binding.evidence_id
        ):
            reasons.append(f"dependency_unverified:{binding.evidence_id}")
    if action.kind == "verify":
        try:
            basis = make_basis(state, action)
        except ValueError as error:
            basis = None
            reasons.append(str(error))
        if basis is not None:
            if not _binding_active(state, basis.target):
                reasons.append("target_digest_missing_or_stale")
            if registration is not None and not registration.allows(basis):
                reasons.append("checker_permission_forbidden")
        if action.checker_id not in policy.trusted_verifiers:
            reasons.append("verifier_unavailable")
        if _gap_for_action(action, assessment.gaps) is None:
            reasons.append("target_already_verified_or_no_matching_gap")
    elif assessment.pending >= policy.max_pending_verifications and not needed_acquisition:
        reasons.append("verification_capacity_reached")
    for name in DIMENSIONS:
        limit = getattr(budget.limits, name)
        upper = getattr(action.resources, name)
        left = getattr(remaining, name)
        if limit is not None:
            if upper is None:
                reasons.append(f"unknown_{name}_upper_bound")
            elif left is not None and upper > left:
                reasons.append(f"budget_{name}_exhausted")
    return tuple(reasons)


def _gap_for_action(action: ActionCandidate, gaps: tuple[Gap, ...]) -> Gap | None:
    for gap in gaps:
        if gap.obligation_id != action.obligation_id:
            continue
        if action.kind != "verify":
            if gap.kind in ("missing_evidence", "provenance"):
                return gap
        elif action.purpose == "content":
            if (
                gap.kind == "content_check"
                and gap.target_evidence_id == action.target_evidence_id
                and (gap.checker_id is None or gap.checker_id == action.checker_id)
            ):
                return gap
        elif action.purpose == "check_resolution":
            if (
                gap.kind in ("failed_check", "unknown_check")
                and action.resolution_target_id in gap.record_ids
            ):
                return gap
        elif action.resolution_target_id in gap.record_ids and gap.kind == "contradiction":
            return gap
    return None


def _needed_acquisition(
    state: State,
    action: ActionCandidate,
    candidates: tuple[ActionCandidate, ...],
    policy: Policy,
    assessment: _Assessment,
) -> bool:
    if action.kind == "verify" or action.produces_evidence_id is None:
        return False
    for verify in candidates:
        if verify.kind != "verify" or _gap_for_action(verify, assessment.gaps) is None:
            continue
        registration = _registration(policy, verify)
        if registration is None or "verify" not in registration.roles:
            continue
        if any(a.action.id == verify.id for a in state.attempts):
            continue
        for dependency in verify.dependencies:
            if (dependency.evidence_id, dependency.obligation_id, dependency.scope) == (
                action.produces_evidence_id,
                action.obligation_id,
                action.scope,
            ) and not any(e.id == dependency.evidence_id for e in state.evidence):
                return True
    return False


def plan(
    state: State, candidates: tuple[ActionCandidate, ...], budget: Budget, policy: Policy
) -> Decision:
    """Recommend at most one declared action without mutating state or consuming budget."""
    if len({a.id for a in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    assessment = _analyze(state, policy)
    residuals = assessment.residuals
    gaps = list(assessment.gaps)
    remaining, resource_issues = _resource_status(state, budget)
    residuals += resource_issues
    required = [o for o in state.obligations if o.required]
    count = sum(o.id in assessment.satisfied for o in required)
    coverage = Coverage(
        satisfied=count,
        required=len(required),
        ratio=count / len(required),
        scopes=tuple(sorted({o.scope for o in required})),
        policy=policy,
    )
    observed = {r.attempt_id for r in state.results}
    in_flight = [a.id for a in state.attempts if a.id not in observed]
    global_reason: str | None = None
    stop: str | None = None
    if resource_issues:
        global_reason, stop = "resource_accounting_unsafe", "escalation_required"
    elif in_flight:
        global_reason, stop = "attempt_pending", "blocked"
        residuals += (
            Residual(
                obligation_id=None,
                code="attempt_pending",
                reason="An issued attempt has no result; it is not automatically reissued.",
                record_ids=tuple(sorted(in_flight)),
            ),
        )
    elif count == len(required) and not any(
        r.code == "contradiction" and r.blocking for r in residuals
    ):
        global_reason, stop = "required_obligations_satisfied", "satisfied"
    exclusions: list[Exclusion] = []
    eligible: list[ActionCandidate] = []
    for action in sorted(candidates, key=lambda a: a.id):
        needed = _needed_acquisition(state, action, candidates, policy, assessment)
        reasons = _candidate_reasons(state, action, budget, policy, remaining, assessment, needed)
        if action.kind == "verify" and _gap_for_action(action, assessment.gaps) is not None:
            for dependency_reason in reasons:
                if dependency_reason.startswith(("dependency_", "prerequisite_missing")):
                    dependency_id = dependency_reason.partition(":")[2] or None
                    gaps.append(
                        Gap(
                            id=f"dependency:{action.id}:{dependency_id or 'unknown'}",
                            obligation_id=action.obligation_id,
                            scope=action.scope,
                            kind="dependency",
                            target_evidence_id=action.target_evidence_id,
                            target_digest=action.target_digest,
                            checker_id=action.checker_id,
                            dependency_id=dependency_id,
                            reason=dependency_reason,
                        )
                    )
        if global_reason:
            reasons += (global_reason,)
        if reasons:
            exclusions.append(Exclusion(action_id=action.id, reasons=reasons))
        else:
            eligible.append(action)
    selected = None
    if eligible:
        obligations = {o.id: o for o in state.obligations}

        def rank(action: ActionCandidate) -> tuple[bool, int, int, str]:
            o = obligations[action.obligation_id]
            target_gap = _gap_for_action(action, assessment.gaps)
            needed = _needed_acquisition(state, action, candidates, policy, assessment)
            if action.kind == "verify":
                relevance = 0
            elif needed:
                relevance = 1
            elif any(g.obligation_id == o.id and g.kind == "provenance" for g in assessment.gaps):
                current = _active_evidence(state, o)
                known_source = action.source is not None and any(
                    e.source == action.source for e in current
                )
                known_group = action.provenance_group is not None and any(
                    e.provenance_group == action.provenance_group for e in current
                )
                if (
                    action.source is not None
                    and action.provenance_group is not None
                    and not known_source
                    and not known_group
                ):
                    relevance = 2
                elif action.source is None or action.provenance_group is None:
                    relevance = 4
                else:
                    relevance = 5
            elif target_gap is not None:
                relevance = 2
            else:
                relevance = 6
            return not o.required, -o.priority, relevance, action.id

        selected = min(eligible, key=rank)
        reason = (
            f"Selected {selected.id} by required status, priority, evidence gap, and stable ID."
        )
    elif stop:
        reason = global_reason or stop
    else:
        budget_block = any(
            exclusion.reasons and all(reason.startswith("budget_") for reason in exclusion.reasons)
            for exclusion in exclusions
        )
        blocking_issue = any(
            r.code in ("contradiction", "check_failed") and r.blocking for r in residuals
        )
        stop = (
            "escalation_required"
            if blocking_issue
            else ("budget_exhausted" if budget_block else "blocked")
        )
        reason = "No declared candidate can safely address the remaining obligations."
    # Literal type is explicit here rather than accepting arbitrary dynamic states.
    stop_reason: (
        Literal["satisfied", "budget_exhausted", "blocked", "escalation_required"] | None
    ) = None
    if stop == "satisfied":
        stop_reason = "satisfied"
    elif stop == "budget_exhausted":
        stop_reason = "budget_exhausted"
    elif stop == "blocked":
        stop_reason = "blocked"
    elif stop == "escalation_required":
        stop_reason = "escalation_required"
    return Decision(
        action=selected,
        reason=reason,
        exclusions=tuple(exclusions),
        residuals=residuals,
        coverage=coverage,
        remaining_resources=remaining,
        stop_reason=stop_reason,
        gaps=tuple(sorted(gaps, key=lambda g: g.id)),
        selected_gap=None if selected is None else _gap_for_action(selected, tuple(gaps)),
        pending_verifications=assessment.pending,
    )


def start(
    state: State,
    action: ActionCandidate,
    attempt_id: str,
    budget: Budget,
    policy: Policy,
    *,
    retry: bool = False,
    candidates: tuple[ActionCandidate, ...] = (),
) -> State:
    """Record host intent immediately before a callback; retry requires explicit opt-in."""
    previous = next((a for a in state.attempts if a.id == attempt_id), None)
    assessment = _analyze(state, policy)
    registration = _registration(policy, action)
    basis = make_basis(state, action) if action.kind == "verify" else None
    inputs = (
        (basis.target, *basis.dependencies) if basis is not None else _input_bindings(state, action)
    )
    attempt = Attempt(
        id=attempt_id,
        action=action,
        retry=retry,
        registration=registration,
        basis=basis,
        inputs=inputs,
    )
    if previous:
        if previous != attempt:
            raise ValueError("attempt ID collision")
        raise ValueError("attempt already issued; do not execute it again")
    remaining, issues = _resource_status(state, budget)
    if issues:
        raise ValueError("resource accounting is unsafe")
    if any(a.id not in {r.attempt_id for r in state.results} for a in state.attempts):
        raise ValueError("an attempt is pending; single-writer execution requires its result")
    reasons = _candidate_reasons(
        state,
        action,
        budget,
        policy,
        remaining,
        assessment,
        needed_acquisition=_needed_acquisition(state, action, candidates, policy, assessment),
        retry=retry,
    )
    if reasons:
        raise ValueError("cannot issue action: " + ", ".join(reasons))
    return State(**{**state.model_dump(), "attempts": (*state.attempts, attempt)})


def _merge(
    existing: tuple[IdentifiedRecord, ...], added: tuple[IdentifiedRecord, ...]
) -> tuple[IdentifiedRecord, ...]:
    merged = list(existing)
    by_id = {item.id: item for item in existing}
    for item in added:
        identifier = item.id
        if identifier in by_id:
            if by_id[identifier] != item:
                raise ValueError(f"record ID collision: {identifier}")
        else:
            merged.append(item)
            by_id[identifier] = item
    return tuple(merged)


def observe(state: State, result: Result, policy: Policy | None = None) -> State:
    """Validate an issued attempt and record its result once; identical replay is idempotent."""
    previous = next((r for r in state.results if r.id == result.id), None)
    if previous:
        if previous != result:
            raise ValueError("result ID collision")
        return state
    if not any(a.id == result.attempt_id for a in state.attempts):
        raise ValueError("result refers to an unissued attempt")
    if policy is not None:
        issued = next(a for a in state.attempts if a.id == result.attempt_id)
        registration = _registration(policy, issued.action)
        if registration is None or issued.action.kind not in registration.roles:
            raise ValueError("current host policy does not authorize this receipt")
        if issued.basis is not None and not registration.allows(issued.basis):
            raise ValueError("current host policy does not authorize this checker receipt")
    values = {name: getattr(state, name) for name in State.model_fields}
    for name in ("evidence", "checks", "contradictions", "supersessions"):
        values[name] = _merge(getattr(state, name), getattr(result, name))
    values["results"] = (*state.results, result)
    return State(**values)


def resolve(state: State, event: Supersession, policy: Policy) -> State:
    """Explicit host reuse of a currently applicable dedicated resolution check."""
    existing = next((s for s in state.supersessions if s.id == event.id), None)
    if existing is not None:
        if existing != event:
            raise ValueError("supersession ID collision")
        return state
    if not _valid_resolution(state, event, policy):
        raise ValueError("resolution needs an authorized current dedicated check basis")
    values = {name: getattr(state, name) for name in State.model_fields}
    values["supersessions"] = (*state.supersessions, event)
    return State(**values)
