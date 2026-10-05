"""Finite candidate-helper reachability, independent of proof-graph memoization."""

from __future__ import annotations

from hashlib import sha256
from random import Random
from unittest.mock import patch

import pytest

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Invalidation,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
    feasible_actions,
    invalidate,
    observe,
    plan,
    start,
)
from evidence_gap_router.router import _HelperGraph, _needed_helper_actions
from evidence_gap_router.runner import CallbackView

POLICY = Policy(
    trusted_verifiers=("v1", "v2"),
    max_pending_verifications=1,
    handlers=(
        HandlerRegistration(handler_id="read", roles=("investigate",)),
        HandlerRegistration(
            handler_id="verify",
            roles=("verify",),
            checkers=tuple(CheckerPermission(checker_id=v) for v in ("v1", "v2")),
        ),
    ),
)
BUDGET = Budget(limits=Resources(actions=10000, verifications=10000))


def changed(value, **fields):
    return type(value)(**{**value.model_dump(), **fields})


def material(identifier, owner="helper", *, scope=None, **fields):
    content = str(identifier)
    return Evidence(
        id=identifier,
        obligation_id=owner,
        scope=scope or owner,
        producer="reader",
        content=content,
        digest=sha256(content.encode()).hexdigest(),
        source=identifier,
        provenance_group=identifier,
        **fields,
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


def read(evidence, identifier=None, **fields):
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


def verify(evidence, identifier=None, **fields):
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


def initial_state():
    root = material("root", "task")
    state = State(
        obligations=(
            Obligation(id="task", description="Validate root", scope="task", acceptance="typed"),
            Obligation(
                id="helper",
                description="Material",
                scope="helper",
                acceptance="typed",
                required=False,
            ),
        )
    )
    action = read(root)
    issued = start(state, action, "initial", BUDGET, POLICY)
    state = observe(
        issued,
        Result(
            id="initial-result",
            attempt_id="initial",
            action_id=action.id,
            obligation_id=action.obligation_id,
            scope=action.scope,
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(root,),
        ),
    )
    return state, root


def helper_chain(depth, alternatives=2):
    state, root = initial_state()
    evidence = tuple(material(f"h{i}") for i in range(depth))
    acquisitions = tuple(
        read(
            evidence[i],
            f"read-h{i}-{alternative}",
            dependencies=() if i == 0 else (dependency(evidence[i - 1]),),
        )
        for i in range(depth)
        for alternative in range(alternatives)
    )
    consumer = verify(root, dependencies=(dependency(evidence[-1]),))
    return state, (consumer, *acquisitions), evidence


def execute(state, action, *, evidence=None, pool=(), policy=POLICY):
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
        valid = all(
            e.content is not None and sha256(e.content.encode()).hexdigest() == e.digest
            for e in view.inputs
        )
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(view.check(status="PASS" if valid else "FAIL", reason="Raw text digest"),),
        )
    else:
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=() if evidence is None else (evidence,),
        )
    return observe(issued, receipt)


