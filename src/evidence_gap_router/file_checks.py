"""A practical host over two separately acquired local data-quality materials."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .data_quality import (
    DataInputError,
    Rules,
    parse_dataset,
    parse_rules,
    read_local_bytes,
    validate_dataset,
)
from .jsonio import exact_json, load_json
from .models import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    CompletionContract,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
    MaterialRequirement,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from .runner import CallbackView, RunReport, run


def report_json(report: RunReport, *, artificial_data: bool, case: str) -> dict[str, Any]:
    """Distinguish input failure, uncertain execution and checked nonacceptance."""
    reasons = [receipt.reason for receipt in report.receipts]
    if any(reason.startswith("input_error:") for reason in reasons):
        outcome = "input_error"
    elif report.stop_reason in {"callback_error", "factory_error", "planning_error", "start_error"}:
        outcome = "callback_failure"
    elif report.decision.stop_reason == "satisfied":
        outcome = "satisfied"
    elif any(check.status == "FAIL" for check in report.state.checks):
        outcome = "inspected_fail"
    elif report.decision.stop_reason == "budget_exhausted":
        outcome = "budget_exhausted"
    else:
        outcome = "missing_material"
    return {
        "schema_version": "3",
        "artificial_data": artificial_data,
        "case": case,
        "outcome": outcome,
        "runner_stop_reason": report.stop_reason,
        "error": report.error,
        "state": report.state.model_dump(mode="json"),
        "decision": report.decision.model_dump(mode="json"),
        "decisions": [item.model_dump(mode="json") for item in report.decisions],
        "callback_calls": list(report.callback_calls),
    }


def _data_host(
    data_read: Callable[[], bytes],
    dictionary_read: Callable[[], bytes],
    *,
    data_source: str,
    dictionary_source: str,
    artificial_data: bool,
    case: str,
    action_limit: int = 4,
    verification_limit: int = 2,
) -> dict[str, Any]:
    scope = "artificial-orders" if artificial_data else "local-orders"
    rules_scope = "artificial-rules" if artificial_data else "local-rules"
    dictionary_obligation = Obligation(
        id="dictionary-quality",
        description="Inspect the data dictionary",
        scope=rules_scope,
        acceptance="Bounded strict dictionary has exactly the documented fixed rule fields",
        required_verifiers=("dictionary-checker",),
        priority=1,
    )
    data_obligation = Obligation(
        id="data-quality",
        description="Inspect orders using the verified dictionary",
        scope=scope,
        acceptance="Nonempty orders have unique IDs, amounts above minimum and allowed currencies",
        required_verifiers=("orders-checker",),
    )
    dictionary_requirement = DependencyRequirement(
        evidence_id="dictionary", obligation_id=dictionary_obligation.id, scope=rules_scope
    )
    dataset_requirement = DependencyRequirement(
        evidence_id="dataset", obligation_id=data_obligation.id, scope=scope
    )
    state = State(
        obligations=(dictionary_obligation, data_obligation),
        completion_contracts=(
            CompletionContract(
                id="dictionary-contract",
                obligation_id=dictionary_obligation.id,
                scope=rules_scope,
                obligation_fingerprint=dictionary_obligation.contract_fingerprint,
                target=dictionary_requirement,
                declared_scope="finite_catalogue",
                catalogue_id="selected-files",
                catalogue_revision="1",
                materials=(
                    MaterialRequirement(id="dictionary-bytes", any_of=(dictionary_requirement,)),
                ),
            ),
            CompletionContract(
                id="orders-contract",
                obligation_id=data_obligation.id,
                scope=scope,
                obligation_fingerprint=data_obligation.contract_fingerprint,
                target=dataset_requirement,
                declared_scope="finite_catalogue",
                catalogue_id="selected-files",
                catalogue_revision="1",
                materials=(
                    MaterialRequirement(id="dataset-bytes", any_of=(dataset_requirement,)),
                    MaterialRequirement(id="dictionary-bytes", any_of=(dictionary_requirement,)),
                ),
            ),
        ),
    )
    budget = Budget(limits=Resources(actions=action_limit, verifications=verification_limit))
    policy = Policy(
        trusted_verifiers=("dictionary-checker", "orders-checker"),
        handlers=(
            HandlerRegistration(handler_id="read-csv", roles=("investigate",)),
            HandlerRegistration(handler_id="read-dictionary", roles=("investigate",)),
            HandlerRegistration(
                handler_id="verify-quality",
                roles=("verify",),
                checkers=(
                    CheckerPermission(
                        checker_id="dictionary-checker",
                        completion_kinds=("content",),
                        completion_scopes=(rules_scope,),
                    ),
                    CheckerPermission(
                        checker_id="orders-checker",
                        completion_kinds=("content",),
                        completion_scopes=(scope,),
                    ),
                ),
            ),
        ),
    )

    def acquire(view: CallbackView, read: Callable[[], bytes], is_dictionary: bool) -> Result:
        try:
            raw = read()
            if is_dictionary:
                parse_rules(raw)
                # Preserve validated decimal lexemes and the input byte bound;
                # inserting defaults could expand a full-sized document.
                content = raw.decode("utf-8-sig")
            else:
                content = exact_json(parse_dataset(raw), sort_keys=True)
        except DataInputError as exc:
            return view.result(
                status="failed",
                reason=f"input_error: {exc}",
                actual_resources=Resources(actions=1, verifications=0, tokens=0),
            )
        evidence = Evidence(
            id="dictionary" if is_dictionary else "dataset",
            obligation_id=view.obligation.id,
            scope=view.obligation.scope,
            digest=hashlib.sha256(raw).hexdigest(),
            producer=view.action.handler_id,
            content=content,
            source=dictionary_source if is_dictionary else data_source,
            reference=dictionary_source if is_dictionary else data_source,
            provenance_group="declared-dictionary-source"
            if is_dictionary
            else "declared-dataset-source",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0, tokens=0), evidence=(evidence,)
        )

    def verify(view: CallbackView) -> Result:
        records = {item.id: item for item in view.inputs}
        if view.action.target_evidence_id == "dictionary":
            try:
                load_json(records["dictionary"].content or "null", Rules)
                errors: tuple[str, ...] = ()
            except ValueError as exc:
                errors = (str(exc),)
        else:
            rules = load_json(records["dictionary"].content or "null", Rules)
            dataset = json.loads(records["dataset"].content or "null")
            errors = validate_dataset(dataset, rules)
        check = view.check(
            status="FAIL" if errors else "PASS",
            reason="; ".join(errors)
            if errors
            else "Parsed material meets the declared fixed rules",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=1, tokens=0), checks=(check,)
        )

    def candidates(current: State) -> tuple[ActionCandidate, ...]:
        declared = [
            ActionCandidate(
                id="read-dictionary",
                obligation_id=dictionary_obligation.id,
                scope=rules_scope,
                kind="investigate",
                handler_id="read-dictionary",
                produces_evidence_id="dictionary",
                source=dictionary_source,
                provenance_group="declared-dictionary-source",
            ),
            ActionCandidate(
                id="read-dataset",
                obligation_id=data_obligation.id,
                scope=scope,
                kind="investigate",
                handler_id="read-csv",
                produces_evidence_id="dataset",
                source=data_source,
                provenance_group="declared-dataset-source",
            ),
        ]
        records = {item.id: item for item in current.evidence}
        for target, obligation, checker in (
            ("dictionary", dictionary_obligation, "dictionary-checker"),
            ("dataset", data_obligation, "orders-checker"),
        ):
            if target not in records:
                continue
            dependencies = (
                ()
                if target == "dictionary"
                else (
                    DependencyRequirement(
                        evidence_id="dictionary",
                        obligation_id=dictionary_obligation.id,
                        scope=rules_scope,
                        requirement="verified",
                        contract_fingerprint=dictionary_obligation.contract_fingerprint,
                    ),
                )
            )
            declared.append(
                ActionCandidate(
                    id=f"verify-{target}",
                    obligation_id=obligation.id,
                    scope=obligation.scope,
                    kind="verify",
                    handler_id="verify-quality",
                    target_evidence_id=target,
                    target_digest=records[target].digest,
                    checker_id=checker,
                    resources=Resources(actions=1, verifications=1, tokens=0),
                    dependencies=dependencies,
                )
            )
        return tuple(declared)

    report = run(
        state,
        candidates,
        budget,
        policy,
        {
            "read-csv": lambda view: acquire(view, data_read, False),
            "read-dictionary": lambda view: acquire(view, dictionary_read, True),
            "verify-quality": verify,
        },
    )
    return report_json(report, artificial_data=artificial_data, case=case)


def check_data(data_path: Path, dictionary_path: Path) -> dict[str, Any]:
    """Read explicitly selected local files without modifying them or fetching URLs."""
    return _data_host(
        lambda: read_local_bytes(data_path),
        lambda: read_local_bytes(dictionary_path),
        data_source=str(data_path),
        dictionary_source=str(dictionary_path),
        artificial_data=False,
        case="local",
    )
