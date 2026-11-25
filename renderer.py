"""输出层：生成 Markdown 报告 + 看板 data.js。"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime

import config as cfg
from models import Article, Lead, RunReport


def render_markdown(report: RunReport) -> str:
    lines = [
        f"# 每日新闻线索分析 · {report.window_end[:10]}",
        "",
        f"> 采集窗口：{report.window_start} → {report.window_end}（{report.timezone}）",
        f"> 生成时间：{report.generated_at}",
        "",
        "## 今日研判",
        "",
        report.brief or "（暂无）",
        "",
        "## 数据概览",
        "",
        f"- 采集原文：{report.total_fetched} 条",
        f"- 窗口内有效：{report.total_after_filter} 条",
        f"- 输出线索：{report.total_leads} 条",
        "",
    ]

    if report.cross_domain:
        lines += ["## 跨领域关联", ""]
        lines += [f"- {x}" for x in report.cross_domain]
        lines.append("")

    lines += ["## 线索明细", ""]
    by_cat: dict[str, list[Lead]] = {}
    for lead in report.leads:
        by_cat.setdefault(lead.category, []).append(lead)

    for cat, leads in by_cat.items():
        label = cfg.CATEGORIES.get(cat, {}).get("label", cat)
        lines.append(f"### {label}")
        lines.append("")
        for lead in leads:
            lines.append(f"#### {lead.title}")
            lines.append("")
            lines.append(f"- **重要度**：{lead.importance}　**可信度**：{lead.confidence}")
            if lead.entities:
                lines.append(f"- **涉及主体**：{'、'.join(lead.entities)}")
            lines.append(f"- **摘要**：{lead.summary}")
            if lead.key_facts:
                lines.append("- **关键事实**：")
                lines += [f"  {i + 1}. {f}" for i, f in enumerate(lead.key_facts)]
            if lead.impact:
                lines.append(f"- **影响研判**：{lead.impact}")
            if lead.followups:
                lines.append("- **待跟踪**：")
                lines += [f"  - {f}" for f in lead.followups]
            if lead.sources:
                lines.append("- **信源**：")
                for s in lead.sources:
                    lines.append(f"  - [{s.publisher}] {s.title} — {s.url}")
            lines.append("")

    if report.errors:
        lines += ["## 运行提示", ""]
        lines += [f"- {e}" for e in report.errors[:20]]
        lines.append("")

    return "\n".join(lines)


def _json_for_js(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")


def render_data_js(report: RunReport, articles: list[Article]) -> str:
    meta = report.to_dict(articles)
    payload = {
        "generatedAt": report.generated_at,
        "window": {"start": report.window_start, "end": report.window_end, "timezone": report.timezone},
        "stats": {
            "fetched": report.total_fetched,
            "valid": report.total_after_filter,
            "leads": report.total_leads,
            "sources": len(report.source_stats),
            "byCategory": report.category_stats,
            "bySource": report.source_stats,
        },
        "brief": report.brief,
        "crossDomain": report.cross_domain,
        "categories": {k: {"label": v["label"], "color": v["color"]} for k, v in cfg.CATEGORIES.items()},
        "leads": [lead.to_dict() for lead in report.leads],
        "errors": report.errors,
    }
    return "window.NEWS_DATA = " + _json_for_js(payload) + ";\n"


def write_outputs(report: RunReport, articles: list[Article], project_root: str) -> tuple[str, str]:
    out_dir = os.path.join(project_root, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    date_str = report.window_end[:10]

    md_path = os.path.join(out_dir, f"news-leads-{date_str}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))

    js_path = os.path.join(project_root, "data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write(render_data_js(report, articles))

    # 最近 30 天索引，便于看板切换历史（按需扩展）
    index_path = os.path.join(out_dir, "index.json")
    index: list[dict] = []
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                index = json.load(f)
        except Exception:  # noqa: BLE001
            index = []
    index = [x for x in index if x.get("date") != date_str]
    index.append({"date": date_str, "file": os.path.basename(md_path), "leads": report.total_leads})
    index = sorted(index, key=lambda x: x["date"], reverse=True)[:30]
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    return md_path, js_path


def build_report(articles: list[Article], leads: list[Lead], brief: str, cross_domain: list[str],
                 errors: list[str], total_fetched: int, dropped: int, start, end) -> RunReport:
    return RunReport(
        window_start=start.strftime("%Y-%m-%d %H:%M"),
        window_end=end.strftime("%Y-%m-%d %H:%M"),
        generated_at=datetime.now(cfg.LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        timezone=str(cfg.LOCAL_TZ),
        total_fetched=total_fetched,
        total_after_filter=len(articles),
        total_leads=len(leads),
        source_stats=dict(Counter(a.source for a in articles).most_common(15)),
        category_stats=dict(Counter(a.category for a in articles)),
        errors=errors,
        brief=brief,
        cross_domain=cross_domain,
        leads=leads,
    )
