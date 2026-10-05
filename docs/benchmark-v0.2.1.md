# v0.2.1 engineering benchmark

This experiment separates three questions: Q1 asks whether acceptance and explicit
continuation agree with an independent contract oracle; Q2 compares scheduling
methods under the same feasible actions and resources; Q3 measures controller
CPU, memory and dependency-evaluation work. A correctness repair does not by itself
establish a scheduling advantage, and fewer callbacks do not imply lower CPU cost.
The [Japanese report](benchmark.ja.md) describes the same protocol.

The frozen experiment completed 5,400 Q1/Q2 rows (4,680 new-version and 720
old-version) and 360 Q3 measurement cells. New EGR completed every solvable
parent; its scheduling gains over strong baselines were small, with clustered
intervals including zero. Callback reductions on selected successful pairs came
with higher traced trial CPU. Q3 observed faster dependency evaluation in most
completed pairs, with higher traced allocations. These are distinct findings.
The completed checks also include the 260-test source suite, an installed-candidate Windows check
with 223 portable tests plus SDK/CLI execution, and a portable smoke covering
11 generated parents, 33 method trials and four graph references. The remaining
37 source-only tests exercise repository/release tooling. The smoke's
outcome digest is
`b151304eaca99ad064b6a6ad6b27cb4a08361f8257438ec910d57ad6d78b35c5`;
that smoke is a portability/regression check, not the 240-parent holdout.

## Q1/Q2 observed outcomes

The saved [aggregate summary](../benchmarks/results/summary.json) and
[scaling summary](../benchmarks/results/scaling-summary.json) retain complete
denominators and assessment status; raw traces and CSV tables are in the bundle
described below. Figures in this report are rounded for display.

The 240 original-order parent tasks include 145 classified as solvable under their
declared material, authority and budget. Primary completion uses original order
and random seed 17. Old unsupported APIs leave 220 compatible parents, 132 of
which are solvable. Counts below are not confidence intervals. Cluster completion
separately averages variants/seeds within each solvable parent.

| Version / method | Primary completion n/N | Cluster completion | False-satisfied parents n/N | Strict correct abstention n/N |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 99/132 | 76.263% | 9/220 | 64/88 |
| 0.2.1 EGR | 145/145 | 100% | 0/240 | 80/95 |
| 0.2.1 fixed-feasible | 142/145 | 98.621% | 0/240 | 70/95 |
| 0.2.1 verify-first | 143/145 | 99.080% | 0/240 | 70/95 |
| 0.2.1 random-feasible | 145/145 | 98.544% | 0/240 | 70/95 |

These observed completion differences are modest: three parents relative to fixed
order, two relative to verify-first, and no primary completion difference relative
to seeded random selection. Other orders/seeds reduce random's cluster mean;
three parents have a lower mean than EGR. No general routing advantage or cost
saving follows. The 4,680 new-version rows include method
variants, random repeats, ablations and pipeline references; they are not 4,680
independent parent tasks.

All 4,680 new rows have worker status `completed` and an assessed oracle. A
completed worker can report a guarded callback/factory/receipt fault rather than
task completion. Old rows comprise 660 completed and 60 unsupported trials
(20 F4 parents requiring the absent invalidation API). Neither version has a
Q1/Q2 worker timeout or unexecuted row. Compatible oracle-unassessed counts are
zero; the 60 unsupported rows have no oracle assessment and remain explicit.

| Version / method | Attempted compatible trials | Unsupported trials | Exception-bearing trials | Unknown verification-cost trials |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 660 | 60 | 57 | 57 |
| 0.2.1 EGR | 720 | 0 | 45 | 45 |
| 0.2.1 fixed-feasible | 720 | 0 | 45 | 45 |
| 0.2.1 verify-first | 720 | 0 | 45 | 45 |
| 0.2.1 random-feasible | 2,160 | 0 | 135 | 135 |

