"""Verify a safely extracted v0.2.4 raw export and reanalyze without inference."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path, PurePosixPath


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.extracted.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(root):
        raise ValueError("Use a new analysis directory outside the extracted export")
    manifest = json.loads((root / "MANIFEST.json").read_text("utf-8"))
    for name, expected in manifest.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError("Manifest path leaves the extracted export")
        path = root / name
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink() or ancestor.is_junction():
                raise ValueError("Extracted files must not traverse links")
            if ancestor == root:
                break
        content = path.read_bytes()
        if (
            len(content) != expected["bytes"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise ValueError(f"Manifest bytes differ: {name}")
    frozen = json.loads((root / "freeze-v0.2.4.json").read_text("utf-8"))
    harness = root / "harness"
    for name, expected in frozen["harness_files"].items():
        if hashlib.sha256((harness / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Measured harness identity differs")
    protocol_path = harness / frozen["protocol_file"]
    if hashlib.sha256(protocol_path.read_bytes()).hexdigest() != frozen["manifest_sha256"]:
        raise ValueError("Measured protocol identity differs")
    protocol = json.loads(protocol_path.read_text("utf-8"))
    if protocol["protocol_id"] != frozen["protocol_id"] or protocol["package_version"] != "0.2.4":
        raise ValueError("Protocol/version identity differs")
    spec = importlib.util.spec_from_file_location(
        "retained_ollama", harness / "__init__.py", submodule_search_locations=[str(harness)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    analyze = importlib.import_module("retained_ollama.analysis").analyze
    analyze(root / "raw", output, protocol, frozen=frozen)
    names = ("summary.json", "scored-trials.json", "scored-trials.csv", "failure-analysis.json")
    for name in names:
        if (output / name).read_bytes() != (root / "analysis" / name).read_bytes():
            raise ValueError(f"Reanalysis differs from retained output: {name}")
    print(
        json.dumps(
            {
                "manifest_entries_verified": len(manifest),
                "reanalysis_files_byte_equal": list(names),
                "model_requests": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
