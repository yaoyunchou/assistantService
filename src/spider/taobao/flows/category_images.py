"""类目页图片全流程：本地上传 → 主图审计 → 图库补救。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Page

from spider.taobao.page_guard import log_browser_state
from spider.taobao.pages import category_page as cat
from utils.logger import get_logger

logger = get_logger('TaobaoCategoryImages')


def upload_images_with_main_recovery(
    page: Page,
    images: List[Path],
    *,
    on_phase: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """
    金标准流程：
      1. 逐张本地上传（click 从本地上传 → 文件选择器 → 等处理）
         非 1:1 图 → 更多图片 + 进图库；1:1 图 → 直接进主图
      2. 全部上传后审计主图
      3. main < 1 → 打开图库弹框，勾最近 N 张 → 平台 1:1 → 入主图
      4. 完成后「确认，下一步」按钮激活
    """
    if not images:
        raise ValueError('商品无图片')

    expected = len(images)
    log_browser_state(page, '图片流程-开始', extra={'count': expected})
    _phase(on_phase, 'start', expected=expected)

    upload_audit = cat.upload_all_images(page, images)
    log_browser_state(page, '图片流程-上传完成', extra={'upload_audit': upload_audit})
    _phase(on_phase, 'upload_local', audit=upload_audit, image_count=expected)

    final_audit = cat.ensure_main_images(page, expected)
    log_browser_state(page, '图片流程-主图确认', extra={'final_audit': final_audit})
    _phase(on_phase, 'done', upload_audit=upload_audit, final_audit=final_audit)

    return {
        'ok': True,
        'expected_images': expected,
        'upload_audit': upload_audit,
        'final_audit': final_audit,
    }


def _phase(callback: Optional[Callable[..., None]], step: str, **payload: Any) -> None:
    if callback:
        try:
            callback(step, **payload)
        except Exception as ex:
            logger.debug('on_phase 回调异常 step=%s err=%s', step, ex)
