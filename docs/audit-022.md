# v0.2.2 model-free audit before the v0.2.3 experiment

The current mechanical SDK was audited before making local-model calls. The
fresh source suite, the original tests against the ordinary public v0.2.2 wheel,
and the finite public-SDK diagnostic matrix passed. One documentation defect was
reproduced: both README continuation snippets imported a helper from a namespace
that does not export it. The audited cases did not establish another runtime
acceptance defect, and do not justify changing the default `run` progress rule.
This is a scoped correctness review, not a security certification or evidence of
live-model utility.

The user's request explicitly includes a v0.2.3 release; that request supersedes
the supplied experiment specification's assumption that no new version would be
published. Release admission, final installed checks and the model experiment
remain separate from the baseline observations below.

## Fresh baseline and provenance

The initial checkout was clean at
`eff875d4c391c476fbe5af43ab4cd7928b7e0ca3`, the published v0.2.2 release commit.
The source baseline ran **before** the version edit. A separate Git archive of
that original commit supplied the unchanged tests for the installed baseline;
the SDK imported from an ordinary external virtual environment's site-packages,
outside the repository. These are newly executed observations, rather than
reused v0.2.2 release results.

| Check executed on 2026-10-05 | Actual result |
| --- | --- |
| Original source: `uv run --locked pytest tests -q` | 428 passed; 0 skipped; 12.13 seconds |
| External original-commit tests: `python -I -m pytest tests -q -ra`, ordinary public wheel | 428 passed; 0 skipped; 13.04 seconds |
| Original `benchmarks/audit_022.py`, ordinary public wheel | 14/14 expected properties met; 0 case exceptions |
| Baseline SDK/dependencies | SDK 0.2.2; Python 3.12.14; Pydantic 2.13.5; pydantic-core 2.46.5; Windows AMD64 |

The complete 428-test installed-baseline run includes source-side archive and
experiment orchestration tests from the external original archive. It is not
described as 428 installed-only runtime regressions or a new six-platform native
release check. The test and diagnostic durations are observations on this host,
not controlled performance measurements.

The fresh downloaded official wheel was independently checked:

| Identity | SHA256 |
| --- | --- |
| `evidence_gap_router-0.2.2-py3-none-any.whl` | `6f417e5664513a5a3125051642dab46b85065f74ab5f669b999a24a79ae7bbc5` |
| Actual package-byte fingerprint, after validating wheel RECORD | `b74c3e906270813246c3871e71a32c40900bbf4bfdc5a7d21577880fddec2afe` |
| Sanitized new diagnostic, `audit-022-sdk.json` | `d5c7abd67d79f3adf0ace02b30eb7bb295cc3767034365a848a66e3a64d4d62e` |
| New baseline verification, `verification-core-baseline-023.json` | `0e0a389c5d80a02d3ab4f5e2ce8367a89fab4eba4fe1c19a7b38826008db154d` |

