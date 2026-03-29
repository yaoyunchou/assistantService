/**
 * 拼多多订单列表：按订单号查询 → 列表存在则点「收货信息」列「查看」→ 若有「查看手机号」则再点 → 返回 手机 + 收货信息
 * 页面：https://mms.pinduoduo.com/orders/list*（推荐使用 ?tab=0）
 *
 * **订单号**：须由外部传入，执行前设置 `window.__PDD_LOOKUP_ORDER_NO = '260329-xxxxxxxx'`（可与本脚本同页、先执行一行再粘贴本文件；MCP 可在 code 前拼接 `window.__PDD_LOOKUP_ORDER_NO='…';`）。
 * **整文件形态**：注释后为自执行 `(async () => { … })();`，**浏览器控制台可直接整段粘贴**（无顶层 `return` 语法错误）。
 * **MCP `page_evaluate` / 扩展「执行脚本」**：仍传入本文件全文（或去掉注释仅传 IIFE）；background 若识别为自执行 async IIFE 则用 `return await …`，与旧版「仅函数体 + return」两种形态均兼容。`timeout` 建议 ≥ 120000。
 * **加载时机**：订单列表为 SPA，筛选区可能在 `domcontentloaded` 之后才挂载；脚本在填单号前会 **轮询等待** 订单号输入框出现（默认最长约 45s），避免「页面未加载完就找不到框」。
 * 结束前会 `console.log('[pdd-order-search-receiver] 返回数据: …')` 打印与返回值一致的 JSON。
 */
