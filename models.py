"""统一数据模型：所有信源归一化为 Article，分析结果归一化为 Lead。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """一条归一化新闻。"""

    title: str
    url: str
    source: str
    published_at: Optional[datetime]
    category: str
    summary: str = ""
    body: str = ""
    language: str = ""
    origin: str = ""  # gdelt / google_news / media_rss / hotlist
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "category": self.category,
            "summary": self.summary,
            "body": self.body[:1200],
            "language": self.language,
            "origin": self.origin,
            "score": round(self.score, 2),
        }


@dataclass
class SourceRef:
    """线索引用的一条原始报道。"""

    title: str
    url: str
    publisher: str
    published_at: str = ""


@dataclass
class Lead:
    """LLM 抽取的一条新闻线索。"""

    id: str
    category: str
    title: str
    summary: str
    key_facts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    impact: str = ""
    confidence: str = "medium"  # high / medium / low
    importance: str = "medium"  # high / medium / low
    followups: list[str] = field(default_factory=list)
    sources: list[SourceRef] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "key_facts": self.key_facts,
            "entities": self.entities,
            "impact": self.impact,
            "confidence": self.confidence,
            "importance": self.importance,
            "followups": self.followups,
            "sources": [
                {"title": s.title, "url": s.url, "publisher": s.publisher, "published_at": s.published_at}
                for s in self.sources
            ],
            "related": self.related,
            "timeline": self.timeline,
        }


@dataclass
class RunReport:
    """一次完整跑批的元数据与结果。"""

    window_start: str
    window_end: str
    generated_at: str
    timezone: str
    total_fetched: int = 0
    total_after_filter: int = 0
    total_leads: int = 0
    source_stats: dict = field(default_factory=dict)
    category_stats: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    brief: str = ""
    cross_domain: list[str] = field(default_factory=list)
    leads: list[Lead] = field(default_factory=list)

    def to_dict(self, articles: Optional[list[Article]] = None) -> dict:
        return {
            "window_start": self.window_start,
            "window_end": self.window_end,
            "generated_at": self.generated_at,
            "timezone": self.timezone,
            "total_fetched": self.total_fetched,
            "total_after_filter": self.total_after_filter,
            "total_leads": self.total_leads,
            "source_stats": self.source_stats,
            "category_stats": self.category_stats,
            "errors": self.errors,
            "brief": self.brief,
            "cross_domain": self.cross_domain,
            "leads": [lead.to_dict() for lead in self.leads],
            "articles": [a.to_dict() for a in (articles or [])][:200],
        }
