"""Acceptance-boundary regressions for A01-A07/A12 and schema migration."""

from __future__ import annotations

import hashlib
import json

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
    Obligation,
    PlanInput,
    Policy,
    Resources,
    Result,
    State,
    Supersession,
    dump_json,
    evidence_binding,
    load_json,
    make_basis,
    migrate_v1_file,
    migrate_v1_json,
    observe,
    plan,
    resolve,
    start,
)


def update(record, **fields):
    return type(record)(**{**record.model_dump(), **fields})


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


DATA = Obligation(
    id="dataset", description="Validate orders", scope="orders", acceptance="amount satisfies rules"
)
RULES = Obligation(
    id="rules", description="Validate rules", scope="orders", acceptance="well-formed rules"
)
E = Evidence(
    id="orders",
    obligation_id=DATA.id,
    scope=DATA.scope,
    digest=digest("10"),
    producer="reader",
    content="10",
    source="orders.csv",
    provenance_group="orders",
)
D = Evidence(
    id="rules-1",
    obligation_id=RULES.id,
    scope=RULES.scope,
    digest=digest("minimum=0"),
    producer="rules-reader",
    content="minimum=0",
    source="rules.json",
    provenance_group="rules",
)
POLICY = Policy(
    trusted_verifiers=("v1", "v2"),
    handlers=(
        HandlerRegistration(handler_id="read", roles=("investigate", "diversify")),
        HandlerRegistration(
            handler_id="verify",
            roles=("verify",),
            checkers=(
                CheckerPermission(
                    checker_id="v1",
                    purposes=("content", "check_resolution", "contradiction_resolution"),
                ),
                CheckerPermission(
                    checker_id="v2",
                    purposes=("content", "check_resolution", "contradiction_resolution"),
                ),
            ),
        ),
    ),
)
BUDGET = Budget(limits=Resources(actions=10, verifications=10))


