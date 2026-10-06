# Completion contracts in 0.3.0

`State`, `PlanInput` and `Decision` use schema **3**. Python entry points remain
`plan/start/observe/resolve/step/run`; every path uses the same pure current
`assess_completion(state, policy, budget=None)` result. It returns one
`CompletionAssessment` per obligation. `Decision.completion` exposes these in
SDK and offline CLI JSON. `coverage` and stop `satisfied` mean finite completion.
`observation_coverage`, `observation_residuals` and `observations_satisfied` report
the older evidence/check adequacy separately; they cannot authorize completion.

The host appends a `CompletionContract` with `declare_completion`. It names an
exact `DependencyRequirement` target, obligation fingerprint, scope and revision.
`declared_scope="finite_catalogue"` needs catalogue identity/revision and finite
`MaterialRequirement` conditions. All conditions are necessary; each `any_of`
contains explicit alternatives. Identity includes owner/scope and optional digest
and obligation-contract fingerprint. Unspecified or empty coverage cannot close.
`not_applicable` needs a reason and no retrieval conditions, for example fixed
arithmetic. The contract history records reasons for host scope changes; receipts
cannot revise it. IDs/revisions cannot be reused with different content.

Catalogue descriptors, raw State evidence, pinned issued inputs, completed
callback receipts and current target/check basis are different. A current check
must use each required material directly, or through a completed producer's
active exact input bindings. Acquisition alone never upgrades an M-only check.
Pending or undispatched inputs cannot prove usage. A valid current OR alternative
avoids unrelated reads. Invalidating used material reopens the relevant grounds;
unused records need no global recheck. The host/checker must actually use its
declared inputs; same-process Python views do not prove secrecy or honesty.

`CheckRequirement` names kind, optional qualified checker IDs, minimum distinct
checks and optional minimum declared correlation groups. `ActionCandidate`
declares `check_kind`; output cannot change the issued basis. `CheckerPermission`
defaults to advisory. The host explicitly lists `completion_kinds` and exact
`completion_scopes`, plus checker ID/revision/purposes. Optional method text is
descriptive. A captured issued permission and currently matching permission are
both necessary; late observations under revocation remain history with expenses.
Names in `trusted_verifiers`, handler separation or valid JSON are insufficient.
Unknown groups do not count and same-group aliases count once. Declared distinct
groups are not evidence of statistical independence. A legitimate fixed checker
can close a contract requiring one check; multiple agents are not mandatory.

Advisory FAIL/UNKNOWN remain visible. `advisory_negatives_block` explicitly
controls whether applicable advisory negatives block this contract. Closing
FAIL/UNKNOWN and blocking contradictions need current dedicated resolution;
generic PASS or majority vote cannot remove them. An unknown actual cost in any
resource dimension, pending calls and unknown effects cannot count as success.
Unbudgeted/unbounded dimensions are not measured by omission; new examples
record known zero model usage. No refund or automatic retry is provided.

Necessary exact material producers and dependency preparation inherit the
required goal's priority. Unrelated optional work does not. Candidate names and
arbitrary gain estimates cannot establish relevance. The finite helper AND/OR
worklist and proof worklist retain grounded alternatives without enumerating
all combinations. Caches belong to a current immutable assessment only. Custom
selectors replace eligible ranking; issuance, receipts, budgets and completion
gates remain common. Factories and callbacks still require host timeouts.

`provisional_answer`, `coverage_complete` and `finite_complete` are separate.
Residuals identify exact missing condition/material/check IDs and current scope
and contract revision. `external_completeness` remains **unknown** even after the
declared finite catalogue completes. There are no invented probabilities.

Run the three actual local-file examples in [getting started](getting-started.md).
They exercise partial/advisory PASS, one pooled callback, and material invalidation
with save/reload and retained costs. These are specification checks, not efficacy
experiments. [Migration](migration.md) preserves old inputs without new authority.
