# A01–A12 audit and regression mapping

The baseline is published v0.1.0 at
`76b9f40f42f3fc13fb535032bb06fdd762d5bffa`, manual run `37243906830`, release
run `37244095696`. Its wheel SHA-256 is
`eb6284ab41f8289def7d6a91ce88bfa23a4250c96c9d12977b536d70216f8083`;
sdist SHA-256 is `20559116f406a90bfd185a23661c2d5666dbb73bc1f6766c8019681352011eed`.

The supplied audit described Linux x86_64 / Python 3.13.5 / Pydantic 2.13.4 /
pytest 9.0.2 with existing dependencies, not the release's full locked environment.
We independently reran all twelve probes against the official installed v0.1.0
wheel on Windows 11 x64 / Python 3.12.14 / Pydantic 2.13.5 before modifying core.
All twelve observations reproduced; the existing 72 tests also passed. The
[raw probe output](audit-v1-probes.json) and [baseline probe script](../scripts/audit_v1.py)
preserve the environment and observations. Run that script only with v0.1.0;
it is not a schema-2 regression suite.

All twelve mechanisms and their regressions below were implemented in
[192da3bb942c71dde2f02d22e15a9e28f899b2c0](https://github.com/kadubon/evidence-gap-router/commit/192da3bb942c71dde2f02d22e15a9e28f899b2c0).
The final documentation commit, exact tagged SHA and executed run IDs are recorded
in the GitHub Release after successful publication. These are mixed implementation
bugs, contract deficiencies and former simplifications, not twelve security
vulnerabilities.

| ID | Reproduced v0.1 observation | v0.2 mechanism (fix commit `192da3b`) | Regression test | Remaining boundary |
| --- | --- | --- | --- | --- |
| A01 | Changed, checked dictionary left old dataset PASS accepted | Finite pinned dependency bindings; changed/inactive references invalidate related checks | `test_v2_core.test_A01_used_dependency_change_invalidates_only_relevant_pass`; `test_dependency_recheck.test_changed_real_dictionary_gets_pass_but_rechecked_dataset_fails` | Host/checker honestly declares and uses dependencies |
| A02 | Acquisition reused old PASS to erase FAIL at zero verification cost | Issued role/checker/purpose permissions and specific check-resolution basis | `test_v2_core.test_A02_acquisition_cannot_reuse_old_pass_to_erase_failure`; `test_A02_dedicated_authorized_resolution_preserves_failure_and_reuses_basis` | Host registration is trusted; raw snapshots are not authenticated |
| A03 | Generic content PASS erased a contradiction | Contradiction-specific purpose, fingerprint and related material | `test_v2_core.test_A03_generic_pass_cannot_close_specific_contradiction`; `test_contradiction_basis_requires_all_declared_related_material` | Resolution proves only the registered check's declared condition |
| A04 | ID order spent the remaining check on an accepted target | Accepted target/checker/purpose excluded; gap-specific eligibility | `test_v2_core.test_A04_already_passed_target_excluded_under_one_remaining_check_budget` | Finite declared candidates, no invented checker |
| A05 | Same-origin diversify preceded a declared new origin | Compare repeated, unknown and gap-filling declared provenance | `test_v2_core.test_A05_declared_new_source_group_beats_known_origin_regardless_ids` | Declaration does not prove statistical independence |
| A06 | Partial required-verifier PASS removed pending capacity | Missing required checker work remains target-level backlog | `test_v2_core.test_A06_partial_required_verifier_pass_stays_in_backlog` | Capacity is work-item count, not time or compute estimation |
| A07 | Cross-obligation evidence was rejected as missing | Explicit ID/scope/contract bindings and exists/active/verified prerequisites | `test_v2_core.test_A07_cross_obligation_verified_dependency_progresses`; `test_cross_obligation_dependency_rejects_mismatch` | Historical `exists` inspection cannot make inactive material acceptable |
| A08 | Duplicate CSV amount column silently overwrote bad value | Strict header/row validation before acceptance | `test_data_quality.test_A08_duplicate_csv_headers_are_rejected_before_acceptance` | Fixed documented order-data schema, not arbitrary CSV inference |
| A09 | Duplicate JSON minimum silently used last value | Shared strict duplicate-key/nonfinite/type parsing on file path | `test_data_quality.test_A09_duplicate_dictionary_keys_are_rejected` | Dictionary semantics are explicitly coded |
| A10 | New IDs allowed indefinitely fruitless callbacks | Finite default/explicit max_steps, meaningful progress, retained factory errors | `test_runner.test_A10_default_and_explicit_finite_limits_preserve_all_material_and_cost`; `test_A10_fresh_ids_without_new_material_are_not_progress`; `test_A10_factory_exception_retains_previous_receipt_and_evidence` | Cannot force-stop arbitrary Python callbacks or ensure crash exactly-once |
| A11 | Existing host-attempt-2 collided with generated ID | Allocation checks complete retained history; explicit snapshot continuation | `test_runner.test_A11_arbitrary_existing_attempt_id_is_not_reused`; `test_public_step_snapshot_continue_and_pinned_verification_view` | Single process/writer; uncertain in-flight attempts are not replayed |
| A12 | Acceptance change reused old-condition PASS | Mechanical contract revision/fingerprint; policy reevaluation | `test_v2_core.test_A12_contract_change_invalidates_check_but_description_priority_do_not` | Text hashes do not infer semantic equivalence |

Additional tests cover stale delayed receipts, same-ID/different-digest rejection,
dependency cycles, exact backpressure exemptions, positive authorized resolution,
legacy migration and size bounds, limited acquisition views, callback failures,
Unicode paths/BOM/line endings, installed CLI exit codes and artifact/job admission.
Final review also identified execution-allowlist intersection and negative alias
handling regressions. Execution availability is separate from historical checker
trust: an empty callback/policy intersection cannot authorize execution, and an
absent callback cannot revoke a valid past check. Deduplication affects positive
evidence/provenance counts while retaining applicable alias FAIL/UNKNOWN and their
exact-target resolution gaps. These are covered by additional focused regressions;
this source statement does not anticipate their executed results or test count.
The [validation record](validation.md) identifies which environments actually ran.
The [comparison](comparison.md) separately reports routing outcomes and ties;
neither regression success nor byte equality establishes scientific intelligence growth.
