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
- Trust comes from host verifier/handler policy, never evidence text. Bind checks
  and results to obligation, scope, digest and issued attempt. Explicit supersession
  retains the old record and reason. No silent obligation deletion or relaxation.
- Planning is read-only. Track separate integer resource dimensions and actual
  costs. Unknown constrained demand or actual use is not zero. No automatic
  retry, refund, dynamic handler imports or external reference fetches.
- Identical result replay is idempotent; conflicting IDs are errors. Do not count
  duplicate evidence/provenance or cost twice. Never reissue uncertain attempts.
- Publication requires local gates, a successful manual CI run for the exact
  unchanged commit, Linux/Windows smoke of the same artifact, matching tag/version
  in main history, confirmed PyPI publisher and environment `pypi`. Use OIDC only.
- Preserve existing data, tags, protection rules and public files; no force push,
  tag movement or `skip-existing` success masking. Record source/Release/PyPI/public
  verification separately. No unexecuted test or publication is reported as passed.
- Follow [release procedure](docs/releasing.md); global Codex settings are outside
  this repository's scope.
