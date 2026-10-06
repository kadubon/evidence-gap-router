# ローカルOllama実験 — v0.2.4

訂正後の主確認では、EGRの選択順Aが検証優先Bを下回りました。解答可能12親課題の
支持付き完了はQwen A 0/12・B 8/12、Gemma A 3/12・B 8/12です。全資料を先に渡す
Cは各12/12・10/12。この少数の人工課題ではAの選択順の優位を支持せず、全文がcontextに
収まる仕事では小さな固定workflowで足りる場合が多いという結果です。

主確認96/96件が終了し、全件の使用量・出力形式が確定しています。通信/形式障害、未確定、
未実施は0件でした。形式と実行の成立は意味判断の信頼性を保証せず、Qwen Aの誤受入は
15/16件です。この結果を見てSDK・oracle・基準を変えていません。停止感度64件と有料の
custom live例も完了しました。この文書は公開前source snapshotで、実際のnative CI・
公開byte検証は[Releaseの確定記録](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.4/publication-verification-v0.2.4.json)に残します。

## 完了した主確認

各モデル・方式は16親課題（解答可能12・本当に情報不足4）で、全16件を独立に採点しました。
正答と根拠判定はreviewと独立です。最終完了には現在のreview・発行receiptの受入も必要です。

| モデル | 方式 | 正答/16 | 根拠付き/16 | 解答可能の最終完了/12 | 全体完了/16 | 根拠付き棄権/4 | 最終review誤PASS/16 | 誤受入/16 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen | A | 3 | 0 | 0 | 0 | 0 | 15 | 15 |
| Qwen | B | 12 | 10 | 8 | 10 | 2 | 5 | 4 |
| Qwen | C | 15 | 15 | 12 | 15 | 3 | 1 | 1 |
| Gemma | A | 7 | 5 | 3 | 4 | 2 | 2 | 2 |
| Gemma | B | 12 | 10 | 8 | 9 | 2 | 1 | 1 |
| Gemma | C | 14 | 14 | 10 | 14 | 4 | 2 | 2 |

主比較は12解答可能親のpaired差です。A−B最終完了はQwen −0.667（勝/同/負 0/4/8）、
Gemma −0.417（0/7/5）。事前2,000親bootstrapの記述的95%区間は各
[−0.917, −0.417]／[−0.667, −0.167]です。誤受入差は各+0.750（9/3/0、区間
[+0.500, +1.000]）／+0.083（2/9/1、区間[−0.167, +0.333]）。誤受入の正の差は悪化です。
解答可能親の根拠付き棄権は両方式0で、差・区間も0。全親が採点済みなので未評価を含む
最良/最悪幅は実測差へ一致します。

情報不足4親は別集計です。Qwenの最終完了と根拠付き棄権差は共に−0.500（0/2/2、
区間[−1.000, 0.000]）、誤受入差は+0.500（3/0/1、区間[−0.500, +1.000]）。
Gemmaは3指標とも差0（0/4/0、区間0）でした。少数・共通familyで、一般化、同等性、
判断の独立性を証明する区間ではありません。

主確認398 callの使用量はすべて既知で、生成63,197／総320,589 tokenです。
全試行・成功/失敗内訳とload/prefill/生成/client時間は[英語技術報告](ollama-experiment-v0.2.4.md)
に載せます。同品質のA/B双方成功はQwen 0親で、token・時間はnullです。Gemmaは3親で
A 20call・生成2,529/総15,874・client 332.033秒、B 16call・2,576/14,307・267.171秒。
Aには19.707秒のloadがあり、Bは0.055秒です。成功subsetの選択とcache/load順の影響を
含むため、Qwen Aの低いraw費用を同品質の節約とは解釈できません。

