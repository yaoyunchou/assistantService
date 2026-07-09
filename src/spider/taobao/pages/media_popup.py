"""图片空间弹框：从图库补救商品主图（平台做 1:1 处理）。

实测弹框结构（2026-06）：
  点空槽 → 展开上传面板（imagesUploadWrap）
          → 点「从图片空间添加」（mediaSpaceBtn）
          → 弹框出现：.next-overlay-inner.sell-component-image-v2-media-popup
              └── <iframe src="sucai-selector-ng">   ← 全部内容在 iframe 里
                    ├── img[120x120] alicdn.com      ← 缩略图
                    └── button.Footer_selectOk       ← 「确定」按钮

流程：
  点主图区空槽 → 点「从图片空间添加」→ 弹框出现 → 进入 iframe → 勾选缩略图 → 「确定」
"""
from __future__ import annotations

import re
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from utils.logger import get_logger

logger = get_logger('TaobaoMediaPopup')

_MARK_ATTR = 'data-tb-main-upload-slot'

# 图库大弹框选择器：实测类名优先，其余作兜底
_POPUP_SELECTORS = [
    '[class*="sell-component-image-v2-media-popup"]',  # 实测（2026-06）
    '[class*="sell-images-upload-media-dialog"]',
    '[class*="uspimages-popup"]',
    '[class*="images-v2-media-popup"]',
    '[class*="media-popup"]',
    '.next-dialog-wrapper:has(iframe)',
]

# iframe 内缩略图选择器（按优先级）：过滤掉 icon（宽<30px）
_THUMB_SELECTORS = [
    'img[src*="alicdn"], img[src*="imgextra"], img[src*="tbcdn"]',
    'img[class*="thumb"], img[class*="Thumb"]',
    'img[class*="image"], img[class*="Image"]',
    'img[src]',
]

# iframe 内确认按钮选择器
_CONFIRM_SELECTORS = [
    '[class*="selectOk"]',          # Footer_selectOk__nEl3N（实测 2026-06）
    'button:has-text("确定")',
    'button:has-text("确认")',
    'button:has-text("插入")',
]

_FIND_MAIN_SLOT_JS = """() => {
  document.querySelectorAll('[data-tb-main-upload-slot]').forEach(el => {
    el.removeAttribute('data-tb-main-upload-slot');
  });

  const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
  const wrap = root?.querySelector('[class*="valueRenderWrap"]');
  const sections = wrap ? [...wrap.children].filter(el => el.tagName === 'DIV') : [];
  // DOM 实测: valueRenderWrap[2]=主图（div:nth-child(3)）
  const main = sections[2];

  if (!main) {
    const sectionTexts = sections.slice(0, 6).map((el, i) =>
      `[${i}]${(el.innerText || '').replace(/\\s+/g, ' ').slice(0, 60)}`
    );
    return { ok: false, reason: 'main section missing', sectionCount: sections.length, sectionTexts };
  }

  const mainText = (main.innerText || '').replace(/\\s+/g, ' ').slice(0, 200);
  const mainImgCount = [...main.querySelectorAll('img')].filter(img =>
    /alicdn|imgextra|tbcdn/.test(img.src) && img.getBoundingClientRect().width > 8
  ).length;
  if (mainImgCount > 0) {
    return { ok: false, reason: 'main already has image', mainImgCount };
  }

  const pickClickable = (el) =>
    el.closest('button,[role="button"],[class*="upload"],[class*="slot"],[class*="imageWrap"],[class*="image-wrap"]') || el;

  for (const text of ['上传图片', '添加图片', '上传主图', '添加主图']) {
    for (const node of [...main.querySelectorAll('*')].filter(el => (el.textContent || '').trim().includes(text))) {
      const target = pickClickable(node);
      if (target && target.getBoundingClientRect().width > 20) {
        target.setAttribute('data-tb-main-upload-slot', '1');
        return { ok: true, method: 'text', text, mainText };
      }
    }
  }

  const classHits = [...main.querySelectorAll('[class*="upload"],[class*="empty"],[class*="add"],[class*="placeholder"]')]
    .filter(el => {
      const r = el.getBoundingClientRect();
      return !el.querySelector('img[src*="alicdn"],img[src*="imgextra"],img[src*="tbcdn"]') && r.width >= 48 && r.height >= 48;
    });
  if (classHits.length) {
    classHits[0].setAttribute('data-tb-main-upload-slot', '1');
    return { ok: true, method: 'class', className: (classHits[0].className || '').slice(0, 80), mainText };
  }

  const boxes = [...main.querySelectorAll('div,span,button')].filter(el => {
    const r = el.getBoundingClientRect();
    return !el.querySelector('img[src*="alicdn"],img[src*="imgextra"],img[src*="tbcdn"]') && r.width >= 60 && r.height >= 60 && r.width <= 220;
  });
  if (boxes.length) {
    boxes[0].setAttribute('data-tb-main-upload-slot', '1');
    return { ok: true, method: 'box', mainText };
  }

  return { ok: false, reason: 'no slot found', mainText, sectionCount: sections.length };
}"""

