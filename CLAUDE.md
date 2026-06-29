# InsureAI — Project Rules for AI Agents

## 项目定位

保险行业智能资讯聚合平台，纯静态 SPA，部署在 Cloudflare Pages。

## 核心架构

- **前端**：单文件 `docs/index.html`（HTML + CSS + JS），零框架依赖
- **数据**：`docs/data.json`，页面通过 `fetch('data.json?t=...')` 加载
- **采集**：`run_collect.py`，多源真实采集（东方财富 API + AkShare + 保险行业协会）
- **部署**：GitHub Actions 每日 UTC 0:00 触发采集 → git push → Cloudflare Pages 自动部署

## 数据源

| 优先级 | 来源 | 类型 | 说明 |
|--------|------|------|------|
| 主源 | 东方财富搜索 API | JSON API | 5 关键词并行搜索，覆盖 15+ 家媒体 |
| 辅源 | 中国保险行业协会 | 网页爬取 | col22 协会要闻 + col24 行业动态 |
| 补充 | AkShare stock_news_em | Python 库 | 5 家险企个股新闻（平安/人寿/太保/新华/人保） |
| 补充 | AkShare news_cctv | Python 库 | 央视新闻联播保险关键词过滤 |
| 兜底 | FALLBACK_DATA | 硬编码 | 真实采集全失败时降级使用 |

## 边界规则

- `docs/index.html` 是所有页面内容唯一来源，不要在 `docs/` 下新增独立 HTML 页面
- 数据格式：`{id, title, summary, source_name, source_type, source_url, ai_score(0-100=int*10), tags, category, published_at, reason}`
- 分类体系固定：regulation / product / industry / research / claims
- 前端 XSS 防护：所有动态内容必须用 `esc()` 转义，URL 用 `safeUrl()` 验证
- 采集端 URL 验证：`validate_url()` 只允许 http/https 协议
- 评分算法确定性：无随机噪声，基础分 3.0 + 关键词(≤1.5) + 权威(≤1.0) + 长度(≤1.0) + 新鲜度(≤1.5)
- `src/` 目录已删除，`run_collect.py` 是唯一采集入口

## 命令速查

```bash
# 本地预览
cd docs && python3 -m http.server 8000

# 数据采集
cd <project-root> && python3 run_collect.py

# 安装依赖
pip install httpx akshare
```

## 深入文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目概览、快速开始 |
| `data/config.json` | 数据源与评分配置 |
| `docs/assets/logo/design-philosophy.md` | Logo 设计理念 |

## 协作流程

1. 修改 `docs/index.html` → 直接生效（静态文件）
2. 修改 `run_collect.py` → 需同步更新 `.github/workflows/daily-pipeline.yml` 中的依赖
3. 新增信息源 → 在 `run_collect.py` 中添加采集函数 + 在 `collect_all()` 中调用
4. 品牌变更 → 同时更新 `docs/index.html`（标题/配色/Logo）、`README.md`、`CLAUDE.md`、`data/config.json`
5. GitHub Actions workflow 文件修改需要 token 有 `workflow` scope
