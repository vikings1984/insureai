第三轮设计：从事件进入可监测对象

- Entity Radar：按实体聚合事件，输出近7/30天活跃度、情报分、事件类型、主题、趋势方向。
- Topic Trend：按研究主题比较最近7天与前7天事件强度，输出 rising/stable/falling。
- 不引入数据库；继续从 data.json 每次构建 intelligence.json。
- Radar 只作为信号，不宣称因果关系；样本不足时标记 low_confidence。