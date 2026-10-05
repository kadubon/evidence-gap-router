"""Bounded, strict local CSV and dictionary input for the supplied host example."""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from .jsonio import load_json
from .models import Record

MAX_FILE_BYTES = 1_048_576
MAX_DATA_ROWS = 10_000
COLUMNS = ("order_id", "amount", "currency")


class DataInputError(ValueError):
    """The complete input was rejected; it must not be treated as accepted data."""


class Rules(Record):
    description: str = ""
    required_columns: tuple[Literal["order_id", "amount", "currency"], ...]
    primary_key: Literal["order_id"]
    minimum_amount: Annotated[int | float, Field(ge=0)]
    allowed_currencies: tuple[Annotated[str, Field(min_length=1)], ...]

    @model_validator(mode="after")
    def fixed_contract(self) -> Self:
        if len(self.required_columns) != 3 or set(self.required_columns) != set(COLUMNS):
            raise ValueError("required_columns must contain order_id, amount and currency once")
        if not self.allowed_currencies or len(set(self.allowed_currencies)) != len(
            self.allowed_currencies
        ):
            raise ValueError("allowed_currencies must contain unique nonempty names")
        return self


def read_local_bytes(path: Path) -> bytes:
    """Read a host-selected file completely or reject it, with a finite byte limit."""
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise DataInputError(f"cannot read {path}: {exc}") from exc
    if len(raw) > MAX_FILE_BYTES:
        raise DataInputError(f"{path}: input exceeds {MAX_FILE_BYTES} bytes")
    return raw


def _decode(raw: bytes) -> str:
    if len(raw) > MAX_FILE_BYTES:
        raise DataInputError(f"input exceeds {MAX_FILE_BYTES} bytes")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DataInputError("input must use UTF-8 (an initial UTF-8 BOM is accepted)") from exc


def parse_rules(raw: bytes) -> Rules:
    """Apply the same duplicate-key/nonfinite/strict JSON rules as the SDK."""
    try:
        return load_json(_decode(raw), Rules)
    except (ValueError, RecursionError) as exc:
        raise DataInputError(f"invalid dictionary: {exc}") from exc


def parse_dataset(raw: bytes) -> dict[str, Any]:
    """Reject duplicate headers, empty data and malformed rows without truncation."""
    try:
        reader = csv.reader(io.StringIO(_decode(raw), newline=""), strict=True)
        header = next(reader, None)
        if header is None:
            raise DataInputError("CSV is empty")
        if any(not name.strip() for name in header):
            raise DataInputError("CSV contains an empty column name")
        if len(set(header)) != len(header):
            raise DataInputError("CSV contains duplicate column names")
        if set(header) != set(COLUMNS) or len(header) != len(COLUMNS):
            raise DataInputError("CSV columns must be exactly order_id, amount and currency")
        rows: list[dict[str, str]] = []
        for row in reader:
            if not row:
                continue
            if len(rows) >= MAX_DATA_ROWS:
                raise DataInputError(f"CSV exceeds {MAX_DATA_ROWS} data rows")
            if len(row) != len(header):
                raise DataInputError(f"CSV line {reader.line_num} has missing or extra fields")
            values = dict(zip(header, row, strict=True))
            try:
                amount = Decimal(values["amount"])
            except InvalidOperation as exc:
                raise DataInputError(f"CSV line {reader.line_num}: amount is not numeric") from exc
            if not amount.is_finite():
                raise DataInputError(f"CSV line {reader.line_num}: amount is non-finite")
            rows.append(values)
        if not rows:
            raise DataInputError("CSV must contain at least one data row")
        return {"columns": header, "rows": rows}
    except csv.Error as exc:
        raise DataInputError(f"invalid CSV: {exc}") from exc


def validate_dataset(dataset: dict[str, Any], rules: Rules) -> tuple[str, ...]:
    """Inspect every parsed row against the declared bounded dictionary contract."""
    errors: list[str] = []
    seen: set[str] = set()
    minimum = Decimal(str(rules.minimum_amount))
    for row_number, row in enumerate(dataset["rows"], start=2):
        identifier = row["order_id"]
        if not identifier.strip():
            errors.append(f"row {row_number}: primary key is empty")
        elif identifier in seen:
            errors.append(f"row {row_number}: duplicate primary key {identifier}")
        else:
            seen.add(identifier)
        if Decimal(row["amount"]) < minimum:
            errors.append(f"row {row_number}: amount is below minimum")
        if row["currency"] not in rules.allowed_currencies:
            errors.append(f"row {row_number}: currency is not in dictionary")
    return tuple(errors)
