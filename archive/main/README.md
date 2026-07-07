# 归档：main 分支独有文件

> 本目录保存原 `main` 分支在「分支统一到 insureai」整合中**独有的文件**。
> 整合时间：2026-07-07｜操作：档位3 单分支统一，仅保留 `insureai` + `cloudflare`。

## 背景
项目原存在多条平行分支（`main`、`insureai`、`insureai-legacy`、`insurescope`），其中
`main` 与 `insureai` 为双主线。经评估，`insureai` 承载线上生产单页应用（collect.py +
data.json + js/app.js），`main` 仅保留旧版 Jekyll 文档站、旧采集脚本与少量额外测试。
为避免删除 `main` 导致内容永久丢失，先将其独有文件归档至此，再删除远程 `main`。

## 归档内容（按原路径保留）

| 类别 | 路径 | 说明 |
|------|------|------|
| CI 工作流 | `.github/workflows/daily-collect.yml` | 旧版每日采集/构建流水线（来自 `main`）；归档后不再自动运行。**注意：活跃 CI 在仓库根 `.github/workflows/daily-collect.yml`（默认分支 `insureai`），并非此处备份。** |
| 项目记忆 | `CLAUDE.md`、`CONCEPTS.md` | 旧版 Agent 上下文文档 |
| 文档站 | `docs/`（Jekyll 站：index.html、data.json、_posts、assets/logo、solutions/） | 旧版文档门户 |
| 旧采集脚本 | `run_collect.py` | 旧版采集入口（现由根目录 `collect.py` 取代） |
| 额外测试 | `tests/test_date_utils.py`、`tests/test_research_topics.py` | 旧版单元测试（现 `tests/` 另有 `test_collect.py`、`test_dedup.py`） |
| 依赖 | `requirements.txt` | 旧版依赖清单 |
| 数据 | `data/config.json`、`data/research_reports.json`、`data/summaries/*`（25 个摘要/报告） | 旧版配置与每日摘要 |

## 还原方式
如需恢复某文件到仓库根目录，执行例如：
```bash
git checkout HEAD -- archive/main/run_collect.py   # 仅取归档内容
# 或手工将 archive/main/<path> 复制到目标位置
```

## 注意
- 本目录内容**不参与**线上站点构建，仅作历史留存。
- 删除远程 `main` 后，原 `main` 提交历史仍可通过本归档在 `insureai` 中追溯。
