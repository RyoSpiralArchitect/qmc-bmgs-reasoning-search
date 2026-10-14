# Receiver ID 修正と同じ E4 データの再利用 — 2026-10-14

状態: **恒久IDの比較を修正。C2 の実再構成によるレビュー用提案を保存。証明書は未発行、本番は未実行。**

## 原因と修正

前回の E4 では `st_dev=16777234`、今回は全6パスで `16777229` だった。
一方、各パスの inode と保存されたファイル内容は一致していた。
旧実装は起動・マウントに依存するデバイス番号を、再起動をまたぐ恒久IDとして
比較していた。これが同じ内容を拒否する実装上の原因だった。

macOS の起動時刻は 2026-10-12 23:03:57 JST で、10月10日の観測と今回の間に
再起動があったことは確認できた。現在の番号は Data のデバイスノードの番号と一致する。
ただし、旧記録にボリュームUUIDやカーネルの割当ログはなく、
**その再起動が番号変更を起こした瞬間の証明や、過去からの物理ディスク連続性の証明ではない。**

Apple は通常の [volume identifier](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumeidentifier)
を再起動後まで永続するものとして扱わず、別に
[volume UUID](https://developer.apple.com/documentation/foundation/urlresourcevalues/volumeuuidstring)
を提供している。ローカルの `diskutil(8)` の IDENTIFIERS 節も再接続・再起動をまたぐ用途には UUID を勧めている。
採取したOS情報、マニュアルのハッシュ、既知のマウント点での読み取り結果は
[診断記録](qualifications/countdown_feedback_budget_receiver_identity_fix_20261014.diagnosis.json)に保存した。

| 照合の範囲 | 修正後の規則 |
| --- | --- |
| 再起動をまたぐ照合 | 固定パス、各階層の inode、ボリュームUUID、全内容を照合 |
| 一回の処理中 | 実際の `(st_dev, st_ino)` とUUIDの両方が変わらないことを要求 |
| 過去の記録 | 元の番号・HEAD・ハッシュをそのまま保持。現在のIDに書き換えない |

UUIDはシンボリックリンクを追わずに保持したファイル記述子から取得する。
現在の `/` は APFS のシステムスナップショット、
`/Users` 以下は Data で、同じ `st_dev` が見えていても UUID は異なる。
そのためパスの各階層を照合する。UUIDを取得できない場合の番号への代替はない。
異なるUUID・inode・パス・内容、処理途中の番号変化は拒否する。
OS更新でシステムスナップショットが変わった場合も、別途レビューが必要になる。

UUIDは今回初めて採取した **2026-10-14 の基準**である。
過去のUUIDが分かっていたことにはしない。
v2提案は `historical_location_correspondence` と `receiver_identity` を分離し、
実行時だけ有効なデバイス番号は別の処理記録に置いた。

## 固定した実装

実装コミット: `23ac0587a1a519cfb85711ffdcc4b28c3ce41a47`

ソースダイジェスト:
`4535836b9321da18e703a457356b5ff939cf8393414ddfa6ac845d2ec01f7f70`

変更は [certifier](../scripts/feedback_budget_receiver_e4_certificate.py)、
[テスト](../tests/test_feedback_budget_receiver_e4_certificate.py)、
[受入方針](strategy/countdown_feedback_budget_receiver_e4_certificate.md) の3ファイルに限定した。
凍結済みの E4/E3/E2 実装、過去の観測・照合記録、元の研究計画は変更していない。
旧定数の差替えや現在の stat 値を旧番号に見せかける処理も行っていない。

## 検証と実再構成

| 検証 | 実測結果 | この結果だけでは言えないこと |
| --- | --- | --- |
| 修正箇所の回帰テスト | 68件 PASS、31.903秒、skip 0 | 実機をもう一度再起動した試験ではない |
| リポジトリ全体 | 1,552件 PASS、単体テスト部分2,004.569秒。compile、Ruff、来歴・成果物・CLI検査も完了、終了コード0 | CI、外部レビュー、研究上の改善 |
| 実データの事前照合 | 6パス、23履歴チェーン、16参照、2アーカイブが一致 | 数値再構成や発行権限の代用ではない |
| C2: 基準動作 | 元の32トレースを再構成 | 新たな研究サンプルではない |
| C2: 保存済み PUBLIC 2組 | 各1,024トレース・512予算比較、全receipt・summaryを再現 | 各組は1入力multiset。2,048独立サンプルではない |
| C2: 元の入力群 | 102試行、採用64・棄却38、全順序・3ファイル・1,109,241バイトの入力射影を再現 | 新しい入力群や本番探索ではない |
| 保存結果と内容の最終照合 | 完全提案、処理記録、元ファイルを照合 | `--verify-proposal` による別プロセスでの全再計算ではない |

C2 は固定HEAD・新規プロセス・専用の空キャッシュで **一回だけ**実行した。
全16項目を過去のE4記録と比較し、完了時にもソース・実行環境・内容・場所・未使用スロットを再確認した。
処理時刻と元stdout/stderrの正確なハッシュは
[操作記録](qualifications/countdown_feedback_budget_receiver_identity_fix_20261014.operations.json)にある。

レビュー用提案: [固定の proposal](qualifications/countdown_feedback_budget_receiver_e4_certificate_20261010.proposal.json)

提案ダイジェスト: `cf718176521e83fbcfdf619d54183f1fee9f40628732c2c6d0f97530ed8e8250`

ファイル名の日付は既定の比較先を保つため `20261010` のまま。
今回の生成時刻やv2スキーマとは区別する。このファイルは**発行済み証明書ではない**。

## 元データの保存と解釈

変更対象3ファイル以外の既存386ファイル / 80,177,593バイトは旧HEADと一致。
以前から追跡していた380ファイルの全POSIXモードも一致した。
両PUBLICアーカイブの計2,054ファイル / 272,846,815バイト、
元の3ファイルのseal、3件のledgerを保持した。
本番出力・本番summary・元研究のclaim・entrypointの4スロットは未使用のまま。
新しい研究ケース E5、新たな PUBLIC 試行、候補発行、本番探索は作っていない。

元の研究IDは `feedback_budget_confirmation_64_seed_26091301/v1`。
64入力 / 1,024セル / 512予算対 / 256四群ブロックの計画を維持した。
両PUBLICの `screen_conjunction=false`、27 unsolvable・8 excluded・3 duplicate の
棄却理由も維持した。今回の成果は受入の誤拒否修正と再現性の確認であり、
探索性能・知能・科学的仮説の改善ではない。

## レビューの範囲と残した失敗

同じ実装担当による限定的な差分点検とテストであり、独立エージェント・外部・人間のレビューではない。
過去と現在のIDの混同、descriptor解放、UUID不取得、誤ボリューム、
処理途中の変化、型alias、提案の全体比較、権限への昇格を点検した。

初回のfocused試験は、正当な読み取り専用descriptorの `open` を禁止するAST検査に
引っかかった。この固定呼出しだけを許す検査に修正し、UUID取得失敗時にもdescriptorを解放する試験を加えた。
最初の全体検証では、スキーマ名変更後のテスト参照に旧 `case.device` が残っていたため
1 ERRORを観測し、既知の失敗がある実行を停止した。
参照を `case.historical_device` に修正し、最終focusedと全体検証を最初から通した。
初回の失敗末尾、途中版のPASS、停止した全体検証の出力は保持している。

最終の全体検証ログはツールで取得した転記であり、途中2箇所に出力省略がある。
終了時の `Ran 1552 tests ... OK`、全体PASSと終了コード0は保存されているが、
**全行の原ログを保存できたとは主張しない**。
一方、実C2のstdout/stderrは開始前に専用ファイルを排他的に確保し、直接・全量を保存した。

## 次の境界

今回で C2 のレビュー用提案まで。同じ原データをそのまま再利用できた。
C3ではこの提案のレビューと別途承認された発行専用実装、
発行直前の新規プロセスでの全再構成が必要。
C4の新coordinator/PUBLIC qualification、C5の新候補と正確なダイジェストへの本番同意は別段階である。
今回、発行・本番実行・push・PR・merge・CIは行っていない。

詳細: [事後保存照合](qualifications/countdown_feedback_budget_receiver_identity_fix_20261014.inventory.json)、
[処理記録](qualifications/countdown_feedback_budget_receiver_identity_fix_20261014.operation.json)。
