# v0.2.2 工学測定

固定した共通 runner の回帰セットでは、可解145親 task の完了は **EGR145/145**、
fixed-feasible **122/145**、verify-first **127/145**、random-feasible **133/145**でした。
各方式240親 task で、評価した誤完了は0件です。観測済み人工課題で共通の gap/必要性/
helper 適格性を条件とした順位選択の結果であり、独立 scheduler に対する一般優位では
ありません。検証済み proof の性能はほぼ同じです。別経路の候補 helper 修正は代替経路の
再訪を除きますが、単純な入力では追加費用も観測しました。

[元の v0.2.1 報告](benchmark-v0.2.1.ja.md)と[停止指標の訂正](benchmark-v0.2.1-erratum.ja.md)
は別に保持します。旧80/95対70/95のラベル差は安全性の改善ではありません。新4方式は
非可解95親 task に対して、既知の適切な停止75、不確実な未完了5、実行障害15で同じです。
未知の消費・作用を残し、新測定で旧観測を書き換えません。

## 識別子・環境・実行制御

| 記録 | 値 |
| --- | --- |
| Protocol | `egr-022-engineering-v1` |
| 測定実装 commit | `08c81a2387db7047b9599d153f48893e510fe85d` |
| 公式旧 runtime commit | `3e6a547dd38af9668115aaad9d9d30129c018c1b` |
| 固定時刻 | `2026-10-05T09:07:39Z` |
| Protocol SHA256 | `4a0ef6b5d7fdcd474f260aba124851ca96d0b55b705ee58dd7d1a84ad7ff7faf` |
| Harness SHA256 | `32512950572d2f78280f5fbda505d6c94a67e44c3c9d60337466f2bbde55aba5` |
| 測定0.2.2 wheel SHA256 | `66b4cad4d4f80c81871c0caf6daa28c472d5fabef310a429bc59e2f85e6059e9` |
| 公式0.2.1 wheel SHA256 | `61129ec160c6c9d718f5173fa0281cdcc735cfdc9222138f45584a6b71202917` |
| 測定0.2.2 package fingerprint | `b74c3e906270813246c3871e71a32c40900bbf4bfdc5a7d21577880fddec2afe` |
| 公式0.2.1 package fingerprint | `5df6a0b5e7c521079e29475950addf6e1b84d62b3f3c70033307a82643e8341a` |
| OS / machine | Windows 11 `10.0.26300`、AMD64 |
| CPU / 電源 | AMD Ryzen 7 8840HS、8 core / 16 logical processor、Balanced |
| Python / Pydantic / core | 3.12.14 / 2.13.5 / 2.46.5 |
| その他の一致した runtime 依存 | annotated-types0.8.0、typing-extensions4.16.0、typing-inspection0.4.4 |

新旧 SDK は checkout 外の通常の非 editable wheel install です。installed package の byte
を宣言 wheel と照合しました。package fingerprint は package 相対 filename → byte SHA256
を整列した compact canonical JSON の SHA256 で、生成 cache を除きます。後の文書/metadata
build で wheel 全体の hash が変わっても、実行 package と harness/protocol の一致を要求します。
[freeze](../benchmarks/results/freeze-v0.2.2.json) は repository 内の固定であり、外部事前登録
ではありません。確認前に runtime/checker/generator を固定しました。

1,680 key を事前列挙した controller が直列実行し、対応 block 内を seed220229 で並べました。
正式測定中は執筆・開発・テスト・別の重い測定を止めました。Codex desktop は稼働したままです。
CPU affinity/priority、熱状態、background service、動作周波数は制御していません。
残る desktop 変動を含む、一台の環境での工学観測です。

worker 全体の上限は wall10秒、Job 累積 CPU8秒、peak aggregate private committed bytes
256MiB です。venv の子 process も含めます。parent の peak working set は別枠512MiB。
全体は wall7,200秒、CPU3,600秒と事前の phase 上限です。owned Windows Job へ実行前に
割り当て、観測した超過でその Job だけを終了します。sampling の overshoot はあり得ます。
private committed bytes、working set、traced Python allocation は異なる指標です。

実行は **wall1,093.901秒、worker CPU938.391秒、parent CPU66.578秒**でした。
worker CPU/memory の観測欠損はありません。観測最大は Job private committed bytes
61,079,552、parent working set70,348,800でした。普遍的な memory 上限の保証ではありません。

