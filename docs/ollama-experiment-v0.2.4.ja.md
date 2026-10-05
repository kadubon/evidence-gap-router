# ローカルOllama実験 — v0.2.4

最終較正と別資料の24試行pilotが完了し、固定した16親課題の主確認を実行中です。
暖機確認からroutingの優劣は判断しません。

現行のQwenとGemmaで、長い入力と条件Qの変更を含むreader・integrator・reviewer
各2回が完了し、すべて使用量が確定しました。先行開発ではQwenが誤ったunknownを
返し、reviewerも受理した例があります。形式の完了と内容の正しさを分けます。
先行する開発試行の出力と費用も同じ台帳に保持しています。

`egr-024-local-ollama-v1` の較正とpilot後に主確認をfreezeします。
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

主確認前に実template/tokenizer、実装byte、資料、gold、全key・順序・seed・予算・解析を固定します。
親課題数24または16は速度・資源と64件の停止感度枠で決めます。有意差まで延長しません。
全native CI、公開後download検証、custom live例はこのsnapshotでは未実施です。
旧v0.2.3のQwen消費不明は旧台帳にそのまま残しています。

## 完了したpilotと主確認freeze

| モデル | 方式 | 終了/4 | 答案正答/4 | review独立の根拠付き/4 | 最終完了/4 | 有料call |
|---|---|---:|---:|---:|---:|---:|
| Qwen | A | 4 | 1 | 0 | 0 | 12 |
| Qwen | B | 4 | 3 | 2 | 1 | 19 |
| Qwen | C | 4 | 4 | 4 | 4 | 8 |
| Gemma | A | 4 | 2 | 2 | 0 | 29 |
| Gemma | B | 4 | 4 | 4 | 0 | 19 |
| Gemma | C | 4 | 4 | 3 | 0 | 8 |

95 callすべて使用量が確定し、生成12,621／総69,525 tokenです。Qwen Bの形式faultと
有料修復も残しています。Qwen Cの測定経路は成立しましたが、Gemmaは最終受入が0で、
routing比較には床効果が残ります。基準を下げず、診断的な結果として本試験でも分離します。
この開発4親課題を主確認の分母には入れません。

生成しない実template/tokenizer検査765件（全公開基本入力と既払い入力）で、最大出力枠を
足した最大値はQwen 3,506／Gemma 3,630、context 8,192以内でした。空preload2回は
台帳に計上しています。任意の最大長schema文字列すべてが収まるという主張ではありません。

16親課題（解答可能12・情報不足4、各family4）の96 trialと、新規64 trialの停止感度を固定。
24親課題案は各trial最大10call、最大cap 2,048で将来生成予約4,259,840 tokenとなり、
開発分を足す前から上限400万を超えます。16案は3,276,800で、freeze時残量3,920,551に
収まります。A−B成績は選択に使っていません。事前の各family親4/5は除外され、XOR、
waiver、明示例外、目的地等のその変形は今回live主確認していません。family構造は開発と
共有する人工資料であり、未知の推論familyへの汎化実験ではありません。

実測時間からの予測は計画用で、全requestの最大待ちを保証しません。各モデル80 trialの
最大trial時計だけでも合計240時間となり、48時間を超えます。各dispatchで元のwall・call・
token残量を検査し、尽きた場合は予算を延長せず、未着手keyを未実施として保持します。

[実行手順](ollama-guide.md) · [監査](audit-024.md) ·
[v0.2.3の保存済み報告](ollama-experiment.ja.md)
