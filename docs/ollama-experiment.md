# Local Gemma/Qwen experiment for v0.2.3

This report records a scoped v0.2.2 SDK audit and a real local-model experiment
using short artificial Japanese documents. Confirmation ended partially: Gemma
completed its 24 arm trials, with A/B each supporting 1/6 answerable parents;
Qwen's first formal reader call timed out, leaving unknown consumption and no
assessed A/B pair. The configured global budget was not exhausted. These data
do not establish a routing benefit or comparable-success cost saving. The
development pilot remains descriptive. Sampled resource observations and the
completed local raw bundle are reconciled below. This is a pre-publication
measurement snapshot; actual publication verification is recorded separately.

The question is whether EGR's choice of the next acquisition/check helps under
incomplete model extraction, integration and review. It is assessed within each
model against a strong verify-first selector using the same public runner. A
pooled-document reference tests a different information-arrival policy. Model
PASS, schema validity and SDK satisfaction are not the independent gold score.

## Audit and executed prerequisites

The starting point was the unchanged public v0.2.2 release commit
`eff875d4c391c476fbe5af43ab4cd7928b7e0ca3`. Its newly downloaded official wheel
had SHA256
`6f417e5664513a5a3125051642dab46b85065f74ab5f669b999a24a79ae7bbc5`.
The [audit report](audit-022.md) records fresh baseline execution and the
14-case public-SDK diagnostic. Its only reproduced fix was the documented
continuation example's import: the helper is imported from `sdk_example`, not
the package root. The review did not establish an acceptance defect requiring
a runtime algorithm change. Default `run` still preserves paid work and stops
on semantic `no_progress`; fresh IDs alone do not establish progress.

| Actually executed prerequisite | Observation |
| --- | --- |
| Original source baseline, before the version edit | 428 passed; no skips |
| Original-commit tests with the ordinary public v0.2.2 wheel | 428 passed; no skips |
| Public-SDK audit with actual issued receipts | 14/14 expected properties; no case exceptions |
| Frozen v0.2.3 source on Windows Python 3.12.14 | 630 passed |
| Frozen source on WSL Linux Python 3.12.14 | 621 passed; 9 Windows Job Object checks skipped |
| Ordinary candidate-wheel Windows runtime regressions | 296 passed, plus SDK/CLI smoke |
| Candidate-wheel portable experiment contracts | 172 passed; ephemeral fake HTTP only |
| Candidate-wheel model-free benchmark smoke | 44 trials, 4 proof cells and 3 helper cells passed |

The two complete 428-test baseline suites include source-side orchestration
tests from an external original archive; they are not 428 installed-only runtime
regressions. The candidate runtime imported from an ordinary external
environment's site-packages, outside the checkout. The 172 fake tests exercise
HTTP, strict output, budget, journal, oracle and resume contracts, including
known format errors, unknown consumption, pending and the explicit wall-budget
amendment. They are not measured Gemma/Qwen inference results. Six-platform
release CI remains a separate, not-yet-verified stage in this report snapshot.

## Observed environment and local execution

Real inference is on one Windows machine. The hardware identity snapshot was
taken at `2026-10-05T12:30:46.3530634Z`, during confirmation, without changing
configuration. It records Windows 11 Home build 26300, AMD64, an AMD Ryzen 7
8840HS with 8 cores/16 logical processors and two 32-GiB memory banks: 64 GiB
installed. The resource preflight reports 66,363,183,104 OS-visible bytes.
Python is 3.12.14, Pydantic 2.13.5 and pydantic-core 2.46.5; the matched lock
also pins annotated-types 0.8.0, typing-extensions 4.16.0 and
typing-inspection 0.4.4.

The graphics-device record is AMD Radeon 780M, driver `32.0.21010.10`.
Its WMI `AdapterRAM=2147483648` is device metadata, not the inference VRAM
allocation, a hard ceiling or a peak measurement. Free disk in the hardware
snapshot was 642,895,974,400 bytes. This single-host record establishes neither
portable live-model performance nor a controlled model-brand speed comparison.

An owned Ollama **0.35.0** server listens on `127.0.0.1:11435`. Its startup
actually inherited `OLLAMA_NO_CLOUD=1`, `OLLAMA_NUM_PARALLEL=1`,
`OLLAMA_MAX_LOADED_MODELS=1` and `OLLAMA_MAX_QUEUE=1`. Supplied-server log
inspection found cloud disabled and the matching listener/version. The existing
server on port 11434 was left in place. Exact existing local tags were used;
there was no model download, update, remote model or cloud fallback. The first
metadata-only preflight at `2026-10-05T10:55:21.415533Z` made zero generation
and model-load requests, found both tags, empty remote fields, no loaded models
and no resource blocking reason. Subsequent backend smoke, rather than that
metadata preflight, establishes actual generation.

