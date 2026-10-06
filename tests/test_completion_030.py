"""R01–R25/R28 public issued-receipt completion specification; no inference."""

import json
import subprocess
import sys
from hashlib import sha256
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import evidence_gap_router as s


def replace(record, **values):
    return type(record)(**{**record.model_dump(), **values})


def fixture(*, materials=True, kinds=("content",), groups=0, alternatives=False):
    goal = s.Obligation(
        id="goal", description="sum", scope="local", acceptance="sum inputs", priority=20
    )
    owner = s.Obligation(
        id="materials", description="files", scope="files", acceptance="bytes", required=False
    )

    def req(identifier):
        return s.DependencyRequirement(
            evidence_id=identifier, obligation_id="materials", scope="files"
        )

    contract = s.CompletionContract(
        id="contract-1",
        obligation_id=goal.id,
        scope=goal.scope,
        obligation_fingerprint=goal.contract_fingerprint,
        target=s.DependencyRequirement(
            evidence_id="answer", obligation_id=goal.id, scope=goal.scope
        ),
        declared_scope="finite_catalogue" if materials else "not_applicable",
        catalogue_id="selected-files" if materials else None,
        catalogue_revision="1" if materials else None,
        scope_reason=None if materials else "Fixed arithmetic on the explicitly supplied answer.",
        materials=(
            s.MaterialRequirement(id="M", any_of=(req("M"),)),
            s.MaterialRequirement(
                id="N", any_of=(req("N"), req("alternative")) if alternatives else (req("N"),)
            ),
        )
        if materials
        else (),
        checks=tuple(s.CheckRequirement(id=k, kind=k, min_declared_groups=groups) for k in kinds),
    )
    state = s.State(
        obligations=(goal, owner),
        completion_contracts=(contract,),
        evidence=(
            evidence("answer", "goal", "local", "5"),
            evidence("M", "materials", "files", "2"),
        ),
    )
    permission = s.CheckerPermission(
        checker_id="check",
        completion_kinds=kinds,
        completion_scopes=(goal.scope,),
        correlation_group="fixed-arithmetic",
        purposes=("content", "check_resolution", "contradiction_resolution"),
    )
    policy = s.Policy(
        trusted_verifiers=("check",),
        handlers=(
            s.HandlerRegistration(handler_id="read", roles=("investigate",)),
            s.HandlerRegistration(handler_id="check", roles=("verify",), checkers=(permission,)),
        ),
    )
    return state, policy, s.Budget(limits=s.Resources(actions=20, verifications=12, tokens=0))


def evidence(identifier, owner, scope, content):
    return s.Evidence(
        id=identifier,
        obligation_id=owner,
        scope=scope,
        content=content,
        digest=sha256(content.encode()).hexdigest(),
        producer="source",
        source=identifier,
        provenance_group=identifier,
    )


def check_action(state, identifier="check-M", inputs=("M",), **values):
    target = state.evidence[0]
    return s.ActionCandidate(
        id=identifier,
        obligation_id="goal",
        scope="local",
        kind="verify",
        handler_id="check",
        target_evidence_id="answer",
        target_digest=target.digest,
        checker_id="check",
        dependencies=tuple(
            s.DependencyRequirement(evidence_id=i, obligation_id="materials", scope="files")
            for i in inputs
        ),
        resources=s.Resources(actions=1, verifications=1, tokens=0),
        **values,
    )


def issue(state, action, policy, budget, status="PASS"):
    identifier = f"attempt-{len(state.attempts)}"
    pending = s.start(state, action, identifier, budget, policy, candidates=(action,))
    attempt = pending.attempts[-1]
    check = s.CheckResult(
        id=f"{identifier}-check",
        obligation_id=action.obligation_id,
        scope=action.scope,
        target_digest=action.target_digest,
        verifier_id=action.checker_id,
        basis=attempt.basis,
        status=status,
        reason="Fixed deterministic fixture check",
    )
    receipt = s.Result(
        id=f"{identifier}-receipt",
        attempt_id=identifier,
        action_id=action.id,
        obligation_id=action.obligation_id,
        scope=action.scope,
        target_digest=action.target_digest,
        actual_resources=s.Resources(actions=1, verifications=1, tokens=0),
        checks=(check,),
    )
    return s.observe(pending, receipt, policy)


