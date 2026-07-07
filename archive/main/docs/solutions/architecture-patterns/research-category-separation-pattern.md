---
title: "Research Category Separation: Dedicating a Classification Category Exclusively to Curated Authoritative Content"
date: 2026-07-03
category: docs/solutions/architecture-patterns
module: run_collect.py
problem_type: architecture_pattern
component: documentation
severity: medium
applies_when:
  - "A content aggregation platform needs to separate curated authoritative research reports from daily time-sensitive news"
  - "A classification category is overloaded with mixed content types that require distinct rendering and lifecycle handling"
  - "Daily news items matching a category's keywords (e.g. AI, InsurTech, digital) must be routed elsewhere to preserve a category's dedicated purpose"
related_components:
  - "frontend (docs/index.html)"
  - "data (data/research_reports.json)"
tags:
  - content-classification
  - research-reports
  - category-design
  - display-logic
  - data-separation
  - architecture
---

# Research Category Separation: Dedicating a Classification Category Exclusively to Curated Authoritative Content

## Context

The InsureAI project is a Chinese insurance industry news aggregation platform that organizes content into five categories: `regulation`, `product`, `industry`, `research`, and `claims`. Originally, the `research` category was populated by the same daily-news collection pipeline as every other category — it simply collected articles whose titles or bodies matched technology-oriented keywords such as `AI`, `保险科技` (InsurTech), `大数据` (big data), `人工智能` (artificial intelligence), `算法` (algorithm), and `数字` (digital).

The result was a category that was, in practice, indistinguishable from the other daily-news categories. A user opening the `research` tab saw the same timeline of news items, ranked by the same recency-and-score logic, with the same card presentation as the `industry` or `product` tabs. There was no signal that anything in the category was *authoritative* or *curated* — because nothing was.

This created two problems. First, the category name `research` set an expectation (deep, authoritative analysis) that the contents (daily news blurbs) could not meet. Second, genuinely valuable curated research reports — the kind produced by McKinsey, Swiss Re, Munich Re, Lloyd's, BCG, and Deloitte — had no natural home. They were either forced into `industry` alongside ephemeral news, or omitted entirely because the collection pipeline had no slot reserved for them.

The user request that prompted this guidance was direct: "区分日常新闻与深度研究报告" (distinguish daily news from deep research reports). The solution was not to add a sixth category, but to *repurpose* the existing `research` category so that it exclusively hosts 19 curated authoritative research reports sourced from `data/research_reports.json`, while migrating the technology keywords that previously populated it into the `industry` category. This transformed `research` from "another news bucket" into "the authoritative-report shelf."

## Guidance

The core pattern is **category dedication by content origin**: when a category is meant to surface high-value curated content, reserve it exclusively for that content and route everything else — even topically adjacent material — into the general-purpose news categories. Implementing this requires coordinated changes across the backend collector, the merge logic, the output schema, and the frontend renderer.

### 1. Strip the dedicated category of all keyword-based collection

Move every keyword that previously routed daily news into the dedicated category into a general-purpose sibling category. The dedicated category should have **no** entries in the keyword map, so that the scoring function can never assign a daily-news item to it.

```python
# Before: research had its own keyword set
CATEGORY_KEYWORDS = {
    "research": ["AI", "保险科技", "InsurTech", "大数据", "人工智能", "算法", "数字"],
}

# After: research has NO keywords; tech terms migrated to industry
CATEGORY_KEYWORDS = {
    "industry": [..., "AI", "保险科技", "InsurTech", "大数据", "人工智能", "算法", "数字"],
    "research": [],   # reserved for curated reports only
}
```

### 2. Guard the category-assignment function against hints

Data sources may still carry a `category_hint` of `"research"` from legacy configuration. Add an explicit guard so that any such hint is redirected to the general-purpose category:

```python
def assign_category(title: str, content: str, hint: str = "") -> str:
    # research 分类保留给权威研究报告，日常新闻不使用此分类
    if hint and hint != "research":
        return hint
    text = (title + " " + content).lower()
    scores = {cat: sum(1 for kw in kws if kw.lower() in text)
              for cat, kws in CATEGORY_KEYWORDS.items()}
    if max(scores.values()) == 0:
        return "industry"
    return max(scores, key=scores.get)
```

### 3. Inject curated reports as a distinct, fixed-score population

After the daily-news items have been merged and deduplicated, inject the curated reports as a separate population with fields that mark them as a different *kind* of content:

```python
# Reserve slots so all curated reports always fit
daily_budget = 81
research_budget = 19
output = daily_items[:daily_budget]

for report in research_items[:research_budget]:
    output.append({
        **report,
        "category": "research",
        "is_research_report": True,
        "ai_score": 95,                      # fixed high score
        "source_type": report["layer_label"],  # 国际再保险巨头 / 全球咨询机构 / 国内研究机构
    })
```

The fixed `ai_score: 95` is deliberate. Curated reports should not compete with daily news on a recency-weighted score curve; they are authoritative by origin, not by freshness.

### 4. Migrate legacy items during incremental merge

Old output files may contain items with `category="research"` and `is_research_report=False`. During the incremental merge step, automatically reclassify these to `industry`:

