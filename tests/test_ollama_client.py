"""Portable fake HTTP contracts; these tests are not live model measurements."""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.ollama.client import (
    ClientBlocked,
    Limits,
    ModelProfile,
    OllamaClient,
    strict_json,
)

TAG = "gemma4:e4b"
PROFILE = ModelProfile(TAG, "a" * 64, num_ctx=16, num_predict=8)
DEFAULT_LIMITS = Limits()
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


def successful(**changes: Any) -> dict[str, Any]:
    result = {
        "model": TAG,
        "created_at": "2026-10-05T00:00:00Z",
        "message": {"role": "assistant", "content": '{"answer":"yes"}', "thinking": "trace"},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 4,
        "prompt_eval_cached_count": 2,
        "eval_count": 2,
        "total_duration": 2_000_000_000,
        "load_duration": 500_000_000,
        "prompt_eval_duration": 250_000_000,
        "eval_duration": 1_000_000_000,
    }
    result.update(changes)
    return result


@contextmanager
def fake_http(
    payload: dict[str, Any] | bytes,
    *,
    status: int = 200,
    delay: float = 0,
    split_delay: float = 0,
    declared_length: int | None = None,
    omit_length: bool = False,
    ledger: Path | None = None,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    received: list[dict[str, Any]] = []
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            request = strict_json(self.rfile.read(int(self.headers["Content-Length"])).decode())
            observed = {"path": self.path, "request": request}
            if ledger is not None:
                observed["durable_rows"] = [
                    strict_json(line) for line in ledger.read_text().splitlines()
                ]
            received.append(observed)
            time.sleep(delay)
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                if not omit_length:
                    self.send_header(
                        "Content-Length",
                        str(len(body) if declared_length is None else declared_length),
                    )
                self.end_headers()
                if split_delay:
                    self.wfile.write(body[:1])
                    self.wfile.flush()
                    time.sleep(split_delay)
                    self.wfile.write(body[1:])
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def client(
    endpoint: str, tmp_path: Path, limits: Limits = DEFAULT_LIMITS, **kwargs: Any
) -> OllamaClient:
    return OllamaClient(
        endpoint,
        tmp_path / "requests.jsonl",
        run_id="test-run",
        freeze_id="test-freeze",
        profiles={TAG: PROFILE},
        limits=limits,
        **kwargs,
    )


def chat(
    connection: OllamaClient,
    request_id: str = "request-1",
    trial_id: str = "trial-1",
    **kwargs: Any,
) -> dict[str, Any]:
    return connection.chat(
        model=TAG,
        trial_id=trial_id,
        request_id=request_id,
        messages=[
            {"role": "system", "content": "Return only JSON."},
            {"role": "user", "content": "Is the short statement true?"},
        ],
        schema=SCHEMA,
        seed=17,
        **kwargs,
    )


def test_success_preserves_identity_raw_thinking_counts_and_ns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://invalid.example:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://invalid.example:1")
    path = tmp_path / "requests.jsonl"
    payload = successful(extra_server_field={"future": "metadata"})
    with fake_http(payload, ledger=path) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        result = chat(connection)
        assert result["status"] == "ok"
        assert result["parsed"] == {"answer": "yes"}
        assert result["content"] == '{"answer":"yes"}'
        assert result["thinking"] == "trace"
        assert result["model_digest"] == "a" * 64
        assert result["usage"] == {"prompt_tokens": 4, "generated_tokens": 2, "total_tokens": 6}
        assert result["durations_ns"]["total_duration"] == 2_000_000_000
        assert result["durations_seconds"]["total_duration"] == 2
        assert strict_json(result["raw_response"])["extra_server_field"] == {"future": "metadata"}
        assert base64.b64decode(result["raw_response_base64"]).decode() == result["raw_response"]
        sent = received[0]
        assert sent["path"] == "/api/chat"
        assert sent["durable_rows"][-1]["event"] == "reserve"
        assert sent["durable_rows"][-1]["reserved_total_tokens"] == 24
        assert sent["request"]["stream"] is False
        assert sent["request"]["think"] is False
        assert sent["request"]["truncate"] is False
        assert sent["request"]["shift"] is False
        assert sent["request"]["format"] == SCHEMA
        assert sent["request"]["options"] == {
            "temperature": 0,
            "seed": 17,
            "num_ctx": 16,
            "num_predict": 8,
        }
        assert connection.lookup("request-1") == result
        assert connection.summary()["reserved_total_tokens"] == 0
        assert connection.summary()["calls"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:11435",
        "http://localhost:11435",
        "http://0.0.0.0:11435",
        "http://192.168.1.1:11435",
        "https://127.0.0.1:11435",
        "http://127.0.0.1",
        "http://user:pass@127.0.0.1:11435",
        "http://127.0.0.1:11435/api/chat",
        "http://127.0.0.1:11435/?secret=x",
        "http://127.0.0.1:11435/#fragment",
    ],
)
def test_endpoint_is_numeric_loopback_only(url: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        client(url, tmp_path)
    assert not (tmp_path / "requests.jsonl").exists()


def test_ipv6_loopback_is_allowed_without_resolution(tmp_path: Path) -> None:
    connection = client("http://[::1]:11435", tmp_path)
    assert connection.host == "::1"


@pytest.mark.parametrize(
    "changes",
    [
        {"tag": "gemma4:latest"},
        {"tag": "gemma4:cloud"},
        {"tag": "https://model.example/name:tag"},
        {"local_verified": False},
        {"digest": "not-a-digest"},
        {"think": "medium"},
        {"think": 0},
        {"num_predict": -1},
        {"temperature": 0.5},
    ],
)
def test_profile_no_cloud_defaults_or_unsupported_think(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(PROFILE, **changes)


def test_pinned_server_version_required(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="0.35.0"):
        client("http://127.0.0.1:11435", tmp_path, server_version="0.34.0")


@pytest.mark.parametrize(
    "message,expected",
    [
        ({"role": "assistant", "content": '{"answer":2}'}, "schema_error"),
        ({"role": "assistant", "content": '{"answer":"yes","extra":1}'}, "schema_error"),
        ({"role": "assistant", "content": ""}, "empty_final"),
        ({"role": "assistant", "content": '{"answer":NaN}'}, "final_json_error"),
        ({"role": "assistant", "content": '{"answer":"yes","answer":"no"}'}, "final_json_error"),
    ],
)
def test_known_format_errors_are_paid_and_can_be_followed_by_a_new_request(
    tmp_path: Path, message: dict[str, str], expected: str
) -> None:
    with fake_http(successful(message=message)) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        result = chat(connection)
        assert result["status"] == expected
        assert result["usage"]["total_tokens"] == 6
        assert result["unknown_consumption"] is False
        chat(connection, "paid-new-request")
        assert len(received) == 2
        assert connection.summary()["total_tokens"] == 12


def test_host_validator_is_authoritative_for_pydantic_schema_refs(tmp_path: Path) -> None:
    def reject(_: dict[str, Any]) -> None:
        raise ValueError("host output schema failure")

    with fake_http(successful()) as (endpoint, _):
        result = chat(client(endpoint, tmp_path), validator=reject)
        assert result["status"] == "schema_error"
        assert result["usage"]["generated_tokens"] == 2
        assert result["parsed"] is None


def test_length_and_missing_optional_durations_are_distinct(tmp_path: Path) -> None:
    payload = successful(done_reason="length")
    del payload["load_duration"]
    del payload["prompt_eval_cached_count"]
    del payload["message"]["thinking"]
    with fake_http(payload) as (endpoint, _):
        result = chat(client(endpoint, tmp_path))
        assert result["status"] == "length"
        assert result["thinking"] is None
        assert result["durations_ns"]["load_duration"] is None
        assert result["durations_seconds"]["load_duration"] is None
        assert result["server_counters"]["prompt_eval_cached_count"] is None
        assert result["unknown_consumption"] is False


@pytest.mark.parametrize(
    "payload,status,expected",
    [
        (successful(eval_count=None), 200, "missing_usage"),
        (successful(done=False), 200, "incomplete_response"),
        ({"error": "server busy"}, 503, "http_503"),
        ({"error": "model does not support thinking"}, 400, "unsupported_think"),
        ({"error": "out of memory"}, 500, "oom"),
        ({"error": "input exceeds context length"}, 500, "context_limit_error"),
    ],
)
def test_unknown_consumption_freezes_all_trials_and_resume(
    tmp_path: Path, payload: dict[str, Any], status: int, expected: str
) -> None:
    with fake_http(payload, status=status) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        result = chat(connection)
        assert result["status"] == expected
        assert result["pending"] is True
        assert result["usage"]["total_tokens"] is None
        assert connection.summary()["reserved_total_tokens"] == 24
        assert connection.summary()["total_tokens"] is None
        assert connection.summary()["observed_total_tokens"] == 0
        with pytest.raises(ClientBlocked, match="pending/unknown"):
            chat(connection, "another-request", "different-trial")
        resumed = client(endpoint, tmp_path)
        assert resumed.lookup("request-1") == result
        with pytest.raises(ClientBlocked):
            chat(resumed, "third-request", "third-trial")
        assert len(received) == 1


@pytest.mark.parametrize(
    "raw", [b'{"model":"x","model":"y"}', b'{"value":NaN}', b'{"value":1e999}', b"\xff"]
)
def test_server_json_is_strict_and_raw_bytes_retained(tmp_path: Path, raw: bytes) -> None:
    with fake_http(raw) as (endpoint, _):
        result = chat(client(endpoint, tmp_path))
        assert result["status"] == "response_json_error"
        assert base64.b64decode(result["raw_response_base64"]) == raw
        assert result["pending"] is True


@pytest.mark.parametrize("counter", [True, -1, 1.2, 2**63])
def test_invalid_usage_never_becomes_zero(tmp_path: Path, counter: Any) -> None:
    with fake_http(successful(eval_count=counter)) as (endpoint, _):
        result = chat(client(endpoint, tmp_path))
        assert result["status"] == "response_metadata_error"
        assert result["usage"]["generated_tokens"] is None
        assert result["unknown_consumption"] is True


@pytest.mark.parametrize(
    "payload,expected",
    [
        (successful(eval_count=9), "token_cap_violation"),
        (successful(model="qwen3.6:35b-a3b"), "model_mismatch"),
    ],
)
def test_profile_violation_halts_with_actual_known_cost(
    tmp_path: Path, payload: dict[str, Any], expected: str
) -> None:
    with fake_http(payload) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        result = chat(connection)
        assert result["status"] == expected
        assert result["unknown_consumption"] is False
        assert connection.summary()["halted"] == ["request-1"]
        with pytest.raises(ClientBlocked):
            chat(connection, "second")
        assert len(received) == 1


@pytest.mark.parametrize("split", [False, True])
def test_socket_and_whole_request_deadlines_keep_unknown_pending(
    tmp_path: Path, split: bool
) -> None:
    with fake_http(successful(), delay=0 if split else 0.15, split_delay=0.15 if split else 0) as (
        endpoint,
        received,
    ):
        connection = client(
            endpoint, tmp_path, Limits(socket_timeout_seconds=1, request_wall_seconds=0.04)
        )
        began = time.monotonic()
        result = chat(connection)
        elapsed = time.monotonic() - began
        assert result["status"] == "timeout"
        assert result["pending"] is True
        assert elapsed < 0.5
        with pytest.raises(ClientBlocked):
            chat(connection, "second")
        assert len(received) == 1


def test_large_declared_body_is_not_read_and_unknown(tmp_path: Path) -> None:
    with fake_http(b"x" * 400, declared_length=400) as (endpoint, _):
        result = chat(client(endpoint, tmp_path, Limits(max_response_bytes=128)))
        assert result["status"] == "response_too_large"
        assert result["raw_response"] == ""
        assert result["pending"] is True


def test_body_without_content_length_is_read_only_to_the_bound(tmp_path: Path) -> None:
    with fake_http(b"x" * 400, omit_length=True) as (endpoint, _):
        result = chat(client(endpoint, tmp_path, Limits(max_response_bytes=128)))
        assert result["status"] == "response_too_large"
        assert len(base64.b64decode(result["raw_response_base64"])) == 129
        assert result["pending"] is True


def test_socket_timeout_is_distinct_from_the_larger_overall_deadline(tmp_path: Path) -> None:
    with fake_http(successful(), delay=0.15) as (endpoint, _):
        result = chat(
            client(endpoint, tmp_path, Limits(socket_timeout_seconds=0.03, request_wall_seconds=1))
        )
        assert result["status"] == "timeout"
        assert result["client_wall_seconds"] < 0.5
        assert result["pending"] is True


def test_reservation_durability_overhead_does_not_extend_request_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path, Limits(request_wall_seconds=0.04))
        original = connection._append

        def slow_durability(row: Any) -> None:
            original(row)
            if row["event"] == "reserve":
                time.sleep(0.08)

        monkeypatch.setattr(connection, "_append", slow_durability)
        result = chat(connection)
        assert result["status"] == "timeout"
        assert result["pending"] is True
        assert received == []


def test_unsupported_schema_without_host_validator_is_rejected_before_reservation(
    tmp_path: Path,
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        with pytest.raises(ValueError, match="host validator"):
            connection.chat(
                model=TAG,
                trial_id="trial",
                request_id="request",
                seed=1,
                messages=[{"role": "user", "content": "short"}],
                schema={"type": "object", "$ref": "#/$defs/Output"},
            )
        assert connection.summary()["calls"] == 0
        assert received == []


def test_partial_content_length_is_disconnect_not_completed(tmp_path: Path) -> None:
    body = json.dumps(successful()).encode()
    with fake_http(body, declared_length=len(body) + 10) as (endpoint, _):
        result = chat(client(endpoint, tmp_path))
        assert result["status"] == "disconnect"
        assert result["pending"] is True
        assert result["usage"]["total_tokens"] is None


def test_resume_completed_ids_are_never_redispatched(tmp_path: Path) -> None:
    with fake_http(successful()) as (endpoint, received):
        record = chat(client(endpoint, tmp_path))
        resumed = client(endpoint, tmp_path)
        assert resumed.lookup("request-1") == record
        with pytest.raises(ClientBlocked, match="already issued"):
            chat(resumed)
        assert len(received) == 1


def test_crash_after_durable_reserve_blocks_resume_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path)

        def crash(*_: Any) -> Any:
            raise RuntimeError("simulated process interruption")

        monkeypatch.setattr(connection, "_dispatch", crash)
        with pytest.raises(RuntimeError, match="interruption"):
            chat(connection)
        resumed = client(endpoint, tmp_path)
        assert resumed.summary()["pending"] == ["request-1"]
        assert resumed.lookup("request-1") is None
        with pytest.raises(ClientBlocked):
            chat(resumed, "second")
        assert received == []


def test_response_append_failure_retains_pending_and_complete_raw_does_not_imply_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path)
        original = connection._append

        def fail(row: Any) -> None:
            if row["event"] == "response":
                raise OSError("simulated disk failure")
            original(row)

        monkeypatch.setattr(connection, "_append", fail)
        with pytest.raises(OSError):
            chat(connection)
        resumed = client(endpoint, tmp_path)
        assert resumed.summary()["pending"] == ["request-1"]
        with pytest.raises(ClientBlocked):
            chat(resumed, "second")
        assert len(received) == 1


