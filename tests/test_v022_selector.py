"""Selection changes ranking only; all public execution and stopping stay shared."""

import pytest

import evidence_gap_router as s


def setup():
    state = s.State(
        obligations=(
            s.Obligation(id="task", scope="s", description="data", acceptance="valid"),
            s.Obligation(
                id="helper", scope="s", description="rules", acceptance="read", required=False
            ),
        ),
        evidence=(
            s.Evidence(
                id="data",
                obligation_id="task",
                scope="s",
                digest="a" * 64,
                producer="host",
                source="data-file",
                provenance_group="declared-data",
                content="actual declared data",
            ),
        ),
    )
    budget = s.Budget(limits=s.Resources(actions=2, verifications=1))
    policy = s.Policy(
        trusted_verifiers=("v",),
        handlers=(
            s.HandlerRegistration(handler_id="read", roles=("investigate",)),
            s.HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=(s.CheckerPermission(checker_id="v"),),
            ),
        ),
    )
    acquisition = s.ActionCandidate(
        id="rules-read",
        obligation_id="helper",
        scope="s",
        kind="investigate",
        handler_id="read",
        produces_evidence_id="rules",
        resources=s.Resources(actions=1, verifications=0),
    )
    verify = s.ActionCandidate(
        id="data-check",
        obligation_id="task",
        scope="s",
        kind="verify",
        handler_id="check",
        checker_id="v",
        target_evidence_id="data",
        target_digest="a" * 64,
        dependencies=(
            s.DependencyRequirement(evidence_id="rules", obligation_id="helper", scope="s"),
        ),
        resources=s.Resources(actions=1, verifications=1),
    )

    def read(view):
        return view.result(
            actual_resources=s.Resources(actions=1, verifications=0),
            evidence=(
                s.Evidence(
                    id="rules",
                    obligation_id="helper",
                    scope="s",
                    digest="b" * 64,
                    producer="read",
                    content="finite actual rules",
                    source="rules-file",
                    provenance_group="declared-rules",
                ),
            ),
        )

    def check(view):
        assert tuple(e.id for e in view.inputs) == ("data", "rules")
        return view.result(
            actual_resources=s.Resources(actions=1, verifications=1),
            checks=(view.check(status="PASS", reason="checked both declared inputs"),),
        )

    return state, (verify, acquisition), budget, policy, {"read": read, "check": check}


def test_selector_keeps_future_helper_pool_and_matches_default_execution():
    args = setup()
    seen = []

    def selector(state, full, eligible):
        assert full == args[1]
        seen.append(tuple(a.id for a in eligible))
        return next(a for a in full if a in eligible)

    normal = s.run(*args)
    selected = s.run(*args, selector=selector)
    assert (
        normal.decision.observations_satisfied == selected.decision.observations_satisfied is True
    )
    assert normal.state == selected.state and normal.receipts == selected.receipts
    assert normal.callback_calls == selected.callback_calls == ("read", "check")
    assert seen == [("rules-read",), ("data-check",)]
    assert normal.stop_reason == selected.stop_reason == "router_stopped"


@pytest.mark.parametrize("bad", ["different_payload", "not_candidate", "raises"])
def test_invalid_selector_does_not_issue_or_charge(bad):
    args = setup()

    def selector(state, full, eligible):
        if bad == "raises":
            raise RuntimeError("ranking failed before execution")
        if bad == "not_candidate":
            return None
        return eligible[0].model_copy(update={"handler_id": "unregistered"})

    report = s.run(*args, selector=selector)
    assert report.state == args[0] and report.receipts == () and report.callback_calls == ()
    assert report.stop_reason == "planning_error" and report.error


def test_known_global_stop_never_calls_selector_and_preserves_pending():
    state, pool, budget, policy, handlers = setup()
    pending = s.start(state, pool[1], "pending", budget, policy, candidates=pool)

    def selector(*args):
        raise AssertionError("ranking cannot override a pending invocation")

    report = s.run(pending, pool, budget, policy, handlers, selector=selector)
    assert report.state == pending and not report.receipts
    assert report.stop_reason == "router_stopped" and report.decision.stop_reason == "blocked"


def test_max_steps_same_for_default_and_selector_with_receipts_retained():
    args = setup()
    normal = s.run(*args, max_steps=1)
    selected = s.run(*args, max_steps=1, selector=lambda state, pool, feasible: feasible[0])
    assert normal.state == selected.state and normal.receipts == selected.receipts
    assert normal.stop_reason == selected.stop_reason == "max_steps_reached"
    assert normal.decision.action == selected.decision.action == args[1][0]


@pytest.mark.parametrize("unknown", [False, True])
def test_empty_receipt_semantic_stop_is_identical_for_all_selection_rules(unknown):
    state, pool, budget, policy, handlers = setup()

    def empty(view):
        return view.result(
            actual_resources=s.Resources(actions=1, verifications=None if unknown else 0),
            status="unknown" if unknown else "completed",
            side_effects="unknown" if unknown else "known",
        )

    args = (state, pool, budget, policy, {**handlers, "read": empty})
    reports = [s.run(*args)] + [
        s.run(*args, selector=selector)
        for selector in (
            lambda state, pool, feasible: feasible[0],
            lambda state, pool, feasible: feasible[-1],
            lambda state, pool, feasible: next(a for a in pool if a in feasible),
        )
    ]
    first = reports[0]
    for report in reports:
        assert report.state == first.state and report.receipts == first.receipts
        assert report.stop_reason == first.stop_reason == "router_stopped"
        assert report.decision.stop_reason == ("escalation_required" if unknown else "blocked")
        assert len(report.receipts) == 1
        assert report.receipts[0].actual_resources.verifications == (None if unknown else 0)


@pytest.mark.parametrize(
    "condition", ["failure", "unknown_use", "exception", "invalid_receipt", "pending", "max_steps"]
)
def test_all_rankings_keep_identical_paid_fault_pending_and_limit_semantics(condition):
    state, pool, budget, policy, handlers = setup()

    def callback(view):
        if condition == "exception":
            raise RuntimeError("actual callback failure")
        if condition == "invalid_receipt":
            return {"unaccepted": "ordinary invalid callback output"}
        return view.result(
            status="failed" if condition == "failure" else "unknown",
            side_effects="known" if condition == "failure" else "unknown",
            actual_resources=s.Resources(
                actions=1, verifications=0 if condition == "failure" else None
            ),
        )

    if condition == "pending":
        state = s.start(state, pool[1], "pending", budget, policy, candidates=pool)
    if condition not in {"pending", "max_steps"}:
        handlers = {**handlers, "read": callback}
    selectors = (
        None,
        lambda state, pool, feasible: feasible[0],
        lambda state, pool, feasible: feasible[-1],
        lambda state, pool, feasible: next(a for a in pool if a in feasible),
    )
    reports = [
        s.run(
            state,
            pool,
            budget,
            policy,
            handlers,
            selector=selector,
            max_steps=1 if condition == "max_steps" else 32,
        )
        for selector in selectors
    ]
    first = reports[0]
    for report in reports:
        assert report.state == first.state and report.receipts == first.receipts
        assert report.stop_reason == first.stop_reason
        assert report.decision.stop_reason == first.decision.stop_reason
        assert report.callback_calls == first.callback_calls and report.error == first.error
        assert len(report.receipts) == (0 if condition == "pending" else 1)
