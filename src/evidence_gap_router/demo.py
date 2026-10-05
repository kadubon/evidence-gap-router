"""Offline bundled artificial examples over the independent public runner."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from .cause_demo import run_cause_demo
from .data_quality import read_local_bytes
from .file_checks import _data_host


def run_demo(
    case: str = "valid", *, data_path: Path | None = None, dictionary_path: Path | None = None
) -> dict[str, Any]:
    """Run dictionary and dataset obligations with actual separate file callbacks."""
    if case not in {"valid", "invalid", "budget"}:
        raise ValueError("case must be valid, invalid or budget")
    name = "orders_invalid.csv" if case == "invalid" else "orders_valid.csv"
    return _data_host(
        (lambda: read_local_bytes(data_path))
        if data_path is not None
        else (lambda: files("evidence_gap_router").joinpath("data", name).read_bytes()),
        (lambda: read_local_bytes(dictionary_path))
        if dictionary_path is not None
        else (
            lambda: (
                files("evidence_gap_router").joinpath("data", "data_dictionary.json").read_bytes()
            )
        ),
        data_source=str(data_path) if data_path is not None else f"bundled artificial {name}",
        dictionary_source=str(dictionary_path)
        if dictionary_path is not None
        else "bundled artificial data_dictionary.json",
        artificial_data=data_path is None and dictionary_path is None,
        case=case,
        action_limit=2 if case == "budget" else 4,
        verification_limit=0 if case == "budget" else 2,
    )


__all__ = ["run_demo", "run_cause_demo"]