| Supplied local tag | Recorded family/size/quantization | Exact model digest |
| --- | --- | --- |
| `gemma4:e4b` | `gemma4`, 7.5B, `Q4_K_M` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |
| `qwen3.6:35b-a3b` | `qwen35moe`, 36.0B, `Q4_K_M` | `07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522` |

These are the `/api/tags` and sanitized `/api/show` observations, including the
exact existing names; parameter counts are not inferred from tag spelling.
Model metadata advertises thinking values `[false,true]`, with a true default.
All experiment requests explicitly use `think:false`. Metadata, template,
parameters, modelfile and license hashes are retained. The observed license
texts begin with Apache License 2.0, but model terms are recorded separately
from this project's license; neither weights nor private modelfile paths are
distributed with the report.

A post-run read-only `/tags`/`/show` observation at
`2026-10-05T13:08:28.0991008Z`, on the preserved port-11434 server, confirmed both
frozen digests without generation or weight modification. Gemma's recorded
`parent_model` is
`gemma4-validation-20260929:e4b-imatrix-attention-q6-q8-draft2`; Qwen's is empty.
Gemma is therefore an existing custom local variant, not an assumed stock
official build. This later metadata confirmation is distinct from the
pre-confirmation freeze and does not independently prove how the weights were
built. The safe record retains response hashes and excludes private paths.

### CPU evidence and its limits

The saved safe observation is scoped to an **owned Ollama stderr snapshot**.
The selected timestamped line at `2026-10-05T19:28:26.845+09:00` explicitly
records `msg="inference compute" library=cpu`. Untimestamped loader lines
record Gemma CPU model/KV/compute buffers of 4242.76/64.00/117.02 MiB and
Qwen buffers of 9196.26/80.00/76.02 MiB. Their preceding timestamp contexts
are `20:34:49.725+09:00` and `20:35:08.639+09:00`, respectively; those are
not timestamps carried by the buffer lines themselves. Each value is an
individual allocation, not a total, peak, process RSS or memory limit.

Both loaded-model observations reported `size_vram=0`. The log setting
`gpu_layers=-1` is a requested configuration value, not an actual offloaded
layer count; actual offload layers remain unknown/null. The CPU backend is
explicitly observed, while a whole-server/GPU hard memory ceiling, continuous
peak and energy use are not established. Private paths, proxy values, complete
environment and full server logs are excluded from the public-safe evidence.

The safe snapshot was read at
`2026-10-05T11:48:28.7818288Z`–`11:48:28.8375535Z`: 407,560 original bytes,
SHA256 `7312ba8b9bb81f30847405c89fb228803afd1519e4810d52f2dbaa09ff10ee54`.
The ten-excerpt JSON record is 5,213 bytes, SHA256
`28e8ff797f81f6e46cd17bb1c4afdc805eb9f31b14de12c923d066251b525302`.
The original log is private; a hash of its snapshot is not disclosure of its
contents or a signed attestation.

## Methods, tasks and scoring

Each model receives the same artificial parent tasks. L1 requires integration
of distributed conditions; L2 includes duplicate origins and disagreement;
L3 includes versions, changes and exceptions; L4 supplies simple and genuinely
underdetermined controls. The development set contains four parents, one per
family: three answerable and one insufficient. The frozen confirmation profile
contains eight different parents, two per family: six answerable and two
insufficient. These small authored inputs are not a representative population,
an external benchmark reproduction or 48 independent parent tasks.

| Arm | Execution and information contract |
| --- | --- |
| A, EGR | Default selector chooses from the shared finite candidate pool. |
| B, strong verify-first | Same public `run`, pool, permissions, views, callbacks, costs and stops; necessary feasible verification is preferred, then an unread document in the fixed public catalogue order. |
| C, pooled reference | All available documents enter the central workflow together. Fixed public `step` issuance, review and bounded correction preserve receipts/costs; EGR gap ranking does not choose which documents C sees. |

A/B share `feasible_actions`, including its necessity/helper gates. Thus their
difference is selector ordering conditional on this mechanism, not EGR's entire
stack against an independent scheduler. Both retain the default `no_progress`
stop. C has a different document-arrival policy and fixed workflow; its SDK
receipts and domain observations are retained, but it is reported as a reference,
not a theoretical upper bound or an identical-information scheduler arm.

