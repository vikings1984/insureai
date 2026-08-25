# InsureAI 产品与技术架构 vNext

## 1. 产品定位

InsureAI 不再以“保险新闻聚合”为核心定位，而是一个**保险行业 AI 情报与决策支持平台**。

核心价值链：

```text
Signal → Event → Evidence → Insight → Decision
```

目标不是增加信息数量，而是降低从“看到信息”到“形成可验证判断”的成本。

## 2. 三个核心产品

### Insurance Radar

回答：**行业正在往哪里走？**

输出主题趋势、加速/形成/降温状态、信号强度、证据覆盖和需要关注的领域。

### Event Intelligence

回答：**到底发生了什么？证据是什么？为什么重要？**

一个事件必须能够回溯到文章、证据和实体，并明确单一来源或多源交叉验证状态。

### Executive Decision Support

回答：**对经营意味着什么？下一步应该观察什么？**

系统只生成 advisory-only 建议；承保、投资、合规和运营动作必须人工确认。

## 3. Canonical data model

```text
Article
  ↓
Claim
  ↓
Evidence
  ↓
Event
  ↓
Trend
  ↓
Insight
  ↓
Decision
```

### Article

外部发布的原始信息单元。它回答“谁发布了什么”。

### Claim

从文章中提取的可验证事实陈述。它回答“具体声称了什么”。

### Evidence

能够追溯到 URL、来源、时间的支持材料。它回答“证据在哪里”。

### Event

同一现实世界变化的多源聚合。事件识别基于实体、动作、主题和时间，而不是标题相似度单一信号。

### Insight

在证据边界内给出的解释，必须同时输出证据覆盖、置信度和需要关注的后续信号。

### Decision

面向角色的、受约束的行动建议。永远不是自动执行指令。

## 4. 关键质量门

1. **False Merge**：不同现实事件被错误合并。
2. **Evidence Coverage**：结论有多少可追溯证据支持。
3. **Single-source risk**：单一来源不得标记为 cross_checked。
4. **Human Review Boundary**：监管、评级、理赔或低证据覆盖事件进入人工复核。
5. **Unsafe Now Rate**：低可信度事件不得生成 `urgency=now`。

## 5. UI 演进方向

现有内容页保留兼容，但首页产品语义应逐步从：

```text
精选 → 全部动态 → 研究
```

转为：

```text
Radar → Events → Research → Decision Support
```

单个事件页面建议固定呈现：

```text
发生了什么
为什么重要
谁受到影响
证据与来源
反向/冲突证据
趋势位置
建议关注
人工复核状态
```

## 6. 工程原则

- 生成逻辑和数据产物分离。
- 前端不重复执行后端语义判断。
- Schema 是数据 API 契约。
- Benchmark 是算法回归基线。
- 新增模型能力必须保留确定性质量门和 provenance。
