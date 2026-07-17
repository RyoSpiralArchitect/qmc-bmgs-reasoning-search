# Algorithm and claim boundaries

## Search layers

1. LM logitsからbounded candidate setを作る。
2. candidate representationを探索用strataへ分ける。Q値は共有しない。
3. uncertainty proxyからThompson-style action scoreを作る。
4. coverage routeまたはglobal routeでactionを選ぶ。
5. exact token prefixを次stateとして展開する。
6. terminal/verifier returnをtrajectory後方からBellman backupする。
7. pruning有効時はactive maskだけを変更し、flat prefix storeを破壊しない。

## Objective separation

LM log-probはbehavior/proposal priorで、learned returnそのものではありません。
Bellman backupとreadout successはverifier return側で評価します。この非対称性を
隠して「同じQ目的を最適化している」とは言いません。

## Uncertainty

Welford statisticsとvisit countから作る値は、非定常TD targetに対する探索用proxyです。
独立同分布を仮定した厳密なBayesian posteriorではありません。D4のSD scaleは
learned meanを変えず、このproxyの標準偏差だけを倍率変更します。

## State and graph semantics

state keyはexact token prefixなので、現状はflat dictionaryに保存したtreeです。
semantic state mergeはしていません。node削除で子孫が自動削除されることもないため、
pruningはmask、物理compactionは別phaseとします。

## Current semantic boundary

token input embeddingのclusterはoracle-aligned toyではpositive controlになりますが、
自然言語reasoning roleの証拠ではありません。chunk、one-step hidden state、verifier
featureへ進む前に、sampler/routing作用点のablationを終えます。

## Uniform-channel localization

channel ablationでは各nodeで、従来と同じ`2 + A`次元のscrambled Sobol点とIID点を
毎selection一つずつ生成します。座標`0`はcoverage gate、`1`はcluster quantile、
`2:`はaction perturbationです。4条件は座標ごとにどちらの点を使うかだけを変えます。

これは3本の独立streamではなく、二つのjoint full-dimensional pointからの
coordinate assignmentです。両endpointの旧挙動を保持し、unchanged coordinateを
paired profile間で共有するpartial common-random-number設計です。両source生成を含む
wall timeは計測用instrumentation costで、deployment sampler costとは扱いません。

## Fixed-verifier conversion

次段ではsearch中のverifier feedbackを正確に700回へ固定し、LM node、prefix token、
edgeを結果として測ります。1111 LM nodesはsaturationではなく緩いintegrity guardです。
EOSをterminal leafとして展開しない現候補集合のD4 reachable prefix boundは820です。
正常な700 simulationは各1 verifier、最大4 edgesなので、edgeは2800以下でなければ
なりません。3500 edge ceilingは性能予算ではなく配管異常用のguardです。

700回到達後のgreedy readoutはsearch verifier feedbackを消費しないdeterministic
evaluationとして1回別計上します。したがってfixed-verifierはequal total computeでは
なく、verifier-to-node conversionを測る実験です。