The new exception-bearing trials are deliberately faulty F7 recipes; they are
retained as failed compatible attempts: 270 across all new rows. Old EGR's 57
exception-bearing rows comprise 45 F7 faults and 12 F4 re-resolution errors.
Strict correct abstention requires a clean router stop:
15 faulty F7 parents therefore do not become clean abstentions merely because
they fail safely. Old false satisfaction occurs on four F5 parents and five F8
parents, 27 variant trials. New false satisfaction is 0/240 EGR parents and
0/4,680 new-version trials, including the separate references, within this oracle.

The frozen parent-record field `correct_abstention` is an error-free router-stop
indicator, despite its name. It is also true for 32 solvable method/parent groups,
including erroneous old/baseline stops. Interpret that flag as correct abstention
only with `solvable == false`. The aggregate n/N tables above already apply that
condition; this naming caveat does not change their counts. The original field
and its raw evidence are retained, rather than silently renamed after measurement.

On the **matched version subset**, new EGR has primary completion 132/132 versus
old 99/132, with 220 compatible parents total. The parent-mean difference is
23.737 percentage points (95% bootstrap interval 16.667–31.061), wins/ties/losses
33/99/0. False-satisfied parents are old 9/220 versus new 0/220. The other
20 requested parents are not silently treated as old failures or successes;
their unsupported operation is shown above. Equal completion in F5/F8 does not
erase the old incorrect acceptance on unsolvable parents.

### Family and budget counts

Entries are primary completion n/N. Each family requests 30 parents; old F4
has only 10 compatible parents. `0/0` means no solvable parent in that stratum,
not a measured zero-percent completion rate.

| Family | 0.2.0 EGR | 0.2.1 EGR | Fixed | Verify-first | Random |
| --- | --- | --- | --- | --- | --- |
| F1 | 18/18 | 18/18 | 16/18 | 16/18 | 18/18 |
| F2 | 0/24 | 24/24 | 24/24 | 24/24 | 24/24 |
| F3 | 19/24 | 24/24 | 24/24 | 24/24 | 24/24 |
| F4 | 5/9 | 22/22 | 21/22 | 22/22 | 22/22 |
| F5 | 16/16 | 16/16 | 16/16 | 16/16 | 16/16 |
| F6 | 21/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| F7 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| F8 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

| Budget | Requested parents | 0.2.0 EGR | 0.2.1 EGR | Fixed | Verify-first | Random |
| --- | --- | --- | --- | --- | --- | --- |
| Adequate | 192 | 88/120 | 132/132 | 132/132 | 132/132 | 132/132 |
| Tight | 48 | 11/12 | 13/13 | 10/13 | 11/13 | 13/13 |

Old compatible budget strata have 176 adequate and 44 tight parents; new has
192 and 48. Within-version primary differences are confined to tight tasks.
F1 provides two of fixed/verify-first's missed parents; F4 provides fixed's
third. All main new methods tie on F2, F3, F5, F6 and F8 completion.

### Paired scheduling differences and costs

Differences are EGR minus baseline, using parent means across variants/seeds.
Intervals are percentage points, not ratios of the primary integer counts.

| Baseline | Paired solvable N | Completion difference, pp | 95% parent-bootstrap interval, pp | Wins/ties/losses |
| --- | --- | --- | --- | --- |
| Fixed | 145 | 1.379 | [0, 3.218] | 3/142/0 |
| Verify-first | 145 | 0.920 | [0, 2.299] | 2/143/0 |
| Random | 145 | 1.456 | [0, 3.295] | 3/142/0 |

All intervals include zero. Callback/check means below measure **continuation**,
excluding separately recorded initialization; trial CPU/end-to-end include
common setup, cold library import, initialization, observer and snapshot work. Costs average variants
within parent, then parents. Verification means omit unknown observations:
known-cost N is 201/220 old parents and 225/240 for each new main method.
The unknown trial counts above are not zeros.

| Version / method | Callback mean (parent N) | Known verification mean (parent N) | Trial CPU mean, s | Trial end-to-end mean, s |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 1.7439 (220) | 0.9983 (201) | 0.4471 | 0.4795 |
| 0.2.1 EGR | 2.1375 (240) | 1.2578 (225) | 0.4868 | 0.5211 |
| Fixed | 2.3319 (240) | 1.2963 (225) | 0.4843 | 0.5160 |
| Verify-first | 2.2042 (240) | 1.2519 (225) | 0.4825 | 0.5149 |
| Random | 2.3079 (240) | 1.2810 (225) | 0.4828 | 0.5158 |