def assessment(state, policy, budget):
    return s.assess_completion(state, policy, budget)[0]


def acquire(state, policy, budget, identifier="N"):
    action = s.ActionCandidate(
        id="read-" + identifier,
        obligation_id="materials",
        scope="files",
        kind="investigate",
        handler_id="read",
        produces_evidence_id=identifier,
        resources=s.Resources(actions=1, verifications=0, tokens=0),
    )
    pending = s.start(state, action, "acquire-" + identifier, budget, policy, candidates=(action,))
    receipt = s.Result(
        id="receipt-" + identifier,
        attempt_id="acquire-" + identifier,
        action_id=action.id,
        obligation_id="materials",
        scope="files",
        actual_resources=s.Resources(actions=1, verifications=0, tokens=0),
        evidence=(evidence(identifier, "materials", "files", "3"),),
    )
    return s.observe(pending, receipt, policy), action


@pytest.mark.parametrize("admitted", (False, True), ids=("R01-advisory", "R02-admitted"))
def test_partial_pass_kept_but_missing_N_is_routed(admitted):
    state, policy, budget = fixture()
    if not admitted:
        registration = policy.handlers[1]
        policy = replace(
            policy,
            handlers=(
                policy.handlers[0],
                replace(registration, checkers=(s.CheckerPermission(checker_id="check"),)),
            ),
        )
    state = issue(state, check_action(state, advisory=not admitted), policy, budget)
    after, acquisition = acquire(state, policy, budget)
    assert s.plan(state, (acquisition,), budget, policy).action == acquisition
    assert (
        state.checks[0].status == "PASS" and not assessment(state, policy, budget).finite_complete
    )
    assert not assessment(after, policy, budget).finite_complete
    assert after.checks == state.checks  # R04 receipt does not upgrade M-only basis.


def test_R03_raw_and_pending_are_not_current_use():
    state, policy, budget = fixture()
    state = issue(state, check_action(state), policy, budget)
    raw = replace(state, evidence=(*state.evidence, evidence("N", "materials", "files", "3")))
    assert not assessment(raw, policy, budget).finite_complete
    assert "material_not_used" in {r.code for r in assessment(raw, policy, budget).residuals}
    pending = s.start(raw, check_action(raw, "full", ("M", "N")), "pending", budget, policy)
    assert not assessment(pending, policy, budget).finite_complete
    assert s.plan(pending, (), budget, policy).stop_reason == "blocked"


def test_R05_full_current_receipt_completes_with_real_cost_and_history():
    state, policy, budget = fixture()
    state = issue(state, check_action(state), policy, budget)
    state, _ = acquire(state, policy, budget)
    state = issue(state, check_action(state, "full", ("M", "N")), policy, budget)
    assert assessment(state, policy, budget).finite_complete
    assert s.plan(state, (), budget, policy).stop_reason == "satisfied"
    assert len(state.results) == 3 and len(state.checks) == 2
    assert sum(r.actual_resources.actions for r in state.results) == 3
    assert s.load_json(s.dump_json(state), s.State) == state


def test_R06_fixed_one_checker_and_R19_external_unknown():
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget)
    result = assessment(state, policy, budget)
    assert result.finite_complete and result.external_completeness == "unknown"
    assert (
        json.loads(s.dump_json(s.plan(state, (), budget, policy)))["completion"][0][
            "external_completeness"
        ]
        == "unknown"
    )


def test_R07_declared_alternative_avoids_other_reads():
    state, policy, budget = fixture(alternatives=True)
    state, action = acquire(state, policy, budget, "alternative")
    state = issue(state, check_action(state, "full", ("M", "alternative")), policy, budget)
    assert assessment(state, policy, budget).finite_complete
    assert (
        s.plan(
            state, (replace(action, id="read-N", produces_evidence_id="N"),), budget, policy
        ).action
        is None
    )


