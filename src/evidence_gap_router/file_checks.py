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
from .models import (
    ActionCandidate,
    Budget,
    CheckerPermission,
    DependencyRequirement,
    Evidence,
    HandlerRegistration,
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
        "schema_version": "2",
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
    state = State(obligations=(dictionary_obligation, data_obligation))
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
                    CheckerPermission(checker_id="dictionary-checker"),
                    CheckerPermission(checker_id="orders-checker"),
                ),
            ),
        ),
    )

    def acquire(view: CallbackView, read: Callable[[], bytes], is_dictionary: bool) -> Result:
        try:
            raw = read()
            value = (
                parse_rules(raw).model_dump(mode="json") if is_dictionary else parse_dataset(raw)
            )
        except DataInputError as exc:
            return view.result(
                status="failed",
                reason=f"input_error: {exc}",
                actual_resources=Resources(actions=1, verifications=0),
            )
        evidence = Evidence(
            id="dictionary" if is_dictionary else "dataset",
            obligation_id=view.obligation.id,
            scope=view.obligation.scope,
            digest=hashlib.sha256(raw).hexdigest(),
            producer=view.action.handler_id,
            content=json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False),
            source=dictionary_source if is_dictionary else data_source,
            reference=dictionary_source if is_dictionary else data_source,
            provenance_group="declared-dictionary-source"
            if is_dictionary
            else "declared-dataset-source",
        )
        return view.result(
            actual_resources=Resources(actions=1, verifications=0), evidence=(evidence,)
        )

    def verify(view: CallbackView) -> Result:
        records = {item.id: item for item in view.inputs}
        if view.action.target_evidence_id == "dictionary":
            try:
                Rules.model_validate_json(records["dictionary"].content or "null")
                errors: tuple[str, ...] = ()
            except ValueError as exc:
                errors = (str(exc),)
        else:
            rules = Rules.model_validate_json(records["dictionary"].content or "null")
            dataset = json.loads(records["dataset"].content or "null")
            errors = validate_dataset(dataset, rules)
        check = view.check(
            status="FAIL" if errors else "PASS",
            reason="; ".join(errors)
            if errors
            else "Parsed material meets the declared fixed rules",
        )
        return view.result(actual_resources=Resources(actions=1, verifications=1), checks=(check,))

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
