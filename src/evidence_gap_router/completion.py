"""Pure finite host-contract assessment. No retrieval, model calls or confidence scores."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from .models import (
    Budget,
    CheckerPermission,
    CheckResult,
    CompletionAssessment,
    CompletionContract,
    DependencyRequirement,
    EvidenceBinding,
    Policy,
    Residual,
    Resources,
    State,
)

if TYPE_CHECKING:
    from .router import _Evaluation


def current_contract(state: State, obligation_id: str) -> CompletionContract | None:
    return next(
        (c for c in reversed(state.completion_contracts) if c.obligation_id == obligation_id), None
    )


def declare_completion(state: State, contract: CompletionContract) -> State:
    """Append a host declaration. Callback receipts have no contract mutation channel."""
    old = next((c for c in state.completion_contracts if c.id == contract.id), None)
    if old is not None:
        if old != contract:
            raise ValueError("completion contract event ID collision")
        return state
    return State(
        **{**state.model_dump(), "completion_contracts": (*state.completion_contracts, contract)}
    )


def requirement_matches(
    requirement: DependencyRequirement, binding: EvidenceBinding, evaluation: _Evaluation
) -> bool:
    return (
        (requirement.evidence_id, requirement.obligation_id, requirement.scope)
        == (binding.evidence_id, binding.obligation_id, binding.scope)
        and (requirement.digest is None or requirement.digest == binding.digest)
        and (
            requirement.contract_fingerprint is None
            or requirement.contract_fingerprint == binding.contract_fingerprint
        )
        and evaluation.binding_active(binding)
        and (
            requirement.requirement != "verified" or evaluation.target_verified(binding.evidence_id)
        )
    )


def _issued_profile(
    state: State, check: CheckResult, evaluation: _Evaluation | None = None
) -> CheckerPermission | None:
    """A seeded observation cannot invent a completed issued invocation."""
    if evaluation is not None:
        attempt = evaluation.check_attempts.get(check.id)
        if attempt is None:
            return None
    else:
        receipt = next((r for r in state.results if check in r.checks), None)
        if receipt is None or receipt.legacy or receipt.status != "completed":
            return None
        attempt = next(a for a in state.attempts if a.id == receipt.attempt_id)
    if (
        attempt.legacy
        or attempt.action.advisory
        or attempt.registration is None
        or check.basis is None
    ):
        return None
    return next(
        (p for p in attempt.registration.checkers if p.admits_completion(check.basis)), None
    )


def _current_profile(
    state: State, check: CheckResult, policy: Policy, evaluation: _Evaluation | None = None
) -> CheckerPermission | None:
    issued = _issued_profile(state, check, evaluation)
    if issued is None or check.basis is None:
        return None
    return next(
        (
            p
            for h in policy.handlers
            if "verify" in h.roles
            for p in h.checkers
            if p.model_dump(exclude={"method"}) == issued.model_dump(exclude={"method"})
            and p.admits_completion(check.basis)
        ),
        None,
    )


def _used_bindings(
    state: State, bindings: tuple[EvidenceBinding, ...], evaluation: _Evaluation
) -> tuple[EvidenceBinding, ...]:
    """Follow completed producer receipts once; mere state/pending input is not usage."""
    producers = evaluation.producer_inputs
    seen: dict[str, EvidenceBinding] = {}
    queue = deque(bindings)
    while queue:
        binding = queue.popleft()
        if binding.evidence_id in seen:
            continue
        seen[binding.evidence_id] = binding
        queue.extend(producers.get(binding.evidence_id, ()))
    return tuple(seen.values())


def _declared_groups(profiles: list[CheckerPermission]) -> set[str]:
    by_checker: dict[tuple[str, str], set[str | None]] = {}
    for profile in profiles:
        by_checker.setdefault((profile.checker_id, profile.revision), set()).add(
            profile.correlation_group
        )
    return {
        g for values in by_checker.values() if len(values) == 1 for g in values if g is not None
    }


def assess_completion(
    state: State,
    policy: Policy,
    budget: Budget | None = None,
    *,
    _evaluation: _Evaluation | None = None,
) -> tuple[CompletionAssessment, ...]:
    """Evaluate current finite completion without modifying observations or consuming costs."""
    from .router import _Evaluation, _resource_status, evidence_binding

    evaluation = _evaluation or _Evaluation(state, policy)
    if budget in evaluation.completion_cache:
        return evaluation.completion_cache[budget]
    _, unsafe = _resource_status(state, budget or Budget(limits=Resources()))
    unsafe += tuple(
        Residual(
            obligation_id=r.obligation_id,
            code="unknown_resource",
            reason="Completion cannot assert known execution cost for an unmeasured dimension.",
            record_ids=(r.id, name),
        )
        for r in state.results
        for name in ("actions", "verifications", "tokens")
        if getattr(r.actual_resources, name) is None
    )
    pending = tuple(
        a.id for a in state.attempts if not any(r.attempt_id == a.id for r in state.results)
    )
    assessments = []
    for obligation in state.obligations:
        contract = current_contract(state, obligation.id)
        issues: list[Residual] = []

        def issue(
            code: str,
            reason: str,
            *ids: str,
            blocking: bool = True,
            collected: list[Residual] = issues,
            owner_id: str = obligation.id,
        ) -> None:
            collected.append(
                Residual(
                    obligation_id=owner_id,
                    code=code,
                    reason=reason,
                    record_ids=ids,
                    blocking=blocking,
                )
            )

        if contract is None:
            issue("missing_completion_contract", "Host must declare the finite completion scope.")
            assessments.append(
                CompletionAssessment(
                    obligation_id=obligation.id, scope=obligation.scope, residuals=tuple(issues)
                )
            )
            continue
        if (contract.scope, contract.obligation_fingerprint) != (
            obligation.scope,
            obligation.contract_fingerprint,
        ):
            issue(
                "completion_contract_stale",
                "Host contract scope/obligation revision is stale.",
                contract.id,
            )
        if contract.declared_scope == "unspecified":
            issue(
                "scope_unspecified", "Declare a finite catalogue or reasoned not_applicable scope."
            )
        elif contract.declared_scope == "not_applicable":
            if contract.scope_reason is None or contract.materials:
                issue(
                    "scope_not_applicable_unjustified",
                    "Fixed scope needs a reason and no retrieval conditions.",
                )
        elif (
            not contract.materials
            or contract.catalogue_id is None
            or contract.catalogue_revision is None
        ):
            issue(
                "coverage_contract_incomplete",
                "Finite coverage needs material conditions and catalogue identity/revision.",
            )
        target = evaluation.evidence.get(contract.target.evidence_id)
        target_ok = False
        if target is not None:
            target_ok = requirement_matches(
                contract.target, evidence_binding(state, target.id), evaluation
            )
        if not target_ok:
            issue(
                "completion_target_missing_or_stale",
                "Acquire the exact current target.",
                contract.target.evidence_id,
            )
        observations = () if target is None else evaluation.target_checks(target)
        closing: list[CheckResult] = []
        advisory: list[str] = []
        profiles: dict[str, CheckerPermission] = {}
        for check in observations:
            basis = check.basis
            profile = _current_profile(state, check, policy, evaluation)
            if (
                target_ok
                and basis is not None
                and profile is not None
                and basis.completion_fingerprint == contract.fingerprint
                and any(
                    q.kind == basis.check_kind
                    and (not q.checker_ids or check.verifier_id in q.checker_ids)
                    for q in contract.checks
                )
            ):
                closing.append(check)
                profiles[check.id] = profile
            else:
                advisory.append(check.id)
                issue(
                    "advisory_check",
                    "Observation has no current issued completion authority/basis.",
                    check.id,
                    blocking=False,
                )
                if contract.advisory_negatives_block and check.status != "PASS":
                    issue(
                        "advisory_negative_blocking",
                        "Host declared this advisory negative blocking.",
                        check.id,
                    )
        # Preserve and expose otherwise inapplicable/seeded observations too.
        for check in state.checks:
            if (
                check.obligation_id == obligation.id
                and check not in closing
                and check.id not in advisory
            ):
                advisory.append(check.id)
                issue(
                    "inapplicable_observation",
                    "Retained observation is not a current completion ground.",
                    check.id,
                    blocking=False,
                )
        used_by_check = {
            c.id: _used_bindings(state, (c.basis.target, *c.basis.dependencies), evaluation)
            for c in closing
            if c.basis is not None
        }

        def covers(
            check: CheckResult,
            used: dict[str, tuple[EvidenceBinding, ...]] = used_by_check,
            current: CompletionContract = contract,
        ) -> bool:
            return all(evaluation.binding_active(b) for b in used[check.id]) and all(
                any(requirement_matches(r, b, evaluation) for r in m.any_of for b in used[check.id])
                for m in current.materials
            )

        covered = [c for c in closing if covers(c)]
        # Existing explicit support quotas apply to the finite used basis,
        # rather than every unrelated/alternative record in the state.
        supported = []
        for check in covered:
            records = [evaluation.evidence[b.evidence_id] for b in used_by_check[check.id]]
            # Same-content reposts with a shared source or group are one contribution,
            # including transitive alias chains; source labels cannot inflate quotas.
            parents = list(range(len(records)))

            def root(index: int, links: list[int] = parents) -> int:
                while links[index] != index:
                    index = links[index]
                return index

            for index, record in enumerate(records):
                for earlier_index, earlier in enumerate(records[:index]):
                    if record.digest == earlier.digest and (
                        record.source == earlier.source
                        or record.provenance_group == earlier.provenance_group
                    ):
                        parents[root(index)] = root(earlier_index)
            distinct = {root(index) for index in range(len(records))}
            by_source: dict[str, set[str]] = {}
            for record in records:
                if record.source is not None and record.provenance_group is not None:
                    by_source.setdefault(record.source, set()).add(record.provenance_group)
            groups = {g for values in by_source.values() for g in values}
            if (
                len(distinct) >= obligation.min_evidence
                and len(groups) >= obligation.min_provenance_groups
                and all(len(values) == 1 for values in by_source.values())
            ):
                supported.append(check)
        if covered and not supported:
            issue(
                "insufficient_declared_support",
                "Used basis does not meet explicit evidence/provenance quotas.",
            )
        covered = supported
        missing = []
        for material in contract.materials:
            if not any(
                any(
                    requirement_matches(r, b, evaluation)
                    for r in material.any_of
                    for b in used_by_check[c.id]
                )
                for c in closing
            ):
                missing.append(material)
                present = any(r.evidence_id in evaluation.active for r in material.any_of)
                issue(
                    "material_not_used" if present else "required_material_missing",
                    "Reintegrate/recheck with the declared input."
                    if present
                    else "Acquire a declared exact material alternative.",
                    material.id,
                    *(r.evidence_id for r in material.any_of),
                )
        for requirement in contract.checks:
            passes = [
                c
                for c in covered
                if c.status == "PASS"
                and c.basis is not None
                and c.basis.check_kind == requirement.kind
                and (not requirement.checker_ids or c.verifier_id in requirement.checker_ids)
            ]
            checker_ids = {c.verifier_id for c in passes}
            declared_groups = _declared_groups([profiles[c.id] for c in passes])
            if (
                len(checker_ids) < requirement.min_checks
                or len(declared_groups) < requirement.min_declared_groups
            ):
                issue(
                    "completion_check_missing",
                    f"Need kind={requirement.kind}, checks={requirement.min_checks}, "
                    f"declared_groups={requirement.min_declared_groups}.",
                    requirement.id,
                    *requirement.checker_ids,
                )
        for check in closing:
            if check.status != "PASS":
                issue(
                    "check_failed" if check.status == "FAIL" else "check_unknown",
                    "Dedicated current resolution is required; "
                    "majority PASS cannot resolve this observation.",
                    check.id,
                )
        if target is not None:
            for check in evaluation.indeterminate_negatives(target):
                if (
                    _current_profile(state, check, policy, evaluation) is not None
                    and check.basis is not None
                    and check.basis.completion_fingerprint == contract.fingerprint
                ):
                    issue(
                        "dependency_indeterminate",
                        "Negative applicability lacks a grounded finite proof.",
                        check.id,
                    )
        for conflict in state.contradictions:
            if (
                conflict.obligation_id == obligation.id
                and conflict.blocking
                and not any(
                    s.kind == "contradiction"
                    and s.target_id == conflict.id
                    and evaluation.valid_resolution(s)
                    for s in state.supersessions
                )
            ):
                issue("contradiction", conflict.reason, conflict.id)
        issues.extend(unsafe)
        if pending:
            issue(
                "attempt_pending",
                "An issued callback lacks a receipt; reconcile execution.",
                *pending,
            )
        assessments.append(
            CompletionAssessment(
                obligation_id=obligation.id,
                scope=obligation.scope,
                contract_id=contract.id,
                contract_revision=contract.revision,
                contract_fingerprint=contract.fingerprint,
                provisional_answer=target_ok,
                coverage_complete=bool(covered) and not missing,
                finite_complete=not any(r.blocking for r in issues),
                closing_check_ids=tuple(c.id for c in closing),
                advisory_check_ids=tuple(advisory),
                residuals=tuple(issues),
                missing_materials=tuple(missing),
            )
        )
    result = tuple(assessments)
    evaluation.completion_cache[budget] = result
    return result


def _progress_fingerprint(state: State, policy: Policy, budget: Budget) -> str:
    """Required-condition progress; aliases and unrelated optional output are not progress."""
    from .models import _fingerprint
    from .router import _Evaluation, evidence_binding

    evaluation = _Evaluation(state, policy)
    values = []
    for result in assess_completion(state, policy, budget, _evaluation=evaluation):
        obligation = evaluation.obligations[result.obligation_id]
        contract = current_contract(state, result.obligation_id)
        if not obligation.required or contract is None:
            continue
        requirements = (contract.target, *(r for m in contract.materials for r in m.any_of))
        available = sorted(
            (r.evidence_id, evaluation.evidence[r.evidence_id].digest)
            for r in requirements
            if r.evidence_id in evaluation.evidence
            and requirement_matches(r, evidence_binding(state, r.evidence_id), evaluation)
        )
        conditions = []
        for requirement in contract.checks:
            checks = [
                evaluation.checks[i]
                for i in result.closing_check_ids
                if (basis := evaluation.checks[i].basis) is not None
                and basis.check_kind == requirement.kind
                and evaluation.checks[i].status == "PASS"
            ]
            profiles = [_current_profile(state, c, policy, evaluation) for c in checks]
            groups = sorted(_declared_groups([p for p in profiles if p is not None]))
            named = sorted(
                {c.verifier_id for c in checks if c.verifier_id in requirement.checker_ids}
            )
            conditions.append(
                (
                    requirement.id,
                    min(len({c.verifier_id for c in checks}), requirement.min_checks),
                    groups if requirement.min_declared_groups else [],
                    named,
                )
            )
        values.append(
            (
                contract.fingerprint,
                available,
                conditions,
                result.coverage_complete,
                result.finite_complete,
                sorted({r.code for r in result.residuals if r.blocking}),
            )
        )
    return _fingerprint(values)
