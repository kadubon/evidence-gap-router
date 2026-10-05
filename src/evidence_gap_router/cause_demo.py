"""Artificial three-material incident investigation with limited callback views."""

from __future__ import annotations

import hashlib
from importlib.resources import files
from typing import Annotated, Any, Literal

from pydantic import Field

from .file_checks import report_json
from .jsonio import load_json
from .models import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    Contradiction,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Record,
    Resources,
    Result,
    State,
)
from .runner import CallbackView, run


class Reading(Record):
    sensor_id: Annotated[str, Field(min_length=1)]
    reading: int | float
    declared_source: str | None
    provenance_group: str | None


class Specification(Record):
    normal_limit: Annotated[int | float, Field(ge=0)]
    exception_limit: Annotated[int | float, Field(ge=0)]
    allow_exceptions: bool


class Exceptions(Record):
    active_sensor_ids: tuple[Annotated[str, Field(min_length=1)], ...]
    complete: bool


def run_cause_demo(case: str = "resolved") -> dict[str, Any]:
    """Read measurements, limits and exception registers instead of voting.

    The reading alone exceeds the normal limit. The exception register is needed
    to determine whether the observed reading is within the permitted limit.
    Cases preserve actual FAIL/UNKNOWN, contradictions, unknown origins and
    budget stops. These artificial sources make no independence claim.
    """
    if case not in {"resolved", "invalid", "conflict", "unknown", "provenance", "budget"}:
        raise ValueError("unsupported cause-demo case")
    names = {
        "reading": "reading_invalid.json"
        if case == "invalid"
        else ("reading_unknown_origin.json" if case == "provenance" else "reading.json"),
        "specification": "specification_conflict.json"
        if case == "conflict"
        else "specification.json",
        "exceptions": "exceptions_unknown.json" if case == "unknown" else "exceptions.json",
    }
    obligation = Obligation(
        id="incident",
        scope="artificial-incident",
        description="Explain the above-normal reading",
        acceptance="Complete compatible materials explain a reading within its permitted limit",
        min_evidence=3,
        min_provenance_groups=3,
        required_verifiers=("incident-checker",),
    )
    state = State(obligations=(obligation,))
    budget = Budget(limits=Resources(actions=6, verifications=1 if case == "budget" else 3))
    policy = Policy(
        trusted_verifiers=("incident-checker",),
        max_pending_verifications=3,
        handlers=(
            *(
                HandlerRegistration(handler_id=f"read-{name}", roles=("investigate", "diversify"))
                for name in names
            ),
            HandlerRegistration(
                handler_id="inspect-incident",
                roles=("verify",),
                checkers=(CheckerPermission(checker_id="incident-checker"),),
            ),
        ),
    )
    disclosed: list[dict[str, Any]] = []

    def acquire(view: CallbackView) -> Result:
        target = view.action.produces_evidence_id or ""
        disclosed.append(
            {"handler": view.action.handler_id, "input_ids": [e.id for e in view.inputs]}
        )
        raw = files("evidence_gap_router").joinpath("data", "cause", names[target]).read_bytes()
        material: Reading | Specification | Exceptions
        if target == "reading":
            material = load_json(raw, Reading)
        elif target == "specification":
            material = load_json(raw, Specification)
        else:
            material = load_json(raw, Exceptions)
        if isinstance(material, Reading):
            source = material.declared_source
            group = material.provenance_group
        else:
            source, group = f"artificial-{target}", f"declared-{target}-source"
        evidence = Evidence(
            id=target,
            obligation_id=obligation.id,
            scope=obligation.scope,
            digest=hashlib.sha256(raw).hexdigest(),
            producer=view.action.handler_id,
            content=material.model_dump_json(),
            source=source,
            provenance_group=group,
            reference=f"bundled artificial data/cause/{names[target]}",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0), evidence=(evidence,)
        )

    def inspect(view: CallbackView) -> Result:
        disclosed.append(
            {"handler": view.action.handler_id, "input_ids": [e.id for e in view.inputs]}
        )
        records = {e.id: e for e in view.inputs}
        target = view.action.target_evidence_id
        status: Literal["PASS", "FAIL", "UNKNOWN"]
        contradictions: tuple[Contradiction, ...] = ()
        if target == "specification":
            specification = Specification.model_validate_json(
                records["specification"].content or "null"
            )
            passed = specification.exception_limit >= specification.normal_limit
            status = "PASS" if passed else "FAIL"
            reason = (
                "Exception limit is at least the normal limit"
                if passed
                else "Exception limit contradicts normal limit"
            )
        elif target == "exceptions":
            specification = Specification.model_validate_json(
                records["specification"].content or "null"
            )
            exceptions = Exceptions.model_validate_json(records["exceptions"].content or "null")
            if not exceptions.complete:
                status, reason = "UNKNOWN", "The exception register declares incomplete coverage"
            elif exceptions.active_sensor_ids and not specification.allow_exceptions:
                status, reason = (
                    "UNKNOWN",
                    "Specification prohibits exceptions but register grants an exception",
                )
                contradictions = (
                    Contradiction(
                        id="exception-conflict",
                        obligation_id=obligation.id,
                        scope=obligation.scope,
                        evidence_ids=("specification", "exceptions"),
                        reason=reason,
                    ),
                )
            else:
                status, reason = (
                    "PASS",
                    "Complete exception register is compatible with specification",
                )
        else:
            reading = Reading.model_validate_json(records["reading"].content or "null")
            specification = Specification.model_validate_json(
                records["specification"].content or "null"
            )
            exceptions = Exceptions.model_validate_json(records["exceptions"].content or "null")
            has_exception = (
                specification.allow_exceptions and reading.sensor_id in exceptions.active_sensor_ids
            )
            limit = specification.exception_limit if has_exception else specification.normal_limit
            passed = reading.reading <= limit
            status = "PASS" if passed else "FAIL"
            reason = (
                f"Reading {reading.reading} compared with applicable limit {limit}; "
                f"declared exception={has_exception}"
            )
        return view.result(
            actual_resources=Resources(actions=1, verifications=1),
            checks=(view.check(status=status, reason=reason),),
            contradictions=contradictions,
        )

    def dependency(
        name: str, requirement: Literal["exists", "active", "verified"] = "verified"
    ) -> DependencyRequirement:
        return DependencyRequirement(
            evidence_id=name,
            obligation_id=obligation.id,
            scope=obligation.scope,
            requirement=requirement,
            contract_fingerprint=obligation.contract_fingerprint,
        )

    def candidates(current: State) -> tuple[ActionCandidate, ...]:
        declared = [
            ActionCandidate(
                id=f"0{index}-read-{name}",
                obligation_id=obligation.id,
                scope=obligation.scope,
                kind="investigate" if name == "reading" else "diversify",
                handler_id=f"read-{name}",
                produces_evidence_id=name,
                source=f"artificial-{name}",
                provenance_group=f"declared-{name}-source",
            )
            for index, name in enumerate(names, start=1)
        ]
        records = {e.id: e for e in current.evidence}
        for name in names:
            if name not in records:
                continue
            dependencies = (
                ()
                if name == "specification"
                else (
                    (dependency("specification"),)
                    if name == "exceptions"
                    else (dependency("specification"), dependency("exceptions"))
                )
            )
            declared.append(
                ActionCandidate(
                    id=f"verify-{name}",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    kind="verify",
                    handler_id="inspect-incident",
                    checker_id="incident-checker",
                    target_evidence_id=name,
                    target_digest=records[name].digest,
                    resources=Resources(actions=1, verifications=1),
                    dependencies=dependencies,
                )
            )
        return tuple(declared)

    report = run(
        state,
        candidates,
        budget,
        policy,
        {**{f"read-{name}": acquire for name in names}, "inspect-incident": inspect},
    )
    output = report_json(report, artificial_data=True, case=case)
    output["example"] = "cause"
    output["disclosures"] = disclosed
    return output
