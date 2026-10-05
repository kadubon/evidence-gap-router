# v0.2.2 engineering measurements

The frozen common-runner regression observed EGR completion **145/145** solvable
parents, fixed-feasible **122/145**, verify-first **127/145** and random-feasible
**133/145**, with zero assessed false satisfaction in 240 parents per method.
This is additional ordering value under shared gap/necessity/helper eligibility,
on an already observed synthetic set. It is not a general EGR advantage over an
independent scheduler. Existing checked-proof performance is nearly unchanged;
the distinct candidate-helper fix removes repeated alternative-path exploration,
while some simpler inputs become slower.

The [original v0.2.1 report](benchmark-v0.2.1.md) and
[stop-metric erratum](benchmark-v0.2.1-erratum.md) remain separate immutable evidence.
The old 80/95 versus 70/95 label difference is not a safety improvement. Every
new main method has 75 known correct abstentions, five uncertain incomplete stops
and 15 execution faults among 95 unsolvable parents. Unknown use/effects are
retained. New measurement does not rewrite old observations.

## Identity, environment and execution control

| Recorded identity | Value |
| --- | --- |
| Protocol | `egr-022-engineering-v1` |
| Measured implementation commit | `08c81a2387db7047b9599d153f48893e510fe85d` |
| Official baseline runtime commit | `3e6a547dd38af9668115aaad9d9d30129c018c1b` |
| Freeze time | `2026-10-05T09:07:39Z` |
| Protocol SHA256 | `4a0ef6b5d7fdcd474f260aba124851ca96d0b55b705ee58dd7d1a84ad7ff7faf` |
| Harness SHA256 | `32512950572d2f78280f5fbda505d6c94a67e44c3c9d60337466f2bbde55aba5` |
| Measured 0.2.2 wheel SHA256 | `66b4cad4d4f80c81871c0caf6daa28c472d5fabef310a429bc59e2f85e6059e9` |
| Official 0.2.1 wheel SHA256 | `61129ec160c6c9d718f5173fa0281cdcc735cfdc9222138f45584a6b71202917` |
| Measured 0.2.2 package fingerprint | `b74c3e906270813246c3871e71a32c40900bbf4bfdc5a7d21577880fddec2afe` |
| Official 0.2.1 package fingerprint | `5df6a0b5e7c521079e29475950addf6e1b84d62b3f3c70033307a82643e8341a` |
| OS / machine | Windows 11 `10.0.26300`, AMD64 |
| CPU / power | AMD Ryzen 7 8840HS, 8 cores / 16 logical processors; Balanced |
| Python / Pydantic / core | 3.12.14 / 2.13.5 / 2.46.5 |
| Other matched runtime dependencies | annotated-types 0.8.0, typing-extensions 4.16.0, typing-inspection 0.4.4 |

Both SDKs were ordinary noneditable wheel installs outside the checkout. Installed
package bytes were compared with their declared wheels. Package fingerprint is
SHA256 of canonical sorted package-relative filename → SHA256(bytes) JSON, with
compact separators, excluding generated caches. It permits a later docs/metadata
build to have a different whole-wheel hash while requiring identical measured
runtime bytes. Harness/protocol identity is also required. The
[freeze](../benchmarks/results/freeze-v0.2.2.json) is repository-local freezing,
not external registration; runtime/checker/generator were fixed before confirmation.

One serial controller enumerated 1,680 keys and shuffled matched blocks with seed
220229. Development, writing, testing and other heavy experiments stopped during
formal measurement. Codex desktop remained active; CPU affinity/priority, thermals,
background services and frequency were not controlled. These are one-host
engineering observations with remaining desktop noise.

Per-worker limits were 10 wall seconds, eight cumulative Job CPU seconds and
256 MiB peak aggregate private committed bytes, including venv descendants.
The parent had a separate 512 MiB peak working-set cap. Overall limits were
7,200 wall and 3,600 CPU seconds, with preregistered phase caps. Workers were
assigned to an owned Windows Job before execution; observed crossing terminates
only that Job, with possible sampling overshoot. Private committed bytes,
working set and traced Python allocations are different metrics.

The run took **1,093.901 wall seconds**, **938.391 worker CPU seconds** and
**66.578 parent CPU seconds**. All worker CPU/memory observations were available.
Observed maximum Job private committed bytes were 61,079,552; maximum parent
working set was 70,348,800. These observed maxima are not universal memory bounds.