def reference_active_helpers(state, pool, budget=BUDGET, policy=POLICY):
    """Small independent exhaustive paths for active acquisition dependencies.

    This reference deliberately does not use the production graph or private
    acceptance helpers. Verification groups have separate actual-history tests.
    """
    owners = {o.id: o for o in state.obligations}
    records = {e.id: e for e in state.evidence}
    handlers = {h.handler_id: h for h in policy.handlers}
    invalid = {i.target_id for i in state.invalidations if i.kind == "evidence"}
    producers = {}
    for action in pool:
        if action.kind != "verify":
            producers.setdefault(action.produces_evidence_id, []).append(action)

    def allowed(action):
        owner = owners.get(action.obligation_id)
        handler = handlers.get(action.handler_id)
        if owner is None or owner.scope != action.scope or handler is None:
            return False
        if action.kind not in handler.roles or any(
            a.action.id == action.id for a in state.attempts
        ):
            return False
        if (
            policy.available_handlers is not None
            and action.handler_id not in policy.available_handlers
        ):
            return False
        if policy.executable_handlers and action.handler_id not in policy.executable_handlers:
            return False
        if action.kind == "verify" and not any(
            p.checker_id == action.checker_id
            and p.revision == action.checker_revision
            and action.purpose in p.purposes
            for p in handler.checkers
        ):
            return False
        for dimension in ("actions", "verifications", "tokens"):
            limit = getattr(budget.limits, dimension)
            cost = getattr(action.resources, dimension)
            spent = sum(getattr(r.actual_resources, dimension) or 0 for r in state.results)
            if limit is not None and (cost is None or cost > max(0, limit - spent)):
                return False
        return True

    def action_path(action, visiting):
        if action.id in visiting or not allowed(action):
            return None
        result = {action.id}
        for requirement in action.dependencies:
            assert requirement.requirement in ("active", "exists")
            owner = owners.get(requirement.obligation_id)
            if (
                owner is None
                or owner.scope != requirement.scope
                or (
                    requirement.contract_fingerprint is not None
                    and requirement.contract_fingerprint != owner.contract_fingerprint
                )
            ):
                return None
            record = records.get(requirement.evidence_id)
            if record is not None:
                if (record.obligation_id, record.scope) != (
                    requirement.obligation_id,
                    requirement.scope,
                ):
                    return None
                if requirement.digest is not None and record.digest != requirement.digest:
                    return None
                if requirement.requirement != "exists" and (
                    record.withdrawn or record.expired or record.id in invalid
                ):
                    return None
                continue
            paths = [
                path
                for producer in producers.get(requirement.evidence_id, ())
                if (producer.obligation_id, producer.scope)
                == (requirement.obligation_id, requirement.scope)
                and (path := action_path(producer, visiting | {action.id})) is not None
            ]
            if not paths:
                return None
            result.update(*paths)
        return result

    result = set()
    for root in pool:
        if root.kind == "verify" and owners[root.obligation_id].required:
            path = action_path(root, frozenset())
            if path is not None:
                result.update(path - {root.id})
    return frozenset(result)


@pytest.mark.parametrize("alternatives", [1, 2, 4])
def test_chain_retains_all_grounded_alternatives_and_exact_start(alternatives):
    state, pool, _ = helper_chain(6, alternatives)
    helpers = _needed_helper_actions(state, pool, BUDGET, POLICY)
    assert helpers == {a.id for a in pool if a.kind != "verify"}
    ready = tuple(a for a in pool if a.kind != "verify" and not a.dependencies)
    assert feasible_actions(state, pool, BUDGET, POLICY) == ready
    for action in ready:
        assert (
            start(state, action, f"try-{action.id}", BUDGET, POLICY, candidates=pool)
            .attempts[-1]
            .action
            == action
        )
    assert plan(state, pool, BUDGET, POLICY).action in ready


def test_known_global_stops_do_not_expand_helper_graph():
    state, pool, _ = helper_chain(8)
    issued = start(state, pool[1], "pending", BUDGET, POLICY, candidates=pool)
    with patch(
        "evidence_gap_router.router._helper_actions", side_effect=AssertionError("expanded")
    ):
        decision = plan(issued, pool, BUDGET, POLICY)
        assert decision.stop_reason == "blocked"
        assert feasible_actions(issued, pool, BUDGET, POLICY) == ()
        assert _needed_helper_actions(issued, pool, BUDGET, POLICY) == frozenset()
    assert all("attempt_pending" in e.reasons for e in decision.exclusions)


@pytest.mark.parametrize("depth", [4, 8, 12, 16, 32, 64])
@pytest.mark.parametrize("alternatives", [1, 2, 4])
def test_structural_edge_visits_are_linear_for_one_shared_root(depth, alternatives):
    state, pool, _ = helper_chain(depth, alternatives)
    visits = 0
    original = _HelperGraph._consume_edge

    def counted(graph, rule, pending):
        nonlocal visits
        visits += 1
        return original(graph, rule, pending)

    with patch.object(_HelperGraph, "_consume_edge", counted):
        helpers = _needed_helper_actions(state, pool, BUDGET, POLICY)
    assert len(helpers) == depth * alternatives
    # Candidate/material dependency incidence, not the number of proof paths.
    incidence = len(pool) + sum(len(a.dependencies) for a in pool)
    assert visits <= 4 * incidence


