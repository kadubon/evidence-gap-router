"""Actual offline callbacks over artificial CSV and JSON data.

``run_host_loop`` is an example host, not an execution service in the router.
It deliberately marks uncertain callback execution and cost as unknown.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from pathlib import Path
from typing import Any

from .models import (
    ActionCandidate,
    Budget,
    CheckResult,
    Decision,
    Evidence,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from .router import observe, plan, start

Handler = Callable[[ActionCandidate, str, State], Result]
CandidateFactory = Callable[[State], tuple[ActionCandidate, ...]]


@dataclass(frozen=True)
class HostRun:
    """State and full recommendations returned by the explicit sample host."""

    state: State
    decision: Decision
    decisions: tuple[Decision, ...]
    callback_calls: tuple[str, ...]


def run_host_loop(
    state: State,
    candidates: tuple[ActionCandidate, ...] | CandidateFactory,
    budget: Budget,
    policy: Policy,
    handlers: Mapping[str, Handler],
) -> HostRun:
    """Run finite host-declared callbacks; never automatically retry a callback.

    Callbacks receive the candidate, issued attempt ID and current immutable
    state, and must return ``Result``. Exceptions, malformed values and rejected
    receipts record an uncertain attempt, one actual invocation, unknown other
    cost, and unknown side effects. External access, timeouts and measurement
    remain the host's responsibility. Candidate factories must declare a finite
    action set with stable IDs.
    """
    policy = policy.model_copy(
        update={
            "executable_handlers": tuple(
                handler_id for handler_id in policy.executable_handlers if handler_id in handlers
            )
        }
    )
    decisions: list[Decision] = []
    calls: list[str] = []
    executed: set[str] = set()
    while True:
        current_candidates = candidates(state) if callable(candidates) else candidates
        decision = plan(state, current_candidates, budget, policy)
        decisions.append(decision)
        action = decision.action
        if action is None:
            return HostRun(state, decision, tuple(decisions), tuple(calls))
        if action.id in executed:
            raise ValueError("sample host refuses to automatically retry an action")
        executed.add(action.id)
        attempt_id = f"host-attempt-{len(state.attempts) + 1}"
        state = start(state, action, attempt_id, budget, policy)
        calls.append(action.handler_id)
        try:
            result = handlers[action.handler_id](action, attempt_id, state)
            if not isinstance(result, Result):
                raise TypeError("callback must return a Result")
            if (
                result.attempt_id,
                result.action_id,
                result.obligation_id,
                result.scope,
                result.target_digest,
            ) != (
                attempt_id,
                action.id,
                action.obligation_id,
                action.scope,
                action.target_digest,
            ):
                raise ValueError("callback receipt does not match the current invocation")
            state = observe(state, result)
        except Exception as exc:
            state = observe(
                state,
                Result(
                    id=f"{attempt_id}-unknown",
                    attempt_id=attempt_id,
                    action_id=action.id,
                    obligation_id=action.obligation_id,
                    scope=action.scope,
                    target_digest=action.target_digest,
                    status="unknown",
                    reason=f"Callback outcome or receipt uncertain: {type(exc).__name__}: {exc}",
                    actual_resources=Resources(actions=1, verifications=None, tokens=None),
                    side_effects="unknown",
                ),
            )


def _content(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _evidence(evidence_id: str, producer: str, source: str, group: str, value: Any) -> Evidence:
    content = _content(value)
    return Evidence(
        id=evidence_id,
        obligation_id="data-quality",
        scope="artificial-orders",
        content=content,
        digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        producer=producer,
        source=source,
        provenance_group=group,
    )


def _dictionary_errors(dictionary: Any) -> list[str]:
    if not isinstance(dictionary, dict):
        return ["dictionary must be a JSON object"]
    errors = []
    columns = dictionary.get("required_columns")
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(item, str) or not item for item in columns)
    ):
        errors.append("required_columns must contain column names")
    key = dictionary.get("primary_key")
    if not isinstance(key, str) or not isinstance(columns, list) or key not in columns:
        errors.append("primary_key must occur in required_columns")
    currencies = dictionary.get("allowed_currencies")
    if (
        not isinstance(currencies, list)
        or not currencies
        or any(not isinstance(item, str) or not item for item in currencies)
    ):
        errors.append("allowed_currencies must contain currency names")
    try:
        minimum = Decimal(str(dictionary["minimum_amount"]))
        if not minimum.is_finite():
            errors.append("minimum_amount must be finite")
    except (KeyError, InvalidOperation):
        errors.append("minimum_amount must be numeric")
    return errors


def _dataset_errors(dataset: dict[str, Any], dictionary: dict[str, Any]) -> list[str]:
    errors = []
    columns = dataset["columns"]
    missing = sorted(set(dictionary["required_columns"]) - set(columns))
    if missing:
        errors.append(f"missing columns: {', '.join(missing)}")
        return errors
    seen: set[str] = set()
    for index, row in enumerate(dataset["rows"], start=2):
        key = row.get(dictionary["primary_key"])
        if not key:
            errors.append(f"line {index}: primary key is empty")
        elif key in seen:
            errors.append(f"line {index}: duplicate primary key {key}")
        else:
            seen.add(key)
        try:
            amount = Decimal(row["amount"])
            if not amount.is_finite() or amount < Decimal(str(dictionary["minimum_amount"])):
                errors.append(f"line {index}: amount is below minimum or non-finite")
        except (KeyError, TypeError, InvalidOperation):
            errors.append(f"line {index}: amount is not numeric")
        if row.get("currency") not in dictionary["allowed_currencies"]:
            errors.append(f"line {index}: currency is not in dictionary")
    return errors


def run_demo(
    case: str = "valid",
    *,
    data_path: Path | None = None,
    dictionary_path: Path | None = None,
) -> dict[str, Any]:
    """Acquire two files separately, then validate their issued target digests.

    ``valid`` closes the declaration; ``invalid`` preserves computed failures;
    ``budget`` stops after acquisition without verification. Optional paths are
    host-authorized local inputs. Bundled fixtures are artificial examples.
    """
    if case not in {"valid", "invalid", "budget"}:
        raise ValueError("case must be valid, invalid or budget")
    fixture_name = "orders_invalid.csv" if case == "invalid" else "orders_valid.csv"
    state = State(
        obligations=(
            Obligation(
                id="data-quality",
                description="Check artificial orders against the separately acquired dictionary",
                scope="artificial-orders",
                acceptance=(
                    "Usable dictionary, unique nonempty order IDs, finite amounts above minimum, "
                    "allowed currencies"
                ),
                min_evidence=2,
                min_provenance_groups=2,
                required_verifiers=("quality-validator",),
            ),
        )
    )
    budget = Budget(limits=Resources(actions=2 if case == "budget" else 4, verifications=2))
    policy = Policy(
        trusted_verifiers=("quality-validator",),
        executable_handlers=("read-csv", "read-dictionary", "verify-quality"),
    )

    def receipt(
        action: ActionCandidate,
        attempt_id: str,
        *,
        evidence: tuple[Evidence, ...] = (),
        checks: tuple[CheckResult, ...] = (),
    ) -> Result:
        return Result(
            id=f"{attempt_id}-result",
            attempt_id=attempt_id,
            action_id=action.id,
            obligation_id=action.obligation_id,
            scope=action.scope,
            target_digest=action.target_digest,
            actual_resources=Resources(
                actions=1, verifications=1 if action.kind == "verify" else 0
            ),
            evidence=evidence,
            checks=checks,
        )

    def acquire_csv(action: ActionCandidate, attempt_id: str, current: State) -> Result:
        text = (
            data_path.read_text(encoding="utf-8")
            if data_path is not None
            else files("evidence_gap_router").joinpath("data", fixture_name).read_text("utf-8")
        )
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if reader.fieldnames is None or any(None in row for row in rows):
            raise ValueError("CSV has no header or contains extra unnamed fields")
        evidence = _evidence(
            "dataset",
            "csv-reader",
            str(data_path) if data_path is not None else fixture_name,
            "declared-dataset-source",
            {"columns": reader.fieldnames, "rows": rows},
        )
        return receipt(action, attempt_id, evidence=(evidence,))

    def acquire_dictionary(action: ActionCandidate, attempt_id: str, current: State) -> Result:
        text = (
            dictionary_path.read_text(encoding="utf-8")
            if dictionary_path is not None
            else files("evidence_gap_router")
            .joinpath("data", "data_dictionary.json")
            .read_text("utf-8")
        )
        evidence = _evidence(
            "dictionary",
            "dictionary-reader",
            str(dictionary_path) if dictionary_path is not None else "data_dictionary.json",
            "declared-dictionary-source",
            json.loads(text),
        )
        return receipt(action, attempt_id, evidence=(evidence,))

    def verify_quality(action: ActionCandidate, attempt_id: str, current: State) -> Result:
        records = {item.id: item for item in current.evidence}
        dataset = json.loads(records["dataset"].content or "null")
        dictionary = json.loads(records["dictionary"].content or "null")
        dictionary_errors = _dictionary_errors(dictionary)
        dataset_errors = (
            ["dataset cannot be accepted against an unusable dictionary"]
            if dictionary_errors
            else _dataset_errors(dataset, dictionary)
        )
        errors = (
            dataset_errors
            if action.target_digest == records["dataset"].digest
            else dictionary_errors
        )
        check = CheckResult(
            id=f"{attempt_id}-check",
            obligation_id="data-quality",
            scope="artificial-orders",
            target_digest=action.target_digest or "",
            verifier_id="quality-validator",
            status="FAIL" if errors else "PASS",
            reason="; ".join(errors)
            if errors
            else "Actual parsed content meets the declared validation rules",
        )
        return receipt(action, attempt_id, checks=(check,))

    def candidates(current: State) -> tuple[ActionCandidate, ...]:
        declared = [
            ActionCandidate(
                id="01-read-dataset",
                obligation_id="data-quality",
                scope="artificial-orders",
                kind="investigate",
                handler_id="read-csv",
                resources=Resources(actions=1, verifications=0),
                source=fixture_name,
                provenance_group="declared-dataset-source",
            ),
            ActionCandidate(
                id="02-read-dictionary",
                obligation_id="data-quality",
                scope="artificial-orders",
                kind="diversify",
                handler_id="read-dictionary",
                resources=Resources(actions=1, verifications=0),
                source="data_dictionary.json",
                provenance_group="declared-dictionary-source",
            ),
        ]
        records = {item.id: item for item in current.evidence}
        for index, evidence_id in enumerate(("dataset", "dictionary"), start=3):
            if evidence_id in records:
                declared.append(
                    ActionCandidate(
                        id=f"0{index}-verify-{evidence_id}",
                        obligation_id="data-quality",
                        scope="artificial-orders",
                        kind="verify",
                        handler_id="verify-quality",
                        resources=Resources(actions=1, verifications=1),
                        target_digest=records[evidence_id].digest,
                        requires_evidence_ids=("dataset", "dictionary"),
                    )
                )
        return tuple(declared)

    run = run_host_loop(
        state,
        candidates,
        budget,
        policy,
        {
            "read-csv": acquire_csv,
            "read-dictionary": acquire_dictionary,
            "verify-quality": verify_quality,
        },
    )
    return {
        "artificial_data": data_path is None and dictionary_path is None,
        "case": case,
        "state": run.state.model_dump(mode="json"),
        "decision": run.decision.model_dump(mode="json"),
        "decisions": [item.model_dump(mode="json") for item in run.decisions],
        "callback_calls": list(run.callback_calls),
    }
