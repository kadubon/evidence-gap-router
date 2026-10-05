"""Metadata/resource preflight is separate from generation and preserves uncertainty."""

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.ollama import environment as env  # noqa: E402

ORIGIN = "http://127.0.0.1:11435"


def test_installed_capacity_sets_stricter_floor_than_os_visible_memory(monkeypatch):
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        env,
        "_windows_sample",
        lambda _pid: {
            "total_memory_bytes": 60 * 1024**3,
            "installed_memory_bytes": 64 * 1024**3,
            "available_memory_bytes": 64 * 1024**3 // 10,
            "processes": [],
        },
    )
    resources = env.collect_resources()
    assert resources["installed_memory_bytes"] == 64 * 1024**3
    assert resources["free_memory_floor_bytes"] == (64 * 1024**3 + 9) // 10
    assert resources["memory_status"] == "below_floor"


def test_backend_observation_only_reads_ps_and_sanitized_log(tmp_path, monkeypatch):
    trace = []

    def metadata(origin, path):
        trace.append((origin, path))
        return {
            "models": [
                {
                    "name": "gemma4:e4b",
                    "digest": "a" * 64,
                    "size": 1024,
                    "size_vram": 0,
                    "context_length": 4096,
                }
            ]
        }, "hash"

    monkeypatch.setattr(env, "_metadata", metadata)
    log = tmp_path / "server.log"
    log.write_text(
        "private path C:\\Users\\secret-user\\models\nloaded CPU backend from private.dll\n"
        "offloaded 0/32 layers to GPU\nPROMPT SECRET TEXT\n",
        encoding="utf-8",
    )
    result = env.observe_backend(ORIGIN, log)
    assert trace == [(ORIGIN, "/api/ps")]
    assert result["loaded_models"][0]["size_vram"] == 0
    assert result["loaded_model_backend"] is None
    assert result["log_observations"]["loaded_backend_libraries"] == ["CPU"]
    assert result["log_observations"]["latest_offload_layers"] == 0
    assert "secret-user" not in json.dumps(result) and "SECRET TEXT" not in json.dumps(result)


def test_inventory_pin_rejects_changed_tag_without_generation(monkeypatch):
    monkeypatch.setattr(env, "_metadata", lambda origin, path: ({"models": [tag()]}, "hash"))
    assert env.verify_inventory(ORIGIN, {"gemma4:e4b": "a" * 64})["verified_tags"]
    with pytest.raises(env.PreflightError, match="changed"):
        env.verify_inventory(ORIGIN, {"gemma4:e4b": "b" * 64})


def tag(name="gemma4:e4b", digest="a" * 64):
    return {"name": name, "digest": digest, "size": 1024, "modified_at": "2026-10-05T10:00:00Z"}


def shown():
    return {
        "license": "Example public model license\n",
        "modelfile": "FROM C:\\Users\\private-user\\.ollama\\models\\secret-location",
        "template": "template bytes",
        "parameters": "parameter bytes",
        "details": {
            "format": "gguf",
            "family": "gemma4",
            "families": ["gemma4"],
            "parameter_size": "7.5B",
            "quantization_level": "Q4_K_M",
        },
        "model_info": {"general.architecture": "gemma4", "gemma4.context_length": 131072},
        "thinking": {"values": [False, True], "default": True},
        "capabilities": ["completion", "thinking"],
    }


def gate():
    return {
        "resources": {"memory_status": "okay"},
        "raw_bytes": 0,
        "raw_limit_bytes": env.MAX_RAW_BYTES,
        "disk_free_bytes": env.MAX_RAW_BYTES * 2,
        "disk_observation_error": None,
        "safe_for_new_request": True,
        "blocking_reasons": [],
    }


@pytest.fixture
def metadata(monkeypatch, tmp_path):
    trace = []
    model_tags = [tag(), tag("qwen3.6:35b-a3b", "b" * 64)]

    def request(origin, path, model=None):
        trace.append((origin, path, model))
        value = {
            "/api/version": {"version": "0.35.0"},
            "/api/tags": {"models": model_tags},
            "/api/ps": {"models": []},
            "/api/show": shown(),
        }[path]
        return value, hashlib.sha256(json.dumps(value).encode()).hexdigest()

    monkeypatch.setattr(env, "_metadata", request)
    monkeypatch.setattr(env, "resource_gate", lambda *args: gate())
    log = tmp_path / "private-server-log.txt"
    log.write_text(
        "server config OLLAMA_MODELS:C:\\Users\\private-user\\models\n"
        "Ollama cloud disabled: true\n"
        "Listening on 127.0.0.1:11435 (version 0.35.0)\n",
        encoding="utf-8",
    )
    return trace, log


