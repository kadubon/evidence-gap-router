# Local Ollama experiment

This directory is an explicit experiment using short artificial Japanese documents.
It is outside the wheel and adds no core runtime dependency. Package import,
ordinary pytest and release CI never start Ollama, download weights or send real
generation requests. The portable fake HTTP tests check the communication contract;
their outcomes are not Gemma/Qwen inference results.

The current protocol compares selectors within each model. A uses the default EGR
selector; B uses a fixed strong verify-first selector with the same public `run`,
candidate pool, permission policy, views, callbacks, resource bounds and stops.
Both share the public feasibility/necessity/helper gates. C sees all available
public documents together and is a separate pooled-information reference with a
different arrival policy. The independent oracle is applied after execution and
has access to evaluation-only gold that the prompts and callbacks do not receive.
Literal quote/schema checks, model semantic review, SDK satisfaction and oracle
completion are distinct observations.

No live inference or v0.2.3 publication is claimed by these instructions. Actual
results and limitations belong in the [English report](../../docs/ollama-experiment.md)
and [Japanese summary](../../docs/ollama-experiment.ja.md) after verification.

## Runtime and owned server

Create an ordinary Python 3.12+ virtual environment outside the checkout and install
the exact candidate wheel. After actual publication, the official index can be
used instead. For example, replace these paths with your own:

```sh
python -m venv /tmp/egr-ollama-env
/tmp/egr-ollama-env/bin/python -m pip install /absolute/path/evidence_gap_router-0.2.3-py3-none-any.whl
```

Run the direct script with that interpreter and `-I`. The script adds the repository
root only for `experiments.ollama`; it does not add `src`. `evidence_gap_router`
therefore comes from the ordinary installed wheel. Do not use an editable install
or a project `uv run` that silently supplies a different runtime.

The experiment pins Ollama **0.35.0** and existing exact local tags
`gemma4:e4b` and `qwen3.6:35b-a3b`. Preflight records `/api/tags`, sanitized
`/api/show` identity/quantization/license/template hashes and `/api/ps`; it does not
pull, update or replace a model. Missing models remain unavailable. The model
sizes and tokenizers differ, so comparisons are primarily A minus B within each
model, not a causal model-brand speed ranking.

Use your own server on an unused numeric loopback port. The server process must
actually inherit cloud-disabled and serial-execution settings; setting environment
variables only in a client attached to an existing server does not establish this.
Do not stop or reconfigure a shared Ollama service. A POSIX startup example is:

```sh
env OLLAMA_HOST=127.0.0.1:11435 OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_MAX_QUEUE=1 ollama serve > /tmp/egr-ollama-server.log 2>&1 &
```

Record the actual PID and log. On Windows, start the separate process with the
same inherited variables, a hidden window and separate redirected stdout/stderr
logs. Use the log containing the server's `Ollama cloud disabled: true` and matching
listener evidence for preflight. Only the server you own may be stopped afterward.
The HTTP client uses `http.client` directly, accepts numeric loopback HTTP origins
only and does not follow redirects or environment proxies. Loopback alone is not
proof of local inference: preflight also rejects nonempty remote model metadata
and requires matching cloud-disabled owned-server evidence.

