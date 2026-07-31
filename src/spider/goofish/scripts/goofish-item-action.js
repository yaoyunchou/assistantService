/*
 * 闲鱼商品操作（上架 / 下架 / 删除）
 *
 * Python 入口：src/spider/goofish/flows/manage_items.py → _run_dom_action()
 * HTTP 路由  ：POST /api/goofish/items/<id>/{online|offline|delete}
 *
 * 配置项（由 Python 通过 window 注入）：
 *   window.__GOOFISH_ACTION          必填，'online' | 'offline' | 'delete'
 *   window.__GOOFISH_ACTION_ITEM_ID  必填，目标商品 ID
 *   window.__GOOFISH_ACTION_CONFIRM  是否确认执行，默认 false（false 时只定位不点击）
 *
 * 上下架与删除的 DOM 结构高度相似，因此合并为一个脚本按 action 分派。
 *
 * 安全约定：
 *   - CONFIRM 为 false 时只做定位演练（dryRun），不产生任何副作用
 *   - 删除属不可逆操作，必须由 Python 侧显式传 confirm=true
 *   - 找不到目标商品行或按钮时返回 success:false，绝不「就近点一个」
 */
(async () => {
  const log = [];
  const action = String(window.__GOOFISH_ACTION || '').toLowerCase();
  const itemId = String(window.__GOOFISH_ACTION_ITEM_ID || '');
  const confirm = window.__GOOFISH_ACTION_CONFIRM === true;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ACTION_TEXTS = {
    offline: ['下架'],
    online: ['上架', '重新上架', '再次上架'],
    delete: ['删除'],
  };
  // 二次确认弹窗里的确认按钮文案
  const CONFIRM_TEXTS = ['确定', '确认', '确认下架', '确认删除', '确认上架', '是'];

  if (!ACTION_TEXTS[action]) {
    return { success: false, error: `不支持的 action: ${action}`, log };
  }
  if (!itemId) {
    return { success: false, error: '缺少 itemId', log };
  }

  function visibleClickable(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle(el);
    return style.visibility !== 'hidden' && style.display !== 'none';
  }

  // 定位目标商品所在的行/卡片：从含该 itemId 的链接向上回溯
  function findItemContainer() {
    const anchors = Array.from(document.querySelectorAll('a[href]')).filter((a) => {
      const href = a.getAttribute('href') || a.href || '';
      return href.includes(itemId);
    });
    if (!anchors.length) return null;

    let node = anchors[0];
    for (let i = 0; i < 8 && node && node.parentElement; i += 1) {
      node = node.parentElement;
      const text = node.innerText || '';
      const hasAction = ACTION_TEXTS[action].some((t) => text.includes(t));
      if (hasAction) return node;
    }
    return null;
  }

  function findActionButton(container) {
    const candidates = Array.from(
      container.querySelectorAll('button, a, span, div[role="button"]')
    );
    for (const text of ACTION_TEXTS[action]) {
      const hit = candidates.find(
        (el) => (el.innerText || '').trim() === text && visibleClickable(el)
      );
      if (hit) return { el: hit, text };
    }
    // 放宽为包含匹配（按钮可能带图标或空白）
    for (const text of ACTION_TEXTS[action]) {
      const hit = candidates.find(
        (el) => (el.innerText || '').trim().includes(text) && visibleClickable(el)
      );
      if (hit) return { el: hit, text };
    }
    return { el: null, text: '' };
  }

  async function clickConfirmDialog() {
    await sleep(800);
    const all = Array.from(document.querySelectorAll('button, a, span, div[role="button"]'));
    for (const text of CONFIRM_TEXTS) {
      const hit = all.find(
        (el) => (el.innerText || '').trim() === text && visibleClickable(el)
      );
      if (hit) {
        hit.click();
        log.push(`已点击确认弹窗: ${text}`);
        return text;
      }
    }
    log.push('未发现二次确认弹窗（可能无需确认）');
    return '';
  }

  try {
    const container = findItemContainer();
    if (!container) {
      return {
        success: false,
        error: `未在当前页面找到商品 ${itemId} 对应的「${ACTION_TEXTS[action][0]}」操作行`,
        log,
      };
    }
    log.push('已定位商品行');

    const { el, text } = findActionButton(container);
    if (!el) {
      return {
        success: false,
        error: `商品行内未找到「${ACTION_TEXTS[action].join('/')}」按钮`,
        log,
      };
    }
    log.push(`已定位操作按钮: ${text}`);

    if (!confirm) {
      return {
        success: true,
        dryRun: true,
        itemId,
        action,
        button: text,
        log,
        message: '定位成功（未执行，confirm=false）',
      };
    }

    el.click();
    log.push(`已点击: ${text}`);
    const confirmed = await clickConfirmDialog();
    await sleep(1200);

    return { success: true, itemId, action, button: text, confirmed, log };
  } catch (e) {
    log.push(`异常: ${e && e.message ? e.message : String(e)}`);
    return { success: false, error: String(e), log };
  }
})()
