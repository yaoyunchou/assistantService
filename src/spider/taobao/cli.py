"""淘宝商品上架 CLI。

用法（在 src 目录下）::

    python -m spider.taobao.cli --list-pending
    python -m spider.taobao.cli --keyword 宋朝 --stop-after audit
    python -m spider.taobao.cli --next-pending
"""
from __future__ import annotations

import argparse
import json
import sys

from config import Config
from spider.query_manager import BrowserPool
from spider.taobao.client import TaobaoPublishClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='淘宝商品 Playwright 自动上架')
    parser.add_argument('--list-pending', action='store_true', help='列出待上架商品')
    parser.add_argument('--keyword', type=str, help='按标题关键词匹配单品')
    parser.add_argument('--title', type=str, help='按完整标题匹配单品')
    parser.add_argument('--next-pending', action='store_true', help='上架队列中第一个待上架商品')
    parser.add_argument('--check-login', action='store_true', help='仅检查/引导登录')
    parser.add_argument(
        '--stop-after',
        choices=['audit', 'category_confirm', 'submit'],
        help='在某步后停止（不提交）',
    )
    parser.add_argument('--no-backfill', action='store_true', help='成功后不回填 Excel')
    parser.add_argument('--shop-name', type=str, default='', help='回填店铺名称')
    parser.add_argument('--headless', action='store_true', help='无头模式（默认跟随 Config.HEADLESS）')
    args = parser.parse_args(argv)

    client = TaobaoPublishClient()

    if args.list_pending:
        print(json.dumps(client.list_pending(), ensure_ascii=False, indent=2))
        return 0

    need_browser = args.check_login or args.keyword or args.title or args.next_pending
    if not need_browser:
        parser.print_help()
        return 1

    headless = args.headless or Config.HEADLESS
    pool = BrowserPool(headless=headless)
    try:
        if args.check_login:
            result = pool.execute(
                lambda page: client.set_page(page) or client.check_login(pause_on_captcha=True),
                timeout=300,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get('ok') else 2

        def _run(page):
            client.set_page(page)
            if args.keyword:
                return client.publish_by_keyword(
                    args.keyword,
                    stop_after=args.stop_after,
                    shop_name=args.shop_name,
                )
            if args.title:
                return client.publish_by_title(
                    args.title,
                    stop_after=args.stop_after,
                    shop_name=args.shop_name,
                )
            return client.publish_next_pending(
                stop_after=args.stop_after,
                shop_name=args.shop_name,
                do_backfill=not args.no_backfill,
            )

        result = pool.execute(_run, timeout=600)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get('ok') else 1
    finally:
        pool.close()


if __name__ == '__main__':
    sys.exit(main())
