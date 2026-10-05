# Optional local Ollama use

Core imports, `egr plan`, file checks and ordinary tests do not connect to Ollama.
The examples below need a **source checkout plus an ordinary installed wheel**.
`experiments.ollama` is not installed by pip. Live v0.2.4 observations use Windows
x64, CPU inference, Ollama 0.35.0 and the existing local models; portable HTTP
contract tests on other operating systems are separate observations.

## Check the existing models

```sh
ollama --version
```

Preflight requires the exact local tags `qwen3.6:35b-a3b` and `gemma4:e4b` and
records their actual digests, quantization, licenses and template hashes.
It does not download, update, requantize or substitute weights. Qwen is loaded
first; a CPU backend can complete the experiment without a GPU.

Use one dedicated external directory and an unused numeric loopback port.
The Windows owned-server helper records the executable hash and process creation
identity, starts a hidden process, and applies these settings to that process:

```text
OLLAMA_NO_CLOUD=1
OLLAMA_NUM_PARALLEL=1
OLLAMA_MAX_LOADED_MODELS=1
OLLAMA_MAX_QUEUE=1
OLLAMA_KEEP_ALIVE=60m
OLLAMA_LOAD_TIMEOUT=30m
```

For a **new** campaign, save this as `start_local.py`, edit the three explicit
paths, then invoke it with the installed environment's Python and `-I`:

```python
import sys
from pathlib import Path

checkout = Path("C:/work/evidence-gap-router")
directory = Path("C:/work/egr-local-run")
executable = Path("C:/work/ollama/ollama.exe")
sys.path.insert(0, str(checkout))

from experiments.ollama.ownership import start_owned

owner = start_owned(directory, executable)
print(owner["root"]["pid"])
```

Do this once. An existing owned campaign uses its `private/current-owner.json`;
starting another server or resetting its directory is not resume. Shared services
are outside this helper's ownership. The supplied native process-handle recovery
controller is Windows-specific; it is not a portable process supervisor.

