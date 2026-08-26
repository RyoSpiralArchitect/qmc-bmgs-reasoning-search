# Countdown Thompson diagnostic v1: selection-margin observation

Date: 2026-08-26

## Bottom line

既存240-cell diagnosticを再検証し、feedback-informed selectionの局所score面を
read-onlyで監査した。新しいoutcome-bearing cohort、retry、provider call、未完了
trajectoryの継続、locked-128実行は行っていない。既存analyzerによるempty state
からのdeterministic search replayとbyte-identical検証は実行した。

V2/V3の48 task/seed pairsには370件のcommon-prefix decision surfacesがあった。
そのうちV3のdense terminal valueがV2との差としてscoreへ届いたsurfaceは94件、
exact zero displacementは276件だった。94件のうちobserved dense scale
`lambda=1`でactionが変わったのは4件だけで、既存post-hoc auditの最初の4 divergence
と完全に一致した。

残る90件では、81件に正方向のaction boundaryがあったものの全て`lambda>1`で、
うち64件は`lambda>16`だった。9件はdense displacementが非ゼロでも、その方向を
正に何倍してもV2 baseline actionを外すboundaryがなかった。したがって、この固定
artifactで最も狭い記述は「dense feedbackは多数のbackup meanを変えたが、次の
decision surfaceへ届く場所が疎で、届いた場合も多くはobserved marginに対して小さ
かった」である。

これは「16倍なら成功した」という結果ではない。Scale pathは一つのnodeで
prior/noise remainderを固定した局所直線であり、action flip後のstate、terminal、
errorは観測していない。

## Question and frozen design

Aggregate marginを見る前に
[`countdown_thompson_selection_margin_audit.md`](../strategy/countdown_thompson_selection_margin_audit.md)
をcommit `997345a6b466d9bc824672921cd2e6bd2dc43668`で固定した。

監査は次を分離した。

1. 各feedback-informed selectionのwinner/runner-up margin。
2. Traceの`before/after`から復元した、そのdecision時点のposterior mean vector。
3. Recorded scoreからcurrent meanだけを`lambda`倍するlocal mean-scale path。
4. V2/V3 common prefix上で、V2 scoreからV3 scoreへのobserved dense displacementを
   `lambda`倍するpaired dense-scale path。
5. Action boundaryとterminal performanceを明示的に分離するclaim boundary。

Binary64は`Fraction.from_float`でexact rationalへ持ち上げ、boundaryの分子・分母を
receiptに保持した。Float approximationは可読用だけである。

## Individual posterior-mean sensitivity

ここで`zero mean`は「feedbackなし」を意味しない。Posterior visitsによるnoise
shrinkageはrecorded prior/noise remainder側に固定されている。この表が測るのは、
current posterior **mean termだけ**を0からrecorded scale 1へ動かした局所効果である。

| Method | Feedback-informed selections | Nonzero mean vector | Zero mean vector | Mean term changed action by scale 1 | Boundary after scale 1 | No positive boundary |
|---|---:|---:|---:|---:|---:|---:|
| v2 binary terminal | 382 | 31 | 351 | 17 | 0 | 365 |
| v3 dense terminal | 382 | 133 | 249 | 22 | 86 | 274 |
| v4 greedy anchor + dense | 359 | 285 | 74 | 128 | 36 | 195 |

Observed winner/runner-up marginのfive-number summaryは次だった。

| Method | Min | Q1 | Median | Q3 | Max |
|---|---:|---:|---:|---:|---:|
| v2 | 0.002742 | 0.091603 | 0.239370 | 0.472754 | 2.172328 |
| v3 | 0.002742 | 0.094497 | 0.240274 | 0.460351 | 2.172328 |
| v4 | 0.008564 | 0.258844 | 0.507845 | 0.887223 | 3.019587 |

先行post-hoc auditではV3の565 backup update entries中540件でmeanが変化していた。
一方、実際のfeedback-informed selectionでnonzero mean vectorが見えていたのは
133/382だった。この差はtree-local updateが「どこかのedgeを更新した」ことと、
次のtrajectoryが「そのnodeを再訪してmeanをdecisionへ載せた」ことが別であると
示す。

V4ではmean termが128/359 selectionsでactionを変えるだけの局所leverageを持って
いた。したがって「posteriorが常にselection-inert」は誤りである。ただし先行
post-hoc resultではanchor-failure 28 cellsのexact post-anchor rescueは0だった。
この二つは両立する。Actionを変えたことは、良いactionへ変えたことを意味しない。

## V2/V3 common-prefix dense displacement

Paired pathは、state、action order、proposal digest、point digest、noise normalizer、
visit vectorが同じpre-decision surfaceだけを含む。最初にrecorded actionが違った
surfaceは含め、その直後でpairingを停止した。

| Reduction | Result |
|---|---:|
| exact task/seed pairs | 48 |
| pairable feedback-informed surfaces | 370 |
| exact zero score displacement | 276 |
| nonzero dense score displacement | 94 |
| action flips at observed scale `lambda=1` | 4 |
| positive boundary after observed scale | 81 |
| nonzero displacement but no positive boundary | 9 |
| max score-vs-mean-delta rounding residual | 1.453e-16 |

