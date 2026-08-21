# InsureAI Production Replay

## 第一性原理

手工案例只能证明“预期行为”，生产回放才可以发现真实数据中的结构性回归。

### 回放原则

1. 默认读取仓库 `data.json` 的真实 `news` 数据。
2. 数据量较大时按 `research_topic` 分层抽样，最多 500 条，固定随机种子保证可复现。
3. 同一批数据以两种输入顺序重跑，检查 Event Partition 是否稳定。
4. 检查事件 ID 唯一性、文章归属唯一性、输入覆盖率和来源多样性。
5. `data.json` 为空时必须输出 `status=unavailable`，不允许伪造为通过。

## 运行

```bash
python3 production_replay.py
python3 -m unittest tests/test_production_replay.py -v
```

## 指标

- `replay_stability`：输入顺序变化后的事件分区稳定率
- `article_coverage`：抽样新闻是否全部进入某个事件
- `duplicate_event_ids`：重复事件 ID
- `duplicate_article_assignments`：一篇新闻被多个事件重复归属
- `source_diversity`：抽样中的独立来源数量
- `top_source_share`：最大来源占比

生产回放的目标不是给出一个漂亮总分，而是发现真实数据回归。
