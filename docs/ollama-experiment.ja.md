# v0.2.3 ローカル Gemma/Qwen 実験

本報告は、公開 v0.2.2 の限定的な SDK 監査と、短い人工日本語文書を
実際のローカルモデルで処理する比較実験を記録する。確認は部分完了で終了した。
Gemma は24 arm試行を終え、回答可能 completion はA/Bとも1/6。Qwen は最初の
formal reader が timeout し、未知消費を残したため A/Bの評価可能 pair は0である。
総予算の枯渇ではない。routing の改善や同じ成功課題での費用節約は、このデータでは
確認できない。pilot は開発観測のまま分離し、標本資源観測と完成したローカルraw
bundleを照合した。本報告は公開前の測定snapshotで、実際の公開検証を別に記録する。

問いは、不完全な抽出・統合・検証を行うモデルに対して、次の取得・検証を選ぶ
EGR が役立つかである。各モデル内で同じ公開 runner を使う strong verify-first
と比較し、資料を最初から集める参照も別に置く。モデルの PASS、schema 適合、
SDK の satisfied と、独立した正解・根拠判定を区別する。

## 監査と実行済みの前提検証

起点は変更のない公開 v0.2.2 commit
`eff875d4c391c476fbe5af43ab4cd7928b7e0ca3` である。新たに取得した公式 wheel
の SHA256 は
`6f417e5664513a5a3125051642dab46b85065f74ab5f669b999a24a79ae7bbc5`
と一致した。[監査報告](audit-022.md) に、新規に実行した baseline と、実際の
発行 receipt を用いる公開 SDK の14ケースを記録した。再現した修正は、README
継続例の import 先だけである。helper は package root ではなく `sdk_example`
に存在する。受入アルゴリズムを変更すべき不具合は、この監査では確認しなかった。
既定の `run` は費用・履歴を保持し、意味上の `no_progress` で停止する。
新しい ID だけを進捗にはしない。

| 今回実行した前提検証 | 実際の結果 |
| --- | --- |
| version 変更前の元 source baseline | 428 passed、skip なし |
| 元 commit の tests と普通の公式 v0.2.2 wheel | 428 passed、skip なし |
| 実 receipt を用いる公開 SDK 監査 | 14/14 の期待条件を確認、ケース例外なし |
| 固定 v0.2.3 source、Windows Python 3.12.14 | 630 passed |
| 固定 source、WSL Linux Python 3.12.14 | 621 passed、Windows Job Object 検査9件 skip |
| 普通にインストールした候補 wheel の Windows runtime 回帰 | 296 passed、SDK/CLI smoke も通過 |
| 同じ wheel を使う実験通信契約 | 172 passed、臨時 fake HTTP のみ |
| 同じ wheel のモデルフリー benchmark smoke | 44試行・proof 4条件・helper 3条件を確認 |

元 baseline の428件には、外部に展開した元 source の orchestration tests も
含まれる。installed runtime 回帰だけが428件あるという意味ではない。候補 SDK
は checkout 外の普通の環境の site-packages から import した。fake tests は
HTTP、strict output、予算、journal、oracle、再開、既知 format error、未知消費、
pending、明示的 wall 上限変更を確認する。Gemma/Qwen の実推論成績には数えない。
6 native profile の release CI は、本報告時点では別の未検証段階である。

## 実機・モデル・ローカル実行

実推論は Windows 1台で行う。`2026-10-05T12:30:46.3530634Z` に確認実験中の
identity snapshot を取得し、設定変更は行っていない。Windows 11 Home build
26300、AMD64、AMD Ryzen 7 8840HS（8 cores/16 logical processors）、32 GiB
の RAM bank 2本で搭載量64 GiBを記録した。資源 preflight が報告した OS-visible
容量は66,363,183,104 bytesである。Python 3.12.14、Pydantic 2.13.5、
pydantic-core 2.46.5を用い、matched lock は annotated-types 0.8.0、
typing-extensions 4.16.0、typing-inspection 0.4.4も固定する。

GPU device metadata は AMD Radeon 780M、driver `32.0.21010.10` である。
WMI の `AdapterRAM=2147483648` は device metadata であり、推論の実 VRAM
割当・上限・peak ではない。hardware snapshot の空き disk は
642,895,974,400 bytesだった。この1台の観測を、他 OS の実推論性能や公平な
モデルブランド間速度比較としない。

