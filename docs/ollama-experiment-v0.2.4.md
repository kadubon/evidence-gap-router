# Local Ollama experiment — v0.2.4

EGR ordering A underperformed strong verify-first B in the completed corrective
confirmation. On 12 answerable parents, Qwen verified 0/12 versus B's 8/12;
Gemma verified 3/12 versus 8/12. Pooled-information C verified 12/12 and 10/12,
respectively. These small artificial tasks provide no evidence of an ordering
advantage for A. C's different information arrival also shows that a small fixed
workflow is sufficient for many of these context-fitting inputs.

All 96 planned main trials completed with known usage, zero pending/unexecuted
trials and zero transport/format faults. Successful execution and valid JSON
did not establish semantic reliability: Qwen A falsely claimed completion on
15/16 parents. The frozen SDK, oracle and criteria remain unchanged after these
observations. All 64 fresh stop-sensitivity trials and the paid custom live
example also completed. This document is the source snapshot before publication;
actual public-byte and native-CI verification is recorded in the
[immutable Release verification](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.4/publication-verification-v0.2.4.json).

## Completed main confirmation

Each model/arm has 16 parents: 12 answerable and four truly insufficient. All
16 were independently assessed. Correctness and grounding below are independent
of model review; verified completion additionally requires the current review
and receipt acceptance conditions.

| Model | Arm | Correct /16 | Grounded /16 | Verified answerable /12 | Verified all /16 | Grounded abstention /4 | Last-review false PASS /16 | False acceptance /16 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen | A | 3 | 0 | 0 | 0 | 0 | 15 | 15 |
| Qwen | B | 12 | 10 | 8 | 10 | 2 | 5 | 4 |
| Qwen | C | 15 | 15 | 12 | 15 | 3 | 1 | 1 |
| Gemma | A | 7 | 5 | 3 | 4 | 2 | 2 | 2 |
| Gemma | B | 12 | 10 | 8 | 9 | 2 | 1 | 1 |
| Gemma | C | 14 | 14 | 10 | 14 | 4 | 2 | 2 |

Paired units are the 12 answerable parents, rather than calls or arms. The
prespecified 2,000 parent-bootstrap resamples give descriptive intervals:

| Model | Metric A−B | Wins / ties / losses | Difference | Bootstrap 95% | All-planned unresolved bounds |
|---|---|---|---:|---|---|
| Qwen | Verified completion | 0 / 4 / 8 | −0.667 | [−0.917, −0.417] | [−0.667, −0.667] |
| Gemma | Verified completion | 0 / 7 / 5 | −0.417 | [−0.667, −0.167] | [−0.417, −0.417] |
| Qwen | False acceptance | 9 / 3 / 0 | +0.750 | [+0.500, +1.000] | [+0.750, +0.750] |
| Gemma | False acceptance | 2 / 9 / 1 | +0.083 | [−0.167, +0.333] | [+0.083, +0.083] |

A positive false-acceptance difference is worse. Grounded abstention is zero on
all answerable pairs, giving a zero difference/interval/bounds for both models.
All pairs were assessed, so the unresolved bounds collapse to the observed
differences. The four insufficient-parent pairs remain separate: Qwen A−B
grounded abstention and verified completion are both −0.500 (0/2/2, interval
[−1.000, 0.000]); false acceptance is +0.500 (3/0/1, interval [−0.500, +1.000]).
Gemma's three differences are zero (0/4/0, zero intervals/bounds). These intervals
do not establish general performance, equivalence or independence across shared
artificial task families.

The 398 main calls all have final usage: 63,197 generated / 320,589 total tokens.
All-planned arm costs include the original load, prefill and generation counters:

| Model | Arm | Calls | Generated | Total | Client s | Load s | Prefill s | Generation s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen | A | 55 | 10,652 | 43,035 | 1,433.502 | 84.521 | 420.256 | 925.288 |
| Qwen | B | 79 | 14,147 | 63,089 | 1,878.999 | 0.212 | 627.422 | 1,246.155 |
| Qwen | C | 32 | 6,647 | 29,879 | 908.016 | 0.088 | 316.739 | 589.056 |
| Gemma | A | 108 | 14,371 | 84,283 | 1,634.310 | 19.976 | 886.188 | 724.070 |
| Gemma | B | 86 | 11,639 | 66,314 | 1,239.095 | 0.273 | 643.431 | 591.907 |
| Gemma | C | 38 | 5,741 | 33,989 | 635.552 | 0.122 | 366.529 | 267.305 |

