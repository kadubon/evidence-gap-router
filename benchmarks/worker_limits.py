"""Bounded serial workers; Windows Job accounting includes venv descendants.

This is experiment orchestration, not an SDK sandbox. CPU is cumulative Job user
and kernel time. Memory is peak aggregate private committed bytes, not working
set/RSS. Limits are sampled and can overshoot. Other hosts retain unknown tree
resources rather than substituting root-process measurements.
"""

from __future__ import annotations

import ctypes
import math
import os
import signal
import subprocess
import time


def process_resources(process):
    """Root-process CPU and peak working set only; never worker-tree accounting."""
    if os.name == "nt":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("faults", wintypes.DWORD),
                ("peak_working_set", ctypes.c_size_t),
                ("working_set", ctypes.c_size_t),
                ("quota_paged_peak", ctypes.c_size_t),
                ("quota_paged", ctypes.c_size_t),
                ("quota_nonpaged_peak", ctypes.c_size_t),
                ("quota_nonpaged", ctypes.c_size_t),
                ("pagefile", ctypes.c_size_t),
                ("pagefile_peak", ctypes.c_size_t),
            ]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_times = kernel.GetProcessTimes
        get_times.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        get_times.restype = wintypes.BOOL
        get_memory = psapi.GetProcessMemoryInfo
        get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_memory.restype = wintypes.BOOL
        if process is None:
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            handle = kernel.GetCurrentProcess()
        else:
            handle = wintypes.HANDLE(int(process._handle))
        stamps = [wintypes.FILETIME() for _ in range(4)]
        cpu = None
        if get_times(handle, *(ctypes.byref(stamp) for stamp in stamps)):
            cpu = (
                sum((stamp.dwHighDateTime << 32) + stamp.dwLowDateTime for stamp in stamps[2:])
                / 10_000_000
            )
        memory = Counters()
        memory.cb = ctypes.sizeof(memory)
        peak = (
            memory.peak_working_set if get_memory(handle, ctypes.byref(memory), memory.cb) else None
        )
        return cpu, peak
    if os.path.isdir("/proc"):
        try:
            from pathlib import Path

            directory = Path("/proc") / str(os.getpid() if process is None else process.pid)
            stat = (directory / "stat").read_text().rsplit(")", 1)[1].split()
            cpu = (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")
            status = (directory / "status").read_text().splitlines()
            high = next(line for line in status if line.startswith("VmHWM:"))
            return cpu, int(high.split()[1]) * 1024
        except (OSError, ValueError, StopIteration, IndexError):
            pass
    return None, None


def parent_resources():
    """Current controller process CPU and peak working set, independently of Jobs."""
    return process_resources(None)


class _WindowsJob:
    """One non-inheritable, non-breakaway Job, created before worker execution."""

    def __init__(self):
        from ctypes import wintypes

        class Accounting(ctypes.Structure):
            _fields_ = [
                ("user", ctypes.c_int64),
                ("kernel", ctypes.c_int64),
                ("period_user", ctypes.c_int64),
                ("period_kernel", ctypes.c_int64),
                ("faults", wintypes.DWORD),
                ("total", wintypes.DWORD),
                ("active", wintypes.DWORD),
                ("terminated", wintypes.DWORD),
            ]

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD),
                ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t),
                ("active_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits),
                ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t),
                ("peak_job_memory", ctypes.c_size_t),
            ]

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD),
                ("usage", wintypes.DWORD),
                ("id", wintypes.DWORD),
                ("owner", wintypes.DWORD),
                ("base_priority", wintypes.LONG),
                ("delta_priority", wintypes.LONG),
                ("flags", wintypes.DWORD),
            ]

        self.accounting = Accounting
        self.extended = ExtendedLimits
        self.thread_entry = ThreadEntry
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
                wintypes.BOOL,
            ),
            "QueryInformationJobObject": (
                [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p],
                wintypes.BOOL,
            ),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Thread32First": ([wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.POINTER(ThreadEntry)], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.kernel.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        snapshot = self.kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD.
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = self.thread_entry()
            entry.size = ctypes.sizeof(entry)
            found = self.kernel.Thread32First(snapshot, ctypes.byref(entry))
            # Snapshot iteration is finite and capped; the suspended process has one thread.
            for _ in range(65536):
                if not found:
                    break
                if entry.owner == process.pid:
                    thread = self.kernel.OpenThread(2, False, entry.id)  # SUSPEND_RESUME.
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        count = self.kernel.ResumeThread(thread)
                        if count != 1:
                            raise OSError(f"Unexpected worker thread suspend count: {count}")
                    finally:
                        self.kernel.CloseHandle(thread)
                    return
                found = self.kernel.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("Suspended worker primary thread unavailable")
        finally:
            self.kernel.CloseHandle(snapshot)

    def resources(self):
        accounting, memory = self.accounting(), self.extended()
        cpu, active, total, peak = None, None, None, None
        if self.kernel.QueryInformationJobObject(
            self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None
        ):
            cpu = (accounting.user + accounting.kernel) / 10_000_000
            active, total = accounting.active, accounting.total
        if self.kernel.QueryInformationJobObject(
            self.handle, 9, ctypes.byref(memory), ctypes.sizeof(memory), None
        ):
            peak = memory.peak_job_memory
        return cpu, peak, active, total

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _stop_worker(process, job):
    """Only this privately contained tree; never global name/PID discovery kills."""
    if job is not None:
        try:
            job.terminate()
        except OSError:
            job.close()  # Kill-on-close is the fallback for this exact private Job.
    elif os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()


