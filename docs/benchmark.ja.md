# v0.2.1 エンジニアリング評価

この評価は三つの問いを分ける。Q1 は受入判定と明示的な継続処理が独立した
契約 oracle に一致するか、Q2 は同じ実行可能な action・資源制限の下で選択方法に
差があるか、Q3 は制御処理の CPU・メモリ・依存評価量がどう変わるかを調べる。
正しさの修正だけでは選択方法の優位性は示せず、callback 数の減少だけでは CPU
時間の減少も示せない。[英語版](benchmark.md) は同じプロトコルを記述している。

固定した実験は Q1/Q2 の 5,400 行（新版 4,680・旧版 720）と Q3 の 360 測定 cell を
実行した。新版 EGR は solvable parent をすべて完了したが、強い baseline に対する選択上の
差は小さく、clustered 区間はゼロを含む。両 method が成功した subset では callback 減少と
traced trial CPU 増加が同時に観測された。Q3 は多くの完了 pair で依存評価時間が短く、
traced allocation は大きかった。これらは別の結果として扱う。その他の完了済み検査は
source の 260 テスト、インストール済み
candidate の Windows 検査（portable 223 テストと SDK/CLI 実行）、portable smoke
（11 parent・33 method trial・4 graph reference）である。残る 37 source-only テストは
repository/release tooling を検査する。
smoke の outcome digest は
`b151304eaca99ad064b6a6ad6b27cb4a08361f8257438ec910d57ad6d78b35c5`。
これは移植性・回帰検査であり、240 parent の holdout とは別の検査である。

## Q1/Q2 の観測結果

[aggregate summary](../benchmarks/results/summary.json) と
[scaling summary](../benchmarks/results/scaling-summary.json) に完全な分母・評価状態を保持し、
raw trace と CSV 表は後述の bundle に入っている。本報告の数値は表示用に丸めている。

original 順の 240 parent task のうち、宣言した material・権限・budget で solvable と
分類されたのは 145 件である。primary completion は original 順・random seed 17 の
件数である。旧版は未対応 API のため互換 parent が 220 件、うち solvable が 132 件となる。
次の件数は信頼区間ではない。cluster completion は各 solvable parent 内の variant/seed
平均を別に集計した値である。

| Version / method | Primary completion n/N | Cluster completion | False-satisfied parent n/N | Strict correct abstention n/N |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 99/132 | 76.263% | 9/220 | 64/88 |
| 0.2.1 EGR | 145/145 | 100% | 0/240 | 80/95 |
| 0.2.1 fixed-feasible | 142/145 | 98.621% | 0/240 | 70/95 |
| 0.2.1 verify-first | 143/145 | 99.080% | 0/240 | 70/95 |
| 0.2.1 random-feasible | 145/145 | 98.544% | 0/240 | 70/95 |

観測した完了件数の差は小さく、fixed 順との比較で 3 件、verify-first で 2 件、seed 付き
random selection との primary completion 差は 0 件である。別の順序・seed により random の
cluster 平均は下がり、3 parent で EGR より低い平均となる。一般的な routing 優位や cost
節約を示すものではない。新版 4,680 行には method variant・random 反復・ablation・
pipeline reference が含まれ、4,680 個の独立 parent task ではない。

新版 4,680 行はすべて worker status `completed` で、oracle 評価済みである。worker の完了は
task 成功と同義ではなく、guard した callback/factory/receipt fault を報告する場合がある。
旧版は completed 660 行と unsupported 60 行（invalidation API を必要とする F4 の
20 parent）である。両 version とも Q1/Q2 の worker timeout・unexecuted は 0 行。
互換な trial の oracle 未評価は 0 だが、unsupported 60 行は未評価として明示的に残す。

| Version / method | 互換な試行 trial | Unsupported trial | Exception を記録した trial | Verification cost 不明の trial |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 660 | 60 | 57 | 57 |
| 0.2.1 EGR | 720 | 0 | 45 | 45 |
| 0.2.1 fixed-feasible | 720 | 0 | 45 | 45 |
| 0.2.1 verify-first | 720 | 0 | 45 | 45 |
| 0.2.1 random-feasible | 2,160 | 0 | 135 | 135 |

