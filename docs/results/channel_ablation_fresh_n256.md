# Fresh-cohort uniform-channel ablation

## Status

Role-Lock D4、fresh paired seed 256–511、n=256、LM-node cap 384の固定full run。
SD 1.0がprimary、過去結果から選ばれたSD 0.5はengineering sensitivity。
raw 2,048 records / 512 paired groupsはdata-qualityとdisk再生成検査をPASSした。

Canonical evidence:
[promoted report](../../artifacts/role_lock/d4/20260717_channel_ablation_fresh_n256/report.md)

## Primary result: SD 1.0

| Profile | Readout success | Mean verifier | Mean edges | Root coverage deviation |
|---|---:|---:|---:|---:|
| `iid_all` | 35.5% (91/256) | 782.6 | 2851.8 | 0.025 |
| `sobol_all` | 37.5% (96/256) | 666.2 | 2428.2 | 0.002 |
| `sobol_routing_only` | 39.1% (100/256) | 695.9 | 2539.9 | 0.002 |
| `sobol_action_only` | 36.7% (94/256) | 738.2 | 2690.7 | 0.026 |

成功率のfactorial simultaneous intervalはすべて0を跨いだ。

- routing Sobol main effect: +2.1pp、95% simultaneous CI [-7.6, +11.9]pp
- action Sobol main effect: -0.2pp、95% simultaneous CI [-10.0, +9.6]pp
- interaction: -2.7pp、95% simultaneous CI [-12.5, +7.0]pp

したがって「routingが成功率を上げる」「action QMCが無効」とはまだ確定しない。
一方、sample meanでは`sobol_all`と`sobol_routing_only`がPareto frontに残り、
`iid_all`と`sobol_action_only`は両者に支配された。

## Engineering signal

`sobol_all`対`iid_all`では、成功率point estimateが+2.0ppのまま、verifierを
116.4回（14.9%）、edgeを423.6回（14.9%）削減した。paired bootstrap 95%は、
verifier [-142.7, -90.3]、edge [-521.3, -327.9]で、ともに0より下だった。

`sobol_routing_only`対`iid_all`も、成功率point estimate +3.5pp、verifier -86.7、
edge -312.0。成功差CIは0を跨ぐが、work削減CIは0より下だった。

全profileが同じ384 LM nodeとほぼ同じfull-prefix token workへ到達している。
差は浅いprefixで止めたことではなく、同じnode獲得までのsimulation・再訪回数が
減ったことから生じる。root coverage deviationもSobol routingでIID routingの約1/11。
QMC routingはこのtoy上で、成功boostより先に「探索workを規則化する機構」として
明確に動いている。

## SD 0.5 sensitivity

SD 0.5では`sobol_all`はIIDに対して成功率-3.1pp
（paired 95% CI [-10.5, +4.3]pp）だが、verifierを30.5%、edgeを29.6%削減した。
`sobol_routing_only`は`sobol_all`に支配された。成功とworkのtrade-offは
uncertainty scaleに依存しており、単一profileを普遍的winnerとは呼べない。

それでも`sobol_all`は両scaleでsample-mean Pareto frontに残り、常に最小workだった。
現時点で次に試すengineering candidateは`sobol_all`、primary-scaleの高成功候補は
`sobol_routing_only`。

## Decision

以前のdiscovery cohortで見えたcombined Sobolの大きな負方向は、fresh cohortでは
再現せず+2.0ppへ反転した。QMCの成功率優位・劣位はいずれも安定した結論ではない。
ただしwork削減は大きく一貫しているため、contextual/chunk actionへ進む前に、
固定した高価なresourceから有用な探索へ変換できるかを直接測る。

次の最小実験:

- D4 aligned strata、pruning off、SD 1.0
- `iid_all` / `sobol_all` / `sobol_routing_only`
- fresh paired seed 512–639、n=128
- hard verifier cap 700
- LM ceiling 1111はsaturation guard、edge cap 3500はsafety guard
- primary: verifier 700回時点のreadout success
- secondary: 獲得LM nodes、full-prefix tokens、edges、first-success verifier index
- 全runがverifier capで停止しなければbudget contract failure

Role-Lockではedgeとverifierがほぼ同じ費用軸なので、edge/verifierの二重sweepはしない。
この次段でSobolが固定verifier予算を追加node・成功へ変換できた場合に、初めて
contextual/chunk actionと実LLM verifierへ接続する。

## Claim boundary

これはoracle-aligned static-token embeddingを使うtoy taskの結果であり、自然言語
reasoningや一般的QMC理論へは一般化しない。success superiorityは未確定で、wall timeは
dual-source instrumentationを含むためdeployment sampler costでもない。
