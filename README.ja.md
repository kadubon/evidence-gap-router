# evidence-gap-router

**Route work by missing evidence, not by agent count.**

不足する証拠に応じて、次の調査・検証を選ぶ小さな Python SDK です。
確認事項と有限の候補を宣言し、自分の callback を接続できます。
検証した対象・受入契約・実際に使った資料を結び付けるため、辞書の更新後は
その辞書に依存する検証だけが不適用になり、必要な再検証へ進みます。

Python **3.12 以上** · Apache-2.0 · [English](README.md)

## インストールと手元のファイル

```sh
python -m pip install evidence-gap-router==0.2.0
egr --version
egr check-data --data ./orders.csv --dictionary ./rules.json --json
egr demo --json
egr demo --case invalid --json
egr demo --case budget --json
egr demo --example cause --case resolved --json
```

`check-data` は指定した CSV と JSON を実際に読み、入力を上書きしません。
辞書の要求を先に検証し、その正確な辞書を依存資料としてデータの要求を検証します。
別の取得 callback と検証 callback が、発行時に固定した入力 view を使います。
人工デモは `artificial_data: true`、手元のファイルは false とローカル scope です。

CSV は `order_id,amount,currency` の 3 列（順序任意）、1 行以上、空でない一意の
ID、有限で下限以上の金額、許可された通貨が必要です。辞書の固定形式は次です。

```json
{
  "required_columns": ["order_id", "amount", "currency"],
  "primary_key": "order_id",
  "minimum_amount": 0,
  "allowed_currencies": ["USD", "JPY"]
}
```

