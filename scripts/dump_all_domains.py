# -*- coding: utf-8 -*-
"""dump 最近活跃 profile 的所有域 cookie（不限 pinduoduo），找鉴权 cookie。"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from spider.pinduoduo.pdd_desktop_cookies import (
    list_profiles, _get_master_key, _read_profile_cookies, DEFAULT_USER_DATA_DIR,
)

profiles = list_profiles(DEFAULT_USER_DATA_DIR)
master = _get_master_key(DEFAULT_USER_DATA_DIR)
now = time.time()
# 取最近活跃的 3 个
for p in profiles[:3]:
    cks = _read_profile_cookies(DEFAULT_USER_DATA_DIR, p["name"], master, host_filter=None)
    print(f"=== {p['name']}  mtime={p['mtime_str']}  共 {len(cks)} 条（所有域）===")
    for c in cks:
        exp = c["expires"]
        exp_str = "session" if exp < 0 else time.strftime('%m-%d %H:%M', time.localtime(exp))
        expired = "EXP" if (exp > 0 and exp < now) else "   "
        v = c["value"]
        if len(v) > 50: v = v[:50] + "..."
        print(f"  [{expired}] {c['domain']:30s} {c['name']:24s} {exp_str}  {v}")
    print()