Success means current verified supported completion. All failures below are
known, independently assessed outcomes. Every unresolved/unexecuted subset has
N=0 and null amounts, rather than zero-cost observations.

| Model | Arm | Subset | Parents | Calls | Generated | Total | Client s | Load s | Prefill s | Generation s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen | A | known_failed | 16 | 55 | 10652 | 43035 | 1433.502 | 84.521 | 420.256 | 925.288 |
| Qwen | A | successful | 0 | 0 | null | null | null | null | null | null |
| Qwen | B | known_failed | 6 | 32 | 5587 | 24574 | 731.125 | 0.088 | 234.609 | 494.265 |
| Qwen | B | successful | 10 | 47 | 8560 | 38515 | 1147.874 | 0.124 | 392.812 | 751.890 |
| Qwen | C | known_failed | 1 | 2 | 549 | 2300 | 72.766 | 0.005 | 23.920 | 48.711 |
| Qwen | C | successful | 15 | 30 | 6098 | 27579 | 835.250 | 0.083 | 292.819 | 540.345 |
| Gemma | A | known_failed | 12 | 80 | 10957 | 62248 | 1183.917 | 0.242 | 628.980 | 551.624 |
| Gemma | A | successful | 4 | 28 | 3414 | 22035 | 450.393 | 19.734 | 257.207 | 172.446 |
| Gemma | B | known_failed | 7 | 36 | 4950 | 25749 | 458.814 | 0.113 | 210.129 | 247.159 |
| Gemma | B | successful | 9 | 50 | 6689 | 40565 | 780.281 | 0.160 | 433.302 | 344.748 |
| Gemma | C | known_failed | 2 | 8 | 1498 | 8249 | 137.751 | 0.023 | 68.800 | 68.589 |
| Gemma | C | successful | 14 | 30 | 4243 | 25740 | 497.801 | 0.099 | 297.729 | 198.715 |

Qwen has no both-successful A/B answerable parents; same-quality token/time
amounts are **null**, rather than zero. Gemma has three: A used 20 calls,
2,529 generated / 15,874 total tokens and 332.033 client seconds; B used 16 calls,
2,576 / 14,307 and 267.171 seconds. Their load/prefill/generation seconds were
A 19.707/184.515/127.095 and B 0.055/133.215/133.219. Load/caching position and
selection of successful pairs limit this comparison. Lower raw Qwen A costs
do not demonstrate savings at equal quality.

In retained Qwen parent `confirmation024r2-L1-1`, A read document-1, integrated
an `unknown` answer citing that rule/M fact, then received reviewer PASS with
no requested sources. The workflow reported satisfaction. Document-2 contained
the available N fact; the independent oracle reported a missing witness and
wrong decision. B and C were correctly grounded and verified on the same parent.
This trace demonstrates one early false-acceptance path, rather than proving
the cause of every failure. Declared host requirements and a model's PASS do not
substitute for factual support; domain acceptance needs an appropriate checker.

## Completed fresh stop-sensitivity comparison

All 64 scheduled trials completed with known termination/usage and independent
assessment, zero pending/unexecuted trials and zero transport/format faults.
Each group below has eight parents (four answerable / four insufficient); these
are repeated designated main parents under fresh keys, not 64 independent parents.
The table's verified and abstention counts use the full eight-parent denominator.

| Model | Stop | Arm | Planned | Executed | Correct | Grounded | Verified | Grounded abstention | Last false PASS | False acceptance | Triggered | Extra callbacks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen | sensitivity-bounded | A | 8 | 8 | 3 | 0 | 0 | 0 | 7 | 7 | 0 | 0 |
| Qwen | sensitivity-bounded | B | 8 | 8 | 6 | 4 | 4 | 2 | 3 | 3 | 0 | 0 |
| Qwen | sensitivity-strict | A | 8 | 8 | 4 | 0 | 0 | 0 | 8 | 8 | 0 | 0 |
| Qwen | sensitivity-strict | B | 8 | 8 | 7 | 5 | 5 | 2 | 3 | 1 | 0 | 0 |
| Gemma | sensitivity-bounded | A | 8 | 8 | 4 | 2 | 1 | 2 | 1 | 1 | 0 | 0 |
| Gemma | sensitivity-bounded | B | 8 | 8 | 6 | 4 | 3 | 2 | 1 | 1 | 0 | 0 |
| Gemma | sensitivity-strict | A | 8 | 8 | 5 | 4 | 3 | 3 | 0 | 0 | 0 | 0 |
| Gemma | sensitivity-strict | B | 8 | 8 | 6 | 4 | 3 | 2 | 0 | 0 | 0 | 0 |

