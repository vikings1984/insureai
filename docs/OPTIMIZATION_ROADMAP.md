# InsureAI 持续优化计划

> 目标：把 InsureAI 从“资讯聚合 + 智能分析”持续收敛为可验证的 Insurance Intelligence & Decision Support Platform。

## 总体链路

Signal → Event → Claim → Evidence → Trust → Insight → Decision → Human Review → Release Provenance → Executive Terminal

## 阶段执行表

| 阶段 | 目标 | 主要工作 | 完成标准 |
|---|---|---|---|
| P0 | 单一发布链 | Claim/Evidence 纳入 Daily Collect 主流水线；统一 audit / manifest / provenance | 主流水线生成 claims.json 且被审计 |
| P0 | CI 稳定 | Claim schema、Claim builder、Decision guardrail 回归测试 | 全量测试 + Intelligence Contract 全绿 |
| P1 | Event Intelligence | Event Detail 中按 Claim 展示 Evidence、独立信源、状态 | 用户可从 Event 直接追到 Claim/Evidence |
| P1 | Decision View | 每个事件展示 urgency、human review、basis、guardrail | 所有行动建议可追溯 |
| P1 | 发布可靠性 | Cloudflare 串行部署、release marker、主发布链线上 verification；定时验证作为兜底 | 每次 Cloudflare 发布后直接完成线上验收并回写状态 |
| P2 | Executive Terminal | Radar、重点事件、风险、待决策事项统一首页 | 管理层无需阅读新闻流即可完成每日情报浏览 |
| P2 | Benchmark | 建立事件聚类、Claim/Evidence、Decision 安全基准 | 算法变更可量化比较 |
| P2 | Knowledge Graph | Company / Person / Product / Event / Regulation 关系 | 从新闻检索升级到关系检索 |

## 当前执行状态

- [x] Evidence Gate：低证据默认 watch + human review
- [x] Event Fingerprint：实体 + 事件类型 + 时间窗
- [x] Signal Layer：战略 / 监管 / 市场 / 技术 / 财务
- [x] Intelligence Command Center：已进入主站
- [x] Claim/Evidence builder：已实现
- [x] Claim/Evidence 纳入唯一主发布链
- [x] Event → Claim → Evidence → Decision 页面闭环基础能力
- [x] 全量测试与 Intelligence Contract 稳定通过
- [x] Executive Terminal 第一版：artifact + 页面 + Daily Collect 自动生成
- [ ] Deployment Verification 最终线上回写状态全链路实测
- [ ] Release Provenance 在最新发布上出现 verified 状态
- [ ] Claims benchmark 与反证指标
- [ ] Knowledge Graph 第一版
- [ ] Executive Terminal 第二阶段：决策事项聚合、历史趋势与管理层操作闭环

## 当前发布原则

1. 不允许 UI 生成未存在于 artifact 中的事实。
2. 单一来源不得获得独立信源加分。
3. `now` 行动必须同时满足高可信度、足够证据、无冲突和趋势条件。
4. 所有重要判断必须能追溯到 artifact；最终 release 必须能追溯到 source commit。
5. Cloudflare 发布必须先通过静态产物身份校验，再执行线上 marker 验证；验证失败不得标记为 verified。
