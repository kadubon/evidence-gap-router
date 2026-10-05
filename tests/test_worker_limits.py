"""Actual worker communication, timeout and observed resource limit behavior."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks import worker_limits  # noqa: E402
from benchmarks.worker_limits import parent_resources, run_worker  # noqa: E402


def test_observation_timeouts_resume_same_worker_without_restarting(tmp_path):
    counter = tmp_path / "invocations.txt"
    code = (
        "import pathlib,sys,time; "
        "p=pathlib.Path(sys.argv[1]); p.write_text('one'); "
        "x=sys.stdin.read(); time.sleep(0.15); print(x)"
    )
    result = run_worker(
        [sys.executable, "-I", "-c", code, str(counter)],
        input_text="bound input",
        wall_limit_seconds=3,
        sampling_interval_seconds=0.02,
    )
    assert result["worker_status"] == "completed" and result["returncode"] == 0
    assert result["stdout"].strip() == "bound input" and counter.read_text() == "one"
    assert result["whole_worker_seconds"] >= 0.15


def test_actual_whole_worker_timeout_is_not_a_plan_time_or_success():
    result = run_worker(
        [sys.executable, "-I", "-c", "import time; time.sleep(5)"],
        wall_limit_seconds=0.2,
    )
    assert result["worker_status"] == "timeout" and result["limit_exceeded"] == "wall"
    assert result["returncode"] != 0 and result["whole_worker_seconds"] < 3


def test_observed_cpu_limit_terminates_busy_worker_without_assuming_zero():
    result = run_worker(
        [sys.executable, "-I", "-c", "while True: pass"],
        cpu_limit_seconds=0.1,
        wall_limit_seconds=1.5,
    )
    assert result["worker_status"] in {"resource_limit", "timeout"}
    if os.name == "nt":
        assert result["cpu_observed"], result
        assert result["worker_process_count"] >= 2  # Current uv venv redirector + interpreter.
        assert result["resource_accounting_complete"], result
    if result["cpu_observed"]:
        assert result["limit_exceeded"] == "cpu" and result["whole_worker_cpu_seconds"] > 0.1
    else:
        assert result["whole_worker_cpu_seconds"] is None


def test_completed_worker_error_keeps_stderr_and_exit_code():
    result = run_worker([sys.executable, "-I", "-c", "raise ValueError('diagnostic')"])
    assert result["worker_status"] == "exception" and result["returncode"] != 0
    assert "ValueError: diagnostic" in result["stderr"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job descendant accounting")
def test_descendant_busy_loop_hits_whole_job_cpu_cap():
    code = "import subprocess,sys; subprocess.run([sys.executable,'-I','-c','while True: pass'])"
    result = run_worker(
        [sys.executable, "-I", "-c", code],
        cpu_limit_seconds=0.15,
        wall_limit_seconds=2,
        sampling_interval_seconds=0.02,
    )
    assert result["worker_status"] == "resource_limit", result
    assert result["limit_exceeded"] == "cpu" and result["whole_worker_cpu_seconds"] > 0.15
    assert result["worker_process_count"] >= 3
    assert result["cpu_metric"] == "job_cumulative_user_plus_kernel_seconds"
    assert result["resource_accounting_complete"]


@pytest.mark.skipif(os.name != "nt", reason="Windows cumulative Job accounting")
def test_exited_descendant_cpu_is_retained_in_final_accounting():
    child = "import time; end=time.process_time()+0.2\nwhile time.process_time()<end: pass"
    code = "import subprocess,sys; subprocess.run([sys.executable,'-I','-c',sys.argv[1]])"
    result = run_worker(
        [sys.executable, "-I", "-c", code, child],
        cpu_limit_seconds=2,
        wall_limit_seconds=4,
        sampling_interval_seconds=0.5,
    )
    assert result["worker_status"] == "completed", result
    assert result["whole_worker_cpu_seconds"] >= 0.19, result
    assert result["worker_process_count"] >= 3 and result["resource_accounting_complete"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job outlives root process")
def test_early_root_exit_does_not_escape_descendant_cpu_cap():
    code = (
        "import subprocess,sys; subprocess.Popen("
        "[sys.executable,'-I','-c','while True: pass'],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)"
    )
    result = run_worker(
        [sys.executable, "-I", "-c", code],
        cpu_limit_seconds=0.15,
        wall_limit_seconds=2,
        sampling_interval_seconds=0.02,
    )
    assert result["worker_status"] == "resource_limit", result
    assert result["limit_exceeded"] == "cpu" and result["whole_worker_cpu_seconds"] > 0.15
    assert result["resource_accounting_complete"]


@pytest.mark.skipif(os.name != "nt", reason="Windows unavailable CPU measurement")
def test_unavailable_cpu_measurement_is_unknown_with_wall_limit_retained(monkeypatch):
    original = worker_limits._WindowsJob.resources

    def unknown_cpu(job):
        _, peak, active, total = original(job)
        return None, peak, active, total

    monkeypatch.setattr(worker_limits._WindowsJob, "resources", unknown_cpu)
    result = run_worker(
        [sys.executable, "-I", "-c", "while True: pass"],
        cpu_limit_seconds=0.1,
        wall_limit_seconds=0.2,
        sampling_interval_seconds=0.02,
    )
    assert result["worker_status"] == "timeout" and result["limit_exceeded"] == "wall", result
    assert result["whole_worker_cpu_seconds"] is None and not result["cpu_observed"]
    assert not result["resource_accounting_complete"] and result["worker_executed"]


@pytest.mark.skipif(os.name != "nt", reason="Windows Job private-commit accounting")
def test_descendant_memory_cap_uses_explicit_private_commit_metric():
    child = "import time; payload=bytearray(96*1024*1024); time.sleep(5)"
    code = "import subprocess,sys; subprocess.run([sys.executable,'-I','-c',sys.argv[1]])"
    result = run_worker(
        [sys.executable, "-I", "-c", code, child],
        memory_limit_bytes=64 * 1024 * 1024,
        wall_limit_seconds=2,
        sampling_interval_seconds=0.02,
    )
    assert result["worker_status"] == "resource_limit", result
    assert result["limit_exceeded"] == "memory"
    assert result["memory_observed"] and result["peak_worker_memory_bytes"] > 64 * 1024 * 1024
    assert result["memory_metric"] == "job_peak_private_committed_bytes"
    assert result["peak_working_set_bytes"] is None and not result["working_set_observed"]


@pytest.mark.skipif(os.name != "nt", reason="Windows final accounting between samples")
def test_short_completed_worker_memory_excess_is_not_reported_as_success():
    result = run_worker(
        [sys.executable, "-I", "-c", "payload=bytearray(80*1024*1024)"],
        memory_limit_bytes=64 * 1024 * 1024,
        sampling_interval_seconds=0.5,
    )
    assert result["worker_status"] == "resource_limit", result
    assert result["limit_exceeded"] == "memory"
    assert result["peak_worker_memory_bytes"] > 64 * 1024 * 1024


@pytest.mark.skipif(os.name != "nt", reason="Windows Job containment")
def test_timeout_terminates_owned_descendant_but_not_unrelated_process(tmp_path):
    heartbeat = tmp_path / "owned-heartbeat.txt"
    child = (
        "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); "
        "\nwhile True: p.write_text(str(time.time())); time.sleep(0.02)"
    )
    code = (
        "import subprocess,sys,time; "
        "subprocess.Popen([sys.executable,'-I','-c',sys.argv[1],sys.argv[2]]); time.sleep(5)"
    )
    with subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(5)"]) as unrelated:
        try:
            result = run_worker(
                [sys.executable, "-I", "-c", code, child, str(heartbeat)],
                # Include two interpreter startups under concurrent CPU load.
                wall_limit_seconds=2,
            )
            assert result["worker_status"] == "timeout", result
            assert heartbeat.exists()
            last = heartbeat.read_text()
            time.sleep(0.1)
            assert heartbeat.read_text() == last
            assert unrelated.poll() is None
        finally:
            unrelated.kill()


@pytest.mark.skipif(os.name != "nt", reason="Windows pre-execution containment")
@pytest.mark.parametrize("failure", ["create", "attach"])
def test_unavailable_job_does_not_execute_or_claim_zero_resources(monkeypatch, tmp_path, failure):
    marker = tmp_path / "must-not-exist.txt"

    def fail(*_args):
        raise OSError("test containment unavailable")

    if failure == "create":
        monkeypatch.setattr(worker_limits, "_WindowsJob", fail)
    else:
        monkeypatch.setattr(worker_limits._WindowsJob, "attach_and_resume", fail)
    result = run_worker(
        [
            sys.executable,
            "-I",
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
            str(marker),
        ],
    )
    assert result["worker_status"] == "unavailable" and not result["worker_executed"]
    assert result["whole_worker_cpu_seconds"] is None and result["peak_worker_memory_bytes"] is None
    assert not result["cpu_observed"] and not result["memory_observed"]
    assert "containment unavailable" in result["resource_error"] and not marker.exists()


def test_parent_resources_are_separate_current_process_observations():
    cpu, peak = parent_resources()
    if os.name == "nt" or os.path.isdir("/proc"):
        assert cpu is not None and cpu >= 0
        assert peak is not None and peak > 0
    else:
        assert cpu is None and peak is None


@pytest.mark.parametrize(
    "options",
    [
        {"wall_limit_seconds": float("inf")},
        {"sampling_interval_seconds": float("nan")},
        {"cpu_limit_seconds": 0},
        {"memory_limit_bytes": -1},
    ],
)
def test_nonfinite_or_nonpositive_limits_are_rejected_before_launch(options):
    with pytest.raises(ValueError):
        run_worker(
            [sys.executable, "-I", "-c", "raise RuntimeError('must not execute')"], **options
        )
