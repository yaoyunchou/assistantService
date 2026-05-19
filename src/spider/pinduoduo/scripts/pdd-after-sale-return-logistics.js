/**
 * pdd-after-sale-return-logistics.js — 拼多多 ERP 售后页：批量采集退货物流信息
 * ============================================================================
 * 目标页面：https://mms.pinduoduo.com/erp/after-sale/manage
 *
 * 运行模式（执行前设置 window.__PDD_LOGISTICS_RUN_MODE）：
 *   'extension'（默认）：在页面内运行，数据直接返回给扩展/MCP
 *   'python' / 'py'   ：同上，额外返回 syncBody + syncUrl 供 Python 侧使用
 *
 * 可选参数（window.__PDD_LOGISTICS_* 执行前赋值）：
 *   __PDD_LOGISTICS_FILTER_TEXT  {string}  筛选项文字，默认 '退回/退货签收待处理'
 *   __PDD_LOGISTICS_HOVER_WAIT   {number}  hover 后等待 popover 的毫秒数，默认 350
 *   __PDD_LOGISTICS_SCROLL_STEP  {number}  每次滚动像素，默认 400
 *   __PDD_LOGISTICS_SCROLL_WAIT  {number}  每次滚动后等待虚拟渲染的毫秒数，默认 600
 *   __PDD_LOGISTICS_SYNC_URL     {string}  数据上报地址（python 模式用）
 *
 * Python 调用示例：
 *   driver.execute_script("window.__PDD_LOGISTICS_RUN_MODE='python';")
 *   result = driver.execute_script(open('pdd-after-sale-return-logistics.js').read())
 *   # result.results 即物流数组
 *
 * page_evaluate 调用示例（MCP）：
 *   code = 'return ' + open('pdd-after-sale-return-logistics.js').read()
 *   page_evaluate(tabId=xxx, code=code, timeout=120000)
 *
 * 返回值：
 *   {
 *     ok:       boolean,
 *     results:  Array<{
 *       orderNo, carrier, trackNo, latestStatus,
 *       allStatuses: string[],   // 全部物流节点（时间 + 描述）
 *       fullText: string         // popover 原始全文
 *     }>,
 *     skipped:  string[],        // 无退货物流信息的订单号
 *     log:      string[],
 *     stats:    { total, withLogistics, withoutLogistics, carriers }
 *   }
 */