@pytest.mark.parametrize(
    "field,value", [("scope", "wrong"), ("digest", "a" * 64), ("contract_fingerprint", "b" * 64)]
)
def test_R08_exact_material_identity_and_contract(field, value):
    state, policy, budget = fixture()
    state, _ = acquire(state, policy, budget)
    contract = state.completion_contracts[0]
    material = contract.materials[1]
    changed = replace(
        contract,
        id="contract-2",
        revision="2",
        materials=(
            contract.materials[0],
            replace(material, any_of=(replace(material.any_of[0], **{field: value}),)),
        ),
        change_reason="Host scope change",
    )
    state = s.declare_completion(state, changed)
    state = issue(state, check_action(state, "full", ("M", "N")), policy, budget)
    assert not assessment(state, policy, budget).finite_complete


def test_R09_check_kinds_do_not_substitute_for_semantic_coverage():
    state, policy, budget = fixture(materials=False, kinds=("schema", "semantic", "coverage"))
    state = issue(state, check_action(state, "schema", (), check_kind="schema"), policy, budget)
    assert not assessment(state, policy, budget).finite_complete
    for kind in ("semantic", "coverage"):
        state = issue(state, check_action(state, kind, (), check_kind=kind), policy, budget)
    assert assessment(state, policy, budget).finite_complete


def test_R10_callback_extra_authority_rejected():
    state, policy, budget = fixture(materials=False)
    with pytest.raises(ValidationError):
        s.CheckResult(
            id="claim",
            obligation_id="goal",
            scope="local",
            target_digest=state.evidence[0].digest,
            verifier_id="check",
            status="PASS",
            reason="claim",
            closing=True,
        )


def test_R11_issued_advisory_never_upgrades_and_revocation_keeps_history():
    state, policy, budget = fixture(materials=False)
    advisory = replace(
        policy,
        handlers=(
            policy.handlers[0],
            replace(policy.handlers[1], checkers=(s.CheckerPermission(checker_id="check"),)),
        ),
    )
    state = issue(state, check_action(state, inputs=(), advisory=True), advisory, budget)
    assert not assessment(state, policy, budget).finite_complete
    state = issue(state, check_action(state, "qualified", ()), policy, budget)
    assert assessment(state, policy, budget).finite_complete
    assert not assessment(state, advisory, budget).finite_complete
    assert len(state.results) == 2 and all(c.status == "PASS" for c in state.checks)


def test_explicit_advisory_action_does_not_close_under_an_admitted_profile():
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=(), advisory=True), policy, budget)
    assert not assessment(state, policy, budget).finite_complete
    state = issue(state, check_action(state, "qualified", ()), policy, budget)
    assert assessment(state, policy, budget).finite_complete


@pytest.mark.parametrize("group", (None, "same"))
def test_R12_unknown_or_alias_correlation_groups_do_not_multiply(group):
    state, policy, budget = fixture(materials=False, groups=2)
    profile = replace(policy.handlers[1].checkers[0], correlation_group=group)
    other = replace(profile, checker_id="alias")
    policy = replace(
        policy,
        trusted_verifiers=("check", "alias"),
        handlers=(policy.handlers[0], replace(policy.handlers[1], checkers=(profile, other))),
    )
    state = issue(state, check_action(state, inputs=()), policy, budget)
    state = issue(
        state, replace(check_action(state, "alias", ()), checker_id="alias"), policy, budget
    )
    assert not assessment(state, policy, budget).finite_complete


