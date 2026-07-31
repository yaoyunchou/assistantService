"""在线商品管理编排：上架 / 下架 / 删除 / 编辑。

删除不可逆，必须由调用方显式传 confirm=True；未确认时脚本只做定位演练。
所有操作都写 step 日志，便于追溯误操作。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.sync_api import Page

from spider.goofish.config import (
    DEFAULT_TIMEOUT_MS,
    ITEM_LIST_URL,
    NAV_TIMEOUT_MS,
)
from spider.goofish.login_gate import ensure_logged_in
from spider.goofish.page_guard import find_business_frame, list_frames
from spider.goofish.step_logger import StepLogger
from utils.logger import get_logger

logger = get_logger('GoofishManageItems')

_ACTION_SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'goofish-item-action.js'

VALID_ACTIONS = ('online', 'offline', 'delete')
# 不可逆操作，必须显式确认
DESTRUCTIVE_ACTIONS = ('delete',)

_EVAL_ACTION = """
async (args) => {
  window.__GOOFISH_ACTION = args.action;
  window.__GOOFISH_ACTION_ITEM_ID = args.itemId;
  window.__GOOFISH_ACTION_CONFIRM = args.confirm === true;
  const run = new Function('return ' + args.source);
  return await run();
}
"""


def _load_script() -> str:
    raw = _ACTION_SCRIPT.read_text(encoding='utf-8')
    raw = raw.lstrip('\ufeff')
    raw = re.sub(r'^/\*[\s\S]*?\*/\s*', '', raw, count=1)
    return raw.strip()


def run_action(
    page: Page,
    item_id: str,
    action: str,
    *,
    confirm: bool = False,
    wait_login_timeout_sec: int = 0,
) -> Dict[str, Any]:
    """对单个商品执行上架/下架/删除。

    Returns:
        { ok, itemId, action, dryRun?, message/error, log_dir }
    """
    item_id = str(item_id or '').strip()
    action = str(action or '').strip().lower()

    if not item_id:
        return {'ok': False, 'error': '缺少 itemId'}
    if action not in VALID_ACTIONS:
        return {'ok': False, 'error': f"action 非法: {action}（可选 {'/'.join(VALID_ACTIONS)}）"}
    if action in DESTRUCTIVE_ACTIONS and not confirm:
        return {
            'ok': False,
            'error': '删除是不可逆操作，需显式传 confirm=true',
            'needs_confirm': True,
            'itemId': item_id,
            'action': action,
        }

    steps = StepLogger(f'manage-{action}-{item_id}')
    steps.log('start', itemId=item_id, action=action, confirm=confirm)

    gate = ensure_logged_in(page, target_url=ITEM_LIST_URL, wait_login_timeout_sec=wait_login_timeout_sec)
    steps.log('login', ok=gate.get('ok'), need_login=gate.get('need_login'))
    if not gate.get('ok'):
        return {
            'ok': False,
            'need_login': gate.get('need_login', True),
            'message': gate.get('message'),
            'itemId': item_id,
            'action': action,
            'log_dir': str(steps.dir),
        }

    # 商品列表页与登录门禁落点可能不同，强制回列表页
    try:
        if ITEM_LIST_URL not in (page.url or ''):
            page.goto(ITEM_LIST_URL, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(4000)
    except Exception as exc:
        steps.log('nav_error', error=str(exc))

    try:
        source = _load_script()
    except Exception as exc:
        return {
            'ok': False,
            'error': f'操作脚本读取失败: {exc}',
            'itemId': item_id,
            'action': action,
            'log_dir': str(steps.dir),
        }

    frame = find_business_frame(page) or page.main_frame
    try:
        raw = frame.evaluate(_EVAL_ACTION, {
            'source': source,
            'action': action,
            'itemId': item_id,
            'confirm': bool(confirm),
        })
    except Exception as exc:
        steps.screenshot(page, f'fail_{action}')
        steps.log('error', error=str(exc))
        return {
            'ok': False,
            'error': f'操作脚本执行失败: {exc}',
            'itemId': item_id,
            'action': action,
            'frames': list_frames(page),
            'log_dir': str(steps.dir),
        }

    raw = raw or {}
    steps.log('action_result', **raw)
    if not raw.get('success'):
        steps.screenshot(page, f'fail_{action}')
        return {
            'ok': False,
            'error': raw.get('error') or '操作失败',
            'itemId': item_id,
            'action': action,
            'log': raw.get('log'),
            'log_dir': str(steps.dir),
        }

    return {
        'ok': True,
        'itemId': item_id,
        'action': action,
        'dryRun': bool(raw.get('dryRun')),
        'button': raw.get('button'),
        'confirmed': raw.get('confirmed'),
        'message': raw.get('message') or f'{action} 执行完成',
        'log': raw.get('log'),
        'log_dir': str(steps.dir),
    }


def _open_item_edit(page: Page, item_id: str) -> Optional[Any]:
    """进入商品编辑态：点列表里该商品的「编辑」入口。"""
    frame = find_business_frame(page) or page.main_frame
    try:
        anchors = frame.locator(f'a[href*="{item_id}"]')
        if anchors.count() == 0:
            return None
    except Exception:
        return None

    for text in ('编辑', '修改'):
        try:
            btn = frame.get_by_text(text, exact=True)
            if btn.count() > 0:
                btn.first.click(timeout=DEFAULT_TIMEOUT_MS)
                page.wait_for_timeout(3000)
                return find_business_frame(page) or page.main_frame
        except Exception:
            continue
    return None


def edit_item(
    page: Page,
    item_id: str,
    changes: Dict[str, Any],
    *,
    wait_login_timeout_sec: int = 0,
) -> Dict[str, Any]:
    """编辑已有商品（首期支持改价与改描述）。

    Args:
        changes: { price?: str|float, description?: str }
    """
    item_id = str(item_id or '').strip()
    if not item_id:
        return {'ok': False, 'error': '缺少 itemId'}

    price = changes.get('price')
    description = changes.get('description')
    if price in (None, '') and not description:
        return {'ok': False, 'error': '未提供要修改的字段（支持 price / description）'}

    steps = StepLogger(f'manage-edit-{item_id}')
    steps.log('start', itemId=item_id, changes=changes)

    gate = ensure_logged_in(page, target_url=ITEM_LIST_URL, wait_login_timeout_sec=wait_login_timeout_sec)
    steps.log('login', ok=gate.get('ok'))
    if not gate.get('ok'):
        return {
            'ok': False,
            'need_login': gate.get('need_login', True),
            'message': gate.get('message'),
            'itemId': item_id,
            'log_dir': str(steps.dir),
        }

    try:
        if ITEM_LIST_URL not in (page.url or ''):
            page.goto(ITEM_LIST_URL, wait_until='domcontentloaded', timeout=NAV_TIMEOUT_MS)
        page.wait_for_timeout(4000)
    except Exception as exc:
        steps.log('nav_error', error=str(exc))

    frame = _open_item_edit(page, item_id)
    if frame is None:
        steps.screenshot(page, 'fail_open_edit')
        return {
            'ok': False,
            'error': (
                f'未能进入商品 {item_id} 的编辑页。'
                '编辑入口选择器需在登录态探测确认，见 docs/goofish/闲鱼后台-探测记录.md'
            ),
            'itemId': item_id,
            'log_dir': str(steps.dir),
        }
    steps.log('edit_opened', frame=(frame.url or '')[:200])

    from spider.goofish.pages import publish_page as pub

    changed = []
    errors = []

    if price not in (None, ''):
        try:
            filled = pub._fill_first_match(
                frame,
                [
                    frame.get_by_placeholder(re.compile('价|要卖|想卖')),
                    frame.locator('input[type="number"]'),
                ],
                str(price),
                what='价格',
            )
            if filled:
                changed.append('price')
            else:
                errors.append('未定位到价格输入框')
        except Exception as exc:
            errors.append(f'改价失败: {exc}')

    if description:
        try:
            filled = pub._fill_first_match(
                frame,
                [
                    frame.get_by_placeholder(re.compile('描述|介绍|说说|详情')),
                    frame.locator('textarea'),
                ],
                description,
                what='描述',
            )
            if filled:
                changed.append('description')
            else:
                errors.append('未定位到描述输入框')
        except Exception as exc:
            errors.append(f'改描述失败: {exc}')

    if not changed:
        steps.screenshot(page, 'fail_edit_fields')
        steps.log('edit_failed', errors=errors)
        return {
            'ok': False,
            'error': '没有字段被成功修改: ' + '；'.join(errors),
            'itemId': item_id,
            'log_dir': str(steps.dir),
        }

    save_result = {}
    try:
        save_result = pub.submit(frame)
    except pub.PublishPageError as exc:
        steps.screenshot(page, 'fail_edit_save')
        return {
            'ok': False,
            'error': f'已修改字段但未能保存: {exc}',
            'itemId': item_id,
            'changedFields': changed,
            'log_dir': str(steps.dir),
        }

    steps.log('edit_saved', changed=changed, save=save_result, errors=errors)
    return {
        'ok': True,
        'itemId': item_id,
        'changedFields': changed,
        'warnings': errors,
        'message': f"已修改并保存: {'、'.join(changed)}",
        'log_dir': str(steps.dir),
    }