_PROBE_OVERLAYS_JS = """() => {
  return [...document.querySelectorAll(
    '.next-dialog,.next-overlay-wrapper,[class*="popup"],[class*="modal"],[class*="dialog"],[class*="overlay"]'
  )].filter(el => { const r = el.getBoundingClientRect(); return r.width > 100 && r.height > 50; })
   .map(el => ({
     tag: el.tagName,
     cls: (el.className||'').slice(0,120),
     w: Math.round(el.getBoundingClientRect().width),
     h: Math.round(el.getBoundingClientRect().height),
     text: (el.innerText||'').replace(/\\s+/g,' ').slice(0,80),
   }));
}"""


def _click_main_upload_slot(page: Page) -> None:
    logger.info('[图库] 定位主图区空槽（sections[2]）…')
    main_wrap = page.locator(
        '#ai-category-page-main-do-not-add-padding [class*="valueRenderWrap"] > div'
    ).nth(2)
    try:
        main_wrap.scroll_into_view_if_needed(timeout=10_000)
    except Exception as e:
        logger.warning('[图库] scroll 失败: %s', e)

    result = page.evaluate(_FIND_MAIN_SLOT_JS)
    logger.info('[图库] JS 空槽结果: %s', result)

    if result.get('ok'):
        slot = page.locator(f'[{_MARK_ATTR}="1"]').first
        slot.wait_for(state='visible', timeout=5_000)
        logger.info('[图库] 点击空槽 method=%s', result.get('method'))
        slot.click(timeout=10_000)
        return

    logger.warning('[图库] JS 未找到槽(%s)，文本兜底', result.get('reason'))
    for pat in (r'上传图片', r'添加图片', r'上传主图', r'添加主图'):
        s = main_wrap.get_by_text(re.compile(pat)).first
        if s.count() > 0:
            s.scroll_into_view_if_needed(timeout=5_000)
            logger.info('[图库] 文本兜底 pat=%s', pat)
            s.click(timeout=10_000)
            return

    raise RuntimeError(f'[图库] 未找到主图空槽: {result}')


def _find_popup(page: Page):
    """在已知选择器中找到可见的图库弹框，返回 locator 或 None。"""
    for sel in _POPUP_SELECTORS:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            box = loc.bounding_box()
            if box and box['width'] > 100 and box['height'] > 100:
                logger.info('[图库] 找到弹框 sel=%s  size=%sx%s', sel, int(box['width']), int(box['height']))
                return loc
        except Exception:
            pass
    return None


def _click_space_btn(page: Page) -> bool:
    """点击上传面板中的「从图片空间添加」按钮，返回是否成功点击。"""
    for sel in ('[class*="mediaSpaceBtn"]', 'button:has-text("从图片空间添加")', 'button:has-text("图片空间")'):
        try:
            btn = page.locator(sel).first
            if btn.count() == 0:
                continue
            box = btn.bounding_box()
            if box and box['width'] > 0:
                logger.info('[图库] 点击「从图片空间添加」sel=%s', sel)
                btn.click(timeout=5_000)
                return True
        except Exception as e:
            logger.debug('[图库] 点击图片空间按钮失败 sel=%s: %s', sel, e)
    return False


def _get_popup_frame(page: Page, popup_loc):
    """
    获取弹框内 iframe 的 FrameLocator。
    实测：整个图库选择器都在 sucai-selector-ng iframe 里。
    """
    try:
        iframe = popup_loc.locator('iframe').first
        if iframe.count() > 0:
            # 用 popup 内 iframe 的 frame_locator
            for sel in _POPUP_SELECTORS:
                try:
                    fl = page.frame_locator(f'{sel} iframe')
                    # 验证 frame 可用（能找到任意元素）
                    fl.locator('body').wait_for(state='attached', timeout=3_000)
                    logger.info('[图库] 获取 iframe FrameLocator  popup_sel=%s', sel)
                    return fl
                except Exception:
                    continue
    except Exception as e:
        logger.debug('[图库] 获取 iframe 失败: %s', e)
    return None


