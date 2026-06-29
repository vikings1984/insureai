# InsureAI

AI 驱动的保险行业智能资讯聚合平台。

## 架构

纯静态 SPA（`docs/index.html`），零后端依赖，托管于 Cloudflare Pages。每日通过 GitHub Actions 自动采集保险行业资讯，生成 `docs/data.json`，触发 Cloudflare Pages 自动部署。

## 数据采集

```bash
pip install httpx akshare
python run_collect.py
```

多源真实采集，覆盖 15+ 家媒体：

| 数据源 | 类型 | 说明 |
|--------|------|------|
| 东方财富搜索 API | JSON API | 5 关键词并行搜索（保险/监管/产品/理赔/科技） |
| AkShare stock_news_em | Python 库 | 5 家险企个股新闻 |
| AkShare news_cctv | Python 库 | 央视新闻联播保险相关 |
| 中国保险行业协会 | 网页爬取 | 协会要闻 + 行业动态 |

采集 → 去重 → 近 14 天过滤 → 评分分类 → Top 25 精选 → 输出 `docs/data.json` 和日报。

## 自动化

`.github/workflows/daily-pipeline.yml` — 每天 UTC 0:00（北京时间 8:00）触发，采集 → 生成 → git commit & push → Cloudflare Pages 自动部署。

## 本地预览

```bash
cd docs && python3 -m http.server 8000
# 打开 http://localhost:8000/
```

## 项目结构

```
docs/
  index.html          # 主 SPA（精选/全部/日报/提报/关于/更新日志/反馈）
  data.json           # 资讯数据
  _posts/             # 每日日报 Markdown
  assets/logo/        # Logo SVG + PNG
run_collect.py        # 数据采集脚本（唯一入口）
data/
  config.json         # 数据源与评分配置
  summaries/          # 采集输出存档
.github/workflows/    # GitHub Actions 自动化
```

## 依赖

- Python 3.11+
- httpx（HTTP 请求）
- akshare（财经数据接口）

## 许可证

MIT License
