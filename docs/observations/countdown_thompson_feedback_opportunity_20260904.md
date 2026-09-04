# Countdown Thompson: feedback opportunity and observed conversion

Date: 2026-09-04. Post-hoc audit of existing evidence only.

## Bottom line

Scale 16の48 task/seed pairsは、次の観察上の段階に分けられた。

```text
異なるfeedback値を受け取った           48
  → その後に最初のactionが分岐した     15
    → 分岐後に1本以上を完走できた       9
      → 共通prefixの最良誤差を更新した 4
        → baseline失敗から新規正解へ   1
```

ここで「完走」は、分岐したtrajectory自身を含め、そのselection後に
`terminal_verified`と対応するbackupが記録されたことをいう。
15組のうち6組は、分岐したtrajectory自体を完走できず、その後の完了terminalも
なかった。残る9組のうち8組は分岐後の完了terminalが1本だけ、1組は2本以上だった。

したがって、観察された新規正解率は次の**件数の恒等式**で表せる。

```text
1/48 = (15/48) × (9/15) × (4/9) × (1/4)
        分岐      完走     最良値更新   正解化
```

これは独立性の仮定でも、将来の成功確率の推定でもない。介入後の条件で分けた
同じ48組の記述であり、どの段階に未変換の事例が残るかを明示するための分解である。
「開発の進歩を測りやすくする」と「探索性能そのものが線形に向上する」は別の主張で、
今回改善したのは前者の観察可能性である。探索本体は変更していない。

## All scales and denominators

完了本数はscaled側の分岐後terminal数。分岐しなかった組はこの3区分へ入れず、
各scaleの分母48に残している。「prefix更新」は共通prefixの最良誤差を下回った
組数で、正解を含む。「対0 W/T/L」は全48組の最終最良誤差をscale 0と比較したもの。

| scale | 分岐 / 48 | 分岐後完了0本 / 1本 / 2本以上 | prefix更新 / 新規正解 | 対0 W/T/L |
|---:|---:|---:|---:|---:|
| 1 | 1 | 1 / 0 / 0 | 0 / 0 | 0 / 48 / 0 |
| 2 | 2 | 2 / 0 / 0 | 0 / 0 | 0 / 48 / 0 |
| 4 | 4 | 2 / 1 / 1 | 0 / 0 | 0 / 48 / 0 |
| 8 | 7 | 4 / 2 / 1 | 1 / 0 | 1 / 47 / 0 |
| 16 | 15 | 6 / 8 / 1 | 4 / 1 | 4 / 43 / 1 |
| 32 | 18 | 7 / 10 / 1 | 4 / 1 | 4 / 43 / 1 |
| 64 | 22 | 9 / 11 / 2 | 6 / 1 | 5 / 41 / 2 |

Scale 1と2では、観測された分岐のすべてが未完走に終わった。「分岐後の候補を
評価したが改善しなかった」とは違う。Scale 16でも40%（6/15）がこの区分だった。
一方、scale 16の完走できた9組には、prefix更新4組、同値1組、prefixより悪い
suffix最良値4組がある。機会の制約だけで全結果を説明できるわけではない。

Prefixより悪いsuffixは、それまで保持していた最良値の悪化を意味しない。
またprefix更新とbaselineへの勝利は別の比較である。Scale 64のprefix更新は6組、
baselineへの勝利は5組であり、この2つを同じ「改善率」にまとめてはいけない。

Scale 16のbaseline比較を分けると、非分岐33組と分岐後完了0本の6組は全てtie、
完了1本の8組は4 wins / 3 ties / 1 loss、完了2本以上の1組はtieだった。
完走例だけを分母にして全体の性能を主張しない。

最初のscale依存backup後の完了数も少ない。Scale 16の全48組で、その後に完了した
terminalは1本が33組、2本が12組、3本が3組だった。これは「利用できたfeedback
以降の観測量」の記述であり、追加予算で救済できるという証拠ではない。

## The one rescue, with its actual window

Task `a4eb31a5ad2b144a738124ec719a2d30331658b19d0eb6996c007fa2c80710b5`、
seed `7168`では、3回の共通prefix backup後、trajectory 3 / depth 0で分岐した。
Scale 0は`5+10`、scale 16は`4*4`を選んだ。

- 共通prefixの誤差: `[90,5484,1984]`、最良値90。
- 分岐後の完了は両側とも1本。Scale 0の誤差は115、scale 16は0。
- 分岐stepに対応するchargeの直前のlegal-action残予算は両側77、直後は58。
- Scaled側の最終残予算は13だが、次のatomic stepは19を要したため停止。
  未受理の19を消費量に足していない。残予算ゼロと予算による停止は同義ではない。
- Scaled actionのscore増分は約0.053951。元の負け幅は約0.038304で、変更後の
  勝ち幅は約0.015646だった。正確なbinary64由来の有理数はreceiptに残した。

Scale 16/32/64の3つの新規正解entryは、すべてこの同じtask/seedである。
独立した3件の救済ではなく、**1 task、1 task/seed pair**の救済である。

## What to test next — proposal only

次の候補は、feedbackの値の式を変えず、**scale 0 / 16 × 現行予算 / 2倍予算**を
対応させた小さな2×2設計である。各予算の中で同じtask/seed・同じ資源上限の2手法を
比較し、予算増で両手法が改善するだけなのか、feedback側の上積みが広がるのかを分ける。

```text
feedbackの上積み(B) = success(scale16, B) - success(scale0, B)
次に見る差 = 上積み(2B) - 上積み(B)
```

これは未実施の修正開発案であり、今回の監査が追加予算の有効性を証明したわけではない。
新しいcohort、seed、予算vector、非primary guardの余裕、評価指標と停止規則は
別途固定し、reviewと認可を経る。分岐後に完走した例だけに絞る評価は主指標にしない。
Scale 16は今回のdevelopmentで選ばれた設定であり、一般的な最適値とは扱わない。

## Evidence and limits

固定した[監査定義](../strategy/countdown_thompson_dense_feedback_opportunity_audit.md)は、
追加集計前のcommit `da48408f70899068e6fdd2dc6a8cdbc9c120835b`にある。
ただし元の結果は既知だったため、事前登録や新しい確認試験ではない。

[Canonical audit receipt](../results/countdown_thompson_feedback_opportunity_v1/audit.json)
は384セル・336比較の全件を保持し、元の9入力ファイルのSHA-256、event hash chain、
7軸の受理chargeの合計、元summaryとの整合を確認した。監査statusはPASS。
監査内の新規探索、生成的replay、provider呼出しはすべて0だった。
PR #24の既往replay PASSとは区別する。

元の判定`STOP_REPAIR_NO_LOCKED_128_RUN`は変更していない。追加run、認可の再利用、
locked 128、confirmation、QMCの優位性、一般的な知能向上への外挿は行わない。
