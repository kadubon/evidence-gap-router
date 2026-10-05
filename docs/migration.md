# Migrating from 0.1 to 0.2

## 0.2.1 to 0.2.2

Schema remains **2** and existing calls remain available. `step` and `run` add an
optional keyword-only `selector(state, full_pool, eligible) -> ActionCandidate`.
Omitting it preserves default routing. A custom selector returns an unchanged
eligible candidate; all execution, receipt, progress, replanning and stop rules
remain those of the public runner. Replace hand-written method loops with this
selection point when comparing ordering. Keep the complete candidate pool, even
when only one action is selected. See [the exact contract](api.md).

`feasible_actions` includes unmet-gap/necessity and helper eligibility, as well as
safety/permission/resource checks. Its output order is unchanged declaration
order, not EGR ranking. Interpret comparisons built on it as additional selection
value conditional on the common mechanism.

A contradiction-resolution PASS must bind every exact related evidence ID in
its target/dependencies, and its target must be one of those IDs. Issued, imported,
reused and reloaded records now undergo the same subject condition. A digest
alias or resolution fingerprint cannot substitute for omitted input disclosure.
Structurally valid old snapshots retain inappropriate checks, supersessions,
FAIL/UNKNOWN, receipts and costs, but those old grounds are inapplicable. A task
previously reported satisfied from such grounds may reopen. Declare the missing
inputs and perform an authorized new check/resolution; do not edit the old basis
or infer that material was checked. Valid full-input imported bases remain usable,
and unrelated additions need not invalidate them.

The indexed finite helper worklist replaces repeated candidate-path enumeration;
its cache is confined to a current evaluation. This changes neither permissions
nor the obligation to record actual callback work. The candidate helper graph is
separate from the checked-proof graph optimized in 0.2.1.

The [v0.2.1 erratum](benchmark-v0.2.1-erratum.md) preserves original raw files and
corrects a stop-label artifact without retiming old trials. Worker faults, runner
stops, domain stops, oracle completion and unknown use/effects are separate fields.
Do not migrate the old `correct_abstention` flag into a claim of known safe
abstention. New common-loop measurements are a separate experiment.

## 0.2.0 to 0.2.1

The SDK/CLI entry points and schema **2** remain. A legitimate old schema-2
snapshot within the current documented JSON size/numeric/depth bounds is
readable without a new basis being invented. The new optional
`State.invalidations` tuple holds exact host evidence/check invalidations;
new snapshots include it, so 0.2.0 readers reject the unknown field. Keep the
original file and upgrade the reader before continuing.

Historical resolution records on a byte-identical different evidence ID remain
history, but cease to be current acceptance grounds. A legacy negative without
a recorded exact subject basis needs explicit host assessment/new supported work;
the importer does not guess its subject. Reopened checks/contradictions may use
new dedicated current grounds while preserving original receipts and events.

Use `invalidate` rather than editing callback-produced expiry/withdrawal flags.
Use `write_json`/`read_json(..., State)` for the separate 32 MiB snapshot contract;
offline plan input and selected files remain 1 MiB. Data-rule JSON numeric text
is now exact and bounded; an already rounded Python float cannot be repaired.
See [SDK contracts](api.md) for new operations and limitations.

## 0.1 to 0.2

Version 0.2.0 uses JSON schema **2** and changes callback, verification and
registration contracts. It is not completely backward compatible. A schema-2
reader rejects schema 1; changing only the version field is not a migration.

## Preserve the old snapshot

```python
from pathlib import Path
from evidence_gap_router import dump_json, migrate_v1_file

state = migrate_v1_file(Path("old-state.json"))
Path("migrated-state.json").write_text(dump_json(state), encoding="utf-8")
```