Answerable and truly insufficient strata remain separate:

| Model | Stop | Arm | Stratum | N | Correct | Grounded | Verified | Abstention | False acceptance |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| Gemma | bounded | A | answerable | 4 | 0 | 0 | 0 | 0 | 1 |
| Gemma | bounded | A | insufficient | 4 | 4 | 2 | 1 | 2 | 0 |
| Gemma | bounded | B | answerable | 4 | 2 | 2 | 2 | 0 | 1 |
| Gemma | bounded | B | insufficient | 4 | 4 | 2 | 1 | 2 | 0 |
| Gemma | strict | A | answerable | 4 | 1 | 1 | 1 | 0 | 0 |
| Gemma | strict | A | insufficient | 4 | 4 | 3 | 2 | 3 | 0 |
| Gemma | strict | B | answerable | 4 | 2 | 2 | 2 | 0 | 0 |
| Gemma | strict | B | insufficient | 4 | 4 | 2 | 1 | 2 | 0 |
| Qwen | bounded | A | answerable | 4 | 0 | 0 | 0 | 0 | 4 |
| Qwen | bounded | A | insufficient | 4 | 3 | 0 | 0 | 0 | 3 |
| Qwen | bounded | B | answerable | 4 | 2 | 2 | 2 | 0 | 2 |
| Qwen | bounded | B | insufficient | 4 | 4 | 2 | 2 | 2 | 1 |
| Qwen | strict | A | answerable | 4 | 0 | 0 | 0 | 0 | 4 |
| Qwen | strict | A | insufficient | 4 | 4 | 0 | 0 | 0 | 4 |
| Qwen | strict | B | answerable | 4 | 3 | 3 | 3 | 0 | 0 |
| Qwen | strict | B | insufficient | 4 | 4 | 2 | 2 | 2 | 1 |

The bounded policy triggered **zero times**, with **zero extra callbacks**, in
every group. Consequently this run does not estimate its recovery benefit or
selector-by-recovery interaction. Fresh strict/bounded outcomes can differ through
generation variability and cache/order position despite temperature zero and
fixed seeds; a policy that never activated cannot explain those differences.
It only covers known-use eligible states and cannot discharge unknown use.

| Model | Stop | Metric | Planned parents | Assessed pairs | Wins | Ties | Losses | A−B | Bootstrap 95% | Unresolved bounds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen | sensitivity-bounded | false_acceptance | 8 | 8 | 5 | 2 | 1 | 0.500 | [0.000, 1.000] | [0.500, 0.500] |
| Qwen | sensitivity-bounded | grounded_abstention | 8 | 8 | 0 | 6 | 2 | -0.250 | [-0.500, 0.000] | [-0.250, -0.250] |
| Qwen | sensitivity-bounded | verified_supported_completion | 8 | 8 | 0 | 4 | 4 | -0.500 | [-0.875, -0.125] | [-0.500, -0.500] |
| Qwen | sensitivity-strict | false_acceptance | 8 | 8 | 7 | 1 | 0 | 0.875 | [0.625, 1.000] | [0.875, 0.875] |
| Qwen | sensitivity-strict | grounded_abstention | 8 | 8 | 0 | 6 | 2 | -0.250 | [-0.500, 0.000] | [-0.250, -0.250] |
| Qwen | sensitivity-strict | verified_supported_completion | 8 | 8 | 0 | 3 | 5 | -0.625 | [-0.875, -0.250] | [-0.625, -0.625] |
| Gemma | sensitivity-bounded | false_acceptance | 8 | 8 | 1 | 6 | 1 | 0.000 | [-0.375, 0.375] | [0.000, 0.000] |
| Gemma | sensitivity-bounded | grounded_abstention | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Gemma | sensitivity-bounded | verified_supported_completion | 8 | 8 | 0 | 6 | 2 | -0.250 | [-0.625, 0.000] | [-0.250, -0.250] |
| Gemma | sensitivity-strict | false_acceptance | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Gemma | sensitivity-strict | grounded_abstention | 8 | 8 | 1 | 7 | 0 | 0.125 | [0.000, 0.375] | [0.125, 0.125] |
| Gemma | sensitivity-strict | verified_supported_completion | 8 | 8 | 2 | 4 | 2 | 0.000 | [-0.500, 0.500] | [0.000, 0.000] |

