# InsureAI · Event OS 收敛方案修订（X2：评审复审）

> 基线：`EVENT_OS_CONVERGENCE_PLAN.md`（v2026-09-02，E1–E3 / S1–S6 已落地、X1 已收口）。
> 触发：用户贴出的专家复审长文。结论——**方向对；范围过大、生命周期过专、Freeze 误伤了唯一该改的界面**；有三处会把"主心骨"做成假完成。
> 本文定位：评审通过前的修订草案（不改动主方案）。评审通过后折回主方案，成为 **X2** 起点。

---

## 0. 评审结论（一句话 + 三处假完成陷阱）

**结论**：主线判断对，两周五 Sprint 切法过满，生命周期模板过窄。该收敛到 Event OS，不该再横向加模块；但方案里有三处会把"主心骨"做成假完成：

| # | 假完成陷阱（方案现状） | 实质 |
|---|---|---|
| A | 收购六段 `rumor→negotiation→agreement→regulatory→closing→integration` 当通用生命周期 | 套到车险指南/非车险治理/分红险会得到假阶段，比没有更糟 |
| B | Canonical Identity 全量迁移 1578 条 Event | 主题型事件实体弱、时间窗长，Jaccard 0.55 会 false merge |
| C | Semantic Alert 准入只靠 Watchlist | 冷启动首页空；中保协/金融监管总局 T1 发文会被漏掉 |

**评审已确认合理的 7 条（保持不动）**：
1. Canonical Identity 为 P0（无稳定 `CE_xxxx`，Memory/KG/Feedback 都会漂）；
2. 阶段来自 Claim+Evidence，不来自标题正则；
3. `NEW_SOURCE` 留内部，阶段变化才上首页（Intelligence Alert 与 Monitoring Diff 的分界）；
4. Decision Funnel 消灭 89 pending（Home "待决策" = 漏斗出口，不是待办堆）；
5. Watchlist 停扩维，改成理解命中（再加财/寿/车险退回关键词表）；
6. Second Brain 停加角色，改成事件记忆；
7. Fail-closed、不伪造偏好（质量门不放松）。

---

## 1. 必须改的四处 → 可执行项

### 1.1 生命周期不做成通用六段 → `lifecycle.domain` 插件

**契约（写进 schema，禁止默默通用化）**：
```
lifecycle.domain = acquisition | regulatory | catastrophe | other
lifecycle.stage  = 该 domain 的枚举 | null
lifecycle.status = emerging | active | cooling | resolved | terminated | denied
```
- **Sprint 2 只实现 `acquisition`**：六段 `rumor→negotiation→agreement→regulatory→closing→integration` **仅限 acquisition**。
- **`regulatory` 这一期只标 `status` + `issued / effective`**，不硬塞 negotiation。
- **`other` 允许 `stage = null`**：只走 Canonical ID + 证据，不准编阶段。
- 否则 P0 身份刚稳住，P1 就用错误状态机把不同现实事件"对齐"到收购剧本。

**改动归属**：S3（Lifecycle）重写——从"通用六段"改为 domain 插件；`acquisition` 先实现，`regulatory` 只 status，`other` stage=null。

### 1.2 Canonical Identity 按 `event_type` 分区，先窄后宽

当前解析已有 `eventType` 过滤（对），风险在**全量迁移 1578 条**。Sprint 1 范围：

| 类别 | 处置 |
|---|---|
| **必须 canonicalize** | `acquisition`、`regulatory`（有明确发文主体 + 文号/办法名更好） |
| **只做 alias、不自动 merge** | `product` / `personnel` / `industry_update` |
| **人工门** | auto merge 可上线；**split 必须人工**；`generic_entities_only` 进复核，不进 CE |
| **质量门** | 准备 **30 条标注集**（见 §6），含 At-Bay 多源必合、Zurich Farmers vs Cover-More 必拆、中保协指南 vs 非车险治理必拆；**false merge = 硬失败** |

没有这 30 条，Registry 只是换了 ID 前缀。

**改动归属**：S1（Registry）加 event_type 分区 + `domain` 概念 + legacy alias 策略 + 30 标注集 + split 人工门；S2（Resolver）按 event_type 分区解析；`generic_entities_only` 进复核不进 CE。

### 1.3 Semantic Alert 准入不靠 Watchlist 单一

只靠观察名单，冷启动首页会空；T1 监管/协会发文会被漏。两层：

| 层 | 进入首页 | 例子 |
|---|---|---|
| **系统级** | T1 监管/协会 + 阶段或效力变化 | 非车险治理方案、车险指南 |
| **个人级** | Watch 命中 + 语义变化 | At-Bay agreement、标过"重要"的 CE |

**仍不上首页**：`NEW_SOURCE`、`NEW_EVIDENCE`（除非新证据 **contradict** 已有 Claim）、单纯转载。
`NEW_CLAIM` 若与已交叉验证命题矛盾 → `EVENT_MATERIAL_CHANGED`（这不是内部 Diff）。

**改动归属**：S4（Alert）两层准入；X1 Home "语义变化（观察）"行接收系统级 T1，不要求 watch 命中。

