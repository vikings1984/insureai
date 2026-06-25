"""数据模型定义"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    """单条资讯条目"""

    title: str
    url: str
    source_name: str
    source_type: str  # rss, reddit, hackernews, github, wechat
    content: str = ""
    published_at: Optional[datetime] = None
    fetched_at: datetime = field(default_factory=datetime.now)
    language: str = "zh"

    # 互动指标
    engagement_score: Optional[float] = None
    comment_count: Optional[int] = None
    upvote_ratio: Optional[float] = None

    # AI 分析结果
    ai_score: float = 0.0
    ai_reason: str = ""
    ai_summary: str = ""
    ai_tags: list[str] = field(default_factory=list)
    insurance_relevance: float = 0.0  # 0-1, 保险相关度
    category: str = ""  # regulation, product, industry, research, claims

    # 增强结果
    whats_new: str = ""
    why_it_matters: str = ""
    key_details: str = ""
    background: list[dict] = field(default_factory=list)
    references: list[dict] = field(default_factory=list)
    community_discussion: str = ""
    detailed_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "content": self.content[:500],
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "fetched_at": self.fetched_at.isoformat(),
            "language": self.language,
            "engagement_score": self.engagement_score,
            "ai_score": self.ai_score,
            "ai_reason": self.ai_reason,
            "ai_summary": self.ai_summary,
            "ai_tags": self.ai_tags,
            "insurance_relevance": self.insurance_relevance,
            "category": self.category,
            "whats_new": self.whats_new,
            "why_it_matters": self.why_it_matters,
            "key_details": self.key_details,
            "background": self.background,
            "references": self.references,
            "community_discussion": self.community_discussion,
        }


@dataclass
class DailySummary:
    """每日简报"""

    date: str  # YYYY-MM-DD
    items: list[NewsItem] = field(default_factory=list)
    highlights: list[NewsItem] = field(default_factory=list)
    by_category: dict[str, list[NewsItem]] = field(default_factory=dict)
    overview_zh: str = ""
    overview_en: str = ""

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def avg_score(self) -> float:
        return sum(i.ai_score for i in self.items) / max(len(self.items), 1)