| Model | Arm | Metric | Planned parents | Assessed pairs | Wins | Ties | Losses | Bounded−strict | Bootstrap 95% | Unresolved bounds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen | A | false_acceptance | 8 | 8 | 0 | 7 | 1 | -0.125 | [-0.375, 0.000] | [-0.125, -0.125] |
| Qwen | A | grounded_abstention | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Qwen | A | verified_supported_completion | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Qwen | B | false_acceptance | 8 | 8 | 2 | 6 | 0 | 0.250 | [0.000, 0.625] | [0.250, 0.250] |
| Qwen | B | grounded_abstention | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Qwen | B | verified_supported_completion | 8 | 8 | 0 | 7 | 1 | -0.125 | [-0.375, 0.000] | [-0.125, -0.125] |
| Gemma | A | false_acceptance | 8 | 8 | 1 | 7 | 0 | 0.125 | [0.000, 0.375] | [0.125, 0.125] |
| Gemma | A | grounded_abstention | 8 | 8 | 0 | 7 | 1 | -0.125 | [-0.375, 0.000] | [-0.125, -0.125] |
| Gemma | A | verified_supported_completion | 8 | 8 | 0 | 6 | 2 | -0.250 | [-0.500, 0.000] | [-0.250, -0.250] |
| Gemma | B | false_acceptance | 8 | 8 | 1 | 7 | 0 | 0.125 | [0.000, 0.375] | [0.125, 0.125] |
| Gemma | B | grounded_abstention | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |
| Gemma | B | verified_supported_completion | 8 | 8 | 0 | 8 | 0 | 0.000 | [0.000, 0.000] | [0.000, 0.000] |

| Model | Stop | Parents × arms | Calls | Generated | Total | Client s | Load s | Prefill s | Generation s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen | sensitivity-bounded | 16 | 69 | 12714 | 54435 | 1759.671 | 102.675 | 524.329 | 1128.171 |
| Qwen | sensitivity-strict | 16 | 65 | 11969 | 49188 | 1631.313 | 111.401 | 457.063 | 1058.379 |
| Gemma | sensitivity-bounded | 16 | 98 | 13213 | 74912 | 1404.905 | 19.203 | 727.437 | 654.462 |
| Gemma | sensitivity-strict | 16 | 100 | 12987 | 76336 | 1427.692 | 19.469 | 745.882 | 658.529 |

These parent-bootstrap intervals are descriptive and use the frozen 2,000
resamples. Every pair is assessed, so unresolved bounds collapse to the observed
difference. Costs include all original load/prefill/generation counters, rather
than only successful trials. Both stop policies retain the same maximum budgets.

## Corrective pre-confirmation gates

Its two warm rounds produced 12 known generation receipts and two empty-load
receipts (2,696 generated / 18,507 total tokens). Qwen changed `yes` to `no` after
the N fact changed and passed both reviews. Gemma initially gave an incorrect
`unknown`, rejected by its reviewer; its changed-fact round gave `no`/PASS. Qwen
was already resident for this repeated preload (0.032 s), so that operation is
not a new cold-load measurement. The retained initial cold observations below
remain separate. No additional prompt/cap tuning was performed.

The new development pilot has four parents (three answerable, one insufficient),
24 trials and 92 known paid calls (14,373 generated / 69,368 total tokens).

| Model | Arm | Parents | Correct | Grounded correct | Verified supported | Calls |
|---|---|---:|---:|---:|---:|---:|
| Qwen | A | 4 | 1 | 0 | 0 | 13 |
| Qwen | B | 4 | 3 | 2 | 2 | 19 |
| Qwen | C | 4 | 4 | 4 | 4 | 8 |
| Gemma | A | 4 | 1 | 1 | 1 | 23 |
| Gemma | B | 4 | 2 | 2 | 2 | 19 |
| Gemma | C | 4 | 4 | 4 | 4 | 10 |

There were no transport/format faults or false acceptances in this pilot. These
development parents do not enter the primary denominator. The raw scope-defect
warm/partial-pilot history was stopped before this pilot and remains separate.

