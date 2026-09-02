# InsureAI · Event OS 主链收口改进方案

> 综合来源：Grok 报告 `grok_report.pdf`（图像型，无法直接抽文本，主体以贴出的战略长文为准）+ 战略自评长文 + 仓库实测校准。
> 日期：2026-09-01 起；最后更新 2026-09-02。状态：E1–E3 / S1–S6 已落地、X1 已收口；**X2 Event OS 产品化收敛（评审修订）已拍板 A，Sprint 1 启动**（§9）。

---

## 0. 仓库实测（方案的事实底座）

| 断言（来自长文） | 实测结果 |
|---|---|
| `event_registry.py` / `event_lifecycle.py` / `p2_alerts.json` 不存在 | ✅ **属实**（Glob 全仓未命中） |
| P2 Monitoring 用 `fingerprint` 做跨天连续性 | ✅ 属实（`optimization_backlog.py` 含 `fingerprint` 生成与使用，属产品局部身份） |
| 事件已有 `event_id` | ✅ 属实（`contract.py` 校验 `event_id` 唯一性；各事件带 `evt_...`） |
| 全局 Canonical Event 注册 / 解析层 | ❌ 不存在（无 `canonical` / `resolver` 概念） |

**结论**：事件有"局部身份"（监控 fingerprint + 每事件 event_id），但**没有跨模块的全局 Canonical Event 身份层**。这正是长文"主脊柱未收敛"判断的命门——多个模块未来可能"都在工作，但说的不是同一个事件"。

数据快照（2026-09-02 实测）：事件语料 1634（data.json，非滚动窗口，逐日增长）· 4 Watchlist · 已决 11/100（89 待决，样本 12<30 未解锁偏好结论）· KG 节点 ~9805 · feedback=0 / monitoring=0（采集桥已就位，待真人输入）。
> 性能实测：CI `unittest discover` 全量中，`tests.test_p2.P2WatchlistExpansionTests.test_expanded_watchlists_present_and_surface_in_production` 在 1634 条真实数据上耗时 **72.7s** 且随数据量**二次增长**（`intelligence._cluster` 全对相似度 + 逐对重复计算 `_entities`/`_event_type`）。详见 §8。

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
5. **Executive Home 不增卡片，只换数据源**——从 Dashboard 演进为 Event Operating Console；**事件详情必须升级为 OS 控制台**（CE / 阶段条 / 合并史 / 语义 Alert / 漏斗状态 / Replay），这是挂钩不是新 Dashboard。

---

## 3. 分阶段改进 Backlog

### P0-A · 使能项（主链依赖，先做）

| ID | 项 | 类型 | 解锁的阻塞维度 | 依赖 |
|---|---|---|---|---|
| **E2** | `decision` 加 `decided_at` 时间戳 + 累计决策样本至 ≥30 | 流程 + 轻量工程 | 记忆时间线（structurally_unavailable）、决策偏好结论（insufficient_sample）、Lifecycle.Decision 阶段、Decision Funnel | Human Review 持续落 decision |
| **E1** | KG 实体抽取噪声治理（过滤句首状语片段、限制机构名长度/词性） | 纯工程 | 干净实体 → 更准确的 canonical 解析与 entity_threads（upstream_noise） | 无 |
| **E3** | feedback / monitoring 采集（Review UI 支持 label + 跟踪书签，写入 `p2_state.json`） | 流程 + UX | Lifecycle.Feedback 阶段、个性化信号（empty→有） | 无 |
| **E3** ✅ 已交付 `40c178c` | 新建 `review-ui.html`（修复 executive_home 两处死链）+ 交互化 `review-ui.js`（6 标签 + 跟踪书签，导出 JSON / GitHub Issue）+ fail-closed 导入器 `p2_import_feedback.py` + 契约测试 `test_site_pages.py`；CI 加 py_compile/测试步骤/`p2_state` schema 守卫。**真实 feedback 仍为 0**——采集桥就位，待真人打标签后方解锁 Lifecycle.Feedback 与个性化信号。 | 流程 + UX | Lifecycle.Feedback 阶段、个性化信号（empty→有） | 无 |

### P0-B · 主链脊柱（两文档核心）

