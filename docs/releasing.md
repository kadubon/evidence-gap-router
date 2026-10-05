# Release procedure

Source publication, GitHub Release, PyPI upload and public-install verification
are separate outcomes. Do not move a public tag, replace public bytes, weaken
environment protection or describe unexecuted checks as passed. This updates an
existing project; v0.1.0, v0.2.0 and v0.2.1 remain unchanged.

## Freeze and measure before final publication

Commit the runtime, checkers, experiment code and protocol before confirmation. Build
the candidate from that exact archive, install it outside the checkout and freeze
the implementation commit, wheel/package hashes, manifest and matched environment.
Use the official v0.2.1 wheel/hash for the separate baseline environment. Its
wheel SHA256 is `61129ec160c6c9d718f5173fa0281cdcc735cfdc9222138f45584a6b71202917`.
Development precedes freeze. The previously observed 240 tasks are a regression
set: the new method comparison fixes original order and random seed 17, rather
than claiming unseen holdout or inventing intervals for unexecuted variants.
New confirmation inputs use the separately fixed unused seed and manifest.
Proof graphs and candidate-helper graphs are measured separately; normal timing,
diagnostic visits and allocation/memory measurements have distinct processes.
Run measurements serially under the protocol's recorded wall/CPU/memory limits.
A runtime/protocol fix after confirmation requires retained old results and a
new protocol with unused confirmation inputs; do not tune seeds to obtain a gain.

Keep raw JSONL/CSV and scaling records outside the wheel. A later docs/results
commit records the freeze, small summary, English report and Japanese summary.
Large raw results are a separately checksummed Release asset. Final CI calls
`package_audit.py --benchmark-freeze benchmarks/results/freeze-v0.2.2.json` so documentation
metadata changes cannot conceal changed measured package bytes. The sdist rebuilt
wheel must also have the same package fingerprint. The benchmark code hashes are
recorded independently of the later results files, avoiding a self-hash cycle.
The original `benchmarks/results/freeze.json`, versioned v0.2.1 results/reports,
`benchmarks/protocol-v0.2.1.json` and official raw ZIP remain unchanged. Raw
reclassification in `benchmarks/results/v0.2.1-erratum/` is separate from newly
executed results in `benchmarks/results/v0.2.2/`. The erratum never promotes an
unknown resource/effect stop to known safe abstention or rewrites old CPU timings.

## Local and exact-commit manual validation