(async () => {
  const ORDER = String(
    (typeof window !== 'undefined' && window.__PDD_LOOKUP_ORDER_NO) || ''
  ).trim();
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /** 控制台打印与 MCP/扩展返回值一致的对象，便于本地确认 */
  function printReturn(payload) {
    try {
      console.log('[pdd-order-search-receiver] 返回数据:\n' + JSON.stringify(payload, null, 2));
    } catch (e) {
      console.log('[pdd-order-search-receiver] 返回数据:', payload);
    }
    return payload;
  }

  if (!ORDER) {
    return printReturn({
      result: null,
      error:
        '未指定订单号：请先设置 window.__PDD_LOOKUP_ORDER_NO = "260329-xxxxxxxx" 再执行（可与脚本同注入：在脚本前加一段赋值即可）',
      log,
    });
  }

  function setInputValueForReact(el, val) {
    if (!el) return;
    const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
    if (proto && proto.set) proto.set.call(el, val);
    else el.value = val;
    try {
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: val }));
    } catch (e) {
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  /** 订单表格根节点，用于把筛选区与页面其它搜索框隔开 */
  function getOrderTableEl() {
    return document.querySelector('[data-testid="beast-core-table"]');
  }

  function listFilterInputs() {
    return Array.from(
      document.querySelectorAll('input[type="text"], input:not([type]), input.semi-input')
    ).filter((el) => !el.disabled && el.offsetParent !== null);
  }

  /**
   * 只认「订单列表筛选区」内的输入框：在表格上方，或 placeholder/文案命中；
   * 不再 fallback 全页第一个 text input（常会误判顶部全局搜索，表现为「没搜订单」）。
   */
  function findOrderSearchInput() {
    const table = getOrderTableEl();
    const tableTop = table ? table.getBoundingClientRect().top : null;
    const inputs = listFilterInputs();

    const aboveTable = (el) =>
      tableTop != null && el.getBoundingClientRect().bottom <= tableTop + 80;

    for (const el of inputs) {
      const ph = (el.getAttribute('placeholder') || '').trim();
      /** 顶栏「搜索功能/订单/商品/课程…」含「订单」但非订单列表筛选框，必须排除 */
      if (/搜索功能\s*[\/／]/.test(ph) && /商品|课程|规则|帮助/.test(ph)) continue;
      if (/订单编号|请输入.*订单|订单号|售后单号|运单号|快递单号/i.test(ph)) {
        if (tableTop == null || aboveTable(el)) return { el, via: 'placeholder:' + ph.slice(0, 40) };
      }
    }
    for (const el of inputs) {
      const ph = (el.getAttribute('placeholder') || '').trim();
      if (/搜索功能\s*[\/／]/.test(ph) && /商品|课程/.test(ph)) continue;
      if (/订单|编号|单号/.test(ph) && ph.length <= 24) {
        if (tableTop == null || aboveTable(el)) return { el, via: 'placeholder(short):' + ph };
      }
    }

    for (const lab of document.querySelectorAll('span, label')) {
      const t = (lab.textContent || '').trim();
      if ((/订单编号|订单号/.test(t) && t.length < 24) || t === '订单编号') {
        let n = lab.parentElement;
        for (let d = 0; d < 8 && n; d++) {
          const inp = n.querySelector('input[type="text"], input:not([type]), input.semi-input');
          if (inp && !inp.disabled) {
            if (tableTop == null || aboveTable(inp)) return { el: inp, via: 'label:' + t.slice(0, 12) };
          }
          n = n.parentElement;
        }
      }
    }

    if (tableTop != null) {
      const candidates = inputs.filter(aboveTable);
      if (candidates.length === 1) return { el: candidates[0], via: 'above-table:only' };
      for (const el of candidates) {
        const ph = (el.getAttribute('placeholder') || '').trim();
        if (/搜索功能\s*[\/／]/.test(ph) && /商品|课程|规则|帮助/.test(ph)) continue;
        if (ph && /单|号|订单|售后|商品|收件人|手机号/i.test(ph))
          return { el, via: 'above-table:hint:' + ph.slice(0, 20) };
      }
    }

    return null;
  }

  /** 多个「查询」时选离搜索框最近的一个，避免点到别的模块 */
  function findQueryButtonNearInput(inputEl) {
    const ir = inputEl.getBoundingClientRect();
    const cands = Array.from(document.querySelectorAll('button, [role="button"]')).filter((b) => {
      const t = (b.textContent || '').replace(/\s+/g, '').trim();
      return t === '查询' || t === '搜索';
    });
    if (!cands.length) return null;
    let best = cands[0];
    let bestScore = Infinity;
    for (const b of cands) {
      const r = b.getBoundingClientRect();
      const dx = Math.min(Math.abs(r.left - ir.right), Math.abs(r.left - ir.left));
      const dy = Math.abs(r.top + r.height / 2 - (ir.top + ir.height / 2));
      const score = dx + dy * 2;
      if (score < bestScore) {
        bestScore = score;
        best = b;
      }
    }
    return best.closest('button') || best;
  }

  function pairOrderRowsFromTbody(body, minDataCells) {
    const allTr = Array.from(body.querySelectorAll('tr'));
    const rows = [];
    let currentOrderNo = null;
    for (const tr of allTr) {
      const tds = tr.querySelectorAll('td');
      const cellCount = tds.length;
      const text = (tr.textContent || '').trim();
      if (cellCount <= 2 && /订单编号/.test(text)) {
        const m = text.match(/订单编号[：:]?\s*([0-9\-]+)/) || text.match(/([0-9]{6}-[0-9]{10,})/);
        currentOrderNo = m ? m[1].trim() : null;
        continue;
      }
      if (cellCount >= minDataCells && currentOrderNo) {
        rows.push({ orderNo: currentOrderNo, dataTr: tr });
      }
    }
    return rows;
  }

  function pairAllOrderRows() {
    const tbodies = Array.from(document.querySelectorAll('[data-testid="beast-core-table-middle-tbody"]'));
    const rows = [];
    for (const body of tbodies) {
      pairOrderRowsFromTbody(body, 5).forEach((r) => rows.push(r));
    }
    return rows;
  }

  const addrColumnIndex = 5;

  function getReceiverCell(dataTr) {
    const cells = dataTr.querySelectorAll('td');
    return cells[addrColumnIndex] || null;
  }

  /** 旧版「查看」；新版收货列为「复制完整信息」「隐私号」等 */
  function findReceiverActionLink(dataTr) {
    const cells = dataTr.querySelectorAll('td');
    for (let c = 0; c < cells.length; c++) {
      for (const a of cells[c].querySelectorAll('a')) {
        const t = (a.textContent || '').trim();
        if (/^查看$/.test(t)) return { el: a, kind: '查看' };
      }
    }
    const ac = getReceiverCell(dataTr);
    if (!ac) return null;
    for (const a of ac.querySelectorAll('a')) {
      const t = (a.textContent || '').trim();
      if (/复制完整信息/.test(t)) return { el: a, kind: '复制完整信息' };
    }
    for (const a of ac.querySelectorAll('a')) {
      const t = (a.textContent || '').trim();
      if (/^隐私号$/.test(t) || t === '隐私号') return { el: a, kind: '隐私号' };
    }
    return null;
  }

  function stripTableNoise(s) {
    return String(s || '')
      .replace(/\.beast-core-ellipsis-\d+\s*\{[^}]*\}/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function normOrder(s) {
    return String(s || '').replace(/\s/g, '');
  }

  /**
   * 提取电话：11 位手机、带星号脱敏号、隐私号、国内座机（如 021-53395199 / 010-12345678）。
   */
  function extractPhone(text) {
    if (!text) return '';
    const stripSpaces = (s) => String(s).replace(/\s/g, '');

    const labeled = text.match(
      /(?:手机|联系电话|收货电话|固定电话|座机)[：:\s]*((?:0\d{2,3}[-－\s]*\d{7,8})|(?:1[3-9]\d{9})|(?:[1*][\d\s*\-]{10,18}))/
    );
    if (labeled && labeled[1]) return stripSpaces(labeled[1]);

    const mobile = text.match(/(1[3-9]\d{9})/);
    if (mobile) return mobile[1];

    const land = text.match(/(?:^|[^\d])(0\d{2,3}[-－\s]*\d{7,8})(?!\d)/);
    if (land) return stripSpaces(land[1]);

    const priv = text.match(/隐私号[：:\s]*([0-9\-*]{10,20})/);
    if (priv) return stripSpaces(priv[1]);

    return '';
  }

  function cleanReceiverBlock(s) {
    return String(s || '')
      .replace(/复制完整信息/g, '')
      .replace(/\s*隐私号\s*/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // --- 1) 填单号并查询（必须用订单列表筛选区内的框；先等 SPA 把筛选区画出来）---
  const WAIT_INPUT_MAX_MS = 45000;
  const WAIT_INPUT_STEP_MS = 500;
  let foundInp = null;
  let waitedMs = 0;
  log.push('开始等待订单筛选区/订单号输入框（最长 ' + WAIT_INPUT_MAX_MS + 'ms）');
  while (waitedMs < WAIT_INPUT_MAX_MS) {
    foundInp = findOrderSearchInput();
    if (foundInp) {
      if (waitedMs > 0) {
        log.push('筛选区就绪，已等待约 ' + waitedMs + 'ms');
      }
      break;
    }
    await sleep(WAIT_INPUT_STEP_MS);
    waitedMs += WAIT_INPUT_STEP_MS;
  }
  if (!foundInp) {
    const hasTable = !!getOrderTableEl();
    return printReturn({
      result: null,
      error:
        '未定位到订单列表筛选区的订单号输入框，已等待约 ' +
        WAIT_INPUT_MAX_MS +
        'ms（表格节点: ' +
        (hasTable ? '已出现' : '未出现') +
        '）。可能原因：① 页面仍在加载或网络慢；② 筛选区未展开，输入框被隐藏；③ 改版后 placeholder/标签与脚本规则不一致。',
      log,
    });
  }
  const inp = foundInp.el;
  log.push('搜索框定位: ' + foundInp.via);
  inp.focus();
  setInputValueForReact(inp, ORDER);
  log.push('已在订单筛选框填入单号: ' + ORDER);
  await sleep(200);
  const qbtn = findQueryButtonNearInput(inp);
  if (qbtn) {
    qbtn.click();
    log.push('已点击订单筛选附近的「查询」');
  } else {
    inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
    log.push('未找到「查询」按钮，已对筛选框尝试回车');
  }
  await sleep(2500);

  // --- 2) 是否在列表中 ---
  const paired = pairAllOrderRows();
  const want = normOrder(ORDER);
  const target = paired.find((r) => normOrder(r.orderNo) === want);
  if (!target) {
    return printReturn({
      result: null,
      orderNo: ORDER,
      reason: '查询后列表中无该行订单',
      listRowCount: paired.length,
      log,
    });
  }
  log.push('列表中已匹配订单行');

  // --- 3) 收货：行内直读 或 查看/复制完整信息/隐私号 → 弹窗「查看手机号」---
  const addrCell = getReceiverCell(target.dataTr);
  let detailText = '';
  if (addrCell) {
    const rowTxt = stripTableNoise(addrCell.innerText || '');
    const earlyPhone = extractPhone(rowTxt);
    if (earlyPhone && /(省|市|区|县|自治区)/.test(rowTxt)) {
      detailText = rowTxt;
      log.push('收货列行内已含地址与号码，跳过点击');
    }
  }

  if (!detailText) {
    const action = findReceiverActionLink(target.dataTr);
    if (!action) {
      return printReturn({
        result: null,
        orderNo: ORDER,
        error: '该行收货列无可点击项（查看 / 复制完整信息 / 隐私号）',
        log,
      });
    }
    action.el.click();
    log.push('已点击「' + action.kind + '」');
    await sleep(700);

    let viewPhoneBtn = document.evaluate(
      "//a[contains(text(),'查看手机号')] | //button[contains(text(),'查看手机号')] | //span[contains(text(),'查看手机号')]",
      document.body,
      null,
      XPathResult.FIRST_ORDERED_NODE_TYPE,
      null
    ).singleNodeValue;
    if (!viewPhoneBtn) {
      viewPhoneBtn = Array.from(document.querySelectorAll('a, button, [role="button"], span')).find((el) =>
        /查看手机号/.test(el.textContent || '')
      );
    }
    if (viewPhoneBtn) {
      viewPhoneBtn.click();
      log.push('已点击「查看手机号」');
      await sleep(500);
    } else {
      log.push('未出现「查看手机号」，读弹窗或收货列');
    }

    const modal =
      document.querySelector('[role="dialog"] .semi-modal-content') ||
      document.querySelector('[class*="drawer"] .semi-drawer-content') ||
      document.querySelector('[role="dialog"]');
    detailText = (modal && modal.innerText ? modal.innerText : '').trim();
    if (!detailText && addrCell) {
      detailText = stripTableNoise(addrCell.innerText || '');
    }
    if (!detailText) {
      const hit = (document.body.innerText || '').match(/收货人[：:][\s\S]{0,1200}/);
      detailText = hit ? hit[0] : (document.body.innerText || '').slice(0, 2500);
    }
  }

  const 手机 = extractPhone(detailText);
  const 收货信息 = cleanReceiverBlock(detailText).slice(0, 2500);

  const closeBtn = document.querySelector(
    '[role="dialog"] [aria-label="关闭"], [role="dialog"] .semi-modal-close, .semi-drawer-close'
  );
  if (closeBtn) closeBtn.click();

  return printReturn({
    手机,
    收货信息,
    orderNo: ORDER,
    log,
  });
})();
