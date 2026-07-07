# InsureScope

保险行业动态资讯聚合平台，纯静态 SPA，零后端依赖。

参考 [aihot.virxact.com](https://aihot.virxact.com) 设计风格，功能架构参考 [vikings1984/insureai](https://github.com/vikings1984/insureai) 开源项目。

> **本质目标**：让保险从业者以最低成本，持续获取高价值的行业资讯。
> 价值公式：`用户价值 = (信息质量 × 新鲜度 × 覆盖面) / 获取成本`

## 快速开始

```bash
# 本地预览（必须通过 HTTP 服务器，直接双击 file:// 无法加载 data.json）
python3 -m http.server 8000
# 打开 http://localhost:8000/
```

## 项目结构

```
├── index.html              # 主 SPA 骨架（HTML + SEO 标签 + 资源引用）
├── css/style.css           # 全部样式
├── js/app.js               # 全部业务逻辑（路由/渲染/交互）
├── data.json               # 资讯数据 + 信源数据（前端异步加载）
├── collect.py              # 零依赖自动采集管道（RSS + 收件箱 ingestion）
├── prerender.py            # SEO 预渲染（JSON-LD + 首屏列表 + sitemap.xml）
├── inbox.json              # 待收录文章收件箱（空数组，填入真实链接即可）
├── inbox.example.json      # 收件箱格式示例
├── sitemap.xml             # 由 prerender.py 生成（部署前跑一次）
├── tests/
│   └── test_dedup.py       # 去重逻辑单测（标准库 unittest）
├── Makefile                # 运维命令：make collect / collect-dry / seo / deploy
├── .github/
│   └── workflows/
│       └── daily-collect.yml  # GitHub Actions 每日定时采集并提交 data.json
├── OPTIMIZATION_PROPOSAL.md   # 第一性原理检视与优化建议
└── README.md
```

## 自动采集管道（P0 核心）

聚合的前提是自动获取。本项目通过 `collect.py`（仅用 Python 标准库，零依赖）实现：

**两条采集通道**
1. **RSS/Atom 信源**：在 `collect.py` 的 `SOURCES` 中填入真实可用的订阅地址。
2. **收件箱 ingestion（主通道）**：把你想收录的真实文章链接放进 `inbox.json`：
   ```json
   [
     { "url": "https://...", "source_name": "慧保天下", "source_type": "媒体", "authority": 89 }
   ]
   ```
   管道会自动抓取标题/摘要、评分、分类、去重并合并。

**处理流程**：抓取 → 评分(0-100) → 研究主题分类 → Levenshtein 去重(相似度≥0.82)
→ 增量合并(不覆盖既有精选) → 重算 `days` / `source_health` → 写回 `data.json`。

**用法**
```bash
make collect        # 采集并合并，写回 data.json
make collect-dry    # 仅预览将新增的条目，不写文件
python3 collect.py --limit 10   # 每个 RSS 信源最多取 10 条
```

**自动化部署**：`.github/workflows/daily-collect.yml` 每日北京时间 08:00 运行采集，
若有新内容则自动提交 `data.json`，使"发布资讯"成本趋近于零。

## SEO 预渲染（P2-8）

纯静态 SPA 内容经 `fetch` 渲染，搜索引擎/爬虫无法直接抓取正文。新增零依赖 `prerender.py`，
在部署前生成可被抓取的静态资产：

- **JSON-LD**：`WebSite` + `ItemList(NewsArticle)` 注入 index.html 的 `<!--SEO_JSONLD_START-->` 占位
- **首屏静态列表**：前 12 条资讯渲染为隐藏 `<div>`，注入 `<!--SEO_FALLBACK_START-->` 占位，供爬虫抓取
- **sitemap.xml**：站点页面 + 前 50 条资讯 URL

同时 `index.html` 已内建 `description` / Open Graph / Twitter Card / `canonical` 社交分享标签。

**用法**
```bash
make seo                                   # 用默认站点地址预渲染
python3 prerender.py --site-url https://your.domain   # 指定正式域名
```

> 部署流程应在上传前运行 `prerender.py`，确保 `sitemap.xml` 与 JSON-LD 为最新。

## 反馈闭环（P2-9）

反馈页与信源提报页通过 `<meta name="github-repo" content="owner/repo">` 配置 GitHub Issue 提交目标
（默认 `vikings1984/insureai`）。当配置了 `<meta name="feedback-email">` 时，反馈页会出现
"邮件提交"备选出口，即使没有 GitHub 也能反馈。所有提交同时写入 localStorage 备份。

```html
<meta name="github-repo" content="your-org/your-repo">
<meta name="feedback-email" content="insurescope@example.com">
```

## 去重测试（P2-10）

`tests/test_dedup.py`（仅标准库 `unittest`）验证 Levenshtein 去重（阈值 0.82）的真实行为：

- **轻微改写 / 同源重复**（相似度 0.84–0.98）→ 判重，避免入库重复
- **长句话题相似但文字差异较大**（~0.71）→ 保守地不误删（避免删掉不同新闻）

```bash
python3 -m unittest tests/test_dedup.py -v
```

## 工程结构（P3-11 拆分）

`index.html` 已从"HTML+CSS+JS 三合一"拆分为 `css/style.css` + `js/app.js`，便于长期维护。
CSP 保持 `script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'`，外链资源经 `'self'`
加载；部署时整个目录上传，引用自动生效（无需改动 index.html）。

## 同步到 GitHub

项目托管在 `vikings1984/insureai` 仓库的 **`insurescope` 分支**（保留 `main` 原始 insureai 内容不动）。
本机 `~/.gitconfig` 配了 `gh-proxy.com` 代理，直连推送需绕过代理并用 `gh` 凭证助手认证，
已封装为 `make sync`：

```bash
# 首次或日常同步（提交后）
make sync
# 等价展开命令（供参考/排错）：
#   cp ~/.gitconfig .gitconfig.tmp && sed -i '' '/gh-proxy/d' .gitconfig.tmp
#   GIT_CONFIG_GLOBAL=$(PWD)/.gitconfig.tmp git -c credential.helper= \
#     -c 'credential.https://github.com.helper=!gh auth git-credential' \
#     push -u https://github.com/vikings1984/insureai.git HEAD:insurescope
#   rm -f .gitconfig.tmp
```

> 推送前请先 `git add -A && git commit -m "..."`。`main` 分支为上游原始项目，请勿直接覆盖；
> 如需把 InsureScope 并回 `main`，可在 GitHub 上从 `insurescope` 向 `main` 开 Pull Request。


## 功能特性

- **7 个完整页面**：精选、全部动态、保险日报、信源提报、关于、更新日志、反馈
- **深色/浅色双主题**：CSS Variables 驱动，支持自动跟随系统偏好
- **8 大研究主题标签**：AI智能化、养老金融、产品创新、渠道变革、资本与再保险、气候与巨灾、数字化转型、监管变革
- **日期验证徽章**：已验证发布日期的文章显示绿色对勾标记
- **权威研究报告徽章**：来自咨询机构/再保险巨头/研究智库的文章显示书本标记
- **热点话题卡片**：精选页面顶部展示 Top 5 热点资讯
- **分享链接**：详情弹窗支持一键复制分享链接
- **Levenshtein 去重**：基于标题相似度的智能去重（阈值 0.82）
- **移动端底部导航**：适配手机端的底部 Tab 导航
- **XSS 防护**：`esc()` 转义 + `safeUrl()` URL 验证
- **数据可配置**：`data.json` 地址经 `<meta name="data-url">` 配置，支持远程数据解耦
- **SEO 友好**：JSON-LD + 首屏静态列表 + sitemap.xml + 社交标签
- **反馈闭环**：GitHub Issues（可配置仓库）+ 邮件备选出口
- **可测试**：去重逻辑标准库单测覆盖

## 数据格式

```json
{
  "news": [{...}],
  "sources": [{...}],
  "days": {...},
  "source_health": {...},
  "version": "2.2.3",
  "last_updated": "2026-07-07T09:30:00+08:00"
}
```

- `ai_score`：统一为 **0-100** 制（≥80 重点推荐）
- `source_health`：由采集管道依据真实数据重算（各信源贡献条数），非硬编码假数据
- `days`：依据 `published_at` 真实统计每日资讯量、高分数与分类分布

## 技术栈

- 纯静态 HTML（零框架依赖）
- CSS Variables 主题系统
- 原生 JavaScript（单页应用路由）
- localStorage 用户状态持久化
- fetch API 加载可配置 data.json
- Python 标准库采集管道 / SEO 预渲染（零第三方依赖）

## 部署

托管于 CloudStudio。推荐发布流程：

```bash
make collect     # 更新资讯（可选）
make seo         # 刷新 SEO 资产
# 重新部署到 CloudStudio（整目录上传 index.html + css/ + js/ + data.json + sitemap.xml）
```

index.html 通常无需改动；若改动了 `index.html`，重新运行 `make seo` 再部署。

## 更新日志

见网站内「更新日志」页面（`#/changelog` 路由）。
