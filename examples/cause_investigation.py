"""Read three independent input views, then inspect exact declared materials."""

import argparse
import json

from evidence_gap_router.demo import run_cause_demo

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--case",
    choices=("resolved", "invalid", "conflict", "unknown", "provenance", "budget"),
    default="resolved",
)
args = parser.parse_args()
print(json.dumps(run_cause_demo(args.case), indent=2, ensure_ascii=False))