所有する Ollama **0.35.0** server を `127.0.0.1:11435` で起動した。
server 自身が `OLLAMA_NO_CLOUD=1`、`OLLAMA_NUM_PARALLEL=1`、
`OLLAMA_MAX_LOADED_MODELS=1`、`OLLAMA_MAX_QUEUE=1` を継承し、log で
cloud disabled と一致する listener/version を確認した。既存 port 11434 の
server は維持した。既存の正確なローカル tag を使い、モデル download・更新・
remote model・cloud fallback は行っていない。最初の metadata preflight
（`2026-10-05T10:55:21.415533Z`）は生成・load request とも0で、両 tag、空の
remote fields、loaded model なし、資源阻害理由なしを確認した。実生成の確認は
その metadata だけではなく、続く backend smoke による。

| 既存の正確な tag | 記録した family/size/quantization | model digest |
| --- | --- | --- |
| `gemma4:e4b` | `gemma4`、7.5B、`Q4_K_M` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |
| `qwen3.6:35b-a3b` | `qwen35moe`、36.0B、`Q4_K_M` | `07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522` |

値は `/api/tags` と安全に縮約した `/api/show` の観測であり、tag の文字列から
parameter 数を推測していない。thinking の対応値は `[false,true]`、default
は true と広告され、全 request で明示的に `think:false` を送る。metadata、
template、parameters、modelfile、license の hash を保持する。取得した license
text は Apache License 2.0で始まるが、model terms と project license は別に
記録する。重み本体や私的な modelfile path は本報告に含めない。

実験後 `2026-10-05T13:08:28.0991008Z` に、維持したport11434からread-only
`/tags`/`/show` を取得し、生成0・重み変更なしで両frozen digestを再確認した。
Gemmaの `parent_model` は
`gemma4-validation-20260929:e4b-imatrix-attention-q6-q8-draft2`、Qwenは空である。
Gemmaは既存のcustom local variantであり、stock official buildと仮定しない。
この後日のmetadata確認は確認実験前のfreezeと別で、元のbuild工程を独立に証明
するものではない。safe recordにresponse hashを保持し、私的pathを含めない。

### CPU log の根拠と限界

安全な観測記録の source_scope は **owned Ollama stderr snapshot** である。
`2026-10-05T19:28:26.845+09:00` を行自身に持つ短い行が
`msg="inference compute" library=cpu` を明示する。時刻を持たない loader 行は、
Gemma の CPU model/KV/compute buffer 4242.76/64.00/117.02 MiBと、
Qwen の9196.26/80.00/76.02 MiBを記録する。直前の時刻付き行はそれぞれ
`20:34:49.725+09:00`、`20:35:08.639+09:00` だが、buffer 行自身の時刻ではない。
各値は個別の allocation であり、合計・peak・process RSS・memory 上限ではない。

両 loaded model の観測は `size_vram=0` だった。log の `gpu_layers=-1` は要求
設定値であり、実際に offload した layer 数は不明/null のまま残す。CPU backend
は明示的な観測である一方、全 server/GPU の hard memory ceiling、連続 peak、
energy 使用は確定していない。私的 path、proxy 値、全環境、全 log は公開用の
安全な記録に含めない。

元 snapshot は `2026-10-05T11:48:28.7818288Z`〜`11:48:28.8375535Z` に
読み取った407,560 bytesで、SHA256 は
`7312ba8b9bb81f30847405c89fb228803afd1519e4810d52f2dbaa09ff10ee54`。
10抜粋の JSON は5,213 bytes、SHA256 は
`28e8ff797f81f6e46cd17bb1c4afdc805eb9f31b14de12c923d066251b525302`
である。元 log は私的に保持し、その hash は内容の公開や署名付き証明ではない。

## 比較・課題・独立採点

各モデルで同じ人工親 task を使う。L1 は分散条件の統合、L2 は由来の重複と
不一致、L3 は版・変更・例外、L4 は単純課題と真に情報不足の対照を含む。
開発4親は family ごと1件で、回答可能3・情報不足1。固定確認8親は family
ごと2件で、回答可能6・情報不足2である。48 arm 試行を48独立親とは数えず、
小さな人工入力を現実業務の母集団や外部 benchmark の再現とはしない。

