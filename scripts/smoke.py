"""Verify an installed distribution; run outside the source checkout."""

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

from evidence_gap_router.demo import run_demo

import evidence_gap_router as egr
from evidence_gap_router.models import State


def main() -> None:
    package_path = Path(egr.__file__).resolve()
    source = Path(__file__).resolve().parents[1] / "src"
    assert not package_path.is_relative_to(source), package_path
    assert egr.__version__ == importlib.metadata.version("evidence-gap-router") == "0.1.0"
    command = Path(sys.executable).with_name("egr.exe" if sys.platform == "win32" else "egr")
    version = subprocess.run(
        [str(command), "--version"], capture_output=True, text=True, check=True
    )
    assert "0.1.0" in version.stdout
    expected = {
        "valid": "satisfied",
        "invalid": "escalation_required",
        "budget": "budget_exhausted",
    }
    for case, stop in expected.items():
        report = run_demo(case=case)
        assert report["artificial_data"] is True
        assert report["decision"]["stop_reason"] == stop, report
        state = State.model_validate_json(json.dumps(report["state"]))
        assert State.model_validate_json(state.model_dump_json()) == state
        completed = subprocess.run(
            [str(command), "demo", "--case", case, "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == (0 if case == "valid" else 2), completed
        assert not completed.stderr, completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["decision"]["stop_reason"] == stop
    print(json.dumps({"version": egr.__version__, "package": str(package_path), "smoke": "passed"}))


if __name__ == "__main__":
    main()
