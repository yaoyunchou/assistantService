/**
 * 拼多多官方 ERP —— 审核订单列表「商品规格」抓取
 * 页面：https://mms.pinduoduo.com/erp/order/audit
 *
 * 抓取字段（每条订单）：
 *   - 平台订单号（td[11]）
 *   - shopName：店铺名称（td[12] 第一行）
 *   - actualAmount：实收金额，如 ¥32.29（td[12] 第二行）
 *   - goods[]：商品列表，每项含 imgSrc(原图URL) / title / spec / qty
 *
 * 运行模式 `window.__PDD_ERP_AUDIT_GOODS_RUN_MODE`：
 *   - `'extension'`（默认）：若设置了 `window.__PDD_ERP_AUDIT_GOODS_SYNC_URL`，
 *     经扩展桥 postMessage POST `{ rows }`；
 *   - `'python'` / `'py'`：不 POST；返回 `syncBody` + `syncUrl` 供 Python 使用。
 *
 * 可选配置（在 window 上提前设置）：
 *   - `window.__PDD_ERP_AUDIT_GOODS_SYNC_URL`：同步接口（默认空，不上传）
 *   - `window.__PDD_ERP_AUDIT_GOODS_AUTO_SCROLL`：是否自动滚动，默认 true
 *   - `window.__PDD_ERP_AUDIT_GOODS_SCROLL_PAUSE_MS`：每步暂停，默认 500
 *   - `window.__PDD_ERP_AUDIT_GOODS_SCROLL_MAX_STEPS`：最大步数，默认 600
 *   - `window.__PDD_ERP_AUDIT_GOODS_SCROLL_STEP_RATIO`：每步滚动视口高度比，默认 0.88
 *   - `window.__PDD_ERP_AUDIT_GOODS_RESTORE_SCROLL`：结束是否回顶，默认 true
 *   - `window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS`：订单号白名单数组，只返回指定订单（默认 null = 全量）
 *     示例：window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS = ['260418-239463381311785', '260418-063648581173653']
 *   - `window.__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS`：勾选指定订单的 checkbox（不影响数据抓取返回值）
 *     示例：window.__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS = ['260418-239463381311785', '260418-063648581173653']
 *     设为 true 时与 FILTER_ORDER_NOS 联动（即勾选过滤出来的订单）
 *   - `window.__PDD_ERP_AUDIT_GOODS_DO_AUDIT`：勾选后自动点击「审核」按钮提交审核，默认 false
 *     ⚠️ 设为 true 会真实提交审核，谨慎使用！
 *
 * Python 使用示例：
 *   import requests, json
 *   # 先在页面执行本脚本并设置 window.__PDD_ERP_AUDIT_GOODS_RUN_MODE = 'python'
 *   result = ...  # 从 page_evaluate 返回值中取
 *   requests.post(result['syncUrl'], json=result['syncBody'])
 */
