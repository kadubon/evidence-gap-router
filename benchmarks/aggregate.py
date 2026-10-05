"""Reaggregate parent-cluster results; retain ties, failures and unsupported rows."""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from benchmarks.erratum_021 import classify_stop
from benchmarks.tasks import manifest


def mean(values):
    return statistics.fmean(values) if values else None


def paired_interval(differences):
    if not differences:
        return None
    rng = random.Random(manifest()["aggregation"]["paired_bootstrap_seed"])
    boots = sorted(
        statistics.fmean(rng.choices(differences, k=len(differences)))
        for _ in range(manifest()["aggregation"]["paired_bootstrap_resamples"])
    )
    return [boots[int(len(boots) * 0.025)], boots[min(len(boots) - 1, int(len(boots) * 0.975))]]


def paired_costs(pairs):
    """Paired parent differences, with explicit subsets and delay assumptions."""
    costs = {}
    for name in ("callbacks", "controller_wall_seconds", "controller_cpu_seconds", "cpu_seconds"):
        differences = [
            a[name] - b[name]
            for a, b in pairs
            if a.get(name) is not None and b.get(name) is not None
        ]
        costs[name] = {
            "paired_parents": len(differences),
            "difference_egr_minus_baseline": mean(differences),
            "paired_bootstrap_95_percent_interval": paired_interval(differences),
        }
    complete = [
        (a, b)
        for a, b in pairs
        if all(
            p.get(k) is not None for p in (a, b) for k in ("callbacks", "controller_wall_seconds")
        )
    ]
    sensitivity = []
    for delay in (0, 0.001, 0.01, 0.1, 1):
        differences = [
            a["controller_wall_seconds"]
            - b["controller_wall_seconds"]
            + delay * (a["callbacks"] - b["callbacks"])
            for a, b in complete
        ]
        sensitivity.append(
            {
                "assumed_equal_callback_delay_seconds": delay,
                "paired_parents": len(complete),
                "difference_egr_minus_baseline_seconds": mean(differences),
                "paired_bootstrap_95_percent_interval": paired_interval(differences),
            }
        )
    return {
        "metrics": costs,
        "delay_sensitivity": sensitivity,
        "scope": (
            "Both oracle-complete known-cost pairs; success-selected subset. Equal additive "
            "delay is an assumption, not observed LLM cost or commercial ROI."
        ),
    }


