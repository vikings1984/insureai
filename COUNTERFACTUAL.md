# Counterfactual Robustness

## 第一性原理
一个判断是否可信，不只取决于结果本身，还取决于结果是否过度依赖某一个关键输入。

第十六轮增加两类反事实：

- 移除冲突标记：验证安全护栏是否真正支配决策，而不是被后续高分规则覆盖。
- 移除主题趋势信号：验证 `now/soon` 判断是否过度依赖短期趋势。

输出：`counterfactual.json`

### 如何解释

`changed=true` 不等于算法错误。它表示“关键输入被移除后结论发生变化”，属于需要解释的敏感依赖。真正的错误需要结合业务语义和人工复核判断。

反事实样本会自动进入 `review_queue.json`，供人工复核；不会自动修改生产结论。

## CI

- Python syntax check
- Counterfactual regression tests
- Full unit tests
- Production replay + review queue

如果 `data.json` 没有新闻，反事实结果可以为空，但不会伪造成高稳健性。