def test_torn_ledger_is_preserved_and_not_silently_repaired(tmp_path: Path) -> None:
    connection = client("http://127.0.0.1:11435", tmp_path)
    with connection.path.open("ab") as stream:
        stream.write(b'{"event":"reserve"')
    before = connection.path.read_bytes()
    with pytest.raises(ClientBlocked, match="incomplete ledger"):
        client("http://127.0.0.1:11435", tmp_path)
    assert connection.path.read_bytes() == before


def test_resume_rejects_profile_budget_or_freeze_changes(tmp_path: Path) -> None:
    endpoint = "http://127.0.0.1:11435"
    client(endpoint, tmp_path)
    with pytest.raises(ClientBlocked, match="identity differs"):
        client(endpoint, tmp_path, Limits(global_calls=1))
    with pytest.raises(ClientBlocked, match="identity differs"):
        OllamaClient(
            endpoint,
            tmp_path / "requests.jsonl",
            run_id="test-run",
            freeze_id="other",
            profiles={TAG: PROFILE},
        )


@pytest.mark.parametrize(
    "limits",
    [
        Limits(global_calls=1),
        Limits(trial_calls=1),
        Limits(global_generated_tokens=8),
        Limits(trial_total_tokens=24),
    ],
)
def test_call_and_conservative_token_budget_blocks_before_second_dispatch(
    tmp_path: Path, limits: Limits
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path, limits)
        chat(connection)
        with pytest.raises(ClientBlocked, match="envelope exhausted"):
            chat(connection, "second")
        assert len(received) == 1
        assert connection.summary()["calls"] == 1


