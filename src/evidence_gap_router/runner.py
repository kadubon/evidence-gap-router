"""Explicit finite local execution over immutable, declared callback inputs."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Literal

from .models import (
    ActionCandidate,
    Budget,
    CheckResult,
    Contradiction,
    Decision,
    Evidence,
    Obligation,
    Policy,
    Record,
    Resources,
    Result,
    State,
    Supersession,
    VerificationBasis,
)
from .router import _needed_helper_actions, _plan, feasible_actions, observe, plan, start


class CallbackView(Record):
    """Pinned task and expressly disclosed records; this is not a Python sandbox."""

    action: ActionCandidate
    attempt_id: str
    obligation: Obligation
    basis: VerificationBasis | None
    inputs: tuple[Evidence, ...]

    def result(
        self,
        *,
        actual_resources: Resources,
        evidence: tuple[Evidence, ...] = (),
        checks: tuple[CheckResult, ...] = (),
        contradictions: tuple[Contradiction, ...] = (),
        supersessions: tuple[Supersession, ...] = (),
        status: Literal["completed", "failed", "unknown"] = "completed",
        reason: str = "",
        side_effects: Literal["known", "unknown"] = "known",
    ) -> Result:
        """Build a receipt for this invocation without inventing measured cost."""
        return Result(
            id=f"{self.attempt_id}:result",
            attempt_id=self.attempt_id,
            action_id=self.action.id,
            obligation_id=self.action.obligation_id,
            scope=self.action.scope,
            target_digest=self.action.target_digest,
            actual_resources=actual_resources,
            evidence=evidence,
            checks=checks,
            contradictions=contradictions,
            supersessions=supersessions,
            status=status,
            reason=reason,
            side_effects=side_effects,
        )

    def check(self, *, status: Literal["PASS", "FAIL", "UNKNOWN"], reason: str) -> CheckResult:
        """Bind an actual checker outcome to the issued target and dependencies."""
        if self.basis is None:
            raise ValueError("only an issued verification has a check basis")
        return CheckResult(
            id=f"{self.attempt_id}:check",
            obligation_id=self.action.obligation_id,
            scope=self.action.scope,
            target_digest=self.basis.target.digest,
            verifier_id=self.basis.checker_id,
            basis=self.basis,
            status=status,
            reason=reason,
        )


Handler = Callable[[CallbackView], Result]
CandidateFactory = Callable[[State], tuple[ActionCandidate, ...]]
Candidates = tuple[ActionCandidate, ...] | CandidateFactory
ActionSelector = Callable[
    [State, tuple[ActionCandidate, ...], tuple[ActionCandidate, ...]], ActionCandidate
]
RunnerStop = Literal[
    "router_stopped",
    "step_completed",
    "max_steps_reached",
    "no_progress",
    "factory_error",
    "planning_error",
    "start_error",
    "callback_error",
]


class StepReport(Record):
    state: State
    decision: Decision
    receipt: Result | None = None
    stop_reason: RunnerStop
    error: str | None = None


class RunReport(Record):
    state: State
    decision: Decision
    receipts: tuple[Result, ...] = ()
    decisions: tuple[Decision, ...] = ()
    callback_calls: tuple[str, ...] = ()
    stop_reason: RunnerStop
    error: str | None = None


def _policy(policy: Policy, handlers: Mapping[str, Handler]) -> Policy:
    available = set(handlers)
    if policy.executable_handlers:
        available.intersection_update(policy.executable_handlers)
    if policy.available_handlers is not None:
        available.intersection_update(policy.available_handlers)
    return policy.model_copy(update={"available_handlers": tuple(sorted(available))})


def _recommend(
    state: State,
    candidates: Candidates,
    budget: Budget,
    policy: Policy,
    selector: ActionSelector | None = None,
) -> tuple[Decision, RunnerStop | None, str | None, tuple[ActionCandidate, ...]]:
    try:
        current = candidates(state) if callable(candidates) else candidates
    except Exception as exc:
        return plan(state, (), budget, policy), "factory_error", f"{type(exc).__name__}: {exc}", ()
    try:
        if not isinstance(current, tuple) or any(
            not isinstance(item, ActionCandidate) for item in current
        ):
            raise TypeError("candidates must be a finite tuple of ActionCandidate records")
        decision = (
            plan(state, current, budget, policy)
            if selector is None
            else _plan(state, current, budget, policy, selector=selector)
        )
        return decision, None, None, current
    except Exception as exc:
        return plan(state, (), budget, policy), "planning_error", f"{type(exc).__name__}: {exc}", ()


def _next_attempt_id(state: State) -> str:
    used = {item.id for item in state.attempts}
    result_ids = {item.id for item in state.results}
    check_ids = {item.id for item in state.checks}
    number = 1
    while (
        f"host-attempt-{number}" in used
        or f"host-attempt-{number}:result" in result_ids
        or f"host-attempt-{number}:unknown" in result_ids
        or f"host-attempt-{number}:check" in check_ids
    ):
        number += 1
    return f"host-attempt-{number}"


def _view(state: State, attempt_id: str) -> CallbackView:
    attempt = next(item for item in state.attempts if item.id == attempt_id)
    action = attempt.action
    inputs = tuple(
        next(
            item
            for item in state.evidence
            if (item.id, item.digest, item.obligation_id, item.scope)
            == (binding.evidence_id, binding.digest, binding.obligation_id, binding.scope)
        )
        for binding in attempt.inputs
    )
    return CallbackView(
        action=action,
        attempt_id=attempt_id,
        obligation=next(item for item in state.obligations if item.id == action.obligation_id),
        basis=attempt.basis,
        inputs=inputs,
    )


def _execute(
    state: State,
    decision: Decision,
    current_candidates: tuple[ActionCandidate, ...],
    budget: Budget,
    policy: Policy,
    handlers: Mapping[str, Handler],
) -> StepReport:
    effective = policy
    action = decision.action
    if action is None:
        return StepReport(state=state, decision=decision, stop_reason="router_stopped")
    attempt_id = _next_attempt_id(state)
    try:
        state = start(state, action, attempt_id, budget, effective, candidates=current_candidates)
        view = _view(state, attempt_id)
    except Exception as exc:
        return StepReport(
            state=state,
            decision=decision,
            stop_reason="start_error",
            error=f"{type(exc).__name__}: {exc}",
        )
    try:
        receipt = handlers[action.handler_id](view)
        if not isinstance(receipt, Result):
            raise TypeError("callback must return a Result")
        if (
            receipt.attempt_id,
            receipt.action_id,
            receipt.obligation_id,
            receipt.scope,
            receipt.target_digest,
        ) != (attempt_id, action.id, action.obligation_id, action.scope, action.target_digest):
            raise ValueError("callback receipt does not match the current invocation")
        state = observe(state, receipt, effective)
    except Exception as exc:
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=None, tokens=None),
            status="unknown",
            side_effects="unknown",
            reason=f"Callback outcome or receipt uncertain: {type(exc).__name__}: {exc}",
        ).model_copy(update={"id": f"{attempt_id}:unknown"})
        state = observe(state, receipt, effective)
        return StepReport(
            state=state,
            decision=plan(state, (), budget, effective),
            receipt=receipt,
            stop_reason="callback_error",
            error=f"{type(exc).__name__}: {exc}",
        )
    return StepReport(state=state, decision=decision, receipt=receipt, stop_reason="step_completed")


def step(
    state: State,
    candidates: Candidates,
    budget: Budget,
    policy: Policy,
    handlers: Mapping[str, Handler],
    *,
    selector: ActionSelector | None = None,
) -> StepReport:
    """Recommend and execute at most one registered callback, retaining all state.

    ``decision`` is the recommendation that selected this invocation. Continue
    with the returned state to obtain the next recommendation. A pending attempt
    is never reissued. Factory/start failures happen before invocation and are
    not charged as callback executions; callback uncertainty is recorded.
    A host ``selector(state, full_pool, eligible)`` may replace ranking only;
    it must return an unchanged eligible action. All current gates and the full
    dependency pool remain in force. Selector exceptions are planning failures.
    """
    effective = _policy(policy, handlers)
    decision, error_stop, error, current = _recommend(
        state, candidates, budget, effective, selector
    )
    if error_stop is not None:
        return StepReport(state=state, decision=decision, stop_reason=error_stop, error=error)
    return _execute(state, decision, current, budget, effective, handlers)


def _progress(state: State) -> str:
    """Compare evidence/check substance, not newly issued IDs or consumed cost."""
    values = {}
    for name in ("evidence", "checks", "contradictions", "supersessions", "invalidations"):
        records = []
        for item in getattr(state, name):
            value = item.model_dump(mode="json")
            value.pop("id", None)
            if name == "evidence":
                value.pop("producer", None)
                value.pop("content", None)
                value.pop("reference", None)
            records.append(json.dumps(value, sort_keys=True, separators=(",", ":")))
        values[name] = sorted(set(records))
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _binding_progress(
    before: State,
    after: State,
    candidates: tuple[ActionCandidate, ...],
    budget: Budget,
    policy: Policy,
    selected: ActionCandidate | None,
) -> bool:
    """A needed exact-ID binding can unlock work despite duplicate information."""
    new_ids = {item.id for item in after.evidence} - {item.id for item in before.evidence}
    if not new_ids:
        return False
    # Verified dependencies may need a concrete verifier candidate derived only
    # after acquisition reveals its digest. Core's original finite helper path
    # approves that acquisition without granting every new alias progress.
    if (
        selected is not None
        and selected.kind != "verify"
        and selected.produces_evidence_id in new_ids
        and selected.id in _needed_helper_actions(before, candidates, budget, policy)
    ):
        acquired = next(item for item in after.evidence if item.id == selected.produces_evidence_id)
        obligation = next(item for item in after.obligations if item.id == acquired.obligation_id)
        if not acquired.withdrawn and not acquired.expired:
            for action in candidates:
                for dependency in action.dependencies:
                    if (
                        dependency.evidence_id == acquired.id
                        and dependency.obligation_id == acquired.obligation_id
                        and dependency.scope == acquired.scope
                        and (dependency.digest is None or dependency.digest == acquired.digest)
                        and (
                            dependency.contract_fingerprint is None
                            or dependency.contract_fingerprint == obligation.contract_fingerprint
                        )
                    ):
                        return True
    previous = {item.id for item in feasible_actions(before, candidates, budget, policy)}
    for action in feasible_actions(after, candidates, budget, policy):
        if action.id in previous:
            continue
        bindings = {item.evidence_id for item in action.dependencies}
        bindings.update(action.requires_evidence_ids)
        if action.kind == "verify" and action.target_evidence_id is not None:
            bindings.add(action.target_evidence_id)
        if bindings & new_ids:
            return True
    return False


def run(
    state: State,
    candidates: Candidates,
    budget: Budget,
    policy: Policy,
    handlers: Mapping[str, Handler],
    *,
    max_steps: int = 32,
    selector: ActionSelector | None = None,
) -> RunReport:
    """Run at most ``max_steps`` callbacks; return current state on every stop.

    New material, check outcomes, or a needed exact input binding count as progress.
    New action/attempt IDs and costs alone do not. This explicit local host does
    not provide background work, forced timeouts, crash recovery or a sandbox.
    Optional ``selector`` replaces only eligible-action ranking, using the same
    current planning, issuance, receipt, progress and stop path as the default.
    """
    if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive finite integer")
    receipts: list[Result] = []
    decisions: list[Decision] = []
    calls: list[str] = []
    effective = _policy(policy, handlers)
    for _ in range(max_steps):
        previous_state = state
        before = _progress(state)
        decision, error_stop, error, current = _recommend(
            state, candidates, budget, effective, selector
        )
        report = (
            StepReport(state=state, decision=decision, stop_reason=error_stop, error=error)
            if error_stop is not None
            else _execute(state, decision, current, budget, effective, handlers)
        )
        state = report.state
        decisions.append(report.decision)
        if report.receipt is not None:
            receipts.append(report.receipt)
            calls.append(
                next(
                    attempt.action.handler_id
                    for attempt in state.attempts
                    if attempt.id == report.receipt.attempt_id
                )
            )
        if report.stop_reason != "step_completed":
            return RunReport(
                state=state,
                decision=report.decision,
                receipts=tuple(receipts),
                decisions=tuple(decisions),
                callback_calls=tuple(calls),
                stop_reason=report.stop_reason,
                error=report.error,
            )
        if _progress(state) == before and not _binding_progress(
            previous_state, state, current, budget, effective, report.decision.action
        ):
            decision, stop, error, _ = _recommend(state, candidates, budget, effective, selector)
            decisions.append(decision)
            return RunReport(
                state=state,
                decision=decision,
                receipts=tuple(receipts),
                decisions=tuple(decisions),
                callback_calls=tuple(calls),
                stop_reason=stop
                or ("router_stopped" if decision.action is None else "no_progress"),
                error=error,
            )
    decision, stop, error, _ = _recommend(state, candidates, budget, effective, selector)
    decisions.append(decision)
    return RunReport(
        state=state,
        decision=decision,
        receipts=tuple(receipts),
        decisions=tuple(decisions),
        callback_calls=tuple(calls),
        stop_reason=stop or ("router_stopped" if decision.action is None else "max_steps_reached"),
        error=error,
    )
