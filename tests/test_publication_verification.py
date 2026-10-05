"""Publication waits for pip's index without hiding altered public bytes."""

import importlib
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def verification(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("verify_pypi")


def response(files):
    return io.BytesIO(json.dumps({"name": "evidence-gap-router", "files": files}).encode())


def test_version_api_visibility_does_not_replace_install_index(verification, monkeypatch):
    expected = {"example.whl": "a" * 64, "example.tar.gz": "b" * 64}
    documents = [
        response([]),
        response(
            [
                {"filename": name, "hashes": {"sha256": digest}, "yanked": False}
                for name, digest in expected.items()
            ]
        ),
    ]
    requests, pauses = [], []

    def download(request, timeout):
        requests.append(request)
        return documents.pop(0)

    monkeypatch.setattr(verification.urllib.request, "urlopen", download)
    monkeypatch.setattr(verification.time, "sleep", pauses.append)
    verification.wait_for_index(expected, attempts=2, interval=15)
    assert len(requests) == 2 and pauses == [15]
    assert requests[0].full_url == "https://pypi.org/simple/evidence-gap-router/"
    assert "application/vnd.pypi.simple.v1+json" in requests[0].get_header("Accept")


@pytest.mark.parametrize("yanked,digest", [(False, "b" * 64), (True, "a" * 64)])
def test_changed_or_yanked_index_file_fails_without_retry(
    verification, monkeypatch, yanked, digest
):
    monkeypatch.setattr(
        verification.urllib.request,
        "urlopen",
        lambda *args, **kwargs: response(
            [{"filename": "example.whl", "hashes": {"sha256": digest}, "yanked": yanked}]
        ),
    )
    monkeypatch.setattr(verification.time, "sleep", lambda _: pytest.fail("unexpected retry"))
    with pytest.raises(ValueError, match="hash mismatch or yanked"):
        verification.wait_for_index({"example.whl": "a" * 64})


def test_index_polling_has_a_finite_deadline(verification, monkeypatch):
    calls, pauses = [], []

    def missing(*args, **kwargs):
        calls.append(1)
        return response([])

    monkeypatch.setattr(verification.urllib.request, "urlopen", missing)
    monkeypatch.setattr(verification.time, "sleep", pauses.append)
    with pytest.raises(RuntimeError, match="official install index"):
        verification.wait_for_index({"example.whl": "a" * 64}, attempts=3, interval=0)
    assert len(calls) == 3 and len(pauses) == 2