The public diagnostic replaces its local interpreter/package location with the
fact that the import is outside-repository site-packages. Internal location
verification was retained separately. No authentication header, personal user
path or API credential is required by this model-free record. The immutable
[official v0.2.2 Release](https://github.com/kadubon/evidence-gap-router/releases/tag/v0.2.2)
remains the baseline; the measured development wheel is not substituted for it.

## Confirmed documentation finding

**EGR022-D01: the copyable continuation example had an invalid import.** On the
official installed wheel, this exact first line raised `ImportError`:

```python
from evidence_gap_router import run_continuation_example
```

Both English and Japanese READMEs used it. The helper exists in `sdk_example.py`
and was already exercised by
`test_packaged_continuation_example_retains_real_receipts_after_check_withdrawal`;
`__init__.py` did not export it. The failure concerns the documented import route,
not issuance, receipt handling or the continuation implementation. The existing
module import is the minimal correction:

```python
from evidence_gap_router.sdk_example import run_continuation_example
```

The continuation function still creates actual acquisition/check receipts,
appends a host invalidation, writes and reloads the checkpoint and invokes a new
check while retaining prior work. No new public root export or weakened receipt
rule is needed. This finding is a documentation bug, not a security CVE.

## Public SDK diagnostics

The unchanged 14-case driver uses public SDK operations, actual issued receipts
and explicit imported-history cases. Its resolution oracle independently checks
exact related inputs, current bindings/contracts/permissions and the supplied
integer computation; it does not call the router's private acceptance predicate.
The old v0.2.1 inappropriate-resolution cases remain regression inputs here, not
newly discovered v0.2.2 defects.

| Actual diagnostic case | Observed domain stop | Expected property met |
| --- | --- | --- |
| Partial external resolution basis | `escalation_required` | yes |
| Same-digest related alias | `escalation_required` | yes |
| Valid all-related external basis | `satisfied` | yes |
| Retained old partial resolution event | `escalation_required` | yes |
| Related evidence invalidation | `escalation_required` | yes |
| Contract update and new resolution | `satisfied` | yes |
| Checker revision update and new resolution | `satisfied` | yes |
| Paid invalidation, save/load and re-resolution | `satisfied` | yes |
| Negative subject alias rejection, then exact-subject resolution | `satisfied` | yes |
| Known prohibited self-verification | `blocked` | yes |
| Satisfied-helper duplicate content fulfilling an exact binding | `satisfied` | yes |
| Actual files with an exact decimal boundary | `escalation_required` | yes |
| Supported snapshot larger than the 1 MiB plan-input limit | `satisfied` | yes |
| Small grounded proof DAG with required checker groups | `satisfied` | yes |

In particular, the negative-subject row's final satisfaction follows rejection of
the wrong alias and a new authorized exact-subject check. It does not mean the
alias was accepted. The decimal row is an inspected FAIL against the actual
threshold, not an input error or rounding-based acceptance. Positive cases
require the final domain property and retained history/costs, not merely a PASS
payload or an error-free worker return.

## Runtime review and regression coverage

Source inspection covered `models`, `router`, `runner`, `jsonio`, the private
schema-1 reader, CLI, local data/rules parsing, file-check host, both demo families,
SDK examples, comparison and package exports. The API/design/migration/security
contracts and existing runtime regressions were read alongside their code. The
following tests actually ran in both complete baseline suites; the names identify
the assertion scope rather than implying exhaustive state-space coverage.

| Area | Reviewed conditions and representative exact regression names |
| --- | --- |
| Issuance, observation and immutable history | `test_closed_loop_and_idempotent_cost_accounting`, `test_result_and_record_id_collisions_are_atomic`, `test_explicit_retry_only_and_pending_attempt_not_reissued`, `test_snapshot_attempt_history_requires_explicit_retry_and_single_writer`, `test_snapshot_fixed_verification_view_matches_issued_basis`. Receipt fields/payloads must match the issued attempt; replay adds no second charge. |
| Normal continuation, delayed work and append-only invalidation | `test_public_step_snapshot_continue_and_pinned_verification_view`, `test_invalidation_retains_real_receipts_costs_and_exact_id`, `test_callback_cannot_supply_invalidation_or_mutate_old_payload`, `test_real_acquisition_resolution_invalidation_save_load_and_re_resolution`, `test_delayed_complete_resolution_receipt_is_retained_but_stale_contract_cannot_accept`. Pending execution is retained rather than reissued. |
| Imported checks and resolution | `test_partial_related_basis_import_and_old_resolution_history_remain_unaccepted`, `test_equal_digest_alias_cannot_replace_an_exact_related_input`, `test_imported_related_binding_must_match_the_recorded_identity`, `test_complete_imported_basis_still_needs_current_contract_permission_and_fingerprint`, `test_valid_imported_all_related_resolution_remains_supported_and_reusable`, `test_content_purpose_cannot_reuse_a_full_basis_to_resolve_a_contradiction`, `test_duplicate_alias_negative_check_blocks_and_resolves_exact_alias`. Exact subject ID, all related IDs, digest, owner/scope, contract, revision and purpose remain distinct requirements. |
| Helper reachability and current checked dependencies | `test_chain_retains_all_grounded_alternatives_and_exact_start`, `test_structural_edge_visits_are_linear_for_one_shared_root`, `test_small_and_or_cycles_diamonds_and_permutations_match_independent_reference`, `test_pure_cycle_blocks_but_grounded_exit_retains_all_viable_routes`, `test_required_checker_groups_are_and_alternatives_and_partial_pass_is_reused`, `test_no_cross_call_cache_for_budget_authority_contract_candidate_or_invalidation`, `test_grounded_live_alternative_any_checker_and_unknown_negative_cycle`. Candidate reachability and recorded-proof applicability use separate finite evaluation-local worklists. |
| Authority and resources | `test_checker_revision_role_and_purpose_are_host_authority`, `test_self_verification_rejected_before_callback_or_budget_charge`, `test_mapping_intersection_cannot_turn_explicit_handler_allowlist_into_unbounded`, `test_execution_availability_does_not_revoke_current_checker_trust`, `test_unknown_actual_or_declared_overrun_freezes_work`, `test_unknown_side_effects_and_failure_cost_preserved`, `test_host_callback_uncertainty_is_charged_recorded_and_not_retried`. A checker/model name in output grants no registered authority; unknown bounded use is not zero. |
| Shared selectors and progress | `test_selector_keeps_future_helper_pool_and_matches_default_execution`, `test_invalid_selector_does_not_issue_or_charge`, `test_empty_receipt_semantic_stop_is_identical_for_all_selection_rules`, `test_all_rankings_keep_identical_paid_fault_pending_and_limit_semantics`, `test_arbitrary_alias_ids_without_a_needed_binding_do_not_count_as_progress`, `test_duplicate_needed_verified_binding_advances_through_dynamic_checker_factory`. Selection changes ordering within the common eligibility mechanism; the original finite pool remains available to issuance/progress. |
| Strict JSON, exact numbers, local files and CLI | `test_bounded_json_duplicate_keys_schema_strictness_and_round_trip`, `test_exact_json_precheck_keeps_core_integer_fields_strict`, `test_json_integer_decimal_and_depth_bounds_are_explicit`, `test_save_rejection_preserves_existing_file_without_temp_success_artifact`, `test_EGR020_07_max_rows_unicode_bom_crlf_snapshot_save_reload_continue`, `test_EGR020_06_exact_file_numbers_before_float_conversion`, `test_cli_plan_is_offline_read_only`, `test_json_cli_unicode_files_work_with_cp1252_stdout`. Unknown fields/versions, duplicates, coercion and malformed/oversized input are rejected. |
| Explicit old-schema import | `test_new_reader_rejects_schema1_and_migration_retains_unassessed_history`, `test_migration_keeps_old_resolution_events_without_trusting_them`, `test_migration_rejects_expanded_snapshot_over_limit_without_overwriting`. Migration retains the archive and history without fabricating missing old verification bases. |

The baseline suites already cover these contracts. Additional runtime patches or
tests were not manufactured to produce an audit-fix narrative. Final v0.2.3
source and installed release checks are reported separately after execution.

## Progress rule and remaining boundaries

Default `run` stops on `no_progress` when eligible work remains after a callback
that added neither material/check substance nor a declared needed exact binding.
It retains the attempt, receipt and cost. Fresh IDs, repeated known-origin
content and consumed work alone do not justify another automatic callback. The
helper exception permits a genuinely needed exact-ID input even when its bytes
repeat prior material; arbitrary aliases remain insufficient. Unknown actual
use/effects and pending work continue to block safe automatic continuation.

This rule can stop a fixed ordering before a later useful action. That is an
explicit productivity boundary rather than an inferred acceptance bug. A host
may continue with public `step` and the returned state within its original
resource/permission bounds. A declared two-callback nonprogress allowance in an
experiment is a separate bounded host policy; it must not reset history/budget,
silently retry uncertain effects or be reported as the SDK's default behavior.

The graph tests establish the stated finite fixtures and structural visit bounds.
They do not prove all possible contracts, arbitrary negative cyclic histories or
universal wall-time/memory bounds. Helper work is shared within an assessment;
multiple consuming roots and separate plan/start/progress evaluations still do
work, and no cache is reused across changed state, pool, budget or authority.

The host remains responsible for authentic policy/checker dispatch, correct
digests and material, measured costs, external effects, timeouts and single-writer
state. Typed snapshots and frozen callback views are not authenticated history or
a Python sandbox. The router does not infer semantic truth from content, prove
provenance independence, force process timeouts or provide exactly-once crash
recovery. Direct Pydantic construction is below the documented bounded snapshot
file API. Use `write_json` for validation-before-replacement; it is not durable
journaling or concurrent-writer coordination.

No model call, model download, Ollama configuration mutation or shared-server
operation was part of this audit. These results are a prerequisite for the
separately specified live-model experiment, not its result. That experiment must
retain model/worker errors, unknown use, both-success subset denominators and
common host-loop semantics; it cannot turn these finite model-free checks into
claims of intelligence growth, general savings or real-world truth.
