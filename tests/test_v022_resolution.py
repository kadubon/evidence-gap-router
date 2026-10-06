"""Exact related-input consistency for issued and imported resolution records."""

from __future__ import annotations

from hashlib import sha256

import pytest
from pydantic import ValidationError

from evidence_gap_router import (
    ActionCandidate,
    Attempt,
    Budget,
    CallbackView,
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
    State,
    Supersession,
    VerificationBasis,
    dump_json,
    evidence_binding,
    invalidate,
    load_json,
    make_basis,
    observe,
    plan,
    read_json,
    resolve,
    run,
    start,
    write_json,
)
from evidence_gap_router.router import resolution_fingerprint

POLICY = Policy(
    trusted_verifiers=("checker",),
    handlers=(
        HandlerRegistration(handler_id="read", roles=("investigate",)),
        HandlerRegistration(
            handler_id="verify",
            roles=("verify",),
            checkers=(
                CheckerPermission(
                    checker_id="checker", purposes=("content", "contradiction_resolution")
                ),
            ),
        ),
    ),
)
BUDGET = Budget(limits=Resources(actions=30, verifications=30))
OBLIGATION = Obligation(
    id="readings",
    description="Inspect both readings",
    scope="local",
    acceptance="Readings are nonnegative integers; compare disputed readings explicitly",
    min_evidence=2,
    min_provenance_groups=2,
)


def replace(record, **fields):
    return type(record)(**{**record.model_dump(), **fields})


def material(identifier, content="4", **fields):
    return Evidence(
        **{
            "id": identifier,
            "obligation_id": OBLIGATION.id,
            "scope": OBLIGATION.scope,
            "digest": sha256(content.encode()).hexdigest(),
            "content": content,
            "producer": "collector",
            "source": identifier,
            "provenance_group": identifier,
            **fields,
        }
    )


A, B = material("a"), material("b", "5")
MATERIAL = {e.id: e for e in (A, B)}


def dependency(evidence):
    return DependencyRequirement(
        evidence_id=evidence.id,
        obligation_id=evidence.obligation_id,
        scope=evidence.scope,
    )


def verifier(evidence, identifier=None, **fields):
    return ActionCandidate(
        **{
            "id": identifier or f"check-{evidence.id}",
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            "kind": "verify",
            "handler_id": "verify",
            "target_evidence_id": evidence.id,
            "target_digest": evidence.digest,
            "checker_id": "checker",
            "resources": Resources(actions=1, verifications=1),
            **fields,
        }
    )


def callback(view):
    if view.action.kind != "verify":
        return view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=(MATERIAL[view.action.produces_evidence_id],),
        )
    values = [int(e.content) for e in view.inputs]
    passed = all(value >= 0 for value in values)
    if view.action.purpose == "contradiction_resolution":
        passed = passed and len(values) >= 2 and values[1] - values[0] == 1
    checked = view.check(
        status="PASS" if passed else "FAIL", reason="Computed from the exact disclosed readings"
    )
    events = ()
    if passed and view.action.purpose == "contradiction_resolution":
        events = (
            Supersession(
                id=f"{view.attempt_id}:resolution",
                kind="contradiction",
                target_id=view.action.resolution_target_id,
                check_id=checked.id,
                reason="Compared every declared related reading",
            ),
        )
    return view.result(
        actual_resources=Resources(actions=1, verifications=1),
        checks=(checked,),
        supersessions=events,
    )


HANDLERS = {"read": callback, "verify": callback}


def real_content_history(*, acquire=False):
    state = State(obligations=(OBLIGATION,), evidence=() if acquire else (A, B))
    actions = tuple(verifier(e) for e in (A, B))
    if acquire:
        actions += tuple(
            ActionCandidate(
                id=f"read-{e.id}",
                obligation_id=e.obligation_id,
                scope=e.scope,
                kind="investigate",
                handler_id="read",
                produces_evidence_id=e.id,
                source=e.source,
                provenance_group=e.provenance_group,
            )
            for e in (A, B)
        )
    report = run(state, actions, BUDGET, POLICY, HANDLERS)
    assert report.decision.observations_satisfied is True
    assert len(report.state.results) == (4 if acquire else 2)
    conflict = Contradiction(
        id="disputed",
        obligation_id=OBLIGATION.id,
        scope=OBLIGATION.scope,
        evidence_ids=(A.id, B.id),
        reason="Host requires an explicit joint comparison",
    )
    return replace(report.state, contradictions=(conflict,))


