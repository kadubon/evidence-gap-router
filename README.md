# evidence-gap-router

**Route work by missing evidence, not by agent count.**

A small Python SDK that chooses the next acquisition or verification from
missing evidence and unfinished checks in a finite, host-declared action set.

Python **3.12+** · Apache-2.0 · [日本語](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/README.ja.md) · [Documentation](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/index.md)

## When to use it

Use it when permitted work depends on the material already obtained, verification
results, prerequisites, costs or changed rules. It retains evidence, issued
checks, failures, expenses and unresolved requirements across explicit continuation.

A fixed pipeline is usually sufficient when every input and step is already
known. The SDK does not supply agents, models, a network gateway or a scheduler.
Tracking verification history does not guarantee semantic truth. Separate calls
to the same model do not establish statistically independent judgments.

## Install and check

```sh
python -m pip install evidence-gap-router==0.3.0
egr --version
egr demo --json
```

These commands need no model or network after installation. The demo uses
artificial data. [Getting started](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/getting-started.md) creates actual UTF-8
CSV/JSON files, including quoted paths with spaces and Japanese characters,
then checks them with `egr check-data`.

## Connect a callback

This complete ordinary-wheel example parses the supplied content, selects a
check, records its actual result and shows the remaining blocking issues:

```python
from hashlib import sha256
from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CallbackView,
    CheckerPermission,
    CompletionContract,
    DependencyRequirement,
    declare_completion,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    State,
    plan,
    run,
)

content = "4"
evidence = Evidence(
    id="answer",
    obligation_id="sum",
    scope="example",
    digest=sha256(content.encode()).hexdigest(),
    content=content,
    producer="calculator",
    source="local-calculation",
    provenance_group="calculator",
)
state = State(
    obligations=(
        Obligation(
            id="sum",
            description="Check arithmetic",
            scope="example",
            acceptance="Parsed answer equals 2 + 2",
        ),
    ),
    evidence=(evidence,),
)
obligation = state.obligations[0]
state = declare_completion(
    state,
    CompletionContract(
        id="fixed-arithmetic-1",
        obligation_id=obligation.id,
        scope=obligation.scope,
        obligation_fingerprint=obligation.contract_fingerprint,
        target=DependencyRequirement(
            evidence_id="answer", obligation_id=obligation.id, scope=obligation.scope
        ),
        declared_scope="not_applicable",
        scope_reason="Fixed supplied arithmetic; no retrieval.",
    ),
)
action = ActionCandidate(
    id="check-answer",
    obligation_id="sum",
    scope="example",
    kind="verify",
    handler_id="check",
    target_evidence_id="answer",
    target_digest=evidence.digest,
    checker_id="arithmetic-check",
    resources=Resources(actions=1, verifications=1, tokens=0),
)
policy = Policy(
    trusted_verifiers=("arithmetic-check",),
    handlers=(
        HandlerRegistration(
            handler_id="check",
            roles=("verify",),
            checkers=(
                CheckerPermission(
                    checker_id="arithmetic-check",
                    completion_kinds=("content",),
                    completion_scopes=("example",),
                ),
            ),
        ),
    ),
)


def check(view: CallbackView):
    passed = int(view.inputs[0].content or "") == 2 + 2
    return view.result(
        actual_resources=Resources(actions=1, verifications=1, tokens=0),
        checks=(view.check(status="PASS" if passed else "FAIL", reason="Compared with 2 + 2"),),
    )


budget = Budget(limits=Resources(actions=1, verifications=1, tokens=0))
next_step = plan(state, (action,), budget, policy)
assert next_step.action is not None
assert any(r.code == "completion_check_missing" for r in next_step.completion[0].residuals)
print(next_step.action.id)  # check-answer

report = run(
    state,
    (action,),
    budget,
    policy,
    {"check": check},
    max_steps=8,
)
print(report.state.checks[-1].status)  # PASS
print(report.decision.stop_reason)  # satisfied
print([r.code for r in report.decision.residuals if r.blocking])  # []
```

Before the callback, `completion_check_missing` names the unfinished condition.
The host registers checker permission; `view.check` binds the issued target,
contract and inputs. An ID supplied by an output grants no authority.
`step` invokes at most one callback; `run` has a finite step limit. Runner stops
and unresolved domain requirements are separate. Pending attempts and unknown
budgeted consumption block automatic continuation.

See [Concepts](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/design.md), [API](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/api.md) and
[snapshot/migration](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/migration.md) for acquisition, invalidation, rechecking,
selectors and retained costs. Limited callback views are application disclosures,
not a Python sandbox. The host owns input trust, effects, costs and single-writer use.

## Completion and local-file examples

An observation PASS, current applicability, and finite goal completion are
separate. The host explicitly declares required materials, scope/catalogue
revision and permitted check kinds. Empty/unspecified scope remains incomplete;
fixed arithmetic uses a reasoned `not_applicable`. Checker permissions default to
advisory. Names, JSON syntax and repeated aliases do not establish authority or
independence. A new permission cannot upgrade an old advisory receipt.

```sh
python -m evidence_gap_router.completion_example partial
python -m evidence_gap_router.completion_example pooled
python -m evidence_gap_router.completion_example continuation
```

These create/read actual UTF-8 integer files, record issued receipts and preserve
costs. Partial M-only PASS leaves N missing; acquiring N does not upgrade that
old basis. A full-input qualified check completes the finite contract. Pooling
can legitimately use one fixed callback. Continuation invalidates used N, saves
and reloads, reads replacement N and rechecks while retaining the original PASS
and reusing M. A user directory may contain spaces and Unicode; existing files
are not overwritten. See [completion contracts](docs/completion.md).

Schema 3 requires explicit [schema-1/2 migration](docs/migration.md). Original
history and bases remain; imported states lack invented completion authority.
`Decision.completion` reports exact missing conditions and external completeness
as unknown. Observation coverage is diagnostic and never substitutes for it.

## Historical results and current limits

The v0.2.4 frozen local experiment found A below B: answerable completion was
Qwen A/B/C **0/8/12 of 12**, Gemma **3/8/10 of 12**. Qwen A false acceptance
was **15/16**. These negative results motivate contracts and role separation;
they do not show that v0.3.0 fixes empirical performance. [Original report](https://github.com/kadubon/evidence-gap-router/blob/v0.2.4/docs/ollama-experiment-v0.2.4.md).

**v0.3.0: new LLM requests 0, new efficacy/performance experiments 0; empirical
utility unmeasured.** This is a contract/control implementation, with no learned
weights or routing-weight tuning. Historical experiments require their original
tag, wheel and harness; the current experiment CLI rejects SDK mismatch before
network or server operations. [Archived Ollama guide](docs/ollama-guide.md).
