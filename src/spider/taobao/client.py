"""淘宝商品自动上架客户端（供 API / CLI 调用）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from playwright.sync_api import Page

from spider.taobao.data.loader import (
    ProductRecord,
    load_pending_products,
    load_product_by_keyword,
    load_product_by_title,
)
from spider.taobao.flows.publish_one import publish_one
from spider.taobao.login_intercept import ensure_logged_in
from utils.logger import get_logger

logger = get_logger('TaobaoPublishClient')


class TaobaoPublishClient:
    """淘宝以图发品自动上架。"""

    def __init__(self, page: Optional[Page] = None):
        self.page = page

    def set_page(self, page: Page) -> None:
        self.page = page

    def list_pending(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in load_pending_products()]

    def check_login(self, *, pause_on_captcha: bool = False) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'message': 'Page 未设置'}
        result = ensure_logged_in(self.page, pause_on_captcha=pause_on_captcha)
        from spider.taobao.page_guard import is_category_upload_ready
        result['logged_in'] = is_category_upload_ready(self.page)
        result['upload_ready'] = result['logged_in']
        return result

    def publish_by_keyword(
        self,
        keyword: str,
        *,
        stop_after: Optional[str] = None,
        pause_on_captcha: bool = True,
        wait_login_timeout_sec: int = 0,
        skip_if_upload_ready: bool = False,
        shop_name: str = '',
    ) -> Dict[str, Any]:
        product = load_product_by_keyword(keyword)
        if not product:
            return {'ok': False, 'error': f'未找到包含「{keyword}」的商品'}
        return self.publish_product(
            product,
            stop_after=stop_after,
            pause_on_captcha=pause_on_captcha,
            wait_login_timeout_sec=wait_login_timeout_sec,
            skip_if_upload_ready=skip_if_upload_ready,
            shop_name=shop_name,
        )

    def publish_by_title(
        self,
        title: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        product = load_product_by_title(title)
        if not product:
            return {'ok': False, 'error': f'未找到标题为「{title}」的商品'}
        return self.publish_product(product, **kwargs)

    def publish_next_pending(self, **kwargs: Any) -> Dict[str, Any]:
        pending = load_pending_products()
        if not pending:
            return {'ok': False, 'error': '没有待上架商品（需有图且上架链接为空）'}
        return self.publish_product(pending[0], **kwargs)

    def publish_product(
        self,
        product: ProductRecord,
        *,
        stop_after: Optional[str] = None,
        pause_on_captcha: bool = True,
        wait_login_timeout_sec: int = 0,
        skip_if_upload_ready: bool = False,
        do_backfill: bool = True,
        shop_name: str = '',
    ) -> Dict[str, Any]:
        if not self.page:
            return {'ok': False, 'error': 'Page 未设置'}
        logger.info('开始上架: %s (%s 张图)', product.title, len(product.images))
        return publish_one(
            self.page,
            product,
            stop_after=stop_after,
            pause_on_captcha=pause_on_captcha,
            wait_login_timeout_sec=wait_login_timeout_sec,
            skip_if_upload_ready=skip_if_upload_ready,
            do_backfill=do_backfill,
            shop_name=shop_name,
        )
