"""单商品发布状态机。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.goofish.config import NAV_TIMEOUT_MS, PUBLISH_URL
from spider.goofish.data.backfill import backfill_upload_result, build_item_url
from spider.goofish.data.loader import ProductRecord
from spider.goofish.login_gate import ensure_logged_in
from spider.goofish.page_guard import (
    ensure_browser_window_default,
    find_business_frame,
    is_publish_ready,
    list_frames,
    log_browser_state,
)
from spider.goofish.pages import publish_page as pub
from spider.goofish.step_logger import StepLogger
from utils.logger import get_logger

logger = get_logger('GoofishPublishOne')

# stop_after 调试断点
VALID_STOP_AFTER = {None, 'upload', 'fill', 'submit'}


def publish_one(
    page: Page,
    product: ProductRecord,
    *,
    stop_after: Optional[str] = None,
    wait_login_timeout_sec: int = 0,
    skip_if_logged_in: bool = False,
    do_backfill: bool = True,
) -> Dict[str, Any]:
    """完整发布一个商品。

    Args:
        stop_after: upload | fill | submit | None（调试用，在该步后停止）
        do_backfill: 成功后写回 Excel

    Returns:
        成功 { ok: True, item_id, item_url, backfill, log_dir }
        失败 { ok: False, step, message/error, need_login? }
    """
    if stop_after not in VALID_STOP_AFTER:
        return {'ok': False, 'error': f'stop_after 非法: {stop_after}'}

    steps = StepLogger(product.slug)
    steps.log('start', product=product.to_dict(), stop_after=stop_after)

    try:
        missing = product.missing_required()
        if missing:
            msg = f"缺少必填项: {'、'.join(missing)}"
            steps.log('validate_failed', missing=missing)
            return {
                'ok': False,
                'step': 'validate',
                'message': msg,
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        if product.upload_link:
            steps.log('skipped', upload_link=product.upload_link)
            return {
                'ok': False,
                'skipped': True,
                'message': '商品已有上架链接，跳过',
                'upload_link': product.upload_link,
                'product': product.to_dict(),
            }

        login = ensure_logged_in(
            page,
            target_url=PUBLISH_URL,
            wait_login_timeout_sec=wait_login_timeout_sec,
            skip_if_logged_in=skip_if_logged_in,
        )
        steps.log('login', **{k: v for k, v in login.items() if k != 'merchant'})
        if not login.get('ok'):
            steps.screenshot(page, 'fail_login')
            return {
                'ok': False,
                'step': 'login',
                'need_login': login.get('need_login', True),
                'message': login.get('message'),
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        ensure_browser_window_default(page)

        # 登录门禁可能停在别的页面，发布前强制回发布页
        if PUBLISH_URL not in (page.url or ''):
            page.goto(PUBLISH_URL, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(3000)
        log_browser_state(page, '发布-准备填表')

        if not is_publish_ready(page):
            steps.screenshot(page, 'fail_publish_not_ready')
            steps.log('publish_not_ready', frames=list_frames(page))
            return {
                'ok': False,
                'step': 'publish_ready',
                'message': (
                    '发布页未就绪（未在业务 iframe 内找到表单）。'
                    '请确认 Chromium 窗口已停在闲鱼发布页；若页面正常但仍报此错，'
                    '说明表单选择器已变，需重新探测并更新 config.SEL_PUBLISH_FORM_ANCHORS'
                ),
                'frames': list_frames(page),
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        frame = find_business_frame(page)
        if frame is None:
            steps.screenshot(page, 'fail_frame')
            return {
                'ok': False,
                'step': 'frame',
                'message': '未能定位发布页业务 iframe',
                'frames': list_frames(page),
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }
        steps.log('frame', url=(frame.url or '')[:300], frames=list_frames(page))

        pub.dismiss_guides(frame)

        upload_result = pub.upload_images(frame, product.images)
        steps.log('upload_images', **upload_result)

        if stop_after == 'upload':
            steps.screenshot(page, 'stop_upload')
            return {
                'ok': True,
                'step': 'upload',
                'images': upload_result,
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        text_result = pub.fill_title_and_description(frame, product)
        price_result = pub.fill_price(frame, product)
        attr_result = pub.fill_attributes(frame, product)
        steps.log('fill_form', text=text_result, price=price_result, attrs=attr_result)

        if stop_after == 'fill':
            steps.screenshot(page, 'stop_fill')
            return {
                'ok': True,
                'step': 'fill',
                'form': {'text': text_result, 'price': price_result, 'attrs': attr_result},
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        submit_result = pub.submit(frame)
        steps.log('submit', **submit_result)

        if stop_after == 'submit':
            steps.screenshot(page, 'stop_submit')
            return {
                'ok': True,
                'step': 'submit',
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        item_id = pub.extract_item_id(frame)
        item_url = build_item_url(item_id) if item_id else ''
        steps.log('item_id', item_id=item_id, item_url=item_url, url=page.url)

        if not item_id:
            # 发布可能已成功但未能解析 ID，交由人工确认，避免误判为失败后重复发布
            steps.screenshot(page, 'warn_no_item_id')
            return {
                'ok': False,
                'step': 'extract_item_id',
                'message': (
                    '已点击发布，但未能从页面解析出商品 ID。'
                    '请在 Chromium 窗口确认是否发布成功；若已成功，可用「手动回填」写入链接，避免重复发布。'
                ),
                'needs_manual_check': True,
                'product': product.to_dict(),
                'log_dir': str(steps.dir),
            }

        backfill_result = None
        if do_backfill:
            backfill_result = backfill_upload_result(
                title=product.title,
                item_id=item_id,
                item_url=item_url,
                product_dir=product.product_dir,
            )
            steps.log('backfill', **(backfill_result or {}))

        return {
            'ok': True,
            'item_id': item_id,
            'item_url': item_url,
            'backfill': backfill_result,
            'product': product.to_dict(),
            'log_dir': str(steps.dir),
        }

    except pub.PublishPageError as exc:
        logger.error('发布页定位失败 %s: %s', product.title, exc)
        steps.screenshot(page, 'fail_selector')
        steps.log('error', error=str(exc), kind='selector')
        return {
            'ok': False,
            'step': 'selector',
            'error': str(exc),
            'product': product.to_dict(),
            'log_dir': str(steps.dir),
        }
    except Exception as exc:
        logger.error('发布失败 %s: %s', product.title, exc, exc_info=True)
        steps.screenshot(page, 'fail_publish')
        steps.log('error', error=str(exc))
        return {
            'ok': False,
            'error': str(exc),
            'product': product.to_dict(),
            'log_dir': str(steps.dir),
        }