def test_same_checker_revision_cannot_claim_two_groups_through_two_handlers():
    state, policy, budget = fixture(materials=False, groups=2)
    profile = policy.handlers[1].checkers[0]
    other = replace(
        policy.handlers[1],
        handler_id="alias-handler",
        checkers=(replace(profile, correlation_group="different-declaration"),),
    )
    policy = replace(policy, handlers=(*policy.handlers, other))
    state = issue(state, check_action(state, inputs=()), policy, budget)
    state = issue(
        state,
        replace(check_action(state, "alias", ()), handler_id=other.handler_id),
        policy,
        budget,
    )
    assert not assessment(state, policy, budget).finite_complete


def test_R13_unavailable_qualified_checker_has_concrete_residual():
    state, policy, budget = fixture(materials=False)
    unavailable = replace(policy, available_handlers=())
    decision = s.plan(state, (check_action(state, inputs=()),), budget, unavailable)
    assert decision.action is None and decision.stop_reason == "blocked"
    assert "handler_unavailable" in decision.exclusions[0].reasons
    assert "completion_check_missing" in {r.code for r in decision.completion[0].residuals}


@pytest.mark.parametrize("status", ("FAIL", "UNKNOWN"))
def test_R14_negative_not_erased_by_generic_pass(status):
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget, status)
    state = issue(state, check_action(state, "later-pass", ()), policy, budget)
    assert not assessment(state, policy, budget).finite_complete
    assert state.checks[0].status == status


def test_R15_unrelated_addition_reuses_but_used_invalidation_reopens():
    state, policy, budget = fixture()
    state, _ = acquire(state, policy, budget)
    state = issue(state, check_action(state, "full", ("M", "N")), policy, budget)
    unrelated = replace(
        state, evidence=(*state.evidence, evidence("unused", "materials", "files", "99"))
    )
    assert assessment(unrelated, policy, budget).finite_complete
    invalid = s.invalidate(
        unrelated,
        s.Invalidation(
            id="withdraw-N",
            kind="evidence",
            target_id="N",
            obligation_id="materials",
            scope="files",
            reason="Host expiry",
        ),
    )
    assert not assessment(invalid, policy, budget).finite_complete
    assert invalid.results == state.results and invalid.checks == state.checks


def test_R16_optional_required_material_inherits_goal_priority():
    state, policy, budget = fixture()
    distractor = s.Obligation(
        id="other", description="other", scope="other", acceptance="other", priority=1
    )
    state = replace(state, obligations=(*state.obligations, distractor))
    _, acquisition = acquire(state, policy, budget)
    unrelated = replace(
        acquisition,
        id="a-distractor",
        obligation_id="other",
        scope="other",
        produces_evidence_id="other",
    )
    assert s.plan(state, (unrelated, acquisition), budget, policy).action == acquisition


def test_R17_explicit_revision_history_and_callback_cannot_remove_contract():
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget)
    changed = replace(
        state.completion_contracts[0], id="contract-2", revision="2", change_reason="Scope review"
    )
    revised = s.declare_completion(state, changed)
    assert len(revised.completion_contracts) == 2
    assert not assessment(revised, policy, budget).finite_complete
    assert revised.checks == state.checks


@pytest.mark.parametrize(
    "scope,reason", [("unspecified", None), ("not_applicable", None), ("finite_catalogue", None)]
)
def test_R18_empty_or_unjustified_scope_never_closes(scope, reason):
    state, policy, budget = fixture(materials=False)
    contract = replace(state.completion_contracts[0], declared_scope=scope, scope_reason=reason)
    state = replace(state, completion_contracts=(contract,))
    state = issue(state, check_action(state, inputs=()), policy, budget)
    assert not assessment(state, policy, budget).finite_complete


def test_R20_unknown_cost_effects_and_pending_do_not_complete():
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget)
    receipt = state.results[0]
    unknown = replace(
        receipt, actual_resources=s.Resources(actions=None, verifications=1, tokens=0)
    )
    uncertain = replace(state, results=(unknown,))
    assert not assessment(uncertain, policy, budget).finite_complete
    assert s.plan(uncertain, (), budget, policy).stop_reason == "escalation_required"


