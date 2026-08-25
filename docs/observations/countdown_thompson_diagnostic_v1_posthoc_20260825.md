# Countdown Thompson diagnostic v1: post-hoc mechanism observation

Date: 2026-08-25

## Bottom line

既存240-cell traceだけをread-onlyで再検証・集計した。新しいoutcome-bearing cohort、
retry、provider call、locked-128実行は行っていない。既存analyzerは各historical
searchをempty stateからdeterministically regenerateし、byte-identical replayを
要求するため、固定search replayそのものは実行している。

Dense terminal backupはtraceに存在し、post-review supplemental checkではV3の
565 update entries中540 entriesでposterior meanが変化した。しかし現行budget内の
選択はほとんど変わらなかった。v2/v3のtrajectory 0は48/48 pairで一致し、1回目の
backup後に始まるtrajectory 1も48/48で一致した。差が初めて出たのは2回backup後の
trajectory 2で、そこまで開始できた44 pair中4 pairだけだった。

その4 pairにもexact rescueはない。post-first best absolute errorは3 pairで不変、
1 pairだけ`2 -> 1`に改善した。全48 pairではv3-only exactが0、v2-only exactも0で、
事前固定ラベルは`MIXED_OR_NULL_DENSE_DIRECTION`となった。これはdense feedbackが
悪いという結果ではない。むしろこのartifactでは、feedbackの違いが選択へ届くのが
遅く、届いた場合もexact successへ変換されなかった、という記述が最も近い。

V4も同じ境界で閉じた。greedy anchor failure 28 cellsのうちpost-anchor best errorが
改善したのは1 cellだけで、同じ`2 -> 1`だった。12 cellsは不変、15 cellsは悪化、
exact post-anchor rescueは0だった。anchor success 20 cellsは全て既存greedy由来で、
V4を追加探索の成功としてpromoteする根拠はない。

## Question and frozen design

結果集計前に
[`countdown_thompson_posthoc_mechanism_audit.md`](../strategy/countdown_thompson_posthoc_mechanism_audit.md)
で次を固定した。

1. v2/v3をtask fingerprintとexploration seedで48 pairにexact matchする。
2. selection identityを
   `(trajectory_index, depth, state, action_index, child_state)`とする。
3. event order上、先行する`trajectory_backed_up`が1件以上あるselection/terminalだけを
   feedback-informedとする。
4. v2/v3の最初のfeedback-informed action divergence、post-first best error、
   post-first exact outcomeを保持する。
5. v4のanchor errorとcompleted post-anchor best errorを全48 cellsおよび
   anchor-failure subsetで分離する。
6. feedback exposureとerror directionを記述しても、どちらがfailureの原因かは
   決めない。

これはoutcomeを既に知った後のexploratory auditであり、preregistrationではない。

最初の実行要求では、reviewed authorization revisionとして
`a0111868d654...`というnonexistent / mistyped revisionを渡した。これは正しい
reviewed revisionでも、authorization内のrunner revision `a0111868aae...`でもない。
operatorが観測したCLIはsource preflightで`INVALID`となり、output pathは
作られなかった。このfailed invocation historyはoperator evidenceであり、canonical
receipt自身が証明する事実ではない。正しい二つのrevisionをdesignに明記してcommit
した後、初めてreductionを実行した。

## V2 versus V3

| Reduction | Result |
|---|---:|
| exact paired cells | 48 |
| trajectory 0 action identity equal | 48/48 |
| trajectory 1 action identity equal after one backup | 48/48 |
| trajectory 2 begun after two backups | 44/48 |
| first action divergence | 4/48 total; 4/44 exposed |
| first divergence coordinate | trajectory 2: depth 0 x3, depth 1 x1 |
| post-first best error: v3 improved / equal / worse | 1 / 47 / 0 |
| post-first exact: both / v3-only / v2-only / neither | 5 / 0 / 0 / 43 |

The four divergent pairs were:

| Task fingerprint prefix | Seed | First difference | v2 best | v3 best |
|---|---:|---|---:|---:|
| `0406b78647c0` | 7171 | trajectory 2, depth 0 | 427 | 427 |
| `c4871dc359ba` | 7169 | trajectory 2, depth 1 | 2 | 2 |
| `c4871dc359ba` | 7171 | trajectory 2, depth 0 | 2 | 1 |
| `eca2d75ca8fc` | 7169 | trajectory 2, depth 0 | 504 | 504 |

したがって「dense feedbackを入れれば最初のfeedback直後から探索が変わる」はこの
artifactでは棄却された。二つ目のterminalまで行動・結果が同じであり、2回更新後に
初めて一部が分岐した。

`c4871dc359ba... / seed 7171`の`2 -> 1`は局所的なnear-miss改善だが、exactではなく、
1/48のpost-hoc観察である。一般的な方向性や次回成功を示さない。

## Feedback exposure

| Method | Backups per cell | Feedback-informed completed trajectories | Feedback-informed begun trajectories |
|---|---|---|---|
| v2 | 2 x31, 3 x17 | 1 x31, 2 x17 | 1 x4, 2 x40, 3 x4 |
| v3 | 2 x31, 3 x17 | 1 x31, 2 x17 | 1 x4, 2 x40, 3 x4 |
| v4 | 2 x39, 3 x9 | 1 x39, 2 x9 | 1 x4, 2 x40, 3 x4 |