def _find_thumbs_in_frame(frame_loc) -> tuple:
    """在 iframe FrameLocator 里找缩略图，返回 (locator, count)。"""
    for sel in _THUMB_SELECTORS:
        try:
            thumbs = frame_loc.locator(sel)
            n = thumbs.count()
            if n == 0:
                continue
            # 过滤掉 icon（宽<30px）：逐个检查
            visible_indices = [
                i for i in range(n)
                if (thumbs.nth(i).bounding_box() or {}).get('width', 0) >= 30
            ]
            if visible_indices:
                logger.info('[图库] iframe 内找到缩略图 sel=%s  total=%s  visible=%s', sel, n, len(visible_indices))
                return thumbs, visible_indices
        except Exception:
            pass
    return None, []


def _click_confirm_in_frame(frame_loc) -> bool:
    """在 iframe 里点确定按钮，返回是否成功。"""
    for sel in _CONFIRM_SELECTORS:
        try:
            btn = frame_loc.locator(sel).first
            if btn.count() == 0:
                continue
            box = btn.bounding_box()
            if box and box['width'] > 0:
                logger.info('[图库] 点击确定 sel=%s', sel)
                btn.click(timeout=5_000)
                return True
        except Exception as e:
            logger.debug('[图库] 点击确定失败 sel=%s: %s', sel, e)
    return False


def recover_main_from_media_popup(page: Page, pick_count: int) -> None:
    """
    从图库弹框补救主图：
      点主图空槽 → 点「从图片空间添加」→ 弹框(iframe)出现
      → 在 iframe 里勾选最近 pick_count 张 → 「确定」
    """
    logger.info('[图库] ══ 开始图库补救 pick_count=%s ══', pick_count)
    _click_main_upload_slot(page)

    # ── 等待上传面板出现，再点「从图片空间添加」──
    logger.info('[图库] 等待上传面板 & 点「从图片空间添加」…')
    space_clicked = False
    for attempt in range(6):   # 最多等 6×1.5s=9s
        page.wait_for_timeout(1_500)
        if _click_space_btn(page):
            space_clicked = True
            break
        logger.debug('[图库] 第 %s 次未找到图片空间按钮', attempt + 1)

    if not space_clicked:
        logger.warning('[图库] 未找到「从图片空间添加」按钮，尝试直接找弹框')

    # ── 等待图库弹框出现（最多再等 15s）──
    logger.info('[图库] 等待图库弹框出现…')
    popup_loc = None
    for attempt in range(10):   # 10 × 1.5s = 15s
        page.wait_for_timeout(1_500)
        popup_loc = _find_popup(page)
        if popup_loc:
            break
        overlays = page.evaluate(_PROBE_OVERLAYS_JS)
        logger.info('[图库] 第 %s 次探测，当前浮层: %s', attempt + 1, overlays)
        # 若按钮没被点到，继续尝试
        if not space_clicked:
            _click_space_btn(page)

    if not popup_loc:
        overlays = page.evaluate(_PROBE_OVERLAYS_JS)
        raise RuntimeError(f'[图库] 未找到图库弹框，当前浮层={overlays}')

    # ── 进入 iframe 操作 ──
    frame_loc = _get_popup_frame(page, popup_loc)
    if frame_loc is None:
        raise RuntimeError('[图库] 弹框内未找到可用 iframe（sucai-selector-ng）')

    # iframe 加载需要时间
    page.wait_for_timeout(2_000)

    thumbs_loc, visible_indices = _find_thumbs_in_frame(frame_loc)
    if not visible_indices:
        raise RuntimeError(
            '[图库] iframe 内未找到缩略图，请确认图片已上传到图片空间'
        )

    pick = min(pick_count, len(visible_indices))
    # 最近上传的图排在末尾，取末尾 pick 张
    chosen = visible_indices[-pick:]
    logger.info('[图库] 共 %s 张可见缩略图，勾选最近 %s 张（indices=%s）',
                len(visible_indices), pick, chosen)

    for rank, idx in enumerate(chosen, 1):
        try:
            src = (thumbs_loc.nth(idx).get_attribute('src') or '')[:120]
        except Exception:
            src = '(无法获取)'
        logger.info('[图库] 勾选 [%s/%s] index=%s  src=%s', rank, pick, idx, src)
        thumbs_loc.nth(idx).click()
        page.wait_for_timeout(300)

    # ── 点确定 ──
    if not _click_confirm_in_frame(frame_loc):
        logger.warning('[图库] iframe 内未找到确定按钮，尝试 popup 外层兜底')
        confirm_btn = page.get_by_role('button', name=re.compile('确定|确认'))
        if confirm_btn.count() > 0:
            confirm_btn.first.click()
        else:
            raise RuntimeError('[图库] 未找到确定按钮')

    page.wait_for_timeout(3_000)
    logger.info('[图库] ══ 图库补救完成，已勾选 %s 张并确认 ══', pick)
