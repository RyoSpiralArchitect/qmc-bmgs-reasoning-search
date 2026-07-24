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

通常のrun出力は`artifacts/work/`へ保存されます。promoteしたcanonical raw JSONLは
dated evidenceとしてGitへ含め、各runの`manifest.json`でrecord数・byte数・SHA-256を
固定します。今後のrawは昇格判断までは追跡しません。

## Immediate roadmap

1. 凍結Countdown snapshot上で`posterior SD scale x prior bonus`の小さな事前登録gridを
   回し、coverageをterminal rewardへ変換できる校正領域を探す。
2. 両source・両provider snapshotでproposal guidanceを保つ1設定をfreezeする。
3. 未使用Countdown task suiteでtask-levelのIID/QMC比較を行う。
4. それでもbreadthだけが増える場合にearly-QMC / late-exploitationを診断し、
   semantic routingとBayesian pruningはその後に分離評価する。
5. arithmeticで設定を凍結してからtyped DSL synthesisへ無調整でtransferする。

自然言語reasoningへの一般化や一般的なQMC優位は、まだ主張しません。
