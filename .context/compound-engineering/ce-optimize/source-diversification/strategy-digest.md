# Strategy Digest: Source Diversification (Batch 1 + Batch 2)

## Goal
扩大信息采集渠道，接入搜索引擎、微信公众号、头条等新数据源，达到 channel_comprehensiveness = 4.0

## Final Result: TARGET MET ✅
- Baseline: comprehensiveness = 2/5 (1 channel, 8 sources)
- Final: comprehensiveness = 4/5 (3 platform types, 5 working channels, 12-24 sources)
- Improvement: +2.0 (100% improvement)

## What Worked

### Batch 1 (Exp 1-4): Initial Channel Expansion
1. **搜狗微信公众号搜索** — 最可靠的新渠道。通过调试HTML结构发现账号名在`all-time-y2`类中，日期在`timeConvert()` JavaScript调用中(Unix时间戳)。6个关键词，每次采集22-24条。
2. **百度新闻搜索** — 高价值但高方差。有时31条，有时0条(反爬)。保留重试逻辑(桌面+移动UA)，系统不依赖百度也能通过门控。
3. **黑名单过滤** — 有效过滤知乎/百科/CSDN等非新闻来源。

### Batch 2 (Exp 5-7): New Search Engines + Quality Enhancement
4. **360搜索新闻** — 最可靠的新搜索引擎渠道。`news.so.com/ns?q=保险` 返回真实新闻标题，每次24条(3关键词×8条)。已替代失败的头条和Bing。
5. **搜狗新闻搜索** — 间歇可用(0-12条)。域名提取来源名需优化，但作为补充渠道有价值。
6. **Google News RSS** — 本环境无法访问Google，但代码保留。GitHub Actions CI环境(美国IP)可能可用。
7. **搜索引擎噪声过滤** — `SEARCH_ENGINE_NOISE_PATTERNS` 过滤产品页/Q&A/SEO垃圾(官网/计算器/保险问答等)。
8. **微信低质号过滤** — `WECHAT_LOW_QUALITY_MARKERS` 移除社区号/个人随笔号(社区/随笔/日常/人社等)。
9. **保险公司官网黑名单** — picc.com.cn/pingan.com等加入`BLACKLIST_DOMAINS`，过滤产品页。
10. **渠道均衡id()修复** — Python字典相等性导致不同文章被误判为重复。改用`id()`跟踪对象身份。`TARGET_TOTAL=30`防止第二轮无限制添加后低分项被截断。

## What Failed
- **今日头条搜索** — so.toutiao.com需要JS渲染，httpx无法工作。代码已移除。
- **Bing News搜索** — 返回Bing首页(JS渲染)，无搜索结果。代码已移除。
- **Google News RSS** — 本环境(Linux VM)无法访问Google。代码保留(CI可能可用)。
- **百度反爬** — 不稳定，有时所有URL均被拦截。系统通过360搜索+微信补偿。
- **内容级Jaccard去重** — 中文字符级n-gram不适合，误判率高(Batch 1已回滚)。

## Key Insights
1. **国内搜索引擎可用性排序**: 360搜索 > 百度(不稳定) > 搜狗新闻(间歇) > Bing(JS渲染) > Google(被墙)
2. **渠道均衡需要id()跟踪**: Python `item in list` 用字典相等性比较，不同文章如有相同字段值会被误判。必须用`id()`跟踪对象身份。
3. **TARGET_TOTAL防止截断丢失**: 渠道均衡第一轮保证每类型3条后，第二轮不能无限制添加再截取[:30]，否则低分保证项会被截断。必须在第二轮就限制总数。
4. **精选阈值影响多样性**: curated阈值6.0会过滤掉低分iachina/微信文章(3.3-5.9分)，导致最终条目数<30。这是质量与数量的权衡。
5. **优雅降级是关键**: 9个采集渠道中5个可用时系统仍通过所有门控。不依赖任何单一渠道。

## Metrics Comparison

| Metric | Baseline | Batch 1 Final | Batch 2 Final | Target |
|--------|----------|---------------|---------------|--------|
| comprehensiveness | 2/5 | 3/5 | **4/5** | 4.0 ✅ |
| total_items | 12 | 18 | 25 | ≥15 ✅ |
| source_diversity | 8 | 14 | 12 | ≥10 ✅ |
| category_diversity | 5 | 5 | 5 | ≥4 ✅ |
| distinct_channels | 1 | 2 | 3 | - |
| new_channel_items | 0 | 6 | 18 | - |
| stock_noise | 0 | 0 | 0 | =0 ✅ |

## Channel Architecture (Final)

```
数据采集层 (9 channels)
├── 财经API层
│   ├── 东方财富搜索API (102条/次) ✅
│   └── AkShare个股新闻 (50条/次) ✅
├── 搜索引擎层
│   ├── 360搜索新闻 (24条/次) ✅ [NEW]
│   ├── 百度新闻搜索 (0-31条/次) ⚠️
│   ├── 搜狗新闻搜索 (0-12条/次) ⚠️ [NEW]
│   └── Google News RSS (0条) ❌ [CI可能可用]
├── 社交媒体层
│   └── 搜狗微信公众号 (22-24条/次) ✅
└── 行业协会层
    └── 中国保险行业协会 (15条/次) ✅

质量过滤层
├── 股市噪声过滤 (47条/次)
├── 非新闻来源黑名单 (10-13条/次)
├── 搜索引擎噪声过滤 (2-8条/次) [NEW]
├── 微信低质号过滤 [NEW]
├── 标题相似度去重 (Jaccard >0.5)
└── 新鲜度过滤 (21天)

输出层
├── 渠道均衡 (MIN_PER_TYPE=3, MAX_PER_TYPE=15, TARGET_TOTAL=30) [FIXED]
├── 精选阈值 (score ≥ 6.0)
└── 重点阈值 (score ≥ 7.0)
```

## Recommended Next Steps
1. iachina加入AUTHORITY_SOURCES，避免低分被curated阈值过滤
2. 360搜索HTML解析优化(提取来源名和精确日期)
3. jieba分词+TF-IDF做微信内容质量评分
4. 微信正文抓取(通过临时链接获取摘要)
5. Brave Search API替代不稳定的百度(需API Key)
