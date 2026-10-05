# v0.2.1 audit and v0.2.2 correction map

Baseline: tag `v0.2.1`, commit
`3e6a547dd38af9668115aaad9d9d30129c018c1b`, official wheel SHA256
`61129ec160c6c9d718f5173fa0281cdcc735cfdc9222138f45584a6b71202917`.
The original 260 source tests passed before changes. New formal installed-version
audit/measurement results are recorded separately after execution; this map
describes the defects, implemented contracts and regression assertions.

| Audit item | Cause and correction | Meaningful regressions | Boundary |
| --- | --- | --- | --- |
| EGR021-01, candidate helper revisits | Path-local cycle detection repeatedly explored shared alternatives. An indexed finite AND/OR worklist shares current-evaluation subproblems, preserves compatible alternatives/required checkers, separates grounded exits from ungrounded cycles, and short-circuits known global stops. | `tests/test_v022_helpers.py`: alternative sets, exact issuance, structural visits, independent small reference/permutations, grounded exits, required checkers, changed state/policy/budget; `tests/test_helper_scaling_022.py`: separate timing/count/memory and reference scope. | Candidate reachability is distinct from existing checked-proof evaluation. Counts are method-specific diagnostics; finite input alone is no general time/memory guarantee. Larger helper inputs remain independently unassessed. |
| EGR021-02, partial contradiction-resolution basis | Issuance required related IDs but reuse could accept a matching fingerprint without them. One subject condition now requires an exact related target and every related ID in target/dependencies, alongside current bindings, authority and purpose. | `tests/test_v022_resolution.py`: ordinary imported partial/full basis, aliases, owner/scope/digest/contract/permission, old resolution history, actual acquisition/re-resolution, invalidation, serialization, contract change and delayed receipt. | Readable inappropriate old history remains retained but inapplicable. Missing inputs/work/cost are not invented. Host authenticity and hidden Python reads remain outside mechanical acceptance. |
| EGR021-03, loop/label artifact | EGR replanned empty receipts while manual baseline loops stopped early; old aggregation required one label. All methods now use public `run` with only a pure selector differing, preserving full pools and identical execution/stops. | `tests/test_v022_selector.py`: full helper pool, invalid selector, global stop, max steps, empty known/unknown receipts, paid faults/pending/limits; `tests/test_benchmark_loop_022.py`: ten F7 parents, actual public-run use and trace equivalence, solvable-stop exclusion, normal uninstrumented timing. | Shared eligibility includes gap/necessity/helper logic. Comparisons assess incremental ordering under that mechanism, not an independent scheduler or general EGR advantage. |

The [raw erratum](benchmark-v0.2.1-erratum.md) reconstructs all published primary
overall/family/budget counts from 5,400 original records. The old 80/95 versus
70/95 stop-label difference is fully explained by ten F7 parents with identical
semantic records. Corrected main methods each have 75 known, five uncertain and
15 fault outcomes among 95 unsolvable parents. Completion/false-satisfaction
observations remain intact; old timing is not reinterpreted as pure ordering cost.

A separate pre-freeze diagnostic used the official ordinary-installed 0.2.1
wheel and exact archived LF harness to run those ten observed F7 parents across
four methods, original order/seed17. All 40 trials completed, preserving unknown
verification costs in mode4, with ten equal parent signatures and successful
snapshot roundtrips. Its new raw SHA256 is
`3d13813e997d95b556001692bb2dc9b6d98b52fbf1c4c06e62973b0c37fdb9bd`.
This diagnostic is separate from raw reaggregation and the new formal experiment;
it is not an unseen confirmation set or performance estimate.

Keep worker status, runner stop, domain stop and independent oracle outcome
separate. Known safe abstention requires assessed non-solvability and known
bounded use/effects with no pending invocation. Unknown use/effects, faults and
erroneous stops on solvable work have distinct output fields. A correct escalation
does not make unknown execution known. Existing EGR020-01 through EGR020-09
regressions remain in the source/installed suites; tests are not deleted or
skipped to produce success. See [validation](validation.md), [API](api.md),
[migration](migration.md), [design](design.md) and [security](../SECURITY.md).
