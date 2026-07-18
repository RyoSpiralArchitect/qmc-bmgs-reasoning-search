# Credit assignment: fixed routing-only n=128 diagnostic

## Bottom line

fresh superiority testではなく、直前のstandalone validationで選ばれた
`sobol_routing_only`とseeds 704–831を固定したpost-validation mechanism diagnostic。
既存terminal-only rawをimmutable controlとして参照し、新規runは
`v(x)=5L(x)/4`のprefix-progress 128本だけ生成した。primaryはfeedbackではなく、
700 calls後のexact deterministic readout successのまま維持した。

prefix-progressは26/128 (20.3%)、terminal-only controlは52/128 (40.6%)。
paired deltaは−20.3pp、95% bootstrap interval [−27.3, −13.3]pp、exact
two-sided McNemar p=2.16e−7だった。固定ruleは`no_gain`であり、Role-Lock D4上の
sampler / feedback tuningはここで終了する。

[promoted report](../../artifacts/role_lock/d4/20260719_credit_assignment_n128/report.md) /
[summary](../../artifacts/role_lock/d4/20260719_credit_assignment_n128/summary.json) /
[manifest](../../artifacts/role_lock/d4/20260719_credit_assignment_n128/manifest.json) /
[frozen contract](../credit_assignment_contract.md)

## Primary paired result

| Condition | Exact success | Wilson 95% |
|---|---:|---:|
| Terminal-only control | 52/128 (40.6%) | [32.5, 49.3]% |
| Prefix-progress | 26/128 (20.3%) | [14.3, 28.1]% |

discordanceはprogress-only 1、control-only 27、both-success 25、both-failure 75。
したがって、これは単に改善を確認できなかっただけでなく、この固定diagnosticでは
trajectory-level prefix rewardがfinal exact successを明確に悪化させた結果である。
ただし、oracle-informedな一つのreward式の結果であり、dense feedback一般の否定ではない。

## Fast hit, then freeze

| Feedback requests | Terminal-only | Prefix-progress | Delta |
|---:|---:|---:|---:|
| 64 | 6 | 18 | +9.4pp |
| 128 | 12 | 25 | +10.2pp |
| 256 | 22 | 25 | +2.3pp |
| 384 | 34 | 25 | −7.0pp |
| 512 | 38 | 26 | −9.4pp |
| 700 | 52 | 26 | −20.3pp |

progressは早期に成功seedを作ったが、curveは`18→25→25→25→26→26`でほぼ停止した。
controlは`6→12→22→34→38→52`とbudget全体で新しい成功seedを増やした。
成功したprogress 26 seedの初回exact hitは条件付き平均57.8 requests、controlの52 seedは
323.3 requests。つまり「当たるseedには速いが、外したseedを後半に救えない」挙動だった。

## Near-miss lock-in

final readoutのcorrect-prefix lengthは、progressがexact 26本、length 3が102本。
controlはlength 0/1/2/3/4がそれぞれ36/13/19/8/52本だった。全run・両条件で
oracle prefix nodeは全depthに存在したため、progressの失敗はpath未発見ではない。

正解直前state `[PROBE, DERIVE, COMMIT]` の総visitはprogress 9,067、control 2,057。
それでもEOS trialは842対787で、visit当たりEOS率は9.3%対38.3%だった。
progressは正解直前へ4.4倍多く戻りながら、最後のaction識別に失敗した。

exact trajectory観測総数はprogress 842、control 787で、progressの方が多い。しかし
到達seedは26対52で、exact-hit seed当たり32.4回対15.1回。探索資源が早期winnerへ
集中し、seed間coverageを失ったwinner-take-all profileである。

有力な機構仮説はcredit aliasing。正しい3-token prefixの後では、誤った4-token目にも
`3.75`、exact EOSには`5`が返る。terminal-onlyの最終arm識別幅`5 vs 0`を
`5 vs 3.75`へ圧縮し、先にfeedbackを得た非EOS armを高価値化した可能性がある。
これはrawと整合する説明であり、因果を単独で証明したものではない。

## Engineering profile

| Condition | Mean LM nodes | Mean prefix tokens | Mean edges | Mean final prefix |
|---|---:|---:|---:|---:|
| Terminal-only | 393.84 | 1478.13 | 2542.86 | 2.21 |
| Prefix-progress | 303.06 | 1123.68 | 2616.52 | 3.20 |
| Progress − control | −90.78 | −354.45 | +73.66 | +0.99 |

progressはLM nodeを23.1%、prefix-token workを24.0%減らしつつedgeを2.9%増やした。
これは少数stateへ長く再集中するcompute profileで、効率化したbreadthをsuccessへ
変換できなかった。全89,600 feedback eventsのうち42,184 (47.1%)がpositiveで、
全128 seedが平均3.67 requestsで最初のpositive feedbackを得た。それでも102 seedが
length 3で固定されたため、feedback不足ではなくfeedbackのaction attributionが疑わしい。

## Engineering decision

このnegative resultを保存し、D4でreward scale、非線形shape、sampler、thresholdを
追加調整しない。次はrouting-onlyを一つの固定baselineとして、より難しい小規模taskと
non-oracle verifierへ移り、greedy / top-p / plain Thompsonを含むequal-total-compute比較を
行う。successだけでなく、correct-path reach、final-action selection rate、exact観測の
seed間集中度を標準telemetryにする。

将来の別設計候補として、exact valueを主channel、progressをtie-break専用channelにする
lexicographic valueやpotential-based incremental shapingは残る。ただし、これらを同じD4で
試して今回のnegative resultを消すことはしない。

## Data quality and claim boundary

- challenger 128 records、seeds 704–831、duplicate/missing 0、strict JSON/digest PASS。
- 全runがfeedback exactly 700、outside-budget readout 1、pruning/candidate miss/overshoot 0。
- 89,600 eventをtokensから再計算し、exact/feedback、checkpoint prefix、final censusが閉包。
- immutable controlはmanifest、full raw SHA、歴史的384-row validator、routing subset SHAを
  challenger search前に検証した。control rowは新rawへコピーしていない。
- 4 shardのbyte concatenationはpromoted challenger rawと完全一致した。
- 結果はRole-Lock D4、aligned static-token strata、固定routing-only substrateに条件付く。
- 自然言語reasoning、dense reward一般、equal-total-compute superiorityへは一般化しない。
