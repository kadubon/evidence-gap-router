"""Read-only local metadata and resource observations for explicit experiments.

Importing this module performs no HTTP request. Preflight never generates,
downloads, loads, unloads or configures a model/server. Metadata advertisements
are recorded separately from the later backend-smoke observations.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .client import strict_json

MAX_METADATA_BYTES = 4_194_304
MAX_RAW_BYTES = 536_870_912
MIN_FREE_RAM_BYTES = 2_147_483_648
_TAG = re.compile(r"[A-Za-z0-9_.-]+:[A-Za-z0-9_.-]+")
_DIGEST = re.compile(r"[0-9a-f]{64}")


class PreflightError(ValueError):
    """Metadata could not establish the declared local preflight conditions."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        raise PreflightError("metadata redirect rejected")


def _origin(base_url: str) -> str:
    parsed = urlsplit(base_url)
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as error:
        raise PreflightError("metadata endpoint requires numeric loopback and port") from error
    if (
        parsed.scheme != "http"
        or not address.is_loopback
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise PreflightError("metadata endpoint must be a plain numeric loopback HTTP origin")
    host = f"[{address}]" if address.version == 6 else str(address)
    return f"http://{host}:{port}"


def _metadata(origin: str, path: str, model: str | None = None) -> tuple[dict[str, Any], str]:
    if path not in ("/api/version", "/api/tags", "/api/ps", "/api/show"):
        raise PreflightError("only metadata endpoints are permitted")
    if (path == "/api/show") != (model is not None):
        raise PreflightError("model identity is only valid for metadata show")
    body = None if model is None else json.dumps({"model": model, "verbose": False}).encode()
    request = urllib.request.Request(
        origin + path,
        data=body,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="GET" if body is None else "POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            if response.status != 200:
                raise PreflightError("metadata HTTP status was not 200")
            raw = response.read(MAX_METADATA_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        # Do not publish URL error strings which might carry local filesystem data.
        raise PreflightError(f"metadata request failed: {type(error).__name__}") from error
    if len(raw) > MAX_METADATA_BYTES:
        raise PreflightError("metadata response exceeds its byte limit")
    try:
        value = strict_json(raw.decode("utf-8"))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise PreflightError("metadata is not bounded strict JSON") from error
    if not isinstance(value, dict) or value.get("error"):
        raise PreflightError("metadata is not an error-free JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _number(value: Any) -> int | float | None:
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def _integer(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _label(value: Any) -> str | None:
    return (
        value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", value) else None
    )


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,12})?(?:Z|[+-]\d\d:\d\d)", value
    ):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def _process_ids(server_pid: int | None) -> tuple[int, ...]:
    if server_pid is not None and (type(server_pid) is not int or server_pid < 1):
        raise ValueError("server PID must be a positive integer or None")
    return tuple(dict.fromkeys((os.getpid(), *((server_pid,) if server_pid else ()))))


def _windows_sample(server_pid: int | None) -> dict[str, Any]:
    selected = ",".join(str(value) for value in _process_ids(server_pid))
    server = 0 if server_pid is None else server_pid
    # Only checked integer IDs enter this fixed command. Command lines, executable
    # paths, user names and environment variables are never queried or serialized.
    script = """
    $operatingSystem = Get-CimInstance Win32_OperatingSystem
    $computerSystem = Get-CimInstance Win32_ComputerSystem
    $memoryBanks = Get-CimInstance Win32_PhysicalMemory
    $installedCapacity = ($memoryBanks | Measure-Object -Property Capacity -Sum).Sum
    $identities = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($identity in @(__IDS__)) { [void]$identities.Add($identity) }
    if (__SERVER__ -gt 0) {
      $allProcesses = @(Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId)
      $descendants = [System.Collections.Generic.HashSet[int]]::new()
      [void]$descendants.Add(__SERVER__)
      do {
        $added = $false
        foreach ($entry in $allProcesses) {
          if ($descendants.Contains([int]$entry.ParentProcessId)) {
            if ($descendants.Add([int]$entry.ProcessId)) { $added = $true }
          }
        }
      } while ($added)
      foreach ($identity in $descendants) { [void]$identities.Add($identity) }
    }
    $samples = @()
    foreach ($identity in $identities) {
      $entry = Get-Process -Id $identity -ErrorAction SilentlyContinue
      if ($null -ne $entry) {
        $samples += [PSCustomObject]@{
          pid=[int]$entry.Id; name=$entry.ProcessName; alive=$true
          working_set_bytes=[int64]$entry.WorkingSet64
          peak_working_set_bytes=[int64]$entry.PeakWorkingSet64
          private_committed_bytes=[int64]$entry.PrivateMemorySize64
          cpu_seconds=[double]$entry.TotalProcessorTime.TotalSeconds
        }
      }
    }
    [PSCustomObject]@{
      total_memory_bytes=[int64]$computerSystem.TotalPhysicalMemory
      installed_memory_bytes=[int64]$installedCapacity
      available_memory_bytes=[int64]$operatingSystem.FreePhysicalMemory*1024
      processes=$samples
    } | ConvertTo-Json -Depth 4 -Compress
    """.replace("__IDS__", selected).replace("__SERVER__", str(server))
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    data = strict_json(result.stdout)
    if not isinstance(data, dict):
        raise ValueError("resource observation is not an object")
    return data


def _linux_sample(server_pid: int | None) -> dict[str, Any]:
    meminfo = {}
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        key, _, value = line.partition(":")
        match = re.fullmatch(r"\s*(\d+) kB\s*", value)
        if match:
            meminfo[key] = int(match.group(1)) * 1024
    processes = []
    selected = set(_process_ids(server_pid))
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text(encoding="utf-8")
            parent = re.search(r"^PPid:\s*(\d+)", status, re.MULTILINE)
            if parent:
                parents[int(entry.name)] = int(parent.group(1))
        except (OSError, UnicodeError):
            continue
    if server_pid is not None:
        descendants = {server_pid}
        previous: set[int] = set()
        while descendants != previous:
            previous = set(descendants)
            descendants.update(pid for pid, parent in parents.items() if parent in previous)
        selected.update(descendants)
    for identity in sorted(selected):
        directory = Path("/proc") / str(identity)
        try:
            status = (directory / "status").read_text(encoding="utf-8")
            values = {}
            for key in ("VmRSS", "VmHWM"):
                match = re.search(rf"^{key}:\s*(\d+) kB", status, re.MULTILINE)
                values[key] = None if match is None else int(match.group(1)) * 1024
            stat = (directory / "stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            cpu = (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")  # type: ignore[attr-defined]
            name = (directory / "comm").read_text(encoding="utf-8").strip()
            processes.append(
                {
                    "pid": identity,
                    "name": name,
                    "alive": True,
                    "working_set_bytes": values["VmRSS"],
                    "peak_working_set_bytes": values["VmHWM"],
                    "private_committed_bytes": None,
                    "cpu_seconds": cpu,
                }
            )
        except (OSError, ValueError, IndexError, UnicodeError):
            continue
    return {
        "total_memory_bytes": meminfo.get("MemTotal"),
        "available_memory_bytes": meminfo.get("MemAvailable"),
        "processes": processes,
    }


def _mac_sample(server_pid: int | None) -> dict[str, Any]:
    total = subprocess.run(
        ["sysctl", "-n", "hw.memsize"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    # vm_stat free pages are deliberately conservative, not a promise that
    # inactive/purgeable or compressed memory can be reclaimed without pressure.
    vm = subprocess.run(["vm_stat"], check=True, capture_output=True, text=True, timeout=5)
    page = re.search(r"page size of (\d+) bytes", vm.stdout)
    free = re.search(r"Pages free:\s*(\d+)\.", vm.stdout)
    available = None if page is None or free is None else int(page[1]) * int(free[1])
    processes = []
    for identity in _process_ids(server_pid):
        result = subprocess.run(
            ["ps", "-p", str(identity), "-o", "pid=,rss=,comm="],
            capture_output=True,
            text=True,
            timeout=5,
        )
        match = re.fullmatch(r"\s*(\d+)\s+(\d+)\s+(.+?)\s*", result.stdout)
        if result.returncode == 0 and match:
            processes.append(
                {
                    "pid": int(match[1]),
                    "name": Path(match[3]).name,
                    "alive": True,
                    "working_set_bytes": int(match[2]) * 1024,
                    "peak_working_set_bytes": None,
                    "private_committed_bytes": None,
                    "cpu_seconds": None,
                }
            )
    return {
        "total_memory_bytes": int(total.stdout),
        "installed_memory_bytes": int(total.stdout),
        "available_memory_bytes": available,
        "processes": processes,
    }


def collect_resources(server_pid: int | None = None) -> dict[str, Any]:
    """Sample RAM/process use without changing processes; unavailable values stay None.

    Windows includes descendants of the supplied server PID. Linux uses /proc;
    macOS samples conservative free pages and only the named processes. These
    snapshots are observations, not enforced peak-memory or server-time limits.
    """
    _process_ids(server_pid)
    system = platform.system()
    error = None
    try:
        if system == "Windows":
            data = _windows_sample(server_pid)
        elif system == "Linux":
            data = _linux_sample(server_pid)
        elif system == "Darwin":
            data = _mac_sample(server_pid)
        else:
            data = {}
    except (OSError, ValueError, subprocess.SubprocessError, RecursionError) as exc:
        data, error = {}, type(exc).__name__
    total = _integer(data.get("total_memory_bytes"))
    installed = _integer(data.get("installed_memory_bytes"))
    available = _integer(data.get("available_memory_bytes"))
    capacity = (
        max(value for value in (total, installed) if value is not None)
        if (total is not None or installed is not None)
        else None
    )
    floor = None if capacity is None else max(MIN_FREE_RAM_BYTES, (capacity + 9) // 10)
    processes = []
    for item in data.get("processes", []):
        if not isinstance(item, dict) or _integer(item.get("pid")) is None:
            continue
        processes.append(
            {
                "pid": item["pid"],
                "name": str(item.get("name", "")).replace("\\", "/").rsplit("/", 1)[-1],
                "alive": item.get("alive") is True,
                **{
                    name: _integer(item.get(name))
                    for name in (
                        "working_set_bytes",
                        "peak_working_set_bytes",
                        "private_committed_bytes",
                    )
                },
                "cpu_seconds": _number(item.get("cpu_seconds")),
            }
        )
    return {
        "sampled_at": datetime.now(UTC).isoformat(),
        "monotonic_seconds": time.monotonic(),
        "platform": system,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "total_memory_bytes": total,
        "installed_memory_bytes": installed,
        "free_memory_floor_basis": (
            "maximum known installed/OS-visible capacity; installed unknown retained"
        ),
        "available_memory_bytes": available,
        "free_memory_floor_bytes": floor,
        "memory_status": (
            "unknown"
            if available is None or floor is None
            else ("below_floor" if available < floor else "okay")
        ),
        "memory_source": {
            "Windows": "CIM PhysicalMemory Capacity/TotalPhysicalMemory/FreePhysicalMemory",
            "Linux": "/proc MemTotal/MemAvailable (OS-visible RAM)",
            "Darwin": "hw.memsize/vm_stat free pages (conservative)",
        }.get(system, "unavailable"),
        "processes": sorted(processes, key=lambda item: item["pid"]),
        "server_pid": server_pid,
        "server_alive": (
            None
            if server_pid is None or error is not None
            else next((item["alive"] for item in processes if item["pid"] == server_pid), None)
        ),
        "descendants_included": system in ("Windows", "Linux"),
        "gpu_memory_bytes": None,
        "loaded_model_backend": None,
        "offload_layers": None,
        "observation_error": error,
        "limits": "Sampled RAM/process observations; no hard server memory ceiling enforced",
    }


def resource_gate(output_dir: str | Path, server_pid: int | None = None) -> dict[str, Any]:
    """Check the next-request RAM/disk preconditions; this function never dispatches."""
    resources = collect_resources(server_pid)
    directory = Path(output_dir)
    ancestor = directory.resolve()
    while not ancestor.exists():
        ancestor = ancestor.parent
    used: int | None = 0
    error = None
    try:
        assert used is not None
        if directory.exists():
            for entry in directory.rglob("*"):
                if entry.is_symlink():
                    raise ValueError("experiment directory contains a symbolic link")
                if entry.is_file():
                    used += entry.stat().st_size
        free = shutil.disk_usage(ancestor).free
    except (OSError, ValueError) as exc:
        used, free, error = None, None, type(exc).__name__
    reasons = []
    if resources["memory_status"] != "okay":
        reasons.append("system_memory_" + resources["memory_status"])
    if server_pid is not None and resources["server_alive"] is not True:
        reasons.append("owned_server_liveness_unconfirmed")
    if used is None or free is None:
        reasons.append("disk_observation_unknown")
    elif used >= MAX_RAW_BYTES:
        reasons.append("raw_disk_envelope_exhausted")
    elif free < MAX_RAW_BYTES - used:
        reasons.append("insufficient_disk_for_remaining_raw_envelope")
    return {
        "resources": resources,
        "raw_bytes": used,
        "raw_limit_bytes": MAX_RAW_BYTES,
        "disk_free_bytes": free,
        "disk_observation_error": error,
        "safe_for_new_request": not reasons,
        "blocking_reasons": reasons,
    }


def _log_evidence(server_log: str | Path | None, origin: str) -> dict[str, Any]:
    evidence = {"sha256": None, "cloud_disabled": None, "matching_listener": False}
    if server_log is None:
        return evidence
    try:
        with Path(server_log).open("rb") as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            return {**evidence, "error": "server_log_exceeds_metadata_bound"}
        text = raw.decode("utf-8", errors="strict")
    except (OSError, UnicodeError):
        return {**evidence, "error": "server_log_unreadable"}
    matches = re.findall(r"Ollama cloud disabled: (true|false)", text)
    listeners = re.findall(r"Listening on ([^\s]+) \(version ([^)]+)\)", text)
    expected = origin.removeprefix("http://")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "cloud_disabled": None if not matches else matches[-1] == "true",
        "matching_listener": bool(listeners and listeners[-1][0] == expected),
        "listener_version": None if not listeners else listeners[-1][1],
        "scope": "Observed supplied server log; client environment is not server configuration",
    }


def observe_backend(base_url: str, server_log: str | Path | None = None) -> dict[str, Any]:
    """Observe already loaded models and bounded log facts; never load/generate.

    VRAM is the server's reported allocation. Loaded libraries and historical
    offload lines do not independently establish a current model's backend.
    Paths, prompts, whole logs and environment settings are never returned.
    """
    origin = _origin(base_url)
    loaded, response_hash = _metadata(origin, "/api/ps")
    if not isinstance(loaded.get("models"), list):
        raise PreflightError("loaded model metadata is malformed")
    models = []
    for item in loaded["models"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or _TAG.fullmatch(item["name"]) is None
            or "cloud" in item["name"].lower()
            or not isinstance(item.get("digest"), str)
            or _DIGEST.fullmatch(item["digest"]) is None
        ):
            raise PreflightError("loaded model identity is not exact local metadata")
        models.append(
            {
                "name": item["name"],
                "digest": item["digest"],
                **{
                    name: _integer(item.get(name))
                    for name in ("size", "size_vram", "context_length")
                },
                "expires_at": _timestamp(item.get("expires_at")),
            }
        )
    log: dict[str, Any] = {
        "sha256": None,
        "loaded_backend_libraries": [],
        "latest_offload_layers": None,
        "latest_total_layers": None,
    }
    if server_log is not None:
        try:
            with Path(server_log).open("rb") as stream:
                raw = stream.read(MAX_METADATA_BYTES + 1)
            if len(raw) > MAX_METADATA_BYTES:
                raise ValueError("bounded log exceeded")
            text = raw.decode("utf-8")
            offloads = re.findall(r"offloaded (\d+)/(\d+) layers to GPU", text)
            libraries = re.findall(
                r"loaded (CPU|CUDA|ROCm|Vulkan|Metal) backend", text, flags=re.IGNORECASE
            )
            log = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "loaded_backend_libraries": sorted({name.upper() for name in libraries}),
                "latest_offload_layers": int(offloads[-1][0]) if offloads else None,
                "latest_total_layers": int(offloads[-1][1]) if offloads else None,
            }
        except (OSError, UnicodeError, ValueError) as error:
            log["observation_error"] = type(error).__name__
    return {
        "sampled_at": datetime.now(UTC).isoformat(),
        "ps_sha256": response_hash,
        "loaded_models": models,
        "log_observations": log,
        "loaded_model_backend": None,
        "scope": (
            "Read-only /ps allocation and historical log facts; "
            "model backend association unassessed"
        ),
    }


def verify_inventory(base_url: str, expected: dict[str, str]) -> dict[str, Any]:
    """Compare currently advertised exact tags/digests before dispatch, without pulls."""
    origin = _origin(base_url)
    tags, response_hash = _metadata(origin, "/api/tags")
    if not isinstance(tags.get("models"), list):
        raise PreflightError("model inventory is malformed")
    seen = {}
    for item in tags["models"]:
        if not isinstance(item, dict):
            raise PreflightError("model inventory contains a non-object")
        name = item.get("name")
        if name in expected:
            if (
                name in seen
                or item.get("digest") != expected[name]
                or any(
                    item.get(field) not in (None, "")
                    for field in ("remote_host", "remote_model", "remote_model_name")
                )
            ):
                raise PreflightError("pinned model inventory identity changed")
            seen[name] = item["digest"]
    if seen != expected:
        raise PreflightError("pinned model inventory identity missing")
    return {
        "tags_sha256": response_hash,
        "verified_tags": seen,
        "scope": "Observed metadata pin; host trust and dispatch TOCTOU remain",
    }


def _model(tag: dict[str, Any], shown: dict[str, Any], raw_hash: str) -> tuple[dict[str, Any], str]:
    name, digest = tag.get("name"), tag.get("digest")
    if (
        not isinstance(name, str)
        or _TAG.fullmatch(name) is None
        or name.lower().endswith(":latest")
        or "cloud" in name.lower()
        or not isinstance(digest, str)
        or _DIGEST.fullmatch(digest) is None
    ):
        raise PreflightError("existing model needs an exact non-cloud tag and SHA256 digest")
    remotes = [
        (key, value)
        for record in (tag, shown)
        for key, value in record.items()
        if key in ("remote_host", "remote_model", "remote_model_name")
    ]
    if any(value not in (None, "") for _, value in remotes):
        raise PreflightError("remote model metadata is prohibited")
    license_text = shown.get("license")
    if not isinstance(license_text, str) or not license_text.strip():
        raise PreflightError("model license metadata is missing")
    thinking = shown.get("thinking")
    values = thinking.get("values") if isinstance(thinking, dict) else None
    if not isinstance(values, list) or any(
        type(v) is not bool and _label(v) is None for v in values
    ):
        values = None
    thinking = (
        {"values": values, "default": thinking.get("default")}
        if isinstance(thinking, dict)
        and (type(thinking.get("default")) is bool or _label(thinking.get("default")) is not None)
        else None
    )
    capabilities = shown.get("capabilities")
    if not isinstance(capabilities, list) or not all(_label(v) is not None for v in capabilities):
        capabilities = None
    model_info = shown.get("model_info", {})
    if not isinstance(model_info, dict):
        model_info = {}
    context = {
        key: value
        for key, value in model_info.items()
        if _label(key) is not None
        and key.endswith(".context_length")
        and type(value) is int
        and value > 0
    }
    text_hashes = {
        key + "_sha256": (
            hashlib.sha256(shown[key].encode()).hexdigest()
            if isinstance(shown.get(key), str)
            else None
        )
        for key in ("license", "template", "parameters", "modelfile")
    }
    details = shown.get("details", {})
    if not isinstance(details, dict):
        details = {}
    safe_details: dict[str, Any] = {
        key: _label(details.get(key))
        for key in ("format", "family", "parameter_size", "quantization_level")
    }
    families = details.get("families")
    safe_details["families"] = (
        families
        if isinstance(families, list) and all(_label(f) is not None for f in families)
        else None
    )
    filename = f"license-{digest[:16]}.txt"
    return {
        "tag": name,
        "digest": digest,
        "model_bytes": _integer(tag.get("size")),
        "modified_at": _timestamp(tag.get("modified_at")),
        "details": safe_details,
        "architecture": _label(model_info.get("general.architecture")),
        "advertised_context_lengths": context,
        "requested_context_4096_within_advertised_limit": (
            None if not context else all(length >= 4096 for length in context.values())
        ),
        "capabilities": capabilities,
        "thinking_metadata": thinking if isinstance(thinking, dict) else None,
        "supported_thinking_values_advertised": values,
        "nonthinking_false_advertised": (
            None if values is None else any(type(v) is bool and v is False for v in values)
        ),
        "thinking_smoke_verified": False,
        "remote_fields_present": sorted({key for key, _ in remotes}),
        "remote_fields_empty": True,
        "local_execution_scope": (
            "Existing local tag plus cloud-disabled owned-server evidence; "
            "backend smoke still required"
        ),
        "license_file": filename,
        **text_hashes,
        "show_response_sha256": raw_hash,
        "requires_server_version": _label(shown.get("requires")),
        "loaded_model_backend": None,
        "offload_layers": None,
    }, license_text


def preflight(
    base_url: str,
    output_dir: str | Path,
    server_log: str | Path | None = None,
    owned_server_pid: int | None = None,
) -> dict[str, Any]:
    """Enumerate existing metadata and retain a sanitized manifest/license files.

    Requires numeric loopback, no redirects/proxies, matching cloud-disabled
    owned-server log/liveness and known sufficient RAM/disk before marking ready.
    Exact model tags/digests and advertised think/context metadata are recorded;
    actual output caps, truncation, backend and inference remain smoke questions.
    No server ownership is inferred from a PID or local URL alone.
    """
    origin = _origin(base_url)
    gate = resource_gate(output_dir, owned_server_pid)
    version, version_hash = _metadata(origin, "/api/version")
    tags, tags_hash = _metadata(origin, "/api/tags")
    loaded, loaded_hash = _metadata(origin, "/api/ps")
    if not isinstance(version.get("version"), str):
        raise PreflightError("server version metadata is missing")
    if not isinstance(tags.get("models"), list) or not isinstance(loaded.get("models"), list):
        raise PreflightError("model inventory metadata is malformed")
    loaded_models = []
    for item in loaded["models"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or _TAG.fullmatch(item["name"]) is None
            or "cloud" in item["name"].lower()
            or not isinstance(item.get("digest"), str)
            or _DIGEST.fullmatch(item["digest"]) is None
        ):
            raise PreflightError("loaded model metadata is not an exact local identity")
        loaded_models.append(
            {
                "name": item["name"],
                "digest": item["digest"],
                "size": _integer(item.get("size")),
                "size_vram": _integer(item.get("size_vram")),
                "expires_at": _timestamp(item.get("expires_at")),
            }
        )
    models, licenses = [], []
    for tag in tags["models"]:
        if not isinstance(tag, dict):
            raise PreflightError("model inventory contains a non-object")
        # Validate identities before using them in a request; no arbitrary URL/path.
        name = tag.get("name")
        if not isinstance(name, str) or _TAG.fullmatch(name) is None or "cloud" in name.lower():
            raise PreflightError("model inventory has an unsupported or cloud identity")
        shown, raw_hash = _metadata(origin, "/api/show", name)
        model, license_text = _model(tag, shown, raw_hash)
        models.append(model)
        licenses.append((model["license_file"], license_text))
    if len({model["tag"] for model in models}) != len(models):
        raise PreflightError("model inventory has duplicate tags")
    log = _log_evidence(server_log, origin)
    reasons = list(gate["blocking_reasons"])
    if owned_server_pid is None:
        reasons.append("owned_server_identity_not_supplied")
    if log["cloud_disabled"] is not True:
        reasons.append("server_cloud_disabled_unconfirmed")
    if not log["matching_listener"] or log.get("listener_version") != version["version"]:
        reasons.append("server_listener_log_mismatch")
    if not models:
        reasons.append("no_existing_models")
    if any(model["requested_context_4096_within_advertised_limit"] is not True for model in models):
        reasons.append("model_context_metadata_unconfirmed")
    manifest = {
        "schema": "egr-023-ollama-preflight-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "endpoint": origin,
        "server_version": version["version"],
        "owned_server_pid_supplied_by_host": owned_server_pid,
        "server_log_evidence": log,
        "metadata_hashes": {"version": version_hash, "tags": tags_hash, "ps": loaded_hash},
        "models": sorted(models, key=lambda model: model["tag"]),
        "loaded_models": loaded_models,
        "resource_gate": gate,
        "ready_for_backend_smoke": not reasons,
        "blocking_reasons": reasons,
        "generation_requests": 0,
        "model_load_requests": 0,
        "boundary": (
            "Metadata/liveness/resource preflight only; no measured inference, "
            "hard memory ceiling, template token accounting or authenticated ownership claim"
        ),
    }
    directory = Path(output_dir)
    filename = "environment-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    manifest["manifest_file"] = filename
    encoded = json.dumps(manifest, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    required_bytes = len(encoded.encode()) + sum(len(text.encode()) for _, text in licenses)
    if gate["raw_bytes"] is None or gate["raw_bytes"] + required_bytes > MAX_RAW_BYTES:
        raise PreflightError("disk envelope cannot preserve preflight metadata")
    if gate["disk_free_bytes"] is None or gate["disk_free_bytes"] < required_bytes:
        raise PreflightError("insufficient disk to preserve preflight metadata")
    directory.mkdir(parents=True, exist_ok=True)
    for license_filename, text in licenses:
        path = directory / license_filename
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise PreflightError("existing license record differs; preserve it")
        if not path.exists():
            path.write_bytes(text.encode("utf-8"))
    with (directory / filename).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded)
    return manifest
