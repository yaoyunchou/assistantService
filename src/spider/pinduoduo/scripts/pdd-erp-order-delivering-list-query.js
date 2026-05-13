/**
 * 拼多多官方 ERP —— 待发货页仅查询当前列表（不点选、不打印）
 * 页面：https://mms.pinduoduo.com/erp/order/delivering
 *
 * 与 pdd-erp-order-delivering-print-ship.js 的「等待列表出现」逻辑一致，只采集行内数据。
 * 若列表为虚拟滚动，未滚入视区的行可能不在本次结果中（与页面上肉眼可见区域一致）。
 */
(async function () {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const GOODS_TD_IDX = 6;
  const ORDER_NO_TD_IDX = 11;

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

  /* ─── 等待表格容器 ─── */
  const t0 = Date.now();
  while (Date.now() - t0 < 12000) {
    const tbody = document.querySelector('[data-testid="beast-core-table-middle-tbody"]');
    if (tbody) break;
    await sleep(400);
  }

  const MIN_WAIT_MS = 5000;
  const MAX_WAIT_MS = 15000;
  const tWait = Date.now();
  let rows = document.querySelectorAll(ROW_SEL);
  while (Date.now() - tWait < MAX_WAIT_MS) {
    rows = document.querySelectorAll(ROW_SEL);
    const elapsed = Date.now() - tWait;
    if (rows.length > 0 && elapsed >= MIN_WAIT_MS) break;
    if (rows.length === 0 && elapsed >= MIN_WAIT_MS) {
      await sleep(500);
      rows = document.querySelectorAll(ROW_SEL);
      break;
    }
    await sleep(400);
  }
  log.push(`列表加载等待 ${Date.now() - tWait}ms，行数=${rows.length}`);

  if (rows.length === 0) {
    log.push('列表为空');
    return { ok: true, empty: true, rows: [], log };
  }

  const outRows = [];
  rows.forEach((tr) => {
    const tds = tr.querySelectorAll('td');
    const orderNo = getOrderNo(tds[ORDER_NO_TD_IDX]);
    if (!orderNo) return;
    outRows.push({
      orderNo,
      goods: extractGoods(tds[GOODS_TD_IDX]),
    });
  });

  log.push(`解析 ${outRows.length} 条订单`);
  return { ok: true, empty: false, rows: outRows, log };
})();
