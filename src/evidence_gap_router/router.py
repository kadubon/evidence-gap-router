"""Pure deterministic planning and explicit single-writer state transitions."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from .models import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckResult,
    Coverage,
    Decision,
    DependencyRequirement,
    Evidence,
    EvidenceBinding,
    Exclusion,
    Gap,
    HandlerRegistration,
    IdentifiedRecord,
    Invalidation,
    Obligation,
    Policy,
    Residual,
    Resources,
    Result,
    State,
    Supersession,
    VerificationBasis,
    _contradiction_inputs_match,
    _fingerprint,
    _resolution_basis_subject_error,
)

DIMENSIONS = ("actions", "verifications", "tokens")


def _active_evidence(state: State, obligation: Obligation) -> tuple[Evidence, ...]:
    replaced = {s.target_id for s in state.supersessions if s.kind == "evidence"}
    replaced.update(i.target_id for i in state.invalidations if i.kind == "evidence")
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
    basis = VerificationBasis(
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
    if action.purpose != "content":
        subjects = state.checks if action.purpose == "check_resolution" else state.contradictions
        subject = next((r for r in subjects if r.id == action.resolution_target_id), None)
        error = _resolution_basis_subject_error(basis, subject)
        if error is not None:
            raise ValueError(error)
    return basis


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


class _Evaluation:
    """Indexes and memoized applicability scoped to one immutable state/policy evaluation."""

    def __init__(self, state: State, policy: Policy):
        self.state, self.policy = state, policy
        self.evidence = {e.id: e for e in state.evidence}
        self.obligations = {o.id: o for o in state.obligations}
        self.checks = {c.id: c for c in state.checks}
        self.contradictions = {c.id: c for c in state.contradictions}
        self.active = {e.id for o in state.obligations for e in _active_evidence(state, o)}
        self.invalid_checks = {i.target_id for i in state.invalidations if i.kind == "check"}
        self.by_target: dict[str, list[CheckResult]] = {}
        self.events: dict[str, list[Supersession]] = {}
        for check in state.checks:
            if check.basis is not None:
                self.by_target.setdefault(check.basis.target.evidence_id, []).append(check)
        for event in state.supersessions:
            if event.kind == "check" and not event.legacy:
                self.events.setdefault(event.target_id, []).append(event)
        self._check_cache: dict[str, bool] = {}
        self._target_cache: dict[str, bool] = {}
        self._resolution_cache: dict[str, bool] = {}
        self._fingerprints: dict[tuple[str, str], str | None] = {}
        self._base_cache = {c.id: self._base_check(c) for c in state.checks}
        self._check_truth: dict[str, bool | None] = {
            c.id: None if self._base_cache[c.id] else False for c in state.checks
        }
        self._target_truth: dict[str, bool | None] = {
            e.id: None if e.id in self.active else False for e in state.evidence
        }
        # Strong-Kleene information only advances from unknown to true/false.
        # Grounded alternative PASS can establish a finite proof; an unresolved
        # potential negative cannot temporarily grant PASS during a cycle.
        listeners: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for check in state.checks:
            if check.basis is not None:
                for binding in check.basis.dependencies:
                    if binding.requirement == "verified":
                        listeners.setdefault(("target", binding.evidence_id), set()).add(
                            ("check", check.id)
                        )
        for evidence in state.evidence:
            for check in self.by_target.get(evidence.id, ()):
                listeners.setdefault(("check", check.id), set()).add(("target", evidence.id))
                for event in self.events.get(check.id, ()):
                    if event.replacement_id is not None:
                        listeners.setdefault(("check", event.replacement_id), set()).add(
                            ("target", evidence.id)
                        )
        pending = deque(
            [*(("check", c.id) for c in state.checks), *(("target", e.id) for e in state.evidence)]
        )
        queued = set(pending)
        while pending:
            kind, identifier = pending.popleft()
            queued.remove((kind, identifier))
            if kind == "check":
                old = self._check_truth[identifier]
                new = self._evaluate_check_truth(self.checks[identifier])
                self._check_truth[identifier] = new
            else:
                old = self._target_truth[identifier]
                new = self._evaluate_target_truth(self.evidence[identifier])
                self._target_truth[identifier] = new
            if old != new:
                for listener in sorted(listeners.get((kind, identifier), ())):
                    if listener not in queued:
                        pending.append(listener)
                        queued.add(listener)

    def binding_active(self, binding: EvidenceBinding) -> bool:
        obligation = self.obligations.get(binding.obligation_id)
        evidence = self.evidence.get(binding.evidence_id)
        return bool(
            obligation is not None
            and obligation.scope == binding.scope
            and obligation.contract_fingerprint == binding.contract_fingerprint
            and evidence is not None
            and evidence.digest == binding.digest
            and evidence.id in self.active
        )

    def trusted_check(self, check: CheckResult) -> bool:
        if check.id not in self._check_cache:
            self._check_cache[check.id] = self._compute_check(check)
        return self._check_cache[check.id]

    def _base_check(self, check: CheckResult) -> bool:
        basis, policy = check.basis, self.policy
        if (
            basis is None
            or check.legacy
            or check.id in self.invalid_checks
            or check.withdrawn
            or check.expired
        ):
            return False
        if check.verifier_id not in policy.trusted_verifiers or not any(
            h.allows(basis) for h in policy.handlers
        ):
            return False
        if not all(self.binding_active(b) for b in (basis.target, *basis.dependencies)):
            return False
        target = self.evidence[basis.target.evidence_id]
        if policy.prohibit_self_verification and target.producer == check.verifier_id:
            return False
        if basis.purpose != "content":
            kind: Literal["check", "contradiction"] = (
                "check" if basis.purpose == "check_resolution" else "contradiction"
            )
            subjects = self.checks if kind == "check" else self.contradictions
            if (
                _resolution_basis_subject_error(
                    basis, subjects.get(basis.resolution_target_id or "")
                )
                is not None
            ):
                return False
            key = (kind, basis.resolution_target_id or "")
            if key not in self._fingerprints:
                try:
                    self._fingerprints[key] = resolution_fingerprint(self.state, kind, key[1])
                except ValueError:
                    self._fingerprints[key] = None
            if self._fingerprints[key] != basis.resolution_fingerprint:
                return False
        return True

    @staticmethod
    def _all(values: Iterable[bool | None]) -> bool | None:
        sequence = tuple(values)
        return False if False in sequence else (None if None in sequence else True)

    @staticmethod
    def _any(values: Iterable[bool | None]) -> bool | None:
        sequence = tuple(values)
        return True if True in sequence else (None if None in sequence else False)

    def _evaluate_check_truth(self, check: CheckResult) -> bool | None:
        if not self._base_cache[check.id] or check.basis is None:
            return False
        return self._all(
            self._target_truth[d.evidence_id]
            for d in check.basis.dependencies
            if d.requirement == "verified"
        )

    def _resolution_truth(self, event: Supersession) -> bool | None:
        identifier = event.replacement_id if event.kind == "check" else event.check_id
        check = self.checks.get(identifier or "")
        expected = "check_resolution" if event.kind == "check" else "contradiction_resolution"
        if (
            event.legacy
            or event.kind == "evidence"
            or check is None
            or check.status != "PASS"
            or check.basis is None
            or check.id in self.events
            or check.basis.purpose != expected
            or check.basis.resolution_target_id != event.target_id
        ):
            return False
        return self._check_truth[check.id]

    def _effective_truth(self, check: CheckResult) -> bool | None:
        truth = self._check_truth[check.id]
        if check.legacy and check.basis is None and check.status in ("FAIL", "UNKNOWN"):
            truth = check.id not in self.invalid_checks
        events = self.events.get(check.id, ())
        if not events:
            return truth
        replaced = (
            True if check.status == "PASS" else self._any(self._resolution_truth(s) for s in events)
        )
        return self._all((truth, None if replaced is None else not replaced))

    def _evaluate_target_truth(self, evidence: Evidence) -> bool | None:
        if evidence.id not in self.active:
            return False
        checks = [
            c
            for c in self.by_target.get(evidence.id, ())
            if c.basis is not None and c.basis.purpose in ("content", "check_resolution")
        ]
        checks.extend(
            c
            for c in self.state.checks
            if c.legacy
            and c.basis is None
            and c.status in ("FAIL", "UNKNOWN")
            and (c.obligation_id, c.scope, c.target_digest)
            == (evidence.obligation_id, evidence.scope, evidence.digest)
        )
        required = self.obligations[evidence.obligation_id].required_verifiers
        passes = [c for c in checks if c.status == "PASS"]
        support = (
            self._all(
                self._any(self._effective_truth(c) for c in passes if c.verifier_id == checker)
                for checker in required
            )
            if required
            else self._any(self._effective_truth(c) for c in passes)
        )
        negatives = self._any(self._effective_truth(c) for c in checks if c.status != "PASS")
        return self._all((support, None if negatives is None else not negatives))

    def _compute_check(self, check: CheckResult) -> bool:
        return self._check_truth[check.id] is True

    def valid_resolution(self, event: Supersession) -> bool:
        if event.id not in self._resolution_cache:
            self._resolution_cache[event.id] = self._resolution_truth(event) is True
        return self._resolution_cache[event.id]

    def target_checks(self, evidence: Evidence) -> tuple[CheckResult, ...]:
        current: list[CheckResult] = []
        # Unassessed legacy negatives remain conservative digest-level issues.
        checks = [
            *self.by_target.get(evidence.id, ()),
            *(
                c
                for c in self.state.checks
                if c.legacy and c.basis is None and c.status in ("FAIL", "UNKNOWN")
            ),
        ]
        for check in checks:
            if (check.obligation_id, check.scope, check.target_digest) != (
                evidence.obligation_id,
                evidence.scope,
                evidence.digest,
            ) or check.id in self.invalid_checks:
                continue
            events = self.events.get(check.id, ())
            if events and (check.status == "PASS" or any(self.valid_resolution(s) for s in events)):
                continue
            if check.legacy and check.status in ("FAIL", "UNKNOWN"):
                current.append(check)
            elif (
                check.basis is not None
                and check.basis.purpose in ("content", "check_resolution")
                and self.trusted_check(check)
            ):
                current.append(check)
        return tuple(current)

    def target_verified(self, identifier: str) -> bool:
        return self._target_truth[identifier] is True

    def indeterminate_negatives(self, evidence: Evidence) -> tuple[CheckResult, ...]:
        return tuple(
            c
            for c in self.by_target.get(evidence.id, ())
            if c.status != "PASS"
            and c.basis is not None
            and c.basis.purpose in ("content", "check_resolution")
            and self._effective_truth(c) is None
        )


def _trusted_check(
    check: CheckResult, state: State, policy: Policy, visiting: frozenset[str] = frozenset()
) -> bool:
    return check.id not in visiting and _Evaluation(state, policy).trusted_check(check)


def _valid_resolution(
    state: State, event: Supersession, policy: Policy, visiting: frozenset[str] = frozenset()
) -> bool:
    return (event.replacement_id or event.check_id) not in visiting and _Evaluation(
        state, policy
    ).valid_resolution(event)


def _replaced_checks(
    state: State, policy: Policy, visiting: frozenset[str] = frozenset()
) -> set[str]:
    evaluation = _Evaluation(state, policy)
    return {
        s.target_id
        for s in state.supersessions
        if s.kind == "check"
        and not s.legacy
        and (evaluation.checks[s.target_id].status == "PASS" or evaluation.valid_resolution(s))
    }


def _target_checks(
    state: State, policy: Policy, evidence: Evidence, visiting: frozenset[str] = frozenset()
) -> tuple[CheckResult, ...]:
    return _Evaluation(state, policy).target_checks(evidence)


def _target_verified(
    state: State, policy: Policy, identifier: str, visiting: frozenset[str] = frozenset()
) -> bool:
    return _Evaluation(state, policy).target_verified(identifier)


@dataclass(frozen=True)
class _Assessment:
    residuals: tuple[Residual, ...]
    satisfied: frozenset[str]
    gaps: tuple[Gap, ...]
    pending: int


def _analyze(state: State, policy: Policy, evaluation: _Evaluation | None = None) -> _Assessment:
    evaluation = evaluation or _Evaluation(state, policy)
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
            target_checks = evaluation.target_checks(evidence)
            failures = [c for c in target_checks if c.status == "FAIL"]
            unknown_checks = [c for c in target_checks if c.status == "UNKNOWN"]
            indeterminate = evaluation.indeterminate_negatives(evidence)
            # Duplicate support never increases coverage, but its actual negative
            # check is still a current issue on that exact alias ID and basis.
            canonical = evidence.id in canonical_ids
            if not canonical and not failures and not unknown_checks and not indeterminate:
                continue
            passes = {
                c.verifier_id
                for c in target_checks
                if c.status == "PASS"
                and c.basis is not None
                and c.basis.purpose in ("content", "check_resolution")
            }
            required = set(obligation.required_verifiers) if canonical else set()
            passed = (required.issubset(passes) if required else bool(passes)) and (
                evaluation.target_verified(evidence.id) if canonical else not indeterminate
            )
            if indeterminate:
                add(
                    "dependency_indeterminate",
                    "Potential negative applicability has no finite grounded dependency proof.",
                    (c.id for c in indeterminate),
                )
                gaps.append(
                    Gap(
                        id=f"dependency:indeterminate:{evidence.id}",
                        obligation_id=obligation.id,
                        scope=obligation.scope,
                        kind="dependency",
                        target_evidence_id=evidence.id,
                        target_digest=evidence.digest,
                        record_ids=tuple(c.id for c in indeterminate),
                        reason="Potential negative applicability has an unresolved cycle.",
                    )
                )
                pending += len(indeterminate)
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
            resolved = any(evaluation.valid_resolution(s) for s in resolutions)
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
            if e.obligation_id == obligation.id and e.id not in evaluation.active
        ]
        if inactive:
            add(
                "ineligible_evidence",
                "Evidence excluded by supersession, host invalidation, flags, or scope.",
                inactive,
                not bool(current),
            )
        for event in state.invalidations:
            if event.obligation_id == obligation.id:
                add(
                    f"host_invalidated_{event.kind}",
                    event.reason,
                    (event.target_id, event.id),
                    False,
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
    evaluation: _Evaluation | None = None,
) -> tuple[str, ...]:
    evaluation = evaluation or _Evaluation(state, policy)
    reasons: list[str] = []
    obligations = {o.id: o for o in state.obligations}
    obligation = obligations.get(action.obligation_id)
    if obligation is None:
        return ("unknown_obligation",)
    if action.scope != obligation.scope:
        reasons.append("scope_mismatch")
    if action.obligation_id in assessment.satisfied and not needed_acquisition:
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
        if binding.requirement != "exists" and not evaluation.binding_active(binding):
            reasons.append(f"dependency_inactive:{binding.evidence_id}")
        elif binding.requirement == "verified" and not evaluation.target_verified(
            binding.evidence_id
        ):
            reasons.append(f"dependency_unverified:{binding.evidence_id}")
    if action.kind == "verify":
        try:
            basis = make_basis(state, action)
        except ValueError as error:
            basis = None
            reasons.append(str(error))
        if basis is not None:
            if not evaluation.binding_active(basis.target):
                reasons.append("target_digest_missing_or_stale")
            target = evaluation.evidence[basis.target.evidence_id]
            if policy.prohibit_self_verification and target.producer == basis.checker_id:
                reasons.append("self_verification_forbidden")
            if registration is not None and not registration.allows(basis):
                reasons.append("checker_permission_forbidden")
        if action.checker_id not in policy.trusted_verifiers:
            reasons.append("verifier_unavailable")
        if _gap_for_action(action, assessment.gaps) is None and not needed_acquisition:
            reasons.append("target_already_verified_or_no_matching_gap")
        elif (
            needed_acquisition
            and action.purpose == "content"
            and action.target_evidence_id in evaluation.evidence
            and evaluation.target_verified(action.target_evidence_id)
        ):
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


class _HelperGraph:
    """Evaluation-local monotone AND/OR rules; each activated node emits once."""

    def __init__(self) -> None:
        self.rules: list[tuple[int, tuple[int, ...]]] = []
        self.by_head: list[list[int]] = []
        self.listeners: list[list[int]] = []

    def node(self) -> int:
        identifier = len(self.by_head)
        self.by_head.append([])
        self.listeners.append([])
        return identifier

    def rule(self, head: int, children: Iterable[int]) -> None:
        inputs = tuple(dict.fromkeys(children))
        index = len(self.rules)
        self.rules.append((head, inputs))
        self.by_head[head].append(index)
        for child in inputs:
            self.listeners[child].append(index)

    def choice(self, alternatives: Iterable[int], *, seed: bool = False) -> int:
        node = self.node()
        if seed:
            self.rule(node, ())
        for alternative in alternatives:
            self.rule(node, (alternative,))
        return node

    def _consume_edge(self, rule: int, pending: list[int]) -> int | None:
        pending[rule] -= 1
        return self.rules[rule][0] if pending[rule] == 0 else None

    def solve(self, blocked: int) -> list[bool]:
        """Least grounded closure excluding the consuming root's own future result."""
        truth = [False] * len(self.by_head)
        pending = [len(children) for _, children in self.rules]
        queue: deque[int] = deque()
        for head, children in self.rules:
            if not children and head != blocked and not truth[head]:
                truth[head] = True
                queue.append(head)
        while queue:
            for rule in self.listeners[queue.popleft()]:
                activated = self._consume_edge(rule, pending)
                if activated is not None and activated != blocked and not truth[activated]:
                    truth[activated] = True
                    queue.append(activated)
        return truth

    def needed(self, inputs: tuple[int, ...], truth: list[bool]) -> set[int]:
        """Retain every grounded alternative without enumerating proof paths."""
        seen: set[int] = set()
        queue = deque(inputs)
        while queue:
            node = queue.popleft()
            if node in seen or not truth[node]:
                continue
            seen.add(node)
            for index in self.by_head[node]:
                children = self.rules[index][1]
                if all(truth[child] for child in children):
                    queue.extend(children)
        return seen