### 1.4 范围重切：两周 5 Sprint → 三周 3 Sprint，只吃 2 类事件

> 两周 5 Sprint 会做成"纸面 Event OS"——文件都在、主链没成为产品。

| Sprint | 范围 | 落地段 | 出口 |
|---|---|---|---|
| **S1** | Canonical Identity（收购+监管） | S1 重写 + S2 分区解析 + 事件详情露出 `CE_xxxx` + KG 节点引用 CE | 30 标注集 false merge=硬失败 |
| **S2** | Acquisition Lifecycle + Semantic Alert | S3 domain 插件(acquisition 先) + S4 两层准入 + X1 Home 改漏斗出口+语义Alert 三行 | 多源合一 / 必拆 CE / 阶段只来自 Claim+Evidence |
| **S3** | Decision Funnel + Replay + 事件记忆 | S5 六条件+分角色 + S6 页内时间轴 + Second Brain FK=CE(冻结角色) + X1 收尾(89 留复核页) + E3 反馈挂 CE | 漏斗分角色计数 / Home 三行固定 / 89 不在主数字 |

每个 Sprint 结束跑同一套 **Event OS Quality Gate（§6）**，不通过不准加 KG / 新角色 / 新 Watchlist。

---

## 2. Decision Funnel 规则硬化

`89 → 8 → 3` 是正确产品指标。入口规则写成**可测试条件**（同时满足才叫 Decision Required）：

1. 用户在监控（Watch / 曾标重要 / 曾 acted_on），**或** 系统级 T1 监管；
2. 存在**语义变化**（阶段变化或关键命题变化），不是又来了一个源；
3. 阶段属于可决策集（收购：`agreement` / `regulatory` / `closing`）；
4. 证据覆盖与可信度过门；**单源 + 监管/评级 不得出 Decision Required**；
5. 该 `canonical_event_id` 在本角色下**未处理**（无 `decided_at`，或反馈非 snoozed/resolved）；
6. **Fail-closed**：推不出就进 Open Question，不进漏斗出口。

**漏斗分角色计数**：同一 CE 对投资是决策、对理赔可能只是观察。全局一个"3"会再次堆积。
**Home 固定三行**（避免把队列当决策）：
- **需决策（漏斗出口）**
- **语义变化（观察）**
- **复核队列（不是决策）**

89 可以留在复核页，**禁止出现在 Executive Home 主数字**。

**改动归属**：S5（Funnel）六条件硬化 + 分角色计数；X1 Home 三行固定 + 89 移出主数字。

---

## 3. Second Brain / 时间语义：改挂钩，不改加页

同意不再加 CEO/核保/理赔等角色。缺的是外键：

```
canonical_event_id
  published_at    事实发生（证据时间）
  ingested_at     系统看到
  decided_at      用户判断
  acted_at        用户行动（跟踪/忽略/已处理）
```
实体时间线继续只当"发布时间证据链"，**禁止冒充决策时间线**。
提醒文案必须是：
> 这是你此前标记的重要事件（CE_xxxx），现在发生了实质变化：谈判 → 协议。
不要是"At-Bay 又出现了"。名称匹配会把 Cover-More 和 Farmers 搅在一起——这正是 Registry 要消灭的问题。

**Watchlist 下一步不是加词，是三维**：`entity | topic | event_type`，用反馈调权重。四类（AI / 并购 / 监管 / 健康险）冻结即可。

**改动归属**：Second Brain 冻结角色 + 记忆外键=`canonical_event_id`；E2 扩展 `acted_at`；X1/事件详情用 CE 外键出提醒。

---

## 4. Feature Freeze 的例外（必须放行）

冻结：新 Watchlist、新 Role、新 Dashboard、新 KG 可视化、新 LLM。

**不要冻结**（这是挂钩不是新功能）：
- **事件详情升级为 OS 控制台**（CE、阶段条、合并史、语义 Alert、漏斗状态、Replay）——不是新 Dashboard；
- **首页从"今日三件事 + 待复核数字"改为"漏斗出口 + 语义 Alert"**；
- **Replay**（可以先做页内时间轴，不必先做命令行）；
- **KG 节点 ID 应开始引用 `canonical_event_id`**（挂钩不是新功能）。

KG 推理按原方案继续不做。

---

## 5. 质量门（每个 Sprint 都跑）

- 同一收购多源（Reuters/FT/Bloomberg/监管）→ **一个** CE；
- Zurich Farmers vs Cover-More → **两个** CE；
- 中保协车险指南 vs 非车险治理 → **两个** CE；
- 无 Claim 或无 Evidence → **禁止阶段前进**；
- 非法回跳（`closing → rumor`）→ `reviewRequired`，不写库；
- 低证据**禁止 `urgency=now`、禁止 Decision Required**；
- Home 产品 Alert **不含 `NEW_SOURCE`**。

新增测试夹具：**`canonical_annotation_set.json`**（≥30 条，含上述必合/必拆样例），作为 S1 回归基线；false merge = 硬失败（断言 0 例）。

---

## 6. 评分修正

