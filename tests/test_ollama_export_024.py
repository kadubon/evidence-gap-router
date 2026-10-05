"""Publication exports retain real events while rejecting mismatched/private bytes."""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import pack_ollama  # noqa: E402


def sha(content):
    return hashlib.sha256(content).hexdigest()


def inputs(tmp_path):
    repository = tmp_path / "repository"
    harness = repository / "experiments/ollama"
    harness.mkdir(parents=True)
    source = b'"""Retained fake harness; no inference."""\n'
    (harness / "__init__.py").write_bytes(source)
    protocol = {
        "protocol_id": "egr-024-export-test",
        "package_version": "0.2.4",
        "global_limits": {"disk_bytes": 1000000},
    }
    protocol_bytes = json.dumps(protocol).encode()
    (harness / "protocol-v0.2.4.json").write_bytes(protocol_bytes)
    (harness / "protocol.json").write_text('{"archived":true}')
    raw = tmp_path / "raw"
    raw.mkdir()
    freeze = {
        "protocol_file": "protocol-v0.2.4.json",
        "harness_files": {"__init__.py": sha(source)},
        "harness_sha256": sha(b"__init__.py" + source),
        "manifest_sha256": sha(protocol_bytes),
    }
    for name, key in (
        ("frozen-public-tasks.json", "public_tasks_sha256"),
        ("evaluation-only-gold.json", "evaluation_only_gold_sha256"),
        ("preflight/manifest.json", "preflight_sha256"),
    ):
        path = raw / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}\n")
        freeze[key] = sha(path.read_bytes())
    (raw / "calls.jsonl").write_bytes(b'{"event":"reserve","request_id":"known-id"}\n')
    (raw / "private").mkdir()
    (raw / "private/current-owner.json").write_text(
        '{"executable":"C:/Users/private/Ollama/ollama.exe"}'
    )
    (raw / "development-history/cycle-1").mkdir(parents=True)
    (raw / "development-history/cycle-1/client.py").write_bytes(source)
    candidate = raw / "candidate/evidence_gap_router-0.2.4-py3-none-any.whl"
    candidate.parent.mkdir()
    candidate.write_bytes(b"fake candidate bytes")
    freeze["candidate_wheel_sha256"] = sha(candidate.read_bytes())
    freeze_path = tmp_path / "freeze-v0.2.4.json"
    freeze_path.write_text(json.dumps(freeze))
    summary = tmp_path / "analysis"
    summary.mkdir()
    (summary / "summary.json").write_bytes(b"{}\n")
    return repository, raw, freeze_path, summary


def test_export_keeps_original_events_and_development_source_and_excludes_private_paths(tmp_path):
    repository, raw, frozen, summary = inputs(tmp_path)
    before = (raw / "calls.jsonl").read_bytes()
    output = tmp_path / "public.zip"
    result = pack_ollama.pack(raw, output, frozen, summary, repository=repository)
    with zipfile.ZipFile(output) as archive:
        assert archive.read("raw/calls.jsonl") == before
        assert "raw/private/current-owner.json" not in archive.namelist()
        assert "raw/development-history/cycle-1/client.py" in archive.namelist()
        assert "harness/protocol-v0.2.4.json" in archive.namelist()
    assert (raw / "calls.jsonl").read_bytes() == before
    assert result["package_version"] == "0.2.4"
    assert "raw/private/current-owner.json" in result["explicitly_excluded_sources"]
    with pytest.raises(ValueError, match="replace"):
        pack_ollama.pack(raw, output, frozen, summary, repository=repository)


@pytest.mark.parametrize("changed", ["candidate", "public-task", "protocol"])
def test_export_rejects_candidate_or_frozen_source_mismatch(tmp_path, changed):
    repository, raw, frozen, summary = inputs(tmp_path)
    path = {
        "candidate": raw / "candidate/evidence_gap_router-0.2.4-py3-none-any.whl",
        "public-task": raw / "frozen-public-tasks.json",
        "protocol": repository / "experiments/ollama/protocol-v0.2.4.json",
    }[changed]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="differs|differ"):
        pack_ollama.pack(raw, tmp_path / "public.zip", frozen, summary, repository=repository)


def test_private_path_in_model_output_is_rejected_without_rewriting_it(tmp_path):
    repository, raw, frozen, summary = inputs(tmp_path)
    original = b'{"event":"response","content":"C:/Users/private/document.txt"}\n'
    (raw / "calls.jsonl").write_bytes(original)
    with pytest.raises(pack_ollama.PrivacyError):
        pack_ollama.pack(raw, tmp_path / "public.zip", frozen, summary, repository=repository)
    assert (raw / "calls.jsonl").read_bytes() == original
