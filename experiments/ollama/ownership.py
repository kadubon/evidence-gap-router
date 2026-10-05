"""Windows owned-server handles. Full paths stay in private operational records.

Inference still uses the existing client/controller. An HTTP disconnect, a
closed port, or an empty /ps response is never proof that computation stopped.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .analysis import write_json
from .client import ClientBlocked, _canonical_sha256

SERVER_ENV = {
    "OLLAMA_NO_CLOUD": "1",
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_MAX_LOADED_MODELS": "1",
    "OLLAMA_MAX_QUEUE": "1",
    "OLLAMA_KEEP_ALIVE": "60m",
    "OLLAMA_LOAD_TIMEOUT": "30m",
    "OLLAMA_HOST": "127.0.0.1:11435",
}


class _Handle:
    def __init__(self, pid: int) -> None:
        if os.name != "nt":
            raise ClientBlocked("owned-server handle control requires Windows")
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
            ctypes.POINTER(wintypes.FILETIME)
        ] * 4
        self.api.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.handle = self.api.OpenProcess(0x100001 | 0x1000, False, pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "cannot open exact process handle")
        self.pid = pid

    def identity(self) -> dict[str, Any]:
        values = [wintypes.FILETIME() for _ in range(4)]
        if not self.api.GetProcessTimes(self.handle, *(ctypes.byref(v) for v in values)):
            raise OSError("process start identity unavailable")
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not self.api.QueryFullProcessImageNameW(self.handle, 0, path, ctypes.byref(size)):
            raise OSError("process executable identity unavailable")
        exe = Path(path.value).resolve()
        return {
            "pid": self.pid,
            "creation_filetime": values[0].dwLowDateTime + (values[0].dwHighDateTime << 32),
            "executable": str(exe),
            "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest(),
        }

    def stopped(self, milliseconds: int = 0) -> bool:
        return self.api.WaitForSingleObject(self.handle, milliseconds) == 0

    def terminate(self) -> None:
        if not self.stopped() and not self.api.TerminateProcess(self.handle, 1):
            raise OSError("exact process handle termination failed")

    def close(self) -> None:
        self.api.CloseHandle(self.handle)


def _process_tree(root: int) -> list[int]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "@(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId)"
            " | ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    entries = json.loads(result.stdout)
    selected = {root}
    while True:
        enlarged = selected | {
            int(p["ProcessId"]) for p in entries if int(p["ParentProcessId"]) in selected
        }
        if enlarged == selected:
            return sorted(selected)
        selected = enlarged


def start_owned(directory: Path, executable: Path) -> dict[str, Any]:
    """Start one hidden dedicated server, with configuration at server startup."""
    directory.mkdir(parents=True, exist_ok=True)
    operational = directory / "private"
    operational.mkdir(exist_ok=True)
    executable = executable.resolve(strict=True)
    if executable.name.lower() != "ollama.exe":
        raise ValueError("expected the existing Ollama executable")
    sequence = len(list(operational.glob("owner-*.json"))) + 1
    log = operational / f"server-{sequence}.log"
    out = operational / f"server-{sequence}.stdout.log"
    with log.open("xb") as stderr, out.open("xb") as stdout:
        process = subprocess.Popen(
            [str(executable), "serve"],
            env={**os.environ, **SERVER_ENV},
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    handle = _Handle(process.pid)
    try:
        identity = handle.identity()
        if handle.stopped():
            raise ClientBlocked("dedicated server exited during startup; retain its log")
    finally:
        handle.close()
    owner = {
        "root": identity,
        "server_epoch": _canonical_sha256(identity),
        "server_log": str(log),
        "started_epoch": time.time(),
        "settings": SERVER_ENV,
    }
    write_json(operational / f"owner-{sequence}.json", owner)
    write_json(operational / "current-owner.json", owner)
    write_json(
        directory / f"server-epoch-{sequence}.json",
        {
            "server_epoch": owner["server_epoch"],
            "pid": identity["pid"],
            "executable_sha256": identity["executable_sha256"],
            "creation_filetime": identity["creation_filetime"],
            "settings": SERVER_ENV,
            "started_epoch": owner["started_epoch"],
        },
    )
    return owner


def verify_and_stop_owned(owner: dict[str, Any]) -> dict[str, Any]:
    """Hold exact process handles across identity checks, termination and waits.

    A reused root PID or an unexpected descendant causes refusal. All discovered
    handles must signal process exit. The root is stopped first so it cannot
    launch replacement workers while its descendants are being terminated.
    """
    handles: list[_Handle] = []
    identities = []
    try:
        root = _Handle(owner["root"]["pid"])
        handles.append(root)
        actual = root.identity()
        if actual != owner["root"] or root.stopped():
            raise ClientBlocked("owned root identity changed or already lost; no PID-based kill")
        for pid in _process_tree(actual["pid"]):
            handle = root if pid == actual["pid"] else _Handle(pid)
            if handle is not root:
                handles.append(handle)
            identity = handle.identity()
            if Path(identity["executable"]).name.lower() not in ("ollama.exe", "llama-server.exe"):
                raise ClientBlocked("unexpected descendant; termination ownership unproven")
            identities.append(identity)
        # Single sequential inference and the frozen MAX_QUEUE=1 limit further
        # work; no closed-port or /ps observation substitutes for these handles.
        root.terminate()
        for handle in handles[1:]:
            handle.terminate()
        if not all(handle.stopped(10000) for handle in handles):
            raise ClientBlocked("not every owned process handle confirmed exit")
        # Catch a child created between the first census and root termination.
        # Keep every old handle open so its identity is still pinned during the
        # final tree census. A bounded failure here retains global blocking.
        for _ in range(10):
            known = {h.pid for h in handles}
            extra = set(_process_tree(actual["pid"])) - known
            if not extra:
                break
            for pid in sorted(extra):
                handle = _Handle(pid)
                handles.append(handle)
                identity = handle.identity()
                if (
                    Path(identity["executable"]).name.lower()
                    not in ("ollama.exe", "llama-server.exe")
                    or identity["creation_filetime"] < actual["creation_filetime"]
                ):
                    raise ClientBlocked("late descendant identity unproven")
                identities.append(identity)
                handle.terminate()
                if not handle.stopped(10000):
                    raise ClientBlocked("late descendant exit unconfirmed")
        else:
            raise ClientBlocked("owned tree did not converge to verified termination")
        return {
            "tree_stopped": True,
            "server_epoch": owner["server_epoch"],
            "identities": [
                {k: v for k, v in i.items() if k != "executable"}
                | {"executable_name": Path(i["executable"]).name}
                for i in identities
            ],
            "verified_exit_epoch": time.time(),
            "proof_method": "held-native-process-handles",
        }
    finally:
        for handle in handles:
            handle.close()


def verify_owned_alive(owner: dict[str, Any]) -> None:
    handle = _Handle(owner["root"]["pid"])
    try:
        if handle.identity() != owner["root"] or handle.stopped():
            raise ClientBlocked("owned process start/executable identity changed")
    finally:
        handle.close()
