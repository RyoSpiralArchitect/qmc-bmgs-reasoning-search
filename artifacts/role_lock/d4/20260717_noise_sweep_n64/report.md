# QMC-BMGS D4 posterior-noise sweep

## 結論

PrimaryではIID優位を支持し、Sobol優位は否定された。
事前固定した SD scale=1, LM cap=384 のreadout成功率は、IID 45.3% (29/64), Sobol 18.8% (12/64)。
paired delta (Sobol - IID) は -26.6%, 95% bootstrap CI [-42.2%, -9.4%], exact McNemar p=0.004551。

これはoracle-aligned static-token embeddingを使ったRole-Lock D4上の条件付き結果であり、自然言語reasoningや一般的なQMC優位の証明ではない。

## 実験契約

- Task: `PROBE -> DERIVE -> COMMIT -> EOS`（terminal-only reward +5）
- Fixed: aligned embedding strata、候補10、LM prior、reward、pruning off
- Factor: IID / node-local `scramble=True` Sobol（coverage gate、cluster quantile、action perturbationをまとめて置換）
- Posterior SD scales: 0.5, 1, 2
- LM caps: 64, 128, 256, 384
- Independent paired randomization replicates: 64
- Total runs: 1536

SD scaleはlearned meanを変えず、uncertainty proxyの標準偏差だけを倍率変更する。このproxyは非定常TD targetに対する探索量で、厳密なBayesian posteriorではない。

## 全successセル

| SD scale | LM cap | IID | Sobol | Delta | Paired 95% CI | Holm p (all 12) |
|---:|---:|---:|---:|---:|---:|---:|
| 0.5 | 64 | 1.6% | 1.6% | 0.0% | [-4.7%, 4.7%] | 1 |
| 0.5 | 128 | 4.7% | 7.8% | 3.1% | [-4.7%, 12.5%] | 1 |
| 0.5 | 256 | 28.1% | 23.4% | -4.7% | [-17.2%, 7.8%] | 1 |
| 0.5 | 384 | 76.6% | 64.1% | -12.5% | [-26.6%, 1.6%] | 1 |
| 1 | 64 | 1.6% | 1.6% | 0.0% | [-4.7%, 4.7%] | 1 |
| 1 | 128 | 4.7% | 3.1% | -1.6% | [-7.8%, 4.7%] | 1 |
| 1 | 256 | 18.8% | 9.4% | -9.4% | [-21.9%, 3.1%] | 1 |
| 1 | 384 | 45.3% | 18.8% | -26.6% | [-42.2%, -9.4%] | 0.05462 |
| 2 | 64 | 1.6% | 0.0% | -1.6% | [-4.7%, 0.0%] | 1 |
| 2 | 128 | 3.1% | 1.6% | -1.6% | [-7.8%, 3.1%] | 1 |
| 2 | 256 | 9.4% | 6.2% | -3.1% | [-12.5%, 6.2%] | 1 |
| 2 | 384 | 26.6% | 12.5% | -14.1% | [-28.1%, 0.0%] | 1 |

低budgetセルは同じseedのnested sensitivityで、独立した12実験ではない。表のHolm値は探索的な多重比較を保守的に可視化するためのもの。

## Scramble replicate数の安定性（最大LM cap）

| SD scale | n | Nested delta | Nested 95% CI | Subset median abs error | Sign disagreement (tie含む) | Adequate? |
|---:|---:|---:|---:|---:|---:|:---:|
| 0.5 | 8 | 25.0% | [-25.0%, 75.0%] | 12.5% | 37.8% | no |
| 0.5 | 16 | 0.0% | [-31.2%, 31.2%] | 6.2% | 24.9% | no |
| 0.5 | 32 | -9.4% | [-31.2%, 12.5%] | 6.2% | 7.2% | no |
| 0.5 | 64 | -12.5% | [-26.6%, 1.6%] | 0.0% | 0.0% | no |
| 1 | 8 | 0.0% | [-50.0%, 50.0%] | 14.1% | 19.1% | no |
| 1 | 16 | -18.8% | [-56.2%, 18.8%] | 10.9% | 5.9% | no |
| 1 | 32 | -21.9% | [-46.9%, 3.1%] | 4.7% | 0.1% | no |
| 1 | 64 | -26.6% | [-42.2%, -9.4%] | 0.0% | 0.0% | no |
| 2 | 8 | -12.5% | [-50.0%, 25.0%] | 14.1% | 35.4% | no |
| 2 | 16 | 0.0% | [-31.2%, 31.2%] | 7.8% | 18.1% | no |
| 2 | 32 | -15.6% | [-34.4%, 3.1%] | 4.7% | 4.7% | no |
| 2 | 64 | -14.1% | [-28.1%, 0.0%] | 0.0% | 0.0% | no |

`Adequate`は、nested paired-delta CI half-width <=10pp かつrandom-subset median absolute error <=5pp、かつdiscordant pairを1件以上観測、という事前engineering rule。n=64でも満たさない場合は「差なし」ではなくscramble不足と読む。

## Success-budget AUCの平均とrun間spread

| SD scale | IID mean AUC | Sobol mean AUC | Delta (95% CI) | Variance ratio S/I | log-ratio 95% CI | Joint candidate? |
|---:|---:|---:|---:|---:|---:|:---:|
| 0.5 | 0.236 | 0.207 | -0.029 ([-0.100, +0.042]) | 1.181 | [-0.433, +0.721] | no |
| 1 | 0.152 | 0.073 | -0.079 ([-0.155, -0.004]) | 0.696 | [-1.685, +0.533] | no |
| 2 | 0.086 | 0.046 | -0.040 ([-0.102, +0.020]) | 0.577 | [-2.220, +0.742] | no |

binary successのSDはp(1-p)に従うため、分散低下の根拠には使っていない。AUCのspreadも一般的RQMC定理ではなく、このadaptive search上の経験的run-to-run stabilityである。`Joint candidate`はlog variance-ratio CIが0未満かつAUC mean-delta CIが0以上のときだけ立てる探索的フラグで、分散検定による支持判定ではない。readout curveの非単調seed数もJSONへ保存した。

## Computeとデータ品質

Primaryの平均cost delta (Sobol - IID): verifier -156.69, edge selections -573.67, full-prefix tokens -0.14。LM node capが同じでも、これらの二次費用は同一とは限らない。

Validation: **PASS**

- PASS: `expected_record_count`
- PASS: `complete_factorial`
- PASS: `unique_composite_keys`
- PASS: `deterministic_digests`
- PASS: `strict_success_encoding`
- PASS: `exact_lm_caps_and_zero_overshoot`
- PASS: `no_verifier_or_edge_guard_stops`
- PASS: `pruning_disabled`
- PASS: `noise_and_seed_config_propagated`
- PASS: `candidate_universe_complete`
- PASS: `root_candidate_manifest_identical`
- PASS: `fresh_budget_observation_consistency`

## Claim boundary / 次の判断

- Primary CIが0を跨ぐなら、IIDとSobolが同等とは言わず未確定とする。
- Primaryのn=64は事前precision ruleを満たさない。差なしとは読まず、必要ならPrimaryセルだけ128/256へ延長する。
- ここで良い結果が出ても、static token embeddingがreasoning roleを捉えるとは限らない。contextual/chunk action embeddingは次の独立段階。
- QMCの効果とsemantic strataの効果は混ぜない。後者のpositive controlはD3で扱い済みで、このD4はaligned strataに条件付けている。
- sampler差はnode-local uniform engine全体の置換であり、posterior perturbation単独のQMC効果ではない。
