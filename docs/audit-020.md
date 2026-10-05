# Audit of the published 0.2.0 release

This audit separates acceptance bugs, missing continuation operations, practical
integration failures and controller performance. EGR020 identifiers are finding
labels; they are not nine assigned security CVEs. The router still relies on
host-owned snapshots, authentic checker dispatch and declared acceptance contracts.

## Baseline and evidence

The audited release is `v0.2.0`, commit
`e8d77f210d7579d6a367b7564b485b2586ffd074`. Its published wheel SHA-256 is
`039594d7fc5e39ab7b600c71f54682bb2d46147ba4e69a05a55f255a1806f3bf`.
The original pre-edit locked 170-test baseline passed. Reproductions then used a separate ordinary
wheel installation on Windows x64 with Python 3.12.14, Pydantic 2.13.5 and
pydantic-core 2.46.5. It imported the unchanged published baseline, independently
of later edits to the working source.
The release agent also extracted the exact original commit into an external
directory and reran all 170 original tests against that hash-verified installed
wheel, using isolated Python and pytest 9.1.1. All passed; the SDK import was from
the external environment rather than the archived source tree.

[Core observations](audit-020-core.json) were produced by
[probe_core_020.py](../scripts/probe_core_020.py);
[I/O and runner observations](audit-020-io.json) were independently reproduced by
the release agent with [probe_io_020.py](../scripts/probe_io_020.py).
`issue_reproduced: true` records observed old behavior; it is not a post-fix oracle.
Core history probes issue attempts and observe actual callback receipts. The
dependency-count probe also constructs its history through those public operations.

## Findings and corresponding regressions

| Finding | Observed 0.2.0 behavior | 0.2.1 change and named regression |
| --- | --- | --- |
| EGR020-01 — host invalidation operation | After two actual receipts, changing a returned evidence record's expiry flag fails the receipt/history equality check. There was no supported host operation to invalidate that record while retaining its original receipt. | Append-only exact-ID `Invalidation` and `invalidate`; original material, receipts and cost remain unchanged. [test_invalidation_retains_real_receipts_costs_and_exact_id](../tests/test_v021_core.py), `test_invalidation_unknown_or_wrong_scope_rejected` and `test_used_verified_dependency_invalidates_only_dependent_basis_and_no_global_cache`. |
| EGR020-02 — reopened resolution history | A contradiction resolved under the first contract cannot receive a second resolution event after the contract changes and new checks have actually run; the single-supersession rule rejects it after five receipts. | Distinct dedicated current grounds can resolve the same historical target again when prior grounds are stale. Active competing grounds and supersession cycles remain rejected. [test_re_resolution_after_contract_change_is_append_only_and_current_only](../tests/test_v021_core.py), `test_re_resolution_after_used_dependency_or_resolution_check_invalidation` and `test_check_resolution_can_be_repeated_after_resolution_check_invalidation`. |
| EGR020-03 — wrong subject acceptance | A resolution on a different evidence ID with the same digest is accepted, suppresses the original negative and yields `satisfied`. The saved reproduction contains four issued attempts/results. | Basis creation, planning, issuance, observation and host resolution bind the original check's exact subject ID. [test_resolution_subject_id_guard_at_basis_plan_start_observe_and_resolve](../tests/test_v021_core.py) and `test_old_inappropriate_alias_snapshot_retained_but_never_applicable` read the [unchanged old snapshot](../tests/fixtures/v020-wrong-alias-resolution.json) while refusing its current acceptance. |
| EGR020-04 — known self-verification scheduled | The planner selects a verifier whose declared ID equals the target's producer even when host policy prohibits self-verification; its receipt cannot establish an applicable PASS later. | Exclude it before callback issuance and charge no new callback cost. [test_self_verification_rejected_before_callback_or_budget_charge](../tests/test_v021_core.py) also retains past charged costs when policy later excludes a recorded self-check. |
| EGR020-05 — necessary helper blocked | After a helper obligation is satisfied, an unresolved required check's exact additional dependency cannot be acquired: `obligation_satisfied` excludes it. | Narrow finite dependency paths admit needed helper acquisition/verification across satisfied or optional obligations, with scope, contract, digest, authority, capacity and resource checks. [test_satisfied_optional_helper_multistage_exact_dependency_path_and_capacity](../tests/test_v021_core.py), `test_dynamic_unknown_digest_dependency_acquisition_can_bootstrap_factory` and `test_dependency_exemption_rejects_impossible_or_unauthorized_paths`. |
| EGR020-06 — decimal input changed before checking | Raw dictionary minimum `9007199254740993.0` becomes retained value `9007199254740992.0`. A CSV amount of `9007199254740992` is consequently reported as `satisfied`. | Preserve bounded decimal JSON values before float conversion and retain validated dictionary numerical text. [test_EGR020_06_exact_file_numbers_before_float_conversion](../tests/test_data_quality.py), `test_decimal_rules_roundtrip_all_supported_json_entrypoints` and numeric-limit regressions cover whole-number and fractional boundaries. An already rounded caller-supplied float is not repaired. |
| EGR020-07 — emitted snapshot cannot reload | A supported 10,000-row CSV produces a 1,297,960-byte successful snapshot, then `load_json` rejects it at 1,048,576 bytes. This reproduction's CSV is 128,915 bytes; the supplied audit used a different 108,915-byte fixture. | Separate 32 MiB State snapshots from 1 MiB plan/file input and validate the writer against reader bounds. [test_EGR020_07_max_rows_unicode_bom_crlf_snapshot_save_reload_continue](../tests/test_json_snapshots.py) covers save, load, continuation, raw digests and unchanged files; `test_save_rejection_preserves_existing_file_without_temp_success_artifact` covers rejection. |
| EGR020-08 — exact binding mistaken for no progress | A needed new evidence ID carries duplicate content. The runner stops at `no_progress` after its read even though the next declared action is `verify-target`; history grows from two to three attempts. | Count a fulfilled needed exact target/dependency binding as progress, without increasing deduplicated support or evaluating a factory twice for a callback. [test_EGR020_08_duplicate_information_fulfills_needed_exact_binding_and_continues](../tests/test_runner.py), `test_binding_progress_retains_original_pool_without_extra_factory_evaluation`, `test_duplicate_needed_verified_binding_advances_through_dynamic_checker_factory` and `test_arbitrary_alias_ids_without_a_needed_binding_do_not_count_as_progress`. |
| EGR020-09 — repeated dependency evaluation | Actual histories with 4/8/10 targets and two required checkers cause 52/1,004/4,072 uncached trusted-check calls during one plan; all return satisfied. Recorded elapsed times are diagnostic observations from that environment. | Per-evaluation indexes and a three-valued worklist reuse grounded applicability. [test_linear_memoized_chain_matches_uncached_reference](../tests/test_v021_core.py), `test_diamond_reference_and_worklist_update_bound`, `test_stale_cyclic_alternative_cannot_poison_current_acyclic_support` and `test_grounded_live_alternative_any_checker_and_unknown_negative_cycle` cover bounded updates, reference agreement and cycle semantics. Method-specific call counts are not a universal speedup measurement. |

