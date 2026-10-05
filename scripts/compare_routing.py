"""Run the package's bounded matched comparison and emit raw JSON."""

import json

from evidence_gap_router.comparison import compare

if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
