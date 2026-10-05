"""Bounded core audit probes for the published 0.2.0 baseline (real receipts)."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from time import perf_counter
from unittest.mock import patch

import evidence_gap_router.router as module
from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    Contradiction,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    State,
    Supersession,
    __version__,
    observe,
    plan,
    resolve,
    start,
)
from evidence_gap_router.runner import CallbackView


def changed(record, **values):
    return type(record)(**{**record.model_dump(), **values})


def policy():
    return Policy(
        trusted_verifiers=("v1", "v2"),
        handlers=(
            HandlerRegistration(handler_id="read", roles=("investigate",)),
            HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=tuple(
                    CheckerPermission(
                        checker_id=v,
                        purposes=("content", "check_resolution", "contradiction_resolution"),
                    )
                    for v in ("v1", "v2")
                ),
            ),
        ),
    )


BUDGET = Budget(limits=Resources(actions=1000, verifications=1000))


def evidence(identifier="e", obligation="o", producer="reader"):
    return Evidence(
        id=identifier,
        obligation_id=obligation,
        scope="s",
        content="4",
        digest=sha256(b"4").hexdigest(),
        producer=producer,
        source="source",
        provenance_group="group",
    )


def check_action(e, identifier="check", **values):
    return ActionCandidate(
        **{
            "id": identifier,
            "obligation_id": e.obligation_id,
            "scope": e.scope,
            "kind": "verify",
            "handler_id": "check",
            "target_evidence_id": e.id,
            "target_digest": e.digest,
            "checker_id": "v1",
            "resources": Resources(actions=1, verifications=1),
            **values,
        }
    )


def execute(state, candidate, identifier, status=None, evidence_record=None, conflict=None):
    issued = start(state, candidate, identifier, BUDGET, policy(), candidates=(candidate,))
    attempt = issued.attempts[-1]
    view = CallbackView(
        action=candidate,
        attempt_id=identifier,
        obligation=next(o for o in state.obligations if o.id == candidate.obligation_id),
        basis=attempt.basis,
        inputs=tuple(
            next(e for e in state.evidence if e.id == b.evidence_id) for b in attempt.inputs
        ),
    )
    if candidate.kind == "verify":
        accepted = int(view.inputs[0].content or "") >= 0
        if status == "BOTH":
            positive = view.check(
                status="PASS" if accepted else "FAIL", reason="Actual nonnegative comparison"
            )
            odd = int(view.inputs[0].content or "") % 2 == 1
            negative = changed(
                view.check(status="PASS" if odd else "FAIL", reason="Actual oddness comparison"),
                id=f"{identifier}:odd",
            )
            checks = (positive, negative)
        else:
            checks = (
                view.check(
                    status=status or ("PASS" if accepted else "FAIL"),
                    reason="Actual integer comparison",
                ),
            )
        receipt = view.result(actual_resources=Resources(actions=1, verifications=1), checks=checks)
    else:
        receipt = view.result(
            actual_resources=Resources(actions=1, verifications=0),
            evidence=() if evidence_record is None else (evidence_record,),
            contradictions=() if conflict is None else (conflict,),
        )
    return observe(issued, receipt)


def history(contradiction=False, required_verifiers=()):
    e = evidence()
    state = State(
        obligations=(
            Obligation(
                id="o",
                description="integer",
                scope="s",
                acceptance="nonnegative",
                required_verifiers=required_verifiers,
            ),
        )
    )
    read = ActionCandidate(
        id="read", obligation_id="o", scope="s", kind="investigate", handler_id="read"
    )
    conflict = (
        Contradiction(
            id="conflict",
            obligation_id="o",
            scope="s",
            evidence_ids=("e",),
            reason="Declared conflict",
        )
        if contradiction
        else None
    )
    state = execute(state, read, "read-attempt", evidence_record=e, conflict=conflict)
    return execute(state, check_action(e), "check-attempt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--alias-snapshot")
    options = parser.parse_args()
    output = {"version": __version__, "execution": "real start/observe receipts"}
    state = history()
    try:
        changed(state, evidence=(changed(state.evidence[0], expired=True),))
        rejected = False
    except ValueError:
        rejected = True
    output["EGR020-01"] = {
        "issue_reproduced": rejected,
        "attempts": len(state.attempts),
        "results": len(state.results),
    }
    conflicted = history(True)
    candidate = check_action(
        evidence(), "resolve-1", purpose="contradiction_resolution", resolution_target_id="conflict"
    )
    resolved = execute(conflicted, candidate, "resolve-1")
    resolved = resolve(
        resolved,
        Supersession(
            id="event-1",
            kind="contradiction",
            target_id="conflict",
            check_id=resolved.checks[-1].id,
            reason="Checked",
        ),
        policy(),
    )
    new = changed(resolved, obligations=(changed(resolved.obligations[0], contract_revision="2"),))
    new = execute(new, check_action(evidence(), "new-content"), "new-content")
    new = execute(new, changed(candidate, id="resolve-2"), "resolve-2")
    try:
        resolve(
            new,
            Supersession(
                id="event-2",
                kind="contradiction",
                target_id="conflict",
                check_id=new.checks[-1].id,
                reason="New contract",
            ),
            policy(),
        )
        blocked = False
    except ValueError:
        blocked = True
    output["EGR020-02"] = {
        "issue_reproduced": blocked,
        "attempts": len(new.attempts),
        "results": len(new.results),
    }
    failed = State(obligations=(changed(state.obligations[0], acceptance="nonnegative and odd"),))
    failed = execute(
        failed,
        ActionCandidate(
            id="get-main", obligation_id="o", scope="s", kind="investigate", handler_id="read"
        ),
        "main",
        evidence_record=evidence(),
    )
    failed = execute(failed, check_action(evidence(), "negative"), "negative", status="BOTH")
    alias = evidence("alias")
    failed = execute(
        failed,
        ActionCandidate(
            id="get-alias", obligation_id="o", scope="s", kind="investigate", handler_id="read"
        ),
        "alias",
        evidence_record=alias,
    )
    candidate = check_action(
        alias, "wrong-alias", purpose="check_resolution", resolution_target_id="negative:odd"
    )
    wrong = execute(failed, candidate, "wrong-alias")
    wrong = resolve(
        wrong,
        Supersession(
            id="wrong-event",
            kind="check",
            target_id="negative:odd",
            replacement_id=wrong.checks[-1].id,
            reason="Alias",
        ),
        policy(),
    )
    if options.alias_snapshot:
        from pathlib import Path

        Path(options.alias_snapshot).write_text(wrong.model_dump_json(), encoding="utf-8")
    output["EGR020-03"] = {
        "issue_reproduced": plan(wrong, (), BUDGET, policy()).stop_reason == "satisfied",
        "wrong_subject_resolution_accepted": True,
        "false_satisfied": plan(wrong, (), BUDGET, policy()).stop_reason == "satisfied",
        "attempts": len(wrong.attempts),
    }
    self_state = State(obligations=state.obligations)
    self_evidence = evidence(producer="v1")
    self_state = execute(
        self_state,
        ActionCandidate(
            id="read", obligation_id="o", scope="s", kind="investigate", handler_id="read"
        ),
        "read",
        evidence_record=self_evidence,
    )
    candidate = check_action(self_evidence)
    output["EGR020-04"] = {
        "issue_reproduced": plan(self_state, (candidate,), BUDGET, policy()).action is not None
    }
    rules = changed(state.obligations[0], id="rules")
    task = changed(state.obligations[0], id="task")
    helper_state = State(obligations=(rules, task))
    helper_evidence = evidence("rule-old", "rules")
    helper_state = execute(
        helper_state,
        ActionCandidate(
            id="get-rule", obligation_id="rules", scope="s", kind="investigate", handler_id="read"
        ),
        "rule-read",
        evidence_record=helper_evidence,
    )
    helper_state = execute(helper_state, check_action(helper_evidence, "check-rules"), "rule-check")
    task_evidence = evidence("task-data", "task")
    helper_state = execute(
        helper_state,
        ActionCandidate(
            id="get-task", obligation_id="task", scope="s", kind="investigate", handler_id="read"
        ),
        "task-read",
        evidence_record=task_evidence,
    )
    get_extra = ActionCandidate(
        id="get-extra",
        obligation_id="rules",
        scope="s",
        kind="investigate",
        handler_id="read",
        produces_evidence_id="rules-extra",
    )
    verify_task = check_action(
        task_evidence,
        "task-check",
        dependencies=(
            DependencyRequirement(evidence_id="rules-extra", obligation_id="rules", scope="s"),
        ),
    )
    decision = plan(helper_state, (get_extra, verify_task), BUDGET, policy())
    output["EGR020-05"] = {
        "issue_reproduced": decision.action is None,
        "exclusions": [e.model_dump(mode="json") for e in decision.exclusions],
        "attempts": len(helper_state.attempts),
    }
    counts = []
    for n in (4, 8, 10):
        obligations = tuple(
            Obligation(
                id=f"o{i}",
                description="integer",
                scope="s",
                acceptance="nonnegative",
                required_verifiers=("v1", "v2"),
            )
            for i in range(n)
        )
        chain = State(obligations=obligations)
        for i in range(n):
            e = evidence(f"e{i}", f"o{i}")
            chain = execute(
                chain,
                ActionCandidate(
                    id=f"read{i}",
                    obligation_id=f"o{i}",
                    scope="s",
                    kind="investigate",
                    handler_id="read",
                ),
                f"read{i}",
                evidence_record=e,
            )
            dependencies = (
                ()
                if i == 0
                else (
                    DependencyRequirement(
                        evidence_id=f"e{i - 1}",
                        obligation_id=f"o{i - 1}",
                        scope="s",
                        requirement="verified",
                    ),
                )
            )
            for v in ("v1", "v2"):
                chain = execute(
                    chain,
                    check_action(e, f"check{i}-{v}", checker_id=v, dependencies=dependencies),
                    f"check{i}-{v}",
                )
        with patch.object(module, "_trusted_check", wraps=module._trusted_check) as tracked:
            started = perf_counter()
            decision = plan(chain, (), BUDGET, policy())
            counts.append(
                {
                    "targets": n,
                    "checks": len(chain.checks),
                    "calls": tracked.call_count,
                    "seconds": perf_counter() - started,
                    "stop": decision.stop_reason,
                }
            )
    output["EGR020-09"] = {
        "issue_reproduced": counts[-1]["calls"] > counts[0]["calls"] * 50,
        "diagnostic": counts,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
