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
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
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


def _stamp() -> str:
    return datetime.now(UTC).isoformat()


def _positive(value: Any, name: str, maximum: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise ValueError(f"{name} must be positive and at most {maximum}")


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
        for name, maximum in (("num_ctx", 4096), ("num_predict", 512)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError(f"{name} must be an integer in 1..{maximum}")
        if type(self.temperature) not in (int, float) or self.temperature != 0:
            raise ValueError("this experiment fixes temperature to zero")
        if not isinstance(self.keep_alive, str) or not re.fullmatch(
            r"[0-9]+[smh]?", self.keep_alive
        ):
            raise ValueError("keep_alive must be an explicit bounded duration")


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

    def __post_init__(self) -> None:
        maximums = {
            "global_wall_seconds": 14_400,
            "global_calls": 1200,
            "global_generated_tokens": 600_000,
            "global_total_tokens": 5_000_000,
            "trial_wall_seconds": 600,
            "trial_calls": 6,
            "trial_total_tokens": 27_648,
            "request_wall_seconds": 120,
            "maximum_request_wall_seconds": 180,
            "socket_timeout_seconds": 180,
            "max_response_bytes": 1_048_576,
            "max_request_bytes": 262_144,
            "max_disk_bytes": 536_870_912,
        }
        for name, maximum in maximums.items():
            value = getattr(self, name)
            _positive(value, name, maximum)
            if name.endswith(("calls", "tokens", "bytes")) and type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.request_wall_seconds > self.maximum_request_wall_seconds:
            raise ValueError("normal request deadline exceeds its maximum")


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
            elif _bytes(rows[0].get("config")) != _bytes(self.config):
                raise ClientBlocked(
                    "run/freeze/profile/limit identity differs from existing ledger"
                )
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
                if os.name == "nt":
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
                    if os.name == "nt":
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

    def _summary(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        reservations: dict[str, dict[str, Any]] = {}
        responses: dict[str, dict[str, Any]] = {}
        for row in rows[1:]:
            key = row.get("request_id")
            if not isinstance(key, str) or not key:
                raise ClientBlocked("ledger contains an invalid request identity")
            event = row.get("event")
            if event == "reserve" and key not in reservations:
                reservations[key] = row
            elif event == "response" and key in reservations and key not in responses:
                responses[key] = row["record"]
            else:
                raise ClientBlocked("ledger request/response order or identity collision")
        pending = [key for key in reservations if key not in responses or responses[key]["pending"]]
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
            "run_id": self.config["run_id"],
            "freeze_id": self.config["freeze_id"],
            "calls": len(reservations),
            "started_epoch": next(iter(reservations.values()))["started_epoch"]
            if reservations
            else None,
            "generated_tokens": None if pending else generated,
            "total_tokens": None if pending else total,
            "observed_generated_tokens": generated,
            "observed_total_tokens": total,
            "usage_assessed": not bool(pending),
            "reserved_generated_tokens": reserved_generated,
            "reserved_total_tokens": reserved_total,
            "unknown_consumption": bool(pending),
            "pending": pending,
            "halted": halted,
            "blocked": bool(pending or halted),
            "request_ids": list(reservations),
            "completed_request_ids": [key for key in responses if not responses[key]["pending"]],
            "trials": trials,
            "limits": asdict(self.limits),
            "responses": responses,
        }

    def summary(self) -> dict[str, Any]:
        with self._locked():
            return self._summary(self._rows())

    def record(self, request_id: str) -> dict[str, Any] | None:
        """Read an existing result without retrying, replaying, or sharing a live response."""
        return self.summary()["responses"].get(request_id)

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
    ) -> dict[str, Any]:
        if model not in self.profiles:
            raise ValueError("model was not verified in the frozen profile set")
        profile = self.profiles[model]
        if not request_id or not trial_id or type(seed) is not int or seed < 0:
            raise ValueError("request/trial identity and nonnegative integer seed are required")
        if not messages or any(
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
        requested_wall = self.limits.request_wall_seconds if wall_seconds is None else wall_seconds
        _positive(requested_wall, "request wall deadline", self.limits.maximum_request_wall_seconds)
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
            summary = self._summary(rows)
            if summary["blocked"]:
                raise ClientBlocked("pending/unknown consumption or profile violation; no retry")
            if request_id in summary["request_ids"]:
                raise ClientBlocked(
                    "request identity already issued; use record(), not a live retry"
                )
            now = max(time.time(), self._created_epoch + time.monotonic() - self._created_monotonic)
            start = summary["started_epoch"] if summary["started_epoch"] is not None else now
            if now < start:
                raise ClientBlocked("wall clock precedes the ledger start")
            trial = summary["trials"].get(trial_id, {})
            remaining_wall = min(
                self.limits.global_wall_seconds - (now - start),
                self.limits.trial_wall_seconds - (now - trial.get("started_epoch", now)),
            )
            gen_reserve = profile.num_predict
            total_reserve = profile.num_ctx + profile.num_predict
            if (
                summary["calls"] >= self.limits.global_calls
                or trial.get("calls", 0) >= self.limits.trial_calls
                or summary["generated_tokens"] + gen_reserve > self.limits.global_generated_tokens
                or summary["total_tokens"] + total_reserve > self.limits.global_total_tokens
                or trial.get("total_tokens", 0) + total_reserve > self.limits.trial_total_tokens
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
            }
            self._append(
                reservation
            )  # Durable issuance precedes every possible network side effect.
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
        deadline = began + max(0, reservation["wall_seconds"] - issuance_elapsed)
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
            return min(self.limits.socket_timeout_seconds, value)

        try:
            # http.client connects directly and ignores all environment proxy variables.
            connection = http.client.HTTPConnection(self.host, self.port, timeout=remaining())
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
        record = self._interpret(
            bytes(raw),
            http_status,
            transport_error,
            profile,
            reservation["request"]["format"],
            validator,
        )
        record.update(
            {
                "request_id": reservation["request_id"],
                "trial_id": reservation["trial_id"],
                "model": profile.tag,
                "model_digest": profile.digest,
                "started_at": reservation["started_at"],
                "ended_at": _stamp(),
                "client_wall_seconds": time.monotonic() - began,
                "http_headers": headers,
                "request_sha256": reservation["request_sha256"],
                "reserved_generated_tokens": reservation["reserved_generated_tokens"],
                "reserved_total_tokens": reservation["reserved_total_tokens"],
            }
        )
        return record

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
