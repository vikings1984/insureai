# InsureAI Evaluation Metrics

## 为什么需要 Metrics

`evaluation.py` 的 `pass_rate` 只能回答“回归用例是否通过”，不能区分错误类型。第二层评估因此增加可解释指标：

| 指标 | 含义 | 目标 |
|---|---|---:|
| Event precision | 被合并的文章对中，真正同一事件的比例 | ≥ 0.95 |
| Event recall | 应合并的事件对中，实际被合并的比例 | ≥ 0.95 |
| False merge rate | 不同事件被错误合并的比例 | ≤ 0.05 |
| Cross-check precision | 被标记为交叉验证的事实中，真正有独立来源支持的比例 | ≥ 0.95 |
| Single-source false cross-check rate | 单一信源被错误升级为交叉验证的比例 | 0 |
| False trend rate | 没有有效时间数据却产生趋势信号的比例 | 0 |
| Unsafe-now rate | 不满足高可信约束却进入“现在关注”的比例 | 0 |
| Guardrail coverage | 决策建议带有明确护栏的比例 | 1 |

## 当前基准集

`evaluation_cases.json` 保留可追加的 regression corpus。新发现的生产错误应优先加入 corpus，再修复实现；不要为了通过测试而降低阈值。

当前基准覆盖：事件聚类、Claim→Evidence、Temporal、Decision 四层。

## Production Replay

`production_replay.py` 使用真实 `data.json` 进行分层抽样回放，并通过改变输入顺序验证 Event Partition 稳定性；当真实数据为空时输出 `unavailable`，不伪造质量结果。

## Gate

CI 对 `macro_quality` 设置 0.95 下限。任何指标恶化都应先解释原因，再决定是否修改算法或扩充基准集。
