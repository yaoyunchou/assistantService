"""闲鱼商品管理客户端（供 API 调用）。

只做数据加载与流程编排，DOM/接口细节在 pages / flows / item_list 内。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from spider.goofish.data.loader import (
    ProductRecord,
    load_pending_products,
    load_product_by_keyword,
    load_product_by_title,
)
from spider.goofish.flows.publish_one import publish_one
from spider.goofish.login_gate import ensure_logged_in
from utils.logger import get_logger

logger = get_logger('GoofishClient')


class GoofishClient:
    """闲鱼卖家后台自动化。"""

    def __init__(self, page: Optional[Page] = None):
        self.page = page

    def set_page(self, page: Page) -> None:
        self.page = page

    # ── 本地队列 ────────────────────────────────────────────
    def list_pending(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in load_pending_products()]

    # ── 登录 ────────────────────────────────────────────────
    def check_login(self, *, wait_login_timeout_sec: int = 0) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        result = ensure_logged_in(
            self.page,
            wait_login_timeout_sec=wait_login_timeout_sec,
            skip_if_logged_in=True,
        )
        merchant = result.get('merchant') or {}
        if isinstance(merchant, dict):
            result['shop_name'] = (
                merchant.get('shopName')
                or merchant.get('nick')
                or merchant.get('userNick')
                or ''
            )
        return result

    # ── 发布 ────────────────────────────────────────────────
    def publish_product(self, product: ProductRecord, **kwargs: Any) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        return publish_one(self.page, product, **kwargs)

    def publish_by_keyword(self, keyword: str, **kwargs: Any) -> Dict[str, Any]:
        product = load_product_by_keyword(keyword)
        if not product:
            return {'ok': False, 'error': f'未找到包含「{keyword}」的商品'}
        return self.publish_product(product, **kwargs)

    def publish_by_title(self, title: str, **kwargs: Any) -> Dict[str, Any]:
        product = load_product_by_title(title)
        if not product:
            return {'ok': False, 'error': f'未找到标题为「{title}」的商品'}
        return self.publish_product(product, **kwargs)

    def publish_next_pending(self, **kwargs: Any) -> Dict[str, Any]:
        pending = load_pending_products()
        if not pending:
            return {'ok': False, 'error': '没有待发布商品（需有图且上架链接为空）'}
        return self.publish_product(pending[0], **kwargs)

    # ── 在线商品管理 ────────────────────────────────────────
    def list_items(self, **kwargs: Any) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        from spider.goofish.item_list import fetch_items
        return fetch_items(self.page, **kwargs)

    def run_item_action(self, item_id: str, action: str, **kwargs: Any) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        from spider.goofish.flows.manage_items import run_action
        return run_action(self.page, item_id, action, **kwargs)

    def edit_item(self, item_id: str, changes: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        from spider.goofish.flows.manage_items import edit_item
        return edit_item(self.page, item_id, changes, **kwargs)
