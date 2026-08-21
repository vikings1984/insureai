# Human-in-the-loop Review

## 第一性原理

不是所有样本都值得人工看。人工时间稀缺，应优先处理：高影响 + 低可信、事实冲突、证据不足、趋势样本不足、行动等级过高的事件。

## 自动流程

```text
采集
 ↓
Intelligence / Trust / Claims / Temporal / Decision
 ↓
review.py
 ↓
review_queue.json
 ↓
人工复核
 ↓
review_labels.json
 ↓
promote_reviews.py
 ↓
evaluation_cases.json
 ↓
CI regression gate
```

## 复核规则

`review.py` 只生成队列，不改变事件、可信度或决策结论。队列按 `priority` 从高到低排序，最多保留 100 条。

常见复核类型：

- `event_cluster`：事件边界可能错误
- `evidence`：关键事实缺少独立证据
- `conflict`：来源存在事实冲突
- `trend`：趋势样本不足
- `decision`：行动级别可能过高

## 如何沉淀成回归测试

复制 `review_labels.example.json` 为 `review_labels.json`，给每个已复核样本填写：

- `review_id`
- `label`
- `notes`
- `expected`

然后执行：

```bash
python3 promote_reviews.py
python3 evaluation.py
```

`promote_reviews.py` 会去重，并把人工结论追加到 `evaluation_cases.json`。人工纠正结果因此成为永久回归约束，而不是一次性的评论。

## 隐私边界

当前实现不上传用户行为，也不自动把浏览行为写入服务端。复核标签文件由维护者显式提交到 Git 后，才会进入公开 regression corpus。