After starting the owned server, inspect **its** catalogue in PowerShell:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11435'
ollama list
```

The controller uses that same endpoint. Pointing `ollama list` at a different
default/shared server does not verify this campaign's inventory.

Ollama 0.35.0's `LOAD_TIMEOUT` is a load-stall detector, not a client deadline.
An empty chat preload returns before model completion. See the pinned
[environment source](https://github.com/ollama/ollama/blob/v0.35.0/envconfig/config.go)
and [ChatHandler](https://github.com/ollama/ollama/blob/v0.35.0/server/routes.go).

## Run the existing controller

Install the actual candidate wheel into an external venv during development;
after publication an official `evidence-gap-router==0.2.4` install is usable.
Use that interpreter directly, rather than an editable install or project `uv run`.
The following PowerShell paths are examples to edit:

```powershell
$runtime = 'C:/work/egr-env/Scripts/python.exe'
$controller = 'C:/work/evidence-gap-router/experiments/ollama/cli.py'
$run = 'C:/work/egr-local-run'
$env:PYTHONIOENCODING = 'utf-8'
& $runtime -I $controller preflight --directory $run
& $runtime -I $controller warmup --directory $run
& $runtime -I $controller calibrate --directory $run
& $runtime -I $controller pilot --directory $run
& $runtime -I $controller freeze --directory $run --wheel 'C:/work/candidate/evidence_gap_router-0.2.4-py3-none-any.whl'
& $runtime -I $controller live --directory $run
```

Check each exit before starting the next command. Preflight pins one manifest;
it refuses to replace it. Warmup includes reader, integrator, reviewer and a
longer input with a changed fact. Calibration is a fixed 24-answer bank with old
and compact review schemas at 512/2048 caps, followed by a separate four-parent
pilot. Freeze chooses 24 or 16 new parents using observed speed/resources, never
A minus B results. The independent oracle's gold is absent from model prompts.

The v0.2.4 profile is nonstreaming, with a 30-second connection timeout and full
hard-deadline response waits: Qwen 1,800 seconds, Gemma 900, preload 1,800.
Initial stage caps are reader 1,024, integrator 1,536, reviewer 768 and repair
1,024; calibration selects the common review cap. Context is 8,192, with explicit
`think:false`, `truncate:false`, `shift:false`, temperature zero and 60-minute
residency. No first-token latency is inferred from a nonstream response.

The single serial campaign retains all development and failed calls inside
48 hours, 4,000 requests, 4 million generated tokens, 40 million total tokens and
4 GiB of raw files. Stage reservations are context plus output cap, distinct
from actual counters. Free RAM must remain at least max(2 GiB, 10% installed
RAM); disk needs 5 GiB plus raw-file margin. Low RAM, OOM or worsening swap
observations prevent new dispatch. These are measured gates, not hard memory
isolation of every inference process.

The current Windows gate reads all pagefiles' CIM `CurrentUsage`. Four known
consecutive increases totaling at least 256 MiB block a new dispatch. Unknown
swap observation also blocks this profile. This sampled trend is separate from
the RAM floor; it does not measure every transient memory or swap peak.

## Status, continuation and reanalysis

In another PowerShell terminal, use the same paths:

```powershell
& $runtime -I $controller status --directory $run
& $runtime -I $controller resume --directory $run
& $runtime -I $controller analyze --directory $run --output 'C:/work/egr-analysis'
```

Run `resume` after the previous worker has exited. Do not start two inference
controllers. A busy status is an observation of the bounded journal tail and
does not claim a fresh budget audit. `worker-heartbeat.json` saves the current
key, last completed request and audited budget snapshot. Heartbeats do not extend
deadlines. Request bytes and receipt spools are saved before interpretation;
checkpoints retain SDK attempts and exact paid records.

Known length/JSON/schema faults may have one paid format repair per stage, at
most two per trial, within the original call/token bounds. Partial PASS text
is never accepted. A model's unknown answer, an UNKNOWN review, an unknown-cost
request and an unexecuted trial are separate states.

A crash with a final spool can be recovered **without inference**:

```powershell
& $runtime -I $controller recover-receipt --directory $run --request-id 'the-exact-retained-request-id'
```

For a hard-deadline uncertain request, `recover-server` requires positive exit
proof from held native handles for the exact owned root/descendants and an
independently supported local consumption cap:

```powershell
& $runtime -I $controller recover-server --directory $run
& $runtime -I $controller resume --directory $run
```

Actual usage stays null; the original full reservation remains charged. A new
server epoch allows unstarted keys, not replacement of the failed primary trial.
There are at most two such recoveries per campaign. Missing identity/exit/bound
proof keeps the global block. A closed connection or empty `/api/ps` is not exit
proof. Changed boot identity blocks automatic time-budget resume; do not reset
the clock or silently exclude pause time.

## Use a small document callback

The [source callback](../examples/ollama_callback.py) reads two artificial
temperature documents, invokes the existing reader/integrator/reviewer runner,
and retains its paid requests in the same campaign ledger. It accepts no gold
answer. It needs the owned server and existing preflight/settings above:

```powershell
& $runtime -I 'C:/work/evidence-gap-router/examples/ollama_callback.py' --directory $run --model 'gemma4:e4b' --key 'my-temperature-example'
```

Expected fields are `new_model_requests`, `answer`, `runner_stop`, `domain_stop`
and `pending`. A retained result or checkpoint resumes its exact key; repeating
it is not a new measurement. Use a new key only for a separate, explicitly paid
invocation. SDK/model acceptance remains separate from independent correctness.
The release report records the actual live invocation after it completes.

[Current technical report](ollama-experiment-v0.2.4.md) ·
[Japanese summary](ollama-experiment-v0.2.4.ja.md) ·
[Archived v0.2.3 report](ollama-experiment.md)
