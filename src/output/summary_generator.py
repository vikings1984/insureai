"""每日简报生成器 - Horizon 风格

生成中英双语 Markdown 格式的每日保险资讯简报
借鉴 Horizon 的丰富内容展示 + 专业分析风格
"""

from __future__ import annotations
import json
from datetime import datetime, date
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import get_categories, get_project_root

if TYPE_CHECKING:
    from src.models import NewsItem, DailySummary


# ============ 中文模板 - Horizon 风格 ============

TEMPLATE_ZH = """---
layout: daily
title: "保险日报 {date}"
date: {date}
lang: zh
total_items: {total_items}
avg_score: {avg_score}
---

# 📋 InsureScope 保险日报

**{date_zh}** · AI 筛选自 {total_sources} 个信息源 · 从 {total_fetched} 条资讯中精选 **{total_items}** 条重要内容

---

## 🌟 今日重点

{highlights_zh}

---

{categories_zh}

---

## 🏷️ 标签云

{tag_cloud}

---

*InsureScope — AI 驱动的保险信息聚合系统 · [English Version](./{date}-en)*
"""

HIGHLIGHT_ITEM_ZH = """### {score:.1f} [{title}]({url})

> {summary}

**来源**: {source} · {source_type}

{detailed_content}

{tags}
"""

CATEGORY_SECTION_ZH = """## {icon} {category_name}

{items}
"""

CATEGORY_ITEM_ZH = """### {score:.1f} [{title}]({url})

{summary}

**来源**: {source} · AI评分: {score:.1f} · 相关度: {relevance:.0%}

{enrichment}

{tags}

---
"""

ENRICHMENT_SECTION_ZH = """{whats_new}

{why_it_matters}

{key_details}

{background}

{references}

{community_discussion}"""


# ============ 英文模板 ============

TEMPLATE_EN = """---
layout: daily
title: "Insurance Daily - {date}"
date: {date}
lang: en
total_items: {total_items}
avg_score: {avg_score}
---

# 📋 InsureScope Insurance Daily

**{date}** · AI-curated from {total_sources} sources · {total_items} notable items selected from {total_fetched}

---

## 🌟 Today's Highlights

{highlights_en}

---

{categories_en}

---

## 🏷️ Tag Cloud

{tag_cloud_en}

---

*InsureScope — AI-Driven Insurance Information Aggregation · [中文版](./{date}-zh)*
"""

HIGHLIGHT_ITEM_EN = """### {score:.1f} [{title}]({url})

> {summary}

**Source**: {source} · {source_type}

{detailed_content}

{tags}
"""

CATEGORY_SECTION_EN = """## {icon} {category_name}

{items}
"""

CATEGORY_ITEM_EN = """### {score:.1f} [{title}]({url})

{summary}

**Source**: {source} · AI Score: {score:.1f} · Relevance: {relevance:.0%}

{enrichment}

{tags}

---
"""


CATEGORY_ICONS = {
    "regulation": "🏛️",
    "product": "📦",
    "industry": "📊",
    "research": "🔬",
    "claims": "⚖️",
}

CATEGORY_NAMES_ZH = {
    "regulation": "监管政策",
    "product": "产品发布/更新",
    "industry": "行业动态",
    "research": "论文研究",
    "claims": "理赔与案例",
}

CATEGORY_NAMES_EN = {
    "regulation": "Regulation & Policy",
    "product": "Product Releases",
    "industry": "Industry Dynamics",
    "research": "Research & Papers",
    "claims": "Claims & Cases",
}


