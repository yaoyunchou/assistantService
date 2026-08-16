# -*- coding: utf-8 -*-
"""详细 dump 每个 profile 的 pinduoduo cookie（含值、过期时间），找有效会话。"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from spider.pinduoduo.pdd_desktop_cookies import (
    get_playwright_cookies, list_profiles, _get_master_key,
    _read_profile_cookies, DEFAULT_USER_DATA_DIR, ERP_LOGIN_COOKIE_NAMES,
)

now = time.time()
profiles = list_profiles(DEFAULT_USER_DATA_DIR)
master = _get_master_key(DEFAULT_USER_DATA_DIR)
print(f"now(unix)={now:.0f}  {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}")
print()
for p in profiles[:6]:
    cks = _read_profile_cookies(DEFAULT_USER_DATA_DIR, p["name"], master, host_filter="pinduoduo.com")
    print(f"=== {p['name']}  (mtime {p['mtime_str']})  共 {len(cks)} 条 ===")
    for c in cks:
        exp = c["expires"]
        exp_str = "session" if exp < 0 else time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))
        expired = "  [EXPIRED]" if (exp > 0 and exp < now) else ""
        v = c["value"]
        if len(v) > 60: v = v[:60] + "..."
        star = " <<<" if c["name"] in ERP_LOGIN_COOKIE_NAMES else ""
        print(f"  {c['domain']:28s} {c['name']:22s} exp={exp_str}{expired}  val={v}{star}")
    print()