> 注：S1–S6 为已落地**引擎原型**（X1 已把它们接入 Home 换源）。X2（§9）在其上**收敛成产品主对象**，不推倒重来；S1/S3 需重写契约，S2/S4/S5/S6/X1/Second Brain/KG 需按 §9 改写。

| ID | 项 | 交付物 | 关键能力 |
|---|---|---|---|
| **S1** | Canonical Event Registry | `event_registry.py` + `canonical_events.json` + `event_id_aliases.json` | `resolve` / `upsert` / `alias` / `merge` / `split` / `migrate` |
| **S2** | Identity Resolver | 把 `optimization_backlog.fingerprint` 升格为全局解析器，映射所有模块引用 → `canonical_event_id` | 跨模块统一事实 |
| **S3** | Acquisition Lifecycle | lifecycle 引擎，阶段源自 Claim+Evidence | rumor→negotiation→agreement→regulatory→closing→integration（先吃透 M&A，复用 `ma` Watchlist） |
| **S4** | Semantic Alert | `p2_alerts.json`，两层 Internal Diff → Semantic Alert | 每日 100+ 底层变化 → 3–8 条 EVENT_STAGE_CHANGED / EVENT_MATERIAL_CHANGED / DECISION_REQUIRED / RISK_INCREASED |
| **S5** | Decision Funnel | `decisions_pending` ← `decision_required` funnel | 承接 E2 |
| **S6** | Replay / Projection | 每 canonical event 的生命周期变化链（stage + Claim + Evidence + Source + AlgoVer） | 与现有"发布时间证据链"区分，回答"为何今天变重要" |

### P1 · 收敛（Executive Home 换源不增卡）

- **X1** ✅ 已交付 `92c824d`：Event Changes 卡换源 `p2_alerts.json`（S4 `semantic_alerts`，实时 8 条）；Decisions Pending 卡换源 `decisions_pending.json`（S5 `top_pending` + `meta.pending_by_tier`，待决 89 / now 13 / soon 22 / watch 54 / 已决 11，样本 12<30 未解锁偏好结论）；所有事件卡以 `canonical_events.json` 的 `canonical_event_id` 为单一事实源锚点（`⌖`，`by_event_id` 兜底）。新增 `tests/test_x1_convergence.py`（9 项：代码契约 + 数据契约 + 单事实源完整性）并接入 `test.yml`。**未新增卡片**——Dashboard→Event Operating Console 仅换源。
- 旧派生路径（`review_queue.change_impact` / `decision===null`）已彻底移除，契约测试 `test_old_review_queue_path_removed` 守护不回归。

---

## 4. 明确不做（降级）

LLM Phase 3 · Interest Model · KG 推理层 · 更多 Dashboard / Watchlist / 角色 · 新模型接入。

> **Freeze 例外（X2，必须放行）**：事件详情→OS 控制台、首页改漏斗出口+语义Alert、Replay 页内时间轴、KG 节点 ID 引用 canonical_event_id——以上为挂钩，不是新功能。

---

## 5. 完成定义（收敛 Sprint 出口）

- 任一真实事件可被所有模块用**同一 `canonical_event_id`** 引用（按 event_type 分区，先窄后宽）；
- **acquisition + regulatory 两类事件**永久知道「是谁 / 在哪一步 / 什么变了 / 该不该决策 / 你上次怎么判断」；
- 每日 100+ 底层变化**收敛为 ≤8 条语义告警**（系统级 T1 + 个人级 watch 两层准入）；
- `decided_at` 落地、决策样本 ≥30 → **记忆时间线与决策偏好结论解锁**；
- **Home 固定三行**（需决策 / 语义变化 / 复核队列），89 待决留复核页、**不进 Executive Home 主数字**。

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
                                                            └──→ X1(Exec Home 换源) ✅ 92c824d
