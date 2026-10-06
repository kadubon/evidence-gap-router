"""Historical audit compatibility and preserved results; current R01–R30 are separate."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmarks.audit_022 import run_audit  # noqa: E402


def test_historical_audit_refuses_current_sdk_before_cases():
    with patch(
        "benchmarks.audit_022.imported_case", side_effect=AssertionError("new historical audit")
    ):
        with pytest.raises(ValueError, match="original tag"):
            run_audit()


def test_old_audit_evidence_remains_available_with_original_identity():
    root = Path(__file__).parents[1]
    assert (root / "docs/audit-022.md").is_file()
    old = json.loads((root / "benchmarks/results/freeze-v0.2.2.json").read_bytes())
    assert len(old["implementation_commit"]) == 40
