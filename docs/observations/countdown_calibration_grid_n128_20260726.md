# Countdown prior/noise calibration grid, n=128

## Bottom line

事前登録した9設定のうち、全gateを通ったのは
`(prior_bonus, posterior_sd_scale) = (0.5, 0.5)`と`(1.0, 1.0)`の2つだった。
preregistered ruleにより、後者をgate-passing development candidateとして
freezeする。

ただし、これはQMC winnerの選出ではない。凍結候補でも全cell合計は
IID `95/512`、QMC `78/512`で、GPT-5.6 snapshotの`->6`では
IID `74/128`に対してQMC `54/128`だった。確認できたのは、

- prior/noise校正によって両sourceがhard taskのterminal feedbackへ入ったこと;
- randomized Sobolがroot discrepancyを下げてbreadthを増やす機構;
- rawな2係数より比率
  `kappa = prior_bonus / posterior_sd_scale`が初回positive前の探索を支配すること;

である。held-out task transferとQMCによるreward conversionは未確認のまま。

## Frozen procedure

結果を見る前にcommit `bb681d22cb50e6509f9b8ddbcd44e03ee1703afa`へ、

- `prior_bonus = {0.1, 0.5, 1.0}`;
- `posterior_sd_scale = {0.25, 0.5, 1.0}`;
- fresh matched dual-stream seeds `2048..2175`;
- 両provider snapshot、両task、matched IID/QMC;
- validity、eligibility、preregistered selection rule;

を固定した。

全workloadは、

```text
9 configs x 2 providers x 2 tasks x 2 sources x 128 seeds
= 9,216 records
= 4,608 paired IID/QMC blocks
```

だった。全設定は同じ256個のdual-source perturbation bankを共有する。同一sourceの
乱数はconfig/provider間で再利用される。一方、IIDとSobolはsource固有の別streamで、
両者の比較はCRNではない。生成・replay中はcredentialをunsetし、socket accessを
拒否した。

## Decision result

| Config | Eligible | Terminal entry | QMC mechanism | Proposal guard |
|---|---|---|---|---|
| `prior=.1, sd=.25` | no | fail | pass | pass |
| `prior=.1, sd=.5` | no | fail | pass | pass |
| `prior=.1, sd=1` | no | fail | pass | pass |
| `prior=.5, sd=.25` | no | pass | fail | pass |
| `prior=.5, sd=.5` | yes | pass | pass | pass |
| `prior=.5, sd=1` | no | fail | pass | pass |
| `prior=1, sd=.25` | no | fail | fail | pass |
| `prior=1, sd=.5` | no | pass | fail | pass |
| `prior=1, sd=1` | **yes, selected** | pass | pass | pass |

両eligible configの最小cell成功数は`2/128`で、成功gateの余裕は1 seedしかない。
両者は8 cellすべてでexact-success countとsuccess AUCが一致し、最初の4つの
selection criteriaは同点だった。`(1,1)`は5番目のbreadth tie-break、
最悪cellのQMC-minus-IID root entropy差
`+0.05647`対`+0.05032`で選ばれた。terminal rewardで`(0.5,0.5)`を
上回ったわけではない。

## Selected configuration versus baseline

各cellは128 fresh seeds。baselineは従来式の`(prior=.1, sd=1)`。

| Snapshot | Task | Source | Selected `(1,1)` | Baseline `(.1,1)` | Delta |
|---|---:|---|---:|---:|---:|
| Anthropic | `->6` | IID | 17/128 (13.28%) | 14/128 (10.94%) | +2.34pp |
| Anthropic | `->6` | QMC | 16/128 (12.50%) | 10/128 (7.81%) | +4.69pp |
| Anthropic | `->10` | IID | 2/128 (1.56%) | 1/128 (0.78%) | +0.78pp |
| Anthropic | `->10` | QMC | 4/128 (3.13%) | 0/128 (0%) | +3.13pp |
| GPT-5.6 | `->6` | IID | 74/128 (57.81%) | 16/128 (12.50%) | +45.31pp |
| GPT-5.6 | `->6` | QMC | 54/128 (42.19%) | 13/128 (10.16%) | +32.03pp |
| GPT-5.6 | `->10` | IID | 2/128 (1.56%) | 1/128 (0.78%) | +0.78pp |
| GPT-5.6 | `->10` | QMC | 4/128 (3.13%) | 0/128 (0%) | +3.13pp |

