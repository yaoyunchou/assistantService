/**
 * 拼多多官方 ERP —— 待发货页仅查询当前列表（不点选、不打印）
 * 页面：https://mms.pinduoduo.com/erp/order/delivering
 *
 * 与 pdd-erp-order-delivering-print-ship.js 的「等待列表出现」逻辑一致，只采集行内数据。
 * 默认开启虚拟滚动采集：按 orderNo 去重合并，避免只抓到视口内十几行而漏单。
 *
 * 可选配置（window，可由 Python evaluate 注入）：
 *   - `__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL`：默认 true；false 则仅首屏
 *   - `__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS`：每步等待，默认 450
 *   - `__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS`：最大步数，默认 200
 *   - `__PDD_ERP_DELIVERING_LIST_RESTORE_SCROLL`：结束后是否回顶，默认 true
 */
(async function () {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const TBODY_SEL = '[data-testid="beast-core-table-middle-tbody"]';
  const TABLE_ROOT_SEL = '[data-testid="beast-core-table"]';
  const BODY_WRAP_SEL = '[data-testid="beast-core-table-middle-body"]';
  const SCROLLBAR_ROOT_SEL = '[data-testid="beast-core-scrollbar-root"]';
  const GOODS_TD_IDX = 6;
  const ORDER_NO_TD_IDX = 11;

  const autoScroll = window.__PDD_ERP_DELIVERING_LIST_AUTO_SCROLL !== false;
  const pauseMs = Number(window.__PDD_ERP_DELIVERING_LIST_SCROLL_PAUSE_MS) || 450;
  const maxSteps = Number(window.__PDD_ERP_DELIVERING_LIST_SCROLL_MAX_STEPS) || 200;
  const restoreScroll = window.__PDD_ERP_DELIVERING_LIST_RESTORE_SCROLL !== false;
  /** 单元测试可覆盖：默认最少等 5s / 最多 15s，避免列表请求慢误判为空 */
  const minWaitMs = Number(window.__PDD_ERP_DELIVERING_LIST_MIN_WAIT_MS);
  const maxWaitMs = Number(window.__PDD_ERP_DELIVERING_LIST_MAX_WAIT_MS);
  const MIN_WAIT_MS = Number.isFinite(minWaitMs) ? minWaitMs : 5000;
  const MAX_WAIT_MS = Number.isFinite(maxWaitMs) ? maxWaitMs : 15000;

  function stripImgQuery(url) {
    if (!url || url.startsWith('data:')) return url;
    try {
      return url.replace(/[?#].*$/, '');
    } catch (e) {
      return url;
    }
  }

  function getOrderNo(td) {
    if (!td) return '';
    const link = td.querySelector('[data-testid="beast-core-button-link"] span');
    if (link) return link.textContent.trim();
    const clone = td.cloneNode(true);
    clone.querySelectorAll('style').forEach((s) => s.remove());
    return (clone.innerText || '').trim().split('\n')[0].trim();
  }

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
        imgSrc: img ? stripImgQuery(img.src || img.getAttribute('data-src') || '') : '',
        title: m ? text.slice(0, m.index).trim() : text,
        spec: '',
        qty: m ? parseInt(m[1], 10) : 0,
      }];
    }
    return items.map((item) => {
      const img = item.querySelector('img');
      const imgRaw =
        (img && (img.src || img.getAttribute('data-src') || img.getAttribute('data-bimg-src'))) || '';
      const imgSrc = stripImgQuery(imgRaw);
      let title = '', spec = '', qty = 0;
      const wrapper = item.querySelector('.content-wrapper');
      if (wrapper) {
        const lightSpan = wrapper.querySelector('.light-span');
        if (lightSpan) {
          qty = parseInt(lightSpan.textContent.trim().replace(/^[xX×]/u, ''), 10) || 0;
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
        }
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
        if (leafSpans.length >= 2) {
          title = leafSpans[0].textContent.trim();
          spec = leafSpans[leafSpans.length - 1].textContent.trim();
        } else if (leafSpans.length === 1) {
          title = leafSpans[0].textContent.trim();
        }
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

  function probeVerticalScrollable(el) {
    if (!el || el.nodeType !== 1) return false;
    try {
      if (el.scrollHeight <= el.clientHeight + 6) return false;
      const prev = el.scrollTop;
      el.scrollTop = prev + 8;
      const moved = el.scrollTop !== prev;
      el.scrollTop = prev;
      return moved;
    } catch (e) {
      return false;
    }
  }

  function findTableBodyScrollEl(root) {
    const candidates = [];
    const tbody = root.querySelector(TBODY_SEL);
    let p = tbody;
    while (p && p !== document.documentElement) {
      if (probeVerticalScrollable(p)) candidates.push(p);
      p = p.parentElement;
    }
    const wrap = root.querySelector(BODY_WRAP_SEL) || root;
    [wrap, ...wrap.querySelectorAll('*')].forEach((n) => {
      if (probeVerticalScrollable(n)) candidates.push(n);
    });
    const sr = root.querySelector(SCROLLBAR_ROOT_SEL);
    if (sr && probeVerticalScrollable(sr)) candidates.push(sr);
    if (!candidates.length) return null;
    return candidates.reduce(
      (best, c) => (c.scrollHeight >= best.scrollHeight ? c : best),
      candidates[0]
    );
  }

  function dispatchWheel(target, deltaY) {
    if (!target) return;
    try {
      target.dispatchEvent(
        new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          deltaY,
          deltaMode: 0,
          view: window,
        })
      );
    } catch (e) {
      /* ignore */
    }
  }

  function broadcastWheel(root, deltaY) {
    [
      root.querySelector(SCROLLBAR_ROOT_SEL),
      root.querySelector(BODY_WRAP_SEL),
      root,
    ]
      .filter(Boolean)
      .forEach((t) => dispatchWheel(t, deltaY));
  }

  function collectRowsFromDom() {
    const result = [];
    [...document.querySelectorAll(TBODY_SEL)].forEach((tbody) => {
      [...tbody.querySelectorAll(ROW_SEL)].forEach((tr) => {
        const tds = tr.querySelectorAll('td');
        const orderNo = getOrderNo(tds[ORDER_NO_TD_IDX]);
        if (!orderNo) return;
        result.push({
          orderNo,
          goods: extractGoods(tds[GOODS_TD_IDX]),
        });
      });
    });
    return result;
  }

  /* ─── 等待表格容器 ─── */
  const t0 = Date.now();
  while (Date.now() - t0 < 12000) {
    const tbody = document.querySelector(TBODY_SEL);
    if (tbody) break;
    await sleep(400);
  }

  const tWait = Date.now();
  let rows = document.querySelectorAll(ROW_SEL);
  while (Date.now() - tWait < MAX_WAIT_MS) {
    rows = document.querySelectorAll(ROW_SEL);
    const elapsed = Date.now() - tWait;
    if (rows.length > 0 && elapsed >= MIN_WAIT_MS) break;
    if (rows.length === 0 && elapsed >= MIN_WAIT_MS) {
      await sleep(Math.min(500, Math.max(50, pauseMs)));
      rows = document.querySelectorAll(ROW_SEL);
      break;
    }
    await sleep(Math.min(400, Math.max(20, Math.floor(pauseMs / 2) || 20)));
  }
  log.push(`列表加载等待 ${Date.now() - tWait}ms，行数=${rows.length}`);
  log.push(
    `[配置] autoScroll=${autoScroll} pauseMs=${pauseMs} maxSteps=${maxSteps} restoreScroll=${restoreScroll} minWait=${MIN_WAIT_MS} maxWait=${MAX_WAIT_MS}`
  );

  if (rows.length === 0) {
    log.push('列表为空');
    return { ok: true, empty: true, rows: [], log, scroll: { autoScroll, steps: 0, uniqueKeys: 0 } };
  }

  const rowMap = new Map();
  function mergeCurrentRows() {
    let added = 0;
    collectRowsFromDom().forEach((row) => {
      if (!rowMap.has(row.orderNo)) {
        rowMap.set(row.orderNo, row);
        added++;
      }
    });
    return added;
  }

  let scrollMeta = {
    autoScroll: false,
    steps: 0,
    uniqueKeys: 0,
    scrollFound: false,
    scrollVia: 'none',
  };

  if (!autoScroll) {
    mergeCurrentRows();
    log.push(`静态模式：抓取 ${rowMap.size} 条（仅当前视口）`);
    scrollMeta.uniqueKeys = rowMap.size;
  } else {
    const tableRoot = document.querySelector(TABLE_ROOT_SEL) || document.body;
    const scrollEl = findTableBodyScrollEl(tableRoot);
    scrollMeta.autoScroll = true;
    scrollMeta.scrollFound = !!scrollEl;
    scrollMeta.scrollVia = scrollEl ? 'scrollTop+wheel' : 'wheel';

    if (scrollEl) {
      log.push(
        `滚动容器：tag=${scrollEl.tagName} scrollHeight=${scrollEl.scrollHeight} clientHeight=${scrollEl.clientHeight}`
      );
    } else {
      log.push('未探测到可设 scrollTop 的层，改用 wheel 驱动虚拟列表');
    }

    if (scrollEl) scrollEl.scrollTop = 0;
    broadcastWheel(tableRoot, -9999);
    await sleep(pauseMs);

    const initAdded = mergeCurrentRows();
    log.push(`初始视口：+${initAdded}，累计=${rowMap.size}`);

    let stale = 0;
    const viewportH = scrollEl ? scrollEl.clientHeight : window.innerHeight;
    const stepPx = Math.max(100, Math.round(viewportH * 0.88));
    log.push(`每步 ${stepPx}px，最多 ${maxSteps} 步，间隔 ${pauseMs}ms`);

    for (let step = 0; step < maxSteps; step++) {
      if (scrollEl) scrollEl.scrollTop += stepPx;
      broadcastWheel(tableRoot, stepPx);
      await sleep(pauseMs);

      const added = mergeCurrentRows();
      scrollMeta.steps = step + 1;
      if (added > 0) {
        stale = 0;
        log.push(`[scroll step=${step + 1}] +${added}，累计=${rowMap.size}`);
      } else {
        stale++;
        if (stale >= 3) {
          log.push(`连续 3 步无新数据，触底停止（step=${step + 1}，总计=${rowMap.size}）`);
          break;
        }
      }
    }

    if (restoreScroll) {
      if (scrollEl) scrollEl.scrollTop = 0;
      broadcastWheel(tableRoot, -9999);
    }
    scrollMeta.uniqueKeys = rowMap.size;
    log.push(`滚动完成，共 ${rowMap.size} 条`);
  }

  const outRows = [...rowMap.values()];
  log.push(`解析 ${outRows.length} 条订单`);
  return {
    ok: true,
    empty: false,
    rows: outRows,
    log,
    scroll: scrollMeta,
  };
})();
