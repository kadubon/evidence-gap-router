"""A01: changing real dictionary bytes triggers the actual orders checker again."""

import hashlib
import json
from pathlib import Path

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CallbackView,
    DependencyRequirement,
    Evidence,
    Policy,
    Resources,
    State,
    Supersession,
    declare_completion,
    load_json,
    plan,
    run,
)
from evidence_gap_router.data_quality import Rules, parse_rules, read_local_bytes, validate_dataset
from evidence_gap_router.demo import run_demo


def test_changed_real_dictionary_gets_pass_but_rechecked_dataset_fails(tmp_path: Path):
    original = run_demo()
    current = load_json(json.dumps(original["state"]), State)
    policy = original["decision"]["coverage"]["policy"]
    policy = Policy.model_validate_json(json.dumps(policy))
    old_dictionary = next(e for e in current.evidence if e.id == "dictionary")
    rules = json.loads(old_dictionary.content)
    rules["minimum_amount"] = 1000
    path = tmp_path / "新しい rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    raw = read_local_bytes(path)
    strict = parse_rules(raw)
    replacement = Evidence(
        **{
            **old_dictionary.model_dump(),
            "id": "strict-dictionary",
            "digest": hashlib.sha256(raw).hexdigest(),
            "content": strict.model_dump_json(),
            "reference": str(path),
        }
    )
    current = State(
        **{
            **current.model_dump(),
            "evidence": (*current.evidence, replacement),
            "supersessions": (
                *current.supersessions,
                Supersession(
                    id="dictionary-revision",
                    kind="evidence",
                    target_id="dictionary",
                    replacement_id=replacement.id,
                    reason="Host supplied stricter real rules",
                ),
            ),
        }
    )
    # A host changes the declared exact catalogue identity; history remains immutable.
    for contract in tuple(current.completion_contracts):
        values = contract.model_dump()
        values.update(id=contract.id + "-strict", revision="2", change_reason="Stricter rules")
        if values["target"]["evidence_id"] == "dictionary":
            values["target"]["evidence_id"] = replacement.id
        for material in values["materials"]:
            for requirement in material["any_of"]:
                if requirement["evidence_id"] == "dictionary":
                    requirement["evidence_id"] = replacement.id
        current = declare_completion(current, type(contract)(**values))
    obligation = next(o for o in current.obligations if o.id == "dictionary-quality")
    dataset = next(e for e in current.evidence if e.id == "dataset")
    dictionary_check = ActionCandidate(
        id="check-new-dictionary",
        obligation_id=obligation.id,
        scope=obligation.scope,
        kind="verify",
        handler_id="verify-quality",
        target_evidence_id=replacement.id,
        target_digest=replacement.digest,
        checker_id="dictionary-checker",
        resources=Resources(actions=1, verifications=1, tokens=0),
    )
    dataset_check = ActionCandidate(
        id="check-dataset-under-new-rules",
        obligation_id=dataset.obligation_id,
        scope=dataset.scope,
        kind="verify",
        handler_id="verify-quality",
        target_evidence_id=dataset.id,
        target_digest=dataset.digest,
        checker_id="orders-checker",
        dependencies=(
            DependencyRequirement(
                evidence_id=replacement.id,
                obligation_id=obligation.id,
                scope=obligation.scope,
                requirement="verified",
                contract_fingerprint=obligation.contract_fingerprint,
            ),
        ),
        resources=Resources(actions=1, verifications=1, tokens=0),
    )
    budget = Budget(limits=Resources(actions=6, verifications=4))
    decision = plan(current, (dataset_check, dictionary_check), budget, policy)
    assert decision.stop_reason != "satisfied"
    assert any(g.target_evidence_id == "dataset" for g in decision.gaps)

    def verify(view: CallbackView):
        if view.action.checker_id == "dictionary-checker":
            Rules.model_validate_json(view.inputs[0].content)
            errors = ()
        else:
            records = {e.id: e for e in view.inputs}
            rules = Rules.model_validate_json(records[replacement.id].content)
            errors = validate_dataset(json.loads(records[dataset.id].content), rules)
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            checks=(
                view.check(
                    status="FAIL" if errors else "PASS",
                    reason="; ".join(errors) if errors else "Strict rules are valid",
                ),
            ),
        )

    report = run(
        current, (dataset_check, dictionary_check), budget, policy, {"verify-quality": verify}
    )
    assert report.decision.stop_reason == "escalation_required"
    assert report.callback_calls == ("verify-quality", "verify-quality")
    assert report.receipts[0].checks[0].status == "PASS"
    assert report.receipts[1].checks[0].status == "FAIL"
    assert report.receipts[1].checks[0].basis.dependencies[0].evidence_id == replacement.id
    assert all(old in report.state.checks for old in current.checks)
    assert report.decision.coverage.satisfied == 1
    assert report.decision.coverage.required == 2