新版の exception trial は意図的に故障を含む F7 recipe であり、失敗した互換試行として
保持する。新版全行では 270 trial が exception を記録した。
旧 EGR の 57 trial は F7 の故障45 trialと F4 の再解消エラー12 trialからなる。strict correct
abstention は error のない router stop を必要とするため、故障した F7 の 15 parent は安全に
失敗しただけで clean abstention として数えない。旧版の false satisfaction は F5 の
4 parent と F8 の 5 parent、variant 単位で 27 trial だった。新版はこの oracle 上で
EGR 0/240 parent、reference を含む全新版 0/4,680 trial である。

固定した parent record の `correct_abstention` field は、名前とは異なり error のない
router-stop indicator である。誤った旧版/baseline stop を含む solvable な method/parent
group 32 件でも true となる。この flag を正しい abstention と解釈するには
`solvable == false` が必要である。上の aggregate n/N は既にこの条件を適用しており、
表の件数は汚染されていない。測定後に field を黙って改名せず、元の記録と証拠を保持する。

**互換な version subset** は全 220 parent、うち solvable 132 parent であり、primary
completion は新版 132/132、旧版 99/132。parent 平均の差は 23.737 percentage point
（95% bootstrap 区間 16.667–31.061）、wins/ties/losses は 33/99/0 である。
false-satisfied parent は旧版 9/220、新版 0/220。残る要求 20 parent を旧版の成功・失敗に
置き換えず、unsupported として上表に示す。F5/F8 の solvable completion が同じでも、
旧版による unsolvable parent の誤受入は消えない。

### Family・budget 別件数

各 cell は primary completion n/N。各 family は 30 parent を要求するが、旧 F4 の互換
parent は 10 件だけである。`0/0` は solvable parent が存在しない層であり、完了率 0% の
観測ではない。

| Family | 0.2.0 EGR | 0.2.1 EGR | Fixed | Verify-first | Random |
| --- | --- | --- | --- | --- | --- |
| F1 | 18/18 | 18/18 | 16/18 | 16/18 | 18/18 |
| F2 | 0/24 | 24/24 | 24/24 | 24/24 | 24/24 |
| F3 | 19/24 | 24/24 | 24/24 | 24/24 | 24/24 |
| F4 | 5/9 | 22/22 | 21/22 | 22/22 | 22/22 |
| F5 | 16/16 | 16/16 | 16/16 | 16/16 | 16/16 |
| F6 | 21/21 | 21/21 | 21/21 | 21/21 | 21/21 |
| F7 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| F8 | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 |

| Budget | 要求 parent | 0.2.0 EGR | 0.2.1 EGR | Fixed | Verify-first | Random |
| --- | --- | --- | --- | --- | --- | --- |
| Adequate | 192 | 88/120 | 132/132 | 132/132 | 132/132 | 132/132 |
| Tight | 48 | 11/12 | 13/13 | 10/13 | 11/13 | 13/13 |

旧版の互換 budget 層は adequate 176・tight 44 parent、新版は 192・48 parent。
同一 version 内の primary 差は tight task に限られる。F1 は fixed/verify-first が未完了の
2 parent、F4 は fixed の残る 1 parent に対応する。新版 main method は F2/F3/F5/F6/F8 の
completion では同じ結果である。

### Paired な選択方法差と cost

差は variant/seed の parent 内平均を使った EGR minus baseline。区間の単位は
percentage point であり、primary 整数件数の比ではない。

| Baseline | Paired solvable N | Completion 差、pp | 95% parent-bootstrap 区間、pp | Wins/ties/losses |
| --- | --- | --- | --- | --- |
| Fixed | 145 | 1.379 | [0, 3.218] | 3/142/0 |
| Verify-first | 145 | 0.920 | [0, 2.299] | 2/143/0 |
| Random | 145 | 1.456 | [0, 3.295] | 3/142/0 |

全区間がゼロを含む。次の callback/check 平均は、別途記録した初期化を除く **継続部分**
を数える。一方 trial CPU/end-to-end は共通 setup・cold library import・初期化・observer・
snapshot 処理を含む。
cost は parent 内で variant 平均を求め、次に parent を平均する。verification 平均は不明な
観測を除き、known-cost N は旧版 201/220 parent、新版各 main method 225/240 parent。
上表の不明 trial をゼロとして計算していない。

