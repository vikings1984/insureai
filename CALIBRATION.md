# InsureAI Human Feedback Calibration

## 原则

人工反馈是校准信号，不是无限放大的训练信号。

当前实现只做两件事：

1. 没有足够样本时保持 `neutral`，不改变任何决策。
2. 当同一 `event_type` 至少有 3 个人工复核样本，且预测过于激进时，允许设置最大紧迫度上限：`soon` 或 `watch`。

不会因为人工标签把任何分数或紧迫度向上放大。

## 数据来源

- `review_queue.json`：记录系统原始预测。
- `review_labels.json`：维护者显式提交的人工复核标签。
- `calibration.py`：生成 `calibration.json`。
- `decision.py`：在最终决策输出前应用受控上限。

## 回滚

删除 `review_labels.json` 中相关标签、或删除/恢复 `calibration.json` 到 `status=neutral`，下一次构建即可停止校准。

## 审计

`calibration.json` 保存每类事件的：

- reviewed count
- false-positive count
- false-positive rate
- applied action

因此任何一次降级都可以追溯到人工样本量和错误率。
