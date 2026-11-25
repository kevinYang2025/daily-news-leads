"""处理层：时间窗过滤 → 跨源去重 → 正文抽取 → 排序截断。"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urlparse

import requests

import config as cfg
from models import Article


def _normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def filter_by_window(articles: list[Article], start: datetime, end: datetime) -> tuple[list[Article], int]:
    """按 24h 窗口过滤。无时间戳的来源（热榜）保留，交由后续人工判断。"""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    kept: list[Article] = []
    for a in articles:
        if a.published_at is None:
            kept.append(a)
            continue
        if start_utc <= a.published_at < end_utc:
            kept.append(a)
    return kept, len(articles) - len(kept)


def dedupe(articles: list[Article]) -> list[Article]:
    """URL 精确去重 + 标题模糊去重；保留来源分更高的一条。"""
    articles = sorted(articles, key=lambda a: (-a.score, a.title))
    seen_urls: set[str] = set()
    seen_titles: list[str] = []
    result: list[Article] = []

    for a in articles:
        parsed = urlparse(a.url)
        url_key = (parsed.netloc + parsed.path).rstrip("/").lower()
        if url_key in seen_urls:
            continue
        norm = _normalize_title(a.title)
        if len(norm) < 6:
            continue
        duplicate = False
        for existing in seen_titles:
            if abs(len(norm) - len(existing)) > 20:
                continue
            if SequenceMatcher(None, norm, existing).ratio() >= cfg.DEDUPE_SIMILARITY:
                duplicate = True
                break
        if duplicate:
            continue
        seen_urls.add(url_key)
        seen_titles.append(norm)
        result.append(a)
    return result


def _extract_with_bs4(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        node = soup.find("article") or soup.find("main") or soup.body
        if node is None:
            return ""
        text = re.sub(r"\n{3,}", "\n\n", node.get_text("\n", strip=True))
        return text.strip()
    except Exception:  # noqa: BLE001
        return ""


def extract_bodies(articles: list[Article], limit: int = 40, errors: list[str] | None = None) -> list[Article]:
    """为高价值条目抽取正文；失败时保留 RSS 摘要，不阻断流程。"""
    targets = [a for a in articles[:limit] if not a.body or len(a.body) < 120]
    session = requests.Session()
    session.headers.update({"User-Agent": cfg.USER_AGENT})
    for a in targets:
        try:
            resp = session.get(a.url, timeout=12, allow_redirects=True)
            if resp.status_code != 200:
                continue
            body = _extract_with_bs4(resp.text)
            if len(body) > 120:
                a.body = body[:4000]
        except Exception as exc:  # noqa: BLE001
            if errors is not None:
                errors.append(f"正文抽取失败 {a.source}: {type(exc).__name__}")
        time.sleep(0.3)  # 温和抓取
    return articles


def rank_and_trim(articles: list[Article]) -> list[Article]:
    """按分类均衡 + 来源分 + 正文完整度排序，控制送入 LLM 的总量。"""
    from collections import defaultdict

    by_cat: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_cat[a.category].append(a)

    result: list[Article] = []
    for cat, items in by_cat.items():
        items.sort(key=lambda a: (a.score + (3 if len(a.body) > 120 else 0), a.title))
        result.extend(items[: cfg.MAX_ARTICLES_PER_CATEGORY])
    result.sort(key=lambda a: (-a.score, a.category))
    return result


def process(articles: list[Article], start: datetime, end: datetime, errors: list[str]) -> tuple[list[Article], int]:
    filtered, dropped = filter_by_window(articles, start, end)
    unique = dedupe(filtered)
    unique = extract_bodies(unique, errors=errors)
    unique = rank_and_trim(unique)
    return unique, dropped