| Version / method | Callback 平均（parent N） | Known verification 平均（parent N） | Trial CPU 平均、s | Trial end-to-end 平均、s |
| --- | --- | --- | --- | --- |
| 0.2.0 EGR | 1.7439 (220) | 0.9983 (201) | 0.4471 | 0.4795 |
| 0.2.1 EGR | 2.1375 (240) | 1.2578 (225) | 0.4868 | 0.5211 |
| Fixed | 2.3319 (240) | 1.2963 (225) | 0.4843 | 0.5160 |
| Verify-first | 2.2042 (240) | 1.2519 (225) | 0.4825 | 0.5149 |
| Random | 2.3079 (240) | 1.2810 (225) | 0.4828 | 0.5158 |

旧版の低い平均 work は低い completion と異なる互換分母を伴い、節約の証明ではない。
EGR は新版 baseline より callback が少ないが、known verification は verify-first より少し
多く、記述的 trial CPU は三つすべてより高かった。同一処理の純粋な plan version 比較は
Q3 で行い、この method 間 observer 時間と混同しない。

| Baseline | Both-success parent N | Callback 差 | Traced trial CPU 差、ms |
| --- | --- | --- | --- |
| Fixed | 142 | -0.2723 | +3.558 |
| Verify-first | 143 | -0.0932 | +5.390 |
| Random | 142 | -0.2504 | +4.988 |

これは両 method の全試行 variant が成功した selected subset である。失敗 pair を除く差で
あり、全 task の効率推定ではない。F3/F6/F8 の成功 subset では callback 差がゼロ。
F2 の EGR versus verify-first は call・completion が同じだが、記述的 trial CPU は EGR が
16.710 ms 高く、混在または不利な結果を示す。

### Ablation と direct pipeline

| Ablation | EGR / ablation primary completion | Paired N | Cluster 差、pp [95% 区間] | Both-success N; callback / CPU-ms 差 |
| --- | --- | --- | --- | --- |
| F1 without provenance rank | 18/18 / 16/18 | 18 | 7.407 [0, 18.519] | 16; -0.6667 / +3.255 |
| F2 without gap rank | 24/24 / 24/24 | 24 | 0 [0, 0] | 24; -0.3333 / +6.510 |

gap ablation はこの F2 task の completion を変えず、call を増やした。provenance ablation は
2 parent に影響したが、区間はゼロを含む。両 cost subset で EGR trial CPU は高いため、
機構を無条件の効率改善として報告しない。

| Reference family | Routed EGR oracle completion / 全 parent | Direct pipeline oracle completion / 全 parent | Routed / pipeline trial CPU 平均、s |
| --- | --- | --- | --- |
| F6 | 21/30 | 25/30 | 0.4760 / 0.4267 |
| F8 | 20/30 | 20/30 | 0.5075 / 0.4717 |

これは全 parent の件数であり、scheduler の solvable n/N ではない。F6 pipeline は SDK
callback budget を越える正常 material を batch で処理でき、その 4 件の追加完了を matched
scheduler の勝利として扱わない。F6 は 1/2/3 material read と 1 validation、F8 は 2 file read
と 1 validation を実行する。raw world と異なる batching/receipt 契約を明示する。
pipeline はこの観測では trial CPU が低い、より単純な reference だが、primary 推論から除く。

## 固定した入力と環境

実行可能な仕様は [protocol.json](../benchmarks/protocol.json) にある。
holdout の前に実装を commit し、両 wheel を別々の通常の非 editable 環境に
インストールした。SDK は source checkout ではなく各環境の `site-packages` から
読み込む。harness は Python・依存関係・platform・package bytes・protocol・harness
fingerprint が freeze 記録に一致することを検査する。

| 項目 | 記録値 |
| --- | --- |
| Protocol | `egr-021-engineering-v1` |
| 実装 commit | `305eec2cbf4f16c7d50dbb8bad002bc0cbc6d1c5` |
| 公開済み 0.2.0 runtime commit | `e8d77f210d7579d6a367b7564b485b2586ffd074` |
| 固定時刻 | `2026-10-05T04:38:11Z` |
| Protocol SHA-256 | `4bfb84ce958aab46890525ee9225832c950e03bbbdfd7266b320c595f65ca06a` |
| Harness SHA-256 | `d3db76040403efbf802437c8a62514466c01ab0efdfec390823989224aeae4de` |
| 測定した 0.2.1 wheel SHA-256 | `e8c2bead23b7c2cc622ff2a3215e262c23452f621d1298359dba520c027b01aa` |
| 公開済み 0.2.0 wheel SHA-256 | `039594d7fc5e39ab7b600c71f54682bb2d46147ba4e69a05a55f255a1806f3bf` |
| 測定した 0.2.1 package fingerprint | `5df6a0b5e7c521079e29475950addf6e1b84d62b3f3c70033307a82643e8341a` |
| OS / architecture | Windows 11、`10.0.26300`、AMD64 |
| CPU | AMD Ryzen 7 8840HS、8 core / 16 logical processor |
| 物理 RAM | 66,363,183,104 bytes |
| Python / Pydantic / pydantic-core | 3.12.14 / 2.13.5 / 2.46.5 |
| その他の runtime package | annotated-types 0.8.0、typing-extensions 4.16.0、typing-inspection 0.4.4 |

