"""Pure deterministic planning and explicit single-writer state transitions."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from .models import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckResult,
    Coverage,
    Decision,
    Evidence,
    Exclusion,
    IdentifiedRecord,
    Obligation,
    Policy,
    Residual,
    Resources,
    Result,
    State,
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


def _trusted_check(check: CheckResult, evidence: tuple[Evidence, ...], policy: Policy) -> bool:
    targets = [e for e in evidence if e.digest == check.target_digest]
    return bool(targets) and (
        check.verifier_id in policy.trusted_verifiers
        and not check.withdrawn
        and not check.expired
        and (
            not policy.prohibit_self_verification
            or all(e.producer != check.verifier_id for e in targets)
        )
    )


def _replaced_checks(state: State, current: tuple[Evidence, ...], policy: Policy) -> set[str]:
    checks = {c.id: c for c in state.checks}
    links = {
        s.target_id: s.replacement_id
        for s in state.supersessions
        if s.kind == "check" and s.replacement_id is not None
    }
    replaced = set()
    for old_id, replacement_id in links.items():
        while replacement_id in links:
            replacement_id = links[replacement_id]
        replacement = checks[replacement_id]
        if checks[old_id].status == "PASS" or (
            replacement.status == "PASS" and _trusted_check(replacement, current, policy)
        ):
            replaced.add(old_id)
    return replaced


def _analyze(state: State, policy: Policy) -> tuple[tuple[Residual, ...], set[str], int]:
    residuals: list[Residual] = []
    satisfied: set[str] = set()
    pending = 0
    for obligation in sorted(state.obligations, key=lambda o: o.id):
        current = _active_evidence(state, obligation)
        replaced_checks = _replaced_checks(state, current, policy)
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

        ordered = sorted(current, key=lambda e: e.id)
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
        if unknown:
            add(
                "unknown_provenance",
                "Missing source/provenance is retained and does not establish a group.",
                unknown,
                len(groups) < obligation.min_provenance_groups,
            )
        unavailable = set(obligation.required_verifiers) - set(policy.trusted_verifiers)
        if not policy.trusted_verifiers or unavailable:
            add(
                "verifier_unavailable",
                "Host policy does not authorize the required verifier(s).",
                unavailable,
            )
        checks = tuple(
            c
            for c in state.checks
            if c.obligation_id == obligation.id
            and c.scope == obligation.scope
            and c.id not in replaced_checks
            and _trusted_check(c, current, policy)
        )
        for digest in sorted({e.digest for e in current}):
            digest_checks = [c for c in checks if c.target_digest == digest]
            failures = [c for c in digest_checks if c.status == "FAIL"]
            unknown_checks = [c for c in digest_checks if c.status == "UNKNOWN"]
            passes = {c.verifier_id for c in digest_checks if c.status == "PASS"}
            required = set(obligation.required_verifiers)
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
                    f"No applicable trusted PASS for digest {digest}.",
                    (e.id for e in current if e.digest == digest),
                )
            if not digest_checks or unknown_checks:
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
            resolved = False
            for resolution in resolutions:
                check = next(c for c in state.checks if c.id == resolution.check_id)
                if (
                    check.id not in replaced_checks
                    and check.status == "PASS"
                    and _trusted_check(check, current, policy)
                ):
                    resolved = True
            if not resolved:
                add(
                    "contradiction",
                    contradiction.reason,
                    (contradiction.id,),
                    contradiction.blocking,
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
    return tuple(residuals), satisfied, pending


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
    satisfied: set[str],
    pending: int,
    retry: bool = False,
) -> tuple[str, ...]:
    reasons: list[str] = []
    obligations = {o.id: o for o in state.obligations}
    obligation = obligations.get(action.obligation_id)
    if obligation is None:
        return ("unknown_obligation",)
    if action.scope != obligation.scope:
        reasons.append("scope_mismatch")
    if action.obligation_id in satisfied:
        reasons.append("obligation_satisfied")
    if action.handler_id not in policy.executable_handlers:
        reasons.append("handler_unavailable")
    previous = [a for a in state.attempts if a.action.id == action.id]
    if previous and not retry:
        reasons.append("already_attempted")
    if previous and any(a.action != action for a in previous):
        reasons.append("action_id_collision")
    current = _active_evidence(state, obligation)
    known = {e.id for e in current}
    if not set(action.requires_evidence_ids).issubset(known):
        reasons.append("prerequisite_missing")
    if action.kind == "verify":
        if not any(e.digest == action.target_digest for e in current):
            reasons.append("target_digest_missing_or_stale")
        if not policy.trusted_verifiers or set(obligation.required_verifiers) - set(
            policy.trusted_verifiers
        ):
            reasons.append("verifier_unavailable")
    elif pending >= policy.max_pending_verifications:
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


def plan(
    state: State, candidates: tuple[ActionCandidate, ...], budget: Budget, policy: Policy
) -> Decision:
    """Recommend at most one declared action without mutating state or consuming budget."""
    if len({a.id for a in candidates}) != len(candidates):
        raise ValueError("candidate IDs must be unique")
    residuals, satisfied, pending = _analyze(state, policy)
    remaining, resource_issues = _resource_status(state, budget)
    residuals += resource_issues
    required = [o for o in state.obligations if o.required]
    count = sum(o.id in satisfied for o in required)
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
        reasons = _candidate_reasons(state, action, budget, policy, remaining, satisfied, pending)
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
            codes = {r.code for r in residuals if r.obligation_id == o.id and r.blocking}
            if "missing_evidence" in codes:
                kinds = {"investigate": 0, "diversify": 1, "verify": 2}
            elif "unverified" in codes or "contradiction" in codes:
                kinds = {"verify": 0, "diversify": 1, "investigate": 2}
            elif "insufficient_provenance" in codes:
                kinds = {"diversify": 0, "investigate": 1, "verify": 2}
            else:
                kinds = {"verify": 0, "investigate": 1, "diversify": 2}
            return not o.required, -o.priority, kinds[action.kind], action.id

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
    )


def start(
    state: State,
    action: ActionCandidate,
    attempt_id: str,
    budget: Budget,
    policy: Policy,
    *,
    retry: bool = False,
) -> State:
    """Record host intent immediately before a callback; retry requires explicit opt-in."""
    previous = next((a for a in state.attempts if a.id == attempt_id), None)
    attempt = Attempt(id=attempt_id, action=action, retry=retry)
    if previous:
        if previous != attempt:
            raise ValueError("attempt ID collision")
        raise ValueError("attempt already issued; do not execute it again")
    _, satisfied, pending = _analyze(state, policy)
    remaining, issues = _resource_status(state, budget)
    if issues:
        raise ValueError("resource accounting is unsafe")
    if any(a.id not in {r.attempt_id for r in state.results} for a in state.attempts):
        raise ValueError("an attempt is pending; single-writer execution requires its result")
    reasons = _candidate_reasons(
        state, action, budget, policy, remaining, satisfied, pending, retry
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


def observe(state: State, result: Result) -> State:
    """Validate an issued attempt and record its result once; identical replay is idempotent."""
    previous = next((r for r in state.results if r.id == result.id), None)
    if previous:
        if previous != result:
            raise ValueError("result ID collision")
        return state
    if not any(a.id == result.attempt_id for a in state.attempts):
        raise ValueError("result refers to an unissued attempt")
    values = {name: getattr(state, name) for name in State.model_fields}
    for name in ("evidence", "checks", "contradictions", "supersessions"):
        values[name] = _merge(getattr(state, name), getattr(result, name))
    values["results"] = (*state.results, result)
    return State(**values)
