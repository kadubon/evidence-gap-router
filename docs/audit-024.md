# v0.2.4 audit

Post-freeze tracing found a mechanical experiment defect: Pydantic added optional
`feedback`/`unit` defaults to saved evidence, so actual model JSON and issued
evidence disagreed. The correction preserves original parsed JSON after strict
validation; the independent oracle and SDK acceptance criteria are unchanged.
The initial worker/server stopped with held native handles, zero pending/unknown
responses, and 957 paid/empty-load reservations (133,726 generated / 742,263 total
tokens). Protocol v2 retains that exact ledger prefix and durable clock, all limits,
and a new owned epoch. Fresh instances change targets, authorities, symbols,
versions and deadlines while retaining the authored rule families.

The corrective source passed 695 tests in 26.92 s, lint and mypy. A further
historical-license export regression and all 50 portable v0.2.4 contracts passed
together (56 tests); the final full suite and native gates remain separate.

The complete corrective source subsequently passed **696 tests in 26.48 s**,
Ruff check/format (119 files) and mypy (14 SDK modules). Its same ordinary
candidate wheel passed **296 installed SDK regressions**, **222 portable
contracts in 12.22 s**, 44 benchmark-smoke trials and three complete document
examples (182 local links). These checks use fake HTTP/offline fixtures and are
separate from live inference and later exact-commit release CI.

Before the corrective main freeze, tracing also found that the fresh rule header
named an internal task ID while its question and facts named a different entity.
This was a task-scope defect, so the corrective warm/pilot worker was stopped at
a durable boundary (991 cumulative reservations, 991 known responses, no pending
or unknown call). Its exact inputs, source and checkpoints remain in development
history. The header now identifies the public rule without overriding its scope;
new development IDs prevent reusing those old calls. Prompts, caps, semantic
criteria and the three completed tuning cycles are unchanged. The scope repair
passed **697 complete source tests in 28.35 seconds**, lint/format and mypy.
The unchanged ordinary candidate wheel also passed 296 installed SDK regressions,
223 portable contracts in 13.81 s, 44 benchmark-smoke trials and three complete
document examples (183 local links) on native Windows x64 / Python 3.12.14.

The audit found experiment transport and output-contract limitations. It did
not establish a new defect in the SDK's acceptance, permission or helper rules.
Those rules continue to use schema 2 and the public `plan/start/observe/step/run`
interfaces. Long-call recovery is an explicit local experiment host policy.

## Executed baseline and candidate checks

The unchanged v0.2.3 source (`6dae35fc9fdd3cf7d751aa73d0c72a435b47578b`)
passed 630 tests in 23.41 seconds. A fresh official PyPI wheel was installed
outside the repository on Windows x64 / Python 3.12.14: 296 SDK regressions,
172 portable fake-HTTP/experiment contracts and SDK/CLI smoke passed. These
are model-free tests, not live model results.

Implementation candidate `110199863b971ca806115c27e07e961f5296a123`
passed 648 source tests in 26.24 seconds, Ruff check/format and mypy on 14
SDK modules. Its ordinary installed wheel passed 296 SDK regressions,
190 portable contracts and SDK/CLI smoke. The 44-trial portable benchmark's
actual canonical outcome matched its earlier regression signature.

The third development revision passed 666 source tests in 42.70 seconds,
Ruff check/format (117 files) and mypy (14 SDK modules). This includes a
reproduced paid-repair resume defect and task/resource/export contracts.
Under concurrent live inference, a Windows containment test's 0.3-second
fixture expired before its nested interpreter wrote a heartbeat. A 2-second
test fixture passed, still checking timeout, descendant termination and an
unrelated process's continued lifetime. Production worker limits did not change.
Its fresh ordinary wheel check also passed 296 SDK regressions, 203 portable
contracts, the 44-trial benchmark and all three complete example documents.

All 25 runtime files matched the candidate wheel, ordinary installation,
working source and committed Git bytes exactly. They use LF before live
measurement. Historical v0.2.3 wheels and raw archives retain their original
CRLF bytes. Line-ending normalization is a new candidate byte identity;
it does not make older artifact fingerprints interchangeable.

## Findings and changes

