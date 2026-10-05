# Local Ollama experiment

The current source-level controller is documented in the
[Ollama guide](../../docs/ollama-guide.md). It uses an ordinary installed SDK;
these modules are outside the wheel. Imports, normal tests and release CI do
not start a model, download weights or run real inference.

The corrective v0.2.4 protocol is [protocol-v0.2.4-r2.json](protocol-v0.2.4-r2.json).
The [initial protocol](protocol-v0.2.4.json), its original freeze and raw records
remain retained. A post-freeze optional-default receipt defect invalidated its
verified-completion interpretation. The correction preserves actual parsed JSON,
uses unused public instances and carries the exact original ledger/clock forward.
Current [English results](../../docs/ollama-experiment-v0.2.4.md) and
[Japanese summary](../../docs/ollama-experiment-v0.2.4.ja.md) distinguish backend
calibration, pilot, new confirmation, fresh stop-policy pairs and custom examples.
Public tasks alone reach prompts; gold is evaluation-only. A/B share the public
runner and feasible pool, while C is a pooled-information reference.

The [v0.2.3 English report](../../docs/ollama-experiment.md),
[Japanese report](../../docs/ollama-experiment.ja.md), `protocol.json` and
`results/v0.2.3/` remain historical records. The old unknown Qwen request is
not settled or retried by the new campaign. Version-specific old command text
remains in the [v0.2.3 source snapshot](https://github.com/kadubon/evidence-gap-router/blob/v0.2.3/experiments/ollama/README.md).