def run_worker(
    command,
    *,
    input_text=None,
    cwd=None,
    wall_limit_seconds=10,
    cpu_limit_seconds=8,
    memory_limit_bytes=268435456,
    sampling_interval_seconds=0.05,
):
    """Execute once; sampled wall/Job CPU/Job private-commit caps, never restart.

    Windows must establish containment before execution, otherwise status is
    ``unavailable`` and execution/resources remain unknown. Non-Windows tree CPU
    and memory are unknown; only wall termination of the owned process group is
    supported there. The controller can separately call ``parent_resources``.
    """
    for value in (wall_limit_seconds, sampling_interval_seconds):
        if not math.isfinite(value) or value <= 0:
            raise ValueError("Worker wall limit and sample interval must be finite and positive")
    for value in (cpu_limit_seconds, memory_limit_bytes):
        if value is not None and (not math.isfinite(value) or value <= 0):
            raise ValueError("Worker resource caps must be finite and positive, or None")
    started = time.perf_counter()
    cpu, peak, total = None, None, None
    status, exceeded, error = "completed", None, None
    stdout, stderr, returncode = "", "", None
    job, process = None, None
    executed = False
    accounting_complete = False
    containment = "windows_job" if os.name == "nt" else "posix_process_group"
    try:
        if os.name == "nt":
            try:
                job = _WindowsJob()
            except OSError as exc:
                status, error = "unavailable", str(exc)
        if status != "unavailable":
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=cwd,
                creationflags=4 if os.name == "nt" else 0,  # CREATE_SUSPENDED.
                start_new_session=os.name != "nt",
            )
            if job is not None:
                try:
                    job.attach_and_resume(process)
                except OSError as exc:
                    status, error = "unavailable", str(exc)
                    _stop_worker(process, job)
                    stdout, stderr = process.communicate(timeout=2)
            if status != "unavailable":
                executed = True
                pending_input = input_text
                while True:
                    if job is not None:
                        current_cpu, current_peak, _, total = job.resources()
                        if current_cpu is not None:
                            cpu = max(cpu or 0.0, current_cpu)
                        if current_peak is not None:
                            peak = max(peak or 0, current_peak)
                    remaining = wall_limit_seconds - (time.perf_counter() - started)
                    if remaining <= 0:
                        status, exceeded = "timeout", "wall"
                    elif (
                        cpu_limit_seconds is not None
                        and cpu is not None
                        and cpu > cpu_limit_seconds
                    ):
                        status, exceeded = "resource_limit", "cpu"
                    elif (
                        memory_limit_bytes is not None
                        and peak is not None
                        and peak > memory_limit_bytes
                    ):
                        status, exceeded = "resource_limit", "memory"
                    if exceeded is not None:
                        _stop_worker(process, job)
                        stdout, stderr = process.communicate(timeout=2)
                        break
                    try:
                        stdout, stderr = process.communicate(
                            input=pending_input,
                            timeout=min(sampling_interval_seconds, remaining),
                        )
                        pending_input = None
                        active = 0 if job is None else job.resources()[2]
                        if active == 0:
                            break
                        if active is None:
                            status, error = (
                                "unavailable",
                                "Job active-process accounting unavailable",
                            )
                            _stop_worker(process, job)
                            break
                        # Root exited but owned descendants remain; keep charging/capping.
                        time.sleep(min(sampling_interval_seconds, max(remaining, 0)))
                    except subprocess.TimeoutExpired:
                        pending_input = None
                if job is not None:
                    # A killed root can exit before the final owned descendant.
                    cleanup_deadline = time.perf_counter() + 2
                    while True:
                        final_cpu, final_peak, active, total = job.resources()
                        if active == 0:
                            cpu, peak = final_cpu, final_peak
                            accounting_complete = final_cpu is not None and final_peak is not None
                            break
                        if active is None or time.perf_counter() >= cleanup_deadline:
                            cpu, peak = None, None
                            status, error = "unavailable", "Final Job accounting unavailable"
                            break
                        time.sleep(0.01)
                # Fast completed workers can exceed a cap between the last two samples.
                if status == "completed":
                    if (
                        cpu_limit_seconds is not None
                        and cpu is not None
                        and cpu > cpu_limit_seconds
                    ):
                        status, exceeded = "resource_limit", "cpu"
                    elif (
                        memory_limit_bytes is not None
                        and peak is not None
                        and peak > memory_limit_bytes
                    ):
                        status, exceeded = "resource_limit", "memory"
                if status == "completed" and process.returncode != 0:
                    status = "exception"
            returncode = process.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        status, error = "exception", str(exc)
    finally:
        if process is not None:
            _stop_worker(process, job)
            try:
                process.wait(timeout=2)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                status, error = (
                    "unavailable",
                    "Owned worker cleanup did not finish within 2 seconds",
                )
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        if job is not None:
            job.close()  # Includes exceptional paths and any residual owned descendants.
    return {
        "worker_status": status,
        "limit_exceeded": exceeded,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "whole_worker_seconds": time.perf_counter() - started,
        "whole_worker_cpu_seconds": cpu,
        "peak_worker_memory_bytes": peak,
        "peak_working_set_bytes": None,
        "wall_limit_seconds": wall_limit_seconds,
        "cpu_limit_seconds": cpu_limit_seconds,
        "memory_limit_bytes": memory_limit_bytes,
        "sampling_interval_seconds": sampling_interval_seconds,
        "cpu_observed": cpu is not None,
        "memory_observed": peak is not None,
        "working_set_observed": False,
        "worker_executed": executed,
        "resource_accounting_complete": accounting_complete,
        "resource_error": error,
        "containment": containment,
        "worker_process_count": total,
        "cpu_metric": "job_cumulative_user_plus_kernel_seconds" if os.name == "nt" else "unknown",
        "memory_metric": "job_peak_private_committed_bytes" if os.name == "nt" else "unknown",
        "resource_scope": (
            "Owned worker Job tree, startup/imports/input/trial/output included. "
            "Sampled limits can overshoot; phase of censoring unknown. "
            "Non-Windows whole-tree CPU/memory are unknown."
        ),
    }
