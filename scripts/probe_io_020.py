"""Reproduce the three v0.2.0 I/O/runner findings; not a post-fix pass oracle.

Run this file with the selected installed wheel's Python interpreter. The probe
records observed behavior; issue_reproduced=True means the old issue occurred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import tempfile
from pathlib import Path

import pydantic

import evidence_gap_router as egr
from evidence_gap_router.file_checks import check_data


def probe() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="egr-v021-original-") as directory:
        root = Path(directory)
        data = root / "data.csv"
        dictionary = root / "rules.json"
        raw = (
            b'{"required_columns":["order_id","amount","currency"],'
            b'"primary_key":"order_id","minimum_amount":9007199254740993.0,'
            b'"allowed_currencies":["USD"]}'
        )
        dictionary.write_bytes(raw)
        data.write_bytes(b"order_id,amount,currency\nA,9007199254740992,USD\n")
        numeric = check_data(data, dictionary)
        numeric_observation = {
            "issue_reproduced": numeric["outcome"] == "satisfied",
            "outcome": numeric["outcome"],
            "retained_content": numeric["state"]["evidence"][0]["content"],
            "raw_dictionary_sha256": hashlib.sha256(raw).hexdigest(),
        }
        dictionary.write_bytes(raw.replace(b"9007199254740993.0", b"0"))
        csv = (
            "order_id,amount,currency\n" + "".join(f"A{i},10,USD\n" for i in range(10_000))
        ).encode()
        data.write_bytes(csv)
        large = check_data(data, dictionary)
        state = egr.State.model_validate_json(json.dumps(large["state"]))
        snapshot = egr.dump_json(state)
        reload_error = None
        try:
            egr.load_json(snapshot, egr.State)
        except ValueError as exc:
            reload_error = str(exc)
        size_observation = {
            "issue_reproduced": reload_error is not None,
            "outcome": large["outcome"],
            "csv_bytes": len(csv),
            "snapshot_bytes": len(snapshot.encode()),
            "reload_error": reload_error,
            "attempts": len(state.attempts),
            "results": len(state.results),
        }

    task = egr.Obligation(
        id="task",
        scope="task",
        description="actualtask",
        acceptance="target plus declared material",
        required_verifiers=("v",),
    )
    helper = egr.Obligation(
        id="helper",
        scope="helper",
        description="helper",
        acceptance="extra material",
        required=False,
    )
    budget = egr.Budget(limits=egr.Resources(actions=10, verifications=10))
    policy = egr.Policy(
        trusted_verifiers=("v",),
        handlers=(
            egr.HandlerRegistration(handler_id="read", roles=("investigate",)),
            egr.HandlerRegistration(
                handler_id="verify",
                roles=("verify",),
                checkers=(egr.CheckerPermission(checker_id="v"),),
            ),
        ),
    )

    def acquisition(identifier: str, oid: str, scope: str) -> egr.ActionCandidate:
        return egr.ActionCandidate(
            id=f"read-{identifier}",
            obligation_id=oid,
            scope=scope,
            kind="investigate",
            handler_id="read",
            produces_evidence_id=identifier,
        )

    def reader(view: egr.CallbackView) -> egr.Result:
        identifier = view.action.produces_evidence_id
        assert identifier is not None
        target = identifier == "target"
        evidence = egr.Evidence(
            id=identifier,
            obligation_id=view.action.obligation_id,
            scope=view.action.scope,
            digest=("a" if target else "b") * 64,
            content="target" if target else "same material",
            producer="read",
            source="target-source" if target else "same-source",
            provenance_group="target-group" if target else "same-group",
        )
        return view.result(
            actual_resources=egr.Resources(actions=1, verifications=0),
            evidence=(evidence,),
        )

    state = egr.State(obligations=(task, helper))
    for action in (
        acquisition("target", "task", "task"),
        acquisition("old-alias", "helper", "helper"),
    ):
        state = egr.step(state, (action,), budget, policy, {"read": reader}).state
    verify = egr.ActionCandidate(
        id="verify-target",
        obligation_id="task",
        scope="task",
        kind="verify",
        handler_id="verify",
        target_evidence_id="target",
        target_digest="a" * 64,
        checker_id="v",
        resources=egr.Resources(actions=1, verifications=1),
        dependencies=(
            egr.DependencyRequirement(
                evidence_id="required-exact",
                obligation_id="helper",
                scope="helper",
            ),
        ),
    )

    def checker(view: egr.CallbackView) -> egr.Result:
        return view.result(
            actual_resources=egr.Resources(actions=1, verifications=1),
            checks=(view.check(status="PASS", reason="actual matching materials"),),
        )

    report = egr.run(
        state,
        (acquisition("required-exact", "helper", "helper"), verify),
        budget,
        policy,
        {"read": reader, "verify": checker},
    )
    return {
        "probe_semantics": "issue_reproduced is an observed old issue, not a corrected oracle",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "pydantic": pydantic.__version__,
            "egr_version": egr.__version__,
            "import_path": str(egr.__file__),
        },
        "EGR020-06": numeric_observation,
        "EGR020-07": size_observation,
        "EGR020-08": {
            "issue_reproduced": report.stop_reason == "no_progress"
            and report.decision.action is not None,
            "runner_stop": report.stop_reason,
            "next_action": report.decision.action.id if report.decision.action else None,
            "calls": report.callback_calls,
            "before_attempts": len(state.attempts),
            "after_attempts": len(report.state.attempts),
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(probe(), ensure_ascii=True, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
