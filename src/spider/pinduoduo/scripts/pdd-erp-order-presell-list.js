/**
 * 拼多多官方 ERP —— 预售订单列表抓取
 * 页面：https://mms.pinduoduo.com/erp/order/presell
 *
 * 返回 **`orders` 为数组**（每项一条订单），主订单号字段 **`orderNo`** = 平台订单号（如 260513-181749727613319）。
 * 另含 **`erpOrderNo`**（ERP 订单编号，FH…，来自「订单编号/操作」列首行）。
 *
 * 「发货剩余/支付时间」列：
 * - **`发货剩余支付时间`**：单元格原文（含动态「X天X时…后超时揽收」等，仅备查）。
 * - **`支付时间`**：从原文拆出的**稳定**支付时刻，格式 `yyyy/MM/dd HH:mm`（无年份的 `MM-dd HH:mm` 按**当年**补全，与 `pdd-erp-order-all-table.js` 一致）。
 * - **`支付时间原文`**：如 `05-13 17:20 支付`。
 * 预售列表该列**不含真实发货时间**；`发货时间` 固定为 `''`（占位，便于与其它 ERP 列表字段对齐）。
 *
 * **图片**（字段必有，无图则为空串 / 空数组）：
 * - **`图片`**：首张商品主图 URL（已去 `?` / `#` 查询串，与 `pdd-erp-order-audit-goods.js` 一致）。
 * - **`图片列表`**：本行所有商品图 URL 顺序列表（多单 SKU 时不丢图）。
 * - **`goods`**：每项含 **`imgSrc`**（必有键）、`title`、`spec`、`qty`，从「商品规格」列 DOM 解析（逻辑与审核页脚本对齐）。
 *
 * 运行模式 `window.__PDD_ERP_PRESELL_RUN_MODE`：
 *   - `'extension'`（默认）：若设置了 `window.__PDD_ERP_PRESELL_SYNC_URL`，经扩展桥 `postMessage` POST `{ orders }`；
 *   - `'python'` / `'py'`：不 POST；返回 `syncBody` + `syncUrl`。
 *
 * 可选：`window.__PDD_ERP_PRESELL_AUTO_SCROLL`（默认 `false`）为 `true` 时，对 `.page-inner-content` 滚动并多次合并，按 `orderNo` 去重（虚拟表或超长列表）。
 * 可调：`__PDD_ERP_PRESELL_SCROLL_STEP`、`__PDD_ERP_PRESELL_SCROLL_PAUSE_MS`、`__PDD_ERP_PRESELL_SCROLL_MAX_STEPS`、`__PDD_ERP_PRESELL_RESTORE_SCROLL`。
 *
 * page_evaluate（MCP）：
 *   code = 'return ' + fs.readFileSync('pdd-erp-order-presell-list.js', 'utf8')
 *
 * Python：
 *   driver.execute_script("window.__PDD_ERP_PRESELL_RUN_MODE='python';")
 *   result = driver.execute_script(open('pdd-erp-order-presell-list.js').read())
 *   # result['orders'] 为 list；若需上报：requests.post(result['syncUrl'], json=result['syncBody'])
 */
