/**
 * 诊断脚本：测试图库弹框点击和缩略图选择
 *
 * 用法：
 *   1. 在浏览器打开「以图发品」类目页，确保主图区有空槽（显示「上传图片」）
 *   2. 打开浏览器开发者工具 → Console
 *   3. 把本文件全部内容粘贴进去，回车执行
 *   4. 等待输出完毕，把控制台全部内容复制给 AI
 */

(async () => {

  const SEP = '='.repeat(60);
  const log = (...args) => console.log(...args);

  // ── 工具：等待指定毫秒 ────────────────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── 工具：探测所有可见浮层 ────────────────────────────────────
  function probeOverlays() {
    const visible = el => {
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
        cls: (el.className || '').slice(0, 150),
        id: el.id || '',
        w: Math.round(r.width),
        h: Math.round(r.height),
        top: Math.round(r.top),
        childCount: el.children.length,
        text: (el.innerText || '').replace(/\s+/g, ' ').slice(0, 80),
      };
    });
  }

  // ── 工具：探测弹框内部结构 ────────────────────────────────────
  function probePopup() {
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
      src: (img.src || '').slice(0, 120),
      w: Math.round(img.getBoundingClientRect().width),
      h: Math.round(img.getBoundingClientRect().height),
      cls: (img.className || '').slice(0, 60),
      alt: img.alt || '',
    })).filter(i => i.w > 10);

    const btns = [...popup.querySelectorAll('button')].map(b => ({
      text: (b.innerText || '').trim().slice(0, 40),
      disabled: b.disabled,
      cls: (b.className || '').slice(0, 60),
    }));

    const iframes = [...popup.querySelectorAll('iframe')].map(f => ({
      src: (f.src || '').slice(0, 120),
      w: Math.round(f.getBoundingClientRect().width),
      h: Math.round(f.getBoundingClientRect().height),
    }));

    const usp = popup.querySelector('[class*="uspimages"]');
    const uspImgs = usp ? [...usp.querySelectorAll('img')].filter(img =>
      img.getBoundingClientRect().width > 10
    ).map(img => ({
      src: (img.src || '').slice(0, 120),
      w: Math.round(img.getBoundingClientRect().width),
      cls: (img.className || '').slice(0, 60),
    })) : [];

    return {
      found: true,
      popup: {
        tag: popup.tagName,
        cls: (popup.className || '').slice(0, 150),
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
  }

  // ════════════════════════════════════════════════════════════
  log(SEP);
  log('【第 1 步】当前页面 URL & 结构');
  log(SEP);
  log('URL:', location.href);

  const root = document.querySelector('#ai-category-page-main-do-not-add-padding');
  const wrap = root?.querySelector('[class*="valueRenderWrap"]');
  const sections = wrap ? [...wrap.children].filter(e => e.tagName === 'DIV') : [];
  log(`sections 数量: ${sections.length}`);
  sections.forEach((el, i) => {
    const imgs = el.querySelectorAll('img');
    const cdnImgs = [...imgs].filter(img =>
      /alicdn|imgextra|tbcdn/.test(img.src) && img.getBoundingClientRect().width > 8
    );
    log(`  [${i}] cls=${(el.className || '').slice(0, 60)}  img=${imgs.length}(cdn=${cdnImgs.length})  text=${(el.innerText || '').replace(/\s+/g, ' ').slice(0, 80)}`);
  });

  // ════════════════════════════════════════════════════════════
  log('');
  log(SEP);
  log('【第 2 步】找主图区空槽（sections[2]），并点击「上传图片」');
  log(SEP);

  const main = sections[2];
  if (!main) {
    log('✗ 找不到 sections[2]，请确认页面已加载且 #ai-category-page-main-do-not-add-padding 存在');
    return;
  }

  // 找包含「上传图片」文字的可点击元素
  const slotNode = [...main.querySelectorAll('*')].find(el =>
    (el.textContent || '').trim().includes('上传图片') &&
    el.getBoundingClientRect().width > 20
  );

  if (!slotNode) {
    log('✗ 未在 sections[2] 找到「上传图片」文字节点');
    log('  → 列出 sections[2] 所有可见子节点：');
    [...main.querySelectorAll('*')].filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 20 && r.height > 20;
    }).slice(0, 20).forEach(el => {
      log(`     ${el.tagName}  cls=${(el.className||'').slice(0,60)}  text=${(el.textContent||'').trim().slice(0,40)}`);
    });
    return;
  }

  const target = slotNode.closest('button,[role="button"],[class*="upload"],[class*="slot"],[class*="imageWrap"]') || slotNode;
  log(`✓ 找到空槽：${target.tagName}  cls=${(target.className||'').slice(0,80)}`);
  target.scrollIntoView({ block: 'center' });
  target.click();
  log('✓ 已点击');

  // ════════════════════════════════════════════════════════════
  log('');
  log(SEP);
  log('【第 3 步】等 2 秒，探测上传面板 & 点击「从图片空间添加」');
  log(SEP);
  await sleep(2000);

  const overlays = probeOverlays();
  log(`浮层/面板数量: ${overlays.length}`);
  overlays.forEach(o => {
    log(`  ${o.tag}  cls=${o.cls.slice(0, 80)}  ${o.w}x${o.h}  top=${o.top}  text=${o.text.slice(0, 60)}`);
  });

  // 找「从图片空间添加」按钮（可能在展开的上传面板里）
  const spaceBtn = document.querySelector('[class*="mediaSpaceBtn"]')
    || [...document.querySelectorAll('button')].find(b =>
        (b.innerText || '').includes('图片空间') && b.getBoundingClientRect().width > 0
       );

  if (!spaceBtn) {
    log('✗ 未找到「从图片空间添加」按钮，请确认点击空槽后展开了上传面板');
    log('  → 上方浮层列表即为当前状态，请复制给 AI');
    return;
  }

  log(`✓ 找到按钮：cls=${(spaceBtn.className || '').slice(0, 80)}  text="${(spaceBtn.innerText || '').trim()}"`);
  spaceBtn.scrollIntoView({ block: 'center' });
  spaceBtn.click();
  log('✓ 已点击「从图片空间添加」');

  // ════════════════════════════════════════════════════════════
  log('');
  log(SEP);
  log('【第 4 步】等 3 秒，探测图片空间弹框结构');
  log(SEP);
  await sleep(3000);

  let popupInfo = probePopup();

  if (!popupInfo.found) {
    log('  未找到弹框，再等 3 秒…');
    await sleep(3000);
    popupInfo = probePopup();
  }

  if (popupInfo.found) {
    const p = popupInfo.popup;
    log(`✓ 弹框: ${p.tag}  cls=${p.cls}  ${p.w}x${p.h}`);
    log(`  img 数量(过滤后): ${popupInfo.imgCount}`);
    popupInfo.imgs.slice(0, 5).forEach((img, i) => log(`    [img${i}] ${img.w}x${img.h}  ${img.src.slice(0, 80)}`));
    log(`  uspImgs 数量: ${popupInfo.uspImgCount}`);
    popupInfo.uspImgs.slice(0, 5).forEach((img, i) => log(`    [usp${i}] ${img.w}  cls=${img.cls}  ${img.src.slice(0, 80)}`));
    log(`  iframe 数量: ${popupInfo.iframeCount}`);
    popupInfo.iframes.forEach((f, i) => log(`    [iframe${i}] ${f.w}x${f.h}  ${f.src.slice(0, 80)}`));
    log(`  按钮(${popupInfo.btns.length}):`);
    popupInfo.btns.forEach(b => log(`    [btn] "${b.text}"  disabled=${b.disabled}  cls=${b.cls.slice(0, 50)}`));

    // 额外：探测弹框内所有可见的带文字节点（用于定位「确认」等操作按钮）
    const popup = document.querySelector('[class*="sell-images-upload-media-dialog"]')
      || document.querySelector('[class*="uspimages-popup"]')
      || document.querySelector('[class*="media-popup"]')
      || [...document.querySelectorAll('.next-dialog')].find(el => {
           const r = el.getBoundingClientRect(); return r.width > 400 && r.height > 200;
         });
    if (popup) {
      const clickables = [...popup.querySelectorAll('button,[role="button"],[class*="confirm"],[class*="submit"],[class*="ok"]')]
        .filter(el => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && (el.innerText || '').trim();
        })
        .map(el => `${el.tagName} "${(el.innerText||'').trim().slice(0,30)}" cls=${(el.className||'').slice(0,60)}`);
      log(`  可点击元素(${clickables.length}):`);
      clickables.forEach(s => log(`    ${s}`));
    }
  } else {
    log('✗ 仍未找到弹框，当前所有浮层：');
    probeOverlays().forEach(o => {
      log(`  ${o.tag}  cls=${o.cls.slice(0, 100)}  ${o.w}x${o.h}  text=${o.text.slice(0, 60)}`);
    });
  }

  log('');
  log(SEP);
  log('测试完成，请把全部控制台输出复制给 AI');
  log(SEP);

})();