Actual template/tokenizer checks covered 1,335 public/previously paid inputs:
Qwen's maximum input plus full output cap was 4,612, Gemma's 4,222, within 8,192.
There were zero generation requests and two charged empty preloads. The new
[freeze](../experiments/ollama/results/freeze-v0.2.4-r2.json) pins measured source
`23dff942cfbbc76d73799893acaa3a394d70621f`, 16 parents, 96 main keys and 64 fresh
sensitivity keys. Its SHA256 is
`3860d9d89f3ca0eeb1e5db6a24612a1d11075b44dde6d9b300244cc90c5a579c`.
The 24-parent proposal exceeds the generated-token envelope even before past
costs. The 16-parent forecast reserves 3,276,800 future generated tokens against
3,841,937 remaining, with 146,354.53 s of the original clock left. Its conservative
paid-development timing forecast is Qwen 62.058 s / Gemma 50.702 s per request;
one interrupted development sampling record uses the observed maximum overhead.
Selection uses resources, never A−B results.

## Retained initial-protocol development history

The initial frozen confirmation completed, but its verified-completion results
were invalidated by a mechanical receipt defect: the host inserted optional
empty `feedback` defaults into model evidence, while the unchanged oracle
required exact actual-response identity. This particularly affected Gemma's
omitted field. The initial worker and owned server were stopped with no pending
or unknown usage. All 957 calls and their costs remain retained.

Corrective protocol `egr-024-local-ollama-v2` preserves the actual parsed JSON,
unchanged review/oracle criteria and cumulative campaign limits. Fresh public
instances and a new confirmation freeze are required; initial results are not
pooled with the corrective confirmation. The initial development observations
below remain historical, rather than corrected or replaced model outputs.

Both current local models completed two reader/integrator/reviewer rounds,
including a longer input and a changed Q fact. Every operation has a known
receipt. In earlier development, Qwen's first integration produced an incorrect
unknown answer and its reviewer accepted it; syntax completion is not correctness.
Earlier development outputs and expenses remain in the same ledger.

The retained initial development protocol is `egr-024-local-ollama-v1`. Its
freeze followed calibration and pilot. All original results are archived
separately; they do not contribute to the corrective main denominators.

## Actual models and finite profile

The owned server is Ollama 0.35.0 on Windows x64, Ryzen 7 8840HS, 64 GiB RAM.
Server logs show CPU inference, zero GPU offload and `size_vram=0`.

| Exact local tag | Reported weights | Digest |
|---|---|---|
| `qwen3.6:35b-a3b` | 36B, Q4_K_M | `07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522` |
| `gemma4:e4b` | Custom 7.5B, Q4_K_M | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |

Gemma's parent is `gemma4-validation-20260929:e4b-imatrix-attention-q6-q8-draft2`.
Actual metadata, templates and model licenses are retained separately from the
Apache-2.0 package license. No weights, template, quantization or server update
was made. Arms are compared within each model. Absolute timing across models
does not establish a brand ranking.