@pytest.mark.parametrize("seed", range(12))
def test_small_and_or_cycles_diamonds_and_permutations_match_independent_reference(seed):
    rng = Random(seed)
    state, root = initial_state()
    items = tuple(material(f"m{i}") for i in range(5))
    actions = tuple(
        read(
            e,
            f"choice-{i}-{j}",
            dependencies=tuple(
                dependency(items[d]) for d in rng.sample(range(5), rng.randrange(3))
            ),
        )
        for i, e in enumerate(items)
        for j in range(2)
    )
    consumer = verify(root, dependencies=(dependency(items[3]), dependency(items[4])))
    pool = (consumer, *actions)
    expected = reference_active_helpers(state, pool)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == expected
    shuffled = list(pool)
    rng.shuffle(shuffled)
    assert _needed_helper_actions(state, tuple(shuffled), BUDGET, POLICY) == expected
    mapping = {a.id: f"renamed-{i:03}" for i, a in enumerate(reversed(pool))}
    renamed = tuple(changed(a, id=mapping[a.id]) for a in shuffled)
    assert _needed_helper_actions(state, renamed, BUDGET, POLICY) == {mapping[i] for i in expected}


def test_pure_cycle_blocks_but_grounded_exit_retains_all_viable_routes():
    state, root = initial_state()
    h1, h2 = material("h1"), material("h2")
    cycle1 = read(h1, "cycle-1", dependencies=(dependency(h2),))
    cycle2 = read(h2, "cycle-2", dependencies=(dependency(h1),))
    consumer = verify(root, dependencies=(dependency(h1),))
    pool = (consumer, cycle1, cycle2)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == frozenset()
    assert feasible_actions(state, pool, BUDGET, POLICY) == ()
    exit_action = read(h1, "grounded-exit")
    pool = (*pool, exit_action)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == reference_active_helpers(
        state, pool
    )
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == {
        cycle1.id,
        cycle2.id,
        exit_action.id,
    }
    assert feasible_actions(state, pool, BUDGET, POLICY) == (exit_action,)
    state = execute(state, exit_action, evidence=h1, pool=pool)
    assert feasible_actions(state, pool, BUDGET, POLICY) == (consumer,)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == frozenset()


def test_consuming_root_cannot_ground_unneeded_helper_cycle_after_its_own_completion():
    state, root = initial_state()
    helper, needed, unrelated = material("h"), material("needed"), material("unrelated")
    consumer = verify(root, dependencies=(dependency(helper, requirement="verified"),))
    exit_check = verify(helper, "exit-check", dependencies=(dependency(needed),))
    cycle_check = verify(
        helper,
        "cycle-check",
        dependencies=(dependency(root, requirement="verified"), dependency(unrelated)),
    )
    pool = (consumer, read(helper), exit_check, cycle_check, read(needed), read(unrelated))
    state = execute(state, read(helper), evidence=helper, pool=pool)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == {exit_check.id, read(needed).id}
    assert feasible_actions(state, pool, BUDGET, POLICY) == (read(needed),)
    with pytest.raises(ValueError, match="verification_capacity_reached"):
        start(state, read(unrelated), "wrong", BUDGET, POLICY, candidates=pool)