package fingerprint は package 相対 filename とその byte hash を整列した canonical
記録の hash であり、生成された `__pycache__` を除く。後の文書・metadata 変更と
測定済み runtime を区別するために使う。実際に測定した配布物の識別子は上記 wheel
hash のままである。[freeze 記録](../benchmarks/results/freeze.json) と
[artifact provenance](../benchmarks/results/artifact-provenance.json) は exact な識別子を保持し、
大きな raw trace は package と別に保存する。
この固定は repository 内の手続であり、外部機関への事前登録ではない。

旧 runtime は元の commit から公開した 0.2.0 配布物である。一方、task generator・oracle・
method/scaling harness は両 version とも固定した 0.2.1 実装 commit の file を使う。
holdout はその commit の LF Git archive から、宣言した installed wheel を使って実行する。
旧版の限定的 demo を旧 version 用 harness として置き換える比較ではない。raw record は
runtime version/wheel/package fingerprint と、共通 implementation/protocol/harness の
識別子を別々に記録する。

## Task・選択方法・oracle

holdout は各 family 30 件、合計 240 件の異なる生成 parent task を持つ。
development は seed 21041・各 family 8 件、holdout は seed 982451653 を使う。
original・reversed・renamed の candidate pool は同じ parent の variant であり、
random method の seed は 17・71・191 である。これらの反復を独立 task として
標本数に加算しない。

| Family | 検査する契約 |
| --- | --- |
| F1 | 宣言された origin の反復・差異、不明 provenance、不正な数値、tight/adequate budget |
| F2 | obligation 間の exact dependency、satisfied/optional helper、同一 content、1/2 段階の prerequisite |
| F3 | 複数 required checker、部分 PASS、自己検証禁止、利用不能 checker、pending capacity |
| F4 | 実 receipt による resolution 履歴、contract/material/check 変更後の再 resolution |
| F5 | FAIL/UNKNOWN 履歴、同一 byte の alias、正しい subject・別 subject の resolution、権限不足 |
| F6 | あらかじめ決まった 1/2/3 source pipeline、初期完了、正常・不正 material |
| F7 | material・権限不足、callback/factory/receipt failure、不明 use、no-op、budget 不足 |
| F8 | 実 CSV/JSON byte、正確な decimal 境界、重複構造、BOM/CRLF/Unicode path、snapshot 継続 |

初期化も public `start`/`observe` を通る実 callback で行い、初期 cost を別途記録して
全 method の総 budget に同じように加える。candidate factory が参照するのは現在の
State と有限 material recipe であり、oracle label や未来の観測を参照しない。
read は exact ID を一度取得し、check は観測済み material と明示された dependency を
使う。数値・file checker は実際に渡した入力を parse する。

0.2.1 内では EGR を三つの feasible baseline と比較する。`fixed-feasible` は宣言順、
`verify-first` は安定した verify 優先、`random-feasible` は seed 付きの選択である。
いずれも public `feasible_actions` の safety gate を使い、public `start` に元の有限
pool を渡す。Attempt の直接挿入や、budget を消費するための valid target 再検証は
行わない。F1 では provenance ranking、F2 では gap ranking を除いた ablation も行う。
0.2.0 EGR の別 run は互換な version pair を比較し、version 修正と同一 version 内の
選択方法の比較を混同しない。

oracle は raw の arithmetic・exact decimal・file 条件、receipt identity、現在の
exact target、owner/scope/contract、dependency、checker/revision/purpose、resolution
fingerprint を独立に検査する。`plan`・coverage・`make_basis`・private acceptance
predicate を正解判定として呼ばない。異なる active required target はそれぞれ valid
support を必要とする。正の content alias は重複として扱う一方、negative check は
exact subject ID を保つ。この有限 DAG recipe 上で least grounded positive proof を
評価する。一般の grounded alternative・negative cycle は runtime 回帰テストの範囲で
あり、この holdout oracle の対象ではない。raw-world validity と、権限・material・
budget を含めた solvability は別 label である。

