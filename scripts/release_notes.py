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
            or report.get("benchmark", {}).get("benchmark_smoke") != "passed"
            or report.get("benchmark", {}).get("trials", 0) < 1
        ):
            raise ValueError(f"Profile is not a passing native test of this artifact: {name}")
        benchmark_hashes.add(report["benchmark"]["outcome_sha256"])
        rows.append(
            f"| {system} | {architecture} | {report['python']} | "
            f"{report['pydantic_version']} / {report['pydantic_core_version']} | passed |"
        )
    if len(benchmark_hashes) != 1:
        raise ValueError("Native benchmark outcomes differ across required profiles")
    tree = f"https://github.com/kadubon/evidence-gap-router/blob/{args.commit}"
    source_tree = f"https://github.com/kadubon/evidence-gap-router/tree/{args.commit}"
    notes = (
        f"Evidence-gap router {args.version}: correctness, continuation and measured routing.\n\n"
        "Preserves issued receipts while allowing explicit host invalidation; supports current "
        "re-resolution; rejects a same-digest alias as grounds for another target's FAIL. "
        "Known prohibited self-checks are excluded before execution. Narrow declared helper "
        "dependencies and exact-ID stage progress can continue. Decimal file thresholds remain "
        "exact, bounded snapshots round-trip, and per-evaluation dependency work avoids "
        "exponential repeated checking.\n\n"
        "**Compatibility:** legitimate schema-2 history remains readable. New invalidation "
        "fields are rejected by old readers; old incorrectly bound resolution records are "
        "retained but cannot grant current acceptance. Schema-1 migration preserves legacy "
        "history without inventing missing bases.\n\n"
        f"Model-free benchmark: [protocol, harness and recorded freeze]({source_tree}/benchmarks), "
        f"[English report]({tree}/docs/benchmark.md), "
        f"[Japanese summary]({tree}/docs/benchmark.ja.md). "
        "The frozen candidate's package bytes match this release; later source changes were "
        "documentation/results only. Large raw trial/scaling data and checksums are linked "
        "from those reports and attached as separate benchmark assets. Baselines, failures, "
        "timeouts, no-advantage cases and selected-subset cost limits remain explicit.\n\n"
        "The same universal project wheel passed native installed core/runner/CLI "
        "regressions, fixtures, migration, Unicode-file, continuation and benchmark smoke below. "
        "Native Pydantic core wheels were installed and imported; reports are attached.\n\n"
        f"Portable benchmark outcome SHA256: {next(iter(benchmark_hashes))}\n\n"
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
