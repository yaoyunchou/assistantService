/*
 * 闲鱼商品列表 DOM 兜底抓取
 *
 * Python 入口：src/spider/goofish/item_list.py → _fetch_via_dom()
 * HTTP 路由  ：GET /api/goofish/items（仅在 mtop 直调与自动识别都失败时才会走到这里）
 *
 * 配置项（由 Python 通过 window 注入，均可选）：
 *   window.__GOOFISH_ITEM_LIST_MAX_SCROLL   最大滚动次数，默认 8
 *   window.__GOOFISH_ITEM_LIST_SCROLL_PAUSE 每次滚动等待毫秒，默认 900
 *
 * 设计说明：
 *   闲鱼后台 class 名带 CSS Modules 构建哈希（形如 xxx--ScuLfa2N），每次发版都变，
 *   因此这里不依赖 class，改用「结构 + 内容」启发式：
 *     1. 找出所有指向商品详情（URL 含 id=<数字>）的链接
 *     2. 向上回溯到公共卡片容器
 *     3. 从卡片文本里解析价格、状态
 *   返回 { items, log }，解析不到时 items 为空数组，由 Python 侧标记为兜底失败。
 */
(async () => {
  const log = [];
  const cfg = {
    maxScroll: Number(window.__GOOFISH_ITEM_LIST_MAX_SCROLL || 8),
    scrollPause: Number(window.__GOOFISH_ITEM_LIST_SCROLL_PAUSE || 900),
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  const ID_RE = /[?&](?:id|itemId)=(\d{6,})/i;
  const PATH_ID_RE = /\/item\/(\d{6,})/i;
  // 必须带货币符号才算价格。标题里常有数字（如「机械键盘 87键」「显示器 27寸」），
  // 允许裸数字会把标题里的数字当成价格。
  const PRICE_CURRENCY_RE = /(?:¥|￥|RMB)\s*(\d+(?:\.\d{1,2})?)/i;
  const PRICE_BARE_RE = /(?:^|\s)(\d+(?:\.\d{1,2})?)(?:\s|$)/;

  function extractId(href) {
    if (!href) return '';
    const m = ID_RE.exec(href) || PATH_ID_RE.exec(href);
    return m ? m[1] : '';
  }

  function detectStatus(text) {
    if (/已售出|已卖出|已成交/.test(text)) return 'sold';
    if (/已下架|下架中/.test(text)) return 'offline';
    if (/在售|出售中|已上架/.test(text)) return 'online';
    return 'unknown';
  }

  // 向上回溯找卡片容器：取包含价格或状态文案的最近祖先
  function findCard(anchor) {
    let node = anchor;
    for (let i = 0; i < 6 && node && node.parentElement; i += 1) {
      node = node.parentElement;
      const text = (node.innerText || '').trim();
      if (text && (PRICE_CURRENCY_RE.test(text) || detectStatus(text) !== 'unknown')) {
        return node;
      }
    }
    return anchor.parentElement || anchor;
  }

  // 优先取带货币符号的价格；没有符号时，先剔除标题再找裸数字，避免误取标题里的数字
  function parsePrice(cardText, title) {
    const withCurrency = PRICE_CURRENCY_RE.exec(cardText);
    if (withCurrency) return Number(withCurrency[1]);

    const stripped = title ? cardText.split(title).join(' ') : cardText;
    const bare = PRICE_BARE_RE.exec(stripped);
    return bare ? Number(bare[1]) : null;
  }

  async function autoScroll() {
    let lastCount = -1;
    for (let step = 0; step < cfg.maxScroll; step += 1) {
      const count = document.querySelectorAll('a[href]').length;
      if (count === lastCount && step > 1) break;
      lastCount = count;
      window.scrollTo(0, document.body.scrollHeight);
      await sleep(cfg.scrollPause);
    }
    window.scrollTo(0, 0);
    log.push(`滚动完成，链接数=${lastCount}`);
  }

  try {
    await autoScroll();

    const byId = new Map();
    const anchors = Array.from(document.querySelectorAll('a[href]'));
    log.push(`候选链接 ${anchors.length} 个`);

    anchors.forEach((a) => {
      const itemId = extractId(a.getAttribute('href') || a.href || '');
      if (!itemId || byId.has(itemId)) return;

      const card = findCard(a);
      const cardText = (card.innerText || '').trim();
      const title =
        (a.getAttribute('title') || '').trim() ||
        (a.innerText || '').trim().split('\n')[0] ||
        cardText.split('\n')[0] ||
        '';

      const img = card.querySelector('img');

      byId.set(itemId, {
        itemId,
        title: title.slice(0, 200),
        price: parsePrice(cardText, title),
        status: detectStatus(cardText),
        coverUrl: img ? (img.getAttribute('src') || img.src || '') : '',
        itemUrl: a.href || '',
        updatedAt: '',
      });
    });

    const items = Array.from(byId.values());
    log.push(`解析出商品 ${items.length} 个`);
    return { items, log, success: items.length > 0 };
  } catch (e) {
    log.push(`异常: ${e && e.message ? e.message : String(e)}`);
    return { items: [], log, success: false, error: String(e) };
  }
})()
