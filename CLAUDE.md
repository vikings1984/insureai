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
- 主站：GitHub Pages `https://vikings1984.github.io/insureai/`（推送即自动部署，零接触刷新）。
- 旧 CloudStudio 托管已弃用。

## CI（已验证可运行）
- `.github/workflows/daily-collect.yml`：每日北京时间 08:00（UTC 00:00）自动运行 + `workflow_dispatch` 手动触发。
- 流程：checkout(insureai) → Run collector → Prerender SEO → 采集质量自动评分(ce-optimize) → Commit data+SEO+质量评分 → Push。
- 最近一次手动验证 run `28876165712` 结论 **success**。

## 推送规则（红线）
- 本机 `~/.gitconfig` 走 `gh-proxy.com` 代理，直连 `github.com:443` 被墙；公开代理匿名 push 被拒。
- ✅ 统一用 `make sync`（经 gh-proxy 透传 `gh auth token`，令牌仅运行时获取不落盘，推 `HEAD:insureai`）。
- ❌ 禁止裸 `git push`（代理缺令牌必失败）。

## 关键文件与职责
- `collect.py`：零依赖采集管道（4 通道见下）；决定 `data.json` 内容。
- `prerender.py`：生成 JSON-LD / 首屏静态列表 / `sitemap.xml`。
- `scripts/quality_score.py`：CI 中跑采集质量评分，写 `data/quality/`。
- `data.json`：前端加载的资讯数据（**由管道生成，勿大段手改**；当前 ~147 条 / v2.2.13）。
- `research.json`：权威研究报告（来自上游归档）。
- `index.html`：SPA 骨架；`<meta name="data-url" content="data.json">` 同源加载；`feedback-email=157247839@qq.com` 已配置。
- `tests/test_collect.py`（18 用例）+ `tests/test_dedup.py`：标准库 unittest。

## 采集通道（4 条）
1. RSS/Atom（`SOURCES`，含 insurancejournal / reinsurancene.ws / artemis.bm）
2. 收件箱 `inbox.json`（填入真实文章链接）
3. 东方财富搜索 API（`fetch_eastmoney()`，零依赖）
4. 中国保险行业协会 iachina.cn（`fetch_iachina()`，`source_type=行业协会`）

所有条目经强保险信号门控（`is_insurance_relevant`），避免泛财经噪声。

## 踩坑警示
- `data-url` 已从 jsDelivr CDN@SHA 改为同源 `./data.json`：不需要 SHA pin / purge 这套间接层。
- 去重阈值 0.82；长句话题相似但文字差异大（~0.71）保守不误删。
- 中文强信号词须覆盖险种专名（惠民保 / 参保 / 新能源车险 …），泛词（如「智能」）不可单独作为信号。
- 分类均衡靠确定性重分类（`run()` 对所有条目重跑 `_category`），非靠新采集。

## 深入文档
- 人类接入 / 部署 / 用法 → `README.md`
- 立项诊断（已落地）→ `OPTIMIZATION_PROPOSAL.md`
- 上游旧版（`run_collect.py` / Jekyll docs / 旧 CLAUDE.md）→ `archive/main/`
