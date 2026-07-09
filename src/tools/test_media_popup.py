"""
诊断脚本：测试图库弹框点击和缩略图选择
用法：
  1. 启动 dev.py，让浏览器停在「以图发品」类目页（上传了图片、更多图片区有缩略图）
  2. 在另一个终端运行：  python src/tools/test_media_popup.py
  3. 把控制台输出复制给 AI
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from spider.query_manager import BrowserPool
from utils.logger import get_logger

logger = get_logger('TestMediaPopup')

# ── JS：抓取当前页面所有浮层 ────────────────────────────────────
PROBE_JS = """() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const els = [...document.querySelectorAll('*')].filter(el => {
    const cls = el.className || '';
    return typeof cls === 'string' && (
      cls.includes('popup') || cls.includes('dialog') || cls.includes('modal') ||
      cls.includes('overlay') || cls.includes('usp') || cls.includes('media') ||
      cls.includes('picker') || cls.includes('space') || cls.includes('images')
    ) && visible(el);
  });
  return els.slice(0, 30).map(el => {
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName,
      cls: (el.className||'').slice(0,150),
      id: el.id || '',
      w: Math.round(r.width),
      h: Math.round(r.height),
      top: Math.round(r.top),
      childCount: el.children.length,
      text: (el.innerText||'').replace(/\\s+/g,' ').slice(0,80),
    };
  });
}"""

# ── JS：找主图区空槽 ──────────────────────────────────────────
FIND_SLOT_JS = """() => {
  const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
  const wrap = root?.querySelector('[class*="valueRenderWrap"]');
  const sections = wrap ? [...wrap.children].filter(e => e.tagName==='DIV') : [];
  const info = sections.map((el, i) => ({
    idx: i,
    cls: (el.className||'').slice(0,80),
    text: (el.innerText||'').replace(/\\s+/g,' ').slice(0,100),
    imgCount: el.querySelectorAll('img').length,
    cdnImgCount: [...el.querySelectorAll('img')].filter(img =>
      /alicdn|imgextra|tbcdn/.test(img.src) && img.getBoundingClientRect().width > 8
    ).length,
  }));
  const main = sections[2];  // nth-child(3) 实测是主图
  const slots = main ? [...main.querySelectorAll('*')].filter(el =>
    (el.textContent||'').trim().includes('上传图片') &&
    el.getBoundingClientRect().width > 20
  ).map(el => ({
    tag: el.tagName,
    cls: (el.className||'').slice(0,80),
    text: (el.textContent||'').trim().slice(0,40),
  })) : [];
  return { sectionCount: sections.length, sections: info, mainSlots: slots };
}"""

# ── JS：弹框打开后抓取内部结构 ─────────────────────────────────
POPUP_STRUCTURE_JS = """() => {
  const candidates = [
    document.querySelector('[class*="sell-images-upload-media-dialog"]'),
    document.querySelector('[class*="uspimages-popup"]'),
    document.querySelector('[class*="images-v2-media-popup"]'),
    document.querySelector('[class*="media-popup"]'),
    ...[...document.querySelectorAll('.next-dialog')].filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 400 && r.height > 200;
    }),
  ].filter(Boolean);

  if (!candidates.length) return { found: false };

  const popup = candidates[0];
  const allImgs = [...popup.querySelectorAll('img')];
  const imgs = allImgs.map(img => ({
    src: (img.src||'').slice(0,120),
    w: Math.round(img.getBoundingClientRect().width),
    h: Math.round(img.getBoundingClientRect().height),
    cls: (img.className||'').slice(0,60),
    alt: img.alt||'',
  })).filter(i => i.w > 10);

  const btns = [...popup.querySelectorAll('button')].map(b => ({
    text: (b.innerText||'').trim().slice(0,40),
    disabled: b.disabled,
    cls: (b.className||'').slice(0,60),
  }));

  // iframe 检测
  const iframes = [...popup.querySelectorAll('iframe')].map(f => ({
    src: (f.src||'').slice(0,120),
    w: Math.round(f.getBoundingClientRect().width),
    h: Math.round(f.getBoundingClientRect().height),
  }));

  // uspimages 子区域
  const usp = popup.querySelector('[class*="uspimages"]');
  const uspImgs = usp ? [...usp.querySelectorAll('img')].filter(img =>
    img.getBoundingClientRect().width > 10
  ).map(img => ({
    src: (img.src||'').slice(0,120),
    w: Math.round(img.getBoundingClientRect().width),
    cls: (img.className||'').slice(0,60),
  })) : [];

  return {
    found: true,
    popup: {
      tag: popup.tagName,
      cls: (popup.className||'').slice(0,150),
      w: Math.round(popup.getBoundingClientRect().width),
      h: Math.round(popup.getBoundingClientRect().height),
    },
    imgs: imgs.slice(0, 20),
    imgCount: imgs.length,
    uspImgs: uspImgs.slice(0, 20),
    uspImgCount: uspImgs.length,
    btns,
    iframes,
    iframeCount: iframes.length,
  };
}"""


def run_test(page):
    print("\n" + "="*60)
    print("【第 1 步】当前页面结构")
    print("="*60)
    slot_info = page.evaluate(FIND_SLOT_JS)
    print(f"  sections 数量: {slot_info['sectionCount']}")
    for s in slot_info['sections']:
        print(f"  [{s['idx']}] cls={s['cls'][:50]}  img={s['imgCount']}(cdn={s['cdnImgCount']})  text={s['text'][:60]}")
    print(f"  主图区(sections[2])空槽: {slot_info['mainSlots']}")

    print("\n" + "="*60)
    print("【第 2 步】点击主图区第一个「上传图片」")
    print("="*60)
    main_section = page.locator(
        '#ai-category-page-main-do-not-add-padding [class*="valueRenderWrap"] > div'
    ).nth(2)

    # 找「上传图片」按钮
    slot = main_section.get_by_text('上传图片').first
    if slot.count() == 0:
        print("  ✗ 未找到「上传图片」文字，改用 JS 标记")
        result = page.evaluate("""() => {
            const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
            const wrap = root?.querySelector('[class*="valueRenderWrap"]');
            const sections = wrap ? [...wrap.children].filter(e => e.tagName==='DIV') : [];
            const main = sections[2];
            if (!main) return false;
            const node = [...main.querySelectorAll('*')].find(el =>
              (el.textContent||'').trim().includes('上传图片') &&
              el.getBoundingClientRect().width > 20
            );
            if (!node) return false;
            const target = node.closest('button,[role="button"],[class*="upload"],[class*="slot"],[class*="imageWrap"]') || node;
            target.setAttribute('data-test-slot', '1');
            return true;
        }""")
        if not result:
            print("  ✗ JS 也找不到空槽，请确认主图区为空且页面已加载")
            return
        slot = page.locator('[data-test-slot="1"]').first

    slot.scroll_into_view_if_needed()
    print(f"  ✓ 找到空槽，准备点击")
    slot.click()

    print("\n" + "="*60)
    print("【第 3 步】点击后等 2 秒，探测浮层")
    print("="*60)
    page.wait_for_timeout(2_000)
    overlays = page.evaluate(PROBE_JS)
    print(f"  浮层数量: {len(overlays)}")
    for o in overlays:
        print(f"  {o['tag']}  cls={o['cls'][:80]}  {o['w']}x{o['h']}  text={o['text'][:50]}")

    print("\n" + "="*60)
    print("【第 4 步】弹框内部结构")
    print("="*60)
    popup_info = page.evaluate(POPUP_STRUCTURE_JS)
    if not popup_info.get('found'):
        print("  ✗ 未找到弹框")
        print("\n  → 等 3 秒后再查一次…")
        page.wait_for_timeout(3_000)
        popup_info = page.evaluate(POPUP_STRUCTURE_JS)

    if popup_info.get('found'):
        p = popup_info['popup']
        print(f"  弹框: {p['tag']}  cls={p['cls']}  {p['w']}x{p['h']}")
        print(f"  img 数量(过滤后): {popup_info['imgCount']}  样本: {[i['src'][:60] for i in popup_info['imgs'][:3]]}")
        print(f"  uspImgs 数量: {popup_info['uspImgCount']}  样本: {[i['src'][:60] for i in popup_info['uspImgs'][:3]]}")
        print(f"  iframe 数量: {popup_info['iframeCount']}  {popup_info['iframes']}")
        print(f"  按钮: {popup_info['btns']}")
    else:
        print("  ✗ 仍未找到弹框，请把上方浮层信息复制给 AI")

    print("\n" + "="*60)
    print("测试完成，请把全部输出复制给 AI")
    print("="*60 + "\n")


def main():
    pool = BrowserPool(headless=False)

    def _run(page):
        print(f"\n当前页面 URL: {page.url}")
        if 'category' not in page.url and 'ai' not in page.url:
            print("警告：当前页面不是类目页，请先导航到以图发品的类目页再运行")
        run_test(page)

    try:
        pool.execute(_run, timeout=120)
    finally:
        pool.close()


if __name__ == '__main__':
    main()
