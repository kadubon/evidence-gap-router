# SDK operations in 0.2.2

The existing `plan`, `start`, `observe`, `resolve`, `step` and `run` signatures
remain available. Planning is pure. The host controls declarations, registrations,
callbacks, execution effects and measurements; a snapshot is not authenticated.

## One finite runner, optional pure selection

`step(state, candidates, budget, policy, handlers, *, selector=None)` invokes at
most one callback. `run(..., max_steps=32, selector=None)` uses the same issuance,
receipt, progress and replanning path with a finite callback limit. Existing calls
without a selector retain the default `plan` ordering.

An optional `ActionSelector` has the contract
`selector(state, full_pool, eligible) -> ActionCandidate`. Both pools are finite
tuples; `eligible` keeps declaration order. Return an unchanged member of that
tuple. The runner calls the selector only when there is eligible work. It retains
the complete pool for dependency/helper eligibility and passes it to issuance;
passing only the chosen action would lose that context.

For example, pass this function as `selector=first_eligible` to the complete
[callback example](../README.md#connect-a-callback):

```python
from evidence_gap_router import ActionCandidate, State


def first_eligible(
    state: State,
    full_pool: tuple[ActionCandidate, ...],
    eligible: tuple[ActionCandidate, ...],
) -> ActionCandidate:
    return eligible[0]
```

The host must keep selection pure: it chooses a candidate, rather than invoking
callbacks, changing policy, mutating material or measuring execution as a side
effect. Python does not enforce that purity or isolate the function. A selector
exception, altered candidate or ineligible return is a `planning_error` before
callback invocation. Handler availability, budget, target/dependency contracts,
issued-receipt validation, no-progress replanning and step limits remain common.
An empty receipt is assessed by the same replan path for every selection rule;
the runner returns `router_stopped` when no eligible action remains and
`no_progress` when eligible work remains without material progress.

Keep worker execution status, runner stop, domain decision and independent task
outcome separate. A timeout/exception is an execution fault, and unknown actual
use, effects or pending execution is an uncertain incomplete stop. Neither is a
known safe abstention merely because execution halted. A step limit is not a
forced wall/CPU timeout: the host supplies external process limits when needed.

## Host invalidation

```python
from evidence_gap_router import Invalidation, State, invalidate, read_json, write_json

event = Invalidation(
    id="host-expiry-1",
    kind="check",  # or "evidence"
    target_id="the-original-record-id",
    obligation_id="the-original-obligation-id",
    scope="the-original-scope",
    reason="Host confirmed that this check is no longer applicable",
)
state = invalidate(state, event)
write_json(state, "snapshot.json")
state = read_json("snapshot.json", State)
```

This fragment needs an existing host-owned `state` and its actual record IDs.
`invalidate(state, event) -> State` is an append-only host operation. Its target
must exist and match the declared obligation/scope. Original records, issued
receipts, FAIL/UNKNOWN and measured work remain unchanged. The target becomes
inapplicable; only checks that use it lose their current applicability. Other
valid checks remain reusable. There is no automatic clock, restoration event,
hidden retry or claim of authenticated host authority.

Identical event-ID replay returns the same state. An event-ID conflict or invalid
reference raises `ValueError`. Acquisition results have no invalidation field.
Do not modify a callback-created record's `expired`/`withdrawn` flag or receipt
payload: issued history continues to reject that mismatch. Seed flags remain
supported, and a pure invalidation needs no fabricated replacement evidence.

## Resolution and prerequisites

A check-resolution action and its PASS must use the exact evidence ID bound by
the negative check being resolved. Matching bytes/digest on a different alias
are insufficient. Old inappropriate alias-resolution history can be retained,
but cannot erase the original current negative result. A legacy check without
a recorded subject basis is not retroactively supplied one.

A contradiction-resolution basis must target one of the contradiction's exact
evidence IDs and include **every related ID** in its target/dependencies. Equal
digests under other IDs do not fill an omitted input. The same subject condition
applies to issuance, imported checks, explicit resolution and current acceptance
after loading. Each binding must still match its owner/scope/digest, current
contract and required applicability, with authorized checker revision/purpose.
A matching resolution fingerprint alone does not disclose the related material.
Old structurally readable checks/events with missing related inputs are retained
but cannot establish current resolution; no missing dependency or execution cost
is invented. Legitimate fully bound imported records remain supported.

`resolve(state, event, policy)` retains all resolution history. If an earlier
ground becomes inapplicable after contract/dependency/check invalidation, a new
currently applicable dedicated PASS may resolve the reopened issue. Identical
event replay is idempotent; duplicate grounds, simultaneous competing current
grounds and replacement cycles remain errors.

Satisfied or optional helper obligations do not grant unrestricted extra work.
The finite pool must declare material/checker work needed by an unresolved
required task, with matching exact IDs, scope, contract, permissions and bounds.
The same pool must be passed to `start(..., candidates=pool)`; `step`/`run` do this.
Known self-verification prohibited by policy is rejected before invocation.

`feasible_actions(state, candidates, budget, policy)` returns eligible candidates
in declaration order. Eligibility includes permissions, resources, current
acceptance gaps/necessity and exact finite helper paths; it is more than a security
filter. It excludes `plan`'s gap/provenance ranking, consumes no execution budget
and grants no new authority. Selecting among these candidates compares ordering
conditional on that common mechanism, rather than EGR against an independent
scheduler. Use the runner's selector to keep actual execution and stops common.

The helper candidate graph has an indexed finite AND/OR worklist, distinct from
the existing checked-proof worklist. Shared prerequisite subproblems are reused
within the current evaluation, preserving compatible alternatives and grounded
cycle exits. Memoization is not carried across state, contract, invalidation,
candidate pool, permission, availability or resource changes. Finite inputs do
not by themselves guarantee a particular wall time or memory footprint.

## Bounded serialization and numbers

`dump_json(model) -> str`, `load_json(text, model_type)`, `read_json(path, model_type)`
and `write_json(model, path) -> None` enforce bounded JSON syntax, duplicate-key
rejection and numeric limits. SDK record models additionally reject unknown
fields/versions; custom Pydantic models retain their own validation and
serialization settings. State/schema-1 snapshots have a 32 MiB limit;
offline `PlanInput` and individual local data/rules files keep their 1 MiB limit.
CSV has at most 10,000 rows and each field at most 131,072 characters.
Nesting is at most 64 levels and JSON integers at
most 128 digits. These are finite input contracts, not memory-use guarantees.

`write_json` validates readable complete output before writing a temporary file
beside the destination and replacing it. Validation failure preserves the prior
file. It does not create missing parent directories, provide a durable filesystem
transaction, preserve every old file attribute or coordinate concurrent writers.

Data-quality decimal thresholds and CSV amounts use at most 64 coefficient
digits, 256 numeric characters and exponent/adjusted exponent within ±128.
Decimal JSON is consumed before float conversion. `Rules.model_validate_json`
and the SDK JSON helpers preserve those exact numbers, and numeric serialization
keeps their meaning. `int`/`Decimal` SDK values are exact within these bounds;
an existing Python `float` is interpreted through its existing representation,
which cannot recover earlier lost digits. Booleans and nonfinite values are not
numbers in this contract. Evidence digests still hash complete original bytes.

Use the SDK snapshot helpers for the documented bounds. Direct Pydantic
construction/serialization is a lower-level model API and does not implement
the complete bounded snapshot-file contract.
