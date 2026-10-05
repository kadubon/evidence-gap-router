"""Record a native installed-package profile; import paths must be outside source."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True, choices=("Linux", "Windows", "Darwin"))
    parser.add_argument("--architecture", required=True, choices=("x86_64", "arm64"))
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    import pydantic
    import pydantic_core
    import pydantic_core._pydantic_core as native_core

    import evidence_gap_router

    machine = platform.machine()
    normalized = {"AMD64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    if platform.system() != args.platform or normalized != args.architecture:
        raise RuntimeError(f"Wrong native profile: {platform.system()}/{machine}")
    translated = False
    if args.platform == "Darwin":
        result = subprocess.run(
            ["sysctl", "-in", "sysctl.proc_translated"], capture_output=True, text=True, check=False
        )
        translated = result.returncode == 0 and result.stdout.strip() == "1"
        if translated:
            raise RuntimeError("Rosetta translation is not a native architecture test")
    package_path = Path(evidence_gap_router.__file__).resolve()
    source = args.source_root.resolve()
    if package_path.is_relative_to(source) or not package_path.is_relative_to(
        Path(sys.prefix).resolve()
    ):
        raise RuntimeError(f"Package imported outside clean environment: {package_path}")
    if (
        evidence_gap_router.__version__ != args.version
        or importlib.metadata.version("evidence-gap-router") != args.version
    ):
        raise RuntimeError("Installed package version mismatch")
    core_distribution = importlib.metadata.distribution("pydantic_core")
    core_wheel = core_distribution.read_text("WHEEL")
    if core_wheel is None:
        raise RuntimeError("Installed pydantic_core wheel metadata is missing")
    core_tags = [line[5:] for line in core_wheel.splitlines() if line.startswith("Tag: ")]
    if not core_tags or all(tag.endswith("-any") for tag in core_tags):
        raise RuntimeError("Expected an actual native pydantic_core wheel")
    project_wheel = importlib.metadata.distribution("evidence-gap-router").read_text("WHEEL")
    if project_wheel is None:
        raise RuntimeError("Installed project wheel metadata is missing")
    report = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "machine": machine,
        "architecture": normalized,
        "rosetta_translated": translated,
        "package_version": evidence_gap_router.__version__,
        "package_import": str(package_path),
        "python_executable": sys.executable,
        "pydantic_version": pydantic.__version__,
        "pydantic_core_version": pydantic_core.__version__,
        "pydantic_core_import": str(Path(native_core.__file__).resolve()),
        "pydantic_core_wheel_tags": core_tags,
        "wheel_filename": args.wheel.name,
        "wheel_sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
        "package_wheel_tags": [
            line[5:] for line in project_wheel.splitlines() if line.startswith("Tag: ")
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
