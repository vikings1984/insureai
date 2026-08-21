# Scenario Intelligence

## 目的

Scenario Intelligence 不是预测器，而是把当前已经观测到的事件、可信度和时间趋势转换成显式的“如果……那么……”假设，帮助用户做压力测试和后续监测。

## 四条原则

1. **事实与假设分离**：场景必须引用当前的 `intelligence_score`、`trust_level` 和 `temporal_phase`。
2. **支持强度 ≠ 概率**：`support_level` 只是当前证据对该假设的支持程度，不代表发生概率。
3. **场景必须可证伪**：每个场景都定义后续应观察的信号。
4. **不直接改变决策**：场景层只提供推演，不自动提高 Decision urgency。

## 当前场景

- `trend_accelerates`：趋势继续加速
- `trend_cools`：趋势降温
- `regulation_leads`：监管先行
- `competition_follows`：竞争跟随

## 使用方式

日常流程为：

`Event → Trust → Temporal → Decision → Scenario → Human Review`

当情景的关键输入变化会导致结论变化时，应结合 Counterfactual Evaluation 进行复核，而不是把场景当成预测结果。
