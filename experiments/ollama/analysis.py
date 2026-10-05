"""Independent parent-paired reanalysis of retained trials, never a live callback."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .oracle import evaluate
from .tasks import confirmation_tasks, development_tasks


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        (
            json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
    )


def _interval(values: list[int], seed: int, repetitions: int) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means = sorted(
        sum(rng.choices(values, k=len(values))) / len(values) for _ in range(repetitions)
    )
    return [means[int(repetitions * 0.025)], means[min(repetitions - 1, int(repetitions * 0.975))]]


def _amount(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _new_cost() -> dict[str, Any]:
    return {
        "attempted_calls": 0,
        "known_usage_calls": 0,
        "unknown_usage_calls": 0,
        "observed_generated_tokens": 0,
        "observed_total_tokens": 0,
        "reserved_unknown_total_tokens": 0,
        "status_counts": {},
        **{
            name: 0.0
            for name in (
                "observed_client_wall_seconds",
                "observed_load_seconds",
                "observed_prefill_seconds",
                "observed_generation_seconds",
            )
        },
        "known_duration_calls": {
            name: 0
            for name in (
                "client_wall_seconds",
                "load_seconds",
                "prefill_seconds",
                "generation_seconds",
            )
        },
    }


def _finish_cost(cost: dict[str, Any]) -> dict[str, Any]:
    return {
        **cost,
        "generated_tokens": cost["observed_generated_tokens"]
        if not cost["unknown_usage_calls"]
        else None,
        "total_tokens": cost["observed_total_tokens"] if not cost["unknown_usage_calls"] else None,
        **{
            name: cost["observed_" + name]
            if cost["known_duration_calls"][name] == cost["attempted_calls"]
            else None
            for name in cost["known_duration_calls"]
        },
    }


def analyze(
    directory: Path, output: Path, protocol: dict[str, Any], *, frozen: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Score every recorded terminal key; unstarted/fault/pending are separate outcomes."""
    edition = "024" if protocol["package_version"] == "0.2.4" else "023"
    tasks = {
        task.task_id: (task, gold)
        for task, gold in (*development_tasks(edition), *confirmation_tasks(edition))
    }
    rows: list[dict[str, Any]] = []
    failures = []
    records = {}
    for path in sorted((directory / "trials").glob("*/*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("kind") == "checkpoint":
            continue
        if record["key"] in records:
            raise ValueError("duplicate terminal trial key")
        records[record["key"]] = record
    planned = [] if frozen is None else frozen["planned_trial_keys"]
    if len({item["key"] for item in planned}) != len(planned):
        raise ValueError("duplicate frozen trial key")
    all_planned = [(item, "confirmation") for item in planned]
    auxiliary_sources = (
        set() if frozen is None else set(frozen.get("planned_auxiliary_source_keys", []))
    )
    all_planned.extend(
        ({**item, "key": item["key"] + "-aux"}, "auxiliary")
        for item in planned
        if item["key"] in auxiliary_sources
    )
    all_planned.extend(
        ({k: v for k, v in item.items() if k != "phase"}, item["phase"])
        for item in ([] if frozen is None else frozen.get("planned_sensitivity_keys", []))
    )
    for item, phase in all_planned:
        saved = records.get(item["key"])
        if saved is not None and (
            saved["phase"] != phase or any(saved.get(k) != v for k, v in item.items())
        ):
            raise ValueError("terminal trial differs from frozen identity")
        if saved is None:
            records[item["key"]] = {
                **item,
                "phase": phase,
                "trial": {},
                "execution": "unexecuted_no_terminal_record",
            }
    for record in sorted(records.values(), key=lambda r: r["key"]):
        result = record["trial"]
        task, gold = tasks[record["task_id"]]
        scored = (
            evaluate(task, gold, result)
            if record["execution"] == "completed"
            else {
                "oracle_assessed": False,
                "answer_correct": False,
                "answer_grounded_correct": None,
                "verified_supported_completion": None,
                "evidence_supported_completion": False,
                "grounded_abstention": False,
                "errors": [record["execution"]],
            }
        )
        row = {
            "phase": record["phase"],
            "key": record["key"],
            "task_id": task.task_id,
            "family": task.family,
            "model": record["model"],
            "arm": record["arm"],
            "seed": record["seed"],
            "execution": record["execution"],
            "gold_decision": gold.decision,
            "trial_wall_seconds": record.get("trial_wall_seconds"),
            "current_controller_segment_wall_seconds": record.get(
                "current_controller_segment_wall_seconds"
            ),
            "runner_stop": result.get("runner_stop"),
            "domain_stop": result.get("domain_stop"),
            "pending": result.get("pending", False),
            "fault": result.get("fault"),
            "system_claimed_complete": bool(result.get("system_claimed_complete")),
            **scored,
        }
        calls = result.get("calls", [])
        row.update(
            answer_grounded_correct=scored.get(
                "answer_grounded_correct", scored["evidence_supported_completion"]
            ),
            verified_supported_completion=scored.get(
                "verified_supported_completion", scored["evidence_supported_completion"]
            ),
            executed=bool(calls),
            unexecuted=record["execution"] != "completed",
            transport_completed=bool(calls) and all(c.get("done") is True for c in calls),
            known_usage=bool(calls) and all(c.get("unknown_consumption") is False for c in calls),
            request_pending=any(c.get("pending") for c in calls),
            output_schema_valid=bool(calls)
            and all(isinstance(c.get("parsed"), dict) for c in calls),
            length_or_format_fault=any(
                c.get("status") in ("length", "final_json_error", "schema_error", "empty_final")
                for c in calls
            ),
            reviewer_status=(result.get("reviews") or [{}])[-1].get("status"),
            router_satisfied=result.get("router_satisfied"),
        )
        row["reviewer_false_pass"] = (
            row["reviewer_status"] == "PASS" and row["answer_grounded_correct"] is False
        )
        row["erroneous_stop"] = (
            row["oracle_assessed"]
            and not row["verified_supported_completion"]
            and row["gold_decision"] != "unknown"
        )
        row["known_attempt_termination"] = (
            row["execution"] == "completed"
            and not row["pending"]
            and row["fault"]
            not in ("unknown_consumption", "pending_or_unknown_dispatch", "callback_exception")
        )
        row["false_acceptance"] = row["system_claimed_complete"] and not bool(
            row["evidence_supported_completion"]
        )
        rows.append(row)
        if not row["evidence_supported_completion"]:
            failures.append(
                {
                    **row,
                    "call_stages": [
                        {k: call.get(k) for k in ("stage", "status", "issues", "request_id")}
                        for call in result.get("calls", [])
                    ],
                    "review_statuses": [
                        review.get("status") for review in result.get("reviews", [])
                    ],
                }
            )
    ledger_path = directory / "calls.jsonl"
    ledger_bytes = ledger_path.read_bytes() if ledger_path.exists() else b""
    ledger = [json.loads(line) for line in ledger_bytes.decode("utf-8").splitlines()]
    reservations = {r["request_id"]: r for r in ledger if r["event"] == "reserve"}
    receipts = {r["request_id"]: r["record"] for r in ledger if r["event"] == "response"}
    costs: dict[str, dict[str, Any]] = {}
    trial_costs: dict[tuple[str, str], dict[str, Any]] = {}
    for request_id, issued in reservations.items():
        model = issued["request"]["model"]
        phase = issued.get("metadata", {}).get("phase", "unknown")
        cost = costs.setdefault(model + "/" + phase, _new_cost())
        tc = trial_costs.setdefault((phase, issued["trial_id"]), _new_cost())
        response = receipts.get(request_id, {})
        usage = response.get("usage") or {}
        known = response.get("unknown_consumption") is False and all(
            type(usage.get(name)) is int and usage[name] >= 0
            for name in ("generated_tokens", "total_tokens")
        )
        status = response.get("status", "pending_without_receipt")
        for aggregate in (cost, tc):
            aggregate["attempted_calls"] += 1
            aggregate["known_usage_calls" if known else "unknown_usage_calls"] += 1
            if known:
                aggregate["observed_generated_tokens"] += usage["generated_tokens"]
                aggregate["observed_total_tokens"] += usage["total_tokens"]
            else:
                aggregate["reserved_unknown_total_tokens"] += issued["reserved_total_tokens"]
            observed = {
                "client_wall_seconds": response.get("client_wall_seconds"),
                **{
                    name: (response.get("durations_seconds") or {}).get(duration)
                    for name, duration in (
                        ("load_seconds", "load_duration"),
                        ("prefill_seconds", "prompt_eval_duration"),
                        ("generation_seconds", "eval_duration"),
                    )
                },
            }
            for name, value in observed.items():
                if _amount(value):
                    aggregate["observed_" + name] += value
                    aggregate["known_duration_calls"][name] += 1
            aggregate["status_counts"][status] = aggregate["status_counts"].get(status, 0) + 1
    models = sorted({row["model"] for row in rows})
    comparisons = {}
    outcomes: dict[str, Any] = {}
    for model in models:
        model_rows = [
            row
            for row in rows
            if row["model"] == model
            and row["phase"] == "confirmation"
            and row["seed"] == protocol["seed"]
        ]
        by_parent: dict[str, dict[str, Any]] = {}
        for row in model_rows:
            by_parent.setdefault(row["task_id"], {})[row["arm"]] = row
        pairs = [
            arms
            for arms in by_parent.values()
            if "A" in arms
            and "B" in arms
            and arms["A"]["oracle_assessed"]
            and arms["B"]["oracle_assessed"]
            and arms["A"]["known_attempt_termination"]
            and arms["B"]["known_attempt_termination"]
            and (edition != "024" or arms["A"]["gold_decision"] != "unknown")
        ]
        differences = [
            int(pair["A"]["evidence_supported_completion"])
            - int(pair["B"]["evidence_supported_completion"])
            for pair in pairs
        ]
        both = [
            pair
            for pair in pairs
            if pair["A"]["evidence_supported_completion"]
            and pair["B"]["evidence_supported_completion"]
        ]
        subset = {}
        for arm in ("A", "B"):
            selected = [trial_costs.get(("confirmation", pair[arm]["key"])) for pair in both]
            aggregate = _new_cost()
            for value in selected:
                if value is None:
                    continue
                for name in aggregate:
                    if name == "status_counts":
                        for status, count in value[name].items():
                            aggregate[name][status] = aggregate[name].get(status, 0) + count
                    elif name == "known_duration_calls":
                        for duration, count in value[name].items():
                            aggregate[name][duration] += count
                    else:
                        aggregate[name] += value[name]
            subset[arm] = {
                **_finish_cost(aggregate),
                "parents": len(both),
                "parents_with_cost_records": sum(v is not None for v in selected),
            }
            if not selected or any(v is None for v in selected):
                for name in (
                    "generated_tokens",
                    "total_tokens",
                    *aggregate["known_duration_calls"],
                ):
                    subset[arm][name] = None
        comparisons[model] = {
            "paired_assessed_parents": len(pairs),
            "scheduled_parents": len(by_parent),
            "wins": differences.count(1),
            "ties": differences.count(0),
            "losses": differences.count(-1),
            "A_minus_B_completion": sum(differences) / len(differences) if differences else None,
            "parent_bootstrap_95_interval": _interval(
                differences, protocol["bootstrap_seed"], protocol["bootstrap_replicates"]
            ),
            "both_successful_parents": len(both),
            "both_successful_costs": subset,
            "success_subset_selection_bias": True,
            "C_interpretation": "pooled-information reference; different information arrival",
        }
        answerable = [
            arms
            for arms in by_parent.values()
            if "A" in arms and "B" in arms and arms["A"]["gold_decision"] != "unknown"
        ]
        bounds = []
        for arms in answerable:
            values = {}
            for arm in ("A", "B"):
                row = arms[arm]
                values[arm] = (
                    [int(bool(row["verified_supported_completion"]))] * 2
                    if (row["oracle_assessed"] and row["known_attempt_termination"])
                    else [0, 1]
                )
            bounds.append((values["A"][0] - values["B"][1], values["A"][1] - values["B"][0]))
        comparisons[model]["all_planned_answerable_parents"] = len(answerable)
        comparisons[model]["unresolved_A_minus_B_bounds"] = (
            [sum(b[i] for b in bounds) / len(bounds) for i in (0, 1)] if bounds else None
        )
        outcomes[model] = {}
        for arm in ("A", "B", "C"):
            arm_rows = [row for row in model_rows if row["arm"] == arm]
            outcomes[model][arm] = {
                "scheduled": len(arm_rows),
                **{
                    metric: sum(bool(row.get(metric)) for row in arm_rows)
                    for metric in (
                        "oracle_assessed",
                        "answer_correct",
                        "evidence_supported_completion",
                        "grounded_abstention",
                        "false_acceptance",
                        "pending",
                        "known_attempt_termination",
                        "answer_grounded_correct",
                        "verified_supported_completion",
                        "executed",
                        "unexecuted",
                        "known_usage",
                        "reviewer_false_pass",
                    )
                },
                "known_insufficient_parents": sum(
                    row["gold_decision"] == "unknown" for row in arm_rows
                ),
                "execution_counts": dict(Counter(row["execution"] for row in arm_rows)),
                "stop_counts": dict(Counter(str(row["runner_stop"]) for row in arm_rows)),
            }
    summary = {
        "protocol_id": protocol["protocol_id"],
        "rows": len(rows),
        "outcomes": outcomes,
        "comparisons": comparisons,
        "all_attempt_costs": {key: _finish_cost(value) for key, value in costs.items()},
        "planned_confirmation_keys": len(planned),
        "planned_auxiliary_keys": len(auxiliary_sources),
        "planned_sensitivity_keys": 0
        if frozen is None
        else len(frozen.get("planned_sensitivity_keys", [])),
        "legacy_metric_mapping": (
            "evidence_supported_completion equals verified_supported_completion; "
            "answer_grounded_correct excludes model-review acceptance"
        ),
        "termination_markers": [r for r in ledger if r.get("event") == "terminated_unmetered"],
        "missing_terminal_keys": sum(
            row["execution"] == "unexecuted_no_terminal_record" for row in rows
        ),
        "primary_seed": protocol["seed"],
        "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
        "ledger_configuration_events": [
            {
                name: row[name]
                for name in (
                    "event",
                    "created_at",
                    "amendment_id",
                    "authorization",
                    "from_config_sha256",
                    "to_config_sha256",
                    "prior_events_canonical_sha256",
                    "prior_event_count",
                )
                if name in row
            }
            | {
                name: {
                    field: row[name][field]
                    for field in ("run_id", "freeze_id", "limits")
                    if field in row[name]
                }
                for name in ("config", "new_config")
                if isinstance(row.get(name), dict)
            }
            for row in ledger
            if row.get("event") in ("config", "wall_budget_amendment")
        ],
        "original_first_reservation_epoch": next(
            (row.get("started_epoch") for row in ledger if row.get("event") == "reserve"), None
        ),
        "declared_global_wall_seconds": protocol["global_limits"]["wall_seconds"],
        "no_cross_model_absolute_timing_claim": True,
        "unknown_tokens_are_not_zero": True,
        "energy_and_price": "not measured",
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "summary.json", summary)
    write_json(output / "scored-trials.json", rows)
    write_json(output / "failure-analysis.json", failures)
    with (output / "scored-trials.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = list(rows[0]) if rows else ["phase", "key", "execution"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return summary
