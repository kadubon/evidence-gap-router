# Release procedure

Source publication, GitHub Release, PyPI upload and public-install verification
are four separate outcomes. A tag or pending publisher alone establishes none
of the later outcomes. Do not move a public tag, overwrite uploaded files or
describe unexecuted checks as passing.

## Local and manual validation

Run the checks from the repository root using a project-local `.venv`:

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest
uv build --no-sources
uv run --locked python -c 'from pathlib import Path; Path("dist/.gitignore").unlink(missing_ok=True)'
uv run --locked twine check dist/*
uv run --locked python scripts/package_audit.py dist
```

uv's build-generated `dist/.gitignore` is removed specifically before auditing;
do not silently ignore other unexpected files. The artifact audit checks exactly
one wheel and sdist, authoritative version,
Python/license metadata, Apache license, typing marker and packaged CSV/JSON
fixtures. Test the wheel in a new environment outside the repository with an
ordinary noneditable install. Build and install from the sdist as well. The
repository's `scripts/smoke.py` checks the installed SDK, CLI and bundled demo;
run it with the clean environment's Python from that external directory.

Review `git status`, tracked and untracked files, archives and metadata. Exclude
credentials, personal data, `.venv`, caches and unrelated project files. Commit
and push `main` normally, without force push. There is one workflow file:
`.github/workflows/workflow.yml`. It starts only by dispatch or a `v*` tag push.
Run a combined manual check after local changes are complete:

```sh
gh workflow run workflow.yml --repo kadubon/evidence-gap-router --ref main
gh run list --repo kadubon/evidence-gap-router --workflow workflow.yml --event workflow_dispatch --limit 5
gh run view RUN_ID --repo kadubon/evidence-gap-router
```

Record the successful run ID and exact `head_sha`. Manual checks never publish,
including dispatches targeting tag refs. Linux Python 3.12 runs the complete
locked gate and builds the wheel/sdist. Linux clean-wheel and clean-sdist smoke
and Windows Python 3.12 installation smoke must pass. Windows consumes the same
Linux-built wheel artifact. Fix causes before rerunning failed CI.

## Trusted Publishing configuration

Use GitHub Actions OIDC through the official `pypa/gh-action-pypi-publish`
release. Do not create a long-lived PyPI token as a fallback. GitHub CLI
authentication does not authenticate the PyPI account.

For a new project, sign into [PyPI account publishing](https://pypi.org/manage/account/publishing/)
and register a pending GitHub publisher with these exact values:

| PyPI field | Value |
| --- | --- |
| PyPI project name | `evidence-gap-router` |
| Owner | `kadubon` |
| Repository name | `evidence-gap-router` |
| Workflow filename | `workflow.yml` |
| Environment name | `pypi` |

For an already owned project use that project's publishing settings instead.
Do not reuse a third-party project. A pending publisher neither creates the
project nor reserves its name. The project is created by its first successful
trusted upload. [PyPI documents this distinction](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

Verify the [GitHub `pypi` environment](https://github.com/kadubon/evidence-gap-router/settings/environments),
restrict deployments to release tags where supported, and preserve existing
reviewers and protection rules. Required review must be completed normally.
Check the actual publisher and environment before pushing the first release
tag. If PyPI login or publisher registration is unavailable, finish source,
build and manual CI, report PyPI as unpublished, and leave the tag unpushed.

## Tag release and public verification

Once external configuration is confirmed and manual CI passed for the unchanged
commit, verify version and main history and push the annotated tag:

```sh
git switch main
git status --short
git rev-parse HEAD
git tag -a v0.1.0 -m "evidence-gap-router 0.1.0"
git push origin v0.1.0
gh run list --repo kadubon/evidence-gap-router --workflow workflow.yml --event push --limit 5
gh run view RELEASE_RUN_ID --repo kadubon/evidence-gap-router
```

If `main` changed after manual validation, validate the new exact commit before
tagging. Use the authenticated user push path: a tag created with a workflow's
`GITHUB_TOKEN` can be subject to event suppression. Confirm that the tag workflow
actually started, rather than inferring execution from tag existence.

The release guard requires the exact repository, tag push, exact `vVERSION`,
matching source/distribution versions, tag target in `main` history and a prior
successful manual run for the same commit. Linux and Windows gates precede
upload. Only the publish job has `id-token: write`, uses environment `pypi`, and
runs the official action on the existing wheel/sdist. It runs no project scripts
and performs no rebuild. Manual concurrency is separate from tag concurrency,
so a manual run cannot cancel publication.

After upload, the workflow makes a bounded check of official PyPI JSON and
downloads both actual files to compare SHA-256 with the build artifacts. It
uses a new environment outside the repository and performs:

```sh
python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple evidence-gap-router==0.1.0
```

It then runs installed-package SDK/CLI/demo smoke and creates a GitHub Release
containing the same wheel, sdist and `SHA256SUMS`. Only this final job has
`contents: write`. Hash equality demonstrates equality of those observed bytes,
not a completely reproducible source build or product performance.

Do not use `skip-existing` to mask collisions or partial publication. If upload
partly succeeded, download the original workflow artifact, compare existing
PyPI filenames/hashes using `scripts/verify_pypi.py`, and report which files are
present. Do not rerun upload blindly. If public smoke fails, report **uploaded,
post-publication verification failed**. Published bytes are never replaced;
changes require a new version. If only the final verification/release job failed,
resolve its cause and rerun only that job after checking for an existing release.

## Initial external-setting status

At setup inspection on 2026-10-05, the PyPI publishing page required account
login, so a pending publisher was not confirmed through the available session.
This records an inspection, not a permanent status assertion. The operator must
confirm login and the five fields above before the first tag push. Successful
publication is established only by actual upload and public-byte/install checks.

## Primary documentation and action pins

Checked on 2026-10-05:

- [uv package build and publish](https://docs.astral.sh/uv/guides/package/)
- [Add a PyPI publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Use a PyPI publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)

Official release refs were checked through GitHub's release and Git-ref APIs;
the workflow pins the resolved commits. The PyPI action's annotated release tag
was dereferenced to its commit. uv is explicitly pinned to the observed 0.12.19.

| Action | Official release | Commit |
| --- | --- | --- |
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| astral-sh/setup-uv | v10.2.0 | `c18668ad3cf93ea998bef934396af7bb5c839dc7` |
| actions/upload-artifact | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| actions/download-artifact | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |
| pypa/gh-action-pypi-publish | v1.14.2 | `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` |
