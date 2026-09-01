# InsureAI · Event OS 主链收口改进方案

> 综合来源：Grok 报告 `grok_report.pdf`（图像型，无法直接抽文本，主体以贴出的战略长文为准）+ 战略自评长文 + 仓库实测校准。
> 日期：2026-09-01。状态：规划草案（未提交）。

---

## 0. 仓库实测（方案的事实底座）

| 断言（来自长文） | 实测结果 |
|---|---|
| `event_registry.py` / `event_lifecycle.py` / `p2_alerts.json` 不存在 | ✅ **属实**（Glob 全仓未命中） |
| P2 Monitoring 用 `fingerprint` 做跨天连续性 | ✅ 属实（`optimization_backlog.py` 含 `fingerprint` 生成与使用，属产品局部身份） |
| 事件已有 `event_id` | ✅ 属实（`contract.py` 校验 `event_id` 唯一性；各事件带 `evt_...`） |
| 全局 Canonical Event 注册 / 解析层 | ❌ 不存在（无 `canonical` / `resolver` 概念） |

**结论**：事件有"局部身份"（监控 fingerprint + 每事件 event_id），但**没有跨模块的全局 Canonical Event 身份层**。这正是长文"主脊柱未收敛"判断的命门——多个模块未来可能"都在工作，但说的不是同一个事件"。

数据快照（上一轮实测）：事件语料 1554/1578 · 4 Watchlist（275 命中）· 已决 11/100（89 待决）· KG 9805 节点 · feedback=0 / monitoring=0。

---

## 1. 总判断（两文档共识 + 实测校准）

- **外围能力完成度高**：采集 / Event Intelligence / Claim·Evidence / Daily Brief / Watchlist / Continuous Monitoring / KG / Personal Memory / Second Brain / Executive Home 均 🟢。
- **主脊柱 Event OS 未收敛**：稳定事件身份 🟡、生命周期 🟡、语义级变化 🟡、决策告警 🟡、跨模块统一事实 🟡、事件完整回放 🟡。
- **最该警惕的不是"功能少"，而是"横向功能增长快于纵向主链建设"**——模块越多，身份分裂风险越大。
- 当前应从"向外长"转为"向内收"。

---

## 2. 设计原则（不可妥协）

1. **单一事实源**：所有模块引用 `canonical_event_id`，不再各自持有 event_id / fingerprint 版本。
2. **阶段来自 Claim + Evidence，不来自标题**——这是治 `false_merge` / `false_split`（P1-4.1 已暴露）的根。
3. **Second Brain 保持确定性**：LLM Phase 3 暂缓，直到 feedback 样本足够（继承现有纪律：只读事实、不伪造偏好、sample<30 不结论）。
4. **纪律继承**：fail-closed 校验、observation/conclusion 分离、open_questions 显式记录。
5. **Executive Home 不增卡片，只换数据源**——从 Dashboard 演进为 Event Operating Console。

---

## 3. 分阶段改进 Backlog

### P0-A · 使能项（主链依赖，先做）

| ID | 项 | 类型 | 解锁的阻塞维度 | 依赖 |
|---|---|---|---|---|
| **E2** | `decision` 加 `decided_at` 时间戳 + 累计决策样本至 ≥30 | 流程 + 轻量工程 | 记忆时间线（structurally_unavailable）、决策偏好结论（insufficient_sample）、Lifecycle.Decision 阶段、Decision Funnel | Human Review 持续落 decision |
| **E1** | KG 实体抽取噪声治理（过滤句首状语片段、限制机构名长度/词性） | 纯工程 | 干净实体 → 更准确的 canonical 解析与 entity_threads（upstream_noise） | 无 |
| **E3** | feedback / monitoring 采集（Review UI 支持 label + 跟踪书签，写入 `p2_state.json`） | 流程 + UX | Lifecycle.Feedback 阶段、个性化信号（empty→有） | 无 |

### P0-B · 主链脊柱（两文档核心）

| ID | 项 | 交付物 | 关键能力 |
|---|---|---|---|
| **S1** | Canonical Event Registry | `event_registry.py` + `canonical_events.json` + `event_id_aliases.json` | `resolve` / `upsert` / `alias` / `merge` / `split` / `migrate` |
| **S2** | Identity Resolver | 把 `optimization_backlog.fingerprint` 升格为全局解析器，映射所有模块引用 → `canonical_event_id` | 跨模块统一事实 |
| **S3** | Acquisition Lifecycle | lifecycle 引擎，阶段源自 Claim+Evidence | rumor→negotiation→agreement→regulatory→closing→integration（先吃透 M&A，复用 `ma` Watchlist） |
| **S4** | Semantic Alert | `p2_alerts.json`，两层 Internal Diff → Semantic Alert | 每日 100+ 底层变化 → 3–8 条 EVENT_STAGE_CHANGED / EVENT_MATERIAL_CHANGED / DECISION_REQUIRED / RISK_INCREASED |
| **S5** | Decision Funnel | `decisions_pending` ← `decision_required` funnel | 承接 E2 |
| **S6** | Replay / Projection | 每 canonical event 的生命周期变化链（stage + Claim + Evidence + Source + AlgoVer） | 与现有"发布时间证据链"区分，回答"为何今天变重要" |

### P1 · 收敛（Executive Home 换源不增卡）

- **X1**：Event Changes ← `p2_alerts`；Decisions Pending ← decision funnel；Watchlist / Second Brain / KG ← canonical event。Dashboard → Event Operating Console。

---

## 4. 明确不做（降级）

LLM Phase 3 · Interest Model · KG 推理层 · 更多 Dashboard / Watchlist / 角色 · 新模型接入。

---

## 5. 完成定义（收敛 Sprint 出口）

- 任一真实事件可被所有模块用**同一 `canonical_event_id`** 引用；
- M&A 事件能展示**完整生命周期 + Replay**；
- 每日 100+ 底层变化**收敛为 ≤8 条语义告警**；
- `decided_at` 落地、决策样本 ≥30 → **记忆时间线与决策偏好结论解锁**。

---

## 6. 与上一轮评估的关系

上一轮（基于真实产物）给出的 P0（决策样本 + `decided_at`）/ P1（KG 噪声）/ P1（feedback·monitoring）在此方案中归并为 **E1 / E2 / E3 使能项**——它们是 Event OS 主链的必要前提，而非替代主链。二者一致：先把"稳定事件身份 + 决策时间戳 + 干净实体 + 反馈信号"四项地基锁死，主链才有意义。两文档（Grok + 战略自评）补上的，是把这些使能项串成一条**以 Canonical Event 为主脊柱的收敛路线**，并明确"停止向外长功能"。

---

## 7. 建议的落地顺序（依赖链）

```
E1(KG噪声) ─┐
E2(decided_at+样本) ─┼─→ S1(Registry) → S2(Resolver) → S3(Lifecycle) → S4(Semantic Alert)
E3(feedback) ───────┘                                  │            │
                                                       S5(Funnel)   S6(Replay)
                                                            │            │
                                                            └──→ X1(Exec Home 换源)
```

> 说明：E2 是单一最高杠杆（解锁 5/7 开放问题），且含流程侧（需 Human Review 落 decision）；E1 是纯工程高 ROI；S1/S2 是脊柱起点，复用既有 event_id + fingerprint，不推倒重来。