def test_known_receipts_settle_reservation_without_token_refund_or_zero_unknown(
    tmp_path: Path,
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path, Limits(global_total_tokens=30))
        chat(connection)
        chat(connection, "second")
        with pytest.raises(ClientBlocked):
            chat(connection, "third")
        assert len(received) == 2
        assert connection.summary()["total_tokens"] == 12


def test_trial_budget_does_not_reset_under_same_id_and_global_budget_spans_trials(
    tmp_path: Path,
) -> None:
    with fake_http(successful()) as (endpoint, received):
        limits = Limits(global_calls=2, trial_calls=1)
        connection = client(endpoint, tmp_path, limits)
        chat(connection)
        with pytest.raises(ClientBlocked):
            chat(connection, "second", "trial-1")
        chat(connection, "second", "trial-2")
        with pytest.raises(ClientBlocked):
            chat(connection, "third", "trial-3")
        assert len(received) == 2


def test_global_wall_begins_first_reservation_and_resume_keeps_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path, Limits(global_wall_seconds=0.2))
        assert connection.summary()["started_epoch"] is None
        chat(connection)
        stamp = connection.summary()["started_epoch"]
        monkeypatch.setattr("experiments.ollama.client.time.time", lambda: stamp + 1)
        with pytest.raises(ClientBlocked, match="envelope exhausted"):
            chat(client(endpoint, tmp_path, Limits(global_wall_seconds=0.2)), "second")
        assert len(received) == 1


def test_disk_envelope_reserves_history_before_dispatch(tmp_path: Path) -> None:
    with fake_http(successful()) as (endpoint, received):
        connection = client(endpoint, tmp_path, Limits(max_disk_bytes=4096, max_response_bytes=16))
        with pytest.raises(ClientBlocked, match="disk envelope"):
            chat(connection)
        assert connection.summary()["calls"] == 0
        assert received == []


def test_two_clients_cannot_dispatch_concurrently(tmp_path: Path) -> None:
    with fake_http(successful()) as (endpoint, received):
        first = client(endpoint, tmp_path)
        second = client(endpoint, tmp_path)
        with first._locked(), pytest.raises(ClientBlocked, match="ledger lock"):
            chat(second)
        assert received == []


def test_validator_exception_is_paid_known_failure(tmp_path: Path) -> None:
    def fail(_: dict[str, Any]) -> Any:
        raise RuntimeError("implementation error")

    with fake_http(successful()) as (endpoint, _):
        result = chat(client(endpoint, tmp_path), validator=fail)
        assert result["status"] == "validator_error"
        assert result["unknown_consumption"] is False
