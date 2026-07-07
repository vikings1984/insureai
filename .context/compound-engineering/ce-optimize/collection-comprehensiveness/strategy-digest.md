# Strategy Digest — Collection Comprehensiveness Optimization

## Run Summary
- **Spec**: collection-comprehensiveness (maximize comprehensiveness_score, target 4.0)
- **Iterations**: 4 (max reached)
- **Result**: Baseline 3/5 → Best 4/5 (+33%), target MET
- **Date**: 2026-07-01

## What Worked

### 1. Stock Market Noise Filter (Experiment 1, KEPT)
**Problem**: 12 of 34 baseline items (35%) were stock market noise ("保险板块拉升", "融资客净买入") cluttering the industry category.
**Solution**: `STOCK_NOISE_KEYWORDS` list + `is_stock_noise()` function with exempt terms for real insurance content.
**Impact**: Eliminated 41 noise items, comprehensiveness 3→4, topic diversity 2→3.

### 2. Expanded Vertical Keywords (Experiment 1+3, KEPT)
**Problem**: Only 5 generic keywords missed vertical insurance topics.
**Solution**: Added 8 targeted keywords: 人身险, 健康险, 养老保险, 险资运用, 偿付能力, 金融监管总局, 车险, 保险消费者.
**Impact**: Better category coverage, especially regulation and product.

### 3. Category Balance Bonus (Experiment 3, KEPT)
**Problem**: regulation and claims categories had <3 items each.
**Solution**: +1.0 score bonus for items in categories with <3 entries.
**Impact**: regulation improved from 1→4, claims from 2→5 in final run.

### 4. Extended Freshness Window + Max Items (Experiment 3, KEPT)
**Problem**: FRESHNESS_DAYS=14 + max_items=25 was too restrictive.
**Solution**: FRESHNESS_DAYS=21, max_items=30.
**Impact**: More historical depth (7 days coverage vs 5), 30 items in final run.

## What Failed

### Content-Level Jaccard Dedup (Experiment 2, REVERTED)
**Hypothesis**: First-100-char content Jaccard >0.5 would catch semantic duplicates.
**Reality**: Too aggressive for Chinese — different articles about same topic share enough characters to trigger false positives. Dropped count below gate (14 < 15).
**Lesson**: Content-level character matching is unsuitable for Chinese semantic dedup.

### N-gram Substring Dedup (Experiment 4, REVERTED)
**Hypothesis**: Shared 4-char substrings indicate duplicate content.
**Reality**: Common Chinese industry terms ("科技保险", "农业保险") are exactly 4 chars and appear across many unrelated articles. Even n=6 was too aggressive (14 < 15).
**Lesson**: Character-level n-grams are fundamentally unsuitable for Chinese — shared domain terminology creates false matches. Semantic dedup requires word segmentation + vector similarity.

## Key Insights

1. **Stock noise is the #1 quality killer** in financial data collection. Domain-specific noise filters outperform generic dedup.
2. **Chinese text dedup needs word-level semantics**, not character-level patterns. The jieba + TF-IDF approach is the natural next step.
3. **Category balance scoring** is an effective low-cost lever — it doesn't change what's collected, only what surfaces.
4. **Degenerate gates are essential** — without the total_items>=15 gate, Experiments 2 and 4 would have been "kept" despite being strictly worse.

## Recommended Next Steps (Backlog)

| Priority | Hypothesis | Dependency |
|----------|-----------|------------|
| High | jieba分词 + TF-IDF语义相似度去重 | jieba |
| Medium | 保险处罚/保险纠纷专门关键词 | none |
| Low | 内容长度惩罚(<100字扣分) | none |
| Low | embedding模型语义去重 | sentence-transformers |
