# Main integration qualification / 統合検証記録

The local repository validator passed on the integrated [source revision](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/commit/68810d091a9991f6d95dd60a5bd9847bd2580075): **2,071 tests in 1,033.534 s, zero failures, errors or skips; exit 0**. The tested Git tree was `bc34e08e5bf095a07dacff8b939827c8fb55fdc7` (629 tracked files). Compilation, Ruff, artifact, provenance and design checks, CLI self-tests and the final manifest verification completed with `repository validation: PASS`.

元の保存物を読み取り専用で照合できる環境で、2,071件すべてが通りました。新しい性能実験や第三者レビューを行ったという意味ではなく、GitHubのホスト型CIの結果でもありません。末尾の検証記録と結果READMEの追記は、検証後の文書変更です。

## What was checked

- [#31](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/31) retains its 64-source allocation experiment, including the original implementation in Git. The active implementation from the separate 256-source study remains in place. [Both records and their denominators](../results/feedback_allocation_history.md).
- [#38](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/38) retains all 21 original changed paths, byte for byte. [#39](https://github.com/RyoSpiralArchitect/qmc-bmgs-reasoning-search/pull/39) adds the public PUCT studies, outcome data and bilingual entry point. None of the scientific outcomes or registered thresholds changed during integration.
- The full run included **328 tests from eight historical modules** against their verified original fixtures. The mirror checked 470 tracked entries and 5,329 protected artifacts. Only the three named narrative guides could use a jointly pinned public revision; no test was removed or marked optional. A plain public clone alone does not contain all these fixtures.

## Earlier attempts retained / 先行検証の記録

| Scope | Outcome |
| --- | --- |
| Original plain public checkout, `d998586` | Full validation did not pass: 1,880 tests, 29 failures and 22 errors in historical receiver/reattestation groups. |
| First integrated preview, `01848f0` | 2,071 tests; one synthetic 384-cell publication test failed. A destination-generation change triggered rollback. The log does not establish which process caused the change. |
| Same preview, physically isolated fixture | The failed case alone passed (1/1). The next full-suite launch stopped **before any test** because the temporary Unix-socket path was too long. |
| Same preview, shorter physical temporary path | 2,071 tests; one error. A synthetic protected-mode test assumed its file was created as 0644, but a private umask created it as 0600. The verifier correctly rejected it. |
| Final integrated source, `68810d0` | The test explicitly sets its fixture mode and checks that a real change to 0600 is rejected. The 12 mirror tests passed under both 022 and 077; the complete 2,071-test run then passed. Production checks, real fixture permissions and the 240-second timeout were unchanged. |

This qualification applies to the stated source tree, not to a later documentation-only commit. For scientific readouts and their limits, see the [results index](../results/README.md).
