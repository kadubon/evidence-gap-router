"""Independent reporting of answerable completion and grounded abstention.

Reads retained outputs only. This does not import or modify the frozen experiment,
re-evaluate its oracle, dispatch a request, or filter failures from denominators.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

BOOTSTRAP_SEED = 23031041
BOOTSTRAP_REPLICATES = 2000
UNKNOWN_FAULTS = {"unknown_consumption", "pending_or_unknown_dispatch", "callback_exception"}


def _read(path: Path) -> Any:
    return json.loads(path.read_text("utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _known(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("oracle_assessed") and row.get("known_attempt_termination"))


def _value(row: dict[str, Any] | None) -> int | None:
    return (
        int(bool(row.get("evidence_supported_completion")))
        if row is not None and _known(row)
        else None
    )


def _bootstrap(values: list[int]) -> list[float] | None:
    if not values:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    means = sorted(
        sum(rng.choices(values, k=len(values))) / len(values) for _ in range(BOOTSTRAP_REPLICATES)
    )
    return [means[50], means[1950]]


def _outcomes(rows: list[dict[str, Any] | None]) -> dict[str, Any]:
    retained = [row for row in rows if row is not None]
    count = len(rows)
    metrics = {
        name: sum(bool(row.get(name)) for row in retained)
        for name in (
            "oracle_assessed",
            "known_attempt_termination",
            "answer_correct",
            "evidence_supported_completion",
            "grounded_abstention",
            "false_acceptance",
            "system_claimed_complete",
            "pending",
        )
    }
    known = sum(_known(row) for row in retained)
    known_supported = sum(_value(row) == 1 for row in retained)
    unsupported_known = sum(
        _known(row) and not row.get("evidence_supported_completion") for row in retained
    )
    unresolved = count - known
    return {
        "scheduled_denominator": count,
        "retained_rows": len(retained),
        "missing_rows": count - len(retained),
        **metrics,
        "known_not_supported": unsupported_known,
        "known_supported_completion": known_supported,
        "unresolved_or_unassessed": unresolved,
        "observed_supported_over_all_scheduled": known_supported / count if count else None,
        "false_acceptance_over_all_scheduled": metrics["false_acceptance"] / count
        if count
        else None,
        "completion_identification_bounds": [
            known_supported / count,
            (known_supported + unresolved) / count,
        ]
        if count
        else None,
        "faults": dict(Counter(str(row.get("fault")) for row in retained if row.get("fault"))),
        "uncertain_execution_rows": sum(
            bool(row.get("pending")) or row.get("fault") in UNKNOWN_FAULTS for row in retained
        ),
        "unexecuted_rows": sum(
            str(row.get("execution", "")).startswith("unexecuted") for row in retained
        ),
        "execution_counts": dict(Counter(str(row.get("execution")) for row in retained)),
        "runner_stops": dict(Counter(str(row.get("runner_stop")) for row in retained)),
        "domain_stops": dict(Counter(str(row.get("domain_stop")) for row in retained)),
        "denominator_policy": (
            "All scheduled arms retained; unresolved use is not a known failure or safe abstention."
        ),
    }


def _new_cost() -> dict[str, Any]:
    durations = ("client_wall_seconds", "load_seconds", "prefill_seconds", "generation_seconds")
    return {
        "attempted_calls": 0,
        "known_usage_calls": 0,
        "unknown_usage_calls": 0,
        "observed_total_tokens": 0,
        "observed_generated_tokens": 0,
        "reserved_unknown_total_tokens": 0,
        **{"observed_" + name: 0.0 for name in durations},
        "known_duration_calls": dict.fromkeys(durations, 0),
        "status_counts": {},
    }


def _finish_cost(cost: dict[str, Any]) -> dict[str, Any]:
    return {
        **cost,
        "total_tokens": cost["observed_total_tokens"] if not cost["unknown_usage_calls"] else None,
        "generated_tokens": cost["observed_generated_tokens"]
        if not cost["unknown_usage_calls"]
        else None,
        **{
            name: cost["observed_" + name] if count == cost["attempted_calls"] else None
            for name, count in cost["known_duration_calls"].items()
        },
    }


def _ledger(
    path: Path, phase: str
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], str]:
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(
            "incomplete ledger tail; retain it and read again after dispatch completes"
        )
    events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
    reservations: dict[str, Any] = {}
    responses: dict[str, Any] = {}
    for event in events:
        if event["event"] == "reserve":
            if event["request_id"] in reservations:
                raise ValueError("duplicate reservation")
            reservations[event["request_id"]] = event
        elif event["event"] == "response":
            if event["request_id"] in responses:
                raise ValueError("duplicate response")
            responses[event["request_id"]] = event["record"]
    by_trial: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for request_id, issued in reservations.items():
        if issued.get("metadata", {}).get("phase") != phase:
            continue
        record = responses.get(request_id, {})
        usage = record.get("usage") or {}
        known = record.get("unknown_consumption") is False and all(
            type(usage.get(name)) is int and usage[name] >= 0
            for name in ("total_tokens", "generated_tokens")
        )
        model = issued["request"]["model"]
        for aggregate in (
            by_trial.setdefault(issued["trial_id"], _new_cost()),
            by_model.setdefault(model, _new_cost()),
        ):
            aggregate["attempted_calls"] += 1
            aggregate["known_usage_calls" if known else "unknown_usage_calls"] += 1
            if known:
                aggregate["observed_total_tokens"] += usage["total_tokens"]
                aggregate["observed_generated_tokens"] += usage["generated_tokens"]
            else:
                aggregate["reserved_unknown_total_tokens"] += issued["reserved_total_tokens"]
            times = {
                "client_wall_seconds": record.get("client_wall_seconds"),
                **{
                    name: (record.get("durations_seconds") or {}).get(key)
                    for name, key in (
                        ("load_seconds", "load_duration"),
                        ("prefill_seconds", "prompt_eval_duration"),
                        ("generation_seconds", "eval_duration"),
                    )
                },
            }
            for name, value in times.items():
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    aggregate["observed_" + name] += value
                    aggregate["known_duration_calls"][name] += 1
            status = record.get("status", "pending_without_receipt")
            aggregate["status_counts"][status] = aggregate["status_counts"].get(status, 0) + 1
    return by_trial, by_model, hashlib.sha256(raw).hexdigest()


def _aggregate_costs(keys: list[str], costs: dict[str, Any] | None) -> dict[str, Any]:
    if not keys:
        return {"parents": 0, "costs": None, "reason": "empty success subset; no cost comparison"}
    if costs is None:
        return {"parents": len(keys), "costs": None, "reason": "per-trial ledger not supplied"}
    aggregate = _new_cost()
    for key in keys:
        # Absence of a reservation is zero observed model calls, not a generated
        # zero-token response. Matching retained records determine execution.
        cost = costs.get(key, _new_cost())
        for name, value in cost.items():
            if name in ("known_duration_calls", "status_counts"):
                for label, count in value.items():
                    aggregate[name][label] = aggregate[name].get(label, 0) + count
            else:
                aggregate[name] += value
    return {
        "parents": len(keys),
        "parents_with_model_reservations": sum(key in costs for key in keys),
        "costs": _finish_cost(aggregate),
    }


def recount(
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    phase: str,
    frozen: dict[str, Any] | None = None,
    seed: int | None = None,
    trial_costs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = [
        row for row in rows if row["phase"] == phase and (seed is None or row["seed"] == seed)
    ]
    observed: dict[str, dict[str, Any]] = {}
    for row in selected:
        if row["key"] in observed:
            raise ValueError("duplicate scored key")
        observed[row["key"]] = row
    scheduled = (
        frozen["planned_trial_keys"] if frozen is not None and phase == "confirmation" else selected
    )
    planned: dict[tuple[str, str, int], dict[str, Any]] = {}
    planned_keys: dict[tuple[str, str, int], dict[str, str]] = {}
    gold: dict[str, str] = {}
    for row in selected:
        decision = row.get("gold_decision")
        if decision not in ("yes", "no", "unknown"):
            raise ValueError("missing or invalid retained gold decision")
        if row["task_id"] in gold and gold[row["task_id"]] != decision:
            raise ValueError("inconsistent gold decision across arms")
        gold[row["task_id"]] = decision
    for item in scheduled:
        if seed is not None and item["seed"] != seed:
            continue
        identity = item["model"], item["task_id"], item["seed"]
        parent = planned.setdefault(identity, {})
        if item["arm"] in parent:
            raise ValueError("duplicate scheduled parent/arm")
        scored = observed.get(item["key"])
        if scored is not None and any(
            scored[name] != item[name] for name in ("model", "task_id", "seed", "arm")
        ):
            raise ValueError("scored/frozen identity mismatch")
        parent[item["arm"]] = scored
        planned_keys.setdefault(identity, {})[item["arm"]] = item["key"]
    models: dict[str, Any] = {}
    for model in sorted({identity[0] for identity in planned}):
        groups: dict[str, list[tuple[str, dict[str, Any]]]] = {
            "answerable": [],
            "underdetermined": [],
            "gold_unclassified": [],
        }
        for (name, task_id, _seed), arms in planned.items():
            if name != model:
                continue
            category = (
                "gold_unclassified"
                if task_id not in gold
                else ("underdetermined" if gold[task_id] == "unknown" else "answerable")
            )
            groups[category].append((task_id, arms))
        rendered: dict[str, Any] = {}
        for category, parents in groups.items():
            arm_rows = {arm: [arms.get(arm) for _, arms in parents] for arm in ("A", "B", "C")}
            differences = []
            both: list[dict[str, Any]] = []
            pair_rows = []
            low, high = 0, 0
            for task_id, arms in sorted(parents):
                a, b = _value(arms.get("A")), _value(arms.get("B"))
                bounds = (
                    (a - b, a - b)
                    if a is not None and b is not None
                    else (
                        (a - 1, a) if a is not None else (-b, 1 - b) if b is not None else (-1, 1)
                    )
                )
                low += bounds[0]
                high += bounds[1]
                if a is not None and b is not None:
                    differences.append(a - b)
                    if a and b:
                        both.append(arms)
                pair_rows.append(
                    {
                        "task_id": task_id,
                        "A_supported": a,
                        "B_supported": b,
                        "A_minus_B": a - b if a is not None and b is not None else None,
                    }
                )
            rendered[category] = {
                "scheduled_parents": len(parents),
                "arms": {arm: _outcomes(values) for arm, values in arm_rows.items()},
                "A_minus_B": {
                    "known_assessed_pairs": len(differences),
                    "unresolved_pairs": len(parents) - len(differences),
                    "wins": differences.count(1),
                    "ties": differences.count(0),
                    "losses": differences.count(-1),
                    "mean_on_known_pairs": sum(differences) / len(differences)
                    if differences
                    else None,
                    "parent_bootstrap_95_interval": _bootstrap(differences),
                    "all_scheduled_identification_bounds": [low / len(parents), high / len(parents)]
                    if parents
                    else None,
                    "pairs": pair_rows,
                },
                "both_A_B_supported_success_subset": {
                    "parents": len(both),
                    "selection_bias": True,
                    "A": _aggregate_costs([pair["A"]["key"] for pair in both], trial_costs),
                    "B": _aggregate_costs([pair["B"]["key"] for pair in both], trial_costs),
                },
                "all_attempt_costs_by_arm": {
                    arm: _aggregate_costs(
                        [
                            key
                            for (name, task_id, _seed), keys in planned_keys.items()
                            if name == model
                            and task_id in {task_id for task_id, _arms in parents}
                            and (key := keys.get(arm)) is not None
                        ],
                        trial_costs,
                    )
                    for arm in arm_rows
                },
                "C_interpretation": (
                    "All public documents initially available; pooled reference, "
                    "different information arrival."
                ),
            }
        models[model] = rendered
    return {
        "analysis": (
            "Independent posthoc reporting separation; "
            "frozen oracle and composite analysis unchanged."
        ),
        "phase": phase,
        "seed_filter": seed,
        "models": models,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "primary_endpoint": (
            "Answerable (gold yes/no) supported completion; "
            "underdetermined grounded abstention separate."
        ),
        "all_attempt_costs_from_frozen_summary": summary.get("all_attempt_costs", {}),
        "frozen_composite_comparisons_preserved": summary.get("comparisons", {}),
        "limitations": [
            "Posthoc endpoint separation, not a new preregistered experiment.",
            (
                "Bootstrap is descriptive for these few artificial parents; "
                "no population or causal superiority claim."
            ),
            (
                "Unresolved/unassessed rows remain visible and "
                "are not known failures or safe abstention."
            ),
            "Both-success costs condition on success and cannot establish total method efficiency.",
            (
                "No cross-model timing, energy, or price inference; "
                "observed duration components remain separate."
            ),
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--phase", choices=("pilot", "confirmation"), default="confirmation")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    costs, ledger_models, ledger_sha = (
        _ledger(args.ledger, args.phase) if args.ledger else (None, None, None)
    )
    result = recount(
        _read(args.scored),
        _read(args.summary),
        phase=args.phase,
        frozen=_read(args.freeze) if args.freeze else None,
        seed=args.seed,
        trial_costs=costs,
    )
    result["inputs_sha256"] = {
        name: _sha(path)
        for name, path in (
            ("scored", args.scored),
            ("summary", args.summary),
            ("freeze", args.freeze),
        )
        if path is not None
    }
    if ledger_sha is not None:
        result["inputs_sha256"]["ledger"] = ledger_sha
    result["supplemental_helper_sha256"] = _sha(Path(__file__))
    result["all_attempt_costs_independent_phase_ledger"] = (
        {model: _finish_cost(value) for model, value in ledger_models.items()}
        if ledger_models is not None
        else None
    )
    encoded = (
        json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, indent=2) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, "utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
