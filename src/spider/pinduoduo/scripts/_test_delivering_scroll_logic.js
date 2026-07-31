/**
 * 本地复现：ERP 待发货虚拟列表「只抓视口」导致漏单。
 * 模拟 2026-07-15 共 50 单、视口仅挂载 12 行的情况。
 *
 * 运行：node src/spider/pinduoduo/scripts/_test_delivering_scroll_logic.js
 */
'use strict';

const TOTAL = 50;
const VISIBLE = 12; // 虚拟列表同时挂载的行数（贴近 beast-core 表体）
const STEP_RATIO = 0.88;
const MAX_STEPS = 200;
const STALE_STOP = 3;

function makeOrderNo(i) {
  return `260715${String(i).padStart(10, '0')}`;
}

/** 按 scrollIndex 返回当前 DOM 中「可见」行（虚拟列表复用节点） */
function getVisibleRows(scrollIndex) {
  const rows = [];
  for (let i = 0; i < VISIBLE; i++) {
    const idx = scrollIndex + i;
    if (idx < 0 || idx >= TOTAL) continue;
    rows.push({ orderNo: makeOrderNo(idx + 1), goods: [{ title: `商品${idx + 1}`, qty: 1 }] });
  }
  return rows;
}

/** 旧逻辑：只 query 一次当前视口 */
function oldCollectOnce() {
  return getVisibleRows(0);
}

/** 新逻辑：滚动 + orderNo 去重合并 */
function newScrollCollect() {
  const rowMap = new Map();
  let scrollIndex = 0;
  let stale = 0;
  const stepPxRows = Math.max(1, Math.floor(VISIBLE * STEP_RATIO));
  const log = [];

  function merge() {
    let added = 0;
    getVisibleRows(scrollIndex).forEach((r) => {
      if (!rowMap.has(r.orderNo)) {
        rowMap.set(r.orderNo, r);
        added++;
      }
    });
    return added;
  }

  const init = merge();
  log.push(`初始可见 ${init}，累计=${rowMap.size}`);

  for (let step = 0; step < MAX_STEPS; step++) {
    scrollIndex = Math.min(scrollIndex + stepPxRows, Math.max(0, TOTAL - VISIBLE));
    const added = merge();
    if (added > 0) {
      stale = 0;
      if (step < 5 || added > 0) log.push(`step=${step + 1} +${added} 累计=${rowMap.size}`);
    } else {
      stale++;
      if (stale >= STALE_STOP) {
        log.push(`连续 ${STALE_STOP} 步无新数据，停止 step=${step + 1}`);
        break;
      }
    }
    if (scrollIndex >= TOTAL - VISIBLE && added === 0 && stale >= 1) {
      // 已到底部窗口
    }
  }

  return { rows: [...rowMap.values()], log };
}

const oldRows = oldCollectOnce();
const neu = newScrollCollect();

console.log('=== 复现：2026-07-15 共 50 单 ===');
console.log(`[旧逻辑] 仅视口一次采集 → ${oldRows.length} 条（漏 ${TOTAL - oldRows.length}）`);
console.log(`[新逻辑] 滚动+去重 → ${neu.rows.length} 条`);
neu.log.slice(0, 8).forEach((l) => console.log('  ', l));
if (neu.log.length > 8) console.log('  ...');
console.log('  ', neu.log[neu.log.length - 1]);

const ok = oldRows.length < TOTAL && neu.rows.length === TOTAL;
if (!ok) {
  console.error('FAIL: 期望旧逻辑不完整、新逻辑=50');
  process.exit(1);
}
console.log('PASS: 根因确认（虚拟滚动视口截断），新逻辑可收齐 50 单');
