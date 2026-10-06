# v0.3.0 completion contract design

Written before implementation. This is an engineering release; no new inference,
efficacy evaluation, benchmark, calibration or parameter search is authorized.
The v0.2.4 negative observations motivate a testable hypothesis: local PASS and
finite input receipt do not by themselves establish completion of the host goal.

Schema 3 separates observations, current check applicability, and finite goal
completion. A host appends CompletionContract revisions, binding an exact target,
obligation fingerprint, declared catalogue revision, AND requirements with small
explicit OR alternatives, and admitted check kinds. A reasoned not_applicable
scope supports fixed arithmetic. Missing contracts never mean empty completion.

CheckerPermission gains explicit completion kinds and scopes. Defaults remain
advisory. Issuance captures the profile and completion fingerprint; current
authority must still match. Correlation groups are declarations, not empirical
independence. A single qualified fixed checker is sufficient when declared.

One pure CompletionAssessment drives all planning and execution gates. Material
presence, disclosed issued inputs, completed receipts and current target/check
basis remain distinct. Costs, pending attempts, negative observations and
invalidation history are retained. Required acquisition helpers inherit the
required goal priority through exact IDs and dependencies.

Schema-2 import is explicit and strict, retaining original JSON and unchanged
old bases. Schema-1 migration remains explicit. Neither grants completion
authority, invents a contract, nor signs old PASS under new meaning. Existing
SDK entry points remain; callers must declare schema-3 contracts and permissions.
Historical experiments belong to their original tags and wheels. Current live
experiment entry points reject incompatible SDKs before network operations.

R01–R30 cover missing/use/basis conditions, roles and groups, current revisions,
negative resolution, routing, bounded progress, migration, JSON safety, graph
structure, pooled execution, generation exclusion and release integrity. Native
tests and release manifests establish shipping identity, not efficacy. v0.3.0
empirical utility remains unmeasured.

## Observations, hypotheses and engineering checks

The original 0.2.4 records remain unchanged: Qwen A/B/C supported answerable
completion 0/8/12 of 12; Gemma 3/8/10. Qwen A false acceptance was 15/16.
Partial integration, scope declaration and semantic false PASS can interact;
these records do not identify every causal contribution. In 64 stopping-policy
pairs the recovery trigger occurred zero times, so recovery efficacy remains
unidentified. Model-free 0.2.2 and model-based 0.2.4 tasks also differ in
information, tasks and verification conditions. Neither establishes a universal
advantage for pooling or a single explanation for the reversal.

| Design input / hypothesis | Engineering response | Specification evidence | Utility status |
| --- | --- | --- | --- |
| Partial PASS can precede necessary material use | Exact finite target/material contract; completed issued input basis | R01–R05, R28 local integer files | Unmeasured |
| Syntax or literal checks do not establish all acceptance conditions | Host-admitted check kinds/scopes; default advisory | R09–R11 | Unmeasured |
| Handler aliases do not establish independent judgments | Exact checker identity and declared correlation groups | R12 | Unmeasured |
| Optional-owner work can be necessary for a required answer | Exact helper reachability inherits required-goal priority | R16, R26–R27 | Unmeasured |
| Generic PASS can coexist with negative observations | Dedicated issued current resolution; original negatives retained | R14, R22 | Unmeasured |
| Repeated aliases can look like progress | Saturated required-condition fingerprint and finite runner | R21 | Unmeasured |

Implementation review additionally found same-content/group aliases inflating
support quotas, producer ancestors being omitted after expiry, externally seeded
resolution erasing a closing negative, and explicit advisory action flags being
ignored under an admitted profile. Their finite counterexamples and normal
paths are in `tests/test_completion_030.py`. No result is an empirical
false-acceptance improvement claim; checker correctness remains host-owned.

## Regression requirement map

Unless otherwise named, tests are in `tests/test_completion_030.py` and use
normal validated records and public issued receipts.

| IDs | Tests / retained safety checks |
| --- | --- |
| R01–R04 | `test_partial_pass_kept_but_missing_N_is_routed`, `test_R03_raw_and_pending_are_not_current_use` |
| R05–R07, R19 | `test_R05_full_current_receipt_completes_with_real_cost_and_history`, `test_R06_fixed_one_checker_and_R19_external_unknown`, `test_R07_declared_alternative_avoids_other_reads` |
| R08–R10 | Exact identity parameterization, distinct check kinds, rejected extra authority fields |
| R11–R13 | Issued/current admission and revocation; alias/unknown groups; unavailable-checker residual |
| R14 | Negative preserved under generic PASS; dedicated resolution reaches completion; retained `test_v022_resolution.py` contradiction/input regressions |
| R15–R18 | Used-input invalidation; irrelevant addition reuse; necessary optional priority; host revision history; empty/unjustified scope |
| R20 | Unknown actual cost and pending; retained `test_runner.py`, `test_v2_core.py` reservation/callback uncertainty |
| R21 | Alias no-progress, duplicate/failing factories; R26–R28 required exact-binding progress |
| R22–R23 | Selector eligibility, external seed/resolution rejection, CLI/assessment equality, reload, valid late receipt and idempotent cost |
| R24 | Rich schema-2 issued PASS/FAIL/UNKNOWN, original JSON, costs, invalidation and pending; retained schema-1 migration tests |
| R25 | Duplicate/nonfinite/unknown-field import; retained bounded JSON, atomic writes, UTF-8/space paths and original-byte digests |
| R26–R27 | Four small public chain/diamond/cycle fixtures and edge-incidence counter bound; retained finite reference tests in `test_v021_core.py` and `test_v022_helpers.py` |
| R28 | Three actual file examples, plus wrong integer bytes returning FAIL |
| R29 | Audited offline import/CLI; test-process socket connect/connect_ex guard; `test_ollama_controller.py` rejects mismatched CLI before preflight/client |
| R30 | `test_release_manifest_030.py`, retained RECORD/sdist/native/tag guards, exact installed package/LICENSE byte checks |

Old implicit completion assertions now inspect observation adequacy explicitly;
new whole-goal success requires a declared completion contract. Receipt, cost,
identity, failure and graph-reference assertions remain. Historical measurement
entry points reject the changed SDK before timers/callbacks. Measurement-invoking
tests were replaced by compatibility-guard/static preservation assertions because
rerunning those experiments is prohibited; original tests, harnesses, protocols,
gold, raw and results remain accessible at their original tags. Fake-client
historical bridge tests retain exact paid calls, feedback and recovery checks;
historical `system_claimed_complete` can describe a model claim while the current
SDK's `router_satisfied` is false. They are not remeasurements or current efficacy.
