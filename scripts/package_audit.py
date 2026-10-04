"""Check release archives without importing project code or extracting archives."""

from __future__ import annotations

import argparse
import ast
import hashlib
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path


def source_version() -> str:
    tree = ast.parse(Path("src/evidence_gap_router/_version.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("No literal authoritative __version__ found")


def audit(dist: Path) -> str:
    version = source_version()
    files = sorted(dist.iterdir())
    expected = {
        f"evidence_gap_router-{version}-py3-none-any.whl",
        f"evidence_gap_router-{version}.tar.gz",
    }
    if {path.name for path in files} != expected or not all(path.is_file() for path in files):
        raise ValueError("Distribution directory must contain exactly the wheel and sdist")
    for path in files:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
                metadata = archive.read(metadata_names[0]) if len(metadata_names) == 1 else b""
        else:
            with tarfile.open(path, "r:gz") as source:
                names = source.getnames()
                metadata_names = [name for name in names if name.endswith("/PKG-INFO")]
                member = source.extractfile(metadata_names[0]) if len(metadata_names) == 1 else None
                metadata = member.read() if member is not None else b""
        message = BytesParser().parsebytes(metadata)
        if message["Name"] != "evidence-gap-router" or message["Version"] != version:
            raise ValueError(f"Metadata mismatch: {path.name}")
        if message["Requires-Python"] != ">=3.12" or message["License-Expression"] != "Apache-2.0":
            raise ValueError(f"Python/license metadata mismatch: {path.name}")
        if not any(name.endswith("/py.typed") for name in names):
            raise ValueError(f"Missing py.typed: {path.name}")
        if not any(name.endswith("/LICENSE") for name in names):
            raise ValueError(f"Missing license: {path.name}")
        if not any("/data/" in name and name.endswith(".csv") for name in names) or not any(
            "/data/" in name and name.endswith(".json") for name in names
        ):
            raise ValueError(f"Missing packaged demo data: {path.name}")
        if any("/.venv/" in name or "/__pycache__/" in name or "/.git/" in name for name in names):
            raise ValueError(f"Unexpected development content: {path.name}")
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    print(f"version={audit(args.dist)}")