記述的な全cell合計はselected `173/1024 = 16.89%`、baseline
`55/1024 = 5.37%`。これは同じdevelopment gridで設定を選んだin-sample値であり、
generalization estimateではない。

特に`->10`は両source・両snapshotでpositiveになったが、IID `2/128`、
QMC `4/128`にすぎない。「feedbackへ入った」とは言えるが、安定した解決率とは
まだ呼べない。

## Ratio controls entry; scale controls post-feedback

このgridで最も強いengineering observationは、rawな2係数より、

```text
kappa = prior_bonus / posterior_sd_scale
```

が初回positive前のtrajectoryを決めたことだった。

| kappa | Config | Exact success / 1,024 | Mean top retention | Mean root entropy | Mean unique edges |
|---:|---|---:|---:|---:|---:|
| 0.1 | `(.1, 1)` | 55 | .393 | .891 | 31.84 |
| 0.2 | `(.1, .5)` | 64 | .408 | .882 | 31.79 |
| 0.4 | `(.1, .25)` | 86 | .435 | .858 | 31.26 |
| 0.5 | `(.5, 1)` | 97 | .442 | .871 | 32.24 |
| 1 | `(.5, .5)` | 173 | .512 | .788 | 31.08 |
| 1 | `(1, 1)` | 173 | .506 | .804 | 31.95 |
| 2 | `(.5, .25)` | 281 | .632 | .641 | 26.71 |
| 2 | `(1, .5)` | 281 | .634 | .655 | 28.30 |
| 4 | `(1, .25)` | 369 | .802 | .509 | 21.01 |

同じkappaを持つ2組では、全1,024 matched runのexact-success labelと
first-success verifierが一致した。失敗runのtrajectory digestも全件一致した。
違いが生じたのはpositive terminalが観測された後だけである。

positive前は全posterior meanが0なので、priorとnoiseを同じ倍率で拡大しても
argmaxは変わらない。一方、positive後のreward mean `1`は同じ倍率で拡大されない。
したがって、

- `kappa`はproposal guidance対noiseの比、つまりsolution entryを制御する;
- 共通振幅`tau`はpositive後のreward meanの相対的な強さを制御する;

と再パラメータ化する方が、次の実験設計には自然である。

高いkappaはaggregate successとproposal retentionを増やしたが、breadthを狭めた。
最大の`kappa=4`は`369/1024`成功でも、Anthropic `9/512`対GPT
`360/512`とprovider snapshot依存が極端で、zero-success cellも残った。
これは「最も大きなaggregate値」を選ばなかった理由でもある。

## QMC mechanism versus reward conversion

Fresh bank上でもSobol root coordinate discrepancyは全256 task-seed bankでIIDより
低かった。

| Task | IID mean root D* | Sobol mean root D* | Delta |
|---|---:|---:|---:|
| `->6` | .28728 | .11698 | -.17030 |
| `->10` | .28326 | .11667 | -.16659 |

Selected configでは、QMC-minus-IIDが全provider/task cellで、

- root entropy: 最小`+0.05647`;
- unique edges: 最小`+2.13281`;

だった。coverage機構はactiveである。

しかしselected configの全cell合計はIID `95/512`、QMC `78/512`
(`-3.32pp`)。QMC success deltaは、

