# InsureAI

AI 驱动的保险行业智能资讯聚合平台。

## 架构

纯静态 SPA（`docs/index.html`），零后端依赖，托管于 Cloudflare Pages。每日通过 GitHub Actions 自动采集保险行业资讯，生成 `docs/data.json`，触发 Cloudflare Pages 自动部署。

## 数据采集

```bash
pip install feedparser httpx
python run_collect.py
```

采集中文保险信息源，基于关键词自动评分分类（监管政策/产品发布/行业动态/论文研究/理赔案例），输出到 `docs/data.json` 和 `docs/_posts/`。

## 自动化

`.github/workflows/daily-pipeline.yml` — 每天北京时间 8:00 触发，采集 → 生成 → git commit & push → Cloudflare Pages 自动部署。

## 本地预览

```bash
cd docs && python3 -m http.server 8000
# 打开 http://localhost:8000/
```

## 项目结构

```
docs/
  index.html          # 主 SPA（精选/全部/日报/提报/关于/更新日志/反馈）
  data.json           # 资讯数据，index.html 通过 fetch 加载
  _posts/             # 每日中英文日报 Markdown
  assets/logo/        # Logo SVG + PNG
run_collect.py        # 数据采集脚本
.github/workflows/    # GitHub Actions 自动化
src/                  # Python 后端模块（采集器/AI评分/API）
data/
  config.json         # 信息源配置
  summaries/          # 采集输出
  rss/                # RSS 订阅源
```

## 许可证

MIT License