| Arm | 実行・情報条件 |
| --- | --- |
| A：EGR | 共通の有限候補 pool から既定 selector で選ぶ。 |
| B：strong verify-first | Aと同じ公開 `run`、pool、権限、views、callbacks、費用、停止条件。必要な実行可能検証を優先し、次に公開目録の固定順で未読資料へ進む。 |
| C：pooled reference | 全資料を最初から中央経路へ渡す。固定段階の公開 `step`、review、有界修正でreceipt/費用を残し、EGR gap ranking で C に見せる資料を選ばない。 |

A/B は `feasible_actions` の necessity/helper gates も共有する。この差は共通
機構内の selector 順序に条件付けられ、独立 scheduler と EGR 全体の比較ではない。
双方が既定 `no_progress` を保持する。C は資料到着条件と固定手順が異なり、
SDK receipt/domain 観測は保持するが、同じ情報到着の比較 arm や理論上限としない。

reader が見るのは明示的に渡した公開資料と schema だけである。統合・review
には取得済み情報と固定 related inputs を渡す。factory、prompts、selector、
callbacks は `PublicTask` だけを受け取り、`GoldTask` は採点専用に隔離する。
digest・version・origin は host が与える。同じモデルの role を増やしても統計的
独立性を作らない。出力は保存するデータであり、実行や出力 URL の取得に使わない。

oracle は canonical answer、事前登録した短い witness の節、正確な引用、
資料 version/origin、現行の発行済み review receipt を独立に照合し、router の
private acceptance predicate は呼ばない。引用一致は文章の存在であり意味的
真実ではない。有限 oracle の support 条件は answer correctness より厳しく、
値を当てた場合や無関係な正しい文を引用した場合を根拠付き完了にしない。
`system_claimed_complete`、`router_satisfied`、`answer_correct`、
`evidence_supported_completion`、`grounded_abstention`、`oracle_assessed`
を別 field に残す。権限を持つ model reviewer が、意味上は誤った回答に、機械的に
有効な PASS receipt を発行することはあり得る。

## durable 費用記録と8時間への明示変更

backend smoke、pilot、確認、補助を通じて、全生成 call を同じ durable ledger
へ記録する。SDK 発行/checkpoint と HTTP token 予約を dispatch 前に保持する。
確定 receipt は実際の prompt/generated 数で精算し、未知消費は予約を保持して
全 trial の後続 dispatch を止める。既知の JSON/schema/length error も有料扱いで
残し、無料再試行はしない。server duration の元 nanoseconds と seconds、load、
prefill、generation、client wall を分ける。欠損値は文字数で補わず null とする。

初期 protocol は `egr-023-local-ollama-v1`、総 wall 上限14,400秒だった。
利用者の「総上限時間は8時間に緩和してください」という明示指示を受け、pilot
終了・生成停止後に一度だけ `wall_budget_amendment` を append/fsyncした。
総 wall のみ28,800秒へ変更し、run/protocol identity を v2へ移行した。
endpoint、正確な model profiles、他の全上限、prompt、task、seed、decode
は不変である。event は先行 history/config hash と保持費用 snapshot を検証し、
pending を消さず、再送を許可しない。旧 v1 client は以後 dispatch できない。
元4時間 segment は raw の `segments/initial-4h` へ不変に保存した。

移行時も **94予約・94確定 receipt**、generated 14,728・total 56,802 tokens、
pending/未知費用0を保持した。最初の予約 epoch は **1791200089.2157648** の
ままである。8時間はこの最初の時刻からの全経過時間であり、変更時から追加の
8時間ではない。元の終了 ledger prefix SHA256 は
`6237c35be61d4a77ed6104989f1194d14d6180cf4d1cc9c5512ad924b6ab6707`。

| 上限 | 固定値 |
| --- | --- |
| 元の最初の予約からの全実験 | 8時間・1,200 calls・600,000 generated・5,000,000 total tokens |
| 補助継続を含む1 trial | LLM 6 calls・600秒・保守予約27,648 total tokens・SDK actions16/verifications8 |
| Request | context4096・output512・temperature0・明示 seed・`stream:false`・`think:false`・`truncate:false`・`shift:false` |
| Request/socket wall | 通常120秒、最初の cold backend smoke は180秒まで、socket は最大180秒かつ残 wall 以下 |
| raw/snapshot disk | 512 MiB、履歴を消さず次の保存が収まらない前に新規発行停止 |

