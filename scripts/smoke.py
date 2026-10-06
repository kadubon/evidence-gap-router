"""Verify an installed distribution; run outside the source checkout."""

import argparse
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

import evidence_gap_router as egr
from evidence_gap_router.demo import run_cause_demo, run_demo
from evidence_gap_router.models import State
from evidence_gap_router.sdk_example import run_callback_example, run_continuation_example


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    expected_version = parser.parse_args().expected_version
    package_path = Path(egr.__file__).resolve()
    source = Path(__file__).resolve().parents[1] / "src"
    assert not package_path.is_relative_to(source), package_path
    assert egr.__version__ == importlib.metadata.version("evidence-gap-router") == expected_version
    assert package_path.is_relative_to(Path(sys.prefix).resolve()), package_path
    command = Path(sys.executable).with_name("egr.exe" if sys.platform == "win32" else "egr")
    version = subprocess.run(
        [str(command), "--version"], capture_output=True, text=True, check=True
    )
    assert version.stdout.strip() == expected_version
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
        assert state.schema_version == "3"

    sdk = run_callback_example()
    assert sdk.decision.stop_reason == "satisfied", sdk
    assert egr.load_json(egr.dump_json(sdk.state), State) == sdk.state
    for case in ("resolved", "conflict", "unknown", "provenance", "budget"):
        report = run_cause_demo(case)
        assert report["artificial_data"] is True
        assert (report["decision"]["stop_reason"] == "satisfied") == (case == "resolved"), report
        state = egr.load_json(json.dumps(report["state"]), State)
        assert egr.load_json(egr.dump_json(state), State) == state

    # The installed CLI reads actual host-selected files, with complete input
    # validation, distinct real-data scope, and Unicode/space/BOM/CRLF handling.
    with tempfile.TemporaryDirectory(prefix="egr-installed-smoke-") as temporary:
        directory = Path(temporary) / "日本語 path"
        directory.mkdir()
        dataset = directory / "受注 data.csv"
        dictionary = directory / "規則 rules.json"
        fixture = files("evidence_gap_router").joinpath("data")
        csv = fixture.joinpath("orders_valid.csv").read_text(encoding="utf-8")
        dataset.write_bytes(
            b"\xef\xbb\xbf" + csv.replace("\r\n", "\n").replace("\n", "\r\n").encode()
        )
        dictionary.write_bytes(
            b"\xef\xbb\xbf" + fixture.joinpath("data_dictionary.json").read_bytes()
        )
        continued = run_continuation_example(directory / "継続 snapshot.json")
        assert continued.decision.stop_reason == "satisfied", continued
        assert len(continued.state.attempts) == len(continued.state.results) == 3
        assert len(continued.state.invalidations) == 1
        assert sum(r.actual_resources.actions or 0 for r in continued.state.results) == 3
        assert sum(r.actual_resources.verifications or 0 for r in continued.state.results) == 2
        assert egr.load_json(egr.dump_json(continued.state), State) == continued.state
        completed = subprocess.run(
            [
                str(command),
                "check-data",
                "--data",
                str(dataset),
                "--dictionary",
                str(dictionary),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert completed.returncode == 0 and not completed.stderr, completed
        payload = json.loads(completed.stdout)
        assert payload["artificial_data"] is False
        assert payload["decision"]["stop_reason"] == "satisfied", payload
        assert all("artificial" not in o["scope"] for o in payload["state"]["obligations"])
        dataset.write_text("order_id,amount,amount,currency\nA,-999,10,USD\n", encoding="utf-8")
        rejected = subprocess.run(
            [
                str(command),
                "check-data",
                "--data",
                str(dataset),
                "--dictionary",
                str(dictionary),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert rejected.returncode == 1 and rejected.stderr, rejected
        assert json.loads(rejected.stdout)["outcome"] == "input_error"

        # The literal decimal threshold is larger than the CSV value by exactly
        # one; losing its least significant digit would incorrectly accept it.
        dictionary.write_bytes(
            b'{"required_columns":["order_id","amount","currency"],'
            b'"primary_key":"order_id","minimum_amount":9007199254740993.0,'
            b'"allowed_currencies":["USD"]}'
        )
        dataset.write_bytes(b"order_id,amount,currency\r\nA,9007199254740992,USD\r\n")
        precise = subprocess.run(
            [
                str(command),
                "check-data",
                "--data",
                str(dataset),
                "--dictionary",
                str(dictionary),
                "--json",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert precise.returncode == 2 and not precise.stderr, precise
        assert json.loads(precise.stdout)["decision"]["stop_reason"] != "satisfied"

    # A legacy PASS is retained without manufacturing its missing verification
    # contract. This snapshot comes from the documented v1 schema.
    legacy = {
        "schema_version": "1",
        "obligations": [
            {
                "id": "legacy",
                "description": "display",
                "scope": "v1",
                "acceptance": "old",
                "required": True,
            }
        ],
        "evidence": [
            {
                "id": "old",
                "obligation_id": "legacy",
                "scope": "v1",
                "digest": "a" * 64,
                "producer": "reader",
                "content": "old",
            }
        ],
        "checks": [
            {
                "id": "old-pass",
                "obligation_id": "legacy",
                "scope": "v1",
                "target_digest": "a" * 64,
                "verifier_id": "checker",
                "status": "PASS",
                "reason": "old check lacks a recorded contract",
            }
        ],
    }
    migrated = egr.migrate_v1_json(json.dumps(legacy))
    assert migrated.schema_version == "3" and migrated.checks[0].legacy
    assert migrated.checks[0].basis is None and migrated.legacy_schema1 is not None
    assert egr.load_json(egr.dump_json(migrated), State) == migrated
    assert (
        egr.plan(migrated, (), egr.Budget(limits=egr.Resources()), egr.Policy()).stop_reason
        != "satisfied"
    )
    old_path = (
        Path(__file__).resolve().parents[1] / "tests/fixtures/v020-wrong-alias-resolution.json"
    )
    original_bytes = old_path.read_bytes()
    imported = egr.migrate_v2_json(original_bytes)
    assert imported.legacy_schema2.encode("utf-8") == original_bytes
    assert imported.schema_version == "3" and not imported.completion_contracts
    assert egr.load_json(egr.dump_json(imported), State) == imported
    assert old_path.read_bytes() == original_bytes
    from evidence_gap_router.completion_example import (
        run_material_continuation,
        run_partial_example,
        run_pooled_example,
    )

    with tempfile.TemporaryDirectory(prefix="egr-completion-installed-") as temporary:
        root = Path(temporary) / "日本語 path"
        partial = run_partial_example(root / "partial")
        assert partial["partial"]["completion"][0]["finite_complete"] is False
        assert partial["after_acquisition"]["completion"][0]["finite_complete"] is False
        assert partial["decision"]["stop_reason"] == "satisfied"
        pooled = run_pooled_example(root / "pooled")
        assert pooled.decision.stop_reason == "satisfied" and len(pooled.state.results) == 1
        continued = run_material_continuation(root / "continuation")
        assert continued.decision.stop_reason == "satisfied" and len(continued.state.results) == 3
        assert len(continued.state.checks) == 2 and len(continued.state.invalidations) == 1
    print(json.dumps({"version": egr.__version__, "package": str(package_path), "smoke": "passed"}))


if __name__ == "__main__":
    main()
