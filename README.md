# QMC-BMGS Reasoning Search

LLMのtest-time searchへ、Bayesian uncertainty proxy、semantic strata、
randomized Sobol / IID exploration、reverse Bellman backupを組み合わせる
engineering research repoです。

このrepoの目的は「QMCを使ったことを証明する」ことではありません。
固定した計算予算で探索成功率が高いか、計算の使い方が良いか、探索挙動として
面白いかを検証し、実際に強いreasoning-time searchへ収束させることです。

## Current read

- D3ではoracle-aligned semantic strataのpositive controlが成立しました。
- D4ではcombined Sobol engineがcoverageを約10倍均一化し、同じLM-node capへ
  少ないedge/verifier workで到達しました。
- しかしPrimary n=256ではIID 40.2%、Sobol 30.1%。Sobol優位は出ませんでした。
- fresh n=256 channel ablationでは成功差は未確定だったが、`sobol_all`はIIDより
  verifier/edge workを約15%減らしつつ成功率point estimateを+2.0pp保ちました。
- `sobol_all`はSD 1.0/0.5の両方でsample-mean Pareto frontに残る唯一のprofileです。
- fixed-verifier n=128ではrouting QMCが同じ700 callsから約6–7%多いdeep nodeを
  得ましたが、成功優位には変換できませんでした。追加breadthの99%は最深層です。
- exploratory two-phase n=64は両対照をpoint estimateで上回りましたが、独立fresh
  n=128ではtwo-phase 37.5%、routing-only 40.6%、Sobol-all 35.9%。routing-onlyとの
  方向は再現せず、threshold tuningを終了しました。
- 固定routing-only上のcredit diagnosticでは、prefix-progressがrequest 128で25対12と
  早く成功した一方、700では26/128対terminal-only 52/128へ反転しました。102 runが
  正解直前prefixで固定され、D4のsampler / feedback tuningを終了しました。
- 次のsubstrateはCountdown-D6です。token prefixではなく合法な算術action chunk、
  canonical DAG state、exact executable verifier、共通multi-axis compute ledgerを先に
  固定し、search比較とは分離して構築します。
- Countdownのmatched source ablation n=128ではSobolがroot discrepancyを約59%下げ、
  root breadthを増やしましたが、equal-task exact successはAnthropicで-1.17pp、
  GPTで-1.95pp。QMC action noiseはpromoteせず、prior/noise calibrationへ進みます。
- prior/noise gridは`(1,1)`をpreregistered gate-passing candidateとして凍結しましたが、
  adversarial reviewで安定性・CRN表記・held-out設計を修正。次はselected対baseline、
  IID対Sobol、simple search baselinesをtask-levelで分離評価します。

結果の短い読み方は [D4 result capsule](docs/results/d4_result.md)、
[fresh channel-ablation capsule](docs/results/channel_ablation_fresh_n256.md)、
[fixed-verifier capsule](docs/results/fixed_verifier_n128.md)、
[two-phase selection capsule](docs/results/two_phase_n64.md)、
[standalone validation capsule](docs/results/two_phase_validation_n128.md)、
[credit-assignment capsule](docs/results/credit_assignment_n128.md)、設計原則は
[engineering north star](docs/engineering_north_star.md)、固定比較の仕様は
[credit-assignment contract](docs/credit_assignment_contract.md)、次substrateの仕様は
[Countdown-D6 contract](docs/countdown_benchmark_contract.md)、最初のprovider接続の境界は
[Anthropic Countdown development-run contract](docs/countdown_anthropic_dev_contract.md)、
対応するGPT-5.6接続の境界は
[GPT-5.6 Countdown development-run contract](docs/countdown_openai_dev_contract.md)
、両providerのdevelopment観察は
[Countdown provider observation](docs/observations/countdown_provider_dev_20260724.md)
、凍結snapshot上の厳密なIID/Sobol摂動源比較は
[matched Thompson source-ablation contract](docs/countdown_thompson_source_ablation_contract.md)
、結果の観察は
[matched Thompson n=128 observation](docs/observations/countdown_thompson_source_n128_20260724.md)
、次の校正設計は
[prior/noise calibration preregistration](docs/countdown_calibration_grid_contract.md)
、その結果は
[prior/noise calibration observation](docs/observations/countdown_calibration_grid_n128_20260726.md)
、再現物は
[calibration release capsule](docs/releases/countdown_calibration_grid_n128_v1.md)
、fresh-eye監査と新作戦は
[Countdown adversarial review](docs/reviews/countdown_adversarial_review_20260726.md)
と
[Countdown next experiment v2](docs/strategy/countdown_next_experiment_v2.md)
を参照してください。

## Layout

