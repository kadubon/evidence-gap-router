# v0.2.1 ベンチマーク訂正：停止の意味

報告された strict abstention の **80/95 対70/95** は、routing による安全な
停止能力の改善を示しません。旧 EGR arm は公開 runner、他方式は別の loop を
使いました。F7 の10親 task では最終記録の意味が同じでも runner の停止ラベルが
異なり、旧集計は EGR 側の `router_stopped` を条件にしていました。

これは公開済み生データの再分類です。再実行、元のラベルの書換え、旧 timing の
差替えは行いません。[元の日本語報告](benchmark-v0.2.1.ja.md)、
[英語報告](benchmark-v0.2.1.md)、protocol、freeze、raw archive を保持します。
v0.2.2 の共通 runner による新測定とは別の結果です。

## 証拠と再構成

正規の [v0.2.1 Release](https://github.com/kadubon/evidence-gap-router/releases/tag/v0.2.1)
から、新しい専用ディレクトリへ `benchmark-raw-v0.2.1.zip` を取得しました。
実際の SHA256 は
`9212ee2499df0b16b47b23ac3150f71b83b1db69abc85a7123a02044f4fa69a0`。
元 ZIP を読取り専用で保持し、展開時にパス逸脱・重複 entry・symlink を検査しました。
manifest の29資料すべての hash とサイズが一致しました。

標準ライブラリだけの [再集計コード](../benchmarks/erratum_021.py) は新版4,680行と
旧版720行を読み、元集計や SDK を import せず callback を実行しません。
primary の全体・family・budget 別分子分母を、公開値どおりに再構成してから分類します。
primary は元順序・random seed 17です。反復を独立した親 task にはしません。
[新出力](../benchmarks/results/v0.2.1-erratum/summary.json) は旧件数、新分類と
trace 比較を併記します。

F7 mode 4/5 の10親 task ×4方式では、invocation/receipt ID だけを正規化すると、
State・action・receipt・decision・oracle・費用が一致しました。資料 ID、権限、scope、
資源値、payload は変えていません。mode 4 は callback 1回、検証消費と作用が不明で
`escalation_required`。mode 5 は callback 1回、検証0、作用既知で `blocked`。
EGR は `router_stopped`、他方式は `no_progress` という runner ラベルでした。

## 別の診断再実行

新版の正式凍結前に、同じ観測済み10親 task を通常インストールした公式0.2.1 wheel と
当時の正確な LF harness で再実行しました。元順序・seed 17、4方式で40試行が完了しました。
wheel SHA256 `61129ec1…202917`、wheel RECORD の29 hash、installed package fingerprint
`5df6a0b5…e8341a` が一致しました。harness
`d3db76040403efbf802437c8a62514466c01ab0efdfec390823989224aeae4de`、protocol
`4bfb84ce958aab46890525ee9225832c950e03bbbdfd7266b320c595f65ca06a`
も元 freeze と一致。Python 3.12.14、Pydantic 2.13.5/core 2.46.5 とすべての runtime
依存 version は旧正式測定環境と同じです。

10親 task の正規化した意味上の signature は各4方式で一致しました。全試行 callback 1回、
oracle 未完了、誤完了なし、snapshot roundtrip 成功です。旧指標は EGR 10、他方式0ですが、
修正した分類では各方式とも既知5、不確実5です。診断 raw の新 SHA256 は
`3d13813e997d95b556001692bb2dc9b6d98b52fbf1c4c06e62973b0c37fdb9bd`。
`reproduce_f7.py`、JSONL、provenance summary は別の外部ディレクトリで保持し、
新版公開の証拠 bundle に含めます。観測済み回帰データの診断再実行であり、5,400行全部の
独立再実行、未見確認、性能の再推定ではありません。元 archive は変更していません。

## 訂正した primary 分類

既知の正当な停止には、明示的に非可解な task、oracle が判定した未完了、正常な
domain 停止、制約のある資源消費と作用の既知性、予算超過なし、未receiptの発行なしを
要求します。可解 task の未完了停止は誤停止です。worker/handler 障害は別分類です。
消費・作用・実行結果が不明、または発行が未完なら、停止していても不確実性を残します。
制約のない token 消費は測定済みの値にはしません。

| 版 / 方式 | 旧ラベル件数 | 既知の未完了 domain 停止 | 不確実性を残す停止 | 実行障害 | 非可解の分母 |
| --- | --- | --- | --- | --- | --- |
| 0.2.0 EGR | 64 | 59 | 5 | 15 | 88 |
| 0.2.1 EGR | 80 | 75 | 5 | 15 | 95 |
| 0.2.1 fixed-feasible | 70 | 75 | 5 | 15 | 95 |
| 0.2.1 verify-first | 70 | 75 | 5 | 15 | 95 |
| 0.2.1 random-feasible、seed 17 | 70 | 75 | 5 | 15 | 95 |

旧版の残る非可解9件は誤完了でした。新版の主4方式では、この oracle 内の誤完了は0件。
4方式とも意味上の未完了停止は80件ですが、既知75件と不確実5件を分けます。
不明な5件を既知の安全な成功や費用0へ昇格させません。旧親出力の
`correct_abstention` は可解な32方式・親群にも true でした。元の意味を保持し、
新しい分類では task の可解性を明示的に条件にします。

完了と誤完了の件数は変わりません。互換な可解132親 task では旧新版 EGR の
primary 完了は99/132→132/132、誤完了は9/220→0/220です。新版全体では
EGR145/145、fixed142/145、verify-first143/145、random145/145のままです。
旧 API 非対応、失敗した試行、不明な費用も削除しません。

## 再実行手順と境界

元 ZIP を取得・安全に展開したあと、source から次を実行します。

```sh
python -m benchmarks.erratum_021 ORIGINAL_DIRECTORY --archive benchmark-raw-v0.2.1.zip --output NEW_ERRATUM.json
```

出力先は未存在である必要があります。元資料の byte 変更、異なる ZIP、primary 再構成の
不一致はエラーです。ラベル同値性、実際の未receipt、未知費用・作用、可解 task の除外、
資料 ID を保持する trace 比較など19回帰テストが通りました。

記録済み oracle と可解性を使った再集計であり、全 task の独立再実行や新しい外部妥当性の
証拠ではありません。旧 CPU/time は異なる loop、tracemalloc、cold import、共通 setup を
含むため純粋な順位付け費用差として使いません。baseline は EGR の feasibility・必要性・
helper 判定を共有し、共通機構を条件とする選択の追加価値を比較します。独立 scheduler
に対する全 stack の優位は示しません。観測0件はリスク0の証明ではなく、人工 family は
実業務からの無作為標本ではありません。
