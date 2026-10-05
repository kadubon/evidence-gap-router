"""Shortest packaged example wrapping an existing plain Python checker."""

from __future__ import annotations

from hashlib import sha256

from .models import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from .runner import CallbackView, RunReport, run


def legacy_checker(answer: str) -> bool:
    """An existing application function needs no framework-specific adapter."""
    return int(answer) == 2 + 2


def run_callback_example() -> RunReport:
    obligation = Obligation(
        id="sum",
        description="Check the sum",
        scope="example",
        acceptance="answer equals 2 + 2",
        required_verifiers=("arithmetic-check",),
    )
    evidence = Evidence(
        id="answer",
        obligation_id="sum",
        scope="example",
        content="4",
        digest=sha256(b"4").hexdigest(),
        producer="calculator",
        source="local calculation",
        provenance_group="calculator",
    )
    action = ActionCandidate(
        id="check-sum",
        obligation_id="sum",
        scope="example",
        kind="verify",
        handler_id="check",
        target_evidence_id="answer",
        target_digest=evidence.digest,
        checker_id="arithmetic-check",
        resources=Resources(actions=1, verifications=1),
    )

    def check(view: CallbackView) -> Result:
        accepted = legacy_checker(view.inputs[0].content or "")
        return view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(
                view.check(status="PASS" if accepted else "FAIL", reason="Compared with 2 + 2"),
            ),
        )

    return run(
        State(obligations=(obligation,), evidence=(evidence,)),
        (action,),
        Budget(limits=Resources(actions=1, verifications=1)),
        Policy(
            trusted_verifiers=("arithmetic-check",),
            handlers=(
                HandlerRegistration(
                    handler_id="check",
                    roles=("verify",),
                    checkers=(CheckerPermission(checker_id="arithmetic-check"),),
                ),
            ),
        ),
        {"check": check},
    )