Ollama 0.35.0's [chat request type](https://github.com/ollama/ollama/blob/v0.35.0/api/types.go)
and [chat handlers](https://github.com/ollama/ollama/blob/v0.35.0/server/routes.go)
support explicit `truncate:false` and `shift:false`. Every request uses both controls;
oversized input is rejected rather than silently shortened. The client records
that policy and absence of an exact local tokenizer, rather than treating JSON
body bytes or character counts as exact tokens.

## Command sequence

Use one dedicated external run directory throughout. The following POSIX examples
use the same script, installed interpreter, owned-server PID and log. Windows uses
the equivalent `Scripts/python.exe` and absolute paths; all CLI arguments are the
same.

```sh
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py preflight --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345 --server-log /tmp/egr-ollama-server.log
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py backend-smoke --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py pilot --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345
```

Preflight is read-only network inspection. Backend smoke and later execution
commands issue real generation requests. Their durable reservations, costs and
failures count toward the same global envelope. Backend smoke checks format,
thinking fields, counters, length and caps; it is not the main experiment.
Development pilot uses four parents × two models × three arms. The configured
schema is sent through `format`, final content is strictly parsed and validated
locally, and `message.thinking` is retained separately from final content.
An absent thinking field does not prove the absence of internal reasoning.

Before confirmation, commit the runtime and experiment implementation, verify
the actually installed wheel bytes, retain the pilot and create the freeze:

```sh
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py freeze --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345 --wheel /absolute/path/evidence_gap_router-0.2.3-py3-none-any.whl --freeze /absolute/path/evidence-gap-router/experiments/ollama/results/freeze-v0.2.3.json
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py live --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345 --freeze /absolute/path/evidence-gap-router/experiments/ollama/results/freeze-v0.2.3.json
```

The freeze pins code/protocol/task/oracle hashes, candidate package/wheel identity,
exact model metadata, decoding controls, seeds and all trial keys. The selected
24/16/8-parent profile depends on pilot timing, memory and remaining wall capacity,
not correctness or arm wins. An infeasible minimum profile is pilot-only. Preserve
all observed failures and explicit unexecuted keys. Do not adjust prompts or seeds
after seeing confirmation outcomes; a required implementation change creates a
new protocol with unused inputs and retains the prior records and total spending.

For the predeclared first confirmation parent in each family, A/B also retain a
separate auxiliary record. A known `no_progress` primary stop may continue from a
copied exact checkpoint by at most two unused callbacks, immediately within the
original six-call, token and wall budget. The main record remains unchanged.
Ineligible or exhausted continuations are recorded explicitly. Restarting later
does not reset the original deadline or create a fresh trial allowance.

Resume and analysis are separate commands:

```sh
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py resume --directory /tmp/egr-ollama-run --url http://127.0.0.1:11435 --server-pid 12345 --freeze /absolute/path/evidence-gap-router/experiments/ollama/results/freeze-v0.2.3.json
/tmp/egr-ollama-env/bin/python -I /absolute/path/evidence-gap-router/experiments/ollama/cli.py analyze --directory /tmp/egr-ollama-run --output /absolute/path/evidence-gap-router/experiments/ollama/results/v0.2.3
```

`resume` checks the same freeze and skips completed keys. A persisted issued SDK
attempt can use its already completed HTTP ledger record without redispatch.
A sent request without a definitive receipt, missing token usage, timeout,
disconnect or an incomplete journal remains unknown and blocks subsequent live
calls across every trial. Stopping the client does not prove the server stopped
working. There is no automatic retry, JSON repair or model fallback. `analyze`
reads saved records and issues no inference.

## Finite costs and interpretation

The immutable ledger configuration covers the first durable generation reservation
through smoke, pilot, confirmation and auxiliary work: at most four hours, 1,200
requests, 600,000 observed generated tokens and 5,000,000 prompt-plus-generated
tokens. Each trial has at most six LLM calls, 600 seconds and a conservative
27,648-token envelope; SDK actions/verifications are separately bounded at 16/8.
Each request fixes temperature 0, explicit seed, context 4096 and output cap 512;
ordinary request wall is 120 seconds and initial cold smoke can use 180 seconds.
Socket waits are bounded by remaining wall, including issuance overhead. Raw and
snapshot storage is bounded at 512 MiB and history is retained when issuance stops.

Calls reserve context-plus-output capacity before dispatch and fsync it. Known
receipts settle actual prompt/generated counters; unknown consumption retains its
reservation and nullable cost. Duration counters retain original nanoseconds and
separate seconds. Missing optional fields remain null. Cached prompt counters,
load time, client wall and complete trial time remain distinct. Character length
is not an exact token count; model tokenizers need not be comparable.

Resource snapshots are before/after observations, not a hard whole-server/GPU
memory ceiling or continuous peak measurement. Low free RAM, disk pressure,
OOM, stalls or unknown pending consumption stop new dispatch. Python client CPU
and memory do not represent total server/GPU inference cost. No API price, energy
or CO2 metric is invented. Report all attempted tasks and the paired-success cost
subset separately, with its denominator and selection bias.

## Small callback use

The following is an explicit live example, not an import-time action. It reuses
the preflight and global ledger and registers the experiment's finite callbacks
through `run_trial`. Save it as a separate script, replace the paths/PID, and run
with the ordinary installed interpreter and `-I`. The two texts are public artificial
inputs; no hidden gold is passed to the runner.

```python
import json
import sys
from argparse import Namespace
from pathlib import Path

checkout = Path("/absolute/path/evidence-gap-router")
sys.path.insert(0, str(checkout))

from experiments.ollama.cli import BoundClient, client_for
from experiments.ollama.harness import run_trial
from experiments.ollama.tasks import Document, PublicTask

directory = Path("/tmp/egr-ollama-run")
args = Namespace(
    directory=directory, url="http://127.0.0.1:11435", server_pid=12345, server_log=None
)
manifest = json.loads((directory / "preflight/manifest.json").read_text("utf-8"))
model = manifest["models"][0]
task = PublicTask(
    task_id="local-example",
    family="L1",
    question="検査対象Aは今回の温度条件に適合しますか。",
    documents=(
        Document(
            "specification",
            "engineering",
            "temperature",
            "1",
            "spec-origin",
            "対象Aの上限温度は10℃です。",
        ),
        Document(
            "measurement",
            "inspection",
            "temperature",
            "1",
            "measurement-origin",
            "今回の対象Aの測定温度は9℃です。",
        ),
    ),
)
result = run_trial(
    task,
    arm="A",
    model=model["tag"],
    model_digest=model["digest"],
    seed=23031003,
    client=BoundClient(client_for(args), args, "example", "local-example-gemma"),
    checkpoint=directory / "local-example-checkpoint.json",
    resume=(directory / "local-example-checkpoint.json").exists(),
)
print(json.dumps(result, ensure_ascii=False))
```

For permitted short local documents, replace those literal texts with explicit
local reads and supply their real versions/origins; model assertions do not define
source provenance or checker authority. Do not execute output as code or fetch
model-produced URLs/paths. A model-reviewed answer can still be wrong. This example
has no independent gold score, so its SDK/model completion is not oracle-confirmed.
The example's calls are still charged to the same global ledger, and it must not
be inserted into a frozen confirmation run with altered conditions.
