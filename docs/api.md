# SDK operations in 0.2.1

The existing `plan`, `start`, `observe`, `resolve`, `step` and `run` signatures
remain available. Planning is pure. The host controls declarations, registrations,
callbacks, execution effects and measurements; a snapshot is not authenticated.

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
in declaration order, applying common execution/acceptance safety gates without
the gap/provenance ordering of `plan`. It consumes no work and grants no new
authority. This small shared operation supports explicit host selection and
fair benchmark baselines; hosts still issue and observe the actual invocation.

## Bounded serialization and numbers

`dump_json(model) -> str`, `load_json(text, model_type)`, `read_json(path, model_type)`
and `write_json(model, path) -> None` reject unknown fields/versions, duplicate
keys and out-of-bound input. State/schema-1 snapshots have a 32 MiB limit;
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