```text
src/qmc_bmgs/       policy, benchmark package, experiment package
tests/              download-free smoke/self-tests
scripts/            validation and artifact verification
artifacts/          promoted dated evidence + scratch work directory
docs/               algorithm boundaries, results, engineering direction
examples/           preserved original single-file prototype
```

## Quick start

既存のPyTorch環境なら、installせずに検証できます。

```bash
PYTHONPATH=src python -m qmc_bmgs.policy --self-test
PYTHONPATH=src python -m qmc_bmgs.benchmarks.role_lock --self-test
PYTHONPATH=src python -m qmc_bmgs.benchmarks.countdown --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.d4_noise_sweep --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.channel_ablation --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.fixed_verifier_budget --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.two_phase_sampler --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.two_phase_validation --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.credit_assignment --self-test
PYTHONPATH=src python -m qmc_bmgs.anthropic_countdown --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_anthropic_dev --self-test
PYTHONPATH=src python -m qmc_bmgs.openai_countdown --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_openai_dev --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_source_ablation --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_calibration_grid --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_track_a_substrate --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_track_a_search --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_track_a_canary_runner --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_track_a_canary_analysis --self-test
python scripts/validate.py
```

Countdownの可解・source-multiset重複なしsuiteは、exhaustive calibrationと
不採用理由manifestを同時に作ります。2つ目のsplitでは先のsuiteを明示的に除外できます。

```bash
PYTHONPATH=src python -m qmc_bmgs.benchmarks.countdown \
  --generate-solvable-suite 8 --seed 17 \
  --output artifacts/work/countdown_calibration.json
PYTHONPATH=src python -m qmc_bmgs.benchmarks.countdown \
  --generate-solvable-suite 8 --seed 18 \
  --exclude-suite artifacts/work/countdown_calibration.json \
  --output artifacts/work/countdown_evaluation.json
```

editable installする場合:

```bash
python -m pip install -e '.[dev]'
qmc-bmgs-proto --self-test
qmc-bmgs-benchmark --smoke
qmc-bmgs-countdown --self-test
qmc-bmgs-d4-sweep --smoke
qmc-bmgs-channel-ablation --smoke
qmc-bmgs-fixed-verifier --smoke
qmc-bmgs-two-phase --smoke
qmc-bmgs-two-phase-validation --smoke
qmc-bmgs-credit-assignment --smoke
qmc-bmgs-countdown-track-a-substrate --self-test
qmc-bmgs-countdown-track-a-search --self-test
qmc-bmgs-countdown-track-a-canary-manifest --self-test
qmc-bmgs-countdown-track-a-canary-runner --self-test
qmc-bmgs-countdown-track-a-canary-analysis --self-test
```

## Anthropic Countdown development runner

これはprovider接続、物理コストguard、固定proposal snapshot、local search、exact
verification、network-free replayを一本通すためのscratch plumbing canaryです。locked
benchmarkではなく、4手法の性能差、QMC優位、Anthropicモデルの優位を示す結果には
使いません。固定仕様と送信範囲は
[development-run contract](docs/countdown_anthropic_dev_contract.md) にあります。

fake runとself-testにはcredentialもnetworkも不要です。Anthropic SDKを含めて
editable installする場合は、固定版をoptional dependencyから入れます。

```bash
python -m pip install -e '.[dev,anthropic]'
qmc-bmgs-countdown-anthropic-dev --self-test
qmc-bmgs-countdown-anthropic-dev --run-fake-dev \
  --output-dir artifacts/work/countdown_anthropic_fake_v1
qmc-bmgs-countdown-anthropic-dev \
  --replay artifacts/work/countdown_anthropic_fake_v1
```

live runは`claude-haiku-4-5-20251001`、Messages API version `2023-06-01`、
Anthropic SDK `0.116.0`へ固定されています。API keyはsecret managerや一時的な
session wrapperから、runner子processの`ANTHROPIC_API_KEY`にだけ渡してください。
keyをCLI引数、shell history、`.env`、repo、artifact、log、永続的なclipboardへ
保存しないでください。次のコマンドはkeyが安全にprocess environmentへ設定済みで
あることを前提にし、値を表示しません。出力先には新しい空directoryを使います。

```bash
test -n "${ANTHROPIC_API_KEY:-}"
env -u ANTHROPIC_LOG qmc-bmgs-countdown-anthropic-dev \
  --run-live-dev \
  --output-dir artifacts/work/countdown_anthropic_live_v1
env -u ANTHROPIC_API_KEY qmc-bmgs-countdown-anthropic-dev \
  --replay artifacts/work/countdown_anthropic_live_v1
```

