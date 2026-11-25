"""Gemini 分析层：把归一化文章转成结构化新闻线索。

输出严格 JSON；无 API Key 时自动降级为规则式摘要，保证管线始终能出报告。
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from typing import Optional

import requests

import config as cfg
from models import Article, Lead, SourceRef

SYSTEM_PROMPT = """你是一名资深科技与地缘政治情报分析师。请从给定新闻中提炼「新闻线索」，供用户做选题与研判。

要求：
1. 只使用提供材料中的事实，不得编造人物、机构、数字、事件。材料不足时明确写「材料有限」。
2. 把同一事件的不同报道合并为一条线索，跨来源印证时提升 confidence。
3. 每条线索必须包含：
   - id: 短横线连接的英文小写标识，如 ai-humanoid-robot-001
   - category: 必须取自给定分类 ID 之一
   - title: 中文，不超过 30 字，聚焦事实
   - summary: 中文，2-3 句说明发生了什么
   - key_facts: 2-5 条关键事实（中文，每条不超过 60 字）
   - entities: 涉及的公司/机构/国家/人物
   - impact: 中文，1-3 句说明可能影响与值得关注的原因
   - confidence: high/medium/low（多源一致为 high，单源为 medium，模糊为 low）
   - importance: high/medium/low（对用户的选题价值）
   - followups: 1-3 个后续应跟踪的问题
   - source_indexes: 支撑该线索的文章序号数组（从 0 开始）
   - related: 与其他线索 id 的关联（可选）
4. 最后给出 brief（今日整体研判，中文 3-5 句）和 cross_domain（跨领域关联观察，中文 2-4 条）。