The importer uses the strict original schema-1 validator and keeps its original
snapshot in `legacy_schema1`, along with migrated evidence, historical checks,
results, supersessions, contradictions and incomplete attempts. Old checks are
legacy/unassessed because schema 1 lacks the acceptance contract, exact target
identity, used dependencies and checker purpose. No old PASS receives an
invented schema-2 basis; old FAIL/UNKNOWN and unresolved conflicts remain visible.
Pending execution is not assumed unperformed and is never automatically issued again.
Invalid or unsupported old input is rejected and the original file is unchanged.
The importer is a bounded snapshot conversion, not a generic migration engine.

The host must explicitly review the current obligation contracts, register actual
checkers and handlers, reconcile unknown execution effects, and issue the missing
schema-2 checks. Do not reset history or alter old receipt identities to obtain a
clean-looking state. A host-owned JSON snapshot remains host-owned material, not
an authenticated execution history.

## Change callback registration and inputs

The old callback shape was `(action, attempt_id, state) -> Result`, in the demo
host loop. The new public shape is `(view: CallbackView) -> Result`, used by
`step` or `run`. Acquisition receives only explicitly declared dependencies in
`view.inputs`; the bundled independent initial reads declare none. Verification
receives only the pinned target and declared dependencies. This disclosure rule
does not provide secret isolation within the host process.

```python
from evidence_gap_router import CallbackView, Resources


def checker(view: CallbackView):
    answer = int(view.inputs[0].content or "")
    check = view.check(
        status="PASS" if answer == 2 + 2 else "FAIL",
        reason="Compared the supplied answer with actual arithmetic",
    )
    return view.result(actual_resources=Resources(actions=1, verifications=1), checks=(check,))
```

Use the [complete runnable SDK example](../README.md#connect-a-callback) for the
state, finite candidates, host registration and invocation. A verify candidate
now declares `target_evidence_id`, `target_digest`, `checker_id`, checker revision
and purpose. `HandlerRegistration` fixes roles; `CheckerPermission` fixes allowed
checker revisions/purposes. `Policy.trusted_verifiers` remains a host trust filter.
Acquisition handlers cannot supersede checks or resolve contradictions.
`Policy.available_handlers` is an optional execution-availability filter, separate
from registered trust. The runner preserves host restrictions when intersecting
them with its callback mapping; an empty intersection allows no callback.
An applicable recorded check does not lose trust merely because the issuing
callback is unavailable for a new invocation.

`start` pins a `VerificationBasis` and registration, plus exact input bindings.
`observe(state, result, policy)` validates the receipt against them. For an
explicit prerequisite-acquisition exemption, `start(..., candidates=...)` uses
the same finite declared candidate pool as planning; the public runner does this.
Do not invent bases after execution or have a checker read arbitrary newer state.

Cross-obligation dependencies use `DependencyRequirement` with evidence ID,
obligation and scope; optionally bind digest and contract fingerprint. `exists`,
`active` and `verified` are distinct requirements. A verified dependency requires
currently applicable checks, not merely a historical PASS. Only the finite used
material is bound; unrelated new evidence does not invalidate every check.
`exists` can disclose historical material, but current acceptance still requires
all material in the check basis to be active and match its pinned contract.
`verified` means the referenced target meets its required checkers; it does not
substitute for whole-obligation evidence/provenance coverage.

Content verification, negative-check resolution and contradiction resolution use
separate purposes (`content`, `check_resolution`, `contradiction_resolution`).
Resolution must bind the actual record fingerprint, current contract and involved
material, and be allowed by the handler's checker permission. A generic old PASS
is insufficient. Reuse of a genuinely matching authorized basis is permitted;
receipt replay remains idempotent and does not charge twice.
Retained FAIL/UNKNOWN on a duplicate evidence alias still blocks acceptance and
requires resolution bound to that exact target. Deduplicated positive counts do
not merge away negative history.

Runner stops are separate from domain stops. Persist `report.state` and continue
explicitly; a finite step limit is not satisfaction or an instruction to retry
unknown effects. The runner defaults to 32 steps and avoids all existing IDs.