保存済みQwen親 `confirmation024r2-L1-1` では、Aがdocument-1の規則/M事実だけでunknownを
統合し、reviewerが追加sourceなしでPASS、workflowが満足を報告しました。取得可能な
document-2にはNの事実があり、独立oracleは根拠不足と判定誤りを記録しています。
同じ親のB/Cは根拠付きで完了しました。一つの早期誤受入経路の観察であり、全失敗の原因を
証明したとはしません。利用者が宣言する要件とmodelのPASSだけで事実の支持は保証されず、
用途に適した検証者が必要です。

## 完了した停止感度分析

事前指定した8親課題（解答可能4・情報不足4）を両モデル、A/B、strict/boundedで新規実行し、
64/64試行が終了しました。全使用量・終了・独立採点は確定し、未確定・未実施・通信/形式障害は0。

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

boundedの対象条件は全群で0件、追加callbackも0件でした。したがって回復の効果と選択順との
相互作用は測定できていません。温度0・固定seedでもfresh出力やcache/実行順の変動があり、
発動しなかったpolicyがstrict/bounded間の差を生んだとは解釈できません。
全8親でA−Bの支持付き完了差はQwen strict −0.625、bounded −0.500、Gemma strict 0、
bounded −0.250です。親bootstrap区間、勝/同/負、誤受入・棄権差、全費用は
[英語技術報告](ollama-experiment-v0.2.4.md)と[機械可読集計](../experiments/ollama/results/v0.2.4/summary.json)
に記録しています。同じ親を反復した64件を独立した親の標本数と扱いません。

## 訂正後の事前検査

新warmは各モデルでreader・integrator・reviewerを2回、計12生成と空load2回が確定。
生成2,696／総18,507 tokenです。Qwenは要件Nを真から偽へ変えるとyesからnoへ変わり、
両reviewはPASSでした。Gemmaは最初にunknownと誤りreviewがFAIL、変更後はno／PASS。
このQwen preloadは既に常駐した状態の0.032秒で、新しいcold測定とは呼びません。
旧cold測定は下記の履歴として残し、追加のprompt/cap調整は行っていません。

新pilotは4親課題（解答可能3・情報不足1）、24試行、92確定call。
生成14,373／総69,368 tokenで、通信・形式faultとfalse acceptanceは0件でした。

| Model | 方式 | 親 | 正答 | 根拠付き正答 | 検証済み支持 | Calls |
|---|---|---:|---:|---:|---:|---:|
| Qwen | A | 4 | 1 | 0 | 0 | 13 |
| Qwen | B | 4 | 3 | 2 | 2 | 19 |
| Qwen | C | 4 | 4 | 4 | 4 | 8 |
| Gemma | A | 4 | 1 | 1 | 1 | 23 |
| Gemma | B | 4 | 2 | 2 | 2 | 19 |
| Gemma | C | 4 | 4 | 4 | 4 | 10 |

これらを主確認の分母へ入れません。対象表記が不整合だった直前のwarm・部分pilotは、
元source・入力・checkpoint・費用を保持した別の開発履歴です。
実template/tokenizerで1,335件を生成なしで検査し、入力＋最大出力枠の最大値は
Qwen 4,612／Gemma 4,222、context 8,192以内。空preload2回を課金台帳に含めました。

新[freeze](../experiments/ollama/results/freeze-v0.2.4-r2.json)は測定source
`23dff942cfbbc76d73799893acaa3a394d70621f`、16親・主確認96件・新規停止感度64件を固定。
SHA256は `3860d9d89f3ca0eeb1e5db6a24612a1d11075b44dde6d9b300244cc90c5a579c`。
24親案は最悪生成予約だけで上限を超えるため除外し、16親案の3,276,800 tokenは
残量3,841,937に収まります。残wallは146,354.53秒、開発実測の保守的request予測は
Qwen 62.058秒／Gemma 50.702秒。中断開発のsampling欠測1件は観測最大overheadを
使っています。A−B成績は課題数の選択に使っていません。

## 保持した初回protocolの開発履歴

