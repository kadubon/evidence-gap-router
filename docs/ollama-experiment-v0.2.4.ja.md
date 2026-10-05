# ローカルOllama実験 — v0.2.4

最終較正が完了し、別資料の24試行pilotを実行中です。主確認と停止規則は未着手です。
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

主確認前に実template/tokenizer、実装byte、資料、gold、全key・順序・seed・予算・解析を固定します。
親課題数24または16は速度・資源と64件の停止感度枠で決めます。有意差まで延長しません。
現在の全native CI、公開後download検証、custom live例は未実施です。
旧v0.2.3のQwen消費不明は旧台帳にそのまま残しています。

[実行手順](ollama-guide.md) · [監査](audit-024.md) ·
[v0.2.3の保存済み報告](ollama-experiment.ja.md)
