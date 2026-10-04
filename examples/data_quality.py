"""Run real local-file callbacks with success, invalid-data and budget cases.

``uv run python examples/data_quality.py --case valid`` runs packaged fixtures.
Use ``--data orders.csv --dictionary dictionary.json`` for your local inputs.
The accepted dictionary shape is illustrated by the bundled JSON fixture.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidence_gap_router.demo import run_demo

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--case", choices=("valid", "invalid", "budget"), default="valid")
parser.add_argument("--data", type=Path)
parser.add_argument("--dictionary", type=Path)
args = parser.parse_args()
print(
    json.dumps(
        run_demo(args.case, data_path=args.data, dictionary_path=args.dictionary),
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    )
)
