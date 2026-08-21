# InsureAI Evaluation

## 第一性原理

系统只有在可测量的情况下才可以持续优化。Evaluation 不测试“代码是否运行”，而测试关键情报能力是否仍然满足产品假设。

当前基准覆盖 4 层：

1. **Event Clustering**：相同事件应聚合，不同事件不应误合并。
2. **Claim → Evidence**：多来源事实应可交叉验证，单来源不能虚假升级。
3. **Temporal Intelligence**：只有真实时间数据才能形成趋势；事件密度增加应识别为加速。
4. **Decision Guardrail**：高分、高可信、加速趋势才能进入“现在关注”，并始终保留决策护栏。

## 运行

```bash
python3 evaluation.py
python3 -m unittest tests/test_evaluation.py -v
```

输出包含 `passed / total / pass_rate`。CI 要求基准集全部通过。

## 演进原则

基准集应随着生产中发现的错误持续增加，而不是为了通过测试而修改期望值。每次新增错误案例，都应先记录“预期行为”，再修复实现。
