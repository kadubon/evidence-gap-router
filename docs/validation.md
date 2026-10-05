# Validation evidence and native profiles

This source document records facts available before the v0.2.0 release workflow.
A configured runner is not an executed test. The exact tagged commit, successful
manual/release run IDs, actual native versions and public verification are written
to the GitHub Release only after those operations succeed. Native JSON reports
are attached to that Release and remain available as workflow artifacts.

## Executed baseline and local checks

The official v0.1.0 installed wheel was independently tested on Windows 11 x64,
Python 3.12.14, Pydantic 2.13.5: all 72 existing tests passed and A01–A12 reproduced
before core changes. See [audit facts and raw results](audit.md).

During v0.2 development, the new CLI/file/runner paths passed 75 targeted tests,
their seven source files passed mypy and their affected paths passed Ruff.
The small comparison passed its three regression tests and produced
[all nine raw cases](comparison-results.json). Thirteen release-admission tests
passed, including rejection of missing/skipped/failed native jobs and another
commit's successful manual run. Actionlint 1.7.12 accepted the workflow structure
(shellcheck was unavailable). These are scoped development checks; they do not
claim final native release success. The completed development suite passed all
169 tests without skips on Windows x86_64 / Python 3.12.14, 3.13.15 and 3.14.7,
and WSL Linux x86_64 / Python 3.12.14. Ruff lint passed and mypy passed all fourteen
source modules. These source-side runs do not substitute for native installed
wheel gates; final artifact/profile checks are recorded by exact-commit CI.

The final local wheel was also installed through cache-free, ordinary pip into
new environments outside the repository. Both profiles below passed all 156
installed core/runner/CLI/file/comparison regressions and the complete SDK, CLI,
fixture, Unicode-path, snapshot and migration smoke. The thirteen source-side
release-guard tests are part of the 169-test development suite, not these installed
regressions. These two checks used the same privately built wheel; the release
workflow builds and records its own single distribution artifact.

| Executed local OS | Actual architecture | Python | Pydantic / native core | Installed result |
| --- | --- | --- | --- | --- |
| Windows 11 | x86_64 (`AMD64`) | 3.12.14 | 2.13.5 / 2.46.5 | 156 passed; smoke passed |
| WSL2 Linux | x86_64 | 3.12.14 | 2.13.5 / 2.46.5 | 156 passed; smoke passed |

## Required same-wheel CI profiles

| OS / runner | Required actual architecture | Python | Status in this source snapshot |
| --- | --- | --- | --- |
| Linux / ubuntu-latest | x86_64 | 3.12 | Required; release result not yet recorded here |
| Windows / windows-latest | x86_64 | 3.12 | Required; release result not yet recorded here |
| macOS / macos-15 | arm64 | 3.12 | Required; release result not yet recorded here |
| macOS / macos-15-intel | x86_64 | 3.12 | Required; release result not yet recorded here |
| Linux / ubuntu-latest | x86_64 | 3.13 | Required; release result not yet recorded here |
| Linux / ubuntu-latest | x86_64 | 3.14 | Required; release result not yet recorded here |

The two macOS labels and architectures were checked in
[GitHub's hosted-runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Each profile rejects an unexpected platform/machine; macOS also rejects Rosetta
translation. Python 3.15 and other architectures are not implied tested.

Linux 3.12 performs locked lint, formatting, mypy and the complete suite, builds
one wheel and one sdist, and checks archive contents/metadata. It rebuilds and
smokes the sdist separately; that wheel is not the release wheel. Every native
profile installs the original release wheel in a new temporary venv with locked
runtime constraints and the locked pytest version. Regression test files are
copied outside the repository, then run with isolated Python; source-side release
guards are tested separately. Package imports must resolve inside that venv and
outside the source checkout. The installed smoke checks SDK/callbacks/step,
snapshot and migration, CLI, actual local files including Unicode paths, and both
independent example families. No editable install or source import substitutes
for installed-package success.

Each JSON profile records OS release, exact Python, `platform.machine()`, normalized
architecture, interpreter/package import paths, Pydantic/core versions, native
core import and wheel tags, project wheel tags, original wheel filename/SHA-256,
selected installed test files, test exit code and smoke result. A profile is marked
passed only after both installed regressions and smoke succeed. The release-note
generator requires all six exact profiles and the same original wheel hash.

The manual admission guard requires completed successful jobs for every profile;
missing, skipped, failed and cancelled jobs are rejected. Publish also directly
depends on the full native set in the tag run. See [the release procedure](releasing.md)
for exact-commit checks, OIDC isolation and post-publication byte/install verification.
