# -*- coding: utf-8 -*-
"""
端到端验证：用 Playwright 启动一个临时 context，注入拼多多桌面端 cookie，
访问 ERP 审核页，看是否能直接进入（免扫码）。
不使用项目的持久化 context，避免污染登录态。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from playwright.sync_api import sync_playwright
from spider.pinduoduo.pdd_desktop_cookies import get_playwright_cookies, pick_best_profile, DEFAULT_USER_DATA_DIR
from config import Config

ERP_URL = getattr(Config, 'PINDUODUO_ERP_ORDER_AUDIT_URL', None) or 'https://mms.pinduoduo.com/erp/order/audit'

best = pick_best_profile(DEFAULT_USER_DATA_DIR)
print(f"best profile = {best}")
cookies = get_playwright_cookies(DEFAULT_USER_DATA_DIR, profile=best)
print(f"cookies count = {len(cookies)}")
if not cookies:
    print("没有可用 cookie，退出")
    raise SystemExit(1)

with sync_playwright() as p:
    # 临时用户数据目录，避免锁住项目持久化目录
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="pdd_e2e_")
    # 用 PddBrowser 风格 UA（Chromium 104），看是否指纹校验导致会话失效
    pdd_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36 PddBrowser/104.5.97.0"
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=tmpdir,
        headless=False,
        no_viewport=True,
        user_agent=pdd_ua,
        args=['--disable-blink-features=AutomationControlled', '--start-maximized'],
    )
    try:
        n = 0
        try:
            ctx.add_cookies(cookies)
            n = len(cookies)
        except Exception as e:
            print(f"add_cookies 失败: {e}")
        print(f"注入 cookie {n} 条")
        page = ctx.new_page()
        print(f"goto {ERP_URL}")
        try:
            page.goto(ERP_URL, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            print(f"goto 超时/失败: {e}")
        page.wait_for_timeout(3000)
        final_url = page.url
        print(f"最终 URL: {final_url}")
        from urllib.parse import urlparse
        path = urlparse(final_url).path or ''
        if '/login' in path or '/passport' in path:
            print("结果: 仍在登录页 → 桌面 cookie 未能免扫码（可能已过期或属于其他店铺）")
        else:
            print("结果: 已进入 ERP → 桌面 cookie 复用成功！")
            try:
                page.screenshot(path=str(Path(tmpdir) / "erp_landed.png"), full_page=False)
                print(f"截图: {Path(tmpdir) / 'erp_landed.png'}")
            except Exception:
                pass
        page.wait_for_timeout(5000)
    finally:
        ctx.close()
