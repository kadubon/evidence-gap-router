"""Issued-history regressions for EGR020-01/02/03/04/05/09."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    CheckResult,
    Contradiction,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Invalidation,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
    Supersession,
    feasible_actions,
    invalidate,
    load_json,
    make_basis,
    observe,
    plan,
    resolve,
    start,
)
from evidence_gap_router.router import _Evaluation
from evidence_gap_router.runner import CallbackView


def changed(record, **fields):
    return type(record)(**{**record.model_dump(), **fields})


POLICY = Policy(
    trusted_verifiers=("v1", "v2"),
    handlers=(
        HandlerRegistration(handler_id="read", roles=("investigate", "diversify")),
        HandlerRegistration(
            handler_id="verify",
            roles=("verify",),
            checkers=tuple(
                CheckerPermission(
                    checker_id=checker,
                    purposes=("content", "check_resolution", "contradiction_resolution"),
                )
                for checker in ("v1", "v2")
            ),
        ),
    ),
)
BUDGET = Budget(limits=Resources(actions=10000, verifications=10000))


def obligation(identifier="o", **fields):
    return Obligation(
        **{
            "id": identifier,
            "description": "Check integer",
            "scope": "s",
            "acceptance": "nonnegative integer",
            **fields,
        }
    )


def material(identifier="e", oid="o", **fields):
    return Evidence(
        **{
            "id": identifier,
            "obligation_id": oid,
            "scope": "s",
            "producer": "reader",
            "content": "4",
            "digest": sha256(b"4").hexdigest(),
            "source": f"source-{oid}",
            "provenance_group": f"group-{oid}",
            **fields,
        }
    )


def acquire(evidence, identifier=None, **fields):
    return ActionCandidate(
        **{
            "id": identifier or f"read-{evidence.id}",
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            "kind": "investigate",
            "handler_id": "read",
            "produces_evidence_id": evidence.id,
            **fields,
        }
    )


def verifier(evidence, identifier=None, **fields):
    return ActionCandidate(
        **{
            "id": identifier or f"verify-{evidence.id}",
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            "kind": "verify",
            "handler_id": "verify",
            "target_evidence_id": evidence.id,
            "target_digest": evidence.digest,
            "checker_id": "v1",
            "resources": Resources(actions=1, verifications=1),
            **fields,
        }
    )


def dependency(evidence, **fields):
    return DependencyRequirement(
        **{
            "evidence_id": evidence.id,
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            **fields,
        }
    )


def execute(
    state, action, *, evidence=None, contradiction=None, statuses=None, pool=(), policy=POLICY
):
    identifier = f"attempt-{len(state.attempts)}-{action.id}"
    issued = start(state, action, identifier, BUDGET, policy, candidates=pool or (action,))
    attempt = issued.attempts[-1]
    view = CallbackView(
        action=action,
        attempt_id=identifier,
        obligation=next(o for o in state.obligations if o.id == action.obligation_id),
        basis=attempt.basis,
        inputs=tuple(
            next(e for e in state.evidence if e.id == b.evidence_id) for b in attempt.inputs
        ),
    )
    if action.kind == "verify":
        actual = int(view.inputs[0].content) >= 0
        check_statuses = statuses or ("PASS" if actual else "FAIL",)
        checks = tuple(
            changed(
                view.check(status=status, reason="Actual integer comparison"),
                id=f"{identifier}:check:{index}",
            )
            for index, status in enumerate(check_statuses)
        )
        receipt = view.result(actual_resources=Resources(actions=1, verifications=1), checks=checks)
    else:
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=() if evidence is None else (evidence,),
            contradictions=() if contradiction is None else (contradiction,),
        )
    return observe(issued, receipt)


def completed_history(*, oid="o", producer="reader", conflict=False):
    evidence = material(oid=oid, producer=producer)
    state = State(obligations=(obligation(oid),))
    contradiction = (
        Contradiction(
            id="conflict",
            obligation_id=oid,
            scope="s",
            evidence_ids=(evidence.id,),
            reason="Explicit conflict",
        )
        if conflict
        else None
    )
    state = execute(state, acquire(evidence), evidence=evidence, contradiction=contradiction)
    return execute(state, verifier(evidence)), evidence


def invalidation(evidence, *, identifier="invalidate", kind="evidence", target=None, **fields):
    return Invalidation(
        **{
            "id": identifier,
            "kind": kind,
            "target_id": target or evidence.id,
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            "reason": "Host found explicit invalidation grounds",
            **fields,
        }
    )


@pytest.mark.parametrize("kind", ["evidence", "check"])
def test_invalidation_retains_real_receipts_costs_and_exact_id(kind):
    state, evidence = completed_history()
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    target = evidence.id if kind == "evidence" else state.checks[0].id
    event = invalidation(evidence, kind=kind, target=target)
    revised = invalidate(state, event)
    assert revised.evidence == state.evidence
    assert revised.checks == state.checks
    assert revised.attempts == state.attempts and revised.results == state.results
    assert revised.invalidations == (event,)
    assert invalidate(revised, event) is revised
    assert plan(revised, (), BUDGET, POLICY).stop_reason != "satisfied"
    diagnostics = plan(revised, (), BUDGET, POLICY).residuals
    assert any(r.code == f"host_invalidated_{kind}" and target in r.record_ids for r in diagnostics)
    if kind == "evidence":
        assert any(r.code == "ineligible_evidence" and target in r.record_ids for r in diagnostics)
    assert (
        plan(revised, (), BUDGET, POLICY).remaining_resources
        == plan(state, (), BUDGET, POLICY).remaining_resources
    )
    with pytest.raises(ValueError, match="ID collision"):
        invalidate(revised, changed(event, reason="different"))


@pytest.mark.parametrize(
    "fields", [{"target": "absent"}, {"scope": "other"}, {"obligation_id": "other"}]
)
def test_invalidation_unknown_or_wrong_scope_rejected(fields):
    state, evidence = completed_history()
    with pytest.raises(ValueError, match="exact recorded"):
        invalidate(state, invalidation(evidence, **fields))


def test_callback_cannot_supply_invalidation_or_mutate_old_payload():
    state, evidence = completed_history()
    with pytest.raises(ValidationError, match="Extra inputs"):
        Result(**{**state.results[0].model_dump(), "invalidations": (invalidation(evidence),)})
    with pytest.raises(ValueError, match="payload differs"):
        changed(state, evidence=(changed(evidence, expired=True),))


def test_used_verified_dependency_invalidates_only_dependent_basis_and_no_global_cache():
    rules, task, unrelated = (
        material("rules", "rules"),
        material("task", "task"),
        material("other", "other"),
    )
    state = State(obligations=tuple(obligation(e.obligation_id) for e in (rules, task, unrelated)))
    for evidence in (rules, task, unrelated):
        state = execute(state, acquire(evidence), evidence=evidence)
    state = execute(state, verifier(rules))
    state = execute(state, verifier(unrelated))
    state = execute(
        state, verifier(task, dependencies=(dependency(rules, requirement="verified"),))
    )
    assert plan(state, (), BUDGET, POLICY).coverage.ratio == 1
    updated = invalidate(state, invalidation(rules, kind="check", target=state.checks[0].id))
    assert plan(updated, (), BUDGET, POLICY).coverage.satisfied == 1
    assert _Evaluation(updated, POLICY).target_verified(unrelated.id)
    assert not _Evaluation(updated, POLICY).target_verified(task.id)
    assert _Evaluation(state, POLICY).target_verified(task.id)
    assert not _Evaluation(state, changed(POLICY, trusted_verifiers=())).target_verified(task.id)


def test_re_resolution_after_contract_change_is_append_only_and_current_only():
    state, evidence = completed_history(conflict=True)
    action = verifier(
        evidence, "resolve1", purpose="contradiction_resolution", resolution_target_id="conflict"
    )
    state = execute(state, action)
    first = Supersession(
        id="first",
        kind="contradiction",
        target_id="conflict",
        check_id=state.checks[-1].id,
        reason="First contract",
    )
    state = resolve(state, first, POLICY)
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    historical = state
    state = changed(state, obligations=(changed(state.obligations[0], contract_revision="2"),))
    assert plan(state, (), BUDGET, POLICY).stop_reason != "satisfied"
    state = execute(state, verifier(evidence, "content2"))
    state = execute(state, changed(action, id="resolve2"))
    second = Supersession(
        id="second",
        kind="contradiction",
        target_id="conflict",
        check_id=state.checks[-1].id,
        reason="New contract",
    )
    state = resolve(state, second, POLICY)
    assert state.supersessions == (first, second)
    assert state.results[: len(historical.results)] == historical.results
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    assert resolve(state, second, POLICY) is state
    with pytest.raises(ValueError, match="current active grounds"):
        resolve(state, changed(second, id="duplicate"), POLICY)


def test_re_resolution_after_used_dependency_or_resolution_check_invalidation():
    rules, newer, target = material("rules", "rules"), material("new-rules", "rules"), material()
    state = State(obligations=(obligation(), obligation("rules")))
    conflict = Contradiction(
        id="conflict", obligation_id="o", scope="s", evidence_ids=(target.id,), reason="conflict"
    )
    state = execute(state, acquire(target), evidence=target, contradiction=conflict)
    state = execute(state, acquire(rules), evidence=rules)
    state = execute(state, verifier(rules))
    state = execute(state, verifier(target))
    action = verifier(
        target,
        "resolve1",
        purpose="contradiction_resolution",
        resolution_target_id="conflict",
        dependencies=(dependency(rules),),
    )
    state = execute(state, action)
    first = Supersession(
        id="first",
        kind="contradiction",
        target_id="conflict",
        check_id=state.checks[-1].id,
        reason="Old rules",
    )
    state = resolve(state, first, POLICY)
    state = invalidate(state, invalidation(rules))
    get = acquire(newer)
    action2 = changed(action, id="resolve2", dependencies=(dependency(newer),))
    pool = (action2, get, verifier(newer))
    state = execute(state, get, evidence=newer, pool=pool)
    state = execute(state, verifier(newer), pool=pool)
    state = execute(state, action2, pool=pool)
    second = Supersession(
        id="second",
        kind="contradiction",
        target_id="conflict",
        check_id=state.checks[-1].id,
        reason="New rules",
    )
    state = resolve(state, second, POLICY)
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    state = invalidate(
        state,
        invalidation(target, identifier="invalidate-check", kind="check", target=second.check_id),
    )
    assert plan(state, (), BUDGET, POLICY).stop_reason != "satisfied"
    state = execute(state, changed(action2, id="resolve3"))
    third = changed(second, id="third", check_id=state.checks[-1].id)
    state = resolve(state, third, POLICY)
    assert len(state.supersessions) == 3
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"


def test_old_inappropriate_alias_snapshot_retained_but_never_applicable():
    path = Path(__file__).parent / "fixtures" / "v020-wrong-alias-resolution.json"
    state = load_json(path.read_bytes(), State)
    # The fixture was emitted by 0.2.0 using its public issue/observe/resolve APIs.
    assert len(state.attempts) == len(state.results) == 4
    assert len(state.supersessions) == 1
    decision = plan(
        state,
        (),
        BUDGET,
        changed(
            POLICY,
            handlers=tuple(
                changed(h, handler_id="check") if h.handler_id == "verify" else h
                for h in POLICY.handlers
            ),
        ),
    )
    assert decision.stop_reason != "satisfied"
    assert any(
        r.code == "check_failed" and "negative:odd" in r.record_ids for r in decision.residuals
    )
    assert state.supersessions[0].id == "wrong-event"


def test_resolution_subject_id_guard_at_basis_plan_start_observe_and_resolve():
    state = load_json(
        (Path(__file__).parent / "fixtures" / "v020-wrong-alias-resolution.json").read_bytes(),
        State,
    )
    policy = changed(
        POLICY,
        handlers=tuple(
            changed(h, handler_id="check") if h.handler_id == "verify" else h
            for h in POLICY.handlers
        ),
    )
    wrong = changed(state.attempts[-1].action, id="new-wrong")
    with pytest.raises(ValueError, match="subject_id"):
        make_basis(state, wrong)
    assert feasible_actions(state, (wrong,), BUDGET, policy) == ()
    assert plan(state, (wrong,), BUDGET, policy).action is None
    with pytest.raises(ValueError, match="subject_id"):
        start(state, wrong, "new", BUDGET, policy)
    with pytest.raises(ValueError, match="current dedicated"):
        resolve(state, changed(state.supersessions[0], id="again"), policy)
    pending = changed(state, results=state.results[:-1], supersessions=())
    with pytest.raises(ValueError, match="subject_id"):
        observe(pending, state.results[-1])
    no_acceptance = changed(
        state.results[-1],
        id="failed-old-receipt",
        status="failed",
        checks=(),
        supersessions=(),
        reason="Historical callback acceptance rejected",
    )
    recorded_failure = observe(pending, no_acceptance)
    assert recorded_failure.results[-1] == no_acceptance
    assert plan(recorded_failure, (), BUDGET, policy).stop_reason != "satisfied"
    exact = changed(wrong, target_evidence_id="e")
    state = execute(state, changed(exact, handler_id="verify"), policy=POLICY)
    event = Supersession(
        id="correct",
        kind="check",
        target_id="negative:odd",
        replacement_id=state.checks[-1].id,
        reason="Exact subject",
    )
    state = resolve(state, event, POLICY)
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"


def test_self_verification_rejected_before_callback_or_budget_charge():
    evidence = material(producer="v1")
    state = execute(State(obligations=(obligation(),)), acquire(evidence), evidence=evidence)
    action = verifier(evidence)
    assert plan(state, (action,), BUDGET, POLICY).action is None
    assert feasible_actions(state, (action,), BUDGET, POLICY) == ()
    with pytest.raises(ValueError, match="self_verification_forbidden"):
        start(state, action, "never", BUDGET, POLICY)
    assert len(state.results) == 1 and state.results[0].actual_resources.verifications == 0
    permitted = changed(POLICY, prohibit_self_verification=False)
    completed = execute(state, action, policy=permitted)
    assert plan(completed, (), BUDGET, permitted).stop_reason == "satisfied"
    assert plan(completed, (), BUDGET, POLICY).stop_reason != "satisfied"
    assert plan(completed, (), BUDGET, POLICY).remaining_resources.verifications == 9999


def test_satisfied_optional_helper_multistage_exact_dependency_path_and_capacity():
    old, new, raw, target = (
        material("old", "rules"),
        material("new", "rules"),
        material("raw", "raw"),
        material("target", "task"),
    )
    state = State(
        obligations=(
            obligation("rules", required=False),
            obligation("raw", required=False),
            obligation("task"),
        )
    )
    state = execute(state, acquire(old), evidence=old)
    state = execute(state, verifier(old))
    state = execute(state, acquire(target), evidence=target)
    get_raw = acquire(raw)
    get_new = acquire(new, dependencies=(dependency(raw),))
    check_new = verifier(new)
    check_target = verifier(target, dependencies=(dependency(new, requirement="verified"),))
    unrelated = acquire(material("unrelated", "rules"))
    policy = changed(POLICY, max_pending_verifications=1)
    pool = (check_target, get_new, check_new, get_raw, unrelated)
    assert feasible_actions(state, pool, BUDGET, policy) == (get_raw,)
    assert plan(state, pool, BUDGET, policy).action == get_raw
    for action, evidence in (
        (get_raw, raw),
        (get_new, new),
        (check_new, None),
        (check_target, None),
    ):
        assert action in feasible_actions(state, pool, BUDGET, policy)
        state = execute(state, action, evidence=evidence, pool=pool, policy=policy)
    assert plan(state, pool, BUDGET, policy).stop_reason == "satisfied"
    assert feasible_actions(state, pool, BUDGET, policy) == ()
    assert len(state.results) == 7


def test_dynamic_unknown_digest_dependency_acquisition_can_bootstrap_factory():
    target, rules = material("target", "task"), material("new-rules", "rules")
    state = State(obligations=(obligation("task"), obligation("rules", required=False)))
    state = execute(state, acquire(target), evidence=target)
    get = acquire(rules)
    check = verifier(target, dependencies=(dependency(rules, requirement="verified"),))
    policy = changed(POLICY, max_pending_verifications=1)
    assert feasible_actions(state, (check, get), BUDGET, policy) == (get,)
    state = execute(state, get, evidence=rules, pool=(check, get), policy=policy)
    derived = verifier(state.evidence[-1])
    assert derived in feasible_actions(state, (check, derived), BUDGET, policy)
    state = execute(state, derived, pool=(check, derived), policy=policy)
    state = execute(state, check, pool=(check, derived), policy=policy)
    assert plan(state, (), BUDGET, policy).stop_reason == "satisfied"


@pytest.mark.parametrize("defect", ["owner", "scope", "digest"])
def test_wrong_future_dependency_verifier_cannot_exempt_unrelated_acquisition(defect):
    target, helper, unrelated = (
        material("target", "task"),
        material("helper", "helper"),
        material("unrelated", "other"),
    )
    state = State(
        obligations=(
            obligation("task"),
            obligation("helper", required=False),
            obligation("other", required=False),
        )
    )
    state = execute(state, acquire(target), evidence=target)
    get_helper, get_unrelated = acquire(helper), acquire(unrelated)
    wrong = verifier(helper, dependencies=(dependency(unrelated),))
    if defect == "owner":
        wrong = changed(wrong, obligation_id="other")
    elif defect == "scope":
        wrong = changed(wrong, scope="other")
    else:
        wrong = changed(wrong, target_digest="0" * 64)
    consumer = verifier(
        target, dependencies=(dependency(helper, requirement="verified", digest=helper.digest),)
    )
    policy = changed(POLICY, max_pending_verifications=1)
    pool = (consumer, get_helper, wrong, get_unrelated)
    # Dynamic unknown-digest reading is still legal. Wrong future verifier
    # metadata must not grant its unrelated dependency a capacity exception.
    assert feasible_actions(state, pool, BUDGET, policy) == (get_helper,)
    with pytest.raises(ValueError, match="verification_capacity_reached"):
        start(state, get_unrelated, "unrelated", BUDGET, policy, candidates=pool)
    state = execute(state, get_helper, evidence=helper, pool=pool, policy=policy)
    assert get_unrelated not in feasible_actions(state, pool, BUDGET, policy)
    correct = verifier(helper, "correct")
    assert correct in feasible_actions(state, (consumer, correct, get_unrelated), BUDGET, policy)


def test_observed_dependency_digest_mismatch_does_not_bootstrap_wrong_helpers():
    target, helper = material("target", "task"), material("helper", "helper")
    state = State(obligations=(obligation("task"), obligation("helper", required=False)))
    state = execute(state, acquire(target), evidence=target)
    get = acquire(helper)
    consumer = verifier(
        target, dependencies=(dependency(helper, requirement="verified", digest="0" * 64),)
    )
    policy = changed(POLICY, max_pending_verifications=1)
    # Reading an exact ID may discover a digest mismatch; that observation
    # cannot then be used as the claimed current dependency.
    state = execute(state, get, evidence=helper, pool=(consumer, get), policy=policy)
    claimed = verifier(helper, target_digest="0" * 64)
    assert feasible_actions(state, (consumer, claimed), BUDGET, policy) == ()
    assert plan(state, (consumer, claimed), BUDGET, policy).stop_reason != "satisfied"


@pytest.mark.parametrize(
    "case", ["cycle", "wrong_scope", "checker_unavailable", "budget", "contract"]
)
def test_dependency_exemption_rejects_impossible_or_unauthorized_paths(case):
    target, helper = (
        material("target", "task"),
        material("helper", "helper"),
    )
    state = State(
        obligations=(
            obligation("task"),
            obligation("helper", required=False),
            obligation("raw", required=False),
        )
    )
    state = execute(state, acquire(target), evidence=target)
    get = acquire(helper)
    check = verifier(target, dependencies=(dependency(helper, requirement="verified"),))
    policy = changed(POLICY, max_pending_verifications=1)
    budget = BUDGET
    if case == "cycle":
        get = changed(get, dependencies=(dependency(helper),))
    elif case == "wrong_scope":
        get = changed(get, scope="other")
    elif case == "checker_unavailable":
        policy = changed(policy, available_handlers=("read",))
    elif case == "budget":
        budget = Budget(limits=Resources(actions=1, verifications=10))
    else:
        check = changed(
            check,
            dependencies=(
                dependency(helper, requirement="verified", contract_fingerprint="0" * 64),
            ),
        )
    assert get not in feasible_actions(state, (check, get), budget, policy)
    assert plan(state, (check, get), budget, policy).action is None


def test_finite_feasibility_order_shared_start_guards_and_candidate_collisions():
    e1, e2 = material("e1", "o1"), material("e2", "o2")
    state = State(obligations=(obligation("o1"), obligation("o2", priority=10)))
    candidates = (acquire(e1, "z"), acquire(e2, "a"))
    assert feasible_actions(state, candidates, BUDGET, POLICY) == candidates
    assert plan(state, candidates, BUDGET, POLICY).action == candidates[1]
    issued = start(state, candidates[0], "chosen", BUDGET, POLICY, candidates=candidates)
    assert feasible_actions(issued, candidates, BUDGET, POLICY) == ()
    with pytest.raises(ValueError, match="unique"):
        start(
            state, candidates[0], "bad", BUDGET, POLICY, candidates=(candidates[0], candidates[0])
        )
    with pytest.raises(ValueError, match="collision"):
        start(
            state,
            candidates[0],
            "bad",
            BUDGET,
            POLICY,
            candidates=(changed(candidates[0], scope="other"),),
        )


def chain_history(count):
    state = State(
        obligations=tuple(
            obligation(f"o{i}", required_verifiers=("v1", "v2")) for i in range(count)
        )
    )
    for index in range(count):
        evidence = material(f"e{index}", f"o{index}")
        state = execute(state, acquire(evidence), evidence=evidence)
        dependencies = (
            ()
            if index == 0
            else (dependency(material(f"e{index - 1}", f"o{index - 1}"), requirement="verified"),)
        )
        for checker in ("v1", "v2"):
            state = execute(
                state,
                verifier(
                    evidence,
                    f"check-{index}-{checker}",
                    checker_id=checker,
                    dependencies=dependencies,
                ),
            )
    return state


def reference_verified(state, policy, identifier, visiting=frozenset()):
    """Deliberately uncached reference for finite acyclic content-only fixtures."""
    if identifier in visiting:
        return False
    evidence = next(e for e in state.evidence if e.id == identifier)
    obligation = next(o for o in state.obligations if o.id == evidence.obligation_id)
    invalid_e = {i.target_id for i in state.invalidations if i.kind == "evidence"}
    invalid_c = {i.target_id for i in state.invalidations if i.kind == "check"}
    if evidence.id in invalid_e or evidence.expired or evidence.withdrawn:
        return False
    statuses = []
    for check in state.checks:
        basis = check.basis
        if basis is None or basis.target.evidence_id != identifier or check.id in invalid_c:
            continue
        if check.expired or check.withdrawn or check.verifier_id not in policy.trusted_verifiers:
            continue
        if not any(h.allows(basis) for h in policy.handlers):
            continue
        if policy.prohibit_self_verification and evidence.producer == check.verifier_id:
            continue
        if basis.contract_fingerprint != obligation.contract_fingerprint:
            continue
        valid = True
        for binding in basis.dependencies:
            dep = next(e for e in state.evidence if e.id == binding.evidence_id)
            contract = next(o for o in state.obligations if o.id == dep.obligation_id)
            if (
                dep.id in invalid_e
                or dep.expired
                or dep.withdrawn
                or binding.contract_fingerprint != contract.contract_fingerprint
            ):
                valid = False
            if binding.requirement == "verified" and not reference_verified(
                state, policy, dep.id, visiting | {identifier}
            ):
                valid = False
        if valid:
            statuses.append((check.verifier_id, check.status))
    passes = {checker for checker, status in statuses if status == "PASS"}
    return not any(status != "PASS" for _, status in statuses) and (
        set(obligation.required_verifiers).issubset(passes)
        if obligation.required_verifiers
        else bool(passes)
    )


@pytest.mark.parametrize("count", [4, 8, 16, 32])
def test_linear_memoized_chain_matches_uncached_reference(count):
    state = chain_history(count)
    original = _Evaluation._compute_check
    calls = []

    def tracked(self, check):
        calls.append(check.id)
        return original(self, check)

    with patch.object(_Evaluation, "_compute_check", tracked):
        decision = plan(state, (), BUDGET, POLICY)
    assert decision.stop_reason == "satisfied"
    assert len(calls) == len(set(calls)) == len(state.checks)
    # The deliberately exponential reference is kept small while the same
    # structural chain extends to32 to measure the implementation's call bound.
    if count <= 8:
        for evidence in state.evidence:
            assert _Evaluation(state, POLICY).target_verified(evidence.id) == reference_verified(
                state, POLICY, evidence.id
            )


def test_stale_cyclic_alternative_cannot_poison_current_acyclic_support():
    state = chain_history(2)
    e0, e1 = state.evidence
    bad = CheckResult(
        id="stale-cycle",
        obligation_id=e0.obligation_id,
        scope=e0.scope,
        target_digest=e0.digest,
        verifier_id="v1",
        status="PASS",
        reason="Historical cyclic claim",
        basis=make_basis(
            state, verifier(e0, dependencies=(dependency(e1, requirement="verified"),))
        ),
        expired=True,
    )
    with_stale = changed(state, checks=(*state.checks, bad))
    assert plan(with_stale, (), BUDGET, POLICY).stop_reason == "satisfied"
    assert reference_verified(with_stale, POLICY, e1.id)
    revised = changed(with_stale, checks=(*state.checks, changed(bad, expired=False)))
    # Independent grounded support establishes e0 and then e1; the back-edge
    # becomes applicable only after that finite proof exists.
    assert _Evaluation(revised, POLICY).target_verified(e0.id)
    assert _Evaluation(revised, POLICY).trusted_check(revised.checks[-1])
    assert plan(revised, (), BUDGET, POLICY).stop_reason == "satisfied"
    assert reference_verified(revised, POLICY, e1.id)

    # Invalidation removes the finite grounding while preserving every old
    # receipt. The remaining loop cannot create authority for either target.
    for index, check in enumerate(state.checks[:2]):
        revised = invalidate(
            revised, invalidation(e0, identifier=f"ground-{index}", kind="check", target=check.id)
        )
    assert not _Evaluation(revised, POLICY).target_verified(e0.id)
    assert not _Evaluation(revised, POLICY).target_verified(e1.id)
    assert plan(revised, (), BUDGET, POLICY).stop_reason != "satisfied"


def test_grounded_live_alternative_any_checker_and_unknown_negative_cycle():
    a, b = material("a", "a"), material("b", "b")
    state = State(obligations=(obligation("a"), obligation("b")))
    for evidence in (a, b):
        state = execute(state, acquire(evidence), evidence=evidence)
    state = execute(state, verifier(a))
    state = execute(state, verifier(b, dependencies=(dependency(a, requirement="verified"),)))
    alternative = CheckResult(
        id="grounded-back-edge",
        obligation_id=a.obligation_id,
        scope=a.scope,
        target_digest=a.digest,
        verifier_id="v1",
        status="PASS",
        reason="Additional finite proof",
        basis=make_basis(state, verifier(a, dependencies=(dependency(b, requirement="verified"),))),
    )
    grounded = changed(state, checks=(*state.checks, alternative))
    assert plan(grounded, (), BUDGET, POLICY).stop_reason == "satisfied"
    for evidence in (a, b):
        assert _Evaluation(grounded, POLICY).target_verified(evidence.id)
        assert reference_verified(grounded, POLICY, evidence.id)
    ambiguous = changed(grounded, checks=(*state.checks, changed(alternative, status="FAIL")))
    assert not _Evaluation(ambiguous, POLICY).target_verified(a.id)
    assert not _Evaluation(ambiguous, POLICY).target_verified(b.id)
    assert plan(ambiguous, (), BUDGET, POLICY).stop_reason != "satisfied"
    optional_b = changed(
        ambiguous,
        obligations=(ambiguous.obligations[0], changed(ambiguous.obligations[1], required=False)),
    )
    assert plan(optional_b, (), BUDGET, POLICY).stop_reason != "satisfied"
    assert any(
        r.code == "dependency_indeterminate" for r in plan(optional_b, (), BUDGET, POLICY).residuals
    )


def test_diamond_reference_and_worklist_update_bound():
    state = State(obligations=tuple(obligation(i) for i in ("root", "left", "right", "leaf")))
    records = {i: material(i, i) for i in ("root", "left", "right", "leaf")}
    for evidence in records.values():
        state = execute(state, acquire(evidence), evidence=evidence)
    state = execute(state, verifier(records["leaf"]))
    for side in ("left", "right"):
        state = execute(
            state,
            verifier(
                records[side], dependencies=(dependency(records["leaf"], requirement="verified"),)
            ),
        )
    state = execute(
        state,
        verifier(
            records["root"],
            dependencies=tuple(
                dependency(records[side], requirement="verified") for side in ("left", "right")
            ),
        ),
    )
    original = _Evaluation._evaluate_check_truth
    evaluations = []

    def tracked(self, check):
        evaluations.append(check.id)
        return original(self, check)

    with patch.object(_Evaluation, "_evaluate_check_truth", tracked):
        assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    edges = sum(len(c.basis.dependencies) for c in state.checks)
    assert len(evaluations) <= len(state.checks) + edges
    versions = (
        state,
        invalidate(state, invalidation(records["leaf"])),
        changed(
            state,
            obligations=tuple(
                changed(o, contract_revision="2") if o.id == "leaf" else o
                for o in state.obligations
            ),
        ),
    )
    for version in versions:
        for evidence in version.evidence:
            assert _Evaluation(version, POLICY).target_verified(evidence.id) == reference_verified(
                version, POLICY, evidence.id
            )


def test_check_resolution_can_be_repeated_after_resolution_check_invalidation():
    evidence = material()
    state = State(obligations=(obligation(),))
    state = execute(state, acquire(evidence), evidence=evidence)
    state = execute(state, verifier(evidence), statuses=("FAIL",))
    original = state.checks[0]
    action = verifier(
        evidence, "resolution1", purpose="check_resolution", resolution_target_id=original.id
    )
    state = execute(state, action)
    first = Supersession(
        id="first",
        kind="check",
        target_id=original.id,
        replacement_id=state.checks[-1].id,
        reason="First check",
    )
    state = resolve(state, first, POLICY)
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    state = invalidate(state, invalidation(evidence, kind="check", target=first.replacement_id))
    assert any(r.code == "check_failed" for r in plan(state, (), BUDGET, POLICY).residuals)
    state = execute(state, changed(action, id="resolution2"))
    second = changed(first, id="second", replacement_id=state.checks[-1].id)
    state = resolve(state, second, POLICY)
    assert state.supersessions == (first, second)
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"


def test_global_required_satisfaction_prevents_optional_host_start():
    state, evidence = completed_history()
    state = changed(state, obligations=(*state.obligations, obligation("optional", required=False)))
    optional = acquire(material("optional", "optional"))
    assert feasible_actions(state, (optional,), BUDGET, POLICY) == ()
    with pytest.raises(ValueError, match="required_obligations_satisfied"):
        start(state, optional, "extra", BUDGET, POLICY, candidates=(optional,))


def test_supersession_multiple_edges_still_reject_cycle():
    state, evidence = completed_history()
    basis = state.checks[0].basis
    c1 = changed(state.checks[0], id="c1", basis=basis)
    c2 = changed(c1, id="c2")
    c3 = changed(c1, id="c3")
    state = changed(state, checks=(*state.checks, c1, c2, c3))
    events = (
        Supersession(id="a", kind="check", target_id="c1", replacement_id="c2", reason="a"),
        Supersession(id="b", kind="check", target_id="c1", replacement_id="c3", reason="b"),
        Supersession(id="c", kind="check", target_id="c2", replacement_id="c1", reason="c"),
    )
    with pytest.raises(ValueError, match="cycle"):
        changed(state, supersessions=events)
