# QMC-BMGS D4 Primary precision extension

## 結論

PrimaryではIID優位を支持し、Sobol優位は否定された。
事前固定した SD scale=1, LM cap=384 のreadout成功率は、IID 40.2% (103/256), Sobol 30.1% (77/256)。
paired delta (Sobol - IID) は -10.2%, nominal 95% bootstrap CI [-18.8%, -1.6%], exact McNemar p=0.02674。

これはoracle-aligned static-token embeddingを使ったRole-Lock D4上の条件付き結果であり、自然言語reasoningや一般的なQMC優位の証明ではない。

## 実験契約

- Task: `PROBE -> DERIVE -> COMMIT -> EOS`（terminal-only reward +5）
- Fixed: aligned embedding strata、候補10、LM prior、reward、pruning off
- Factor: IID / node-local `scramble=True` Sobol（coverage gate、cluster quantile、action perturbationをまとめて置換）
- Posterior SD scales: 1
- LM caps: 384
- Independent paired randomization replicates: 256
- Total runs: 512

SD scaleはlearned meanを変えず、uncertainty proxyの標準偏差だけを倍率変更する。このproxyは非定常TD targetに対する探索量で、厳密なBayesian posteriorではない。

## Precision-extension provenance

初期n=64で事前precision ruleを満たさなかったため、Primaryセルだけn=256へ延長した。これは効果方向ではなくCI幅で発火したsequential extension。
nominalな最終p値/CIはanytime-validではない。ただし初期64-replicate PrimaryでもIID方向は既に有意で、延長は効果量精度を上げるために行った。

| Actual checkpoint n | IID success | Sobol success | Delta | Nominal 95% CI | McNemar p |
|---:|---:|---:|---:|---:|---:|
| 64 | 29 | 12 | -26.6% | [-42.2%, -10.9%] | 0.004551 |
| 128 | 57 | 31 | -20.3% | [-33.6%, -7.0%] | 0.003836 |
| 256 | 103 | 77 | -10.2% | [-18.8%, -2.0%] | 0.02674 |

このcheckpoint表は実際のseed追加順。後段のstability表はdiagnostic seedで固定shuffleしたnested subsetで、別の診断である。

## 全successセル

| SD scale | LM cap | IID | Sobol | Delta | Paired 95% CI | Holm p (all 1) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 384 | 40.2% | 30.1% | -10.2% | [-18.8%, -1.6%] | 0.02674 |

この表は事前Primaryの1セルだけで、多重なsensitivity検定ではない。

## Scramble replicate数の安定性（最大LM cap）

| SD scale | n | Nested delta | Nested 95% CI | Subset median abs error | Sign disagreement (tie含む) | Adequate? |
|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 8 | -12.5% | [-37.5%, 0.0%] | 14.8% | 42.1% | no |
| 1 | 16 | -12.5% | [-43.8%, 18.8%] | 10.2% | 36.9% | no |
| 1 | 32 | -15.6% | [-37.5%, 6.2%] | 7.0% | 22.2% | no |
| 1 | 64 | -7.8% | [-23.4%, 7.8%] | 5.5% | 12.3% | no |
| 1 | 128 | -13.3% | [-25.0%, -1.6%] | 3.1% | 1.4% | no |
| 1 | 256 | -10.2% | [-18.8%, -1.6%] | 0.0% | 0.0% | yes |

`Adequate`は、nested paired-delta CI half-width <=10pp かつrandom-subset median absolute error <=5pp、かつdiscordant pairを1件以上観測、という事前engineering rule。n=256で事前engineering precision ruleを満たした。

Success-budget AUC spreadは省略した。LM capが1点だけの場合、AUCはbinary successの定数倍にすぎず、独立な分散指標にならない。

## Computeとデータ品質

Primaryの平均cost delta (Sobol - IID): verifier -137.73, edge selections -503.23, full-prefix tokens -0.12。LM node capが同じでも、これらの二次費用は同一とは限らない。

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

## Claim boundary / 次の判断

- Primary CIが0を跨ぐなら、IIDとSobolが同等とは言わず未確定とする。
- Primaryのn=256は事前precision ruleを満たした。このendpointのscramble追加は不要。
- ここで良い結果が出ても、static token embeddingがreasoning roleを捉えるとは限らない。contextual/chunk action embeddingは次の独立段階。
- QMCの効果とsemantic strataの効果は混ぜない。後者のpositive controlはD3で扱い済みで、このD4はaligned strataに条件付けている。
- sampler差はnode-local uniform engine全体の置換であり、posterior perturbation単独のQMC効果ではない。
