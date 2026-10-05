# Design and trust boundaries

## Small responsibility

The host declares obligations, acceptance contracts, finite action candidates,
handler permissions and resource limits. The router derives target-specific gaps
and recommends at most one eligible action. The explicit local runner calls a
registered Python function and replans from its receipt. It does not discover all
requirements, grant execution rights or implement a new agent framework.

State remains strict, typed, frozen and single-writer. `plan` is pure; `start`
pins an issued attempt; `observe` validates its receipt and host permissions.
`invalidate` appends an explicit host event; `resolve` records checked current
resolution grounds. Neither operation rewrites a callback's original receipt.
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
cannot create authority from their own circular support. Applicability is evaluated
as described below; this is not a general graph execution runtime.
`exists` allows explicit historical inspection; a PASS used for current acceptance
still requires every referenced target/dependency to be active and contract-matching.
`verified` evaluates the referenced target's required checkers, rather than requiring
the whole dependency obligation to have complete evidence/provenance coverage.

Only material actually declared and used is bound: unrelated additions leave
applicable checks reusable. A changed contract, replaced target or inapplicable
used dependency does not reuse the old PASS. Initial expiry/withdrawal flags remain
explicit input information; there is no hidden wall-clock change. After a record
has appeared in a callback receipt, the host uses an append-only `Invalidation`
for its exact evidence/check ID, obligation and scope. The event has its own ID
and reason. Identical event replay is idempotent; unknown targets, mismatched
scope and conflicting reuse of an event ID are rejected. Callback results cannot
supply host invalidations. Original evidence, checks, attempts, receipts and
resource observations remain intact, and diagnostics identify excluded records.
The host/checker is trusted to use the declared material; hidden Python reads,
external checker dishonesty and authenticity are not detected.

## Current-state dependency evaluation

Each planning/feasibility/start assessment builds indexes for that immutable
state and host policy. There is no cache carried across calls, contracts,
invalidations or changes to checker authority. The evaluator first assesses
fixed identity, active material, contracts and checker permissions, then uses
a finite worklist for `verified` dependencies.

The worklist uses three-valued (strong-Kleene) logic: a check or target can be
established, excluded, or unresolved. Information advances from unresolved to
established/excluded. An independent currently authorized PASS on A can establish
A, then a check on B depending on verified A, and finally an optional A check
depending on B. A loop without such grounding cannot manufacture PASS. A
potential negative whose applicability remains unresolved also prevents coverage
from being reported as satisfied; it exposes a blocking `dependency_indeterminate`
residual and dependency gap. Expired, invalidated or unauthorized historical
checks with recorded bases do not poison a valid independent proof. Unassessed
legacy negatives retain their explicit host-review boundary.

Indexes and per-assessment memoization avoid recursively recomputing every
checker combination along a chain or diamond. The regression fixtures compare
against an independent small reference evaluator and bound worklist updates by
the recorded nodes/dependency edges. Those diagnostic counts are not a general
CPU speedup claim; uninstrumented timings and bounded process measurements are
separate engineering evidence.

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
insufficient. Check resolution also requires the exact subject evidence ID from
the original negative check's basis; equal bytes/digests under another ID do not
substitute for that subject. Old inappropriate alias-resolution records remain
readable history but are excluded from current acceptance. A basis-less legacy
negative needs explicit host assessment rather than an inferred subject ID.

Matching authorized resolution evidence may be reused. If earlier grounds become
inapplicable because of a changed contract or used material/check invalidation,
new dedicated current checks can support another append-only resolution event
for the same historical target. Identical event replay is idempotent; conflicting
reuse of its ID and an additional resolution while current grounds are already
active are rejected. Evidence replacement remains single-target replacement;
multiple historical check-resolution edges still undergo cycle validation.
Receipt replay charges no second cost. Earlier records are never silently erased.
Known producer/checker self-verification is excluded before issuance when host
policy prohibits it. Previously recorded callback costs are still retained.

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
`feasible_actions(state, candidates, budget, policy)` exposes the same safety
gates in the original finite pool order. It adds no EGR ranking, provenance
preference or randomized choice. A host may select any returned action and use
`start(..., candidates=original_pool)`; start checks the same helper context,
pending execution, resource bounds and required-satisfaction boundary.
Provenance fit separates known repetition, unknown origin and declared new
source/group material. Same-source/group bridges collapse transitively; source
names and groups do not prove statistical independence.
Positive evidence/provenance deduplication does not suppress a duplicate alias's
applicable FAIL or UNKNOWN. Such records remain blocking and expose a resolution
gap for the exact alias target; a PASS on another alias does not silently erase them.

