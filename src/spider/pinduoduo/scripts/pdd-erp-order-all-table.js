/**
 * 拼多多官方 ERP —— 全部订单列表 `beast-core-table` 双 table 抓取
 * 页面：https://mms.pinduoduo.com/erp/order/all*
 *
 * DOM（chrome-robot `page_get_dom` 实测）：
 * - 表头与表体为两个独立的 `<table>`：表头在 `[data-testid="beast-core-table-middle-header"]` → `thead[data-testid="beast-core-table-middle-thead"]`；
 *   表体在 `[data-testid="beast-core-table-middle-body"]` → `tbody[data-testid="beast-core-table-middle-tbody"]`。
 * - 数据行：`tr[data-testid="beast-core-table-body-tr"]`（每行一条订单，列与表头下标一一对应；首列为勾选框）。
 * - 虚拟列表下可能存在多个 `middle-tbody`，需 `querySelectorAll` 合并。
 *
 * 运行模式 `window.__PDD_ERP_ORDER_ALL_RUN_MODE`（执行前设置）：
 * - `'extension'`（默认）：若设置了 `window.__PDD_ERP_ORDER_ALL_SYNC_URL`，则经扩展桥 `postMessage` POST `{ rows }`（与 get_pdd_orders 同源桥接字段 `__crPdd`）。
 * - `'python'` / `'py'`：不 POST；返回 `syncBody` + `syncUrl` 供 Python `requests.post(json=syncBody)`。
 *
 * 可选：`window.__PDD_ERP_ORDER_ALL_SYNC_URL`（同步接口，默认不抓后上传则跳过）。
 *
 * **飞书多维表格**：`rows` 与 `syncBody.rows` 为与下述字段名完全一致的对象（无则空字符串 `''`），便于 Upsert / 写入接口直接使用：
 * 平台订单号、店铺、系统订单号、是否打印快递单、是否打印发货单、是否打印备货单、提醒、收件人、收件电话、收件省、收件市、收件区、收件详细地址、
 * ERP标签、ERP备注、标记、买家备注、卖家备注、发货剩余、付款时间、审核时间、发货时间、商品信息、商品快照、快递公司、快递单号、快递模板、订单状态、是否有售后、
 * 重量、体积、商品种类、商品总数、商品金额、运费、店铺优惠金额、平台优惠金额、实收金额、验货状态、称重状态、审核人、打印人、发货人。
 * 另可设 `window.__PDD_ERP_ORDER_ALL_INCLUDE_LEGACY === true` 时附带 `rowsLegacy`（含 `byHeader` 等调试字段）。
 *
 * **虚拟滚动 / 滚动加载**（默认开启）：
 * - `window.__PDD_ERP_ORDER_ALL_AUTO_SCROLL === false`：只抓当前视口 DOM（旧行为）。
 * - `window.__PDD_ERP_ORDER_ALL_SCROLL_PAUSE_MS`：每步滚动后等待渲染，默认 `500`。
 * - `window.__PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS`：最大滚动步数上限，默认 `600`（订单很多时可调大；步数×暂停≈耗时，注意 MCP/扩展 `timeout`）。
 * - `window.__PDD_ERP_ORDER_ALL_SCROLL_STEP_RATIO`：每步滚动视口高度比例，默认 `0.88`。
 * - `window.__PDD_ERP_ORDER_ALL_RESTORE_SCROLL !== false`：结束后是否 `scrollTop = 0`（默认恢复顶部）。
 * - `window.__PDD_ERP_ORDER_ALL_USE_WHEEL === true`：强制只用 wheel 不改写 scrollTop（调试用；默认优先 scrollTop + 辅助 wheel）。
 *
 * **飞书「提醒」DOM 兜底**（与表头文案无关，按列位取）：
 * 参考路径 `tbody tr > td:nth-child(2) > div > span > span`（第 1 列多为勾选，第 2 列为提醒文案）。
 * - `window.__PDD_ERP_REMINDER_TD_NTH`：从 1 开始，默认 `2`；设为 `0` 关闭该兜底。
 *
 * **商品快照**（飞书文本列）：从「商品信息」列 `td` 内收集 `img` 的 `src` / `data-src` 等、CSS `background url()`、`srcset` 首地址及 `alt`，空格拼接；写入前会去掉 URL 的 **`?` 查询串与 `#` 片段**（如 `...jpeg?imageView2/2/w/32/q/85` → `...jpeg`）。`__PDD_ERP_PRODUCT_SNAPSHOT_MAX_LEN` 默认 2000。
 *
 * **发货剩余 / 付款时间**：表头「发货剩余/支付时间」整格拆成飞书 **`发货剩余`**（文本）与 **`付款时间`**（`yyyy/MM/dd HH:mm`）；按行关键词与是否含日期启发式拆分。
 * 支持短日期 `MM-dd HH:mm 支付` 格式（如 `"- - 04-06 09:11 支付"`），自动补当前年份。
 */
