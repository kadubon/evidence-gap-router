from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    State,
    dump_json,
    load_json,
    observe,
    plan,
    start,
)
from evidence_gap_router.runner import CallbackView, run, step
from evidence_gap_router.sdk_example import run_callback_example, run_continuation_example


def foundation(min_evidence: int = 1) -> tuple[State, Budget, Policy]:
    state = State(
        obligations=(
            Obligation(
                id="o",
                scope="s",
                description="Obtain and check",
                acceptance="accepted content",
                min_evidence=min_evidence,
                required_verifiers=("v",),
            ),
        )
    )
    policy = Policy(
        trusted_verifiers=("v",),
        max_pending_verifications=100,
        handlers=(
            HandlerRegistration(handler_id="read", roles=("investigate",)),
            HandlerRegistration(
                handler_id="verify",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id="v"),),
            ),
        ),
    )
    return state, Budget(limits=Resources()), policy


def acquisition(identifier: str = "read") -> ActionCandidate:
    return ActionCandidate(
        id=identifier,
        obligation_id="o",
        scope="s",
        kind="investigate",
        handler_id="read",
        produces_evidence_id=identifier,
    )


def material(view: CallbackView):
    index = int(view.attempt_id.rsplit("-", 1)[-1])
    evidence = Evidence(
        id=view.action.produces_evidence_id or view.action.id,
        obligation_id="o",
        scope="s",
        digest=f"{index:064x}",
        content=f"material {index}",
        producer="read",
        source=f"source {index}",
        provenance_group=f"group {index}",
    )
    return view.result(actual_resources=Resources(actions=1, verifications=0), evidence=(evidence,))


def test_A10_default_and_explicit_finite_limits_preserve_all_material_and_cost() -> None:
    state, budget, policy = foundation(min_evidence=100)

    def factory(current: State) -> tuple[ActionCandidate, ...]:
        return (acquisition(f"read-{len(current.attempts)}"),)

    limited = run(state, factory, budget, policy, {"read": material}, max_steps=3)
    assert limited.stop_reason == "max_steps_reached"
    assert len(limited.state.results) == len(limited.state.evidence) == 3
    assert limited.decision.observations_satisfied is False
    default = run(state, factory, budget, policy, {"read": material})
    assert default.stop_reason == "max_steps_reached"
    assert len(default.state.results) == 32
    assert sum(r.actual_resources.actions or 0 for r in default.state.results) == 32


def test_A10_fresh_ids_without_new_material_are_not_progress() -> None:
    state, budget, policy = foundation()

    def factory(current: State) -> tuple[ActionCandidate, ...]:
        return (acquisition(f"new-{len(current.attempts)}"),)

    report = run(
        state,
        factory,
        budget,
        policy,
        {"read": lambda view: view.result(actual_resources=Resources(actions=1, verifications=0))},
    )
    assert report.stop_reason == "no_progress"
    assert len(report.state.results) == 1
    assert report.state.results[0].actual_resources.actions == 1


def test_A10_factory_exception_retains_previous_receipt_and_evidence() -> None:
    state, budget, policy = foundation(min_evidence=2)

    def factory(current: State) -> tuple[ActionCandidate, ...]:
        if current.results:
            raise RuntimeError("factory failed after prior progress")
        return (acquisition(),)

    report = run(state, factory, budget, policy, {"read": material})
    assert report.stop_reason == "factory_error"
    assert len(report.state.results) == len(report.state.evidence) == 1
    assert report.error and "factory failed" in report.error
    assert report.state.results[0].actual_resources.actions == 1


def test_invalid_factory_retains_state_and_charges_no_callback() -> None:
    state, budget, policy = foundation()

    def malformed(current: State) -> Any:
        return [acquisition()]

    report = run(state, malformed, budget, policy, {"read": material})
    assert report.stop_reason == "planning_error"
    assert report.state == state
    assert report.receipts == ()


