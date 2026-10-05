# evidence-gap-router

**Route work by missing evidence, not by agent count.**

A small Python SDK for choosing the next investigation or verification from a
finite host-declared action set. Checks bind the actual target, acceptance
contract and material used, so changed rules trigger the relevant recheck.
Use it from ordinary Python callbacks or inspect recommendations with an offline CLI.

Python **3.12 or newer** · Apache-2.0 · [日本語](README.ja.md)

## Install and use your own files

```sh
python -m pip install evidence-gap-router==0.2.0
egr --version
egr check-data --data ./orders.csv --dictionary ./rules.json --json
egr demo --json
egr demo --case invalid --json
egr demo --case budget --json
egr demo --example cause --case resolved --json
```

`check-data` reads the two explicitly selected local files without changing them.
It first checks the dictionary under its own obligation, then checks the orders
using that exact verified dictionary. Each stage has its own callback and pinned
input view. The bundled demos are **artificial examples**; local-file output has
`artificial_data: false` and local scopes.

CSV columns must be exactly `order_id,amount,currency`, in any order. Data must
have at least one row, unique nonempty IDs, finite amounts above the declared
minimum, and an allowed currency. The dictionary is the following fixed contract:

```json
{
  "required_columns": ["order_id", "amount", "currency"],
  "primary_key": "order_id",
  "minimum_amount": 0,
  "allowed_currencies": ["USD", "JPY"]
}
```

Unknown dictionary fields, duplicate JSON keys/CSV columns, blank column names,
missing/extra row fields, nonfinite values, invalid types and invalid UTF-8 are
rejected. Each input is limited to 1 MiB and CSV to 10,000 rows; exceeding a bound
never turns a prefix into accepted whole-file evidence. UTF-8 BOM and LF/CRLF are
accepted. Evidence digests hash the original bytes, including BOM and line endings.
Space and Japanese characters in paths are supported with `pathlib`; shell commands
are never assembled from those paths. See [the data-quality example](examples/data_quality.py).

## Connect a callback

This complete SDK example checks an actual parsed answer. Register your own
function in `handlers`; the helper creates a check tied to the issued basis.

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


