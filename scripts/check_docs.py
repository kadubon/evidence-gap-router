"""Check local documentation links and execute complete ordinary-wheel examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.2.4")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    names = ["README.md", "README.ja.md", "SECURITY.md", "experiments/ollama/README.md"]
    names += [str(p.relative_to(root)) for p in sorted((root / "docs").glob("*.md"))]
    checked = 0
    for name in names:
        text = (root / name).read_text("utf-8")
        for target in re.findall(r"\[[^\]\n]+\]\(([^)\n]+)\)", text):
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (root / name).parent / unquote(parsed.path)
            if not path.resolve().is_relative_to(root) or not path.exists():
                raise ValueError(f"Missing local documentation link: {name}: {target}")
            checked += 1
    for name in ("README.md", "README.ja.md", "docs/getting-started.md"):
        if f"pip install evidence-gap-router=={args.version}" not in (root / name).read_text(
            "utf-8"
        ):
            raise ValueError(f"Install version differs from this candidate: {name}")
    report = {"version": args.version, "local_links_checked": checked, "examples": []}
    if args.python:
        # Preserve a venv's interpreter symlink when launching: resolving the
        # executable itself would select the base interpreter on POSIX.
        python = args.python.absolute()
        if not python.is_file():
            raise FileNotFoundError(python)
        if python.parent.resolve(strict=True).is_relative_to(root):
            raise ValueError("Example verification needs an ordinary environment outside checkout")
        with tempfile.TemporaryDirectory(prefix="egr-docs-") as temporary:
            directory = Path(temporary)
            for name in ("README.md", "README.ja.md", "docs/getting-started.md"):
                blocks = re.findall(
                    r"```python\n(.*?)\n```", (root / name).read_text("utf-8"), re.S
                )
                script = directory / (Path(name).stem + ".py")
                script.write_text("\n\n".join(blocks), encoding="utf-8")
                completed = subprocess.run(
                    [str(python), "-I", str(script)],
                    cwd=directory,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if name.startswith("README") and completed.stdout.splitlines() != [
                    "check-answer",
                    "PASS",
                    "satisfied",
                    "[]",
                ]:
                    raise ValueError("README callback output differs from its documented contract")
                report["examples"].append(
                    {
                        "document": name,
                        "source_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                        "stdout": completed.stdout,
                        "exit_code": completed.returncode,
                    }
                )
            checked_files = subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "evidence_gap_router.cli",
                    "check-data",
                    "--data",
                    "入力 ファイル/注文.csv",
                    "--dictionary",
                    "入力 ファイル/規則.json",
                    "--json",
                ],
                cwd=directory,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            report["unicode_space_file_cli"] = {
                "exit_code": checked_files.returncode,
                "output": json.loads(checked_files.stdout),
            }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "version": args.version,
                "local_links_checked": checked,
                "executed_example_documents": len(report["examples"]),
            }
        )
    )


if __name__ == "__main__":
    main()
