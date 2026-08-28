# CLAUDE.md — InsureAI（项目 Agent 上下文）

> 本文件供在本项目中工作的 AI 阅读；人类接入指南见 `README.md`。
> 立项诊断快照见 `OPTIMIZATION_PROPOSAL.md`（建议已全部落地，勿作待办）；上游旧版文件见 `archive/main/`。

## 项目身份
保险行业动态资讯聚合平台：纯静态 SPA（`index.html` + `css/` + `js/`） + 零依赖 Python 采集管道（`collect.py`）。
本质目标：让保险从业者以最低成本持续获取高价值行业资讯。

## 仓库与分支模型（硬约定）
- 仓库 `vikings1984/insureai`，**默认分支 `insureai`（单分支项目）**。
- 原 `main` / `insureai-legacy` / `insurescope` 分支已于 2026-07-07 整合：旧文件归档于 `archive/main/`，分支已删除。
- 另有一条 `cloudflare/workers-autoconfig` 分支，由 Cloudflare Pages 自动维护，**勿动**。
- ❌ 不存在 `main` 分支，也不存在 `SKILL.md` 文件 —— 历史记忆中 "SKILL.md" 均为幽灵引用；本项目 Agent 文档即本文件。

## 线上部署
- 生产部署：Cloudflare Workers（`release_channel=cloudflare_workers`；`DEPLOYMENT_URL` 指向生产域名，`deployment-verification.yml` 每 6 小时探测验证）。
- 部署流水线：`deploy-cloudflare.yml`（`wrangler deploy` 上传静态资产，`secrets.CLOUDFLARE_API_TOKEN`/`CLOUDFLARE_ACCOUNT_ID` 门控；未配置时 job 跳过，不失败）。启用步骤见 `DEPLOYMENT.md`。
- SEO/canonical：GitHub Pages `https://vikings1984.github.io/insureai/`（`SITE_URL`，prerender 生成 JSON-LD / sitemap 指向它）。
- 两个 URL 有意分离（`PUBLIC_SITE_URL` vs `DEPLOYMENT_URL`），详 `DEPLOYMENT.md`。
- 旧 CloudStudio 托管已弃用。

## CI（已验证可运行）
- `.github/workflows/daily-collect.yml`：每 6 小时自动运行（UTC 00/06/12/18 = 北京时间 08/14/20/02）+ `workflow_dispatch` 手动触发。
- 并发控制：`concurrency.group=daily-collect`，`cancel-in-progress=false`。
- 流程：checkout(insureai) → Run collector → **Data validation** → **Run tests** → Prerender SEO → 采集质量自动评分(ce-optimize) → Commit data+SEO+质量评分 → Push → **Notify on failure**（失败时自动创建 Issue）。
- 另 `.github/workflows/weekly-research.yml`：每周一北京时间 08:00（UTC 周一 00:00）自动运行 + `workflow_dispatch`；跑 `collect_research.py` 更新 `research.json`（深度研究页半自动闭环，详见下）。

## 推送规则（红线）
- 本机 `~/.gitconfig` 走 `gh-proxy.com` 代理，直连 `github.com:443` 被墙；公开代理匿名 push 被拒。
- ✅ 统一用 `make sync`（经 gh-proxy 透传 `gh auth token`，令牌仅运行时获取不落盘，推 `HEAD:insureai`）。
- ❌ 禁止裸 `git push`（代理缺令牌必失败）。

## 关键文件与职责
- `collect.py`：零依赖采集管道（6 通道见下）；决定 `data.json` 内容。
- `translate.py`：免费英译中模块（Google gtx + MyMemory 双端点回退 + SHA-1 持久缓存 `data/translation_cache.json`）。`collect.py` 采集尾部按预算（budget=40）翻译英文条目，写 `title_zh` / `summary_zh` 字段；缓存命中零请求，CI 已纳入提交。
- `prerender.py`：生成 JSON-LD / 首屏静态列表 / `sitemap.xml`。
- `collect_research.py`：深度研究页半自动采集（零依赖，复用 `collect.py` 工具）；维护 `research.json`，每周 CI 触发。白皮书聚焦版三重门控：①机构域名白名单 `RESEARCH_DOMAINS`（媒体网站不算研究报告）②财报噪声排除 `EARNINGS_NOISE_RE` ③标题须含报告型名词（报告/白皮书/研报/展望/report/whitepaper/sigma…）；`--clean` 可清洗历史 auto 条目（curated 条目永不动）。**方向驱动补充**：每次运行统计 8 方向报告数，低于 `RESEARCH_TOPIC_MIN=3` 的方向自动触发「方向主题页 `TOPIC_SOURCES` + 搜狗定向搜索」，尾部输出方向覆盖报告，缺口提示人工经 inbox/MCP 补充。
- `scripts/quality_score.py`：CI 中跑采集质量评分，写 `data/quality/`。
- `data.json`：前端加载的资讯数据（**由管道生成，勿大段手改**；2026-08-28 实测 1586 条 / 1532 事件）。**顶层是 dict**（`news` / `sources` / `days` / `version` / `last_updated` / `source_health`），取文章列表必须走 `data["news"]`——`p2_intelligence.py::load_news()` 已封装此契约。
- `research.json`：权威研究报告（深度研究页数据源）。**半自动闭环**：`collect_research.py` 每周自动发现机构新报告并标 `auto=True` 写入；人工精炼 `key_data/key_insight` 后把条目标 `curated=True`（CI 永不覆盖）；无 `auto` 字段的历史人工条也视为 `curated`。`renderResearch` 据此显示「⚙ 自动收录·待精炼」或「✓ 精编」徽标。
- `index.html`：SPA 骨架；`<meta name="data-url" content="data.json">` 同源加载；`feedback-email=157247839@qq.com` 已配置。含 ARIA 可访问性标签、localStorage LRU 自动清理（含配额耗尽降级）。
- `tests/`：标准库 unittest，**2026-08-28 实测 423 用例全绿**（`python3 -m unittest discover tests/`）。核心：`test_collect.py`(18) / `test_dedup.py`(9) / `test_stock_noise.py`(22) / `test_research_topics_v2.py`(18) / `test_research_filter.py` / `test_sogou_sources.py` / `test_translate.py` / `test_p2.py`(8) / `test_module_hygiene.py`(3)。
- `intelligence_signal.py`：Signal Layer（战略/监管/市场/技术/财务）。⚠️ **原名 `signal.py`，与 Python 标准库 `signal` 同名，已重命名** —— 遮蔽标准库会让 `intelligence.py` 的导入在 sys.path 顺序不同的环境下直接 ImportError（曾导致 9 个测试模块导入失败）。`tests/test_module_hygiene.py` 已锁定此约束，**禁止新建任何与标准库同名的模块**。
- `p2_intelligence.py`：P2 每日情报闭环（Daily Brief → Watchlist → Monitoring → Feedback）。产出 `p2_daily_brief.json`（已进 audit ledger 与 CI 门禁），用户状态持久化在 `p2_state.json`（随仓库提交以跨次运行累积反馈）。用法：`python3 p2_intelligence.py --watchlist '{"id":"ai","name":"AI保险","topics":["ai_intelligent"],"keywords":["AI"],"priority_boost":8}'`。⚠️ 事件的智能分在 `event["scores"]["intelligence_score"]`，**不是** `event["intelligence_score"]`。
- `benchmarks/real_v1/`：P1-4 真实语料人工标注基准（21 篇真实文章 / 6 正例对 / 6 负例对 / 3 claim 用例），`baseline.json` 已 `validated`，改算法前先跑它对拍。
- 旧 `config.json` 已废弃（配置内嵌于 `collect.py` 常量中），归档于 `archive/main/data/config.json`。

