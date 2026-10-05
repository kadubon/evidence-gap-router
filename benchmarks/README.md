# Finite CPU engineering experiment

Q1 asks about correct acceptance and continuation, Q2 compares scheduling methods,
and Q3 measures control overhead. These are distinct questions. The old nine-case
comparison remains its limited demo. This harness uses the public typed records,
callbacks, `plan`, `start`, `observe`, `run` and common `feasible_actions`; it does
not replace the runtime, bypass issuance or use its acceptance predicates as truth.

`protocol.json` fixes eight families, material and budget arithmetic, checker and
candidate recipes, development/holdout seeds, variants, random repetitions, caps,
oracle and task-cluster bootstrap. `tasks.py` generates 30 distinct content/budget/
dependency tasks per holdout family, 240 parents. Reversed order and renamed
candidate IDs, and random seeds, are repeated variants of those same parents.
Actual raw numeric/file checks create receipts; the oracle independently checks
the world condition and receipt target/contract/dependency/checker/purpose bindings.
Initialization uses actual callbacks and its cost is reported separately.
Raw mathematical/file validity and bound-aware solvability are distinct labels;
solvability follows explicit attainable callback recipes. Receipt-backed completion
also requires every distinct active required target to be validated. Positive aliases
collapse without granting authority to resolve a negative check on another exact ID.
These finite recipes have acyclic verified dependencies; arbitrary negative cyclic
authority is tested by runtime regressions, beyond this oracle's domain.

Development only, with the current source environment:

```sh
uv run --locked python -m benchmarks.harness run --phase development --output EXTERNAL/dev.jsonl
uv run --locked python -m benchmarks.aggregate EXTERNAL/dev.jsonl --output EXTERNAL/dev-report
```

Holdout must wait until the runtime/checker/generator are frozen and committed.
Install the official baseline wheel (SHA in protocol) and the exact candidate
wheel into separate ordinary noneditable environments with matching Python,
Pydantic and core versions. Run from this repository's benchmark code with each
clean interpreter; `src/` is not a Python path. Record freeze once:

```sh
NEW_PYTHON -m benchmarks.harness freeze --output EXTERNAL/freeze.json --implementation-commit COMMIT --wheel CANDIDATE_WHEEL --baseline-wheel OFFICIAL_020_WHEEL
NEW_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --output EXTERNAL/methods.jsonl
OLD_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --version-only --output EXTERNAL/old-version.jsonl
NEW_PYTHON -m benchmarks.aggregate EXTERNAL/methods.jsonl EXTERNAL/old-version.jsonl --output EXTERNAL/report
```

The complete holdout refuses partial task limits, a changed manifest/harness,
changed candidate/baseline wheel, mismatched Python/OS/architecture/dependencies or
source import. It compares installed package files byte-for-byte against the declared
wheel and records a canonical package-content fingerprint for a later docs-only build.
Never replace existing freeze/results.
An old API not present is an explicit unsupported row, not a fabricated outcome.
Changes after seeing holdout require a new protocol and unused seed with the old
evidence retained. This is repository experiment freezing, not external registration.
Each method/variant/seed uses the same bounded isolated worker. Whole-worker deadlines
include startup/import/serialization; these isolation costs are recorded separately
from trial CPU/end-to-end time. Experiment caps leave unexecuted rows explicit.
Timeout/exception rows have unknown oracle or costs where unavailable, and remain
failed compatible attempts rather than becoming correct abstentions or observed zeros.

Scaling separates normal timings from diagnostic call instrumentation:

```sh
NEW_PYTHON -m benchmarks.scaling run --python NEW_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-new.jsonl
NEW_PYTHON -m benchmarks.scaling run --python OLD_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-old.jsonl
NEW_PYTHON -m benchmarks.scaling summarize EXTERNAL/scaling-new.jsonl EXTERNAL/scaling-old.jsonl --output EXTERNAL/scaling-report
```

Graphs are chain/diamond/branches/cycle, sizes 4/8/16/32/64, 1/2/3 checkers. Small
timings have one warmup and ten repeats; large timings are explicitly one repeat.
Each measurement is a bounded separate process. New actual base-check and worklist
check/target operations use `_base_check`, `_evaluate_check_truth` and
`_evaluate_target_truth`; `_compute_check` counts final memo lookups separately.
Old recursive visits use `_trusted_check`.
Those are explicitly different diagnostic labels, not a claim of identical units.
Public plan timings include evaluation/index construction. Input construction,
serialization/loading and process end-to-end are separate from plan time. Peak traced
Python allocations have their own replay; they are not resident memory measurements.
Whole-worker timeouts retain their cutoff with unknown phase, and do not become plan
time lower bounds, exact seconds, infinity or deleted rows. The independent scaling
reference covers identical parents across checkers and pure ungrounded cycles; general
grounded alternative and negative cyclic semantics belong to runtime regressions.

`aggregate.py` produces CSV, JSON tables, English report and Japanese summary.
Primary completion is integer original-task n/N (random seed 17), alongside cluster
means across attempted variants/seeds. Compatible errors/timeouts count as failures.
All compatible attempted parents are the false-satisfied denominator, with unknown
assessments counted explicitly. Requested, unsupported and unexecuted rows are
separate. Random/ordering repetitions are averaged within parent before
paired bootstrap. All-task costs and the selected both-success cost subset are
separate. Matched old/new EGR version pairs are distinct from within-version method
pairs. F6/F8 direct pipelines actually read/parse raw materials and skip routed
initialization; their read/validation counts and differing batching, receipt and
resource-bound contract are explicit separate references, excluded from primary tables.
Common `World`/SDK State/Policy/material setup remains in their CPU/end-to-end costs;
an ordinary minimal pipeline can be cheaper than this shared harness reference.

Native smoke copies only this small code package outside the checkout and runs
`python -I ABSOLUTE/benchmarks/smoke.py` with the installed wheel. It uses the same
development generator/oracle, exact-ID multi-stage helpers, alias resolution,
real invalidation/re-resolution history, initial completion, precise real files,
snapshots and four graph references: 11 parents, 33 method trials.
Its digest excludes CPU timings, paths and other machine-specific values.

Raw JSONL traces retain identifiers, raw-content digests, issued bases, receipts,
states, stops, costs, exceptions, timeouts, versions/wheel/manifest/commit and
environment. Large measured results belong in Release artifacts, not the wheel.
These model-free synthetic tasks do not establish LLM accuracy, independence,
money savings, capability growth, intelligence phases or risk zero.
