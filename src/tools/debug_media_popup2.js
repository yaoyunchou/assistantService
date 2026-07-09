/**
 * 诊断脚本 2：探测图片空间弹框内部（iframe + 确认按钮）
 *
 * 前置条件：图片空间弹框已打开（运行 debug_media_popup.js 后不要关弹框）
 * 直接在控制台粘贴执行，把输出复制给 AI
 */

(async () => {

  const SEP = '='.repeat(60);
  const log = (...args) => console.log(...args);
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── 找弹框根节点 ──────────────────────────────────────────
  const popup =
    document.querySelector('[class*="sell-component-image-v2-media-popup"]') ||
    document.querySelector('[class*="media-popup"]') ||
    [...document.querySelectorAll('.next-overlay-inner')].find(el => {
      const r = el.getBoundingClientRect();
      return r.width > 400 && r.height > 200;
    });

  if (!popup) {
    log('✗ 未找到弹框，请先运行 debug_media_popup.js 打开弹框，不要关闭它');
    return;
  }

  const pr = popup.getBoundingClientRect();
  log(SEP);
  log('【弹框信息】');
  log(SEP);
  log(`tag=${popup.tagName}  cls=${(popup.className||'').slice(0,120)}`);
  log(`位置: ${Math.round(pr.left)},${Math.round(pr.top)}  大小: ${Math.round(pr.width)}x${Math.round(pr.height)}`);

  // 把弹框滚动到视口内
  popup.scrollIntoView({ block: 'center' });
  await sleep(500);

  // ── 弹框内 iframe ─────────────────────────────────────────
  log('');
  log(SEP);
  log('【iframe 信息】');
  log(SEP);
  const iframes = [...popup.querySelectorAll('iframe')];
  log(`iframe 数量: ${iframes.length}`);
  iframes.forEach((f, i) => {
    const r = f.getBoundingClientRect();
    log(`  [${i}] ${Math.round(r.width)}x${Math.round(r.height)}  src=${f.src.slice(0, 120)}`);
    // 尝试访问 iframe 内容（同源才有效）
    try {
      const doc = f.contentDocument || f.contentWindow?.document;
      if (doc) {
        const imgs = [...doc.querySelectorAll('img')].filter(img => img.getBoundingClientRect().width > 10);
        const btns = [...doc.querySelectorAll('button,[role="button"]')].filter(el => el.getBoundingClientRect().width > 0);
        log(`    → iframe 可访问！img数量=${imgs.length}  btn数量=${btns.length}`);
        imgs.slice(0, 5).forEach((img, j) => log(`      [img${j}] ${Math.round(img.getBoundingClientRect().width)}x${Math.round(img.getBoundingClientRect().height)}  src=${img.src.slice(0,80)}`));
        btns.forEach(b => log(`      [btn] "${(b.innerText||'').trim().slice(0,40)}"  cls=${(b.className||'').slice(0,60)}`));
      } else {
        log(`    → iframe 不可访问（contentDocument 为空）`);
      }
    } catch (e) {
      log(`    → iframe 跨域，无法访问内容: ${e.message}`);
    }
  });

  // ── 弹框外层的按钮（footer / toolbar）────────────────────
  log('');
  log(SEP);
  log('【弹框外层按钮（非 iframe 内）】');
  log(SEP);

  // 向上找到整个 dialog/overlay 容器（可能比 popup 更大）
  const dialogRoot = popup.closest('[class*="next-dialog"],.next-overlay,.next-dialog-wrapper') || popup.parentElement;
  const allBtns = [...(dialogRoot || popup).querySelectorAll('button,[role="button"]')]
    .filter(el => {
      const r = el.getBoundingClientRect();
      // 排除 iframe 内的（iframe 内元素在父 frame 中 getBoundingClientRect 会返回 0）
      return r.width > 0 && r.height > 0;
    });
  log(`可见按钮数量: ${allBtns.length}`);
  allBtns.forEach(b => {
    const r = b.getBoundingClientRect();
    log(`  "${(b.innerText||'').trim().slice(0,40)}"  cls=${(b.className||'').slice(0,80)}  pos=${Math.round(r.left)},${Math.round(r.top)}  disabled=${b.disabled}`);
  });

  // ── 弹框外层所有文字节点（找「确认」「插入」等操作区）────
  log('');
  log(SEP);
  log('【弹框内可见文字节点（找操作区）】');
  log(SEP);
  const textNodes = [...(dialogRoot || popup).querySelectorAll('*')]
    .filter(el => {
      if (el.tagName === 'IFRAME' || el.closest('iframe')) return false;
      const r = el.getBoundingClientRect();
      const txt = (el.childNodes[0]?.nodeType === 3 ? el.childNodes[0].textContent : el.innerText || '').trim();
      return r.width > 0 && r.height > 0 && txt.length > 0 && txt.length < 20 && el.children.length <= 2;
    })
    .slice(0, 30);
  textNodes.forEach(el => {
    const r = el.getBoundingClientRect();
    log(`  ${el.tagName}  "${(el.innerText||'').trim()}"  cls=${(el.className||'').slice(0,60)}  pos=${Math.round(r.left)},${Math.round(r.top)}`);
  });

  log('');
  log(SEP);
  log('测试完成，请把全部输出复制给 AI');
  log(SEP);

})();
