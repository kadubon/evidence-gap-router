"""Distribution verification rejects corrupted and incomplete wheel manifests."""

import base64
import csv
import hashlib
import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest


def wheel(*, corrupt=False, missing=False, duplicated=False, package=b"", metadata=b"example"):
    files = {
        "evidence_gap_router/py.typed": package,
        "example.dist-info/METADATA": b"Name: " + metadata + b"\n",
    }
    record = "example.dist-info/RECORD"
    text = io.StringIO()
    writer = csv.writer(text, lineterminator="\n")
    for name, content in files.items():
        if missing and name.endswith("py.typed"):
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
        writer.writerow([name, "sha256=" + digest, len(content)])
    writer.writerow([record, "", ""])
    if duplicated:
        writer.writerow([record, "", ""])
    files[record] = text.getvalue().encode()
    if corrupt:
        files["evidence_gap_router/py.typed"] = b"changed"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    data.seek(0)
    return zipfile.ZipFile(data)


def test_actual_record_covers_each_file_and_its_bytes(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("package_audit")
    with wheel() as archive:
        module.verify_record(archive)
    for options, message in [
        ({"corrupt": True}, "byte mismatch"),
        ({"missing": True}, "enumerate every file"),
        ({"duplicated": True}, "enumerate every file"),
    ]:
        with wheel(**options) as archive, pytest.raises(ValueError, match=message):
            module.verify_record(archive)


def test_frozen_package_requires_exact_bytes_but_allows_doc_metadata(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("package_audit")
    paths = []
    for index, options in enumerate([{}, {"metadata": b"new docs"}, {"package": b"changed"}]):
        path = tmp_path / f"{index}.whl"
        with wheel(**options) as archive:
            path.write_bytes(archive.fp.getvalue())
        paths.append(path)
    directory = tmp_path / "benchmarks"
    (directory / "results").mkdir(parents=True)
    (directory / "protocol.json").write_bytes(b"declared protocol")
    (directory / "harness.py").write_bytes(b"declared experiment")
    freeze = directory / "results/freeze.json"
    freeze.write_text(
        json.dumps(
            {
                "candidate_package_sha256": module.package_fingerprint(paths[0]),
                "manifest_sha256": hashlib.sha256(b"declared protocol").hexdigest(),
                "harness_sha256": hashlib.sha256(b"harness.pydeclared experiment").hexdigest(),
            }
        )
    )
    module.verify_benchmark_package(paths[1], freeze)
    with pytest.raises(ValueError, match="differ"):
        module.verify_benchmark_package(paths[2], freeze)
    (directory / "harness.py").write_bytes(b"changed experiment")
    with pytest.raises(ValueError, match="harness differs"):
        module.verify_benchmark_package(paths[1], freeze)