def test_complete_preflight_writes_manifest_after_multiple_licenses_without_overwrite(
    tmp_path, metadata
):
    trace, log = metadata
    output = tmp_path / "output"
    first = env.preflight(ORIGIN, output, log, 12)
    path = output / first["manifest_file"]
    assert path.name.startswith("environment-") and path.suffix == ".json"
    assert json.loads(path.read_text(encoding="utf-8")) == first
    assert first["ready_for_backend_smoke"]
    assert first["generation_requests"] == first["model_load_requests"] == 0
    assert first["loaded_models"] == []
    original = path.read_bytes()
    second = env.preflight(ORIGIN, output, log, 12)
    assert second["manifest_file"] != first["manifest_file"]
    assert path.read_bytes() == original
    assert len(tuple(output.glob("environment-*.json"))) == 2
    for model in first["models"]:
        assert (output / model["license_file"]).read_text(encoding="utf-8") == shown()["license"]
        assert (
            model["modelfile_sha256"] == hashlib.sha256(shown()["modelfile"].encode()).hexdigest()
        )
        assert model["supported_thinking_values_advertised"] == [False, True]
        assert model["thinking_smoke_verified"] is False
        assert model["loaded_model_backend"] is None and model["offload_layers"] is None
    assert "private-user" not in path.read_text(encoding="utf-8")
    assert {item[1] for item in trace} == {"/api/version", "/api/tags", "/api/ps", "/api/show"}


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:11435",
        "https://127.0.0.1:11435",
        "http://192.0.2.1:11435",
        "http://user:secret@127.0.0.1:11435",
        "http://127.0.0.1:11435/api/chat",
        "http://127.0.0.1:11435?key=secret",
        "http://127.0.0.1",
    ],
)
def test_preflight_rejects_nonliteral_nonlocal_or_credentialed_origins_before_network(
    endpoint, metadata, tmp_path
):
    trace, log = metadata
    with pytest.raises(env.PreflightError):
        env.preflight(endpoint, tmp_path / "output", log, 12)
    assert trace == []


def test_cloud_disable_requires_server_log_not_a_client_environment_flag(
    metadata, monkeypatch, tmp_path
):
    _, log = metadata
    monkeypatch.setenv("OLLAMA_NO_CLOUD", "1")
    log.write_text("Ollama cloud disabled: false\n", encoding="utf-8")
    result = env.preflight(ORIGIN, tmp_path / "output", log, 12)
    assert not result["ready_for_backend_smoke"]
    assert "server_cloud_disabled_unconfirmed" in result["blocking_reasons"]
    assert result["server_log_evidence"]["cloud_disabled"] is False


def test_server_log_latest_observation_and_owner_are_explicit(metadata, tmp_path):
    _, log = metadata
    log.write_text(log.read_text(encoding="utf-8") + "Ollama cloud disabled: false\n")
    result = env.preflight(ORIGIN, tmp_path / "output", log, None)
    assert not result["ready_for_backend_smoke"]
    assert "owned_server_identity_not_supplied" in result["blocking_reasons"]
    assert result["server_log_evidence"]["cloud_disabled"] is False


@pytest.mark.parametrize("remote_location", ["tag", "shown", "both"])
def test_remote_metadata_cannot_be_hidden_by_an_empty_show_field(remote_location):
    declared, observed = tag(), shown()
    if remote_location in ("tag", "both"):
        declared["remote_host"] = "https://remote.invalid"
    observed["remote_host"] = "https://remote.invalid" if remote_location == "shown" else ""
    with pytest.raises(env.PreflightError, match="remote"):
        env._model(declared, observed, "c" * 64)


@pytest.mark.parametrize("identity", ["gemma4:latest", "gemma4:cloud", "../../private/model"])
def test_exact_model_identity_and_digest_are_required(identity):
    with pytest.raises(env.PreflightError):
        env._model(tag(identity), shown(), "c" * 64)
    with pytest.raises(env.PreflightError):
        env._model(tag(digest="not-a-digest"), shown(), "c" * 64)


