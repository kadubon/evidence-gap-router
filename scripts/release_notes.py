"""Generate release notes only after all recorded native profiles actually passed."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PROFILES = {
    "linux-3.12.json": ("Linux", "x86_64", "3.12"),
    "windows-3.12.json": ("Windows", "x86_64", "3.12"),
    "macos-arm64-3.12.json": ("Darwin", "arm64", "3.12"),
    "macos-intel-3.12.json": ("Darwin", "x86_64", "3.12"),
    "linux-3.13.json": ("Linux", "x86_64", "3.13"),
    "linux-3.14.json": ("Linux", "x86_64", "3.14"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--manual-run", required=True)
    parser.add_argument("--release-run", required=True)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected the one release wheel")
    wheel_hash = hashlib.sha256(wheels[0].read_bytes()).hexdigest()
    paths = {path.name: path for path in args.profiles.glob("*.json")}
    if set(paths) != set(PROFILES):
        raise ValueError("All six native profiles must be present; no extras")
    rows = []
    benchmark_hashes = set()
    for name, (system, architecture, python) in PROFILES.items():
        report = json.loads(paths[name].read_text(encoding="utf-8"))
        if (
            report["os"] != system
            or report["architecture"] != architecture
            or not report["python"].startswith(python + ".")
            or report["package_version"] != args.version
            or report["wheel_sha256"] != wheel_hash
            or report["installed_smoke"] != "passed"
            or report["pytest_exit_code"] != 0
            or report["rosetta_translated"]
        ):
            raise ValueError(f"Profile is not a passing native test of this artifact: {name}")
        if (
            args.version in {"0.2.3", "0.2.4"}
            and report.get("experiment_contract", {}).get("status") != "passed"
        ):
            raise ValueError(f"Portable experiment contract did not pass: {name}")
        if (
            args.version in {"0.2.4", "0.3.0"}
            and report.get("documentation_examples", {}).get("status") != "passed"
        ):
            raise ValueError(f"Installed documentation examples did not pass: {name}")
        if args.version != "0.3.0":
            if report.get("benchmark", {}).get("benchmark_smoke") != "passed":
                raise ValueError(f"Benchmark is not a passing native check: {name}")
            benchmark_hashes.add(report["benchmark"]["outcome_sha256"])
        else:
            if (
                report.get("new_llm_requests") != 0
                or report.get("new_efficacy_or_performance_experiments") != 0
            ):
                raise ValueError("v0.3.0 native validation must contain no experiments")
        rows.append(
            f"| {system} | {architecture} | {report['python']} | "
            f"{report['pydantic_version']} / {report['pydantic_core_version']} | passed |"
        )
    if args.version != "0.3.0" and len(benchmark_hashes) != 1:
        raise ValueError("Native benchmark outcomes differ across required profiles")
    tree = f"https://github.com/kadubon/evidence-gap-router/blob/{args.commit}"
    source_tree = f"https://github.com/kadubon/evidence-gap-router/tree/{args.commit}"
    notes = (
        f"Evidence-gap router {args.version}: consistent acceptance and comparable execution.\n\n"
        "Candidate-helper exploration reuses shared subproblems within the current evaluation, "
        "preserving exact prerequisites, authority and grounded alternatives. Contradiction "
        "resolution requires all related evidence in the pinned basis during issuance and "
        "reuse of imported records. Selectors share the same finite public runner, complete "
        "candidate pool, receipt/error handling and progress checks.\n\n"
        "**Compatibility:** legitimate schema-2 history remains readable. Incomplete old "
        "resolution grounds remain in history but cannot grant current acceptance; missing "
        "inputs are never invented. Snapshot, exact-decimal files, host invalidation and "
        "schema-1 migration continue to retain prior material, receipts and costs.\n\n"
        f"Model-free benchmark: [protocol, harness and recorded freeze]({source_tree}/benchmarks), "
        f"[English report]({tree}/docs/benchmark.md), "
        f"[Japanese summary]({tree}/docs/benchmark.ja.md), "
        f"[v0.2.1 erratum]({tree}/docs/benchmark-v0.2.1-erratum.md). "
        "The frozen candidate's package bytes match this release; later source changes were "
        "documentation/results and standalone source-test import setup; measured "
        "runtime/harness/generator bytes remain unchanged. Large raw trial/scaling data "
        "and checksums are linked "
        "from those reports and attached as separate benchmark assets. Baselines, failures, "
        "timeouts, no-advantage cases and selected-subset cost limits remain explicit.\n\n"
        "The old ten-parent F7 abstention difference came from runner-stop labels, not a "
        "demonstrated routing advantage. Recorded unknown use/effects remain uncertain. "
        "Old raw/report/freeze records are preserved; raw reclassification and new "
        "common-runner regression/confirmation measurements are separate outputs. "
        "Existing tasks are a regression set, not an unseen holdout. Helper candidate "
        "graphs and already-verified proof graphs have separate controller measurements.\n\n"
        "The same universal project wheel passed native installed core/runner/CLI "
        "regressions, fixtures, migration, Unicode-file, continuation and benchmark smoke below. "
        "Native Pydantic core wheels were installed and imported; reports are attached.\n\n"
        f"Portable benchmark outcome SHA256: {next(iter(benchmark_hashes), 'not_run')}\n\n"
        "| OS | Actual architecture | Python | Pydantic / core | Installed checks |\n"
        "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        f"Commit: {args.commit}\n\n"
        f"Manual validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.manual_run}\n\n"
        f"Release validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.release_run}\n\n"
        "The actual official PyPI wheel/sdist bytes matched the original build artifacts. "
        "A fresh, cache-free official-index install passed SDK/CLI/examples/migration smoke. "
        "Attached SHA256SUMS applies to the distribution files.\n\n"
        "Single process and writer. Host/checker trust, external effects, measurements and "
        "timeouts remain host responsibilities. Limited views are not a Python sandbox; "
        "fingerprints are not semantic truth or independence proofs. No exactly-once "
        "execution, statistical intelligence improvement or general performance advantage "
        "is established. Byte equality is not fully reproducible source builds.\n"
    )
    if args.version == "0.2.3":
        summary = json.loads(
            Path("experiments/ollama/results/v0.2.3/summary.json").read_text("utf-8")
        )
        frozen = json.loads(
            Path("experiments/ollama/results/freeze-v0.2.3.json").read_text("utf-8")
        )
        notes = (
            "Evidence-gap router 0.2.3 corrects the installed continuation import example "
            "and adds an optional source-level local Ollama experiment. The audited router "
            "keeps its default no_progress behavior and its Pydantic/standard-library core. "
            "The SDK and ordinary CLI do not load models or make network requests.\n\n"
            f"[Fresh audit]({tree}/docs/audit-022.md), "
            f"[experiment commands]({source_tree}/experiments/ollama), "
            f"[English results]({tree}/docs/ollama-experiment.md), "
            f"[Japanese results]({tree}/docs/ollama-experiment.ja.md). "
            "Exact local model identities, durable attempts, known/unknown usage, "
            "independent witness checks, failures and resource limits are retained. "
            "A/B share the same public runner and complete candidate pool; C is a "
            "pooled-information reference with different information arrival.\n\n"
            f"Confirmation profile: {frozen['selected_parent_count']} task parents per model; "
            f"recorded rows including pilot and unexecuted keys: {summary['rows']}. "
            "Read the attached summary for actual assessed/paired counts and cost subsets. "
            "Same-model review calls are not statistically independent agents, and these "
            "small artificial tasks do not establish general performance superiority. "
            "Model weights and user credentials are not bundled. Earlier tags, "
            "benchmark records and public assets remain unchanged.\n\n"
            "The same release wheel passed installed runtime/CLI/fixture regressions "
            "and portable fake-HTTP experiment contracts on all six native profiles. "
            "Live Ollama inference is never run by CI.\n\n"
            "| OS | Actual architecture | Python | Pydantic / core | Installed checks |\n"
            "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
            f"New model-free smoke outcome SHA256: {next(iter(benchmark_hashes), 'not_run')}\n\n"
            f"Commit: {args.commit}\n\n"
            f"Manual validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.manual_run}\n\n"
            f"Release validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.release_run}\n\n"
            "Actual official PyPI wheel/sdist bytes matched the build artifacts. "
            "A cache-free official-index installation passed SDK/CLI/examples/migration "
            "and model-free benchmark smoke. SHA256SUMS covers the distribution files; "
            "the experiment has a separate raw-data manifest and checksum.\n"
        )
    if args.version == "0.2.4":
        summary = json.loads(
            Path("experiments/ollama/results/v0.2.4/summary.json").read_text("utf-8")
        )
        frozen = json.loads(
            Path("experiments/ollama/results/freeze-v0.2.4-r2.json").read_text("utf-8")
        )
        results = []
        for model in summary["outcomes"]:
            for arm in ("A", "B", "C"):
                value = summary["outcomes"][model][arm]
                answerable = value["answerable"]
                results.append(
                    f"| {model} | {arm} | {answerable['verified_supported_completion']} / "
                    f"{answerable['assessed']} / {answerable['planned']} | "
                    f"{value['false_acceptance']} | {value['unexecuted']} |"
                )
        notes = (
            "Evidence-gap router 0.2.4 retains the SDK acceptance and authority contracts, "
            "adds a finite long-request owned Ollama controller, durable receipt recovery, "
            "paid common formatting repair, independent grounding scores "
            "and fresh stop-policy measurements. "
            "The READMEs and complete ordinary-wheel examples "
            "now lead to a small documentation index.\n\n"
            f"[Getting started]({tree}/docs/getting-started.md), "
            f"[Ollama guide]({tree}/docs/ollama-guide.md), "
            f"[audit]({tree}/docs/audit-024.md), "
            f"[English results]({tree}/docs/ollama-experiment-v0.2.4.md), "
            f"[Japanese summary]({tree}/docs/ollama-experiment-v0.2.4.ja.md).\n\n"
            f"New frozen confirmation: {frozen['selected_parent_count']} parents per model. "
            "A and B share the public runner, pool, permissions, views, "
            "callback budgets and stops; "
            "C is a pooled-information reference. Exact model identities "
            "and every development/failed invocation remain in the experiment assets. "
            "Unknown usage is not zero or model incapacity.\n\n"
            "| Model | Arm | Answerable verified / assessed / planned | "
            "False acceptance | Unexecuted |\n"
            "| --- | --- | --- | --- | --- |\n" + "\n".join(results) + "\n\n"
            "Review syntax, grounded answers, review acceptance, "
            "unknown-world abstention and false PASS are separate metrics. "
            "The summary retains parent-paired intervals, unresolved bounds, all-trial costs, "
            "failed/successful costs, both-success subset costs and fresh strict/bounded pairs. "
            "Small authored tasks do not establish general superiority, model ranking "
            "or independent-agent benefits. Earlier tags and public bytes are unchanged.\n\n"
            "The same universal wheel passed installed SDK/CLI, Unicode-file, "
            "continuation, migration, "
            "documentation examples and portable fake-HTTP contracts on all six native profiles. "
            "Live model inference was local and separate from CI.\n\n"
            "| OS | Actual architecture | Python | Pydantic / core | Installed checks |\n"
            "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
            f"Portable benchmark outcome SHA256: {next(iter(benchmark_hashes), 'not_run')}\n\n"
            f"Commit: {args.commit}\n\n"
            f"Manual validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.manual_run}\n\n"
            f"Release validation: https://github.com/kadubon/evidence-gap-router/actions/runs/{args.release_run}\n\n"
            "Actual official PyPI wheel/sdist bytes matched the build artifacts. "
            "A cache-free official-index install passed SDK/CLI/migration smoke. "
            "Raw export creation, upload, public download and "
            "byte-equal reanalysis are separately recorded in publication verification assets. "
            "Host input/checker trust, effects and process ownership remain host responsibilities; "
            "the SDK does not supply exactly-once external execution "
            "or semantic truth guarantees.\n"
        )
    if args.version == "0.3.0":
        notes = (
            "Evidence-gap router 0.3.0: explicit finite completion contracts.\n\n"
            "Individual PASS, current checker authority, material coverage and goal completion "
            "are separate. Host-declared contracts bind target, scope/catalogue revision, "
            "required inputs and qualified check kinds. Issued profiles and current permissions "
            "must agree; advisory checks cannot silently become completion authority. "
            "Exact required-material helpers inherit goal priority.\n\n"
            "Schema 3; explicit schema-1/2 imports preserve original history, bases, expenses "
            "and uncertainty without inventing completion authority. Three executable local-file "
            "examples cover partial PASS, one-callback pooling and invalidation/save/reload.\n\n"
            "New LLM requests: 0. New efficacy/performance experiments: 0. "
            "v0.3.0 empirical efficacy is unmeasured. The release manifest proves shipping "
            "identity, not efficacy. Historical experiments belong to their original tags.\n\n"
            "The same wheel passed installed SDK/CLI/migration/examples and native dependency "
            "imports on every required profile.\n\n"
            "| OS | Architecture | Python | Pydantic / core | Installed checks |\n"
            "| --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
            f"Commit: {args.commit}\n\n"
            "[Manual CI](https://github.com/kadubon/evidence-gap-router/actions/runs/"
            f"{args.manual_run}) · "
            "[Release CI](https://github.com/kadubon/evidence-gap-router/actions/runs/"
            f"{args.release_run})\n\n"
            "Official PyPI wheel/sdist bytes matched the fixed build artifacts and a cache-free "
            "official-index installation passed smoke checks. Source/Release/PyPI/public "
            "download verification are separately recorded. Limited callback views are not "
            "a Python sandbox; host trust and execution measurement remain host duties.\n"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