| 维度 | 原评分 | 修订目标 | 说明 |
|---|---|---|---|
| Event OS 核心主链 | 60 | **目标 80（三周后）**，不写 95 | 全类型生命周期不在这一期 |
| Second Brain | 70 | **维持 70**；接 CE 后到 80 | 现在加角色只会把这项做虚 |

---

## 7. 落地映射：X2 对已交付 S1–S6 / E1–E3 / X1 的影响

> 已落地的 S1–S6 / E1–E3 / X1 是**引擎原型**，未成为产品主对象、生命周期过通用、身份迁移过满、Alert 过依赖 watch。X2 = 在原型上收敛，不推倒重来。

| 已交付段 | 是否要改 | X2 改动 |
|---|---|---|
| S1 Registry | ✅ 重写 | event_type 分区 + `domain` 概念 + legacy alias 策略(product/personnel/industry_update 只 alias) + 30 标注集 + split 人工门 + canonicalize 范围限 acquisition/regulatory |
| S2 Resolver | ✅ 改 | 按 event_type 分区解析；`generic_entities_only` 进复核不进 CE；legacy alias 映射 |
| S3 Lifecycle | ✅ 重写 | 通用六段 → `lifecycle.domain` 插件；acquisition 先实现；regulatory 只 status+issued/effective；other stage=null |
| S4 Alert | ✅ 改 | 两层准入（系统级 T1 + 个人级 watch）；`NEW_SOURCE`/`NEW_EVIDENCE` 不上首页；`NEW_CLAIM` contradict → `EVENT_MATERIAL_CHANGED` |
| S5 Funnel | ✅ 改 | 6 条件硬化 + 分角色计数；89 留复核页不进 Home 主数字 |
| S6 Replay | ✅ 改 | 页内时间轴优先（事件详情控制台内）；回答"为何今天变重要" |
| X1 Home | ✅ 收尾 | 固定三行（需决策/语义变化/复核队列）；监管 T1 无 watch 命中也要系统级高严重度进首页；89 移出主数字 |
| Second Brain | ✅ 改 | 冻结角色；记忆外键=`canonical_event_id`；时间语义属性 |
| KG | ✅ 改(挂钩) | 节点 ID 引用 `canonical_event_id` |
| E1 KG噪声 | ➖ 保持 | 干净实体支撑 event_type 分区解析 |
| E2 decided_at | ➖ 保持+扩 | 扩展 `acted_at`；时间语义已具备 |
| E3 feedback | ➖ 保持 | 反馈挂 CE 上，已就位 |

**新增 artifact**：`canonical_annotation_set.json`（Sprint 1 质量门基线）。

---

## 8. 对原方案的具体语句修订建议（评审通过后折回主方案）

| 主方案位置 | 现状 | 修订 |
|---|---|---|
| §2 设计原则 5 | "Executive Home 不增卡片，只换数据源" | 补："事件详情必须改为 OS 控制台（CE/阶段条/合并史/语义Alert/漏斗/Replay），这不是新 Dashboard" |
| §3 P0-B S3 行 | "rumor→…→integration（先吃透 M&A）" | 改为 `lifecycle.domain` 插件；acquisition 先实现；regulatory 只 status；other stage=null |
| §3 P0-B S1 行 | "resolve/upsert/alias/merge/split/migrate" | 加 "按 event_type 分区；acquisition/regulatory 必 canonicalize；product/personnel/industry_update 只 alias；split 人工门；30 标注集质量门" |
| §3 P0-B S4 行 | "两层 Internal Diff → Semantic Alert" | 加 "两层准入：系统级 T1 + 个人级 watch；NEW_SOURCE/NEW_EVIDENCE 不上首页" |
| §3 P0-B S5 行 | "decision_required funnel" | 加 "6 条件硬化 + 分角色计数；89 留复核页" |
| §4 明确不做 | 冻结所有新页面 | 加例外："事件详情→OS 控制台、首页改漏斗出口+语义Alert、Replay 页内时间轴、KG 节点引用 CE 不冻结" |
| §5 完成定义 | "M&A 事件完整生命周期+Replay" | 改为 "acquisition + regulatory 两类事件永久知道 是谁/在哪步/什么变了/该不该决策/你上次怎么判断"；补 "Home 三行固定、89 不在主数字" |
| §7 落地顺序 | 现依赖链 | 改为三周 3 Sprint（见 §1.4），每 Sprint 跑 Quality Gate |

---

## 9. 下一步（评审通过后的动作）

1. 你把本修订拍板（A/B/C 或 a+b 组合）→ 我折回主方案，新增 **X2** 段与三周 3 Sprint 排期；
2. **Sprint 1 先建 `canonical_annotation_set.json`（30 条）** + S1 event_type 分区重写 + S2 分区解析 + 事件详情露出 `CE_xxxx` + KG 节点引用 CE；跑 §5 质量门；
3. Sprint 2/3 依次落地，每 Sprint 末跑 Event OS Quality Gate；
4. 保持 E1/E2/E3 不变，T1 性能债独立排期。

> 纪律不变：fail-closed、observation/conclusion 分离、sample<30 不结论、open_questions 显式记录。
