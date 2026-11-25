"""多源新闻采集层。

设计原则：任一信源失败不影响整体，所有异常记录到 errors 并继续。
优先级：GDELT（全球覆盖） > Google News RSS（按主题） > 媒体 RSS（兜底） > 热榜（国内情绪）。
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

import config as cfg
from models import Article


def _get(url: str, params: Optional[dict] = None, timeout: int = None) -> requests.Response:
    return requests.get(
        url,
        params=params,
        timeout=timeout or cfg.FETCH_TIMEOUT,
        headers={"User-Agent": cfg.USER_AGENT, "Accept": "*/*"},
    )


def _parse_date(value: str) -> Optional[datetime]:
    """兼容 RFC822 / ISO8601 / GDELT YYYYMMDDHHMMSS。"""
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        return datetime.strptime(value[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;|&apos;", "'", text)
    return re.sub(r"\s+", " ", text).strip()


def collect_gdelt(start: datetime, end: datetime, errors: list[str]) -> list[Article]:
    """GDELT DOC 2.0：全球新闻全文检索，支持精确时间窗与主题过滤。"""
    articles: list[Article] = []
    start_s = start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    end_s = end.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")

    # 每个分类取 1~2 个高区分度检索式，避免请求过多触发限流
    plan: list[tuple[str, str]] = []
    for cat, meta in cfg.CATEGORIES.items():
        for q in meta["queries"][:2]:
            plan.append((cat, q))

    for idx, (cat, query) in enumerate(plan):
        if idx > 0:
            time.sleep(cfg.GDELT_REQUEST_INTERVAL)
        try:
            resp = _get(
                cfg.GDELT_ENDPOINT,
                params={
                    "query": query,
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": cfg.GDELT_MAX_RECORDS,
                    "startdatetime": start_s,
                    "enddatetime": end_s,
                    "sort": "datedesc",
                },
            )
            if resp.status_code != 200:
                errors.append(f"GDELT[{query}] HTTP {resp.status_code}")
                continue
            payload = resp.json()
            for item in payload.get("articles", []):
                title = _strip_html(item.get("title", ""))
                url = item.get("url", "")
                if len(title) < cfg.MIN_TITLE_LEN or not url.startswith("http"):
                    continue
                articles.append(
                    Article(
                        title=title,
                        url=url,
                        source=item.get("domain") or "GDELT",
                        published_at=_parse_date(item.get("seendate", "")),
                        category=cat,
                        summary=_strip_html(item.get("title", ""))[:300],
                        language=item.get("language", ""),
                        origin="gdelt",
                        score=10.0,  # GDELT 覆盖最广，基础分最高
                    )
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GDELT[{query}] {type(exc).__name__}: {exc}")
    return articles


def _parse_rss(xml_text: str, category: str, source_name: str, origin: str) -> list[Article]:
    articles: list[Article] = []
    root = ET.fromstring(xml_text)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for item in items:
        def txt(tag: str, ns: str = "") -> str:
            node = item.find(f"{ns}{tag}") if ns else item.find(tag)
            return node.text.strip() if node is not None and node.text else ""

        title = _strip_html(txt("title")) or _strip_html(txt("title", "{http://www.w3.org/2005/Atom}"))
        link_node = item.find("link")
        if link_node is None:
            link_node = item.find("{http://www.w3.org/2005/Atom}link")
        url = ""
        if link_node is not None:
            url = link_node.get("href") or (link_node.text or "").strip()
        if not url:
            continue
        desc = txt("description") or txt("summary", "{http://www.w3.org/2005/Atom}")
        pub = txt("pubDate") or txt("published", "{http://www.w3.org/2005/Atom}") or txt("updated", "{http://www.w3.org/2005/Atom}")

        # Google News 的 <source> 标签带真实媒体名
        src_node = item.find("source")
        publisher = src_node.text.strip() if src_node is not None and src_node.text else source_name

        if len(title) < cfg.MIN_TITLE_LEN:
            continue
        articles.append(
            Article(
                title=title,
                url=url,
                source=publisher,
                published_at=_parse_date(pub),
                category=category,
                summary=_strip_html(desc)[:500],
                origin=origin,
                score=8.0 if origin == "google_news" else 6.0,
            )
        )
    return articles


def collect_google_news(errors: list[str]) -> list[Article]:
    """Google News RSS：每个分类检索近 24 小时。"""
    articles: list[Article] = []
    queries: list[tuple[str, str, dict]] = []
    for cat, meta in cfg.CATEGORIES.items():
        for q in meta["queries"][:1]:
            if not cfg.GOOGLE_NEWS_LOCALES:
                continue
            locale = cfg.GOOGLE_NEWS_LOCALES[0] if cat != "tech_ai" else cfg.GOOGLE_NEWS_LOCALES[1]
            queries.append((cat, q, locale))
        for q in meta["zh_queries"][:1]:
            locale = cfg.GOOGLE_NEWS_LOCALES[1]
            queries.append((cat, q, locale))

    seen_query: set[str] = set()
    for cat, query, locale in queries:
        key = (cat, query, locale["hl"])
        if key in seen_query:
            continue
        seen_query.add(key)
        try:
            resp = _get(
                cfg.GOOGLE_NEWS_RSS,
                params={
                    "q": f"{query} when:1d",
                    "hl": locale["hl"],
                    "gl": locale["gl"],
                    "ceid": locale["ceid"],
                },
            )
            if resp.status_code != 200:
                errors.append(f"GoogleNews[{query}] HTTP {resp.status_code}")
                continue
            articles.extend(_parse_rss(resp.text, cat, "Google News", "google_news"))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GoogleNews[{query}] {type(exc).__name__}: {exc}")
    return articles


def collect_media_rss(errors: list[str]) -> list[Article]:
    """媒体官方 RSS：信源不可用时的兜底。

    媒体源按栏目整体抓取，需按分类关键词二次过滤，避免航天/健康等无关内容混入。
    """
    articles: list[Article] = []
    for feed in cfg.MEDIA_RSS:
        try:
            resp = _get(feed["url"])
            if resp.status_code != 200:
                errors.append(f"RSS[{feed['name']}] HTTP {resp.status_code}")
                continue
            parsed = _parse_rss(resp.text, feed["category"], feed["name"], "media_rss")
            # 按标题动态判类：英文用词边界匹配（避免 us/ai 等短词误命中），中文用子串
            import re

            def hits(title: str, keywords: list[str]) -> int:
                n = 0
                for kw in keywords:
                    if re.search(r"[\u4e00-\u9fff]", kw):
                        if kw in title:
                            n += 1
                    else:
                        if re.search(r"\b" + re.escape(kw.strip()) + r"\b", title):
                            n += 1
                return n

            kept: list[Article] = []
            for a in parsed:
                title_l = a.title.lower()
                best_cat, best_hits = None, 0
                for cat, keywords in cfg.RELEVANCE_KEYWORDS.items():
                    h = hits(title_l, keywords)
                    if h > best_hits:
                        best_cat, best_hits = cat, h
                if best_cat and best_hits >= 1:
                    a.category = best_cat
                    kept.append(a)
                    articles.append(a)
            print(f"[collect] RSS[{feed['name']}] {len(parsed)} → {len(kept)} 条相关")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"RSS[{feed['name']}] {type(exc).__name__}: {exc}")
    return articles


def collect_hotlist(errors: list[str]) -> list[Article]:
    """国内科技热榜补充（DailyHotApi 风格端点）。"""
    if not cfg.HOT_API_BASE:
        return []
    articles: list[Article] = []
    endpoints = ["36kr", "zhihu", "weibo", "toutiao"]
    for ep in endpoints:
        try:
            resp = _get(f"{cfg.HOT_API_BASE}/{ep}")
            if resp.status_code != 200:
                continue
            payload = resp.json()
            data = payload.get("data", [])
            items = data if isinstance(data, list) else []
            for item in items[:30]:
                title = _strip_html(item.get("title", ""))
                if len(title) < cfg.MIN_TITLE_LEN:
                    continue
                # 只保留命中科技关键词的热榜条目
                if not any(k in title for k in ["AI", "人工智能", "机器人", "智能", "汽车", "电池", "芯片", "大模型"]):
                    continue
                url = item.get("url") or item.get("link") or item.get("mobileUrl") or ""
                if not url:
                    continue
                articles.append(
                    Article(
                        title=title,
                        url=url,
                        source=item.get("source") or ep,
                        published_at=None,  # 热榜无精确时间，后续按窗口内处理
                        category="tech_ai",
                        summary=_strip_html(item.get("desc", ""))[:300],
                        language="zh",
                        origin="hotlist",
                        score=4.0,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Hotlist[{ep}] {type(exc).__name__}: {exc}")
    return articles


def collect_all(start: datetime, end: datetime) -> tuple[list[Article], list[str]]:
    errors: list[str] = []
    buckets: list[Article] = []
    for name, fn in [
        ("GDELT", lambda: collect_gdelt(start, end, errors)),
        ("GoogleNews", lambda: collect_google_news(errors)),
        ("MediaRSS", lambda: collect_media_rss(errors)),
        ("Hotlist", lambda: collect_hotlist(errors)),
    ]:
        try:
            got = fn()
            buckets.extend(got)
            print(f"[collect] {name}: {len(got)} 条")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name} 整体失败: {type(exc).__name__}: {exc}")
    return buckets, errors