(async function () {
  // ============================================================
  // 1. 配置
  // ============================================================
  const FILTER_TEXT  = window.__PDD_LOGISTICS_FILTER_TEXT  || '退回/退货签收待处理';
  const HOVER_WAIT   = window.__PDD_LOGISTICS_HOVER_WAIT   ?? 550;
  const SCROLL_STEP  = window.__PDD_LOGISTICS_SCROLL_STEP  ?? 400;
  const SCROLL_WAIT  = window.__PDD_LOGISTICS_SCROLL_WAIT  ?? 600;
  const POPOVER_STABLE_ROUNDS = 2;

  const SCROLL_EL_SEL  = '.page-inner-content.after-sale-manage';
  const LOGISTICS_TEXT = '退货物流信息';
  const POPOVER_SEL    = '[class*="PP_popoverContent"]';

  // ============================================================
  // 2. 运行模式
  // ============================================================
  function resolveRunMode() {
    const m = (window.__PDD_LOGISTICS_RUN_MODE || '').trim().toLowerCase();
    return (m === 'python' || m === 'py') ? 'python' : 'extension';
  }

  // ============================================================
  // 3. 工具函数
  // ============================================================
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const log   = [];
  const info  = msg => { log.push('[INFO] ' + msg); console.log('[pdd-logistics]', msg); };
  const warn  = msg => { log.push('[WARN] ' + msg); console.warn('[pdd-logistics]', msg); };

  /** 从 TR 里找订单编号（格式：260428-387018954283543，即"订单编号：XXXXXX-XXXXXXXXXXXXXXX"） */
  function getOrderNo(tr) {
    const m = tr.textContent.match(/订单编号[：:]\s*(\d{6}-\d{10,18})/);
    return m ? m[1] : null;
  }

  /** 派发鼠标进入事件，触发 Popover */
  function hoverSpan(el) {
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top  + rect.height / 2;
    const base = {
      bubbles: true, cancelable: true, composed: true,
      clientX: cx, clientY: cy,
      screenX: cx + window.screenX, screenY: cy + window.screenY,
      view: window
    };
    try {
      el.dispatchEvent(new PointerEvent('pointerover',  { ...base, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
      el.dispatchEvent(new PointerEvent('pointerenter', { ...base, bubbles: false, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
    } catch (e) { /* 不支持 PointerEvent 时跳过 */ }
    el.dispatchEvent(new MouseEvent('mouseenter', { ...base, bubbles: false }));
    el.dispatchEvent(new MouseEvent('mouseover',  base));
    el.dispatchEvent(new MouseEvent('mousemove',  base));
  }

  /** 派发鼠标离开事件，收起 Popover */
  function leaveSpan(el) {
    const base = { bubbles: true, cancelable: true, view: window };
    try {
      el.dispatchEvent(new PointerEvent('pointerout',   { ...base, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
      el.dispatchEvent(new PointerEvent('pointerleave', { ...base, bubbles: false, pointerId: 1, pointerType: 'mouse', isPrimary: true }));
    } catch (e) {}
    el.dispatchEvent(new MouseEvent('mouseout',   base));
    el.dispatchEvent(new MouseEvent('mouseleave', { ...base, bubbles: false }));
  }

  /** 读取当前可见的 Popover 文本，清除 CSS 噪声 */
  function readPopover() {
    const p = document.querySelector(POPOVER_SEL);
    if (!p) return null;
    return p.textContent
      .replace(/\.beast[\w-]*\s*\{[^}]*\}/g, '')
      .replace(/复制/g, '')
      .trim();
  }

  /** 移开鼠标，尽量收起上一条 Popover，避免读到上一行残留 */
  async function dismissPopover() {
    try {
      document.body.dispatchEvent(new MouseEvent('mousemove', {
        bubbles: true, cancelable: true, clientX: 4, clientY: 4, view: window,
      }));
    } catch (e) { /* ignore */ }
    await sleep(200);
  }

  /** 等待 Popover 文本连续稳定后再返回，降低串行/未加载完就读取的问题 */
  async function readPopoverStable(maxMs) {
    const deadline = Date.now() + maxMs;
    let last = null;
    let stableHits = 0;
    while (Date.now() < deadline) {
      const t = readPopover();
      if (t && t.length >= 8) {
        if (t === last) {
          stableHits++;
          if (stableHits >= POPOVER_STABLE_ROUNDS) return t;
        } else {
          last = t;
          stableHits = 1;
        }
      }
      await sleep(70);
    }
    return last || readPopover();
  }

  function statusCount(entry) {
    return (entry && entry.allStatuses && entry.allStatuses.length) || 0;
  }

  /**
   * 解析物流文本：提取快递公司、运单号、所有物流节点
   * 格式示例：
   *   「韵达465332904015842」「顺丰快递SF5136477156239」
   *   「邮政EMS1328920659544」「极兔速递JT5483122437206」「圆通YT8865465660379」
   * 运单号组兼容：可选大写字母前缀（SF/EMS/JT/YT 等）+ 纯数字
   */
  function parseLogistics(text) {
    if (!text) return { carrier: '', trackNo: '', latestStatus: '', allStatuses: [], fullText: '' };

    // 快递公司名 + 可选空白 + 运单号（兼容「中通 79103650383484」中间有空格的格式）
    const hm = text.match(/([\u4e00-\u9fa5]{2,10})\s*([A-Z]{0,6}\d{8,30})/);
    const carrier = hm ? hm[1] : '';
    const trackNo = hm ? hm[2] : '';

    // 按时间戳切割物流节点
    // 实际格式：「描述文字 时间戳」，时间戳在每条描述末尾
    // 策略：找出所有时间戳位置，上一个时间戳结束到当前时间戳开始的文字 = 描述
    const timeRe = /\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/g;
    const timePositions = [];
    let tm;
    while ((tm = timeRe.exec(text)) !== null) {
      timePositions.push({ time: tm[0], start: tm.index, end: tm.index + tm[0].length });
    }
    const allStatuses = [];
    for (let i = 0; i < timePositions.length; i++) {
      const { time, start, end: tEnd } = timePositions[i];
      const descStart = i === 0 ? 0 : timePositions[i - 1].end;
      const desc = text.slice(descStart, start).trim().replace(/\s+/g, ' ').slice(0, 120);
      allStatuses.push((desc ? desc + ' ' : '') + time);
    }

    const latestStatus = allStatuses[0] || '';

    return { carrier, trackNo, latestStatus, allStatuses, fullText: text };
  }

  // ============================================================
  // 4. 核心采集逻辑
  // ============================================================
  async function collect() {
    // Step 1: 确认筛选器已激活
    info('检查筛选器');
    const filterEl = Array.from(document.querySelectorAll('[data-checked]'))
      .find(el => el.textContent.includes(FILTER_TEXT));
    if (!filterEl) return { ok: false, error: `未找到筛选器「${FILTER_TEXT}」`, log };

    if (filterEl.getAttribute('data-checked') !== 'true') {
      info('筛选器未选中，点击激活');
      filterEl.click();
      await sleep(1500);
    }
    info('筛选器: ' + filterEl.textContent.trim());

    // Step 2: 滚动容器重置到顶部
    const scrollEl = document.querySelector(SCROLL_EL_SEL);
    if (!scrollEl) return { ok: false, error: `未找到滚动容器「${SCROLL_EL_SEL}」`, log };
    scrollEl.scrollTop = 0;
    await sleep(800);
    info(`滚动容器 scrollHeight=${scrollEl.scrollHeight} clientHeight=${scrollEl.clientHeight}`);

    // Step 3: 循环滚动 + 逐行 hover 采集
    const resultsByOrder = new Map();
    const skipped   = [];
    const processed = new Set();
    let stallCount  = 0;

    while (stallCount < 3) {
      // 找当前 DOM 里在数据行里的「退货物流信息」span
      const dataSpans = Array.from(document.querySelectorAll('span'))
        .filter(el => el.textContent.trim() === LOGISTICS_TEXT && !!el.closest('tr'));

      let gotNew = false;

      for (const span of dataSpans) {
        const tr      = span.closest('tr');
        const orderNo = getOrderNo(tr);
        if (!orderNo) continue;

        try {
          span.scrollIntoView({ block: 'center', behavior: 'auto' });
        } catch (e) { /* ignore */ }
        await sleep(120);
        await dismissPopover();

        hoverSpan(span);
        const popoverText = await readPopoverStable(HOVER_WAIT + 250);
        leaveSpan(span);
        await dismissPopover();

        processed.add(orderNo);

        if (!popoverText) {
          if (!resultsByOrder.has(orderNo)) {
            warn(`无 Popover: ${orderNo}`);
            skipped.push(orderNo);
          }
          continue;
        }

        const lg = parseLogistics(popoverText);
        const entry = { orderNo, ...lg };
        const prev = resultsByOrder.get(orderNo);
        if (prev && statusCount(prev) >= statusCount(entry)) {
          continue;
        }
        resultsByOrder.set(orderNo, entry);
        info(`✅ ${orderNo}  ${lg.carrier}  ${lg.trackNo}  节点${lg.allStatuses.length}条`);
        gotNew = true;
      }

      // 记录无退货物流信息的行
      for (const tr of document.querySelectorAll('[data-testid="beast-core-table-body-tr"]')) {
        const orderNo = getOrderNo(tr);
        if (!orderNo || processed.has(orderNo)) continue;
        const hasSpan = Array.from(tr.querySelectorAll('span'))
          .some(el => el.textContent.trim() === LOGISTICS_TEXT);
        if (!hasSpan) {
          processed.add(orderNo);
          skipped.push(orderNo);
          info(`— ${orderNo} 无退货物流列`);
        }
      }

      if (!gotNew) stallCount++; else stallCount = 0;

      // 向下滚动
      const prevTop = scrollEl.scrollTop;
      scrollEl.scrollTop += SCROLL_STEP;
      await sleep(SCROLL_WAIT);

      const reachedBottom =
        scrollEl.scrollTop === prevTop ||
        scrollEl.scrollTop + scrollEl.clientHeight >= scrollEl.scrollHeight - 10;
      if (reachedBottom) { info('已到达底部'); break; }
    }

    const results = Array.from(resultsByOrder.values());
    const carriers = [...new Set(results.map(r => r.carrier).filter(Boolean))];
    info(`采集完成：${results.length} 条有物流，${skipped.length} 条无物流`);

    return {
      ok: true,
      results,
      skipped,
      log,
      stats: {
        total:              processed.size,
        withLogistics:      results.length,
        withoutLogistics:   skipped.length,
        carriers,
      },
    };
  }

  // ============================================================
  // 5. 主入口：按运行模式分流
  // ============================================================
  async function main() {
    const result = await collect();
    if (!result.ok) {
      result.sync = { skipped: true, reason: 'collect_error' };
      return result;
    }

    const mode = resolveRunMode();

    if (mode === 'python') {
      result.runMode = 'python';
      result.syncBody = { results: result.results };
      result.syncUrl  = (window.__PDD_LOGISTICS_SYNC_URL || '').trim()
        || 'http://127.0.0.1:8887/api/pdd/after-sale-logistics';
      result.sync = { skipped: true, reason: 'python_mode' };
      result.log.push('python 模式：请用 result.syncUrl + result.syncBody 在 Python 侧 POST');
      return result;
    }

    // extension 模式：直接返回数据（调用方自行处理）
    result.runMode = 'extension';
    result.sync = { skipped: true, reason: 'no_backend_configured' };
    return result;
  }

  return await main();
})();