重複列名・空列名・余分/不足 field、JSON 重複 key、未知辞書 field、不正な型、
非有限数、不正 UTF-8 を拒否します。各ファイルは 1 MiB、CSV は 10,000 行まで。
上限を超えた入力の一部だけを全体合格にしません。UTF-8 BOM と LF/CRLF を受け付け、
内容 digest は BOM・改行を含む元 byte を SHA-256 にかけます。
空白・日本語 path は pathlib で扱い、path から shell コマンドを組み立てません。
[ローカルファイル例](examples/data_quality.py)と
[完全な callback コード](README.md#connect-a-callback)を参照してください。

## callback と有限 runner

```python
from evidence_gap_router.sdk_example import run_callback_example

report = run_callback_example()
print(report.decision.stop_reason)  # satisfied
print(report.callback_calls)
```

この同梱例は固定の成功を返さず、Python の実際の計算で入力を確認します。
自分の関数は `callback(view: CallbackView) -> Result` として明示 mapping に登録します。
検証は `view.check(status=..., reason=...)` で発行時の basis に結び付け、
`view.result(actual_resources=..., checks=(check,))` で実績とともに返します。
ホスト登録は handler の役割、checker ID/revision、purpose を許可します。
結果本文へ ID を書くことは権限取得ではありません。

`step` は最大 1 呼出し、`run(..., max_steps=32)` は既定で有限です。
返る State・Decision・receipt を保存し、同じ公開 API から明示的に継続できます。
既存の全履歴を見て attempt ID を発行し、不明な in-flight attempt は再発行しません。
factory/callback の例外、不正 receipt、無進捗、上限到達でも状態を保持します。
runner の `max_steps_reached` 等と業務上の `satisfied` を混同しません。
実行した失敗は呼出回数・不明な費用・副作用を保持し、自動 retry しません。

初期取得 view には他の取得者の回答を含めず、検証時に対象と明示依存資料だけを
開示します。これはアプリの情報露出規則であり、同一プロセス内の sandbox、
暗号学的秘匿、統計的独立性ではありません。ホストの factory は計画のため
全 State を読めます。

core の `plan` は読み取り専用で予算を消費しません。`start` が basis と登録権限を
固定し、`observe(state, receipt, policy)` が発行との対応と現在の policy を照合します。
推薦は実行許可ではなく、認証・権限・外部効果・タイムアウト・費用計測はホストの責任です。

## gap と JSON

[英語 README の JSON 全文](README.md#inspect-gaps-without-execution)を `INPUT.json`
に保存すると、`egr plan INPUT.json --json` が不足に応じた候補を推薦します。
URL/path の参照を自動取得せず、handler の文字列を import しません。
新しい入出力の schema version は **"2"**。未知 field/version、重複 key、不正型を
拒否し、CLI JSON は 1 MiB まで。`dump_json`/`load_json`/`read_json` で round-trip できます。
schema 1 は黙って受理せず、[明示的な移行](docs/migration.md)を使います。

Decision の `gaps`・`selected_gap`・`pending_verifications` は、どの対象・条件・
依存資料・checker が不足しているかを示します。満たされた対象を既定で再検証せず、
部分的な必須 verifier の PASS は残る検証待ちを消しません。宣言された不足前提の
取得は既存 backlog を解消できますが、単に investigate と名付けて容量制限を
迂回しません。既知の同じ由来・由来不明・宣言上の不足を補える由来を区別し、
実質条件が同じ場合だけ安定した ID 順で選びます。

Check は evidence ID/digest/scope、契約 fingerprint、有限の使用資料、checker
ID/revision、purpose に結び付きます。契約には ID/scope/revision/acceptance、必要
証拠数・由来数・必須 verifier を含め、表示 description・priority・required は含めません。
無関係な追加では再利用でき、依存の変更・失効・withdrawal・supersession では
関係する check だけを不適用にします。fingerprint は意味や真偽の自動認定ではありません。

通常の内容検証、FAIL/UNKNOWN 解消、矛盾解消は別 purpose です。取得結果だけで
否定的記録を消せず、一般的な内容 PASS で矛盾を閉じません。適合する対象・契約・
根拠・purpose とホスト許可が必要です。原記録は保持し、同一 receipt の再入力は冪等、
ID 衝突はエラーにします。

業務上の停止は `satisfied`、`budget_exhausted`、`blocked`、`escalation_required`。
満足は宣言済み条件と現在 policy に相対的で、業務成功・一般的真理の認定ではありません。
coverage は分子/分母・scope・policy を示し、正答確率や知能スコアではありません。
必須要求ゼロは拒否。action・検証・token は別の整数次元で、制約/申告上限のある
実績不明や外部効果不明は自動継続を止めます。

`--json` は機械可読結果を stdout に出します。不正な plan 入力は stdout を出さず
stderr へエラーを出します。ファイル入力/callback 失敗は状態・費用を含む JSON を
stdout に保持し、stderr にも理由を出します。
exit 0 は推薦または満足、2 は有効な入力に対する未解決/検査済み不合格、1 は入力/実行失敗。
argparse の使用法エラーも stderr/exit 2 です。`outcome` と業務/runner の停止を見て、
入力不正、実行失敗、検証済み FAIL、資料不足、予算不足を区別してください。

## 監査・比較・検証範囲

v0.1 の A01〜A12 を再現し、[監査対応表](docs/audit.md)へ修正・回帰・制限を対応付けます。
旧 PASS に欠けた根拠は推測して補わず、旧 FAIL/UNKNOWN/矛盾/pending/history を保持します。
破壊的な schema/API 更新を完全後方互換とは説明しません。

`egr demo --example cause` は CSV の名称変更ではなく、記録・仕様・例外資料を
別 view で調べる照合例です。`resolved` のほか `invalid`、`conflict`、`unknown`、
`provenance`、`budget` を扱い、実際の資料とコードから判定します。
[小さな比較の生結果と解釈](docs/comparison.md)は、同じ資料・callback・checker・予算で
固定順と gap routing を比較し、同等だったケースも残します。
一般的な AI 改善、コスト削減、知能成長、集合知効果の実証ではありません。

[実行済みと未確認を分けた検証記録](docs/validation.md)を参照してください。
CI は Linux/Python 3.12 で 1 回だけ build し、同じ wheel を Windows x64、
macos-15 arm64、macos-15-intel x86_64 に install。Linux 3.13/3.14 も検証します。
各 profile が実 machine、Python、import 先、Pydantic/core wheel tag、wheel hash を記録します。
将来の Python version まで検証済みとはしません。

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

lock は開発/CI を固定し、全 pip 利用者の環境を固定しません。影響範囲をローカルで
確認し、完成した変更をまとめて手動 CI へ送ります。workflow は 1 つ、手動と v* tag
push のみ。全 native gate と同一 commit の手動成功なしには公開しません。
[design](docs/design.md)、[security](SECURITY.md)、[公開手順](docs/releasing.md)に責任分界を記します。
