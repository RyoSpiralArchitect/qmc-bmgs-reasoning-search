# Countdown Thompson dense terminal-value scale v5: development observation

Date: 2026-09-04

## Bottom line

事前固定した12 development tasks、8 scales、4 exploration seedsの384セルを、
認可済みの一回だけ実行した。全セルがcommitされ、別processのanalyzerが全384
recordsをempty stateから再構成してtwo-stage byte-identical replayを閉じた。
Integrityは`PASS`である。

選ばれたscaleは`s*=16`だった。Exact successはscale 0の`2/48`から
`3/48`へ増え、lost successは0だった。しかし事前条件はnet `+2`以上かつ
new success 2件以上であり、実測はいずれも`1`だった。したがって固定ルールの
判定は`STOP_REPAIR_NO_LOCKED_128_RUN`である。Confirmation cohortもlocked 128も
開かない。

これは単なる「何も変わらなかった」結果ではない。Feedback-informedな最初の
action divergenceはscaleとともに`0,1,2,4,7,15,18,22 / 48`へ増えた。
scale 16以上では同じ1 cellがnew exact successとなった。一方、48-cell latticeで
handoff閾値へ届くほど広いexact gainには変換されなかった。最も近い解釈は、
terminal feedbackの強さはこの固定cohortの探索trajectoryを段階的に変えたが、
現budgetでのexact rescueは局所的な1件に留まった、である。

## Frozen dose response

`min-error W/T/L`は、各positive scaleのcellwise minimum terminal absolute
errorを同じtask/seedのscale 0と比較したexact countである。Meanとmedianは
48 cellsを等重みで集計したreduced rationalである。

| scale | exact success | new / lost / net | min-error W/T/L | mean min error | median min error | feedback-informed first divergences |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 2/48 | 0 / 0 / 0 | 0 / 48 / 0 | 3961/24 | 147/2 | 0 |
| 1 | 2/48 | 0 / 0 / 0 | 0 / 48 / 0 | 3961/24 | 147/2 | 1 |
| 2 | 2/48 | 0 / 0 / 0 | 0 / 48 / 0 | 3961/24 | 147/2 | 2 |
| 4 | 2/48 | 0 / 0 / 0 | 0 / 48 / 0 | 3961/24 | 147/2 | 4 |
| 8 | 2/48 | 0 / 0 / 0 | 1 / 47 / 0 | 7921/48 | 147/2 | 7 |
| **16** | **3/48** | **1 / 0 / +1** | **4 / 43 / 1** | **1291/8** | **46** | **15** |
| 32 | 3/48 | 1 / 0 / +1 | 4 / 43 / 1 | 2579/16 | 46 | 18 |
| 64 | 3/48 | 1 / 0 / +1 | 5 / 41 / 2 | 7571/48 | 73/2 | 22 |

Scale 16、32、64はexact-success countが同じため、事前固定したlower-scale
tiebreakにより16が選ばれた。Scale 64はminimum-errorのwinsもlossesも最多で、
より強いfeedbackが全cellを一様に改善したとは読めない。

## The one exact rescue

New successはtask fingerprint
`a4eb31a5ad2b144a738124ec719a2d30331658b19d0eb6996c007fa2c80710b5`、
seed `7168`の1 cellだった。

- scales 0–8: terminal errors `[90,5484,1984,115]`、exact hitなし;
- scales 16–64: terminal errors `[90,5484,1984,0]`、trajectory 3でfirst hit;
- scale 16対0の共通prefixでは、trajectory 0–2の三つのterminal backupが
  scaled valueを変えた;
- 最初のaction divergenceはtrajectory 3、depth 0、state
  `[4,4,5,5,10,10]`;
- scale 0は`5+10`、scale 16は`4*4`を選んだ。

これは固定task/seedで、scale介入後のfeedback、score、action、最終outcomeが
整合する一つのdeterministic trajectoryである。ただし分岐後の未観測continuation
を合成しておらず、1 cellを一般的な成功因果や次cohortの予測へ外挿しない。

## Handoff rule

| Gate | Result |
|---|---|
| all integrity and replay gates pass | PASS |
| selected scale has at least two more exact successes than scale 0 | FAIL: +1 |
| at least two scale-0 failures become exact successes | FAIL: 1 |
| each new success diverges after scale-dependent feedback | PASS for the one observed new success |

The conjunction fails, so the only authorized terminal decision is
`STOP_REPAIR_NO_LOCKED_128_RUN`.

## Provenance and retained evidence

- implementation PR #22 merge:
  `b2f30edde6170eba3e08b41d0fc4e30bb6721457`;
- authorization-only PR #23 merge:
  `f13e3a5d08333f94e44eeeb921e2dfe253cc72e8`;
- authorization digest:
  `0b22bc1838eec287b85a9e66a54bb0092209bde2ee0f149d1c6d37f2f411ee6a`;
- run: `COMMITTED`, 384 cells, 142.24 seconds, authorization consumed,
  retry prohibited;
- independent analysis: 336.06 seconds, integrity `PASS`;
- summary deterministic digest:
  `b7886df480ad0047d781673119b24482711a89ff46929066152a1c9c18d7e1e7`;
- summary file SHA-256:
  `76e181de21f7efbd4eb826f5dff181d7e13a1daf5c0da2e926b76f305b2fc651`;
- pre-execution repository validation: 728 tests in 401.686 seconds, all CLI
  self-tests, artifact verifier and sealed-manifest verifier passed;
- GitHub CI: not configured for PR #23;
- provider calls: zero; no Anthropic/OpenAI key, network model, or furnace
  workload was used.

The 42,248,633-byte raw JSONL and all lifecycle sidecars remain immutable
outside Git. The tracked canonical summary is byte-identical to the independently
published summary. [Evidence inventory](../results/countdown_thompson_dense_scale_v5/evidence.json)
records hashes for every retained raw file.

## Claim boundary

This result describes the causal trajectory response of the exact frozen scale
intervention on one source-disjoint development cohort under matched IID
streams and budgets. It does not establish general method superiority, task
transfer, statistical significance, QMC benefit, Bayesian posterior validity,
natural-language generalization, confirmation, or locked-cohort performance.

Integrity `PASS` proves authority, provenance, exact schedule, budget and
replay closure only. The local mechanistic response and one exact rescue are
interesting development evidence, but the preregistered threshold controls the
handoff: stop and repair before any further outcome-bearing cohort.