Pending capacity counts unfilled required target/checker work, including a
partial required-verifier PASS and UNKNOWN, while retaining FAIL as a distinct
negative result. A satisfied or optional helper obligation may still need a
particular new evidence ID or its verification for an unresolved required check.
Only finite declared dependency paths grant that helper an exception to ordinary
obligation-satisfied/backpressure exclusions. The path must match exact IDs,
obligation/scope, current contract and any declared/observed digest, use allowed
handlers/checkers, and fit resource bounds. An unrelated acquisition, a wrong-scope
future verifier, an impossible prerequisite or a dependency cycle gets no such
exception. Multi-stage acquisition and verification use the same rules.

An unknown digest may prevent the host from declaring a concrete verifier action
before acquisition. Exact missing verified-dependency acquisition can bootstrap
the next factory result if the contract-required checker is already authorized
and available. This permits a bounded read, not an unissued verification or PASS.
Once material exists, its helper verification needs a concrete compatible action.
The runner evaluates a factory once for a callback's finite pool. New duplicate
content can count as binding progress only when it fulfils a needed exact input
binding; it does not increase deduplicated evidence/provenance counts. Fresh
unneeded alias IDs, attempt IDs and costs alone do not count as progress.
Decisions expose typed gaps, selected gap, pending count, residuals and exclusions.

Action, verification and optional token counts remain separate nonnegative
integers. Bounds/estimates are distinct from actual observations. Unknown demand
in a constrained dimension is not zero. Unknown budgeted/bounded actual use,
overrun or uncertain side effects prevents safe automatic continuation.

## Bounded JSON and local numerical input

Schema remains **2**. State snapshots (including strict schema-1 import/archive
content) have a separate 32 MiB byte bound. Offline `PlanInput`, other JSON models
and selected CSV/dictionary files retain their 1 MiB bounds. Writers enforce the
matching reader's byte, structural-depth and number limits before reporting a
successful save. `write_json` validates first and replaces a file through a
temporary file; failed validation leaves an existing file intact. This does not
claim crash-safe journaling or an unlimited history store. An expanded migration
that exceeds the archive-inclusive snapshot limit is rejected without dropping
history or overwriting its input.

JSON rejects duplicate keys, non-finite numbers and nesting beyond 64 levels.
Integers have at most 128 digits. Decimal numerical input has at most 64 coefficient
digits, an exponent/adjusted exponent within +/-128, and a 256-character numeric
text limit. Core integer resource fields remain strict: booleans, floating JSON
numbers and exponent notation cannot impersonate integer action counts.

The local data checker retains validated dictionary numeric text and parses
decimal-sensitive JSON before a binary-float conversion. CSV amount comparison
uses the same bounded decimal values. Small fractional boundaries and integers
around `2**53` therefore retain the supplied numeric meaning. A Python float supplied
by a caller has already lost any original digits; its existing representation is
accepted as such rather than claimed to be recovered. CSV input is read completely
or rejected, with a maximum 10,000 data rows and an explicit 131,072-character
field limit. These limits and evidence digests do not establish financial or
semantic correctness beyond the declared example contract.

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
research claims are not used as product evidence. The earlier small matched
comparison records synthetic observed calls/outcomes, including equal-result
cases. A separate engineering protocol distinguishes correctness, matched method
utility and controller CPU/memory costs; its [comparison record](comparison.md)
must state the executed environment, bounds and remaining measurements.

## Not implemented

No server, database, scheduler, lease, reservation service, authentication system,
cryptographic signing, model gateway, framework adapter suite, GUI, telemetry,
learning, optimizer, semantic truth/contradiction detector or automatic plugin
loading is included. References are data, never automatic fetches. Host access
control, credentials, external effects, strong isolation, measurement, timeouts
and concurrency remain outside the router. Limited views are not a sandbox.
