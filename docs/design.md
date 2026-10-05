# Design and trust boundaries

## Small responsibility

The host declares obligations, acceptance contracts, finite action candidates,
handler permissions and resource limits. The router derives target-specific gaps
and recommends at most one eligible action. The explicit local runner calls a
registered Python function and replans from its receipt. It does not discover all
requirements, grant execution rights or implement a new agent framework.

State remains strict, typed, frozen and single-writer. `plan` is pure; `start`
pins an issued attempt; `observe` validates its receipt and host permissions.
`step`/`run` add a finite host loop and immutable input disclosure views without
changing that separation. Factory and callback failures preserve the latest state.
Snapshot continuation is explicit, with no crash-safe exactly-once claim.

## Mechanical acceptance and actual used material

An obligation's fingerprint includes ID, scope, contract revision, acceptance,
minimum evidence/provenance groups and required verifiers. Description, priority
and required status are display/selection fields and do not change that check
contract. String hashes are mechanical bindings, not semantic interpretation.

A `VerificationBasis` identifies the target evidence ID/digest/obligation/scope,
current acceptance fingerprint, finite dependency bindings, checker revision and
purpose. Issuance fixes these values; the callback receives that material in its
view and its receipt must echo the basis. Cross-obligation dependencies explicitly
name the owner/scope and required condition (`exists`, `active`, `verified`).
Presence does not imply active or checked. Finite cyclic verification dependencies
are rejected/blocked rather than scheduled through a general graph runtime.
`exists` allows explicit historical inspection; a PASS used for current acceptance
still requires every referenced target/dependency to be active and contract-matching.
`verified` evaluates the referenced target's required checkers, rather than requiring
the whole dependency obligation to have complete evidence/provenance coverage.

Only material actually declared and used is bound: unrelated additions leave
applicable checks reusable. A changed contract, replaced target or inapplicable
used dependency does not reuse the old PASS. Expiry/withdrawal are explicit host
flags; there is no hidden wall-clock change. The raw record and history remain.
The host/checker is trusted to use the declared material; hidden Python reads,
external checker dishonesty and authenticity are not detected.

## Permission and historical resolution

Host registrations fix allowed action roles, checker ID/revision and purpose.
`Policy.available_handlers` optionally restricts current execution availability;
it does not alter registered checker trust or invalidate an earlier applicable
check just because its Python callback is absent. The runner intersects its
explicit callback mapping with host execution restrictions. An empty intersection
permits no execution rather than broadening the allowlist.
The core distinguishes content verification, negative-check resolution and
contradiction resolution. A collected result cannot grant itself checker power,
replace FAIL/UNKNOWN with an arbitrary old PASS or resolve a contradiction.
Resolution binds the actual record fingerprint, involved evidence and current
contract, and requires matching authorized basis. Generic content PASS is
insufficient. Matching authorized resolution evidence may be reused; identical
receipt replay charges no second cost. Earlier records are never silently erased.

Schema 2 expresses these meanings. Schema-1 migration preserves the strict old
snapshot and historical records but leaves unsupported old check bases legacy/
unassessed; it does not infer contracts or dependencies. The host must declare
current contracts and reconcile pending execution before new work.

## Gaps, capacity and separate costs

Eligibility checks target, dependency applicability, prerequisites, registration,
previous attempt IDs and resource bounds before ranking. Required status and
priority lead, followed by the specific missing target/checker/purpose or an
explicit material prerequisite; stable IDs resolve otherwise comparable ties.
Current satisfied content targets are excluded from redundant rechecks by default.
Provenance fit separates known repetition, unknown origin and declared new
source/group material. Same-source/group bridges collapse transitively; source
names and groups do not prove statistical independence.
Positive evidence/provenance deduplication does not suppress a duplicate alias's
applicable FAIL or UNKNOWN. Such records remain blocking and expose a resolution
gap for the exact alias target; a PASS on another alias does not silently erase them.

Pending capacity counts unfilled required target/checker work, including a
partial required-verifier PASS and UNKNOWN, while retaining FAIL as a distinct
negative result. Explicit prerequisite acquisition can unblock a pending check
within the declared finite pool; arbitrary acquisition cannot bypass backpressure.
Decisions expose typed gaps, selected gap, pending count, residuals and exclusions.

Action, verification and optional token counts remain separate nonnegative
integers. Bounds/estimates are distinct from actual observations. Unknown demand
in a constrained dimension is not zero. Unknown budgeted/bounded actual use,
overrun or uncertain side effects prevents safe automatic continuation.

## Neighbors and research

The following source contracts were read; their main revisions were rechecked on
2026-10-05 and unchanged. They are references, not dependencies or qualified adapters.

| Reference | Observed responsibility | Boundary here |
| --- | --- | --- |
| [CCR workcells](https://github.com/kadubon/collective-capability-runtime/blob/d6806b158ffb9ff76937c6c3eb3f9391a1fcf21a/docs/collective-workcells.md) | Staged contributions, provenance deduplication, verified residual resolution, runtime leases/fencing. | Finite recommendations and local receipts; no CCR coordination service or adapter. |
| [VEK model](https://github.com/kadubon/verification-ecology-kit/blob/4008e311ceb16edd6e74d9f71341a90120c0d046/docs/data_model.md) | Structured verification records, non-erasing residual history, explicit authority and bounded formal VET-Core. | Bound host check applicability; no VEK conformance or formal proof. |
| [CIO lifecycle](https://github.com/kadubon/collective-intelligence-overlay/blob/46276b4080dadd70ffa2608533139e8df6dcf75d/docs/lifecycle-reference.md) | Read-only lifecycle observations distinguish exact identity, costs, unknowns and receiver assessment. | Action selection; no lifecycle admission, transport or schema compatibility claim. |

The [research index](https://kadubon.github.io/github.io/collective-intelligence-index.html)
distinguishes interaction, checked reusable capability and stronger acceleration
claims. Preserving residuals and authority boundaries follows those cautions.
This implementation does not establish a complete theory, novelty, general cost
reduction, collective-intelligence gain or causal capability growth. Numerical
research claims are not used as product evidence. The small matched comparison
records synthetic observed calls/outcomes, including equal-result cases.

## Not implemented

No server, database, scheduler, lease, reservation service, authentication system,
cryptographic signing, model gateway, framework adapter suite, GUI, telemetry,
learning, optimizer, semantic truth/contradiction detector or automatic plugin
loading is included. References are data, never automatic fetches. Host access
control, credentials, external effects, strong isolation, measurement, timeouts
and concurrency remain outside the router. Limited views are not a sandbox.
