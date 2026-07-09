"""类目页图片列表审计。"""

from __future__ import annotations



from dataclasses import dataclass, asdict

from typing import Any, Dict, Optional



from playwright.sync_api import Page



from utils.logger import get_logger



logger = get_logger('TaobaoImageAudit')



_AUDIT_JS = """

() => {

  const root = document.querySelector('#ai-category-page-main-do-not-add-padding');

  const wrap = root?.querySelector('[class*="valueRenderWrap"]');

  const sections = wrap ? [...wrap.children].filter(el => el.tagName === 'DIV') : [];



  const imgSrc = (img) =>

    img.src || img.currentSrc || img.getAttribute('data-src') || img.getAttribute('data-original') || '';



  const isCdnImg = (img) => {

    const src = imgSrc(img);

    if (!src || src.startsWith('data:')) return false;

    if (/alicdn|imgextra|tbcdn|oss-cn|taobaocdn|gw.alicdn/.test(src)) {

      const r = img.getBoundingClientRect();

      return r.width > 8 || r.height > 8;

    }

    if (src.startsWith('blob:')) {

      const r = img.getBoundingClientRect();

      return r.width > 8 && r.height > 8;

    }

    return false;

  };



  const scan = (container) => {

    if (!container) return { count: 0, relaxed: 0, samples: [] };

    const all = [...container.querySelectorAll('img')];

    const strict = all.filter(isCdnImg);

    const relaxed = all.filter((img) => {

      const r = img.getBoundingClientRect();

      const src = imgSrc(img);

      return r.width > 8 && r.height > 8 && src && !src.startsWith('data:');

    });

    return {

      count: strict.length,

      relaxed: relaxed.length,

      samples: strict.slice(0, 3).map((img) => imgSrc(img).slice(0, 120)),

    };

  };



  const sectionPreview = (el, idx) => {

    if (!el) return { idx, missing: true };

    const s = scan(el);

    const text = (el.innerText || '').replace(/\\s+/g, ' ').slice(0, 100);

    return { idx, count: s.count, relaxed: s.relaxed, text, samples: s.samples };

  };



  const hintPatterns = [

    /已上传\\s*(\\d+)\\s*张/,

    /成功上传\\s*(\\d+)\\s*张/,

    /上传成功[\\s，,]*(\\d+)\\s*张/,

    /共\\s*(\\d+)\\s*张/,

  ];

  let hint = null;

  let hintMatch = null;

  const bodyText = document.body.innerText || '';

  for (const re of hintPatterns) {

    const m = bodyText.match(re);

    if (m) {

      hint = parseInt(m[1], 10);

      hintMatch = re.toString();

      break;

    }

  }



  const confirm = [...document.querySelectorAll('button')].find(

    (b) => b.innerText.includes('确认') && b.innerText.includes('下一步')

  );



  // DOM 实测: valueRenderWrap > div:nth-child(3) = 主图，div:nth-child(4) = 更多图片
  // nth-child 1-indexed → 数组下标 sections[2] / sections[3]
  const mainByIndex = scan(sections[2]);

  const moreByIndex = scan(sections[3]);

  const pageImgs = [...document.querySelectorAll('img')].filter(isCdnImg);

  const footerEl = document.querySelector('#ai-category-image-mode-footer')
    || document.querySelector('[class*="ai-category-image-mode-footer"]');
  const uploadFooter = footerEl ? {
    present: true,
    visible: footerEl.getBoundingClientRect().width > 0,
    text: (footerEl.innerText || '').replace(/\\s+/g, ' ').slice(0, 120),
    buttons: [...footerEl.querySelectorAll('button')].map((b) => (b.innerText || '').trim()),
  } : { present: false, visible: false, buttons: [] };

  return {

    main: { count: mainByIndex.count, relaxed: mainByIndex.relaxed, samples: mainByIndex.samples },

    more: { count: moreByIndex.count, relaxed: moreByIndex.relaxed, samples: moreByIndex.samples },

    uploadedHint: hint,

    hintMatch,

    confirmDisabled: confirm ? confirm.disabled : null,

    hasMediaPopup: !!document.querySelector('[class*="images-v2-media-popup"]'),

    debug: {

      sectionCount: sections.length,

      sections: sections.slice(0, 5).map((el, i) => sectionPreview(el, i)),

      pageCdnImgCount: pageImgs.length,

      bodyHintSnippet: bodyText.match(/[^\\n]{0,30}上传[^\\n]{0,30}/)?.[0] || null,
      uploadFooter,

    },

  };

}

"""





@dataclass

class ImageListAudit:

    main_count: int

    more_count: int

    total_in_lists: int

    uploaded_hint: Optional[int]

    needs_main_recovery: bool

    confirm_next_disabled: Optional[bool]

    has_media_popup: bool

    raw_debug: Optional[Dict[str, Any]] = None



    def to_dict(self) -> Dict[str, Any]:

        return asdict(self)





def audit_category_images(page: Page) -> ImageListAudit:

    data = page.evaluate(_AUDIT_JS)

    main = int(data['main']['count'])

    more = int(data['more']['count'])

    main_relaxed = int(data['main'].get('relaxed', main))

    more_relaxed = int(data['more'].get('relaxed', more))

    hint = data.get('uploadedHint')



    # 严格计数为 0 时用 relaxed 兜底（DOM 结构或 CDN 域名变化时）

    if main == 0 and main_relaxed > 0:

        logger.info('主图区 strict=0 relaxed=%s，采用 relaxed 计数', main_relaxed)

        main = main_relaxed

    if more == 0 and more_relaxed > 0:

        logger.info('更多图区 strict=0 relaxed=%s，采用 relaxed 计数', more_relaxed)

        more = more_relaxed



    debug = data.get('debug') or {}

    if hint is None and debug.get('bodyHintSnippet'):

        logger.info('未匹配 uploaded_hint，页面片段=%s', debug.get('bodyHintSnippet'))



    audit = ImageListAudit(

        main_count=main,

        more_count=more,

        total_in_lists=main + more,

        uploaded_hint=hint,

        needs_main_recovery=(main == 0 and (more > 0 or (hint or 0) > 0)),

        confirm_next_disabled=data.get('confirmDisabled'),

        has_media_popup=bool(data.get('hasMediaPopup')),

        raw_debug={

            **debug,

            'main_samples': data['main'].get('samples'),

            'more_samples': data['more'].get('samples'),

            'hint_match': data.get('hintMatch'),

        },

    )

    logger.info(
        '[审计] main=%s more=%s hint=%s needs_recovery=%s '
        'pageCdn=%s sections=%s hintMatch=%s  '
        'main_samples=%s  more_samples=%s',
        audit.main_count,
        audit.more_count,
        audit.uploaded_hint,
        audit.needs_main_recovery,
        debug.get('pageCdnImgCount'),
        debug.get('sectionCount'),
        data.get('hintMatch'),
        data['main'].get('samples'),
        data['more'].get('samples'),
    )

    return audit





def should_recover_main(audit: ImageListAudit, uploaded_count: int) -> bool:

    """主图为空时是否应走图片空间补救。"""

    if audit.main_count >= 1:

        return False

    if audit.needs_main_recovery:

        return True

    # 本地上传后主图仍空：即使审计未数到更多图/hint，也尝试图片空间

    return uploaded_count > 0


