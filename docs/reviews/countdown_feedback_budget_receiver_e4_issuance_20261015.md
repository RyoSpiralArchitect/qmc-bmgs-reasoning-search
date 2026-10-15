# E4 証明書の実発行 — 2026-10-15 JST

状態: **C3 の証明書だけの発行が完了。保存後の読み取り専用照合も PASS。**

[発行専用実装のレビュー](countdown_feedback_budget_receiver_e4_publisher_20261015.md)後の
明示的な証明書発行の承認に基づき、固定した実装を新規プロセスで一度だけ実行した。
実データを完全再構成し、レビュー済み提案と全バイト一致した後に、固定の raw bundle を排他的に発行した。
これは新 coordinator の適格性、候補発行、本番探索の承認ではない。
先行レビューの「未発行」は当時の正しい状態として変更せず、この報告を追加する。

## 今回、実際に完了したこと

| 対象 | 完了した処理 |
| --- | --- |
| baseline | 32 trace の再構成 |
| 元の PUBLIC archive | 1,024 trace、512 budget-prefix 比較、receipt と summary 全体の再現 |
| receiver-v2 PUBLIC archive | 1,024 trace、512 budget-prefix 比較、receipt と summary 全体の再現 |
| 元の入力群 | 102試行を再構成し、64採用・38棄却、seal 全体と入力投影全体を再現 |
| 証明書 | 新しい再構成結果が固定提案の 226,656 bytes と完全一致 |
| 発行 | 証明書 → 検証記録 → COMMIT の順に保存。排他作成・書き込み・ファイル／ディレクトリ同期・最終観測の全項目が `COMPLETE` |
| 保存後の照合 | 全3ファイルの canonical JSON、内容ダイジェスト、バイト列、相互参照、source、保存先の現在の ID と所有状態を確認 |

発行側の最終記録は `CERTIFICATE_ONLY_BUNDLE_ISSUED`、
`certificate_issued=true`、`execution_dispatch_entered=false`。終了コードは0だった。
保存後の別プロセスの照合は `SAVED_ISSUED_BUNDLE_BYTES_BINDINGS_AND_LOCATION_MATCH_READ_ONLY`、
終了コード0。こちらは保存された内容の検査であり、数値再構成・再発行・将来の receiver admission は行っていない。

2つの過去の PUBLIC screen conjunction はどちらも **false のまま**。
今回の再生を新しい PUBLIC 試行に数えず、2,048 trace を2,048の独立した研究標本とも扱わない。
38棄却は、解なし27・除外済み source multiset 8・重複 source multiset 3であり、結果を取り除いていない。
新規プロセスで同じ凍結実装を実行した検証であって、アルゴリズム的に独立した実装や独立担当者の検証ではない。

## 固定した実装と時刻

- 処理中の HEAD: `f807c8a5b3566f1b3bb0699f191de892547f25fe`
- 発行側実装: `abf04523809a440b760886b48d2aa681749825e5`
- 発行側 source digest: `38a104e89256216c1df8184877ef89e4e457f2c22fb21b5bff0df4d5c757da0c`
- certifier 実装: `23ac0587a1a519cfb85711ffdcc4b28c3ce41a47`
- 固定提案のリビジョン: `d9809393352e533374eff3df742b7aa5c41e3ccb`
- 提案レビューのリビジョン: `d3f088c324f59db433dc8e9fc9a4c194d2e17fe1`

発行処理は 2026-10-14 **17:59:09.577988–21:31:14.442125 UTC**、
JST では2026-10-15 **02:59–06:31**。約3時間32分で正常終了した。
数値再構成だけでなく、発行前後の繰り返しの照合・保存・同期を含む所要時間であり、探索性能の測定ではない。
保存後の照合は同日 **07:53:32.433293–07:53:39.293743 UTC**（JST 16:53）に実施した。
処理終了と事後照合は別時点の観測であり、その間や将来の状態を保証する記録ではない。

新規の private empty cache と専用プロセスを使い、stdout / stderr は開始時から原ログに直接保存した。
中間のファイル出現・サイズだけでは成功と判定せず、最終操作記録と正常終了を確認した。
再試行・再開・別名出力・raw bundle の上書きや削除はしていない。
発行側、certifier、旧 E4/E3 のソース・テスト・受入方針は変更していない。

## 発行原本と同一バイトの文書コピー

原本は `artifacts/work/feedback-budget-receiver-e4-certificate-20261010-a/` の3ファイル。
発行処理の終了と保存後照合の成功を確認してから、以下を同一バイトで追加した。
ミラー配置は発行処理とは別であり、発行側自身の `promoted_mirrors_written=false` と矛盾しない。
ファイル名の `20261010` は固定された提案の識別子で、今回の発行日への付け替えはしていない。