def test_A11_arbitrary_existing_attempt_id_is_not_reused() -> None:
    state, budget, policy = foundation()
    old_action = acquisition("old")
    state = start(state, old_action, "host-attempt-2", budget, policy)
    old_view = CallbackView(
        action=old_action,
        attempt_id="host-attempt-2",
        obligation=state.obligations[0],
        basis=None,
        inputs=(),
    )
    state = observe(
        state,
        old_view.result(
            actual_resources=Resources(actions=1, verifications=0),
            status="failed",
            reason="old failure",
        ),
        policy,
    )
    report = step(state, (acquisition("new"),), budget, policy, {"read": material})
    assert report.stop_reason == "step_completed"
    assert len({attempt.id for attempt in report.state.attempts}) == 2
    assert report.receipt and report.receipt.attempt_id != "host-attempt-2"


def test_pending_attempt_is_never_automatically_reissued() -> None:
    state, budget, policy = foundation()
    action = acquisition()
    pending = start(state, action, "external-pending", budget, policy)
    report = run(pending, (action,), budget, policy, {"read": material})
    assert report.stop_reason == "router_stopped"
    assert report.decision.stop_reason == "blocked"
    assert report.state == pending
    assert report.callback_calls == ()


def test_public_step_snapshot_continue_and_pinned_verification_view() -> None:
    state, budget, policy = foundation()
    first = step(state, (acquisition(),), budget, policy, {"read": material})
    assert first.stop_reason == "step_completed"
    restored = load_json(dump_json(first.state), State)
    target = restored.evidence[0]
    verify = ActionCandidate(
        id="verify-new",
        obligation_id="o",
        scope="s",
        kind="verify",
        handler_id="verify",
        checker_id="v",
        target_evidence_id=target.id,
        target_digest=target.digest,
        resources=Resources(actions=1, verifications=1),
    )
    views = []

    def checker(view: CallbackView):
        views.append(view)
        return view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(view.check(status="PASS", reason="actual checker result"),),
        )

    final = run(restored, (verify,), budget, policy, {"verify": checker})
    assert final.decision.observations_satisfied is True
    assert len(final.state.results) == 2
    assert views[0].inputs == (target,)
    assert views[0].basis == final.state.checks[0].basis
    assert load_json(dump_json(final.state), State) == final.state


def test_acquisition_views_hide_unrelated_answers_and_remain_immutable() -> None:
    state, budget, policy = foundation()
    unrelated = Evidence(
        id="other",
        obligation_id="o",
        scope="s",
        digest="f" * 64,
        content="another producer answer",
        producer="other",
        source="other",
        provenance_group="other",
    )
    state = State(obligations=state.obligations, evidence=(unrelated,))
    seen = []

    def reader(view: CallbackView):
        seen.append(view.inputs)
        with pytest.raises(ValidationError):
            view.inputs = (unrelated,)
        return material(view)

    result = step(state, (acquisition(),), budget, policy, {"read": reader})
    assert result.stop_reason == "step_completed"
    assert seen == [()]


def test_explicit_acquisition_dependency_is_the_only_disclosed_input() -> None:
    state, budget, policy = foundation()
    evidence = Evidence(
        id="allowed",
        obligation_id="o",
        scope="s",
        digest="a" * 64,
        content="allowed source",
        producer="other",
        source="source",
        provenance_group="group",
    )
    hidden = evidence.model_copy(update={"id": "hidden", "digest": "b" * 64, "content": "hidden"})
    state = State(obligations=state.obligations, evidence=(evidence, hidden))
    action = acquisition().model_copy(
        update={
            "dependencies": (
                DependencyRequirement(evidence_id="allowed", obligation_id="o", scope="s"),
            )
        }
    )
    seen = []

    def reader(view: CallbackView):
        seen.append(view.inputs)
        return material(view)

    step(state, (action,), budget, policy, {"read": reader})
    assert seen == [(evidence,)]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, float("inf")])
def test_step_limit_rejects_invalid_and_unbounded_values(value: Any) -> None:
    state, budget, policy = foundation()
    with pytest.raises(ValueError):
        run(state, (), budget, policy, {}, max_steps=value)


def test_installed_sdk_example_wraps_existing_plain_python_callback() -> None:
    report = run_callback_example()
    assert report.decision.observations_satisfied is True
    assert report.state.checks[0].basis is not None


