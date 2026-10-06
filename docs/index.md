# Current 0.3.0 documentation

[Getting started](getting-started.md) · [Completion contracts](completion.md) ·
[API](api.md) · [Design](design.md) · [Migration](migration.md) ·
[Validation](validation.md) · [Release](releasing.md) · [Design note](design-v0.3.0.md).

Current SDK is schema 3. Historical experiments below belong to their original
tags/wheels/harnesses; v0.3.0 empirical efficacy remains unmeasured.

# Documentation

Start with [the SDK and offline CLI guide](getting-started.md).
The package requires Python 3.12 or newer and has one runtime dependency,
Pydantic. Model weights, Ollama and experiment scripts are optional.

| Need | Guide |
| --- | --- |
| Install, run a callback, generate real local example files | [Getting started](getting-started.md) |
| Understand evidence gaps, authority, costs and stops | [Design](design.md) |
| Use public SDK calls and selectors | [API](api.md) |
| Preserve old snapshots and migrate schema 1 | [Migration](migration.md) |
| Connect a local Ollama model through the source examples | [Ollama guide](ollama-guide.md) |
| Inspect current local-model measurements and limitations | [v0.2.4 report](ollama-experiment-v0.2.4.md), [日本語](ollama-experiment-v0.2.4.ja.md) |
| Check SDK and experiment audit scope | [v0.2.4 audit](audit-024.md) |
| Inspect native installation and publication checks | [Validation](validation.md), [Release procedure](releasing.md) |
| Understand host trust and input boundaries | [Security](../SECURITY.md) |

Historical engineering experiments remain available:
[v0.2.3 local Ollama experiment](ollama-experiment.md),
[v0.2.2 model-free benchmark](benchmark.md),
[v0.2.1 erratum](benchmark-v0.2.1-erratum.md),
[v0.2.2 audit](audit-022.md).
Their archived observations are not results for a later protocol.
