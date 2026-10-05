"""Public raw archives cannot write outside a fresh bounded extraction root."""

import hashlib
import stat
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.extract_ollama_raw import extract  # noqa: E402


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/outside",
        "C:/outside",
        "raw\\outside",
        "raw/file:stream",
        "raw/NUL.txt",
        "raw/end.",
        "raw/./file",
    ],
)
def test_unsafe_paths_are_rejected_before_writing(tmp_path, name):
    archive = tmp_path / "raw.zip"
    with zipfile.ZipFile(archive, "w") as output:
        item = zipfile.ZipInfo()
        item.filename = item.orig_filename = name
        output.writestr(item, b"content")
    destination = tmp_path / "extract"
    with pytest.raises(ValueError, match="Unsafe"):
        extract(archive, destination, hashlib.sha256(archive.read_bytes()).hexdigest())
    assert not destination.exists()


def test_symlink_and_case_collisions_are_rejected(tmp_path):
    archive = tmp_path / "raw.zip"
    link = zipfile.ZipInfo("raw/link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(link, "../../outside")
    with pytest.raises(ValueError, match="Unsafe"):
        extract(
            archive, tmp_path / "link-extract", hashlib.sha256(archive.read_bytes()).hexdigest()
        )
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("raw/Data.json", b"one")
        output.writestr("raw/data.json", b"two")
    with pytest.raises(ValueError, match="duplicate"):
        extract(
            archive,
            tmp_path / "collision-extract",
            hashlib.sha256(archive.read_bytes()).hexdigest(),
        )


def test_hash_size_and_existing_directory_guards_and_normal_extraction(tmp_path, monkeypatch):
    from scripts import extract_ollama_raw

    archive = tmp_path / "raw.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("raw/calls.jsonl", b"{}\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="SHA256 differs"):
        extract(archive, tmp_path / "wrong", "0" * 64)
    monkeypatch.setattr(extract_ollama_raw, "MAX_BYTES", 2)
    with pytest.raises(ValueError, match="envelope"):
        extract(archive, tmp_path / "large", digest)
    monkeypatch.setattr(extract_ollama_raw, "MAX_BYTES", 100)
    root = tmp_path / "normal"
    assert extract(archive, root, digest)["expanded_bytes"] == 3
    assert (root / "raw/calls.jsonl").read_bytes() == b"{}\n"
    with pytest.raises(ValueError, match="new extraction"):
        extract(archive, root, digest)
