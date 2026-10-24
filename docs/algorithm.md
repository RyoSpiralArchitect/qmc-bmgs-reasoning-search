# Algorithm and claim boundaries

## Two implementation layers, not one current algorithm

この文書は初期token-prefix実装と、現在のprovider-free Countdown開発実装を
区別します。研究目的と結果の現在地は
[research status, 2026-10-24](research_status_20261024.md)を参照してください。

| Role | Original token-prefix / D4 layer | Current Countdown allocation-development layer |
| --- | --- | --- |
| State | Exact token prefix; flat dictionary-backed tree | Task-namespaced canonical arithmetic multiset; paths can merge into a DAG |
| Proposal | LM logits over bounded candidates | `greedy_rollout_target_error/v1`, a provider-free deterministic heuristic |
| Exploration | IID/Sobol channel and semantic-stratum variants | IID, action-dimension-normalized perturbations; no semantic routing/pruning |
| Learned return | Prototype TD/Bellman-style backup, with its own limitations | Same completed terminal return averaged into every traversed state-action edge |
| Uncertainty | Welford/visit-derived nonstationary proxy | Noise scale shrinks with visits and action dimension; saved `m2` is not used in selection |
| Evidence boundary | Toy/channel-specific observations | Countdown development observations; not an LM or QMC-versus-IID evaluation |

### Current Countdown selection and return

The ordinary single16 selection value in
[`countdown_search.py`](../src/qmc_bmgs/substrate/countdown_search.py) is:

```text
edge_mean
+ prior_bonus * exp(proposal_logp)
+ posterior_sd_scale * normal
  / (action_dimension_normalizer * sqrt(edge_visits + 1))
```

The current allocation experiments use the unchanged dimension-normalized,
dense-feedback, scale-16 method. Exact success is still determined by executable
terminal verification. Scale 0 means exact-success-only feedback, **not** a
no-learning control. A future selection-mean-off control would be a different,
explicitly specified intervention; none is implemented by this documentation.

`_preview_backup` traverses the completed path in reverse and applies Welford
mean/second-moment updates using the same terminal return at every edge.
Reverse traversal alone does not make this successor-value Bellman bootstrapping.
The selection formula does not read `m2`; its visit-dependent perturbation is an
exploration proxy, not a calibrated Bayesian posterior. These are descriptions
of the current mechanism, not new algorithm fixes or evidence that learning helps.

Every ordinary selection scores all current legal actions. Proposal cache misses
also evaluate a row of action priors. The greedy-rollout proposal performs
internal deterministic completions; its diagnostic internal work is not fully
represented by the legal-action-score stopping axis. Equal caps, actual charged
work, proposal-internal work and deployment cost must remain separate. See the
[Track A contract](countdown_track_a_search_contract.md) and
[observed work table](observations/countdown_feedback_allocation_recovery_20261024.md#actual-work-under-equal-caps).

## Historical token-prefix / D4 layer

The remaining sections describe the original layer and its dated experiments.
They do not describe the current Countdown DAG, dense terminal update, or a
newly approved experiment. The prototype remains available for provenance.

### Search layers

1. LM logitsからbounded candidate setを作る。
2. candidate representationを探索用strataへ分ける。Q値は共有しない。
3. uncertainty proxyからThompson-style action scoreを作る。
4. coverage routeまたはglobal routeでactionを選ぶ。
5. exact token prefixを次stateとして展開する。
6. terminal/verifier returnをtrajectory後方からBellman backupする。
7. pruning有効時はactive maskだけを変更し、flat prefix storeを破壊しない。

### Objective separation

LM log-probはbehavior/proposal priorで、learned returnそのものではありません。
Bellman backupとreadout successはverifier return側で評価します。この非対称性を
隠して「同じQ目的を最適化している」とは言いません。

### Uncertainty

Welford statisticsとvisit countから作る値は、非定常TD targetに対する探索用proxyです。
独立同分布を仮定した厳密なBayesian posteriorではありません。D4のSD scaleは
learned meanを変えず、このproxyの標準偏差だけを倍率変更します。

### State and graph semantics

この初期実装のstate keyはexact token prefixなので、flat dictionaryに保存したtreeです。
semantic state mergeはしていません。node削除で子孫が自動削除されることもないため、
pruningはmask、物理compactionは別phaseとします。

### Semantic boundary of the original layer

token input embeddingのclusterはoracle-aligned toyではpositive controlになりますが、
自然言語reasoning roleの証拠ではありません。chunk、one-step hidden state、verifier
featureへ進む前に、sampler/routing作用点のablationを終えます。

### Uniform-channel localization

channel ablationでは各nodeで、従来と同じ`2 + A`次元のscrambled Sobol点とIID点を
毎selection一つずつ生成します。座標`0`はcoverage gate、`1`はcluster quantile、
`2:`はaction perturbationです。4条件は座標ごとにどちらの点を使うかだけを変えます。

これは3本の独立streamではなく、二つのjoint full-dimensional pointからの
coordinate assignmentです。両endpointの旧挙動を保持し、unchanged coordinateを
paired profile間で共有するpartial common-random-number設計です。両source生成を含む
wall timeは計測用instrumentation costで、deployment sampler costとは扱いません。

### Fixed-verifier conversion

次段ではsearch中のverifier feedbackを正確に700回へ固定し、LM node、prefix token、
edgeを結果として測ります。1111 LM nodesはsaturationではなく緩いintegrity guardです。
EOSをterminal leafとして展開しない現候補集合のD4 reachable prefix boundは820です。
正常な700 simulationは各1 verifier、最大4 edgesなので、edgeは2800以下でなければ
なりません。3500 edge ceilingは性能予算ではなく配管異常用のguardです。

700回到達後のgreedy readoutはsearch verifier feedbackを消費しないdeterministic
evaluationとして1回別計上します。したがってfixed-verifierはequal total computeでは
なく、verifier-to-node conversionを測る実験です。
