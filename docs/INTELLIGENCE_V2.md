# InsureAI Intelligence V2

## 核心变化

InsureAI 的核心实体从“新闻文章”升级为“事件”。事件由标题 token、实体、事件类型和时间窗口共同决定，而不是单纯依赖字符串相似度。

## 事件聚类规则

- 同一事件优先通过实体重叠识别。
- 同一事件的时间窗口默认 96 小时。
- 标题词相似度 + 实体相似度 + 事件类型一致性组成语义相似度。
- 同一公司发生的不同时间、不同类型事件不会因为公司名相同而无限合并。

## 情报可信度

Confidence 现在同时考虑来源权威度、日期验证和独立来源域数量。

## 事件结构

事件包含：

- `event_type`
- `entities`
- `topic`
- `source_count`
- `article_count`
- `scores`
- `insight.evidence`

## 设计约束

当前仍然不引入外部 embedding / LLM API。先让事件边界可解释、可测试，再通过人工标注集评估是否值得增加模型能力。
