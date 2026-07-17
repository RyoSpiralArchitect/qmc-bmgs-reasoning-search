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
