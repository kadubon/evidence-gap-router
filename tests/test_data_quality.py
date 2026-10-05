from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest

from evidence_gap_router.cli import main
from evidence_gap_router.data_quality import DataInputError, parse_dataset, parse_rules
from evidence_gap_router.file_checks import check_data


def rules_bytes() -> bytes:
    return files("evidence_gap_router").joinpath("data", "data_dictionary.json").read_bytes()


def local_files(tmp_path: Path, data: bytes, rules: bytes | None = None) -> tuple[Path, Path]:
    directory = tmp_path / "日本語 空白 directory"
    directory.mkdir()
    data_path = directory / "注文 data.csv"
    dictionary_path = directory / "規則 rules.json"
    data_path.write_bytes(data)
    dictionary_path.write_bytes(rules if rules is not None else rules_bytes())
    return data_path, dictionary_path


def test_A08_duplicate_csv_headers_are_rejected_before_acceptance(tmp_path: Path) -> None:
    raw = b"order_id,amount,amount,currency\nA,-999,10,USD\n"
    with pytest.raises(DataInputError, match="duplicate column"):
        parse_dataset(raw)
    data, dictionary = local_files(tmp_path, raw)
    report = check_data(data, dictionary)
    assert report["outcome"] == "input_error"
    assert report["decision"]["stop_reason"] != "satisfied"
    assert not any(check["verifier_id"] == "orders-checker" for check in report["state"]["checks"])
    failures = [result for result in report["state"]["results"] if result["status"] == "failed"]
    assert failures[0]["actual_resources"]["actions"] == 1


def test_A09_duplicate_dictionary_keys_are_rejected(tmp_path: Path) -> None:
    raw = (
        b'{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
        b'"minimum_amount":1000,"minimum_amount":0,"allowed_currencies":["USD"]}'
    )
    with pytest.raises(DataInputError, match="duplicate"):
        parse_rules(raw)
    data, dictionary = local_files(tmp_path, b"order_id,amount,currency\nA,10,USD\n", raw)
    report = check_data(data, dictionary)
    assert report["outcome"] == "input_error"
    assert report["state"]["checks"] == []
    assert report["state"]["results"][0]["actual_resources"]["actions"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"order_id,amount,currency\n",
        b"order_id,,currency\nA,10,USD\n",
        b"order_id,amount,other\nA,10,USD\n",
        b"order_id,amount,currency,extra\nA,10,USD,x\n",
        b"order_id,amount,currency\nA,10\n",
        b"order_id,amount,currency\nA,10,USD,x\n",
        b"order_id,amount,currency\nA,NaN,USD\n",
        b"order_id,amount,currency\nA,Infinity,USD\n",
        b"order_id,amount,currency\nA,true,USD\n",
        b"\xffinvalid",
        b'order_id,amount,currency\n"unclosed,1,USD\n',
    ],
    ids=(
        "empty",
        "no-rows",
        "empty-header",
        "missing-header",
        "extra-header",
        "missing-field",
        "extra-field",
        "nan",
        "infinity",
        "wrong-type",
        "encoding",
        "quotes",
    ),
)
def test_csv_input_contract_rejects_bad_inputs(raw: bytes) -> None:
    with pytest.raises(DataInputError):
        parse_dataset(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown-field",
        "string-number",
        "bool-number",
        "negative-number",
        "infinity",
        "empty-currencies",
        "repeated-currencies",
        "repeated-columns",
        "missing-column",
    ],
)
def test_dictionary_strict_fields_and_types(mutation: str) -> None:
    value = json.loads(rules_bytes())
    if mutation == "unknown-field":
        value["unexpected"] = 1
    elif mutation == "string-number":
        value["minimum_amount"] = "0"
    elif mutation == "bool-number":
        value["minimum_amount"] = True
    elif mutation == "negative-number":
        value["minimum_amount"] = -1
    elif mutation == "infinity":
        value["minimum_amount"] = float("inf")
    elif mutation == "empty-currencies":
        value["allowed_currencies"] = []
    elif mutation == "repeated-currencies":
        value["allowed_currencies"] = ["USD", "USD"]
    elif mutation == "repeated-columns":
        value["required_columns"] = ["order_id", "amount", "amount", "currency"]
    else:
        value["required_columns"] = ["order_id", "amount"]
    with pytest.raises(DataInputError):
        parse_rules(json.dumps(value).encode())


@pytest.mark.parametrize("newline,bom", [("\n", False), ("\r\n", False), ("\r\n", True)])
def test_unicode_space_paths_line_endings_bom_raw_digests_and_read_only(
    newline: str, bom: bool, tmp_path: Path
) -> None:
    raw = ("order_id,amount,currency" + newline + "A,10,USD" + newline).encode()
    prefix = b"\xef\xbb\xbf" if bom else b""
    raw = prefix + raw
    dictionary_raw = prefix + rules_bytes()
    data, dictionary = local_files(tmp_path, raw, dictionary_raw)
    report = check_data(data, dictionary)
    assert report["outcome"] == "satisfied"
    assert report["artificial_data"] is False
    assert {item["scope"] for item in report["state"]["obligations"]} == {
        "local-orders",
        "local-rules",
    }
    dataset = next(item for item in report["state"]["evidence"] if item["id"] == "dataset")
    assert dataset["digest"] == hashlib.sha256(raw).hexdigest()
    assert data.read_bytes() == raw and dictionary.read_bytes() == dictionary_raw


def test_limits_reject_full_input_instead_of_accepting_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("evidence_gap_router.data_quality.MAX_DATA_ROWS", 1)
    with pytest.raises(DataInputError, match="exceeds 1 data rows"):
        parse_dataset(b"order_id,amount,currency\nA,1,USD\nB,2,USD\n")
    monkeypatch.setattr("evidence_gap_router.data_quality.MAX_FILE_BYTES", 32)
    with pytest.raises(DataInputError, match="exceeds 32 bytes"):
        parse_dataset(b"order_id,amount,currency\nA,1,USD\nB,2,USD\n")


def test_checked_failure_differs_from_input_error(tmp_path: Path) -> None:
    data, dictionary = local_files(tmp_path, b"order_id,amount,currency\nA,-1,XXX\nA,2,USD\n")
    report = check_data(data, dictionary)
    assert report["outcome"] == "inspected_fail"
    assert report["decision"]["stop_reason"] == "escalation_required"
    assert any(check["status"] == "FAIL" for check in report["state"]["checks"])
    assert all(result["status"] == "completed" for result in report["state"]["results"])


def test_cli_real_files_json_and_exit_codes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data, dictionary = local_files(tmp_path, b"order_id,amount,currency\nA,10,USD\n")
    args = ["check-data", "--data", str(data), "--dictionary", str(dictionary), "--json"]
    assert main(args) == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["outcome"] == "satisfied"
    data.write_bytes(b"order_id,amount,currency\nA,-1,USD\n")
    assert main(args) == 2
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out)["outcome"] == "inspected_fail"
    data.write_bytes(b"order_id,amount,amount,currency\nA,-99,10,USD\n")
    assert main(args) == 1
    output = capsys.readouterr()
    assert "input_error" in output.err
    assert json.loads(output.out)["outcome"] == "input_error"