def test_mapping_intersection_cannot_turn_explicit_handler_allowlist_into_unbounded() -> None:
    state, budget, policy = foundation()
    policy = policy.model_copy(
        update={
            "executable_handlers": ("read",),
            "handlers": (
                *policy.handlers,
                HandlerRegistration(handler_id="blocked", roles=("investigate",)),
            ),
        }
    )
    action = acquisition().model_copy(update={"handler_id": "blocked"})
    direct = plan(state, (action,), budget, policy)
    assert direct.action is None
    assert "handler_unavailable" in direct.exclusions[0].reasons
    calls = []

    def blocked(view: CallbackView):
        calls.append(view.action.id)
        return material(view)

    stepped = step(state, (action,), budget, policy, {"blocked": blocked})
    looped = run(state, (action,), budget, policy, {"blocked": blocked})
    for report in (stepped, looped):
        assert report.state == state
        assert report.stop_reason == "router_stopped"
        assert report.decision.action is None
        assert report.decision.stop_reason == "blocked"
    assert stepped.receipt is None
    assert looped.receipts == ()
    assert calls == []

    permitted = step(state, (acquisition(),), budget, policy, {"read": material})
    assert permitted.stop_reason == "step_completed"
    assert permitted.receipt is not None
    assert permitted.receipt.actual_resources.actions == 1


def test_absent_executable_mapping_does_not_revoke_existing_trusted_pass() -> None:
    previous = run_callback_example()
    policy = previous.decision.coverage.policy.model_copy(update={"available_handlers": None})
    budget = Budget(limits=Resources(actions=1, verifications=1))
    action = previous.state.attempts[0].action
    stepped = step(previous.state, (action,), budget, policy, {})
    looped = run(previous.state, (action,), budget, policy, {})
    for report in (stepped, looped):
        assert report.state == previous.state
        assert report.stop_reason == "router_stopped"
        assert report.decision.observations_satisfied is True
        assert report.decision.observation_coverage.satisfied == 1
    assert stepped.receipt is None
    assert looped.receipts == ()


def test_needed_acquisition_only_mapping_keeps_other_obligation_pass_applicable() -> None:
    previous = run_callback_example()
    extra = Obligation(
        id="new",
        scope="new-scope",
        description="Acquire another material",
        acceptance="checked",
        required_verifiers=("arithmetic-check",),
    )
    values = {name: getattr(previous.state, name) for name in State.model_fields}
    values["obligations"] = (*previous.state.obligations, extra)
    state = State(**values)
    policy = previous.decision.coverage.policy.model_copy(
        update={
            "available_handlers": None,
            "handlers": (
                *previous.decision.coverage.policy.handlers,
                HandlerRegistration(handler_id="new-reader", roles=("investigate",)),
            ),
        }
    )
    action = ActionCandidate(
        id="new-read",
        obligation_id="new",
        scope="new-scope",
        kind="investigate",
        handler_id="new-reader",
        produces_evidence_id="new-material",
    )

    def reader(view: CallbackView):
        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(
                Evidence(
                    id="new-material",
                    obligation_id="new",
                    scope="new-scope",
                    content="new",
                    digest="c" * 64,
                    producer="new-reader",
                    source="new-source",
                    provenance_group="new-group",
                ),
            ),
        )

    budget = Budget(limits=Resources(actions=2, verifications=2))
    report = step(state, (action,), budget, policy, {"new-reader": reader})
    assert report.stop_reason == "step_completed"
    assert report.decision.observation_coverage.satisfied == 1
    assert report.decision.coverage.required == 2
    assert report.receipt is not None
    assert report.state.checks == previous.state.checks