| Phase | Requested workers | Completed workers | CPU-limited workers |
| --- | --- | --- | --- |
| B, main methods and direct references | 1,020 | 1,020 | 0 |
| A, fixed functional audit | 2 | 2 | 0 |
| C, proof and helper measurements | 594 | 566 | 28 |
| New confirmation | 64 | 64 | 0 |
| All | 1,680 | 1,652 | 28 |

No worker keys were deleted, unsupported, unexecuted or timed out. Worker completion
does not mean task completion: the method workers include handled callback/factory/
receipt faults. The 28 resource-limit rows are old helper workers and remain
right-censored whole-worker observations with unknown internal phase, outcome and
unreturned costs. They are not plan-time lower bounds, exact times or zero cost.

## B: common-runner method regression

The old 240 parents (30 per F1–F8, seed982451653) are **observed regression data**.
Only original candidate order and random seed17 were rerun: four methods, 960
trials, plus 60 separate direct references. Old reversed/renamed/other random
variants were not rerun and do not enter these intervals.

F1 covers declared provenance/duplicate origin; F2 exact cross-obligation staged
helpers; F3 partial required checkers/self-verification; F4 contract/dependency
changes and re-resolution; F5 exact negative-subject and contradiction grounds;
F6 fixed pipelines/initial completion; F7 missing authority/material, faults,
unknown use and no-op; F8 actual bounded CSV/rules, exact decimals and snapshots.
Raw validity and permitted within-budget solvability are separate labels.
Initialization uses actual issued callbacks; paid initialization is recorded
separately and added equally to total budgets. Callbacks check supplied raw material,
not a fixed PASS or an oracle label.

All four methods use public `run`, changing only its pure selector. Complete pools,
availability, issuance, callback views, receipt/error validation, progress/replan,
finite step bounds and external worker supervision are common. `feasible_actions`
includes unmet-gap/necessity and helper eligibility, not only safety filtering.
Thus this is an ordering comparison conditional on EGR's common mechanism.

The independent oracle inspects raw numeric/file conditions, receipt identity,
exact active targets, owner/scope/contracts, finite dependencies, checker authority/
revision/purpose and full related resolution inputs. It calls neither `plan` nor
private acceptance predicates. It requires all distinct active required targets
to be checked and uses least grounded support for these finite recipes. General
negative cyclic authority is outside this method oracle's scope and has separate
runtime regressions.

| Method | Completion / solvable | False-satisfied / all attempted | Erroneous stop / solvable |
| --- | --- | --- | --- |
| EGR | 145/145 | 0/240 | 0/145 |
| Fixed-feasible | 122/145 | 0/240 | 23/145 |
| Verify-first | 127/145 | 0/240 | 18/145 |
| Random-feasible, seed17 | 133/145 | 0/240 | 12/145 |

For each method the 95 unsolvable parents split into **75 known correct
abstentions, five uncertain incomplete stops and 15 execution faults**.
All 240 oracle outcomes were assessed. Known abstention requires defined
non-solvability, incomplete outcome, meaningful clean domain halt, known bounded
use/effects and no pending invocation. The five unknown-effect/use cases are
not promoted to known safe success. Fifteen verification-cost observations per
method remain unknown; that count is not interchangeable with fault or uncertain
stop counts. Faults remain paid attempted work.

| Family | Solvable N | EGR | Fixed | Verify-first | Random17 | All-task false-satisfied denominator |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | 18 | 18 | 0 | 0 | 18 | 30 |
| F2 | 24 | 24 | 24 | 24 | 24 | 30 |
| F3 | 24 | 24 | 24 | 24 | 24 | 30 |
| F4 | 22 | 22 | 17 | 22 | 22 | 30 |
| F5 | 16 | 16 | 16 | 16 | 4 | 30 |
| F6 | 21 | 21 | 21 | 21 | 21 | 30 |
| F7 | 0 | 0 | 0 | 0 | 0 | 30 |
| F8 | 20 | 20 | 20 | 20 | 20 | 30 |
| Adequate budget | 132 | 132 | 112 | 116 | 120 | 192 |
| Tight budget | 13 | 13 | 10 | 11 | 13 | 48 |