The reader sees only its supplied public documents and schema. Integration and
review see actually available information and pinned related inputs. The
factory, prompts, selector and callbacks receive `PublicTask`, never
`GoldTask`. Source digest, version and origin are host-supplied; role names or
multiple copies of one model do not establish statistical independence.
Model output is retained as data, never executed or used to fetch its own URLs.

Scoring independently inspects the canonical answer, registered short witness
clauses, exact citations, source versions/origins and current issued review
receipts. It does not call the router's private acceptance predicate. Literal
quotation establishes text presence; it is not semantic truth. The finite
oracle's support contract is intentionally stricter than answer correctness:
guessing the correct label or quoting an irrelevant true sentence is not a
supported completion. `system_claimed_complete`, `router_satisfied`,
`answer_correct`, `evidence_supported_completion`, `grounded_abstention` and
`oracle_assessed` remain separate. An authorized model reviewer may issue a
mechanically valid PASS on a semantically wrong answer.

## Durable costs and the authorized eight-hour amendment

Every generation call across backend smoke, pilot, confirmation and auxiliary
work uses one durable ledger. SDK issuance/checkpoint and HTTP token reservation
precede dispatch. Successful usage records actual prompt/generated counters;
unknown consumption keeps its reservation and blocks all later dispatch. Known
JSON/schema/length errors are charged, not retried for free. Nanosecond server
durations and converted seconds, load, prefill, generation and client wall are
kept separately. Missing counters remain null, not estimated from characters.

The initial protocol was `egr-023-local-ollama-v1` with a 14,400-second
global wall ceiling. The user explicitly instructed
“総上限時間は8時間に緩和してください”. After the pilot finished and generation
stopped, the one-time `wall_budget_amendment` event changed only that ceiling
to 28,800 seconds and moved run/protocol identities to v2. Endpoint, exact model
profiles, all other caps, prompts, tasks, seeds and decode controls stayed fixed.
The event validates predecessor history/config hashes and the retained cost
snapshot, is appended and fsynced, and cannot clear pending or authorize a retry.
Stale v1 clients cannot dispatch after it. The original four-hour segment remains
immutable under `segments/initial-4h` in the raw data.

At the amendment, **94 reservations and 94 known receipts** were retained:
14,728 generated and 56,802 total tokens, with no pending or unknown cost.
The original first-reservation epoch remains **1791200089.2157648**. The
eight-hour clock includes all elapsed time since that epoch; it is not an
additional eight hours starting at the amendment. The original closing ledger
prefix SHA256 is
`6237c35be61d4a77ed6104989f1194d14d6180cf4d1cc9c5512ad924b6ab6707`.

| Bound | Frozen value |
| --- | --- |
| Entire run, from its original first reservation | 8 hours; 1,200 calls; 600,000 generated tokens; 5,000,000 total tokens |
| One trial, including any auxiliary continuation | 6 LLM calls; 600 seconds; 27,648 conservatively reserved total tokens; 16 SDK actions/8 verifications |
| Request controls | Context 4096; output 512; temperature 0; explicit seed; `stream:false`, `think:false`, `truncate:false`, `shift:false` |
| Request wall/socket | 120 seconds normally; initial cold backend smoke up to 180; socket wait at most 180 and never longer than remaining wall |
| Raw/snapshot disk | 512 MiB; retain history and stop before new issuance cannot fit |

Ollama 0.35.0's inspected [request type](https://github.com/ollama/ollama/blob/v0.35.0/api/types.go)
and [handlers](https://github.com/ollama/ollama/blob/v0.35.0/server/routes.go)
support the explicit nontruncation/nonshift controls. The local client has no
exact tokenizer: it reserves context-plus-output conservatively and inspects
actual server usage rather than treating encoded JSON bytes as exact tokens.
A timeout does not prove the server has ceased work. Incomplete/unknown calls
stay blocked across every trial and after resume.

The pilot resource record contains 188 before/after samples. The final
[resource reconciliation](../experiments/ollama/results/v0.2.3/resource-summary.json)
covers all 182 requests with **364 before/after samples**. Minimum available RAM
was **11,561,979,904 bytes**, above the installed-memory 10% floor of
**6,871,947,674 bytes** and the earlier online OS-visible floor of 6,636,318,311.
Minimum observed disk free space was **642,574,450,688 bytes**; maximum raw
directory size observed before a request was **17,457,739 bytes**, below the
536,870,912-byte guard. These sampled checks do not establish a continuous peak
or an operating-system hard memory cap.

For the selected client/owned-server processes, the maximum simultaneously
sampled working-set sum was **30,479,630,336 bytes** and private-commitment sum
**31,444,402,176 bytes**. The measures are separate and exclude the shared
server; separate per-process peaks are not added as a coincident peak. CPU
counters are per-PID cumulative observations with first-to-last differences,
not an exact aggregate server/trial CPU bill. Gaps before/after samples and PID
identity ambiguity remain. All 182 loaded-model observations had `size_vram=0`
(Gemma 134, Qwen 48); actual offload layers and continuous VRAM peak remain null.
Desktop background load, power and thermals were not experimentally controlled.

## Completed development pilot

All **24 pilot trials** were retained: four development parents × two models
× three arms, seed `23031003`. There was no successful-trial rerun or
cross-arm answer cache. Completion below is obtained from the 24 independently
scored rows, not the pilot summary's confirmation-only counters (which have zero
planned confirmation keys).