From the repository root, with uv-managed Python and project-local `.venv`:

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest
uv build --no-sources
uv run --locked python -c 'from pathlib import Path; Path("dist/.gitignore").unlink(missing_ok=True)'
uv run --locked twine check dist/*
uv run --locked python scripts/package_audit.py dist --benchmark-freeze benchmarks/results/freeze-v0.2.2.json
```

Remove only uv's generated `dist/.gitignore`; other unexpected files remain errors.
Start with no stale distributions, without deleting unrelated files. Archive audit
requires exactly one wheel/sdist, authoritative version/Python/SPDX metadata, the
full unchanged Apache LICENSE, typing marker, implementation modules, migration
reader and all packaged example fixtures. Inspect git status and archives for
credentials, unrelated files, caches or local/editable dependencies.

Test the existing wheel from a new environment outside the checkout, for example:

```sh
uv run --no-project --python 3.12 python scripts/native_check.py --wheel dist/evidence_gap_router-0.2.2-py3-none-any.whl --version 0.2.2 --python 3.12 --platform Linux --architecture x86_64 --report /tmp/egr-native-linux.json
```

On Windows use `--platform Windows --architecture x86_64` and an external report
path. The helper creates a clean venv, installs the actual wheel with locked
runtime constraints and pytest, copies regressions and the small benchmark outside
the source, verifies import locations and runs both installed smokes.
Build/install the sdist separately and compare its package bytes with the release
wheel using `package_audit.py --rebuilt-wheel PATH`.
`scripts/smoke.py --expected-version 0.2.2` receives the actual expected version;
it must run with that clean environment's isolated Python outside the repository.

Commit/push `main` normally, then dispatch combined CI only after changes are ready:

```sh
gh workflow run workflow.yml --repo kadubon/evidence-gap-router --ref main
gh run list --repo kadubon/evidence-gap-router --workflow workflow.yml --event workflow_dispatch --limit 5
gh run view RUN_ID --repo kadubon/evidence-gap-router
```

Record exact `head_sha` and run ID. All six native jobs must complete successfully:
Linux 3.12, Windows x64 3.12, macOS arm64 3.12, macOS Intel 3.12, Linux 3.13 and
Linux 3.14. Skipped/missing jobs are not success. Manual runs, including a dispatch
at a tag ref, never publish. Any changed commit needs a new successful manual run.

Before creating the tag, download that exact successful manual run's distribution
artifact and all six native JSON reports into a new external directory. Confirm
the reported wheel hashes match its wheel, the six canonical benchmark outcome
hashes agree, and each report has the expected actual OS/architecture/Python,
locked Pydantic/core, no Rosetta translation, passing pytest and installed smoke.
Check the actual selected runtime tests and portable smoke outcomes, including
the new helper/resolution/selector regressions; do not substitute an old outcome
hash for the newly executed report. Source-only archive/experiment tests run in
the full Linux source gate and are listed separately in each native report.
Record the run ID, commit, wheel hash and agreed benchmark hash. A missing,
failed or differing report prevents tagging. The workflow checks cross-profile
outcome equality again after upload; this pre-tag comparison establishes it before
publishing. Archive the comparison evidence with the validation records.

There is one workflow, `.github/workflows/workflow.yml`, triggered only by dispatch
or `v*` tag pushes. Linux 3.12 builds the release distributions once after locked
gates. The other profiles install that same uploaded wheel. A separate sdist
rebuild tests source distribution usability without replacing the release wheel.
Native JSON reports record actual platform/architecture/interpreter/imports,
dependency versions/native wheel tags and the original release-wheel hash.

## Existing Trusted Publisher and environment

Inspect the existing project's PyPI publishing settings; do not unconditionally
create a new Pending Publisher or use a long-lived token as a fallback. GitHub CLI
authentication does not authenticate PyPI. Keep these existing values:

| PyPI field | Value |
| --- | --- |
| Project | `evidence-gap-router` |
| Owner | `kadubon` |
| Repository | `evidence-gap-router` |
| Workflow filename | `workflow.yml` |
| Environment | `pypi` |

Use the official `pypa/gh-action-pypi-publish` action with GitHub OIDC. Verify
[GitHub environment `pypi`](https://github.com/kadubon/evidence-gap-router/settings/environments)
and complete any required review normally. Preserve existing tag restrictions,
reviewers and protections. If authentication, publisher or required approval is
actually unavailable, finish implementation/local/manual verification, record
the exact remaining operation and do not bypass it.

Check official PyPI for 0.2.2 before tagging. If it already exists, compare its
actual files/hashes and report the collision; do not change version silently,
replace files or use `skip-existing` to turn conflict into success.

## Tag admission, upload and public verification

Once configuration is confirmed and manual CI passed for the unchanged commit:

```sh
git switch main
git status --short
git rev-parse HEAD
git tag -a v0.2.2 -m "evidence-gap-router 0.2.2"
git push origin v0.2.2
gh run list --repo kadubon/evidence-gap-router --workflow workflow.yml --event push --limit 5
gh run view RELEASE_RUN_ID --repo kadubon/evidence-gap-router
```

Use authenticated user push, and confirm the tag run actually started; workflows
using `GITHUB_TOKEN` can suppress subsequent events. The guard requires exact
repository, tag-push event, `vVERSION`, source/distribution versions, tag target
in `main` history, and a completed successful exact-commit manual run whose six
required native jobs also succeeded. Manual/tag concurrency groups are separate.

Publish directly needs all native jobs in the tag run. Only publish has
`id-token: write`, uses environment `pypi`, and downloads the fixed distribution
artifact before the pinned official upload action. It performs no checkout,
build, test or project-script execution. Default permissions are `contents: read`;
only the final verified GitHub Release job has `contents: write`.

After upload, `scripts/verify_pypi.py` polls official PyPI JSON within a finite
bound, downloads the actual wheel and sdist, and compares each SHA-256 against
the original workflow artifact. It then polls the official Simple index at most
20 times, 15 seconds apart, requiring the same non-yanked filenames and hashes.
This addresses actual 0.2.0 index visibility lag without retrying its successful
upload. A new outside-repository environment then runs:

```sh
python -m pip --isolated install --no-cache-dir --index-url https://pypi.org/simple evidence-gap-router==0.2.2
```

Installed isolated smoke verifies version, SDK, CLI, exact-decimal local files,
issued-history invalidation/continuation, data/cause examples and migration;
the same public environment runs portable benchmark smoke. The final job requires
six matching passed native reports and benchmark outcome hashes, generates
v0.2.2-specific release notes and attaches the original wheel/sdist, `SHA256SUMS`
and native JSON reports, the new freeze/protocol, method and controller summaries,
artifact provenance, English/Japanese reports and the separate v0.2.1 erratum.
Upload the separately checksummed large raw benchmark archive without replacing
any existing asset. Tagged docs do not anticipate these future outcomes.
Hash equality establishes equality of observed bytes, not a completely
reproducible source build or general product performance.

## Partial publication and recovery

Do not rerun an upload blindly. If any upload succeeded, report the package as
published (or partially published), download the original run's artifact to a
new directory, and compare public filenames/bytes before choosing the next action:

```sh
gh run download RELEASE_RUN_ID --repo kadubon/evidence-gap-router --name distributions-COMMIT_SHA --dir EXTERNAL_ARTIFACT_DIR
python scripts/verify_pypi.py EXTERNAL_ARTIFACT_DIR 0.2.2
```

If public verification fails after upload, report **published; post-publication
verification failed**. Never delete/re-upload to hide it. Changes to published
bytes require another authorized version. If only the final verification/release
job failed, inspect logs and existing assets first; after resolving the actual
cause, rerun only failed jobs rather than the successful upload. A pre-existing
GitHub Release or asset is not overwritten. Required approval is not bypassed.

## Primary documentation and pinned tools

Checked 2026-10-05:

- [uv package build and publish](https://docs.astral.sh/uv/guides/package/)
- [Add a PyPI publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
- [Use a PyPI publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)
- [GitHub workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
- [Native hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

The existing official release pins were checked through GitHub release/ref APIs,
including dereferencing the PyPI action's annotated tag. They remain unchanged;
uv is pinned to the installed/observed 0.12.19.

| Action | Official release | Resolved commit |
| --- | --- | --- |
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| astral-sh/setup-uv | v10.2.0 | `c18668ad3cf93ea998bef934396af7bb5c839dc7` |
| actions/upload-artifact | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` |
| actions/download-artifact | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` |
| pypa/gh-action-pypi-publish | v1.14.2 | `dc37677b2e1c63e2034f94d8a5b11f265b73ba33` |