def resolution_action(identifier="resolve-disputed", target=A, dependencies=(B,)):
    return verifier(
        target,
        identifier,
        purpose="contradiction_resolution",
        resolution_target_id="disputed",
        dependencies=tuple(dependency(e) for e in dependencies),
    )


def imported_resolution(state, *, target=A, dependencies=(B,), **basis_fields):
    basis = VerificationBasis(
        **{
            "obligation_id": OBLIGATION.id,
            "scope": OBLIGATION.scope,
            "contract_fingerprint": state.obligations[0].contract_fingerprint,
            "target": evidence_binding(state, target.id),
            "dependencies": tuple(evidence_binding(state, e.id) for e in dependencies),
            "checker_id": "checker",
            "purpose": "contradiction_resolution",
            "resolution_target_id": "disputed",
            "resolution_fingerprint": resolution_fingerprint(state, "contradiction", "disputed"),
            **basis_fields,
        }
    )
    check = CheckResult(
        id="imported-resolution",
        obligation_id=basis.obligation_id,
        scope=basis.scope,
        target_digest=basis.target.digest,
        verifier_id=basis.checker_id,
        status="PASS",
        reason="Externally supplied typed record",
        basis=basis,
    )
    return replace(state, checks=(*state.checks, check)), check


def event(check):
    return Supersession(
        id="imported-event",
        kind="contradiction",
        target_id="disputed",
        check_id=check.id,
        reason="Host requests reuse of the imported check",
    )


def test_partial_related_basis_import_and_old_resolution_history_remain_unaccepted(tmp_path):
    original = real_content_history()
    state, checked = imported_resolution(original, dependencies=())
    disclosed = {b.evidence_id for b in (checked.basis.target, *checked.basis.dependencies)}
    assert set(state.contradictions[0].evidence_ids) - disclosed == {B.id}
    assert len(state.results) == 2 and state.results == original.results
    assert plan(state, (), BUDGET, POLICY).stop_reason == "blocked"
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(state, event(checked), POLICY)

    # Ordinary typed State input preserves a formerly accepted old event unchanged.
    history = replace(state, supersessions=(event(checked),))
    path = tmp_path / "old partial resolution.json"
    write_json(history, path)
    loaded = read_json(path, State)
    assert loaded == history == load_json(dump_json(history), State)
    assert loaded.checks[-1] == checked and loaded.supersessions == (event(checked),)
    assert loaded.results == original.results and loaded.attempts == original.attempts
    assert plan(loaded, (), BUDGET, POLICY).stop_reason == "blocked"
    assert sum(r.actual_resources.actions for r in loaded.results) == 2


def test_partial_resolution_is_excluded_before_issuance_and_new_receipt_acceptance():
    state = real_content_history()
    action = resolution_action(dependencies=())
    decision = plan(state, (action,), BUDGET, POLICY)
    assert decision.action is None
    assert "resolution_related_evidence_missing" in decision.exclusions[0].reasons
    with pytest.raises(ValueError, match="resolution_related_evidence_missing"):
        make_basis(state, action)
    with pytest.raises(ValueError, match="resolution_related_evidence_missing"):
        start(state, action, "new-partial", BUDGET, POLICY)

    # A typed externally supplied attempt can be retained as history, but a new
    # callback's incomplete resolution cannot bypass observe's mechanical check.
    imported, checked = imported_resolution(state, dependencies=())
    attempt = Attempt(
        id="external-issued",
        action=action,
        registration=POLICY.handlers[1],
        basis=checked.basis,
        inputs=(checked.basis.target,),
    )
    issued = replace(imported, attempts=(*imported.attempts, attempt))
    view = CallbackView(
        action=action,
        attempt_id=attempt.id,
        obligation=OBLIGATION,
        basis=attempt.basis,
        inputs=(A,),
    )
    receipt = callback(view)
    with pytest.raises(ValueError, match="resolution_related_evidence_missing"):
        observe(issued, receipt, POLICY)
    uncertain = view.result(
        actual_resources=Resources(actions=1, verifications=None),
        status="unknown",
        side_effects="unknown",
        reason="Incomplete externally issued verification was actually invoked",
    )
    retained = observe(issued, uncertain, POLICY)
    assert retained.results[-1].actual_resources.actions == 1
    assert plan(retained, (), BUDGET, POLICY).stop_reason == "escalation_required"


