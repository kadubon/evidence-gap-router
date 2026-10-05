# evidence-gap-router

**Route work by missing evidence, not by agent count.**

A small Python SDK that chooses the next acquisition or verification from
missing evidence and unfinished checks in a finite, host-declared action set.

Python **3.12+** · Apache-2.0 · [日本語](README.ja.md) · [Documentation](docs/index.md)

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
python -m pip install evidence-gap-router==0.2.4
egr --version
egr demo --json
```

These commands need no model or network after installation. The demo uses
artificial data. [Getting started](docs/getting-started.md) creates actual UTF-8
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
action = ActionCandidate(
    id="check-answer",
    obligation_id="sum",
    scope="example",
    kind="verify",
    handler_id="check",
    target_evidence_id="answer",
    target_digest=evidence.digest,
    checker_id="arithmetic-check",
    resources=Resources(actions=1, verifications=1),
)
policy = Policy(
    trusted_verifiers=("arithmetic-check",),
    handlers=(
        HandlerRegistration(
            handler_id="check",
            roles=("verify",),
            checkers=(CheckerPermission(checker_id="arithmetic-check"),),
        ),
    ),
)


def check(view: CallbackView):
    passed = int(view.inputs[0].content or "") == 2 + 2
    return view.result(
        actual_resources=Resources(actions=1, verifications=1),
        checks=(view.check(status="PASS" if passed else "FAIL", reason="Compared with 2 + 2"),),
    )


budget = Budget(limits=Resources(actions=1, verifications=1))
next_step = plan(state, (action,), budget, policy)
assert next_step.action is not None
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

The host registers checker permission; `view.check` binds the issued target,
contract and inputs. An ID supplied by an output grants no authority.
`step` invokes at most one callback; `run` has a finite step limit. Runner stops
and unresolved domain requirements are separate. Pending attempts and unknown
budgeted consumption block automatic continuation.

See [Concepts](docs/design.md), [API](docs/api.md) and
[snapshot/migration](docs/migration.md) for acquisition, invalidation, rechecking,
selectors and retained costs. Limited callback views are application disclosures,
not a Python sandbox. The host owns input trust, effects, costs and single-writer use.

## Local Ollama experiment

The optional [Ollama guide](docs/ollama-guide.md) uses source-level examples with
an ordinary installed SDK and explicit local inference. Ollama is not required
by core imports or the offline CLI. Model weights and user credentials are absent
from the package; normal tests and release CI do not run model inference.

The v0.2.4 campaign is in development calibration. Both existing local models
completed six warm reader/integrator/reviewer requests. Primary A/B/C parent
measurements have not started; those warm receipts are not routing performance.
See the [current technical report](docs/ollama-experiment-v0.2.4.md),
[Japanese summary](docs/ollama-experiment-v0.2.4.ja.md) and
[archived v0.2.3 report](docs/ollama-experiment.md).

A uses EGR ordering; B uses strong verify-first ordering with the same public
runner, pool, permissions, callbacks and budgets. C is a pooled-information
reference. The comparison concerns extra selection value within the shared
feasibility mechanism, not independent agent frameworks or a model ranking.

[Audit](docs/audit-024.md) · [Validation](docs/validation.md) ·
[Releasing](docs/releasing.md) · [Security](SECURITY.md)
