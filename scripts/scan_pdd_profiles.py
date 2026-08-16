# -*- coding: utf-8 -*-
"""扫描 PddBrowser 所有 profile，找出含 pinduoduo 登录态 cookie 的 profile。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_pdd_cookies import read_cookies, DEFAULT_USER_DATA

user_data = DEFAULT_USER_DATA
print(f"User Data: {user_data}")
if not user_data.is_dir():
    print("目录不存在")
    raise SystemExit(1)

for prof in sorted(user_data.iterdir()):
    if not prof.is_dir():
        continue
    cookies_file = prof / "Network" / "Cookies"
    if not cookies_file.is_file():
        continue
    try:
        rows = read_cookies(user_data, prof.name, host_filter="pinduoduo.com")
    except Exception as e:
        print(f"[{prof.name}] 读取失败: {e}")
        continue
    pdd_rows = [r for r in rows if "pinduoduo" in r["host"]]
    print(f"[{prof.name}] 共 {len(rows)} 条 cookie，pinduoduo 相关 {len(pdd_rows)} 条")
    for r in pdd_rows[:15]:
        print(f"    {r['host']:35s} {r['name']:30s} len={len(r['value'] or '')}")
