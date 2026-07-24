# Countdown matched Thompson source observation, n=128

## Bottom line

Randomized Sobolは、狙い通りrootのperturbation coverageを均し、8 simulationで
訪れるroot arm、root entropy、unique edgeを増やした。したがってQMCの機構自体は
明確にactiveだった。

しかしexact successへの変換は改善しなかった。2つのdevelopment taskを等重みした
success差 `(QMC - IID)` は、Anthropic snapshotで`-1.17pp`、GPT-5.6 snapshotで
`-1.95pp`だった。特に`(1,1,1,1,1,2) -> 10`では、matched IIDに残った4件 / 5件の
成功がQMCでは両providerとも0件になった。

したがってこのcellでは、QMC action perturbationをwinnerとしてpromoteしない。
次のengineering targetはQMC自体の追加装飾ではなく、`0.1 * p_LM`に対して
unit-scale noiseを加えているprior/noise calibrationと、terminal-only feedbackが
遅すぎる問題である。

これは2つの固定development taskに対する128 sampler seedsの条件付き観察であり、
task generalization、provider superiority、一般的なQMC superiorityを示さない。

## Fixed comparison

Historical `iid_thompson_8`はglobal SHA-counter Box--Muller streamなので対照に使わず、
次の新しいmatched pairを比較した。

- `matched_iid_thompson_8`
- `qmc_thompson_8`

両条件はnode-localの同一`8 x 14` perturbation bank、同じclipped inverse-CDF、
canonical action coordinates、8 simulations、exact terminal reward、reverse update、
proposal snapshot、budgetを共有する。選択されるuniform sourceだけがIID / scrambled
Sobolで異なる。

Seedsはfreshな`1024..1151`。全workloadは、

```text
2 provider snapshots x 2 tasks x 2 sources x 128 seeds = 1,024 records
```

各runは40 transitions、8 verifier calls、40 posterior updates、sourceごとに40 full
points / 560 coordinatesで閉じた。元provider artifactはscratch copy上で検証し、
source bytesは変更していない。credentialをunsetし、socket network guard下で実行した。
provider callsとprovider costは0。

## Exact outcome

| Snapshot | Task | Matched IID | QMC | Delta |
|---|---|---:|---:|---:|
| Anthropic | `(1,1,1,1,1,1) -> 6` | 12/128 (9.38%) | 13/128 (10.16%) | +0.78pp |
| Anthropic | `(1,1,1,1,1,2) -> 10` | 4/128 (3.12%) | 0/128 (0%) | -3.12pp |
| GPT-5.6 | `(1,1,1,1,1,1) -> 6` | 15/128 (11.72%) | 15/128 (11.72%) | 0pp |
| GPT-5.6 | `(1,1,1,1,1,2) -> 10` | 5/128 (3.91%) | 0/128 (0%) | -3.91pp |

Equal-task macro:

| Snapshot | Matched IID | QMC | Delta | Success-AUC delta |
|---|---:|---:|---:|---:|
| Anthropic | 6.25% | 5.08% | -1.17pp | -1.03pp |
| GPT-5.6 | 7.81% | 5.86% | -1.95pp | -1.27pp |

`->6`の平均successだけを見るとほぼ同等だが、seed identityは安定していない。
Anthropicではboth-successが0、IID-only 12、QMC-only 13。GPTでもboth-success 1、
IID-only 14、QMC-only 14だった。同じ成功率でも、sourceを変えると成功するseedが
大きく入れ替わる。8 simulationでのrun-to-run reliabilityが高いとは言えない。

またexact-terminal countは全4 cellsでQMCの方が低かった。QMCは成功seedを増やす
だけでなく、一度得たpositive pathを残りsimulationで再利用できるかという面でも
優位を示さなかった。

## Manipulation check: coverage works

Rootの各active coordinateは必ず8点を受け取るため、ここが最もcleanなQMC機構確認に
なる。

| Task | IID mean root D* | Sobol mean root D* | Delta | Sobol lower |
|---|---:|---:|---:|---:|
| `->6` | 0.28759 | 0.11636 | -0.17123 | 128/128 seeds |
| `->10` | 0.28440 | 0.11746 | -0.16694 | 128/128 seeds |

Sobolはmean coordinate discrepancyを約59%下げた。

