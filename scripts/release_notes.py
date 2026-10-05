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
        rows.append(
            f"| {system} | {architecture} | {report['python']} | "
            f"{report['pydantic_version']} / {report['pydantic_core_version']} | passed |"
        )
    notes = (
        f"Evidence-gap router {args.version}: dependency-bound verification and a bounded SDK.\n\n"
        "Checks now bind the target, acceptance contract, exact dependency material, checker "
        "revision and purpose. Registered handler permissions separate acquisition from "
        "check/contradiction resolution. Target-specific gaps avoid unnecessary rechecks and "
        "known-origin repetition. Includes public step/run, limited callback views, strict "
        "local-file check-data and a separate multi-source investigation example.\n\n"
        "**Compatibility change:** schema 2 and the new callback/basis/registration API. "
        "The explicit schema-1 migration preserves legacy history without inventing missing "
        "check bases; old PASS remains unassessed. See docs/migration.md.\n\n"
        "The same universal project wheel passed native installed core/runner/CLI "
        "regressions, fixtures, migration, Unicode-file and snapshot smoke below. "
        "Native Pydantic core wheels were installed and imported; reports are attached.\n\n"
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
