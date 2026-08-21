# Scenario Decision Matrix

## 第一性原理

未来不确定时，优先选择跨多个情景仍然成立、可逆、保留选择权、并有明确升级/降级阈值的动作，而不是押注单一未来。

`scenario_matrix.json` 输出：

- `robust_actions`：在当前至少两个情景下都成立的稳健动作；
- `scenario_specific_actions`：只针对某一情景的准备动作。

## 边界

- 少于两个情景时不声称“稳健”；
- `robust=true` 不等于业务上一定应该执行；
- 不输出情景发生概率；
- 不替代承保、投资、合规或管理决策。
