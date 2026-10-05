"""Clean native wheel install, regression tests and smoke without source imports."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

SOURCE_ONLY_TESTS = {
    "test_release_guard.py",
    "test_package_audit.py",
    "test_publication_verification.py",
    "test_benchmarks.py",
    "test_benchmark_erratum.py",
    "test_benchmark_loop_022.py",
    "test_audit_022.py",
    "test_controller_022.py",
    "test_helper_scaling_022.py",
    "test_worker_limits.py",
    "test_summarize_022.py",
}
V022_INSTALLED_TESTS = {
    "test_v022_helpers.py",
    "test_v022_resolution.py",
    "test_v022_selector.py",
}


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
        # These inspect repository orchestration/archives or experiment code.
        # Runtime regressions still run against the installed release wheel;
        # the portable benchmark smoke is exercised separately below.
        selected = [
            p for p in sorted((root / "tests").glob("test_*.py")) if p.name not in SOURCE_ONLY_TESTS
        ]
        if not selected:
            raise ValueError("No installed regression tests selected")
        if args.version == "0.2.2" and not V022_INSTALLED_TESTS.issubset(
            {test.name for test in selected}
        ):
            raise ValueError("All v0.2.2 runtime regressions must run against the installed wheel")
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
        benchmark_dir = clean / "benchmarks"
        benchmark_dir.mkdir()
        for source in sorted((root / "benchmarks").glob("*.py")):
            shutil.copyfile(source, benchmark_dir / source.name)
        shutil.copyfile(root / "benchmarks/protocol.json", benchmark_dir / "protocol.json")
        outcome = subprocess.run(
            [str(python), "-I", str(benchmark_dir / "smoke.py")],
            cwd=clean,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        benchmark = json.loads(outcome.stdout)
        if benchmark.get("benchmark_smoke") != "passed" or benchmark.get("trials", 0) < 1:
            raise ValueError("Installed benchmark smoke did not pass")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report.update(
            {
                "installed_regression_tests": [test.name for test in selected],
                "source_only_regression_tests": sorted(
                    name for name in SOURCE_ONLY_TESTS if (root / "tests" / name).is_file()
                ),
                "pytest_exit_code": 0,
                "installed_smoke": "passed",
                "benchmark": benchmark,
                "dependency_constraints": "uv.lock runtime dependencies; locked pytest",
            }
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
