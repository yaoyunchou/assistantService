/**
 * 拼多多官方 ERP —— 已发货订单筛选 + 数据抓取
 * 页面：https://mms.pinduoduo.com/erp/order/delivered
 *
 * Python 入口：spider.pinduoduo.erp_audit.fetch_delivered_today_printed_rows
 * HTTP：POST /api/pinduoduo/erp-delivered/today-printed-query（浏览器池执行，结束后飞书 Webhook 摘要）
 *
 * 流程：
 *   1. 等待筛选表单加载
 *   2. 「时间类型」选择「发货时间」
 *   3. 「时间范围」点快捷「今天」按钮（今日 00:00~23:59）
 *   4. 「打印状态」选择「已打印快递单」（可通过 FILTER_PRINT_STATUS 覆盖）
 *   5. 点击「查询」
 *   6. 等待结果加载后，支持自动滚动抓取所有订单行
 *   7. 返回 rows[]（平台订单号、商品规格、快递信息、发货时间、打印状态等）
 *
 * 可选配置（window 上提前设置）：
 *   - `window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS`：打印状态过滤
 *       默认「已打印快递单」；填 `__ALL__` 或 `*` 表示不筛选（全部）
 *       （误传空串 / null 仍按默认筛「已打印快递单」）
 *   - `window.__PDD_ERP_DELIVERED_TIME_TYPE`：时间类型，默认 '发货时间'
 *       可选 '付款时间' | '审核时间'
 *   - `window.__PDD_ERP_DELIVERED_DATE_SHORTCUT`：快捷日期选项，默认 '今天'
 *       可选 '昨天' | '近7天' | '近30天' 等
 *   - `window.__PDD_ERP_DELIVERED_AUTO_SCROLL`：是否滚动加载全部，默认 true
 *   - `window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS`：每步等待 ms，默认 500
 *   - `window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS`：最大滚动步数，默认 200
 *
 * 返回值字段（rows[]）：
 *   orderNo      平台订单号 (td[11])
 *   erpOrderNo   系统订单号 (td[25])
 *   goods[]      商品规格列表 { imgSrc(原图URL), title, spec, qty }
 *   imgUrl       第一件商品原图 URL（可直接在浏览器中打开查看）
 *   express      快递公司+单号 (td[7])
 *   shippingTime 发货时间 (td[12])
 *   printStatus  打印状态 (td[24])
 *   shopName     店铺名称 (td[14] 第一行)
 *   actualAmount 实收金额，如 ¥50.3 (td[14] 第二行)
 */
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const log = [];

  /* ─── 配置（与 Python 注入配合；过滤 Swagger 等误传的类型占位符如 "string"） ─── */
  const DEFAULT_PRINT_STATUS = '已打印快递单';
  const DEFAULT_TIME_TYPE = '发货时间';
  const DEFAULT_DATE_SHORTCUT = '今天';
  /** OpenAPI / 错误客户端偶发把 schema 类型名当成字段值传入 */
  const SCHEMA_PLACEHOLDER = new Set(['string', 'number', 'integer', 'boolean', 'object', 'array']);

  function normOpt(v) {
    if (v === undefined || v === null) return undefined;
    const s = String(v).trim();
    if (!s || SCHEMA_PLACEHOLDER.has(s)) return undefined;
    return s;
  }

  function resolvePrintStatus() {
    const w = window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS;
    if (w === undefined || w === null) return DEFAULT_PRINT_STATUS;
    if (w === '__ALL__' || w === '*') return '';
    if (w === '') return DEFAULT_PRINT_STATUS;
    const p = normOpt(w);
    return p !== undefined ? p : DEFAULT_PRINT_STATUS;
  }
  const printStatus = resolvePrintStatus();

  const timeType = normOpt(window.__PDD_ERP_DELIVERED_TIME_TYPE) || DEFAULT_TIME_TYPE;
  const dateShortcut = normOpt(window.__PDD_ERP_DELIVERED_DATE_SHORTCUT) || DEFAULT_DATE_SHORTCUT;
  const autoScroll = window.__PDD_ERP_DELIVERED_AUTO_SCROLL !== false;
  const pauseMs = Number(window.__PDD_ERP_DELIVERED_SCROLL_PAUSE_MS) || 500;
  const maxSteps = Number(window.__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS) || 200;

  /* ─── 工具 ─── */
  function stripImgQuery(url) {
    if (!url || url.startsWith('data:')) return url;
    return url.replace(/[?#].*$/, '');
  }

  /** 打开 beast-core-select 并选中指定文本的选项 */
  async function selectOption(formItemId, optionText) {
    const container = document.querySelector(`#${formItemId} [data-testid="beast-core-select"]`);
    if (!container) return { ok: false, reason: `#${formItemId} select not found` };
    const header = container.querySelector('[data-testid="beast-core-select-header"]');
    if (!header) return { ok: false, reason: 'no header' };

    // 若已选中则跳过
    const currentInput = container.querySelector('input');
    if (currentInput && currentInput.value === optionText) {
      return { ok: true, skipped: true };
    }

    header.click();
    await sleep(500);

    const option = [...document.querySelectorAll(
      '[class*="dropdown"] li, [class*="Dropdown"] li, [class*="ST_"] li, [class*="popup"] li'
    )].filter((el) => el.offsetParent !== null).find((el) => el.innerText.trim() === optionText);

    if (!option) {
      // 关闭下拉
      header.click();
      await sleep(200);
      return { ok: false, reason: `option "${optionText}" not found` };
    }
    option.click();
    await sleep(300);
    const newVal = container.querySelector('input');
    return { ok: true, newValue: newVal ? newVal.value : '' };
  }

  /** 从 beast-core-select 下拉中找全部选项文本（用于调试） */
  async function getSelectOptions(formItemId) {
    const container = document.querySelector(`#${formItemId} [data-testid="beast-core-select"]`);
    if (!container) return [];
    const header = container.querySelector('[data-testid="beast-core-select-header"]');
    header && header.click();
    await sleep(400);
    const opts = [...document.querySelectorAll(
      '[class*="dropdown"] li, [class*="Dropdown"] li, [class*="ST_"] li, [class*="popup"] li'
    )].filter((el) => el.offsetParent !== null).map((el) => el.innerText.trim());
    header && header.click();
    await sleep(200);
    return opts;
  }

  /** 从商品规格 td 提取商品列表 */
  function extractGoods(td) {
    if (!td) return [];
    let items = [...td.querySelectorAll('.sc-dUYKzm')];
    if (!items.length) {
      items = [...td.querySelectorAll('div[class]')].filter(
        (el) => /\bsc-\w+/.test(el.className) && el.querySelector('img')
      );
      if (items.length > 1) {
        const s = new Set(items);
        items = items.filter((d) => {
          for (let p = d.parentElement; p && p !== td; p = p.parentElement)
            if (s.has(p)) return false;
          return true;
        });
      }
    }
    if (!items.length) {
      const img = td.querySelector('img');
      const text = (td.innerText || '').trim();
      const m = text.match(/\s*[xX×](\d+)\s*$/);
      return [{
        imgSrc: img ? stripImgQuery(img.src || '') : '',
        title: m ? text.slice(0, m.index).trim() : text,
        spec: '',
        qty: m ? parseInt(m[1], 10) : 0,
      }];
    }
    return items.map((item) => {
      const img = item.querySelector('img');
      const imgSrc = stripImgQuery((img && (img.src || img.getAttribute('data-src') || '')) || '');
      let title = '', spec = '', qty = 0;
      const wrapper = item.querySelector('.content-wrapper');
      if (wrapper) {
        const ls = wrapper.querySelector('.light-span');
        if (ls) qty = parseInt(ls.textContent.trim().replace(/^[xX×]/u, ''), 10) || 0;
        const childSpans = [...wrapper.children].filter(
          (el) => el.tagName === 'SPAN' && !el.classList.contains('light-span') && el.textContent.trim()
        );
        if (childSpans.length >= 2) { title = childSpans[0].textContent.trim(); spec = childSpans[childSpans.length - 1].textContent.trim(); }
        else if (childSpans.length === 1) title = childSpans[0].textContent.trim();
      }
      if (!title) {
        const allSpans = [...item.querySelectorAll('span')];
        const qtySpan = allSpans.find((s) => /^[xX×]\d+$/.test(s.textContent.trim()));
        if (qtySpan && !qty) {
          qty = parseInt(qtySpan.textContent.trim().replace(/^[xX×]/u, ''), 10) || 0;
        }
        const leafSpans = allSpans.filter(
          (s) => s !== qtySpan && !s.querySelector('span') && s.textContent.trim()
        );
        if (leafSpans.length >= 2) { title = leafSpans[0].textContent.trim(); spec = leafSpans[leafSpans.length - 1].textContent.trim(); }
        else if (leafSpans.length === 1) title = leafSpans[0].textContent.trim();
        if (!title) {
          const ft = (item.innerText || '').trim();
          const m2 = ft.match(/\s*[xX×](\d+)\s*$/);
          if (m2 && !qty) qty = parseInt(m2[1], 10) || 0;
          title = m2 ? ft.slice(0, m2.index).trim() : ft;
        }
      }
      return { imgSrc, title, spec, qty };
    });
  }

  /** 从 td 获取去除 style 污染的纯文本（通用） */
  function getCellText(td) {
    if (!td) return '';
    const clone = td.cloneNode(true);
    clone.querySelectorAll('style').forEach((s) => s.remove());
    return (clone.innerText || '').trim().replace(/\s+/g, ' ');
  }

  /** 平台订单号 td[11]：优先取 button-link span */
  function getOrderNo(td) {
    if (!td) return '';
    const link = td.querySelector('[data-testid="beast-core-button-link"] span');
    if (link) return link.textContent.trim();
    return getCellText(td).split(/\s/)[0];
  }

  /** 系统订单号 td[25]：取第一个文字段（去掉「查看详情/回收单号」等） */
  function getErpOrderNo(td) {
    if (!td) return '';
    const text = getCellText(td);
    // 格式：「FH260417...查看详情回收单号发起聊天」，取第一个中文操作词前的内容
    return text.replace(/查看详情.*$/, '').replace(/回收单号.*$/, '').trim();
  }

  /** 快递信息 td[7]：全文去掉「物流信息」链接文字 */
  function getExpress(td) {
    if (!td) return '';
    const text = getCellText(td);
    return text.replace(/物流信息\s*$/, '').replace(/\s*物流信息/, '').trim();
  }

  /**
   * 店铺 td[14]：拆出 shopName + actualAmount
   * DOM 结构：两个 [data-testid="beast-core-ellipsis"] 节点
   *   第一个 = 店铺名，第二个 = 实收金额（「实收：¥50.3」）
   */
  function getShop(td) {
    if (!td) return { shopName: '', actualAmount: '' };
    const ellipses = [...td.querySelectorAll('[data-testid="beast-core-ellipsis"]')];
    const texts = ellipses.map((el) => {
      const clone = el.cloneNode(true);
      clone.querySelectorAll('style').forEach((s) => s.remove());
      return (clone.innerText || '').trim();
    });
    const shopName = texts[0] || '';
    // 实收字段格式「实收：¥50.3」，只保留金额部分
    const rawAmount = texts[1] || '';
    const actualAmount = rawAmount.replace(/^实收[：:]\s*/, '').trim() || rawAmount;
    return { shopName, actualAmount };
  }

  /* ─── Step 1: 等待表单加载 ─── */
  const t0 = Date.now();
  while (Date.now() - t0 < 12000) {
    if (document.querySelector('#timeType') && document.querySelector('#timeRange')) break;
    await sleep(400);
  }
  if (!document.querySelector('#timeType')) {
    return { ok: false, error: '筛选表单超时未加载', log };
  }
  log.push('表单已加载');

  /* ─── Step 2: 选择时间类型「发货时间」 ─── */
  const timeTypeResult = await selectOption('timeType', timeType);
  log.push(`时间类型 → ${timeType}：${JSON.stringify(timeTypeResult)}`);
  if (!timeTypeResult.ok) return { ok: false, error: `时间类型选择失败：${timeTypeResult.reason}`, log };

  /* ─── Step 3: 日期范围「今天」快捷按钮 ─── */
  const rangeInput = document.querySelector('#timeRange [data-testid="beast-core-rangePicker-htmlInput"]');
  if (!rangeInput) return { ok: false, error: '未找到日期范围输入框', log };

  rangeInput.click();
  await sleep(500);

  const todayBtn = [...document.querySelectorAll('button')]
    .find((b) => b.offsetParent !== null && b.innerText.trim() === dateShortcut && b.className.includes('RPR_'));
  if (!todayBtn) return { ok: false, error: `未找到「${dateShortcut}」快捷按钮`, log };

  todayBtn.click();
  await sleep(400);
  log.push(`日期范围 → ${rangeInput.value}`);

  /* ─── Step 4: 打印状态 ─── */
  if (printStatus) {
    const printResult = await selectOption('isPrintTracking', printStatus);
    log.push(`打印状态 → ${printStatus}：${JSON.stringify(printResult)}`);
    if (!printResult.ok) return { ok: false, error: `打印状态选择失败：${printResult.reason}`, log };
  } else {
    log.push('打印状态：不筛选（全部）');
  }

  /* ─── Step 5: 点击查询 ─── */
  const queryBtn = [...document.querySelectorAll('button')]
    .find((b) => b.offsetParent !== null && b.textContent.trim() === '查询' && !b.disabled);
  if (!queryBtn) return { ok: false, error: '未找到查询按钮', log };

  queryBtn.click();
  await sleep(2000);
  log.push('已点击查询，等待结果加载');

  /* ─── Step 6: 等待结果 ─── */
  const waitResult = Date.now();
  while (Date.now() - waitResult < 8000) {
    if (document.querySelector('[data-testid="beast-core-table-middle-tbody"]')) break;
    await sleep(300);
  }

  /* ─── Step 7: 抓取数据（支持虚拟滚动） ─── */
  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const TBODY_SEL = '[data-testid="beast-core-table-middle-tbody"]';
  const TABLE_ROOT_SEL = '[data-testid="beast-core-table"]';
  const BODY_WRAP_SEL = '[data-testid="beast-core-table-middle-body"]';

  function collectRows() {
    const result = [];
    [...document.querySelectorAll(TBODY_SEL)].forEach((tbody) => {
      [...tbody.querySelectorAll(ROW_SEL)].forEach((row) => {
        const tds = [...row.querySelectorAll('td')];
        const orderNo = getOrderNo(tds[11]);
        const key = orderNo || tds.map((td) => td.textContent.trim().slice(0, 10)).join('|');
        if (!orderNo) return; // 跳过无订单号行
        const goods = extractGoods(tds[6]);
        const { shopName, actualAmount } = getShop(tds[14]);
        result.push({
          key,
          orderNo,
          erpOrderNo: getErpOrderNo(tds[25]),
          goods,
          imgUrl: goods.length ? goods[0].imgSrc : '',  // 第一件商品大图 URL（可直接在浏览器打开）
          express: getExpress(tds[7]),
          shippingTime: getCellText(tds[12]),
          printStatus: getCellText(tds[24]),
          shopName,
          actualAmount,
          orderStatus: getCellText(tds[10]),
        });
      });
    });
    return result;
  }

  const rowMap = new Map();
  function mergeRows() {
    let added = 0;
    collectRows().forEach(({ key, ...data }) => {
      if (!rowMap.has(key)) { rowMap.set(key, data); added++; }
    });
    return added;
  }

  if (!autoScroll) {
    mergeRows();
    log.push(`静态模式：抓取 ${rowMap.size} 条`);
  } else {
    const tableRoot = document.querySelector(TABLE_ROOT_SEL);
    const bodyWrap = tableRoot && tableRoot.querySelector(BODY_WRAP_SEL);

    // 探测可滚动层
    function probeScroll(el) {
      if (!el || el.nodeType !== 1) return false;
      try {
        if (el.scrollHeight <= el.clientHeight + 6) return false;
        const prev = el.scrollTop; el.scrollTop = prev + 8;
        const moved = el.scrollTop !== prev; el.scrollTop = prev;
        return moved;
      } catch (e) { return false; }
    }

    let scrollEl = null;
    const candidates = bodyWrap ? [bodyWrap, ...bodyWrap.querySelectorAll('*')] : [];
    for (const c of candidates) {
      if (probeScroll(c)) { scrollEl = c; break; }
    }

    if (scrollEl) scrollEl.scrollTop = 0;
    await sleep(300);
    mergeRows();
    log.push(`初始：${rowMap.size} 条`);

    let stale = 0;
    const stepPx = Math.max(100, Math.round((scrollEl ? scrollEl.clientHeight : 600) * 0.88));
    for (let step = 0; step < maxSteps; step++) {
      if (scrollEl) scrollEl.scrollTop += stepPx;
      await sleep(pauseMs);
      const added = mergeRows();
      if (added === 0) {
        stale++;
        if (stale >= 3) { log.push(`触底停止（step=${step + 1}）`); break; }
      } else {
        stale = 0;
      }
    }
    if (scrollEl) scrollEl.scrollTop = 0;
    log.push(`滚动完成，共 ${rowMap.size} 条`);
  }

  const rows = [...rowMap.values()];
  log.push(`最终输出 ${rows.length} 条已发货订单`);

  return { ok: true, count: rows.length, rows, log };
})();