(async function () {
  const TABLE_SEL = '[data-testid="beast-core-table"]';
  const SCROLL_WRAP_SEL = '.page-inner-content.order-manage, .page-inner-content';

  const DEFAULT_SYNC_URL = '';

  function resolveRunMode() {
    const m = String(window.__PDD_ERP_PRESELL_RUN_MODE || '')
      .trim()
      .toLowerCase();
    return m === 'python' || m === 'py' ? 'python' : 'extension';
  }

  const isPython = resolveRunMode() === 'python';
  const syncUrl = String(window.__PDD_ERP_PRESELL_SYNC_URL || DEFAULT_SYNC_URL).trim();

  const autoScroll = window.__PDD_ERP_PRESELL_AUTO_SCROLL === true;
  const scrollStep =
    Number(window.__PDD_ERP_PRESELL_SCROLL_STEP) || 420;
  const scrollPauseMs =
    Number(window.__PDD_ERP_PRESELL_SCROLL_PAUSE_MS) || 550;
  const scrollMaxSteps =
    Number(window.__PDD_ERP_PRESELL_SCROLL_MAX_STEPS) || 80;
  const restoreScroll =
    window.__PDD_ERP_PRESELL_RESTORE_SCROLL !== false;

  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function findColIndex(headers, needle) {
    const compactNeedle = String(needle || '').replace(/\s/g, '');
    for (let i = 0; i < headers.length; i++) {
      const h = String(headers[i] || '').replace(/\s/g, '');
      if (h.indexOf(compactNeedle) !== -1) return i;
    }
    return -1;
  }

  function lineHasCalendarDate(line) {
    const s = String(line || '');
    return (
      /(\d{4})\s*[年\/.\-]\s*\d{1,2}\s*[月\/.\-]\s*\d{1,2}/.test(s) ||
      /\b\d{4}-\d{1,2}-\d{1,2}\b/.test(s)
    );
  }

  function parseShipRemainAndPayTime(raw) {
    const t = String(raw || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .trim();
    if (!t) return { remain: '', payForFormat: '' };

    const lines = t
      .split('\n')
      .map((l) => l.replace(/\s+/g, ' ').trim())
      .filter(Boolean);
    if (!lines.length) return { remain: '', payForFormat: '' };

    const splitLines = [];
    for (let si = 0; si < lines.length; si++) {
      const spm = lines[si].match(/(\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}\s*支付)/);
      if (spm && spm.index > 0) {
        const bef = lines[si].slice(0, spm.index).trim();
        if (bef) splitLines.push(bef);
        splitLines.push(spm[1].trim());
        const aft = lines[si].slice(spm.index + spm[0].length).trim();
        if (aft) splitLines.push(aft);
      } else {
        splitLines.push(lines[si]);
      }
    }

    const payLines = [];
    const remainLines = [];

    for (let i = 0; i < splitLines.length; i++) {
      const L = splitLines[i];
      const d = lineHasCalendarDate(L);
      if (/支付\s*时间|付款\s*时间|支付[:：]|付款[:：]|买家\s*付|已\s*支付/.test(L)) {
        payLines.push(L);
      } else if (/发货\s*剩余|距\s*发\s*货|剩余\s*时间|超时未发|倒\s*计\s*时|发\s*货\s*剩|后超时揽收/.test(L)) {
        remainLines.push(L);
      } else if (d) {
        payLines.push(L);
      } else if (/支付/.test(L) && /\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}/.test(L)) {
        payLines.push(L);
      } else {
        remainLines.push(L);
      }
    }

    if (payLines.length === 0) {
      let di = -1;
      for (let j = 0; j < splitLines.length; j++) {
        if (lineHasCalendarDate(splitLines[j])) {
          di = j;
          break;
        }
      }
      if (di >= 0) {
        payLines.push(splitLines[di]);
        for (let k = 0; k < splitLines.length; k++) {
          if (k !== di) remainLines.push(splitLines[k]);
        }
      }
    }

    if (payLines.length === 0) {
      return { remain: t.slice(0, 500), payForFormat: '' };
    }

    const payJoined = payLines.join(' ');
    let remainJoined = remainLines.join(' | ');

    if (!remainJoined && splitLines.length === 2) {
      const other = splitLines[0] === payLines[0] ? splitLines[1] : splitLines[0];
      if (!lineHasCalendarDate(other)) remainJoined = other;
    }

    const cleanRemain = remainJoined.replace(/^[\s\-\|]+$/, '').trim();
    return {
      remain: cleanRemain.slice(0, 500),
      payForFormat: payJoined,
    };
  }

  function formatFeishuDateTime(input) {
    const s = String(input || '').trim();
    if (!s) return '';

    let m = s.match(
      /(\d{4})\s*[年\/.\-]\s*(\d{1,2})\s*[月\/.\-]\s*(\d{1,2})(?:日)?\s*(?:[Tt\s]+(\d{1,2}):(\d{2})(?::\d{2})?)?/
    );
    if (m) {
      const y = m[1];
      const mo = ('0' + m[2]).slice(-2);
      const d = ('0' + m[3]).slice(-2);
      if (m[4] != null && m[4] !== '' && m[5] != null) {
        const h = ('0' + m[4]).slice(-2);
        const mi = ('0' + m[5]).slice(-2);
        return y + '/' + mo + '/' + d + ' ' + h + ':' + mi;
      }
      return y + '/' + mo + '/' + d + ' 00:00';
    }
    m = s.match(/(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s]+(\d{1,2}):(\d{2})(?::\d{2})?)?/);
    if (m) {
      const y = m[1];
      const mo = ('0' + m[2]).slice(-2);
      const d = ('0' + m[3]).slice(-2);
      if (m[4] != null && m[5] != null) {
        const h = ('0' + m[4]).slice(-2);
        const mi = ('0' + m[5]).slice(-2);
        return y + '/' + mo + '/' + d + ' ' + h + ':' + mi;
      }
      return y + '/' + mo + '/' + d + ' 00:00';
    }
    m = s.match(/(?:^|[^\d])(\d{1,2})\s*[-\/]\s*(\d{1,2})\s+(\d{1,2}):(\d{2})/);
    if (m) {
      const y = String(new Date().getFullYear());
      const mo = ('0' + m[1]).slice(-2);
      const d = ('0' + m[2]).slice(-2);
      const h = ('0' + m[3]).slice(-2);
      const mi = ('0' + m[4]).slice(-2);
      return y + '/' + mo + '/' + d + ' ' + h + ':' + mi;
    }
    return s.slice(0, 32);
  }

  /** 支付时间原文：从 payForFormat 抽「MM-dd HH:mm 支付」一段 */
  function extractPayTimeRaw(payForFormat) {
    const s = String(payForFormat || '').trim();
    if (!s) return '';
    const m = s.match(/(\d{1,2}[-\/]\d{1,2}\s+\d{1,2}:\d{2}\s*支付)/);
    return m ? m[1].replace(/\s+/g, ' ').trim() : s.slice(0, 80);
  }

  function specFragmentFromGoodsCell(text) {
    const t = String(text || '').trim();
    const idx = t.lastIndexOf('】');
    if (idx !== -1) {
      const tail = t.slice(idx + 1).trim();
      return tail || t;
    }
    return t;
  }

  function parseErpOrderNo(opCell) {
    const line = String(opCell || '')
      .split('\n')[0]
      .trim();
    const m = line.match(/\bFH\d+\b/);
    return m ? m[0] : line.split(/\s+/)[0] || '';
  }

  /** 去掉图片 URL 的 ? 查询串与 # 片段（与 audit-goods 一致） */
  function stripImgQuery(url) {
    if (!url || String(url).startsWith('data:')) return url || '';
    try {
      return String(url).replace(/[?#].*$/, '');
    } catch (e) {
      return String(url || '');
    }
  }

  /**
   * 从「商品规格」列 td 提取商品块（含图），与 pdd-erp-order-audit-goods.js extractGoods 对齐。
   * 每条必有 imgSrc 键（无图则为 ''）。
   */
  function extractGoodsFromSpecTd(td) {
    if (!td) {
      return [];
    }
    const items = [...td.querySelectorAll('.sc-dUYKzm')];
    if (!items.length) {
      const img = td.querySelector('img');
      const text = (td.innerText || '').trim();
      return [
        {
          imgSrc: img
            ? stripImgQuery(
                img.src ||
                  img.getAttribute('data-src') ||
                  img.getAttribute('data-bimg-src') ||
                  ''
              )
            : '',
          title: text,
          spec: '',
          qty: 0,
        },
      ];
    }
    return items.map((item) => {
      const img = item.querySelector('img');
      const imgRaw =
        (img &&
          (img.src ||
            img.getAttribute('data-src') ||
            img.getAttribute('data-bimg-src'))) ||
        '';
      const imgSrc = stripImgQuery(imgRaw);

      let title = '';
      let spec = '';
      let qty = 0;
      const wrapper = item.querySelector('.content-wrapper');
      if (wrapper) {
        const lightSpan = wrapper.querySelector('.light-span');
        if (lightSpan) {
          const qtyText = lightSpan.textContent.trim();
          qty = parseInt(qtyText.replace(/^[xX×]/u, ''), 10) || 0;
        }
        const childSpans = [...wrapper.children].filter(
          (el) =>
            el.tagName === 'SPAN' &&
            !el.classList.contains('light-span') &&
            el.textContent.trim().length > 0
        );
        if (childSpans.length >= 2) {
          title = childSpans[0].textContent.trim();
          spec = childSpans[childSpans.length - 1].textContent.trim();
        } else if (childSpans.length === 1) {
          title = childSpans[0].textContent.trim();
          spec = '';
        }
      }

      return { imgSrc, title, spec, qty };
    });
  }

  /**
   * 解析当前 DOM 表格，返回 orders（不滚动）。
   */
  function parseTableOnce() {
    const table = document.querySelector(TABLE_SEL);
    if (!table) {
      return { error: '未找到 beast-core-table', orders: [] };
    }

    const trs = Array.from(table.querySelectorAll('tr'));
    if (trs.length < 2) {
      return { error: '表格无数据行', orders: [] };
    }

    const headers = Array.from(trs[0].querySelectorAll('th, td')).map((c) =>
      (c.innerText || '').replace(/\s+/g, ' ').trim()
    );

    const idxPlatform = findColIndex(headers, '平台订单号');
    const idxSpec =
      findColIndex(headers, '商品规格') >= 0
        ? findColIndex(headers, '商品规格')
        : findColIndex(headers, '规格');
    let idxShipPay = findColIndex(headers, '发货剩余');
    if (idxShipPay < 0) idxShipPay = findColIndex(headers, '支付时间');
    const idxOp = findColIndex(headers, '订单编号');

    if (idxPlatform < 0) {
      return { error: '表头缺少「平台订单号」', orders: [], headers };
    }

    const orders = [];
    for (let ri = 1; ri < trs.length; ri++) {
      const tds = Array.from(trs[ri].querySelectorAll('td, th'));
      const cells = tds.map((c) => (c.innerText || '').trim());
      const orderNo = String(cells[idxPlatform] || '')
        .replace(/\s+/g, ' ')
        .trim();
      if (!orderNo || !/^\d{6}-\d{8,22}$/.test(orderNo)) continue;

      const specTd = idxSpec >= 0 ? tds[idxSpec] : null;
      const goods = extractGoodsFromSpecTd(specTd);
      const goodsCell =
        specTd != null
          ? String(specTd.innerText || '').trim()
          : idxSpec >= 0
            ? String(cells[idxSpec] || '').trim()
            : '';
      const 图片列表 = goods
        .map((g) => String(g.imgSrc || '').trim())
        .filter((u) => u.length > 0);
      const 图片 = 图片列表[0] || '';

      const shipPayRaw =
        idxShipPay >= 0 ? String(cells[idxShipPay] || '').trim() : '';
      const opCell = idxOp >= 0 ? String(cells[idxOp] || '').trim() : '';

      const shipPay = parseShipRemainAndPayTime(shipPayRaw);
      const 支付时间 = formatFeishuDateTime(shipPay.payForFormat);
      const 支付时间原文 = extractPayTimeRaw(shipPay.payForFormat);

      const row = {
        orderNo,
        erpOrderNo: parseErpOrderNo(opCell),
        图片,
        图片列表,
        goods,
        商品规格: goodsCell,
        规格片段: specFragmentFromGoodsCell(goodsCell),
        发货剩余支付时间: shipPayRaw,
        支付时间,
        支付时间原文,
        发货时间: '',
      };
      orders.push(row);
    }

    return { orders, headers };
  }

  function findScrollEl() {
    const cand = document.querySelector(SCROLL_WRAP_SEL);
    if (!cand) return null;
    if (cand.scrollHeight > cand.clientHeight + 30) return cand;
    let el = cand;
    while (el && el !== document.body) {
      if (el.scrollHeight > el.clientHeight + 30) {
        const before = el.scrollTop;
        el.scrollTop = before + 1;
        const moved = el.scrollTop !== before;
        el.scrollTop = before;
        if (moved) return el;
      }
      el = el.parentElement;
    }
    return cand.scrollHeight > cand.clientHeight + 30 ? cand : null;
  }

  async function collectOrdersWithOptionalScroll() {
    const scrollEl = findScrollEl();
    const startTop = scrollEl ? scrollEl.scrollTop : 0;
    const merged = new Map();

    const ingest = () => {
      const { orders, error } = parseTableOnce();
      if (error && orders.length === 0) return error;
      for (const o of orders) {
        merged.set(o.orderNo, o);
      }
      return null;
    };

    let err = ingest();
    if (err) return { error: err, orders: [] };

    if (!autoScroll || !scrollEl) {
      log.push(
        autoScroll
          ? '未找到可滚动容器，仅解析当前视口表格'
          : 'AUTO_SCROLL=false，仅解析当前视口'
      );
      return { orders: Array.from(merged.values()) };
    }

    log.push('AUTO_SCROLL=true，滚动合并多屏行');
    let steps = 0;
    let prevSize = 0;
    while (steps < scrollMaxSteps) {
      scrollEl.scrollTop = Math.min(
        scrollEl.scrollTop + scrollStep,
        scrollEl.scrollHeight - scrollEl.clientHeight
      );
      await sleep(scrollPauseMs);
      ingest();
      const size = merged.size;
      const atBottom =
        scrollEl.scrollTop + scrollEl.clientHeight >=
        scrollEl.scrollHeight - 8;
      if (atBottom && size === prevSize) break;
      prevSize = size;
      steps++;
      if (atBottom) break;
    }

    if (restoreScroll && scrollEl) scrollEl.scrollTop = startTop;

    return { orders: Array.from(merged.values()) };
  }

  const { orders, error } = await collectOrdersWithOptionalScroll();

  if (error) {
    log.push('抓取失败：' + error);
    return {
      ok: false,
      error,
      orders: [],
      count: 0,
      log,
      sync: { skipped: true, reason: 'extract_error' },
    };
  }

  orders.sort((a, b) => a.orderNo.localeCompare(b.orderNo));
  log.push(`共 ${orders.length} 条订单`);

  const syncBody = { orders };

  if (isPython) {
    return {
      ok: true,
      runMode: 'python',
      count: orders.length,
      orders,
      syncBody,
      syncUrl: syncUrl || DEFAULT_SYNC_URL,
      log,
      sync: { skipped: true, reason: 'python_mode' },
    };
  }

  let sync = { skipped: true, reason: '未配置 __PDD_ERP_PRESELL_SYNC_URL' };
  if (syncUrl) {
    try {
      const ackKey = '__crPddPresell_' + Date.now();
      let resolved = false;
      const bridgePromise = new Promise((resolve) => {
        const handler = (e) => {
          if (e.data && e.data.__type === ackKey + '_reply') {
            window.removeEventListener('message', handler);
            resolved = true;
            resolve({ via: 'extension', ...e.data });
          }
        };
        window.addEventListener('message', handler);
        window.postMessage(
          {
            __type: '__crPdd',
            ackKey,
            url: syncUrl,
            body: syncBody,
          },
          '*'
        );
        setTimeout(() => {
          if (!resolved) {
            window.removeEventListener('message', handler);
            resolve(null);
          }
        }, 3000);
      });

      const bridgeResult = await bridgePromise;
      if (bridgeResult) {
        sync = bridgeResult;
        log.push('同步成功（扩展桥）：' + syncUrl);
      } else {
        try {
          const resp = await fetch(syncUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(syncBody),
          });
          const json = await resp.json().catch(() => null);
          sync = { via: 'fetch', status: resp.status, json };
          log.push(`同步成功（fetch）：status=${resp.status}`);
        } catch (fe) {
          sync = { via: 'fetch', error: String(fe) };
          log.push('同步失败（fetch）：' + fe);
        }
      }
    } catch (e) {
      sync = { error: String(e) };
      log.push('同步异常：' + e);
    }
  }

  return {
    ok: true,
    runMode: 'extension',
    count: orders.length,
    orders,
    sync,
    log,
  };
})();
