"""The release guard must keep manual and unvalidated commits from publishing."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def guard(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("release_guard")
    monkeypatch.setattr(module, "source_version", lambda: "0.1.0")
    monkeypatch.setattr(module, "git", lambda *args: "abc123")
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "validated_manual_run", lambda commit: 42)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v0.1.0")
    monkeypatch.setenv("GITHUB_REF_NAME", "v0.1.0")
    monkeypatch.setenv("GITHUB_REPOSITORY", "kadubon/evidence-gap-router")
    output = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    return module, output


def test_manual_tag_run_never_publishes(guard, monkeypatch):
    module, output = guard
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setattr(
        module, "validated_manual_run", lambda commit: pytest.fail("manual run queried admission")
    )
    module.main()
    assert "release=false" in output.read_text()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("GITHUB_REPOSITORY", "other/evidence-gap-router"),
        ("GITHUB_REF_NAME", "v0.1.1"),
        ("GITHUB_REF_NAME", "v0.1.0-rc1"),
    ],
)
def test_release_target_must_match(guard, monkeypatch, key, value):
    module, output = guard
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        module.main()
    assert not output.exists()


def test_tag_requires_validated_commit(guard, monkeypatch):
    module, output = guard

    def unvalidated(commit):
        raise ValueError("No successful manual workflow.yml run for this exact commit")

    monkeypatch.setattr(module, "validated_manual_run", unvalidated)
    with pytest.raises(ValueError, match="exact commit"):
        module.main()
    assert not output.exists()


def test_main_ancestor_is_required(guard, monkeypatch):
    module, output = guard

    def wrong_history(*args, **kwargs):
        raise module.subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(module.subprocess, "run", wrong_history)
    with pytest.raises(module.subprocess.CalledProcessError):
        module.main()
    assert not output.exists()


def test_validated_exact_tag_is_admitted(guard):
    module, output = guard
    module.main()
    assert "release=true" in output.read_text()
    assert "manual_run=42" in output.read_text()