def summarize(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[(row["environment"]["package"], row["method"], row["task_id"])].append(row)
    parents = []
    for (version, method, task), variants in groups.items():
        supported = [r for r in variants if r.get("status") not in {"unsupported", "unexecuted"}]
        first = variants[0]
        original = next(
            (
                r
                for r in supported
                if r.get("variant") == "original"
                and (
                    method != "random-feasible"
                    or r.get("random_seed") == manifest()["random_seeds"][0]
                )
            ),
            None,
        )

        def completed(row):
            return (
                row.get("status") == "completed"
                and not row.get("timeout")
                and bool((row.get("oracle") or {}).get("completion"))
            )

        def cost(name, supported=supported):
            return mean([r[name] for r in supported if r.get(name) is not None])

        classification = classify_stop(original or {"status": "unexecuted", "task": first["task"]})

        parents.append(
            {
                "version": version,
                "method": method,
                "task_id": task,
                "family": first["task"]["family"],
                "budget": first["task"]["budget_class"],
                "solvable": first["task"]["solvable"],
                "repetitions": len(variants),
                "supported": bool(supported),
                "reference_only": first.get("reference_only", False),
                "attempted_repetitions": len(supported),
                "unexecuted": sum(r.get("status") == "unexecuted" for r in variants),
                "unsupported": sum(r.get("status") == "unsupported" for r in variants),
                "timeouts": sum(bool(r.get("timeout")) for r in variants),
                "resource_limits": sum(
                    r.get("worker_status", r.get("status")) == "resource_limit" for r in variants
                ),
                "unavailable_workers": sum(
                    r.get("worker_status", r.get("status")) == "unavailable" for r in variants
                ),
                "exceptions": sum(
                    r.get("status") == "exception"
                    or bool(r.get("exception"))
                    and r.get("status") != "unsupported"
                    for r in variants
                ),
                "completion": mean([float(completed(r)) for r in supported]) or 0,
                "primary_original_completion": int(completed(original)) if original else 0,
                "known_correct_abstention": int(classification["known_correct_abstention"]),
                "uncertain_incomplete_stop": int(classification["uncertain_incomplete_stop"]),
                "execution_fault": int(classification["execution_fault"]),
                "erroneous_stop": int(classification["erroneous_stop"]),
                "terminal_class": classification["terminal_class"],
                "uncertainty_reasons": classification["uncertainty_reasons"],
                "false_satisfied": any(r.get("false_satisfied") is True for r in variants),
                "false_satisfied_trials": sum(r.get("false_satisfied") is True for r in supported),
                "unassessed_false_satisfied_repetitions": sum(
                    r.get("false_satisfied") is None for r in supported
                ),
                "callbacks": cost("callbacks"),
                "verifications": cost("verifications"),
                "unknown_callback_cost_repetitions": sum(
                    r.get("callbacks") is None for r in supported
                ),
                "unknown_verification_cost_repetitions": sum(
                    r.get("verifications") is None for r in supported
                ),
                "cpu_seconds": cost("cpu_seconds"),
                "planning_cpu_seconds": cost("planning_cpu_seconds"),
                "controller_wall_seconds": cost("controller_wall_seconds"),
                "controller_cpu_seconds": cost("controller_cpu_seconds"),
                "end_to_end_seconds": cost("end_to_end_seconds"),
                "peak_traced_python_allocation_bytes": max(
                    (
                        r["peak_traced_python_allocation_bytes"]
                        for r in supported
                        if r.get("peak_traced_python_allocation_bytes") is not None
                    ),
                    default=None,
                ),
                "snapshot_resume": mean(
                    [
                        float(r["snapshot_resume"])
                        for r in supported
                        if r.get("snapshot_resume") is not None
                    ]
                ),
            }
        )
    tables = []
    for dimension in ("overall", "family", "budget"):
        bins = defaultdict(list)
        for parent in parents:
            if parent["reference_only"]:
                continue
            key = (
                parent["version"],
                parent["method"],
                parent[dimension] if dimension != "overall" else "all",
            )
            bins[key].append(parent)
        for (version, method, label), values in sorted(bins.items()):
            supported = [p for p in values if p["supported"]]
            solvable = [p for p in supported if p["solvable"]]
            stop_tasks = [p for p in supported if not p["solvable"]]
            tables.append(
                {
                    "dimension": dimension,
                    "label": label,
                    "version": version,
                    "method": method,
                    "requested_parents": len(values),
                    "supported_parents": len(supported),
                    "solvable_parents": len(solvable),
                    "completion_numerator": sum(p["primary_original_completion"] for p in solvable),
                    "completion_rate": mean([p["primary_original_completion"] for p in solvable]),
                    "cluster_mean_completion_sum": sum(p["completion"] for p in solvable),
                    "cluster_mean_completion_rate": mean([p["completion"] for p in solvable]),
                    "false_satisfied_count": sum(p["false_satisfied"] for p in supported),
                    "false_satisfied_denominator": len(supported),
                    "known_correct_abstention_numerator": sum(
                        p["known_correct_abstention"] for p in stop_tasks
                    ),
                    "known_correct_abstention_denominator": len(stop_tasks),
                    "uncertain_incomplete_stop_numerator": sum(
                        p["uncertain_incomplete_stop"] for p in stop_tasks
                    ),
                    "execution_fault_numerator": sum(p["execution_fault"] for p in supported),
                    "semantic_erroneous_stop_numerator": sum(p["erroneous_stop"] for p in solvable),
                    "erroneous_stop_numerator": sum(1 - p["completion"] for p in solvable),
                    "unsupported_repetitions": sum(p["unsupported"] for p in values),
                    "unexecuted_repetitions": sum(p["unexecuted"] for p in values),
                    "attempted_repetitions": sum(p["attempted_repetitions"] for p in values),
                    "false_satisfied_trial_count": sum(
                        p["false_satisfied_trials"] for p in supported
                    ),
                    "unassessed_false_satisfied_repetitions": sum(
                        p["unassessed_false_satisfied_repetitions"] for p in supported
                    ),
                    "unknown_callback_cost_repetitions": sum(
                        p["unknown_callback_cost_repetitions"] for p in supported
                    ),
                    "unknown_verification_cost_repetitions": sum(
                        p["unknown_verification_cost_repetitions"] for p in supported
                    ),
                    "timeout_repetitions": sum(p["timeouts"] for p in values),
                    "resource_limit_repetitions": sum(p["resource_limits"] for p in values),
                    "unavailable_worker_repetitions": sum(p["unavailable_workers"] for p in values),
                    "exception_repetitions": sum(p["exceptions"] for p in values),
                    "callbacks_all_tasks_mean": mean(
                        [p["callbacks"] for p in supported if p["callbacks"] is not None]
                    ),
                    "verifications_all_tasks_mean": mean(
                        [p["verifications"] for p in supported if p["verifications"] is not None]
                    ),
                    "cpu_seconds_mean": mean(
                        [p["cpu_seconds"] for p in supported if p["cpu_seconds"] is not None]
                    ),
                    "planning_cpu_seconds_mean": mean(
                        [
                            p["planning_cpu_seconds"]
                            for p in supported
                            if p["planning_cpu_seconds"] is not None
                        ]
                    ),
                    "end_to_end_seconds_mean": mean(
                        [
                            p["end_to_end_seconds"]
                            for p in supported
                            if p["end_to_end_seconds"] is not None
                        ]
                    ),
                    "controller_wall_seconds_all_tasks_mean": mean(
                        [
                            p["controller_wall_seconds"]
                            for p in supported
                            if p["controller_wall_seconds"] is not None
                        ]
                    ),
                    "controller_cpu_seconds_all_tasks_mean": mean(
                        [
                            p["controller_cpu_seconds"]
                            for p in supported
                            if p["controller_cpu_seconds"] is not None
                        ]
                    ),
                    "costs_by_outcome": [
                        {
                            "outcome": outcome,
                            "parents": len(selected),
                            "known_callback_parents": sum(
                                p["callbacks"] is not None for p in selected
                            ),
                            "callbacks_mean": mean(
                                [p["callbacks"] for p in selected if p["callbacks"] is not None]
                            ),
                            "controller_wall_seconds_mean": mean(
                                [
                                    p["controller_wall_seconds"]
                                    for p in selected
                                    if p["controller_wall_seconds"] is not None
                                ]
                            ),
                        }
                        for outcome, selected in (
                            ("oracle_complete", [p for p in supported if p["completion"] == 1]),
                            (
                                "incomplete_or_execution_failure",
                                [p for p in supported if p["completion"] != 1],
                            ),
                        )
                    ],
                    "peak_traced_python_allocation_bytes_max": max(
                        (
                            p["peak_traced_python_allocation_bytes"]
                            for p in supported
                            if p["peak_traced_python_allocation_bytes"] is not None
                        ),
                        default=None,
                    ),
                }
            )
    comparisons = []
    versions = sorted({p["version"] for p in parents})
    for version in versions:
        egr = {
            p["task_id"]: p
            for p in parents
            if p["method"] == "egr" and p["version"] == version and p["supported"]
        }
        for method in sorted(
            {p["method"] for p in parents if p["version"] == version and not p["reference_only"]}
            - {"egr"}
        ):
            baseline = {
                p["task_id"]: p
                for p in parents
                if p["method"] == method and p["version"] == version and p["supported"]
            }
            common = sorted(set(egr) & set(baseline))
            for family in ["all", *manifest()["families"]]:
                pairs = [
                    (egr[t], baseline[t])
                    for t in common
                    if egr[t]["solvable"] and (family == "all" or egr[t]["family"] == family)
                ]
                if not pairs:
                    continue
                differences = [a["completion"] - b["completion"] for a, b in pairs]
                both = [(a, b) for a, b in pairs if a["completion"] == b["completion"] == 1]
                comparisons.append(
                    {
                        "version": version,
                        "baseline": method,
                        "family": family,
                        "paired_solvable_parents": len(pairs),
                        "completion_difference": mean(differences),
                        "cluster_bootstrap_95_percent_interval": paired_interval(differences),
                        "wins": sum(d > 0 for d in differences),
                        "ties": sum(d == 0 for d in differences),
                        "losses": sum(d < 0 for d in differences),
                        "both_success_cost_subset_parents": len(both),
                        "paired_costs_on_selected_subset": paired_costs(both),
                        "callback_difference_on_selected_subset": mean(
                            [
                                a["callbacks"] - b["callbacks"]
                                for a, b in both
                                if a["callbacks"] is not None and b["callbacks"] is not None
                            ]
                        ),
                        "cpu_difference_on_selected_subset": mean(
                            [
                                a["cpu_seconds"] - b["cpu_seconds"]
                                for a, b in both
                                if a["cpu_seconds"] is not None and b["cpu_seconds"] is not None
                            ]
                        ),
                        "subset_limitation": (
                            "Both-success selected subset; not an all-task efficiency estimate."
                        ),
                    }
                )
    version_comparisons = []
    old = {
        p["task_id"]: p
        for p in parents
        if p["version"] == manifest()["baseline_version"]
        and p["method"] == "egr"
        and p["supported"]
    }
    new = {
        p["task_id"]: p
        for p in parents
        if p["version"] == manifest()["candidate_version"]
        and p["method"] == "egr"
        and p["supported"]
    }
    for family in ["all", *manifest()["families"]]:
        common = [
            (new[t], old[t])
            for t in sorted(set(new) & set(old))
            if family == "all" or new[t]["family"] == family
        ]
        if not common:
            continue
        solvable = [(a, b) for a, b in common if a["solvable"]]
        differences = [a["completion"] - b["completion"] for a, b in solvable]
        version_comparisons.append(
            {
                "question": "Q1",
                "comparison_kind": "matched-version EGR",
                "family": family,
                "old_version": manifest()["baseline_version"],
                "new_version": manifest()["candidate_version"],
                "compatible_attempted_parents": len(common),
                "paired_solvable_parents": len(solvable),
                "completion_difference": mean(differences),
                "cluster_bootstrap_95_percent_interval": paired_interval(differences),
                "wins": sum(d > 0 for d in differences),
                "ties": sum(d == 0 for d in differences),
                "losses": sum(d < 0 for d in differences),
                "old_false_satisfied_parents": sum(b["false_satisfied"] for a, b in common),
                "new_false_satisfied_parents": sum(a["false_satisfied"] for a, b in common),
                "old_unassessed_false_satisfied_repetitions": sum(
                    b["unassessed_false_satisfied_repetitions"] for a, b in common
                ),
                "new_unassessed_false_satisfied_repetitions": sum(
                    a["unassessed_false_satisfied_repetitions"] for a, b in common
                ),
                "limitation": (
                    "API-unsupported/unexecuted excluded only from matched-version pairing, "
                    "listed in version tables; compatible exceptions/timeouts remain "
                    "failed attempts."
                ),
            }
        )
    return {
        "schema_version": "egr-aggregate-022-1",
        "parents": parents,
        "tables": tables,
        "paired_comparisons": comparisons,
        "version_comparisons": version_comparisons,
        "reference_parents": [p for p in parents if p["reference_only"]],
        "denominator_definition": (
            "Primary integer n/N: original order and random seed17. Paired bootstrap uses "
            "parent means across attempted variants/seeds; exceptions/timeouts=failed. "
            "False-satisfied parent-any and per-attempted-trial counts both provided; "
            "unsupported/unexecuted separate. Direct pipelines are separate references."
        ),
        "raw_trial_count": len(rows),
        "unique_parent_tasks": len({r["task_id"] for r in rows}),
        "measurement_sources": [
            json.loads(value)
            for value in sorted(
                {
                    json.dumps(
                        {
                            "environment": r["environment"],
                            "implementation_commit": r.get("implementation_commit"),
                            "wheel_sha256": r.get("wheel_sha256"),
                            "package_sha256": r.get("package_sha256"),
                            "manifest_sha256": r.get("manifest_sha256"),
                        },
                        sort_keys=True,
                    )
                    for r in rows
                }
            )
        ],
        "limitations": (
            "Synthetic finite CPU-only experiment; clusters are generated task parents, "
            "not external populations. No LLM accuracy, money saving, independence, "
            "capability growth or intelligence phase claim. Zero observed false-satisfied "
            "is not zero risk. All four methods share current necessity/helper gates and "
            "the public finite runner; ranking is the only method difference. Normal "
            "timings have no allocation tracing/profile. Proof/helper memory and visits "
            "are separate processes. The previously observed 240-parent set is a "
            "regression set; only original/seed17 was rerun."
        ),
    }


def export(rows: list[dict], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if any(
        (destination / name).exists()
        for name in ("summary.json", "trials.csv", "report.md", "summary.ja.md")
    ):
        raise ValueError("Aggregation output exists; use a new directory")
    summary = summarize(rows)
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    fields = (
        "task_id",
        "variant",
        "random_seed",
        "method",
        "status",
        "worker_status",
        "runner_stop",
        "domain_stop",
        "terminal_class",
        "known_correct_abstention",
        "uncertain_incomplete_stop",
        "execution_fault",
        "erroneous_stop",
        "false_satisfied",
        "callbacks",
        "verifications",
        "stop_reason",
        "domain_stop",
        "planning_cpu_seconds",
        "cpu_seconds",
        "end_to_end_seconds",
        "callback_cpu_seconds",
        "callback_wall_seconds",
        "execution_and_transitions_seconds",
        "peak_traced_python_allocation_bytes",
        "timeout",
        "exception",
        "snapshot_resume",
        "wheel_sha256",
        "package_sha256",
        "manifest_sha256",
        "implementation_commit",
        "version",
        "python",
        "os",
        "machine",
        "pydantic",
        "pydantic_core",
        "oracle_completion",
        "solved_required",
        "required",
        "resource_overrun",
        "reference_only",
        "whole_worker_seconds",
        "startup_import_and_ipc_seconds",
    )
    with (destination / "trials.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            values = dict(row)
            values.update(
                {
                    key: row["environment"].get(key)
                    for key in ("python", "os", "machine", "pydantic", "pydantic_core")
                }
            )
            values["version"] = row["environment"]["package"]
            assessed = row.get("oracle") or {}
            values.update(
                oracle_completion=assessed.get("completion"),
                solved_required=assessed.get("solved_required"),
                required=assessed.get("required"),
            )
            values.update(classify_stop(row))
            writer.writerow(values)
    lines = [
        "# v0.2.2 common-loop regression experiment",
        "",
        summary["limitations"],
        "",
        f"Raw trials: {len(rows)}; distinct parent tasks: {summary['unique_parent_tasks']}. "
        "Variants and random seeds are clustered, not independent tasks.",
        "",
        "Q1 correctness/continuation and Q2 utility are separate from Q3 controller cost. "
        "Unsupported old APIs, errors and timeouts remain in raw results. "
        "Tokens and money are unmeasured.",
        "Primary completion is integer original-task n/N (random seed17); separate "
        "cluster means retain failed compatible variants. False-satisfied is parent-any "
        "observed error, with unassessed trials separately counted. Worker startup/import/IPC "
        "is an imposed isolation cost, separate from trial time.",
        "",
        "| Version | Method | Solvable denominator | Completion numerator | "
        "False-satisfied / supported parents | Mean callbacks | Mean CPU seconds |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for t in summary["tables"]:
        if t["dimension"] == "overall":
            lines.append(
                f"| {t['version']} | {t['method']} | {t['solvable_parents']} | "
                f"{t['completion_numerator']} | "
                f"{t['false_satisfied_count']}/{t['false_satisfied_denominator']} | "
                f"{t['callbacks_all_tasks_mean']} | {t['cpu_seconds_mean']} |"
            )
    lines += [
        "",
        "Family/budget denominators, task bootstrap intervals, wins/ties/losses and "
        "selected both-success cost subsets are in summary.json. Cheap failure is not "
        "an efficiency win. Direct pipelines have explicit differing controller contracts.",
        "",
        "A fixed pipeline suffices when dependency order is predetermined. Gap control "
        "can add CPU/memory overhead when callback counts tie. Results are not conditioned "
        "on EGR winning. Manifests and traces make these distinctions reaggregatable.",
    ]
    lines += [
        "",
        "| Family/budget | Label | Version | Method | Completion n/N | False-satisfied n/N |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for table in summary["tables"]:
        if table["dimension"] != "overall":
            lines.append(
                f"| {table['dimension']} | {table['label']} | {table['version']} | "
                f"{table['method']} | "
                f"{table['completion_numerator']}/{table['solvable_parents']} | "
                f"{table['false_satisfied_count']}/{table['false_satisfied_denominator']} |"
            )
    lines += [
        "",
        "| Method paired comparison | Family | Solvable parents | Mean completion difference | "
        "95% parent-cluster interval | Wins/ties/losses |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for pair in summary["paired_comparisons"]:
        lines.append(
            f"| {pair['version']} EGR − {pair['baseline']} | {pair['family']} | "
            f"{pair['paired_solvable_parents']} | {pair['completion_difference']} | "
            f"{pair['cluster_bootstrap_95_percent_interval']} | "
            f"{pair['wins']}/{pair['ties']}/{pair['losses']} |"
        )
    lines += [
        "",
        "| Version Q1 EGR comparison | Family | Compatible parents | Solvable parents | "
        "Completion difference | 95% parent-cluster interval | Old/new false-satisfied parents |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for pair in summary["version_comparisons"]:
        lines.append(
            f"| 0.2.1 − 0.2.0 | {pair['family']} | {pair['compatible_attempted_parents']} | "
            f"{pair['paired_solvable_parents']} | {pair['completion_difference']} | "
            f"{pair['cluster_bootstrap_95_percent_interval']} | "
            f"{pair['old_false_satisfied_parents']}/{pair['new_false_satisfied_parents']} |"
        )
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (destination / "summary.ja.md").write_text(
        f"# モデルフリー工学実験\n\n生試行 {len(rows)} 件、"
        f"親 task {summary['unique_parent_tasks']} 件。"
        "順序・名前変更と random seed は親 task 内でまとめ、独立標本として数えていません。\n\n"
        "summary.json は family/予算別の分母、完了率、誤受入、誤停止、paired bootstrap 区間、"
        "勝ち・同等・悪化、両者成功した限定 subset の費用を残します。"
        "停止の安さを効率改善としません。"
        "旧 API 非対応・例外・timeout を除去していません。\n\n"
        "固定順で十分な単純処理では router の制御費用だけ増える場合があります。"
        "CPU の有限人工 task の結果であり、LLM 正答率、金額削減、統計的独立性、"
        "集合知・能力成長の実証ではありません。誤受入 0 件もリスク 0 の証明ではありません。\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [
        json.loads(line)
        for path in args.inputs
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    export(rows, args.output)


if __name__ == "__main__":
    main()