全methodでtrajectory 1は48/48 cellsが1回のbackup後に開始した。trajectory 2は
44/48 cellsが2回のbackup後に開始し、trajectory 3まで開始したのは4/48 cellsだった。
各completed trajectoryは5 edge updatesを持つため、v2/v3のupdate-entry totalは
10 x31 cells、15 x17 cellsだった。

これは「feedback opportunityがゼロだった」という説明を否定する。一方で、v2/v3の
差が実際のactionへ届いたのは2回更新後の4 pairだけであり、現在のbudgetで十分な
posterior leverageがあったとも言えない。追加updateなら成功した、という反実仮想は
このtraceからは検証できない。

## V4 anchor versus post-anchor

| Reduction | All 48 cells | Anchor-failure 28 cells |
|---|---:|---:|
| improved | 1 | 1 |
| equal | 31 | 12 |
| worse | 16 | 15 |
| no completed post-anchor terminal | 0 | 0 |
| exact rescue | - | 0 |

Anchor successは20/48 cellsだった。Post-review supplemental validationで、V4
anchorと対応するheuristic greedyのselection identityおよびterminal identityが
48/48 pairsで一致することを別途確認した。したがって20 cellsは元のgreedy 5/12
tasksを4 seedsずつ再現したものだった。そのうち19 cellsではpost-anchor trajectoryも
exactだったが、anchorが既に成功しているためrescueではない。

唯一のanchor-failure improvementも
`c4871dc359ba... / seed 7171`の`2 -> 1`で、v2/v3比較の唯一のstrict improvementと
同じpairだった。局所構造として次のmargin audit候補にはなるが、成功追加ではない。

## Failed hypotheses retained

1. **Dense feedback changes the next trajectory.** Failed here: trajectory 1
   action identity was equal in all 48 v2/v3 pairs.
2. **Dense feedback adds exact successes over v2.** Failed here: v3-only
   post-first exact count was 0.
3. **A greedy anchor lets posterior perturbation rescue anchor failures.**
   Failed here: exact post-anchor rescue count was 0/28 anchor failures.
4. **This trace can identify “too few updates” versus “bad feedback
   direction” as the cause.** Not identified. Exposure was limited and observed
   direction was overwhelmingly null, but no unobserved continuation exists.

## Interpretation and claim boundary

`MIXED_OR_NULL_DENSE_DIRECTION`は事前固定したdescriptive labelであり、統計検定でも
method rankingでもない。実数は`improved/equal/worse = 1/47/0`なので、dense direction
が有害だったという証拠はない。より狭い解釈は、現行fixed budgetではdense valueが
ほぼselection-inertで、稀に分岐してもexactへ届かなかった、である。

Integrity `PASS`は、authorization、source bytes、240-cell collective、stage-one /
stage-two replay、既存summary、pair coverage、canonical reductionが閉じたことだけを
表す。因果、優越性、task transfer、retry、locked-128実行を一切authorizeしない。

Decisionは`STOP_REPAIR_NO_LOCKED_128_RUN`のまま維持する。

## Provenance and validation

- audit source revision: `c07ee042feb2e3cedf3d2713f4fb236fad40495b`
- artifact commit digest:
  `ffd5f875f3d560382dd21fddec95b47ad0d4442913d8a5fb7faf104d12f209b9`
- records JSONL: 22,113,649 bytes,
  SHA-256 `352e225eefe3a8ef8ebc1718b3bb0162913af81cc7211c1cd4acfaff00ab9669`
- existing summary deterministic digest:
  `46ebdb1eabcaa91220ed8bb10370f70aad0c61d37a2ef6150d09ca29beac0db5`
- post-hoc receipt deterministic digest:
  `880f9453f2d85a6e2490c80424dc54d5d88c8838c9a5e5ece53c26172840b17e`
- post-hoc receipt raw SHA-256:
  `ede8d2caedf75ebf6d29a5861bd2e9a68792155307c788a2f553e64b73effff8`
- repository receipt and external receipt: byte-identical, 82,996 bytes
- operator validation outside the canonical receipt: implementation validation
  before real reduction passed 567 tests and 310 subtests; the first six new
  synthetic post-hoc tests passed

Canonical receipt:
[`posthoc_mechanism.json`](../results/countdown_thompson_diagnostic_v1/posthoc_mechanism.json)

## Next handoff

次に進むなら新しいsuccess runではなく、同じtraceのselection marginを読む
read-only auditを先に置く。具体的には、feedback-informed selectionごとにwinnerと
runner-upのmargin、v2/v3 posterior差、action flipに必要なvalue scaleを分離する。
これは「何倍なら成功した」という性能反実仮想ではなく、現行feedbackがdecisionへ
届かなかった理由を数値化する感度診断に限定する。

その診断でposterior leverage不足が再現可能に確認できた場合だけ、別のdevelopment
cohortでtrajectory budgetまたはfeedback scaleを一因子ずつ変える設計を新たに
freezeする。locked-128は引き続き開かない。