The 0.2.1 original-order counts were 145/142/143/145; current counts are
145/122/127/133. Independent old/new trace review attributes the baseline decline
entirely to common-runner `no_progress`: fixed loses20 parents (16 F1, four F4),
verify-first loses16 F1 and random loses12 F5. First actions and initial full-pool
feasible order are unchanged. F1 first reads `read:repeat`; the four F4 cases read
`read:extra` duplicating rules0's content/source/group; F5 reads `read:alias`.
The old manual baseline treated any nonempty evidence payload as progress and
continued. Public `run` stops unneeded duplicate substance/bindings after one
callback. For example F1 fixed index1 previously executed repeat → e1 → e2 →
check-e1 → check-e2; it now stops after repeat. EGR loses no completed parent.
Thus the changed difference includes a shared semantic-progress contract, not
improved ranking or an independent-stack gain. Original observations are preserved.
The old all-variant
intervals included zero; the current original-only paired intervals below answer
a narrower regression question, not an unseen population claim or equivalence test.

| EGR minus baseline | Paired solvable N | Completion difference | 95% parent-paired bootstrap interval | Wins / ties / losses |
| --- | --- | --- | --- | --- |
| Fixed | 145 | 0.15862 | [0.10345, 0.22069] | 23 / 122 / 0 |
| Verify-first | 145 | 0.12414 | [0.07586, 0.17931] | 18 / 127 / 0 |
| Random17 | 145 | 0.08276 | [0.04138, 0.13103] | 12 / 133 / 0 |

Bootstrap seed2239 uses 1,000 paired parent resamples. Each parent has one
declared trial per method here; no missing-variant cluster mean is invented.
The synthetic families are designed finite workloads, not a random sample of
real business tasks. Intervals describe variation within this task construction.

## Same-completion costs, all-task costs and fixed references

Normal method time has no profile/tracemalloc. The controller interval is the
common public-run execution/replanning path; trial CPU/end-to-end additionally
include setup, actual initialization, final assessment, oracle and snapshot work.
Cold SDK import and whole-worker startup/IPC are separately recorded. These
different scopes must not be called a pure ranking cost or a pure minimal pipeline.

| Both-success pair | N | Callback difference EGR − baseline (95% interval) | Controller wall difference, ms (95% interval) | Controller CPU difference, ms (95% interval) |
| --- | --- | --- | --- | --- |
| Fixed | 122 | −0.16393 [−0.27049, −0.07377] | −0.16216 [−0.30154, −0.04763] | +0.12807 [−1.15266, +1.53689] |
| Verify-first | 127 | 0 [0, 0] | +0.00937 [−0.04216, +0.05986] | +0.49213 [−0.86122, +1.84547] |
| Random17 | 133 | −0.06015 [−0.13534, −0.01504] | −0.11674 [−0.20776, −0.04043] | +0.35244 [−1.05733, +1.64474] |

These are success-selected known-cost pairs, not all-task savings. Verify-first
has equal callbacks and no resolved overhead difference; every controller CPU
interval includes zero. Desktop noise and coarse Windows CPU quantization limit
submillisecond interpretations. Zero CPU median does not imply no CPU work.

| All 240 task attempts | Mean callbacks | Known verification mean (N=225) | Mean controller wall, ms | Complete / incomplete-or-fault callback mean (N) |
| --- | --- | --- | --- | --- |
| EGR | 2.13750 | 1.25778 | 2.32486 | 2.49655 (145) / 1.58947 (95) |
| Fixed | 1.99583 | 1.10222 | 2.30581 | 2.66393 (122) / 1.30508 (118) |
| Verify-first | 1.87917 | 1.07111 | 2.17171 | 2.44094 (127) / 1.24779 (113) |
| Random17 | 2.20417 | 1.22667 | 2.44121 | 2.69173 (133) / 1.59813 (107) |

The baseline's low all-task mean may reflect failed solvable work; it is not an
efficiency advantage. All callback costs are known, while 15 verification costs
per method are unknown and excluded only from the known-cost mean, never replaced
by zero. [Method summary](../benchmarks/results/v0.2.2/summary.json) retains outcome,
family/budget, all-task and selected-pair costs with their denominators.

Delay sensitivity adds an assumed equal delay of 0/0.001/0.01/0.1/1 seconds to
every callback. At 0.01 seconds, selected-pair EGR wall differences are −1.8015 ms
for fixed, +0.00937 ms for verify-first and −0.71824 ms for random. This is an
additive assumption, not measured latency, token savings, LLM fees or commercial ROI.