Old lower average work accompanies poorer completion and a different compatible
denominator; it is not demonstrated savings. EGR uses fewer callbacks than the
new baselines, but slightly more known verifications than verify-first and more
descriptive trial CPU than all three. The separate pure-plan version timing is
Q3, not this cross-method observer timing.

| Baseline | Both-success parent N | Callback difference | Traced trial CPU difference, ms |
| --- | --- | --- | --- |
| Fixed | 142 | -0.2723 | +3.558 |
| Verify-first | 143 | -0.0932 | +5.390 |
| Random | 142 | -0.2504 | +4.988 |

This selected subset requires full success across attempted variants for both
methods. Its cost differences exclude failing pairs and do not estimate all-task
efficiency. F3, F6 and F8 have zero callback difference on their successful
subsets. In F2, EGR versus verify-first has identical calls and completion but
16.710 ms more descriptive trial CPU, illustrating a mixed or unfavorable result.

### Ablations and direct pipelines

| Ablation | EGR / ablation primary completion | Paired N | Cluster difference, pp [95% interval] | Both-success N; callback / CPU-ms difference |
| --- | --- | --- | --- | --- |
| F1 without provenance rank | 18/18 / 16/18 | 18 | 7.407 [0, 18.519] | 16; -0.6667 / +3.255 |
| F2 without gap rank | 24/24 / 24/24 | 24 | 0 [0, 0] | 24; -0.3333 / +6.510 |

The gap ablation does not change completion on these F2 tasks, although it adds
calls. The provenance ablation affects two parents; its interval still includes
zero. Both cost subsets retain higher EGR trial CPU, so the mechanisms are not
reported as unqualified efficiency wins.

| Reference family | Routed EGR oracle completions / all parents | Direct pipeline oracle completions / all parents | Routed / pipeline trial CPU mean, s |
| --- | --- | --- | --- |
| F6 | 21/30 | 25/30 | 0.4760 / 0.4267 |
| F8 | 20/30 | 20/30 | 0.5075 / 0.4717 |

These are all-parent counts, not the scheduler's solvable n/N. F6's pipeline can
batch valid material beyond the SDK callback budget, explaining its four
additional completions without treating them as a matched scheduler win. F6
reads one/two/three materials and performs one validation; F8 reads two files
and performs one validation. Their raw worlds and differing batching/receipt
contracts are explicit. The pipeline is a useful simpler reference with lower
observed trial CPU here; it is excluded from primary inference.

## Frozen inputs and execution environment

The executable protocol is [protocol.json](../benchmarks/protocol.json). The
implementation was committed and both distributions installed into separate
ordinary, noneditable environments before holdout execution. SDK imports resolve
to those environments' `site-packages`, outside the source checkout. The harness
verifies interpreter, runtime dependencies, platform, package bytes, protocol and
harness fingerprints against its freeze record.

| Item | Recorded value |
| --- | --- |
| Protocol | `egr-021-engineering-v1` |
| Implementation commit | `305eec2cbf4f16c7d50dbb8bad002bc0cbc6d1c5` |
| Official 0.2.0 runtime commit | `e8d77f210d7579d6a367b7564b485b2586ffd074` |
| Freeze time | `2026-10-05T04:38:11Z` |
| Protocol SHA-256 | `4bfb84ce958aab46890525ee9225832c950e03bbbdfd7266b320c595f65ca06a` |
| Harness SHA-256 | `d3db76040403efbf802437c8a62514466c01ab0efdfec390823989224aeae4de` |
| Measured 0.2.1 wheel SHA-256 | `e8c2bead23b7c2cc622ff2a3215e262c23452f621d1298359dba520c027b01aa` |
| Official 0.2.0 wheel SHA-256 | `039594d7fc5e39ab7b600c71f54682bb2d46147ba4e69a05a55f255a1806f3bf` |
| Measured 0.2.1 package fingerprint | `5df6a0b5e7c521079e29475950addf6e1b84d62b3f3c70033307a82643e8341a` |
| Operating system / architecture | Windows 11, `10.0.26300`, AMD64 |
| CPU | AMD Ryzen 7 8840HS, 8 cores / 16 logical processors |
| Physical RAM | 66,363,183,104 bytes |
| Python / Pydantic / pydantic-core | 3.12.14 / 2.13.5 / 2.46.5 |
| Other runtime packages | annotated-types 0.8.0; typing-extensions 4.16.0; typing-inspection 0.4.4 |