(async function () {
  const today = new Date().toISOString().slice(0, 10);
  const DEFAULT_SYNC_URL = '';

  const sleep = function (ms) {
    return new Promise(function (r) {
      setTimeout(r, ms);
    });
  };

  /** 与飞书表字段名完全一致（顺序仅作文档，映射用 Set） */
  const FEISHU_FIELD_NAMES = [
    '平台订单号',
    '店铺',
    '系统订单号',
    '是否打印快递单',
    '是否打印发货单',
    '是否打印备货单',
    '提醒',
    '收件人',
    '收件电话',
    '收件省',
    '收件市',
    '收件区',
    '收件详细地址',
    'ERP标签',
    'ERP备注',
    '标记',
    '买家备注',
    '卖家备注',
    '发货剩余',
    '付款时间',
    '审核时间',
    '发货时间',
    '商品信息',
    '商品快照',
    '快递公司',
    '快递模板',
    '快递单号',
    '订单状态',
    '是否有售后',
    '重量',
    '体积',
    '商品种类',
    '商品总数',
    '商品金额',
    '运费',
    '店铺优惠金额',
    '平台优惠金额',
    '实收金额',
    '验货状态',
    '称重状态',
    '审核人',
    '打印人',
    '发货人',
  ];

  const TBODY_SEL = '[data-testid="beast-core-table-middle-tbody"]';
  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const TABLE_ROOT_SEL = '[data-testid="beast-core-table"]';
  const BODY_WRAP_SEL = '[data-testid="beast-core-table-middle-body"]';
  const SCROLLBAR_ROOT_SEL = '[data-testid="beast-core-scrollbar-root"]';

  /**
   * 实测 ERP 表体常见：`overflow: scroll hidden`（横向 scroll + 纵向 hidden），
   * 纵向滚动落在外层父节点；仅靠 overflowY===auto 会找不到。
   * 用「scrollTop 能否被改写」探测真实滚动层。
   */
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

  /** 自 tbody 向上、再在 middle-body 子树内找可纵向滚动的元素（取 scrollHeight 最大） */
  function findTableBodyScrollEl(root) {
    const candidates = [];

    const tbody = root.querySelector(TBODY_SEL);
    let p = tbody;
    while (p && p !== document.documentElement) {
      if (probeVerticalScrollable(p)) {
        candidates.push(p);
      }
      p = p.parentElement;
    }

    const wrap = root.querySelector(BODY_WRAP_SEL) || root;
    const nodes = [wrap].concat(Array.from(wrap.querySelectorAll('*')));
    for (let i = 0; i < nodes.length; i++) {
      if (probeVerticalScrollable(nodes[i])) {
        candidates.push(nodes[i]);
      }
    }

    const sr = root.querySelector(SCROLLBAR_ROOT_SEL);
    if (sr && probeVerticalScrollable(sr)) {
      candidates.push(sr);
    }

    if (!candidates.length) {
      return null;
    }

    let best = candidates[0];
    let bestH = best.scrollHeight;
    for (let j = 1; j < candidates.length; j++) {
      const c = candidates[j];
      if (c.scrollHeight >= bestH) {
        bestH = c.scrollHeight;
        best = c;
      }
    }
    return best;
  }

  /** 虚拟列表只响应 wheel 时：在容器上派发 wheel（需 bubbles） */
  function dispatchWheelScroll(target, deltaY) {
    if (!target) return;
    try {
      target.dispatchEvent(
        new WheelEvent('wheel', {
          bubbles: true,
          cancelable: true,
          deltaY: deltaY,
          deltaMode: 0,
          view: window,
        })
      );
    } catch (e) {
      try {
        const ev = document.createEvent('MouseEvents');
        ev.initEvent('wheel', true, true);
        Object.defineProperty(ev, 'deltaY', { value: deltaY });
        target.dispatchEvent(ev);
      } catch (e2) {
        /* ignore */
      }
    }
  }

  function wheelBroadcastTargets(root) {
    const list = [];
    const sr = root.querySelector(SCROLLBAR_ROOT_SEL);
    const bd = root.querySelector(BODY_WRAP_SEL);
    if (sr) {
      list.push(sr);
    }
    if (bd && bd !== sr) {
      list.push(bd);
    }
    list.push(root);
    return list;
  }

  function broadcastWheelOnTable(root, deltaY) {
    const list = wheelBroadcastTargets(root);
    for (let i = 0; i < list.length; i++) {
      dispatchWheelScroll(list[i], deltaY);
    }
  }

  /**
   * 在多个可能绑定 wheel 的节点上派发同一 delta，提高命中虚拟列表的概率。
   */
  async function wheelScrollTableChunk(root, deltaY, pauseMs) {
    if (!root) return;
    const focusEl =
      root.querySelector(SCROLLBAR_ROOT_SEL) || root.querySelector(BODY_WRAP_SEL) || root;
    try {
      if (focusEl && typeof focusEl.focus === 'function') {
        focusEl.tabIndex = -1;
        focusEl.focus({ preventScroll: true });
      }
    } catch (e) {
      /* ignore */
    }
    broadcastWheelOnTable(root, deltaY);
    await sleep(Math.max(30, pauseMs));
  }

  function simpleHash(s) {
    let h = 0;
    const t = String(s);
    for (let i = 0; i < t.length; i++) {
      h = ((h << 5) - h + t.charCodeAt(i)) | 0;
    }
    return String(h);
  }

  /** 虚拟列表复用 DOM 时用稳定键去重 */
  function rowDedupeKey(feishuRow) {
    const sys = String(feishuRow['系统订单号'] || '').trim();
    const plat = String(feishuRow['平台订单号'] || '').trim();
    if (sys) return 'sys:' + sys;
    if (plat) return 'plat:' + plat;
    return (
      'h:' +
      simpleHash(
        String(feishuRow['收件人'] || '') +
          '|' +
          String(feishuRow['付款时间'] || '') +
          '|' +
          String(feishuRow['实收金额'] || '') +
          '|' +
          String(feishuRow['收件详细地址'] || '').slice(0, 80)
      )
    );
  }

  /** @returns {'python' | 'extension'} */
  function resolveRunMode() {
    if (typeof window === 'undefined') return 'extension';
    const m = window.__PDD_ERP_ORDER_ALL_RUN_MODE;
    if (m == null || m === '') return 'extension';
    const s = String(m).trim().toLowerCase();
    if (s === 'python' || s === 'py') return 'python';
    return 'extension';
  }

  function findColIndex(headers, needle) {
    const compactNeedle = String(needle || '').replace(/\s/g, '');
    for (let i = 0; i < headers.length; i++) {
      const h = String(headers[i] || '').replace(/\s/g, '');
      if (h.indexOf(compactNeedle) !== -1) return i;
    }
    return -1;
  }

  /**
   * 仅从「表头 table」取列名（双 table 布局下 root 内第一个 table 可能是 body，必须用 middle-thead）。
   */
  function collectErpHeaderTexts() {
    const thead = document.querySelector('[data-testid="beast-core-table-middle-thead"]');
    if (!thead) return [];
    const ths = thead.querySelectorAll('th');
    const texts = [];
    ths.forEach(function (th) {
      const t = (th.innerText || '').trim();
      texts.push(t.split('\n')[0].trim());
    });
    return texts;
  }

  function getCellText(row, colIndex) {
    if (colIndex == null || colIndex < 0) return '';
    const cells = row.querySelectorAll('td');
    const td = cells[colIndex];
    let s = (td && td.innerText != null ? String(td.innerText) : '').trim().replace(/\s+/g, ' ');
    s = s.replace(/\.beast-core-ellipsis-\d+\s*\{[^}]*\}/g, ' ').replace(/\s+/g, ' ').trim();
    return s;
  }

  /**
   * 按「第 N 个 td」取提醒（与参考选择器 `tr > td:nth-child(2) > ... span` 对齐，用 td.innerText 已含嵌套 span）。
   */
  function getReminderDomByTdNth(tr) {
    if (!tr || !tr.querySelector) {
      return '';
    }
    let nth = 2;
    if (typeof window !== 'undefined' && window.__PDD_ERP_REMINDER_TD_NTH != null && window.__PDD_ERP_REMINDER_TD_NTH !== '') {
      const v = Math.floor(Number(window.__PDD_ERP_REMINDER_TD_NTH));
      if (Number.isFinite(v)) {
        nth = v;
      }
    }
    if (nth <= 0) {
      return '';
    }
    const td = tr.querySelector(':scope > td:nth-child(' + nth + ')');
    if (!td) {
      return '';
    }
    let s = (td.innerText != null ? String(td.innerText) : '').trim().replace(/\s+/g, ' ');
    s = s.replace(/\.beast-core-ellipsis-\d+\s*\{[^}]*\}/g, ' ').replace(/\s+/g, ' ').trim();
    return s;
  }

  function getTdByColIndex(tr, colIndex) {
    if (!tr || colIndex == null || colIndex < 0) {
      return null;
    }
    const cells = tr.querySelectorAll('td');
    return colIndex < cells.length ? cells[colIndex] : null;
  }

  /** 去掉 `?imageView2/...` 等查询参数与 `#` 片段；`data:` 内联图不截断 */
  function stripImageUrlQueryAndHash(raw) {
    let s = String(raw || '').trim();
    if (!s) {
      return '';
    }
    if (/^data:/i.test(s)) {
      return s;
    }
    const q = s.indexOf('?');
    if (q >= 0) {
      s = s.slice(0, q);
    }
    const h = s.indexOf('#');
    if (h >= 0) {
      s = s.slice(0, h);
    }
    return s.trim();
  }

  /**
   * 「商品信息」格内商品缩略图/快照：图片 URL + 可选 alt（文字字段供飞书同步）。
   */
  function extractProductSnapshotFromTd(td) {
    if (!td || td.nodeType !== 1) {
      return '';
    }
    const urls = [];
    const seen = {};
    function addUrl(u) {
      let s = String(u || '').trim();
      if (!s) {
        return;
      }
      if (s.indexOf('//') === 0) {
        s = 'https:' + s;
      }
      s = stripImageUrlQueryAndHash(s);
      if (!s) {
        return;
      }
      if (seen[s]) {
        return;
      }
      seen[s] = true;
      urls.push(s);
    }

    const imgs = td.querySelectorAll('img');
    for (let i = 0; i < imgs.length; i++) {
      const img = imgs[i];
      addUrl(img.getAttribute('src'));
      addUrl(img.getAttribute('data-src'));
      addUrl(img.getAttribute('data-original'));
      addUrl(img.getAttribute('data-lazy-src'));
    }

    const sources = td.querySelectorAll('source[srcset]');
    for (let s = 0; s < sources.length; s++) {
      const ss = sources[s].getAttribute('srcset');
      if (!ss) {
        continue;
      }
      const parts = ss.split(',');
      for (let p = 0; p < parts.length; p++) {
        const u = parts[p].trim().split(/\s+/)[0];
        addUrl(u);
      }
    }

    const urlEls = td.querySelectorAll('[style*="url("]');
    for (let e = 0; e < urlEls.length; e++) {
      const st = urlEls[e].getAttribute('style') || '';
      const re = /url\(\s*["']?([^"')]+)["']?\s*\)/gi;
      let m;
      while ((m = re.exec(st))) {
        addUrl(m[1]);
      }
    }

    const alts = [];
    const altSeen = {};
    for (let j = 0; j < imgs.length; j++) {
      const a = (imgs[j].getAttribute('alt') || '').trim();
      if (a && !altSeen[a]) {
        altSeen[a] = true;
        alts.push(a);
      }
    }

    let out = urls.join(' ');
    if (alts.length) {
      const altPart = alts.join(' | ');
      out = out ? out + ' 图注:' + altPart : altPart;
    }
    let maxLen = 2000;
    if (typeof window !== 'undefined' && Number(window.__PDD_ERP_PRODUCT_SNAPSHOT_MAX_LEN) > 0) {
      maxLen = Math.floor(Number(window.__PDD_ERP_PRODUCT_SNAPSHOT_MAX_LEN));
    }
    return out
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, maxLen);
  }

  function extractMobileFromText(s) {
    const m = String(s || '').match(/1[3-9]\d{9}/);
    return m ? m[0] : '';
  }

  function emptyFeishuRow() {
    const o = {};
    for (let i = 0; i < FEISHU_FIELD_NAMES.length; i++) {
      o[FEISHU_FIELD_NAMES[i]] = '';
    }
    return o;
  }

  function parseYuan(s) {
    if (s == null || s === '') return null;
    const t = String(s)
      .replace(/,/g, '')
      .replace(/元|¥|￥/g, '')
      .replace(/\s/g, '')
      .trim();
    const n = parseFloat(t);
    return Number.isFinite(n) ? n : null;
  }

  function formatYuan2(n) {
    if (n == null || !Number.isFinite(n)) return '';
    return n.toFixed(2);
  }

  function formatWeight1(n) {
    if (n == null || !Number.isFinite(n)) return '';
    return (Math.round(n * 10) / 10).toFixed(1);
  }

  function formatInt(n) {
    if (n == null || !Number.isFinite(n)) return '';
    return String(Math.round(n));
  }

  /** 是否含 yyyy-(m)m-(d)d 或中文年月日 / `.` 分隔日期 */
  function lineHasCalendarDate(line) {
    const s = String(line || '');
    return (
      /(\d{4})\s*[年\/.\-]\s*\d{1,2}\s*[月\/.\-]\s*\d{1,2}/.test(s) ||
      /\b\d{4}-\d{1,2}-\d{1,2}\b/.test(s)
    );
  }

  /** 是否含短日期 MM-dd HH:mm（无年份，常见于 ERP 发货剩余列的支付时间） */
  function lineHasShortDateTime(line) {
    return /(?:^|[^\d])(\d{1,2})\s*[-\/]\s*(\d{1,2})\s+(\d{1,2}):(\d{2})/.test(String(line || ''));
  }

  /**
   * 「发货剩余/支付时间」单列内拆成：发货剩余文案 + 供 formatFeishuDateTime 解析的支付相关串。
   */
  function parseShipRemainAndPayTime(raw) {
    const t = String(raw || '')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .trim();
    if (!t) {
      return { remain: '', payForFormat: '' };
    }

    const lines = t
      .split('\n')
      .map(function (l) {
        return l.replace(/\s+/g, ' ').trim();
      })
      .filter(Boolean);

    if (!lines.length) {
      return { remain: '', payForFormat: '' };
    }

    var splitLines = [];
    for (var si = 0; si < lines.length; si++) {
      var spm = lines[si].match(/(\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}\s*支付)/);
      if (spm && spm.index > 0) {
        var bef = lines[si].slice(0, spm.index).trim();
        if (bef) splitLines.push(bef);
        splitLines.push(spm[1].trim());
        var aft = lines[si].slice(spm.index + spm[0].length).trim();
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
      } else if (/发货\s*剩余|距\s*发\s*货|剩余\s*时间|超时未发|倒\s*计\s*时|发\s*货\s*剩/.test(L)) {
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
          if (k !== di) {
            remainLines.push(splitLines[k]);
          }
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
      if (!lineHasCalendarDate(other)) {
        remainJoined = other;
      }
    }

    let cleanRemain = remainJoined.replace(/^[\s\-\|]+$/, '').trim();
    return {
      remain: cleanRemain.slice(0, 500),
      payForFormat: payJoined,
    };
  }

  /** 付款时间等：尽量输出 yyyy/MM/dd HH:mm（支持 `.` 分隔、可选秒） */
  function formatFeishuDateTime(input) {
    const s = String(input || '').trim();
    if (!s) {
      return '';
    }
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

  /**
   * 从「收件信息」格解析收件人/电话/省市区/详细（兼容「姓名 + 脱敏手机」与「省 市 区 详细」分行）。
   */
  function parseReceiverBlock(full) {
    const out = {
      收件人: '',
      收件电话: '',
      收件省: '',
      收件市: '',
      收件区: '',
      收件详细地址: '',
    };
    const raw = String(full || '').replace(/\r/g, '\n').trim();
    if (!raw) return out;

    const lines = raw
      .split('\n')
      .map(function (l) {
        return l.replace(/\s+/g, ' ').trim();
      })
      .filter(Boolean);

    const phone = extractMobileFromText(raw);
    if (phone) out.收件电话 = phone;

    let addrLine = '';
    if (lines.length >= 1) {
      const line0 = lines[0];
      if (phone) {
        const idx = line0.indexOf(phone);
        if (idx !== -1) {
          out.收件人 = line0.slice(0, idx).replace(/\s+$/, '').replace(/[\s*]+$/, '').trim();
        } else {
          const parts = line0.split(/\s+/);
          out.收件人 = parts[0] || '';
        }
      } else {
        const mStar = line0.match(/^(.+?)\s+([\d\*]{8,20})$/);
        if (mStar) {
          out.收件人 = mStar[1].trim();
          if (!out.收件电话) out.收件电话 = mStar[2].trim();
        } else {
          out.收件人 = line0.split(/\s+/)[0] || line0.slice(0, 24);
        }
      }
    }
    if (lines.length >= 2) {
      addrLine = lines.slice(1).join(' ');
    } else if (/省|市|区|县|自治区/.test(lines[0] || '') && !out.收件人) {
      addrLine = lines[0];
    }

    if (addrLine) {
      out.收件详细地址 = addrLine;
      const prov = addrLine.match(
        /^([\u4e00-\u9fa5]+?(?:省|自治区)|北京市|天津市|上海市|重庆市)/
      );
      if (prov) {
        out.收件省 = prov[1];
        let rest = addrLine.slice(prov[0].length).trim();
        const city = rest.match(
          /^([\u4e00-\u9fa5]+?(?:市|州|盟|地区|自治州))/
        );
        if (city) {
          out.收件市 = city[1];
          rest = rest.slice(city[0].length).trim();
          const dist = rest.match(
            /^([\u4e00-\u9fa5]+?(?:区|县|市|旗|新区|开发区))/
          );
          if (dist) {
            out.收件区 = dist[1];
            const tail = rest.slice(dist[0].length).trim();
            if (tail) out.收件详细地址 = tail;
          }
        }
      }
    }

    return out;
  }

  /** 从「快递信息」格拆快递公司 / 单号（启发式） */
  function parseExpressBlock(text) {
    const t = String(text || '').replace(/\s+/g, ' ').trim();
    if (!t) return { 快递公司: '', 快递单号: '' };

    const waybill = t.match(/\b([A-Za-z0-9]{10,30})\b/);
    const num = t.match(/(1[0-9]{11}|[0-9]{12,20})/);

    let 单号 = '';
    if (waybill) 单号 = waybill[1];
    else if (num && !extractMobileFromText(t)) 单号 = num[1];

    let 公司 = t;
    if (单号) {
      公司 = t
        .replace(单号, '')
        .replace(/单号|运单|快递|：/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    }

    const common = ['顺丰', '圆通', '中通', '申通', '韵达', '极兔', '邮政', 'EMS', '京东', '德邦', '百世'];
    for (let i = 0; i < common.length; i++) {
      if (t.indexOf(common[i]) !== -1) {
        if (!公司 || 公司.length > 40) 公司 = common[i];
        break;
      }
    }

    return { 快递公司: 公司.slice(0, 80), 快递单号: 单号.slice(0, 80) };
  }

  /** 从「店铺/实收金额」拆店铺名与实收 */
  function parseShopAndReceived(text) {
    const t = String(text || '').replace(/\s+/g, ' ').trim();
    const out = { 店铺: '', 实收金额: '' };
    if (!t) return out;

    const yuan = parseYuan(t);
    if (yuan != null) out.实收金额 = formatYuan2(yuan);

    const m = t.match(/实收[：:\s]*([\d.,]+)/);
    if (m) {
      const v = parseYuan(m[1]);
      if (v != null) out.实收金额 = formatYuan2(v);
    }

    let name = t
      .replace(/实收[：:\s]*[\d.,]+\s*元?/g, ' ')
      .replace(/¥|￥|元/g, ' ')
      .replace(/[\d.,]+\s*$/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (name) out.店铺 = name.slice(0, 120);
    return out;
  }

  /** 打印状态列 → 三个是否字段（文本） */
  function splitPrintFlags(printText) {
    const t = String(printText || '').replace(/\s+/g, ' ').trim();
    const empty = { 是否打印快递单: '', 是否打印发货单: '', 是否打印备货单: '' };
    if (!t) return empty;

    function yesNoCell(sub) {
      const s = String(sub || '').trim();
      if (!s) return '';
      if (/已打印|是|√|✓|已打|完成/i.test(s)) return '是';
      if (/未|否|无|待|未打/i.test(s)) return '否';
      return s.slice(0, 20);
    }

    if (/[\/／|｜]/.test(t)) {
      const parts = t.split(/[\/／|｜]/);
      return {
        是否打印快递单: yesNoCell(parts[0]),
        是否打印发货单: yesNoCell(parts[1]),
        是否打印备货单: yesNoCell(parts[2]),
      };
    }

    return {
      是否打印快递单: yesNoCell(t),
      是否打印发货单: '',
      是否打印备货单: '',
    };
  }

  function slugHeader(h, i, used) {
    let base = String(h || '').trim() || 'col_' + i;
    base = base.replace(/\s+/g, '_').replace(/[\/\\]/g, '_');
    base = base.replace(/[^\w\u4e00-\u9fff_]/g, '').slice(0, 56) || 'col_' + i;
    let key = base;
    let n = 2;
    while (used[key]) {
      key = base + '_' + n;
      n++;
    }
    used[key] = true;
    return key;
  }

  /** th 列数与 tr 的 td 数在 ERP 页一致时 offset=0；若表头多一列空占位则减 1 */
  function detectDataTdOffset(headers, sampleRow) {
    if (!headers.length || !sampleRow) return 0;
    const tdCount = sampleRow.querySelectorAll('td').length;
    if (tdCount === headers.length) return 0;
    if (tdCount === headers.length - 1) return 1;
    return 0;
  }

  function normalizeColIndicesForDataRow(col, offset) {
    if (!offset || offset <= 0) return col;
    function adj(v) {
      if (v == null || v < 0) return v;
      const n = v - offset;
      return n >= 0 ? n : 0;
    }
    const out = {};
    for (const k in col) {
      if (Object.prototype.hasOwnProperty.call(col, k)) {
        out[k] = adj(col[k]);
      }
    }
    return out;
  }

  function resolveErpColumnIndices(headers) {
    const h = headers && headers.length ? headers : [];
    function idx(needles) {
      if (typeof needles === 'string') return findColIndex(h, needles);
      for (let i = 0; i < needles.length; i++) {
        const j = findColIndex(h, needles[i]);
        if (j >= 0) return j;
      }
      return -1;
    }

    let orderOp = idx(['订单编号/操作', '订单编号']);
    return {
      platform: idx('平台订单号'),
      orderOp: orderOp,
      recv: idx('收件信息'),
      remarkBuyer: idx('留言备注'),
      systemTag: idx(['系统标签备注', '系统标签']),
      payOrRemain: idx(['发货剩余/支付时间', '发货剩余', '支付时间']),
      product: idx(['商品信息', '商品']),
      express: idx('快递信息'),
      expressTpl: idx('快递模板'),
      warehouse: idx('仓库'),
      status: idx('订单状态'),
      /** 飞书「提醒」：优先表头含「提醒」的独立列，勿与「异常处理建议」混为一谈 */
      remind: idx(['催付提醒', '超时提醒', '订单提醒', '提醒', '提示']),
      abnormal: idx(['异常处理建议', '异常处理']),
      shopAmt: idx(['店铺/实收金额', '店铺/实收', '店铺']),
      weight: idx(['重量（kg）', '重量']),
      volume: idx(['体积（m³）', '体积']),
      kind: idx('商品种类'),
      goodsCount: idx('商品总数'),
      goodsAmt: idx('商品金额'),
      shopDisc: idx('店铺优惠金额'),
      platDisc: idx('平台优惠金额'),
      inspect: idx('验货状态'),
      weigh: idx('称重状态'),
      print: idx('打印状态'),
    };
  }

  function parseOrderNoFromCell(text) {
    const s = String(text || '');
    const m = s.match(/([0-9]{6}-[0-9]{10,})/);
    return m ? m[1].trim() : '';
  }

  function buildFeishuRowFromTr(tr, col) {
    const row = emptyFeishuRow();

    const recvText = col.recv >= 0 ? getCellText(tr, col.recv) : '';
    const recv = parseReceiverBlock(recvText);
    row['收件人'] = recv.收件人;
    row['收件电话'] = recv.收件电话;
    row['收件省'] = recv.收件省;
    row['收件市'] = recv.收件市;
    row['收件区'] = recv.收件区;
    row['收件详细地址'] = recv.收件详细地址;

    const platformText = col.platform >= 0 ? getCellText(tr, col.platform) : '';
    row['平台订单号'] = platformText.slice(0, 120);

    const orderOpText = col.orderOp >= 0 ? getCellText(tr, col.orderOp) : '';
    const sysNo = parseOrderNoFromCell(orderOpText) || parseOrderNoFromCell(platformText);
    row['系统订单号'] = (sysNo || orderOpText.replace(/\s+/g, ' ').trim()).slice(0, 80);

    const shopCell = col.shopAmt >= 0 ? getCellText(tr, col.shopAmt) : '';
    const shopBlock = parseShopAndReceived(shopCell);
    row['店铺'] = shopBlock.店铺;
    row['实收金额'] = shopBlock.实收金额;

    const printParts =
      col.print >= 0 ? splitPrintFlags(getCellText(tr, col.print)) : { 是否打印快递单: '', 是否打印发货单: '', 是否打印备货单: '' };
    row['是否打印快递单'] = printParts.是否打印快递单;
    row['是否打印发货单'] = printParts.是否打印发货单;
    row['是否打印备货单'] = printParts.是否打印备货单;

    const domRemind = getReminderDomByTdNth(tr);
    const remindText = col.remind >= 0 ? getCellText(tr, col.remind).trim() : '';
    const abnormalText = col.abnormal >= 0 ? getCellText(tr, col.abnormal).trim() : '';
    const tipSegs = [];
    function pushTipUnique(s) {
      const t = String(s || '').trim();
      if (!t) {
        return;
      }
      for (let i = 0; i < tipSegs.length; i++) {
        if (tipSegs[i] === t) {
          return;
        }
      }
      tipSegs.push(t);
    }
    pushTipUnique(domRemind);
    pushTipUnique(remindText);
    pushTipUnique(abnormalText);
    row['提醒'] = tipSegs.length ? tipSegs.join(' | ').slice(0, 500) : '';
    row['是否有售后'] = /售后|退款|退货|换货|维权/.test(abnormalText + remindText + domRemind) ? '是' : '';

    row['ERP标签'] = col.systemTag >= 0 ? getCellText(tr, col.systemTag).slice(0, 200) : '';
    row['ERP备注'] = '';
    row['标记'] = '';
    row['买家备注'] = col.remarkBuyer >= 0 ? getCellText(tr, col.remarkBuyer).slice(0, 500) : '';
    row['卖家备注'] = '';

    const payOrRemainRaw = col.payOrRemain >= 0 ? getCellText(tr, col.payOrRemain) : '';
    const shipPay = parseShipRemainAndPayTime(payOrRemainRaw);
    row['发货剩余'] = shipPay.remain;
    row['付款时间'] = formatFeishuDateTime(shipPay.payForFormat);

    row['审核时间'] = '';
    row['发货时间'] = '';

    row['商品信息'] = col.product >= 0 ? getCellText(tr, col.product).slice(0, 1000) : '';
    const productTd = getTdByColIndex(tr, col.product);
    row['商品快照'] = productTd ? extractProductSnapshotFromTd(productTd) : '';

    const ex = col.express >= 0 ? parseExpressBlock(getCellText(tr, col.express)) : { 快递公司: '', 快递单号: '' };
    row['快递公司'] = ex.快递公司;
    row['快递单号'] = ex.快递单号;
    row['快递模板'] = col.expressTpl >= 0 ? getCellText(tr, col.expressTpl).slice(0, 120) : '';

    row['订单状态'] = col.status >= 0 ? getCellText(tr, col.status).slice(0, 200) : '';

    const wRaw = col.weight >= 0 ? getCellText(tr, col.weight).replace(/kg|KG|（kg）/g, '') : '';
    const w = parseYuan(wRaw);
    row['重量'] = w != null ? formatWeight1(w) : '';

    const vRaw = col.volume >= 0 ? getCellText(tr, col.volume).replace(/m³|m3|（m³）/gi, '') : '';
    const v = parseYuan(vRaw);
    row['体积'] = v != null ? formatInt(v) : '';

    row['商品种类'] = col.kind >= 0 ? getCellText(tr, col.kind).slice(0, 80) : '';

    const gcRaw = col.goodsCount >= 0 ? getCellText(tr, col.goodsCount) : '';
    let gci = null;
    const gcm = String(gcRaw).match(/\d+/);
    if (gcm) gci = parseInt(gcm[0], 10);
    row['商品总数'] = gci != null && Number.isFinite(gci) ? formatInt(gci) : '';

    const ga = col.goodsAmt >= 0 ? parseYuan(getCellText(tr, col.goodsAmt)) : null;
    row['商品金额'] = ga != null ? formatYuan2(ga) : '';

    row['运费'] = '';

    const sd = col.shopDisc >= 0 ? parseYuan(getCellText(tr, col.shopDisc)) : null;
    row['店铺优惠金额'] = sd != null ? formatYuan2(sd) : '';

    const pd = col.platDisc >= 0 ? parseYuan(getCellText(tr, col.platDisc)) : null;
    row['平台优惠金额'] = pd != null ? formatYuan2(pd) : '';

    row['验货状态'] = col.inspect >= 0 ? getCellText(tr, col.inspect).slice(0, 80) : '';
    row['称重状态'] = col.weigh >= 0 ? getCellText(tr, col.weigh).slice(0, 80) : '';

    row['审核人'] = '';
    row['打印人'] = '';
    row['发货人'] = '';

    if (col.warehouse >= 0) {
      const wh = getCellText(tr, col.warehouse).slice(0, 80);
      if (wh) row['标记'] = wh;
    }

    return row;
  }

  function tryExtensionBridgeSync(payload) {
    return new Promise(function (resolve) {
      const id = 'pdd_' + Date.now() + '_' + Math.random().toString(36).slice(2);
      let acked = false;
      let settled = false;
      function finish(val) {
        if (settled) return;
        settled = true;
        window.removeEventListener('message', onMsg);
        clearTimeout(shortTimer);
        clearTimeout(longTimer);
        resolve(val);
      }
      const shortTimer = setTimeout(function () {
        if (!acked) finish(null);
      }, 400);
      const longTimer = setTimeout(function () {
        if (acked) finish({ ok: false, error: '扩展通道超时' });
      }, 120000);
      function onMsg(e) {
        if (!e.data) return;
        if (e.origin && location.origin && e.origin !== location.origin) return;
        if (e.data.__crPddAck === 1 && e.data.id === id) {
          acked = true;
          return;
        }
        if (e.data.__crPddReply === 1 && e.data.id === id) {
          finish(e.data.payload != null ? e.data.payload : { ok: false, error: 'empty bridge reply' });
        }
      }
      window.addEventListener('message', onMsg);
      window.postMessage({ __crPdd: 1, id: id, params: payload }, '*');
    });
  }

  function collectDataTrElements() {
    const tbodyList = Array.from(document.querySelectorAll(TBODY_SEL));
    const allRows = [];
    for (let bi = 0; bi < tbodyList.length; bi++) {
      const trs = tbodyList[bi].querySelectorAll(ROW_SEL);
      for (let i = 0; i < trs.length; i++) {
        allRows.push(trs[i]);
      }
    }
    return { allRows, tbodyCount: tbodyList.length };
  }

  function buildLegacyForTr(tr, col, headers, headerKeys, dataTdOffset) {
    const byHeader = {};
    const cells = tr.querySelectorAll('td');
    for (let c = 0; c < headers.length; c++) {
      const key = headerKeys[c];
      const ti = c - dataTdOffset;
      byHeader[key] = ti >= 0 && ti < cells.length ? getCellText(tr, ti) : '';
    }
    const orderOpText = col.orderOp >= 0 ? getCellText(tr, col.orderOp) : '';
    const platformText = col.platform >= 0 ? getCellText(tr, col.platform) : '';
    const recvText = col.recv >= 0 ? getCellText(tr, col.recv) : '';
    return {
      orderNo: parseOrderNoFromCell(orderOpText) || parseOrderNoFromCell(platformText) || '',
      platformOrderNo: platformText.slice(0, 120),
      receiverInfo: recvText.slice(0, 500),
      mobile: extractMobileFromText(recvText),
      byHeader,
    };
  }

  async function extractErpOrderAllTable() {
    const log = [];
    const root = document.querySelector(TABLE_ROOT_SEL);
    if (!root) {
      return {
        error: '未找到 ' + TABLE_ROOT_SEL,
        date: today,
        log: log.concat(['请先打开 ERP 全部订单页并等待表格加载']),
        headers: [],
        rows: [],
        feishuFieldNames: FEISHU_FIELD_NAMES,
        count: 0,
      };
    }

    const headers = collectErpHeaderTexts();
    if (!headers.length) {
      return {
        error: '未找到表头 thead[data-testid=beast-core-table-middle-thead]',
        date: today,
        log,
        headers: [],
        rows: [],
        feishuFieldNames: FEISHU_FIELD_NAMES,
        count: 0,
      };
    }

    let { allRows, tbodyCount } = collectDataTrElements();
    if (tbodyCount === 0) {
      return {
        error: '未找到表格 tbody（' + TBODY_SEL + '）',
        date: today,
        log,
        headers,
        rows: [],
        feishuFieldNames: FEISHU_FIELD_NAMES,
        count: 0,
      };
    }

    log.push('表头列数: ' + headers.length + '，tbody 块: ' + tbodyCount + '，首屏数据行: ' + allRows.length);

    if (!allRows.length) {
      return { date: today, log, headers, rows: [], feishuFieldNames: FEISHU_FIELD_NAMES, count: 0 };
    }

    const dataTdOffset = detectDataTdOffset(headers, allRows[0]);
    log.push('dataTdOffset: ' + dataTdOffset + '（表头列与 td 对齐校正）');
    const col = normalizeColIndicesForDataRow(resolveErpColumnIndices(headers), dataTdOffset);

    const used = {};
    const headerKeys = headers.map(function (h, i) {
      return slugHeader(h, i, used);
    });

    const includeLegacy =
      typeof window !== 'undefined' && window.__PDD_ERP_ORDER_ALL_INCLUDE_LEGACY === true;

    const autoScroll =
      typeof window === 'undefined' || window.__PDD_ERP_ORDER_ALL_AUTO_SCROLL !== false;

    let rows = [];
    let rowsLegacy = [];
    let scrollMeta = { autoScroll: false, steps: 0, uniqueKeys: 0, scrollFound: false };

    if (!autoScroll) {
      for (let r = 0; r < allRows.length; r++) {
        const tr = allRows[r];
        rows.push(buildFeishuRowFromTr(tr, col));
        if (includeLegacy) {
          rowsLegacy.push(buildLegacyForTr(tr, col, headers, headerKeys, dataTdOffset));
        }
      }
    } else {
      const scrollEl = findTableBodyScrollEl(root);
      const pause = Math.max(120, Number(window.__PDD_ERP_ORDER_ALL_SCROLL_PAUSE_MS) || 500);
      const maxSteps = Math.max(10, Number(window.__PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS) || 600);
      const stepRatio = Math.min(1, Math.max(0.2, Number(window.__PDD_ERP_ORDER_ALL_SCROLL_STEP_RATIO) || 0.88));
      const restoreScroll =
        typeof window === 'undefined' || window.__PDD_ERP_ORDER_ALL_RESTORE_SCROLL !== false;

      const wheelSurface =
        root.querySelector(SCROLLBAR_ROOT_SEL) ||
        root.querySelector(BODY_WRAP_SEL) ||
        root;
      const useWheel =
        typeof window !== 'undefined' && window.__PDD_ERP_ORDER_ALL_USE_WHEEL === true;
      scrollMeta = {
        autoScroll: true,
        steps: 0,
        uniqueKeys: 0,
        scrollFound: !!scrollEl,
        scrollVia: scrollEl ? 'scrollTop+wheel' : wheelSurface ? 'wheel' : 'none',
        pauseMs: pause,
        maxSteps: maxSteps,
      };

      if (scrollEl) {
        scrollEl.scrollTop = 0;
        await sleep(pause);
        log.push('滚动采集：已探测到可设 scrollTop 的节点（scrollHeight=' + scrollEl.scrollHeight + '）');
      } else if (wheelSurface) {
        log.push(
          '滚动采集：未探测到 scrollTop 滚动层，改用 wheel 事件驱动（目标: ' +
            (wheelSurface.getAttribute && wheelSurface.getAttribute('data-testid')
              ? 'data-testid=' + wheelSurface.getAttribute('data-testid')
              : wheelSurface.tagName) +
            '）'
        );
      } else {
        log.push('滚动采集：无表体节点，仅采集当前 DOM 行');
      }

      const merged = new Map();
      let steps = 0;
      let stuckAtBottom = 0;
      let stuckNoNewWheel = 0;

      while (steps < maxSteps) {
        const pack = collectDataTrElements();
        allRows = pack.allRows;
        let newKeys = 0;
        for (let r = 0; r < allRows.length; r++) {
          const row = buildFeishuRowFromTr(allRows[r], col);
          const k = rowDedupeKey(row);
          if (!merged.has(k)) {
            merged.set(k, row);
            newKeys++;
          }
        }

        log.push(
          '滚动采集 step ' +
            steps +
            ': DOM 行 ' +
            allRows.length +
            '，累计唯一订单 ' +
            merged.size +
            '，本批新键 ' +
            newKeys
        );

        const stepPx = scrollEl
          ? Math.max(48, Math.floor(scrollEl.clientHeight * stepRatio))
          : Math.max(
              200,
              Math.floor(
                (wheelSurface.clientHeight || root.clientHeight || 400) * stepRatio
              )
            );

        if (scrollEl && !useWheel) {
          const atBottom =
            scrollEl.scrollTop + scrollEl.clientHeight >= scrollEl.scrollHeight - 12;
          if (atBottom) {
            if (newKeys === 0) {
              stuckAtBottom++;
            } else {
              stuckAtBottom = 0;
            }
            if (stuckAtBottom >= 3) {
              log.push('滚动采集：已触底且连续 3 次无新订单键，结束');
              break;
            }
            broadcastWheelOnTable(root, Math.min(500, Math.floor(stepPx * 1.1)));
            await sleep(Math.max(100, Math.floor(pause * 0.55)));
          } else {
            stuckAtBottom = 0;
            scrollEl.scrollTop = Math.min(scrollEl.scrollTop + stepPx, scrollEl.scrollHeight);
            broadcastWheelOnTable(root, stepPx);
            await sleep(pause);
          }
        } else if (wheelSurface) {
          if (newKeys === 0) {
            stuckNoNewWheel++;
          } else {
            stuckNoNewWheel = 0;
          }
          if (stuckNoNewWheel >= 12) {
            log.push('滚动采集：wheel 驱动结束（连续 12 步无新订单键）');
            break;
          }
          await wheelScrollTableChunk(root, stepPx, pause);
        }
        steps++;
      }

      scrollMeta.steps = steps;
      scrollMeta.uniqueKeys = merged.size;

      if (scrollEl && restoreScroll) {
        scrollEl.scrollTop = 0;
      }

      rows = Array.from(merged.values());
      if (includeLegacy) {
        log.push('滚动模式下未生成 rowsLegacy（避免与虚拟列表 DOM 错位）；可设 __PDD_ERP_ORDER_ALL_AUTO_SCROLL=false 仅首屏并开 LEGACY');
      }
    }

    log.push('飞书字段行数: ' + rows.length + '（键名与多维表格字段一致）');

    const out = {
      date: today,
      count: rows.length,
      headers,
      headerKeys,
      rows,
      feishuFieldNames: FEISHU_FIELD_NAMES,
      log,
      scroll: scrollMeta,
      pageHint: autoScroll
        ? '已尝试滚动加载并去重合并；订单极多时可调大 __PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS 或 __PDD_ERP_ORDER_ALL_SCROLL_PAUSE_MS'
        : '已关闭自动滚动，仅当前视口；可设 __PDD_ERP_ORDER_ALL_AUTO_SCROLL=true（默认）滚动整表',
    };
    if (includeLegacy && rowsLegacy.length) {
      out.rowsLegacy = rowsLegacy;
    }
    return out;
  }

  async function syncRows(rows) {
    let url = '';
    if (typeof window !== 'undefined' && window.__PDD_ERP_ORDER_ALL_SYNC_URL) {
      url = String(window.__PDD_ERP_ORDER_ALL_SYNC_URL).trim();
    }
    if (!url) url = DEFAULT_SYNC_URL;
    if (!url) {
      return { ok: false, skipped: true, reason: 'no_sync_url', via: 'none' };
    }

    const body = { rows: rows };
    const bridged = await tryExtensionBridgeSync({ url: url, body: body });
    if (bridged !== null) {
      return {
        ok: !!bridged.ok,
        status: bridged.status,
        json: bridged.json,
        error: bridged.error,
        via: 'extension',
      };
    }
    return {
      ok: false,
      error: '未收到扩展桥接，请安装扩展并刷新；或未设置有效 __PDD_ERP_ORDER_ALL_SYNC_URL',
      via: 'none',
    };
  }

  async function main() {
    const result = await extractErpOrderAllTable();
    if (result.error) {
      result.sync = { skipped: true, reason: 'extract_error' };
      console.log('[pdd-erp-order-all-table]', result);
      return result;
    }
    if (!result.rows || !result.rows.length) {
      result.sync = { skipped: true, reason: 'no_rows' };
      result.log.push('同步：跳过（无数据行）');
      console.log('[pdd-erp-order-all-table]', result);
      return result;
    }

    let syncUrl = '';
    if (typeof window !== 'undefined' && window.__PDD_ERP_ORDER_ALL_SYNC_URL) {
      syncUrl = String(window.__PDD_ERP_ORDER_ALL_SYNC_URL).trim();
    }

    if (resolveRunMode() === 'python') {
      result.runMode = 'python';
      result.syncBody = { rows: result.rows };
      result.syncUrl = syncUrl || DEFAULT_SYNC_URL;
      result.sync = { skipped: true, reason: 'python_mode' };
      result.log.push(
        '同步：python 模式；请用 requests.post(result.syncUrl, json=result.syncBody)（若 syncUrl 为空则仅使用 rows）'
      );
      console.log('[pdd-erp-order-all-table]', result);
      return result;
    }

    if (!syncUrl) {
      result.sync = { skipped: true, reason: 'no_sync_url' };
      result.log.push('同步：未设置 __PDD_ERP_ORDER_ALL_SYNC_URL，仅返回表格数据');
      console.log('[pdd-erp-order-all-table]', result);
      return result;
    }

    try {
      const sync = await syncRows(result.rows);
      result.sync = sync;
      result.log.push('同步：' + (sync.ok ? 'ok' : 'fail') + ' via ' + (sync.via || '?'));
    } catch (e) {
      result.sync = { ok: false, error: e && e.message ? e.message : String(e) };
      result.log.push('同步：异常 ' + result.sync.error);
    }
    console.log('[pdd-erp-order-all-table]', result);
    return result;
  }

  return await main();
})();
