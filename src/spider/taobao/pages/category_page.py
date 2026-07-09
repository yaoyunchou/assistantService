"""类目页：本地上传、干扰弹层、类目属性。

正确流程：
  1. upload_all_images  — 逐张点「从本地上传」→ 文件选择器 → 等待上传完成
                          （非 1:1 图进「更多图片」，同时入卖家图库）
  2. ensure_main_images — 审计主图区；若 main < 1 则打开图库弹框，
                          勾选最近 N 张 → 平台做 1:1 → 入主图
  3. fill_category_attrs — 品牌/品名/类目，等「确认，下一步」可点
  4. goto_publish_page   — 点「确认，下一步」跳转发布页
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page, BrowserContext

from spider.taobao.audit.image_lists import audit_category_images
from spider.taobao.config import DISMISS_TEXTS, UPLOAD_BETWEEN_SEC
from spider.taobao.data.loader import ProductRecord
from spider.taobao.pages.media_popup import recover_main_from_media_popup
from utils.logger import get_logger

logger = get_logger('TaobaoCategoryPage')


# ──────────────────────────────────────────────────────────
# 干扰弹层关闭
# ──────────────────────────────────────────────────────────

def dismiss_overlays(page: Page) -> None:
    """关闭 toast / next-dialog，排除图片空间弹框。"""
    for text in DISMISS_TEXTS:
        try:
            dlg = page.locator('.next-dialog').filter(
                has_not=page.locator('[class*="images-v2-media-popup"]')
            )
            btn = dlg.get_by_role('button', name=re.compile(text))
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                page.wait_for_timeout(300)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────
# 本地上传
# ──────────────────────────────────────────────────────────

def _click_local_upload_button(page: Page):
    """定位「从本地上传」按钮。"""
    for loc in (
        page.get_by_role('button', name=re.compile('从本地上传')),
        page.locator('button').filter(has_text=re.compile('从本地上传')),
        page.locator('[class*="upload"]').filter(has_text=re.compile('从本地上传')),
    ):
        if loc.count() == 0:
            continue
        btn = loc.first
        btn.scroll_into_view_if_needed(timeout=10_000)
        btn.wait_for(state='visible', timeout=10_000)
        return btn
    raise RuntimeError('未找到「从本地上传」按钮，请确认页面已加载完成')


def _page_state_snapshot(page: Page) -> dict:
    """快照当前页面图片区状态，供日志使用。"""
    try:
        return page.evaluate("""() => {
            const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
            const wrap = root?.querySelector('[class*="valueRenderWrap"]');
            const sections = wrap ? [...wrap.children].filter(e => e.tagName === 'DIV') : [];
            const countImgs = (el) => el
                ? [...el.querySelectorAll('img')].filter(img => {
                    const r = img.getBoundingClientRect();
                    return r.width > 8 && img.src && !img.src.startsWith('data:');
                  }).length
                : 0;
            const allBtns = [...document.querySelectorAll('button')].map(b => ({
                text: (b.innerText || '').trim().slice(0, 30),
                disabled: b.disabled,
            })).filter(b => b.text);
            const confirmNext = allBtns.find(b => b.text.includes('确认') && b.text.includes('下一步'));
            // DOM 实测: valueRenderWrap[2]=主图, [3]=更多图片
            const sectionTexts = sections.slice(0, 6).map((el, i) =>
                `[${i}]${(el.innerText || '').replace(/\\s+/g, ' ').slice(0, 50)}`
            );
            return {
                url: location.href.slice(0, 120),
                sectionCount: sections.length,
                mainImgs: countImgs(sections[2]),
                moreImgs: countImgs(sections[3]),
                confirmNext,
                sectionTexts,
                pageText200: (document.body?.innerText || '').slice(0, 200).replace(/\\s+/g, ' '),
            };
        }""")
    except Exception as e:
        return {'error': str(e)}


def upload_one_local(page: Page, file_path: Path) -> None:
    """
    上传一张图片：
      点「从本地上传」→ 文件选择器选文件 → 等待服务器处理
    非 1:1 图 → 更多图片 + 进图库；1:1 → 主图。
    「确认，下一步」需等主图 ≥ 1 才激活，与上传无关，不在这里点。
    """
    logger.info('[上传] ── 准备上传 %s ──', file_path.name)

    snap_before = _page_state_snapshot(page)
    logger.info('[上传] 上传前页面快照: %s', snap_before)

    btn = _click_local_upload_button(page)
    logger.info('[上传] 找到「从本地上传」按钮，准备点击并打开文件选择器')

    with page.expect_file_chooser(timeout=15_000) as fc_info:
        btn.click()
    fc = fc_info.value
    logger.info('[上传] 文件选择器已打开，设置文件: %s', file_path)
    fc.set_files(str(file_path))
    logger.info('[上传] 文件已设置，等待服务器处理（约 8 秒）…')

    # 等待 AI 处理 / 缩略图渲染
    page.wait_for_timeout(8_000)

    snap_after = _page_state_snapshot(page)
    audit = audit_category_images(page)
    logger.info(
        '[上传] 处理完成 ─ file=%s  main=%s more=%s hint=%s  '
        '页面快照=%s  audit_debug=%s',
        file_path.name,
        audit.main_count, audit.more_count, audit.uploaded_hint,
        snap_after,
        {
            'sectionCount': (audit.raw_debug or {}).get('sectionCount'),
            'pageCdn':      (audit.raw_debug or {}).get('pageCdnImgCount'),
            'sections':     (audit.raw_debug or {}).get('sections'),
            'main_samples': (audit.raw_debug or {}).get('main_samples'),
            'more_samples': (audit.raw_debug or {}).get('more_samples'),
            'hintMatch':    (audit.raw_debug or {}).get('hint_match'),
        },
    )


def upload_all_images(page: Page, images: list[Path]) -> dict:
    """逐张上传，全部完成后返回最后一次审计。"""
    logger.info('[上传] ══ 开始批量上传 共 %s 张图片 ══', len(images))
    for i, img in enumerate(images):
        logger.info('[上传] 文件列表[%s/%s]: %s', i + 1, len(images), img)
    logger.info('[上传] ──────────────────────────────')

    last_audit = None
    for idx, img in enumerate(images, start=1):
        dismiss_overlays(page)
        upload_one_local(page, img)
        time.sleep(UPLOAD_BETWEEN_SEC)
        last_audit = audit_category_images(page)
        logger.info(
            '[上传] ─ 第 %s/%s 张完成汇总 ─ main=%s more=%s total=%s hint=%s',
            idx, len(images),
            last_audit.main_count,
            last_audit.more_count,
            last_audit.total_in_lists,
            last_audit.uploaded_hint,
        )

    logger.info(
        '[上传] ══ 批量上传结束 ══ main=%s more=%s hint=%s',
        (last_audit.main_count if last_audit else '?'),
        (last_audit.more_count if last_audit else '?'),
        (last_audit.uploaded_hint if last_audit else '?'),
    )
    return last_audit.to_dict() if last_audit else {}


# ──────────────────────────────────────────────────────────
# 主图补救（图库）
# ──────────────────────────────────────────────────────────

def ensure_main_images(page: Page, image_count: int) -> dict:
    """
    检查主图；若 main < 1 则从图库补救：
      点主图槽 → 图库弹框 → 勾选最近 N 张 → 平台做 1:1
    补救成功后「确认，下一步」按钮激活。
    """
    logger.info('[主图] ══ 开始主图检查 uploaded=%s ══', image_count)

    audit = audit_category_images(page)
    snap = _page_state_snapshot(page)
    logger.info(
        '[主图] 当前审计 main=%s more=%s hint=%s  confirmNext=%s  snap=%s',
        audit.main_count, audit.more_count, audit.uploaded_hint,
        snap.get('confirmNext'), snap,
    )
    logger.info(
        '[主图] audit debug: sectionCount=%s pageCdn=%s sections=%s',
        (audit.raw_debug or {}).get('sectionCount'),
        (audit.raw_debug or {}).get('pageCdnImgCount'),
        (audit.raw_debug or {}).get('sections'),
    )

    if audit.main_count >= 1:
        logger.info('[主图] ✓ 主图已满足 main=%s，无需图库补救', audit.main_count)
        return audit.to_dict()

    pick = max(image_count, audit.more_count or 0, audit.uploaded_hint or 0, 1)
    logger.info(
        '[主图] ✗ 主图为空 → 打开图库补救 pick=%s（more=%s hint=%s uploaded=%s）',
        pick, audit.more_count, audit.uploaded_hint, image_count,
    )
    dismiss_overlays(page)
    recover_main_from_media_popup(page, pick_count=pick)
    page.wait_for_timeout(3_000)

    after = audit_category_images(page)
    snap_after = _page_state_snapshot(page)
    logger.info(
        '[主图] 图库补救后 main=%s more=%s hint=%s  confirmNext=%s  snap=%s',
        after.main_count, after.more_count, after.uploaded_hint,
        snap_after.get('confirmNext'), snap_after,
    )

    if after.main_count < 1:
        raise RuntimeError(
            f'[主图] 图库补救后主图仍为空 main={after.main_count}'
            f'  audit={after.to_dict()}'
        )
    logger.info('[主图] ✓ 补救成功 main=%s，「确认，下一步」应已激活', after.main_count)
    return after.to_dict()


# ──────────────────────────────────────────────────────────
# 类目属性 + 跳转发布页
# ──────────────────────────────────────────────────────────

def fill_category_attrs(page: Page, product: ProductRecord) -> None:
    """填写品牌、品名/型号，等「确认，下一步」可点。"""
    for sel in ('[class*="path-name"]', '[class*="categoryCard"]', '[class*="category-card"]'):
        loc = page.locator(sel)
        if loc.count() > 0:
            try:
                loc.first.click(timeout=3000)
                page.wait_for_timeout(500)
                break
            except Exception:
                continue

    _fill_next_select_by_label(page, '品牌', '无品牌', '无品牌/无注册商标')

    pinming = product.brand_short_name
    for label in ('品名', '型号', '产品名称'):
        if _fill_text_by_label(page, label, pinming):
            break

    confirm = page.get_by_role('button', name=re.compile('确认.*下一步'))
    confirm.wait_for(state='visible', timeout=30_000)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if confirm.is_enabled():
                break
        except Exception:
            pass
        page.wait_for_timeout(500)
    if not confirm.is_enabled():
        snap = _page_state_snapshot(page)
        raise RuntimeError(
            f'「确认，下一步」仍不可点，请确认主图已上传、品牌品名已填写  snap={snap}'
        )


def goto_publish_page(page: Page, context: BrowserContext) -> Page:
    confirm = page.get_by_role('button', name=re.compile('确认.*下一步'))
    with context.expect_page(timeout=60_000) as new_page_info:
        confirm.click()
    publish_page = new_page_info.value
    publish_page.wait_for_load_state('domcontentloaded', timeout=60_000)
    publish_page.wait_for_url(re.compile(r'publish\.htm'), timeout=60_000)
    return publish_page


# ──────────────────────────────────────────────────────────
# 内部辅助
# ──────────────────────────────────────────────────────────

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

    # 优先精确匹配 .options-item（实测选项节点类名），避免误点外层容器
    for item_sel in ('[class*="options-item"]', 'li', '[role="option"]'):
        opt = overlay.locator(item_sel).filter(has_text=exact_option)
        if opt.count() > 0:
            opt.first.click()
            break
    else:
        # 最终兜底：get_by_text 精确匹配
        opt = overlay.get_by_text(exact_option, exact=True)
        if opt.count() == 0:
            opt = overlay.get_by_text(keyword, exact=False)
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