def exact_dependency_history():
    task = Obligation(
        id="task",
        scope="task",
        description="Inspect target with material",
        acceptance="target and correct material",
        required_verifiers=("v",),
    )
    helper = Obligation(
        id="helper",
        scope="helper",
        description="Supply material",
        acceptance="material",
        required=False,
    )
    state, budget, policy = foundation()
    state = State(obligations=(task, helper))

    def acquire(identifier: str, obligation: Obligation) -> ActionCandidate:
        return ActionCandidate(
            id=f"read-{identifier}",
            obligation_id=obligation.id,
            scope=obligation.scope,
            kind="investigate",
            handler_id="read",
            produces_evidence_id=identifier,
        )

    def read(view: CallbackView):
        identifier = view.action.produces_evidence_id
        assert identifier is not None
        target = identifier == "target"
        evidence = Evidence(
            id=identifier,
            obligation_id=view.obligation.id,
            scope=view.obligation.scope,
            digest=("a" if target else "b") * 64,
            producer="read",
            content="target" if target else "material",
            source="target source" if target else "same material source",
            provenance_group="target group" if target else "same material group",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(evidence,),
        )

    for action in (acquire("target", task), acquire("old-alias", helper)):
        record = step(state, (action,), budget, policy, {"read": read})
        assert record.stop_reason == "step_completed"
        state = record.state
    verify = ActionCandidate(
        id="verify-target",
        obligation_id=task.id,
        scope=task.scope,
        kind="verify",
        handler_id="verify",
        checker_id="v",
        target_evidence_id="target",
        target_digest="a" * 64,
        resources=Resources(actions=1, verifications=1),
        dependencies=(
            DependencyRequirement(
                evidence_id="needed-exact", obligation_id=helper.id, scope=helper.scope
            ),
        ),
    )

    def checker(view: CallbackView):
        records = {item.id: item for item in view.inputs}
        accepted = (
            records["target"].content == "target" and records["needed-exact"].content == "material"
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(
                view.check(
                    status="PASS" if accepted else "FAIL", reason="Compared disclosed material"
                ),
            ),
        )

    return state, budget, policy, acquire("needed-exact", helper), verify, read, checker


def test_EGR020_08_duplicate_information_fulfills_needed_exact_binding_and_continues() -> None:
    state, budget, policy, acquisition, verify, reader, checker = exact_dependency_history()
    assert len(state.attempts) == len(state.results) == 2
    state = load_json(dump_json(state), State)
    before = plan(state, (acquisition, verify), budget, policy)
    assert before.action == acquisition
    report = run(state, (acquisition, verify), budget, policy, {"read": reader, "verify": checker})
    assert report.decision.observations_satisfied is True
    assert report.callback_calls == ("read", "verify")
    assert report.stop_reason == "router_stopped"
    assert len(report.state.attempts) == len(report.state.results) == 4
    assert sum(result.actual_resources.actions for result in report.state.results) == 4
    check = report.state.checks[0]
    assert check.basis is not None
    assert check.basis.dependencies[0].evidence_id == "needed-exact"
    assert {item.id for item in report.state.evidence} == {"target", "old-alias", "needed-exact"}
    assert load_json(dump_json(report.state), State) == report.state


def test_binding_progress_retains_original_pool_without_extra_factory_evaluation() -> None:
    state, budget, policy, acquisition, verify, reader, checker = exact_dependency_history()
    evaluated = []

    def factory(current: State):
        evaluated.append(current)
        return (
            (verify,)
            if any(e.id == "needed-exact" for e in current.evidence)
            else (acquisition, verify)
        )

    report = run(state, factory, budget, policy, {"read": reader, "verify": checker})
    assert report.decision.observations_satisfied is True
    assert report.callback_calls == ("read", "verify")
    assert len(evaluated) == 3
    assert [len(item.results) for item in evaluated] == [2, 3, 4]


def test_arbitrary_alias_ids_without_a_needed_binding_do_not_count_as_progress() -> None:
    state, budget, policy = foundation(min_evidence=2)

    def duplicate(view: CallbackView):
        identifier = view.action.produces_evidence_id
        assert identifier is not None
        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(
                Evidence(
                    id=identifier,
                    obligation_id="o",
                    scope="s",
                    digest="a" * 64,
                    producer="read",
                    content="same",
                    source="same",
                    provenance_group="same",
                ),
            ),
        )

    state = step(state, (acquisition("original"),), budget, policy, {"read": duplicate}).state

    def aliases(current: State):
        return (acquisition(f"alias-{len(current.evidence)}"),)

    report = run(state, aliases, budget, policy, {"read": duplicate}, max_steps=32)
    assert report.stop_reason == "no_progress"
    assert report.callback_calls == ("read",)
    assert len(report.state.evidence) == 2
    assert len(report.state.results) == 2
    assert sum(result.actual_resources.actions for result in report.state.results) == 2