class SummaryGenerator:
    """每日简报生成器 - Horizon 风格"""

    def __init__(self, config: dict):
        self.config = config
        self.categories = get_categories(config)

    def generate(self, summary: "DailySummary", total_fetched: int = 0) -> dict[str, str]:
        """生成中英双语简报"""
        total_sources = len(set(item.source_name for item in summary.items))

        # 按分类组织
        by_category: dict[str, list["NewsItem"]] = {}
        for item in summary.items:
            cat = item.category or "industry"
            by_category.setdefault(cat, []).append(item)

        # 生成高亮部分
        highlights_zh = self._render_highlights(summary.highlights, "zh")
        highlights_en = self._render_highlights(summary.highlights, "en")

        # 生成分类部分
        categories_zh = self._render_categories(by_category, "zh")
        categories_en = self._render_categories(by_category, "en")

        # 生成标签云
        tag_cloud = self._render_tag_cloud(summary.items, "zh")
        tag_cloud_en = self._render_tag_cloud(summary.items, "en")

        # 日期格式
        date_str = summary.date
        date_zh = self._format_date_zh(date_str)

        # 生成中文简报
        zh_md = TEMPLATE_ZH.format(
            date=date_str,
            date_zh=date_zh,
            total_sources=total_sources,
            total_fetched=total_fetched or summary.total_items,
            total_items=summary.total_items,
            avg_score=round(summary.avg_score, 1),
            highlights_zh=highlights_zh,
            categories_zh=categories_zh,
            tag_cloud=tag_cloud,
        )

        # 生成英文简报
        en_md = TEMPLATE_EN.format(
            date=date_str,
            total_sources=total_sources,
            total_fetched=total_fetched or summary.total_items,
            total_items=summary.total_items,
            avg_score=round(summary.avg_score, 1),
            highlights_en=highlights_en,
            categories_en=categories_en,
            tag_cloud_en=tag_cloud_en,
        )

        return {"zh": zh_md, "en": en_md}

    def _render_highlights(self, highlights: list["NewsItem"], lang: str) -> str:
        """渲染高亮部分"""
        if not highlights:
            return "今日无特别高亮内容。" if lang == "zh" else "No highlighted items today."

        template = HIGHLIGHT_ITEM_ZH if lang == "zh" else HIGHLIGHT_ITEM_EN
        parts = []
        for item in highlights:
            # 渲染详细内容
            detailed = self._render_detailed_content(item, lang)
            # 渲染标签
            tags = self._render_tags(item.ai_tags, lang)
            
            parts.append(template.format(
                score=item.ai_score,
                title=item.title,
                summary=item.ai_summary or item.content[:200],
                source=item.source_name,
                source_type=item.source_type,
                url=item.url,
                detailed_content=detailed,
                tags=tags,
            ))
        return "\n".join(parts)

    def _render_detailed_content(self, item: "NewsItem", lang: str) -> str:
        """渲染详细内容（Horizon 风格）"""
        parts = []
        
        # What's New
        if item.whats_new:
            label = "**最新动态**" if lang == "zh" else "**What's New**"
            parts.append(f"{label}: {item.whats_new}")
        
        # Why It Matters
        if item.why_it_matters:
            label = "**行业影响**" if lang == "zh" else "**Why It Matters**"
            parts.append(f"{label}: {item.why_it_matters}")
        
        # Key Details
        if item.key_details:
            label = "**关键细节**" if lang == "zh" else "**Key Details**"
            parts.append(f"{label}: {item.key_details}")
        
        # Background
        if item.background:
            label = "**背景知识**" if lang == "zh" else "**Background**"
            bg_parts = []
            for bg in item.background[:3]:
                concept = bg.get('concept', '')
                explanation = bg.get('explanation', '')
                if concept and explanation:
                    bg_parts.append(f"- **{concept}**: {explanation}")
            if bg_parts:
                parts.append(f"{label}:\n" + "\n".join(bg_parts))
        
        # References
        if item.references:
            label = "**参考链接**" if lang == "zh" else "**References**"
            ref_parts = []
            for ref in item.references[:3]:
                title = ref.get('title', '')
                url = ref.get('url', '')
                desc = ref.get('description', '')
                if title and url:
                    ref_parts.append(f"- [{title}]({url})" + (f" - {desc}" if desc else ""))
            if ref_parts:
                parts.append(f"{label}:\n" + "\n".join(ref_parts))
        
        # Community Discussion
        if item.community_discussion:
            label = "**社区讨论**" if lang == "zh" else "**Community Discussion**"
            parts.append(f"{label}: {item.community_discussion}")
        
        return "\n\n".join(parts) if parts else ""

    def _render_categories(self, by_category: dict[str, list["NewsItem"]], lang: str) -> str:
        """渲染分类部分"""
        section_template = CATEGORY_SECTION_ZH if lang == "zh" else CATEGORY_SECTION_EN
        item_template = CATEGORY_ITEM_ZH if lang == "zh" else CATEGORY_ITEM_EN
        names = CATEGORY_NAMES_ZH if lang == "zh" else CATEGORY_NAMES_EN

        parts = []
        for cat_key in ["regulation", "product", "industry", "research", "claims"]:
            items = by_category.get(cat_key, [])
            if not items:
                continue

            icon = CATEGORY_ICONS.get(cat_key, "📌")
            name = names.get(cat_key, cat_key)

            items_md = []
            for item in items:
                # 渲染增强内容
                enrichment = self._render_enrichment_brief(item, lang)
                # 渲染标签
                tags = self._render_tags(item.ai_tags, lang)
                
                items_md.append(item_template.format(
                    score=item.ai_score,
                    title=item.title,
                    url=item.url,
                    summary=item.ai_summary or "",
                    source=item.source_name,
                    relevance=item.insurance_relevance,
                    enrichment=enrichment,
                    tags=tags,
                ))

            parts.append(section_template.format(
                icon=icon,
                category_name=name,
                items="\n".join(items_md),
            ))

        return "\n".join(parts)

    def _render_enrichment_brief(self, item: "NewsItem", lang: str) -> str:
        """渲染简化的增强内容（用于分类列表）"""
        parts = []
        
        if item.whats_new:
            label = "📌 最新动态" if lang == "zh" else "📌 What's New"
            parts.append(f"**{label}**: {item.whats_new}")
        
        if item.why_it_matters:
            label = "💡 行业影响" if lang == "zh" else "💡 Why It Matters"
            parts.append(f"**{label}**: {item.why_it_matters}")
        
        if item.background:
            label = "📚 背景知识" if lang == "zh" else "📚 Background"
            bg_texts = []
            for bg in item.background[:2]:
                concept = bg.get('concept', '')
                explanation = bg.get('explanation', '')
                if concept:
                    bg_texts.append(f"**{concept}**" + (f": {explanation[:50]}..." if explanation else ""))
            if bg_texts:
                parts.append(f"**{label}**: " + " | ".join(bg_texts))
        
        return "\n\n".join(parts) if parts else ""

    def _render_tags(self, tags: list[str], lang: str) -> str:
        """渲染标签"""
        if not tags:
            return ""
        tag_links = []
        for tag in tags[:8]:  # 最多显示8个标签
            tag_links.append(f"`{tag}`")
        return " ".join(tag_links)

    def _render_tag_cloud(self, items: list["NewsItem"], lang: str) -> str:
        """渲染标签云"""
        # 收集所有标签并统计频率
        tag_counts = {}
        for item in items:
            for tag in item.ai_tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        if not tag_counts:
            return "暂无标签" if lang == "zh" else "No tags yet"
        
        # 按频率排序
        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        
        # 渲染标签云
        tag_links = []
        for tag, count in sorted_tags[:20]:  # 最多显示20个标签
            tag_links.append(f"`{tag}`({count})")
        
        return " ".join(tag_links)

    def _format_date_zh(self, date_str: str) -> str:
        """格式化中文日期"""
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            return f"{d.year}年{d.month}月{d.day}日 星期{weekdays[d.weekday()]}"
        except ValueError:
            return date_str

    def save(self, summary: "DailySummary", total_fetched: int = 0, output_dir: Path | None = None, suffix: str = "") -> dict[str, Path]:
        """保存简报到文件
        
        Args:
            summary: 日报数据
            total_fetched: 采集总数
            output_dir: 输出目录
            suffix: 文件名后缀（如 "-full" 表示全量模式）
        """
        if output_dir is None:
            output_dir = get_project_root() / "data" / "summaries"

        output_dir.mkdir(parents=True, exist_ok=True)

        contents = self.generate(summary, total_fetched)

        # 保存 Markdown
        paths = {}
        for lang, content in contents.items():
            filename = f"{summary.date}-{lang}{suffix}.md"
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            paths[lang] = filepath

        # 保存 JSON 数据
        json_filename = f"{summary.date}{suffix}.json"
        json_path = output_dir / json_filename
        json_data = {
            "date": summary.date,
            "total_items": summary.total_items,
            "avg_score": round(summary.avg_score, 1),
            "items": [item.to_dict() for item in summary.items],
            "highlights": [item.to_dict() for item in summary.highlights],
            "by_category": {
                cat: [item.to_dict() for item in items]
                for cat, items in summary.by_category.items()
            },
        }
        json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["json"] = json_path

        # 复制到 docs 目录（用于 GitHub Pages）- 仅精选模式
        if not suffix:
            docs_dir = get_project_root() / "docs" / "_posts"
            docs_dir.mkdir(parents=True, exist_ok=True)
            for lang in ("zh", "en"):
                src = output_dir / f"{summary.date}-{lang}.md"
                dst = docs_dir / f"{summary.date}-{lang}.md"
                if src.exists():
                    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        return paths