@pytest.mark.parametrize("target_alias", [False, True])
def test_equal_digest_alias_cannot_replace_an_exact_related_input(target_alias):
    state = real_content_history()
    alias = material("alias", A.content if target_alias else B.content)
    state = replace(state, evidence=(*state.evidence, alias))
    target, dependencies = (alias, (A, B)) if target_alias else (A, (alias,))
    imported, checked = imported_resolution(state, target=target, dependencies=dependencies)
    assert plan(imported, (), BUDGET, POLICY).stop_reason == "blocked"
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(imported, event(checked), POLICY)
    with pytest.raises(ValueError, match="resolution_related_evidence_missing"):
        make_basis(state, resolution_action(target=target, dependencies=dependencies))


@pytest.mark.parametrize("field", ["digest", "obligation_id", "scope"])
def test_imported_related_binding_must_match_the_recorded_identity(field):
    state = real_content_history()
    state, checked = imported_resolution(state)
    binding = replace(
        checked.basis.dependencies[0], **{field: "0" * 64 if field == "digest" else "wrong"}
    )
    changed_basis = replace(checked.basis, dependencies=(binding,))
    changed_check = replace(checked, basis=changed_basis)
    with pytest.raises(ValidationError, match="mismatched evidence ID/digest/scope"):
        replace(state, checks=(*state.checks[:-1], changed_check))


@pytest.mark.parametrize("mismatch", ["dependency_contract", "checker_revision", "fingerprint"])
def test_complete_imported_basis_still_needs_current_contract_permission_and_fingerprint(mismatch):
    state = real_content_history()
    fields = {}
    if mismatch == "dependency_contract":
        state, checked = imported_resolution(state)
        binding = replace(evidence_binding(state, B.id), contract_fingerprint="0" * 64)
        checked = replace(checked, basis=replace(checked.basis, dependencies=(binding,)))
        state = replace(state, checks=(*state.checks[:-1], checked))
    elif mismatch == "checker_revision":
        fields["checker_revision"] = "unregistered"
    else:
        fields["resolution_fingerprint"] = "0" * 64
    if mismatch != "dependency_contract":
        state, checked = imported_resolution(state, **fields)
    assert load_json(dump_json(state), State) == state
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(state, event(checked), POLICY)


def test_valid_imported_all_related_resolution_remains_supported_and_reusable():
    state = real_content_history()
    state, checked = imported_resolution(state)
    resolved = resolve(state, event(checked), POLICY)
    assert plan(resolved, (), BUDGET, POLICY).observations_satisfied is True
    assert resolved.results == state.results and len(resolved.results) == 2
    assert resolve(resolved, event(checked), POLICY) == resolved
    unrelated = material("unrelated", "4", source=A.source, provenance_group=A.provenance_group)
    unchanged = replace(resolved, evidence=(*resolved.evidence, unrelated))
    assert plan(unchanged, (), BUDGET, POLICY).observations_satisfied is True


