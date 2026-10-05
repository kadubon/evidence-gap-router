"""Bounded, duplicate-key rejecting versioned JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .models import State

MAX_JSON_BYTES = 1_048_576


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant: {value}")


def load_json[T: BaseModel](text: str | bytes, model_type: type[T]) -> T:
    """Validate bytes as JSON without coercion or discarding unknown fields."""
    raw = text.encode("utf-8") if isinstance(text, str) else text
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"JSON exceeds {MAX_JSON_BYTES} byte limit")
    decoded = raw.decode("utf-8", errors="strict")
    try:
        json.loads(decoded, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant)
        return model_type.model_validate_json(decoded)
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds parser limits") from error


def read_json[T: BaseModel](path: str | Path, model_type: type[T]) -> T:
    """Read at most the input limit, with no reference fetching or code execution."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    return load_json(raw, model_type)


def dump_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def migrate_v1_json(text: str | bytes) -> State:
    """Preserve a strictly valid schema-1 snapshot without inventing check foundations."""
    from ._legacy import State as LegacyState

    old = load_json(text, LegacyState)
    values = old.model_dump(mode="json")
    values["schema_version"] = "2"
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
    if len(dump_json(migrated).encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError(
            "migrated snapshot exceeds the JSON byte limit including its original archive; "
            "input is unchanged and needs explicit host migration/archive handling"
        )
    return migrated


def migrate_v1_file(path: str | Path) -> State:
    """Read-only migration; the original input file is never overwritten."""
    with Path(path).open("rb") as stream:
        return migrate_v1_json(stream.read(MAX_JSON_BYTES + 1))
