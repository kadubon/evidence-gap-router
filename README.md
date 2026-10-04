# evidence-gap-router

**Route work by missing evidence, not by agent count.**

A small Python SDK and offline CLI for scripts and agent applications that need
to decide what to investigate or verify next. Declare acceptance conditions and
finite action candidates, collect evidence through your own callbacks, and route
the next action according to the remaining gaps. Keep unresolved work visible.

Python **3.12 or newer** · Apache-2.0 · [日本語](README.ja.md)

## Install and try

```sh
python -m pip install evidence-gap-router
egr --version
egr demo --json
egr demo --case invalid --json
egr demo --case budget --json
```

The installed demo reads bundled **artificial** CSV and JSON files through two
separate acquisition callbacks, then checks actual rows and dictionary values
with a different verification callback. Missing information changes the next
action; checks run only after their inputs are available. `valid` satisfies the
declaration, `invalid` retains computed failures, and `budget` stops before
verification. No source checkout, API key, model or network is required at runtime.

The [local-file example](examples/data_quality.py) shows how to point these
callbacks at your own CSV/dictionary. Its constraints cover required columns,
primary-key uniqueness, minimum amounts and allowed currencies. An executed
check and accepted data are separate outcomes.

## Connect a Python callback

This runnable example verifies supplied evidence by doing actual arithmetic.
Replace `check` with your own checker and register it in the explicit mapping.
The example host loop records exceptions and invalid callback returns as
uncertain attempts, including the invocation, unknown remaining cost and effects;
it does not automatically retry them.

```python
from hashlib import sha256
from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CheckResult,
    Evidence,
    Obligation,
    Policy,
    Resources,
    Result,
    State,
)
from evidence_gap_router.demo import run_host_loop

content = "4"
digest = sha256(content.encode()).hexdigest()
state = State(
    obligations=(
        Obligation(
            id="sum",
            description="Check the sum",
            scope="example",
            acceptance="answer equals 2 + 2",
        ),
    ),
    evidence=(
        Evidence(
            id="answer",
            obligation_id="sum",
            scope="example",
            digest=digest,
            content=content,
            producer="calculator",
            source="local calculation",
            provenance_group="calculator",
        ),
    ),
)
action = ActionCandidate(
    id="check-sum",
    obligation_id="sum",
    scope="example",
    kind="verify",
    handler_id="check",
    target_digest=digest,
    resources=Resources(actions=1, verifications=1),
)


def check(action: ActionCandidate, attempt_id: str, state: State) -> Result:
    answer = next(e for e in state.evidence if e.digest == action.target_digest)
    passed = int(answer.content or "") == 2 + 2
    return Result(
        id=f"{attempt_id}-result",
        attempt_id=attempt_id,
        action_id=action.id,
        obligation_id=action.obligation_id,
        scope=action.scope,
        target_digest=action.target_digest,
        actual_resources=Resources(actions=1, verifications=1),
        checks=(
            CheckResult(
                id=f"{attempt_id}-check",
                obligation_id="sum",
                scope="example",
                target_digest=digest,
                verifier_id="arithmetic-check",
                status="PASS" if passed else "FAIL",
                reason="Compared with 2 + 2",
            ),
        ),
    )


run = run_host_loop(
    state,
    (action,),
    Budget(limits=Resources(actions=1, verifications=1)),
    Policy(trusted_verifiers=("arithmetic-check",), executable_handlers=("check",)),
    {"check": check},
)
print(run.decision.stop_reason)  # satisfied
```

The core APIs are `plan(state, candidates, budget, policy)`,
`start(state, action, attempt_id, budget, policy)` and `observe(state, result)`.
Planning does not execute or spend resources. `start` records an attempt before
the host invokes its callback; `observe` checks the result's issued attempt,
action, target and costs. [The complete callback example](examples/callback.py)
uses the same public API. A host may use the core transitions instead of the
provided example loop.

## Offline JSON planning

Save this as `INPUT.json`, then run `egr plan INPUT.json --json`. The decision
selects `read-orders` and explains its gaps; the CLI executes nothing.

```json
{
  "schema_version": "1",
  "state": {
    "schema_version": "1",
    "obligations": [{
      "id": "quality", "description": "Inspect order data", "scope": "orders-v1",
      "acceptance": "Host checker accepts required columns and values"
    }]
  },
  "candidates": [{
    "id": "read-orders", "obligation_id": "quality", "scope": "orders-v1",
    "kind": "investigate", "handler_id": "read-csv",
    "resources": {"actions": 1, "verifications": 0},
    "source": "orders.csv", "provenance_group": "orders-file"
  }],
  "budget": {"limits": {"actions": 3, "verifications": 1}},
  "policy": {"executable_handlers": ["read-csv"], "trusted_verifiers": ["csv-check"]}
}
```