The 60 direct references are separate: F6 raw completion25/30 and F8 20/30,
with no assessed false acceptance. They perform 50/60 material reads respectively
and 30 validations each. Batching, receipts and SDK resource-bound contracts
differ; callback/verification counts are not comparable SDK costs. Shared harness
setup remains measured. F6/F8 solvable routed tasks have equal method completion,
and predetermined steps may be better served by a simple fixed pipeline.

## A: acceptance and continuation diagnostics

Each installed version ran 14 fixed functional properties. Old 0.2.1 met11/14;
candidate 0.2.2 met14/14, with no unassessed cases or case exceptions. The three
old failures were a partial external resolution basis, a same-digest related alias
and retained partial resolution history. They incorrectly reported satisfied;
the candidate retains the history but leaves the issue unresolved. Valid all-related
external grounds remain accepted. Actual paid invalidation, contract/checker updates,
save/load/re-resolution, exact negative subject, prohibited self-check, helper
bindings, exact decimal file rejection and supported large snapshots remain usable.
These are mechanical finite properties, not authentication or population CVE claims.

## C: proof and candidate-helper graphs

Existing proof graphs and unacquired helper candidates are measured separately.
Time, diagnostic visits and traced allocation run in separate processes. Normal
time has one warmup and ten repeats. Input/candidate construction, real seed
callbacks, snapshot dump/load and semantic assessment are separate recorded scopes.
Construction/initialization observations are single samples, not stable percentiles.

| Family / version | Completed / requested measurement rows | CPU-limited | Reference agree / disagree / unassessed / not completed |
| --- | --- | --- | --- |
| Proof / 0.2.1 | 180/180 | 0 | 180 / 0 / 0 / 0 |
| Proof / 0.2.2 | 180/180 | 0 | 180 / 0 / 0 / 0 |
| Helper / 0.2.1 | 89/117 | 28 | 63 / 0 / 26 / 28 |
| Helper / 0.2.2 | 117/117 | 0 | 63 / 0 / 54 / 0 |

Proof uses 60 chain/diamond/branches/pure-cycle inputs, sizes4/8/16/32/64 and
checkers1/2/3. Both versions already use the indexed proof evaluator. All 60
paired normal plan timings completed; median old/new ratio is **1.00600** (new
shorter38, longer22). This is nearly unchanged observed performance, not a second
proof-graph speedup. The restricted proof reference checks identical required
parents and ungrounded cycles; arbitrary negative/grounded alternatives have
separate functional regressions.

Helpers use 39 declared inputs: alternatives1/2/4, depths4/8/12/16/24/32/64,
shared/diamond/branching inputs, multiple checkers, current evidence, unavailable
authority, exact scope/digest, optional/satisfied ownership, invalidation/contract
changes and grounded/ungrounded cycles. The independent scanning AND/OR reference
is deliberately limited to positive recipes of depth≤8 with the consuming root
blocked. The 21 small inputs ×three modes agree for both versions. Larger
completion is not independent reference agreement; its unassessed rows remain.

| Paired normal-time scope | Positive finite pairs / inputs | Median old/new ratio | Noncompleted pairs | Completed zero/missing phase pairs |
| --- | --- | --- | --- | --- |
| Helper plan | 29/39 | 1.02193 | 10 | 0 |
| Helper plan + start/observe + binding progress | 29/39 | 1.19479 | 10 | 0 |
| Helper start/observe | 23/39 | 1.28855 | 10 | 6 |
| Helper binding progress | 23/39 | 1.02900 | 10 | 6 |
| Proof plan | 60/60 | 1.00600 | 0 | 0 |

The six absent continuation phases reflect no selected callback, not missing
positive cost. No speed ratio is assigned to censored or zero phases. Of29 paired
helper plan timings, new is shorter16 and longer13. The median conceals important
alternative-branch differences and overhead on simple inputs.
For the seven one-alternative chains, the median old/new plan ratio is0.816,
favoring the old simpler path; removal of exponential revisit does not imply
every input becomes cheaper.