Nonzero 94 surfacesのboundary内訳は次である。

| First boundary scale | Count |
|---|---:|
| `<= 1` (observed action flip) | 4 |
| `(1, 2]` | 3 |
| `(2, 4]` | 5 |
| `(4, 8]` | 4 |
| `(8, 16]` | 5 |
| `> 16` | 64 |
| no positive boundary in this direction | 9 |

V2 margin medianは0.238531だった。各surfaceのmaximum absolute dense score
displacementはmedian 0、Q3 0.000362、maximum 0.333333だった。別々のquantileを
直接比率と読むべきではないが、exact boundary集計は、非ゼロdisplacementの多くが
recorded action marginを越えるには遠かったことを直接示している。

## Where the displacement reached

Dense displacementが非ゼロだった94 surfacesのdepth分布は:

- depth 0: 85;
- depth 1: 8;
- depth 3: 1;
- other depths: 0.

Trajectory別には:

| Trajectory | Pairable surfaces | Nonzero displacement | Action flips |
|---|---:|---:|---:|
| 1, after one backup | 240 | 50 | 0 |
| 2, after two backups | 126 | 42 | 4 |
| 3, after three backups | 4 | 2 | 0 |

最初のbackup直後は50 surfacesでV2/V3 scoreが異なっていたが、240/240でactionは
同じだった。Actionが初めて変わったのは、先行auditと同じく2回backup後の
trajectory 2だけだった。Feedback差は主として再訪される浅いnodeへ届き、深い
新規stateの大半ではdecision差がexact zeroだった。

## The four observed action flips

| Task fingerprint prefix | Seed | Coordinate | V2 margin | Boundary scale | V2 -> V3 action |
|---|---:|---|---:|---:|---|
| `0406b78647c0` | 7171 | trajectory 2, depth 0 | 0.023419 | 0.289258 | 3 -> 10 |
| `c4871dc359ba` | 7169 | trajectory 2, depth 1 | 0.085848 | 0.257545 | 8 -> 17 |
| `c4871dc359ba` | 7171 | trajectory 2, depth 0 | 0.021061 | 0.063182 | 1 -> 19 |
| `eca2d75ca8fc` | 7169 | trajectory 2, depth 0 | 0.027684 | 0.110736 | 17 -> 10 |

これらは全てfull observed displacementより前にlocal boundaryを越えていた。
しかし先行post-hoc receiptのterminal reductionでは、対応するpost-first best errorは
順に`427 -> 427`、`2 -> 2`、`2 -> 1`、`504 -> 504`で、exact rescueは0だった。
Margin receipt自身はterminal errorをreductionへ使用せず、この対応は既存post-hoc
resultとの別表cross-referenceである。

## Failed hypotheses retained

1. **Dense backup values never reach selection scores.** Rejected. 94 common
   surfaces had nonzero v3-v2 displacement.
2. **The first dense update changes the next trajectory.** Failed here. There
   were 0 action flips across 240 trajectory-1 surfaces.
3. **Most nonzero dense displacements sit just below an action boundary.**
   Failed here. 64/94 required scale greater than 16, and 9/94 had no positive
   boundary along the observed direction.
4. **Posterior means are globally selection-inert.** Rejected. The recorded
   mean term changed 22/382 v3 and 128/359 v4 local decisions.
5. **A local action boundary identifies a successful feedback scale.** Not
   identified. The audit observes no future state or terminal after a
   hypothetical scale change.

## Interpretation and claim boundary

このartifactは、単純な二択「feedbackが全く効かなかった」対「feedbackの向きが悪か
った」を支持しない。Mean更新は存在し、V4を含めaction leverageも存在した。一方、
V2/V3差は370 common surfaces中276でexact zero、非ゼロ94のうちobserved actionを
変えたのは4だけである。

したがってmechanism-levelの結論は、dense valueが多くのdecisionへ届く前にbudgetが
閉じ、届いた箇所でもmarginに対して不足する場合が多かった、である。ただし、より
大きなscale、より多いtrajectory、異なるcredit assignmentのどれが成功を増やすかは
このtraceから識別できない。

Integrity `PASS`はprovenance、240-cell replay、posterior reconstruction、pairing、
exact-rational boundary reductionが閉じたことだけを表す。Method superiority、因果、
task transfer、retry、locked-128 authorityではない。

Decisionは`STOP_REPAIR_NO_LOCKED_128_RUN`のまま維持する。

## Fresh-review hardening

初回PR headのdisk-blinded fresh reviewは三つの実装上の穴を見つけた。

1. frozen digestとrevisionがcode内でpinされず、callerがcoherentに改変した
   post-hoc receiptと新hashを同時に渡せた。
2. repository validationがtracked `selection_margin_v1.json`そのものを読まず、
   canonical receiptの破損を検出できなかった。
