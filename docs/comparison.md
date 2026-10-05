# Archived v0.2.0 limited comparison

The nine conditions below and their raw records are retained from v0.2.0. Its
fixed-order baseline deliberately permits redundant verification and is a
limited demonstration. New routing or performance claims use the independent
oracle, strong feasible baselines and parent-task holdout in the
[v0.2.1 benchmark](benchmark.md), rather than this table alone.

The [raw results](comparison-results.json) retain all nine runs, identical initial
snapshots, evidence/bases, seed checker work, budgets, actual action trace,
verification counts, stops and satisfied/required/unresolved counts. The experiment
uses artificial material, ordinary callbacks and the same real checker in both arms.

Reproduce from the installed package (no model or API key):

```sh
python -m evidence_gap_router.comparison
```

The baseline follows the declared order among feasible actions and permits a
redundant content recheck; the router chooses target-specific gaps. Permission,
applicability and resource constraints apply to both. Current-run counters and
budgets start from the same prebuilt snapshot; seed checks are shown separately
in the raw records rather than claimed free or hidden. The dependency case
expires previously checked rules, reacquires material and reruns the affected checks.

Each case also reverses candidate order and renames candidates. No variant is
omitted. Numbers below are **callback calls / verifications**, followed by domain
stop and satisfied/required coverage; unresolved count is denominator minus numerator.

| Case | Variant | Baseline calls/checks | Baseline stop/coverage | Router calls/checks | Router stop/coverage |
| --- | --- | --- | --- | --- | --- |
| A04_recheck | declared | 1 / 1 | budget_exhausted 0/1 | 1 / 1 | satisfied 1/1 |
| A04_recheck | reversed | 1 / 1 | satisfied 1/1 | 1 / 1 | satisfied 1/1 |
| A04_recheck | renamed | 1 / 1 | budget_exhausted 0/1 | 1 / 1 | satisfied 1/1 |
| A05_provenance | declared | 2 / 0 | budget_exhausted 0/1 | 2 / 1 | satisfied 1/1 |
| A05_provenance | reversed | 2 / 1 | satisfied 1/1 | 2 / 1 | satisfied 1/1 |
| A05_provenance | renamed | 2 / 0 | budget_exhausted 0/1 | 2 / 1 | satisfied 1/1 |
| dependency_recheck | declared | 3 / 2 | satisfied 2/2 | 3 / 2 | satisfied 2/2 |
| dependency_recheck | reversed | 3 / 2 | satisfied 2/2 | 3 / 2 | satisfied 2/2 |
| dependency_recheck | renamed | 3 / 2 | satisfied 2/2 | 3 / 2 | satisfied 2/2 |

In the declared A04 order the baseline spends the limited check on an already
accepted target while the router checks the missing target. In declared A05 the
router uses the two-call budget to get new declared provenance and check it;
the baseline's repeated origin consumes that opportunity. Reversed orders in
those cases remove the advantage: both satisfy the declaration at the same cost.
All three dependency-recheck variants are equal in calls and verification use.

This establishes only these observed finite outcomes. The comparison does not
estimate statistical independence, general cost savings, AI accuracy, causal
capability formation, collective intelligence or performance under other workloads.
The baseline order sensitivity and equal-result variants are part of the result.
