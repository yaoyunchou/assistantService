# 1688 订单列表信息提取

从 1688「已买到的货品」订单列表页中，提取 `order-list-content` 下每个 `order-item` 的 **total-price**、**product-name**、**product-sku-info** 列表信息。

## 方式一：浏览器控制台运行（推荐，当前已打开订单列表时）

1. 打开 1688 订单列表页：  
   https://air.1688.com/app/ctf-page/trade-order-list/buyer-order-list.html?tradeStatus=waitbuyerreceive&page=1&pageSize=100  
2. 若列表在 **iframe** 内：在 DevTools 的 Console 顶部下拉框中选择对应的 iframe（如 `top` 或该 iframe），再执行下面脚本。  
3. 在 Console 中粘贴并执行以下脚本，结果会打印并复制到剪贴板（便于粘贴到别处）：

```javascript
(function() {
  var root = document.querySelector('.order-list-content') || document;
  var items = root.querySelectorAll('.order-item');
  var list = [];
  items.forEach(function(el) {
    var totalPriceEl = el.querySelector('.total-price');
    var nameEl = el.querySelector('.product-name');
    var skuEl = el.querySelector('.product-sku-info');
    list.push({
      totalPrice: totalPriceEl ? totalPriceEl.textContent.trim() : '',
      productName: nameEl ? nameEl.textContent.trim() : '',
      productSkuInfo: skuEl ? skuEl.textContent.trim() : ''
    });
  });
  var json = JSON.stringify(list, null, 2);
  console.log('订单条数:', list.length);
  console.log(json);
  try {
    navigator.clipboard.writeText(json);
    console.log('已复制到剪贴板');
  } catch (e) {}
  return list;
})();
```

若页面使用的类名带前缀（如 `next-`），可先在本页用「检查元素」确认实际类名，再把上面脚本中的 `.order-list-content`、`.order-item`、`.total-price`、`.product-name`、`.product-sku-info` 替换为实际选择器。

**若列表在 Shadow DOM 内**（路径：`body > article > app-root` → shadowRoot → `div > main > q-theme > order-list` → shadowRoot → `div`），请使用应用内 **「1688 订单提取」** 页面（左侧导航进入），其已做 Shadow DOM 兼容；或在控制台用「检查元素」在 shadow 内找到 `.order-list-content` / `.order-item` 后自行改选择器。

## 方式二：应用内页面（推荐）

启动如意助手后，在左侧导航进入 **「1688 订单提取」**，点击「开始提取」即可。会使用项目配置的浏览器与登录态，提取完成后可「同步到飞书」或「下载 JSON」。逻辑位于 `src/spider/order_1688/` 模块。
