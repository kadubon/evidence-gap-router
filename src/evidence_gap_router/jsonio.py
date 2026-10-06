"""Bounded, duplicate-key rejecting versioned JSON snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from .models import State

MAX_JSON_BYTES = 1_048_576
MAX_SNAPSHOT_BYTES = 33_554_432
MAX_JSON_DEPTH = 64
MAX_INTEGER_DIGITS = 128
MAX_DECIMAL_DIGITS = 64
MAX_DECIMAL_EXPONENT = 128
MAX_NUMBER_CHARACTERS = 256


def bounded_decimal(value: str | Decimal) -> Decimal:
    """Preserve a finite decimal value within the supplied data contract's limits."""
    try:
        if isinstance(value, str) and len(value.strip()) > MAX_NUMBER_CHARACTERS:
            raise ValueError(f"decimal number exceeds {MAX_NUMBER_CHARACTERS} characters")
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid decimal number") from error
    if not result.is_finite():
        raise ValueError("decimal number must be finite")
    parts = result.as_tuple()
    if len(parts.digits) > MAX_DECIMAL_DIGITS:
        raise ValueError(f"decimal number exceeds {MAX_DECIMAL_DIGITS} coefficient digits")
    exponent = cast(int, parts.exponent)
    if abs(exponent) > MAX_DECIMAL_EXPONENT or abs(result.adjusted()) > MAX_DECIMAL_EXPONENT:
        raise ValueError(f"decimal exponent exceeds +/-{MAX_DECIMAL_EXPONENT}")
    return result


