# QMC-BMGS D4 result capsule

## Bottom line

Role-Lock D4のoracle-aligned embedding条件では、node-local uniform engine全体を
IIDからscrambled Sobolへ置き換える優位性は出なかった。事前Primary
（posterior SD scale 1.0、LM node cap 384）では、初期64 paired replicatesで
IID 29/64、Sobol 12/64、delta (Sobol - IID) -26.6pp、95% bootstrap CI
[-42.2, -9.4]pp、exact McNemar p=0.00455だった。

初期CIが事前precision ruleを満たさなかったため、Primaryだけ256 paired
replicatesへ延長した。最終値はIID 103/256 (40.2%)、Sobol 77/256 (30.1%)、
delta -10.2pp、nominal 95% bootstrap CI [-18.8, -1.6]pp、exact McNemar
p=0.0267。CI half-widthは8.6ppとなり、事前の10pp precision ruleを満たした。
延長はCI幅で発火したsequential designなので、最終p/CIはanytime-validではない。
ただし初期64の事前PrimaryでもIID方向は既に有意だった。

## Posterior-noise sensitivity at 64 paired replicates

最大cap 384でのreadout successは次の通り。

| Posterior SD scale | IID | Sobol | Delta (S-I) | Paired 95% CI |
|---:|---:|---:|---:|---:|
| 0.5 | 76.6% | 64.1% | -12.5pp | [-26.6, +1.6]pp |
| 1.0 | 45.3% | 18.8% | -26.6pp | [-42.2, -9.4]pp |
| 2.0 | 26.6% | 12.5% | -14.1pp | [-28.1, 0.0]pp |

したがって、このprototypeではsampler差よりposterior-noise設定の絶対性能への影響が
大きい。SD 0.5が両samplerで最も良く、現在のbase noiseは探索過多の可能性がある。

## What Sobol did accomplish

最終Primary n=256では、root coverageのuniform分布からの最大偏差はIID 0.0261、
Sobol 0.00242で、Sobolは約10.8倍均一だった。同じ384 logical LM node capに対し、
Sobolは平均でverifier requestを137.7件、edge selectionを503.2件少なく使い、
full-prefix token workはほぼ同じだった。

つまりlow-discrepancy化は配管上きちんと働き、unique prefixをより少ないtrajectory
workで覆った。ただし、その規則的なcoverageはterminal sequenceのreadout successを
改善しなかった。これは「QMCが均等化できなかった」という失敗ではなく、
「このadaptive policyでは均等化と目的成功が一致しなかった」という負の結果。

64-seedのsuccess-budget AUCでも、default noiseはIID 0.152、Sobol 0.073、
paired delta CIは0未満だった。一方、AUC variance-ratio CIは全noise条件で1を跨ぎ、
Sobolのrun間spread低下は支持されなかった。

## Claim boundary

- 結果はoracle-aligned static-token embeddingを使うRole-Lock D4に条件付く。
- Sobol/IID差はcoverage gate、cluster quantile、action posterior perturbationを含む
  uniform engine全体の差で、posterior perturbation単独のQMC効果ではない。
- uncertaintyは非定常TD target用のproxyで、厳密なBayesian posteriorではない。
- 自然言語reasoning、chunk action、contextual embedding、一般的QMC理論へは一般化しない。
- 内部数値・予算・serializationへの信頼度は高い。外的妥当性はまだ低い。

## Next experiment

contextual/chunk embeddingへ進む前に、QMCの作用点を分離する。

1. `iid_all`: gate / cluster / action perturbationをすべてIID。
2. `sobol_all`: 現在のcombined Sobol条件。
3. `sobol_routing_only`: gateとcluster quantileだけSobol、action perturbationはIID。
4. `sobol_action_only`: gateとcluster quantileはIID、action perturbationだけSobol。

同じcandidate、aligned strata、pruning off、SD 0.5と1.0、D4、paired seedで比較する。
Primaryはreadout success at fixed LM-node capのままにしつつ、fixed edge/verifier budgetも
副budgetとして追加する。`sobol_action_only`がneutral/positiveで
`sobol_routing_only`がnegativeなら、現在の損失はsemantic routingの過度な均等化に
局在できる。その確認後にcontextual/chunk action embeddingへ進む。