初回の主確認は完了しましたが、機械的な証拠保存の不整合により検証済み完了の解釈を
無効としました。省略可能な `feedback` をhostが空文字で補完し、変更していないoracleの
実応答との完全一致条件に反していました。省略したGemmaの応答が特に影響を受けました。
workerと所有Ollamaは未確定・使用量不明0件で停止し、957呼び出しと費用を保持しています。

修正protocol `egr-024-local-ollama-v2` は実際のparsed JSONを保存します。
review/oracleの受入基準と累積予算を変えず、未使用資料と新freezeで再確認しました。
初回結果は修正後の主確認へ混ぜません。以下の開発観察は原記録の履歴です。

現行のQwenとGemmaで、長い入力と条件Qの変更を含むreader・integrator・reviewer
各2回が完了し、すべて使用量が確定しました。先行開発ではQwenが誤ったunknownを
返し、reviewerも受理した例があります。形式の完了と内容の正しさを分けます。
先行する開発試行の出力と費用も同じ台帳に保持しています。

保存した初回 `egr-024-local-ollama-v1` は較正とpilot後に主確認をfreezeしました。
このページには実行済みの分母、方式間差、未確定・未実施、公開後検証を記録します。
未実施の測定や未公開の配布物を完了扱いにはしません。

## 完了したreview較正

24件は12の人工親課題から作った答案候補です。各条件で正当9件、不当15件を
reviewerへ渡し、gold labelは隠しています。24件を独立親課題とは数えません。
旧形式／簡潔形式 × cap 512／2,048 × 2モデルの192 requestすべてで使用量が確定しました。

| モデル | 形式 | cap | 形式完了/24 | 最終20件 | length | 誤PASS/不当15件 | 正しいunknown受理/3 |
|---|---|---:|---:|---:|---:|---:|---:|
| Qwen | 旧 | 512 | 21 | 17 | 3 | 9 | 0 |
| Qwen | 旧 | 2,048 | 24 | 20 | 0 | 9 | 0 |
| Qwen | 簡潔 | 512 | 24 | 20 | 0 | 11 | 1 |
| Qwen | 簡潔 | 2,048 | 24 | 20 | 0 | 11 | 1 |
| Gemma | 旧 | 512 | 13 | 11 | 11 | 3 | 0 |
| Gemma | 旧 | 2,048 | 24 | 20 | 0 | 9 | 0 |
| Gemma | 簡潔 | 512 | 24 | 20 | 0 | 14 | 0 |
| Gemma | 簡潔 | 2,048 | 24 | 20 | 0 | 13 | 0 |

簡潔形式では有限のstatus/reason、最大4件の取得要求、任意160字のfeedbackを使います。
schemaと指示を同時に変えた複合介入です。形式完了は改善しましたが、意味上の誤PASSは
残りました。lengthの断片からPASSを拾いません。事前規則（両モデル19/20以上、簡潔形式の
誤PASS合計最小、同数なら小cap）でreviewer 2,048を選択しました。誤PASS合計24対25の
1件差は一般的な能力改善の証拠ではなく、A−B成績も選択に使っていません。

正当答案9件の受理はQwen旧形式が両capで4/9、簡潔形式は両capで6/9です。
Gemma旧512は3/9、その他は6/9。不当答案15件のうち形式上の判定欠落は旧512で
Qwen 1件・Gemma 7件、他条件は0件でした。誤PASSの分母は予定された不当15件で、
lengthによる判定欠落を意味上の正しい拒否やreviewerの品質改善とは数えません。

最終選択の対象は簡潔な出力契約に限定しました。旧2,048の両モデル合計誤PASSは18件で、
簡潔2,048の24件より少ないため、選択した条件が全比較の中で意味判定に最良という結果では
ありません。出力契約の選択と、誤判定が残る限界を区別します。

