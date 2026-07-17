# Engineering north star

## Destination

目標は、数理的に説明できるだけのsearchではなく、固定された意味のある予算で
強く、計算資源の使い方が良く、観察して面白いreasoning-time searchです。

数理・統計は次のために使います。

- 実装バグと本当のアルゴリズム差を分ける。
- 何が効いたかを作用点単位で切り分ける。
- seed、budget、候補集合の不公平を除く。
- 負の結果を再利用可能な設計判断へ変える。

## Four gates

### 1. Correctness gate

再現性、予算上限、candidate identity、strict JSON、terminal backup、非破壊pruning。
ここを通らない結果は性能比較に使わない。

### 2. Search-strength gate

固定LM-node / verifier / edge budgetで、success、best return、time-to-hitを比較する。
平均だけでなくseed間安定性と失敗モードも残す。

### 3. Behavioral-interest gate

探索が単に均一かではなく、意味の異なる仮説、反転、計算、収束をどう配分するかを
観察する。面白さは可視化可能な探索軌跡と反実仮想ablationで評価する。

### 4. Systems gate

KV-cache、candidate refresh、batching、verifier latency、memory boundを含め、
実際のtest-time compute allocationとして得かを測る。

## Current decision

D4ではcombined Sobol engineがcoverageを強く均一化した一方、successはIIDより低い。
次にembeddingを複雑化すると原因が混ざるため、まずuniform sourceの作用点を分離する。

```text
iid_all
sobol_all
sobol_routing_only   = Sobol gate/cluster + IID action noise
sobol_action_only    = IID gate/cluster + Sobol action noise
```

このablationでaction-onlyがneutral/positive、routing-onlyがnegativeなら、損失を
semantic routingの過度な規則化へ局在できる。その後にchunk/contextual actionへ進む。

Primary localizationは既存D4の発見cohortを再利用せず、fresh exploration seed
256–511で固定する。SD 1.0をprimary、過去結果から選ばれたSD 0.5をengineering
sensitivityとし、途中結果でreplicate数や条件を変更しない。routing/action/interactionは
同一seed-block bootstrapのsimultaneous intervalで読む。

full resultでは成功main effectは未確定だったが、Sobol routing条件は同じLM-node capへ
少ないverifier/edge workで到達した。次は表現を増やさず、fresh seed 512–639・verifier
cap 700で、この再訪削減が追加nodeとsuccessへ変換されるかを測る。
1111はLM saturationではなくconservative integrity ceilingとし、実到達可能prefix上限
820より前に止まらないためのguardとして扱う。全runでverifier exactly 700、LM<1111、
edge≤2800かつedge<3500を満たさなければ、valid rowだけを選ばず実験全体を失敗とする。

## Promotion rule

新機構はtoyで「動く」だけでは昇格しません。少なくとも次を満たしてから実LLM段階へ
進めます。

- matched computeでbaselineを上回る、または同等成功率を明確に低い総費用で達成。
- seedを増やしても方向が大きく反転しない。
- 改善が一つのoracle partitionだけに依存しない。
- 失敗時に何を探索したか説明できるdiagnosticを持つ。
