/**
 * 诊断脚本：验证类目选择页交互
 *
 * 前置条件：已进入类目确认页（有「商品类目」「品牌」「确认，下一步」）
 * 粘贴到控制台执行，把输出复制给 AI
 */

(async () => {

  const SEP = '='.repeat(60);
  const log = (...args) => console.log(...args);
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ── 第 1 步：推荐类目列表 ─────────────────────────────────
  log(SEP);
  log('【第 1 步】推荐类目列表');
  log(SEP);

  const pathNames = [...document.querySelectorAll('.path-name')];
  log(`推荐类目数量: ${pathNames.length}`);
  pathNames.forEach((el, i) => {
    const r = el.getBoundingClientRect();
    log(`  [${i}] cls="${el.className}"  ${Math.round(r.width)}x${Math.round(r.height)}  text="${el.innerText.trim()}"`);
  });

  // ── 第 2 步：品牌下拉区域 ─────────────────────────────────
  log('');
  log(SEP);
  log('【第 2 步】品牌属性区域');
  log(SEP);

  const brandField = document.querySelector('#sell-field-p-20000');
  if (!brandField) {
    log('✗ 未找到 #sell-field-p-20000');
  } else {
    const trigger = brandField.querySelector('.next-select-trigger');
    const r = trigger ? trigger.getBoundingClientRect() : null;
    log(`  next-select-trigger: ${trigger ? `${Math.round(r.width)}x${Math.round(r.height)}  pos=${Math.round(r.left)},${Math.round(r.top)}` : '未找到'}`);
    log(`  当前值: "${(brandField.querySelector('.next-select-values')?.innerText || '').trim()}"`);
  }

  // ── 第 3 步：点第一个推荐类目 ────────────────────────────
  log('');
  log(SEP);
  log('【第 3 步】点击第一个推荐类目');
  log(SEP);

  const firstPath = pathNames[0];
  if (!firstPath) {
    log('✗ 无推荐类目可点');
  } else {
    firstPath.scrollIntoView({ block: 'center' });
    firstPath.click();
    log(`✓ 已点击: "${firstPath.innerText.trim()}"`);
    await sleep(800);
  }

  // ── 第 4 步：点击品牌下拉，看 overlay ──────────────────────
  log('');
  log(SEP);
  log('【第 4 步】点开品牌下拉框');
  log(SEP);

  const trigger2 = document.querySelector('#sell-field-p-20000 .next-select-trigger');
  if (!trigger2) {
    log('✗ 品牌 trigger 未找到');
  } else {
    trigger2.scrollIntoView({ block: 'center' });
    trigger2.click();
    log('✓ 已点击品牌 trigger');
    await sleep(600);

    const overlay = document.querySelector('.next-overlay-wrapper.opened');
    if (!overlay) {
      log('✗ 未出现 .next-overlay-wrapper.opened');
    } else {
      const r = overlay.getBoundingClientRect();
      log(`✓ overlay 出现  ${Math.round(r.width)}x${Math.round(r.height)}`);

      const input = overlay.querySelector('input');
      log(`  搜索框: ${input ? '有' : '无'}`);

      const items = [...overlay.querySelectorAll('li,div[role="option"],[class*="option"],[class*="item"]')]
        .filter(el => {
          const r2 = el.getBoundingClientRect();
          return r2.width > 0 && (el.innerText || '').trim();
        })
        .slice(0, 10);
      log(`  选项数量（前10）: ${items.length}`);
      items.forEach((el, i) => log(`    [${i}] "${(el.innerText || '').trim().slice(0, 40)}"  cls=${(el.className || '').slice(0, 60)}`));

      // 搜索「无品牌」
      if (input) {
        input.focus();
        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(input, '无品牌');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        await sleep(600);

        const items2 = [...overlay.querySelectorAll('li,div[role="option"],[class*="option"],[class*="item"]')]
          .filter(el => {
            const r2 = el.getBoundingClientRect();
            return r2.width > 0 && (el.innerText || '').trim();
          });
        log(`  搜索「无品牌」后选项数: ${items2.length}`);
        items2.slice(0, 5).forEach((el, i) => log(`    [${i}] "${(el.innerText || '').trim().slice(0, 40)}"`));
      }
    }
  }

  // ── 第 5 步：「确认，下一步」按钮 ────────────────────────
  log('');
  log(SEP);
  log('【第 5 步】确认按钮状态');
  log(SEP);

  // 先按 Escape 关掉下拉
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await sleep(300);

  const confirmBtns = [...document.querySelectorAll('button')].filter(b =>
    (b.innerText || '').includes('确认') && (b.innerText || '').includes('下一步')
  );
  log(`「确认，下一步」按钮数量: ${confirmBtns.length}`);
  confirmBtns.forEach(b => {
    const r = b.getBoundingClientRect();
    log(`  "${b.innerText.trim()}"  disabled=${b.disabled}  cls=${b.className.slice(0, 80)}  ${Math.round(r.width)}x${Math.round(r.height)}`);
  });

  log('');
  log(SEP);
  log('测试完成，请把全部输出复制给 AI');
  log(SEP);

})();