The package fingerprint hashes canonical sorted package-relative filenames and
their byte hashes, excluding generated `__pycache__`. It distinguishes the measured
runtime from later documentation/metadata changes; the measured wheel hash remains
the identity of the actual input distribution. The [freeze record](../benchmarks/results/freeze.json)
and [artifact provenance](../benchmarks/results/artifact-provenance.json) retain
the exact identities; large raw traces are separate from the package. Freezing here is a
repository procedure, not external preregistration.

The old runtime is the published 0.2.0 distribution from its original commit;
the task generator, oracle and method/scaling harness are the frozen 0.2.1
implementation-commit files for both version arms. Holdout executes from the LF
Git archive of that commit with the declared installed wheel. Thus an old/new
runtime comparison does not silently substitute the old release's limited demo
as its harness. Raw records retain the runtime version/wheel/package fingerprint
and the common implementation/protocol/harness identity separately.

## Tasks, methods and oracle

The holdout has 240 distinct generated parent tasks: 30 per family. Development
uses seed 21041 and eight parents per family; the frozen holdout uses seed
982451653. Original, reversed and renamed candidate pools are variants of the same
parent. Random scheduling uses seeds 17, 71 and 191. These repetitions do not create
additional independent tasks.

| Family | Contract exercised |
| --- | --- |
| F1 | Repeated/distinct declared origins, unknown provenance, invalid numbers and tight/adequate budgets |
| F2 | Exact cross-obligation dependencies, satisfied/optional helpers, duplicate content and one/two prerequisite stages |
| F3 | Multiple required checkers, partial PASS, self-verification prohibition, unavailable checker and pending capacity |
| F4 | Real resolution history followed by contract/material/check changes and explicit re-resolution |
| F5 | FAIL/UNKNOWN history, same-byte aliases, exact/wrong-subject resolution and unavailable resolution authority |
| F6 | Simple predetermined one/two/three-source pipelines, initial completion and valid/invalid material |
| F7 | Missing material/authority, callback/factory/receipt failures, unknown use, no-op and insufficient budget |
| F8 | Actual CSV/JSON bytes, exact decimal boundaries, duplicate structures, BOM/CRLF/Unicode paths and snapshot continuation |

Initialization uses actual public `start`/`observe` callbacks. Its cost is recorded
separately and added equally to each method's total budget. Candidate factories
inspect current State and finite material recipes, never oracle labels or future
observations. A read acquires an exact ID once; a check uses observed material and
explicit dependencies. Numerical/file checkers parse the real supplied data.

Within 0.2.1, EGR competes with three feasible baselines: `fixed-feasible` preserves
declaration order; `verify-first` stably selects verification before acquisition;
`random-feasible` makes a seeded choice. All use the public `feasible_actions`
safety gates and preserve the original finite pool for public `start`; no baseline
injects Attempts or repeats an already valid target merely to waste its budget.
F1 additionally removes provenance ranking, and F2 removes gap ranking, as bounded
ablations. A separate 0.2.0 EGR run compares compatible version pairs rather than
mixing a version repair with the within-version scheduler comparison.

The oracle independently examines raw arithmetic/exact decimal/file conditions,
receipt identity, current exact targets, owner/scope/contract, dependencies,
checker/revision/purpose and resolution fingerprints. It does not call `plan`,
coverage, `make_basis` or private acceptance predicates. Every distinct active
required target needs valid support. Positive content aliases collapse; a negative
check retains its exact subject ID. A least grounded positive proof is evaluated
over these finite DAG recipes. General grounded alternatives and indeterminate
negative cycles are runtime regression cases outside this holdout oracle's domain.
Raw-world validity and solvability under available authority/material/budgets are
separate labels; valid data alone does not imply a solvable task.

