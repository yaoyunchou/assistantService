"""发布页填表、规格、提交。"""
from __future__ import annotations

import re
import time
from typing import Optional

from playwright.sync_api import Page

from spider.taobao.data.loader import ProductRecord
from spider.taobao.pages.reference_page import fetch_filing_number
from utils.logger import get_logger

logger = get_logger('TaobaoPublishPage')


def fill_publish_form(page: Page, product: ProductRecord, *, ref_page: Optional[Page] = None) -> None:
    page.wait_for_load_state('domcontentloaded', timeout=60_000)
    page.wait_for_timeout(2000)

    _fill_title(page, product.title)

    filing = _param_value(product, '备案') or _param_value(product, '化妆品备案')
    if not filing and ref_page and product.product_url:
        filing = fetch_filing_number(ref_page, product.product_url)
    if filing:
        _fill_text_by_label(page, '化妆品备案编号', filing)
        _fill_text_by_label(page, '备案编号', filing)

    # 常见化妆品参数
    for label in ('功效', '产地', '规格类型', '净含量', '适合肤质', '品牌'):
        val = _param_value(product, label)
        if val:
            if not _fill_next_select_by_label(page, label, val, val):
                _fill_text_by_label(page, label, val)

    if product.spec_count >= 2 and product.skus:
        _fill_multi_sku(page, product)
    else:
        _fill_single_price(page, product)


def submit_and_get_id(page: Page) -> str:
    btn = page.get_by_role('button', name=re.compile('提交宝贝信息'))
    btn.scroll_into_view_if_needed()
    btn.click()
    page.wait_for_url(re.compile(r'success\.htm'), timeout=120_000)
    m = re.search(r'primaryId=(\d+)', page.url)
    if not m:
        raise RuntimeError(f'提交成功但未解析到 primaryId: {page.url}')
    item_id = m.group(1)
    logger.info('上架成功 item_id=%s', item_id)
    return item_id


def _fill_title(page: Page, title: str) -> None:
    for sel in (
        'input[placeholder*="标题"]',
        '[class*="title"] input',
        'textarea[placeholder*="标题"]',
    ):
        loc = page.locator(sel).first
        if loc.count() > 0:
            loc.fill(title[:60])
            loc.press('Tab')
            page.wait_for_timeout(300)
            return
    block = page.locator('[class*="sell-component-info-wrapper"]').filter(has_text='宝贝标题').first
    if block.count() > 0:
        inp = block.locator('input, textarea').first
        inp.fill(title[:60])
        inp.press('Tab')


def _fill_single_price(page: Page, product: ProductRecord) -> None:
    price = product.price
    if product.skus:
        price = product.skus[0].get('price') or price
    if not price:
        return
    for label in ('一口价', '价格', '售价'):
        if _fill_text_by_label(page, label, str(price)):
            return


def _fill_multi_sku(page: Page, product: ProductRecord) -> None:
    """多规格：创建规格 + 填 SKU 价/库存。"""
    create_btn = page.get_by_text(re.compile(r'\+?\s*创建规格'))
    if create_btn.count() > 0:
        create_btn.first.click()
        page.wait_for_timeout(800)

    # 单层展示
    single_layer = page.get_by_text('单层展示', exact=False)
    if single_layer.count() > 0:
        single_layer.first.click()
        page.wait_for_timeout(400)

    spec_names = []
    for spec in product.specs:
        for val in spec.get('values', []):
            text = val.get('text') if isinstance(val, dict) else str(val)
            if text and text not in spec_names:
                spec_names.append(text)

    for name in spec_names[:20]:
        spec_input = page.locator('input[placeholder*="规格"], input[placeholder*="请输入"]').last
        if spec_input.count() == 0:
            break
        spec_input.click()
        spec_input.fill(name[:30])
        spec_input.press('Enter')
        page.wait_for_timeout(500)

    confirm_create = page.get_by_role('button', name=re.compile('确认创建'))
    if confirm_create.count() > 0 and confirm_create.first.is_enabled():
        confirm_create.first.click()
        page.wait_for_timeout(1500)

    # SKU 表填价
    for sku in product.skus:
        price = sku.get('price') or product.price
        if not price:
            continue
        names = sku.get('names') or []
        if not names:
            continue
        row_hint = names[-1][:20]
        row = page.locator('tr, [class*="sku"]').filter(has_text=row_hint).first
        if row.count() == 0:
            continue
        price_cell = row.locator('input').first
        if price_cell.count() > 0:
            price_cell.click()
            price_cell.fill(str(price))
            price_cell.press('Tab')
            page.wait_for_timeout(200)


def _fill_next_select_by_label(page: Page, label: str, keyword: str, exact_option: str) -> bool:
    block = page.locator('[class*="sell-component-info-wrapper"]').filter(has_text=label).first
    if block.count() == 0:
        return False
    block.scroll_into_view_if_needed()
    trigger = block.locator('.next-select-trigger')
    if trigger.count() == 0:
        return False
    trigger.click()
    page.wait_for_timeout(400)
    overlay = page.locator('.next-overlay-wrapper.opened, .next-overlay-wrapper:visible').last
    search = overlay.locator('input').first
    if search.count() > 0:
        search.fill(keyword)
        page.wait_for_timeout(600)
    opt = overlay.get_by_text(exact_option, exact=False)
    if opt.count() == 0:
        opt = overlay.get_by_text(keyword, exact=False)
    if opt.count() == 0:
        page.keyboard.press('Escape')
        return False
    opt.first.click()
    page.keyboard.press('Tab')
    page.wait_for_timeout(300)
    return True


def _fill_text_by_label(page: Page, label: str, value: str) -> bool:
    block = page.locator('[class*="sell-component-info-wrapper"]').filter(has_text=label).first
    if block.count() == 0:
        return False
    inp = block.locator('input, textarea').first
    if inp.count() == 0:
        return False
    inp.scroll_into_view_if_needed()
    inp.fill(value)
    inp.press('Tab')
    page.wait_for_timeout(300)
    return True


def _param_value(product: ProductRecord, keyword: str) -> str:
    for p in product.params:
        label = p.get('label') or ''
        if keyword in label:
            return (p.get('value') or '').strip()
    return ''
