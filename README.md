# InsureAI

保险行业动态资讯与风险情报平台。当前产品形态是**纯静态 SPA + GitHub Actions 数据流水线**：前端无需后端服务，采集、分析、评估、审计与发布由自动化任务生成可追溯的数据产物。

> **核心目标**：让保险从业者以最低成本持续获取高价值、可验证、可追溯的行业信息。

## 当前架构

```text
外部信源 / RSS / 搜索 / Inbox
            │
            ▼
      collect.py / research
            │
            ▼
       事件与证据层
            │
     ┌──────┼────────┐
     ▼      ▼        ▼
 evaluation decision  scenario
     │      │        │
     └──────┼────────┘
            ▼
   credibility / owner view
            │
            ▼
     audit / provenance
            │
            ▼
       release artifacts
            │
            ▼
     静态 SPA / GitHub Pages
```

项目坚持一个重要边界：**分析与建议可以自动化，承保、投资、合规和运营动作必须保留人工确认边界。**

## 快速开始

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000/
```

运行测试：

```bash
python3 -m unittest discover -s tests -v
```

## 主要目录

| 路径 | 作用 |
| --- | --- |
| `index.html` | SPA 入口、SEO 元数据与静态壳 |
| `css/style.css` | 前端样式 |
| `js/app.js` | 前端路由、渲染与交互 |
| `data.json` | 资讯数据产物 |
| `research.json` | 研究报告数据产物 |
| `collect.py` | 日常资讯采集与整理 |
| `collect_research.py` | 研究报告发现与门控 |
| `decision_credibility.py` | 决策可信度摘要 |
| `owner_risk_view.py` | 面向负责人的风险视图 |
| `evaluation_metrics.py` | 质量评估指标 |
| `audit_ledger.py` | 审计记录 |
| `release_manifest.py` | 发布清单与发布身份 |
| `prerender.py` | SEO 预渲染 |
| `tests/` | 标准库测试 |
| `.github/workflows/` | 自动采集、研究与发布流水线 |
| `BRANCHING.md` | 分支与仓库治理规则 |
| `DEPLOYMENT.md` | 部署说明 |
| `Makefile` | 常用本地运维命令 |

> `*.json` 中由流水线生成的文件属于**数据产物**；修改逻辑时应优先修改对应 generator，而不是手工编辑生成结果。

## 数据流水线

### 日常资讯

`collect.py` 从 RSS、Inbox、行业站点和搜索通道发现资讯，执行相关性过滤、评分、分类、去重、翻译与增量合并。

### 研究报告

`collect_research.py` 对机构白名单、报告型标题、保险相关性及财报噪声执行门控，并区分自动收录与人工精编内容。

### 质量与决策

数据进入事件、证据、评估、决策、情景和审计阶段后，会生成包括：

- `evaluation_metrics.json`
- `decision_credibility.json`
- `owner_risk_view.json`
- `decision_stability.json`
- `evidence_availability.json`
- `audit_ledger.json`
- `release_manifest.json`

这些文件共同构成发布前的质量、可信度、责任分配和可追溯性链路。

## 可信度状态

`decision_credibility.json` 不重新评分，也不替代原始决策，只汇总已有信号：

```text
ready   → 没有发现需要升级处理的质量问题
caution → 存在需要关注但未直接阻断发布的信号
review  → 需要人工复核或生产验收
blocked → 已有明确证据表明质量门失败
```

特别注意：**“证据尚未生成”不等于“证据证明失败”。** 流水线按 artifact 生命周期处理未来阶段尚未产生的文件，避免时间顺序造成错误的 `blocked`。

## 自动化与人工边界

自动化系统负责资讯发现、研究报告门控、事件与证据整理、质量评估、稳定性检查、风险提示、负责人视图、审计与发布 provenance。

系统不会自动执行：

- 承保决定
- 投资交易
- 合规结论
- 运营处置
- 对外具有约束力的业务动作

相关建议始终以 `advisory_only` / human approval boundary 表达。

## 本地命令

```bash
make collect
make collect-dry
make seo
make sync
```

如需生产发布，应通过 GitHub Actions 与正式发布流程完成，不建议绕过 CI 手工修改生产数据。

## 测试

所有核心逻辑使用 Python 标准库 `unittest`，无需额外依赖：

```bash
python3 -m unittest discover -s tests -v
```

修改 generator 时，应同时验证对应 artifact 的 schema、版本和关键字段，避免“代码已升级、CI 仍检查旧契约”的回归。

## 分支策略

长期维护只保留：

```text
insureai                         # 唯一主线 / 生产源
feature/<single-purpose-change> # 短生命周期功能
fix/<single-purpose-bug>        # 短生命周期修复
chore/<maintenance-task>        # 工程维护
```

历史实验分支应在确认没有开放 PR、workflow/deployment 引用且已合并或明确废弃后删除。详细规则见 `BRANCHING.md`。

## 贡献原则

1. 一个提交解决一个明确问题。
2. 生成文件与生成逻辑分离维护。
3. 不为了修 CI 而放宽业务质量门。
4. 不用缺失数据伪装成失败证据。
5. 所有重要决策信号必须可追溯到来源 artifact。
6. 生产发布必须保留 release provenance。

## License

详见仓库许可证文件。
