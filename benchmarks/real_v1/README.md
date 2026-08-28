# P1-4 真实数据标注基准 v1.0

## 目标

建立一套与合成 fixture 独立的、基于真实公开保险行业新闻的人工标注基准，用于验证 InsureAI 在真实语料上的：

1. Event 聚合：同一事件能否合并；
2. Event 拆分：不同事件能否保持分离；
3. Claim 提取：关键命题能否被正确抽取；
4. Evidence 状态：多源是否正确标记为 `cross_checked`，单源是否保持 `single_source`；
5. Provenance：每条样本都保留公开来源 URL。

## 数据范围

当前 v1.0 包含 **21 篇真实公开文章元数据**，覆盖 2026 年 8 月保险行业的：

- 保险并购 / takeover
- AI 与网络保险
- 保险科技
- 再保险 / Lloyd's
- 监管与资本
- 气候与巨灾风险
- 渠道扩张

只保存标题、来源、发布时间、标签、主题和来源 URL，**不复制文章正文**。

## 标注原则

### Same Event

必须同时满足：

- 指向同一现实世界事件；
- 核心主体一致；
- 事件类型兼容；
- 时间窗口兼容。

### Different Event

即使主体相同，只要动作/事件不同，也必须标记为不同事件。例如：

- Munich Re 收购 At-Bay；
- Munich Re/其他保险公司针对 AI agent 风险调整网络保险政策。

### Uncertain Event

“preferred target”“discussions ongoing”“no certainty a deal would result”等报道不能标记为已经完成交易；应保留不确定性。

### Evidence

- 两个独立来源支持同一命题 → `cross_checked`；
- 只有一个来源 → `single_source`；
- 不得因为标题相似而把单源升级为交叉验证。

## 文件

- `articles.json`：真实文章元数据与 provenance；
- `gold.json`：人工标注的事件关系、Claim 期望值与安全标签；
- `../../real_data_benchmark.py`：基准执行器。

## 验收指标

真实数据基准单独输出：

- Event precision / recall
- False Merge Rate
- False Split Rate
- Claim accuracy
- Single-source False Cross-check Rate
- macro_quality

P1-4 当前属于**真实数据质量基线**，与核心 Benchmark v1.0 的发布门槛分开管理。核心 Benchmark 仍必须满足既定发布门槛后才能锁定 v1.0。