3. imported post-hoc publication errorがCLIのcanonical `INVALID` boundaryから漏れた。

これらをsource revision `64fda29cac2499bf42e749d721d3c08742bac038`で修正した。
全frozen anchorsをsource-attested moduleへpinし、post-hoc authority metadataもfresh
recomputationと照合した。Tracked receiptのstrict JSON、digest、raw hash、byte count、
source/design hash、主要集計をrepository testへ追加し、missing/occupied inputも
tracebackなしのcanonical `INVALID`へ閉じた。

修正後のfresh replayは旧receiptと`reductions`、`posthoc_revalidation`、
`input_provenance`がexactly equalだった。したがってfindingはauthorityとvalidation
surfaceを修正したが、selection-margin結果は変更していない。

更新headのfresh rereviewはさらに、on-disk module/HEAD blobの照合だけでは実行中の
loaded module originをbindしないP1を見つけた。Schema v2はselection audit自身、
post-hoc audit、diagnostic analyzer、regular-file publication、trace、およびpackage
modulesのloaded `__file__`をrepository内のregular clean-HEAD blobへ結び、8-file
runtime source receiptをmaterializeする。Historical module originとdisplaced post-hoc
originはinput open前にfail closedするtestを追加した。

このbindingはordinary Python importとclean-HEAD file bytesの範囲である。Hostile
interpreter、実行中code objectのin-memory mutation、kernel compromiseをattestしない。
Schema v2 fresh replayもv1と`reductions`、`posthoc_revalidation`、`input_provenance`が
exactly equalであり、数値結果は変わっていない。

最終exact-head fresh reviewは、通常のtimestamp-based `.pyc`へ改変codeを置くと、
loaded moduleの`__file__`がclean tracked `.py`を指したまま改変codeを実行できる
追加の穴を再現した。Reviewerの最終summary自体はhost safety filterで中断したが、
その前の独立messageはexact head、targeted 20/20、clean external clone、empty
`git status`、改変code sentinel実行、runtime receipt `PASS`を具体的に報告した。

Schema v3はaudit modeをsafe-path `-P`、bytecode write disabled `-B`、専用の空
mode-`0700` bytecode-cache prefixに限定する。8 project modulesすべてについてexact
`SourceFileLoader`、expected clean-HEAD origin、prefix内のcache path、cache file不在を
frozen input path解決前に確認する。Regression testは実際に改変timestamp `.pyc`を
loadしてsentinelを確認した後、そのruntimeをfail closedする。

このbindingはordinary source-file imports、静的に存在するbytecode-cache substitution、
clean-HEAD file bytesまでである。Hostile interpreter/import hook、first attestation前の
concurrent cache deletion、in-memory code mutation、kernel compromiseをattestしない。
Schema v3のnormal/lowercase fresh replayもv2と`reductions`、
`posthoc_revalidation`、`input_provenance`、handoff decisionがexactly equalだった。

## Provenance and validation

- frozen design revision:
  `997345a6b466d9bc824672921cd2e6bd2dc43668`
- audit source revision:
  `a14f0ffeacf87a37bebc51633f9483b2b06c474b`
- audit module SHA-256:
  `1406ad7e0eb94331ac3142038d9e509fde9aae0a3f5644b30ad9b25a9604f8dd`
- frozen design SHA-256:
  `9c92292769b0395c7c818fe4032713b4018ecd319ba4b9d583d98e557c4a5509`
- receipt deterministic digest:
  `8efff0561f1ba65bc45580573ba422371bfaefe285269434ca785bebc83fc252`
- receipt raw SHA-256:
  `8414267365ef8b172bb6ebef6a9886a60560058079ae93d16f3d0c6c3e67afc0`
- receipt byte count: 2,003,163
- existing post-hoc frozen reductions and supplemental validation freshly
  recomputed exactly: `PASS`
- normal `/Users/...` inputs and lowercase `/users/...` aliases produced
  byte-identical receipts: `PASS`
- focused old/new audit tests: 40/40 `PASS`
- full repository validation: 601 tests, artifact verification, and every CLI
  self-test `PASS`

Canonical receipt:
[`selection_margin_v1.json`](../results/countdown_thompson_diagnostic_v1/selection_margin_v1.json)

External byte-identical copy:
`/Users/ryohiga/Documents/Codex/2026-07-17/3-qmc-thompson-sampling-qmc-token/countdown_thompson_diagnostic_v1.selection_margin.json`

## Next handoff

このfixed diagnosticから追加のscaleを選んで同じ12 tasksをretryしてはいけない。
次へ進む場合は、別のsource-disjoint development cohortを先にfreezeし、候補集合と
compute budgetを固定した上で、一つのmechanism factorだけを変える。

最初の候補はdense terminal-value scaleのdose-responseである。Selection turnoverを
mechanism endpoint、exact successをseparately reported outcomeとし、scale levelsは
新cohortを開く前に固定する。Trajectory budget、candidate refresh、credit ruleを同時
に変えない。そのdevelopment evidenceがheld-outで再現しない限り、locked-128は
開かない。