実 version 0.35.0の [request type](https://github.com/ollama/ollama/blob/v0.35.0/api/types.go)
と [handlers](https://github.com/ollama/ollama/blob/v0.35.0/server/routes.go) を確認し、
非 truncation/非 shift を明示した。client に正確な tokenizer はないため、
context＋output を保守予約し、JSON byte 数を token とせず実 response 数を使う。
timeout は server の処理終了を証明しない。未確定 call は、再開後を含め全試行の
dispatch を止めたまま残す。

pilot の before/after 資源観測は188 samplesだった。最終の
[資源照合](../experiments/ollama/results/v0.2.3/resource-summary.json) は182 requestsを
**364 before/after samples**で確認する。最小 available RAMは
**11,561,979,904 bytes**で、搭載量10%のfloor **6,871,947,674 bytes**と、
初期onlineのOS-visible floor6,636,318,311 bytesの双方を上回る。
空きdiskの観測最小は **642,574,450,688 bytes**、request前raw directoryの
観測最大は **17,457,739 bytes**で、536,870,912-byte guard未満だった。
標本によるavailability確認であり、連続peakやOSのhard memory capではない。

選択したclient/owned-server processesの同時sample合計の最大は、working set
**30,479,630,336 bytes**、private commitment **31,444,402,176 bytes**だった。
異なる量として別に保持し、shared serverを含めず、各processの別時刻peakを
同時peakとして加算しない。CPUはPIDごとの累積観測と最初〜最後の差であり、
server/trialの正確なaggregate CPU費用ではない。sample間の欠落とPID identityの
曖昧さがある。loaded-model観測182件（Gemma134/Qwen48）は全て`size_vram=0`。
actual offload layers・連続VRAM peakはnullのまま残す。desktopの背景負荷、
電源、thermalは実験的に統制していない。

## 完了した開発 pilot

4開発親 ×2 models ×3 arms の **24試行**を、seed `23031003` で実行し保持した。
成功試行の再実行や arm 間の回答 cache 共有はない。次の値は独立採点した24行
から取得した。pilot summary の confirmation-only counters（予定確認 key 0）
から開発成績を読み取っていない。

| Model | Arm | 回答可能課題の根拠付き完了 | 情報不足の根拠ある回答 | 全 support | 全親での誤受入 |
| --- | --- | --- | --- | --- | --- |
| Gemma | A | 0/3 | 0/1 | 0/4 | 0/4 |
| Gemma | B | 1/3 | 0/1 | 1/4 | 0/4 |
| Gemma | C | 3/3 | 0/1 | 3/4 | 0/4 |
| Qwen | A | 0/3 | 1/1 | 1/4 | 2/4 |
| Qwen | B | 1/3 | 1/1 | 2/4 | 0/4 |
| Qwen | C | 3/3 | 0/1 | 3/4 | 0/4 |

Qwen A の development L1/L3 では SDK satisfaction が成立したが、独立した
answer/support 判定は拒否し、誤受入2件として残った。両 model の C は回答可能
3件を全て完了した。これは普遍的な性能上限や確認実験の勝利ではない。C は
早い段階で全資料を見ており、A/B では読取・統合・review の情報欠落もあり得る。
canonical answer が正しくても、必要な grounded semantic-review receipt が
なければ根拠付き完了にはならない。

| Phase/model | Calls | Generated/total tokens | client HTTP wall の合計 | Length応答 |
| --- | --- | --- | --- | --- |
| Gemma backend smoke | 1 | 6/32 | 17.266秒 | 0 |
| Qwen backend smoke | 1 | 10/39 | 111.454秒 | 0 |
| Gemma pilot | 46 | 6644/26438 | 546.785秒 | 6 |
| Qwen pilot | 46 | 8068/30293 | 1049.876秒 | 2 |

94 calls 全ての usage は確定している。backend smoke の load 観測は Gemma
16.568秒、Qwen110.533秒で、cold 観測と費用を分けて残す。ブランド間の統制された
速度比較ではない。pilot の length 応答も call/token を消費したものとして数える。
合計 HTTP wall と全 run の経過時間、controller/server CPU は同じではない。
API料金・電力・CO2は測定していない。pilot は速度/資源による実行可能性と失敗
境界を示す開発観測であり、確認実験の confidence interval ではない。

全stage reviewはpilot全経路を保持し、support完了10/24・未支持14件の内訳は
review-length8・semantic FAIL/UNKNOWN4・Qwen-A false PASS2だった。
canonical labelは15/24で正しい。開発の記述統計であり、確認親や独立した反復に
追加していない。

## 固定確認の部分完了・感度分析

速度・資源だけの規則で、確認前に **8親**を選んだ。L1 `{1,2}`、L2 `{1,5}`、
L3 `{1,2}`、L4 `{1,6}`で、主試行は48 keys、seed `23031017`。familyごとの
parent1・両 model・A/Bについて補助 source keys16を事前固定した。残り16の
人工確認親は profile 規則による未選択であり、結果を見て除外していない。
model ごと block を作り、その内側で親順を shuffle、A/B/C を counterbalance
し、schedule seed `23031029` を使う。

forecast は、観測 request wall の最大値から load を分離し、観測 controller/
sample overhead を加え、model block load を別に予約する。正解や arm 差は
profile 選択に用いない。freeze 時点の残 wall は元 epoch から25,834.914秒。
Gemma/Qwen の request forecast は30.262/57.857秒、model ごとの load
予約は17.196/110.533秒だった。実行前の仮定であり、確認時刻の実測や全最悪費用
trial が終わる保証ではない。

対象補助 key の既知 `no_progress` だけについて、同じ checkpoint の copy を
public `step` で直ちに最大2未使用 callbacks まで続ける。元 trial の call/token/
wall・費用・履歴の枠を維持し、primary を上書きしない。対象外、予算不足、fault、
pending は別に明示する。mixed-model role 感度分析は任意で、本時点では実施済み
と記録していない。

[固定 summary](../experiments/ollama/results/v0.2.3/summary.json) は原本のまま保持する。
別の [answerable recount](../experiments/ollama/results/v0.2.3/answerable-recount.json)
で、同じ raw を仕様の事前定義した回答可能/情報不足へ分けた。実験・oracle は
変更せず、全予定の失敗・未知・未実行を残す。採点記録は88行（pilot24・main48・
auxiliary16）。main の着手25件は、Gemma確定24件とQwen不確実1件である。

### Gemma：A/Bの完了改善は識別できなかった

| Gemma arm | 回答可能の根拠付き完了 | 回答可能の正しいlabel | 情報不足のgrounded answer | 全8親の誤受入 |
| --- | --- | --- | --- | --- |
| A | 1/6 | 2/6 | 0/2 | 0/8 |
| B | 1/6 | 3/6 | 0/2 | 0/8 |
| C参照 | 2/6 | 5/6 | 0/2 | 1/8 |

Gemma main24件は terminal record と既知 call usage を保持するが、全ての回答が
成功した意味ではない。Aは `L4-1`、Bは `L1-2`、Cは `L1-1`/`L3-1`で支持を
満たした。回答可能6親のA対Bは **1 win・4 ties・1 loss、平均差0**。
事前固定の2,000 parent bootstrap interval は **[-0.50,0.50]**で、優位や同等性を
示さない。元の全8親 support composite も差0、interval **[-0.375,0.375]**だが、
情報不足2親の tie を含む別 endpointである。call、別ID、複製資料を独立親と数えない。

Cの `confirmation-L2-1` は、機械的 satisfaction/PASS があっても正解・support
を満たさず誤受入となった。raw1/2/3を引用しながら「no」と答え、独立origin
`{調査A,消防}`を誤って退け、reviewもPASSを出した。stage監査で発行target、
related-input digest、contract、checker、purposeの固定に不一致はなかった。
hostがmodelに委譲した意味判断の失敗であり、coreのbinding違反の観測ではない。
pooled の正しい回答labelは回答可能5/6だったが、完全な
根拠・review条件を満たすのは2/6。性能上限や structured review の信頼性を保証する
参照ではない。情報不足2親では、unknown labelが正しい場合も、全armでgrounded
accepted abstention は0だった。

### 有料の出力失敗と停止の相互作用

Gemma main は **87 generation calls、ok71・length16**で、read30・integrate29・
review28からなる。reviewの内訳は整形式PASS5・FAIL2・UNKNOWN5・length16。
length16件全てが固定512-token capに達した応答であり、費用と未成功を残す。
設定した有界structured-review経路の失敗で、モデル理解能力やscheduler効果と
ここでは分離できない。確認結果を見てcap/promptを拡張していない。

| 固定親 | A | B | C参照 |
| --- | --- | --- | --- |
| L1-1：回答可能 | semantic FAIL、escalation | review length | supported |
| L1-2：回答可能 | `no_progress`＋review length | supported | 正しいlabel、review length |
| L2-1：回答可能 | 修正版review前に6-call cap | review length | 誤受入 |
| L2-5：情報不足 | 正しいunknown、`no_progress`＋review length | 正しいunknown、semantic UNKNOWN | 正しいunknown、review length |
| L3-1：回答可能 | 正しいlabel、`no_progress`＋review length | review length | supported |
| L3-2：回答可能 | `no_progress`＋review length | 正しいlabel、review length | 正しいlabel、review length |
| L4-1：単純回答可能 | supported | 正しいlabel、review length | 正しいlabel、review length |
| L4-6：情報不足 | `no_progress`＋review length | review length | 正しいunknown、review length |

全8親・全3armを掲載し、詳細なsource/引用/receipt errorは
[failure analysis](../experiments/ollama/results/v0.2.3/failure-analysis.json) と
[全stage review](../experiments/ollama/results/v0.2.3/stage-failure-review.json) に保持する。
後者はpilot24件の全stage、Qwenの未知/未実行も含む。A-L1-1はreaderが架空の
引用`unknown`を出してliteral検証で拒否され、統合時にはdocument2だけを見た。
A-L3-1は旧document1で偶然正しいlabelを出したが、現行document2と個人statusの
document3を欠いた。L4-6のA/Bは到着記録の欠損を「no」と扱い、Cは正しいunknown
だがreview lengthで失敗した。観測された経路であり、因果寄与を分解したものではない。
Aの `no_progress` は5/8、Bは0/8だった。Aの5件全てにreview-length faultも
存在する。事前定義したauxiliary16件は全て `not_eligible_for_auxiliary` で、補助
生成は0。対象subsetでfaultのない適格継続は得られず、Qwen blockも停止したため、
**追加2callbackのlive感度効果は評価できない**。平均差0や対象外記録から、停止規則を
変えれば改善すると推定しない。model混合はfreeze/実施しておらず、予算枯渇を理由に
実施済み・中途失敗とは扱わない。

### Qwen：未知実行であり、性能0ではない

shuffleされた最初の確認keyは `confirmation-L2-5`、Aだった。readerが固定の
通常 **120秒 deadline** に達し、HTTP wall **119.985秒**、controller segment
**122.218秒**を観測した。server usage/load/prefill/generationの確定receiptは
得られない。**generated512/total4608 tokensの予約**と実消費不明のpending1件を
ledgerに残し、全ての後続生成を停止した。他のQwen main **23 keysは未実行**。
回答可能6pairと情報不足2pairは全て未解決で、**paired N=0、平均/CIはnull**である。

元wrapperの `execution="completed"` はterminal rowを保存して返した意味だけで、
`oracle_assessed=1` も回答がないことを採点しただけである。確定推論の証明ではない。
SDKの `pending=false` はopen SDK attemptがない意味であり、HTTP ledgerの
`pending=true`・`known_attempt_termination=false` と区別する。Qwenの回答可能
成功率を0/6と結論せず、安全なabstentionや失敗確率0ともしない。未実行armの性能
は未観測である。rawの `unexecuted_due_to_budget` はここではgeneric labelで、
詳細停止理由は **pending_or_unknown_consumption**。8時間/call/token上限の枯渇
ではない。完了したQwen開発pilotを、欠けた確認比較やtimeout原因の特定に代用しない。

### 全着手費用と空の成功subset

| Gemma範囲/arm | 予定親 | Generation calls | Generated/total tokens | HTTP wall合計 |
| --- | --- | --- | --- | --- |
| 回答可能 A | 6 | 22 | 3845/13408 | 302.329秒 |
| 回答可能 B | 6 | 27 | 4705/16620 | 376.752秒 |
| 回答可能 C | 6 | 12 | 2753/8716 | 201.314秒 |
| 全8親 A | 8 | 30 | 5511/18706 | 444.050秒 |
| 全8親 B | 8 | 37 | 6092/22652 | 492.906秒 |
| 全8親 C | 8 | 20 | 5013/15623 | 363.252秒 |

Gemma全87callsのserver countersはload **18.844秒**、prefill **490.278秒**、
generation **787.613秒**、client HTTP wall **1300.208秒**を別に合計した。
controller CPU・全trial経過時間・energyではない。**A/B双方がsupport完了する親は0**で、
成功subset N=0、費用比較はnull。元summaryの空aggregateの0を、費用0の成功実測と
解釈しない。Aの合計消費の少なさには未成功の早期停止も含み、同じ完了業務の効率改善
とは言えない。Cの消費も、異なる初期情報量と手順に条件付けた参照である。

smoke・pilot・main全体で **182予約、usage確定181件、未知1件**を保持する。
既知の観測小計は **generated31,344/total113,783 tokens**。実際のgrand totalは
**null**であり、未知を0として加算していない。Qwenの512/4608予約と欠損durationを
保持する。追加の有料修復・retry・auxiliary・混合生成を総数から隠していない。
API料金・電力・CO2は測定していない。

## 同一性・再現・残る状態

| 固定対象 | Identity |
| --- | --- |
| Implementation commit | `481419e252d233d712de237e96af2ae6184b9b33` |
| Candidate wheel build commit | `1ed12f13c4d5b1a78fc39f9d1fb476da78f3449a` |
| Candidate wheel SHA256 | `8227a37be95b615f1608619592298b401bfc73cc412b90857e07ccada8215bc5` |
| 実 installed package-byte fingerprint | `dca4042a019b0af214b6f9e39fa1aaef2d9547c091e828020929be323d9cdd6b` |
| Experiment harness SHA256 | `2edd5334dfefa7dc16d4c4327cd9109834300bb779532cb15b269424b0abb7b9` |
| v2 protocol SHA256 | `5775bc0f540bb60df81631645229bb2ba51aadc81d5ba0de1b00fae68d74a68f` |
| v1 protocol SHA256 | `d116d3fdba875c3aed4eb9f79a89cc18274b2794d0fdeb79a8fb667e644560e1` |
| 元4時間 segment manifest SHA256 | `a8f554ce9ae8f3ba0b73e29af2bac0fe2677e97e7bca92d69c38834cfcf1d19e` |
| 確認 freeze JSON SHA256 | `a9677a9a1cecd75259fc841c2ab588cc66094b354fe3276e6e7a2bf84b148f77` |

[protocol](../experiments/ollama/protocol.json) と
[freeze](../experiments/ollama/results/freeze-v0.2.3.json) は model、task/gold、
prompt/schema、decode、code、budget、予定 keys を固定する。
[実験 README](../experiments/ollama/README.md) に、実装済みの `preflight`、
`backend-smoke`、`pilot`、`amend-wall`、`freeze`、`live`、`resume`、`analyze`、
所有 server の起動条件、小さな callback 例を示す。普通の外部 installed-wheel
環境から `python -I` で直接 script を実行する。experiment だけ checkout から
import し、`src` は package path に追加しない。実験コードは wheel 外にあり、
package import や普通の CLI は Ollama に接続しない。

保存済みデータの再集計は `analyze --directory RUN --output OUTPUT` であり、
生成を発行しない。`resume` は同じ freeze の実行を継続し、完了 keys を skip、
確定済み HTTP receipt は保存された SDK attempt を network 再送なしで精算できる。
未確定/未知 receipt、不完全 journal、identity 変更は再開を止める。**今回のrunは
引き続きblockedであり再dispatchしてはいけない**。owned server停止は未知usageの
精算や予約返金ではない。新たな再現
は別の実 request を発行するため再集計と区別する。temperature0・同 seed でも
model output の byte 同一性は保証しない。

READMEのcustom callback例は、checkout外のinstalled候補と既にblockedのledgerで
実行した。**callbacks/actions0・新規生成0・answerなし・SDK satisfactionなし**。
共通pending gateの動作を示すもので、custom資料へのlive回答精度は検証していない。
checkpoint/resultを採点taskとは別に保持する。

owned server PID12912と追跡した子processは
`2026-10-05T12:54:48.0119207Z`〜`12:54:48.1758553Z` に停止を確認し、owned
remaining PIDsは0。既存PID9536/port11434は維持し、version0.35.0を返した。
無関係/shared processを停止せず、request再送もしない。未知HTTP予約は未精算のまま。
最終ledger SHA256は
`99c53cebeb3f87683330bd1d12dcf455757502642c9d370d33b8abb68ba83a5c`。

### 完成したローカルbundleと保存データ再集計

| 保存成果物 | 実際のローカル同一性 |
| --- | --- |
| `ollama-raw-v0.2.3.zip` | 1,822,461 bytes、SHA256 `c4a1ca613a70b61fb3ac3bc035537e439f962a330816bc9fe5a2fdf8288392a5` |
| ZIP data manifest | data files198、非圧縮source18,626,914 bytes、`MANIFEST.json`/`EXCLUDED_SOURCES.json`を含めZIP entries200 |
| `MANIFEST.json` | SHA256 `540de0ecb333a4d29894b0a6aeaf610f2b2be1ce1265e076c249bb94325a4486` |
| 別の [artifact provenance](../experiments/ollama/results/v0.2.3/artifact-provenance.json) | SHA256 `9c57ce0298d6619ae40af012055b6db25a10e1bfa70290ad8d468baf070a993d` |

完成ZIPを再度開き、198 data-file hashesと全200 entriesのintegrityを検証した。
manifest自身と除外recordはmanifestによるself-hashの対象にしない。provenanceは
不変ZIP完成後に書く別assetであり、自分が記録するZIPの中には入れない。
初期v1 journalは1,221,476 bytes、prefix hash `6237c35b…6ab6707`で、最終ledgerの
正確なprefixのまま残る。履歴コピーを追加call/tokenとして二重計上しない。

最初のstrict UTF-8 packagingで、Windowsのcustom callback診断stdoutがCP932
であることを検出した。元診断bytesを別途保持し、rawの
`callback-example-output-observation.json`にbase64でlossless保存した。
公開UTF-8 transcodeのsemantic identityも確認した。出力encodingの修正であり、
再送・生成は0、model responses/request-receipt journalsは変更していない。
Windowsで診断stdoutを再現する場合は`PYTHONIOENCODING=utf8`を設定する。

予定するRelease assetsは
[raw ZIP](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/ollama-raw-v0.2.3.zip) と
[raw checksums](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/OLLAMA_RAW_SHA256SUMS)
で、この測定snapshotでは未uploadである。公開後の次のPOSIX-shell手順はtagged
実験sourceと普通にinstalledしたwheelを使い、検証したarchiveを展開し、新しい
directoryへ再集計を出力する。Ollama生成requestは発行しない。

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

補助recountは回答可能6親と情報不足2親を分け、未解決予定pairを残す。
archiveの`analysis/answerable-recount.json`とinput hashes/metricsを照合する。
helper SHA256は
`a1fa61f52d7554a417240c959c953a5181a2afe1188e5317e1ce506bf10292e9`。
保存recountと同じく生成行のseed filterは指定しない。bootstrap seed23031041は
helper内で既に固定されている。
上の手順は再現用であり、将来のtag download/installが既に通過した主張ではない。
v0.2.3 manual/native CI、GitHub Release、PyPI、fresh official-index installは、
この公開前snapshotで未検証の別段階である。実際の結果は後で添付する
[publication verification asset](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.3/publication-verification-v0.2.3.json)
へ記録する。

最初のmanual run [37317646260](https://github.com/kadubon/evidence-gap-router/actions/runs/37317646260)、
commit `f302f7f8c3681d47e294367f01748d6fbc73e650` はlint・mypy・Linux source
suite（621 passed、Windows限定9 skip）を通過後、frozen-package byte equality
で失敗した。測定したWindows Git archiveは`core.autocrlf=true`で非空package
24 filesがCRLF、Linux checkout blobはLFだった。LF→CRLF変換後は全25 filesが
完全一致した。`.gitattributes`に`src/evidence_gap_router/** text eol=crlf`を
加え、測定済みcandidate bytesをCIで再現する。core semantics・freeze記録・
一致gateは変更しない。このsnapshotでは第二manualと実公開は未実施であり、
後日の結果は別のverification assetへ保存する。

利用者の明示 v0.2.3公開要求が、添付仕様の当初の新versionなしの仮定に
優先する。既存 v0.2.2成果物は不変に保つ。

現時点の根拠は、明示的な権限、現行 evidence binding、保持された費用、有界継続
を監査可能にする SDK の用途を支持する。LLM checker を意味的真実の oracle には
しない。GemmaはA/Bの完了改善や同じ成功課題での費用比較を識別できず、Qwen確認は
未知実行により結論不能である。pooled情報は一部の短い課題で役立ったが、誤受入と
review-cap失敗があるため信頼性・性能上限としない。短い資料が1 contextに入る用途では
分割routingが不要な可能性を残す。この CPU 観測のローカル実験を、一般的 agent stack の優位、
統計的独立性、集団超知能、API費用削減、energy削減の証明とはしない。