def test_R22_seeded_pass_is_not_issued_and_reload_does_not_bypass():
    state, policy, budget = fixture(materials=False)
    action = check_action(state, inputs=())
    seeded = s.CheckResult(
        id="seed",
        obligation_id="goal",
        scope="local",
        verifier_id="check",
        target_digest=state.evidence[0].digest,
        status="PASS",
        reason="seeded",
        basis=s.make_basis(state, action),
    )
    state = replace(state, checks=(seeded,))
    assert not assessment(s.load_json(s.dump_json(state), s.State), policy, budget).finite_complete


def test_R23_valid_late_receipt_retained_under_revocation_and_no_double_charge():
    state, policy, budget = fixture(materials=False)
    action = check_action(state, inputs=())
    pending = s.start(state, action, "late", budget, policy)
    check = s.CheckResult(
        id="late-check",
        obligation_id="goal",
        scope="local",
        verifier_id="check",
        target_digest=state.evidence[0].digest,
        status="PASS",
        reason="late",
        basis=pending.attempts[-1].basis,
    )
    receipt = s.Result(
        id="late-result",
        attempt_id="late",
        action_id=action.id,
        obligation_id="goal",
        scope="local",
        target_digest=action.target_digest,
        checks=(check,),
        actual_resources=s.Resources(actions=1, verifications=1, tokens=0),
    )
    revoked = s.Policy()
    state = s.observe(pending, receipt, revoked)
    assert s.observe(state, receipt, revoked) == state
    assert (
        not assessment(state, revoked, budget).finite_complete and state.checks[0].status == "PASS"
    )


def test_R24_explicit_v2_import_preserves_original_basis_and_pass_without_authority():
    state, policy, budget = fixture(materials=False)
    original = state.model_dump(mode="json")
    original.pop("completion_contracts")
    original.pop("legacy_schema2")
    original["schema_version"] = "2"
    raw = json.dumps(original, ensure_ascii=False)
    migrated = s.migrate_v2_json(raw)
    assert migrated.legacy_schema2 == raw and migrated.evidence == state.evidence
    assert (
        not migrated.completion_contracts
        and not assessment(migrated, policy, budget).finite_complete
    )
    with pytest.raises(ValidationError):
        s.load_json(raw, s.State)


@pytest.mark.parametrize(
    "raw",
    (
        '{"schema_version":"2","schema_version":"2"}',
        '{"n":NaN}',
        '{"schema_version":"2","completion_contracts":[]}',
    ),
)
def test_R25_import_rejects_duplicate_nonfinite_and_new_fields(raw):
    with pytest.raises(ValueError):
        s.migrate_v2_json(raw)


@pytest.mark.parametrize("status", ("FAIL", "UNKNOWN"))
def test_R14_dedicated_resolution_reopens_the_normal_completion_path(status):
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget, status)
    negative = state.checks[0]
    action = check_action(
        state, "resolve", (), purpose="check_resolution", resolution_target_id=negative.id
    )
    state = issue(state, action, policy, budget)
    resolved = s.resolve(
        state,
        s.Supersession(
            id="resolution",
            kind="check",
            target_id=negative.id,
            replacement_id=state.checks[-1].id,
            reason="Dedicated fixed-condition recheck",
        ),
        policy,
    )
    assert assessment(resolved, policy, budget).finite_complete
    assert resolved.checks[0] == negative and len(resolved.results) == 2
    assert s.resolve(resolved, resolved.supersessions[-1], policy) == resolved


