# E4 提案のレビューと全再検証 — 2026-10-15 JST

状態: **保存済み提案と新規プロセスの全再計算が完全一致。証明書は未発行、本番は未実行。**

[前回の ID 修正と C2 提案](../countdown_feedback_budget_receiver_identity_fix_20261014.md)を対象に、
同じ担当によるソースレビューと読み取り専用の全再検証を行った。
今回の範囲で追加修正を要する具体的な finding は見つからず、実装変更は行っていない。
独立エージェント・外部・人間のレビューではなく、別実装による独立検証でもない。

## 固定した対象

- 実装リビジョン: `23ac0587a1a519cfb85711ffdcc4b28c3ce41a47`
- 実装ソースダイジェスト: `4535836b9321da18e703a457356b5ff939cf8393414ddfa6ac845d2ec01f7f70`
- 検証時 HEAD / 提案のレビュー対象: `d9809393352e533374eff3df742b7aa5c41e3ccb`
- [既存提案](../qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.proposal.json):
  226,656 bytes、SHA-256 `129c3baa318eebb6eb88a6b124e84d681d1bd7f6b43596bc179908277e887c79`
- 提案ダイジェスト: `cf718176521e83fbcfdf619d54183f1fee9f40628732c2c6d0f97530ed8e8250`

提案の日付付きファイル名は既定の比較先として維持した。今回の検証日は JST 2026-10-15。
処理記録の UTC 日付は 2026-10-14 であり、日付や履歴を付け替えていない。

## レビューの範囲

対象は [certifier](../../scripts/feedback_budget_receiver_e4_certificate.py)、
[回帰テスト](../../tests/test_feedback_budget_receiver_e4_certificate.py)、
[受入方針](../strategy/countdown_feedback_budget_receiver_e4_certificate.md)と、
その境界を確認するための既存の読み取り・再構成ヘルパーである。

| 点検した境界 | 確認した内容 |
| --- | --- |
| 過去と現在の ID | 過去の番号を保持し、現在の UUID・パス・inode と、処理中の実際の device/inode を別々に照合する |
| UUID の取得と変化 | no-follow の保持 descriptor から各階層の UUID を取得。取得失敗、別 UUID、処理途中の変化を拒否し、descriptor を解放する |
| 提案と計算の結び付け | 固定パスとレビュー済みの完全なバイト列を認証してから解析。保存済み PASS やテンプレート比較だけでは実計算を代替できない |
| 全体比較と失敗 | 16 項目の完全比較に加え、提案全バイトを比較。途中未完了の件数は unknown のままで、完了済み件数と区別する |
| 権限の境界 | 検証結果は発行・受入・候補・本番実行の権限にならない。publisher や自動再試行・再開の経路は追加されていない |

今回も実機の再起動を挟んだ試験ではない。
現在の UUID は 2026-10-14 に採取した基準であり、過去の UUID や物理ディスク連続性を証明してはいない。
再起動による番号変化の回帰ケースは模擬試験である。この限界は前回から変更していない。

## 実測結果

新しいプロセスで `--verify-proposal` を一度だけ実行した。
固定の実装・レビュー対象、専用の空キャッシュ、変更のない checkout で、
保存済み記録の読み直しではなく、元の計算をすべて繰り返した。

- 開始: 2026-10-14 15:43:58.209956 UTC
- 完了: 2026-10-14 16:52:06.300019 UTC
- 所要: 約68分8秒、終了コード0。自動再試行なし。

| 検証 | 今回の結果 |
| --- | --- |
| 修正箇所の回帰テスト | 68件 PASS、42.027秒、skip 0 |
| リポジトリ全体 | 1,552件 PASS、単体テスト部分2,245.405秒、skip 0。compile・Ruff・成果物・来歴・CLI検査も PASS、終了コード0 |
| 元の基準動作 | 32トレースを再現 |
| 保存済み PUBLIC 2組 | 各1,024トレース・512予算比較、完全な receipt と summary が一致 |
| 元の入力群 | 102試行 / 採用64 / 棄却38、全順序と棄却理由を再現 |
| 保存済みの元入力 | 3ファイルの seal と1,109,241バイトの入力射影を再現 |
| 固定提案 | 新しく再構成した全226,656バイトが一致し、最終のソース・環境・提案・保存内容の再照合も完了 |

[検証結果](../qualifications/countdown_feedback_budget_receiver_e4_proposal_review_20261015.verification.json)
の状態は `WHOLE_RECONSTRUCTED_PROPOSAL_BYTE_IDENTICAL_NOT_ISSUED`。
検証結果ダイジェストは
`0eb7df81ab9c275441c997dc3c77682f4265ad52cdb517852e2c6bd9bbc766cb`。

手法は `fresh_process_same_frozen_implementation_full_recomputation`。
別プロセスではあるが、アルゴリズム上は同じ固定実装である。
全体テストは同じ固定 HEAD で並行して実行した。これらの所要時間は性能ベンチマークではない。

元の研究 ID は `feedback_budget_confirmation_64_seed_26091301/v1` のまま。
64入力 / 1,024セル / 512予算対 / 256四群ブロックの計画、
両 PUBLIC の `screen_conjunction=false`、
27 unsolvable・8 excluded source multiset・3 duplicate source multiset の棄却を保持した。
各 PUBLIC は1入力 multiset であり、2,048の独立サンプルではない。
探索性能・知能・科学的仮説の改善を示した結果ではない。

## 保存と記録

処理後に、検証前の追跡済み395ファイル / 80,574,496バイトと全POSIXモード、
両 PUBLIC の計2,054ファイル / 272,846,815バイト、
元の3ファイルと3件の ledger を再照合し、すべて不変だった。
元の研究用4スロットと発行済み証明書用4スロットは、計8箇所とも未使用のまま。

[操作・保存確認の記録](../qualifications/countdown_feedback_budget_receiver_e4_proposal_review_20261015.operations.json)
は、実行引数、開始・完了時刻、終了コード、各ログと補助プログラム、
実行前の全ファイル目録の正確なハッシュを保持する。
子プロセス記録は採取時の状態を残し、事後照合結果を最上位で区別した。
事後の保存内容の点検は、もう一回の数値再構成として数えていない。

今回は回帰テスト・全体検証・実データ検証の stdout/stderr を開始時から専用ファイルへ直接保存した。
全体検証の原ログは stdout 21,301 bytes、stderr 294,174 bytes。
実データ検証の原ログは stdout 12,500 bytes、stderr 14,373 bytes。
実データ側の stderr 16行は情報提供用の進捗であり、最終成功の根拠は正常終了と検証結果の組である。
原ログは local/ignored に保持し、上記の追跡対象 manifest と一致する。

この後の追跡対象への追加は、この報告書・検証結果・操作記録の3ファイルのみ。
既存提案、凍結済みソース、過去の失敗・観測記録は変更していない。

## 次の境界

今回で提案のレビューと全再検証まで完了した。C3 の発行は未完了である。
発行専用実装はまだなく、別途その実装・レビューと発行の承認が必要になる。
発行する場合は、その直前にも新規プロセスで完全再構成し、排他的な証明書 bundle を作る必要がある。
今回の検証結果を保存済みの発行権限として流用しない。

この検証ファイルは `proposal_review_20261015` 名前空間に保存し、
発行済み証明書の `certificate_20261010.verification.json` スロットには置いていない。
新 PUBLIC 試行、新入力群の発行、新候補、本番探索、push、PR、merge、CI は実施していない。
C4 の coordinator/PUBLIC qualification と C5 の新候補・正確なダイジェストへの本番同意は、引き続き別段階である。
