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

結果の短い読み方は [D4 result capsule](docs/results/d4_result.md)、
[fresh channel-ablation capsule](docs/results/channel_ablation_fresh_n256.md)、
[fixed-verifier capsule](docs/results/fixed_verifier_n128.md)、
[two-phase selection capsule](docs/results/two_phase_n64.md)、
[standalone validation capsule](docs/results/two_phase_validation_n128.md)、
[credit-assignment capsule](docs/results/credit_assignment_n128.md)、設計原則は
[engineering north star](docs/engineering_north_star.md)、固定比較の仕様は
[credit-assignment contract](docs/credit_assignment_contract.md)、次substrateの仕様は
[Countdown-D6 contract](docs/countdown_benchmark_contract.md) を参照してください。

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

通常のrun出力は`artifacts/work/`へ保存されます。promoteしたcanonical raw JSONLは
dated evidenceとしてGitへ含め、各runの`manifest.json`でrecord数・byte数・SHA-256を
固定します。今後のrawは昇格判断までは追跡しません。

## Immediate roadmap

1. Countdown-D6のTaskAdapter、exact verifier、canonical DAG、compute ledgerを固定する。
2. exhaustive calibratorでcalibration taskとlocked evaluation taskを分離する。
3. greedy / top-p / IID Thompson / best-first / routing-onlyをmatched computeで比較する。
4. arithmeticで設定を凍結し、typed DSL synthesisへ無調整でtransferする。

自然言語reasoningへの一般化や一般的なQMC優位は、まだ主張しません。
