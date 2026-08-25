# InsureAI

> **保险行业 AI 情报与决策支持平台**

InsureAI 的目标不是堆积更多新闻，而是把分散的公开信息转化为**可验证、可解释、可追溯的行业情报**，帮助保险从业者更快回答：发生了什么、为什么重要、证据在哪里、下一步应该关注什么。

## 核心闭环

```text
Signal → Event → Evidence → Insight → Decision
```

系统坚持一个重要边界：**分析与建议可以自动化，承保、投资、合规和运营动作必须保留人工确认。**

## 三个核心产品

### Insurance Radar

回答：**行业正在往哪里走？**

输出研究主题趋势、加速/形成/降温状态、信号强度和证据覆盖。

### Event Intelligence

回答：**到底发生了什么？证据是什么？为什么重要？**

事件识别不再只依赖标题相似度，而是综合实体、事件类型、主题和时间窗口；每个事件都保留原始文章与可追溯证据。

### Executive Decision Support

回答：**对经营意味着什么？应该继续关注什么？**

系统生成 advisory-only 建议，并对单一来源、低证据覆盖、冲突或监管/评级/理赔事件设置人工复核边界。

## Canonical Intelligence Model

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

这些对象已经建立对应的数据契约，位于 `schemas/`。

### Article
外部公开信息的原始单元。

### Claim
从文章中提取的可验证事实陈述。

### Evidence
能够回溯到来源 URL、来源名称和发布时间的支持材料。

### Event
同一现实世界变化的多源聚合。

### Insight
基于证据的解释，必须同时说明证据覆盖、置信度和后续观察点。

### Decision
受约束的角色化行动建议，绝不直接执行业务动作。

## 当前架构

```text
外部信源 / RSS / Search / Inbox
             │
             ▼
       collect / research
             │
             ▼
        Signal Layer
             │
             ▼
        Event Engine
        │          │
        ▼          ▼
     Claims      Evidence
        │          │
        └────┬─────┘
             ▼
      Intelligence / Radar
             │
             ▼
       Decision Support
             │
       human approval
             │
             ▼
       Audit / Provenance
             │
             ▼
     Static SPA / Release
```

## 关键质量门

系统不以一个笼统的总分掩盖不同类型的错误，而关注：

- **False Merge**：把不同现实事件错误合并。
- **Evidence Coverage**：判断是否有足够可追溯证据支持。
- **Single-source Risk**：单一来源不得标记为 cross_checked。
- **Human Review Boundary**：监管、评级、理赔和低覆盖事件进入人工复核。
- **Unsafe Now Rate**：低可信度或低证据事件不得直接生成 `urgency=now`。

事件模型当前版本为 `v4`，事件指纹采用 `entity + action + topic + time` 结构，详见 `docs/PRODUCT_ARCHITECTURE.md`。

## 主要目录

| 路径 | 作用 |
| --- | --- |
| `collect.py` | 日常资讯采集、过滤、评分与合并 |
| `collect_research.py` | 研究报告发现与门控 |
| `signal.py` | 透明、可解释的 Signal Layer |
| `intelligence.py` | Event / Evidence / Insight 核心引擎 |
| `decision.py` | 角色化、advisory-only 决策支持 |
| `schemas/` | Article / Claim / Evidence / Event / Decision 契约 |
| `benchmark/` | 事件聚类回归基线 |
| `evaluation_metrics.py` | 质量指标与评估门 |
| `audit_ledger.py` | 审计记录 |
| `release_manifest.py` | 发布清单与 provenance |
| `tests/` | 标准库单元测试 |
| `.github/workflows/` | 采集、研究、测试和发布流水线 |
| `docs/PRODUCT_ARCHITECTURE.md` | 产品与技术架构说明 |

## 快速开始

```bash
python3 -m http.server 8000
# http://localhost:8000/
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

运行事件智能引擎：

```bash
python3 intelligence.py
```

运行决策构建：由现有 decision pipeline 负责，输出始终保留人工确认边界。

## 数据与发布原则

`*.json` 中由流水线生成的内容属于数据产物。修改业务逻辑时，应优先修改 generator，而不是手工编辑生产数据。

“证据尚未生成”不等于“证据证明失败”。artifact 生命周期必须与质量门分离，避免时间顺序造成错误的 blocked 状态。

## 工程原则

1. 一个提交解决一个明确问题。
2. 数据契约与生成逻辑分离。
3. 前端不重复执行后端语义判断。
4. 不为了修 CI 而放宽业务质量门。
5. 所有重要结论必须能够回溯到来源 artifact。
6. AI 建议不直接执行承保、投资、合规或运营动作。
7. 新的模型能力必须通过 benchmark、质量门和 provenance 验证。

## 下一阶段

优先继续完成：

```text
Radar UI
   ↓
Event Detail UI
   ↓
Evidence / Claim inspection
   ↓
Executive Decision View
   ↓
Knowledge Graph
```

其中前端应逐步从“精选资讯阅读器”转变为“事件与决策工作台”。

## License

详见仓库许可证文件。
