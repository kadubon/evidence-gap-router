# Design and boundaries

## Problem and loop

The host declares required obligations and a finite set of investigation,
verification and diversification actions. The router exposes the current gaps,
selects at most one eligible action, and lets an explicit host callback produce
new evidence, checks and measured resource use. Replanning changes the next
action as those gaps change. The router does not discover every requirement.

`plan` is read-only. `start` records a host-issued attempt before a callback;
`observe` validates that result against its attempt and target. Frozen, strict
Pydantic records and versioned JSON snapshots are the public data interface.
The JSON format rejects extra fields, duplicate keys, nonfinite numbers, invalid
types and unsupported schema versions. Python APIs use tuples for record lists;
JSON naturally uses arrays. At least one required obligation must be declared.

## Policy and applicability

Host policy chooses executable handler IDs and trusted verifier IDs. Evidence
text is data; it cannot add authority or alter policy. Acceptance text describes
what a host checker must actually test. The router evaluates supplied records
against structural policy; it does not interpret arbitrary natural-language
acceptance conditions or verify that a declared source told the truth.

Evidence applies only to its declared obligation, scope and digest. Repeated
content/source groups count once within that target and scope. Unknown
provenance stays unknown. Distinct declared groups or producer/verifier IDs do
not prove real-world or statistical independence. A digest identifies supplied
content bytes; it does not establish authenticity or correctness.
Observed same-source/group bridges collapse transitively; conflicting provenance
groups declared for one source are a blocking residual for that obligation.

Checks distinguish PASS, FAIL, UNKNOWN and absence. Expiry is a host-supplied
flag; there is no implicit wall-clock expiry. Current acceptance needs
trusted PASS for the active evidence digests and required verifiers. Withdrawal,
supersession, scope mismatch and old digests remove current applicability while
retaining the records. A later PASS does not silently erase FAIL/UNKNOWN or a
blocking contradiction. Supersession records identify the replaced record and
reason; contradiction resolution additionally references a trusted matching
PASS. Contradictions are explicit relations, not detected semantic conflicts.

## Deterministic selection and resources

Eligibility is checked before ranking: target and scope, handler policy, previous
attempts, prerequisites, available resources and verification capacity. Every
excluded candidate retains its reasons. Remaining eligible actions are ordered
by required status, descending obligation priority, relevance to the current gap,
then stable action ID. Unverified evidence favors verification; missing evidence
favors investigation; provenance shortage favors diversification. This rule is
an explainable default, not an optimality claim.

Actions, verifications and optional tokens are separate nonnegative integer
dimensions. Candidate estimates and observed costs are distinct. Unknown demand
on a constrained dimension is not treated as free. Unknown actual consumption
in a budgeted or bounded dimension, uncertain callback effects or consumption
above the declared bound stops further
automatic work. Verification backpressure suppresses new acquisition when the
declared pending-check capacity is reached.

`satisfied` means the declared required conditions are currently met under this
policy. `budget_exhausted`, `blocked` and `escalation_required` preserve unresolved
work. Coverage includes numerator, denominator, scopes and policy; it is neither
a correctness probability nor an intelligence score.

## Responsibility relative to neighboring OSS

The following primary documentation was read on 2026-10-05. These are design
references, not runtime dependencies or interoperability qualifications.

| Reference and checked revision | Observed contract | This package's boundary |
| --- | --- | --- |
| [CCR workcells](https://github.com/kadubon/collective-capability-runtime/blob/d6806b158ffb9ff76937c6c3eb3f9391a1fcf21a/docs/collective-workcells.md) | Staged contributions, provenance-group deduplication, blocking contradictions and verified residual resolution; leases and fencing belong to its runtime. | Retain evidence, gaps and issued attempts in a single writer; provide no leases, worker scheduler or CCR adapter. |
| [VEK data model](https://github.com/kadubon/verification-ecology-kit/blob/4008e311ceb16edd6e74d9f71341a90120c0d046/docs/data_model.md) and [README](https://github.com/kadubon/verification-ecology-kit/blob/4008e311ceb16edd6e74d9f71341a90120c0d046/README.md) | Structured verification records, residual history, explicit authority and a bounded formal VET-Core claim. | Consume host checks with target binding; provide neither VEK conformance nor a formal proof. |
| [CIO lifecycle interface](https://github.com/kadubon/collective-intelligence-overlay/blob/46276b4080dadd70ffa2608533139e8df6dcf75d/docs/lifecycle-reference.md) | Finite read-only lifecycle views keep original identity, costs, unknowns and receiver-local assessment distinct; references do not fetch material. | Recommend the next declared action; do not assess CIO admission, transport records or claim schema compatibility. |

The [research index](https://kadubon.github.io/github.io/collective-intelligence-index.html)
distinguishes interaction, checked reusable capability and stronger acceleration
claims. It emphasizes observable completion, preserved unknown effects and finite
verification capacity. These boundaries motivate the design; this release has
no evidence establishing novelty, collective-intelligence improvement, causal
growth or cost savings. No numerical research result is used as a product claim.

## Assumptions and omissions

The trusted host supplies authentic verifier records, correct digests, policy,
measurements, declared source groups and a finite callback mapping. State has a
single process and writer. No core operation fetches references, imports handler
strings or invokes an LLM. The example host loop records callback exceptions and
invalid return values as uncertain attempts and never automatically retries them.

No agent framework, model gateway, server, database, distributed scheduler,
authentication system, lease, reservation service, GUI, telemetry, learning,
solver, semantic truth/contradiction detector or plugin discovery is implemented.
No exactly-once side effects or crash recovery is guaranteed. Execution,
timeouts, external credentials, authorization, concurrency and external resource
limits remain host responsibilities. Explicit retries need a new attempt ID and
budget; an uncertain effect needs host reconciliation first.
