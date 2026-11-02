# QMC-BMGS Reasoning Search

Can changing **which branch a search visits next** help it find exact answers within a fixed budget? This research repository tests that question on Countdown: combine six numbers with legal arithmetic to reach a target. The verifier checks the arithmetic; a heuristic ranks actions. The latest experiments use no language model.

**探索の予算が同じでも、次に選ぶ枝を変えれば、正解に届く問題は増えるか。** 6個の数から四則演算で目標値を作る Countdown で調べています。式の正しさは検算器が判定します。直近の実験では言語モデルを使わず、探索の選び方だけを変えました。

## What we found / ここまでに分かったこと

Three studies kept the first search trajectory fixed and varied the PUCT exploration bonus. In the latest study, only **unvisited root actions** received a perturbation. Against fixed PUCT, QMC gained 10 paired trials across 7 of 512 problems and lost none on that cohort. The source-mean difference was **+0.49 percentage points**; the registered model interval was **+0.08 to +0.90 points**, below the **+2-point** practical threshold.

最初の探索経路を固定し、その後どこで探索ボーナスを揺らすかを3通り試しました。直近の「未訪問の初手だけ」では、固定PUCTに対し、512問中7問にまたがる10試行で新たに正解し、逆に失った正解はありませんでした。問題ごとに平均した差は **+0.49ポイント**。事前に定めた実用上の基準（+2ポイント）には届いていません。3研究は別々の問題で行ったため、順位や継続的な改善を示すものではありません。

**[Results, evidence and research history / 結果・根拠・研究の経緯 →](docs/results/README.md)**

## Start here / 使い方

With Python 3.10+ and the development dependencies installed, the commands below run locally. The results check reads published outcomes; it does not rerun the experiments. No provider credentials are needed.

Python 3.10以降で利用できます。次のコマンドはローカルで動き、APIキーは不要です。結果の照合には公開済みの成否データを使うため、実験を回し直す必要はありません。

```sh
python -m pip install -e '.[dev]'
python -m qmc_bmgs.benchmarks.countdown --self-test
python scripts/verify_puct_qmc_results.py
python scripts/validate.py
```

| Explore / 読み進める | Where / リンク |
| --- | --- |
| Design goals and algorithm / 研究の狙いと手法 | [Engineering north star](docs/engineering_north_star.md) · [Algorithm](docs/algorithm.md) |
| Search implementations / 探索の実装 | [Substrate](src/qmc_bmgs/substrate/) · [Experimental policies](src/qmc_bmgs_next/) |
| Evidence and limitations / 検証結果と限界 | [Results index](docs/results/README.md) · [Artifact guide](artifacts/README.md) |