def test_R21_aliases_stop_without_erasing_paid_receipts_and_factory_errors_stop():
    state, policy, budget = fixture()

    def factory(current):
        return (check_action(current, f"alias-{len(current.attempts)}"),)

    def callback(view):
        return view.result(
            actual_resources=s.Resources(actions=1, verifications=1, tokens=0),
            checks=(view.check(status="PASS", reason="M-only observation"),),
        )

    report = s.run(state, factory, budget, policy, {"check": callback}, max_steps=6)
    assert report.stop_reason == "no_progress" and len(report.receipts) == 2
    assert not report.decision.completion[0].finite_complete
    assert sum(r.actual_resources.actions for r in report.receipts) == 2
    broken = s.run(state, lambda _: (factory(state)[0],) * 2, budget, policy, {"check": callback})
    assert broken.stop_reason == "planning_error" and not broken.receipts
    assert "candidate IDs must be unique" in broken.error

    def invalid_factory(_):
        raise ValueError("bounded factory failure")

    broken = s.run(state, invalid_factory, budget, policy, {"check": callback})
    assert broken.stop_reason == "factory_error" and not broken.receipts


def test_R22_selector_cannot_choose_an_unqualified_check():
    state, policy, budget = fixture(materials=False)
    permitted = check_action(state, "permitted", ())
    unqualified = replace(permitted, id="unqualified", checker_id="not-registered")
    report = s.run(
        state,
        (permitted, unqualified),
        budget,
        policy,
        {"check": lambda _: pytest.fail("must not dispatch")},
        selector=lambda _state, _pool, _eligible: unqualified,
    )
    assert report.stop_reason == "planning_error" and not report.state.attempts
    assert "eligible" in report.error


@pytest.mark.parametrize("shape", ("chain", "diamond", "grounded-cycle", "pure-cycle"))
def test_R26_R27_finite_completion_graphs_and_snapshot_local_counters(shape):
    from evidence_gap_router.router import _HelperGraph

    state, policy, budget = fixture()

    def read(identifier, output, dependencies):
        return s.ActionCandidate(
            id=identifier,
            obligation_id="materials",
            scope="files",
            kind="investigate",
            handler_id="read",
            produces_evidence_id=output,
            resources=s.Resources(actions=1, verifications=0, tokens=0),
            dependencies=tuple(
                s.DependencyRequirement(evidence_id=i, obligation_id="materials", scope="files")
                for i in dependencies
            ),
        )

    if shape == "chain":
        acquisitions = (read("X", "X", ("M",)), read("N", "N", ("X",)))
    elif shape == "diamond":
        acquisitions = (read("X", "X", ("M",)), read("Y", "Y", ("M",)), read("N", "N", ("X", "Y")))
    else:
        acquisitions = (read("cycle-X", "X", ("N",)), read("N", "N", ("X",)))
        if shape == "grounded-cycle":
            acquisitions += (read("ground-X", "X", ("M",)),)
    full = check_action(state, "full", ("M", "N"))
    pool = (full, *acquisitions)
    visits = 0
    original = _HelperGraph._consume_edge

    def count(graph, rule, pending):
        nonlocal visits
        visits += 1
        return original(graph, rule, pending)

    with patch.object(_HelperGraph, "_consume_edge", count):
        decision = s.plan(state, pool, budget, policy)
    incidence = len(pool) + sum(len(a.dependencies) for a in pool)
    assert visits <= 20 * incidence  # Structural bound, no clock or performance score.
    assert (decision.action is None) == (shape == "pure-cycle")

    def callback(view):
        if view.action.kind == "verify":
            values = {e.id: int(e.content) for e in view.inputs}
            return view.result(
                actual_resources=s.Resources(actions=1, verifications=1, tokens=0),
                checks=(
                    view.check(
                        status="PASS" if values["answer"] == values["M"] + values["N"] else "FAIL",
                        reason="Actual integer condition",
                    ),
                ),
            )
        return view.result(
            actual_resources=s.Resources(actions=1, verifications=0, tokens=0),
            evidence=(evidence(view.action.produces_evidence_id, "materials", "files", "3"),),
        )

    report = s.run(state, pool, budget, policy, {"read": callback, "check": callback}, max_steps=8)
    assert report.decision.completion[0].finite_complete == (shape != "pure-cycle")
    assert len(report.receipts) <= 4
    assert not assessment(state, policy, budget).finite_complete  # No cross-snapshot cache.
    if shape != "pure-cycle":
        invalid = s.invalidate(
            report.state,
            s.Invalidation(
                id="withdraw-root-input",
                kind="evidence",
                target_id="M",
                obligation_id="materials",
                scope="files",
                reason="Used ancestor expires",
            ),
        )
        assert not assessment(invalid, policy, budget).finite_complete
        assert invalid.checks == report.state.checks


