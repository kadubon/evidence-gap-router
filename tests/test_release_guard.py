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


def required_jobs(module):
    return [
        {"name": name, "status": "completed", "conclusion": "success"}
        for name in module.REQUIRED_JOBS
    ]


def test_all_native_profiles_required_for_manual_admission(guard):
    module, _ = guard
    jobs = required_jobs(module)
    assert module.successful_required_jobs(jobs)
    for missing in module.REQUIRED_JOBS:
        assert not module.successful_required_jobs([job for job in jobs if job["name"] != missing])


@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_overall_success_cannot_mask_nonpassing_native_job(guard, conclusion):
    module, _ = guard
    jobs = required_jobs(module)
    for job in jobs:
        if job["name"] == "macos-intel":
            job["conclusion"] = conclusion
    assert not module.successful_required_jobs(jobs)


def test_manual_run_api_requires_completed_native_jobs_for_exact_commit(guard, monkeypatch):
    module, _ = guard
    monkeypatch.setenv("GH_TOKEN", "test-placeholder-not-a-real-token")
    # Restore the implementation replaced by the outer fixture, using a fresh source module.
    source = Path(module.__file__).read_text(encoding="utf-8")
    namespace = {"__name__": "guard_test_copy", "__file__": module.__file__}
    exec(compile(source, module.__file__, "exec"), namespace)
    requests = []

    def responses(url, token):
        requests.append(url)
        if "/jobs?" in url:
            return {"total_count": 6, "jobs": required_jobs(module)}
        return {
            "workflow_runs": [
                {
                    "id": 7,
                    "head_sha": "other-commit",
                    "event": "workflow_dispatch",
                    "status": "completed",
                    "conclusion": "success",
                },
                {
                    "id": 8,
                    "head_sha": "verified",
                    "event": "workflow_dispatch",
                    "status": "completed",
                    "conclusion": "success",
                },
            ]
        }

    namespace["github_json"] = responses
    assert namespace["validated_manual_run"]("verified") == 8
    assert not any("/runs/7/jobs" in url for url in requests)
