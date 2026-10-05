"""Check release archives without importing project code or extracting archives."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

REQUIRED_MODULES = (
    "__init__.py",
    "_version.py",
    "models.py",
    "router.py",
    "jsonio.py",
    "_legacy.py",
    "runner.py",
    "cli.py",
    "demo.py",
    "cause_demo.py",
    "file_checks.py",
    "data_quality.py",
    "sdk_example.py",
    "comparison.py",
)

REQUIRED_DATA = (
    "orders_valid.csv",
    "orders_invalid.csv",
    "data_dictionary.json",
    "cause/reading.json",
    "cause/reading_invalid.json",
    "cause/reading_unknown_origin.json",
    "cause/specification.json",
    "cause/specification_conflict.json",
    "cause/exceptions.json",
    "cause/exceptions_unknown.json",
)


def verify_record(archive: zipfile.ZipFile) -> None:
    """Check the actual wheel manifest, including every packaged file's bytes."""
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError("Duplicate wheel entries")
    record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
    if len(record_names) != 1:
        raise ValueError("Wheel needs exactly one RECORD")
    record_name = record_names[0]
    rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
    if any(len(row) != 3 for row in rows):
        raise ValueError("Invalid wheel RECORD row")
    recorded = {row[0]: row[1:] for row in rows}
    if len(recorded) != len(rows) or set(recorded) != set(names):
        raise ValueError("Wheel RECORD must enumerate every file exactly once")
    for name in names:
        digest, size = recorded[name]
        if name == record_name:
            if digest or size:
                raise ValueError("Wheel RECORD cannot hash itself")
            continue
        content = archive.read(name)
        expected = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
        if digest != "sha256=" + expected.decode("ascii") or size != str(len(content)):
            raise ValueError(f"Wheel RECORD byte mismatch: {name}")


def package_fingerprint(wheel: Path) -> str:
    """Fingerprint package bytes independently of later documentation metadata."""
    with zipfile.ZipFile(wheel) as archive:
        verify_record(archive)
        mapping = {
            name.removeprefix("evidence_gap_router/"): hashlib.sha256(
                archive.read(name)
            ).hexdigest()
            for name in archive.namelist()
            if name.startswith("evidence_gap_router/")
        }
    if not mapping:
        raise ValueError("No package files in wheel")
    canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_benchmark_package(wheel: Path, freeze: Path) -> None:
    manifest = json.loads(freeze.read_text(encoding="utf-8"))
    if package_fingerprint(wheel) != manifest["candidate_package_sha256"]:
        raise ValueError("Release package bytes differ from the measured frozen candidate")
    directory = freeze.resolve().parents[1]
    actual = hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()
    if actual != manifest["manifest_sha256"]:
        raise ValueError("Benchmark protocol differs from the measured freeze")
    content = b"".join(
        path.name.encode() + path.read_bytes() for path in sorted(directory.glob("*.py"))
    )
    if not content or hashlib.sha256(content).hexdigest() != manifest["harness_sha256"]:
        raise ValueError("Benchmark harness differs from the measured freeze")


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
    packages = {}
    for path in files:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                verify_record(archive)
                names = archive.namelist()
                packages["wheel"] = {
                    name.removeprefix("evidence_gap_router/"): archive.read(name)
                    for name in names
                    if name.startswith("evidence_gap_router/")
                }
                metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
                metadata = archive.read(metadata_names[0]) if len(metadata_names) == 1 else b""
                license_names = [name for name in names if name.endswith("/LICENSE")]
                license_bytes = archive.read(license_names[0]) if len(license_names) == 1 else b""
        else:
            with tarfile.open(path, "r:gz") as source:
                names = source.getnames()
                package = {}
                prefix = f"evidence_gap_router-{version}/src/evidence_gap_router/"
                for item in source.getmembers():
                    if item.name.startswith(prefix) and item.isfile():
                        member = source.extractfile(item)
                        if member is None:
                            raise ValueError("Unreadable sdist package file")
                        package[item.name.removeprefix(prefix)] = member.read()
                packages["sdist"] = package
                metadata_names = [name for name in names if name.endswith("/PKG-INFO")]
                member = source.extractfile(metadata_names[0]) if len(metadata_names) == 1 else None
                metadata = member.read() if member is not None else b""
                license_names = [name for name in names if name.endswith("/LICENSE")]
                license_member = (
                    source.extractfile(license_names[0]) if len(license_names) == 1 else None
                )
                license_bytes = license_member.read() if license_member is not None else b""
        message = BytesParser().parsebytes(metadata)
        if message["Name"] != "evidence-gap-router" or message["Version"] != version:
            raise ValueError(f"Metadata mismatch: {path.name}")
        if message["Requires-Python"] != ">=3.12" or message["License-Expression"] != "Apache-2.0":
            raise ValueError(f"Python/license metadata mismatch: {path.name}")
        if not any(name.endswith("/py.typed") for name in names):
            raise ValueError(f"Missing py.typed: {path.name}")
        if license_bytes != Path("LICENSE").read_bytes() or len(license_bytes) < 10_000:
            raise ValueError(f"Missing or changed full Apache license: {path.name}")
        if not all(
            any(f"/{name}".endswith(f"/evidence_gap_router/{module}") for name in names)
            for module in REQUIRED_MODULES
        ):
            raise ValueError(f"Missing installed SDK/runner/migration/example module: {path.name}")
        if not all(
            any(f"/{name}".endswith(f"/evidence_gap_router/data/{fixture}") for name in names)
            for fixture in REQUIRED_DATA
        ):
            raise ValueError(f"Missing packaged data-quality/cause fixture: {path.name}")
        if not any("/data/" in name and name.endswith(".csv") for name in names) or not any(
            "/data/" in name and name.endswith(".json") for name in names
        ):
            raise ValueError(f"Missing packaged demo data: {path.name}")
        if any("/.venv/" in name or "/__pycache__/" in name or "/.git/" in name for name in names):
            raise ValueError(f"Unexpected development content: {path.name}")
        print(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    if packages.get("wheel") != packages.get("sdist") or not packages.get("wheel"):
        raise ValueError("Wheel and sdist package files differ")
    print(f"RECORD verified; wheel/sdist share {len(packages['wheel'])} identical package files")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--benchmark-freeze", type=Path)
    parser.add_argument("--rebuilt-wheel", type=Path)
    args = parser.parse_args()
    print(f"version={audit(args.dist)}")
    if args.benchmark_freeze is not None:
        verify_benchmark_package(next(args.dist.glob("*.whl")), args.benchmark_freeze)
        print("Measured candidate package bytes match release package bytes")
    if args.rebuilt_wheel is not None:
        if package_fingerprint(next(args.dist.glob("*.whl"))) != package_fingerprint(
            args.rebuilt_wheel
        ):
            raise ValueError("Sdist rebuild package differs from release wheel")
        print("Sdist rebuild package bytes match release package bytes")
