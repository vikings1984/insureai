# InsureAI — Project Rules for AI Agents

## 项目定位

保险行业智能资讯聚合平台，纯静态 SPA，部署在 Cloudflare Pages。

## 核心架构

- **前端**：单文件 `docs/index.html`（HTML + CSS + JS），零框架依赖
- **数据**：`docs/data.json`，页面通过 `fetch('data.json?t=...')` 加载
- **采集**：`run_collect.py`，从中文保险信息源采集，关键词评分分类
- **部署**：GitHub Actions 每日 UTC 0:00 触发采集 → git push → Cloudflare Pages 自动部署

## 边界规则

- `docs/index.html` 是所有页面内容唯一来源，不要在 `docs/` 下新增独立 HTML 页面
- 数据格式必须兼容 `data.news` 数组格式：`{id, title, summary, source_name, source_type, source_url, ai_score(0-100), tags, category, published_at, reason}`
- 分类体系固定：regulation / product / industry / research / claims
- 配色主题：`--accent: #F97316`（暗色）/ `#EA580C`（亮色），Logo 橙红渐变
- Logo 文件：`docs/assets/logo/logo.svg`（矢量）和 `logo.png`（位图）

## 命令速查

```bash
# 本地预览
cd docs && python3 -m http.server 8000

# 数据采集
cd <project-root> && python3 run_collect.py

# 安装依赖
pip install feedparser httpx
```

## 深入文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目概览、快速开始 |
| `docs/assets/logo/design-philosophy.md` | Logo 设计理念 |
| `data/config.json` | 信息源与分类配置 |
| `pyproject.toml` | Python 包依赖与 CLI 入口 |

## 协作流程

1. 修改 `docs/index.html` → 直接生效（静态文件）
2. 修改 `run_collect.py` → 需同步更新 `.github/workflows/daily-pipeline.yml` 中的依赖
3. 新增信息源 → 修改 `run_collect.py` 中的 `MOCK_SEARCH_RESULTS` 或 RSS_SOURCES
4. 品牌变更 → 同时更新 `docs/index.html`（标题/配色/Logo）、`README.md`、`CLAUDE.md`