| Model | Arm | Supported answerable completion | Grounded insufficient answer | All supported outcomes | False acceptance, all parents |
| --- | --- | --- | --- | --- | --- |
| Gemma | A | 0/3 | 0/1 | 0/4 | 0/4 |
| Gemma | B | 1/3 | 0/1 | 1/4 | 0/4 |
| Gemma | C | 3/3 | 0/1 | 3/4 | 0/4 |
| Qwen | A | 0/3 | 1/1 | 1/4 | 2/4 |
| Qwen | B | 1/3 | 1/1 | 2/4 | 0/4 |
| Qwen | C | 3/3 | 0/1 | 3/4 | 0/4 |

Qwen A's two false acceptances were development L1 and L3: the SDK recorded
satisfaction but the independent answer/support check rejected them. Both
models' C workflow completed all three answerable development tasks. That
establishes neither a universal ceiling nor an independent confirmation win:
C received all documents earlier, while A/B could lose or omit information
during reading, integration or review. An answer can also be canonically
correct without the required grounded semantic-review receipt.

| Phase/model | Calls | Generated/total tokens | Summed client HTTP wall | Length responses |
| --- | --- | --- | --- | --- |
| Gemma backend smoke | 1 | 6/32 | 17.266 s | 0 |
| Qwen backend smoke | 1 | 10/39 | 111.454 s | 0 |
| Gemma development pilot | 46 | 6644/26438 | 546.785 s | 6 |
| Qwen development pilot | 46 | 8068/30293 | 1049.876 s | 2 |

Every one of these 94 calls has known usage. Backend smoke observed server
load times of 16.568 s for Gemma and 110.533 s for Qwen; these are separate cold
observations, not a controlled brand-speed result. The pilot's `length`
responses still count as spent calls/tokens. Summed HTTP wall is not whole-run
elapsed time or controller/server CPU time. No API price, electricity or CO2
cost was measured. The pilot supplies speed/resource feasibility information
and disclosed development failures, not the confirmation confidence interval.

The all-stage review retains all pilot paths: 10/24 supported completions and
14 unsupported trials, comprising eight review-length failures, four semantic
FAIL/UNKNOWN outcomes and two Qwen-A false PASS outcomes. Canonical labels were
correct in 15/24. These are descriptive development observations, not additional
confirmation parents or independent replications.

## Frozen confirmation, observed partial end and separate sensitivity

The speed/resource-only rule selected **eight parents** before confirmation:
L1 `{1,2}`, L2 `{1,5}`, L3 `{1,2}`, L4 `{1,6}`. There are 48 frozen main keys
(eight parents × two models × A/B/C), seed `23031017`, plus 16 predeclared
auxiliary source keys for parent 1 in every family, both models and A/B.
The other 16 authored confirmation parents are excluded by the predeclared
profile, not post-result filtering. Model blocks avoid repeated cold loads;
within each block parents are shuffled and A/B/C order is counterbalanced with
schedule seed `23031029`.

The forecast used maximum observed per-request wall minus load duration plus
observed sampling/controller overhead, reserving model-block load separately.
It did not use correctness or arm differences. At freeze, remaining wall from
the original start was 25,834.914 seconds. The frozen per-request forecasts were
30.262/57.857 seconds for Gemma/Qwen, with once-per-model load reserves of
17.196/110.533 seconds. Forecasts are admission assumptions, not measured
confirmation times or a guarantee that every maximum-cost trial can finish.

