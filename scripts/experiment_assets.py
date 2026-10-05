"""Copy version-matched frozen evidence to distinct release asset names."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--version", choices=("0.2.3", "0.2.4"), default="0.2.4")
    args = parser.parse_args()
    paths = {
        "ollama-protocol-v0.2.3.json": Path("experiments/ollama/protocol.json"),
        "ollama-freeze-v0.2.3.json": Path("experiments/ollama/results/freeze-v0.2.3.json"),
        "ollama-summary-v0.2.3.json": Path("experiments/ollama/results/v0.2.3/summary.json"),
        "ollama-provenance-v0.2.3.json": Path(
            "experiments/ollama/results/v0.2.3/artifact-provenance.json"
        ),
        "ollama-report-v0.2.3.md": Path("docs/ollama-experiment.md"),
        "ollama-report-v0.2.3.ja.md": Path("docs/ollama-experiment.ja.md"),
        "audit-v0.2.2-for-v0.2.3.md": Path("docs/audit-022.md"),
    }
    if args.version == "0.2.4":
        paths = {
            "ollama-protocol-v0.2.4.json": Path("experiments/ollama/protocol-v0.2.4-r2.json"),
            "ollama-freeze-v0.2.4.json": Path("experiments/ollama/results/freeze-v0.2.4-r2.json"),
            "ollama-summary-v0.2.4.json": Path("experiments/ollama/results/v0.2.4/summary.json"),
            "ollama-provenance-v0.2.4.json": Path(
                "experiments/ollama/results/v0.2.4/artifact-provenance.json"
            ),
            "ollama-calibration-v0.2.4.json": Path(
                "experiments/ollama/results/v0.2.4/calibration-summary.json"
            ),
            "ollama-report-v0.2.4.md": Path("docs/ollama-experiment-v0.2.4.md"),
            "ollama-report-v0.2.4.ja.md": Path("docs/ollama-experiment-v0.2.4.ja.md"),
            "audit-v0.2.4.md": Path("docs/audit-024.md"),
        }
    args.destination.mkdir(parents=True, exist_ok=False)
    hashes = []
    for name, path in paths.items():
        if not path.is_file():
            raise ValueError(f"Missing experiment evidence: {path}")
        shutil.copyfile(path, args.destination / name)
        hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}\n")
    (args.destination / "EXPERIMENT_SHA256SUMS").write_text("".join(hashes), encoding="utf-8")


if __name__ == "__main__":
    main()
