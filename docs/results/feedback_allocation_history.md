# Allocation studies: two distinct records / 予算配分の二つの記録

The two studies used the same three total-512 allocations but different cohorts
and frozen implementations. Neither establishes an optimal allocation. A paired
comparison is valid **within** a study; do not pool the two denominators.

| Study | Source problems × seeds | Full 512/0 | Equal 256/256 | Weighted 384/128 | Weighted − full: gains / losses |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Oct 22: original allocation study](../observations/countdown_feedback_allocation_development_20261022.md) | 64 × 8 | 48/512 | 40/512 | 46/512 | 3 / 5 (net −2) |
| [Oct 24: later allocation study and analysis recovery](../observations/countdown_feedback_allocation_recovery_20261024.md) | 256 × 8 | 212/2,048 | 185/2,048 | 195/2,048 | 34 / 51 (net −17) |

Merging the first study later does not turn it into the successor. The active
implementation, runner and two test modules in `src/`, `scripts/` and `tests/`
stay at the successor's versions. For the **original** study use the immutable
[implementation](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/blob/07424f7d0ebaf2406a46db4e8f4851f1d283794b/src/qmc_bmgs_next/allocation_search.py),
[runner](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/blob/07424f7d0ebaf2406a46db4e8f4851f1d283794b/scripts/run_feedback_allocation_development.py),
[kernel tests](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/blob/07424f7d0ebaf2406a46db4e8f4851f1d283794b/tests/test_feedback_allocation.py)
and [runner tests](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/blob/07424f7d0ebaf2406a46db4e8f4851f1d283794b/tests/test_feedback_allocation_development.py).
Its [final plan](../preregistrations/countdown_feedback_allocation_development_20261022.v3.plan.json),
[original qualification](../reviews/countdown_feedback_allocation_development_result_qualification_20261022.md)
and dated evidence remain byte-identical. A historical pending state or execution
approval is not an instruction to repeat either study.

10月22日と24日の研究は、同じ配分を比べていますが、別の実験です。
保存した問題のIDを照合すると、両研究で入力の数字6個が一致する組は5組、
目標値まで一致する問題は0問でした。結果を足し合わせたり、実装を入れ替えた
効果として読み替えたりはできません。

## Checking the integrated tree / 統合後の検証

The public research checks need only the published files. Eight older receiver
test modules additionally require their authentic, path-bound local fixtures.
On a machine that already holds those fixtures, the following runs complete
test discovery, not a subset:

```sh
QMC_BMGS_HISTORICAL_TEST_ROOT=/path/to/the/recorded/checkout \
QMC_BMGS_HISTORICAL_TEST_GUIDES=published-guides-20261103 \
python scripts/validate.py
```

Use the actual recorded location; an arbitrary substitute cannot pass the check.
With the guides option unset, the original mirror check is unchanged. With it
set, only the three narrative guides may use an exact, jointly pinned public
revision. All historical code, test modules and evidence keep the existing
byte checks, directory memberships and absence checks. The candidate validator
entry point is the one pre-existing exception on the candidate side. Test
identities and multiplicities must match, failures or skips remain nonzero,
and the mirror is rechecked at the end. This does **not** make a clean clone a
copy of the historical execution environment, or authorize any new search.