- Anthropic `->6`: `-0.78pp`;
- Anthropic `->10`: `+1.56pp`;
- GPT-5.6 `->6`: `-15.63pp`;
- GPT-5.6 `->10`: `+1.56pp`;

と混在した。breadthがterminal rewardへ一貫して変換されたとは言えない。

Post-hoc adversarial auditで再構成した記述的なQMC-minus-IID success intervalは、

| Snapshot | Task | Delta | Descriptive 95% interval |
|---|---:|---:|---:|
| Anthropic | `->6` | -0.78pp | -9.06 to +7.50pp |
| Anthropic | `->10` | +1.56pp | -2.19 to +5.32pp |
| GPT-5.6 | `->6` | -15.63pp | -27.42 to -3.83pp |
| GPT-5.6 | `->10` | +1.56pp | -2.19 to +5.32pp |

だった。これはfixed-task内のsampler intervalであり、task-transfer intervalや
multiplicity-corrected promotion testではない。

## Engineering decision

1. `(prior_bonus, posterior_sd_scale) = (1,1)`をgate-passing development
   candidateとして変更せず保存する。
2. これはQMC winnerではなく、両sourceがfeedbackへ入りQMC mechanismも保った
   development calibrationである。
3. selected-only held-outはcalibration transferを測れないため実行しない。candidate
   とfrozen baseline、IIDとSobol、simple search baselinesを新規preregisterする。
4. 次の診断ではraw 2軸を`kappa`と共通振幅`tau`へ再パラメータ化し、
   `pre_first_positive_trajectory_digest`、post-feedback exact-terminal reuse、
   successful-terminal diversityを記録する。
5. `(1,1)`からfirst positive後に`(.5,.5)`へ切り替える案は、固定`(.5,.5)`と
   behaviorally identicalなので実行しない。
6. semantic routingとBayesian pruningは、このentry/exploitation分離を確認するまで
   追加しない。

## Artifact and replay

Scratch artifact:

```text
artifacts/work/countdown_calibration_grid_n128_v1
```

- preregistration commit:
  `bb681d22cb50e6509f9b8ddbcd44e03ee1703afa`
- summary deterministic digest:
  `82542ba2a8a9f9622a0302ecdde132aeeb4f9a452d1983ddfc27630b32e5efac`
- manifest deterministic digest:
  `49d8a0465c89584f18b4242d329ffc58482453f8f5f6d5b6af87e91041414270`
- bank SHA-256:
  `385c67b060634791c8228aa0809362064c541be7d094120b5241674779d2d06d`
- seed-map digest:
  `1d5e37cd950b87351de27e04cf571e8bb90aad4bfb2400068b2647e82e9e70b0`

Search-byte replay regenerated all nine canonical JSONL shards byte-for-byte
and recomputed the summary and decision. Artifact creation additionally
validated both original provider artifacts on scratch copies. The corrected
full replay mode now repeats that source validation; search-only replay is
explicitly labeled. The artifact contains 9,216 records, 4,608 paired blocks,
no missing/duplicate record, fixed compute closure, zero
credential/network/provider calls, and 256 shared bank records.

ここでfixedなのはtrajectory、verifier、posterior update、padded-bank axesである。
実際のlegal-action score workはtrajectory依存でrunあたり`142..333`、paired
IID/QMCの`4,461/4,608` blockで異なるため、完全な算術演算数一致とは主張しない。

Selection freeze digestは
`15de3ff8386d5839ba5e50c53baa0ef861b515f1d29aa985a67a114a7e02a72d`。
held-out task manifestとproposal snapshotは未封印なので、freeze recordは
`execution_authorized=false`として次段をfail closedにしている。

The result remains conditional on two frozen tasks, two frozen proposal
snapshots, binary exact reward, and eight simulations. It is not provider
superiority, task-transfer, causal, or general QMC-superiority evidence.

See `docs/reviews/countdown_adversarial_review_20260726.md` for the complete
fresh-eye review and stateful correction record.
