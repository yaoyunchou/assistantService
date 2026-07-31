#!/usr/bin/env python3
"""
把已抓到的 ERP 已发货数据（如 data/erp_delivered_2026-07-15.json）直接推送到 Nest 数据库，
调用的是 Swagger 文档里 **可直接写库、不用再走助手/浏览器** 的接口：

  POST {NEST_API_BASE}/assistant/pinduoduo/erp-delivered/today-printed-records
  （文档：https://nestapi.xfysj.top/xcx/api#/如意助手 / 拼多多ERP/ErpDeliveredTodayPrintedRecordController_create）
  按 orderNo upsert：已存在则更新，不存在则新建。

不走「.../erp-delivered/today-printed-query」那条（那个需要 Nest 经 Socket 转发给在线助手，
再由助手打开浏览器抓取——也就是之前一直卡住 Page.goto 的那条链路）。
现在数据已经用 scripts/run_delivered_sync_standalone.py 抓好了，直接写库最快最稳。

用法：
  # 1) 用设备密钥登录换 token（推荐，一次配置，无需每次输密码）
  python scripts/push_erp_delivered_to_nest.py --file data/erp_delivered_2026-07-15.json --device-key "keyId.secret"

  # 2) 用用户名密码登录换 token
  python scripts/push_erp_delivered_to_nest.py --file data/erp_delivered_2026-07-15.json --username xxx --password xxx

  # 3) 已经有现成的 JWT，直接用
  python scripts/push_erp_delivered_to_nest.py --file data/erp_delivered_2026-07-15.json --jwt "eyJxxx..."

环境变量（可选，等价于命令行参数）：
  NEST_API_BASE   默认 https://nestapi.xfysj.top/api/v1
  NEST_DEVICE_KEY / NEST_USERNAME+NEST_PASSWORD / NEST_JWT
  ASSISTANT_KEY   写入每条记录的 assistantKey（可选，Nest 侧字段允许省略）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))


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


def _http_json(url: str, *, method: str = 'GET', body: dict | None = None, headers: dict | None = None, timeout: int = 30) -> tuple[int, dict]:
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {'raw': raw}
        return e.code, parsed


def _extract_token(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ('access_token', 'accessToken', 'token'):
        if payload.get(key):
            return str(payload[key])
    data = payload.get('data')
    if isinstance(data, dict):
        return _extract_token(data)
    return None


def _login(nest_base: str, args) -> str:
    if args.jwt:
        return args.jwt
    if args.device_key:
        status, resp = _http_json(
            f'{nest_base}/auth/login-with-device-key',
            method='POST',
            body={'device_key': args.device_key},
        )
        token = _extract_token(resp)
        if status != 200 or not token:
            raise RuntimeError(f'设备密钥登录失败 HTTP {status}: {resp}')
        print('[auth] 设备密钥登录成功')
        return token
    if args.username and args.password:
        status, resp = _http_json(
            f'{nest_base}/auth/login',
            method='POST',
            body={'username': args.username, 'password': args.password},
        )
        token = _extract_token(resp)
        if status != 200 or not token:
            raise RuntimeError(f'用户名密码登录失败 HTTP {status}: {resp}')
        print('[auth] 用户名密码登录成功')
        return token
    raise RuntimeError('缺少鉴权方式：请提供 --jwt 或 --device-key 或 --username/--password')


def _load_rows(file_path: Path) -> list[dict]:
    payload = json.loads(file_path.read_text(encoding='utf-8'))
    # 兼容两种落盘格式：
    #  1) run_delivered_sync_standalone.py 直接落盘的助手原始返回 {ok, rows, ...}
    #  2) backfill_erp_delivered.py 落盘的包装 {result: {rows, ...}, ...}
    if isinstance(payload.get('rows'), list):
        return payload['rows']
    result = payload.get('result')
    if isinstance(result, dict) and isinstance(result.get('rows'), list):
        return result['rows']
    raise ValueError(f'无法从 {file_path} 中找到 rows 数组')


def _row_to_dto(row: dict, *, assistant_key: str | None) -> dict:
    goods = row.get('goods') or []
    dto_goods = [
        {
            'imgSrc': g.get('imgSrc') or '',
            'qty': int(g.get('qty') or 0),
            'spec': g.get('spec') or '',
            'title': g.get('title') or '',
        }
        for g in goods
        if isinstance(g, dict)
    ]
    dto = {
        'orderNo': str(row.get('orderNo') or ''),
        'actualAmount': str(row.get('actualAmount') or ''),
        'erpOrderNo': str(row.get('erpOrderNo') or ''),
        'express': str(row.get('express') or ''),
        'goods': dto_goods,
        'imgUrl': str(row.get('imgUrl') or ''),
        'orderStatus': str(row.get('orderStatus') or ''),
        'printStatus': str(row.get('printStatus') or ''),
        'shippingTime': str(row.get('shippingTime') or ''),
        'shopName': str(row.get('shopName') or ''),
    }
    if assistant_key:
        dto['assistantKey'] = assistant_key
    return dto


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description='把已抓好的已发货数据直接推送进 Nest 库（按 orderNo upsert）')
    parser.add_argument('--file', required=True, help='data/erp_delivered_*.json 路径')
    parser.add_argument(
        '--nest-base',
        default=os.getenv('NEST_API_BASE', 'https://nestapi.xfysj.top/xcx/api/v1').rstrip('/'),
    )
    parser.add_argument('--jwt', default=os.getenv('NEST_JWT') or '')
    parser.add_argument('--device-key', default=os.getenv('NEST_DEVICE_KEY') or '')
    parser.add_argument('--username', default=os.getenv('NEST_USERNAME') or '')
    parser.add_argument('--password', default=os.getenv('NEST_PASSWORD') or '')
    parser.add_argument('--assistant-key', default=os.getenv('ASSISTANT_KEY') or '')
    parser.add_argument('--dry-run', action='store_true', help='只打印将要发送的第一条 DTO，不真正请求')
    parser.add_argument('--sleep-ms', type=int, default=80, help='每条请求间隔，避免打太快')
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.is_file():
        print(f'ERROR: 文件不存在: {file_path}', file=sys.stderr)
        return 2

    rows = _load_rows(file_path)
    print(f'[1/3] 读取 {file_path} → {len(rows)} 条')
    if not rows:
        print('没有数据，退出')
        return 0

    dtos = [_row_to_dto(r, assistant_key=args.assistant_key) for r in rows if r.get('orderNo')]
    print(f'[1/3] 有效订单号 {len(dtos)} 条')

    if args.dry_run:
        print('[dry-run] 第一条 DTO：')
        print(json.dumps(dtos[0], ensure_ascii=False, indent=2))
        return 0

    print('[2/3] 登录换取 token…')
    try:
        token = _login(args.nest_base, args)
    except Exception as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    url = f'{args.nest_base}/assistant/pinduoduo/erp-delivered/today-printed-records'
    headers = {'Authorization': f'Bearer {token}'}

    ok_count = 0
    fail_rows: list[dict] = []
    print(f'[3/3] 推送到 {url} …')
    for i, dto in enumerate(dtos, 1):
        status, resp = _http_json(url, method='POST', body=dto, headers=headers, timeout=30)
        if status in (200, 201):
            ok_count += 1
        else:
            fail_rows.append({'orderNo': dto['orderNo'], 'status': status, 'resp': resp})
            print(f'  [{i}/{len(dtos)}] FAIL orderNo={dto["orderNo"]} HTTP {status}: {resp}', file=sys.stderr)
        if i % 10 == 0 or i == len(dtos):
            print(f'  进度 {i}/{len(dtos)}（成功 {ok_count}）')
        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000)

    print('----------')
    print(f'成功 {ok_count}/{len(dtos)}')
    if fail_rows:
        fail_path = file_path.with_name(file_path.stem + '_push_failed.json')
        fail_path.write_text(json.dumps(fail_rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'失败 {len(fail_rows)} 条，详情见 {fail_path}', file=sys.stderr)
        return 1
    print('OK：全部写入 Nest 库（按 orderNo upsert）')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
