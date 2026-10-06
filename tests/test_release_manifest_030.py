"""R30 finite shipping-identity assertions; no measured-performance artifacts."""

import base64
import csv
import hashlib
import importlib
import io
import json
import zipfile
from pathlib import Path

import pytest


def archive(files, *, record=False):
    files = dict(files)
    if record:
        name = "example.dist-info/RECORD"
        text = io.StringIO()
        writer = csv.writer(text, lineterminator="\n")
        for path, data in files.items():
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            writer.writerow((path, "sha256=" + digest, len(data)))
        writer.writerow((name, "", ""))
        files[name] = text.getvalue().encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for name, data in files.items():
            output.writestr(name, data)
    return stream.getvalue()


@pytest.mark.parametrize("defect", (None, "dirty", "commit", "package", "license"))
def test_R30_manifest_binds_clean_exact_source_package_and_license(monkeypatch, tmp_path, defect):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("release_manifest")
    source = {
        "src/evidence_gap_router/_version.py": b'__version__ = "0.3.0"\n',
        "LICENSE": b"original complete license fixture",
    }
    package = {
        "evidence_gap_router/_version.py": source["src/evidence_gap_router/_version.py"],
        "example.dist-info/licenses/LICENSE": source["LICENSE"],
    }
    if defect == "package":
        package["evidence_gap_router/_version.py"] = b'__version__ = "0.2.4"\n'
    if defect == "license":
        package["example.dist-info/licenses/LICENSE"] = b"altered license"
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "example.whl").write_bytes(archive(package, record=True))
    (dist / "example.tar.gz").write_bytes(b"sdist already checked by package_audit")
    monkeypatch.setattr(module, "audit", lambda _: "0.3.0")

    def git(args, **kwargs):
        if args[1] == "archive":
            return archive(source)
        if args[1] == "status":
            return " M source" if defect == "dirty" else ""
        if args[-1] == "HEAD":
            return "another" if defect == "commit" else "exact"
        return "tree"

    monkeypatch.setattr(module.subprocess, "check_output", git)
    if defect:
        with pytest.raises(ValueError):
            module.create(dist, "exact")
    else:
        value = module.create(dist, "exact")
        assert value["commit"] == "exact" and value["version"] == "0.3.0"
        assert value["efficacy"] == "unmeasured"
        assert value["new_llm_requests"] == value["new_efficacy_or_performance_experiments"] == 0
        assert set(value["source_files"]) == set(source)
        assert value["license_sha256"] == hashlib.sha256(source["LICENSE"]).hexdigest()
        assert "release-manifest.json" not in value["source_files"]


def test_R30_old_freeze_cannot_be_shipping_or_new_measurement_evidence(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("package_audit")
    path = tmp_path / "new-0.3.0.whl"
    path.write_bytes(
        archive({"evidence_gap_router/_version.py": b'__version__ = "0.3.0"'}, record=True)
    )
    freeze = tmp_path / "old-freeze.json"
    freeze.write_text(json.dumps({"candidate_package_sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(ValueError, match="differ from the measured"):
        module.verify_benchmark_package(path, freeze)


@pytest.mark.parametrize("defect", (None, "docs", "generation", "experiment"))
def test_R30_six_profile_gate_requires_docs_and_zero_new_experiments(monkeypatch, tmp_path, defect):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("release_notes")
    dist, profiles = tmp_path / "dist", tmp_path / "profiles"
    dist.mkdir()
    profiles.mkdir()
    data = b"fixed artifact fixture"
    (dist / "example.whl").write_bytes(data)
    for name, (system, architecture, python) in module.PROFILES.items():
        report = dict(
            os=system,
            architecture=architecture,
            python=python + ".1",
            package_version="0.3.0",
            wheel_sha256=hashlib.sha256(data).hexdigest(),
            installed_smoke="passed",
            pytest_exit_code=0,
            rosetta_translated=False,
            pydantic_version="locked",
            pydantic_core_version="locked",
            documentation_examples={"status": "passed"},
            new_llm_requests=0,
            new_efficacy_or_performance_experiments=0,
        )
        if name == "macos-intel-3.12.json":
            if defect == "docs":
                report["documentation_examples"]["status"] = "failed"
            elif defect == "generation":
                report["new_llm_requests"] = 1
            elif defect == "experiment":
                report["new_efficacy_or_performance_experiments"] = 1
        (profiles / name).write_text(json.dumps(report), encoding="utf-8")
    output = tmp_path / "notes.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "release_notes",
            "--version",
            "0.3.0",
            "--commit",
            "exact",
            "--manual-run",
            "1",
            "--release-run",
            "2",
            "--profiles",
            str(profiles),
            "--dist",
            str(dist),
            "--output",
            str(output),
        ],
    )
    if defect:
        with pytest.raises(ValueError):
            module.main()
        assert not output.exists()
    else:
        module.main()
        text = output.read_text("utf-8")
        assert "unmeasured" in text and "benchmark smoke" not in text