live canaryは最大64 attempts、USD 0.50のhard capです。replayはcredentialもnetworkも
使わず、保存済みproposalからsearch recordをbyte単位で再構成します。出力は
`artifacts/work/`のscratch evidenceのままとし、locked comparisonへ昇格しません。

## GPT-5.6 Countdown development runner

GPT-5.6版は同じ2 task・64 state・proposal意味論・4 local search・exact verifierを
共有し、provider固有のResponses API、token会計、料金、artifact検証だけを分離します。
固定仕様は
[GPT-5.6 development-run contract](docs/countdown_openai_dev_contract.md) にあります。

```bash
python -m pip install -e '.[dev,openai]'
qmc-bmgs-countdown-openai-dev --self-test
qmc-bmgs-countdown-openai-dev --run-fake-dev \
  --output-dir artifacts/work/countdown_openai_fake_v1
qmc-bmgs-countdown-openai-dev \
  --replay artifacts/work/countdown_openai_fake_v1
```

live runは`gpt-5.6-sol`、Responses API、OpenAI SDK `2.45.0`、
`reasoning.effort=none`へ固定します。keyはrunner processの
`OPENAI_API_KEY`だけに渡し、CLI、repo、artifact、logへ保存しません。

```bash
test -n "${OPENAI_API_KEY:-}"
env -u OPENAI_LOG -u OPENAI_BASE_URL -u OPENAI_CUSTOM_HEADERS \
  -u OPENAI_ORG_ID -u OPENAI_PROJECT_ID \
  qmc-bmgs-countdown-openai-dev \
  --run-live-dev \
  --output-dir artifacts/work/countdown_openai_live_v1
env -u OPENAI_API_KEY qmc-bmgs-countdown-openai-dev \
  --replay artifacts/work/countdown_openai_live_v1
```

最大64 attempts、4,096 input tokens/request、512 output tokens/requestを
cache-write最高単価で予約し、USD 3.00をhard capとします。これもscratch plumbing
evidenceであり、provider/model/search superiorityの根拠にはしません。

## Frozen-snapshot Thompson source ablation

旧`iid_thompson_8`はglobal Box--Muller streamなので、そのままSobolと比較しません。
新しいmatched IID/QMCペアは、両providerの凍結proposal、node-localの同一bank、
同じinverse-CDF、8 simulation、exact reward、reverse updateを共有し、選択する
摂動源だけを変えます。128 fresh seedsの全runはcredential/networkなしで行います。

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_source_ablation \
  --run \
  --anthropic-dir artifacts/work/countdown_anthropic_dev_20260722_live_v3 \
  --openai-dir artifacts/work/countdown_openai_dev_20260724_live_v2 \
  --output-dir artifacts/work/countdown_thompson_source_n128_v2
```

これは2つのdevelopment task上のsampler robustness観察であり、held-out性能や一般的な
QMC優位を示すものではありません。

## Preregistered prior/noise calibration grid

旧v2を回帰境界として保存したまま、`prior_bonus x posterior_sd_scale`の9設定を
fresh seed `2048..2175`上で比較します。全設定は同じdual-source bankを共有し、
IID/QMCのどちらが勝つかではなく、両source・両snapshotでterminal feedbackへ入る
gate-passing candidateを事前固定ルールで選びます。IID/Sobolはmatched
dual-streamであり、互いにcommon random numbersではありません。

```bash
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY \
  PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_calibration_grid \
  --run \
  --anthropic-dir artifacts/work/countdown_anthropic_dev_20260722_live_v3 \
  --openai-dir artifacts/work/countdown_openai_dev_20260724_live_v2 \
  --output-dir artifacts/work/countdown_calibration_grid_n128_v1
```

eligibleな設定がなければ、実験は正常完了したうえで
`NO_STABLE_CALIBRATION_REGION`を返します。閾値を結果後に緩めません。

通常のrun出力は`artifacts/work/`へ保存されます。promoteしたcanonical raw JSONLは
dated evidenceとしてGitへ含め、各runの`manifest.json`でrecord数・byte数・SHA-256を
固定します。今後のrawは昇格判断までは追跡しません。

## Immediate roadmap

Track Aではdynamic action dimension、atomicな7軸work ledger、visited-state lazy
materialization、hash-chain traceに加え、greedy、beam width 2、PUCT、2設定×IID/Sobol
Thompsonを共通search transactionへ載せた。proposal/perturbation materialの独立再生成後、
空graphからsearch全体をbyte単位で再実行する。download-free確認は次で実行できる。

```bash
qmc-bmgs-countdown-track-a-substrate --self-test
qmc-bmgs-countdown-track-a-search --self-test
```

これは53-action fixture上のtransaction・method plumbing・二段階replayを確認する
integrity milestoneであり、search性能の結果ではない。12 task、936 cell、
proposal/method/budget、analysis gateはsearchを一度も走らせずcanonical JSONとして
seal済みで、次で独立再生成できる。

```bash
qmc-bmgs-countdown-track-a-canary-manifest \
  --verify docs/preregistrations/countdown_track_a_canary_v2 \
  --repository-root .
