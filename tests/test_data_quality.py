from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from evidence_gap_router import dump_json, load_json
from evidence_gap_router.cli import main
from evidence_gap_router.data_quality import DataInputError, Rules, parse_dataset, parse_rules
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


def precise_rules(number: str) -> bytes:
    return (
        '{"required_columns":["order_id","amount","currency"],"primary_key":"order_id",'
        f'"minimum_amount":{number},"allowed_currencies":["USD"]}}'
    ).encode()


@pytest.mark.parametrize(
    "minimum,amount,expected",
    [
        ("9007199254740993.0", "9007199254740992", "inspected_fail"),
        ("9007199254740993.0", "9007199254740993", "satisfied"),
        ("0.12345678901234567890123456789", "0.12345678901234567890123456788", "inspected_fail"),
        ("0.12345678901234567890123456789", "0.12345678901234567890123456789", "satisfied"),
        ("1e-128", "0", "inspected_fail"),
        ("1e128", "1e128", "satisfied"),
    ],
)
def test_EGR020_06_exact_file_numbers_before_float_conversion(
    minimum: str, amount: str, expected: str, tmp_path: Path
) -> None:
    raw = precise_rules(minimum)
    data, dictionary = local_files(
        tmp_path, f"order_id,amount,currency\nA,{amount},USD\n".encode(), raw
    )
    report = check_data(data, dictionary)
    assert report["outcome"] == expected
    assert len(report["state"]["attempts"]) == len(report["state"]["results"]) == 4
    retained = next(
        record for record in report["state"]["evidence"] if record["id"] == "dictionary"
    )
    assert retained["digest"] == hashlib.sha256(raw).hexdigest()
    assert json.loads(retained["content"], parse_float=Decimal)["minimum_amount"] == Decimal(
        minimum
    )
    assert load_json(retained["content"], Rules).minimum_amount == Decimal(minimum)
    assert dictionary.read_bytes() == raw
    if expected == "inspected_fail":
        orders_check = next(
            c for c in report["state"]["checks"] if c["verifier_id"] == "orders-checker"
        )
        assert orders_check["status"] == "FAIL"
        assert "amount is below minimum" in orders_check["reason"]


def test_decimal_rules_roundtrip_all_supported_json_entrypoints() -> None:
    raw = precise_rules("9007199254740993.0")
    direct = Rules.model_validate_json(raw)
    parsed = parse_rules(raw)
    assert direct == parsed
    assert parsed.minimum_amount == Decimal("9007199254740993.0")
    for text in (dump_json(parsed), parsed.model_dump_json(), parsed.model_dump_json(indent=2)):
        value = json.loads(text, parse_float=Decimal)
        assert not isinstance(value["minimum_amount"], str)
        assert value["minimum_amount"] == Decimal("9007199254740993.0")
        assert load_json(text, Rules) == parsed
        assert Rules.model_validate_json(text) == parsed


@pytest.mark.parametrize("number", ["-0.001", "1e129", "1e-129", "9" * 65 + ".0", "9" * 129])
def test_dictionary_numeric_contract_rejects_negative_or_unbounded_numbers(number: str) -> None:
    with pytest.raises(DataInputError):
        parse_rules(precise_rules(number))


@pytest.mark.parametrize("amount", ["1e129", "1e-129", "9" * 65, "1e" + "0" * 300 + "1"])
def test_csv_numbers_use_the_same_finite_decimal_bounds(amount: str) -> None:
    with pytest.raises(DataInputError, match="invalid amount"):
        parse_dataset(f"order_id,amount,currency\nA,{amount},USD\n".encode())


def test_sdk_float_has_its_existing_representation_not_recovered_source_digits() -> None:
    rounded = 9007199254740993.0
    rules = Rules(
        required_columns=("order_id", "amount", "currency"),
        primary_key="order_id",
        minimum_amount=rounded,
        allowed_currencies=("USD",),
    )
    assert rules.minimum_amount == 9007199254740992.0
    assert load_json(dump_json(rules), Rules).minimum_amount == Decimal("9007199254740992.0")
    with pytest.raises(ValueError):
        Rules.model_validate_json(precise_rules('"9007199254740993.0"'))


def test_maximum_dictionary_file_does_not_grow_past_reader_limit_from_optional_defaults(
    tmp_path: Path,
) -> None:
    from evidence_gap_router.data_quality import MAX_FILE_BYTES

    value = json.loads(precise_rules("0"))
    value["allowed_currencies"] = ["USD", *[str(i) + "U" * 60_000 for i in range(17)]]
    initial = json.dumps(value, separators=(",", ":")).encode()
    value["allowed_currencies"][-1] += "U" * (MAX_FILE_BYTES - len(initial))
    raw = json.dumps(value, separators=(",", ":")).encode()
    assert len(raw) == MAX_FILE_BYTES
    data, dictionary = local_files(tmp_path, b"order_id,amount,currency\nA,0,USD\n", raw)
    report = check_data(data, dictionary)
    assert report["outcome"] == "satisfied"
    retained = next(e for e in report["state"]["evidence"] if e["id"] == "dictionary")
    assert len(retained["content"].encode()) <= MAX_FILE_BYTES
    assert retained["content"].encode() == raw
    assert "description" not in json.loads(retained["content"])
    assert dictionary.read_bytes() == raw


def test_csv_field_limit_is_explicit_and_does_not_modify_process_global_setting() -> None:
    from evidence_gap_router.data_quality import MAX_CSV_FIELD_CHARACTERS

    initial = csv.field_size_limit()
    raw = b"order_id,amount,currency\nA,0," + b"U" * (MAX_CSV_FIELD_CHARACTERS + 1) + b"\n"
    with pytest.raises(DataInputError, match="field.*(limit|exceeds)"):
        parse_dataset(raw)
    assert csv.field_size_limit() == initial
