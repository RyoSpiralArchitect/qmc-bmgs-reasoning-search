# Results and research history / 結果と研究の経緯

[Project overview / プロジェクト概要](../../README.md) · [Outcome data](puct_qmc_series/outcomes.csv) · [Study manifest](puct_qmc_series/manifest.json) · [Recompute the table](../../scripts/verify_puct_qmc_results.py)

## The three anchored PUCT studies / 初手からの探索経路を固定した3研究

The question was *where*, if anywhere, bounded variation in the exploration bonus helps. All three studies used binary exact-solve rewards, the same heuristic prior within each study, and an identical first trajectory across arms. Only the location of the variation changed in the sequence of designs. **The cohorts also changed:** compare each policy to its own fixed PUCT control, not one row of this table to another.

探索ボーナスを「すべての深さ」「初手だけ」「未訪問の初手だけ」の順に絞りました。正解は、制限内に目標値と一致する式を一度でも見つけたかどうかです。各行は別々の新しい512問での結果です。行をまたいだ数値の差から、手法を変えた効果を読むことはできません。

| Study / 揺らした場所 | QMC exact / 2,048 | IID exact / 2,048 | Fixed PUCT exact / 512 | Gains / losses / ties vs PUCT | QMC − PUCT, pp (model interval) |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Oct 27 · All depths / 全深さ](../observations/countdown_puct_qmc_hybrid_development_20261027.md) | 1,096 | 1,091 | 272 | 22 / 14 / 2,012 | +0.391 (−0.391, +1.172) |
| [Oct 29 · Root only / 初手のみ](../observations/countdown_puct_qmc_root_development_20261029.md) | 1,164 | 1,158 | 286 | 22 / 2 / 2,024 | +0.977 (+0.364, +1.589) |
| [Oct 30 · Unvisited root edges / 未訪問の初手のみ](../observations/countdown_puct_qmc_unvisited_development_20261030.md) | 1,122 | 1,120 | 278 | 10 / 0 / 2,038 | +0.488 (+0.076, +0.901) |

**All three: `NO_PRACTICAL_UPLIFT_SIGNAL`.** The upper endpoint stayed below the prespecified +2-percentage-point threshold. In the last study the ten gains were spread across seven problems; the other 505 had no change in their average. Zero observed losses is not a guarantee. QMC exceeded IID by just two trials on that cohort; the secondary QMC–IID interval includes zero.

**判定はいずれも「実用上の改善シグナルなし」です。** 直近の2研究では差の区間が正の側にありますが、小さな差があることと、実用上の基準を超えることは別です。勝者や既定の探索方針は選んでいません。

### How to read the numbers / 分母と判定

- Per study: 512 distinct six-number inputs × (4 QMC seeds + 4 IID seeds + **1 deterministic PUCT**) = 4,608 physical runs. Each had a cap of 512 legal-action scores. Other work, including proposal generation, need not be equal.
- The primary statistic averages four QMC outcomes within each problem, subtracts that problem’s single PUCT outcome, then averages the 512 differences. Gains/losses describe 2,048 pairings; they are **not** 2,048 independent problems. The interval is the registered mean ± 2 × source SD / √512, not a guarantee of population coverage. The secondary contrasts cannot replace the primary.
- 成否CSVは1問1行です。各行に固定PUCTの成否1個と、QMC・IID各4試行の成否が入っています。1つのPUCT成績を4回分の独立した観測とは数えません。各研究ノートには損失、打ち切り、未使用予算、計上外の仕事量も残しました。

### Verification / 検証

For each study a separate process regenerated the cohort and every one of the 4,608 cells byte for byte. A separate implementation checked the saved events, source-level reductions, 2,048 QMC/IID pairs and 512 common first trajectories. Local result-package suites passed **1,940 / 1,992 / 2,055 tests** respectively (zero skips). These checks establish local consistency; they are not three independent replications of one effect or third-party review.

最後の研究の検算器では、初回の合成テスト58件中57件が通り、入力を共有していた1件が失敗しました。失敗版を残し、そのテストの入力だけを分離すると、対象1件の再テストが通りました。検算器本体は変更していません。実データには「すべての初手を訪問済み」の例はなく、この境界条件は合成テストで確認しています。