def test_R28_real_local_files_partial_pooled_and_continuation(tmp_path):
    from evidence_gap_router.completion_example import (
        run_material_continuation,
        run_partial_example,
        run_pooled_example,
    )

    partial = run_partial_example(tmp_path / "部分 入力")
    assert not partial["partial"]["completion"][0]["finite_complete"]
    assert not partial["after_acquisition"]["completion"][0]["finite_complete"]
    assert partial["decision"]["stop_reason"] == "satisfied"
    pooled = run_pooled_example(tmp_path / "一括 入力")
    assert pooled.decision.stop_reason == "satisfied" and len(pooled.receipts) == 1
    resumed = run_material_continuation(tmp_path / "再開 入力")
    assert resumed.decision.stop_reason == "satisfied" and len(resumed.state.results) == 3
    assert len(resumed.state.checks) == 2 and len(resumed.state.invalidations) == 1
    # Existing files are really evaluated; they are never overwritten to force PASS.
    (tmp_path / "一括 入力" / "N.txt").write_text("30", encoding="utf-8")
    failed = run_pooled_example(tmp_path / "一括 入力")
    assert (
        failed.state.checks[0].status == "FAIL"
        and not failed.decision.completion[0].finite_complete
    )


def test_R29_offline_import_cli_and_R22_current_assessment_match(tmp_path):
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget)
    path = tmp_path / "計画 入力.json"
    s.write_json(s.PlanInput(state=state, candidates=(), budget=budget, policy=policy), path)
    script = """import sys
def audit(event, args):
    if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system"}:
        raise AssertionError("Offline import/CLI must not dispatch: " + event)
sys.addaudithook(audit)
import evidence_gap_router
from evidence_gap_router.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, "plan", str(path), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    actual = json.loads(result.stdout)
    expected = s.plan(state, (), budget, policy).model_dump(mode="json")
    assert actual == expected and actual["stop_reason"] == "satisfied"


def test_used_producer_ancestor_invalidation_reopens_even_outside_required_catalogue():
    state, policy, budget = fixture(materials=False)
    state = replace(state, evidence=tuple(e for e in state.evidence if e.id != "answer"))
    action = s.ActionCandidate(
        id="produce-answer",
        obligation_id="goal",
        scope="local",
        kind="investigate",
        handler_id="read",
        produces_evidence_id="answer",
        dependencies=(
            s.DependencyRequirement(evidence_id="M", obligation_id="materials", scope="files"),
        ),
        resources=s.Resources(actions=1, verifications=0, tokens=0),
    )
    report = s.run(
        state,
        (action,),
        budget,
        policy,
        {
            "read": lambda view: view.result(
                actual_resources=s.Resources(actions=1, verifications=0, tokens=0),
                evidence=(
                    evidence("answer", "goal", "local", str(int(view.inputs[0].content) + 3)),
                ),
            )
        },
    )
    state = report.state
    state = replace(state, evidence=tuple(sorted(state.evidence, key=lambda e: e.id != "answer")))
    state = issue(state, check_action(state, inputs=()), policy, budget)
    assert assessment(state, policy, budget).finite_complete
    invalid = s.invalidate(
        state,
        s.Invalidation(
            id="expire-M",
            kind="evidence",
            target_id="M",
            obligation_id="materials",
            scope="files",
            reason="Input expiry",
        ),
    )
    assert not assessment(invalid, policy, budget).finite_complete


def test_R22_seeded_resolution_cannot_remove_an_issued_closing_negative():
    state, policy, budget = fixture(materials=False)
    state = issue(state, check_action(state, inputs=()), policy, budget, "FAIL")
    negative = state.checks[0]
    state = issue(state, check_action(state, "generic", ()), policy, budget)
    action = check_action(
        state, "seed-resolution", (), purpose="check_resolution", resolution_target_id=negative.id
    )
    seed = s.CheckResult(
        id="external-resolution",
        obligation_id="goal",
        scope="local",
        target_digest=state.evidence[0].digest,
        verifier_id="check",
        status="PASS",
        reason="External seed cannot prove an issued closing invocation",
        basis=s.make_basis(state, action),
    )
    state = replace(state, checks=(*state.checks, seed))
    event = s.Supersession(
        id="seed-event",
        kind="check",
        target_id=negative.id,
        replacement_id=seed.id,
        reason="Attempted host reuse",
    )
    with pytest.raises(ValueError, match="authorized current dedicated"):
        s.resolve(state, event, policy)
    imported = replace(state, supersessions=(event,))
    assert not assessment(imported, policy, budget).finite_complete
    assert imported.checks[0].status == "FAIL"


def test_same_content_source_group_alias_cannot_inflate_support_quota():
    state, policy, budget = fixture()
    goal = replace(state.obligations[0], min_evidence=3)
    contract = replace(
        state.completion_contracts[0], obligation_fingerprint=goal.contract_fingerprint
    )
    alias = replace(evidence("N", "materials", "files", "2"), provenance_group="M")
    state = replace(
        state,
        obligations=(goal, state.obligations[1]),
        completion_contracts=(contract,),
        evidence=(*state.evidence, alias),
    )
    state = issue(state, check_action(state, "full", ("M", "N")), policy, budget)
    result = assessment(state, policy, budget)
    assert not result.finite_complete
    assert "insufficient_declared_support" in {r.code for r in result.residuals}


def test_R24_schema2_rich_issued_history_cost_unknown_invalidation_pending_and_original_file(
    tmp_path,
):
    state, policy, budget = fixture()
    for status in ("PASS", "FAIL", "UNKNOWN"):
        state = issue(state, check_action(state, status), policy, budget, status)
    state = s.invalidate(
        state,
        s.Invalidation(
            id="withdraw-M",
            kind="evidence",
            target_id="M",
            obligation_id="materials",
            scope="files",
            reason="Host expiry",
        ),
    )
    action = s.ActionCandidate(
        id="pending-N",
        obligation_id="materials",
        scope="files",
        kind="investigate",
        handler_id="read",
        produces_evidence_id="N",
        resources=s.Resources(actions=1, verifications=0, tokens=0),
    )
    state = s.start(state, action, "pending-N", budget, policy, candidates=(action,))
    fields = {
        "completion_contracts",
        "legacy_schema2",
        "completion_fingerprint",
        "check_kind",
        "advisory",
        "completion_kinds",
        "completion_scopes",
        "correlation_group",
        "method",
    }

    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in fields}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return value

    original = strip(state.model_dump(mode="json"))
    original["schema_version"] = "2"
    original["results"][0]["actual_resources"]["tokens"] = None
    raw = json.dumps(original, ensure_ascii=False, indent=2).encode("utf-8")
    path = tmp_path / "旧 保存.json"
    path.write_bytes(raw)
    migrated = s.migrate_v2_file(path)
    s.write_json(migrated, tmp_path / "新 保存.json")
    assert path.read_bytes() == raw and migrated.legacy_schema2.encode("utf-8") == raw
    assert tuple(c.status for c in migrated.checks) == ("PASS", "FAIL", "UNKNOWN")
    assert migrated.invalidations == state.invalidations
    assert len(migrated.attempts) == 4 and len(migrated.results) == 3
    assert migrated.results[0].actual_resources.tokens is None
    assert [r.actual_resources.actions for r in migrated.results] == [1, 1, 1]
    assert not migrated.completion_contracts
    assert s.plan(migrated, (), budget, policy).stop_reason != "satisfied"
    assert s.read_json(tmp_path / "新 保存.json", s.State) == migrated
