"""Shortest packaged example wrapping an existing plain Python checker."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .jsonio import read_json, write_json
from .models import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    CompletionContract,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Invalidation,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from .router import invalidate
from .runner import CallbackView, RunReport, run, step


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
        resources=Resources(actions=1, verifications=1, tokens=0),
    )

    def check(view: CallbackView) -> Result:
        accepted = legacy_checker(view.inputs[0].content or "")
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            checks=(
                view.check(status="PASS" if accepted else "FAIL", reason="Compared with 2 + 2"),
            ),
        )

    return run(
        State(
            obligations=(obligation,),
            evidence=(evidence,),
            completion_contracts=(
                CompletionContract(
                    id="sum-contract",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    obligation_fingerprint=obligation.contract_fingerprint,
                    target=DependencyRequirement(
                        evidence_id=evidence.id, obligation_id=obligation.id, scope=obligation.scope
                    ),
                    declared_scope="not_applicable",
                    scope_reason="Fixed supplied arithmetic, no retrieval.",
                ),
            ),
        ),
        (action,),
        Budget(limits=Resources(actions=1, verifications=1, tokens=0)),
        Policy(
            trusted_verifiers=("arithmetic-check",),
            handlers=(
                HandlerRegistration(
                    handler_id="check",
                    roles=("verify",),
                    checkers=(
                        CheckerPermission(
                            checker_id="arithmetic-check",
                            completion_kinds=("content",),
                            completion_scopes=(obligation.scope,),
                        ),
                    ),
                ),
            ),
        ),
        {"check": check},
    )


def run_continuation_example(snapshot_path: str | Path | None = None) -> RunReport:
    """Acquire, check, invalidate a check, save/reload, and check again with real receipts.

    Supply a host-selected path to retain the snapshot before rechecking. Without
    a path the example uses a temporary directory. Original evidence, receipts,
    checks and measured costs remain in the final state.
    """
    obligation = Obligation(
        id="sum",
        description="Check the sum",
        scope="continuation",
        acceptance="answer equals 2 + 2",
        required_verifiers=("arithmetic-check",),
    )
    budget = Budget(limits=Resources(actions=3, verifications=2))
    policy = Policy(
        trusted_verifiers=("arithmetic-check",),
        handlers=(
            HandlerRegistration(handler_id="calculate", roles=("investigate",)),
            HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=(
                    CheckerPermission(
                        checker_id="arithmetic-check",
                        completion_kinds=("content",),
                        completion_scopes=(obligation.scope,),
                    ),
                ),
            ),
        ),
    )
    acquisition = ActionCandidate(
        id="calculate",
        obligation_id=obligation.id,
        scope=obligation.scope,
        kind="investigate",
        handler_id="calculate",
        produces_evidence_id="answer",
    )

    def calculate(view: CallbackView) -> Result:
        content = str(2 + 2)
        evidence = Evidence(
            id="answer",
            obligation_id=view.obligation.id,
            scope=view.obligation.scope,
            digest=sha256(content.encode()).hexdigest(),
            content=content,
            producer="calculate",
            source="local calculation",
            provenance_group="calculator",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0, tokens=0),
            evidence=(evidence,),
        )

    def check(view: CallbackView) -> Result:
        accepted = legacy_checker(view.inputs[0].content or "")
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0),
            checks=(
                view.check(status="PASS" if accepted else "FAIL", reason="Compared with 2 + 2"),
            ),
        )

    acquired = step(
        State(
            obligations=(obligation,),
            completion_contracts=(
                CompletionContract(
                    id="sum-contract",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    obligation_fingerprint=obligation.contract_fingerprint,
                    target=DependencyRequirement(
                        evidence_id="answer", obligation_id=obligation.id, scope=obligation.scope
                    ),
                    declared_scope="not_applicable",
                    scope_reason="Fixed arithmetic, no retrieval.",
                ),
            ),
        ),
        (acquisition,),
        budget,
        policy,
        {"calculate": calculate},
    )
    verification = ActionCandidate(
        id="check-original",
        obligation_id=obligation.id,
        scope=obligation.scope,
        kind="verify",
        handler_id="check",
        checker_id="arithmetic-check",
        target_evidence_id="answer",
        target_digest=acquired.state.evidence[0].digest,
        resources=Resources(actions=1, verifications=1, tokens=0),
    )
    completed = run(acquired.state, (verification,), budget, policy, {"check": check})
    invalidated = invalidate(
        completed.state,
        Invalidation(
            id="host-check-withdrawal",
            kind="check",
            target_id=completed.state.checks[0].id,
            obligation_id=obligation.id,
            scope=obligation.scope,
            reason="Host requests a fresh arithmetic check",
        ),
    )

    def resume(path: Path) -> RunReport:
        write_json(invalidated, path)
        restored = read_json(path, State)
        return run(
            restored,
            (verification.model_copy(update={"id": "check-after-withdrawal"}),),
            budget,
            policy,
            {"check": check},
        )

    if snapshot_path is not None:
        return resume(Path(snapshot_path))
    with TemporaryDirectory(prefix="egr-continuation-") as directory:
        return resume(Path(directory) / "state.json")