| Helper input | Old / new normal median plan, ms | Old / new normal median sequence, ms |
| --- | --- | --- |
| Chain depth4, alternatives2 | 0.19175 / 0.15790 | 0.67470 / 0.45170 |
| Chain depth8, alternatives2 | 1.15370 / 0.22105 | 3.36725 / 0.60160 |
| Chain depth12, alternatives2 | 15.96050 / 0.30435 | 47.76690 / 0.77745 |
| Chain depth8, alternatives4 | 157.40240 / 0.35425 | 474.34600 / 0.88090 |
| Chain depth16, alternatives2 | Whole-worker CPU limit / 0.38700 | Whole-worker CPU limit / 0.97575 |
| Chain depth24, alternatives2 | Whole-worker CPU limit / 0.52315 | Whole-worker CPU limit / 1.28315 |
| Chain depth64, alternatives1 | 0.59660 / 0.70430 | 1.37910 / 1.74480 |

Separate count workers record old depth12/alternatives2 action-path entries8,191
and depth16 entries131,071, while new expands25/33 action subproblems and consumes
59/79 rule edges in each assessed phase. Old/new counts are different units,
not a universal count speed ratio. The depth16 count/memory arms can complete
even though the ten-repeat normal-time worker crosses its CPU bound; this is not
an inconsistent plan outcome. All28 old helper limits are CPU crossings: count9,
memory9 and time10. The unknown internal phase is retained.

Memory is a separate single traced replay, not normal timing, RSS or Job memory.
Across30 completed helper memory pairs, new traced allocation is lower26 and
higher4; across60 proof pairs it is lower41 and higher19. These small differences
do not establish a general memory improvement. For example helper chain64 with
one alternative uses769,199/671,327 old/new traced bytes, yet normal new plan is
slower. A memory or timing win alone is not an overall efficiency result.
The unmatched helper medians are393,774 old bytes (30 completed inputs) versus
407,896 new bytes (39); different completed-input sets prevent interpreting that
contrast as a memory advantage or regression.

## New confirmation and retained evidence

Unused seed49979687 generated32 conditions with actual topology, alternative,
prerequisite/current-validity, availability/budget and update differences. Both
versions completed32/32 semantic workers and agreed with the small independent
helper reference32/32, with no disagreement or unassessed outcomes. These
confirmation cases are separate from the observed regression set. They check
finite semantics, not completion frequency in real applications; numeric/ID
changes are not inflated into independent external tasks.

The [controller summary](../benchmarks/results/v0.2.2/controller-summary.json)
retains every measurement cell, censor, reference status, timing denominator,
work count and allocation scope. Formal raw JSONL SHA256 is
`7c8d40a6dd80db41adfa91ce4e0ad581119032d421ccaaac22675b2b66473dd2`;
execution-manifest SHA256 is
`652f80e1627aaa4ab3a7b4b48f5884423b46284901c98c3294878ec70129a305`.
The [provenance](../benchmarks/results/v0.2.2/artifact-provenance.json) separates
measured candidate and final release bytes. Original v0.2.1 evidence, diagnostic
replay, exact source/constraints, wheels, freeze and new raw traces are retained.
The new `benchmark-raw-v0.2.2.zip` was generated: all 54 manifest asset hashes
and all 56 entries' ZIP integrity verified.
Size 12,592,735 bytes, SHA256
`e90060aae7c2fac6ebe3f920a74a7066a4b63353daf7f7f0ffdbc23440b3f37a`.
Its 54 manifest assets plus `MANIFEST.json` and `BUNDLE_README.txt` include the
unchanged old raw ZIP, formal records/CSV, frozen LF source/wheels/constraints,
old40-case diagnostic and separately labeled post-formal independent review.
[Checksums](../benchmarks/results/v0.2.2/BENCHMARK_SHA256SUMS) identify the archive.
The planned [raw release asset](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.2/benchmark-raw-v0.2.2.zip)
has not been reported uploaded here; archive generation, upload, native CI and
PyPI verification have separate states in [validation](validation.md).

Reproduction commands are in [benchmarks/README](../benchmarks/README.md).
No measured runtime, oracle, generator or protocol was changed after this formal
run. Result/docs collection can change metadata, but release admission must match
the measured runtime/package and harness/protocol.
The final collection also includes standalone source-test import setup in
`test_summarize_022.py`; it changes no measured runtime/harness/generator bytes.
This CPU-only experiment uses
no LLM/GPU/paid inference and establishes neither source independence, money
savings, capability growth nor risk zero. Routing fits conditional evidence work;
fixed known pipelines can remain simpler and cheaper.
