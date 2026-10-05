"""Bounded, local-only Ollama transport for the explicit experiment commands.

This module never discovers, downloads, loads, or generates a model on import.
The host establishes local model identity and cloud-disabled server configuration.
The ledger records that supplied identity; a string or boolean is not authentication.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_DURATIONS = ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")
_COUNTERS = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count")
SUPPORTED_SERVER_VERSION = "0.35.0"


class ClientBlocked(RuntimeError):
    """No request was sent: an envelope, pending request, or ledger prevents it."""


def _json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError(f"nonfinite JSON value: {value}")


def strict_json(text: str) -> Any:
    """Parse without duplicate keys, NaN/Infinity, or overflow to infinity."""
    value = json.loads(text, object_pairs_hook=_json_pairs, parse_constant=_nonfinite)

    def visit(item: Any, depth: int = 0) -> None:
        if depth > 64:
            raise ValueError("JSON nesting exceeds 64 levels")
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                visit(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                visit(child, depth + 1)

    visit(value)
    return value


def _bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _wall_amended_config(
    config: dict[str, Any], new_run_id: str, new_freeze_id: str
) -> dict[str, Any]:
    if config["limits"]["global_wall_seconds"] != 14_400:
        raise ValueError("only the initial 14400-second wall budget can be amended once")
    if (
        not isinstance(new_run_id, str)
        or not new_run_id
        or len(new_run_id) > 256
        or new_run_id == config["run_id"]
    ):
        raise ValueError("the amendment requires a different explicit run identity")
    if (
        not isinstance(new_freeze_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", new_freeze_id)
        or new_freeze_id == config["freeze_id"]
    ):
        raise ValueError("the amendment requires a different protocol SHA256 freeze identity")
    amended = strict_json(_bytes(config).decode())
    if not isinstance(amended, dict):
        raise ValueError("the frozen config must be a JSON object")
    amended["run_id"] = new_run_id
    amended["freeze_id"] = new_freeze_id
    amended["limits"]["global_wall_seconds"] = 28_800
    return amended


def _retained_budget_state(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: summary[key]
        for key in (
            "calls",
            "started_epoch",
            "generated_tokens",
            "total_tokens",
            "observed_generated_tokens",
            "observed_total_tokens",
            "usage_assessed",
            "reserved_generated_tokens",
            "reserved_total_tokens",
            "unknown_consumption",
            "pending",
            "halted",
            "blocked",
            "request_ids",
            "completed_request_ids",
            "trials",
        )
    }


def _stamp() -> str:
    return datetime.now(UTC).isoformat()


def _positive(value: Any, name: str, maximum: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise ValueError(f"{name} must be positive and at most {maximum}")


@lru_cache(maxsize=1)
def _boot_identity() -> str:
    """Read one stable boot identity on explicit campaign use, never on import."""
    if sys.platform == "win32":
        value = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"
                ".ToUniversalTime().ToString('o')",
            ],
            text=True,
            timeout=20,
        ).strip()
    elif sys.platform.startswith("linux"):
        value = Path("/proc/sys/kernel/random/boot_id").read_text("ascii").strip()
    elif sys.platform == "darwin":
        value = subprocess.check_output(
            ["sysctl", "-n", "kern.boottime"], text=True, timeout=20
        ).strip()
    else:
        raise ClientBlocked("campaign boot identity unavailable")
    if not value:
        raise ClientBlocked("campaign boot identity empty")
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class ModelProfile:
    tag: str
    digest: str
    think: bool | str | None = False
    thinking_values: tuple[bool | str, ...] = (False, True)
    num_ctx: int = 4096
    num_predict: int = 512
    temperature: float = 0.0
    keep_alive: str = "5m"
    local_verified: bool = True
    request_wall_seconds: float | None = None
    trial_wall_seconds: float | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tag, str)
            or not re.fullmatch(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+", self.tag)
            or self.tag.lower().endswith(":latest")
            or "cloud" in self.tag.lower()
        ):
            raise ValueError("model must have an exact, local, non-cloud tag")
        if not re.fullmatch(r"[0-9a-f]{64}", self.digest):
            raise ValueError("model digest must be lower-case SHA256 hex")
        if self.local_verified is not True:
            raise ValueError("host must verify the model is local before creating its profile")
        if any(type(item) not in (bool, str) or item == "" for item in self.thinking_values):
            raise ValueError("thinking_values must be the exact supported boolean/string values")
        if self.think is not None and not any(
            type(self.think) is type(item) and self.think == item for item in self.thinking_values
        ):
            raise ValueError("unsupported think value; no silent fallback")
        for name, maximum in (("num_ctx", 16384), ("num_predict", 4096)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError(f"{name} must be an integer in 1..{maximum}")
        if type(self.temperature) not in (int, float) or self.temperature != 0:
            raise ValueError("this experiment fixes temperature to zero")
        if not isinstance(self.keep_alive, str) or not re.fullmatch(
            r"[0-9]+[smh]?", self.keep_alive
        ):
            raise ValueError("keep_alive must be an explicit bounded duration")
        if self.request_wall_seconds is not None:
            _positive(self.request_wall_seconds, "model request deadline", 3600)
        if self.trial_wall_seconds is not None:
            _positive(self.trial_wall_seconds, "model trial deadline", 14400)


@dataclass(frozen=True)
class Limits:
    global_wall_seconds: float = 14_400
    global_calls: int = 1200
    global_generated_tokens: int = 600_000
    global_total_tokens: int = 5_000_000
    trial_wall_seconds: float = 600
    trial_calls: int = 6
    trial_total_tokens: int = 27_648
    request_wall_seconds: float = 120
    maximum_request_wall_seconds: float = 180
    socket_timeout_seconds: float = 15
    max_response_bytes: int = 1_048_576
    max_request_bytes: int = 262_144
    max_disk_bytes: int = 536_870_912
    connect_timeout_seconds: float = 30
    read_until_deadline: bool = False

    def __post_init__(self) -> None:
        maximums = {
            "global_wall_seconds": 172_800,
            "global_calls": 4000,
            "global_generated_tokens": 4_000_000,
            "global_total_tokens": 40_000_000,
            "trial_wall_seconds": 14400,
            "trial_calls": 12,
            "trial_total_tokens": 245760,
            "request_wall_seconds": 3600,
            "maximum_request_wall_seconds": 3600,
            "socket_timeout_seconds": 3600,
            "max_response_bytes": 1_048_576,
            "max_request_bytes": 262_144,
            "max_disk_bytes": 4_294_967_296,
            "connect_timeout_seconds": 30,
        }
        for name, maximum in maximums.items():
            value = getattr(self, name)
            _positive(value, name, maximum)
            if name.endswith(("calls", "tokens", "bytes")) and type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.request_wall_seconds > self.maximum_request_wall_seconds:
            raise ValueError("normal request deadline exceeds its maximum")
        if type(self.read_until_deadline) is not bool:
            raise ValueError("read_until_deadline must be explicit boolean")


_DEFAULT_LIMITS = Limits()


def _endpoint(base_url: str) -> tuple[str, int]:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("endpoint must be a plain local HTTP origin")
    try:
        host = parsed.hostname or ""
        address = ipaddress.ip_address(host)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("endpoint requires a numeric loopback address and port") from exc
    if not address.is_loopback or port is None or not 1 <= port <= 65535:
        raise ValueError("endpoint requires a numeric loopback address and port")
    return str(address), port


def _basic_schema(value: Any, schema: Mapping[str, Any]) -> None:
    """Small explicit schema subset; complex schemas require the host validator."""
    kind = schema.get("type")
    types = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: type(item) is int,
        "number": lambda item: type(item) in (int, float),
        "boolean": lambda item: type(item) is bool,
        "null": lambda item: item is None,
    }
    if kind not in types or not types[kind](value):
        raise ValueError("schema type mismatch")
    if "enum" in schema and not any(
        type(value) is type(item) and value == item for item in schema["enum"]
    ):
        raise ValueError("schema enum mismatch")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if any(key not in value for key in schema.get("required", [])):
            raise ValueError("missing required field")
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            raise ValueError("unexpected field")
        for key in set(value) & set(properties):
            _basic_schema(value[key], properties[key])
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", math.inf):
            raise ValueError("array length mismatch")
        for item in value:
            _basic_schema(item, schema["items"])


def _check_schema_subset(schema: Mapping[str, Any]) -> None:
    allowed = {
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "items",
        "minItems",
        "maxItems",
    }
    if set(schema) - allowed or schema.get("type") not in {
        "object",
        "array",
        "string",
        "integer",
        "number",
        "boolean",
        "null",
    }:
        raise ValueError("complex JSON schema requires an explicit host validator")
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        raise ValueError("complex JSON schema requires an explicit host validator")
    for child in schema.get("properties", {}).values():
        _check_schema_subset(child)
    if "items" in schema:
        _check_schema_subset(schema["items"])


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        ledger_path: Path,
        *,
        run_id: str,
        freeze_id: str,
        profiles: Mapping[str, ModelProfile],
        limits: Limits = _DEFAULT_LIMITS,
        disk_root: Path | None = None,
        server_version: str = SUPPORTED_SERVER_VERSION,
        server_epoch: str | None = None,
        termination_policy: bool = False,
    ) -> None:
        self.host, self.port = _endpoint(base_url)
        if server_version != SUPPORTED_SERVER_VERSION:
            raise ValueError(
                "host preflight must verify Ollama 0.35.0 chat truncate/shift controls"
            )
        if not run_id or not freeze_id or not profiles:
            raise ValueError("run/freeze identities and verified profiles are required")
        if any(key != profile.tag for key, profile in profiles.items()):
            raise ValueError("profile keys must be the exact model tags")
        self.profiles = dict(profiles)
        self.limits = limits
        self.path = Path(ledger_path)
        self.disk_root = Path(disk_root) if disk_root is not None else self.path.parent
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.resolve().is_relative_to(self.disk_root.resolve()):
            raise ValueError("ledger must be inside the measured disk root")
        self._thread_lock = threading.Lock()
        self.config = {
            "schema_version": "1",
            "run_id": run_id,
            "freeze_id": freeze_id,
            "endpoint": {"host": self.host, "port": self.port},
            "profiles": {key: asdict(value) for key, value in sorted(self.profiles.items())},
            "limits": asdict(limits),
            "server_version": server_version,
            "context_policy": {
                "truncate": False,
                "shift": False,
                "local_tokenizer_available": False,
                "input_tokens": None,
                "truncation_observed": None,
                "enforcement": "pinned server rejects over-context input; no local token estimate",
            },
        }
        if termination_policy:
            if not run_id.startswith("egr-024-") or not server_epoch:
                raise ValueError("termination recovery requires a new v0.2.4 campaign")
            self.config["termination_policy"] = "retain-full-reservation-max-two-v1"
            self.config["server_epoch"] = server_epoch
        with self._locked():
            rows = self._rows()
            if not rows:
                self._append(
                    {
                        "event": "config",
                        "config": self.config,
                        "created_at": _stamp(),
                        "started_epoch": time.time(),
                    }
                )
            else:
                self._assert_identity(rows)
                self._summary(rows)
        self._created_monotonic = time.monotonic()
        self._created_epoch = time.time()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if not self._thread_lock.acquire(blocking=False):
            raise ClientBlocked("another request is in flight")
        lock_file = None
        acquired = False
        try:
            lock_file = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
            if lock_file.seek(0, os.SEEK_END) == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            try:
                if sys.platform == "win32":
                    import msvcrt

                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                raise ClientBlocked("another client holds the ledger lock") from exc
            yield
        finally:
            if lock_file is not None:
                if acquired:
                    lock_file.seek(0)
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            self._thread_lock.release()

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        if self.path.stat().st_size > self.limits.max_disk_bytes:
            raise ClientBlocked("ledger exceeds disk envelope")
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise ClientBlocked("incomplete ledger tail; retain it and do not retry")
        try:
            rows = [strict_json(line.decode("utf-8")) for line in raw.splitlines()]
            if not all(isinstance(row, dict) for row in rows):
                raise ValueError("non-object ledger record")
            if rows and rows[0].get("event") != "config":
                raise ValueError("ledger does not begin with its frozen config")
            return rows
        except (ValueError, RecursionError, UnicodeError) as exc:
            raise ClientBlocked("ledger is invalid; retain it and do not retry") from exc

    def _disk_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.disk_root.rglob("*") if path.is_file())

    def _append(self, row: Mapping[str, Any]) -> None:
        encoded = _bytes(row) + b"\n"
        if self._disk_bytes() + len(encoded) > self.limits.max_disk_bytes:
            raise ClientBlocked("disk envelope cannot retain the next ledger record")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            position = 0
            while position < len(encoded):
                position += os.write(fd, encoded[position:])
            os.fsync(fd)
        finally:
            os.close(fd)

    def _effective_config(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        initial_config = rows[0].get("config") if rows else None
        if not isinstance(initial_config, dict):
            raise ClientBlocked("ledger does not contain its original config")
        effective: dict[str, Any] = initial_config
        seen_amendment = False
        expected_fields = {
            "event",
            "schema_version",
            "amendment_id",
            "created_at",
            "authorization",
            "from_config_sha256",
            "to_config_sha256",
            "prior_events_canonical_sha256",
            "prior_event_count",
            "config",
            "retained_budget_state",
        }
        for index, row in enumerate(rows[1:], start=1):
            if row.get("event") == "server_epoch":
                new_config = {**effective, "server_epoch": row.get("server_epoch")}
                prior = self._summary(rows[:index])
                if (
                    effective.get("termination_policy") != "retain-full-reservation-max-two-v1"
                    or not prior.get("terminated_unmetered")
                    or row.get("prior_events_canonical_sha256") != _canonical_sha256(rows[:index])
                    or row.get("from_config_sha256") != _canonical_sha256(effective)
                    or not isinstance(row.get("server_epoch"), str)
                    or not row["server_epoch"]
                    or row["server_epoch"] == effective.get("server_epoch")
                    or row.get("stop_request_id") != prior["terminated_unmetered"][-1]
                    or any(r.get("stop_request_id") == row["stop_request_id"] for r in rows[:index])
                ):
                    raise ClientBlocked("invalid server epoch transition")
                effective = new_config
                continue
            if row.get("event") != "wall_budget_amendment":
                continue
            try:
                if seen_amendment or set(row) != expected_fields or row["schema_version"] != "1":
                    raise ValueError("invalid or repeated amendment")
                if (
                    not isinstance(row["amendment_id"], str)
                    or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", row["amendment_id"])
                    or not isinstance(row["authorization"], str)
                    or not row["authorization"].strip()
                    or len(row["authorization"]) > 1024
                    or not isinstance(row["created_at"], str)
                    or datetime.fromisoformat(row["created_at"]).tzinfo is None
                    or type(row["prior_event_count"]) is not int
                    or row["prior_event_count"] != index
                ):
                    raise ValueError("invalid amendment identity or authorization record")
                new_config = row["config"]
                if not isinstance(new_config, dict):
                    raise ValueError("amended config must be an object")
                expected = _wall_amended_config(
                    effective, new_config["run_id"], new_config["freeze_id"]
                )
                if (
                    _canonical_sha256(new_config) != _canonical_sha256(expected)
                    or row["from_config_sha256"] != _canonical_sha256(effective)
                    or row["to_config_sha256"] != _canonical_sha256(expected)
                    or row["prior_events_canonical_sha256"] != _canonical_sha256(rows[:index])
                    or row["retained_budget_state"]
                    != _retained_budget_state(self._summary(rows[:index]))
                ):
                    raise ValueError("amendment changed frozen config or retained history")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ClientBlocked("invalid wall-budget amendment; retain ledger") from exc
            effective = new_config
            seen_amendment = True
        return effective

    def _assert_identity(self, rows: list[dict[str, Any]]) -> None:
        if _canonical_sha256(self._effective_config(rows)) != _canonical_sha256(self.config):
            raise ClientBlocked("run/freeze/profile/limit identity differs from existing ledger")

    def amend_global_wall_budget(
        self,
        *,
        amendment_id: str,
        new_run_id: str,
        new_freeze_id: str,
        authorization: str,
    ) -> dict[str, Any]:
        """Record the explicit 4h-to-8h authorization without resetting any consumption.

        The host establishes the user's authorization. This method records it; it
        cannot authenticate a human instruction. Reopen with the new identity after
        this durable one-time event. Pending consumption remains blocked.
        """
        if (
            not isinstance(amendment_id, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", amendment_id)
            or not isinstance(authorization, str)
            or not authorization.strip()
            or len(authorization) > 1024
        ):
            raise ValueError("an explicit amendment identity and authorization are required")
        new_config = _wall_amended_config(self.config, new_run_id, new_freeze_id)
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            if any(row.get("event") == "wall_budget_amendment" for row in rows[1:]):
                raise ClientBlocked("wall-budget amendment already recorded")
            summary = self._summary(rows)
            amendment = {
                "event": "wall_budget_amendment",
                "schema_version": "1",
                "amendment_id": amendment_id,
                "created_at": _stamp(),
                "authorization": authorization,
                "from_config_sha256": _canonical_sha256(self.config),
                "to_config_sha256": _canonical_sha256(new_config),
                "prior_events_canonical_sha256": _canonical_sha256(rows),
                "prior_event_count": len(rows),
                "config": new_config,
                "retained_budget_state": _retained_budget_state(summary),
            }
            self._append(amendment)
            return amendment

    def _summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        effective_config = self._effective_config(rows)
        reservations: dict[str, dict[str, Any]] = {}
        responses: dict[str, dict[str, Any]] = {}
        terminated: dict[str, dict[str, Any]] = {}
        for row in rows[1:]:
            if row.get("event") in ("wall_budget_amendment", "server_epoch"):
                continue
            key = row.get("request_id")
            if not isinstance(key, str) or not key:
                raise ClientBlocked("ledger contains an invalid request identity")
            event = row.get("event")
            if event == "reserve" and key not in reservations:
                reservations[key] = row
            elif event == "response" and key in reservations and key not in responses:
                responses[key] = row["record"]
            elif event == "terminated_unmetered" and key in reservations and key not in terminated:
                reserve = reservations[key]
                proof = row.get("proof", {})
                if (
                    not effective_config.get("termination_policy")
                    or len(terminated) >= 2
                    or (key in responses and not responses[key].get("unknown_consumption"))
                    or proof.get("tree_stopped") is not True
                    or not proof.get("identities")
                    or proof.get("proof_method") != "held-native-process-handles"
                    or row.get("server_epoch") != reserve.get("server_epoch")
                    or proof.get("server_epoch") != row.get("server_epoch")
                    or row.get("charged_generated_tokens") != reserve["reserved_generated_tokens"]
                    or row.get("charged_total_tokens") != reserve["reserved_total_tokens"]
                    or row.get("actual_usage") is not None
                    or row.get("bound_evidence") != "ollama-0.35.0-no-shift-explicit-ctx-predict"
                ):
                    raise ClientBlocked("unproven termination or consumption bound")
                identities = proof["identities"]
                if (
                    not isinstance(identities, list)
                    or len({i.get("pid") for i in identities}) != len(identities)
                    or any(
                        type(i.get("pid")) is not int
                        or i["pid"] < 1
                        or type(i.get("creation_filetime")) is not int
                        or i["creation_filetime"] < 1
                        or not isinstance(i.get("executable_sha256"), str)
                        or re.fullmatch(r"[0-9a-f]{64}", i["executable_sha256"]) is None
                        or i.get("executable_name", "").lower()
                        not in ("ollama.exe", "llama-server.exe", "conhost.exe")
                        for i in identities
                    )
                ):
                    raise ClientBlocked("invalid termination identity proof")
                terminated[key] = row
            else:
                raise ClientBlocked("ledger request/response order or identity collision")
        uncertain = [
            key for key in reservations if key not in responses or responses[key]["pending"]
        ]
        pending = [key for key in uncertain if key not in terminated]
        needs_epoch = bool(terminated) and (
            terminated[next(reversed(terminated))]["server_epoch"]
            == effective_config.get("server_epoch")
        )
        generated = 0
        total = 0
        reserved_generated = 0
        reserved_total = 0
        trials: dict[str, dict[str, Any]] = {}
        halted: list[str] = []
        for key, reservation in reservations.items():
            trial = trials.setdefault(
                reservation["trial_id"],
                {
                    "calls": 0,
                    "generated_tokens": 0,
                    "total_tokens": 0,
                    "reserved_generated_tokens": 0,
                    "reserved_total_tokens": 0,
                    "started_epoch": reservation["started_epoch"],
                },
            )
            trial["calls"] += 1
            response = responses.get(key)
            if response is None or response["unknown_consumption"]:
                reserved_generated += reservation["reserved_generated_tokens"]
                reserved_total += reservation["reserved_total_tokens"]
                trial["reserved_generated_tokens"] += reservation["reserved_generated_tokens"]
                trial["reserved_total_tokens"] += reservation["reserved_total_tokens"]
            else:
                actual_generated = response["usage"]["generated_tokens"]
                actual_total = response["usage"]["total_tokens"]
                generated += actual_generated
                total += actual_total
                trial["generated_tokens"] += actual_generated
                trial["total_tokens"] += actual_total
            if response is not None and response.get("halt"):
                halted.append(key)
        return {
            "run_id": effective_config["run_id"],
            "freeze_id": effective_config["freeze_id"],
            "calls": len(reservations),
            "started_epoch": next(iter(reservations.values()))["started_epoch"]
            if reservations
            else None,
            "generated_tokens": None if uncertain else generated,
            "total_tokens": None if uncertain else total,
            "charged_generated_tokens": generated + reserved_generated,
            "charged_total_tokens": total + reserved_total,
            "observed_generated_tokens": generated,
            "observed_total_tokens": total,
            "usage_assessed": not bool(uncertain),
            "reserved_generated_tokens": reserved_generated,
            "reserved_total_tokens": reserved_total,
            "unknown_consumption": bool(uncertain),
            "terminated_unmetered": list(terminated),
            "terminated_trial_ids": [reservations[k]["trial_id"] for k in terminated],
            "pending": pending,
            "halted": halted,
            "needs_server_epoch": needs_epoch,
            "blocked": bool(pending or halted or needs_epoch),
            "request_ids": list(reservations),
            "completed_request_ids": [key for key in responses if not responses[key]["pending"]],
            "trials": trials,
            "limits": effective_config["limits"],
            "initial_config": rows[0]["config"],
            "wall_budget_amendments": [
                row for row in rows[1:] if row.get("event") == "wall_budget_amendment"
            ],
            "responses": responses,
        }

    def summary(self) -> dict[str, Any]:
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            summary = self._summary(rows)
            if summary["started_epoch"] is not None:
                summary["campaign_elapsed_seconds"] = (
                    self._campaign_epoch(rows) - summary["started_epoch"]
                )
            else:
                summary["campaign_elapsed_seconds"] = 0.0
            return summary

    def _campaign_epoch(self, rows: list[dict[str, Any]]) -> float:
        """Keep paused time and a same-boot monotonic lower bound across processes."""
        observed = max(
            time.time(), self._created_epoch + time.monotonic() - self._created_monotonic
        )
        if not self.config.get("termination_policy"):
            return observed
        first = next((r["started_epoch"] for r in rows if r.get("event") == "reserve"), None)
        if first is None:
            return observed
        clock_path = self.path.with_suffix(".clock.json")
        if not clock_path.exists():
            last = max(
                [first]
                + [r.get("started_epoch", first) for r in rows if r.get("event") == "reserve"]
                + [
                    datetime.fromisoformat(r["record"]["ended_at"]).timestamp()
                    for r in rows
                    if r.get("event") == "response"
                ]
            )
            if observed < last:
                raise ClientBlocked("clock precedes the existing campaign; no new anchor")
            prefix = self.path.read_bytes()
            anchor = {
                "first_reservation_epoch": first,
                "anchor_epoch": observed,
                "elapsed_seconds": observed - first,
                "anchor_monotonic": time.monotonic(),
                "boot_identity": _boot_identity(),
                "prefix_bytes": len(prefix),
                "prefix_sha256": hashlib.sha256(prefix).hexdigest(),
            }
            with clock_path.open("xb") as handle:
                handle.write(_bytes(anchor))
                handle.flush()
                os.fsync(handle.fileno())
        if clock_path.stat().st_size > 4096:
            raise ClientBlocked("clock anchor exceeds its finite envelope")
        anchor = strict_json(clock_path.read_text("utf-8"))
        if (
            anchor["first_reservation_epoch"] != first
            or anchor["boot_identity"] != _boot_identity()
            or type(anchor["prefix_bytes"]) is not int
            or not 0 < anchor["prefix_bytes"] <= self.path.stat().st_size
            or any(
                type(anchor.get(k)) not in (int, float)
                or not math.isfinite(anchor[k])
                or anchor[k] < 0
                for k in ("elapsed_seconds", "anchor_monotonic", "anchor_epoch")
            )
        ):
            raise ClientBlocked("clock anchor or boot identity differs; no restart reset")
        with self.path.open("rb") as handle:
            prefix = handle.read(anchor["prefix_bytes"])
        if hashlib.sha256(prefix).hexdigest() != anchor["prefix_sha256"]:
            raise ClientBlocked("clock's exact retained ledger prefix differs")
        monotonic_elapsed = time.monotonic() - anchor["anchor_monotonic"]
        if monotonic_elapsed < 0:
            raise ClientBlocked("monotonic clock precedes the durable campaign anchor")
        return max(observed, first + anchor["elapsed_seconds"] + monotonic_elapsed)

    def record(self, request_id: str) -> dict[str, Any] | None:
        """Read an existing result without retrying, replaying, or sharing a live response."""
        record = self.summary()["responses"].get(request_id)
        if record is not None and not isinstance(record, dict):
            raise ClientBlocked("ledger response must be an object")
        return record

    def lookup(self, request_id: str) -> dict[str, Any] | None:
        """Alias for settling a persisted SDK attempt from its already completed HTTP record."""
        return self.record(request_id)

    def chat(
        self,
        *,
        model: str,
        trial_id: str,
        request_id: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        seed: int,
        metadata: dict[str, Any] | None = None,
        validator: Callable[[dict[str, Any]], Any] | None = None,
        wall_seconds: float | None = None,
        num_predict: int | None = None,
        preload: bool = False,
    ) -> dict[str, Any]:
        if model not in self.profiles:
            raise ValueError("model was not verified in the frozen profile set")
        profile = self.profiles[model]
        if not request_id or not trial_id or type(seed) is not int or seed < 0:
            raise ValueError("request/trial identity and nonnegative integer seed are required")
        if (not messages and not preload) or any(
            set(message) != {"role", "content"}
            or message["role"] not in ("system", "user", "assistant")
            or not isinstance(message["content"], str)
            for message in messages
        ):
            raise ValueError("messages must contain only explicit text role/content pairs")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("an explicit object JSON schema is required")
        if validator is None:
            _check_schema_subset(schema)
        requested_wall = (
            profile.request_wall_seconds or self.limits.request_wall_seconds
            if wall_seconds is None
            else wall_seconds
        )
        _positive(requested_wall, "request wall deadline", self.limits.maximum_request_wall_seconds)
        if num_predict is not None:
            if type(num_predict) is not int or not 0 < num_predict <= profile.num_predict:
                raise ValueError("stage output cap must fit the frozen profile")
            profile = replace(profile, num_predict=num_predict)
        if type(preload) is not bool or (preload and messages):
            raise ValueError("preload requires an explicit empty message list")
        request = {
            "model": profile.tag,
            "messages": messages,
            "stream": False,
            "format": schema,
            "think": profile.think,
            "truncate": False,
            "shift": False,
            "keep_alive": profile.keep_alive,
            "options": {
                "temperature": profile.temperature,
                "seed": seed,
                "num_ctx": profile.num_ctx,
                "num_predict": profile.num_predict,
            },
        }
        body = _bytes(request)
        if len(body) > self.limits.max_request_bytes:
            raise ValueError("request byte envelope exceeded")
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            summary = self._summary(rows)
            if summary["blocked"]:
                raise ClientBlocked("pending/unknown consumption or profile violation; no retry")
            if request_id in summary["request_ids"]:
                raise ClientBlocked(
                    "request identity already issued; use record(), not a live retry"
                )
            if trial_id in summary["terminated_trial_ids"]:
                raise ClientBlocked("terminated primary trial cannot be retried")
            now = self._campaign_epoch(rows)
            start = summary["started_epoch"] if summary["started_epoch"] is not None else now
            if now < start:
                raise ClientBlocked("wall clock precedes the ledger start")
            trial = summary["trials"].get(trial_id, {})
            remaining_wall = min(
                self.limits.global_wall_seconds - (now - start),
                min(
                    self.limits.trial_wall_seconds,
                    profile.trial_wall_seconds or self.limits.trial_wall_seconds,
                )
                - (now - trial.get("started_epoch", now)),
            )
            gen_reserve = profile.num_predict
            total_reserve = profile.num_ctx + profile.num_predict
            if (
                summary["calls"] >= self.limits.global_calls
                or trial.get("calls", 0) >= self.limits.trial_calls
                or summary["charged_generated_tokens"] + gen_reserve
                > self.limits.global_generated_tokens
                or summary["charged_total_tokens"] + total_reserve > self.limits.global_total_tokens
                or trial.get("total_tokens", 0)
                + trial.get("reserved_total_tokens", 0)
                + total_reserve
                > self.limits.trial_total_tokens
                or remaining_wall <= 0
            ):
                raise ClientBlocked("global or trial wall/call/token envelope exhausted")
            # Bound every retained copy/escape of the response and fixed-size status metadata.
            disk_reserve = 20 * self.limits.max_response_bytes + 6 * len(body) + 65_536
            if self._disk_bytes() + disk_reserve > self.limits.max_disk_bytes:
                raise ClientBlocked("disk envelope cannot reserve a bounded response")
            if len(_bytes(metadata or {})) > 16_384:
                raise ValueError("sanitized request metadata exceeds 16 KiB")
            reservation = {
                "event": "reserve",
                "request_id": request_id,
                "trial_id": trial_id,
                "started_at": _stamp(),
                "started_epoch": now,
                "reserved_generated_tokens": gen_reserve,
                "reserved_total_tokens": total_reserve,
                "reserved_response_bytes": disk_reserve,
                "request": request,
                "request_sha256": hashlib.sha256(body).hexdigest(),
                "metadata": metadata or {},
                "wall_seconds": min(requested_wall, remaining_wall),
                "operation": "preload" if preload else "generation",
                "server_epoch": self.config.get("server_epoch"),
            }
            self._append(
                reservation
            )  # Durable issuance precedes every possible network side effect.
            self._campaign_epoch([*rows, reservation])
            record = self._dispatch(body, profile, reservation, validator)
            self._append({"event": "response", "request_id": request_id, "record": record})
            return record

    def _dispatch(
        self,
        body: bytes,
        profile: ModelProfile,
        reservation: dict[str, Any],
        validator: Callable[[dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        began = time.monotonic()
        observed_epoch = max(time.time(), self._created_epoch + began - self._created_monotonic)
        issuance_elapsed = max(0, observed_epoch - reservation["started_epoch"])
        deadline: float = began + max(0, reservation["wall_seconds"] - issuance_elapsed)
        connection: http.client.HTTPConnection | None = None
        read_socket: socket.socket | None = None
        raw = bytearray()
        http_status = None
        headers: dict[str, str | None] = {}
        transport_error: str | None = None

        def remaining() -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise TimeoutError("request wall deadline")
            return (
                value
                if self.limits.read_until_deadline
                else min(self.limits.socket_timeout_seconds, value)
            )

        try:
            # http.client connects directly and ignores all environment proxy variables.
            connection = http.client.HTTPConnection(
                self.host, self.port, timeout=min(self.limits.connect_timeout_seconds, remaining())
            )
            connection.connect()
            assert connection.sock is not None
            connection.sock.settimeout(remaining())
            connection.request(
                "POST",
                "/api/chat",
                body=body,
                headers={"Content-Type": "application/json", "Connection": "close"},
            )
            assert connection.sock is not None
            read_socket = connection.sock
            read_socket.settimeout(remaining())
            response = connection.getresponse()
            http_status = response.status
            declared = response.getheader("Content-Length")
            content_type = response.getheader("Content-Type")
            headers = {
                "content_type": None if content_type is None else content_type[:1024],
                "content_length": None if declared is None else declared[:1024],
            }
            if declared is not None and int(declared) < 0:
                raise ValueError("negative Content-Length")
            if declared is not None and int(declared) > self.limits.max_response_bytes:
                transport_error = "response_too_large"
            else:
                while True:
                    read_socket.settimeout(remaining())
                    chunk = response.read1(min(8192, self.limits.max_response_bytes + 1 - len(raw)))
                    if not chunk:
                        if declared is not None and len(raw) != int(declared):
                            transport_error = "disconnect"
                        break
                    raw.extend(chunk)
                    if len(raw) > self.limits.max_response_bytes:
                        transport_error = "response_too_large"
                        break
                    remaining()
                    if response.isclosed():
                        if declared is not None and len(raw) != int(declared):
                            transport_error = "disconnect"
                        break
        except TimeoutError:
            transport_error = "timeout"
        except (OSError, http.client.HTTPException):
            transport_error = "disconnect"
        except ValueError:
            transport_error = "response_metadata_error"
        finally:
            if connection is not None:
                connection.close()
        capture = {
            "request_id": reservation["request_id"],
            "request_sha256": reservation["request_sha256"],
            "raw_base64": base64.b64encode(raw).decode("ascii"),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "http_status": http_status,
            "transport_error": transport_error,
            "headers": headers,
            "client_wall_seconds": time.monotonic() - began,
            "ended_at": _stamp(),
        }
        path = self._capture_path(reservation["request_id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(_bytes(capture))
            handle.flush()
            os.fsync(handle.fileno())
        return self._captured_record(capture, reservation, profile, validator)

    def _capture_path(self, request_id: str) -> Path:
        return (
            self.path.parent
            / "receipts"
            / (hashlib.sha256(request_id.encode()).hexdigest() + ".json")
        )

    def _captured_record(
        self,
        capture: dict[str, Any],
        reservation: dict[str, Any],
        profile: ModelProfile,
        validator: Callable[[dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        raw = base64.b64decode(capture["raw_base64"], validate=True)
        if (
            capture["request_id"] != reservation["request_id"]
            or capture["request_sha256"] != reservation["request_sha256"]
            or hashlib.sha256(raw).hexdigest() != capture["raw_sha256"]
        ):
            raise ClientBlocked("durable receipt identity differs")
        record = self._interpret(
            raw,
            capture["http_status"],
            capture["transport_error"],
            profile,
            reservation["request"]["format"],
            validator,
        )
        # The pinned ChatHandler returns before Completion for an empty preload.
        # Missing counters on an ordinary generation response are never zero.
        if (
            reservation.get("operation") == "preload"
            and record["done_reason"] == "load"
            and record["done"] is True
            and record["returned_model"] == profile.tag
            and capture["http_status"] == 200
            and capture["transport_error"] is None
            and record["content"] in (None, "")
            and not record["thinking"]
            and all(v in (None, 0) for v in record["server_counters"].values())
        ):
            record.update(
                status="loaded",
                issues=[],
                parsed=None,
                pending=False,
                unknown_consumption=False,
                usage={"prompt_tokens": 0, "generated_tokens": 0, "total_tokens": 0},
                usage_basis="pinned-empty-ChatHandler-before-Completion",
            )
        record.update(
            {
                "request_id": reservation["request_id"],
                "trial_id": reservation["trial_id"],
                "model": profile.tag,
                "model_digest": profile.digest,
                "started_at": reservation["started_at"],
                "ended_at": capture["ended_at"],
                "client_wall_seconds": capture["client_wall_seconds"],
                "http_headers": capture["headers"],
                "request_sha256": reservation["request_sha256"],
                "reserved_generated_tokens": reservation["reserved_generated_tokens"],
                "reserved_total_tokens": reservation["reserved_total_tokens"],
            }
        )
        return record

    def recover_receipt(
        self,
        request_id: str,
        *,
        validator: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Settle an already captured final response without a network call."""
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            summary = self._summary(rows)
            if request_id in summary["terminated_unmetered"]:
                raise ClientBlocked("terminated primary cannot be relabeled as recovered")
            existing = summary["responses"].get(request_id)
            if existing is not None:
                return existing
            reserve = next(
                r for r in rows if r.get("event") == "reserve" and r["request_id"] == request_id
            )
            path = self._capture_path(request_id)
            if path.stat().st_size > 3 * self.limits.max_response_bytes + 16384:
                raise ClientBlocked("captured response exceeds envelope")
            capture = strict_json(path.read_text("utf-8"))
            profile = replace(
                self.profiles[reserve["request"]["model"]],
                num_predict=reserve["request"]["options"]["num_predict"],
            )
            record = self._captured_record(capture, reserve, profile, validator)
            self._append({"event": "response", "request_id": request_id, "record": record})
            return record

    def terminate_unmetered(self, request_id: str, proof: dict[str, Any]) -> dict[str, Any]:
        """Retain unknown actual usage and its full bound after verified process death."""
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            summary = self._summary(rows)
            if not self.config.get("termination_policy") or request_id not in summary["pending"]:
                raise ClientBlocked("no recoverable new-campaign pending request")
            reserve = next(
                r for r in rows if r.get("event") == "reserve" and r["request_id"] == request_id
            )
            marker = {
                "event": "terminated_unmetered",
                "request_id": request_id,
                "server_epoch": reserve["server_epoch"],
                "proof": proof,
                "actual_usage": None,
                "charged_generated_tokens": reserve["reserved_generated_tokens"],
                "charged_total_tokens": reserve["reserved_total_tokens"],
                "bound_evidence": "ollama-0.35.0-no-shift-explicit-ctx-predict",
                "created_at": _stamp(),
            }
            self._summary([*rows, marker])
            self._append(marker)
            return marker

    def advance_server_epoch(self, server_epoch: str) -> None:
        with self._locked():
            rows = self._rows()
            self._assert_identity(rows)
            summary = self._summary(rows)
            if summary["pending"] or summary["halted"] or not summary["terminated_unmetered"]:
                raise ClientBlocked("unproven termination prevents an epoch change")
            event = {
                "event": "server_epoch",
                "server_epoch": server_epoch,
                "stop_request_id": summary["terminated_unmetered"][-1],
                "prior_events_canonical_sha256": _canonical_sha256(rows),
                "from_config_sha256": _canonical_sha256(self.config),
                "created_at": _stamp(),
            }
            config = self._effective_config([*rows, event])
            self._append(event)
            self.config = config

    def _interpret(
        self,
        raw: bytes,
        http_status: int | None,
        transport_error: str | None,
        profile: ModelProfile,
        schema: dict[str, Any],
        validator: Callable[[dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        record: dict[str, Any] = {
            "status": "ok",
            "issues": [],
            "http_status": http_status,
            "raw_response_base64": base64.b64encode(raw).decode("ascii"),
            "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_response": None,
            "content": None,
            "thinking": None,
            "parsed": None,
            "returned_model": None,
            "done": None,
            "done_reason": None,
            "server_created_at": None,
            "durations_ns": dict.fromkeys(_DURATIONS),
            "durations_seconds": dict.fromkeys(_DURATIONS),
            "server_counters": dict.fromkeys(_COUNTERS),
            "usage": {"prompt_tokens": None, "generated_tokens": None, "total_tokens": None},
            "unknown_consumption": True,
            "pending": True,
            "halt": False,
        }
        issues: list[str] = record["issues"]
        if transport_error is not None:
            issues.append(transport_error)
        server: dict[str, Any] = {}
        try:
            text = raw.decode("utf-8")
            record["raw_response"] = text
            decoded = strict_json(text)
            if not isinstance(decoded, dict):
                raise ValueError("server response must be an object")
            server = decoded
        except (ValueError, RecursionError, UnicodeError) as exc:
            issues.append("response_json_error")
            if "nonfinite" in str(exc):
                issues.append("nonfinite_json")
            if "duplicate JSON key" in str(exc):
                issues.append("duplicate_json_key")
        error = str(server.get("error", "")).lower()
        if http_status == 503:
            issues.append("http_503")
        elif http_status != 200:
            issues.append("http_error")
        if (
            "out of memory" in error
            or "cannot allocate memory" in error
            or re.search(r"\boom\b", error)
        ):
            issues.append("oom")
        if "context length" in error or "context window" in error:
            issues.append("context_limit_error")
        if ("think" in error) and any(
            term in error for term in ("unsupported", "not support", "invalid")
        ):
            issues.append("unsupported_think")
        if server.get("error") and http_status == 200:
            issues.append("server_error")
        for key in _COUNTERS + _DURATIONS:
            value = server.get(key)
            if value is not None and (type(value) is not int or not 0 <= value <= 2**63 - 1):
                issues.append("response_metadata_error")
                value = None
            if key in _COUNTERS:
                record["server_counters"][key] = value
            else:
                record["durations_ns"][key] = value
                record["durations_seconds"][key] = None if value is None else value / 1_000_000_000
        record.update(
            {
                "returned_model": server.get("model"),
                "done": server.get("done"),
                "done_reason": server.get("done_reason"),
                "server_created_at": server.get("created_at"),
            }
        )
        if server and server.get("model") != profile.tag:
            issues.append("model_mismatch")
            record["halt"] = True
        prompt = record["server_counters"]["prompt_eval_count"]
        generated = record["server_counters"]["eval_count"]
        if prompt is None or generated is None:
            issues.append("missing_usage")
        elif transport_error is None and http_status == 200 and server.get("done") is True:
            record["usage"] = {
                "prompt_tokens": prompt,
                "generated_tokens": generated,
                "total_tokens": prompt + generated,
            }
            record["unknown_consumption"] = False
            record["pending"] = False
            if prompt > profile.num_ctx or generated > profile.num_predict:
                issues.append("token_cap_violation")
                record["halt"] = True
        if server and server.get("done") is not True:
            issues.append("incomplete_response")
        if server.get("done_reason") == "length":
            issues.append("length")
        message = server.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            thinking = message.get("thinking")
            if thinking is not None and not isinstance(thinking, str):
                issues.append("response_metadata_error")
            else:
                record["thinking"] = thinking
            if isinstance(content, str):
                record["content"] = content
                if not content.strip():
                    issues.append("empty_final")
                else:
                    try:
                        parsed = strict_json(content)
                    except (ValueError, RecursionError) as exc:
                        issues.append("final_json_error")
                        if "nonfinite" in str(exc):
                            issues.append("nonfinite_json")
                        if "duplicate JSON key" in str(exc):
                            issues.append("duplicate_json_key")
                    else:
                        try:
                            if not isinstance(parsed, dict):
                                raise ValueError("final JSON must be an object")
                            if validator is None:
                                _basic_schema(parsed, schema)
                            else:
                                validator(parsed)
                            record["parsed"] = parsed
                        except (ValueError, TypeError, RecursionError, KeyError):
                            issues.append("schema_error")
                        except Exception:
                            issues.append("validator_error")
            else:
                issues.append("empty_final")
        elif http_status == 200:
            issues.append("empty_final")
        priority = (
            "timeout",
            "disconnect",
            "response_too_large",
            "oom",
            "unsupported_think",
            "context_limit_error",
            "http_503",
            "http_error",
            "response_json_error",
            "model_mismatch",
            "token_cap_violation",
            "response_metadata_error",
            "missing_usage",
            "incomplete_response",
            "length",
            "empty_final",
            "final_json_error",
            "schema_error",
            "validator_error",
            "server_error",
        )
        issues[:] = list(dict.fromkeys(issues))
        record["status"] = next((name for name in priority if name in issues), "ok")
        return record
