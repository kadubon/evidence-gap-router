"""Minimal custom callback; the sample host records callback errors safely."""

from hashlib import sha256

from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckResult,
    Evidence,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from evidence_gap_router.demo import run_host_loop

content = "4"
digest = sha256(content.encode()).hexdigest()
state = State(
    obligations=(
        Obligation(
            id="sum", description="Check the sum", scope="example", acceptance="answer equals 2 + 2"
        ),
    ),
    evidence=(
        Evidence(
            id="answer",
            obligation_id="sum",
            scope="example",
            digest=digest,
            content=content,
            producer="calculator",
            source="local calculation",
            provenance_group="calculator",
        ),
    ),
)
action = ActionCandidate(
    id="check-sum",
    obligation_id="sum",
    scope="example",
    kind="verify",
    handler_id="check",
    target_digest=digest,
    resources=Resources(actions=1, verifications=1),
)


def check(action: ActionCandidate, attempt_id: str, state: State) -> Result:
    answer = next(e for e in state.evidence if e.digest == action.target_digest)
    passed = int(answer.content or "") == 2 + 2
    return Result(
        id=f"{attempt_id}-result",
        attempt_id=attempt_id,
        action_id=action.id,
        obligation_id=action.obligation_id,
        scope=action.scope,
        target_digest=action.target_digest,
        actual_resources=Resources(actions=1, verifications=1),
        checks=(
            CheckResult(
                id=f"{attempt_id}-check",
                obligation_id="sum",
                scope="example",
                target_digest=digest,
                verifier_id="arithmetic-check",
                status="PASS" if passed else "FAIL",
                reason="Compared the parsed answer with actual arithmetic",
            ),
        ),
    )


run = run_host_loop(
    state,
    (action,),
    Budget(limits=Resources(actions=1, verifications=1)),
    Policy(trusted_verifiers=("arithmetic-check",), executable_handlers=("check",)),
    {"check": check},
)
print(run.decision.stop_reason)
