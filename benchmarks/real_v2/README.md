# P1-4.1 真实数据标注基准 v2.0（困难样本扩容）

## 定位

本目录是 P1-4 真实数据标注基准的 **v2 扩容层**，承接已冻结的 v1.0
（`../real_v1/`，21 篇 / macro_quality=1.0）。目标：把真实语料基准从 21 篇
逐步扩到 **100 → 300 篇**，并补入 v1 未覆盖的**困难样本维度**。

v1.0 已冻结：只允许新增 v2 cases，不得修改 v1 任何 expected output
（见 `../benchmarks/README.md` 的 Versioning rule）。

## 困难样本四维度（本版新增）

| 维度 | 含义 | 被测安全属性 |
|---|---|---|
| `rumor_to_confirmed` | 同一交易从"据称洽谈/首选目标"演进到"已完成收购"，是同一事件 | 同事件对必须合并；rumor 阶段 `forbid_urgency=now` + `require_human_review` |
| `same_company_diff_event` | 同一主体（如 Zurich）但不同动作（收购 vs 业绩/派息），必须保持分离 | 显式不同事件对**不得合并**（false_merge=0） |
| `multi_source_3_5` | 同一事件被 3–5 个独立来源覆盖 | 多源同事件簇必须合并为单一事件；交叉验证 `cross_checked` |
| `contradiction` | 同一主体/事件出现相互冲突的报道（否认 vs 确认） | **不得把冲突报道合并为同一（误判的）已确认事件**（`false_merge=0`）；不得把冲突单源误升为 `cross_checked`。引擎对 deny/confirm 保持分离并交人工审阅，本维度以显式不同事件对测试"不可合并"安全属性 |

## 标注与审阅策略（关键约束）

- **生产数据不能直接成为基准标注**，需人工审阅（与 v1.0 一致）。
- 本目录分两层文件：
  - `gold.json`：**已验证标注**（`review_status: validated`）。当前首批为助手
    构造的困难样本（已知真值），经 runner 硬安全门验证通过；后续 Vikings 审阅
    通过的真实样本也写入此处。
  - `candidates.json`：**待人工审阅候选**（`review_status: proposed`），
    由 `../../scripts/sample_real_v2_candidates.py` 从生产 `data.json` 抽取，
    **绝不自动进入 `gold.json`**。Vikings 审阅通过后，把候选提升（promote）为
    `gold.json` 中的 validated 条目，才算入基准。
- 只保存元数据与来源 URL，**不复制文章正文**（同 v1.0）。

## 扩容路径 21 → 100 → 300

1. 首批：本目录已交付 **12 篇已验证构造困难样本**（4 维度全覆盖）+ baseline。
2. 规模化：运行 `python3 scripts/sample_real_v2_candidates.py` 从 1634 篇生产数据
   按四维度抽取候选簇（默认每维度封顶，避免噪声），产出 `candidates.json`。
3. Vikings 对 `candidates.json` 逐簇审阅 → 通过者提升进 `gold.json`（validated）。
4. 重复 2–3 直至 `gold.json` 累计达到 100 篇 → 300 篇，每次扩容后跑 runner
   确认 macro_quality 不退化、硬安全门不破。

## 文件

- `articles.json`：真实/构造文章元数据与 provenance。
- `gold.json`：已验证标注（事件关系、claim 期望、安全标签、维度、review_status）。
- `candidates.json`：待审阅候选（runner 不读取，仅人工审阅用）。
- `baseline.json`：本版 validated 基线（macro_quality + 硬安全门）。
- `../../real_data_benchmark.py`：执行器，支持 `--articles/--gold/--out` 指向本目录。

## 验收指标（同 v1.0，单独报告）

event precision/recall、false_merge_rate、false_split_rate、claim accuracy、
single_source_false_cross_check_rate、macro_quality。硬安全门：
false_merge_rate=0 且 false_split_rate=0 且 single_source_false_cross_check_rate=0，
否则 runner 以非零退出（CI 失败）。
