#!/usr/bin/env python3
"""Gemini API Key 预检：在能连通 Google 的环境验证密钥是否可用。

用法：
    GEMINI_API_KEY='你的key' python check_key.py
    # 或填入 .env 后：python check_key.py

检查项：
  1. Key 格式（新版 AQ. 53 字符 / 旧版 AIza 39 字符）
  2. 网络连通性（能否连到 generativelanguage.googleapis.com）
  3. 模型列表接口（验证认证）
  4. generateContent 实际生成（验证端到端可用）
"""
from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("缺少 requests，请先 pip install requests")
    sys.exit(1)

# 原生读取 .env（不依赖 python-dotenv）
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

KEY = os.getenv("GEMINI_API_KEY", "").strip()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
BASE = "https://generativelanguage.googleapis.com/v1beta"


def section(n: int, title: str) -> None:
    print(f"\n[{n}] {title}")


def main() -> int:
    print("=" * 60)
    print("Gemini API Key 预检")
    print("=" * 60)

    # 1. 格式检查
    section(1, "Key 格式")
    if not KEY:
        print("  ✗ 未配置 GEMINI_API_KEY")
        print("    方式一：export GEMINI_API_KEY='你的key'")
        print("    方式二：在仓库 Settings → Secrets 中配置后由 Actions 注入")
        return 1
    masked = KEY[:3] + "*" * (len(KEY) - 7) + KEY[-4:]
    print(f"  已读取：{masked}（长度 {len(KEY)}）")
    if KEY.startswith("AQ.") and len(KEY) == 53:
        print("  ✓ 新版 Authentication Key 格式正确（AQ. 前缀，53 字符）")
    elif KEY.startswith("AIza") and len(KEY) >= 35:
        print("  ✓ 旧版 Traffic Key 格式正确（AIza 前缀）")
    else:
        print("  ! 格式非标准，但继续尝试调用（以实际结果为准）")

    headers = {"x-goog-api-key": KEY, "Content-Type": "application/json"}

    # 2. 网络连通性
    section(2, "网络连通性")
    try:
        r = requests.get(f"{BASE}/models", headers=headers, timeout=25)
        print(f"  models 端点 HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 无法连接 Google API：{type(exc).__name__}")
        print("    本地网络若屏蔽 Google，请在 GitHub Actions / 境外服务器运行本脚本")
        return 1

    # 3. 认证检查
    section(3, "认证与模型列表")
    if r.status_code != 200:
        reason = ""
        try:
            reason = r.json().get("error", {}).get("status", "")
        except Exception:  # noqa: BLE001
            pass
        print(f"  ✗ 认证失败：HTTP {r.status_code} {reason}")
        if r.status_code == 401 and "UNAUTHENTICATED" in reason:
            print("    新版 AQ. Key 的已知问题：请确认")
            print("    - 在 AI Studio 重新用「Copy key」复制完整 53 字符")
            print("    - AI Studio 中该项目已启用 Gemini API")
            print("    - 如仍失败，在 AI Studio 重新生成 Key（优先试旧版 AIza 若你的账号仍可生成）")
        print(f"    响应：{r.text[:300]}")
        return 1

    models = [m.get("name", "").split("/")[-1] for m in r.json().get("models", [])]
    print(f"  ✓ 认证成功，可用模型 {len(models)} 个")
    flash = [m for m in models if "flash" in m.lower()]
    print(f"  Flash 系列：{flash[:8]}")
    if MODEL not in models:
        print(f"  ! 当前配置的 {MODEL} 不在列表中，建议改用：{flash[0] if flash else models[0] if models else '?'}")

    # 4. 实际生成
    section(4, f"实际生成测试（{MODEL}）")
    try:
        g = requests.post(
            f"{BASE}/models/{MODEL}:generateContent",
            headers=headers,
            json={
                "contents": [{"role": "user", "parts": [{"text": "只回复两个字：可用"}]}],
                "generationConfig": {"maxOutputTokens": 32},
            },
            timeout=60,
        )
        if g.status_code == 200:
            text = g.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"  ✓ 生成成功，模型回复：{text.strip()[:40]}")
            print("\n" + "=" * 60)
            print("结论：Key 完全可用，可填入 GitHub Actions Secrets。")
            print("=" * 60)
            return 0
        reason = ""
        try:
            reason = g.json().get("error", {}).get("status", "")
        except Exception:  # noqa: BLE001
            pass
        print(f"  ✗ 生成失败：HTTP {g.status_code} {reason}")
        print(f"    响应：{g.text[:300]}")
        if g.status_code == 401 and "UNAUTHENTICATED" in reason:
            print("    这是新版 AQ. Key 的已知兼容问题（ACCESS_TOKEN_TYPE_UNSUPPORTED）。")
            print("    建议：在 AI Studio 重新生成 Key，或提交工单给 Google 官方。")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ 生成请求异常：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
