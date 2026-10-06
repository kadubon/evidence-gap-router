"""Shipping identity from a clean exact commit; no experiment or self/future hash."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

from package_audit import audit, package_fingerprint, verify_record


def create(dist: Path, commit: str) -> dict:
    if subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() != commit:
        raise ValueError("manifest requires the current exact commit")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("manifest requires a clean source checkout")
    version = audit(dist)
    archive_bytes = subprocess.check_output(["git", "archive", "--format=zip", commit])
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source:
        source_files = {n: source.read(n) for n in source.namelist() if not n.endswith("/")}
    wheels = list(dist.glob("*.whl"))
    with zipfile.ZipFile(wheels[0]) as wheel:
        verify_record(wheel)
        package = {
            n: wheel.read(n) for n in wheel.namelist() if n.startswith("evidence_gap_router/")
        }
        expected = {
            n.removeprefix("src/"): data
            for n, data in source_files.items()
            if n.startswith("src/evidence_gap_router/")
        }
        if package != expected:
            raise ValueError("wheel package differs from exact committed source bytes")
        license_names = [n for n in wheel.namelist() if n.endswith("/LICENSE")]
        if len(license_names) != 1 or wheel.read(license_names[0]) != source_files["LICENSE"]:
            raise ValueError("wheel license differs from the exact committed full license")
    return {
        "manifest_type": "release-shipping-identity",
        "schema_version": "1",
        "version": version,
        "commit": commit,
        "git_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip(),
        "source_archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        "source_files": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(source_files.items())},
        "package_files": {n: hashlib.sha256(b).hexdigest() for n, b in sorted(package.items())},
        "package_fingerprint": package_fingerprint(wheels[0]),
        "distributions": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(dist.iterdir())
        },
        "license_sha256": hashlib.sha256(source_files["LICENSE"]).hexdigest(),
        "new_llm_requests": 0,
        "new_efficacy_or_performance_experiments": 0,
        "efficacy": "unmeasured",
        "historical_experiments": (
            "Use original tags/wheels/harnesses; their freezes do not bind this release."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = create(args.dist, args.commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"version": value["version"], "commit": args.commit, "manifest": str(args.output)}
        )
    )


if __name__ == "__main__":
    main()