def test_valid_seed_content_checks_and_full_related_resolution_remain_supported():
    state = State(obligations=(OBLIGATION,), evidence=(A, B))
    checks = tuple(
        CheckResult(
            id=f"external-content-{e.id}",
            obligation_id=e.obligation_id,
            scope=e.scope,
            target_digest=e.digest,
            verifier_id="checker",
            status="PASS" if int(e.content) >= 0 else "FAIL",
            reason="External host compared the supplied integer with zero",
            basis=make_basis(state, verifier(e)),
        )
        for e in (A, B)
    )
    state = replace(state, checks=checks)
    assert not state.attempts and not state.results
    assert plan(state, (), BUDGET, POLICY).observations_satisfied is True
    conflict = Contradiction(
        id="disputed",
        obligation_id=OBLIGATION.id,
        scope=OBLIGATION.scope,
        evidence_ids=(A.id, B.id),
        reason="Host requires joint inspection",
    )
    state, checked = imported_resolution(replace(state, contradictions=(conflict,)))
    resolved = resolve(state, event(checked), POLICY)
    assert plan(resolved, (), BUDGET, POLICY).observations_satisfied is True
    assert resolved.checks[:2] == checks and not resolved.results


def test_content_purpose_cannot_reuse_a_full_basis_to_resolve_a_contradiction():
    state = real_content_history()
    state, checked = imported_resolution(
        state, purpose="content", resolution_target_id=None, resolution_fingerprint=None
    )
    history = replace(state, supersessions=(event(checked),))
    assert plan(load_json(dump_json(history), State), (), BUDGET, POLICY).stop_reason == "blocked"
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(state, event(checked), POLICY)


def test_current_policy_must_still_allow_the_resolution_checker_purpose():
    state, checked = imported_resolution(real_content_history())
    resolved = resolve(state, event(checked), POLICY)
    registration = replace(POLICY.handlers[1], checkers=(CheckerPermission(checker_id="checker"),))
    policy = replace(POLICY, handlers=(POLICY.handlers[0], registration))
    assert plan(resolved, (), BUDGET, policy).stop_reason == "blocked"
    assert resolved.results == state.results and resolved.checks[-1] == checked


def test_resolution_event_cannot_reuse_a_check_bound_to_another_conflict():
    state = real_content_history()
    other = replace(state.contradictions[0], id="another-conflict")
    state = replace(state, contradictions=(*state.contradictions, other))
    state, checked = imported_resolution(
        state,
        resolution_target_id=other.id,
        resolution_fingerprint=resolution_fingerprint(state, "contradiction", other.id),
    )
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(state, event(checked), POLICY)
    history = replace(state, supersessions=(event(checked),))
    assert plan(load_json(dump_json(history), State), (), BUDGET, POLICY).stop_reason == "blocked"


def test_real_acquisition_resolution_invalidation_save_load_and_re_resolution(tmp_path):
    state = real_content_history(acquire=True)
    original_results = state.results
    first = run(state, (resolution_action(),), BUDGET, POLICY, HANDLERS)
    assert first.decision.observations_satisfied is True and len(first.callback_calls) == 1
    resolution_check = first.state.checks[-1]
    assert {
        b.evidence_id for b in (resolution_check.basis.target, *resolution_check.basis.dependencies)
    } == {A.id, B.id}
    stale = invalidate(
        first.state,
        Invalidation(
            id="host-expiry",
            kind="check",
            target_id=resolution_check.id,
            obligation_id=OBLIGATION.id,
            scope=OBLIGATION.scope,
            reason="Host requires a new comparison",
        ),
    )
    write_json(stale, tmp_path / "日本語 checkpoint.json")
    resumed = read_json(tmp_path / "日本語 checkpoint.json", State)
    assert plan(resumed, (), BUDGET, POLICY).stop_reason == "blocked"
    second = run(resumed, (resolution_action("resolve-again"),), BUDGET, POLICY, HANDLERS)
    assert second.decision.observations_satisfied is True and len(second.callback_calls) == 1
    assert second.state.results[:4] == original_results
    assert len(second.state.attempts) == len(second.state.results) == 6
    assert len(second.state.supersessions) == 2
    assert sum(r.actual_resources.actions for r in second.state.results) == 6
    assert sum(r.actual_resources.verifications for r in second.state.results) == 4


