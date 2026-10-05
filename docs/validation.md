# Validation evidence and native profiles

## v0.2.1 facts available before publication

The official v0.2.0 wheel (SHA256
`039594d7fc5e39ab7b600c71f54682bb2d46147ba4e69a05a55f255a1806f3bf`)
was installed in an isolated external Windows x86_64 / Python 3.12.14 environment,
with Pydantic 2.13.5 / native core 2.46.5. The original 170 source tests passed
before edits. All nine supplied observations were independently reproduced;
[audit mapping and boundaries](audit-020.md) links the actual baseline records.
The exact original commit was also extracted outside the repository and all 170
original tests passed against that installed official wheel, using isolated
Python and pytest 9.1.1 (1.82 seconds on this host).

New regression expectations cover issued-record invalidation, repeated current
resolution, old wrong-alias acceptance, pre-callback self-check rejection, narrow
multi-stage helpers, exact JSON decimals, bounded snapshot continuation,
exact-ID progress and state/policy/cycle-safe dependency evaluation. Publication
and archive guards also check index visibility, RECORD bytes and measured-package
equality. Final commands/counts and the measured protocol/environment are recorded
below after execution; a development check is not a native release result.

The v0.2.1 release still requires all six same-wheel native profiles in the table
below. Each also runs the same portable benchmark smoke, whose canonical outcome
hash must agree. Full statistical measurements run in one explicit environment;
the native smoke is not a replacement for that experiment.

Executed on Windows x86_64 / uv-managed Python 3.12.14 before the implementation
commit: `uv sync --locked --group dev`, `ruff check .`, `ruff format --check .`
(61 files), `mypy src` (14 modules), and the full `pytest -q` suite: **260 passed,
no skips**, in 5.53 seconds. The private development wheel/sdist passed
`uv build --no-sources`, `twine check` and actual RECORD/package-byte audit
(25 identical package files). Its external cache-free ordinary install passed
isolated SDK/CLI/file/issued-history continuation smoke. It is a development
artifact, distinct from the exact Git-archive candidate and final CI build.
Actionlint 1.7.12 accepted the changed workflow; shellcheck was unavailable.

The immutable v0.2.0 release ultimately passed manual run `37255968948` and tag
run `37256324812` attempt 2 at commit
`e8d77f210d7579d6a367b7564b485b2586ffd074`. Attempt 1 had already published both
files, then failed a fresh install while the official Simple index still listed
only 0.1.0. After verifying the public bytes and a cache-free install, only the
failed verification/release job was rerun. v0.2.1 now waits within a finite bound
for the expected non-yanked index files/hashes before installing; no successful
upload is blindly repeated.

## Archived v0.2.0 development and release checks

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
170 tests without skips on Windows x86_64 / Python 3.12.14, 3.13.15 and 3.14.7,
and WSL Linux x86_64 / Python 3.12.14. Ruff lint passed and mypy passed all fourteen
source modules. These source-side runs do not substitute for native installed
wheel gates; final artifact/profile checks are recorded by exact-commit CI.

The final local wheel was also installed through cache-free, ordinary pip into
new environments outside the repository. Both profiles below passed all 157
installed core/runner/CLI/file/comparison regressions and the complete SDK, CLI,
fixture, Unicode-path, snapshot and migration smoke. The thirteen source-side
release-guard tests are part of the 170-test development suite, not these installed
regressions. These two checks used the same privately built wheel; the release
workflow builds and records its own single distribution artifact.

| Executed local OS | Actual architecture | Python | Pydantic / native core | Installed result |
| --- | --- | --- | --- | --- |
| Windows 11 | x86_64 (`AMD64`) | 3.12.14 | 2.13.5 / 2.46.5 | 157 passed; smoke passed |
| WSL2 Linux | x86_64 | 3.12.14 | 2.13.5 / 2.46.5 | 157 passed; smoke passed |

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

The first v0.2 manual run, `37255060613` at
`95776be77fefef96ec6b6020299bf1857735bf9c`, passed Linux and both native macOS
profiles but failed Windows's import-location check. Pip had correctly installed
the package; the check compared a resolved long path against `sys.prefix` containing
the runner's Windows 8.3 alias `RUNNER~1`. Both paths are now resolved before the
containment check. The required Windows gate was retained, and full manual
validation is repeated on the corrected commit; the failed run is not admission
evidence for publication.

The second manual run, `37255356564` at
`72a85ce8267ddaf9aaddec6b97c0ad56c96659c4`, passed Windows native imports and
all 156 installed regressions, then exposed a real CLI encoding failure in its
Japanese-path file smoke under the runner's cp1252 stdout. CLI JSON now escapes
non-ASCII characters losslessly, with a subprocess regression under cp1252;
the runner locale is not overridden to mask the defect. Linux and both macOS
profiles passed in that run. Neither failed manual run permits publication.
