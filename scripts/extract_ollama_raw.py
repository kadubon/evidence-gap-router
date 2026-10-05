"""Extract a hash-pinned raw ZIP into a new bounded directory without links."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath

MAX_BYTES = 4 * 1024**3
RESERVED = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)


def extract(archive_path: Path, destination: Path, expected_sha256: str) -> dict[str, int | str]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Supply the published lowercase SHA256")
    with archive_path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != expected_sha256:
        raise ValueError("Archive SHA256 differs")
    for path in (destination.absolute(), *destination.absolute().parents):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Extraction path cannot traverse links")
    root = destination.resolve()
    if root.exists():
        raise ValueError("Use a new extraction directory")
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 100_000 or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("Archive exceeds the finite extraction envelope")
        seen: set[str] = set()
        for item in entries:
            name = item.orig_filename
            relative = PurePosixPath(name)
            kind = stat.S_IFMT(item.external_attr >> 16)
            parts = name.rstrip("/").split("/")
            if (
                relative.is_absolute()
                or any(part in ("", ".", "..") for part in parts)
                or "\\" in name
                or "\x00" in name
                or any(
                    ":" in part or part.endswith((".", " ")) or RESERVED.match(part)
                    for part in parts
                )
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or name.casefold() in seen
                or not (root / relative).resolve().is_relative_to(root)
            ):
                raise ValueError("Unsafe or duplicate archive member")
            seen.add(name.casefold())
        root.mkdir(parents=True, exist_ok=False)
        written = 0
        for item in entries:
            target = root / item.filename
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as source, target.open("xb") as output:
                while chunk := source.read(1024 * 1024):
                    written += len(chunk)
                    if written > MAX_BYTES:
                        raise ValueError("Expanded bytes exceed the extraction envelope")
                    output.write(chunk)
    return {"archive_sha256": digest, "members": len(entries), "expanded_bytes": written}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(extract(args.archive, args.destination, args.sha256)))


if __name__ == "__main__":
    main()