```python
for item in existing_items:
    if item.get("category") == "research" and not item.get("is_research_report"):
        item["category"] = "industry"
```

### 5. Render the dedicated category with a distinct UI

On the frontend, give the dedicated category its own render path. Do not reuse the timeline component that serves daily news. Curated reports warrant a card grid that surfaces institution, layer, topic, and a direct report link:

```javascript
function renderResearchReports(containerId, data) {
    // Sort by layer: reinsurance → consulting → domestic
    const layerOrder = { reinsurance: 0, consulting: 1, domestic: 2 };
    data.sort((a, b) => layerOrder[a.layer] - layerOrder[b.layer]);
    // Render card grid: badge + institution + title + summary + topic + link
}
```

Route the category tab so that selecting `research` calls `renderResearchReports()` instead of `renderTimeline()`, and so that selecting any *other* tab filters research items out. Also exclude research reports from the hot-topics ranking, since their fixed high score would otherwise dominate.

### 6. Label the section by content type, not count

In the daily-report summary section, label the research block as "X 份报告" (X reports) rather than "X 条" (X items). The counter noun signals to the reader that these are documents, not news snippets.

## Why This Matters

Mixing curated authoritative content with algorithmically-collected daily news in a single category damages both populations. The curated reports are buried under a stream of fresher, lower-effort items, because any recency-weighted ranking will favor today's news over a report published last month — even though the report is the higher-value artifact. Conversely, the daily news is polluted by a handful of high-score reports that distort the ranking and make the category feel inconsistent.

Dedicating the category exclusively to curated content resolves this on three axes simultaneously:

- **Signal integrity.** The category name becomes a truthful promise. When a user opens `research`, every item is an authoritative report from a named institution.
- **Ranking fairness.** Daily news competes only with daily news on the recency-score curve. Curated reports are not forced into a ranking game they were never designed for.
- **UX differentiation.** Because every item in the category shares the same origin and structure, the frontend can render them with a purpose-built card grid that surfaces institution, layer, and report link.

## When to Apply

- A category is intended to surface curated, high-signal content but is currently being populated by the same keyword-driven collection pipeline as the daily-news categories.
- Daily news matching a category's keyword set is topically adjacent to the category's intended content, but differs in origin (automated aggregation vs manual curation), lifecycle (ephemeral vs evergreen), or effort (a news blurb vs a multi-week institutional report).
- The category name sets an expectation (e.g., "research," "analysis," "reports") that the algorithmically-collected contents cannot meet.
- Genuinely valuable curated content exists but has no reserved slot in the output, causing it to be dropped on high-volume days or forced into an ill-fitting sibling category.
- A fixed high score applied to curated content would distort a shared ranking if mixed with daily news.

This pattern is **not** a good fit when the curated population is small enough to surface as a "featured" section within a general-purpose category, or when the curated content and daily news genuinely belong to the same browsing intent.

## Examples

### Before: research populated by keyword matching

```python
# Daily news matching "AI" or "保险科技" lands in research
def assign_category(title, content, hint=""):
    if hint:
        return hint
    # ... keyword scoring includes "research" category
    return max(scores, key=scores.get)

# research items are indistinguishable from industry items
{"title": "某险企上线AI核保系统", "category": "research", "ai_score": 62, "is_research_report": false}
```

### After: research reserved for curated reports

```python
def assign_category(title: str, content: str, hint: str = "") -> str:
    if hint and hint != "research":
        return hint
    # ... keyword scoring excludes "research" category entirely

# Curated report injected with distinct fields
{"title": "全球再保险市场展望 2026", "category": "research",
 "is_research_report": true, "ai_score": 95,
 "source_type": "国际再保险巨头", "source_url": "https://example.com/report.pdf"}
```

### Before: frontend treats research as a timeline tab

```javascript
function renderAll(category) {
    const items = data.filter(i => i.category === category);
    renderTimeline(items);  // same component for every category
}
```

### After: frontend routes research to a dedicated renderer

```javascript
function renderAll(category) {
    if (category === 'research') {
        renderResearchReports(data.filter(i => i.category === 'research'));
    } else {
        const items = data.filter(i => i.category === category && i.category !== 'research');
        renderTimeline(items);
    }
}

// Hot topics exclude research so the fixed high score doesn't dominate
const hotTopics = data.filter(item => item.category !== 'research').slice(0, 5);
```

## Related

- **CLAUDE.md** (lines 62-65): Encodes the category-separation rule as a boundary constraint. States WHAT but not the architectural WHY.
- **Commit `e29760d`**: Backend implementation — `assign_category()` guard, keyword migration, report injection, slot reservation, legacy migration.
- **Commit `18777f0`**: Frontend implementation — `renderResearchReports()` card grid, category routing, hot-topics exclusion.
- **`data/research_reports.json`**: 19 curated reports from 3 layers (international reinsurance / global consulting / domestic research).
- **Pattern: Category design by content origin, not by topic.** Two items about AI in insurance can belong in different categories if one is a news blurb and the other is a Swiss Re report.
- **Pattern: Slot reservation for curated content.** Reserving fixed output budgets for high-value populations so high-volume populations cannot crowd them out.
- **Pattern: Incremental schema migration during merge.** Old data is upgraded in place as it passes through the pipeline, without a dedicated migration script.
