# Finite v0.2.2 engineering experiment

Correct acceptance/continuation, method ordering and controller cost are separate
questions. The small original comparison remains a limited demo. These scripts
use ordinary installed SDKs and actual public issued callbacks; independent raw
material/receipt oracles do not call the router's private acceptance predicates.

The current `protocol.json` fixes the v0.2.2 experiment before observation.
The immutable `protocol-v0.2.1.json`, versioned reports/results and official old
raw archive preserve the prior experiment. Its stopping-label correction is
in [the erratum](../docs/benchmark-v0.2.1-erratum.md); recorded old CPU values are
not reused as pure ranking cost.

## Requested keys and contracts

The controller enumerates **1,680 worker keys** before execution:

- B: 240 observed parents, original order, four methods: 960 trials; random seed17.
  Sixty F6/F8 direct-pipeline references are separate.
- A: two installed-version audit workers, 14 explicit property cases each.
- C proof: 60 graph/size/checker inputs, two versions, three modes: 360 workers.
- C helper: 39 candidate-graph inputs, two versions, three modes: 234 workers.
- New confirmation: 32 unused-seed graph/update conditions, two versions: 64 workers.

These are requested keys, not executed-success claims. The old 240 parents are a
regression set, not unseen holdout. Seed49979687 fixes new confirmation separately.
No intervals are fabricated for unexecuted old order/seed variants.

EGR, fixed-feasible, verify-first and random-feasible use the same public finite
`run`; only the pure selector changes. Complete pools, input disclosure, issuance,
permission/resource checks, receipt/errors, progress and replanning are common.
Eligibility includes unmet-gap/necessity and helper evaluation as well as safety.
This measures additional ordering value conditional on that mechanism, not the
complete EGR stack against an independent scheduler.

Raw validity and within-budget solvability are separate. Receipt-backed completion
requires every distinct active required target to be checked. Positive aliases do
not resolve a negative on another exact ID. The method oracle uses finite
acyclic/grounded declared recipes; arbitrary negative cyclic authority belongs to
runtime regressions. Direct references read/parse material but have a different
batching/receipt/bound contract, so do not enter primary method tables. Shared
World/State/Policy/material setup remains measured; a minimal pipeline may be cheaper.

## Freeze and one serial controller

Finish development, record the implementation commit and build its LF archive
candidate before freeze. Install the official **0.2.1** baseline wheel
(`61129ec160c6c9d718f5173fa0281cdcc735cfdc9222138f45584a6b71202917`)
and candidate in separate ordinary noneditable environments. Match Python,
OS/architecture and all runtime dependencies. Run from an external copy of the
committed benchmark code, without adding `src/` to imports:

```sh
NEW_PYTHON -m benchmarks.harness freeze --output EXTERNAL/freeze-v0.2.2.json --implementation-commit COMMIT --wheel CANDIDATE_WHEEL --baseline-wheel OFFICIAL_021_WHEEL --host-record EXTERNAL/host-record.json
NEW_PYTHON -m benchmarks.controller_022 run --freeze EXTERNAL/freeze-v0.2.2.json --output EXTERNAL/formal --old-python OLD_PYTHON --new-python NEW_PYTHON
NEW_PYTHON -m benchmarks.summarize_022 --input EXTERNAL/formal/raw.jsonl --output EXTERNAL/controller-summary.json --report-en EXTERNAL/controller-report.md --report-ja EXTERNAL/controller-report.ja.md
```

Output directories must be new. Freeze validates installed bytes against the
candidate wheel and records wheel, package, harness, protocol, commit and environment.
Workers revalidate them. A later docs-only wheel must retain the measured package,
harness and protocol identities. The release gate uses
`benchmarks/results/freeze-v0.2.2.json`; old `freeze.json` stays unchanged.
Changes after confirmation require a new protocol/unused seed with old evidence
retained. This is repository freezing, not external registration.

The Windows controller launches serial owned workers in a private Job, with
10-second whole-worker wall, 8-second cumulative Job CPU and 256MiB peak aggregate
private committed byte limits. The separate parent cap is 512MiB peak working
set. Overall limits are 7,200 wall and 3,600 CPU seconds, with declared phase caps.
Job accounting includes venv descendants; sampled crossing can overshoot.
Private committed bytes, working set and traced Python allocations are different
metrics. Missing accounting stops dependent work instead of assuming zero.
Do not run tests, writing or heavy experiments alongside formal timing.

Whole-worker limits include startup/import/construction/serialization and retain
timeout/resource-limit/unexecuted keys with unknown outcomes/costs as appropriate.
They are not exact plan times or plan-only lower bounds. Worker status, runner stop,
domain stop and independent oracle outcome stay separate. Known correct abstention
requires unsolvable, assessed incomplete, meaningful domain halt, known constrained
use/effects and no pending invocation. Uncertainty and execution faults are separate.

## Aggregation and controller costs

Extract only method rows into a new JSONL, then run the method aggregate:

```python
import json
from pathlib import Path

source = Path("EXTERNAL/formal/raw.jsonl")
with Path("EXTERNAL/methods.jsonl").open("x", encoding="utf-8") as output:
    for line in source.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["spec"]["kind"] == "method":
            output.write(line + "\n")
```

```sh
NEW_PYTHON -m benchmarks.aggregate EXTERNAL/methods.jsonl --output EXTERNAL/method-report
```

Primary completion is integer original-parent n/N; false satisfaction uses all
compatible attempted parents with unassessed outcomes explicit. Failures/timeouts
remain failed repetitions; unsupported/unexecuted counts stay separate.
Task-paired differences do not inflate rows into independent samples. All-task
success/failure costs and selected both-success costs are separate. Delay
break-even is assumption-based sensitivity, not tokens, money or commercial ROI.

Recorded proof graphs and unacquired helper candidates are separate C families.
Normal timing has no profile/tracemalloc. Time, method-specific structural visits
and a traced-allocation replay use separate processes. Warm timing has one warmup
and ten repeats. Input/candidate construction, real initialization, serialization/
load, plan, start/observe and binding-progress costs are identified where applicable.
Small helpers have an independent public-field scanning AND/OR reference with the
consuming root blocked; larger inputs remain unassessed. Old recursive entries and
new rule/edge work are not identical units.

## Portable native smoke and retained evidence

Native CI copies the small benchmark code outside the checkout and runs
`python -I ABSOLUTE/benchmarks/smoke.py` against the installed wheel. It uses the
same generator/oracles, 11 development parents across four methods (**44 trials**),
four proof references and three helper-reference cells. Critical runtime
regressions execute against that wheel. Full timed confirmation stays on one
explicit local host. Configured runner labels alone do not prove native work.
The portable outcome digest excludes timing, paths and machine-specific values.

Raw JSONL/CSV retain material digests, exact inputs, issued bases, receipts, state,
stops, known/unknown costs, faults, censoring, wheel/manifest/commit and environment.
Large evidence belongs in Release assets, not the wheel. These finite CPU-only
tasks do not establish general LLM accuracy, source independence, money savings,
capability growth or risk zero. Predetermined work may need only a fixed pipeline.
