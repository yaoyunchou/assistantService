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

  /* ─── 运行配置汇总（第一条日志） ─── */
  log.push(`[配置] timeType=${timeType} dateShortcut=${dateShortcut} printStatus="${printStatus}" autoScroll=${autoScroll} pauseMs=${pauseMs} maxSteps=${maxSteps}`);

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

  /** 在单个容器内按 img 拆出多件商品块（合单/多 SKU 同一 .sc-dUYKzm 时使用） */
  function findGoodsContainersInElement(el) {
    const imgs = [...el.querySelectorAll('img')];
    if (imgs.length < 2) return [el];

    /* 当前 DOM：每件商品一行 .sc-cXPBhi（img-box + render-content） */
    let sub = [...el.querySelectorAll('.sc-cXPBhi')].filter((c) => c.querySelector('img'));
    sub = sub.filter((d) => !sub.some((other) => other !== d && d.contains(other)));
    if (sub.length >= 2) return sub;

    /* .render-content 的最近含图祖先 */
    sub = [...el.querySelectorAll('.render-content')].map((rc) => {
      let p = rc.parentElement;
      while (p && p !== el && !p.querySelector('img')) p = p.parentElement;
      return p && p.querySelector('img') ? p : rc;
    });
    sub = [...new Set(sub)].filter((c) => c.querySelector('img'));
    sub = sub.filter((d) => !sub.some((other) => other !== d && d.contains(other)));
    if (sub.length >= 2) return sub;

    /* LCA 直接子节点（与策略3相同，但作用域为单容器） */
    const getPath = (img) => {
      const path = [];
      let p = img;
      while (p && p !== el) { path.unshift(p); p = p.parentElement; }
      return path;
    };
    const paths = imgs.map(getPath);
    let commonDepth = 0;
    while (
      paths.every((p) => p.length > commonDepth) &&
      paths.every((p) => p[commonDepth] === paths[0][commonDepth])
    ) commonDepth++;
    const lca = commonDepth > 0 ? paths[0][commonDepth - 1] : el;
    const lcaChildren = [...lca.children].filter((c) => c.querySelector('img'));
    if (lcaChildren.length >= 2) return lcaChildren;
    if (lcaChildren.length === 1) {
      const inner = [...lcaChildren[0].children].filter((c) => c.querySelector('img'));
      if (inner.length >= 2) return inner;
    }

    return [el];
  }

  function expandMultiGoodsItems(items, diag) {
    const expanded = items.flatMap((item) => findGoodsContainersInElement(item));
    if (diag && expanded.length > items.length) {
      diag.strategy = `${diag.strategy || 'unknown'}+multi-split`;
    }
    return expanded;
  }

  /**
   * 从商品规格 td 提取商品列表
   * @param {HTMLElement} td
   * @param {object|null} diag  传入对象则填充诊断信息；null 表示不采集
   */
  function extractGoods(td, diag) {
    if (!td) return [];

    if (diag) {
      diag.innerText = (td.innerText || '').trim().slice(0, 600);
      diag.rawHtml = td.innerHTML.replace(/\s+/g, ' ').slice(0, 4000);
      diag.strategy = null;
      diag.itemCount = 0;
      diag.items = [];
    }

    /* ── 策略1：原始 styled-components 类名 .sc-dUYKzm ── */
    let items = [...td.querySelectorAll('.sc-dUYKzm')];
    if (items.length && diag) diag.strategy = 'sc-dUYKzm';

    /* ── 策略2：任意 sc- 开头类名 + 包含 img 的 div ── */
    if (!items.length) {
      items = [...td.querySelectorAll('div[class]')].filter(
        (el) => /\bsc-\w+/.test(el.className) && el.querySelector('img')
      );
      if (items.length > 1) {
        /* 保留最内层：去掉自身还包含集合内其他节点的外层容器 */
        items = items.filter((d) => !items.some((other) => other !== d && d.contains(other)));
      }
      if (items.length && diag) diag.strategy = 'sc-class-with-img';
    }

    /* ── 策略3：公共祖先子节点法（兼容多商品） ── */
    if (!items.length) {
      const allImgs = [...td.querySelectorAll('img')];
      if (allImgs.length) {
        if (allImgs.length === 1) {
          /* 单商品：向上走到第一个含有意义文本的祖先 */
          let el = allImgs[0].parentElement;
          while (el && el !== td) {
            if ((el.innerText || '').trim().length > 2) { items = [el]; break; }
            el = el.parentElement;
          }
          if (!items.length) items = [allImgs[0].parentElement || td];
          if (items.length && diag) diag.strategy = 'single-img-ancestor';
        } else {
          /*
           * 多商品：
           *   1. 求所有 img 相对于 td 的路径
           *   2. 找最近公共祖先（LCA）
           *   3. 取 LCA 的直接子节点中各自包含 img 的 → 每个子节点即一件商品
           *   这样可避免"两件商品被同一个父容器合并成一条"的问题
           */
          const getPath = (el) => {
            const path = [];
            let p = el;
            while (p && p !== td) { path.unshift(p); p = p.parentElement; }
            return path; // path[0] 是 td 的直接子节点，path[最后] 是 el 自身
          };
          const paths = allImgs.map(getPath);
          /* 计算公共路径长度 */
          let commonDepth = 0;
          while (
            paths.every((p) => p.length > commonDepth) &&
            paths.every((p) => p[commonDepth] === paths[0][commonDepth])
          ) commonDepth++;
          /* LCA = 公共路径的最后一个节点（commonDepth-1），不存在则为 td */
          const lca = commonDepth > 0 ? paths[0][commonDepth - 1] : td;
          /* LCA 的直接子节点中包含 img 的即为各商品容器 */
          const lcaChildren = [...lca.children].filter((c) => c.querySelector('img'));
          if (lcaChildren.length >= 2) {
            items = lcaChildren;
            if (diag) diag.strategy = 'lca-children';
          } else if (lcaChildren.length === 1) {
            /* LCA 下只有1个子节点含所有 img，继续向其内部找下一层直接子节点 */
            const inner = [...lcaChildren[0].children].filter((c) => c.querySelector('img'));
            items = inner.length >= 2 ? inner : lcaChildren;
            if (diag) diag.strategy = inner.length >= 2 ? 'lca-grandchildren' : 'lca-single-child';
          } else {
            /* 兜底：各 img 各自的直接父节点去重 */
            const parents = allImgs.map((img) => img.parentElement || td);
            const ps = new Set(parents);
            items = [...ps].filter((c) => {
              for (let p = c.parentElement; p && p !== td; p = p.parentElement)
                if (ps.has(p)) return false;
              return true;
            });
            if (diag) diag.strategy = 'lca-parent-fallback';
          }
        }
      }
    }

    /* ── 合单/多商品：单块容器内再拆（如 .sc-dUYKzm 包住多个 .sc-cXPBhi） ── */
    if (items.length) {
      items = expandMultiGoodsItems(items, diag);
    }

    /* ── 策略4：整个 td 作为单商品兜底 ── */
    if (!items.length) {
      if (diag) diag.strategy = 'fallback-td';
      const img = td.querySelector('img');
      const text = (td.innerText || '').trim();
      const m = text.match(/\s*[xX×](\d+)\s*$/);
      const result = [{
        imgSrc: img ? stripImgQuery(img.src || '') : '',
        title: m ? text.slice(0, m.index).trim() : text,
        spec: '',
        qty: m ? parseInt(m[1], 10) : 0,
        rawText: text.replace(/\s+/g, ' '),
      }];
      if (diag) { diag.itemCount = 1; diag.items = result.map((r) => ({ ...r })); }
      return result;    }

    if (diag) {
      diag.itemCount = items.length;
      diag.itemsRaw = items.map((item) => ({
        outerHtml: item.outerHTML.replace(/\s+/g, ' ').slice(0, 800),
        innerText: (item.innerText || '').trim().slice(0, 200),
        classNames: item.className,
      }));
    }

    const extracted = items.map((item) => {
      const img = item.querySelector('img');
      const imgSrc = stripImgQuery((img && (img.src || img.getAttribute('data-src') || '')) || '');
      let title = '', spec = '', qty = 0;

      /* ── 尝试 .content-wrapper（旧版类名） ── */
      const wrapper = item.querySelector('.content-wrapper');
      if (wrapper) {
        const ls = wrapper.querySelector('.light-span');
        if (ls) qty = parseInt(ls.textContent.trim().replace(/^[xX×]/u, ''), 10) || 0;
        const childSpans = [...wrapper.children].filter(
          (el) => el.tagName === 'SPAN' && !el.classList.contains('light-span') && el.textContent.trim()
        );
        if (childSpans.length >= 2) {
          title = childSpans[0].textContent.trim();
          spec = childSpans[childSpans.length - 1].textContent.trim();
        } else if (childSpans.length === 1) {
          title = childSpans[0].textContent.trim();
        }
      }

      /* ── 通过 span 叶节点解析（无需特定类名） ── */
      if (!title) {
        const allSpans = [...item.querySelectorAll('span')];
        const qtySpan = allSpans.find((s) => /^[xX×]\d+$/.test(s.textContent.trim()));
        if (qtySpan && !qty)
          qty = parseInt(qtySpan.textContent.trim().replace(/^[xX×]/u, ''), 10) || 0;
        const leafSpans = allSpans.filter(
          (s) => s !== qtySpan && !s.querySelector('span') && s.textContent.trim()
        );
        if (leafSpans.length >= 2) {
          title = leafSpans[0].textContent.trim();
          spec = leafSpans[leafSpans.length - 1].textContent.trim();
        } else if (leafSpans.length === 1) {
          title = leafSpans[0].textContent.trim();
        }
      }

      /* ── 最终兜底：innerText 正则提取 ── */
      if (!title) {
        const ft = (item.innerText || '').trim();
        const m2 = ft.match(/\s*[xX×](\d+)\s*$/);
        if (m2 && !qty) qty = parseInt(m2[1], 10) || 0;
        title = m2 ? ft.slice(0, m2.index).trim() : ft;
      }

      /* ── 完整原始文本（含价格等该格子所有文字） ── */
      const rawText = (item.innerText || '').trim().replace(/\s+/g, ' ');

      return { imgSrc, title, spec, qty, rawText };
    });

    if (diag) diag.items = extracted.map((r) => ({ ...r }));
    return extracted;
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
  log.push(`[Step1] 表单加载完成，耗时 ${Date.now() - t0}ms`);
  log.push(`[Step1] timeType存在=${!!document.querySelector('#timeType')} timeRange存在=${!!document.querySelector('#timeRange')} isPrintTracking存在=${!!document.querySelector('#isPrintTracking')}`);

  /* ─── Step 2: 选择时间类型「发货时间」 ─── */
  const timeTypeResult = await selectOption('timeType', timeType);
  log.push(`[Step2] 时间类型 → "${timeType}"：${JSON.stringify(timeTypeResult)}`);
  if (!timeTypeResult.ok) return { ok: false, error: `时间类型选择失败：${timeTypeResult.reason}`, log };

  /* ─── Step 3: 日期范围「今天」快捷按钮 ─── */
  const rangeInput = document.querySelector('#timeRange [data-testid="beast-core-rangePicker-htmlInput"]');
  if (!rangeInput) return { ok: false, error: '未找到日期范围输入框', log };

  rangeInput.click();
  await sleep(500);

  const todayBtn = [...document.querySelectorAll('button')]
    .find((b) => b.offsetParent !== null && b.innerText.trim() === dateShortcut && b.className.includes('RPR_'));
  if (!todayBtn) {
    const allShortcuts = [...document.querySelectorAll('button')]
      .filter((b) => b.offsetParent !== null && b.className.includes('RPR_'))
      .map((b) => b.innerText.trim());
    log.push(`[Step3] 快捷按钮列表：${JSON.stringify(allShortcuts)}`);
    return { ok: false, error: `未找到「${dateShortcut}」快捷按钮`, log };
  }

  todayBtn.click();
  await sleep(400);
  log.push(`[Step3] 日期范围 → "${rangeInput.value}"`);

  /* ─── Step 4: 打印状态 ─── */
  if (printStatus) {
    const printResult = await selectOption('isPrintTracking', printStatus);
    log.push(`[Step4] 打印状态 → "${printStatus}"：${JSON.stringify(printResult)}`);
    if (!printResult.ok) return { ok: false, error: `打印状态选择失败：${printResult.reason}`, log };
  } else {
    log.push('[Step4] 打印状态：不筛选（全部）');
  }

  /* ─── Step 5: 点击查询 ─── */
  const queryBtn = [...document.querySelectorAll('button')]
    .find((b) => b.offsetParent !== null && b.textContent.trim() === '查询' && !b.disabled);
  if (!queryBtn) return { ok: false, error: '未找到查询按钮', log };

  const t5 = Date.now();
  queryBtn.click();
  await sleep(2000);
  log.push(`[Step5] 已点击查询，等待结果加载（点击后等待 2000ms）`);

  /* ─── Step 6: 等待结果 ─── */
  const waitResult = Date.now();
  while (Date.now() - waitResult < 8000) {
    if (document.querySelector('[data-testid="beast-core-table-middle-tbody"]')) break;
    await sleep(300);
  }
  const tbodyReady = !!document.querySelector('[data-testid="beast-core-table-middle-tbody"]');
  log.push(`[Step6] 表格tbody ${tbodyReady ? '已加载' : '超时未出现'}，等待耗时 ${Date.now() - waitResult}ms`);

  /* 列数校验：打印第一行的 td 数量，用于确认各字段 td 下标是否正确 */
  const firstRow = document.querySelector('[data-testid="beast-core-table-body-tr"]');
  if (firstRow) {
    const tdCount = firstRow.querySelectorAll('td').length;
    log.push(`[Step6] 首行 td 数量=${tdCount}（期望：orderNo=td[11] goods=td[6] express=td[7] shippingTime=td[12] printStatus=td[24] erpOrderNo=td[25] shop=td[14]）`);
  } else {
    log.push('[Step6] 首行未找到，可能无数据或表格结构已变更');
  }

  /* ─── Step 7: 抓取数据（支持虚拟滚动） ─── */
  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const TBODY_SEL = '[data-testid="beast-core-table-middle-tbody"]';
  const TABLE_ROOT_SEL = '[data-testid="beast-core-table"]';
  const BODY_WRAP_SEL = '[data-testid="beast-core-table-middle-body"]';

  /* 前 N 行商品 td 诊断（用于发给 AI 分析） */
  const goodsDiag = [];
  /* goods 策略计数（key=策略名, value=命中次数） */
  const goodsStrategyCount = {};

  const rowMap = new Map();

  function collectRows() {
    const result = [];
    [...document.querySelectorAll(TBODY_SEL)].forEach((tbody) => {
      [...tbody.querySelectorAll(ROW_SEL)].forEach((row) => {
        const tds = [...row.querySelectorAll('td')];
        const orderNo = getOrderNo(tds[11]);
        const key = orderNo || tds.map((td) => td.textContent.trim().slice(0, 10)).join('|');
        if (!orderNo) return; // 跳过无订单号行

        /* 诊断采集：
         *   - 前 3 行无条件采集（基线样本）
         *   - 此后：goods 为空 或 td 内 img 数量 > goods 数量（疑似多商品漏抓）时补充采集，最多再采 3 条
         */
        const tdImgCount = tds[6] ? tds[6].querySelectorAll('img').length : 0;
        let diag = null;
        const isBaseline = !rowMap.has(key) && goodsDiag.filter((d) => d._type === 'baseline').length < 3;
        const needsExtra = !rowMap.has(key) && !isBaseline && goodsDiag.filter((d) => d._type === 'extra').length < 3;
        if (isBaseline || needsExtra) {
          diag = { orderNo, tdIndex: 6, _type: isBaseline ? 'baseline' : 'extra' };
          goodsDiag.push(diag);
        }

        const goods = extractGoods(tds[6], diag);
        /* 策略命中计数（用 diag 时能拿到 strategy，否则做轻量探测） */
        const strategy = diag ? diag.strategy : (() => {
          if (tds[6] && tds[6].querySelector('.sc-dUYKzm')) return 'sc-dUYKzm';
          if (tds[6] && [...tds[6].querySelectorAll('div[class]')].some((el) => /\bsc-\w+/.test(el.className) && el.querySelector('img'))) return 'sc-class-with-img';
          return 'other';
        })();
        if (strategy) goodsStrategyCount[strategy] = (goodsStrategyCount[strategy] || 0) + 1;

        /* 多商品漏抓补充诊断（已解析完才能判断） */
        if (!diag && !rowMap.has(key) && goodsDiag.filter((d) => d._type === 'extra').length < 3) {
          if (!goods.length || (tdImgCount > goods.length)) {
            const extraDiag = { orderNo, tdIndex: 6, _type: 'extra', tdImgCount, goodsLength: goods.length };
            goodsDiag.push(extraDiag);
            extractGoods(tds[6], extraDiag); // 重新采集诊断（不影响 goods 结果）
          }
        }
        const { shopName, actualAmount } = getShop(tds[14]);
        result.push({
          key,
          orderNo,
          erpOrderNo: getErpOrderNo(tds[25]),
          goods,
          goodsCellText: getCellText(tds[6]),  // 商品格完整文字（含价格等全部内容）
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

  function mergeRows() {
    let added = 0;
    collectRows().forEach(({ key, ...data }) => {
      if (!rowMap.has(key)) { rowMap.set(key, data); added++; }
    });
    return added;
  }

  if (!autoScroll) {
    mergeRows();
    log.push(`[Step7] 静态模式：抓取 ${rowMap.size} 条`);
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

    if (scrollEl) {
      log.push(`[Step7] 滚动容器：tag=${scrollEl.tagName} class="${scrollEl.className.slice(0, 60)}" scrollHeight=${scrollEl.scrollHeight} clientHeight=${scrollEl.clientHeight}`);
    } else {
      log.push(`[Step7] 未找到可滚动容器（bodyWrap=${!!bodyWrap} tableRoot=${!!tableRoot}），将作静态抓取`);
    }

    if (scrollEl) scrollEl.scrollTop = 0;
    await sleep(300);
    const initCount = mergeRows();
    log.push(`[Step7] 初始可见：${initCount} 条（rowMap=${rowMap.size}）`);

    let stale = 0;
    const stepPx = Math.max(100, Math.round((scrollEl ? scrollEl.clientHeight : 600) * 0.88));
    log.push(`[Step7] 每步滚动 ${stepPx}px，最多 ${maxSteps} 步，间隔 ${pauseMs}ms`);
    for (let step = 0; step < maxSteps; step++) {
      if (scrollEl) scrollEl.scrollTop += stepPx;
      await sleep(pauseMs);
      const added = mergeRows();
      if (added > 0) {
        log.push(`[scroll step=${step + 1}] +${added} 条，累计=${rowMap.size}`);
        stale = 0;
      } else {
        stale++;
        if (stale >= 3) { log.push(`[Step7] 连续 3 步无新数据，触底停止（step=${step + 1}，总计=${rowMap.size} 条）`); break; }
      }
    }
    if (scrollEl) scrollEl.scrollTop = 0;
    log.push(`[Step7] 滚动完成，共 ${rowMap.size} 条`);
  }

  const rows = [...rowMap.values()];
  log.push(`[汇总] 最终输出 ${rows.length} 条已发货订单`);

  /* goods 命中情况汇总 */
  const goodsStrategySummary = {};
  rows.forEach((r) => {
    const s = (r.goods && r.goods.length) ? 'has-goods' : 'empty';
    goodsStrategySummary[s] = (goodsStrategySummary[s] || 0) + 1;
  });
  const multiGoodsOrders = rows.filter((r) => r.goods && r.goods.length > 1)
    .map((r) => `${r.orderNo}(${r.goods.length}件)`);
  log.push(`[汇总] goods 状态：${JSON.stringify(goodsStrategySummary)}`);
  log.push(`[汇总] goods 提取策略分布：${JSON.stringify(goodsStrategyCount)}`);
  if (multiGoodsOrders.length)
    log.push(`[汇总] 多商品订单（${multiGoodsOrders.length}条）：${multiGoodsOrders.join(', ')}`);

  /* 异常行详情：goods 为空 或 title 为空 */
  const badRows = rows.filter((r) => !r.goods || !r.goods.length || !r.goods[0].title);
  if (badRows.length) {
    log.push(`[汇总] goods异常行 ${badRows.length} 条（前5详情）：`);
    badRows.slice(0, 5).forEach((r) => {
      log.push(`  订单=${r.orderNo} goods=${JSON.stringify(r.goods)} goodsCellText="${(r.goodsCellText || '').slice(0, 80)}"`);
    });
  }

  /* qty=0 但 rawText 含数字的行（可能数量未提取到） */
  const qtyZeroRows = rows.filter((r) => r.goods && r.goods.some((g) => g.qty === 0 && /\d/.test(g.rawText || '')));
  if (qtyZeroRows.length) {
    log.push(`[汇总] qty=0 但 rawText 含数字的订单（前5）：`);
    qtyZeroRows.slice(0, 5).forEach((r) => {
      r.goods.filter((g) => g.qty === 0).forEach((g) => {
        log.push(`  订单=${r.orderNo} title="${g.title.slice(0, 20)}" rawText="${(g.rawText || '').slice(0, 80)}"`);
      });
    });
  }

  return { ok: true, count: rows.length, rows, log, goodsDiag, goodsStrategyCount };
})();