## 采集通道（6 条）
1. RSS/Atom（`SOURCES`，含 insurancejournal / reinsurancene.ws / artemis.bm）
2. 收件箱 `inbox.json`（填入真实文章链接）
3. 东方财富搜索 API（`fetch_eastmoney()`，零依赖）
4. 中国保险行业协会 iachina.cn（`fetch_iachina()`，`source_type=行业协会`）
5. 搜狗资讯垂直搜索（`fetch_sogou_news()`）：独立报道补充；关键词按天轮换（`_rotate_queries`，每日 3 词防 IP 限流），触发反爬自动跳过该通道。
6. 搜狗微信公众号搜索（`fetch_wechat()`，`source_type=微信公众号`）：搜狗是唯一深度索引公众号文章的搜索引擎；搜索页与 /link 跳转页共享 Cookie（SNUID），真实 URL 由跳转页 JS 片段解析。

所有条目经强保险信号门控（`is_insurance_relevant`），避免泛财经噪声。

## 免费英译中（translate.py）
- 双端点回退：Google gtx（`translate.googleapis.com`）→ MyMemory API；译文须含中文且非原文回显才采纳。
- 持久缓存：`data/translation_cache.json`（SHA-1 键），命中零请求；CI 提交已包含该文件，跨次运行复用。
- 预算控制：`translate_news(news, budget=40)` 每次运行最多翻译 40 条（缓存命中不占预算），失败静默跳过不影响采集。
- 前端展示：卡片中文标题副行（`.card-title-zh`）+ 摘要优先中文 + 弹窗可折叠英文原文；搜索同时匹配中英文字段。

## 踩坑警示
- `data-url` 已从 jsDelivr CDN@SHA 改为同源 `./data.json`：不需要 SHA pin / purge 这套间接层。
- 去重阈值 0.82；长句话题相似但文字差异大（~0.71）保守不误删。
- 中文强信号词须覆盖险种专名（惠民保 / 参保 / 新能源车险 …），泛词（如「智能」）不可单独作为信号。
- 分类均衡靠确定性重分类（`run()` 对所有条目重跑 `_category`），非靠新采集。
- 股市行情噪声过滤（`is_stock_noise()`）：强信号（板块行情/涨跌停/资金流向/收评）+ 弱信号组合（股价词+股市上下文词）双重判定，仅检查标题避免误删深度分析。`_ingest()` 入册门控 + `run()` 存量清洗双层防护。
- 研究主题关键词需定期扩充：`digital_transformation` 和 `ai_intelligent` 的"数字化"归属前者(digital_transformation)，已从后者(ai_intelligent)移除避免冲突。同主题内须避免子串包含关系（如"数字化"已覆盖"数字化转型/建设/升级"），跨主题须避免关键词重复（如"线上化"仅属于 channel_transformation）。
- 搜狗反爬：一次性跑全部关键词易触发验证码；已改为每日轮换 3 词（`_rotate_queries` 按 yday 偏移），检测到"验证码/antispider"即中断该通道。搜索结果标题的高亮标签去掉后，中文间残留空格须清理。
- 翻译端点：Google gtx 对长文本偶发超时，MyMemory 兜底但每日有匿名配额；译文必须校验含中文（防接口返回英文错误提示被当译文入库）。

## 深入文档
- 人类接入 / 部署 / 用法 → `README.md`
- 立项诊断（已落地）→ `OPTIMIZATION_PROPOSAL.md`
- 上游旧版（`run_collect.py` / Jekyll docs / 旧 CLAUDE.md）→ `archive/main/`