固定順blockで実行したため、loadやprompt/KV cacheが時間比較に影響します。
後の2,048条件が速かったことから、cap増加が推論を速くすると因果推論しません。
方式間で生成答案を使い回していません。先行192件の異なる開発較正も原文・実装・
支出とともに保存し、最終較正と合算採点していません。最終較正終了時の開発累計は
426 call、生成66,828／総352,381 tokenです。

## 現行環境と境界

Ollama 0.35.0、Windows x64、Ryzen 7 8840HS、RAM 64 GiB、CPU推論です。
実tagは `qwen3.6:35b-a3b`（報告36B/Q4_K_M）と `gemma4:e4b`（custom 7.5B/Q4_K_M）。
exact digest・template・モデル別licenseは[英語報告](ollama-experiment-v0.2.4.md)と
preflightに記録しています。重み・量子化・template・serverを更新していません。

接続30秒、全応答hard deadlineはQwen 1,800／Gemma 900／preload 1,800秒。
nonstreamなので初token時間は未測定です。context 8,192、temperature 0、
think/truncate/shiftはfalse、常駐60分。serverの30分LOAD_TIMEOUTはload停滞検出です。
最終cycleでは両モデルのreader・統合・review各2回が確定し、長い資料とQの変更も含みます。

最終cycleの空preload待ちはQwen 102.110秒、Gemma 19.687秒です。生成0の応答に
server durationがなく、別計測したserver load CPU時間とはしません。暖機時のclient秒は
通常／長い変更資料の順に、Qwen reader 24.219／36.875、統合28.766／39.453、
review 16.578／32.141。Gemmaはreader 19.594／39.750、統合22.328／19.297、
review 11.813／32.765です。prefillと生成の内訳は英語報告とrawに記録しています。
この暖機cycleのreview capはまだ512で、最終2,048は後の較正とpilotで検査しました。
両モデルの統合はQを真から偽に変えるとyesからnoへ変わりました。一般的な意味判断の
信頼性を保証する例ではありません。

reader 1,024／統合1,536／review 2,048／有料修復1,024、trialは10call・32action・
16verification、Qwen 7,200／Gemma 3,600秒です。選択capから求めるSDK token枠は
102,400、外側transport上限は122,880。protocolの97,280は初期capの値です。
実消費とcontext＋stage capの保守的予約を区別します。

48時間は最初の新予約から開発・待機を含め、4,000 call、生成400万／総4,000万token、
raw 4 GiB。空きRAM下限6.4 GiB、diskは5 GiB＋raw余白、4回連続swap増加が合計256 MiB
または観測不明なら新dispatchを止めます。全瞬間の資源使用を保証する測定ではありません。

A/Bは公開runner・pool・権限・view・callback・費用・停止を共有し、選択順序を比較します。
同一origin/version/topicの明示的な完全転載除外も共通です。Cは全資料先渡しの参照条件。
goldは評価専用で、有限の最小根拠、scope、版、引用、origin、現在の発行receiptを独立確認します。
答案正誤、reviewと独立な根拠付き正誤、現在受入付き完了を別に集計します。
未記録の世界事実、reviewer UNKNOWN、消費不明、未実施を同じ失敗点にしません。

形式完了は最終の統合答案と、修復前も含む全callで別々に記録します。試行単位の
誤PASSは最終reviewと最終答案の独立した根拠判定の比較で、途中の全review数とは異なります。
false acceptanceはworkflowの完了主張が独立oracleに支持されない状態で、routerの満足判定も
別に残します。根拠付き棄権は本当に世界が情報不足の正しいunknown答案で、reviewと独立です。
erroneous stopは採点済み解答可能trialの未完了ラベルであり、停止規則の因果診断ではありません。

answer correctは最終yes/no/unknownの判定labelを作成済みの真値と比較します。根拠判定は
有限のscope付き支持集合、引用、版、発行済みbindingを追加確認するもので、任意の自由文の
説明すべてを一般的な自然言語含意システムで評価するものではありません。