| Finding | Change | Verification |
| --- | --- | --- |
| A short socket wait could expire before a longer request deadline | Separate 30-second connection bound and nonstream response waits using the hard deadline | Delayed headers/body and independent hard-deadline HTTP tests |
| Model profile and limit validators rejected the new finite envelope | Permit explicit bounded context/output, per-model request/trial deadlines and campaign limits | Profile validation, per-stage reservation and exhausted-budget tests |
| A crash after receiving bytes but before journal settlement lost the usable receipt | Fsync a raw receipt spool before parsing; recover it without HTTP | Crash, tamper, torn journal, idempotent recovery and no-redispatch tests |
| Unknown cost could only halt all later trials | New-campaign-only verified termination marker, retained full reservation and new server epoch | Unknown actual usage remains null; stale clients and failed-primary retry stay blocked |
| Long review feedback conflated syntax failure with judgment | Closed compact review schema, bounded feedback, separate legacy calibration schema | Unknown fields, reason codes and feedback bounds rejected |
| Necessary-only rules and whole-document quotation obscured scoring | New explicit necessary-and-sufficient public rules and minimal exact witnesses | Distinct development/calibration/confirmation tasks; public/gold separation |
| Answer grounding depended on reviewer acceptance in the old metric | Separate answer grounding and verified supported completion | Correct grounded answer with failed review remains grounded, incomplete |
| Known formatting faults were immediately terminal | Common paid one-shot format repair, maximum two per trial | Original bad output retained; both calls charged; terminal resume sends no new request |
| A recovered paid format repair could be absent from the trial call list when its original call was already checkpointed | Independently reconcile both persisted request records | Reproduced three-call checkpoint resume; both repair and original remain charged, with no HTTP retry |
| Wall-clock rollback or process restart could omit campaign waiting time | Durable original epoch, same-boot monotonic anchor and ledger-prefix identity | Rollback, restart, boot-change and tampered-prefix tests; original first dispatch retained |
| Resource observations did not enforce sustained swap growth | Require known swap use; four consecutive increases totaling at least 256 MiB block a new dispatch | Windows CIM observation; unknown and threshold boundary tests |
| Arrival rules mixed a world fact with whether it had been confirmed; several parents differed only in names | Explicit world conditions and distinct AND/OR/XOR, report thresholds, current exceptions, deadlines and destinations | Separate public/gold types; distinct normalized parent signatures; 18/6 and 12/4 task counts; minimal source/version witnesses |
| Success-only cost summaries hid missing trials and zero-member subsets | Planned-key accounting, nullable unresolved outcomes, paired bounds and subset denominators | Missing-key, no-success-cost, independent grounding and bounded-continuation tests |
| The export path was pinned to the previous protocol and omitted the measured wheel | Version-bound freeze, candidate wheel hash and retained development implementations | Export rejects mismatched bytes and private paths without rewriting model output; no-overwrite tests |
| Catalogue ordering forced an explicitly identical same-origin reprint | Common A/B retrieval catalogue omits only declared copies with identical full content, topic, origin and version | Reproduced forced-copy candidate; both selectors retain different information/versions/origins and any specifically requested copy |
| A single spelling/source of a witness rejected equivalent minimal support | Evaluation-only alternatives allow the same signed fact without its redundant scoped target label and an explicitly equivalent copy | Actual bound fake receipts reproduce the rejection; altered copy origin/version/content remains rejected |

Old FAIL/UNKNOWN, pending invocation, withdrawal, contract changes, exact-ID
resolution, helper/proof AND/OR and grounded-cycle behavior remain covered by
the installed regression suite. No new PASS, authority or evidence is seeded
to make a model trial succeed.

## Limits

The final pre-confirmation source revision passed 683 tests in 28.18 seconds,
Ruff check/format and mypy. The added ten raw-extraction regressions reject
escaped paths, symlinks, case collisions, Windows special names/streams,
incorrect archive hashes, oversized expansion and existing destinations.
They are source-only checks, separate from the unchanged 296 installed SDK
regressions and 210 portable optional-experiment contracts.

Fake HTTP checks establish local transport and ledger contracts. They do not
establish live-model correctness or speed. Process-handle evidence is supplied
by the trusted local host, not cryptographic authentication. Resource samples
are observations, not a hard whole-server/GPU memory guarantee.

Live-model results, calibrations, failure chains and publication evidence are
reported separately after their actual execution. The old v0.2.3 unknown
Qwen request remains unknown in its original campaign.

Development cycles and their original prompts, answer banks, outputs and costs
remain in the new campaign's history. The earlier arrival-rule ambiguity is a
development limitation, not a retrospective correction to old model scores.
The final bank uses 24 answer cases drawn from 12 underlying task parents; those
cases are not 24 independent statistical parents. Main confirmation parents
are unused until the frozen schedule dispatches them.

The final common-catalogue change passed 668 source tests in 43.61 seconds,
Ruff check/format and mypy. It does not alter core feasibility or acceptance.
The pooled reference still receives all public records. Review requests can
explicitly restore a copy to A/B retrieval, retaining that real extra cost.

Witness alternatives are finite, authored scoring keys, not a general language
entailment checker. Exact literal quotations, scope, source versions, current
issued receipts, relevant inputs and independent-origin requirements still
apply. Public inputs, canonical calibration quotations and task answers remain
unchanged by these evaluation-only alternatives. No main result was observed
when the alternatives were defined; v0.2.3's default witness rules stay unchanged.
