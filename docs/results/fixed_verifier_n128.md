# Fixed-verifier conversion: fresh n=128

## Status

Role-Lock D4、SD scale 1.0、fresh paired seed 512–639。各runはsearch中の
verifier feedbackを正確に700回消費し、LM 1111とedge 3500はintegrity guardだけに
使った。384 records / 128 paired groupsはdata-quality、disk再生成、独立raw再計算を
PASSした。

Canonical evidence:
[promoted report](../../artifacts/role_lock/d4/20260718_fixed_verifier_n128/report.md)

## Result

| Profile | Readout success | Mean LM nodes | Mean prefix tokens | Mean edges |
|---|---:|---:|---:|---:|
| `iid_all` | 43.0% (55/128) | 373.3 | 1395.9 | 2543.0 |
| `sobol_all` | 35.9% (46/128) | 399.7 | 1501.1 | 2543.3 |
| `sobol_routing_only` | 41.4% (53/128) | 396.3 | 1487.6 | 2542.2 |

`sobol_all`対IIDは成功率-7.0pp、paired simultaneous 95% CI
[-20.3, +6.2]pp、Holm p=0.642。LM nodesは+26.4、paired 95% CI
[+20.3, +32.1]で、同じ700 verifier callsから約7.1%多いunique prefixを得た。

`sobol_routing_only`対IIDは成功率-1.6pp、paired simultaneous 95% CI
[-14.8, +11.7]pp、Holm p=0.885。LM nodesは+23.0、paired 95% CI
[+18.2, +27.6]で、約6.2%多いunique prefixを得た。

したがってsuccess superiorityはどちらも未確定だが、verifier-to-node conversionは
正方向。ただしこれはuseful-compute superiorityでもtotal-compute efficiencyでもない。
QMC側はLM forwardとprefix-token workを実際に多く使っている。

## Where the extra nodes went

追加nodeの約99%は最深depth 3にあった。edgesはほぼ同じで、全recordにおいて
`nodes_created + cache_hits == edge_selections`。QMCはtrajectoryを増やしたのではなく、
同じedge選択内のcache revisitをdeep unique prefixへ置き換えた。

| Correct-prefix stage | IID | Sobol all | Routing only |
|---|---:|---:|---:|
| 0 | 58 | 21 | 40 |
| 1 | 10 | 30 | 15 |
| 2 | 4 | 16 | 12 |
| 3 | 1 | 15 | 8 |
| Success | 55 | 46 | 53 |

`sobol_all`はstage-0 failureを減らしたが、そのmassをsuccessではなくstage 1–3へ
移した。stage 3でもEOSではなく`PROBE`や`DERIVE`へ戻るfailureが多い。静的token
clusterは「現在stageで必要な役割」を表さず、同じreasoning tokenの反復を区別できない。

oracle pathはIID 126/128、両Sobol 128/128ですでにtree内にあった。したがって主な失敗は
path discoveryではなく、terminal-only sparse reward下で正しいdeep branchへ再集中できない
こと。追加breadthをそのまま有用な探索と呼んではいけない。

## Coverage and time-to-hit

Sobol routingはroot coverage deviationを0.0255から0.00201へ約12.7倍tightにし、
explored state-cluster pairsも増やした。これはrouting QMCの配管が意図どおり働く直接証拠。

一方、`sobol_all`は成功した46 seedsではfirst hitが平均301 callsで、IIDの成功55 seedsの
平均367 callsより早い。しかしhitしないseedが多く、censored込みfirst-hit scoreはほぼ
同じ。特にSobol failure / IID successの37 seedsではSobolが平均51.4 nodes多かった。
positive node conversionの一部は「成功せず探索が広がり続けた量」でもある。

## Engineering decision

現時点では`Sobol action perturbation`をwinnerとしてpromoteしない。
`sobol_routing_only`はIIDに近い成功point estimateを保ちながらdeep breadthを増やすため、
次の探索substrateとしてはより安全。ただし成功優位は証明されていない。

次の最小実験はtwo-phase action sourceを1条件だけ試す。

- verifier 0–255: `sobol_all`
- verifier 256–699: routingはSobolのまま、action perturbationだけIIDへ切替
- tree/valueと両uniform source streamはリセットしない
- fresh paired seeds 640–703、n=64
- controls: `sobol_all` / `sobol_routing_only`
- primary: exact success at verifier 700
- passive telemetry: success-by-verifier、depth別node、on/off-oracle-prefix node、
  oracle-node visits、EOS trials

256は今回のcurveを見て選んだ探索的thresholdなのでsweepしない。two-phaseが改善しなければ
threshold tuningを止め、terminal-only対prefix-progress verifierのcredit-assignment
ablationへ進む。

## Claim boundary

これはoracle-aligned static-token strataとterminal-only rewardを使うtoy taskの結果。
自然言語reasoning、equal total compute、deployment wall time、一般的QMC優位へは一般化しない。
700 search verifier feedback後のgreedy readout evaluation 1回は予算外に別計上されている。