(async function () {
  /* ─── 常量 / 选择器 ─── */
  const TBODY_SEL = '[data-testid="beast-core-table-middle-tbody"]';
  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const TABLE_ROOT_SEL = '[data-testid="beast-core-table"]';
  const BODY_WRAP_SEL = '[data-testid="beast-core-table-middle-body"]';
  const SCROLLBAR_ROOT_SEL = '[data-testid="beast-core-scrollbar-root"]';

  /** 商品规格列（td 下标，0=勾选框） */
  const GOODS_TD_IDX = 6;
  /** 平台订单号列 */
  const ORDER_NO_TD_IDX = 11;
  /** 店铺/实收列 */
  const SHOP_TD_IDX = 12;

  /* ─── 运行模式 ─── */
  const runMode =
    (window.__PDD_ERP_AUDIT_GOODS_RUN_MODE || 'extension').toLowerCase();
  const isPython = runMode === 'python' || runMode === 'py';
  const syncUrl = (
    window.__PDD_ERP_AUDIT_GOODS_SYNC_URL || ''
  ).trim();

  /* ─── 滚动参数 ─── */
  const autoScroll =
    window.__PDD_ERP_AUDIT_GOODS_AUTO_SCROLL !== false;
  const pauseMs =
    Number(window.__PDD_ERP_AUDIT_GOODS_SCROLL_PAUSE_MS) || 500;
  const maxSteps =
    Number(window.__PDD_ERP_AUDIT_GOODS_SCROLL_MAX_STEPS) || 600;
  const stepRatio =
    Number(window.__PDD_ERP_AUDIT_GOODS_SCROLL_STEP_RATIO) || 0.88;
  const restoreScroll =
    window.__PDD_ERP_AUDIT_GOODS_RESTORE_SCROLL !== false;

  /** 订单号白名单（null = 不过滤，返回全量） */
  const filterOrderNos = Array.isArray(window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS)
    ? new Set(window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS.map((s) => String(s).trim()))
    : null;

  /**
   * 勾选列表：
   *   - Array → 勾选指定订单号
   *   - true  → 与 filterOrderNos 联动（勾选过滤结果）
   *   - null / false → 不勾选
   */
  const checkOrderNosRaw = window.__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS;
  const checkOrderNos = Array.isArray(checkOrderNosRaw)
    ? new Set(checkOrderNosRaw.map((s) => String(s).trim()))
    : checkOrderNosRaw === true && filterOrderNos
    ? filterOrderNos
    : null;

  /** 勾选后是否自动点击「审核」按钮（⚠️ 真实提交，谨慎！） */
  const doAudit = !!window.__PDD_ERP_AUDIT_GOODS_DO_AUDIT;

  const log = [];
  if (filterOrderNos) {
    log.push(`订单号过滤模式：只抓 ${[...filterOrderNos].join(', ')}`);
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /* ─── 工具函数 ─── */

  /** 去掉图片 URL 的 ? 查询串与 # 片段（保留路径到扩展名） */
  function stripImgQuery(url) {
    if (!url || url.startsWith('data:')) return url;
    try {
      return url.replace(/[?#].*$/, '');
    } catch (e) {
      return url;
    }
  }

  /** 从订单号 td 取平台订单号（排除 style 标签文本污染） */
  function getOrderNo(td) {
    if (!td) return '';
    // 优先取 button-link 内的 span 文本（最精确）
    const link = td.querySelector('[data-testid="beast-core-button-link"] span');
    if (link) return link.textContent.trim();
    // 兜底：克隆后移除 style 节点再取 innerText
    const clone = td.cloneNode(true);
    clone.querySelectorAll('style').forEach((s) => s.remove());
    return (clone.innerText || '').trim().split('\n')[0].trim();
  }

  /** 从商品规格 td 提取商品列表 */
  function extractGoods(td) {
    if (!td) return [];
    const items = [...td.querySelectorAll('.sc-dUYKzm')];
    if (!items.length) {
      // 兼容：没有该 class 时直接读整格文本
      const img = td.querySelector('img');
      const text = (td.innerText || '').trim();
      return [
        {
          imgSrc: img ? stripImgQuery(img.src || img.getAttribute('data-src') || '') : '',
          title: text,
          spec: '',
          qty: 0,
        },
      ];
    }
    return items.map((item) => {
      /* 图片 */
      const img = item.querySelector('img');
      const imgRaw =
        (img && (img.src || img.getAttribute('data-src') || img.getAttribute('data-bimg-src'))) || '';
      const imgSrc = stripImgQuery(imgRaw);

      /* 标题 / 规格 / 数量 */
      let title = '', spec = '', qty = 0;
      const wrapper = item.querySelector('.content-wrapper');
      if (wrapper) {
        // 数量：.light-span 内 "x1" → 1
        const lightSpan = wrapper.querySelector('.light-span');
        if (lightSpan) {
          const qtyText = lightSpan.textContent.trim();
          qty = parseInt(qtyText.replace(/^[xX×]/u, ''), 10) || 0;
        }

        // 取所有直接子 span（非空、非 light-span）
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
   * 店铺 td[12]：拆出 shopName + actualAmount
   * DOM 结构：两个 [data-testid="beast-core-ellipsis"] 节点
   *   第一个 = 店铺名，第二个 = 实收金额（「实收：¥32.29」）
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
    const rawAmount = texts[1] || '';
    const actualAmount = rawAmount.replace(/^实收[：:]\s*/, '').trim() || rawAmount;
    return { shopName, actualAmount };
  }

  /* ─── 滚动探测（与 pdd-erp-order-all-table.js 同逻辑） ─── */

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
    const nodes = [wrap, ...wrap.querySelectorAll('*')];
    nodes.forEach((n) => {
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
    const targets = [
      root.querySelector(SCROLLBAR_ROOT_SEL),
      root.querySelector(BODY_WRAP_SEL),
      root,
    ].filter(Boolean);
    targets.forEach((t) => dispatchWheel(t, deltaY));
  }

  /* ─── 核心抓取 ─── */

  /**
   * 从当前视口 DOM 收集所有数据行，返回去重用 key → row 的 Map 条目数组。
   * key = 平台订单号（或 fallback = 图片+标题 hash）
   */
  function collectRowsFromDom() {
    const tbodies = [
      ...document.querySelectorAll(TBODY_SEL),
    ];
    const result = [];
    tbodies.forEach((tbody) => {
      [...tbody.querySelectorAll(ROW_SEL)].forEach((row) => {
        const tds = [...row.querySelectorAll('td')];
        const orderNo = getOrderNo(tds[ORDER_NO_TD_IDX]);
        const goods = extractGoods(tds[GOODS_TD_IDX]);
        const { shopName, actualAmount } = getShop(tds[SHOP_TD_IDX]);
        const key =
          orderNo ||
          `${goods.map((g) => g.imgSrc + g.title).join('|')}`;
        result.push({ key, orderNo, shopName, actualAmount, goods });
      });
    });
    return result;
  }

  /* ─── 主流程 ─── */

  const tableRoot = document.querySelector(TABLE_ROOT_SEL);
  if (!tableRoot) {
    return {
      ok: false,
      error: '未找到 beast-core-table，请确认页面已加载',
      log,
    };
  }

  // 等待 tbody 出现
  const waitStart = Date.now();
  while (!document.querySelector(TBODY_SEL) && Date.now() - waitStart < 10000) {
    await sleep(300);
  }
  if (!document.querySelector(TBODY_SEL)) {
    return { ok: false, error: 'tbody 超时未出现', log };
  }

  const rowMap = new Map(); // key → { orderNo, goods }

  function mergeCurrentRows() {
    const rows = collectRowsFromDom();
    let added = 0;
    rows.forEach(({ key, orderNo, shopName, actualAmount, goods }) => {
      // 白名单过滤：设置了 filterOrderNos 时只保留命中的订单号
      if (filterOrderNos && !filterOrderNos.has(orderNo)) return;
      if (!rowMap.has(key)) {
        rowMap.set(key, { orderNo, shopName, actualAmount, goods });
        added++;
      }
    });
    return added;
  }

  if (!autoScroll) {
    /* 仅抓当前视口 */
    mergeCurrentRows();
    log.push(`静态模式：共抓到 ${rowMap.size} 条`);
  } else {
    /* 自动滚动模式 */
    const scrollEl = findTableBodyScrollEl(tableRoot);
    log.push(scrollEl ? `找到滚动层：${scrollEl.tagName}.${scrollEl.className.slice(0, 40)}` : '未找到独立滚动层，改用 wheel 广播');

    // 先回顶
    if (scrollEl) scrollEl.scrollTop = 0;
    broadcastWheel(tableRoot, -9999);
    await sleep(pauseMs);

    mergeCurrentRows();
    log.push(`初始视口：${rowMap.size} 条`);

    let staleRounds = 0;
    const viewportH = scrollEl ? scrollEl.clientHeight : window.innerHeight;
    const stepPx = Math.max(100, Math.round(viewportH * stepRatio));

    for (let step = 0; step < maxSteps; step++) {
      // 滚动
      if (scrollEl) {
        scrollEl.scrollTop += stepPx;
      }
      broadcastWheel(tableRoot, stepPx);
      await sleep(pauseMs);

      const added = mergeCurrentRows();
      if (added === 0) {
        staleRounds++;
        if (staleRounds >= 3) {
          log.push(`连续 3 步无新数据，触底停止（step=${step + 1}）`);
          break;
        }
      } else {
        staleRounds = 0;
      }

      if (step % 10 === 0) {
        log.push(`step=${step + 1}，累计 ${rowMap.size} 条`);
      }
    }

    log.push(`滚动完成，共 ${rowMap.size} 条`);

    // 恢复顶部
    if (restoreScroll) {
      if (scrollEl) scrollEl.scrollTop = 0;
      broadcastWheel(tableRoot, -9999);
    }
  }

  /* ─── 构建 rows ─── */
  const rows = [...rowMap.values()];
  log.push(`最终输出 ${rows.length} 条订单数据`);

  /* ─── 勾选 checkbox ─── */
  const checkResult = [];
  if (checkOrderNos) {
    log.push(`开始勾选：目标 ${checkOrderNos.size} 个订单号`);
    const allRows = [...document.querySelectorAll(ROW_SEL)];
    for (const row of allRows) {
      const tds = [...row.querySelectorAll('td')];
      const linkSpan = tds[ORDER_NO_TD_IDX] &&
        tds[ORDER_NO_TD_IDX].querySelector('[data-testid="beast-core-button-link"] span');
      const orderNo = linkSpan ? linkSpan.textContent.trim() : '';
      if (!orderNo || !checkOrderNos.has(orderNo)) continue;

      const label = row.querySelector('label[data-testid="beast-core-checkbox"]');
      if (!label) {
        checkResult.push({ orderNo, ok: false, reason: '未找到 checkbox label' });
        continue;
      }
      // 用 input.checked 判断（比 class 名更可靠，class 名随版本可能变化）
      const input = label.querySelector('input');
      const isChecked = input ? input.checked : label.classList.contains('CBX_active_5-184-0');
      if (!isChecked) {
        label.click();
        await sleep(200);
      }
      const isCheckedAfter = input ? input.checked : label.classList.contains('CBX_active_5-184-0');
      checkResult.push({ orderNo, ok: isCheckedAfter, wasAlreadyChecked: isChecked });
    }
    log.push(`勾选完成：${checkResult.filter((r) => r.ok).length}/${checkOrderNos.size} 成功`);
  }

  /* ─── 提交审核 ─── */
  let auditResult = null;
  if (doAudit && checkOrderNos) {
    const successCount = checkResult.filter((r) => r.ok).length;
    if (successCount === 0) {
      auditResult = { ok: false, reason: '没有成功勾选的订单，跳过审核' };
      log.push('跳过审核：无成功勾选项');
    } else {
      // 等待页面响应勾选状态
      await sleep(300);
      const auditBtn = [...document.querySelectorAll('button[data-testid="beast-core-button"]')]
        .find((btn) => btn.textContent.trim() === '审核' && !btn.disabled);
      if (!auditBtn) {
        auditResult = { ok: false, reason: '未找到可用的「审核」按钮' };
        log.push('审核失败：未找到按钮');
      } else {
        auditBtn.click();
        await sleep(800);
        // 检测是否有确认弹窗（部分场景需要二次确认）
        const confirmBtn = [...document.querySelectorAll('button[data-testid="beast-core-button"]')]
          .filter((btn) => btn.offsetParent !== null)
          .find((btn) => /^(确定|确认|提交|ok)$/i.test(btn.textContent.trim()));
        if (confirmBtn) {
          confirmBtn.click();
          await sleep(500);
          log.push('检测到确认弹窗，已点击确认');
        }
        auditResult = { ok: true, auditedCount: successCount, confirmedModal: !!confirmBtn };
        log.push(`审核提交完成：${successCount} 条订单`);
      }
    }
  }

  /* ─── 同步 ─── */
  const syncBody = { rows };

  if (isPython) {
    return {
      ok: true,
      runMode: 'python',
      count: rows.length,
      rows,
      checkResult,
      auditResult,
      syncBody,
      syncUrl,
      log,
    };
  }

  // extension 模式
  let sync = { skipped: true, reason: '未配置 syncUrl' };
  if (syncUrl) {
    try {
      const ackKey = '__crPddAuditGoods_' + Date.now();
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
        log.push(`同步成功（扩展桥）：${syncUrl}`);
      } else {
        // 直接 fetch（仅非 CSP 严格域有效）
        try {
          const resp = await fetch(syncUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(syncBody),
          });
          const json = await resp.json().catch(() => null);
          sync = { via: 'fetch', status: resp.status, json };
          log.push(`同步成功（fetch）：${syncUrl} status=${resp.status}`);
        } catch (fe) {
          sync = { via: 'fetch', error: String(fe) };
          log.push(`同步失败：${fe}`);
        }
      }
    } catch (e) {
      sync = { error: String(e) };
      log.push(`同步异常：${e}`);
    }
  }

  return {
    ok: true,
    runMode: 'extension',
    count: rows.length,
    rows,
    checkResult,
    auditResult,
    sync,
    log,
  };
})();