For eligible auxiliary keys only, a known `no_progress` main stop may immediately
continue the copied exact checkpoint by at most two unused callbacks via public
`step`. The original trial's call/token/wall/cost/history limits remain in force.
Primary records are not overwritten. Ineligible, exhausted, faulted or pending
continuations remain explicitly separate. Mixed-model role sensitivity is
optional and is not recorded as executed at this stage.

The saved [frozen summary](../experiments/ollama/results/v0.2.3/summary.json)
is preserved. The separate
[answerable recount](../experiments/ollama/results/v0.2.3/answerable-recount.json)
applies the specification's predeclared answerable/insufficient split to those
same raw rows without changing the frozen experiment/oracle. It retains all
scheduled failures, unknowns and unexecuted keys. There are 88 scored records:
24 pilot, 48 main confirmation and 16 auxiliary dispositions. Only 25 main
trials started: 24 with known Gemma receipts and one uncertain Qwen trial.

### Gemma: no identified A/B completion gain

| Gemma arm | Answerable supported completion | Answer correct, answerable | Grounded insufficient answer | False acceptance, all 8 parents |
| --- | --- | --- | --- | --- |
| A | 1/6 | 2/6 | 0/2 | 0/8 |
| B | 1/6 | 3/6 | 0/2 | 0/8 |
| C reference | 2/6 | 5/6 | 0/2 | 1/8 |

All 24 Gemma main trials have retained terminal records and known call usage;
this does not mean their answers succeeded. A succeeds on `L4-1`, B on `L1-2`
and C on `L1-1`/`L3-1`. For the six answerable paired parents, A versus B has
**1 win, 4 ties and 1 loss**, mean difference **0**, with the predeclared
2,000-resample parent bootstrap interval **[-0.50,0.50]**. This wide interval
does not establish superiority or equivalence. The original all-eight-parent
support composite is also zero, interval **[-0.375,0.375]**, with two additional
insufficient-parent ties; it is a distinct endpoint, not the answerable interval.
Per-model pairing uses parents, not calls, renamings or source copies.

C's false acceptance is `confirmation-L2-1`: its mechanically recorded
satisfaction/PASS did not establish the gold answer and required support.
The answer cited raw documents 1/2/3 but answered "no", incorrectly dismissing
the independent origins `{調査A,消防}`. The review issued PASS despite this
semantic error. The stage audit found the issued target, related-input digests,
contract, checker and purpose consistently pinned: this is the host-delegated
model review's semantic failure, not an observed core binding violation.
Pooled information raised correct-label recovery to 5/6 answerable parents,
but only 2/6 met the complete support/review contract. C therefore supplies
neither a perfect ceiling nor evidence that local structured review is reliable.
None of the three arms produced grounded accepted abstention on the two
insufficient parents, even when an unknown label was textually correct.

### Paid output failures and stop interaction

Gemma issued **87 main generation calls**: 71 `ok` and **16 `length`**, comprising
30 reader, 29 integration and 28 review calls. Reviews produced 5 well-formed
PASS, 2 FAIL, 5 UNKNOWN and 16 length responses. All 16 length responses reached
the fixed 512-token cap; their costs and unsuccessful outcomes remain counted.
This configured bounded structured-review failure is not separable here from
model comprehension or scheduling effects. The cap/prompts were not expanded
after confirmation outcomes became visible.

| Frozen parent | A | B | C reference |
| --- | --- | --- | --- |
| L1-1, answerable | semantic FAIL, escalation | review length | supported |
| L1-2, answerable | `no_progress` and review length | supported | correct label, review length |
| L2-1, answerable | six-call cap before revised review | review length | false accepted |
| L2-5, insufficient | correct unknown label, `no_progress` and review length | correct unknown label, semantic UNKNOWN | correct unknown label, review length |
| L3-1, answerable | correct label, `no_progress` and review length | review length | supported |
| L3-2, answerable | `no_progress` and review length | correct label, review length | correct label, review length |
| L4-1, simple answerable | supported | correct label, review length | correct label, review length |
| L4-6, insufficient | `no_progress` and review length | review length | correct unknown label, review length |

