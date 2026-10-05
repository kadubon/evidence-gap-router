"""Clean native wheel install, regression tests and smoke without source imports."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path


def call(arguments: list[str], *, cwd: Path) -> None:
    subprocess.run(arguments, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--python", default="3.12")
    parser.add_argument("--platform", required=True, choices=("Linux", "Windows", "Darwin"))
    parser.add_argument("--architecture", required=True, choices=("x86_64", "arm64"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("Provide the existing release wheel")
    report_path = args.report.resolve()
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    pytest_versions = {p["version"] for p in lock["package"] if p["name"] == "pytest"}
    if len(pytest_versions) != 1:
        raise ValueError("Native pytest version must be unambiguous in uv.lock")
    pytest_requirement = f"pytest=={next(iter(pytest_versions))}"
    with tempfile.TemporaryDirectory(prefix="egr-native-") as temporary:
        clean = Path(temporary)
        if clean.is_relative_to(root):
            raise RuntimeError("Native test directory must be outside repository")
        environment = clean / "venv"
        call(["uv", "venv", "--seed", "--python", args.python, str(environment)], cwd=clean)
        python = environment / (
            "Scripts/python.exe" if args.platform == "Windows" else "bin/python"
        )
        constraints = clean / "runtime-constraints.txt"
        call(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--output-file",
                str(constraints),
            ],
            cwd=root,
        )
        call(
            [
                str(python),
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-cache-dir",
                "--only-binary=:all:",
                "--constraint",
                str(constraints),
                str(wheel),
                pytest_requirement,
            ],
            cwd=clean,
        )
        call(
            [
                str(python),
                "-I",
                str(root / "scripts/native_probe.py"),
                "--version",
                args.version,
                "--platform",
                args.platform,
                "--architecture",
                args.architecture,
                "--wheel",
                str(wheel),
                "--source-root",
                str(root / "src"),
                "--report",
                str(report_path),
            ],
            cwd=clean,
        )
        tests = clean / "tests"
        tests.mkdir()
        # Release guards test source-side GitHub orchestration, not installed core behavior.
        selected = [
            p
            for p in sorted((root / "tests").glob("test_*.py"))
            if p.name != "test_release_guard.py"
        ]
        if not selected:
            raise ValueError("No installed regression tests selected")
        for test in selected:
            shutil.copyfile(test, tests / test.name)
        for fixture in (root / "tests").iterdir():
            if fixture.is_dir() and fixture.name not in {"__pycache__", ".pytest_cache"}:
                shutil.copytree(fixture, tests / fixture.name)
        conftest = root / "tests/conftest.py"
        if conftest.is_file():
            shutil.copyfile(conftest, tests / "conftest.py")
        call([str(python), "-I", "-m", "pytest", str(tests), "-q"], cwd=clean)
        call(
            [str(python), "-I", str(root / "scripts/smoke.py"), "--expected-version", args.version],
            cwd=clean,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report.update(
            {
                "installed_regression_tests": [test.name for test in selected],
                "pytest_exit_code": 0,
                "installed_smoke": "passed",
                "dependency_constraints": "uv.lock runtime dependencies; locked pytest",
            }
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