| Phase | 要求 worker | 完了 worker | CPU 上限による打切り |
| --- | --- | --- | --- |
| B、主方式と固定参照 | 1,020 | 1,020 | 0 |
| A、機能監査 | 2 | 2 | 0 |
| C、proof と helper | 594 | 566 | 28 |
| 新確認 | 64 | 64 | 0 |
| 全体 | 1,680 | 1,652 | 28 |

非対応・未実施・wall timeout・削除した key はありません。worker 完了は課題完了ではなく、
callback/factory/receipt の処理済み障害も含みます。28 resource-limit は旧 helper worker で、
内部 phase、不返却の outcome/cost は未知の右打切りです。plan 単体の時間下限、正確な秒数、
費用0へ置き換えません。

## B：共通 runner の方式回帰

旧240親 task（F1〜F8各30、seed982451653）は **観測済み回帰データ**です。
元の candidate 順、random seed17だけを再実行しました。主4方式960試行、別の固定参照60試行。
旧 reversed/renamed/他 random seed は再実行せず、その反復を含む区間を作りません。

F1は由来と同一由来の重複、F2はexactな段階的依存、F3は部分的必須 checker/自己検証、
F4は契約・依存変更と再解消、F5は否定的記録の正確な対象と矛盾根拠、F6は固定手順と初期完了、
F7は権限/資料不足・障害・不明消費・no-op、F8は実CSV/rules・厳密な十進数・snapshotを扱います。
raw validity と許可/予算込みの可解性は別です。初期化も実際の発行 callback を使い、
支出を別記して全方式の総予算へ同じように足します。固定 PASS や oracle label を返しません。

すべて公開 `run` を使い、純粋な selector だけを変えます。完全な pool、availability、発行、
入力 view、receipt/error、進捗/再計画、有限回数、外部 worker 上限は共通です。
`feasible_actions` は safety だけでなく未充足 gap/必要性/helper 適格性を含みます。
その共通機構を条件とした順位付けの比較です。

独立 oracle は raw 数値/file 条件、receipt identity、active な exact target、owner/scope/
契約、依存、checker 権限/revision/purpose、矛盾の全関連入力を確認します。`plan` や内部受入
predicate を正解として使いません。異なる active required target はすべて検証を要求し、
有限 recipe の least grounded support を評価します。一般的な negative cycle は別の runtime
回帰であり、この方法 oracle の対象外です。

| 方式 | 完了 / 可解 | 誤完了 / 全試行親 | 誤停止 / 可解 |
| --- | --- | --- | --- |
| EGR | 145/145 | 0/240 | 0/145 |
| Fixed-feasible | 122/145 | 0/240 | 23/145 |
| Verify-first | 127/145 | 0/240 | 18/145 |
| Random-feasible、seed17 | 133/145 | 0/240 | 12/145 |

各方式の非可解95親 task は **既知の適切な停止75、不確実な未完了5、実行障害15**です。
oracle は各240件を評価しました。既知の停止には定義した非可解性、未完了、正常な domain 停止、
上限のある消費/作用の既知性、pending invocation なしを要求します。不明な5件を既知の安全な
成功にしません。各方式の検証費用15件は不明のままです。この費用件数は障害/不確実な停止の
件数と同じ意味ではありません。失敗も支出済み試行として残ります。

| Family | 可解N | EGR | Fixed | Verify-first | Random17 | 誤完了の全親分母 |
| --- | --- | --- | --- | --- | --- | --- |
| F1 | 18 | 18 | 0 | 0 | 18 | 30 |
| F2 | 24 | 24 | 24 | 24 | 24 | 30 |
| F3 | 24 | 24 | 24 | 24 | 24 | 30 |
| F4 | 22 | 22 | 17 | 22 | 22 | 30 |
| F5 | 16 | 16 | 16 | 16 | 4 | 30 |
| F6 | 21 | 21 | 21 | 21 | 21 | 30 |
| F7 | 0 | 0 | 0 | 0 | 0 | 30 |
| F8 | 20 | 20 | 20 | 20 | 20 | 30 |
| Adequate budget | 132 | 132 | 112 | 116 | 120 | 192 |
| Tight budget | 13 | 13 | 10 | 11 | 13 | 48 |

