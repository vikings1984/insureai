# Repository Governance Audit

**审计基线：`insureai` 分支**

## 1. 审计结论

当前仓库的**生产主线是清晰的**：`insureai` 是唯一应用与发布主线，`cloudflare/workers-autoconfig` 属于部署专项分支。当前没有发现开放 Pull Request，因此历史 feature 分支没有正在进行的 PR 合并义务。

本审计时仓库可见历史 `feature/*` 分支 100+，其中包含明显的迭代/试验命名，例如 `eval-final*`、`*-v2`、`*-final*`。这些分支不应继续被视为架构组成部分。

**处理原则：先审计、后删除；不通过 force-push 重写 `insureai` 历史。**

> **2026-08-28 复核更新**：清理已完成。当前远程分支仅剩 2 条 —— `insureai`（canonical）与 `cloudflare/workers-autoconfig`（deployment-specific），历史 `feature/*` 已全部移除。孤儿分支的持续检查已由 `.github/workflows/branch-hygiene.yml` 自动化（每周一生成候选报告 Issue，只报告不删除）。

## 2. 分支分类

### 保留

| 分支 | 分类 | 原因 |
| --- | --- | --- |
| `insureai` | canonical | 唯一生产/主开发源 |
| `cloudflare/workers-autoconfig` | deployment-specific | 部署专项维护；不得成为第二应用主线 |

### 历史清理候选

所有 `feature/*` 默认进入候选池。尤其是：

- `feature/eval-final*`
- `feature/eval-run-*`
- `feature/evaluation-system*`
- `feature/deployment-*`
- `feature/release-provenance*`
- `feature/audit-lineage*`
- `feature/change-impact*`
- `feature/personal-intelligence*`
- 其它已完成单一目的开发的 feature 分支

这些名称本身不能证明可以删除，因此删除前仍需确认 commit 是否已合并或明确废弃。

## 3. Pull Request 审计

截至本次审计，仓库没有开放 PR。因此当前没有需要保护的开放 feature → `insureai` 合并链。

历史已关闭 PR 显示大量功能已经通过 PR 进入主线，例如 deployment provenance、release identity、owner risk routing、audit 等。这进一步说明这些历史 feature 分支主要是开发历史，而不是运行时依赖。

## 4. Workflow / deployment 审计

`daily-collect.yml` 明确以 `${{ github.ref_name }}` checkout 和 push，正常运行应以 `insureai` 作为生产 ref。工作流的分析、质量、审计、release manifest 和 provenance 均在同一流水线完成。

部署配置明确区分：

- `PUBLIC_SITE_URL`：canonical / SEO URL
- `DEPLOYMENT_URL`：实际生产部署验证 URL

缺少 `DEPLOYMENT_URL` 被定义为 configuration debt，而不是 outage；这一边界已经写入 `DEPLOYMENT.md`。

## 5. Source-of-truth 审计

仓库应遵循：

```text
Python / JS generator
        ↓
JSON / HTML generated artifact
```

不能反过来：

```text
generated JSON
        ↓
hand-maintained business logic
```

当前主要质量 artifact 均有对应 generator / workflow stage，后续清理应优先删除重复 generator，而不是删除生成结果。

## 6. Artifact 生命周期

当前流水线已经存在明确的阶段顺序：

```text
collect
→ intelligence / trust / temporal
→ decision / stability / credibility
→ scenario / action / readiness
→ audit / contract / evaluation
→ review / health / backlog / radar / owner view
→ p2 daily brief
→ release manifest
→ final audit
→ restamp release
→ provenance
→ commit / push
```

重要治理规则：**前置阶段不得把后置阶段尚未生成的 artifact 当作质量失败。**

这条规则用于避免 `release_manifest.json` 等 future-stage artifact 导致提前 `blocked`。

## 7. 清理执行规则

历史分支只有在以下条件全部满足时才允许删除：

1. 没有开放 PR 使用该分支；
2. 没有 workflow / deployment 配置引用；
3. commit 已合并到 `insureai`，或已经明确确认废弃；
4. 没有文档要求用户 checkout；
5. 删除不会丢失唯一存在于该分支的业务逻辑。

**无法确认时保留，不猜测删除。**

## 8. 当前仓库治理状态

- [x] canonical branch 已明确
- [x] deployment branch 已明确
- [x] feature naming 规则已明确
- [x] README 已同步当前架构
- [x] `.gitignore` 已覆盖常见缓存/IDE/测试产物
- [x] deployment URL 与 canonical URL 已分离
- [x] release quality 与 deployment verification 已分离
- [x] artifact provenance 已纳入发布链
- [x] 开放 PR 审计：当前无开放 PR
- [x] 历史 feature 分支逐项确认并删除（2026-08-28 复核：远程分支仅剩 2 条）
- [x] 定期自动检查孤儿分支（`branch-hygiene.yml` 每周一自动出候选报告）
- [x] P2 产物纳入发布链（`p2_daily_brief.json` 进 audit ledger + 非空门禁）

## 9. 后续维护标准

每轮优化结束前应执行：

```bash
git fetch --prune --all
git status --short
python3 -m unittest discover -s tests -v
```

并确认：

- 工作树干净；
- 新分支有单一目的；
- 已合并 feature 分支及时删除；
- 不创建 `final2/final3/v2` 式永久分支；
- generated artifact 只由 generator 更新；
- release provenance 与实际发布身份一致。