def test_required_checker_groups_are_and_alternatives_and_partial_pass_is_reused():
    state, root = initial_state()
    helper_owner = changed(state.obligations[1], required_verifiers=("v1", "v2"))
    state = changed(state, obligations=(state.obligations[0], helper_owner))
    h, x, y = material("h"), material("x"), material("y")
    consumer = verify(root, dependencies=(dependency(h, requirement="verified"),))
    c1 = verify(h, "check-v1", dependencies=(dependency(x),))
    c2 = verify(h, "check-v2", checker_id="v2", dependencies=(dependency(y),))
    pool = (consumer, read(h), c1, c2, read(x), read(y))
    state = execute(state, read(h), evidence=h, pool=pool)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == {
        c1.id,
        c2.id,
        read(x).id,
        read(y).id,
    }
    forbidden = tuple(changed(a, handler_id="absent") if a == c2 else a for a in pool)
    assert _needed_helper_actions(state, forbidden, BUDGET, POLICY) == frozenset()
    assert feasible_actions(state, forbidden, BUDGET, POLICY) == ()
    state = execute(state, read(x), evidence=x, pool=pool)
    state = execute(state, c1, pool=pool)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == {c2.id, read(y).id}
    state = execute(state, read(y), evidence=y, pool=pool)
    state = execute(state, c2, pool=pool)
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == frozenset()
    state = execute(state, consumer, pool=pool)
    assert plan(state, pool, BUDGET, POLICY).stop_reason == "satisfied"
    assert len(state.results) == 7


def test_no_cross_call_cache_for_budget_authority_contract_candidate_or_invalidation():
    state, pool, materials = helper_chain(3)
    expected = {a.id for a in pool if a.kind != "verify"}
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == expected
    assert (
        _needed_helper_actions(
            state, pool, Budget(limits=Resources(actions=1, verifications=100)), POLICY
        )
        == frozenset()
    )
    assert (
        _needed_helper_actions(state, pool, BUDGET, changed(POLICY, available_handlers=("verify",)))
        == frozenset()
    )
    revised_handler = changed(
        POLICY.handlers[1], checkers=(CheckerPermission(checker_id="v1", revision="2"),)
    )
    assert (
        _needed_helper_actions(
            state, pool, BUDGET, changed(POLICY, handlers=(POLICY.handlers[0], revised_handler))
        )
        == frozenset()
    )
    damaged = tuple(
        changed(a, scope="wrong") if a.produces_evidence_id == "h0" else a for a in pool
    )
    assert _needed_helper_actions(state, damaged, BUDGET, POLICY) == frozenset()
    owner = state.obligations[1]
    bound = tuple(
        changed(
            a,
            dependencies=tuple(
                changed(d, contract_fingerprint=owner.contract_fingerprint) for d in a.dependencies
            ),
        )
        for a in pool
    )
    revised = changed(state, obligations=(state.obligations[0], changed(owner, acceptance="new")))
    assert _needed_helper_actions(revised, bound, BUDGET, POLICY) == frozenset()
    state = execute(state, pool[1], evidence=materials[0], pool=pool)
    assert pool[1].id not in _needed_helper_actions(state, pool, BUDGET, POLICY)
    state = invalidate(
        state,
        Invalidation(
            id="withdraw-first",
            kind="evidence",
            target_id=materials[0].id,
            obligation_id="helper",
            scope="helper",
            reason="Host update",
        ),
    )
    assert _needed_helper_actions(state, pool, BUDGET, POLICY) == frozenset()


def test_global_resource_and_completion_stops_keep_residuals_without_helper_expansion():
    state, pool, _ = helper_chain(3)
    issued = start(state, pool[1], "unknown", BUDGET, POLICY, candidates=pool)
    unsafe = observe(
        issued,
        Result(
            id="unknown-result",
            attempt_id="unknown",
            action_id=pool[1].id,
            obligation_id="helper",
            scope="helper",
            status="unknown",
            actual_resources=Resources(actions=1, verifications=None),
        ),
    )
    root = state.evidence[0]
    complete = execute(state, verify(root, "complete-root"))
    with patch(
        "evidence_gap_router.router._helper_actions", side_effect=AssertionError("expanded")
    ):
        assert plan(unsafe, pool, BUDGET, POLICY).stop_reason == "escalation_required"
        assert feasible_actions(unsafe, pool, BUDGET, POLICY) == ()
        assert plan(complete, pool, BUDGET, POLICY).stop_reason == "satisfied"
        assert feasible_actions(complete, pool, BUDGET, POLICY) == ()
    assert any(r.code == "unknown_resource" for r in plan(unsafe, pool, BUDGET, POLICY).residuals)