def test_contract_change_requires_new_content_checks_and_actual_new_resolution():
    state = real_content_history(acquire=True)
    first = run(state, (resolution_action(),), BUDGET, POLICY, HANDLERS)
    updated = replace(first.state, obligations=(replace(OBLIGATION, contract_revision="2"),))
    assert plan(updated, (), BUDGET, POLICY).stop_reason == "blocked"
    pool = (
        verifier(A, "new-content-a"),
        verifier(B, "new-content-b"),
        resolution_action("new-resolution"),
    )
    second = run(updated, pool, BUDGET, POLICY, HANDLERS)
    assert second.decision.observations_satisfied is True and len(second.callback_calls) == 3
    assert second.state.results[:5] == first.state.results
    assert len(second.state.supersessions) == 2
    assert load_json(dump_json(second.state), State) == second.state


def test_related_evidence_invalidation_reopens_resolution_and_retains_charged_history():
    state = real_content_history(acquire=True)
    first = run(state, (resolution_action(),), BUDGET, POLICY, HANDLERS)
    stale = invalidate(
        first.state,
        Invalidation(
            id="input-expiry",
            kind="evidence",
            target_id=B.id,
            obligation_id=B.obligation_id,
            scope=B.scope,
            reason="Reading no longer current",
        ),
    )
    assert stale.results == first.state.results and stale.supersessions == first.state.supersessions
    assert plan(load_json(dump_json(stale), State), (), BUDGET, POLICY).stop_reason == "blocked"
    with pytest.raises(ValueError, match="authorized current dedicated"):
        resolve(stale, replace(first.state.supersessions[0], id="new-event"), POLICY)


def test_supplemental_dependency_update_requires_actual_new_resolution(tmp_path):
    state = real_content_history()
    helper = Obligation(
        id="rules", description="Local rule", scope="rule", acceptance="nonnegative", required=False
    )
    old = material(
        "old-rule", "1", obligation_id=helper.id, scope=helper.scope, producer="host-seed"
    )
    state = replace(
        state, obligations=(*state.obligations, helper), evidence=(*state.evidence, old)
    )
    first = run(state, (resolution_action(dependencies=(B, old)),), BUDGET, POLICY, HANDLERS)
    assert first.decision.observations_satisfied is True
    stale = invalidate(
        first.state,
        Invalidation(
            id="rule-update",
            kind="evidence",
            target_id=old.id,
            obligation_id=helper.id,
            scope=helper.scope,
            reason="Host replaced its rule",
        ),
    )
    assert plan(stale, (), BUDGET, POLICY).stop_reason == "blocked"
    new = material(
        "new-rule", "2", obligation_id=helper.id, scope=helper.scope, producer="host-seed"
    )
    updated = replace(stale, evidence=(*stale.evidence, new))
    write_json(updated, tmp_path / "rule continuation.json")
    second = run(
        read_json(tmp_path / "rule continuation.json", State),
        (resolution_action("new-rule-resolution", dependencies=(B, new)),),
        BUDGET,
        POLICY,
        HANDLERS,
    )
    assert second.decision.observations_satisfied is True and len(second.callback_calls) == 1
    assert second.state.results[:3] == first.state.results
    assert len(second.state.supersessions) == 2
    assert sum(r.actual_resources.actions for r in second.state.results) == 4


def test_delayed_complete_resolution_receipt_is_retained_but_stale_contract_cannot_accept():
    state = real_content_history()
    action = resolution_action()
    issued = start(state, action, "delayed", BUDGET, POLICY)
    view = CallbackView(
        action=action,
        attempt_id="delayed",
        obligation=OBLIGATION,
        basis=issued.attempts[-1].basis,
        inputs=(A, B),
    )
    receipt = callback(view)
    updated = replace(issued, obligations=(replace(OBLIGATION, contract_revision="2"),))
    observed = observe(updated, receipt, POLICY)
    assert observed.results[-1] == receipt and observed.results[-1].actual_resources.actions == 1
    assert plan(observed, (), BUDGET, POLICY).stop_reason == "blocked"
