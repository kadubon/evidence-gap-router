# ローカルOllama実験 — v0.2.4

新campaignは開発較正中です。主確認のA/B/C比較と停止規則の測定は未着手です。
暖機確認からroutingの優劣は判断しません。

現行のQwenとGemmaで、長い入力と条件Qの変更を含むreader・integrator・reviewer
各2回が完了し、すべて使用量が確定しました。Qwenは初回統合で誤ったunknownを
返し、reviewerもその答案を受理しています。形式の完了と内容の正しさを分けます。
先行する開発試行の出力と費用も同じ台帳に保持しています。

`egr-024-local-ollama-v1` の較正とpilot後に主確認をfreezeします。
このページには実行済みの分母、方式間差、未確定・未実施、公開後検証を記録します。
未実施の測定や未公開の配布物を完了扱いにはしません。

[実行手順](ollama-guide.md) · [監査](audit-024.md) ·
[v0.2.3の保存済み報告](ollama-experiment.ja.md)