只输出 JSON，不要 markdown 代码块，不要解释。格式：
{"brief":"...","cross_domain":["..."],"leads":[{"id":"...","category":"...","title":"...","summary":"...","key_facts":[],"entities":[],"impact":"...","confidence":"medium","importance":"medium","followups":[],"source_indexes":[0],"related":[]}]}
"""


def _call_gemini(prompt: str, errors: list[str], retries: int = 2) -> Optional[dict]:
    if not cfg.GEMINI_API_KEY:
        return None
    # 官方推荐用 x-goog-api-key 请求头传递密钥（新版 AQ. 认证密钥尤其需要）
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{cfg.GEMINI_MODEL}:generateContent"
    )
    headers = {"x-goog-api-key": cfg.GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": cfg.LLM_MAX_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=90)
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            if resp.status_code != 200:
                # 提取错误 reason，便于诊断新版 Key 的 ACCESS_TOKEN_TYPE_UNSUPPORTED
                reason = ""
                try:
                    reason = resp.json().get("error", {}).get("status", "")
                except Exception:  # noqa: BLE001
                    pass
                errors.append(f"Gemini HTTP {resp.status_code} {reason}: {resp.text[:180]}")
                return None
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
            return json.loads(text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Gemini {type(exc).__name__}: {exc}")
            if attempt < retries:
                time.sleep(2)
    return None


def _build_prompt(articles: list[Article], start, end) -> str:
    lines = [
        f"报道窗口：{start.strftime('%Y-%m-%d %H:%M')} 至 {end.strftime('%Y-%m-%d %H:%M')}（北京时间）",
        f"可用分类 ID：{', '.join(cfg.CATEGORIES.keys())}",
        "",
        "新闻列表（每条前面的数字为 source_indexes 使用的序号）：",
    ]
    for i, a in enumerate(articles):
        pub = a.published_at.strftime("%Y-%m-%d %H:%M UTC") if a.published_at else "时间未知"
        lines.append(
            f"[{i}] 分类={a.category} | 媒体={a.source} | 时间={pub}\n"
            f"标题：{a.title}\n"
            f"摘要：{a.summary[:280]}\n"
            f"正文节选：{a.body[:600]}\n"
            f"链接：{a.url}\n"
        )
    return "\n".join(lines)


def _fallback_analyze(articles: list[Article], start, end, errors: list[str]) -> dict:
    """无 Gemini Key 时的规则式降级：按分类聚类，保留来源，不做事实推断。"""
    errors.append("未配置 GEMINI_API_KEY，已使用规则式摘要降级输出")
    by_cat: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        by_cat[a.category].append(a)

    leads: list[dict] = []
    for cat, items in by_cat.items():
        if not items:
            continue
        for i, a in enumerate(items[:6]):
            leads.append(
                {
                    "id": f"{cat}-{i + 1:03d}",
                    "category": cat,
                    "title": a.title[:30],
                    "summary": a.summary[:220] or "原文未提供摘要，请点击下方来源查看。",
                    "key_facts": [f"{a.source} 于 {a.published_at.strftime('%m-%d %H:%M') if a.published_at else '近期'} 报道：{a.title[:70]}"],
                    "entities": [a.source],
                    "impact": "待分析（当前为无 Key 降级输出，配置 GEMINI_API_KEY 后可获得影响研判）",
                    "confidence": "medium" if a.origin != "hotlist" else "low",
                    "importance": "medium",
                    "followups": ["核实事件细节与后续进展"],
                    "source_indexes": [articles.index(a)],
                    "related": [],
                }
            )
    return {
        "brief": f"本窗口共采集 {len(articles)} 条报道，覆盖 {len(by_cat)} 个主题。当前为规则式降级输出，配置 GEMINI_API_KEY 后可生成完整研判。",
        "cross_domain": ["配置 GEMINI_API_KEY 后可获得跨领域关联分析"],
        "leads": leads,
    }


def analyze(articles: list[Article], start, end, errors: list[str]) -> tuple[str, list[str], list[Lead]]:
    if not articles:
        return "本时间窗内未采集到有效新闻。", [], []

    result: Optional[dict] = None
    if cfg.GEMINI_API_KEY:
        # 分批送入，避免超出上下文；每批独立抽取线索
        batches = [articles[i : i + cfg.LLM_BATCH_SIZE] for i in range(0, len(articles), cfg.LLM_BATCH_SIZE)]
        merged: dict = {"brief": "", "cross_domain": [], "leads": []}
        for bi, batch in enumerate(batches):
            parsed = _call_gemini(_build_prompt(batch, start, end), errors)
            if not parsed:
                continue
            if bi == 0:
                merged["brief"] = parsed.get("brief", "")
                merged["cross_domain"] = parsed.get("cross_domain", [])
            merged["leads"].extend(parsed.get("leads", []))
            if len(batches) > 1:
                time.sleep(2)
        if merged["leads"]:
            result = merged

    if not result:
        result = _fallback_analyze(articles, start, end, errors)

    leads: list[Lead] = []
    seen_ids: set[str] = set()
    for lead_data in result.get("leads", []):
        try:
            cat = lead_data.get("category", "")
            if cat not in cfg.CATEGORIES:
                cat = articles[0].category if articles else "tech_ai"
            indexes = lead_data.get("source_indexes", []) or []
            refs: list[SourceRef] = []
            for idx in indexes[:6]:
                if isinstance(idx, int) and 0 <= idx < len(articles):
                    a = articles[idx]
                    refs.append(
                        SourceRef(
                            title=a.title,
                            url=a.url,
                            publisher=a.source,
                            published_at=a.published_at.strftime("%Y-%m-%d %H:%M") if a.published_at else "",
                        )
                    )
            lid = str(lead_data.get("id") or f"lead-{len(leads) + 1:03d}")
            if lid in seen_ids:
                continue
            seen_ids.add(lid)
            leads.append(
                Lead(
                    id=lid,
                    category=cat,
                    title=str(lead_data.get("title", ""))[:60],
                    summary=str(lead_data.get("summary", "")),
                    key_facts=[str(x) for x in lead_data.get("key_facts", [])[:6]],
                    entities=[str(x) for x in lead_data.get("entities", [])[:10]],
                    impact=str(lead_data.get("impact", "")),
                    confidence=str(lead_data.get("confidence", "medium")),
                    importance=str(lead_data.get("importance", "medium")),
                    followups=[str(x) for x in lead_data.get("followups", [])[:4]],
                    sources=refs,
                    related=[str(x) for x in lead_data.get("related", [])[:5]],
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"线索解析失败: {type(exc).__name__}: {exc}")

    return str(result.get("brief", "")), [str(x) for x in result.get("cross_domain", [])[:6]], leads
