# Changelog

## 0.2.0

- Verification bases bind target IDs/digests, acceptance contracts, finite explicit
  cross-obligation dependencies, checker revisions and distinct resolution purposes.
  Relevant dependency/contract changes invalidate checks without deleting history.
- Registered handler roles and checker permissions prevent acquisition from erasing
  FAIL/UNKNOWN or using ordinary content checks to resolve contradictions.
- Target-specific gaps exclude already accepted checks, compare declared provenance,
  retain partial-verifier backlog and permit only explicit missing-prerequisite work
  through verification backpressure.
- Public finite `step`/`run`, pinned immutable callback views, history-safe IDs,
  snapshots and failure/cost retention. No background execution or automatic retries.
- Installed `egr check-data` with bounded strict CSV/JSON parsing, duplicate detection,
  raw-byte digests, Unicode paths and actual dependency-bound verification.
  Separate multi-material cause investigation and plain Python callback examples.
- Schema 2 and explicit schema-1 migration preserve legacy material and history;
  missing legacy check bases remain unassessed. This is an API/schema compatibility change.
- A01–A12 regression coverage and a small fixed-order comparison with complete raw
  results, including ties. Native same-wheel Linux/Windows/macOS arm64/macOS Intel
  release gates and Linux Python 3.13/3.14 checks record actual dependency/import profiles.

## 0.1.0

- Typed evidence, obligations, target-bound checks, explicit supersession,
  attempts, results, residuals and versioned JSON snapshots.
- Deterministic finite-action routing with provenance deduplication, verification
  backpressure, separate resource limits and distinct unresolved stop reasons.
- Explicit host callback integration and offline `egr` CLI.
- Artificial CSV/JSON data-quality demos with real acquisition and verification,
  including accepted, invalid-data and budget-limited scenarios.
- Source packaging, installed-wheel/sdist smoke support and one guarded Linux/
  Windows release workflow using PyPI Trusted Publishing.

This entry describes the implemented release content. Publication and executed
validation evidence are tracked separately; it does not assert they have passed.