The public export includes research code, synthetic problem definitions, frozen plan JSON, observations, checker source and the nine final binary outcomes per source. The manifest binds plans, cohorts and local analysis outputs by SHA-256. Raw event streams, machine records and private approval text are **not** distributed. The original runners remain tied to their frozen environments and authorizations; use the [public verifier](../../scripts/verify_puct_qmc_results.py) to reproduce the published primary results without rerunning a study.

### Public checkout / 公開版での検証

| Check | Result in the separate public checkout |
| --- | --- |
| [Public outcome verifier](../../scripts/verify_puct_qmc_results.py) | All 3 primary results reproduced from 1,536 source rows (13,824 outcomes) |
| PUCT research tests / public-export boundary tests | 191/191 and 4/4 passed, no skips; Ruff passed |
| Full repository suite on public commit `d998586` | **Not passed.** unittest reported 1,880 tests, 29 failures and 22 errors; the validator exited 1. Some class setups failed, so discovery did not run every case. |

All failing groups belong to the earlier feedback-budget receiver/reattestation work, not to the new PUCT tests. The earlier checks compare saved absolute locations, coordinator identities and local-only artifacts with the original execution environment; a distinct checkout does not recreate it. For example, one check rejects a different lexical path and another cannot find a historical start record. We did not distribute the private records, skip the old checks or rerun a scientific experiment to make them pass.

公開データから主結果は再計算でき、公開研究用のテストも通ります。一方、研究を行った元の端末・場所まで含めて照合する全体検証は、別の場所に用意した公開版では通りません。元の3研究のローカル検証合格と、公開版の全体検証失敗は、対象が違うため両方を記録しています。

## Earlier work / これまでの実験をたどる

| Question / 問い | Evidence / 記録 |
| --- | --- |
| Where does QMC help in small controlled searches? / どの段階の揺らぎが効くか | [D4 noise sweep](d4_result.md) · [Fresh channel ablation](channel_ablation_fresh_n256.md) · [Fixed verifier](fixed_verifier_n128.md) |
| Does splitting exploration and feedback help? / 探索と評価を分けるとどうか | [Two-phase pilot](two_phase_n64.md) → [validation](two_phase_validation_n128.md) · [credit assignment](credit_assignment_n128.md) |
| Frozen proposals versus a live provider / 固定した候補とモデル呼び出しの違い | [Thompson source comparison](../observations/countdown_thompson_source_n128_20260724.md) · [prior/noise calibration](../observations/countdown_calibration_grid_n128_20260726.md) · [canary v2](../observations/countdown_track_a_canary_v2_20260810.md) |
| How did feedback, scale and budget interact? / フィードバックと予算の関係 | [v3/v4 diagnostics](countdown_thompson_diagnostic_v1/README.md) · [v5 dense scale](countdown_thompson_dense_scale_v5/README.md) · [v6 development](../observations/countdown_feedback_budget_v6_development_20260910.md) · [v7 retained verification record](../qualifications/countdown_feedback_budget_v7_reattest_20260921.verification.json) |
| Can more searches compensate for their cost? / 複数探索と予算配分 | [Portfolio](../observations/countdown_feedback_portfolio_development_20261020.md) → [diversity](../observations/countdown_feedback_diversity_development_20261022.md) → [allocation recovery](../observations/countdown_feedback_allocation_recovery_20261024.md) |
| Why return to binary PUCT? / 二値報酬のPUCTに戻った理由 | [Single16 vs PUCT](../observations/countdown_search_value_development_20261025.md) · [prior tilt](../observations/countdown_prior_tilt_development_20261026.md) · [dense vs binary PUCT: 0 gains, 82 losses](../observations/countdown_puct_return_development_20261027.md) |

For the complete dated roadmap, legacy commands and original links, see the [previous front README at its immutable public revision](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/blob/e3729fe506a62d0c4b711da5cdfa2e83be0975f4/README.md). Historical pending, failed and unknown states are retained as recorded; they are not current authorizations. 旧READMEの計画や未確定事項は当時の記録として読んでください。