## Denominators and paired analysis

The primary completion statistic is integer **n/N solvable parent tasks**, using
original order and random seed 17. False satisfaction is **n/N compatible attempted
parents**, where any evaluated variant falsely satisfied makes that parent positive;
per-trial counts and unassessed outcomes are also retained. Unsupported old APIs,
unexecuted trials, exceptions and timeouts are explicitly counted. Compatible
exceptions/timeouts are failed attempts, not correct abstentions or free runs.
An old unsupported invalidation operation is excluded only from matched-version
pairing and remains visible in the old-version table.

For method differences, variants and random seeds are averaged within each parent.
Paired bootstrap resamples these parent differences 1,000 times with seed 2239 to
form a 95% interval. The report retains paired N and wins/ties/losses, overall and
family/budget strata. Generated families are a finite engineered workload, not a
sample from all user tasks. A confidence interval expresses variability within that
task construction; it does not establish a population-wide causal benefit.

All-task costs are reported separately from the selected **both-success subset**,
which requires every attempted variant in both paired methods to succeed. A subset
cost difference always includes its N. Cheap failure is not an efficiency win, and
conditioning on this successful subset is not an all-task savings estimate. Tokens
and money are unmeasured; no conversion from CPU/callback counts is supplied.

## Timing, memory and reference pipelines

Q1/Q2 uses identical isolated workers and a 10-second whole-worker deadline.
The 7,200-second cap applies per `run_trials` invocation, separately to the new
method run and old version-only run. Startup/import, trial, serialization and IPC are
within that worker limit. Costs unavailable after timeout stay unknown; the cap
leaves explicit unexecuted rows. Trial CPU/end-to-end, planning, callbacks,
serialization, initialization and worker startup/import/IPC are recorded fields.
Trial CPU/end-to-end and allocation tracing start before `environment()` first
imports the SDK/Pydantic. Their cold library import is therefore inside the
traced trial cost and allocation peak. `startup_import_and_ipc_seconds` is a
whole-worker residual covering outside-trial process/harness startup and IPC;
it neither isolates nor removes all library import time. These trial values
are not pure controller-resource measurements.
Q1/Q2 timing also includes `tracemalloc` overhead. Its `planning_cpu_seconds` field
times EGR runner `plan` calls, whereas the host-baseline branch includes candidate
factory evaluation, `feasible_actions` and selection. These are different phase
definitions, so that field is not a cross-method pure-planner timing comparison.
Both branches additionally include the final common public `plan` assessment.
Total trial CPU/end-to-end still measure the declared observer and method work.
Peak traced Python allocations are not resident memory, and worker-spawn cost is
not planner CPU cost. The separate uninstrumented Q3 `plan` timing is the pure-plan
old/new performance comparison.

Measurements use an ordinary Windows desktop. Power/thermal state, background
processes and scheduler behavior were not experimentally controlled. The early
installed-candidate Windows check (223 tests, SDK/CLI and smoke) overlapped part
of F1. Q1/Q2 timings therefore describe this traced run under variable desktop
load; they do not support a wall-time performance-superiority claim. Q3 ran
serially after both Q1/Q2 version runs, with timing/count/memory in
separate workers, but remains a measurement on this one ordinary host.

Q3 ran separately after Q1/Q2 to avoid that workload's concurrent timing load.
It uses chain, diamond, branches and pure cycle histories of sizes 4, 8, 16, 32 and
64 with one/two/three checkers. Old and new graph inputs have the same semantic
records and required conditions; the new default invalidation field does not add
authority. Construction, dump/load and end-to-end worker time are recorded apart
from `plan` CPU/wall time. Timings have one warmup, ten repetitions for sizes 4/8
and one repetition for larger sizes. Timing, diagnostic counts and traced memory
use separate processes; timing is uninstrumented.