def _helper_actions(
    state: State,
    candidates: tuple[ActionCandidate, ...],
    budget: Budget,
    policy: Policy,
    assessment: _Assessment,
    remaining: Resources,
    evaluation: _Evaluation,
) -> frozenset[str]:
    """Grounded finite helper closure, shared rules and linear work per consuming root."""
    roots = tuple(
        action
        for action in candidates
        if action.kind == "verify"
        and (action.dependencies or action.requires_evidence_ids)
        and (gap := _gap_for_action(action, assessment.gaps)) is not None
        and (obligation := evaluation.obligations.get(action.obligation_id)) is not None
        and (obligation.required or gap.kind == "contradiction")
    )
    if not roots:
        return frozenset()
    by_produced: dict[str, list[ActionCandidate]] = {}
    by_target: dict[str, list[ActionCandidate]] = {}
    attempted = {attempt.action.id for attempt in state.attempts}
    registrations = {
        handler.handler_id: handler
        for handler in policy.handlers
        if (policy.available_handlers is None or handler.handler_id in policy.available_handlers)
        and (not policy.executable_handlers or handler.handler_id in policy.executable_handlers)
    }
    conflicts = {conflict.id: conflict for conflict in state.contradictions}
    for action in candidates:
        if action.kind == "verify" and action.target_evidence_id is not None:
            by_target.setdefault(action.target_evidence_id, []).append(action)
        elif action.produces_evidence_id is not None:
            by_produced.setdefault(action.produces_evidence_id, []).append(action)

    def authorized(action: ActionCandidate) -> bool:
        obligation = evaluation.obligations.get(action.obligation_id)
        registration = registrations.get(action.handler_id)
        if (
            obligation is None
            or obligation.scope != action.scope
            or registration is None
            or action.kind not in registration.roles
            or action.id in attempted
        ):
            return False
        for name in DIMENSIONS:
            upper, left = getattr(action.resources, name), getattr(remaining, name)
            if getattr(budget.limits, name) is not None and (upper is None or upper > (left or 0)):
                return False
        if action.kind == "verify":
            if any(
                d.evidence_id == action.target_evidence_id and d.requirement == "verified"
                for d in action.dependencies
            ):
                return False
            if action.checker_id not in policy.trusted_verifiers or not any(
                p.checker_id == action.checker_id
                and p.revision == action.checker_revision
                and action.purpose in p.purposes
                for p in registration.checkers
            ):
                return False
            target = evaluation.evidence.get(action.target_evidence_id or "")
            if target is not None and (
                (target.obligation_id, target.scope, target.digest)
                != (action.obligation_id, action.scope, action.target_digest)
                or target.id not in evaluation.active
                or policy.prohibit_self_verification
                and target.producer == action.checker_id
            ):
                return False
            if action.purpose == "check_resolution":
                old = evaluation.checks.get(action.resolution_target_id or "")
                if (
                    old is None
                    or old.basis is None
                    or old.basis.target.evidence_id != action.target_evidence_id
                ):
                    return False
            elif action.purpose == "contradiction_resolution":
                conflict = conflicts.get(action.resolution_target_id or "")
                if conflict is None or not _contradiction_inputs_match(
                    conflict,
                    action.target_evidence_id or "",
                    (
                        action.target_evidence_id or "",
                        *(d.evidence_id for d in action.dependencies),
                        *action.requires_evidence_ids,
                    ),
                ):
                    return False
        return True

    graph = _HelperGraph()
    action_nodes = {action.id: graph.node() for action in candidates}
    authorized_ids = {action.id for action in candidates if authorized(action)}
    requirements: dict[DependencyRequirement, int] = {}
    pending_requirements: deque[DependencyRequirement] = deque()

    def material_node(requirement: DependencyRequirement) -> int:
        if requirement not in requirements:
            requirements[requirement] = graph.node()
            pending_requirements.append(requirement)
        return requirements[requirement]

    def expand_action(action: ActionCandidate) -> None:
        if action.id not in authorized_ids:
            return
        declared = {d.evidence_id for d in action.dependencies}
        inputs = list(action.dependencies)
        for identifier in action.requires_evidence_ids:
            if identifier in declared:
                continue
            evidence = evaluation.evidence.get(identifier)
            if evidence is None:
                # Missing legacy prerequisites declare no owner/scope.
                return
            inputs.append(
                DependencyRequirement(
                    evidence_id=identifier,
                    obligation_id=evidence.obligation_id,
                    scope=evidence.scope,
                )
            )
        graph.rule(action_nodes[action.id], (material_node(d) for d in inputs))

    future_checkers = {
        permission.checker_id
        for handler in registrations.values()
        if "verify" in handler.roles
        for permission in handler.checkers
        if "content" in permission.purposes and permission.checker_id in policy.trusted_verifiers
    }

    def expand_material(requirement: DependencyRequirement) -> None:
        node = requirements[requirement]
        obligation = evaluation.obligations.get(requirement.obligation_id)
        if (
            obligation is None
            or obligation.scope != requirement.scope
            or (
                requirement.contract_fingerprint is not None
                and requirement.contract_fingerprint != obligation.contract_fingerprint
            )
        ):
            return
        evidence = evaluation.evidence.get(requirement.evidence_id)
        inputs: list[int] = []
        if evidence is None:
            alternatives = [
                action_nodes[producer.id]
                for producer in by_produced.get(requirement.evidence_id, ())
                if producer.id in authorized_ids
                and (producer.obligation_id, producer.scope)
                == (requirement.obligation_id, requirement.scope)
            ]
            if not alternatives:
                return
            inputs.append(graph.choice(alternatives))
        elif (
            (evidence.obligation_id, evidence.scope)
            != (requirement.obligation_id, requirement.scope)
            or requirement.digest is not None
            and evidence.digest != requirement.digest
            or requirement.requirement != "exists"
            and evidence.id not in evaluation.active
        ):
            return
        if requirement.requirement != "verified" or (
            evidence is not None and evaluation.target_verified(evidence.id)
        ):
            graph.rule(node, inputs)
            return
        current = () if evidence is None else evaluation.target_checks(evidence)

        def compatible(candidate: ActionCandidate) -> bool:
            return (
                (candidate.obligation_id, candidate.scope)
                == (requirement.obligation_id, requirement.scope)
                and (requirement.digest is None or candidate.target_digest == requirement.digest)
                and (evidence is None or candidate.target_digest == evidence.digest)
            )

        for negative in (c for c in current if c.status in ("FAIL", "UNKNOWN")):
            alternatives = [
                action_nodes[candidate.id]
                for candidate in by_target.get(requirement.evidence_id, ())
                if candidate.id in authorized_ids
                and candidate.purpose == "check_resolution"
                and compatible(candidate)
                and candidate.resolution_target_id == negative.id
            ]
            inputs.append(graph.choice(alternatives))
        passes = {c.verifier_id for c in current if c.status == "PASS"}
        checkers: tuple[str | None, ...] = (
            tuple(checker for checker in obligation.required_verifiers if checker not in passes)
            if obligation.required_verifiers
            else (() if passes else (None,))
        )
        for checker in checkers:
            alternatives = [
                action_nodes[candidate.id]
                for candidate in by_target.get(requirement.evidence_id, ())
                if candidate.id in authorized_ids
                and candidate.purpose in ("content", "check_resolution")
                and compatible(candidate)
                and (checker is None or candidate.checker_id == checker)
            ]
            # Unknown-digest acquisition may bootstrap the next concrete factory
            # only with currently available registered content-check authority.
            dynamic = evidence is None and (
                checker in future_checkers if checker is not None else bool(future_checkers)
            )
            inputs.append(graph.choice(alternatives, seed=dynamic))
        graph.rule(node, inputs)

    for action in candidates:
        expand_action(action)
    while pending_requirements:
        expand_material(pending_requirements.popleft())
    helpers: set[str] = set()
    by_node = {node: identifier for identifier, node in action_nodes.items()}
    for action in roots:
        root = action_nodes[action.id]
        rules = graph.by_head[root]
        if not rules:
            continue
        inputs = graph.rules[rules[0]][1]
        truth = graph.solve(root)
        if all(truth[node] for node in inputs):
            helpers.update(by_node[node] for node in graph.needed(inputs, truth) if node in by_node)
    return frozenset(helpers)


