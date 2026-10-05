"""Finite, synthetic matched-input comparison; no general performance claim."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Literal

from .models import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckerPermission,
    CheckResult,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
    VerificationBasis,
)
from .router import make_basis, observe, plan, start
from .runner import CallbackView


def _change(record: Any, **updates: Any) -> Any:
    return type(record)(**{**record.model_dump(), **updates})


def _material(identifier: str, obligation: str, value: int, source: str) -> Evidence:
    content = json.dumps({"value": value}, sort_keys=True)
    return Evidence(
        id=identifier,
        obligation_id=obligation,
        scope="synthetic-comparison",
        digest=hashlib.sha256(content.encode()).hexdigest(),
        content=content,
        producer="read",
        source=source,
        provenance_group=source,
    )


def _verify(identifier: str, evidence: Evidence, **updates: Any) -> ActionCandidate:
    return ActionCandidate(
        id=identifier,
        obligation_id=evidence.obligation_id,
        scope=evidence.scope,
        kind="verify",
        handler_id="check",
        target_evidence_id=evidence.id,
        target_digest=evidence.digest,
        checker_id="positive",
        resources=Resources(actions=1, verifications=1),
        **updates,
    )


def _checked(state: State, action: ActionCandidate, identifier: str) -> CheckResult:
    basis = make_basis(state, action)
    status, reason = _outcome(basis, state.evidence)
    return CheckResult(
        id=identifier,
        obligation_id=action.obligation_id,
        scope=action.scope,
        target_digest=basis.target.digest,
        verifier_id="positive",
        basis=basis,
        status=status,
        reason=reason,
    )


def _outcome(
    basis: VerificationBasis, inputs: tuple[Evidence, ...]
) -> tuple[Literal["PASS", "FAIL"], str]:
    bound = {item.id: item for item in inputs}
    value = json.loads(bound[basis.target.evidence_id].content or "null")["value"]
    minimum = max(
        (json.loads(bound[d.evidence_id].content or "null")["value"] for d in basis.dependencies),
        default=0,
    )
    return ("PASS" if value >= minimum else "FAIL"), f"computed {value} >= bound minimum {minimum}"


def _scenario(name: str) -> tuple[State, tuple[ActionCandidate, ...], Budget, dict[str, Evidence]]:
    obligation = Obligation(
        id="dataset",
        description="Check numeric material",
        scope="synthetic-comparison",
        acceptance="value >= bound rule minimum, or zero if no rule declared",
        required_verifiers=("positive",),
        min_evidence=2 if name == "A04_recheck" else 1,
        min_provenance_groups=2 if name == "A05_provenance" else 1,
    )
    first = _material("first", "dataset", 10, "origin-1")
    second = _material("second", "dataset", 20, "origin-2")
    current = State(obligations=(obligation,), evidence=(first,))
    check_first = _verify("a-first-check", first)
    current = _change(current, checks=(_checked(current, check_first, "seed-check"),))
    if name == "A04_recheck":
        current = _change(current, evidence=(first, second))
        return (
            current,
            (check_first, _verify("z-second-check", second)),
            Budget(limits=Resources(actions=1, verifications=1)),
            {},
        )
    if name == "A05_provenance":
        duplicate = _change(first, id="duplicate")
        acquire_same = ActionCandidate(
            id="a-repeat-origin",
            obligation_id="dataset",
            scope=first.scope,
            kind="diversify",
            handler_id="read",
            source=first.source,
            provenance_group=first.provenance_group,
            produces_evidence_id=duplicate.id,
        )
        acquire_new = _change(
            acquire_same,
            id="z-new-origin",
            source=second.source,
            provenance_group=second.provenance_group,
            produces_evidence_id=second.id,
        )
        return (
            current,
            (acquire_same, acquire_new, _verify("verify-second", second)),
            Budget(limits=Resources(actions=2, verifications=1)),
            {duplicate.id: duplicate, second.id: second},
        )
    rules_obligation = Obligation(
        id="rules",
        description="Confirm minimum",
        scope=first.scope,
        acceptance="minimum >= 0",
        priority=10,
        required_verifiers=("positive",),
    )
    old_rules = _material("old-rules", "rules", 0, "rule-origin")
    new_rules = _material("new-rules", "rules", 5, "rule-origin")
    current = State(obligations=(obligation, rules_obligation), evidence=(first, old_rules))
    old_action = _verify(
        "previous-dataset-check",
        first,
        dependencies=(
            DependencyRequirement(
                evidence_id=old_rules.id,
                obligation_id="rules",
                scope=first.scope,
            ),
        ),
    )
    current = _change(
        current,
        checks=(_checked(current, old_action, "old-dataset-pass"),),
        evidence=(first, _change(old_rules, expired=True)),
    )
    new_action = _verify(
        "a-dataset-recheck",
        first,
        dependencies=(
            DependencyRequirement(
                evidence_id=new_rules.id,
                obligation_id="rules",
                scope=first.scope,
                requirement="verified",
            ),
        ),
    )
    acquire_rules = ActionCandidate(
        id="read-new-rules",
        obligation_id="rules",
        scope=first.scope,
        kind="investigate",
        handler_id="read",
        source=new_rules.source,
        provenance_group=new_rules.provenance_group,
        produces_evidence_id=new_rules.id,
    )
    return (
        current,
        (new_action, acquire_rules, _verify("verify-new-rules", new_rules)),
        Budget(limits=Resources(actions=3, verifications=2)),
        {new_rules.id: new_rules},
    )


def _execute(
    initial: State,
    candidates: tuple[ActionCandidate, ...],
    budget: Budget,
    materials: dict[str, Evidence],
    *,
    routed: bool,
) -> dict[str, Any]:
    policy = Policy(
        trusted_verifiers=("positive",),
        handlers=(
            HandlerRegistration(handler_id="read", roles=("investigate", "diversify")),
            HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id="positive"),),
            ),
        ),
    )

    def read(view: CallbackView) -> Result:
        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(materials[view.action.produces_evidence_id or ""],),
        )

    def check(view: CallbackView) -> Result:
        assert view.basis is not None
        status, reason = _outcome(view.basis, view.inputs)
        record = view.check(status=status, reason=reason)
        return view.result(actual_resources=Resources(actions=1, verifications=1), checks=(record,))

    handlers: dict[str, Callable[..., Any]] = {"read": read, "check": check}
    state = initial
    calls = []
    for number in range(1, 17):
        decision = plan(state, candidates, budget, policy)
        if decision.stop_reason == "satisfied":
            break
        action = decision.action
        if not routed:
            action = None
            for candidate in candidates:
                single = plan(state, (candidate,), budget, policy)
                reasons = {r for e in single.exclusions for r in e.reasons}
                # The baseline deliberately follows its declared order, including a
                # redundant check. It retains every other feasibility constraint.
                if single.action is not None or reasons == {
                    "target_already_verified_or_no_matching_gap"
                }:
                    action = candidate
                    break
        if action is None:
            break
        attempt_id = f"comparison-{number}"
        basis = make_basis(state, action) if action.kind == "verify" else None
        if routed:
            state = start(state, action, attempt_id, budget, policy)
        else:
            registration = next(h for h in policy.handlers if h.handler_id == action.handler_id)
            attempt = Attempt(
                id=attempt_id,
                action=action,
                registration=registration,
                basis=basis,
                inputs=(basis.target, *basis.dependencies) if basis is not None else (),
            )
            # State is host-owned. This explicit host choice does not broaden handler
            # permissions or bypass receipt/basis/cost validation in observe.
            state = _change(state, attempts=(*state.attempts, attempt))
        view = CallbackView(
            action=action,
            attempt_id=attempt_id,
            obligation=next(o for o in state.obligations if o.id == action.obligation_id),
            basis=basis,
            inputs=tuple(
                next(e for e in state.evidence if e.id == b.evidence_id)
                for b in (basis.target, *basis.dependencies)
            )
            if basis is not None
            else (),
        )
        state = observe(state, handlers[action.handler_id](view), policy)
        calls.append(
            {
                "action": action.id,
                "handler": action.handler_id,
                "target": action.target_evidence_id,
                "produces": action.produces_evidence_id,
            }
        )
    final = plan(state, candidates, budget, policy)
    return {
        "callback_calls": len(calls),
        "calls": calls,
        "verifications": sum(r.actual_resources.verifications or 0 for r in state.results),
        "stop": final.stop_reason,
        "satisfied": final.coverage.satisfied,
        "required": final.coverage.required,
        "unresolved": final.coverage.required - final.coverage.satisfied,
        "residual_codes": sorted({r.code for r in final.residuals if r.blocking}),
    }


def compare() -> dict[str, Any]:
    """Return every predeclared case, including no advantage and reversed orders."""
    results = []
    for name in ("A04_recheck", "A05_provenance", "dependency_recheck"):
        state, actions, budget, materials = _scenario(name)
        for variant in ("declared", "reversed", "renamed"):
            candidates = actions
            if variant == "reversed":
                candidates = tuple(reversed(actions))
            elif variant == "renamed":
                candidates = tuple(
                    _change(a, id=f"renamed-{len(actions) - i}") for i, a in enumerate(actions)
                )
            results.append(
                {
                    "scenario": name,
                    "variant": variant,
                    "identical_initial_state": {
                        "evidence": [e.model_dump(mode="json") for e in state.evidence],
                        "checks": [c.model_dump(mode="json") for c in state.checks],
                        "seed_checker_calls": len(state.checks),
                    },
                    "budget": budget.model_dump(mode="json"),
                    "baseline": _execute(state, candidates, budget, materials, routed=False),
                    "router": _execute(state, candidates, budget, materials, routed=True),
                }
            )
    return {
        "artificial_data": True,
        "protocol": "finite matched inputs/callbacks/checker/budget",
        "baseline": "declared order among feasible actions; allows redundant content checks",
        "counting": "Counts and budgets start after the identical snapshots; seed checks are shown",
        "results": results,
        "limitation": "Small synthetic cases; no claim of general cost, truth, or AI improvement",
    }


if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