This table preserves all eight Gemma parents and all three arms; the saved
[failure analysis](../experiments/ollama/results/v0.2.3/failure-analysis.json)
and [all-stage review](../experiments/ollama/results/v0.2.3/stage-failure-review.json)
retain detailed source/citation/receipt errors, all 24 pilot stage chains and
the Qwen uncertain/unexecuted records. On A-L1-1 the reader invented a quote
`unknown`, which failed literal validation; subsequent integration saw only
document 2. A-L3-1 gave the correct label using old document 1 but omitted
current document 2 and personal-status document 3. A/B on L4-6 treated an absent
arrival record as "no"; C selected the correct unknown label but failed review
length. These observed paths are not a causal decomposition. A reached `no_progress` in
5/8 trials; B did so in 0/8. Those five A stops also carried a review-length
fault. Every one of the 16 predeclared auxiliary records is
`not_eligible_for_auxiliary`; no auxiliary generation was dispatched. Eligible
fault-free continuation was not observed on the predeclared subset, and the
Qwen block was stopped. Consequently there is **no live estimate of the
two-callback sensitivity effect**. Neither the zero paired mean nor these
ineligible records establish that altering the stop rule would help. Mixed-model
roles were not frozen/executed, and are not attributed to resource exhaustion.

### Qwen: uncertain execution, not zero model performance

The first shuffled Qwen confirmation key was `confirmation-L2-5`, arm A.
Its reader call hit the fixed normal **120-second** deadline. Observed HTTP
wall was **119.985 seconds**, controller segment **122.218 seconds**. No definitive
server usage/load/prefill/generation receipt was obtained. The ledger keeps one
pending call with **512 generated / 4608 total tokens reserved**, and unknown
actual use. It blocked every later generation. The other **23 Qwen main keys**
remain unexecuted; all six answerable pairs and both insufficient pairs are
unresolved, with **paired N=0**, null mean and null confidence interval.

The original terminal wrapper's `execution="completed"` only means it returned
a saved row. `oracle_assessed=1` evaluated the absence of an answer, not a known
settled inference. SDK `pending=false` means there is no open SDK attempt;
HTTP ledger `pending=true` and `known_attempt_termination=false` still establish
uncertain external consumption. These observations do not imply Qwen has a
0/6 answerable success rate, zero failure probability or safe abstention.
Unexecuted arms have no observed performance. The untouched raw label
`unexecuted_due_to_budget` is generic here: the controller's detailed reason is
**pending_or_unknown_consumption**, not exhaustion of the eight-hour/call/token
limits. The earlier Qwen 12-arm development pilot remains real, but cannot
replace the missing confirmation comparison or identify this timeout's cause.

### All attempted costs, without an empty-subset efficiency claim

| Gemma scope/arm | Scheduled parents | Generation calls | Generated/total tokens | Summed HTTP wall |
| --- | --- | --- | --- | --- |
| Answerable A | 6 | 22 | 3845/13408 | 302.329 s |
| Answerable B | 6 | 27 | 4705/16620 | 376.752 s |
| Answerable C | 6 | 12 | 2753/8716 | 201.314 s |
| All 8 A | 8 | 30 | 5511/18706 | 444.050 s |
| All 8 B | 8 | 37 | 6092/22652 | 492.906 s |
| All 8 C | 8 | 20 | 5013/15623 | 363.252 s |

Gemma's all-87-call server counters separately sum load **18.844 s**, prefill
**490.278 s**, generation **787.613 s**, and client HTTP wall **1300.208 s**.
These sums are not controller CPU, complete trial elapsed time or energy.
There are **zero parents on which both A and B support completion**: success
subset N=0, costs/comparison null. The empty aggregate zeros in the original
summary are not measured zero-cost successes. A's lower aggregate spending
includes earlier unsuccessful stops and cannot establish efficiency on
equivalently completed work. C's cheaper totals remain conditional on its
different initial information/workflow contract.

Across smoke, pilot and main execution the ledger records **182 reservations,
181 known usage receipts and one unknown**. Known observed subtotals are
**31,344 generated / 113,783 total tokens**. Grand actual generated/total costs
are **null**, not those subtotals plus zero. The Qwen unknown retains its
512/4608 reservation and absent duration counters. No additional paid repair,
retry, auxiliary or mixed-role generation was hidden in the totals. There was
no API bill or measured electricity/CO2 cost.

## Identity, reproduction and remaining status

