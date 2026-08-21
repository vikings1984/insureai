# Scenario Decision Matrix

## 第一性原理

未来不确定时，最优策略通常不是押注一个场景，而是优先采取：

1. 跨多个情景仍然成立的动作；
2. 可逆、低沉没成本的动作；
3. 能保留未来选择权的动作；
4. 有明确升级/降级触发条件的动作。

因此 `scenario_matrix.json` 不输出“哪个情景最可能”，而输出：

- `robust_actions`：在至少两个情景中都存在的稳健行动；
- `scenario_specific_actions`：只适用于某一情景的准备动作。

`robust=true` 只代表跨情景适用，不代表业务上一定应该执行。

## 边界

- 没有至少两个情景时，不生成稳健行动矩阵，避免制造虚假的稳健性；
- 不替代承保、投资、合规或管理决策；
- 所有行动建议都应该回溯到 Scenario、Temporal、Trust 与 Evidence 层。