旧元順序の145/142/143/145に対し、現行は145/122/127/133です。独立した新旧 trace の点検では
baseline 減少はすべて共通 runner の `no_progress` に対応しました。fixed は20件（F1の16、
F4の4）、verify-first はF1の16、random はF5の12です。最初の action と初期poolのfeasible順は
変わりません。F1は `read:repeat`、F4の4件はrules0の内容/source/groupを繰り返す `read:extra`、
F5は `read:alias` です。旧手書きloopは非空 evidence payload を進捗として継続し、公開 `run` は
不要な同一実質/入力bindingを1 callback後に止めます。例えばF1固定順index1は旧repeat→e1→e2→
check-e1→check-e2から、repeatだけで止まる形になりました。EGRの完了減少はありません。
共有する実質進捗契約の影響を含む差で、順位改善や独立stack優位と解釈しません。
旧の全variant区間は0を含み、その記録は変更しません。

| EGR − baseline | 対応可解N | 完了差 | 95%親paired bootstrap区間 | 勝ち / 同等 / 負け |
| --- | --- | --- | --- | --- |
| Fixed | 145 | 0.15862 | [0.10345,0.22069] | 23 / 122 / 0 |
| Verify-first | 145 | 0.12414 | [0.07586,0.17931] | 18 / 127 / 0 |
| Random17 | 145 | 0.08276 | [0.04138,0.13103] | 12 / 133 / 0 |

seed2239で親をpairedに1,000回resampleしました。ここは方式ごとに各親1試行であり、欠けた
variant のcluster平均を作りません。区間は人工課題構成内の変動を示します。実業務の無作為標本、
未見母集団への効果、同等性検定ではありません。

## 同完了費用、全課題費用、固定参照

通常方式時間にはprofile/tracemallocを入れません。controller区間は公開runの実行/再計画経路、
trial CPU/end-to-endはsetup、実初期化、最終判定、oracle、snapshotも含みます。cold SDK importと
whole-worker startup/IPCも別記します。これらを純粋な順位付け費用や最小pipeline費用と呼びません。

| 両者成功pair | N | callback差 EGR − baseline（95%区間） | controller wall差ms（95%区間） | controller CPU差ms（95%区間） |
| --- | --- | --- | --- | --- |
| Fixed | 122 | −0.16393 [−0.27049,−0.07377] | −0.16216 [−0.30154,−0.04763] | +0.12807 [−1.15266,+1.53689] |
| Verify-first | 127 | 0 [0,0] | +0.00937 [−0.04216,+0.05986] | +0.49213 [−0.86122,+1.84547] |
| Random17 | 133 | −0.06015 [−0.13534,−0.01504] | −0.11674 [−0.20776,−0.04043] | +0.35244 [−1.05733,+1.64474] |

成功を条件に選んだ既知費用pairであり、全課題の節約率ではありません。verify-firstのcallbackは
同じで、overhead差も区間が0を含みます。すべてのcontroller CPU区間が0を含み、desktop変動と
Windows CPUの量子化がsubmillisecondの解釈を制約します。CPU中央値0は処理0ではありません。

| 全240親試行 | 平均callback | 既知検証平均（N225） | 平均controller wall ms |
| --- | --- | --- | --- |
| EGR | 2.13750 | 1.25778 | 2.32486 |
| Fixed | 1.99583 | 1.10222 | 2.30581 |
| Verify-first | 1.87917 | 1.07111 | 2.17171 |
| Random17 | 2.20417 | 1.22667 | 2.44121 |

baselineの小さい全課題平均には可解課題の失敗も含み、効率改善ではありません。全callback費用は
既知ですが、各方式15件の検証費用は不明で、既知平均のNからだけ除き、0へ補いません。
EGRの完了145親/未完了・障害95親の平均callbackは2.49655/1.58947です。
[方法summary](../benchmarks/results/v0.2.2/summary.json)は全方式のoutcome/family/budget/
全課題/選択pair費用と分母を保持します。

callback一回に同じ0/0.001/0.01/0.1/1秒を加える感度分析も記録します。仮定0.01秒の選択pairで
EGR wall差はfixed−1.8015ms、verify-first+0.00937ms、random−0.71824msです。
実測latency、token節約、LLM料金、商用ROIではなく、加算仮定です。

