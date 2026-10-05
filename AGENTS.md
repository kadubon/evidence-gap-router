# Repository instructions

- Python >=3.12, `src/` layout, uv-managed Python and project-local `.venv`.
- Keep YAGNI/KISS: small typed functions, explicit state, one Pydantic runtime
  dependency. Do not add unused abstractions, model SDKs or automatic discovery.
- Use `uv sync --locked --group dev`; run `uv run --locked ruff check .`,
  `uv run --locked ruff format --check .`, `uv run --locked mypy src`,
  `uv run --locked pytest`, `uv build --no-sources`,
  `uv run --locked twine check dist/*` and
  `uv run --locked python scripts/package_audit.py dist` before a release.
  Remove only uv's generated `dist/.gitignore` before artifact audit/upload;
  other unexpected files remain errors.
- For routine edits check the affected behavior first. Batch full CI after local
  completion: `.github/workflows/workflow.yml` is the only workflow, dispatch and
  `v*` tag push only; no branch, PR, schedule or release trigger.
- Route by declared unmet evidence/check conditions, never headcount, role names,
  voting, persuasive text or assumed statistical independence. Missing provenance,
  unperformed checks, FAIL, UNKNOWN, stale targets and contradictions stay visible.
- Trust comes from registered host functions and policy, never evidence text or
  checker IDs alone. Bind checks to issued target ID/digest, obligation/scope,
  contract fingerprint, exact finite dependencies, checker revision and purpose.
  Acquisition cannot resolve negative checks or contradictions; resolution needs
  matching host authority and basis. Retain all original records.
- Planning is read-only. Track separate integer resource dimensions and actual
  costs. Unknown constrained demand or actual use is not zero. No automatic
  retry, refund, dynamic handler imports or external reference fetches.
- Identical result replay is idempotent; conflicting IDs are errors. Do not count
  duplicate evidence/provenance or cost twice. Never reissue uncertain attempts.
- Keep plan/start/observe explicit and the public step/run separate from demos.
  Callback views disclose only pinned inputs and are not a Python sandbox.
  run has a finite step limit; factory/receipt/callback errors retain state and
  invocation costs. Preserve strict schema-2 IO and explicit schema-1 migration:
  old PASS without a basis is unassessed, never retroactively authenticated.
- Reject duplicate CSV headers and JSON keys on the actual local-file path.
  Digest complete original bytes; reject over-limit input rather than accepting
  a prefix. File paths are data, never shell-command fragments.
- Publication requires local gates, a successful manual CI run for the exact
  unchanged commit, and installed regressions/smoke of the same wheel on Linux,
  Windows x64, macOS native arm64 and macOS native x86_64, plus Linux 3.13/3.14.
  Record actual architectures/imports/dependency wheel tags/hashes. Required jobs
  cannot be missing or skipped. Match tag/version/main history, confirm the existing
  PyPI publisher and environment `pypi`, and use OIDC only. The publish job runs
  no checkout, build, test or project script. Build the release distributions once.
- Preserve existing data, tags, protection rules and public files; no force push,
  tag movement or `skip-existing` success masking. Record source/Release/PyPI/public
  verification separately. No unexecuted test or publication is reported as passed.
- Follow [release procedure](docs/releasing.md); global Codex settings are outside
  this repository's scope.
