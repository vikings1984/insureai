# InsureAI Benchmark

## Purpose

建立与生产数据隔离、可重复执行、可量化比较的核心智能基准，覆盖 Event、Claim/Evidence、Decision 三层安全能力。

## Current benchmark v1

固定人工标注案例：

- Event：同一事件多源报道、相似但不同事件
- Claim/Evidence：多源交叉验证、单源不得升级为 cross_checked
- Decision：冲突或受限事件不得升级为 `now`，必须进入人工复核

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

`benchmark_results.json` 为运行时产物，不提交到仓库，避免把动态结果误当作基准标注。

## Versioning rule

基准标注变化必须同步修改 benchmark version，并经过人工审阅。生产数据不能直接成为 benchmark expected output。