# InsureAI 持续优化计划

> **注（2026-08-27）**：v1.0 阶段计划已完成历史使命，v1.5 阶段的 Issue 级实施计划见 `docs/V1.5_ROADMAP.md`（含 Claim Intelligence、Evidence Graph、Source Tier、False Split、Trend Engine、Decision Card、KG 查询、benchmark v2 等拆解）。

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
- [x] Deployment Verification 最终线上回写状态全链路实测 —— `deployment_verification.json`：`status=verified`、`http_status=200`、`marker_found=true`（2026-08-28 实测）
- [x] Release Provenance 在最新发布上出现 verified 状态 —— `release_provenance.json::deployment` 含 `status/release_match/trend.classification=recovered`
- [x] Claims benchmark 与反证指标 —— `benchmarks/real_v1/baseline.json`：`status=validated`，21 篇真实语料 / 6 正例对 / 6 负例对 / 3 claim 用例，macro_quality=1.0
- [x] Knowledge Graph 第一版 —— `knowledge_graph.json` v3：9517 节点 / 12686 边，`kg_query.py` 提供实体检索、Topic×Entity 交叉、一跳邻居
- [x] Executive Terminal 第二阶段：决策事项聚合、历史趋势与管理层操作闭环 —— `executive_terminal.json` v3 含 what_changed / what_is_accelerating / what_needs_attention / what_needs_human_decision；决策卡六要素 + 8 角色分发（`decision_context_coverage=1.0`）

### 2026-08-28 补充：P2 闭环的两个真实缺陷（已修）

P2「每日情报简报 → 关注清单 → 持续监控 → 决策反馈」此前**只是纸面完成**：单测全跑合成 fixture，从未在真实数据上执行过一次。实际运行暴露两个缺陷，均已修复并锁定回归测试：

| 缺陷 | 根因 | 影响 | 修复 |
|---|---|---|---|
| `p2_intelligence.py` 在真实数据直接崩溃 | `data.json` 顶层是 dict，P2 当 list 传入引擎，`_cluster()` 遍历出字符串 | 每日简报从未产出过 | 新增 `load_news()` 统一取 `data["news"]` |
| 简报排序全为 0，排序形同虚设 | 读 `event["intelligence_score"]`，实际在 `event["scores"]["intelligence_score"]` | 20 条简报优先级全 0，等于随机序 | 新增 `_intelligence_score()` 读嵌套路径 |

同时把 P2 接入主流水线：`daily-collect.yml` 新增构建 + 校验步骤，`p2_daily_brief.json` 进入 audit ledger（29 stages）并加 fail-closed 非空门禁；`test_p2.py` 由 3 个合成用例扩到 8 个，新增真实数据端到端回归。

> 教训：断言写成 `assertGreaterEqual(x, 0)` 等于没有断言。分数类断言必须验证**非零且有序**。

## 当前发布原则

1. 不允许 UI 生成未存在于 artifact 中的事实。
2. 单一来源不得获得独立信源加分。
3. `now` 行动必须同时满足高可信度、足够证据、无冲突和趋势条件。
4. 所有重要判断必须能追溯到 artifact；最终 release 必须能追溯到 source commit。
5. Cloudflare 发布必须先通过静态产物身份校验，再执行线上 marker 验证；验证失败不得标记为 verified。
