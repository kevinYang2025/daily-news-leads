#!/usr/bin/env python3
"""每日新闻线索分析 — 主入口。

用法：
    python main.py                 # 跑当天窗口
    python main.py --dry-run       # 不调用 LLM，验证采集链路
    python main.py --window 24     # 指定回溯小时数
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

import config as cfg
from analyzer import analyze
from collectors import collect_all
from processors import process
from renderer import build_report, write_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="每日新闻线索分析管线")
    parser.add_argument("--dry-run", action="store_true", help="跳过 Gemini，使用规则式摘要")
    parser.add_argument("--window", type=int, default=None, help="回溯小时数，默认 24")
    parser.add_argument("--no-body", action="store_true", help="跳过正文抽取，加快速度")
    args = parser.parse_args()

    if args.window:
        cfg.WINDOW_HOURS = args.window
    if args.dry_run:
        cfg.GEMINI_API_KEY = ""

    start, end = cfg.compute_window()
    print(f"[run] 窗口：{start} → {end}（{cfg.LOCAL_TZ}）")

    articles, errors = collect_all(start, end)
    total_fetched = len(articles)
    print(f"[run] 原始采集：{total_fetched} 条，错误 {len(errors)} 项")

    if args.no_body:
        cfg.FETCH_TIMEOUT = 5

    articles, dropped = process(articles, start, end, errors)
    print(f"[run] 处理后：{len(articles)} 条（窗口外剔除 {dropped} 条）")

    if not articles:
        errors.append("所有信源均未返回窗口内新闻，请检查网络或信源配置")

    brief, cross_domain, leads = analyze(articles, start, end, errors)
    print(f"[run] 输出线索：{len(leads)} 条")

    report = build_report(articles, leads, brief, cross_domain, errors, total_fetched, dropped, start, end)
    project_root = os.path.dirname(os.path.abspath(__file__))
    md_path, js_path = write_outputs(report, articles, project_root)
    print(f"[run] 报告：{md_path}")
    print(f"[run] 看板数据：{js_path}")

    if errors:
        print(f"[run] 提示 {len(errors)} 项：")
        for e in errors[:10]:
            print(f"  - {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
