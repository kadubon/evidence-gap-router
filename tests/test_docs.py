"""Executable documentation retains the selected outside-checkout environment."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt", reason="POSIX venv interpreter symlink contract")
def test_documentation_examples_keep_venv_interpreter_symlink(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    (root / "scripts").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "experiments/ollama").mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).resolve().parents[1] / "scripts/check_docs.py",
        root / "scripts/check_docs.py",
    )
    environment = tmp_path / "ordinary environment"
    venv.EnvBuilder(symlinks=True, with_pip=False).create(environment)
    python = environment / "bin/python"
    assert python.is_symlink()
    prefix = str(environment.resolve())
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        f"assert str(Path(sys.prefix).resolve()) == {prefix!r}\n"
        "print('check-answer')\nprint('PASS')\nprint('satisfied')\nprint('[]')"
    )
    for name in ("README.md", "README.ja.md", "docs/getting-started.md"):
        (root / name).write_text(
            f"pip install evidence-gap-router==0.2.4\n```python\n{code}\n```\n",
            encoding="utf-8",
        )
    for name in ("SECURITY.md", "experiments/ollama/README.md"):
        (root / name).write_text("", encoding="utf-8")
    # A minimal fake CLI isolates this launcher contract from SDK regressions;
    # both the example and -m invocation must run in the selected actual venv.
    package = (
        environment
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages/evidence_gap_router"
    )
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        f"assert str(Path(sys.prefix).resolve()) == {prefix!r}\n"
        "print(json.dumps({'selected_environment': True}))\n",
        encoding="utf-8",
    )
    output = tmp_path / "report.json"
    subprocess.run(
        [
            sys.executable,
            "-I",
            str(root / "scripts/check_docs.py"),
            "--python",
            str(python),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(output.read_bytes())
    assert len(report["examples"]) == 3
    assert report["unicode_space_file_cli"]["output"] == {"selected_environment": True}