探索挙動も同方向だった。

- `->6`: root unique arms `+0.078`、root entropy `+0.056..+0.059`
- `->10`: root unique arms `+0.766..+0.773`、root entropy
  `+0.077`前後
- unique edges: 全cellでrunあたり`+2.16..+2.55`
- shared `(state, node visit)`のIID/Sobol vector digest mismatch: 0

つまり「Sobolが何も変えなかった」のではない。低discrepancy化が実際に探索breadthへ
変換されたが、そのbreadthがexact rewardへ変換されなかった。

## Proposal preservation and sparse feedback

QMCが単純にproposalを壊した、という読みも強すぎる。

全depth平均のproposal top-set retention差は全4 cellsでわずかに正
(`+0.2..+1.1pp`)で、normalized proposal rankもほぼ同等だった。Root top-set visit
fractionはcellにより`-1.46pp..+0.29pp`で、大きな一方向差ではない。

一方、両samplerともnoiseは非常に強い。

| Snapshot / Task | IID proposal-top override | QMC proposal-top override |
|---|---:|---:|
| Anthropic `->6` | 27.7% | 27.3% |
| Anthropic `->10` | 78.9% | 78.1% |
| GPT-5.6 `->6` | 67.3% | 66.2% |
| GPT-5.6 `->10` | 69.0% | 68.8% |

同じposterior stateでIID / Sobolを差し替えたlocal choice disagreementも
約71%から80%。source factorは十分に強く、proposalの微調整ではなくtrajectoryを
大きく変えている。

現行scoreは、

```text
mean_a + 0.1 * p_LM(a|s) + z_a / sqrt(visits_a + 1)
```

GPT `->6` rootでも最強 / 最弱actionのprior-component gapは約`0.099986`にすぎず、
初期noise SD 1.0の約1/10。positive terminalが出る前は全backupが0なので、この
calibrationではproposalよりnoise sourceがtrajectoryを支配しやすい。

`->10`ではQMC 256 runs（2 snapshots x 128 seeds）にpositive terminalが一度もなく、
posterior meanによる再集中フェーズへ入れなかった。Coverage改善だけでは
terminal-only sparse feedbackを越えられなかった、と読むのが最も安全である。

## Engineering decision

1. `qmc_thompson_8`をcurrent winnerとしてpromoteしない。
2. QMCをsemantic routingやpruningで複雑化する前に、同じ凍結snapshot上で
   prior/noise calibrationを切り分ける。
3. 次のdiagnosticは別experimentとして事前固定する。
   - prior bonus: `{0.1, 0.5, 1.0}`
   - posterior SD scale: `{0.25, 0.5, 1.0}`
   - IID / QMC source pairを各cellで維持
   - fresh seedsを使い、`->10`のpositive-feedback entry、proposal retention、
     success AUC、root breadthを同時に見る
4. dev gridから選ぶ場合も「QMCが勝つcell」ではなく、両source・両snapshotで
   proposal guidanceを保ち、terminal feedbackへ入れる安定領域を選ぶ。
5. 設定をfreezeしてから、未使用のheld-out Countdown task suiteで評価する。

## Artifact and replay

Scratch artifact:

```text
artifacts/work/countdown_thompson_source_n128_v2
```

- summary deterministic digest:
  `8e037efcba2cead9c78463ce6f026b517dd4a8c1a194958ad1b8060e4fb749d0`
- manifest deterministic digest:
  `2f303018e67202824516a7fd84b32dc64492c6167ed6428f29283b23d610cb11`
- perturbation bank SHA-256:
  `2a30a8c90c3538cd378a860c02a9e544e8912fafbef81fadea0107e9591166ed`
- search records SHA-256:
  `4947f8d7f5e6fd131718680d1c92f767efc5dddac882a7094ff20ba107d160fe`
- seed-map digest:
  `a5523f22fa79adea67704b463a1397fb702e70165c38a057e1dce4294c65f5b1`
- uint32 seed collisions: 0 / 16,384 identities

Credential-free, network-denied replay:

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_source_ablation \
  --replay artifacts/work/countdown_thompson_source_n128_v2
```

Copied proposal bytes、bank/state/seed identities、exact terminal traces、compute
closure、paired vector digests、summary recomputation、search JSONL bytesの全検証がPASSした。
