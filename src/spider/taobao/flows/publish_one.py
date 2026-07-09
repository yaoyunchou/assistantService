"""单商品上架状态机。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.taobao.data.backfill import backfill_upload_result, sync_summary_upload_link
from spider.taobao.data.loader import ProductRecord
from spider.taobao.flows.category_images import upload_images_with_main_recovery
from spider.taobao.login_intercept import ensure_logged_in
from spider.taobao.page_guard import ensure_browser_window_default, log_browser_state
from spider.taobao.pages import category_page as cat_page
from spider.taobao.pages import publish_page as pub_page
from spider.taobao.step_logger import StepLogger
from utils.logger import get_logger

logger = get_logger('TaobaoPublishOne')

# stop_after: None | category_confirm | submit
VALID_STOP_AFTER = {None, 'category_confirm', 'audit', 'submit'}


def publish_one(
    page: Page,
    product: ProductRecord,
    *,
    stop_after: Optional[str] = None,
    pause_on_captcha: bool = True,
    wait_login_timeout_sec: int = 0,
    skip_if_upload_ready: bool = False,
    do_backfill: bool = True,
    shop_name: str = '',
) -> Dict[str, Any]:
    """
    单商品完整上架流程。

    Args:
        page: BrowserPool 提供的 page（使用其 context 开新 tab）
        stop_after: 在某步后停止（调试用）
        pause_on_captcha: 验证码时暂停等待人工
        do_backfill: 成功后写 Excel
        shop_name: 回填店铺名
    """
    steps = StepLogger(product.slug)
    context = page.context

    try:
        if not product.images:
            raise ValueError('商品无图片，无法上架')

        if product.upload_link:
            summary_synced = sync_summary_upload_link(product)
            logger.info(
                '跳过已有上架链接 title=%s link=%s time=%s shop=%s dir=%s summary_synced=%s',
                product.title,
                product.upload_link,
                product.upload_time or '(无)',
                product.shop_name or '(无)',
                product.product_dir,
                summary_synced,
            )
            msg = '商品已有上架链接，跳过'
            if summary_synced:
                msg += '（已同步汇总表上架链接）'
            elif not product.upload_time:
                msg += '（链接来自单品 Excel，汇总表为空）'
            return {
                'ok': False,
                'skipped': True,
                'message': msg,
                'upload_link': product.upload_link,
                'upload_time': product.upload_time,
                'summary_synced': summary_synced,
                'product': product.to_dict(),
            }

        login = ensure_logged_in(
            page,
            pause_on_captcha=pause_on_captcha,
            wait_login_timeout_sec=wait_login_timeout_sec,
            skip_if_upload_ready=skip_if_upload_ready,
        )
        steps.log('login', **login)
        if not login.get('ok'):
            steps.screenshot(page, 'fail_login')
            return {
                'ok': False,
                'step': 'login',
                'need_login': login.get('need_login', True),
                'message': login.get('message'),
                'product': product.to_dict(),
            }

        ensure_browser_window_default(page)
        log_browser_state(page, '上架-登录完成')

        # 不关闭用户手动打开的标签页（调试时新开 tab 不会被删）
        log_browser_state(page, '上架-准备上传图片')

        def _on_image_phase(step: str, **payload):
            steps.log(f'images_{step}', **payload)

        image_result = upload_images_with_main_recovery(
            page,
            product.images,
            on_phase=_on_image_phase,
        )
        steps.save_audit(image_result.get('final_audit') or {})
        steps.log(
            'images',
            ok=image_result.get('ok'),
            expected=image_result.get('expected_images'),
            upload_audit=image_result.get('upload_audit'),
            final_audit=image_result.get('final_audit'),
        )

        if stop_after == 'audit':
            steps.screenshot(page, 'stop_audit')
            return {
                'ok': True,
                'step': 'audit',
                'audit': image_result.get('final_audit'),
                'images': image_result,
                'product': product.to_dict(),
            }

        cat_page.fill_category_attrs(page, product)
        steps.log('category_attrs')

        if stop_after == 'category_confirm':
            steps.screenshot(page, 'stop_category_confirm')
            return {'ok': True, 'step': 'category_confirm', 'product': product.to_dict()}

        publish_pg = cat_page.goto_publish_page(page, context)
        steps.log('open_publish', url=publish_pg.url)

        ref_page = context.new_page() if product.product_url else None
        try:
            pub_page.fill_publish_form(publish_pg, product, ref_page=ref_page)
            steps.log('fill_publish')
        finally:
            if ref_page and not ref_page.is_closed():
                ref_page.close()

        if stop_after == 'submit':
            steps.screenshot(publish_pg, 'stop_before_submit')
            return {'ok': True, 'step': 'fill_publish', 'product': product.to_dict()}

        item_id = pub_page.submit_and_get_id(publish_pg)
        steps.log('submit', item_id=item_id, url=publish_pg.url)

        backfill_result = None
        if do_backfill:
            backfill_result = backfill_upload_result(
                title=product.title,
                item_id=item_id,
                product_dir=product.product_dir,
                shop_name=shop_name,
            )
            steps.log('backfill', **(backfill_result or {}))

        try:
            if not publish_pg.is_closed():
                publish_pg.close()
        except Exception:
            pass

        return {
            'ok': True,
            'item_id': item_id,
            'item_url': f'https://item.taobao.com/item.htm?id={item_id}',
            'backfill': backfill_result,
            'product': product.to_dict(),
            'log_dir': str(steps.dir),
        }

    except Exception as e:
        logger.error('上架失败 %s: %s', product.title, e, exc_info=True)
        try:
            active = context.pages[-1] if context.pages else page
            steps.screenshot(active, 'fail_publish')
        except Exception:
            steps.screenshot(page, 'fail_publish')
        steps.log('error', error=str(e))
        return {
            'ok': False,
            'error': str(e),
            'product': product.to_dict(),
            'log_dir': str(steps.dir),
        }