def action(evidence, **fields):
    return ActionCandidate(
        **{
            "id": "check-" + evidence.id,
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


def check(state, candidate, identifier="pass", status="PASS"):
    return CheckResult(
        id=identifier,
        obligation_id=candidate.obligation_id,
        scope=candidate.scope,
        target_digest=candidate.target_digest,
        verifier_id=candidate.checker_id,
        status=status,
        reason="computed by the registered checker",
        basis=make_basis(state, candidate),
    )


def initial(evidence=(E, D), obligations=(DATA, RULES), **fields):
    return State(obligations=obligations, evidence=evidence, **fields)


def acquired(**fields):
    return ActionCandidate(
        **{
            "id": "acquire",
            "obligation_id": DATA.id,
            "scope": DATA.scope,
            "kind": "investigate",
            "handler_id": "read",
            **fields,
        }
    )


def dependency(evidence=D, **fields):
    return DependencyRequirement(
        **{
            "evidence_id": evidence.id,
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            **fields,
        }
    )


def receipt(issued, **fields):
    attempt = issued.attempts[-1]
    return Result(
        **{
            "id": "receipt-" + attempt.id,
            "attempt_id": attempt.id,
            "action_id": attempt.action.id,
            "obligation_id": attempt.action.obligation_id,
            "scope": attempt.action.scope,
            "target_digest": attempt.action.target_digest,
            "actual_resources": Resources(
                actions=1, verifications=1 if attempt.action.kind == "verify" else 0
            ),
            **fields,
        }
    )


def satisfied():
    state = initial()
    dcheck = check(state, action(D), "rules-pass")
    state = update(state, checks=(dcheck,))
    candidate = action(E, dependencies=(dependency(requirement="verified"),))
    return update(state, checks=(*state.checks, check(state, candidate, "data-pass")))


def test_A01_used_dependency_change_invalidates_only_relevant_pass():
    state = satisfied()
    assert plan(state, (), BUDGET, POLICY).stop_reason == "satisfied"
    strict = update(D, id="rules-2", digest=digest("minimum=1000"), content="minimum=1000")
    updated = update(
        state,
        evidence=(*state.evidence, strict),
        supersessions=(
            Supersession(
                id="rules-update",
                kind="evidence",
                target_id=D.id,
                replacement_id=strict.id,
                reason="new threshold",
            ),
        ),
    )
    updated = update(
        updated, checks=(*updated.checks, check(updated, action(strict), "new-rules-pass"))
    )
    next_check = action(
        E, id="data-again", dependencies=(dependency(strict, requirement="verified"),)
    )
    decision = plan(updated, (next_check,), BUDGET, POLICY)
    assert decision.action == next_check
    assert decision.stop_reason is None
    assert decision.coverage.satisfied == 1
    assert [g.target_evidence_id for g in decision.gaps if g.kind == "content_check"] == [E.id]
    assert len(updated.checks) == 3
    assert updated.checks[1].basis.dependencies[0].digest == D.digest


@pytest.mark.parametrize("field", ["withdrawn", "expired"])
def test_A01_dependency_status_invalidates_related_pass(field):
    state = satisfied()
    changed_dependency = update(D, **{field: True})
    updated = update(state, evidence=(E, changed_dependency))
    decision = plan(updated, (), BUDGET, POLICY)
    assert decision.stop_reason != "satisfied"
    assert decision.coverage.satisfied == 0


def test_A12_contract_change_invalidates_check_but_description_priority_do_not():
    state = satisfied()
    display = update(DATA, description="display change", priority=99, required=False)
    assert display.contract_fingerprint == DATA.contract_fingerprint
    assert (
        plan(update(state, obligations=(display, RULES)), (), BUDGET, POLICY).stop_reason
        == "satisfied"
    )
    for contract in (
        update(DATA, acceptance="different acceptance"),
        update(DATA, contract_revision="2"),
        update(DATA, min_evidence=2),
        update(DATA, required_verifiers=("v1", "v2")),
    ):
        decision = plan(update(state, obligations=(contract, RULES)), (), BUDGET, POLICY)
        assert decision.stop_reason != "satisfied"
    assert (
        update(DATA, required_verifiers=("v2", "v1")).contract_fingerprint
        == update(DATA, required_verifiers=("v1", "v2")).contract_fingerprint
    )


def test_unrelated_evidence_does_not_invalidate_finite_basis():
    state = satisfied()
    optional = Obligation(
        id="unrelated", description="context", scope="other", acceptance="optional", required=False
    )
    unrelated = update(
        E,
        id="unrelated-data",
        obligation_id=optional.id,
        scope=optional.scope,
        digest=digest("other"),
    )
    updated = update(
        state, obligations=(*state.obligations, optional), evidence=(*state.evidence, unrelated)
    )
    assert plan(updated, (), BUDGET, POLICY).stop_reason == "satisfied"


def test_A02_acquisition_cannot_reuse_old_pass_to_erase_failure():
    state = initial(evidence=(E,), obligations=(DATA,))
    old_fail = check(state, action(E), "fail", "FAIL")
    old_pass = check(state, action(E), "pass")
    state = update(state, checks=(old_fail, old_pass))
    issued = start(state, acquired(), "acquire", BUDGET, POLICY)
    event = Supersession(
        id="erase", kind="check", target_id="fail", replacement_id="pass", reason="claims success"
    )
    with pytest.raises(ValidationError, match="acquisition cannot supersede"):
        observe(issued, receipt(issued, supersessions=(event,)))
    assert plan(state, (), BUDGET, POLICY).stop_reason == "escalation_required"


def test_A02_dedicated_authorized_resolution_preserves_failure_and_reuses_basis():
    state = initial(evidence=(E,), obligations=(DATA,))
    fail = check(state, action(E), "fail", "FAIL")
    state = update(state, checks=(fail,))
    candidate = action(E, purpose="check_resolution", resolution_target_id=fail.id)
    issued = start(state, candidate, "resolution", BUDGET, POLICY)
    resolved_check = check(issued, candidate, "resolution-check")
    observed = observe(issued, receipt(issued, checks=(resolved_check,)))
    event = Supersession(
        id="resolve",
        kind="check",
        target_id=fail.id,
        replacement_id=resolved_check.id,
        reason="checked resolution",
    )
    resolved = resolve(observed, event, POLICY)
    assert plan(resolved, (), BUDGET, POLICY).stop_reason == "satisfied"
    assert resolved.checks[0] == fail
    assert resolved.results == observed.results
    assert resolve(resolved, event, POLICY) is resolved


def test_A03_generic_pass_cannot_close_specific_contradiction():
    state = initial(evidence=(E,), obligations=(DATA,))
    conflict = Contradiction(
        id="conflict",
        obligation_id=DATA.id,
        scope=DATA.scope,
        evidence_ids=(E.id,),
        reason="explicit conflict",
    )
    state = update(state, contradictions=(conflict,), checks=(check(state, action(E)),))
    event = Supersession(
        id="resolve",
        kind="contradiction",
        target_id=conflict.id,
        check_id="pass",
        reason="generic pass",
    )
    with pytest.raises(ValueError, match="dedicated"):
        resolve(state, event, POLICY)
    assert (
        plan(update(state, supersessions=(event,)), (), BUDGET, POLICY).stop_reason
        == "escalation_required"
    )
    candidate = action(E, purpose="contradiction_resolution", resolution_target_id=conflict.id)
    issued = start(state, candidate, "resolution", BUDGET, POLICY)
    resolved_check = check(issued, candidate, "specific")
    observed = observe(
        issued,
        receipt(
            issued,
            checks=(resolved_check,),
            supersessions=(update(event, check_id=resolved_check.id),),
        ),
    )
    assert plan(observed, (), BUDGET, POLICY).stop_reason == "satisfied"
    assert observed.contradictions == (conflict,)


def test_contradiction_basis_requires_all_declared_related_material():
    second = update(E, id="second", digest=digest("20"), content="20")
    conflict = Contradiction(
        id="conflict",
        obligation_id=DATA.id,
        scope=DATA.scope,
        evidence_ids=(E.id, second.id),
        reason="explicit",
    )
    state = initial(evidence=(E, second), obligations=(DATA,), contradictions=(conflict,))
    candidate = action(E, purpose="contradiction_resolution", resolution_target_id=conflict.id)
    with pytest.raises(ValueError, match="related_evidence_missing"):
        make_basis(state, candidate)
    candidate = update(candidate, dependencies=(dependency(second),))
    assert make_basis(state, candidate).dependencies[0].evidence_id == second.id


def test_A04_already_passed_target_excluded_under_one_remaining_check_budget():
    second = update(E, id="second", digest=digest("20"), content="20")
    state = initial(evidence=(E, second), obligations=(DATA,))
    state = update(state, checks=(check(state, action(E)),))
    wasted = action(E, id="a-recheck")
    needed = action(second, id="z-needed")
    limited = Budget(limits=Resources(actions=1, verifications=1))
    decision = plan(state, (wasted, needed), limited, POLICY)
    assert decision.action == needed
    assert decision.selected_gap.target_evidence_id == second.id
    assert "target_already_verified_or_no_matching_gap" in decision.exclusions[0].reasons
    issued = start(state, needed, "needed", limited, POLICY)
    observed = observe(issued, receipt(issued, checks=(check(issued, needed, "second-pass"),)))
    assert plan(observed, (), limited, POLICY).stop_reason == "satisfied"


def test_A05_declared_new_source_group_beats_known_origin_regardless_ids():
    obligation = update(DATA, min_evidence=2, min_provenance_groups=2)
    state = initial(evidence=(E,), obligations=(obligation,))
    state = update(state, checks=(check(state, action(E)),))
    repeated = acquired(
        id="a-repeat", kind="diversify", source=E.source, provenance_group=E.provenance_group
    )
    novel = acquired(
        id="z-new",
        kind="diversify",
        source="independent-declaration.csv",
        provenance_group="new-declaration",
    )
    unknown = acquired(id="b-unknown", kind="diversify")
    assert plan(state, (repeated, novel, unknown), BUDGET, POLICY).action == novel
    assert (
        plan(state, (update(novel, id="a"), update(repeated, id="z")), BUDGET, POLICY).action.source
        == novel.source
    )


def test_A06_partial_required_verifier_pass_stays_in_backlog():
    obligation = update(DATA, required_verifiers=("v1", "v2"))
    state = initial(evidence=(E,), obligations=(obligation,))
    state = update(state, checks=(check(state, action(E)),))
    policy = update(POLICY, max_pending_verifications=1)
    remaining = action(E, id="v2", checker_id="v2")
    already = action(E, id="v1")
    more = acquired()
    decision = plan(state, (more, already, remaining), BUDGET, policy)
    assert decision.pending_verifications == 1
    assert decision.action == remaining
    assert decision.selected_gap.checker_id == "v2"
    assert (
        "verification_capacity_reached"
        in next(e for e in decision.exclusions if e.action_id == more.id).reasons
    )


def test_A07_cross_obligation_verified_dependency_progresses():
    state = initial()
    candidate = action(E, dependencies=(dependency(requirement="verified"),))
    blocked = plan(state, (candidate,), BUDGET, POLICY)
    assert blocked.action is None
    assert any(g.kind == "dependency" and g.dependency_id == D.id for g in blocked.gaps)
    state = update(state, checks=(check(state, action(D), "rules-pass"),))
    assert plan(state, (candidate,), BUDGET, POLICY).action == candidate
    issued = start(state, candidate, "data", BUDGET, POLICY)
    assert issued.attempts[-1].inputs == (
        evidence_binding(state, E.id),
        evidence_binding(state, D.id, "verified"),
    )
    observed = observe(issued, receipt(issued, checks=(check(issued, candidate, "data-pass"),)))
    assert plan(observed, (), BUDGET, POLICY).stop_reason == "satisfied"


@pytest.mark.parametrize(
    "fields,reason",
    [
        ({"obligation_id": "dataset"}, "dependency_scope_mismatch"),
        ({"scope": "wrong"}, "dependency_scope_mismatch"),
        ({"digest": digest("wrong")}, "dependency_digest_mismatch"),
        ({"contract_fingerprint": digest("wrong")}, "dependency_contract_mismatch"),
    ],
)
def test_cross_obligation_dependency_rejects_mismatch(fields, reason):
    state = initial()
    candidate = action(E, dependencies=(dependency(**fields),))
    decision = plan(state, (candidate,), BUDGET, POLICY)
    assert decision.action is None
    assert any(reason in r for r in decision.exclusions[0].reasons)


def test_backpressure_exempts_only_exact_declared_missing_prerequisite_acquisition():
    state = initial(evidence=(E,))
    policy = update(POLICY, max_pending_verifications=1)
    candidate = action(E, dependencies=(dependency(requirement="verified"),))
    get_rules = acquired(
        id="get-rules", obligation_id=RULES.id, scope=RULES.scope, produces_evidence_id=D.id
    )
    unrelated = acquired(id="a-unrelated", produces_evidence_id="different")
    candidates = (candidate, get_rules, unrelated)
    decision = plan(state, candidates, BUDGET, policy)
    assert decision.action == get_rules
    with pytest.raises(ValueError, match="capacity"):
        start(state, get_rules, "no-declaration", BUDGET, policy)
    issued = start(state, get_rules, "allowed", BUDGET, policy, candidates=candidates)
    observed = observe(issued, receipt(issued, evidence=(D,)))
    assert plan(observed, (candidate, action(D)), BUDGET, policy).action == action(D)


def test_issued_basis_is_fixed_and_late_receipt_cannot_close_changed_contract():
    state = initial(evidence=(E,), obligations=(DATA,))
    candidate = action(E)
    issued = start(state, candidate, "issued", BUDGET, POLICY)
    changed_state = update(issued, obligations=(update(DATA, acceptance="amount>1000"),))
    old_check = check(issued, candidate)
    observed = observe(changed_state, receipt(changed_state, checks=(old_check,)))
    assert plan(observed, (), BUDGET, POLICY).stop_reason != "satisfied"
    fresh_check = check(changed_state, candidate, "different-basis")
    with pytest.raises(ValidationError, match="issued verification"):
        observe(changed_state, receipt(changed_state, checks=(fresh_check,)))


def test_same_evidence_id_other_digest_is_structural_error():
    state = satisfied()
    with pytest.raises(ValidationError, match="unrecorded|mismatched"):
        update(state, evidence=(update(E, digest=digest("different")), D))


def test_checker_revision_role_and_purpose_are_host_authority():
    state = initial(evidence=(E,), obligations=(DATA,))
    candidate = action(E)
    wrong_revision = update(candidate, checker_revision="unregistered")
    assert plan(state, (wrong_revision,), BUDGET, POLICY).action is None
    wrong_handler = update(candidate, handler_id="read")
    decision = plan(state, (wrong_handler,), BUDGET, POLICY)
    assert "handler_role_forbidden" in decision.exclusions[0].reasons
    valid = update(state, checks=(check(state, candidate),))
    permissions = CheckerPermission(checker_id="v1", revision="2")
    policy = update(
        POLICY, handlers=(POLICY.handlers[0], update(POLICY.handlers[1], checkers=(permissions,)))
    )
    assert plan(valid, (), BUDGET, policy).stop_reason != "satisfied"
    with pytest.raises(ValidationError, match="acquisition cannot declare"):
        acquired(checker_id="v1")


def test_dependency_cycle_blocked_with_finite_reason():
    state = initial()
    a = action(E, dependencies=(dependency(requirement="verified"),))
    b = action(D, dependencies=(dependency(E, requirement="verified"),))
    decision = plan(state, (a, b), BUDGET, POLICY)
    assert decision.stop_reason == "blocked"
    assert all(any("dependency_unverified" in r for r in e.reasons) for e in decision.exclusions)
    self_dependent = action(E, dependencies=(dependency(E, requirement="verified"),))
    assert any(
        "dependency_cycle" in r
        for r in plan(state, (self_dependent,), BUDGET, POLICY).exclusions[0].reasons
    )


def test_new_reader_rejects_schema1_and_migration_retains_unassessed_history():
    from evidence_gap_router import _legacy

    old_obligation = _legacy.Obligation(
        **{k: v for k, v in DATA.model_dump().items() if k != "contract_revision"}
    )
    old_evidence = _legacy.Evidence(**E.model_dump())
    old_check = _legacy.CheckResult(
        id="old-pass",
        obligation_id=DATA.id,
        scope=DATA.scope,
        target_digest=E.digest,
        verifier_id="v1",
        status="PASS",
        reason="old conditions",
    )
    old_fail = _legacy.CheckResult(**{**old_check.model_dump(), "id": "old-fail", "status": "FAIL"})
    old_action = _legacy.ActionCandidate(
        id="read", obligation_id=DATA.id, scope=DATA.scope, kind="investigate", handler_id="read"
    )
    pending = _legacy.Attempt(id="host-attempt-2", action=old_action)
    old = _legacy.State(
        obligations=(old_obligation,),
        evidence=(old_evidence,),
        checks=(old_check, old_fail),
        attempts=(pending,),
    )
    raw = old.model_dump_json()
    with pytest.raises(ValidationError):
        load_json(raw, State)
    migrated = migrate_v1_json(raw)
    assert migrated.legacy_schema1 == raw
    assert migrated.checks[0].legacy and migrated.checks[0].basis is None
    assert migrated.attempts[0].legacy and migrated.attempts[0].id == "host-attempt-2"
    decision = plan(migrated, (), BUDGET, POLICY)
    assert decision.stop_reason != "satisfied"
    assert "check_failed" in {r.code for r in decision.residuals}
    assert load_json(dump_json(migrated), State) == migrated
    with pytest.raises(ValueError, match="pending"):
        start(migrated, acquired(), "new", BUDGET, POLICY)


def test_migration_keeps_old_resolution_events_without_trusting_them():
    from evidence_gap_router import _legacy

    old_obligation = _legacy.Obligation(
        id=DATA.id, description="old", scope=DATA.scope, acceptance="old"
    )
    old_evidence = _legacy.Evidence(**E.model_dump())
    old_pass = _legacy.CheckResult(
        id="pass",
        obligation_id=DATA.id,
        scope=DATA.scope,
        target_digest=E.digest,
        verifier_id="v1",
        status="PASS",
        reason="legacy",
    )
    old_fail = _legacy.CheckResult(**{**old_pass.model_dump(), "id": "fail", "status": "UNKNOWN"})
    conflict = _legacy.Contradiction(
        id="conflict",
        obligation_id=DATA.id,
        scope=DATA.scope,
        evidence_ids=(E.id,),
        reason="old conflict",
    )
    events = (
        _legacy.Supersession(
            id="old-replacement",
            kind="check",
            target_id="fail",
            replacement_id="pass",
            reason="old generic pass",
        ),
        _legacy.Supersession(
            id="old-resolution",
            kind="contradiction",
            target_id="conflict",
            check_id="pass",
            reason="old generic pass",
        ),
    )
    old = _legacy.State(
        obligations=(old_obligation,),
        evidence=(old_evidence,),
        checks=(old_pass, old_fail),
        contradictions=(conflict,),
        supersessions=events,
    )
    migrated = migrate_v1_json(old.model_dump_json())
    assert len(migrated.supersessions) == 2
    decision = plan(migrated, (), BUDGET, POLICY)
    assert decision.stop_reason == "escalation_required"
    assert {"check_unknown", "contradiction"}.issubset({r.code for r in decision.residuals})


def test_schema2_plan_roundtrip_and_unknown_migration_fields_rejected():
    state = satisfied()
    value = PlanInput(state=state, candidates=(action(E),), budget=BUDGET, policy=POLICY)
    assert load_json(dump_json(value), PlanInput) == value
    assert (
        load_json(
            dump_json(plan(state, (), BUDGET, POLICY)), type(plan(state, (), BUDGET, POLICY))
        ).stop_reason
        == "satisfied"
    )
    with pytest.raises(ValidationError):
        migrate_v1_json(json.dumps({"schema_version": "1", "obligations": [], "policy": {}}))


def test_migration_rejects_expanded_snapshot_over_limit_without_overwriting(tmp_path):
    from evidence_gap_router import _legacy

    obligation = _legacy.Obligation(
        id=DATA.id, description="old", scope=DATA.scope, acceptance="old"
    )
    evidence = _legacy.Evidence(**{**E.model_dump(), "content": "x" * 550_000})
    raw = _legacy.State(obligations=(obligation,), evidence=(evidence,)).model_dump_json()
    path = tmp_path / "old.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="including its original archive"):
        migrate_v1_file(path)
    assert path.read_text(encoding="utf-8") == raw


def test_acquisition_capacity_declaration_cannot_emit_other_new_targets():
    state = initial(evidence=(), obligations=(DATA,))
    candidate = acquired(produces_evidence_id="promised")
    issued = start(state, candidate, "acquisition", BUDGET, POLICY)
    with pytest.raises(ValidationError, match="declared acquisition target"):
        observe(issued, receipt(issued, evidence=(E,)))


def test_snapshot_fixed_verification_view_matches_issued_basis():
    state = initial(evidence=(E,), obligations=(DATA,))
    issued = start(state, action(E), "verification", BUDGET, POLICY)
    with pytest.raises(ValidationError, match="inputs must equal"):
        update(issued, attempts=(update(issued.attempts[0], inputs=()),))
    extra = initial()
    extra_issued = start(extra, action(E), "verification", BUDGET, POLICY)
    pinned = extra_issued.attempts[0]
    undeclared = update(pinned.basis, dependencies=(evidence_binding(extra, D.id),))
    with pytest.raises(ValidationError, match="finite declared dependencies"):
        update(
            extra_issued,
            attempts=(
                update(
                    pinned, basis=undeclared, inputs=(undeclared.target, *undeclared.dependencies)
                ),
            ),
        )


def test_pending_basis_must_match_issued_obligation_and_scope():
    state = initial()
    issued = start(state, action(E), "verification", BUDGET, POLICY)
    pinned = issued.attempts[0]
    other_action = update(pinned.action, obligation_id=RULES.id, scope=RULES.scope)
    with pytest.raises(ValidationError, match="action and verification basis mismatch"):
        update(issued, attempts=(update(pinned, action=other_action),))


def test_existing_historical_dependency_can_be_inspected_but_cannot_accept_target():
    state = initial(evidence=(E, update(D, withdrawn=True)))
    candidate = action(E, dependencies=(dependency(requirement="exists"),))
    assert plan(state, (candidate,), BUDGET, POLICY).action == candidate
    record = check(state, candidate)
    assert plan(update(state, checks=(record,)), (), BUDGET, POLICY).stop_reason != "satisfied"


@pytest.mark.parametrize("status", ["FAIL", "UNKNOWN"])
def test_duplicate_alias_negative_check_blocks_and_resolves_exact_alias(status):
    alias = update(E, id="duplicate")
    state = initial(evidence=(E, alias), obligations=(DATA,))
    passed = check(state, action(E), "canonical-pass")
    negative = check(state, action(alias), "alias-negative", status)
    state = update(state, checks=(passed, negative))
    decision = plan(state, (), BUDGET, POLICY)
    assert decision.stop_reason != "satisfied"
    assert decision.coverage.satisfied == 0
    gap = next(g for g in decision.gaps if negative.id in g.record_ids)
    assert gap.target_evidence_id == alias.id
    assert gap.kind == ("failed_check" if status == "FAIL" else "unknown_check")
    assert gap.purpose == "check_resolution"
    candidate = action(alias, purpose="check_resolution", resolution_target_id=negative.id)
    assert plan(state, (candidate,), BUDGET, POLICY).action == candidate
    issued = start(state, candidate, "alias-resolution", BUDGET, POLICY)
    resolution = check(issued, candidate, "alias-resolution")
    event = Supersession(
        id="resolve-alias",
        kind="check",
        target_id=negative.id,
        replacement_id=resolution.id,
        reason="checked exact alias",
    )
    observed = observe(issued, receipt(issued, checks=(resolution,), supersessions=(event,)))
    final = plan(observed, (), BUDGET, POLICY)
    assert final.stop_reason == "satisfied"
    assert final.coverage.satisfied == final.coverage.required == 1
    assert observed.checks[1] == negative
    higher = update(DATA, min_evidence=2)
    assert (
        plan(update(observed, obligations=(higher,)), (), BUDGET, POLICY).stop_reason != "satisfied"
    )


def test_execution_availability_does_not_revoke_current_checker_trust():
    state = satisfied()
    unavailable = update(POLICY, available_handlers=())
    assert plan(state, (), BUDGET, unavailable).stop_reason == "satisfied"
    pending = initial(evidence=(E,), obligations=(DATA,))
    candidate = action(E)
    decision = plan(pending, (candidate,), BUDGET, unavailable)
    assert decision.action is None
    assert "handler_unavailable" in decision.exclusions[0].reasons
    with pytest.raises(ValueError, match="handler_unavailable"):
        start(pending, candidate, "not-available", BUDGET, unavailable)
