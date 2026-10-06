"""Finite public-SDK diagnostics, executed separately from confirmatory experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
from decimal import Decimal
from importlib import metadata
from pathlib import Path

import evidence_gap_router as sdk
from evidence_gap_router.file_checks import check_data

BUDGET = sdk.Budget(limits=sdk.Resources(actions=100, verifications=100))
POLICY = sdk.Policy(
    trusted_verifiers=("checker",),
    handlers=(
        sdk.HandlerRegistration(handler_id="read", roles=("investigate",)),
        sdk.HandlerRegistration(
            handler_id="verify",
            roles=("verify",),
            checkers=(
                sdk.CheckerPermission(
                    checker_id="checker",
                    purposes=("content", "check_resolution", "contradiction_resolution"),
                ),
            ),
        ),
    ),
)


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def changed(record, **fields):
    return type(record)(**{**record.model_dump(), **fields})


def obligation(identifier="readings", *, required=True, minimum=2):
    return sdk.Obligation(
        id=identifier,
        description="Inspect actual integer readings",
        scope="local",
        acceptance="Nonnegative integers; disputed readings require explicit joint inspection",
        min_evidence=minimum,
        min_provenance_groups=minimum,
        required=required,
    )


def material(identifier, value="4", owner="readings", **fields):
    return sdk.Evidence(
        **{
            "id": identifier,
            "obligation_id": owner,
            "scope": "local",
            "content": value,
            "digest": digest(value),
            "producer": "collector",
            "source": identifier,
            "provenance_group": identifier,
            **fields,
        }
    )


def dependency(evidence, requirement="active"):
    return sdk.DependencyRequirement(
        evidence_id=evidence.id,
        obligation_id=evidence.obligation_id,
        scope=evidence.scope,
        requirement=requirement,
    )


def verifier(evidence, identifier=None, **fields):
    return sdk.ActionCandidate(
        **{
            "id": identifier or f"check-{evidence.id}",
            "obligation_id": evidence.obligation_id,
            "scope": evidence.scope,
            "kind": "verify",
            "handler_id": "verify",
            "target_evidence_id": evidence.id,
            "target_digest": evidence.digest,
            "checker_id": "checker",
            "resources": sdk.Resources(actions=1, verifications=1),
            **fields,
        }
    )


def read_action(evidence):
    return sdk.ActionCandidate(
        id=f"read-{evidence.id}",
        obligation_id=evidence.obligation_id,
        scope=evidence.scope,
        kind="investigate",
        handler_id="read",
        produces_evidence_id=evidence.id,
        source=evidence.source,
        provenance_group=evidence.provenance_group,
    )


def handlers(materials, trace, *, unavailable_threshold=False):
    def callback(view):
        if view.action.kind != "verify":
            result = view.result(
                actual_resources=sdk.Resources(actions=1, verifications=0),
                evidence=(materials[view.action.produces_evidence_id],),
            )
        else:
            values = [int(e.content) for e in view.inputs]
            passed = bool(values) and all(value >= 0 for value in values)
            if view.action.purpose == "contradiction_resolution":
                passed = passed and len(values) >= 2 and values[1] - values[0] == 1
            status = "UNKNOWN" if unavailable_threshold else ("PASS" if passed else "FAIL")
            check = view.check(
                status=status,
                reason=(
                    "Required threshold material is unavailable"
                    if unavailable_threshold
                    else "Computed using the actual disclosed integer inputs"
                ),
            )
            events = ()
            if status == "PASS" and view.action.purpose != "content":
                events = (
                    sdk.Supersession(
                        id=f"{view.attempt_id}:resolution",
                        kind=(
                            "check"
                            if view.action.purpose == "check_resolution"
                            else "contradiction"
                        ),
                        target_id=view.action.resolution_target_id,
                        replacement_id=(
                            check.id if view.action.purpose == "check_resolution" else None
                        ),
                        check_id=(
                            check.id if view.action.purpose == "contradiction_resolution" else None
                        ),
                        reason="Compared the exact declared subject and supplied inputs",
                    ),
                )
            result = view.result(
                actual_resources=sdk.Resources(actions=1, verifications=1),
                checks=(check,),
                supersessions=events,
            )
        trace.append(
            {
                "action": view.action.model_dump(mode="json"),
                "inputs": [e.model_dump(mode="json") for e in view.inputs],
                "receipt": result.model_dump(mode="json"),
            }
        )
        return result

    return {"read": callback, "verify": callback}


def history(*, acquire=False):
    a, b = material("a"), material("b", "5")
    materials, trace = {e.id: e for e in (a, b)}, []
    state = sdk.State(obligations=(obligation(),), evidence=() if acquire else (a, b))
    pool = (verifier(a), verifier(b))
    if acquire:
        pool += (read_action(a), read_action(b))
    report = sdk.run(state, pool, BUDGET, POLICY, handlers(materials, trace))
    conflict = sdk.Contradiction(
        id="disputed",
        obligation_id="readings",
        scope="local",
        evidence_ids=(a.id, b.id),
        reason="Host requires a joint comparison of the two raw readings",
    )
    return changed(report.state, contradictions=(conflict,)), materials, trace


def resolution_action(materials, identifier="resolve", *, extra=(), revision="1"):
    return verifier(
        materials["a"],
        identifier,
        dependencies=tuple(dependency(e) for e in (materials["b"], *extra)),
        purpose="contradiction_resolution",
        resolution_target_id="disputed",
        checker_revision=revision,
    )


def contract_hash(owner):
    fields = {
        name: getattr(owner, name)
        for name in (
            "id",
            "scope",
            "contract_revision",
            "acceptance",
            "min_evidence",
            "min_provenance_groups",
        )
    }
    fields["required_verifiers"] = sorted(set(owner.required_verifiers))
    return digest(json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def independent_resolution_inputs(state, checked, policy):
    """Exact-input/current-authority oracle; it does not call SDK acceptance predicates."""
    basis = checked.basis
    if basis is None or basis.purpose != "contradiction_resolution" or checked.status != "PASS":
        return False
    subject = next((c for c in state.contradictions if c.id == basis.resolution_target_id), None)
    records = {e.id: e for e in state.evidence}
    owners = {o.id: o for o in state.obligations}
    bindings = (basis.target, *basis.dependencies)
    disclosed = {b.evidence_id for b in bindings}
    inactive = {i.target_id for i in state.invalidations if i.kind == "evidence"}
    inactive.update(e.target_id for e in state.supersessions if e.kind == "evidence")
    if (
        subject is None
        or (subject.obligation_id, subject.scope) != (basis.obligation_id, basis.scope)
        or basis.target.evidence_id not in subject.evidence_ids
        or not set(subject.evidence_ids) <= disclosed
        or checked.expired
        or checked.withdrawn
        or any(i.kind == "check" and i.target_id == checked.id for i in state.invalidations)
        or checked.verifier_id not in policy.trusted_verifiers
    ):
        return False
    if not any(
        "verify" in registration.roles
        and any(
            permission.checker_id == basis.checker_id
            and permission.revision == basis.checker_revision
            and basis.purpose in permission.purposes
            for permission in registration.checkers
        )
        for registration in policy.handlers
    ):
        return False
    for binding in bindings:
        item, owner = records.get(binding.evidence_id), owners.get(binding.obligation_id)
        if (
            item is None
            or owner is None
            or item.id in inactive
            or item.expired
            or item.withdrawn
            or (item.obligation_id, item.scope, item.digest)
            != (binding.obligation_id, binding.scope, binding.digest)
            or owner.scope != binding.scope
            or contract_hash(owner) != binding.contract_fingerprint
            or item.content is None
            or digest(item.content) != item.digest
        ):
            return False
    related = [
        {
            "evidence_id": identifier,
            "digest": records[identifier].digest,
            "obligation_id": records[identifier].obligation_id,
            "scope": records[identifier].scope,
            "contract_fingerprint": contract_hash(owners[records[identifier].obligation_id]),
            "requirement": "active",
        }
        for identifier in subject.evidence_ids
    ]
    fingerprint = digest(
        json.dumps(
            {
                "kind": "contradiction",
                "record": subject.model_dump(mode="json"),
                "contract": contract_hash(owners[subject.obligation_id]),
                "related": related,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    values = [int(records[i].content) for i in subject.evidence_ids]
    return (
        fingerprint == basis.resolution_fingerprint
        and all(value >= 0 for value in values)
        and values[1] - values[0] == 1
        and not (
            policy.prohibit_self_verification
            and records[basis.target.evidence_id].producer == basis.checker_id
        )
    )


def imported(state, materials, *, partial=False, alias=False):
    basis = sdk.make_basis(state, resolution_action(materials))
    if partial:
        basis = changed(basis, dependencies=())
    if alias:
        alternate = changed(materials["b"], id="b-alias")
        state = changed(state, evidence=(*state.evidence, alternate))
        basis = changed(basis, dependencies=(sdk.evidence_binding(state, alternate.id),))
    check = sdk.CheckResult(
        id="external-resolution",
        obligation_id="readings",
        scope="local",
        target_digest=basis.target.digest,
        verifier_id="checker",
        status="PASS",
        reason="Typed external assertion; only the recorded basis discloses its used inputs",
        basis=basis,
    )
    state = changed(state, checks=(*state.checks, check))
    event = sdk.Supersession(
        id="external-event",
        kind="contradiction",
        target_id="disputed",
        check_id=check.id,
        reason="Host requests reuse of the imported record",
    )
    return state, check, event


def state_observation(state, trace, policy=POLICY):
    decision = sdk.plan(state, (), BUDGET, policy)
    return {
        "domain_stop": decision.stop_reason,
        "attempts": len(state.attempts),
        "results": len(state.results),
        "actual_actions": sum(r.actual_resources.actions or 0 for r in state.results),
        "actual_verifications": (
            None
            if any(r.actual_resources.verifications is None for r in state.results)
            else sum(r.actual_resources.verifications for r in state.results)
        ),
        "callback_trace": trace,
        "state": state.model_dump(mode="json"),
    }


def imported_case(*, partial=False, alias=False, retained_event=False):
    original, materials, trace = history()
    state, check, event = imported(original, materials, partial=partial, alias=alias)
    expected = independent_resolution_inputs(state, check, POLICY)
    error, accepted = None, False
    if retained_event:
        state = changed(state, supersessions=(event,))
        state = sdk.load_json(sdk.dump_json(state), sdk.State)
    else:
        try:
            state = sdk.resolve(state, event, POLICY)
            accepted = True
        except ValueError as exc:
            error = str(exc)
    observation = state_observation(state, trace)
    observation.update(
        imported_via="ordinary State(...) with two actual content receipts",
        external_check=check.model_dump(mode="json"),
        resolve_accepted=accepted,
        resolve_error=error,
        independent_resolution_inputs_valid=expected,
    )
    met = (
        observation["domain_stop"] == "satisfied"
        if expected
        else observation["domain_stop"] != "satisfied" and not accepted
    )
    met = met and state.results == original.results and state.checks[:2] == original.checks
    return observation, met


def continuation_case():
    state, materials, trace = history(acquire=True)
    original = state.results
    first = sdk.run(
        state, (resolution_action(materials),), BUDGET, POLICY, handlers(materials, trace)
    )
    old = first.state.checks[-1]
    stale = sdk.invalidate(
        first.state,
        sdk.Invalidation(
            id="host-expiry",
            kind="check",
            target_id=old.id,
            obligation_id="readings",
            scope="local",
            reason="Host requires a current comparison",
        ),
    )
    before = sdk.plan(stale, (), BUDGET, POLICY).stop_reason
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "日本語 checkpoint.json"
        sdk.write_json(stale, path)
        loaded = sdk.read_json(path, sdk.State)
    second = sdk.run(
        loaded,
        (resolution_action(materials, "re-resolve"),),
        BUDGET,
        POLICY,
        handlers(materials, trace),
    )
    observation = state_observation(second.state, trace)
    observation.update(
        invalidated_stop=before,
        snapshot_equal=loaded == stale,
        original_receipts_preserved=second.state.results[:4] == original,
        independent_resolution_inputs_valid=independent_resolution_inputs(
            second.state, second.state.checks[-1], POLICY
        ),
    )
    met = (
        before != "satisfied"
        and loaded == stale
        and second.state.results[:4] == original
        and len(second.state.results) == 6
        and observation["actual_actions"] == 6
        and observation["independent_resolution_inputs_valid"]
        and observation["domain_stop"] == "satisfied"
    )
    return observation, met


def related_invalidation_case():
    state, materials, trace = history()
    first = sdk.run(
        state, (resolution_action(materials),), BUDGET, POLICY, handlers(materials, trace)
    )
    stale = sdk.invalidate(
        first.state,
        sdk.Invalidation(
            id="reading-expiry",
            kind="evidence",
            target_id="b",
            obligation_id="readings",
            scope="local",
            reason="The related reading is no longer current",
        ),
    )
    stale = sdk.load_json(sdk.dump_json(stale), sdk.State)
    oracle = independent_resolution_inputs(stale, stale.checks[-1], POLICY)
    observation = state_observation(stale, trace)
    observation["independent_resolution_inputs_valid"] = oracle
    return observation, (
        not oracle
        and observation["domain_stop"] != "satisfied"
        and stale.results == first.state.results
    )


def contract_revision_case(*, authority=False):
    state, materials, trace = history()
    first = sdk.run(
        state, (resolution_action(materials),), BUDGET, POLICY, handlers(materials, trace)
    )
    policy, revision = POLICY, "1"
    if authority:
        revision = "2"
        permission = changed(POLICY.handlers[1].checkers[0], revision=revision)
        policy = changed(
            POLICY,
            handlers=(POLICY.handlers[0], changed(POLICY.handlers[1], checkers=(permission,))),
        )
        updated = first.state
    else:
        updated = changed(
            first.state, obligations=(changed(state.obligations[0], contract_revision="2"),)
        )
    oracle_before = independent_resolution_inputs(updated, updated.checks[-1], policy)
    stop_before = sdk.plan(updated, (), BUDGET, policy).stop_reason
    pool = (
        verifier(materials["a"], "new-content-a", checker_revision=revision),
        verifier(materials["b"], "new-content-b", checker_revision=revision),
        resolution_action(materials, "new-resolution", revision=revision),
    )
    second = sdk.run(updated, pool, BUDGET, policy, handlers(materials, trace))
    observation = state_observation(second.state, trace, policy)
    observation.update(
        old_basis_valid=oracle_before,
        prior_domain_stop=stop_before,
        independent_resolution_inputs_valid=independent_resolution_inputs(
            second.state, second.state.checks[-1], policy
        ),
    )
    return observation, (
        not oracle_before
        and stop_before != "satisfied"
        and len(second.state.results) == 6
        and second.state.results[:3] == first.state.results
        and observation["independent_resolution_inputs_valid"]
        and observation["domain_stop"] == "satisfied"
    )


def subject_alias_case():
    state, materials, trace = history()
    state = changed(state, contradictions=())
    old = next(c for c in state.checks if c.basis.target.evidence_id == "a")
    state = sdk.invalidate(
        state,
        sdk.Invalidation(
            id="content-expiry",
            kind="check",
            target_id=old.id,
            obligation_id="readings",
            scope="local",
            reason="Need a new external threshold",
        ),
    )
    unknown = sdk.run(
        state,
        (verifier(materials["a"], "uncertain-check"),),
        BUDGET,
        POLICY,
        handlers(materials, trace, unavailable_threshold=True),
    )
    state, negative = unknown.state, unknown.state.checks[-1]
    alias = changed(materials["a"], id="a-alias")
    state = changed(state, evidence=(*state.evidence, alias))
    wrong = verifier(
        alias, "wrong-subject", purpose="check_resolution", resolution_target_id=negative.id
    )
    error = None
    try:
        sdk.make_basis(state, wrong)
    except ValueError as exc:
        error = str(exc)
    proper = verifier(
        materials["a"],
        "correct-subject",
        purpose="check_resolution",
        resolution_target_id=negative.id,
    )
    report = sdk.run(state, (proper,), BUDGET, POLICY, handlers(materials, trace))
    observation = state_observation(report.state, trace)
    observation.update(
        wrong_subject_error=error,
        exact_negative_id=negative.basis.target.evidence_id,
        negative_record_preserved=negative in report.state.checks,
    )
    return observation, (
        error is not None
        and negative in report.state.checks
        and report.state.checks[-1].basis.target.evidence_id == "a"
        and observation["domain_stop"] == "satisfied"
    )


def self_check_case():
    evidence = material("self", producer="checker")
    trace = []
    state = sdk.State(obligations=(obligation(minimum=1),))
    first = sdk.run(
        state, (read_action(evidence),), BUDGET, POLICY, handlers({evidence.id: evidence}, trace)
    )
    before = len(trace)
    report = sdk.run(first.state, (verifier(evidence),), BUDGET, POLICY, handlers({}, trace))
    observation = state_observation(report.state, trace)
    observation["known_self_identity"] = evidence.producer == "checker"
    return observation, (
        len(trace) == before
        and report.state.results == first.state.results
        and observation["known_self_identity"]
        and not report.state.checks
    )


def helper_progress_case():
    target = material("target", owner="task")
    old = material("old-helper", owner="helper")
    needed = changed(old, id="needed")
    state = sdk.State(
        obligations=(obligation("task", minimum=1), obligation("helper", minimum=1)),
        evidence=(target, old),
    )
    trace, materials = [], {needed.id: needed}
    first = sdk.run(state, (verifier(old),), BUDGET, POLICY, handlers(materials, trace))
    wanted = sdk.DependencyRequirement(
        evidence_id=needed.id, obligation_id="helper", scope="local", requirement="verified"
    )
    root = verifier(target, dependencies=(wanted,))

    def candidates(current):
        pool = [root]
        if not any(e.id == needed.id for e in current.evidence):
            pool.append(read_action(needed))
        else:
            pool.append(verifier(needed))
        return tuple(pool)

    report = sdk.run(first.state, candidates, BUDGET, POLICY, handlers(materials, trace))
    observation = state_observation(report.state, trace)
    observation.update(
        runner_stop=report.stop_reason,
        duplicate_raw_digest=needed.digest == old.digest,
        fulfilled_exact_id=any(e.id == needed.id for e in report.state.evidence),
    )
    expected_ids = {"needed", "target"}
    checked_ids = {c.basis.target.evidence_id for c in report.state.checks if c.status == "PASS"}
    return observation, (
        observation["duplicate_raw_digest"]
        and expected_ids <= checked_ids
        and report.state.results[0] == first.state.results[0]
        and len(report.state.results) == 4
        and observation["actual_actions"] == 4
        and observation["domain_stop"] == "satisfied"
    )


def file_case(*, snapshot=False):
    if snapshot:
        raw = (
            b"\xef\xbb\xbf"
            + (
                "order_id,amount,currency\r\n"
                + "".join(f"order-{i},1,USD\r\n" for i in range(10000))
            ).encode()
        )
        rules = (
            b'{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
            b'"minimum_amount":0,"allowed_currencies":["USD"]}'
        )
    else:
        raw = b"order_id,amount,currency\nA,9007199254740992,USD\n"
        rules = (
            b'{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
            b'"minimum_amount":9007199254740993.0,"allowed_currencies":["USD"]}'
        )
    with tempfile.TemporaryDirectory() as folder:
        data_path, rule_path = Path(folder) / "日本語 data.csv", Path(folder) / "rules.json"
        data_path.write_bytes(raw)
        rule_path.write_bytes(rules)
        output = check_data(data_path, rule_path)
        state = sdk.load_json(json.dumps(output["state"]), sdk.State)
        encoded = sdk.dump_json(state)
        loaded = sdk.load_json(encoded, sdk.State)
        unchanged = data_path.read_bytes() == raw and rule_path.read_bytes() == rules
    recorded_data = next(e for e in state.evidence if e.id == "dataset")
    recorded_rules = next(e for e in state.evidence if e.id == "dictionary")
    recorded_rows = len(json.loads(recorded_data.content)["rows"])
    observed = {
        "raw_csv_sha256": digest(raw),
        "raw_rules_sha256": digest(rules),
        "raw_csv_bytes": len(raw),
        "rules_numeric_text": rules.decode(),
        "rows": 10000 if snapshot else 1,
        "callback_calls": output["callback_calls"],
        "checks": [c.model_dump(mode="json") for c in state.checks],
        "actual_costs": [r.actual_resources.model_dump(mode="json") for r in state.results],
        "outcome": output["outcome"],
        "domain_stop": output["decision"]["stop_reason"],
        "snapshot_bytes": len(encoded.encode()),
        "snapshot_sha256": digest(encoded),
        "snapshot_equal": state == loaded,
        "inputs_unchanged": unchanged,
        "recorded_data_rows": recorded_rows,
        "recorded_data_digest_matches_raw": recorded_data.digest == digest(raw),
        "recorded_rules_digest_matches_raw": recorded_rules.digest == digest(rules),
    }
    if snapshot:
        met = (
            len(raw) <= 1048576
            and observed["snapshot_bytes"] > 1048576
            and state == loaded
            and unchanged
            and len(state.results) == 4
            and len(state.checks) == 2
            and recorded_rows == 10000
            and observed["domain_stop"] == "satisfied"
        )
    else:
        independent_valid = Decimal("9007199254740992") >= Decimal("9007199254740993.0")
        observed["independent_amount_meets_threshold"] = independent_valid
        met = (
            not independent_valid
            and any(c.status == "FAIL" for c in state.checks)
            and observed["domain_stop"] != "satisfied"
            and unchanged
        )
    return observed, (
        met and recorded_data.digest == digest(raw) and recorded_rules.digest == digest(rules)
    )


def proof_case():
    records = tuple(material(f"e{i}", str(i + 1)) for i in range(4))
    owner = changed(obligation(minimum=4), required_verifiers=("v1", "v2"))
    permissions = tuple(sdk.CheckerPermission(checker_id=i) for i in ("v1", "v2"))
    policy = changed(
        POLICY,
        trusted_verifiers=("v1", "v2"),
        handlers=(changed(POLICY.handlers[1], checkers=permissions),),
    )
    state = sdk.State(obligations=(owner,), evidence=records)
    pool = tuple(
        verifier(
            e,
            f"{checker}-{e.id}",
            checker_id=checker,
            dependencies=() if i == 0 else (dependency(records[i - 1], "verified"),),
        )
        for i, e in enumerate(records)
        for checker in ("v1", "v2")
    )
    trace = []
    report = sdk.run(state, pool, BUDGET, policy, handlers({}, trace))
    observation = state_observation(report.state, trace, policy)
    actual = {
        (c.basis.target.evidence_id, c.verifier_id)
        for c in report.state.checks
        if c.status == "PASS"
    }
    expected = {(e.id, checker) for e in records for checker in ("v1", "v2")}
    raw_truth = all(int(e.content) == i + 1 for i, e in enumerate(records))
    observation.update(independent_grounded_dag_truth=raw_truth, verified_pairs=sorted(actual))
    return observation, (
        raw_truth
        and actual == expected
        and len(report.state.results) == 8
        and observation["actual_actions"] == observation["actual_verifications"] == 8
        and observation["domain_stop"] == "satisfied"
    )


def run_audit() -> dict:
    from benchmarks.compatibility import require_original_sdk

    require_original_sdk()
    cases = (
        ("EGR021-02", "partial-external-basis", lambda: imported_case(partial=True)),
        ("EGR021-02", "same-digest-related-alias", lambda: imported_case(alias=True)),
        ("EGR021-02", "valid-all-related-external-basis", imported_case),
        (
            "EGR021-02",
            "retained-old-partial-event",
            lambda: imported_case(partial=True, retained_event=True),
        ),
        ("EGR021-02", "related-evidence-invalidation", related_invalidation_case),
        ("EGR021-02", "contract-update-and-new-resolution", contract_revision_case),
        (
            "EGR021-02",
            "checker-revision-update-and-new-resolution",
            lambda: contract_revision_case(authority=True),
        ),
        ("EGR020-01/02", "paid-invalidation-save-load-re-resolution", continuation_case),
        ("EGR020-03", "negative-subject-alias", subject_alias_case),
        ("EGR020-04", "known-prohibited-self-verification", self_check_case),
        ("EGR020-05/08", "satisfied-helper-duplicate-exact-binding", helper_progress_case),
        ("EGR020-06", "actual-file-exact-decimal", file_case),
        ("EGR020-07", "supported-large-snapshot", lambda: file_case(snapshot=True)),
        ("EGR020-09", "small-grounded-proof-dag", proof_case),
    )
    rows = []
    for finding, name, case in cases:
        try:
            observation, met = case()
            error = None
        except Exception as exc:
            observation, met, error = None, False, f"{type(exc).__name__}: {exc}"
        rows.append(
            {
                "finding": finding,
                "case": name,
                "observation": observation,
                "independent_expected_property_met": bool(met),
                "exception": error,
                "old021_issue_reproduced": sdk.__version__ == "0.2.1"
                and name
                in {
                    "partial-external-basis",
                    "same-digest-related-alias",
                    "retained-old-partial-event",
                }
                and observation is not None
                and observation["domain_stop"] == "satisfied"
                and not observation["independent_resolution_inputs_valid"],
            }
        )
    return {
        "schema": "egr-022-audit-v1",
        "sdk_version": sdk.__version__,
        "sdk_import": str(Path(sdk.__file__).resolve()),
        "python": platform.python_version(),
        "os": platform.platform(),
        "pydantic": metadata.version("pydantic"),
        "pydantic_core": metadata.version("pydantic_core"),
        "cases": rows,
        "all_expected_properties_met": all(
            row["independent_expected_property_met"] for row in rows
        ),
        "scope": (
            "Finite functional diagnostics; not timing, population inference "
            "or confirmatory holdout"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write UTF-8 diagnostic JSON; stdout otherwise")
    args = parser.parse_args(argv)
    report = run_audit()
    text = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