Nonstream transport uses 30-second connect and independent full-response hard
deadlines: Qwen 1,800 seconds, Gemma 900, preload 1,800. Context is 8,192,
temperature zero, `think:false`, `truncate:false`, `shift:false`, and 60-minute
residency. First-token latency is unmeasured. The server applies local-only,
one parallel inference/loaded model/queue entry, and a 30-minute load-stall
detector. The detector is not a request deadline; see the pinned
[ChatHandler source](https://github.com/ollama/ollama/blob/v0.35.0/server/routes.go).

Three development cycles retained six empty preloads and 36 warm generation
requests, all with known usage. Each model completed six final-cycle warm
reader/integrator/reviewer requests, including 100 irrelevant memo lines and a
changed Q fact. Earlier wrong unknown answers and false review acceptances remain.

Final-cycle empty-preload client waits were Qwen **102.110 s** and Gemma
**19.687 s**. Their zero-token receipts do not expose server duration counters,
so these are client cold waits, not separately measured server load CPU time.
Warm timings below list round 0 / the longer changed-fact round 1, in seconds:

| Model | Stage | Client wall | Server prefill | Server generation |
|---|---|---:|---:|---:|
| Qwen | reader | 24.219 / 36.875 | 3.955 / 23.405 | 20.235 / 13.403 |
| Qwen | integrator | 28.766 / 39.453 | 7.888 / 17.144 | 20.812 / 22.284 |
| Qwen | reviewer | 16.578 / 32.141 | 8.676 / 28.872 | 7.852 / 3.180 |
| Gemma | reader | 19.594 / 39.750 | 4.240 / 24.078 | 15.315 / 15.634 |
| Gemma | integrator | 22.328 / 19.297 | 10.453 / 7.246 | 11.845 / 12.022 |
| Gemma | reviewer | 11.813 / 32.765 | 10.333 / 30.469 | 1.432 / 2.271 |

Warm generation receipts report approximately 0.002–0.003 s load duration.
This cycle still used review cap 512; the selected 2,048 cap was subsequently
checked in the final matrix and pilot. Both models' final integration changed
from yes to no when Q changed from true to false. This demonstrates input-sensitive
calls in these examples, not general semantic reliability.

The campaign has 48 hours from first reservation, including development/waits,
4,000 calls, 4 million generated / 40 million total tokens, and 4 GiB raw. Free
RAM must stay above 6.4 GiB here; disk needs 5 GiB plus raw margin. Four known
consecutive swap increases totaling 256 MiB, or an unknown observation, block
dispatch. These samples do not measure every transient resource peak.

Final caps are reader 1,024, integrator 1,536, reviewer **2,048**, repair 1,024.
All arms/models have ten paid calls, 32 SDK actions, 16 verifications; trial wall
is Qwen 7,200 / Gemma 3,600 seconds. The derived SDK token budget is **102,400**.
The outer transport ceiling is 122,880 (ten context-plus-4,096 reservations).
Protocol 97,280 is the initial context-plus-1,536 budget, not the selected budget.
Full context-plus-stage-cap reservations are separate from actual API counters.

## Final review schema × cap calibration

There are 24 answer cases over **12 underlying artificial parents**, nine valid
and 15 invalid candidates per cell. Correct yes/no/grounded unknown, wrong
answers, fake/irrelevant quotations, stale versions and false insufficient-world
completion are included. Labels never enter reviewer inputs. Eight cells give
192 fresh requests; all have final usage. Cases are not independent parents.

| Model | Schema | Cap | Valid /24 | Last 20 valid | Length | False PASS /15 | Grounded unknown PASS /3 |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen | old | 512 | 21 | 17 | 3 | 9 | 0 |
| Qwen | old | 2,048 | 24 | 20 | 0 | 9 | 0 |
| Qwen | compact | 512 | 24 | 20 | 0 | 11 | 1 |
| Qwen | compact | 2,048 | 24 | 20 | 0 | 11 | 1 |
| Gemma | old | 512 | 13 | 11 | 11 | 3 | 0 |
| Gemma | old | 2,048 | 24 | 20 | 0 | 9 | 0 |
| Gemma | compact | 512 | 24 | 20 | 0 | 14 | 0 |
| Gemma | compact | 2,048 | 24 | 20 | 0 | 13 | 0 |

Compact status/reason enums, at most four requests and optional 160-character
feedback change schema and instructions together: a compound intervention.
Larger old caps and compact review improve formal completion; semantic false
PASS remains substantial. Partial/length output never grants PASS.

Valid-candidate acceptance was Qwen old 4/9 at either cap and compact 6/9;
Gemma old 512 was 3/9, and its other cells were 6/9. The old 512 cells had
one Qwen and seven Gemma invalid candidates with no schema-valid verdict.
All larger-cap/compact cells had zero such missing verdicts. False PASS uses
the 15 planned invalid candidates, so a truncated response is not a correct
semantic rejection or evidence of a better reviewer.

The prespecified choice requires at least 19/20 valid in both models, minimizes
compact false PASS across models, then cap. It chooses 2,048 (24 false PASS
versus 25 at 512), without A−B outcomes. The one-case difference is not evidence
of a general semantic benefit. Fixed blocks and shared prompt/KV cache confound
latencies; faster later 2,048 cells do not establish a causal speed improvement.
No generated answer is reused between arms or requests.

The final choice was restricted to the compact output contract. Old 2,048 had
18 combined false PASS across the two models, versus compact 2,048's 24.
Selecting the compact contract therefore does not identify the best overall
semantic-review cell; its operational contract and false-positive limitation
remain explicit.

An earlier 192-request matrix preceded the final explicit task contracts. Its
original bank, implementation and 29,167 generated / 149,483 total tokens remain
separately retained; it is not pooled into this final matrix. At final calibration
completion, development totaled 426 calls, 66,828 generated / 352,381 total tokens.

## Common methods and independent oracle

A is EGR ordering; B uses the same public runner, feasible pool, authority, views,
callbacks, budgets and stops, prioritizing executable checks then public catalogue
retrieval. Their comparison measures extra ordering value within shared machinery.
A/B skip only explicit byte-identical same-origin/version/topic copies; requested
copies and different information remain. C receives all public documents with the
same trial/stage/repair limits, as a different-information-arrival reference.

New tasks state necessary-and-sufficient rules, closed factual universes, current
authority, exceptions, report thresholds, destinations and deadlines. Missing
facts are not false facts. Evaluation-only gold checks finite minimal witnesses,
literal spans, scoped equivalents and proven identical copies, versions, origins
and currently issued receipt bindings. It does not use model PASS as truth or
router private predicates. Witness alternatives preceded pilot/main outcomes;
the retained 52-record identity check shows unchanged public/canonical inputs.

Answer correctness, grounding independent of review, and current verified
supported completion are distinct. The last maps to the old
`evidence_supported_completion` name. Grounded world-unknown, UNKNOWN reviewer,
unknown usage and unexecuted trials remain distinct. A recorded check is not a
semantic guarantee; a short fixed workflow may suffice when all records fit.

`output_schema_valid` describes the final parsed integration answer; the separate
all-call field retains earlier formatting failures. Trial `reviewer_false_pass`
compares the last review with the final independently grounded answer. It is not
an all-intermediate-review count. `false_acceptance` means the workflow claimed
completion but the independent oracle did not support it; `router_satisfied` is
recorded separately. Grounded abstention is a correct supported unknown-world
answer, independent of review. `erroneous_stop` labels an assessed incomplete
answerable trial; it is not, by itself, a causal diagnosis of the stop rule.

`answer_correct` compares the final yes/no/unknown decision with the authored
truth. Grounding additionally checks finite scoped support sets, quotations,
versions and issued bindings. Arbitrary free-form explanation text is not fully
evaluated by a general natural-language entailment system.

Primary settings were frozen after the four-parent/24-trial pilot and actual
template/tokenizer input-room checks. The balanced 16-parent profile fits
speed/resources including 64 fresh sensitivity trials. One seed per
parent/model/arm, shuffled parents, counterbalanced arms, Qwen first and 2,000
prespecified parent-bootstrap resamples are used. Small-N intervals are descriptive.

The 16 selected parents include 12 answerable and four insufficient worlds,
four per family. Predetermined parents 4/5 in each family are excluded before
confirmation; their XOR, waiver, explicit exception, destination and other
variants are not live-confirmed here. Task families are shared with development;
fresh instances are not held-out reasoning families. The retained initial
pilot/context analysis remains in the raw history and
[initial results](../experiments/ollama/results/v0.2.4-initial/summary.json).
Its 95 paid pilot calls cost 12,621 generated / 69,525 total tokens. Its Gemma
verification counts are affected by the receipt defect and cannot establish a
semantic capability floor. The scope-consistent 92-call pilot and 1,335-input
context check above are the actual corrective pre-confirmation gates.

The observed-time forecast is a planning estimate, not a guarantee that all
maximum waits fit. Eighty trials per model at maximum trial clocks alone sum
to 240 hours, exceeding 48 hours; per-request deadlines cannot all be exhausted.
Every dispatch checks the original remaining wall/call/token limits. Exhaustion
would leave unstarted keys unexecuted, without extending the frozen budget.

## Measurement and publication boundary

The measured ordinary outside-checkout candidate wheel SHA256 is
`715b2785d3dab1f8b2b7076f8307efdc7fa6105547e5fbf5f0093b4701dec80c`;
its 25-file runtime fingerprint is
`cd0ac5397f5636fb797e9ec5e64ae740bbc3d4130b120d5c4ed73fd8ade4fbc9`.
Runtime/harness bytes use exact canonical Git LF equality. The corrective main
freeze binds implementation `23dff942cfbbc76d73799893acaa3a394d70621f`;
its SHA256 is
`3860d9d89f3ca0eeb1e5db6a24612a1d11075b44dde6d9b300244cc90c5a579c`.
Main and sensitivity outcomes and the custom example are completed observations.
The final source snapshot precedes native CI and public upload/download checks.
Their actual run IDs, final commit, shipping wheel/sdist hashes and post-publication
results are recorded in the [Release verification](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.4/publication-verification-v0.2.4.json),
not guessed in a self-referential source commit.
The old v0.2.3 unknown Qwen request stays unknown in its original ledger.

See [the source-level guide](ollama-guide.md), [audit](audit-024.md) and
the [archived v0.2.3 experiment](ollama-experiment.md).

## Campaign expenditure, example and normal cleanup

The complete cumulative journal has **1,835 reservations / 1,835 known usage
receipts**, including 14 empty-load operations. Generated tokens are **272,592**,
prompt-plus-generated tokens **1,446,319**. Pending, usage-unknown and
terminated-unmetered calls are all zero, with no outstanding token reservations.
The original clock and all invalidated development expenses remain retained:

| Retained scope | Calls | Generated | Total | Empty loads |
|---|---:|---:|---:|---:|
| Initial protocol v1, including invalidated confirmation | 957 | 133,726 | 742,263 | 8 |
| Pre-freeze corrective scope defect | 34 | 7,268 | 37,450 | 2 |
| Scope-consistent corrective v2 | 844 | 131,598 | 666,606 | 4 |

The independent trial tables use only the appropriate frozen phase. Neither the
1,835 operations nor their model calls are independent statistical parents.
Recorded client wait sums to 34,183.476 s; observed server load/prefill/generation
sums are 1,125.232 / 13,636.878 / 18,631.076 s. Empty-load receipts do not supply
all server duration counters, so these are observed component sums, not estimates
of missing time. Controller pre/post resource sampling separately accounts for
2,789.252 s across 1,833 resource records; it excludes model wait and other work.
The whole campaign clock at normal cleanup was **43,933.079 s (12.204 h)**,
including development and waits. These scopes overlap and must not be added as
mutually exclusive elapsed-time components. Publication work follows this cleanup.

Of 3,666 before/after resource observations, available memory is known in 3,666
and swap in 3,226; historical missing swap samples remain missing. The observed
minimum free RAM is 9,189,036,032 bytes, maximum known swap 133,169,152 bytes,
and minimum pre-dispatch free disk 639,348,342,784 bytes. Host snapshots do not
measure transient peaks, physical speculative work, energy, prices or CO2.

The documented artificial temperature callback used a new healthy journal key
and **six actual paid requests**, 449 generated / 3,271 total tokens, with 71.453 s
client wall. The public specification permits the measured 9°C iff it is at most
10°C. Gemma returned `yes` with both specification and measurement citations;
domain stop was satisfied, runner stop was `router_stopped`, with no pending call.
This is a connectivity/callback example, not another independently scored main
parent. The optional mixed-model experiment was not performed.

All **100** independently incomplete chains are preserved in
`raw/diagnostics/failure-chains.json`: 11 pilot, 44 main and 45 sensitivity.
They retain original documents, extracted records, integration/review calls and
stop/receipt states for every incomplete corrective trial, without changing scores.
The new owned server epoch and descendants were stopped using held native process
handles and verified exit. Shared servers were untouched. Cleanup dispatched no
model request. The old v0.2.3 unknown-cost Qwen call remains unknown in its original
ledger with its 512 generated / 4,608 total-token reservation retained.

## Raw export and model-free reanalysis

The privacy-checked export preserves actual public journal/model-output bytes;
it explicitly excludes five operational private/log/lock files and contains no
weights. Its distinct export identity and exclusions are recorded in the ZIP.
It has **5,785** verified manifest entries and **25,666,393** compressed bytes.
Raw ZIP SHA256:
`274de4b2a99119829fded7a30e7b9bf6bb47179f1ad69b1e5289aa680f6e726f`.

The [provenance](../experiments/ollama/results/v0.2.4/artifact-provenance.json)
records creation and local checks at the source snapshot. Upload and a new public
download are separate stages. Obtain `ollama-raw-v0.2.4.zip` and
`OLLAMA_RAW_SHA256SUMS` from the
[v0.2.4 Release](https://github.com/kadubon/evidence-gap-router/releases/tag/v0.2.4)
and use the matching tag's source checkout with an ordinary installed SDK:

```sh
python -m pip install evidence-gap-router==0.2.4
python -I scripts/extract_ollama_raw.py "ollama-raw-v0.2.4.zip" "raw-024" --sha256 274de4b2a99119829fded7a30e7b9bf6bb47179f1ad69b1e5289aa680f6e726f
python -I raw-024/supplemental/reanalyze_ollama_024.py "raw-024" "analysis-024"
```

These commands also work in PowerShell with Python >=3.12; destinations must be
new, and analysis must be outside the extraction directory. The extractor checks
path/size/case/ADS/symlink boundaries. Reanalysis verifies every manifest hash,
the exact frozen harness/protocol/runtime and four byte-equal outputs:
`summary.json`, `scored-trials.json`, `scored-trials.csv`, `failure-analysis.json`.
It makes **zero model requests**. Calibration and provenance remain separate saved
records; they are not synthesized as live results by reanalysis.