## 分母と paired 集計

primary completion は original 順・random seed 17 における **solvable parent の n/N**
である。false satisfaction は **互換で試行した parent の n/N** であり、一つでも
評価済み variant が誤って satisfied となれば、その parent を数える。trial 単位の
件数と未評価 outcome も残す。旧 API の unsupported、unexecuted、exception、timeout
は明示的に数える。互換な exception/timeout は失敗した試行であり、正しい停止や
cost ゼロには置き換えない。旧版で未対応の invalidation は version pairing からのみ
除外し、旧 version の表には残す。

method 差では variant・random seed を parent 内で平均する。その paired parent 差を
seed 2239 で 1,000 回 bootstrap し、95% 区間を計算する。paired N、wins/ties/losses、
overall・family・budget 別結果を残す。生成 family は有限の設計 workload であり、
すべての利用者 task の標本ではない。区間はこの task 構成内の変動を示すものであり、
母集団全体への因果的な便益を証明しない。

全 task の cost と **both-success subset** の cost は分ける。後者は両 method の
すべての試行 variant が成功した parent に限定し、cost 差にはその N を併記する。
低 cost の失敗は効率改善ではなく、成功 subset の差は全 task の節約率でもない。
token・金額は測定せず、CPU/callback 数から金額への換算もしない。

## 時間・メモリ・pipeline reference

Q1/Q2 は同条件の isolated worker を使い、whole worker の deadline は 10 秒である。
7,200 秒の cap は `run_trials` 呼出しごとに、新版 method run と旧版 version-only run に
別々に適用する。startup/import・trial・serialization・IPC を
worker limit に含む。timeout 後に不明な cost は不明のまま保持し、cap による未実行行も
残す。trial CPU/end-to-end、planning、callback、serialization、初期化、worker の
startup/import/IPC を記録した field がある。trial CPU/end-to-end と allocation tracing は、
`environment()` が初めて SDK/Pydantic を import する前に開始する。その cold library import
は traced trial cost と allocation peak に含まれる。`startup_import_and_ipc_seconds` は
whole-worker の残差であり、trial 外の process/harness startup と IPC を含むが、すべての
library import 時間を分離・除去する field ではない。trial 値は純粋な controller resource
測定ではない。Q1/Q2 時間には `tracemalloc` の overhead も含まれる。
`planning_cpu_seconds` は EGR では runner の `plan` call を測るが、host baseline では
candidate factory・`feasible_actions`・selection を含む。phase の定義が異なるため、この
列を method 間の純粋な planner 時間として比較しない。両 branch は最後の共通 public
`plan` assessment も含む。trial 全体の CPU/end-to-end は
宣言した observer と method の実処理を測る。peak traced Python allocation は resident
memory ではなく、spawn cost は planner CPU cost ではない。旧・新版の pure-plan 性能比較は
別に実行する instrumentation なしの Q3 `plan` 時間である。

測定機は通常の Windows desktop であり、電源・熱状態、background process、scheduler の
挙動を実験的に制御していない。初期の installed-candidate Windows 検査（223 テスト、
SDK/CLI、smoke）は F1 の一部と重なった。したがって Q1/Q2 時間は tracing と変動する
desktop 負荷を含む実行の記述的観測であり、wall time の性能優位を主張する根拠には
しない。Q3 は両 version の Q1/Q2 完了後に直列実行し、時間・count・memory を別 worker で
測定したが、引き続きこの一台の通常 host 上の測定である。

Q3 は Q1/Q2 の並行負荷を避けて、その後に別に実行した。chain・diamond・branches・
pure cycle をサイズ 4/8/16/32/64、checker 数 1/2/3 で測る。旧・新版は同じ意味の record と
required 条件を使い、新版の default invalidation field は権限を追加しない。構築・
dump/load・worker end-to-end と `plan` CPU/wall time は分ける。warmup は 1 回、サイズ
4/8 は 10 回、それより大きいサイズは 1 回測定する。時間・diagnostic count・traced memory
は別 process で測り、時間測定には count instrumentation を入れない。

