"""Archive the retained local experiment without weights, logs, or absolute paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Never replace an existing raw archive")
    root = Path(__file__).resolve().parents[1]
    sources: dict[str, Path] = {}
    for path in sorted(args.raw.rglob("*")):
        if path.is_file():
            if path.is_symlink() or path.suffix in {".log", ".lock", ".tmp"}:
                continue
            sources["raw/" + path.relative_to(args.raw).as_posix()] = path
    for path in sorted((root / "experiments/ollama").glob("*.py")):
        sources["harness/" + path.name] = path
    sources["harness/protocol.json"] = root / "experiments/ollama/protocol.json"
    sources["freeze-v0.2.3.json"] = args.freeze
    for path in sorted(args.summary.glob("*")):
        if path.is_file():
            sources["analysis/" + path.name] = path
    manifest = {
        name: {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        for name, path in sources.items()
    }
    if sum(item["bytes"] for item in manifest.values()) > 512 * 1024**2:
        raise ValueError("Raw archive source envelope exceeds 512 MiB")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sources.items():
            archive.writestr(name, path.read_bytes())
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    with zipfile.ZipFile(args.output) as archive:
        if archive.testzip() is not None:
            raise ValueError("Archive integrity failed")
        for name, item in manifest.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != item["sha256"]:
                raise ValueError("Archive hash verification failed")
    print(
        json.dumps(
            {
                "filename": args.output.name,
                "bytes": args.output.stat().st_size,
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "verified_entries": len(manifest),
            }
        )
    )


if __name__ == "__main__":
    main()
