# evidence-gap-router

**Route work by missing evidence, not by agent count.**

未取得の根拠や未実施の検証を見て、次に行う処理を選ぶ小さなPython SDKです。
実行できる処理と権限、費用の上限は利用者が有限の候補として登録します。

Python **3.12以上** · Apache-2.0 · [English](README.md) · [文書一覧](docs/index.md)

## 向く用途

取得済みの資料、検証結果、依存関係、費用、規則の変更によって次の処理が変わる
仕事に向きます。根拠、検証の発行履歴、失敗、費用、未解決事項を保存し、明示的に
処理を再開できます。入力と手順が決まっている仕事には固定の処理順で十分です。

検証履歴の管理は内容の意味的な正しさを保証しません。同じモデルを別に呼ぶだけで
判断の統計的独立性が成立するわけではありません。

## インストールと動作確認

```sh
python -m pip install evidence-gap-router==0.2.4
egr --version
egr demo --json
```

インストール後のこの確認にはモデルや通信が不要です。demoは人工データを使います。
[使い始める手順](docs/getting-started.md)には、実際のUTF-8 CSV/JSONを生成し、
空白・日本語を含むパスを引用して `egr check-data` へ渡す完全な例があります。

## 自分の処理を接続する

配布wheelだけで動く例です。入力内容を読み、次の検証を選び、実際の結果と
残った阻害事項を表示します。

```python
from hashlib import sha256
from evidence_gap_router import (
    ActionCandidate,
    Budget,
    CallbackView,
    CheckerPermission,
    Evidence,
    HandlerRegistration,
    Obligation,
    Policy,
    Resources,
    State,
    plan,
    run,
)

content = "4"
evidence = Evidence(
    id="answer",
    obligation_id="sum",
    scope="example",
    digest=sha256(content.encode()).hexdigest(),
    content=content,
    producer="calculator",
    source="local-calculation",
    provenance_group="calculator",
)
state = State(
    obligations=(
        Obligation(
            id="sum",
            description="Check arithmetic",
            scope="example",
            acceptance="Parsed answer equals 2 + 2",
        ),
    ),
    evidence=(evidence,),
)
action = ActionCandidate(
    id="check-answer",
    obligation_id="sum",
    scope="example",
    kind="verify",
    handler_id="check",
    target_evidence_id="answer",
    target_digest=evidence.digest,
    checker_id="arithmetic-check",
    resources=Resources(actions=1, verifications=1),
)
policy = Policy(
    trusted_verifiers=("arithmetic-check",),
    handlers=(
        HandlerRegistration(
            handler_id="check",
            roles=("verify",),
            checkers=(CheckerPermission(checker_id="arithmetic-check"),),
        ),
    ),
)


def check(view: CallbackView):
    passed = int(view.inputs[0].content or "") == 2 + 2
    return view.result(
        actual_resources=Resources(actions=1, verifications=1),
        checks=(view.check(status="PASS" if passed else "FAIL", reason="Compared with 2 + 2"),),
    )


budget = Budget(limits=Resources(actions=1, verifications=1))
next_step = plan(state, (action,), budget, policy)
assert next_step.action is not None
print(next_step.action.id)  # check-answer

report = run(
    state,
    (action,),
    budget,
    policy,
    {"check": check},
    max_steps=8,
)
print(report.state.checks[-1].status)  # PASS
print(report.decision.stop_reason)  # satisfied
print([r.code for r in report.decision.residuals if r.blocking])  # []
```

出力は `check-answer`、`PASS`、`satisfied`、`[]` です。
利用者が検証者の権限を登録し、`view.check` が発行済みの対象・契約・入力を結びます。
出力に検証者IDを書くだけでは権限が生まれません。

`step` は最大1処理、`run` は有限回の処理を実行します。実行側の停止と、未解決の
要求は別に確認します。未確定の試行や予算対象の消費不明は自動継続を止めます。
[概念](docs/design.md)、[API](docs/api.md)、[保存・移行](docs/migration.md)に、
取得、失効、再検証、選択規則、費用を保持した再開をまとめています。
入力を限定したcallbackはPythonのsandboxではありません。入力の信頼性、外部効果、
実費用、単一writerの管理は利用者が担います。

## ローカルOllama実験

[Ollama手順](docs/ollama-guide.md)は、通常インストールしたSDKとsource側の実験例を
組み合わせ、明示的にローカル推論を行います。coreのimportやoffline CLIにOllamaは
不要です。モデル重みと認証情報は同梱せず、通常のtestsと公開CIで推論しません。

初回v0.2.4確認で省略可能な項目の証拠保存に不整合が見つかりました。
原結果と費用を残し、新protocol・未使用資料・元の累積上限で再確認します。
意味的な受入基準は変えていません。[現在の技術報告](docs/ollama-experiment-v0.2.4.md)、
[日本語要約](docs/ollama-experiment-v0.2.4.ja.md)、
[v0.2.3の保存済み報告](docs/ollama-experiment.md)を分けて参照できます。

AはEGRの選択順、Bは共通runner・候補・権限・callback・予算で検証を優先する選択順、
Cは全文資料を先に渡す参照方式です。共通の実行可能性判定の中で選択順の追加価値を
測ります。別frameworkの比較やモデルの順位付けではありません。

[監査](docs/audit-024.md) · [検証](docs/validation.md) ·
[公開手順](docs/releasing.md) · [責任境界](SECURITY.md)
