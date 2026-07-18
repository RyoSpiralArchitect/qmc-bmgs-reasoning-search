# Two-phase action source: standalone fresh n=128 validation

## Bottom line

request 256までSobol action perturbation、257以降をIIDへ切り替える固定two-phaseを、
選抜に使ったn=64を混ぜず、fresh seeds 704–831で一度だけ再検証した。全profileは
Role-Lock D4でsearch verifier feedbackを正確に700回消費し、candidate集合、routing、
posterior SD 1.0、pruning off、LM/edge guardを揃えた。

two-phaseは48/128 (37.5%)。`sobol_routing_only`は52/128 (40.6%)、
`sobol_all`は46/128 (35.9%)だった。したがってtwo-phaseはSobol-allへ+1.6ppだが、
routing-onlyへ−3.1pp。事前ルールの「両対照へ正のpoint delta」を満たさず、
`direction_not_replicated`となった。

[promoted report](../../artifacts/role_lock/d4/20260718_two_phase_validation_n128/report.md) /
[summary](../../artifacts/role_lock/d4/20260718_two_phase_validation_n128/summary.json) /
[manifest](../../artifacts/role_lock/d4/20260718_two_phase_validation_n128/manifest.json)

## Primary paired result

| Contrast | Success delta | Simultaneous 95% interval | Discordance | McNemar p |
|---|---:|---:|---:|---:|
| two-phase − routing-only | −3.1pp | [−13.3, +7.0]pp | 15 / 19 | 0.608 |
| two-phase − Sobol-all | +1.6pp | [−8.6, +11.7]pp | 20 / 18 | 0.871 |

discordanceは「two-phaseのみ成功 / controlのみ成功」。両co-primaryのHolm調整pは1.0。
区間は広く、Sobol-allへの小さな正差もsuperiority evidenceではない。

選抜n=64ではtwo-phase − routing-onlyが+4.7pp、two-phase − Sobol-allが+3.1pp
だった。今回routing-onlyとの方向が反転したため、n=64と結合したn=192を新しいprimary
として作らない。n=64はselection、今回のn=128だけがstandalone validationである。

## Success timing

| Verifier request | Sobol-all | Routing-only | Two-phase |
|---:|---:|---:|---:|
| 64 | 3 | 6 | 3 |
| 128 | 4 | 12 | 4 |
| 256 | 14 | 22 | 14 |
| 384 | 30 | 34 | 23 |
| 512 | 36 | 38 | 29 |
| 700 | 46 | 52 | 48 |

two-phaseとSobol-allはswitch直前の256まで同一で、これはexpected nonintervention。
switch後、two-phaseは384・512でSobol-allより遅れ、最後の188 requestsで追い越した。
「late IIDが後から効く」可能性は見えるが、checkpoint curveはdescriptiveであり、ここから
別thresholdを選び直さない。routing-onlyは最初から先行し、700でも最多成功だった。

request 256までにtwo-phase/Sobol-allの全128 runで完全なoracle prefix path自体は
展開済みだった。したがって、この差は正解pathを一度も発見できない問題より、展開済みの
branchへfeedbackを集め、readout valueへ変換する問題として読む方が整合的である。

## Engineering profile

| Method | Mean LM nodes | Mean prefix tokens | Mean edges |
|---|---:|---:|---:|
| Sobol-all | 404.13 | 1518.48 | 2540.61 |
| Routing-only | 393.84 | 1478.12 | 2542.86 |
| Two-phase | 400.36 | 1503.51 | 2537.34 |

two-phase − routing-onlyはLM node +6.52、prefix token +25.38、edge −5.52。
成功率も低いため、routing-onlyに対するengineering Pareto improvementではない。

two-phase − Sobol-allはLM node −3.77、prefix token −14.98、edge −3.27で、
LM nodeとprefix tokenのpaired nominal intervalは0より小さい。一方、成功差は+1.6ppで
不確か。つまりtwo-phaseはSobol-allより少し再集中寄りだが、そのprofileは最良controlの
routing-onlyを上回る強さへ変換しなかった。

このcompute shapingは選抜n=64でも同方向で、two-phase − Sobol-allはLM node −5.69、
prefix token −22.0、成功point delta +3.1ppだった。2 cohortを通じて残ったのは
「continuous Sobol actionよりbreadthを少し抑える」という挙動であり、baseline全体に対する
探索強度ではない。

またn=128のtwo-phase対Sobol-allは、両方成功28に対してtwo-phaseのみ20、Sobol-allのみ
18だった。平均差が小さくても探索経路の入れ替わりは実在する。将来fixed total budgetで
portfolio allocationを比較する余地はあるが、現時点のunionは単純に二倍予算なので性能証拠に
数えない。

## Pre-hit window

request 257–384について、初回成功request自身を厳密な固定寄与
`(edges, nonroot, on-oracle nonroot, correct-stage, EOS) = (4, 3, 3, 1, 1)`として
分離し、その直前だけをpassive snapshot差分から復元した。checkpoint 384追加前後で
outcome、usage、final behavior digest、共通checkpoint digestは完全一致した。

pairwise eligible blockでのpre-hit on-path share差は、two-phase − routing-onlyが
+0.00053（nominal 95% [−0.00056, +0.00182]）、two-phase − Sobol-allが+0.00215
（[+0.00001, +0.00462]）。非常に小さく、outcome-conditionedかつoracle-informedなので
因果効果ではない。pre-hit EOS rateが全methodで0なのは、正しい最終stageのEOSがそのまま
初回成功になるためで、分離が機能した確認にはなるがmechanism endpointとしては情報を
持たない。

## Engineering decision

threshold 256のschedule tuningはここで終了する。失敗を別thresholdで消さず、次は予定どおり
terminal-only対prefix-progress verifierのcredit-assignment ablationへ進む。

最小の次設計は、今回最良だった`sobol_routing_only`を固定substrateにして、探索budgetと
exact-success readoutを変えず、search feedbackだけを次の2条件で比較すること。

1. terminal-only: 現行の完全一致だけ5、その他0。
2. prefix-progress: `v(x) = 5 L(x) / 4`。`L`はtargetと一致する最長prefix長0–4。

これはdeployable verifierの主張ではなく、sparse creditが現在のbottleneckかを調べる
oracle-positive-controlである。`feedback > 0`をsuccessとして数えず、best feedbackと
first exact successを別ledgerにする。今回のrouting-only terminal rawをimmutable controlとして
再利用し、同じseedsでprogress条件だけを追加する最小診断なら新規128 runで済む。ただし
post-validation mechanism diagnosisであり、新しい性能validationとは呼ばない。

prefix-progressが同じ700 callsでexact successを明確に増やすなら、sampler scheduleではなく
credit/value側を育ててchunk/contextual actionへ進む。増えなければ、このtoyでの追加sampler
tuningを止める。Sobol-all×two-phaseの2×2はswitch固有の因果診断としてはきれいだが、
engineering trackでは負けたscheduleの救済より、最良substrateの改善を先に問う。

## Data quality and claim boundary

- 384 records、128 complete paired blocks、duplicate 0、strict JSON/digest PASS。
- 全runがverifier exactly 700、edge ≤ 2800、LM node < 1111。
- minimum guard headroomはLM 678、edge 865。
- 4 shardのbyte concatenationはpromoted rawと完全一致。
- 結果はoracle-aligned static-token Role-Lock D4に条件付く。
- 自然言語reasoning、equal total compute、一般的QMC優位へは一般化しない。