The self-check finding concerns an avoidable call, not proof that producer and
checker labels authenticate different organizations. The subject-ID and numeric
findings demonstrate false satisfaction under the recorded contracts. None of
these results establishes semantic truth outside those explicit contracts.

## Additional implementation review

A pre-release review found that a missing dependency's future verifier could use
the correct target ID but the wrong obligation/scope, then give its unrelated
prerequisite acquisition a backpressure exception. The later verifier would fail
the binding check, so this was an overbroad helper exception rather than observed
false satisfaction. The fix checks verifier owner/scope plus declared and observed
digest compatibility before extending the path. Regressions
`test_wrong_future_dependency_verifier_cannot_exempt_unrelated_acquisition` and
`test_observed_dependency_digest_mismatch_does_not_bootstrap_wrong_helpers` cover
both missing and acquired material. Legitimate unknown-digest acquisition still
bootstraps a subsequent concrete verifier factory.

The evaluation review also tested a live dependency loop with an independent
grounded PASS. Blanket cycle-component exclusion would incorrectly reject its
finite proof. The implemented strong-Kleene worklist accepts grounded alternatives,
leaves unsupported circular proofs unresolved, and blocks unresolved potential
negative applicability. It does not cache provisional recursion failures or reuse
an assessment after a state/policy change. See [design boundaries](design.md).

The file-boundary review found that reformatting a valid near-1 MiB dictionary
and inserting default fields could push the retained material beyond the same
reader's limit. Validated original numeric text is now retained; the raw byte
digest remains unchanged. `test_maximum_dictionary_file_does_not_grow_past_reader_limit_from_optional_defaults`
exercises the actual file path. CSV fields have an explicit 131,072-character
bound without changing the process-global stdlib reader setting. During decimal
implementation review, generic Pydantic datetime/UUID serialization was also
preserved rather than replaced by a custom encoder; the actual generic save/load
regression is `test_generic_sdk_serializer_preserves_existing_pydantic_datetime_uuid_support`.
These are input-boundary and compatibility checks, not additional CVE claims.

## Distribution and publication verification

An independent inspection found 25 package files in the old release artifacts.
The additional archive checks strengthen verification: actual wheel `RECORD`
enumeration, digest and size checks; identical package-file bytes in wheel/sdist;
comparison with a wheel rebuilt from the sdist; and a frozen measured-candidate
package fingerprint. These are verification improvements, not claims that the
old archive was an exploitable runtime defect. The frozen fingerprint permits
documentation/metadata changes while rejecting changed package code/data.
[Package-audit regressions](../tests/test_package_audit.py) exercise invalid,
missing and duplicate RECORD information and changed package bytes.

The old [tag workflow run 37256324812](https://github.com/kadubon/evidence-gap-router/actions/runs/37256324812)
published both 0.2.0 files on attempt 1. Version-JSON and downloaded-file hash
verification passed, but pip at 02:42:22 saw only 0.1.0 in the official Simple
index and reported no matching distribution. After an actual cacheless public
installation succeeded, attempt 2 reran only the failed verify-and-release job;
the original upload and failure history were preserved.

The new verifier waits for the official installation index as a separate bounded
step: up to 20 attempts at 15-second intervals, checking exact expected filenames,
hashes and yanked status before installation. Altered/yanked files fail rather
than being hidden by retry. Four
[publication-verification regression cases](../tests/test_publication_verification.py)
cover delayed visibility, mismatched bytes, yanked files and the finite deadline.
This does not make upload, index propagation and public installation one atomic
operation.

## Evidence limits and remaining release work

The named targeted regressions were exercised during implementation. They cover
the stated contracts and adversarial cases, not every possible Python host or
untrusted external checker. Full final source/native matrices, frozen holdout
comparison, and 0.2.1 public publication/install verification are separate release
outcomes. This audit does not declare them complete. Their actual results and
remaining operations belong in [validation](validation.md),
[comparison](comparison.md) and [release procedure](releasing.md).
