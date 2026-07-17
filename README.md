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
- したがって次は、QMCをsemantic routingとposterior perturbationへ分離します。

結果の短い読み方は [D4 result capsule](docs/results/d4_result.md)、設計原則は
[engineering north star](docs/engineering_north_star.md) を参照してください。

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
PYTHONPATH=src python -m qmc_bmgs.experiments.d4_noise_sweep --self-test
python scripts/validate.py
```

editable installする場合:

```bash
python -m pip install -e '.[dev]'
qmc-bmgs-proto --self-test
qmc-bmgs-benchmark --smoke
qmc-bmgs-d4-sweep --smoke
```

通常のrun出力は`artifacts/work/`へ保存されます。初期3実験のcanonical raw JSONLは
dated evidenceとしてGitへ含め、各runの`manifest.json`でrecord数・byte数・SHA-256を
固定します。今後のrawは昇格判断までは追跡しません。

## Immediate roadmap

1. `iid_all` / `sobol_all` / `sobol_routing_only` / `sobol_action_only`。
2. LM-node capだけでなくedge/verifier budgetでもcompute-matchする。
3. 有望な作用点だけをchunk action・contextual representationへ接続する。
4. KV-cacheとcandidate refreshを導入し、実LLM/verifierで測る。

自然言語reasoningへの一般化や一般的なQMC優位は、まだ主張しません。