主確認前に実template/tokenizer、実装byte、資料、gold、全key・順序・seed・予算・解析を固定しました。
16親課題は資源と64件の停止感度枠から選び、有意差まで延長していません。
custom live例は6件の新しい有料requestで完了しました。native CIと公開後downloadは
source snapshot以後の段階として[Release確定記録](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.4/publication-verification-v0.2.4.json)で確認できます。
旧v0.2.3のQwen消費不明は旧台帳にそのまま残しています。

## 主確認の対象と保存履歴

訂正後の主確認は16親課題（解答可能12・情報不足4、各family4）の96 trialと、新規64 trialの
停止感度です。現在の92-call pilot・1,335-input context検査・freezeの数値は冒頭に記録しています。
事前の各family親4/5は除外され、XOR、waiver、明示例外、目的地等のその変形は今回live主確認
していません。family構造は開発と共有する人工資料であり、未知の推論familyへの汎化実験では
ありません。

初回pilotの95 call、生成12,621／総69,525 tokenとQwen Bの形式fault・有料修復は
[初回解析](../experiments/ollama/results/v0.2.4-initial/summary.json)とraw履歴に保存しています。
そのGemma最終受入0は保存JSONの機械的不一致を含むため、モデル能力の床効果とは解釈
できません。訂正後の新pilotと主確認を別に測定し、旧試行の費用も累積保持しています。

実測時間からの予測は計画用で、全requestの最大待ちを保証しません。各モデル80 trialの
最大trial時計だけでも合計240時間となり、48時間を超えます。各dispatchで元のwall・call・
token残量を検査し、尽きた場合は予算を延長せず、未着手keyを未実施として保持します。

[実行手順](ollama-guide.md) · [監査](audit-024.md) ·
[v0.2.3の保存済み報告](ollama-experiment.ja.md)

## 累積費用・実例・終了・生データ

累積1,835予約と1,835使用量receiptがすべて確定しました。空loadは14件、生成272,592／
総1,446,319 token、pending・消費不明・terminated-unmetered・未精算予約はすべて0です。
初回957 call（生成133,726／総742,263）、scope不備34 call（7,268／37,450）、
訂正後844 call（131,598／666,606）を元時計・台帳に保持し、主確認と混ぜて採点しません。
正常終了時のcampaign経過は43,933.079秒（12.204時間）。モデルclient待機34,183.476秒、
controller資源採取2,789.252秒は別scopeで、すべてを排他的な時間として加算しません。

新しい健全なkeyで人工温度資料のcallback例を実行し、6件の実request・生成449／総3,271
tokenを課金しました。10℃以下なら許可という仕様と9℃の測定を引用してGemmaがyes、
domainはsatisfied、runnerはrouter_stopped、pendingなしでした。主確認の追加親とは扱いません。
任意の混合モデル実験は未実施です。未完了の全100 chain（pilot11・主確認44・感度45）の
資料・抽出・統合・review・停止をrawに保存しました。

所有serverと子processはnative handleで同一性と終了を確認し停止済みで、共有serverは操作
していません。旧v0.2.3の消費不明callは元台帳で不明のまま、生成512／総4,608の予約を保持します。
資源は採取時点の観察でありpeak・電力・料金・CO2の実測ではありません。

ZIPは25,666,393 bytes・manifest 5,785 entryを検証し、原出力を書き換えずprivateな5ファイルを
明示除外した別export identityです。SHA256は
`274de4b2a99119829fded7a30e7b9bf6bb47179f1ad69b1e5289aa680f6e726f`。
[英語報告の安全な展開・再解析](ollama-experiment-v0.2.4.md#raw-export-and-model-free-reanalysis)
でモデルcallなしに4解析ファイルのbyte一致を確認できます。
ZIP作成、upload、公開download後の検証は別状態として、実際の公開結果を
[Release確定記録](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.4/publication-verification-v0.2.4.json)
に記録します。
