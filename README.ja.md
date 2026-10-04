# evidence-gap-router

**Route work by missing evidence, not by agent count.**

不足している証拠に応じて、次に調査・検証・別の情報源の確認を行う小さな
Python SDK とオフライン CLI です。既存のスクリプトやエージェントアプリから、
確認事項と有限の候補を宣言し、自分の Python callback を接続できます。
解決できない条件とその理由を残したまま停止します。

Python **3.12 以上** · Apache-2.0 · [English](README.md)

## インストールと動作確認

```sh
python -m pip install evidence-gap-router
egr --version
egr demo --json
egr demo --case invalid --json
egr demo --case budget --json
```

同梱デモは**人工的な** CSV とデータ辞書 JSON を、別々の取得 callback で
実際に読みます。別の検証 callback が必須列、主キー重複、金額下限、通貨を
実際の値から確認します。不足している情報によって次の処理が変わり、資料が
揃ってから検証します。`valid` は条件達成、`invalid` は計算した FAIL を保持、
`budget` は検証前の予算不足で停止します。検査を実行したことと、データが
合格したことを区別します。実行時にソース checkout、API key、モデル、
ネットワークは不要です。

[ローカルファイルの利用例](examples/data_quality.py)で手元の CSV/JSON を
指定できます。[callback の実行可能な最短例](examples/callback.py)と
[英語 README の完全なコード](README.md#connect-a-python-callback)は、
明示した関数 mapping を使い、入力した値と実際の `2 + 2` を比較します。
ホストループは例外・不正な返却値も、不明な実行結果・実コスト・副作用を
持つ attempt として記録し、呼出回数を無料扱いにせず自動再試行しません。

## SDK と callback

```python
from evidence_gap_router.demo import run_demo

report = run_demo("valid")
print(report["decision"]["stop_reason"])  # satisfied
print(report["callback_calls"])  # 実際に呼んだ登録済み関数
```

自分の処理には `run_host_loop(state, candidates, budget, policy, handlers)` を
使えます。`handlers` は `handler_id` と Python 関数の明示的な mapping です。
各関数は `(action, attempt_id, state)` を受け取り、対象・検証結果・実コストを
持つ `Result` を返します。上記の完全な callback 例の関数を自分の検証器へ
置き換え、`Policy` に handler と信頼する verifier を登録してください。

core の公開操作は `plan(state, candidates, budget, policy)`、
`start(state, action, attempt_id, budget, policy)`、`observe(state, result)`。
`plan` は読み取り専用で、実行も予算消費もしません。ホストは `start` で
attempt を発行してから callback を呼び、`observe` で結果を取り込みます。
文字列から関数を import せず、推薦だけで実行権限を与えません。

## JSON 入出力と CLI

[英語 README の JSON 全文](README.md#offline-json-planning)を `INPUT.json` に
保存すると、次のコマンドが候補 `read-orders` と不足情報を推薦します。

```sh
egr plan INPUT.json --json
```

入力の最上位は `schema_version: "1"`, `state`, `candidates`, `budget`, `policy`。
状態・decision にも schema version があります。SDK では `dump_json(model)`、
`load_json(text, Model)`、`read_json(path, Model)` を使えます。

```python
import json
from evidence_gap_router import State, dump_json, load_json
from evidence_gap_router.demo import run_demo

state = load_json(json.dumps(run_demo()["state"]), State)
assert load_json(dump_json(state), State) == state
```

CLI 入力上限は 1 MiB。不明な schema version、未知 field、重複 JSON key、
不正な参照・値・型・非有限数を拒否し、無言の型変換はしません。
`plan` はオフラインで読み取り専用です。証拠に URL/path があっても取得・実行
しません。JSON 入力の policy はローカル操作主体の設定です。非信頼の証拠を
受け入れるサービスは、証拠の外で保持したホスト policy を SDK に渡してください。

`--json` の domain 結果は stdout、入力・IO エラーは stderr に出ます。
exit **0** は推薦ありまたは条件達成、**2** は有効な入力に対する未解決停止
（JSON は stdout）、**1** は入力・IO エラー（JSON stdout なし）。
argparse の使用法エラーも exit 2 ですが、stderr に出ます。

## レコードと停止理由

| 型 | 意味 |
| --- | --- |
| Obligation | ホストが宣言した確認事項、scope、優先順位、受入条件。ルーターは条件を削除・緩和しません。 |
| Evidence | 内容または参照、digest、producer、宣言された由来。証拠自身の「検証済み」は trusted PASS になりません。 |
| CheckResult | 信頼する verifier による特定 digest/scope の PASS・FAIL・UNKNOWN。未実施は記録済み UNKNOWN と区別します。 |
| Residual | 現在不足している証拠・由来・検証・資源、未解決の矛盾や否定的結果と理由。 |
| Decision | 1 件の候補または停止理由、選択・除外理由、残課題、coverage、残り資源。 |

停止は `satisfied`, `budget_exhausted`, `blocked`, `escalation_required` を区別。
`satisfied` だけが現在の policy で宣言済み必須条件を満たした状態です。
現実の業務成功や一般的真理の認定ではありません。coverage は必須条件の
達成件数/全件数・scope・policy を示し、正答確率や知能スコアとは呼びません。
必須条件ゼロの状態は拒否します。

候補は実行可能性・前提条件・予算・検証容量を確認してから、必須、優先順位の
降順、不足への適合性、安定した ID 順で比較します。未検証の証拠があれば検証を
優先。同一内容・同一由来の重複は独立した支持を増やしません。由来不明は
不明のまま保持し、別 ID/model/provider を統計的独立性の証明にしません。
同じ情報源でつながる由来 group は推移的にまとめ、1 つの情報源の矛盾した
group 宣言は blocking residual として残します。

FAIL・UNKNOWN・blocking contradiction は、後の PASS だけで消えません。
対象と理由を持つ明示的 supersession または検証付き解決で現在の適用状態を
更新し、履歴を保持します。失効・withdrawal・古い digest・scope 不一致は
現在の合格根拠になりません。失効はホストが明示し、暗黙の時計は使いません。
既定 policy は自己検証を禁止し、明示した verifier ID だけを信頼します。

action 回数、検証回数、任意の token は別次元の非負整数です。見積と実績を
区別し、制約のある資源の不明量をゼロとみなしません。制約または申告上限が
ある次元の実績不明、副作用不明、上限超過があれば自動継続を停止。
検証待ち容量に達したら追加取得を抑制します。
同一 result の再入力は冪等、同じ ID の異なる内容はエラー。失敗・不明の後に
同じ候補を自動再実行しません。

## ホストの責任と実装範囲

実行、タイムアウト、アクセス権、認証、正確な費用計測、入力の信頼性、並行処理は
ホストの責任です。単一プロセス・単一 writer の状態と JSON snapshot を扱い、
scheduler、DB、crash recovery、exactly-once 外部実行は提供しません。
LLM gateway、framework 専用 adapter、GUI、telemetry、学習 routing、
自然言語の真偽・矛盾・独立性の自動認定も実装していません。

[研究 index](https://kadubon.github.io/github.io/collective-intelligence-index.html)
と CCR/VEK/CIO の契約は残課題・検証容量・権限分界の設計参考です。
依存・検証済み統合・schema 互換性は主張しません。新規性、集団知能向上、
成長、コスト削減、性能優位が実証済みとはしません。デモは人工例です。
詳しくは [design](docs/design.md) と [security](SECURITY.md) を参照してください。

## 開発と公開

```sh
uv sync --locked --group dev
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src
uv run --locked pytest
uv build --no-sources
uv run --locked python -c 'from pathlib import Path; Path("dist/.gitignore").unlink(missing_ok=True)'
uv run --locked twine check dist/*
uv run --locked python scripts/package_audit.py dist
```

uv 管理 Python とプロジェクト内 `.venv` を使います。uv.lock は開発と CI を
固定しますが、pip 利用者全員の依存環境を固定するものではありません。
日常の修正は影響範囲をローカルで確認し、完成した変更をまとめて手動 CI へ
送ります。workflow は 1 ファイル、手動実行と `v*` tag push だけです。
Linux/Python 3.12 の品質・build・clean install と、同じ artifact の
Windows/Python 3.12 smoke を実施する構成です。公開には同じ commit の
手動 CI 成功と Trusted Publisher/environment の確認が必要です。
設定、公開状態の区別、再開手順は [releasing](docs/releasing.md) にあります。
