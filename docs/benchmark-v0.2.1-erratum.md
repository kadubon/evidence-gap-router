# v0.2.1 benchmark erratum: stopping semantics

The reported 80/95 versus 70/95 strict-abstention difference does not establish
a routing safety benefit. The old EGR arm used the public runner; other methods
used another loop. On ten F7 parents, equivalent final records received different
runner labels, and the aggregate required the EGR label `router_stopped`.

This correction reclassifies the **published raw evidence**. It does not rerun
the experiment, rewrite the original labels or replace its timing observations.
The [original English report](benchmark-v0.2.1.md),
[Japanese report](benchmark-v0.2.1.ja.md), protocol, freeze and raw archive remain
available. New v0.2.2 common-runner measurements are separate results.

## Evidence and reconstruction

The official [v0.2.1 Release](https://github.com/kadubon/evidence-gap-router/releases/tag/v0.2.1)
archive `benchmark-raw-v0.2.1.zip` was downloaded into a new dedicated directory.
Actual SHA256:
`9212ee2499df0b16b47b23ac3150f71b83b1db69abc85a7123a02044f4fa69a0`.
The original ZIP is retained read-only. Safe extraction checked paths, duplicate
entries and symlinks; all 29 manifest asset hashes and sizes verified.

The stdlib-only [reaggregation code](../benchmarks/erratum_021.py) consumes 4,680
new-version and 720 old-version recorded rows. It imports neither SDK nor the
original aggregate and executes no callbacks. It reproduces every published
primary overall/family/budget numerator and denominator before classification.
Primary means original order and random seed 17; repeats remain one parent.
The [new output](../benchmarks/results/v0.2.1-erratum/summary.json) preserves legacy
counts alongside the corrected classifications and trace comparisons.

For all ten F7 mode-4/mode-5 parents, the four primary methods' recorded
State/action/receipt/decision, oracle and costs are identical after normalizing
only invocation/receipt identifiers. Material IDs, authority, scopes, resource
values and payload remain exact. Mode 4 records one callback, unknown verification
use and effects, and `escalation_required`; mode 5 records one callback, zero
verification use, known effects and `blocked`. EGR's runner label was
`router_stopped`; the other methods' label was `no_progress`.

## Separate diagnostic replay

Before the new formal freeze, the same ten already observed parents were rerun
with the ordinary official 0.2.1 wheel and exact archived LF harness: 40 completed
trials, original order, seed 17. Wheel SHA256 `61129ec1…202917`, all 29 wheel RECORD
hashes and installed package fingerprint `5df6a0b5…e8341a` verified. Harness
`d3db76040403efbf802437c8a62514466c01ab0efdfec390823989224aeae4de`
and protocol `4bfb84ce958aab46890525ee9225832c950e03bbbdfd7266b320c595f65ca06a`
match the original freeze. Python 3.12.14, Pydantic 2.13.5/core 2.46.5 and all
runtime dependencies match the prior formal environment.

All ten normalized parent signatures agree across the four methods. Every trial
has one callback, incomplete oracle, no false satisfaction and a successful
snapshot roundtrip. Legacy counts are EGR 10 versus each baseline 0; corrected
counts are five known and five uncertain incomplete stops for every method.
New diagnostic raw SHA256:
`3d13813e997d95b556001692bb2dc9b6d98b52fbf1c4c06e62973b0c37fdb9bd`.
The separate `reproduce_f7.py`, JSONL and provenance summary are retained externally
for the new release evidence bundle. This is a diagnostic replay of observed
regression data, not an independent rerun of all 5,400 rows, unseen confirmation
or a new timing estimate. The original archive remains unchanged.

## Corrected primary classifications

Known correct abstention requires an explicitly unsolvable task, assessed
incompletion, an actual clean domain halt, known constrained resource use/effects,
no overrun and no unreceipted issued invocation. A solvable task's incomplete halt
is an erroneous stop. Worker/handler faults are separate. Unknown use/effects,
unknown execution or pending invocation remain uncertain, even when escalation
correctly prevents further work. Unconstrained tokens remain unmeasured.

| Version / method | Legacy label count | Known incomplete domain stop | Uncertain incomplete stop | Execution fault | Non-solvable denominator |
| --- | --- | --- | --- | --- | --- |
| 0.2.0 EGR | 64 | 59 | 5 | 15 | 88 |
| 0.2.1 EGR | 80 | 75 | 5 | 15 | 95 |
| 0.2.1 fixed-feasible | 70 | 75 | 5 | 15 | 95 |
| 0.2.1 verify-first | 70 | 75 | 5 | 15 | 95 |
| 0.2.1 random-feasible, seed 17 | 70 | 75 | 5 | 15 | 95 |

The old-version remaining nine non-solvable parents falsely satisfied the oracle.
New main methods have no false satisfaction within the recorded oracle. All four
have 80 semantic incomplete stops, split into 75 known and five uncertain; the
five uncertain cases are not promoted to known safe success or zero cost.
The old parent field `correct_abstention` also marked 32 solvable arm-parent
groups. Its original meaning is preserved; new fields explicitly require task
solvability rather than inheriting that ambiguous name.

Completion and false-satisfaction results are unchanged. On 132 compatible
solvable parents, old/new EGR primary completion remains 99/132 to 132/132;
false satisfaction remains 9/220 to 0/220. New all-task primary completion remains
EGR 145/145, fixed 142/145, verify-first 143/145 and random 145/145. Unsupported
old API rows, failed attempts and unknown costs stay in their recorded categories.

## Reproduction and limits

After downloading and safely extracting the original archive, run from the source:

```sh
python -m benchmarks.erratum_021 ORIGINAL_DIRECTORY --archive benchmark-raw-v0.2.1.zip --output NEW_ERRATUM.json
```

The output must not exist. Bundle byte changes, a wrong archive or a primary-table
reconstruction mismatch are errors. Nineteen regressions passed, including label
equivalence, actual pending receipts, uncertainty, solved-task exclusion and
identity-sensitive trace comparison.

This analysis reuses the recorded independent oracle and task-solvability labels;
it is not an independent rerun of all tasks or new external-validity evidence.
Old CPU/time retains different loops, tracing, cold imports and shared setup, so
it cannot be interpreted as pure ranking cost. The method baselines share EGR's
feasibility/necessity/helper mechanisms; they assess incremental selection value,
not the complete stack against an independent scheduler. Zero observed errors
do not establish risk zero, and the synthetic families do not represent random
samples of real workloads.