report = run(
    state,
    (action,),
    Budget(limits=Resources(actions=1, verifications=1)),
    policy,
    {"check": check},
    max_steps=8,
)
print(report.decision.stop_reason)  # satisfied
```

`step` invokes at most one callback. `run` defaults to a finite `max_steps=32`.
Both return state, decisions and receipts that can be inspected and serialized;
continue explicitly from the returned state. Runner stops such as
`max_steps_reached`, `factory_error`, `callback_error` and `no_progress` are separate
from the router's domain stop. Exceptions and invalid receipts retain issued
attempts, invocation cost and uncertain effects. A pending attempt is never
reissued. Attempt IDs avoid the entire existing history.

Initial acquisition views contain no other collector's evidence. A verification
view receives its declared target and exact dependency material. Views are frozen
application-level disclosures, **not a sandbox or a proof of statistical independence**.
Host-owned candidate factories may inspect the whole state for planning.

The pure SDK remains `plan`, `start` and `observe`. Planning is read-only and
spends no budget; explicit issuance pins the basis and registered permissions.
`observe(state, receipt, policy)` checks the receipt against that issuance and
current host policy. Host registrations authorize roles, checker revision and
purpose; an ID written in result text grants no permission.

## Inspect gaps without execution

Save this as `INPUT.json` and run `egr plan INPUT.json --json`:

```json
{
  "schema_version": "2",
  "state": {
    "schema_version": "2",
    "obligations": [{"id": "quality", "description": "Inspect data", "scope": "orders",
                     "acceptance": "Host checker accepts the supplied data"}]
  },
  "candidates": [{"id": "read-orders", "obligation_id": "quality", "scope": "orders",
                  "kind": "investigate", "handler_id": "read", "produces_evidence_id": "orders",
                  "source": "orders.csv", "provenance_group": "orders-file"}],
  "budget": {"limits": {"actions": 3, "verifications": 1}},
  "policy": {"handlers": [{"handler_id": "read", "roles": ["investigate"]}],
             "trusted_verifiers": ["csv-check"]}
}
```

The decision includes target-specific `gaps`, `selected_gap`, pending verification
count, residuals, resource limits and candidate exclusion reasons. Already
satisfied target/checker/purpose combinations are excluded by default. Missing
required verifiers remain backlog after a partial PASS. Explicit prerequisite
acquisition can unblock a declared pending check without letting arbitrary new
content bypass verification capacity. Provenance-shortage routing distinguishes
known repetition, unknown origin and a declared source/group that can fill the gap;
only otherwise comparable candidates use stable ID order.

`plan` is offline: references are never fetched and handler strings are never
imported. Input is strict schema **2**, bounded to 1 MiB, with duplicate keys and
unknown fields/versions rejected. `dump_json`, `load_json` and `read_json` provide
validated round trips. Schema-1 requires [explicit migration](docs/migration.md).

With `--json`, domain reports go to stdout. A malformed plan input has no JSON
stdout and reports an error on stderr. File-input and callback failures retain
their state/cost report on stdout and also explain the error on stderr.
Exit 0 means an action or satisfied result; exit 2 means a valid unresolved domain
stop or inspected nonacceptance; exit 1 means an input/execution failure. Argparse
usage errors also use exit 2, on stderr. The report's `outcome`, domain stop and
runner stop distinguish malformed input, callback failure, checked FAIL, missing
material, budget exhaustion and satisfaction.

## What acceptance means

An obligation declares acceptance text plus a mechanical contract fingerprint.
A check binds evidence ID/digest/scope, contract fingerprint, the finite material
actually used, checker ID/revision and purpose. Contract fields include ID, scope,
contract revision, acceptance, evidence/provenance requirements and required
verifiers; display description, priority and required status are excluded.
Unrelated evidence additions leave an applicable check reusable. Changed,
withdrawn, expired or superseded dependencies invalidate only their dependent
checks. A fingerprint does not understand semantic equivalence or certify truth.

Normal content checks, negative-check resolution and contradiction resolution are
separate purposes. Acquisition cannot erase FAIL/UNKNOWN or resolve contradictions.
Resolution needs host permission and a matching target/fingerprint/basis. Generic
content PASS cannot resolve a contradiction. All original records remain visible;
identical receipt replay is idempotent and ID collisions fail.

Router stops remain `satisfied`, `budget_exhausted`, `blocked` and
`escalation_required`. Satisfaction is relative to declared required conditions
and current host policy. Coverage reports its numerator, denominator, scopes and
policy; it is not a correctness probability or intelligence score. States with zero required
obligations are rejected. Actions, verifications and optional tokens remain separate
integer dimensions; unknown budgeted/bounded actual consumption and uncertain
execution effects stop automatic continuation.

The host owns authentic checker registration, input trust, costs, permissions,
external effects, timeouts and single-writer consistency. Structurally valid JSON
and a receipt are not authenticated real-world evidence. No LLM gateway, server,
DB, distributed scheduler, cryptographic authentication or exactly-once recovery
is provided. The [design](docs/design.md), [audit mapping](docs/audit.md),
[migration guide](docs/migration.md) and [security policy](SECURITY.md) give the boundaries.

## Small comparison and validation

`egr demo --example cause` is a separate multi-material investigation: acquisition views
read records, specifications and exceptions separately; checks use disclosed raw
material. Conflict, unknown provenance and verification budget cases preserve gaps.
The [comparison](docs/comparison.md) records fixed-order and gap-routing outcomes
from the same materials, checker, callbacks and limits. These finite model-free
examples do not establish general AI improvement, cost savings or intelligence growth.

[Validation profiles](docs/validation.md) distinguish executed results from planned
profiles. CI builds once on Linux/Python 3.12, installs the same wheel on Windows
x64, macOS `macos-15` arm64 and `macos-15-intel` x86_64, and checks Linux 3.13/3.14.
Native reports record actual machine, Python, imports, Pydantic/core wheel tags and
artifact hash. Future Python versions are not implied to have been tested.

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

The lock governs development/CI, not all pip users. Check relevant changes locally,
then combine manual CI after the changes are complete. The single workflow starts
only on dispatch or `v*` tag push. Publication requires every native gate and an
exact-commit successful manual run; manual runs never publish.
[Releasing](docs/releasing.md) records configuration and recovery procedures.
