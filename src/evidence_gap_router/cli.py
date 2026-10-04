"""Offline, read-only CLI for explicit routing inputs."""

from __future__ import annotations

import argparse
import json
import sys

from ._version import __version__
from .demo import run_demo
from .jsonio import read_json
from .models import PlanInput
from .router import plan


def main(argv: list[str] | None = None) -> int:
    """Return 0 for action/satisfaction, 2 for unresolved stops, 1 for bad input."""
    parser = argparse.ArgumentParser(
        prog="egr", description="Route work by missing evidence, not by agent count."
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo_parser = commands.add_parser("demo", help="run the artificial offline CSV demo")
    demo_parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    demo_parser.add_argument("--case", choices=("valid", "invalid", "budget"), default="valid")
    plan_parser = commands.add_parser("plan", help="read JSON and recommend without executing")
    plan_parser.add_argument("input", help="UTF-8 JSON file, at most 1 MiB")
    plan_parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            output = run_demo(args.case)
            if args.json:
                print(json.dumps(output, ensure_ascii=False, sort_keys=True, allow_nan=False))
            else:
                decision = output["decision"]
                print("Artificial offline data-quality demonstration.")
                print(f"Case: {args.case}; stop: {decision['stop_reason']}")
                print(f"Callbacks: {', '.join(output['callback_calls'])}")
                print(decision["reason"])
            return 0 if output["decision"]["stop_reason"] == "satisfied" else 2
        request = read_json(args.input, PlanInput)
        decision_model = plan(request.state, request.candidates, request.budget, request.policy)
        if args.json:
            print(decision_model.model_dump_json())
        else:
            if decision_model.action is not None:
                print(f"Next action: {decision_model.action.id}")
            else:
                print(f"Stop: {decision_model.stop_reason}")
            print(decision_model.reason)
        return (
            0
            if decision_model.action is not None or decision_model.stop_reason == "satisfied"
            else 2
        )
    except (OSError, ValueError, RecursionError) as exc:
        print(f"egr: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
