"""Compare actual official PyPI wheel/sdist bytes with the release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def verify(dist: Path, version: str, checksums: Path) -> None:
    expected = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dist.iterdir()}
    if set(expected) != {
        f"evidence_gap_router-{version}-py3-none-any.whl",
        f"evidence_gap_router-{version}.tar.gz",
    }:
        raise ValueError("Release artifacts must be exactly the expected wheel and sdist")
    url = f"https://pypi.org/pypi/evidence-gap-router/{version}/json"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                document = json.load(response)
            files = {item["filename"]: item for item in document["urls"]}
            if set(files) == set(expected):
                break
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
        if attempt == 5:
            raise RuntimeError("Official PyPI files did not appear within bounded polling")
        time.sleep(20)
    if document["info"]["name"] != "evidence-gap-router" or document["info"]["version"] != version:
        raise ValueError("Official PyPI project/version mismatch")
    for filename, digest in expected.items():
        item = files[filename]
        if item.get("yanked") or item["digests"]["sha256"] != digest:
            raise ValueError(f"PyPI metadata hash mismatch or yanked file: {filename}")
        parsed = urllib.parse.urlparse(item["url"])
        if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
            raise ValueError("Unexpected official file origin")
        with urllib.request.urlopen(item["url"], timeout=30) as response:
            actual = hashlib.sha256(response.read()).hexdigest()
        if actual != digest:
            raise ValueError(f"Downloaded bytes mismatch: {filename}")
        print(f"verified {digest}  {filename}")
    checksums.parent.mkdir(parents=True, exist_ok=True)
    checksums.write_text(
        "".join(f"{expected[name]}  {name}\n" for name in sorted(expected)), encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("version")
    parser.add_argument("--checksums", type=Path, default=Path("release/SHA256SUMS"))
    args = parser.parse_args()
    verify(args.dist, args.version, args.checksums)