Counts name actual new base-check/worklist-check/worklist-target evaluations and
final memo lookups separately. The old count names recursive trusted-check entries.
These are different work units; their ratio alone is not a CPU speedup. Memory uses
one separate traced-allocation replay. Ordinary scaling workers have a 3-second
deadline, small timing workers 20 seconds, and each version's scaling run has a
1,200-second cap.
Whole-worker timeouts are right-censored with unknown phase: startup, construction
or evaluation may be responsible. They are neither exact plan times nor plan-time
lower bounds, and remain in the report.

F6/F8 also have actual direct-pipeline references. They read/parse materials and
validate them without routed initialization. Batching, receipts and SDK resource
bounds differ, so they are excluded from primary scheduler tables. Shared
World/State/Policy/material setup still contributes to their CPU/end-to-end costs;
a minimal ordinary pipeline can be cheaper than this harness reference. When a
fixed dependency order already suffices, routing can add overhead without reducing
calls. Equal, worse and mixed outcomes remain part of the experiment.

## Q3 observed controller work and cost

The two versions each requested 180 cells: 60 graph/size/checker inputs times
count, timing and memory arms. All new cells completed. Old results retain
65 whole-worker timeouts and one count-instrumentation exception.

| Version | Completed cells | Timeouts | Exceptions | Unexecuted |
| --- | --- | --- | --- | --- |
| 0.2.0 | 114/180 | 65 | 1 | 0 |
| 0.2.1 | 180/180 | 0 | 0 | 0 |

There are no reference disagreements among assessed completed cells and no new
indexed-work bound violations. Each of the 60 new count inputs evaluated every
recorded check once for its base and final memo lookup, and check-truth steps
were at most recorded checks plus verified-dependency edges. This observed
fixture bound is not a universal cost theorem for arbitrary histories.

| Graph / targets / checkers | Old recursive entries | New base / check-truth / target-truth / memo |
| --- | --- | --- |
| Branches / 4 / 1 | 7 | 4 / 7 / 7 / 4 |
| Chain / 4 / 2 | 52 | 8 / 14 / 7 / 8 |
| Chain / 8 / 2 | 1,004 | 16 / 30 / 15 / 16 |
| Diamond / 8 / 2 | 4,452 | 16 / 42 / 15 / 16 |
| Branches / 64 / 3 | 759 | 192 / 381 / 127 / 192 |
| Chain / 64 / 3 | Whole-worker timeout | 192 / 381 / 127 / 192 |
| Cycle / 64 / 3 | Count-arm RecursionError | 192 / 192 / 64 / 192 |

These diagnostic units differ; dividing old entries by new memo lookups would
omit real new work. The tables below combine **separate** time and memory arms
for the same graph, not simultaneously instrumented timing. Small timings have
ten measured repetitions, larger timings one; a single-repeat value is not a
stable percentile estimate. Traced allocation covers the memory replay's input
construction, dump/load, reference and plan, rather than isolated planner memory.

| Graph / targets / checkers | Old / new median plan wall, ms | Old / new peak traced allocation, bytes | Timing repetitions |
| --- | --- | --- | --- |
| Branches / 4 / 1 | 0.1196 / 0.1238 | 878,939 / 1,116,880 | 10 |
| Chain / 4 / 2 | 0.6565 / 0.1747 | 904,004 / 1,142,605 | 10 |
| Chain / 8 / 2 | 13.1176 / 0.3159 | 972,324 / 1,208,581 | 10 |
| Diamond / 8 / 2 | 57.3133 / 0.3895 | 991,121 / 1,227,389 | 10 |
| Branches / 64 / 3 | 16.2565 / 4.2293 | 3,275,593 / 3,834,572 | 1 |
| Chain / 64 / 3 | Timeout / 4.1350 | Timeout / 3,835,571 | 1 |
| Cycle / 64 / 3 | Timeout / 4.3264 | Timeout / 3,847,591 | 1 |

Among the 39 matched completed timing inputs, new plan wall time is lower in
38 and higher in one (branches, four targets, one checker). Among 36 matched
completed memory inputs, new peak traced allocations are higher in all 36.
Thus faster plan observations accompany higher replay allocations, and small
simple inputs need not improve. Submillisecond Windows CPU medians can quantize
to zero; that is not zero CPU work. No rate or lower-bound speedup is imputed to
censored old inputs. The complete table retains all 360 cells rather than just
these examples.