| 文書コピー | bytes | SHA-256 |
| --- | ---: | --- |
| [証明書](../qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.certificate.json) | 226,656 | `129c3baa318eebb6eb88a6b124e84d681d1bd7f6b43596bc179908277e887c79` |
| [発行直前の検証記録](../qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.verification.json) | 18,494 | `e9db116a27e40019deb9ba6351d4f6c85312253ebaa3bb19e45f1ba60f5233d5` |
| [確定記録](../qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.commit.json) | 11,561 | `5452dd5bbc315e1af4d0ab356212516e099c7e70c2563d269cc7640deedcdd32` |

証明書自体は提案と同一で、発行済みフラグを追加していない。
検証記録の `certificate_issued_at_verification=false` は発行直前の状態。
実際に発行が完了したことは、COMMIT と最終操作記録が区別して保持する。
現在の UUID / path / inode と処理中の device / inode を照合したが、
過去まで遡る物理ディスク同一性や、再起動が ID 変更の原因だったことは証明していない。

## 検証・保存した境界

同じ凍結 HEAD で全体検証を実施し、**1,592件 PASS、skip 0**。
単体テストは1,993.188秒、compile・Ruff・成果物・来歴・設計・CLI検査を含む
`python scripts/validate.py` 全体も終了コード0、`repository validation: PASS` だった。
全体検証は 2026-10-14 17:59:00.971263–18:38:57.851244 UTC。
これは文書ミラー追加前のソース検証であり、科学的な性能改善や本番適格性の証拠ではない。

文書追加後にも、原本／コピーの全バイト一致、strict JSON / 内容ダイジェスト、参照ログ、
相対リンク、Ruff・成果物・来歴・設計検査と、ステージ済み差分の空白検査を確認した。
1,592件の全単体テストを文書追加後にもう一度実行したという意味ではない。
文書配送の初回補助検査は `git diff --no-index` の「差分あり」終了コード1を失敗と扱って停止した。
空白診断はなく、先行4検査は成功。初回の原ログ・失敗記録は保持し、別の補助プログラムで
ステージ済みの正確な5ファイルに対する `git diff --cached --check` に切り替えて確認した。
これは文書検査の修正であり、発行の再試行・再構成・raw bundle の変更ではない。
両検査の原記録は local の `artifacts/work/feedback-budget-receiver-e4-issuance-20261015/`
にある `delivery.process.json` / `delivery-v2.process.json` に分けて保持した。

発行前から存在した追跡済み **404ファイル / 80,714,552 bytes** と、
保存済み raw **2,060ファイル / 274,380,339 bytes** の全バイト・POSIXモードは不変。
後者のファイル集合も不変で、過去の PUBLIC 2組、元入力群3ファイル、既存 ledger 3件を保持している。
元の研究用4スロットは事後照合時にも未使用。今回使用した証明書用の保存先と混同しない。

[操作記録](../qualifications/countdown_feedback_budget_receiver_e4_issuance_20261015.operations.json)には、
事前目録、4プロセスの引数・時刻・終了コード、原ログのハッシュ、最終発行記録、読み取り専用照合、
source、3組の原本／ミラー照合、補助プログラムの参照を保存した。
この操作記録も local 原本と同一バイトで、47,708 bytes、SHA-256
`447ed727d89b2339b0958a03caacf8fa68cd298dc4fab8d9109641f68108dbb0`。
raw bundle・原ログ・実行時の補助プログラムは local / ignored のまま保持する。
今回追加した追跡対象は3つのミラー、この操作記録、この報告の計5ファイルのみ。

## 次の境界

C3 は完了。次は **C4: 発行済み証明書を使う新 coordinator の実行連携を、別の実装・レビューで検証する段階**。
元の study を使う前は未使用を確認し、使った後は正確な所有済み claim / output との結び付きを確認する必要がある。
過去の「未使用だった」という値を永久に有効にしたり、既存の未使用チェックを飛ばしたりしない。
実装・レビュー後の固定 PUBLIC 試行にも別の明示承認と保存結果全体の検証が必要となる。

新候補・新 PUBLIC 試行・新 cohort 公開・本番探索・provider 呼び出しは未実施。
元の study / input / schedule / seal / claim / output を別物に替えていない。
C5 の本番には、新候補のレビューとその**正確な新ダイジェストへの同意**が引き続き必要。
今回、push・PR・merge・CI は行っていない。