| Frozen item | Identity |
| --- | --- |
| Implementation commit | `481419e252d233d712de237e96af2ae6184b9b33` |
| Candidate wheel build commit | `1ed12f13c4d5b1a78fc39f9d1fb476da78f3449a` |
| Candidate wheel SHA256 | `8227a37be95b615f1608619592298b401bfc73cc412b90857e07ccada8215bc5` |
| Actual installed package-byte fingerprint | `dca4042a019b0af214b6f9e39fa1aaef2d9547c091e828020929be323d9cdd6b` |
| Frozen experiment harness SHA256 | `2edd5334dfefa7dc16d4c4327cd9109834300bb779532cb15b269424b0abb7b9` |
| v2 protocol SHA256 | `5775bc0f540bb60df81631645229bb2ba51aadc81d5ba0de1b00fae68d74a68f` |
| v1 protocol SHA256 | `d116d3fdba875c3aed4eb9f79a89cc18274b2794d0fdeb79a8fb667e644560e1` |
| Original four-hour segment manifest SHA256 | `a8f554ce9ae8f3ba0b73e29af2bac0fe2677e97e7bca92d69c38834cfcf1d19e` |
| Confirmation freeze JSON SHA256 | `a9677a9a1cecd75259fc841c2ab588cc66094b354fe3276e6e7a2bf84b148f77` |

The checked-in [protocol](../experiments/ollama/protocol.json) and
[freeze](../experiments/ollama/results/freeze-v0.2.3.json) pin model, task,
gold, prompt/schema, decoding, code, budget and scheduled-key identities.
The [experiment README](../experiments/ollama/README.md) contains the actual
`preflight`, `backend-smoke`, `pilot`, `amend-wall`, `freeze`, `live`, `resume`
and `analyze` commands, owned-server startup and a finite callback example.
Use an ordinary external installed-wheel environment and `python -I` on the
direct script. The script imports the experiment from the checkout without
putting `src` on the package path. Experiment code is outside the wheel and
package import/ordinary CLI never connects to Ollama.

For saved-data reanalysis, `analyze --directory RUN --output OUTPUT` reads the
ledger, exact snapshots and terminal records without generation. `resume` is
for the same frozen run: completed keys are skipped, and an already completed
HTTP receipt can settle a saved issued SDK attempt without network replay.
Missing/unknown receipts, incomplete journals and changed identities stop
resume. **This actual run remains blocked and must not dispatch again:** stopping
its owned server did not settle the unknown usage or refund its reservation.
A fresh reproduction issues new requests and must be distinguished
from reanalysis; temperature zero and the same seed do not guarantee
byte-identical model output.

The README's custom callback example was executed outside the checkout with
the installed candidate and the already blocked ledger. It performed **zero
callbacks/actions and zero new generation**, produced no answer and no SDK
satisfaction. This demonstrates the shared pending gate, not live-model accuracy
on custom documents; its checkpoint/result are retained separately from scored
tasks.

The owned server PID 12912 and its traced descendants were verified stopped at
`2026-10-05T12:54:48.0119207Z`–`12:54:48.1758553Z`, with no remaining owned PIDs.
The preexisting server PID 9536 on port 11434 remained alive and returned version
0.35.0. No unrelated/shared process was stopped and no request was replayed.
The unknown HTTP reservation remains unsettled. Final ledger SHA256 is
`99c53cebeb3f87683330bd1d12dcf455757502642c9d370d33b8abb68ba83a5c`.

### Completed local bundle and saved-data reanalysis

| Retained artifact | Actual local identity |
| --- | --- |
| `ollama-raw-v0.2.3.zip` | 1,822,461 bytes; SHA256 `c4a1ca613a70b61fb3ac3bc035537e439f962a330816bc9fe5a2fdf8288392a5` |
| ZIP data manifest | 198 data files; 18,626,914 uncompressed source bytes; 200 ZIP entries including `MANIFEST.json` and `EXCLUDED_SOURCES.json` |
| `MANIFEST.json` | SHA256 `540de0ecb333a4d29894b0a6aeaf610f2b2be1ce1265e076c249bb94325a4486` |
| Separate [artifact provenance](../experiments/ollama/results/v0.2.3/artifact-provenance.json) | SHA256 `9c57ce0298d6619ae40af012055b6db25a10e1bfa70290ad8d468baf070a993d` |

All 198 manifest data-file hashes and the integrity of all 200 ZIP entries were
verified by reopening the completed archive. The manifest does not hash itself
or the exclusion record. Provenance is written after the immutable ZIP and is
a separate asset, outside the archive whose identity it records. The closing
v1 journal is 1,221,476 bytes with prefix hash `6237c35b…6ab6707`; it remains an
exact prefix of the final ledger. Historical copies are not counted again as
additional calls or token use.

The first strict-UTF-8 packaging attempt detected Windows CP932 stdout from the
custom callback example. Original diagnostic bytes were retained separately
and encoded losslessly as base64 in `raw/callback-example-output-observation.json`;
the public UTF-8 transcode was checked for semantic identity. This was an
output-encoding correction with no replay or generation. Model responses and
the request/receipt journals remain unchanged. Windows reproduction should set
`PYTHONIOENCODING=utf8` for diagnostic stdout.

