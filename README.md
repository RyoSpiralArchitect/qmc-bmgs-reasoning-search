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
- Track A canary v2は全936 cellのreplay gateを通過しましたが、heuristic `score256`の
  Thompson 4変種は`0/192`、greedy/beam/PUCTは各`6/12`でした。多armのNormal極値が
  priorを飲み込むbase-search不全として保持し、semantic routing/pruningとlocked-128を
  保留して、一因子のaction-dimension正規化v2へ進みます。
- v2の次の診断ablationは、binary64正値floor付き`1/(1+absolute error)`を加えるv3と、
  座標を消費しないgreedy 1 trajectoryを明示的に先行させるv4です。いずれも旧methodを
  置換せず、anchor成功とその後のThompson追加成功を分離して評価します。
- 240-cell診断ではmechanism更新は閉じたものの新規exact rescueは0でした。後続の
  selection-margin監査でdense差は370 common surfaces中94件へ届き、action flipは4件、
  64件は局所boundaryが16倍超でした。これを結果後の成功仮説にせず、旧154 task/sourceを
  全除外した12-task開発cohort上で`0,1,2,4,8,16,32,64`だけを動かす384-cell v5を
  outcome-blindにsealしました。通過しても次はfresh confirmationでありlocked-128ではありません。

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
、実行済みcanaryの境界は
[Track A canary v2 observation](docs/observations/countdown_track_a_canary_v2_20260810.md)
、次の一因子修正は
[Thompson dimension-normalization v2](docs/strategy/countdown_thompson_dimension_normalization_v2.md)
、後続のfeedback/anchor ablationは
[Thompson feedback and anchor v3/v4](docs/strategy/countdown_thompson_feedback_anchor_v3_v4.md)、
次のsource-disjoint scale設計は
[dense terminal scale dose response v5](docs/strategy/countdown_thompson_dense_scale_dose_response_v5.md)
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
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_diagnostic_runner --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2 --self-test
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
qmc-bmgs-countdown-thompson-publication-v2 --self-test
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

したがってhard gateとaggregate adaptive signal上の`CANARY_ENGINEERING_PASS`を
ThompsonやQMCの性能passとは読まない。formal Pareto gateはsemantic routing/pruningを
blockするが、locked evaluation自体はblockしない。現candidateのlocked-128実行は
engineering判断として保留し、dynamic action dimension下のprior/noise scaleと疎な
binary feedbackを先に診断する。結果、exact digest、release archive、post-hocな
proposal-rank診断は
[`docs/observations/countdown_track_a_canary_v2_20260810.md`](docs/observations/countdown_track_a_canary_v2_20260810.md)
に保存した。

この診断を結果後に組み替えないため、historical 2 + canary 12をauthorityにして、
まだ未実行のlocked 128（seed `26072602`）を先に予約し、さらにtask fingerprintと
source-multiset fingerprintの両方で分離したdiagnostic 12（seed `26081001`）をsealした。
score256、IIDのみ、v1/v2/v3/v4 + greedy/beam/PUCT、oracle-greedy controlの240 cellsで、
search outcome、proposal row、perturbation pointはまだ一件も生成していない。

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_diagnostic_manifest \
  --verify docs/preregistrations/countdown_thompson_diagnostic_v1 \
  --repository-root .
```

seal digestは
`cc633b9ee3ffda6a9115af07f0cc047a1bd8cd7af5e11d07f6ddb0faa4e5f975`。
これはtask予約、240-cell schedule、分析順序とengineering gateの同一性だけを証明する。
契約は
[`docs/countdown_thompson_diagnostic_contract.md`](docs/countdown_thompson_diagnostic_contract.md)
に固定した。runner/analyzerはsource checkoutのGit履歴とsource closureをauthorityにするため、
packaged console entrypointは設けない。自己診断は非diagnostic fixtureだけを使い、sealed bundle、
task、proposal、search record、outcomeを開かない。

```bash
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_diagnostic_runner --self-test
PYTHONPATH=src python -m qmc_bmgs.experiments.countdown_thompson_diagnostic_analysis --self-test
```

legacy production runnerは、portable POSIXの`mkdir`後にdescriptor authorityを取得するまでの
raceを閉じられない。次のpublication substrateとして、固定名のregular fileを`openat(O_EXCL)`で直接取得し、
出力path自体を最後のcommit receiptにするflat v2を非diagnostic fixtureだけで実装した。
現在のwire revisionはv2r3で、実行前に外部レビュー済みのroot-to-parent
`(st_dev, st_ino)` bindingを必須とする。lexical parentを別directoryへ差し替えても、
同じbindingでは空namespaceとして再実行できず`AMBIGUOUS`になる。bindingの生成helperは
planning用のmechanicsに限られる。authorization v2のplanning/strict loaderは、backend、layout、
lexical output path digest、exact binding bytesとその環境review要件を一つのdigestに閉じ、loaderは
live pathからexpected bindingを再生成しない。regular-file module自身もrunner source attestationへ加えた。
production v2r3 publisher/analyzerは、同じ公開APIを使う240-cell nondiagnostic full-shaped fixtureで
統合・全cell replay済みになった。public `--run`はauthorization v2のstrict loaderだけを入口とし、
別schema/scopeのfixture authorityを拒否する。このrevisionでは実authorization candidateを生成せず、
sealed 240-cell diagnosticも実行・分析していない。
これはauthorization closureとpublication mechanicsの証拠であり、240-cell diagnosticの実行許可や科学的結果ではない。
設計、不変条件、残余仮定、production移行条件は
[`docs/countdown_thompson_regular_file_publication_v2_contract.md`](docs/countdown_thompson_regular_file_publication_v2_contract.md)
に固定している。

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_regular_file_publication_v2 \
  --self-test

PYTHONPATH=src python -m pytest -q \
  tests/test_countdown_thompson_v2r3_full_shape_fixture.py
```

将来の実run時はclean source checkoutからmodule invocationを使い、`--repository-root .`を明示する。
現revisionではproduction run/analyze実装までが有効だが、実runにはこのrevisionからstrictに派生した
別PRのreviewed authorizationが必要である。plan、別PRでのauthorization review、1回限りのrun、
独立analysisの順序と現在の実装境界は
[`docs/countdown_thompson_diagnostic_execution_contract.md`](docs/countdown_thompson_diagnostic_execution_contract.md)
に固定した。binding不一致や親差替えは空namespaceとして再捕捉せず
`PUBLICATION_STATE_AMBIGUOUS`に分離する。実行・解析はv2r3 terminal collective、bounded read、
authorization/source/bundleの前後再検証、no-overwrite summary publicationに閉じている。
v2/v3/v4のどれもbase searchとしてgreedy/beamを上回れなければ、locked-128は
開かず`STOP_REPAIR_NO_LOCKED_128_RUN`とする。

現在の次段はsearch runnerを持たないv5 preregistrationまでです。次のコマンドは旧4 cohortの
identity authority、新12-task生成、8 scale、384-cell schedule、canonical bytesを再検証しますが、
開発cohortのproposal/perturbation/search outcomeは生成しません。

```bash
PYTHONPATH=src python -m \
  qmc_bmgs.experiments.countdown_thompson_dense_scale_manifest \
  --verify docs/preregistrations/countdown_thompson_dense_scale_v5 \
  --repository-root .
```

seal digestは
`c9f667db2a2ec36e193ce6a8dea32b95a0327028cc121c7e72bc365424ecb09b`です。

自然言語reasoningへの一般化や一般的なQMC優位は、まだ主張しません。
