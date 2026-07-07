# 策略摘要 — category-balance

## 运行状态
- 目标：提升 min_category_count（最小分类条目数），target=15。
- 已运行 2 个实验（Exp 1 综合重平衡、Exp 2 弱分类关键词加权），均 KEEP。
- 当前 best：min=16（≥target 15），**目标已达成**。

## 各类目尝试与结果
| 类别 | 信号提取(signal-extraction) | 参数调优(parameter-tuning) |
|------|------|------|
| _category 重平衡（claims/product/research 精准词 + 优先级） | ✅ 主胜利（Exp 1，min 6→16） | — |
| 弱分类关键词加权(per_kw) | — | ✅ 二级改善（Exp 2） |

## 关键学习
1. **根因**：`_category()` 以 `industry` 为默认兜底类，且原 claims 词过窄（仅 理赔/案例/纠纷/判决），
   导致 53 条(45%) 落入 industry；claims 仅 6 条。
2. **主杠杆是确定性重分类**：实时采集近乎饱和（每次仅新增 2~25 条且高去重），
   均衡改善主要来自让 `run()` 对所有 merged 条目重跑改进后的 `_category()`，
   把 industry 兜底项正确归位（claims 6→22、product 17→29）。
3. **精准词优于泛词**：claims 用 理赔/赔付/索偿/保险欺诈/反欺诈/车险理赔… 等精准词，
   弃用裸 案例/纠纷/判决（易误命中「数字化转型案例」等）。
4. **判定优先级**：regulation→claims→product→research→industry 顺序，避免 industry 抢占。
5. **二级增益**：弱分类专属搜索词 + per_kw 加权提升 source_diversity(49→56)、压低 max_category_pct(34.1%→32.2%)。

## 探索前沿（未尝试）
- research 类当前为绑定约束(16)：可新增研究/研报类专属搜索词或 RSS，进一步抬升 min。
- 可对 RSS 英文源做分类微调（当前英文源偏 industry/regulation/research）。
- 可引入「分类均衡感知」的采集配额（按当前最小类动态加权）。

## 当前最佳
- min_category_count=16，max_category_pct=32.2%，source_diversity=56，
  category_diversity=5，avg_score=85.6，stock_noise=0，max_single_source=11.9%。
- 基线→最优：min 6→16(+10)，industry 占比 44.2%→32.2%(-12.0pp)。
