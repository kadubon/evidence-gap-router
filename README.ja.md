# evidence-gap-router

**Route work by missing evidence, not by agent count.**

未取得の根拠や未実施の検証を見て、次に行う処理を選ぶ小さなPython SDKです。
実行できる処理と権限、費用の上限は利用者が有限の候補として登録します。

Python **3.12以上** · Apache-2.0 · [English](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/README.md) · [文書一覧](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/index.md)

## 向く用途

取得済みの資料、検証結果、依存関係、費用、規則の変更によって次の処理が変わる
仕事に向きます。根拠、検証の発行履歴、失敗、費用、未解決事項を保存し、明示的に
処理を再開できます。入力と手順が決まっている仕事には固定の処理順で十分です。

検証履歴の管理は内容の意味的な正しさを保証しません。同じモデルを別に呼ぶだけで
判断の統計的独立性が成立するわけではありません。

## インストールと動作確認

```sh
python -m pip install evidence-gap-router==0.3.0
egr --version
egr demo --json
```

インストール後のこの確認にはモデルや通信が不要です。demoは人工データを使います。
[使い始める手順](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/getting-started.md)には、実際のUTF-8 CSV/JSONを生成し、
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
    CompletionContract,
    DependencyRequirement,
    declare_completion,
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
obligation = state.obligations[0]
state = declare_completion(
    state,
    CompletionContract(
        id="fixed-arithmetic-1",
        obligation_id=obligation.id,
        scope=obligation.scope,
        obligation_fingerprint=obligation.contract_fingerprint,
        target=DependencyRequirement(
            evidence_id="answer", obligation_id=obligation.id, scope=obligation.scope
        ),
        declared_scope="not_applicable",
        scope_reason="Fixed supplied arithmetic; no retrieval.",
    ),
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
    resources=Resources(actions=1, verifications=1, tokens=0),
)
policy = Policy(
    trusted_verifiers=("arithmetic-check",),
    handlers=(
        HandlerRegistration(
            handler_id="check",
            roles=("verify",),
            checkers=(
                CheckerPermission(
                    checker_id="arithmetic-check",
                    completion_kinds=("content",),
                    completion_scopes=("example",),
                ),
            ),
        ),
    ),
)


def check(view: CallbackView):
    passed = int(view.inputs[0].content or "") == 2 + 2
    return view.result(
        actual_resources=Resources(actions=1, verifications=1, tokens=0),
        checks=(view.check(status="PASS" if passed else "FAIL", reason="Compared with 2 + 2"),),
    )


budget = Budget(limits=Resources(actions=1, verifications=1, tokens=0))
next_step = plan(state, (action,), budget, policy)
assert next_step.action is not None
assert any(r.code == "completion_check_missing" for r in next_step.completion[0].residuals)
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
callback前には `completion_check_missing` が未充足条件を示します。
利用者が検証者の権限を登録し、`view.check` が発行済みの対象・契約・入力を結びます。
出力に検証者IDを書くだけでは権限が生まれません。

`step` は最大1処理、`run` は有限回の処理を実行します。実行側の停止と、未解決の
要求は別に確認します。未確定の試行や予算対象の消費不明は自動継続を止めます。
[概念](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/design.md)、[API](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/api.md)、[保存・移行](https://github.com/kadubon/evidence-gap-router/blob/v0.3.0/docs/migration.md)に、
取得、失効、再検証、選択規則、費用を保持した再開をまとめています。
入力を限定したcallbackはPythonのsandboxではありません。入力の信頼性、外部効果、
実費用、単一writerの管理は利用者が担います。

## 完了契約と実ファイルの例

個別のPASS、現在の適用性、有限な目標の完了は別の状態です。利用者が必須資料、
範囲・カタログの版、完了に使えるチェック種別を明示します。未指定・空の調査範囲は
未完了です。固定計算は理由付きの `not_applicable` を使えます。検証権限の既定値は
advisoryであり、後の権限追加によって古い観測が完了権限へ昇格することはありません。

```sh
python -m evidence_gap_router.completion_example partial
python -m evidence_gap_router.completion_example pooled
python -m evidence_gap_router.completion_example continuation
```

実際のUTF-8整数ファイルを使い、発行済みreceiptと費用を記録します。MのみのPASSは
Nの不足を解消せず、N取得後も古いbasisは変わりません。全文入力を使う適格な検証は
完了できます。pooledは固定callback一つで完了します。continuationは使用済みNを
失効、保存・再読込し、Mを再取得せず必要なN取得と検証だけを行います。元のPASSと
費用は残ります。空白・日本語のディレクトリを指定でき、既存ファイルは上書きしません。
[完了契約](docs/completion.md)にAPIをまとめています。

schemaは3です。[schema 1/2の明示移行](docs/migration.md)は元の履歴・basisを保持し、
不足している完了権限や契約を捏造しません。`Decision.completion` に不足条件を返し、
宣言範囲外の完全性はunknownと表示します。観測coverageは診断値です。

## 既知の負の結果と今回の限界

v0.2.4の固定実験ではAがBを下回りました。解答可能12件の完了はQwen A/B/Cが
**0/8/12**、Gemmaが**3/8/10**、Qwen Aの誤受入は**15/16**でした。
[元の報告](https://github.com/kadubon/evidence-gap-router/blob/v0.2.4/docs/ollama-experiment-v0.2.4.ja.md)を保持します。

**v0.3.0の新規LLM推論0、新規効用・性能実験0、経験的効用は未評価です。**
契約と制御構造を一般化する実装で、学習や重み調整は行いません。歴史的実験は元の
tag・wheel・harnessに束縛されます。現行実験CLIはSDKの版が違えば通信やサーバー操作の
前に拒否します。[保存版Ollama手順](docs/ollama-guide.md)を参照してください。