def _bounded_integer(value: str) -> int:
    if len(value.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise ValueError(f"integer exceeds {MAX_INTEGER_DIGITS} digits")
    return int(value)


def _byte_limit(model_type: type[BaseModel]) -> int:
    from ._legacy import State as LegacyState

    return MAX_SNAPSHOT_BYTES if issubclass(model_type, (State, LegacyState)) else MAX_JSON_BYTES


def _depth_check(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")
        elif char in "]}":
            depth -= 1


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def _parse_json(text: str | bytes, limit: int) -> tuple[str, object]:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    if len(raw) > limit:
        raise ValueError(f"JSON exceeds {limit} byte limit")
    decoded = raw.decode("utf-8", errors="strict")
    try:
        _depth_check(decoded)
        parsed = json.loads(
            decoded,
            object_pairs_hook=_unique_pairs,
            parse_constant=_invalid_constant,
            parse_float=bounded_decimal,
            parse_int=_bounded_integer,
        )
        return decoded, parsed
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds parser limits") from error


def load_json[T: BaseModel](text: str | bytes, model_type: type[T]) -> T:
    """Validate bytes as JSON without coercion or discarding unknown fields."""
    decoded, parsed = _parse_json(text, _byte_limit(model_type))
    exact_validator = getattr(model_type, "_validate_exact_json", None)
    if exact_validator is not None:
        return cast(T, exact_validator(parsed))
    # Core strict integer and tuple validation uses Pydantic's JSON semantics.
    # Decimal-sensitive models explicitly consume the parsed values above.
    return model_type.model_validate_json(decoded)


def read_json[T: BaseModel](path: str | Path, model_type: type[T]) -> T:
    """Read at most the input limit, with no reference fetching or code execution."""
    with Path(path).open("rb") as stream:
        raw = stream.read(_byte_limit(model_type) + 1)
    return load_json(raw, model_type)


def exact_json(
    value: object, *, sort_keys: bool = False, indent: int | None = None, ensure_ascii: bool = False
) -> str:
    """Encode bounded Decimal values as exact JSON numbers, never rounded floats."""

    def encode(item: object, depth: int) -> str:
        if depth > MAX_JSON_DEPTH:
            raise ValueError(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")
        if isinstance(item, Decimal):
            return str(bounded_decimal(item))
        if isinstance(item, dict):
            keys = sorted(item) if sort_keys else item
            if any(not isinstance(key, str) for key in keys):
                raise TypeError("JSON object keys must be strings")
            parts = [
                json.dumps(key, ensure_ascii=ensure_ascii)
                + (": " if indent is not None else ":")
                + encode(item[key], depth + 1)
                for key in keys
            ]
            return container(parts, "{", "}", depth)
        if isinstance(item, (list, tuple)):
            return container([encode(part, depth + 1) for part in item], "[", "]", depth)
        if isinstance(item, int) and not isinstance(item, bool):
            _bounded_integer(str(item))
        if isinstance(item, float):
            bounded_decimal(str(item))
        return json.dumps(item, ensure_ascii=ensure_ascii, allow_nan=False)

    def container(parts: list[str], opening: str, closing: str, depth: int) -> str:
        if indent is None or not parts:
            return opening + ",".join(parts) + closing
        padding = " " * max(0, indent)
        return (
            opening
            + "\n"
            + padding * (depth + 1)
            + (",\n" + padding * (depth + 1)).join(parts)
            + "\n"
            + padding * depth
            + closing
        )

    return encode(value, 0)


def dump_json(model: BaseModel) -> str:
    """Serialize within this model's finite read limit, or reject the complete output."""
    # Preserve Pydantic's serializers for existing custom models (e.g. datetime
    # and UUID). Decimal-sensitive Rules supplies its own exact JSON override.
    text = model.model_dump_json(indent=2)
    _parse_json(text, _byte_limit(type(model)))
    return text


def write_json(model: BaseModel, path: str | Path) -> None:
    """Validate a readable snapshot before atomically replacing a host-selected file."""
    text = dump_json(model)
    load_json(text, type(model))
    target = Path(path)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(text.encode("utf-8"))
        os.replace(temp_path, target)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def migrate_v1_json(text: str | bytes) -> State:
    """Preserve a strictly valid schema-1 snapshot without inventing check foundations."""
    from ._legacy import State as LegacyState

    old = load_json(text, LegacyState)
    values = old.model_dump(mode="json")
    values["schema_version"] = "3"
    values["legacy_schema1"] = text.decode("utf-8") if isinstance(text, bytes) else text
    for name in ("checks", "supersessions", "attempts"):
        for record in values[name]:
            record["legacy"] = True
    for receipt in values["results"]:
        receipt["legacy"] = True
        for name in ("checks", "supersessions"):
            for record in receipt[name]:
                record["legacy"] = True
    migrated = State.model_validate_json(json.dumps(values, ensure_ascii=False))
    dump_json(migrated)
    return migrated


def migrate_v1_file(path: str | Path) -> State:
    """Read-only migration; the original input file is never overwritten."""
    with Path(path).open("rb") as stream:
        return migrate_v1_json(stream.read(MAX_SNAPSHOT_BYTES + 1))


def migrate_v2_json(text: str | bytes) -> State:
    """Strict schema-2 import; retain original bytes and unchanged mechanical bases."""
    decoded, parsed = _parse_json(text, MAX_SNAPSHOT_BYTES)
    if not isinstance(parsed, dict) or parsed.get("schema_version") != "2":
        raise ValueError("expected an explicit schema-2 snapshot")
    forbidden = {
        "completion_contracts",
        "legacy_schema2",
        "check_kind",
        "advisory",
        "completion_fingerprint",
        "completion_kinds",
        "completion_scopes",
        "correlation_group",
        "method",
    }

    def original_fields(value: object) -> None:
        if isinstance(value, dict):
            if forbidden.intersection(value):
                raise ValueError("schema-2 input contains schema-3 fields")
            for child in value.values():
                original_fields(child)
        elif isinstance(value, list):
            for child in value:
                original_fields(child)

    original_fields(parsed)
    parsed["schema_version"] = "3"
    parsed["legacy_schema2"] = decoded
    try:
        migrated = State.model_validate_json(json.dumps(parsed, ensure_ascii=False))
    except TypeError as exc:
        raise ValueError("schema-2 snapshot contains an invalid numeric field") from exc
    dump_json(migrated)
    return migrated


def migrate_v2_file(path: str | Path) -> State:
    """Read-only explicit migration; use write_json with a separate destination."""
    with Path(path).open("rb") as stream:
        return migrate_v2_json(stream.read(MAX_SNAPSHOT_BYTES + 1))
