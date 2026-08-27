# InsureAI Benchmark

## Purpose

建立与生产数据隔离、可重复执行、可量化比较的核心智能基准，覆盖 Event、Claim/Evidence、Decision 三层安全能力。

## Current benchmark v1.0 — locked baseline

固定人工标注案例：

- Event：同一事件多源报道、相似但不同事件
- Claim/Evidence：多源交叉验证、单源不得升级为 `cross_checked`
- Decision：允许的高证据 `now` 与冲突事件人工复核边界

### Locked baseline

在当前候选版本上，依据仓库中的确定性 Benchmark Runner 与固定 fixture，预期基线为：

```text
macro_quality = 1.0000
Event precision = 1.0000
Event recall = 1.0000
Event false_merge_rate = 0.0000
Claim cross_check_accuracy = 1.0000
Claim single_source_state_accuracy = 1.0000
Claim single_source_false_cross_check_rate = 0.0000
Decision unsafe_now_rate = 0.0000
Decision human_review_recall = 1.0000
```

这些数值由固定测试案例定义，并由 CI 在每次变更中重新计算验证；任何偏离都必须作为回归处理，而不是通过放宽门槛解决。

## Metrics

- Event precision / recall
- Event false merge rate
- Claim cross-check accuracy
- Single-source false cross-check rate
- Multi-source evidence coverage
- Decision unsafe-now rate，目标为 `0`
- Human-review recall
- Macro quality，当前 CI 门槛 `>= 0.95`

## CI

`.github/workflows/benchmark.yml` 在 push、pull request 和手工运行时执行 benchmark runner 与 regression tests。

`benchmark_results.json` 为运行时产物，不提交到仓库；固定 baseline 只维护在本文件与测试契约中，避免把动态结果误当作基准标注。

## Versioning rule

基准标注变化必须同步修改 benchmark version，并经过人工审阅。生产数据不能直接成为 benchmark expected output。Benchmark v1.0 发布后默认冻结，只允许新增 v2 cases，不修改 v1 expected outputs。
