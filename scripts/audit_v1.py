"""Reproduce A01-A12 with an installed 0.1.0 (not a v2 regression suite).

Run outside the checkout with Python from a fresh official v0.1.0 installation.
No supplied audit artifacts were attached; these probes derive from the prompt.
"""

import hashlib
import importlib.metadata
import json
import platform
import tempfile
from pathlib import Path

from evidence_gap_router import (
    ActionCandidate,
    Attempt,
    Budget,
    CheckResult,
    Contradiction,
    Evidence,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
    Supersession,
    observe,
    plan,
    start,
)
from evidence_gap_router.demo import run_demo, run_host_loop


def change(record, **updates):
    return type(record)(**{**record.model_dump(), **updates})


def main():
    assert importlib.metadata.version("evidence-gap-router") == "0.1.0"
    digest = hashlib.sha256(b"one").hexdigest()
    other = hashlib.sha256(b"two").hexdigest()
    obligation = Obligation(id="o", description="display", scope="s", acceptance="original")
    evidence = Evidence(
        id="e1",
        obligation_id="o",
        scope="s",
        digest=digest,
        content="one",
        producer="reader",
        source="s1",
        provenance_group="g1",
    )
    passed = CheckResult(
        id="pass",
        obligation_id="o",
        scope="s",
        target_digest=digest,
        verifier_id="v1",
        status="PASS",
        reason="content checked",
    )
    policy = Policy(trusted_verifiers=("v1", "v2"), executable_handlers=("read", "check"))
    budget = Budget(limits=Resources(actions=10, verifications=10))
    acquire = ActionCandidate(
        id="read",
        obligation_id="o",
        scope="s",
        kind="investigate",
        handler_id="read",
    )
    verify = ActionCandidate(
        id="a-checked",
        obligation_id="o",
        scope="s",
        kind="verify",
        handler_id="check",
        target_digest=digest,
        resources=Resources(actions=1, verifications=1),
    )
    base = State(obligations=(obligation,), evidence=(evidence,), checks=(passed,))
    probes = {}

    report = run_demo()
    original = State.model_validate_json(json.dumps(report["state"]))
    records = {e.id: e for e in original.evidence}
    rules = json.loads(records["dictionary"].content)
    rules["minimum_amount"] = 1000
    content = json.dumps(rules, sort_keys=True, separators=(",", ":"))
    replacement = change(
        records["dictionary"],
        id="strict-dictionary",
        content=content,
        digest=hashlib.sha256(content.encode()).hexdigest(),
    )
    new_check = CheckResult(
        id="strict-dictionary-pass",
        obligation_id="data-quality",
        scope="artificial-orders",
        target_digest=replacement.digest,
        verifier_id="quality-validator",
        status="PASS",
        reason="dictionary has valid structure; dataset not rechecked",
    )
    updated = change(
        original,
        evidence=(*original.evidence, replacement),
        checks=(*original.checks, new_check),
        supersessions=(
            Supersession(
                id="dict-update",
                kind="evidence",
                target_id="dictionary",
                replacement_id=replacement.id,
                reason="new rules",
            ),
        ),
    )
    demo_policy = Policy(trusted_verifiers=("quality-validator",))
    stop = plan(updated, (), Budget(limits=Resources()), demo_policy).stop_reason
    probes["A01"] = {
        "issue_reproduced": stop == "satisfied",
        "stop": stop,
        "new_minimum_amount": 1000,
        "dataset_rechecked": False,
    }

    failed = change(passed, id="fail", status="FAIL", reason="negative observation")
    negative = change(base, checks=(passed, failed))
    issued = start(negative, acquire, "acquisition", budget, policy)
    receipt = Result(
        id="result",
        attempt_id="acquisition",
        action_id="read",
        obligation_id="o",
        scope="s",
        actual_resources=Resources(actions=1, verifications=0),
        supersessions=(
            Supersession(
                id="replace-fail",
                kind="check",
                target_id="fail",
                replacement_id="pass",
                reason="reuse generic PASS",
            ),
        ),
    )
    stop = plan(observe(issued, receipt), (), budget, policy).stop_reason
    probes["A02"] = {"issue_reproduced": stop == "satisfied", "stop": stop, "new_verifications": 0}
    contradiction = Contradiction(
        id="conflict",
        obligation_id="o",
        scope="s",
        evidence_ids=("e1",),
        reason="declared relation",
    )
    conflicted = change(base, contradictions=(contradiction,))
    issued = start(conflicted, acquire, "acquisition", budget, policy)
    receipt = change(
        receipt,
        supersessions=(
            Supersession(
                id="resolve",
                kind="contradiction",
                target_id="conflict",
                check_id="pass",
                reason="generic content PASS",
            ),
        ),
    )
    stop = plan(observe(issued, receipt), (), budget, policy).stop_reason
    probes["A03"] = {"issue_reproduced": stop == "satisfied", "stop": stop}

    evidence2 = change(
        evidence, id="e2", digest=other, content="two", source="s2", provenance_group="g2"
    )
    partial = change(
        base, obligations=(change(obligation, min_evidence=2),), evidence=(evidence, evidence2)
    )
    second_verify = change(verify, id="z-unchecked", target_digest=other)
    selected = plan(partial, (second_verify, verify), budget, policy).action
    probes["A04"] = {"issue_reproduced": selected.id == "a-checked", "selected": selected.id}
    provenance_gap = change(base, obligations=(change(obligation, min_provenance_groups=2),))
    same = change(acquire, id="a-same", kind="diversify", source="s1", provenance_group="g1")
    novel = change(same, id="z-novel", source="s2", provenance_group="g2")
    selected = plan(provenance_gap, (novel, same), budget, policy).action
    probes["A05"] = {"issue_reproduced": selected.id == "a-same", "selected": selected.id}
    multiple = change(base, obligations=(change(obligation, required_verifiers=("v1", "v2")),))
    selected = plan(
        multiple, (acquire,), budget, change(policy, max_pending_verifications=1)
    ).action
    probes["A06"] = {
        "issue_reproduced": selected is not None,
        "selected": selected.id if selected else None,
        "missing_verifier": "v2",
    }
    dict_obligation = change(obligation, id="dictionary")
    dictionary = change(evidence, id="dictionary", obligation_id="dictionary")
    cross = State(obligations=(obligation, dict_obligation), evidence=(evidence, dictionary))
    candidate = change(verify, requires_evidence_ids=("dictionary",))
    decision = plan(cross, (candidate,), budget, policy)
    reasons = [r for exclusion in decision.exclusions for r in exclusion.reasons]
    probes["A07"] = {"issue_reproduced": "prerequisite_missing" in reasons, "reasons": reasons}

    with tempfile.TemporaryDirectory(prefix="egr-v1-probes-") as temporary:
        folder = Path(temporary)
        data = folder / "orders.csv"
        dictionary_file = folder / "rules.json"
        dictionary_file.write_text(json.dumps(rules | {"minimum_amount": 0}), encoding="utf-8")
        data.write_text("order_id,amount,amount,currency\nA,-999,10,USD\n", encoding="utf-8")
        stop = run_demo(data_path=data, dictionary_path=dictionary_file)["decision"]["stop_reason"]
        probes["A08"] = {"issue_reproduced": stop == "satisfied", "stop": stop}
        data.write_text("order_id,amount,currency\nA,10,USD\n", encoding="utf-8")
        duplicate = json.dumps(rules | {"minimum_amount": 1000})[:-1] + ',"minimum_amount":0}'
        dictionary_file.write_text(duplicate, encoding="utf-8")
        stop = run_demo(data_path=data, dictionary_path=dictionary_file)["decision"]["stop_reason"]
        probes["A09"] = {"issue_reproduced": stop == "satisfied", "stop": stop}

    calls = 0

    def empty_callback(action, attempt_id, _state):
        nonlocal calls
        calls += 1
        if calls == 8:
            raise RuntimeError("audit safety stop after eight invocations")
        return Result(
            id=f"r-{calls}",
            attempt_id=attempt_id,
            action_id=action.id,
            obligation_id="o",
            scope="s",
            actual_resources=Resources(actions=1, verifications=0),
        )

    def fresh(current):
        return (change(acquire, id=f"fresh-{len(current.attempts)}"),)

    run_host_loop(
        State(obligations=(obligation,)),
        fresh,
        Budget(limits=Resources()),
        policy,
        {"read": empty_callback},
    )
    probes["A10"] = {
        "issue_reproduced": calls == 8,
        "callback_calls": calls,
        "termination": "audit callback injected safety exception",
    }
    previous = Attempt(id="host-attempt-2", action=change(acquire, id="old"))
    previous_result = Result(
        id="old-result",
        attempt_id=previous.id,
        action_id="old",
        obligation_id="o",
        scope="s",
        actual_resources=Resources(actions=1, verifications=0),
    )
    resumed = State(obligations=(obligation,), attempts=(previous,), results=(previous_result,))
    try:
        run_host_loop(resumed, (acquire,), budget, policy, {"read": empty_callback})
    except ValueError as exc:
        probes["A11"] = {"issue_reproduced": "collision" in str(exc), "error": str(exc)}
    else:
        probes["A11"] = {"issue_reproduced": False}
    changed_contract = change(
        base, obligations=(change(obligation, acceptance="new strict rules"),)
    )
    stop = plan(changed_contract, (), budget, policy).stop_reason
    probes["A12"] = {"issue_reproduced": stop == "satisfied", "stop": stop}
    print(
        json.dumps(
            {
                "baseline_commit": "76b9f40f42f3fc13fb535032bb06fdd762d5bffa",
                "version": importlib.metadata.version("evidence-gap-router"),
                "python": platform.python_version(),
                "os": platform.platform(),
                "pydantic": importlib.metadata.version("pydantic"),
                "probes": probes,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