def test_missing_thinking_values_do_not_turn_into_a_nonthinking_claim():
    value = shown()
    value.pop("thinking")
    result, _ = env._model(tag(), value, "c" * 64)
    assert result["supported_thinking_values_advertised"] is None
    assert result["nonthinking_false_advertised"] is None
    assert result["thinking_smoke_verified"] is False


def test_freeform_metadata_private_paths_are_not_published():
    value = shown()
    value["thinking"]["private_path"] = "C:\\Users\\private-user"
    value["details"]["family"] = "C:\\Users\\private-user"
    value["model_info"]["general.architecture"] = "/home/private-user/model"
    value["model_info"]["/home/private-user.context_length"] = 131072
    result, _ = env._model(tag(), value, "c" * 64)
    assert "private-user" not in json.dumps(result)
    assert result["details"]["family"] is None and result["architecture"] is None


@pytest.mark.parametrize(
    "available,expected",
    [(8 * 2**30, "okay"), (2**30, "below_floor"), (None, "unknown"), (True, "unknown")],
)
def test_resource_samples_keep_ram_unknown_and_check_maximum_floor(
    monkeypatch, available, expected
):
    monkeypatch.setattr(env.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        env,
        "_windows_sample",
        lambda pid: {
            "total_memory_bytes": 64 * 2**30,
            "available_memory_bytes": available,
            "processes": [
                {
                    "pid": 12,
                    "name": "ollama",
                    "alive": True,
                    "working_set_bytes": 1,
                    "private_committed_bytes": None,
                }
            ],
        },
    )
    result = env.collect_resources(12)
    assert result["memory_status"] == expected
    assert result["free_memory_floor_bytes"] == (64 * 2**30 + 9) // 10
    assert result["processes"][0]["private_committed_bytes"] is None
    assert result["processes"][0]["cpu_seconds"] is None
    assert result["gpu_memory_bytes"] is None and result["loaded_model_backend"] is None


def test_unavailable_resource_observation_does_not_invent_process_death_or_zero_cost(monkeypatch):
    monkeypatch.setattr(env.platform, "system", lambda: "unavailable")
    result = env.collect_resources(12)
    assert result["server_alive"] is None
    assert result["available_memory_bytes"] is None
    assert result["memory_status"] == "unknown"
    with pytest.raises(ValueError):
        env.collect_resources(True)


def test_resource_gate_preserves_disk_bound_and_memory_block(monkeypatch, tmp_path):
    monkeypatch.setattr(
        env,
        "collect_resources",
        lambda pid: {
            "memory_status": "unknown",
            "server_alive": None,
        },
    )
    monkeypatch.setattr(env, "MAX_RAW_BYTES", 8)
    target = tmp_path / "history.jsonl"
    target.write_bytes(b"12345678")
    result = env.resource_gate(tmp_path, 12)
    assert not result["safe_for_new_request"] and result["raw_bytes"] == 8
    assert set(result["blocking_reasons"]) == {
        "system_memory_unknown",
        "owned_server_liveness_unconfirmed",
        "raw_disk_envelope_exhausted",
    }
    assert target.read_bytes() == b"12345678"


def test_metadata_transport_has_no_proxy_redirect_or_generation_path(monkeypatch):
    observed = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            assert size == env.MAX_METADATA_BYTES + 1
            return b'{"license":"example"}'

    def build(*handlers):
        observed["handlers"] = handlers

        def open_request(request, timeout):
            observed.update(
                url=request.full_url,
                method=request.method,
                timeout=timeout,
                body=json.loads(request.data),
            )
            return Response()

        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(env.urllib.request, "build_opener", build)
    result, raw_hash = env._metadata(ORIGIN, "/api/show", "gemma4:e4b")
    assert result == {"license": "example"} and len(raw_hash) == 64
    assert observed["handlers"][0].proxies == {}
    assert isinstance(observed["handlers"][1], env._NoRedirect)
    assert observed["url"] == ORIGIN + "/api/show" and observed["method"] == "POST"
    assert observed["body"] == {"model": "gemma4:e4b", "verbose": False}
    with pytest.raises(env.PreflightError, match="only metadata"):
        env._metadata(ORIGIN, "/api/chat", "gemma4:e4b")
    with pytest.raises(env.PreflightError, match="redirect"):
        env._NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://remote.invalid")