固定参照60件は別枠で、F6 raw完了25/30、F8 20/30、評価済み誤受入なしです。
資料readはそれぞれ50/60回、validationは各30回。batching/receipt/SDK上限の契約が違い、
callback/検証数を同じSDK費用として比べません。共通harness setupも残ります。F6/F8の可解な
routed task は全方式同完了で、手順既知なら単純pipelineで足りる場合があります。

## A：受入と継続の診断

各installed版で固定14機能性質を確認しました。旧0.2.1は11/14、新0.2.2は14/14を満たし、
未評価・case例外はありません。旧3件の不適合は部分的な外部解消basis、同digest関連alias、
保持された部分解消履歴でした。旧は誤ってsatisfiedとなり、新版は履歴を保って未解消にします。
正当な全関連入力の外部根拠は受け付けます。実支出を含む失効、契約/checker更新、保存/再解消、
正確な否定的対象、自己検証禁止、helper binding、実fileの厳密decimal拒否、サポートする大きな
snapshotは使えます。有限の機械的性質であり、認証や母集団CVEの主張ではありません。

## C：proofと候補helper

検証済みproofと未取得helper候補は別familyです。time、訪問数、traced allocationを別processで
測り、通常timeはwarmup1回と10反復。入力/候補構築、実seed callback、snapshot、意味の判定を
別記します。構築・初期化の値は単回であり、安定したpercentile推定ではありません。

| Family / 版 | 完了 / 要求measurement | CPU打切り | reference一致 / 不一致 / 未評価 / 不完了 |
| --- | --- | --- | --- |
| Proof /0.2.1 | 180/180 | 0 | 180 / 0 / 0 / 0 |
| Proof /0.2.2 | 180/180 | 0 | 180 / 0 / 0 / 0 |
| Helper /0.2.1 | 89/117 | 28 | 63 / 0 / 26 / 28 |
| Helper /0.2.2 | 117/117 | 0 | 63 / 0 / 54 / 0 |

Proofはchain/diamond/branches/pure-cycle、size4/8/16/32/64、checker1/2/3の60入力です。
両版とも既にindexed proof evaluatorを使い、60対応plan時間の旧/新比中央値は **1.00600**
（新が短い38、長い22）です。ほぼ変わらない観測で、proofを再高速化した証拠ではありません。
制限したreferenceは同じrequired parentとungrounded cycleを確認し、一般negative/grounded
alternativeは機能回帰で別に扱います。

Helper39入力は代替1/2/4、深さ4/8/12/16/24/32/64、shared/diamond/branches、複数checker、
current evidence、権限不足、exact scope/digest、optional/satisfied owner、失効/契約更新、
grounded/ungrounded cycleを含みます。独立した走査AND/OR referenceはdepth≤8のpositive recipe
だけを扱い、consumer rootを根拠にしません。小21入力×3modeは両版一致します。大入力の完了を
独立reference一致とせず、未評価を残します。

| 対応normal-time範囲 | 正の有限pair / 入力 | 旧/新比中央値 | 不完了pair | 完了した0/不在phase pair |
| --- | --- | --- | --- | --- |
| Helper plan | 29/39 | 1.02193 | 10 | 0 |
| Helper plan+start/observe+binding progress | 29/39 | 1.19479 | 10 | 0 |
| Helper start/observe | 23/39 | 1.28855 | 10 | 6 |
| Helper binding progress | 23/39 | 1.02900 | 10 | 6 |
| Proof plan | 60/60 | 1.00600 | 0 | 0 |

6件の継続phase不在はcallback未選択であり、正の費用欠損ではありません。打切り/0phaseに
速度比を作りません。helper対応29planの新は短い16、長い13。代替1のchain7件の比中央値は
0.816で旧単純経路が有利でした。指数的再訪の除去はすべての入力の低費用化を意味しません。

