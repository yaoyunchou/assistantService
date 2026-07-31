#!/usr/bin/env python3
"""
补刷 ERP「已发货」数据（修复漏单 / 历史某天）。

默认按「昨天 + 全部打印状态」拉取，避免默认「已打印快递单」只入库一部分。
结果写入 data/erp_delivered_*.json。

用法（仓库根目录，助手服务需已启动且已登录拼多多）：

  python scripts/backfill_erp_delivered.py --date-shortcut 昨天

  # 经 Nest 网关（Nest 若会落库，用这个才能刷进业务库）
  python scripts/backfill_erp_delivered.py --via-nest --date-shortcut 昨天

环境变量（--via-nest）：
  NEST_API_BASE   例 https://nestapi.xfysj.top/api/v1
  ASSISTANT_KEY   例 erp-001
  NEST_JWT        可选
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / '.env'
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding='utf-8')
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _post_json(url: str, body: dict, *, headers: dict, timeout: int) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        method='POST',
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(err_body) if err_body else {}
        except json.JSONDecodeError:
            parsed = {'raw': err_body}
        raise RuntimeError(f'HTTP {e.code}: {parsed}') from e


def _unwrap_nest(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    if 'rows' in payload or 'success' in payload:
        return payload
    data = payload.get('data')
    if isinstance(data, dict):
        if 'rows' in data or 'success' in data:
            return data
        inner = data.get('data')
        if isinstance(inner, dict) and ('rows' in inner or 'success' in inner):
            return inner
    return payload


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description='补刷 ERP 已发货列表（可修历史漏单）')
    parser.add_argument(
        '--base-url',
        default=os.getenv('ASSISTANT_BASE_URL', 'http://127.0.0.1:8887').rstrip('/'),
        help='助手根地址（默认 8887）',
    )
    parser.add_argument(
        '--via-nest',
        action='store_true',
        help='经 Nest 转发（便于 Nest 落库）',
    )
    parser.add_argument(
        '--nest-base',
        default=(os.getenv('NEST_API_BASE') or '').rstrip('/'),
        help='Nest API 前缀，如 https://xxx/api/v1',
    )
    parser.add_argument(
        '--assistant-key',
        default=os.getenv('ASSISTANT_KEY') or os.getenv('WS_ASSISTANT_KEY') or 'erp-001',
    )
    parser.add_argument('--jwt', default=os.getenv('NEST_JWT') or '')
    parser.add_argument('--date-shortcut', default='昨天', help='今天/昨天/近7天…')
    parser.add_argument('--ship-date', default='', help='文件名标注，如 2026-07-15')
    parser.add_argument(
        '--printed-only',
        action='store_true',
        help='只抓已打印（补漏单不要开；默认抓全部）',
    )
    parser.add_argument('--time-type', default='发货时间')
    parser.add_argument('--timeout', type=int, default=650)
    parser.add_argument('--out', default='', help='输出 JSON 路径')
    args = parser.parse_args()

    ship_date = (args.ship_date or '').strip()
    if not ship_date:
        if args.date_shortcut.strip() == '昨天':
            ship_date = (date.today() - timedelta(days=1)).isoformat()
        elif args.date_shortcut.strip() == '今天':
            ship_date = date.today().isoformat()
        else:
            ship_date = args.date_shortcut.strip().replace('/', '-')

    body = {
        'date_shortcut': args.date_shortcut,
        'time_type': args.time_type,
        'auto_scroll': True,
        'scroll_pause_ms': 500,
        'filter_print_status': '已打印快递单' if args.printed_only else '__ALL__',
    }

    headers: dict = {}
    if args.via_nest:
        nest_base = args.nest_base
        if not nest_base:
            print('ERROR: --via-nest 需要 NEST_API_BASE 或 --nest-base', file=sys.stderr)
            return 2
        q = urllib.parse.urlencode({'assistantKey': args.assistant_key})
        url = f'{nest_base}/assistant/pinduoduo/erp-delivered/today-printed-query?{q}'
        if args.jwt:
            headers['Authorization'] = f'Bearer {args.jwt}'
        print(f'[via Nest] {url}')
    else:
        url = f'{args.base_url}/api/pinduoduo/erp-delivered/today-printed-query'
        print(f'[local] {url}')

    print(f'body={json.dumps(body, ensure_ascii=False)}')
    print('拉取中（可能要几分钟，请保持 ERP 已登录）…')

    try:
        payload = _post_json(url, body, headers=headers, timeout=args.timeout)
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        print(
            '提示：若 Page.goto 超时，请先在助手浏览器打开已发货页并登录，再重跑。',
            file=sys.stderr,
        )
        return 1

    result = _unwrap_nest(payload)
    rows = result.get('rows') if isinstance(result.get('rows'), list) else []
    count = len(rows)
    page_total = result.get('pageTotal')
    incomplete = result.get('incomplete')
    success = bool(result.get('success'))
    message = result.get('message') or ''

    out_path = Path(args.out) if args.out else (ROOT / 'data' / f'erp_delivered_{ship_date}.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                'shipDate': ship_date,
                'request': body,
                'viaNest': bool(args.via_nest),
                'result': result,
                'raw': payload if payload is not result else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )

    nos_path = out_path.with_name(out_path.stem + '_order_nos.txt')
    order_nos = [
        str(r.get('orderNo') or '')
        for r in rows
        if isinstance(r, dict) and r.get('orderNo')
    ]
    nos_path.write_text('\n'.join(order_nos) + ('\n' if order_nos else ''), encoding='utf-8')

    print('----------')
    print(f'success={success}  message={message}')
    print(f'count={count}  pageTotal={page_total}  incomplete={incomplete}')
    print(f'saved={out_path}')
    print(f'orderNos={nos_path} ({len(order_nos)} 个)')
    if page_total is not None and count < int(page_total):
        print(f'警告：已抓 {count} < 页脚 {page_total}，可能仍未抓全', file=sys.stderr)
        return 3
    if not success:
        return 1
    if count == 0:
        print('警告：0 条，请确认日期快捷与 ERP 筛选', file=sys.stderr)
        return 4
    print('OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