The exception is **old cycle / 64 targets / 3 checkers / count arm**:
`RecursionError` occurs with the recursive counting wrapper adding stack depth.
It is a failed diagnostic arm, not evidence of an uninstrumented runtime crash,
and is not merged with the 65 timeouts. Its original stderr and row remain in
the raw archive. Completed pure-cycle cells agree that an ungrounded cycle is
not satisfied. More general grounded/negative cycle authority stays outside this
scaling reference, as stated in the protocol.

## Reproduction and evidence boundaries

Use separate ordinary installations of the exact measured wheels, with the frozen
Python/runtime versions. The commands below run benchmark code without putting
`src/` on the import path. Use fresh external output paths; existing freeze/results
are not replaced.

```sh
NEW_PYTHON -m benchmarks.harness freeze --output EXTERNAL/freeze.json --implementation-commit 305eec2cbf4f16c7d50dbb8bad002bc0cbc6d1c5 --wheel CANDIDATE_WHEEL --baseline-wheel OFFICIAL_020_WHEEL
NEW_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --output EXTERNAL/methods.jsonl
OLD_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --version-only --output EXTERNAL/old-version.jsonl
NEW_PYTHON -m benchmarks.aggregate EXTERNAL/methods.jsonl EXTERNAL/old-version.jsonl --output EXTERNAL/report
NEW_PYTHON -m benchmarks.scaling run --python NEW_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-new.jsonl
NEW_PYTHON -m benchmarks.scaling run --python OLD_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-old.jsonl
NEW_PYTHON -m benchmarks.scaling summarize EXTERNAL/scaling-new.jsonl EXTERNAL/scaling-old.jsonl --output EXTERNAL/scaling-report
```

The full protocol requests 4,680 new-version method/ablation/reference rows, plus
720 old-version rows and the separately bounded scaling runs. Requested rows are
not completed observations. Earlier development logs include cap and metadata
revisions; they are retained diagnostic work, not confirmatory holdout evidence.
Any changed implementation/checker/generator/protocol after viewing holdout requires
a new protocol and unused seed, with the previous evidence preserved.

The raw archive `benchmark-raw-v0.2.1.zip` was generated and its contents verified:
9,502,776 bytes, SHA-256
`9212ee2499df0b16b47b23ac3150f71b83b1db69abc85a7123a02044f4fa69a0`.
The [checksum record](../benchmarks/results/BENCHMARK_SHA256SUMS) identifies it.
Its 31 members contain 29 source assets plus `MANIFEST.json` and `BUNDLE_README.txt`:
the unmodified formal method/version/scaling traces and reports, separately labelled
development traces, freeze/provenance/runtime constraints, frozen benchmark source,
the implementation LF archive, the completed Windows candidate profile, and both
official baseline and measured candidate wheel/sdist pairs. Manifest entries record
member byte sizes and hashes. Compact summaries/freeze
records belong in `benchmarks/results`; large traces are not wheel contents.
The measured candidate wheel is retained even if the final documentation-only
release wheel has different METADATA and therefore a different whole-wheel hash.
The frozen package fingerprint and byte comparisons distinguish those metadata
changes from executable package changes. Final CI enforces the same actual
package, protocol and harness bytes; changing them invalidates this measurement's
identity rather than becoming a documentation-only rebuild.
The designated [Release asset reference](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.1/benchmark-raw-v0.2.1.zip)
and `BENCHMARK_SHA256SUMS` are publication targets. Archive generation/verification
does not assert that Release upload or PyPI installation has already completed;
their actual status is recorded separately in [validation](validation.md).
This CPU-only, model-free synthetic experiment does not establish LLM accuracy,
statistical independence, monetary savings, capability growth or intelligence phases.
Zero observed false satisfaction does not imply zero risk. For the old published
defects and their actual histories, see [the 0.2.0 audit](audit-020.md); implementation
boundaries remain in [design](design.md).