def test_packaged_continuation_example_retains_real_receipts_after_check_withdrawal(
    tmp_path,
) -> None:
    snapshot = tmp_path / "日本語 保存.json"
    report = run_continuation_example(snapshot)
    assert report.decision.observations_satisfied is True
    assert len(report.state.attempts) == len(report.state.results) == 3
    assert len(report.state.evidence) == 1 and len(report.state.checks) == 2
    assert sum(result.actual_resources.actions for result in report.state.results) == 3
    assert sum(result.actual_resources.verifications for result in report.state.results) == 2
    assert len(report.state.invalidations) == 1
    assert report.state.invalidations[0].target_id == report.state.checks[0].id
    assert report.state.checks[0] == report.state.results[1].checks[0]
    assert report.state.evidence[0] == report.state.results[0].evidence[0]
    restored = load_json(snapshot.read_bytes(), State)
    assert restored.results == report.state.results[:2]
    assert restored.checks == report.state.checks[:1]
    assert restored.invalidations == report.state.invalidations
    assert report.callback_calls == ("check",)


def test_duplicate_needed_verified_binding_advances_through_dynamic_checker_factory() -> None:
    state, budget, policy, acquisition, verify, reader, checker = exact_dependency_history()
    helper = state.obligations[1].model_copy(update={"required_verifiers": ("v",)})
    state = State(**{**state.model_dump(), "obligations": (state.obligations[0], helper)})
    old_alias = next(item for item in state.evidence if item.id == "old-alias")
    old_check = ActionCandidate(
        id="verify-old-alias",
        obligation_id=helper.id,
        scope=helper.scope,
        kind="verify",
        handler_id="verify",
        checker_id="v",
        target_evidence_id=old_alias.id,
        target_digest=old_alias.digest,
        resources=Resources(actions=1, verifications=1),
    )

    def material_checker(view: CallbackView):
        accepted = view.inputs[0].content == "material"
        return view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(
                view.check(status="PASS" if accepted else "FAIL", reason="Inspected material"),
            ),
        )

    state = step(state, (old_check,), budget, policy, {"verify": material_checker}).state
    assert len(state.results) == 3
    assert plan(state, (), budget, policy).observation_coverage.satisfied == 0
    verify = verify.model_copy(
        update={
            "dependencies": (
                DependencyRequirement(
                    evidence_id="needed-exact",
                    obligation_id=helper.id,
                    scope=helper.scope,
                    requirement="verified",
                ),
            )
        }
    )
    evaluations = []

    def factory(current: State):
        evaluations.append(len(current.results))
        declared = [acquisition, verify]
        material = next((item for item in current.evidence if item.id == "needed-exact"), None)
        if material is not None:
            declared.append(
                ActionCandidate(
                    id="verify-needed-exact",
                    obligation_id=helper.id,
                    scope=helper.scope,
                    kind="verify",
                    handler_id="verify",
                    checker_id="v",
                    target_evidence_id=material.id,
                    target_digest=material.digest,
                    resources=Resources(actions=1, verifications=1),
                )
            )
        return tuple(declared)

    def selected_checker(view: CallbackView):
        return material_checker(view) if view.obligation.id == "helper" else checker(view)

    report = run(state, factory, budget, policy, {"read": reader, "verify": selected_checker})
    assert report.decision.observations_satisfied is True
    assert report.callback_calls == ("read", "verify", "verify")
    assert evaluations == [3, 4, 5, 6]
    assert len(report.state.attempts) == len(report.state.results) == 6
    assert report.state.checks[-1].basis.dependencies[0].evidence_id == "needed-exact"
    assert report.state.checks[-1].basis.dependencies[0].requirement == "verified"
    assert report.state.results[:3] == state.results
