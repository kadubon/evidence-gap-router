# Local Ollama experiment — v0.2.4

Calibration and the separate 24-trial pilot have completed. The frozen 16-parent
confirmation is running, followed by 64 fresh stop-policy trials. Qwen completes
the current CPU measurement path. That is not a routing advantage.

Both current local models completed two reader/integrator/reviewer rounds,
including a longer input and a changed Q fact. Every operation has a known
receipt. In earlier development, Qwen's first integration produced an incorrect
unknown answer and its reviewer accepted it; syntax completion is not correctness.
Earlier development outputs and expenses remain in the same ledger.

The current frozen-development protocol is `egr-024-local-ollama-v1`; confirmation
freeze follows calibration and pilot. This page will report actually executed
phase counts, denominators, paired outcomes and public artifact verification.
It does not claim pending publication or primary measurements as complete.

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
was made. Model-within-arm differences are the comparison, not brand rankings.

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

The prespecified choice requires at least 19/20 valid in both models, minimizes
compact false PASS across models, then cap. It chooses 2,048 (24 false PASS
versus 25 at 512), without A−B outcomes. The one-case difference is not evidence
of a general semantic benefit. Fixed blocks and shared prompt/KV cache confound
latencies; faster later 2,048 cells do not establish a causal speed improvement.
No generated answer is reused between arms or requests.

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

Primary settings were frozen after the four-parent/24-trial pilot and actual
template/tokenizer input-room checks. The balanced 16-parent profile fits
speed/resources including 64 fresh sensitivity trials. One seed per
parent/model/arm, shuffled parents, counterbalanced arms, Qwen first and 2,000
prespecified parent-bootstrap resamples are used. Small-N intervals are descriptive.

### Completed pilot and context checks

| Model | Arm | Terminal /4 | Answer correct /4 | Grounded independent of review /4 | Verified complete /4 | Paid calls |
|---|---|---:|---:|---:|---:|---:|
| Qwen | A | 4 | 1 | 0 | 0 | 12 |
| Qwen | B | 4 | 3 | 2 | 1 | 19 |
| Qwen | C | 4 | 4 | 4 | 4 | 8 |
| Gemma | A | 4 | 2 | 2 | 0 | 29 |
| Gemma | B | 4 | 4 | 4 | 0 | 19 |
| Gemma | C | 4 | 4 | 3 | 0 | 8 |

All 95 pilot calls have known usage: 12,621 generated / 69,525 total tokens.
One Qwen B trial retains a schema fault and its paid repair. C shows a usable
Qwen path and a Gemma final-acceptance floor despite mostly grounded answers;
Gemma routing results therefore remain diagnostic. No criterion was lowered.
These four development parents are excluded from primary denominators.

The pinned debug-render branch returns before inference. Its rendered template
and the actual owned llama-server tokenizer checked 765 full-public base and
previously paid inputs, with full output-cap room: maxima Qwen 3,506 and Gemma
3,630 versus context 8,192. Two empty preloads were charged, zero generation
requests made. This does not assert arbitrary maximum-length schema strings fit;
dynamic over-context input is rejected by `truncate:false`/`shift:false`.

Freeze selects 16 parents: 12 answerable / four insufficient, four per family,
96 main trials and 64 fresh sensitivity trials. Under ten calls/trial and the
maximum selected cap 2,048, the 24-parent plan would reserve 4,259,840 generated
tokens before development, exceeding four million. The 16-parent plan bounds
future generated tokens at 3,276,800; 3,920,551 remain at freeze. This is a
resource decision, not an A−B result decision. Predetermined parents 4/5 in each
family are excluded before confirmation; their XOR, waiver, explicit exception,
destination and other variants are not live-confirmed here. Task families are
shared with development; fresh instances are not held-out reasoning families.

## Measurement and publication boundary

The measured ordinary outside-checkout candidate wheel SHA256 is
`715b2785d3dab1f8b2b7076f8307efdc7fa6105547e5fbf5f0093b4701dec80c`;
its 25-file runtime fingerprint is
`cd0ac5397f5636fb797e9ec5e64ae740bbc3d4130b120d5c4ed73fd8ade4fbc9`.
Runtime/harness bytes use exact canonical Git LF equality. Main freeze binds
implementation `bb6304e2f8b58b98feb9ce3010a0b8e2055eae57`; freeze SHA256 is
`f4268bcd25bac6d1d152e2d59e6f06bce61f967be1373cad9d553623297d4061`.
Final main/sensitivity outcomes, custom live example, native CI and public
downloads are pending at this source snapshot.
The old v0.2.3 unknown Qwen request stays unknown in its original ledger.

See [the source-level guide](ollama-guide.md), [audit](audit-024.md) and
the [archived v0.2.3 experiment](ollama-experiment.md).
