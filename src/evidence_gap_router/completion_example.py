"""Three bounded model-free examples using actual host-selected UTF-8 local files."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .completion import declare_completion
from .data_quality import read_local_bytes
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
    MaterialRequirement,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from .router import invalidate, plan
from .runner import CallbackView, RunReport, run


def _evidence(path: Path, identifier: str, owner: str, scope: str) -> Evidence:
    raw = read_local_bytes(path)
    int(raw.decode("utf-8"))
    return Evidence(
        id=identifier,
        obligation_id=owner,
        scope=scope,
        content=raw.decode("utf-8"),
        digest=sha256(raw).hexdigest(),
        producer="local-file",
        source=str(path),
        reference=str(path),
        provenance_group=identifier,
    )


def _prepare(directory: Path, *, pooled: bool) -> tuple[State, Policy, Budget]:
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in (("M.txt", "2"), ("N.txt", "3"), ("answer.txt", "5")):
        path = directory / name
        if not path.exists():
            path.write_text(text, encoding="utf-8")
    goal = Obligation(
        id="sum",
        description="Inspect supplied sum",
        scope="local-sum",
        acceptance="Answer equals the integer contents of M and N",
        priority=10,
    )
    materials = Obligation(
        id="files",
        description="Selected input files",
        scope="local-files",
        acceptance="Read exact UTF-8 integer bytes",
        required=False,
    )
    requirements = tuple(
        DependencyRequirement(evidence_id=i, obligation_id=materials.id, scope=materials.scope)
        for i in ("M", "N")
    )
    contract = CompletionContract(
        id="sum-scope-1",
        obligation_id=goal.id,
        scope=goal.scope,
        obligation_fingerprint=goal.contract_fingerprint,
        target=DependencyRequirement(evidence_id="answer", obligation_id=goal.id, scope=goal.scope),
        declared_scope="finite_catalogue",
        catalogue_id="selected-M-and-N",
        catalogue_revision="1",
        scope_reason="Only the supplied M/N files belong to this finite task.",
        materials=tuple(MaterialRequirement(id=r.evidence_id, any_of=(r,)) for r in requirements),
    )
    evidence: tuple[Evidence, ...] = (
        _evidence(directory / "answer.txt", "answer", goal.id, goal.scope),
        _evidence(directory / "M.txt", "M", materials.id, materials.scope),
    )
    if pooled:
        evidence += (_evidence(directory / "N.txt", "N", materials.id, materials.scope),)
    state = State(
        obligations=(goal, materials), evidence=evidence, completion_contracts=(contract,)
    )
    policy = Policy(
        trusted_verifiers=("integer-sum",),
        handlers=(
            HandlerRegistration(handler_id="read", roles=("investigate",)),
            HandlerRegistration(
                handler_id="check",
                roles=("verify",),
                checkers=(
                    CheckerPermission(
                        checker_id="integer-sum",
                        completion_kinds=("content",),
                        completion_scopes=(goal.scope,),
                        method="Direct integer addition",
                    ),
                ),
            ),
        ),
    )
    return state, policy, Budget(limits=Resources(actions=8, verifications=4, tokens=0))


def _check(
    state: State, identifier: str, inputs: tuple[str, ...], *, advisory: bool = False
) -> ActionCandidate:
    target = next(e for e in state.evidence if e.id == "answer")
    return ActionCandidate(
        id=identifier,
        obligation_id="sum",
        scope="local-sum",
        kind="verify",
        handler_id="check",
        target_evidence_id=target.id,
        target_digest=target.digest,
        checker_id="integer-sum",
        advisory=advisory,
        resources=Resources(actions=1, verifications=1, tokens=0),
        dependencies=tuple(
            DependencyRequirement(evidence_id=i, obligation_id="files", scope="local-files")
            for i in inputs
        ),
    )


def _checker(view: CallbackView) -> Result:
    values = {e.id: int(e.content or "") for e in view.inputs}
    if view.action.advisory:
        passed, reason = values["M"] == 2, "M alone matches 2; N and the full sum remain unchecked."
    else:
        other = next(i for i in values if i not in {"answer", "M"})
        passed, reason = (
            values["answer"] == values["M"] + values[other],
            "Compared the answer with both supplied integer files.",
        )
    return view.result(
        actual_resources=Resources(actions=1, verifications=1, tokens=0),
        checks=(view.check(status="PASS" if passed else "FAIL", reason=reason),),
    )


def _acquire(
    state: State, policy: Policy, budget: Budget, directory: Path, identifier: str
) -> RunReport:
    action = ActionCandidate(
        id="read-" + identifier,
        obligation_id="files",
        scope="local-files",
        kind="investigate",
        handler_id="read",
        produces_evidence_id=identifier,
        resources=Resources(actions=1, verifications=0, tokens=0),
    )

    def read(view: CallbackView) -> Result:
        return view.result(
            actual_resources=Resources(actions=1, verifications=0, tokens=0),
            evidence=(_evidence(directory / "N.txt", identifier, "files", "local-files"),),
        )

    return run(state, (action,), budget, policy, {"read": read})


def run_partial_example(directory: str | Path) -> dict[str, object]:
    """Advisory M-only PASS → acquire N → actual full-input check → finite completion."""
    path = Path(directory)
    state, policy, budget = _prepare(path, pooled=False)
    advisory = policy.model_copy(
        update={
            "handlers": (
                policy.handlers[0],
                HandlerRegistration(
                    handler_id="check",
                    roles=("verify",),
                    checkers=(CheckerPermission(checker_id="integer-sum"),),
                ),
            )
        }
    )
    partial = run(
        state,
        (_check(state, "partial", ("M",), advisory=True),),
        budget,
        advisory,
        {"check": _checker},
    )
    acquired = _acquire(partial.state, policy, budget, path, "N")
    final = run(
        acquired.state,
        (_check(acquired.state, "full", ("M", "N")),),
        budget,
        policy,
        {"check": _checker},
    )
    return {
        "partial": partial.decision.model_dump(mode="json"),
        "after_acquisition": acquired.decision.model_dump(mode="json"),
        "state": final.state.model_dump(mode="json"),
        "decision": final.decision.model_dump(mode="json"),
    }


def run_pooled_example(directory: str | Path) -> RunReport:
    """One fixed callback receives the whole finite input and completes legitimately."""
    state, policy, budget = _prepare(Path(directory), pooled=True)
    return run(state, (_check(state, "pooled", ("M", "N")),), budget, policy, {"check": _checker})


def run_material_continuation(directory: str | Path) -> RunReport:
    """Save/reload an invalidated used input; reuse M and retain old PASS and costs."""
    path = Path(directory)
    state, policy, budget = _prepare(path, pooled=True)
    complete = run(
        state, (_check(state, "original", ("M", "N")),), budget, policy, {"check": _checker}
    )
    state = invalidate(
        complete.state,
        Invalidation(
            id="host-N-withdrawal",
            kind="evidence",
            target_id="N",
            obligation_id="files",
            scope="local-files",
            reason="Host requests fresh N bytes.",
        ),
    )
    write_json(state, path / "継続 state.json")
    state = read_json(path / "継続 state.json", State)
    assert plan(state, (), budget, policy).stop_reason != "satisfied"
    original = state.completion_contracts[0]
    revised = CompletionContract(
        **{
            **original.model_dump(),
            "id": "sum-scope-2",
            "revision": "2",
            "catalogue_revision": "2",
            "change_reason": "Replace the withdrawn N ID explicitly.",
            "materials": (
                original.materials[0],
                MaterialRequirement(
                    id="N",
                    any_of=(
                        DependencyRequirement(
                            evidence_id="N-v2", obligation_id="files", scope="local-files"
                        ),
                    ),
                ),
            ),
        }
    )
    state = declare_completion(state, revised)
    acquired = _acquire(state, policy, budget, path, "N-v2")
    return run(
        acquired.state,
        (_check(acquired.state, "recheck", ("M", "N-v2")),),
        budget,
        policy,
        {"check": _checker},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=("partial", "pooled", "continuation"))
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()

    def execute(path: Path) -> None:
        value = (
            run_partial_example(path)
            if args.case == "partial"
            else (
                run_pooled_example(path)
                if args.case == "pooled"
                else run_material_continuation(path)
            ).model_dump(mode="json")
        )
        print(json.dumps(value, ensure_ascii=True))

    if args.directory is not None:
        execute(args.directory)
    else:
        with TemporaryDirectory(prefix="egr-completion-") as temporary:
            execute(Path(temporary) / "入力 ファイル")


if __name__ == "__main__":
    main()