SDK serialization uses `dump_json(model)`, `load_json(text, Model)` and
`read_json(path, Model)`, for example `load_json(dump_json(state), State)`.
JSON schema version is `"1"`. Unknown fields/versions, duplicate keys, invalid
references, nonfinite values and silent scalar type conversions are rejected.
CLI files are bounded to 1 MiB. A URL or path inside evidence is a reference,
never automatically fetched. Operator-selected planning JSON includes host
policy; a service accepting untrusted evidence must supply its policy separately.

With `--json`, domain results go to stdout and validation/IO errors to stderr.
Exit **0** means an action was selected or the declaration is satisfied; **2**
means a valid unresolved domain stop (JSON remains on stdout); **1** means bad
input/IO with no JSON stdout. Argparse usage errors also use exit 2, on stderr.

## Records and decisions

| Record | Meaning |
| --- | --- |
| Obligation | Host-declared requirement, scope, priority and acceptance conditions; the router does not invent or relax requirements. |
| Evidence | Supplied content/reference, digest, producer and declared origin; it is not itself a trusted PASS. |
| CheckResult | Host-trusted verifier's PASS, FAIL or UNKNOWN for an exact digest and scope; absent checks remain unperformed. |
| Residual | Current missing evidence, provenance, verification, resources or unresolved negative/conflicting records. |
| Decision | One eligible declared action or a stop reason, with selection and exclusion reasons, residuals, coverage and remaining resources. |

Stops are `satisfied`, `budget_exhausted`, `blocked`, or `escalation_required`.
Only the first meets the declared required conditions under the supplied policy.
Coverage reports satisfied/required counts, scopes and policy; it is not a
probability of correctness. At least one required obligation is necessary.

Routing favors required obligations, descending priority, action relevance to
the current gap, then stable action ID. Existing unchecked evidence favors
verification. Provenance shortages can favor another declared source. Every
distinct active digest needs trusted verification; duplicated content/origins do
not become additional independent support. Unknown origins stay unknown, and
different IDs/models/providers do not prove independence.
Same-source bridges also collapse declared provenance groups transitively;
conflicting group declarations for one source remain a blocking residual.

FAIL, UNKNOWN and explicit blocking contradictions are preserved. A later PASS
cannot erase them without explicit, valid supersession/resolution. Expired,
withdrawn, superseded or differently scoped evidence/checks cannot justify
current acceptance. Expiry is explicitly marked by the host; no hidden clock
changes a decision. Checks on old digests cannot close changed content. The
default policy prohibits self-verification and trusts only declared verifier IDs.

Resource limits keep action, verification and optional token counts separate.
Estimates differ from actual consumption. Unknown constrained demand is not
free; unknown actual use in a budgeted or bounded dimension, uncertain effects,
or overrun stops further automatic work.
Verification-capacity backpressure prevents acquisition from growing unchecked
work indefinitely. Identical result replay is idempotent; an ID collision is an
error. Candidates are not automatically repeated after failure or uncertainty.

## Host boundary and research context

The host owns execution, timeouts, authorization, external credentials, exact
cost measurement, input trust and concurrency. A recommendation grants no
permission. Handler registration is explicit; strings are never imported as
code. This release uses one process and writer, without a scheduler, database,
crash recovery or exactly-once external effects. It has no LLM gateway, framework
adapters, GUI, telemetry, learned routing or semantic truth/contradiction detector.

The [research index](https://kadubon.github.io/github.io/collective-intelligence-index.html)
and related CCR/VEK/CIO contracts informed preservation of unresolved work,
verification capacity and authority boundaries. They are not dependencies or
tested integrations. This release does not establish novelty, intelligence
growth, cost savings or performance superiority. The demo is a synthetic usage
example. See [design](docs/design.md) and [security](SECURITY.md).

## Development and release

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest
uv build --no-sources
uv run --locked python -c 'from pathlib import Path; Path("dist/.gitignore").unlink(missing_ok=True)'
uv run --locked twine check dist/*
uv run --locked python scripts/package_audit.py dist
```

uv manages Python and the project-local `.venv`; the lockfile controls development
and CI, not every pip user's dependency environment. Check affected changes
locally, then combine CI validation when the changes are ready. One workflow
does Linux/Python 3.12 quality/build/clean-install checks and Windows/Python 3.12
smoke against the same artifact. Only tag push may publish after the exact
commit's successful manual validation and Trusted Publisher/environment checks.
See [releasing](docs/releasing.md) for configuration, pins and recovery steps.