| Helper入力 | 旧 / 新normal plan中央値ms | 旧 / 新normal sequence中央値ms |
| --- | --- | --- |
| Chain深さ4、代替2 | 0.19175 / 0.15790 | 0.67470 / 0.45170 |
| Chain深さ8、代替2 | 1.15370 / 0.22105 | 3.36725 / 0.60160 |
| Chain深さ12、代替2 | 15.96050 / 0.30435 | 47.76690 / 0.77745 |
| Chain深さ8、代替4 | 157.40240 / 0.35425 | 474.34600 / 0.88090 |
| Chain深さ16、代替2 | whole-worker CPU上限 / 0.38700 | whole-worker CPU上限 / 0.97575 |
| Chain深さ24、代替2 | whole-worker CPU上限 / 0.52315 | whole-worker CPU上限 / 1.28315 |
| Chain深さ64、代替1 | 0.59660 / 0.70430 | 1.37910 / 1.74480 |

別count workerの旧action-path訪問は深さ12/代替2で8,191、深さ16で131,071。
新は各phaseでaction subproblem25/33、rule edge59/79です。単位が違うため普遍的な訪問数
速度比ではありません。深さ16はcount/memoryが完了しても、通常timeの10反復workerはCPU上限を
超えます。plan outcomeの矛盾ではありません。旧28打切りはcount9/memory9/time10のCPU超過で、
内部phase不明を保持します。

Memoryは別の単回traced replayであり、通常time、RSS、Job memoryではありません。
helper完了memory30pairでは新が小26/大4、proof60pairでは小41/大19でした。一般的なmemory改善の
証明ではありません。例えば深さ64/代替1は旧/新769,199/671,327 traced bytesですが、新の通常
planは遅くなります。単一指標の利点を総合効率改善にしません。
非対応集合のhelper中央値は旧393,774bytes（完了30入力）、新407,896bytes（39入力）です。
完了した入力集合が異なるため、この差をmemory優位や悪化と解釈しません。

## 新確認と保持した証拠

未使用seed49979687で32条件を生成し、実topology、代替、前提/current validity、availability/
budget、更新条件を変えました。両版semantic worker32/32完了、small独立helper reference32/32一致、
不一致/未評価なしです。観測済み回帰とは別です。有限の意味を確認し、実アプリ完了率ではなく、
数値/ID変更だけを独立した外部課題として増やしません。

[Controller summary](../benchmarks/results/v0.2.2/controller-summary.json)は全cell、打切り、
reference状態、時間分母、count、allocation範囲を保持します。formal raw JSONL SHA256は
`7c8d40a6dd80db41adfa91ce4e0ad581119032d421ccaaac22675b2b66473dd2`、
execution-manifest SHA256は
`652f80e1627aaa4ab3a7b4b48f5884423b46284901c98c3294878ec70129a305`。
[Provenance](../benchmarks/results/v0.2.2/artifact-provenance.json)は測定candidateと最終配布物を
分けます。旧証拠、診断再現、exact source/constraints、wheel、freeze、新traceを保持します。
新 `benchmark-raw-v0.2.2.zip` を生成し、manifest資料54件のhashと全56entryのZIP整合性を
確認しました。12,592,735bytes、
SHA256 `e90060aae7c2fac6ebe3f920a74a7066a4b63353daf7f7f0ffdbc23440b3f37a`。
manifest資料54件と `MANIFEST.json` / `BUNDLE_README.txt` からなり、変更していない旧ZIP、
formal raw/CSV、固定LF source/wheel/constraints、旧40診断、別labelの測定後独立確認を含みます。
[Checksum](../benchmarks/results/v0.2.2/BENCHMARK_SHA256SUMS)にarchiveを識別します。
[予定raw Release asset](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.2/benchmark-raw-v0.2.2.zip)
のupload済みとはここでは記録していません。archive生成、upload、native CI、PyPI確認の状態は
[validation](validation.md)で分けます。[再実行手順](../benchmarks/README.md)も参照してください。

この正式実行後にruntime/oracle/generator/protocolは変更していません。結果/文書収録はmetadataを
変えても、公開時に測定済みpackage/harness/protocolの一致を要求します。
結果収録時に `test_summarize_022.py` の単独source-test import設定も調整しましたが、
測定したruntime/harness/generatorのbyteは変えません。CPUのみでLLM/GPU/有料推論を
使わず、source独立性、金額節約、能力成長、リスク0を実証しません。条件によって仕事が変わる証拠
処理にはroutingが候補で、既知の固定手順はより単純で低費用なpipelineが適する場合があります。
