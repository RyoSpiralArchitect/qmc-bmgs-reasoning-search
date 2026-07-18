# Two-phase action source: exploratory fresh n=64

## Status

Role-Lock D4、SD scale 1.0、fresh paired seeds 640–703。各runはsearch中の
verifier feedbackを正確に700回消費した。two-phaseはrequest 1–256で
`sobol_all`と同一、request 256のbackupとcheckpoint後にaction perturbationだけを
IIDへ切り替えた。routingはSobolのままで、tree/valueとSobol/IID streamはresetしない。

192 records / 64 paired groupsはdata quality、disk再生成、record/checkpoint/first-hit
digest、独立raw再計算をPASSした。request 256までのbehavior identityと、257からの
source switchも全64 seedで確認した。

Canonical evidence:
[promoted report](../../artifacts/role_lock/d4/20260718_two_phase_n64/report.md)

## Outcome

| Profile | Readout success | Mean LM nodes | Mean prefix tokens | Mean edges |
|---|---:|---:|---:|---:|
| `sobol_all` | 37.5% (24/64) | 401.0 | 1505.8 | 2537.1 |
| `sobol_routing_only` | 35.9% (23/64) | 397.1 | 1490.6 | 2539.3 |
| `two_phase_action_256` | 40.6% (26/64) | 395.3 | 1483.8 | 2544.4 |

two-phase対routing-onlyは成功率+4.7pp、paired simultaneous 95% interval
[-9.4, +18.8]pp、McNemar p=0.581、Holm p=1.0。discordanceはtwo-phaseのみ8、
routingのみ5だった。

two-phase対Sobol-allは+3.1pp、paired simultaneous 95% interval
[-10.9, +17.2]pp、McNemar p=0.804、Holm p=1.0。discordanceはtwo-phaseのみ9、
Sobol-allのみ7だった。

両区間は0を跨ぐ。これは正方向のengineering signalであり、success superiorityや
winnerの証拠ではない。

## What changed after request 256

checkpoint 64 / 128 / 256 / 512 / 700の成功数は次のとおり。

| Profile | 64 | 128 | 256 | 512 | 700 |
|---|---:|---:|---:|---:|---:|
| `sobol_all` | 1 | 4 | 11 | 21 | 24 |
| `sobol_routing_only` | 1 | 4 | 10 | 19 | 23 |
| `two_phase_action_256` | 1 | 4 | 11 | 23 | 26 |

two-phaseとSobol-allは256まで同一。そこで未成功だった53 seedのうち、後半で
two-phaseは15、Sobol-allは13を成功へ変換した。純増は2 seedで、効果は少数seedの
入れ替わりを含む。

Sobol-all比ではtwo-phaseはLM node -5.69、prefix token -22.0、edge +7.30。
各paired 95% intervalは0を跨がない。late depth-3新規nodeも144.6から139.7へ減り、
一方で既存edgeの再訪は少し増えた。これは「後半に新しいdeep prefixを広げ続ける」
挙動から、「既存枝へわずかに再集中する」挙動への移動と整合する。

late oracle action visitsもtwo-phaseが各stageで高かった。

| Profile | stage 0 / 1 / 2 / 3 |
|---|---:|
| `sobol_all` | 104.2 / 31.4 / 11.7 / 4.8 |
| `sobol_routing_only` | 102.3 / 30.1 / 10.8 / 4.3 |
| `two_phase_action_256` | 108.8 / 34.3 / 13.2 / 5.5 |

ただし最終correct-prefix分布は一様な支配ではない。two-phase / Sobol-all /
routing-onlyの`[stage 0, 1, 2, 3, success]`は、それぞれ
`[17, 9, 6, 6, 26]`、`[15, 11, 5, 9, 24]`、`[20, 9, 7, 5, 23]`だった。

## Mechanism boundary

事前gateで使ったlate on-path shareとEOS/requestの平均差はrouting-only比でそれぞれ
+0.0105、+0.00278となり、success point deltaと合わせて全て正だった。

しかしこれは独立な因果証拠ではない。全192 recordで
`late_correct_stage_eos_trials > 0`とfinal successが完全一致した。late on-path差の
中央値もほぼ0で、平均差の多くは片方だけ成功したseedの成功後lock-inから生じる。
したがって「switchが先に正解枝へ集中させた」のか、「成功後のrewardが集中させた」のかは
このtelemetryだけでは分離できない。

次のvalidationではprimary outcomeを変えず、request 257からfirst hitまで、または
257–384固定windowのpre-hit on-path occupancyをpassive diagnosticとして追加すると、
探索原因と成功後lock-inを分けやすい。

## Engineering decision

事前gateの機械的条件は満たしたため、fresh standalone n=128を一度だけ実行してよい。

- seeds 704–831
- threshold 256を固定し、sweepしない
- 同じ3 profile、verifier cap 700、同じguard
- primaryはexact verifier 700時点のsuccess
- 現n=64はpool selection cohortとしてprimaryへ混ぜない

n=128の役割はwinner確定より、方向の再現性とengineering profileの検証にある。
同程度の3–5pp差なら区間がなお0を跨ぐ可能性が高い。再現しなければthreshold tuningを
止め、予定どおりterminal-only対prefix-progressのcredit-assignment ablationへ進む。

## Follow-up

[standalone fresh n=128 validation](two_phase_validation_n128.md)ではtwo-phase 37.5%、
routing-only 40.6%、Sobol-all 35.9%となり、routing-onlyとの方向は再現しなかった。
このn=64はselection cohortのままprimaryへ混ぜず、予定どおりthreshold tuningを終了した。

## Claim boundary

これはoracle-aligned static-token strata、terminal-only reward、posthoc thresholdを使う
toy taskの結果。自然言語reasoning、equal total compute、deployment wall time、一般的な
QMC優位へは一般化しない。equal verifier callsでもtotal computeは同一ではない。