The planned Release assets are the
[raw ZIP](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/ollama-raw-v0.2.3.zip)
and [raw checksums](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/OLLAMA_RAW_SHA256SUMS).
They were not uploaded at this measurement snapshot. After publication, the
following POSIX-shell procedure uses tagged experiment code and an ordinary
installed wheel, unpacks only the checked local archive, and writes reanalysis
to a new directory. It makes no Ollama generation request:

```sh
git clone --branch v0.2.3 --depth 1 https://github.com/kadubon/evidence-gap-router.git /tmp/egr-ollama-023-source
python3.12 -m venv /tmp/egr-ollama-023-env
/tmp/egr-ollama-023-env/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple evidence-gap-router==0.2.3
mkdir /tmp/egr-ollama-023-assets
gh release download v0.2.3 --repo kadubon/evidence-gap-router --pattern ollama-raw-v0.2.3.zip --pattern OLLAMA_RAW_SHA256SUMS --dir /tmp/egr-ollama-023-assets
cd /tmp/egr-ollama-023-assets
sha256sum -c OLLAMA_RAW_SHA256SUMS
/tmp/egr-ollama-023-env/bin/python -m zipfile -e ollama-raw-v0.2.3.zip /tmp/egr-ollama-023-evidence
/tmp/egr-ollama-023-env/bin/python -I /tmp/egr-ollama-023-source/experiments/ollama/cli.py analyze --directory /tmp/egr-ollama-023-evidence/raw --freeze /tmp/egr-ollama-023-evidence/freeze-v0.2.3.json --output /tmp/egr-ollama-023-reanalysis
/tmp/egr-ollama-023-env/bin/python -I /tmp/egr-ollama-023-source/scripts/recount_ollama_023.py --scored /tmp/egr-ollama-023-reanalysis/scored-trials.json --summary /tmp/egr-ollama-023-reanalysis/summary.json --freeze /tmp/egr-ollama-023-evidence/freeze-v0.2.3.json --ledger /tmp/egr-ollama-023-evidence/raw/calls.jsonl --phase confirmation --output /tmp/egr-ollama-023-reanalysis/answerable-recount.json
```

The supplemental recount separates the six answerable and two insufficient
parents and retains unresolved scheduled pairs. Compare its input hashes and
metrics with `analysis/answerable-recount.json` in the archive. The helper's
SHA256 is `a1fa61f52d7554a417240c959c953a5181a2afe1188e5317e1ce506bf10292e9`.
The command leaves the generation-row seed filter unset, as in the saved
recount; bootstrap seed 23031041 is already fixed within the helper.
These reanalysis commands are reproducibility instructions, not a claim that
the future tagged download/installation has already passed. Manual/native CI,
GitHub Release, PyPI and fresh official-index installation are pending in this
pre-publication snapshot; their actual outcomes belong to the later
[publication verification asset](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/publication-verification-v0.2.3.json).

The first manual run [37317646260](https://github.com/kadubon/evidence-gap-router/actions/runs/37317646260),
commit `f302f7f8c3681d47e294367f01748d6fbc73e650`, passed lint, mypy and the
Linux source suite (621 passed, 9 Windows-only skips), then failed frozen-package
byte equality. The measured Windows Git archive used `core.autocrlf=true`, so
its 24 nonempty package files had CRLF; Linux checkout blobs had LF. All 25
package files matched exactly after LF-to-CRLF conversion. Adding
`src/evidence_gap_router/** text eol=crlf` to `.gitattributes` makes CI reproduce
the measured candidate bytes, without changing core semantics, freeze records
or equality gates. The second manual run and actual publication have not been
executed at this snapshot; later outcomes belong to the separate verification asset.

The user's explicit v0.2.3 publication request supersedes the supplied file's
initial no-new-version assumption; existing v0.2.2 artifacts remain unchanged.

The present evidence supports using the SDK for explicit authority, current
evidence binding, retained costs and auditable finite continuation. It does not
make an LLM checker a semantic truth oracle. Gemma supplies no identified A/B
completion gain and no comparable-success cost comparison; Qwen confirmation
is inconclusive because of uncertain execution. Pooled information was useful
on some short tasks, but the false acceptance and review-cap failures preclude
a reliability or ceiling claim. Short documents fitting one context may need
no distributed routing. This CPU-observed local experiment establishes no general agent-stack
superiority, statistical independence, collective superintelligence, API-cost
saving or energy reduction.