新版の count は実際の base-check/worklist-check/worklist-target 評価と最終 memo lookup を
別々に記録する。旧版は recursive trusted-check entry を数える。異なる作業単位であり、
比だけから CPU 高速化を主張しない。memory は別の 1 回の traced-allocation replay である。
通常の scaling worker は 3 秒、小さいサイズの timing worker は 20 秒、version ごとの
scaling run の cap は 1,200 秒である。whole-worker timeout は phase 不明の右打切りであり、startup・構築・
評価のどこで制限に達したか確定しない。正確な plan 時間やその下限には置き換えない。

F6/F8 の direct-pipeline reference も実 material を read/parse/validate し、routing 用の
初期化を省く。batching・receipt・SDK resource bound の契約が異なるため primary scheduler
表から除く。ただし共通 World/State/Policy/material setup は CPU/end-to-end に含まれ、
通常の最小 pipeline はこの reference より安く実装できる場合がある。依存順序が既知なら、
routing は call 数を減らさず overhead を増やす場合がある。同等・不利・指標間で混在する
結果も評価結果として保持する。

## Q3 の制御処理量・cost の観測

各 version は graph/size/checker の 60 input に count・timing・memory arm を適用し、
180 cell を要求した。新版は全 cell 完了し、旧版は whole-worker timeout 65 cell と
count instrumentation exception 1 cell を保持する。

| Version | 完了 cell | Timeout | Exception | Unexecuted |
| --- | --- | --- | --- | --- |
| 0.2.0 | 114/180 | 65 | 1 | 0 |
| 0.2.1 | 180/180 | 0 | 0 | 0 |

評価できた完了 cell の reference disagreement はなく、新版 indexed-work bound 違反も
なかった。新版 60 count input では、記録した各 check の base と最終 memo lookup を
一度ずつ評価し、check-truth step は recorded check 数と verified-dependency edge 数の和
以下だった。これは観測した fixture の bound であり、任意の履歴の cost 定理ではない。

| Graph / target 数 / checker 数 | 旧 recursive entry | 新 base / check-truth / target-truth / memo |
| --- | --- | --- |
| Branches / 4 / 1 | 7 | 4 / 7 / 7 / 4 |
| Chain / 4 / 2 | 52 | 8 / 14 / 7 / 8 |
| Chain / 8 / 2 | 1,004 | 16 / 30 / 15 / 16 |
| Diamond / 8 / 2 | 4,452 | 16 / 42 / 15 / 16 |
| Branches / 64 / 3 | 759 | 192 / 381 / 127 / 192 |
| Chain / 64 / 3 | Whole-worker timeout | 192 / 381 / 127 / 192 |
| Cycle / 64 / 3 | Count-arm RecursionError | 192 / 192 / 64 / 192 |

diagnostic の単位は異なり、旧 entry を新 memo lookup だけで割ると新版の実 work を省く。
次の表は同じ graph の **別々の** time/memory arm をまとめたもので、同時 instrumentation
付きの時間ではない。小さいサイズの timing は 10 回、大きいサイズは 1 回測定した。
1 回の値は安定した percentile 推定ではない。traced allocation は replay の input 構築・
dump/load・reference・plan を含み、planner だけの memory ではない。

| Graph / target 数 / checker 数 | 旧 / 新 median plan wall、ms | 旧 / 新 peak traced allocation、bytes | Timing 反復数 |
| --- | --- | --- | --- |
| Branches / 4 / 1 | 0.1196 / 0.1238 | 878,939 / 1,116,880 | 10 |
| Chain / 4 / 2 | 0.6565 / 0.1747 | 904,004 / 1,142,605 | 10 |
| Chain / 8 / 2 | 13.1176 / 0.3159 | 972,324 / 1,208,581 | 10 |
| Diamond / 8 / 2 | 57.3133 / 0.3895 | 991,121 / 1,227,389 | 10 |
| Branches / 64 / 3 | 16.2565 / 4.2293 | 3,275,593 / 3,834,572 | 1 |
| Chain / 64 / 3 | Timeout / 4.1350 | Timeout / 3,835,571 | 1 |
| Cycle / 64 / 3 | Timeout / 4.3264 | Timeout / 3,847,591 | 1 |

両 version が完了した timing input 39 件では、新 plan wall は 38 件で短く、1 件
（branches・4 target・1 checker）で長かった。両 version が完了した memory input
36 件では、新 peak traced allocation は全 36 件で大きかった。短い plan 時間と多い replay
allocation が同時に観測され、小さい単純 input は改善しない場合もある。Windows の
submillisecond CPU median は量子化によりゼロとなることがあるが、CPU work ゼロではない。
打切りとなった旧 input に速度比や高速化の下限を補完しない。完全な表には、この例だけで
なく全 360 cell を保持する。

