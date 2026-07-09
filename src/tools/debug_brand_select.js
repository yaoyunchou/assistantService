/**
 * 诊断脚本：测试品牌下拉框选中
 *
 * 前置条件：已在类目确认页（有「品牌」下拉框）
 * 粘贴到控制台执行，把输出复制给 AI
 */

(async () => {

  const SEP = '='.repeat(60);
  const log = (...args) => console.log(...args);
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // React 受控 input 设值（绕过合成事件限制）
  function setReactInputValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // ── 1. 找品牌 trigger ───────────────────────────────────
  log(SEP);
  log('【第 1 步】打开品牌下拉框');
  log(SEP);

  const brandField = document.querySelector('#sell-field-p-20000');
  const trigger = brandField?.querySelector('.next-select-trigger');
  if (!trigger) { log('✗ 未找到品牌 trigger'); return; }

  trigger.scrollIntoView({ block: 'center' });
  trigger.click();
  await sleep(600);

  const overlay = document.querySelector('.next-overlay-wrapper.opened');
  if (!overlay) { log('✗ overlay 未出现'); return; }
  log('✓ overlay 出现');

  // ── 2. 搜索「无品牌」─────────────────────────────────────
  log('');
  log(SEP);
  log('【第 2 步】搜索「无品牌」');
  log(SEP);

  const input = overlay.querySelector('input');
  if (!input) { log('✗ 没有搜索框，跳过搜索'); }
  else {
    setReactInputValue(input, '无品牌');
    await sleep(800);
    log('✓ 已设置搜索词「无品牌」');
  }

  // ── 3. 列出当前所有 options-item ─────────────────────────
  log('');
  log(SEP);
  log('【第 3 步】列出选项，尝试各种点击方式');
  log(SEP);

  const items = [...overlay.querySelectorAll('[class*="options-item"]')]
    .filter(el => el.getBoundingClientRect().width > 0);

  log(`options-item 数量: ${items.length}`);
  items.forEach((el, i) => {
    const r = el.getBoundingClientRect();
    log(`  [${i}] "${el.innerText.trim()}"  cls="${el.className}"  ${Math.round(r.width)}x${Math.round(r.height)}  pos=${Math.round(r.left)},${Math.round(r.top)}`);
  });

  // 找「无品牌/无注册商标」
  const target = items.find(el => el.innerText.includes('无品牌/无注册商标'))
               || items.find(el => el.innerText.includes('无品牌'));

  if (!target) { log('✗ 未找到目标选项'); return; }
  log(`\n目标选项: "${target.innerText.trim()}"  cls="${target.className}"`);

  // ── 4. 尝试点击方式 A：直接 click() ─────────────────────
  log('');
  log('▶ 方式 A：target.click()');
  target.click();
  await sleep(500);
  const valA = brandField.querySelector('.next-select-values')?.innerText?.trim() || '';
  log(`  品牌框当前值: "${valA}"`);
  if (valA && !valA.includes('请选择')) { log('  ✓ 方式 A 成功！'); return; }
  log('  ✗ 方式 A 未选中，继续尝试');

  // ── 5. 尝试点击方式 B：mousedown + mouseup + click ────────
  log('');
  log('▶ 方式 B：mousedown → mouseup → click 事件序列');
  const events = ['mousedown', 'mouseup', 'click'];
  events.forEach(type => {
    target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
  });
  await sleep(500);
  const valB = brandField.querySelector('.next-select-values')?.innerText?.trim() || '';
  log(`  品牌框当前值: "${valB}"`);
  if (valB && !valB.includes('请选择')) { log('  ✓ 方式 B 成功！'); return; }
  log('  ✗ 方式 B 未选中，继续尝试');

  // ── 6. 尝试点击方式 C：用坐标 getBoundingClientRect 点击 ──
  log('');
  log('▶ 方式 C：elementFromPoint 验证 + 坐标点击');
  const r = target.getBoundingClientRect();
  const cx = Math.round(r.left + r.width / 2);
  const cy = Math.round(r.top + r.height / 2);
  const elAtPoint = document.elementFromPoint(cx, cy);
  log(`  中心坐标 (${cx}, ${cy})  elementFromPoint: ${elAtPoint?.tagName} cls="${(elAtPoint?.className||'').slice(0,60)}"`);

  // 尝试点 elementFromPoint 返回的元素
  if (elAtPoint && elAtPoint !== target) {
    elAtPoint.click();
    await sleep(500);
    const valC = brandField.querySelector('.next-select-values')?.innerText?.trim() || '';
    log(`  品牌框当前值: "${valC}"`);
    if (valC && !valC.includes('请选择')) { log('  ✓ 方式 C 成功！'); return; }
    log('  ✗ 方式 C 未选中');
  }

  // ── 7. 最终状态 ──────────────────────────────────────────
  log('');
  log(SEP);
  log('所有方式均未能选中，请把上方输出复制给 AI');
  log(SEP);

  // 额外信息：overlay 里所有事件监听情况（通过查 data 属性推断）
  log('overlay 根节点 outerHTML 前 300 字符:');
  log(overlay.outerHTML.slice(0, 300));

})();
