"""Bounded, duplicate-key rejecting versioned JSON snapshots."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

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
