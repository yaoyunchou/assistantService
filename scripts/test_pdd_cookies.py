# -*- coding: utf-8 -*-
"""快速验证 pdd_desktop_cookies 模块能正确输出 Playwright 格式 cookie。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spider.pinduoduo.pdd_desktop_cookies import (
    get_playwright_cookies,
    list_profiles,
    pick_best_profile,
    DEFAULT_USER_DATA_DIR,
)

print("=== 所有 profile ===")
for p in list_profiles(DEFAULT_USER_DATA_DIR):
    print(f"  {p['name']:40s} {p['mtime_str']}  {p['cookies_path']}")

print("\n=== 自动挑选最佳 profile ===")
best = pick_best_profile(DEFAULT_USER_DATA_DIR)
print(f"  best = {best}")

print("\n=== Playwright 格式 cookie（前 8 条）===")
cks = get_playwright_cookies(DEFAULT_USER_DATA_DIR, profile=best)
for c in cks[:8]:
    v = c["value"]
    if len(v) > 50:
        v = v[:50] + "..."
    print(f"  {c['domain']:30s} {c['name']:25s} expires={c['expires']:.0f} secure={c['secure']} httpOnly={c['httpOnly']} sameSite={c['sameSite']} val={v!r}")
print(f"\n共 {len(cks)} 条")
print("\n=== 抽样 JSON（首条）===")
print(json.dumps(cks[0], ensure_ascii=False, indent=2) if cks else "(空)")
