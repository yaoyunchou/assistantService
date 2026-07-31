#!/usr/bin/env python3
"""
独立脚本：不经过 Flask / 浏览器池 / HTTP 接口，直接用 Playwright 打开一个浏览器，
跑一遍「ERP 已发货页」同步流程（与线上 today-printed-query 同一套逻辑），
只是把日期改成「昨天」（默认），打印状态默认「全部」（避免只入库已打印的漏单）。

为什么不用 dist 里跑着的助手/也不启动 Flask dev：
- dist\\如意助手.exe 是打包版，不会读 src/ 里改过的脚本
- 系统 Python 没装 flask，起 Flask dev 还要处理依赖/编码一堆事
- 这个流程本质只需要「Playwright + 已登录的 Cookie + 注入同一份 JS」，不需要 Flask

用法（仓库根目录）：
  python scripts/run_delivered_sync_standalone.py
  python scripts/run_delivered_sync_standalone.py --date-shortcut 昨天 --ship-date 2026-07-15
  python scripts/run_delivered_sync_standalone.py --printed-only   # 只要已打印（默认是全部）

首次运行会打开一个可见 Chromium 窗口；若未登录会停在登录页，
用拼多多 APP 扫码即可（本脚本会自动等待并继续，无需按任何按键）。
登录态会持久化到独立的浏览器数据目录（与 dist EXE 和 dev.py 都不共享，不会互相冲突/顶号）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from playwright.sync_api import sync_playwright  # noqa: E402

SCRIPT_PATH = SRC / 'spider' / 'pinduoduo' / 'scripts' / 'pdd-erp-order-delivered-query.js'
DELIVERED_URL = 'https://mms.pinduoduo.com/erp/order/delivered'

EVAL_WRAPPER = """
async (args) => {
  delete window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS;
  delete window.__PDD_ERP_DELIVERED_TIME_TYPE;
  delete window.__PDD_ERP_DELIVERED_DATE_SHORTCUT;
  delete window.__PDD_ERP_DELIVERED_AUTO_SCROLL;
  delete window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS;
  delete window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS;
  if (args.filterPrintStatus !== undefined && args.filterPrintStatus !== null) {
    window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS = args.filterPrintStatus;
  }
  if (args.timeType != null && args.timeType !== '') {
    window.__PDD_ERP_DELIVERED_TIME_TYPE = args.timeType;
  }
  if (args.dateShortcut != null && args.dateShortcut !== '') {
    window.__PDD_ERP_DELIVERED_DATE_SHORTCUT = args.dateShortcut;
  }
  if (args.autoScroll !== undefined) {
    window.__PDD_ERP_DELIVERED_AUTO_SCROLL = args.autoScroll;
  }
  if (args.scrollMaxSteps != null && args.scrollMaxSteps !== '') {
    window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS = Number(args.scrollMaxSteps);
  }
  if (args.scrollPauseMs != null && args.scrollPauseMs !== '') {
    window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS = Number(args.scrollPauseMs);
  }
  const source = args.source;
  const run = new Function('return ' + source);
  return await run();
}
"""


def _load_script_source(path: Path) -> str:
    raw = path.read_text(encoding='utf-8').lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def _get_user_data_dir() -> Path:
    """独立于 dist EXE（browser_data）与 dev.py（browser_data_dev）的第三份 profile，避免冲突。"""
    import os

    base = Path(os.getenv('LOCALAPPDATA') or Path.home())
    d = base / '如意助手' / 'browser_data_standalone'
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_chrome_executable() -> str | None:
    try:
        from utils.browser_path import find_chrome_executable, CHROME_EXECUTABLE_PATH  # type: ignore

        find_chrome_executable()
        from utils import browser_path  # type: ignore

        return browser_path.CHROME_EXECUTABLE_PATH
    except Exception as e:
        print(f'[warn] 未能定位内置 Chromium，回退 Playwright 默认: {e}')
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description='独立跑一遍 ERP 已发货同步（改日期即可）')
    parser.add_argument('--date-shortcut', default='昨天', help='今天/昨天/近7天…（默认昨天）')
    parser.add_argument('--ship-date', default='', help='仅用于输出文件名，如 2026-07-15')
    parser.add_argument('--time-type', default='发货时间')
    parser.add_argument(
        '--printed-only',
        action='store_true',
        help='只抓「已打印快递单」（默认抓全部，避免漏未打印的单）',
    )
    parser.add_argument('--headless', action='store_true', help='无头模式（默认可见，方便扫码）')
    parser.add_argument('--login-wait-seconds', type=int, default=300, help='等待扫码登录的最长秒数')
    args = parser.parse_args()

    ship_date = args.ship_date.strip()
    if not ship_date:
        if args.date_shortcut.strip() == '昨天':
            ship_date = (date.today() - timedelta(days=1)).isoformat()
        elif args.date_shortcut.strip() == '今天':
            ship_date = date.today().isoformat()
        else:
            ship_date = args.date_shortcut.strip()

    script_source = _load_script_source(SCRIPT_PATH)
    user_data_dir = _get_user_data_dir()
    chrome_path = _find_chrome_executable()

    print(f'[1/4] 浏览器数据目录: {user_data_dir}')
    print(f'[1/4] Chromium: {chrome_path or "(Playwright 默认)"}')

    launch_kwargs = dict(
        user_data_dir=str(user_data_dir),
        headless=args.headless,
        no_viewport=True,
        locale='zh-CN',
        timezone_id='Asia/Shanghai',
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-web-security',
            '--disable-site-isolation-trials',
            '--start-maximized',
        ],
    )
    if chrome_path:
        launch_kwargs['executable_path'] = chrome_path

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
        try:
            page = context.pages[0] if context.pages else context.new_page()

            print(f'[2/4] 打开已发货页: {DELIVERED_URL}')
            page.goto(DELIVERED_URL, wait_until='domcontentloaded', timeout=90_000)

            if 'login' in (page.url or '').lower():
                print('[2/4] 需要登录 —— 请在弹出的浏览器窗口里用拼多多 APP 扫码。')
                print(f'      最多等待 {args.login_wait_seconds}s，扫码后脚本会自动继续…')
                waited = 0
                interval = 3
                while waited < args.login_wait_seconds:
                    page.wait_for_timeout(interval * 1000)
                    waited += interval
                    if 'login' not in (page.url or '').lower():
                        print(f'[2/4] 已检测到登录成功（等待 {waited}s）')
                        break
                else:
                    print('[2/4] 超时仍未登录，退出。请重跑脚本并尽快扫码。', file=sys.stderr)
                    return 2
                # 登录后重新进入目标页
                page.goto(DELIVERED_URL, wait_until='domcontentloaded', timeout=90_000)

            print('[3/4] 等待筛选表单…')
            try:
                page.wait_for_selector('#timeType', timeout=15_000)
            except Exception:
                print('[3/4] 筛选表单未按时出现，仍继续尝试（脚本内部还有一轮等待）')

            filter_print_status = '已打印快递单' if args.printed_only else '__ALL__'
            print(
                f'[3/4] 注入抓取脚本：date_shortcut={args.date_shortcut} '
                f'time_type={args.time_type} filter_print_status={filter_print_status}'
            )
            raw = page.evaluate(
                EVAL_WRAPPER,
                {
                    'source': script_source,
                    'dateShortcut': args.date_shortcut,
                    'timeType': args.time_type,
                    'filterPrintStatus': filter_print_status,
                    'autoScroll': True,
                    'scrollPauseMs': 500,
                },
            )
        finally:
            context.close()

    if not isinstance(raw, dict):
        print(f'ERROR: 脚本返回异常类型 {type(raw).__name__}', file=sys.stderr)
        return 1

    ok = bool(raw.get('ok'))
    rows = raw.get('rows') or []
    count = len(rows)
    page_total = raw.get('pageTotal')
    incomplete = raw.get('incomplete')

    out_path = ROOT / 'data' / f'erp_delivered_{ship_date}.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')

    nos_path = out_path.with_name(out_path.stem + '_order_nos.txt')
    order_nos = [str(r.get('orderNo') or '') for r in rows if isinstance(r, dict) and r.get('orderNo')]
    nos_path.write_text('\n'.join(order_nos) + ('\n' if order_nos else ''), encoding='utf-8')

    print('[4/4] 完成')
    print('----------')
    print(f'ok={ok}  count={count}  pageTotal={page_total}  incomplete={incomplete}')
    print(f'saved={out_path}')
    print(f'orderNos={nos_path} ({len(order_nos)} 个)')
    if not ok:
        print(f'error={raw.get("error")}', file=sys.stderr)
        return 1
    if page_total is not None and count < int(page_total):
        print(f'警告：已抓 {count} < 页脚 {page_total}，仍可能漏单', file=sys.stderr)
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