def feasible_actions(
    state: State, candidates: tuple[ActionCandidate, ...], budget: Budget, policy: Policy
) -> tuple[ActionCandidate, ...]:
    """Safety-only feasible pool in input order; applies no routing preference."""
    if len({a.id for a in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    evaluation = _Evaluation(state, policy)
    assessment = _analyze(state, policy, evaluation)
    remaining, issues = _resource_status(state, budget)
    if issues or any(a.id not in {r.attempt_id for r in state.results} for a in state.attempts):
        return ()
    if all(not o.required or o.id in assessment.satisfied for o in state.obligations) and not any(
        r.code == "contradiction" and r.blocking for r in assessment.residuals
    ):
        return ()
    helpers = _helper_actions(state, candidates, budget, policy, assessment, remaining, evaluation)
    return tuple(
        a
        for a in candidates
        if not _candidate_reasons(
            state, a, budget, policy, remaining, assessment, a.id in helpers, evaluation=evaluation
        )
    )


def _needed_helper_actions(
    state: State, candidates: tuple[ActionCandidate, ...], budget: Budget, policy: Policy
) -> frozenset[str]:
    """Shared helper context for the runner's exact-binding progress accounting."""
    evaluation = _Evaluation(state, policy)
    assessment = _analyze(state, policy, evaluation)
    remaining, issues = _resource_status(state, budget)
    if issues or any(a.id not in {r.attempt_id for r in state.results} for a in state.attempts):
        return frozenset()
    return _helper_actions(state, candidates, budget, policy, assessment, remaining, evaluation)


def _plan(
    state: State,
    candidates: tuple[ActionCandidate, ...],
    budget: Budget,
    policy: Policy,
    *,
    selector: Callable[
        [State, tuple[ActionCandidate, ...], tuple[ActionCandidate, ...]], ActionCandidate
    ]
    | None = None,
) -> Decision:
    """Prepare one current evaluation; optionally replace only eligible-action ranking."""
    if len({a.id for a in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    evaluation = _Evaluation(state, policy)
    assessment = _analyze(state, policy, evaluation)
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
    helpers = (
        frozenset()
        if global_reason
        else _helper_actions(state, candidates, budget, policy, assessment, remaining, evaluation)
    )
    exclusions: list[Exclusion] = []
    eligible: list[ActionCandidate] = []
    for action in sorted(candidates, key=lambda a: a.id):
        needed = action.id in helpers
        reasons = _candidate_reasons(
            state, action, budget, policy, remaining, assessment, needed, evaluation=evaluation
        )
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
            needed = action.id in helpers
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

        if selector is None:
            selected = min(eligible, key=rank)
            reason = (
                f"Selected {selected.id} by required status, priority, evidence gap, and stable ID."
            )
        else:
            selected = selector(state, candidates, tuple(eligible))
            if not isinstance(selected, ActionCandidate) or selected not in eligible:
                raise ValueError("selector must return an unchanged currently eligible action")
            reason = f"Host selector ranked eligible action {selected.id}; current gates retained."
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


def plan(
    state: State, candidates: tuple[ActionCandidate, ...], budget: Budget, policy: Policy
) -> Decision:
    """Recommend at most one declared action without mutating state or consuming budget."""
    return _plan(state, candidates, budget, policy)


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
    if len({a.id for a in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    if any(a.id == action.id and a != action for a in candidates):
        raise ValueError("candidate action ID collision")
    previous = next((a for a in state.attempts if a.id == attempt_id), None)
    evaluation = _Evaluation(state, policy)
    assessment = _analyze(state, policy, evaluation)
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
    helpers = _helper_actions(state, candidates, budget, policy, assessment, remaining, evaluation)
    reasons = _candidate_reasons(
        state,
        action,
        budget,
        policy,
        remaining,
        assessment,
        needed_acquisition=action.id in helpers,
        retry=retry,
        evaluation=evaluation,
    )
    if all(not o.required or o.id in assessment.satisfied for o in state.obligations) and not any(
        r.code == "contradiction" and r.blocking for r in assessment.residuals
    ):
        reasons += ("required_obligations_satisfied",)
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
    issued = next(a for a in state.attempts if a.id == result.attempt_id)
    if (
        issued.basis is not None
        and issued.basis.purpose != "content"
        and (result.checks or result.supersessions)
    ):
        subjects = (
            state.checks if issued.basis.purpose == "check_resolution" else state.contradictions
        )
        subject = next((r for r in subjects if r.id == issued.basis.resolution_target_id), None)
        error = _resolution_basis_subject_error(issued.basis, subject)
        if error is not None:
            raise ValueError(error)
    if policy is not None:
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
    evaluation = _Evaluation(state, policy)
    if any(
        s.kind == event.kind and s.target_id == event.target_id and evaluation.valid_resolution(s)
        for s in state.supersessions
    ):
        raise ValueError("resolution already has current active grounds")
    values = {name: getattr(state, name) for name in State.model_fields}
    values["supersessions"] = (*state.supersessions, event)
    return State(**values)


def invalidate(state: State, event: Invalidation) -> State:
    """Append a host invalidation without altering the original record or receipt."""
    previous = next((i for i in state.invalidations if i.id == event.id), None)
    if previous is not None:
        if previous != event:
            raise ValueError("invalidation ID collision")
        return state
    values = {name: getattr(state, name) for name in State.model_fields}
    values["invalidations"] = (*state.invalidations, event)
    return State(**values)