exception は **旧 cycle / 64 target / 3 checker / count arm** の `RecursionError` である。
recursive counting wrapper が stack depth を増やした arm の失敗であり、instrumentation
なしの runtime crash の証拠ではない。65 timeout に混ぜず、元の stderr と row を raw
archive に保持する。完了した pure-cycle cell は、grounding のない cycle を satisfied と
しない reference に一致した。一般の grounded/negative cycle authority は protocol に
記したとおり scaling reference の対象外である。

## 再実行と証拠の境界

測定した exact wheel を別の通常環境へインストールし、固定した Python・runtime
version を合わせる。次の command は `src/` を import path に加えず benchmark code を
実行する。外部の新規 output path を使い、既存 freeze/results を上書きしない。

```sh
NEW_PYTHON -m benchmarks.harness freeze --output EXTERNAL/freeze.json --implementation-commit 305eec2cbf4f16c7d50dbb8bad002bc0cbc6d1c5 --wheel CANDIDATE_WHEEL --baseline-wheel OFFICIAL_020_WHEEL
NEW_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --output EXTERNAL/methods.jsonl
OLD_PYTHON -m benchmarks.harness run --phase holdout --freeze EXTERNAL/freeze.json --version-only --output EXTERNAL/old-version.jsonl
NEW_PYTHON -m benchmarks.aggregate EXTERNAL/methods.jsonl EXTERNAL/old-version.jsonl --output EXTERNAL/report
NEW_PYTHON -m benchmarks.scaling run --python NEW_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-new.jsonl
NEW_PYTHON -m benchmarks.scaling run --python OLD_PYTHON --freeze EXTERNAL/freeze.json --output EXTERNAL/scaling-old.jsonl
NEW_PYTHON -m benchmarks.scaling summarize EXTERNAL/scaling-new.jsonl EXTERNAL/scaling-old.jsonl --output EXTERNAL/scaling-report
```

protocol は新版の method/ablation/reference 合計 4,680 行、旧版 720 行と、別途制限した
scaling を要求する。要求行数は完了観測数ではない。以前の development log には cap・
metadata の変更過程が含まれ、診断用に保持するが confirmatory holdout 証拠には使わない。
holdout 閲覧後に実装・checker・generator・protocol を変更する場合は、新しい protocol と
未使用 seed が必要であり、以前の証拠は保存する。

raw archive `benchmark-raw-v0.2.1.zip` を生成し、内容を検証した。サイズ 9,502,776 bytes、
SHA-256 は `9212ee2499df0b16b47b23ac3150f71b83b1db69abc85a7123a02044f4fa69a0` である。
[checksum 記録](../benchmarks/results/BENCHMARK_SHA256SUMS) に識別子がある。
31 member は 29 source asset と `MANIFEST.json`・`BUNDLE_README.txt` からなり、変更して
いない formal method/version/scaling trace と report、別に label した development trace、
freeze/provenance/runtime constraint、固定 benchmark source、implementation LF archive、
完了済み Windows candidate profile、旧公開版と測定 candidate の wheel/sdist pair を含む。
manifest は member の byte size と hash を記録する。
小さい summary/freeze は `benchmarks/results` に保存し、大きな trace を
wheel に含めない。最終公開 wheel が文書のみの変更で METADATA と whole-wheel hash を
変えても、測定した candidate wheel を保持する。package fingerprint と byte 比較により、
metadata の変更と実行 package の変更を区別する。最終 CI は実 package・protocol・harness
byte の一致を検査し、それらの変更を文書のみの rebuild として扱わない。
[Release asset reference](https://github.com/kadubon/evidence-gap-router/releases/download/v0.2.1/benchmark-raw-v0.2.1.zip)
と `BENCHMARK_SHA256SUMS` は公開先である。archive の生成・検証は Release upload や
PyPI installation の完了を意味せず、実際の公開状態は [validation](validation.md) に別に記録する。
この CPU のみ・model 不使用の人工 task 評価は、LLM accuracy・統計的独立性・金銭節約・
capability growth・intelligence phase を示さない。観測された false satisfaction がゼロでも
risk ゼロとはならない。旧公開版の実際の不具合・履歴は [0.2.0 audit](audit-020.md)、
実装の境界は [design](design.md) を参照する。