```

> 说明：E2 是单一最高杠杆（解锁 5/7 开放问题），且含流程侧（需 Human Review 落 decision）；E1 是纯工程高 ROI；S1/S2 是脊柱起点，复用既有 event_id + fingerprint，不推倒重来。

> **X2 重切（评审）：两周 5 Sprint → 三周 3 Sprint**，只吃 acquisition+regulatory 两类（见 §9.3），每 Sprint 末跑 Event OS Quality Gate（§9.7），不通过不准加 KG / 新角色 / 新 Watchlist。

---

## 8. 已知技术债（实测，非阻塞）

### T1 · `build_intelligence` / `daily_brief` 二次复杂度（性能债）
- **实测**：1634 条真实新闻上 `daily_brief` 耗时 ~72.7s 单测、~160s 全量；n 翻倍耗时 ×4（典型 O(n²)）。
- **根因**：`intelligence.py:152 _cluster` 全对相似度；内部 `_event_type`/`_entities`/`_norm` 逐对重复计算（无记忆化）。cProfile：`_event_type` 310,998 次、`_entities` 441,252 次、`re.sub` 933,805 次（n=400）。
- **影响面**：`p2_intelligence.py` 在 `daily-collect.yml` + `test.yml` 均被调用 → CI 该步随 data.json 增长二次变慢（data.json 当前 1634、非滚动窗口，长期累积）。
- **状态**：与 E3 无关（E3 未触碰 intelligence 评分路径）。**待办**：先加 `_entities`/`_event_type` 记忆化（~常量级加速、行为可字节校验），再视需引入分桶/阻断策略消除 O(n²)。属独立优化，不在本 Sprint 强制出口。
- **纪律约束**：行为须保持确定性——优化后 `intelligence.json` 关键字段需与现状对齐（回归测试 `test_intelligence*` 已覆盖），严禁为提速改变事件合并/评分结果。

---

## 9. X2 · Event OS 产品化收敛（评审修订，已拍板 A）

> 触发：用户贴专家复审长文。评审结论——**方向对；范围过大、生命周期过专、Freeze 误伤了唯一该改的界面**；三处假完成陷阱（收购六段当通用生命周期 / Canonical 全量迁移 1578 条 / Semantic Alert 只靠 Watchlist）。
> 已于 `EVENT_OS_PLAN_REVISION.md` 形成修订草案，用户拍板 **A**（采纳草案，Sprint 1 = 收购+监管 两类），本节约其权威折回。

### 9.1 保持不动（评审确认 7 条）
Canonical Identity 为 P0 · 阶段来自 Claim+Evidence · `NEW_SOURCE` 留内部、阶段变化才上首页 · Funnel 消灭 89 pending · Watchlist 停扩维改理解命中 · Second Brain 停加角色改事件记忆 · fail-closed 不伪造偏好。

### 9.2 四處必改（契约，写入 schema）
1. **生命周期 domain 插件**：`lifecycle.domain = acquisition|regulatory|catastrophe|other`；`lifecycle.stage` 仅 acquisition 用六段 `rumor→negotiation→agreement→regulatory→closing→integration`；`regulatory` 只 `status + issued/effective`；`other` `stage=null`。禁止默默通用化（S3 重写）。
2. **Canonical 按 event_type 分区、先窄后宽**：acquisition/regulatory 必 canonicalize；product/personnel/industry_update 只 alias 不 merge；split 人工门；**30 条标注集质量门（false merge=硬失败）**（S1 已落地 er-v1.1 + `canonical_annotation_set.json`）。
3. **Semantic Alert 两层准入**：系统级 T1 监管/协会 + 阶段或效力变化；个人级 Watch 命中 + 语义变化；`NEW_SOURCE`/`NEW_EVIDENCE` 不上首页；`NEW_CLAIM` 矛盾已交叉验证命题 → `EVENT_MATERIAL_CHANGED`（S4 改）。
4. **范围重切**：两周 5 Sprint → 三周 3 Sprint，只吃 acquisition+regulatory（见 9.3）。

### 9.3 三周 3 Sprint 排期
| Sprint | 范围 | 落地段 | 出口（Quality Gate） |
|---|---|---|---|
| **S1** | Canonical Identity（收购+监管） | S1 er-v1.1 分区 + S2 分区解析 + 事件详情露出 `CE_xxxx` + KG 节点引用 CE | 30 标注集 false merge=硬失败（✅ 已实现：er-v1.1 + `canonical_annotation_set.json` + `tests/test_canonical_annotations.py`） |
| **S2** | Acquisition Lifecycle + Semantic Alert | S3 domain 插件(acquisition 先) + S4 两层准入 + X1 Home 改三行 | 多源合一 CE / 必拆 CE / 阶段只来自 Claim+Evidence |
| **S3** | Decision Funnel + Replay + 事件记忆 | S5 六条件+分角色 + S6 页内时间轴 + Second Brain FK=CE(冻结角色) + X1 收尾(89 留复核页) + E3 反馈挂 CE | 漏斗分角色计数 / Home 三行固定 / 89 不在主数字 |

### 9.4 Decision Funnel 六条件（同时满足才 Decision Required）
1. 在监控(Watch/曾标重要/曾 acted_on) **或** 系统级 T1 监管；2. 存在语义变化（阶段/关键命题），不是又来一个源；3. 阶段属可决策集（收购 agreement/regulatory/closing）；4. 证据覆盖+可信度过门，**单源+监管/评级不得出 Decision Required**；5. 该 CE 本角色下未处理（无 `decided_at` 或反馈非 snoozed/resolved）；6. fail-closed：推不出进 Open Question。漏斗**分角色计数**；Home 固定三行（需决策/语义变化/复核队列），89 留复核页。

### 9.5 Second Brain / 时间语义：改挂钩不改加页
冻结角色；记忆外键 = `canonical_event_id`；时间属性 `published_at / ingested_at / decided_at / acted_at`（实体时间线=发布时间证据链，禁冒充决策时间线）；Watchlist 三维 `entity|topic|event_type`，用反馈调权重，四类(AI/并购/监管/健康险)冻结。

### 9.6 Feature Freeze 例外（§4 已列）
事件详情→OS 控制台、首页改漏斗出口+语义Alert、Replay 页内时间轴、KG 节点引用 CE——挂钩不是新功能。KG 推理继续不做。

### 9.7 质量门（每 Sprint 跑）
同一收购多源→一个 CE；Zurich Farmers vs Cover-More→两个 CE；中保协车险指南 vs 非车险治理→两个 CE；无 Claim/Evidence 禁阶段前进；非法回跳(closing→rumor)→reviewRequired 不写库；低证据禁 `urgency=now` 与 Decision Required；Home 产品 Alert 不含 `NEW_SOURCE`。基线：`canonical_annotation_set.json`（30 条）。

### 9.8 评分修正
Event OS 核心主链 60 → **目标 80（三周后）**，不写 95；Second Brain 70 维持，接 CE 后到 80。

### 9.9 落地映射（X2 对已交付段的改动）
| 段 | X2 改动 |
|---|---|
| S1 Registry | ✅ er-v1.1：event_type 分区 + domain + key_entity + `should_merge` + `validate_against_annotations` + split 人工门 |
| S2 Resolver | 按 event_type 分区解析；`generic_entities_only` 进复核不进 CE；legacy alias |
| S3 Lifecycle | 通用六段→domain 插件；acquisition 先；regulatory 只 status；other stage=null |
| S4 Alert | 两层准入；NEW_SOURCE/NEW_EVIDENCE 不上首页 |
| S5 Funnel | 六条件硬化 + 分角色计数；89 留复核页 |
| S6 Replay | 页内时间轴优先 |
| X1 Home | 固定三行；监管 T1 无 watch 命中也系统级高严重度进首页；89 移出主数字 |
| Second Brain | 冻结角色；FK=canonical_event_id |
| KG | 节点 ID 引用 canonical_event_id |
| E1/E2/E3 | 保持（E2 扩 acted_at） |

### 9.10 Sprint 1 进度（当前）
- ✅ `event_registry.py` er-v1.1：CANONICALIZE_POLICY / event_type_domain / may_auto_merge / should_merge / validate_against_annotations / split 人工门；build 记录 domain+key_entity（向后兼容 X1 的 by_event_id/count）。
- ✅ `canonical_annotation_set.json`：30 条标注（必合/必拆/alias-only/跨类型/缺类型），质量门基线。
- ✅ `tests/test_canonical_annotations.py`：12 项（策略 / should_merge / 30 标注门 / split 人工门 / build 向后兼容），全绿。
- ✅ `canonical_events.json` 重建为 er-v1.1（141 canonical，domain/key_entity 增补，by_event_id/count 不变）。
- ⬜ 余下 Sprint 1：S2 分区解析接入、`事件详情`页露出 `CE_xxxx`、KG 节点引用 CE、CI 加 test_canonical_annotations。
