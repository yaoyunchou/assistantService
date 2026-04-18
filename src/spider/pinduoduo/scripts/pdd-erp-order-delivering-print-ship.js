/**
 * 拼多多官方 ERP —— 待发货订单「全选 → 打印快递单 → 打印并发货」
 * 页面：https://mms.pinduoduo.com/erp/order/delivering
 *
 * 流程：
 *   1. 检查列表是否有订单，无则直接返回 { empty: true }
 *   2. 点击表头全选 checkbox
 *   3. 点击「打印快递单」按钮
 *   4. 弹窗出现「确认选择」→ 点击
 *   5. 打印预览弹窗出现「打印并发货」→ 点击
 *   6. 等待 10s 后检查列表是否清空
 *   7. 返回 { success: true/false, ... }
 *
 * 运行方式：
 *   在 https://mms.pinduoduo.com/erp/order/delivering 页面通过
 *   page_evaluate 注入本脚本全文（timeout 建议 ≥ 30000）
 */
(async function () {
  const log = [];
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ROW_SEL = 'tr[data-testid="beast-core-table-body-tr"]';
  const HEADER_CHECK_SEL = 'th.TB_checkCell_5-184-0 label[data-testid="beast-core-checkbox"]';

  /* ─── Step 0: 等待表格容器加载 ─── */
  const t0 = Date.now();
  while (Date.now() - t0 < 12000) {
    const tbody = document.querySelector('[data-testid="beast-core-table-middle-tbody"]');
    if (tbody) break;
    await sleep(400);
  }

  /* ─── Step 1: 等待列表数据出现（最少 5s，最多 15s），再判定是否为空 ─── */
  // 列表请求需要时间，过早判空会出现「明明有单也被判空」的情况；
  // 这里保证至少 5s 的缓冲，期间一旦出现行就提前结束等待。
  const MIN_WAIT_MS = 5000;
  const MAX_WAIT_MS = 15000;
  const tWait = Date.now();
  let rows = document.querySelectorAll(ROW_SEL);
  while (Date.now() - tWait < MAX_WAIT_MS) {
    rows = document.querySelectorAll(ROW_SEL);
    const elapsed = Date.now() - tWait;
    if (rows.length > 0 && elapsed >= MIN_WAIT_MS) break;
    if (rows.length === 0 && elapsed >= MIN_WAIT_MS) {
      // 至少等够 5s 后仍为空，再多观察一轮防抖（500ms）后判空
      await sleep(500);
      rows = document.querySelectorAll(ROW_SEL);
      break;
    }
    await sleep(400);
  }
  log.push(`列表加载等待 ${Date.now() - tWait}ms，行数=${rows.length}`);

  if (rows.length === 0) {
    log.push('列表为空，无待发货订单');
    return { ok: true, empty: true, success: false, log };
  }
  log.push(`列表有 ${rows.length} 条待发货订单`);

  /* ─── Step 2: 全选 ─── */
  const headerLabel = document.querySelector(HEADER_CHECK_SEL);
  if (!headerLabel) {
    return { ok: false, error: '未找到表头全选 checkbox', log };
  }
  const headerInput = headerLabel.querySelector('input');
  if (headerInput && !headerInput.checked) {
    headerLabel.click();
    await sleep(400);
  }
  const allChecked = [...document.querySelectorAll(ROW_SEL + ' label[data-testid="beast-core-checkbox"]')]
    .every((label) => { const inp = label.querySelector('input'); return inp ? inp.checked : false; });
  log.push(`全选完成，allChecked=${allChecked}`);
  if (!allChecked) {
    return { ok: false, error: '全选后仍有行未被勾选', log };
  }

  /* ─── Step 3: 点击「打印快递单」 ─── */
  const printBtn = [...document.querySelectorAll('button[data-testid="beast-core-button"]')]
    .find((btn) => btn.textContent.trim() === '打印快递单' && !btn.disabled);
  if (!printBtn) {
    return { ok: false, error: '未找到「打印快递单」按钮', log };
  }
  printBtn.click();
  log.push('已点击「打印快递单」');

  /* ─── Step 4: 等待弹窗 → 点击「确认选择」 ─── */
  const waitBtn = async (text, timeoutMs) => {
    const t = Date.now();
    while (Date.now() - t < timeoutMs) {
      const btn = [...document.querySelectorAll('button')]
        .find((b) => b.offsetParent !== null && b.textContent.trim() === text && !b.disabled);
      if (btn) return btn;
      await sleep(300);
    }
    return null;
  };

  const confirmBtn = await waitBtn('确认选择', 8000);
  if (!confirmBtn) {
    return { ok: false, error: '等待「确认选择」按钮超时', log };
  }
  confirmBtn.click();
  log.push('已点击「确认选择」');

  /* ─── Step 5: 等待打印预览弹窗 → 点击「打印并发货」 ─── */
  const printAndShipBtn = await waitBtn('打印并发货', 8000);
  if (!printAndShipBtn) {
    return { ok: false, error: '等待「打印并发货」按钮超时', log };
  }
  printAndShipBtn.click();
  log.push('已点击「打印并发货」');

  /* ─── Step 6: 等待 10s 后检查列表 ─── */
  log.push('等待 10s...');
  await sleep(10000);

  const remainRows = document.querySelectorAll(ROW_SEL).length;
  const success = remainRows === 0;
  log.push(`等待完毕，列表剩余 ${remainRows} 条，success=${success}`);

  return {
    ok: true,
    empty: false,
    success,
    remainRows,
    log,
  };
})();
