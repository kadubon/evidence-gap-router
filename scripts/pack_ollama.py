"""Archive the retained local experiment without weights, logs, or absolute paths."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

MAX_BYTES = 512 * 1024**2
PRIVATE_PATH = re.compile(
    r"(?i)(?:\b[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s\"']+"
    r"|(?<![\w:])/(?:Users|home)/[^/\s\"']+)"
)
CREDENTIAL = re.compile(
    r"(?:\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}|\bpypi-[A-Za-z0-9_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\b(?:Bearer|Basic) [A-Za-z0-9+/=_-]{20,}"
    r"|\bhttps?://[^/\s:@]+:[^/@\s]+@)"
)
SECRET_KEYS = {
    "apikey",
    "accesstoken",
    "refreshtoken",
    "password",
    "passwd",
    "secretaccesskey",
    "clientsecret",
    "cookie",
}
PLACEHOLDERS = {"redacted", "placeholder", "example", "replace_me", "your_api_key", "not set"}


class PrivacyError(ValueError):
    """A publication-sensitive value was found; no original record is altered."""


def checked_path(path: Path) -> Path:
    """Reject symlinks and directory junctions before resolving any ancestor."""
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Archive paths cannot have symlink or junction ancestors")
    return absolute.resolve()


def scan_string(value: str, name: str) -> None:
    if PRIVATE_PATH.search(value.replace("\\\\", "\\")):
        raise PrivacyError(f"Private user absolute path in {name}; do not publish")
    if CREDENTIAL.search(value):
        raise PrivacyError(f"Credential value in {name}; do not publish")


def json_value(content: str | bytes, name: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        for key, value in items:
            normalized = key.lower().replace("_", "").replace("-", "")
            if isinstance(value, str):
                secret = (
                    normalized in SECRET_KEYS
                    and value.strip()
                    and value.lower().strip() not in PLACEHOLDERS
                )
                header = normalized in {"authorization", "proxyauthorization"} and re.match(
                    r"(?i)^(?:Bearer|Basic)\s+\S+", value
                )
                if secret or header:
                    raise PrivacyError(f"Credential field value in {name}; do not publish")
        return dict(items)

    return json.loads(content, object_pairs_hook=pairs)


def scan_value(value: Any, name: str) -> None:
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, content in item.items():
                normalized = str(key).lower().replace("_", "").replace("-", "")
                if (
                    normalized in SECRET_KEYS
                    and isinstance(content, str)
                    and content.strip()
                    and content.lower().strip() not in PLACEHOLDERS
                ):
                    raise PrivacyError(f"Credential field value in {name}; do not publish")
                if key == "raw_response_base64":
                    if not isinstance(content, str) or len(content) > 1_398_104:
                        raise ValueError(f"Unbounded/invalid encoded response in {name}")
                    try:
                        decoded = base64.b64decode(content, validate=True)
                    except (ValueError, UnicodeError) as error:
                        raise ValueError(f"Invalid encoded response in {name}") from error
                    scan_string(decoded.decode("utf-8", errors="replace"), name)
                    try:
                        parsed = json_value(decoded, name)
                    except PrivacyError:
                        raise
                    except (ValueError, UnicodeError, RecursionError):
                        # Malformed original responses remain; visible text is still scanned.
                        pass
                    else:
                        stack.append(parsed)
                stack.append(content)
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, str):
            scan_string(item, name)
            if item.lstrip().startswith(("{", "[")):
                try:
                    parsed = json_value(item, name)
                except PrivacyError:
                    raise
                except (ValueError, RecursionError):
                    continue
                if isinstance(parsed, (dict, list)):
                    stack.append(parsed)


def public_text(content: bytes, name: str) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"Unexplained binary source in {name}") from error
    scan_string(text, name)
    if Path(name).suffix == ".json":
        scan_value(json_value(text, name), name)
    elif Path(name).suffix == ".jsonl":
        if content and not content.endswith(b"\n"):
            raise ValueError(f"Incomplete journal tail in {name}; retain original")
        for line in text.splitlines():
            scan_value(json_value(line, name), name)
    elif Path(name).suffix == ".csv":
        for row in csv.DictReader(io.StringIO(text)):
            scan_value(row, name)


def pack(
    raw: Path, output: Path, freeze_path: Path, summary: Path, *, repository: Path | None = None
) -> dict[str, Any]:
    """Keep full allowed histories; reject mismatches instead of silently redacting."""
    raw, output, freeze_path, summary = map(checked_path, (raw, output, freeze_path, summary))
    if output.is_relative_to(raw) or output.is_relative_to(summary):
        raise ValueError("Archive output must be outside raw and summary inputs")
    if output.exists():
        raise ValueError("Never replace an existing raw archive")
    root = checked_path(repository or Path(__file__).resolve().parents[1])
    freeze = json.loads(freeze_path.read_bytes())
    directory = root / "experiments/ollama"
    harness_paths = sorted(directory.glob("*.py"))
    hashes = {
        p.name: hashlib.sha256(checked_path(p).read_bytes()).hexdigest() for p in harness_paths
    }
    combined = b"".join(p.name.encode() + p.read_bytes() for p in harness_paths)
    protocol_path = checked_path(directory / "protocol.json")
    if (
        hashes != freeze["harness_files"]
        or hashlib.sha256(combined).hexdigest() != freeze["harness_sha256"]
        or hashlib.sha256(protocol_path.read_bytes()).hexdigest() != freeze["manifest_sha256"]
    ):
        raise ValueError("Current harness/protocol differs from supplied exact freeze")
    protocol = json.loads(protocol_path.read_bytes())
    for filename, key in (
        ("frozen-public-tasks.json", "public_tasks_sha256"),
        ("evaluation-only-gold.json", "evaluation_only_gold_sha256"),
        ("preflight/manifest.json", "preflight_sha256"),
    ):
        if hashlib.sha256(checked_path(raw / filename).read_bytes()).hexdigest() != freeze[key]:
            raise ValueError("Raw task/gold/preflight bytes differ from freeze")
    if not (raw / "calls.jsonl").is_file():
        raise ValueError("Use the dedicated live-data directory with its original journal")
    historical = raw / "segments/initial-4h"
    initial_path = checked_path(historical / "manifest.json")
    expected_initial = protocol["budget_amendment"]["initial_segment_manifest_sha256"]
    if hashlib.sha256(initial_path.read_bytes()).hexdigest() != expected_initial:
        raise ValueError("Historical segment manifest differs from preserved provenance")
    for filename, expected in json.loads(initial_path.read_bytes())["files"].items():
        source = checked_path(historical / filename)
        if not source.is_relative_to(historical):
            raise ValueError("Historical manifest path leaves its segment")
        content = source.read_bytes()
        if (
            len(content) != expected["bytes"]
            or hashlib.sha256(content).hexdigest() != expected["sha256"]
        ):
            raise ValueError("Historical segment file differs from retained manifest")
    sources: dict[str, Path] = {}
    excluded: dict[str, str] = {}
    wheel = historical / f"evidence_gap_router-{protocol['package_version']}-py3-none-any.whl"
    for path in sorted(raw.rglob("*")):
        checked = checked_path(path)
        if not checked.is_relative_to(raw):
            raise ValueError("Raw source leaves its dedicated directory")
        if not path.is_file():
            continue
        name = "raw/" + path.relative_to(raw).as_posix()
        if path.name == "artifact-provenance.json" and not path.is_relative_to(historical):
            excluded[name] = "Published separately to avoid a ZIP self-hash cycle"
            continue
        if path.suffix in {".log", ".lock"}:
            excluded[name] = "Private server log or operational lock, not a request/receipt event"
            continue
        allowed = (
            path.suffix in {".json", ".jsonl", ".csv"}
            or (path.suffix == ".py" and path.parent == historical)
            or (
                path.suffix == ".txt"
                and path.parent == raw / "preflight"
                and re.fullmatch(r"license-[0-9a-f]{16}\.txt", path.name)
            )
        )
        if checked == wheel:
            if hashlib.sha256(path.read_bytes()).hexdigest() != freeze["candidate_wheel_sha256"]:
                raise ValueError("Historical candidate wheel differs from pinned freeze")
        elif not allowed:
            raise ValueError(f"Unexplained source type: {name}; no history silently omitted")
        sources[name] = path
    sources.update({"harness/" + p.name: p for p in harness_paths})
    sources["harness/protocol.json"] = protocol_path
    sources["freeze-v0.2.3.json"] = freeze_path
    for path in sorted(summary.iterdir()):
        checked_path(path)
        if path.is_dir():
            raise ValueError("Summary must contain only explicit result files")
        if path.name == "artifact-provenance.json":
            excluded["analysis/" + path.name] = (
                "Published separately to avoid a ZIP self-hash cycle"
            )
            continue
        if path.suffix not in {".json", ".jsonl", ".csv", ".md"}:
            raise ValueError("Unexpected summary source type")
        sources["analysis/" + path.name] = path
    supplemental = root / "scripts/recount_ollama_023.py"
    if supplemental.exists():
        sources["supplemental/recount_ollama_023.py"] = checked_path(supplemental)
    if sum(path.stat().st_size for path in sources.values()) > MAX_BYTES:
        raise ValueError("Raw archive source envelope exceeds 512 MiB")
    manifest = {}
    for name, path in sources.items():
        content = path.read_bytes()
        if path != wheel:
            public_text(content, name)
        manifest[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sources.items():
            content = path.read_bytes()
            if (
                len(content) != manifest[name]["bytes"]
                or hashlib.sha256(content).hexdigest() != manifest[name]["sha256"]
            ):
                raise ValueError("Source changed while packing; retain originals, do not publish")
            archive.writestr(name, content)
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        archive.writestr(
            "EXCLUDED_SOURCES.json", json.dumps(excluded, indent=2, sort_keys=True) + "\n"
        )
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Archive integrity or entry uniqueness failed")
        for name, item in manifest.items():
            content = archive.read(name)
            if (
                len(content) != item["bytes"]
                or hashlib.sha256(content).hexdigest() != item["sha256"]
            ):
                raise ValueError("Archive manifest byte verification failed")
    return {
        "filename": output.name,
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "verified_entries": len(manifest),
        "explicitly_excluded_sources": excluded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(pack(args.raw, args.output, args.freeze, args.summary)))


if __name__ == "__main__":
    main()
