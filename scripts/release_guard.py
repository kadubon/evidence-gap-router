"""Read-only tag admission: exact repository, version, main history and manual CI."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

from package_audit import source_version


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], text=True).strip()


def validated_manual_run(commit: str) -> int:
    token = os.environ["GH_TOKEN"]
    for page in range(1, 11):
        url = (
            "https://api.github.com/repos/kadubon/evidence-gap-router/actions/workflows/"
            f"workflow.yml/runs?event=workflow_dispatch&status=success&per_page=100&page={page}"
        )
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            runs = json.load(response)["workflow_runs"]
        for run in runs:
            if (
                run["head_sha"] == commit
                and run["event"] == "workflow_dispatch"
                and run["conclusion"] == "success"
                and run["status"] == "completed"
            ):
                return int(run["id"])
        if len(runs) < 100:
            break
    raise ValueError("No successful manual workflow.yml run for this exact commit")


def main() -> None:
    version = source_version()
    event = os.environ["GITHUB_EVENT_NAME"]
    is_release = event == "push" and os.environ["GITHUB_REF"].startswith("refs/tags/")
    commit = git("rev-parse", "HEAD")
    manual_run = ""
    if is_release:
        if os.environ["GITHUB_REPOSITORY"] != "kadubon/evidence-gap-router":
            raise ValueError("Publishing is restricted to kadubon/evidence-gap-router")
        tag = os.environ["GITHUB_REF_NAME"]
        if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) or tag != f"v{version}":
            raise ValueError("Release tag must exactly equal the package version")
        if git("rev-parse", f"refs/tags/{tag}^{{commit}}") != commit:
            raise ValueError("Tag does not point at the checked-out commit")
        subprocess.run(["git", "merge-base", "--is-ancestor", commit, "origin/main"], check=True)
        manual_run = str(validated_manual_run(commit))
    output = (
        f"version={version}\ncommit={commit}\n"
        f"release={'true' if is_release else 'false'}\nmanual_run={manual_run}\n"
    )
    print(output, end="")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
        handle.write(output)


if __name__ == "__main__":
    main()
