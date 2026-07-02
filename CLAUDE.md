# InsureAI — Project Rules for AI Agents

## 项目定位

保险行业智能资讯聚合平台，纯静态 SPA，部署在 Cloudflare Pages + EdgeOne Pages。

## 核心架构

- **前端**：单文件 `docs/index.html`（HTML + CSS + JS），零框架依赖
- **数据**：`docs/data.json`，页面通过 `fetch('data.json?t=...')` 加载
- **采集**：`run_collect.py`，多源真实采集（东方财富 API + AkShare + 保险行业协会 + 搜索引擎）
- **部署**：GitHub Actions 每6小时触发采集（UTC 0/6/12/18 = 北京时间 08/14/20/02）→ git push → Cloudflare Pages + EdgeOne Pages 自动部署
- **根目录 `index.html`**：EdgeOne 部署的入口重定向页，指向 `docs/index.html`，不可删除

## 数据源

| 优先级 | 来源 | 类型 | 说明 |
|--------|------|------|------|
| 主源 | 东方财富搜索 API | JSON API | 13 关键词搜索，覆盖 17+ 家媒体 |
| 辅源 | 中国保险行业协会 | 网页爬取 | col22 协会要闻 + col24 行业动态 |
| 补充 | AkShare stock_news_em | Python 库 | 5 家险企个股新闻（平安/人寿/太保/新华/人保） |
| 补充 | AkShare news_cctv | Python 库 | 央视新闻联播保险关键词过滤 |
| 搜索引擎 | 百度新闻 | 网页爬取 | 4关键词，gpc参数限制7天内结果 |
| 搜索引擎 | 360搜索新闻 | 网页爬取 | 2关键词，24条/次 |
| 搜索引擎 | 搜狗新闻 | 网页爬取 | 2关键词，非微信来源 |
| 搜索引擎 | Google News RSS | RSS | 4关键词，CI环境可用 |
| 微信 | 搜狗微信公众号 | 网页爬取 | 6关键词，22-24条/次，含账号名和时间戳 |
| 兜底 | FALLBACK_DATA | 硬编码 | 真实采集全失败时降级使用 |

## 边界规则

- `docs/index.html` 是所有页面内容唯一来源，不要在 `docs/` 下新增独立 HTML 页面
- 数据格式：`{id, title, summary, source_name, source_type, source_url, ai_score(0-100=int*10), tags, category, published_at, date_verified, reason}`
- `date_verified` 布尔字段：标记发布日期是否从源页面验证。已验证条目获得新鲜度加分，未验证条目不获得新鲜度加分
- 分类体系固定：regulation / product / industry / research / claims
- 前端 XSS 防护：所有动态内容必须用 `esc()` 转义，URL 用 `safeUrl()` 验证
- 采集端 URL 验证：`validate_url()` 只允许 http/https 协议；`is_safe_url()` 拦截内网 IP（SSRF 防护）
- 评分算法确定性：无随机噪声，基础分 3.0 + 关键词(≤1.5) + 权威(≤1.0) + 长度(≤1.0) + 新鲜度(≤3.5)，满分 10.0
- 新鲜度加分仅对 `date_verified=True` 的条目生效；未知日期的文章不获得新鲜度加分
- 评分阈值：curated ≥ 6.0（对应 ai_score ≥ 60），highlight ≥ 7.0（对应 ai_score ≥ 70），前端精选页阈值 60
- 时区：所有日期计算使用 Asia/Shanghai 时区
- 新鲜度过滤窗口：最近 21 天（FRESHNESS_DAYS=21），已验证条目超窗口淘汰，未验证条目通过但不加分
- 日期验证：最多对 15 条未验证条目访问文章页面提取真实发布日期（Semaphore(5) 并发）
- source_type 输出为中文标签（财经媒体/行业协会/监管机构等），非技术值
- data.json 输出包含 sources 数组和 source_health 数据源健康状态
- 增量更新：data.json 保留近 3 天历史新闻，总量上限 100 条；已验证条目检查3天窗口，未验证条目保留1个周期
- 采集端文章页抓取使用流式读取（限制 50K）+ 手动重定向校验（每跳检查 SSRF 安全性）
- 百度新闻搜索使用 `gpc=stf` 参数限制结果为最近 7 天
- `src/` 目录已删除，`run_collect.py` 是唯一采集入口

## 命令速查

```bash
# 本地预览
cd docs && python3 -m http.server 8000

# 数据采集
cd <project-root> && python3 run_collect.py

# 安装依赖
pip install -r requirements.txt

# 运行测试
python3 -m pytest tests/ -v
```

## 深入文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目概览、快速开始 |
| `requirements.txt` | Python 依赖（httpx, akshare） |
| `data/config.json` | 数据源与评分配置 |
| `docs/assets/logo/design-philosophy.md` | Logo 设计理念 |

## 协作流程

1. 修改 `docs/index.html` → 直接生效（静态文件）
2. 修改 `run_collect.py` → 需同步更新 `requirements.txt` 中的依赖
3. 新增信息源 → 在 `run_collect.py` 中添加采集函数 + 在 `collect_all()` 中调用
4. 品牌变更 → 同时更新 `docs/index.html`（标题/配色/Logo）、`README.md`、`CLAUDE.md`、`data/config.json`
5. GitHub Actions workflow 文件修改需要 token 有 `workflow` scope
6. CI 每6小时运行一次，依赖 `requirements.txt`（非内联 pip install）