```

seal digestは
`5799c9f17686f064b7c50ee741d79bfbb14a4d61b9048672068a586b258fd437`。
これはpreregistrationの同一性であり、canary性能結果ではない。契約は
[`docs/countdown_track_a_substrate_contract.md`](docs/countdown_track_a_substrate_contract.md)
と
[`docs/countdown_track_a_search_contract.md`](docs/countdown_track_a_search_contract.md)
、
[`docs/countdown_track_a_canary_contract.md`](docs/countdown_track_a_canary_contract.md)
を参照。

このbundleの実行資格はCPython 3.13.13、arm64、Torch 2.11.0と記録済み
generator conformance digestへ固定している。一般的なpackage install可否とは分け、
実行前にportableなartifact監査とlive exact-runtime qualificationの両方を要求する。
runtime不一致は失敗rowではなく`NOT_RUN`として扱う。
qualifier単体は実行を認可しない。次runnerがverified bundle、fresh qualifier、cleanな
runner/search build digestを同一preflight内で結合し、`implementation_base`を祖先として
検証して初めてcellを開ける。PR3 revisionは将来runnerのHEAD要件ではない。

Version oneのsealは履歴として保持しているが、atomic selectionの次vectorが
legal-score primaryとcoordinate guardを同時にblockし得ることを非canary fixtureで
実行前に確認したため、outcome-blindなversion twoへsupersedeした。Version twoは
score256のnon-primary envelopeだけを修正し、12 tasks、methods、seeds、analysis rules、
936-cell scopeは変えていない。

```bash
qmc-bmgs-countdown-track-a-canary-manifest --qualify-runtime
```

runnerと独立analyzerのself-testは非canary fixtureだけを使う。sealed canaryを開く手順は
runner実装PRのmerge、clean checkoutからrepo内の将来tracked pathへの`--plan`、生成した
authorizationだけを含む別PRのreview/merge、review済みdigestとそのPR merge revisionを
明示した1回の`--run`、外部authorizationを再度渡すindependent analysis、の順を変えない。
source closureは4つの実行済みpackage initializerを含む13ファイルをrunnerがattestし、
独立analyzerはhistorical runner leafを除く現在の12 imported modulesを再検証する。
`--plan`は実行ではなく、authorization candidateを作るだけである。完全なコマンド、
`NOT_RUN`/`INVALID`境界、durable attempt reservationによるauthorization消費、
copy後artifactの分析条件は
[`docs/countdown_track_a_canary_execution_contract.md`](docs/countdown_track_a_canary_execution_contract.md)
に固定した。

1. source-multiset-disjointな12-task canaryと936-cell scheduleはGit上でseal済み。
2. runner/analyzerをmergeした後、別authorization PRをreview/mergeする。merge前には
   sealed outcomeを一件も開かない。
3. review済みauthorization digestとauthorization PR merge revisionでexact 936-cell
   runを一度だけ実行し、全cellのbudget closure、provider call zero、二段階replayを
   独立analyzerで検証する。durable attempt marker生成後は同じauthorizationでretryしない。
4. canary gate通過後だけ128-task locked evaluationをsealして実行する。
5. taskを独立単位としてcalibration transfer、source effect、simple-baseline差を分離
   評価する。
6. competitiveなbase searchが確認できた後だけsemantic routingとBayesian pruningを
   一因子ずつ追加する。

このcanaryはreview済みauthorizationで一度だけ実行され、936/936 cellのbudget
closure、provider call zero、独立二段階replayを通過した。一方、heuristic proposalの
`score256`ではgreedy/beam/PUCTが各`6/12` taskを解いたのに対し、4つのThompson
variantは合計`0/192` runだった。`verifier8`でもcandidate IID/Sobolは各`1/48`に
留まり、両budgetでsimple-baseline Pareto blockが成立した。

したがってintegrity/livenessとしての`CANARY_ENGINEERING_PASS`をThompsonやQMCの
性能passとは読まない。現candidateのlocked-128実行とsemantic routing/pruning追加は
保留し、dynamic action dimension下のprior/noise scaleと疎なbinary feedbackを先に
診断する。結果、exact digest、release archive、post-hocなproposal-rank診断は
[`docs/observations/countdown_track_a_canary_v2_20260810.md`](docs/observations/countdown_track_a_canary_v2_20260810.md)
に保存した。

自然言語reasoningへの一般化や一般的なQMC優位は、まだ主張しません。
