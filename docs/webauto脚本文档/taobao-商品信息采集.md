# 淘宝商品信息采集脚本

> 采集逻辑维护在 webAuto Chrome 扩展 popup 组件中：  
> `C:\Users\yao\Desktop\work\webAuto\chrome-extension\src\popup\pages\TaobaoAssistant.jsx`  
> 内嵌脚本常量名：`EXTRACT_CODE`
>
> **最后同步：2026-05-26**

**目标页面**：淘宝商品详情页（`https://item.taobao.com/item.htm?id=...`）  
**功能**：采集商品标题、主图列表（还原原图 URL）、销售规格（含规格图片 / vid / 缺货状态 / 价格）、SKU 精确价格、商品参数、售价、已售量。

---

## 采集脚本（可直接用于 Playwright 注入）

> ⚠️ 此脚本与 webAuto popup 内的 `EXTRACT_CODE` 保持同步，如需修改请以 `TaobaoAssistant.jsx` 为准，此处同步更新。

```javascript
// taobao-product-extract.js
// 在淘宝商品详情页注入，返回商品完整信息
// Playwright 用法：result = await page.evaluate(code)
(function () {

  // ── 图片 URL 标准化（阿里 CDN）──
  // .heic 文件必须保留扩展名并加 _.webp 让 CDN 转码，不能直接改成 .jpg
  function normalizeAliImg(src) {
    if (!src) return null;
    src = src.replace(/~crop[^~]*~/, '');
    src = src.replace(/_q\d+\.jpg_\.(webp|web)$/, '');
    src = src.replace(/\.webp$/, '');
    if (src.endsWith('.heic')) src = src + '_.webp';
    return src || null;
  }

  // ── 标题 ──
  const titleEl = document.querySelector('[class*="mainTitle"]');
  const title = titleEl?.innerText?.trim() || document.title;

  // ── 主图：优先 ICE 静态数据，兜底 DOM thumbnailPic ──
  const iceRes = window.__ICE_APP_CONTEXT__?.loaderData?.home?.data?.res;
  const iceItemImages = iceRes?.item?.images || [];
  let images;
  if (iceItemImages.length > 0) {
    images = iceItemImages.map(normalizeAliImg).filter(Boolean);
  } else {
    const thumbEls = Array.from(document.querySelectorAll('[class*="thumbnailPic"]'));
    images = thumbEls.map(img => normalizeAliImg(img.src)).filter(Boolean);
  }

  // ── 销售规格（SKU）+ 每 SKU 单独价格 ──
  // 优先从 __ICE_APP_CONTEXT__ 读取结构化数据（含规格图片 & 精确单价）
  const specs = [];
  const skus  = [];

  const iceProps    = iceRes?.skuBase?.props    || [];
  const iceSkuList  = iceRes?.skuBase?.skus     || [];
  const iceSku2info = iceRes?.skuCore?.sku2info || {};

  if (iceProps.length > 0) {
    // 构建 vid → {name, image} 映射
    const vidMap = {};
    for (const prop of iceProps) {
      for (const v of (prop.values || [])) {
        if (v.name) vidMap[String(v.vid)] = { name: v.name, image: v.image || null };
      }
      const values = (prop.values || []).filter(v => v.name).map(v => ({
        text : v.name,
        img  : normalizeAliImg(v.image),
        vid  : String(v.vid),
        empty: !!v.empty,
      }));
      if (values.length) specs.push({ label: prop.name, values });
    }

    // 构建 SKU 价格列表
    // 路径1：skuBase.skus propPath（最准确）
    // 路径2：sku2info 直接遍历（skuBase.skus 为空时）
    const skuEntries = iceSkuList.length > 0
      ? iceSkuList.map(s => ({ skuId: String(s.skuId), propPath: s.propPath }))
      : Object.entries(iceSku2info).map(([skuId, info]) => ({
          skuId,
          propPath: info.propPath || info.propStr || '',
        })).filter(e => e.propPath);

    for (const s of skuEntries) {
      const vids  = s.propPath.split(';').map(seg => seg.split(':')[1]).filter(Boolean);
      const names = vids.map(vid => vidMap[vid]?.name).filter(Boolean);
      const price = iceSku2info[s.skuId]?.price?.priceText || null;
      const skuEmpty = vids.every(vid => {
        const propVal = iceProps.flatMap(p => p.values || []).find(v => String(v.vid) === vid);
        return propVal ? !!propVal.empty : false;
      });
      skus.push({ skuId: s.skuId, vids, names, price, empty: skuEmpty });
    }
  } else {
    // 兜底：从 DOM 提取（带规格图片）
    const skuWrapper = document.querySelector('[class*="skuWrapper"]');
    if (skuWrapper) {
      const skuItems = Array.from(skuWrapper.querySelectorAll('[class*="skuItem"]'));
      for (const item of skuItems) {
        const labelEl = item.querySelector('[class*="labelWrapTitle"] span') ||
                        item.querySelector('[class*="ItemLabel"] span');
        const label = labelEl?.innerText?.trim();
        if (!label) continue;
        const realValues = Array.from(item.querySelectorAll('[class*="valueItem"]'))
          .filter(el => {
            const cls = el.className;
            return cls.includes('valueItem--') && !cls.includes('valueItemImg') && !cls.includes('valueItemText');
          })
          .map(el => {
            const imgEl = el.querySelector('img');
            const rawSrc = imgEl?.src || imgEl?.dataset?.src || imgEl?.dataset?.lazySrc || null;
            return {
              text : el.querySelector('[class*="valueItemText"]')?.innerText?.trim()?.split('\n')[0]
                     || el.innerText?.trim()?.split('\n')[0],
              img  : normalizeAliImg(rawSrc),
              vid  : el.querySelector('[data-vid]')?.dataset?.vid || null,
            };
          })
          .filter(v => v.text);
        const seenTexts = new Set();
        const unique = realValues.filter(v => { if (seenTexts.has(v.text)) return false; seenTexts.add(v.text); return true; });
        if (unique.length) specs.push({ label, values: unique });
      }
      const seenLabels = new Set();
      const deduped = specs.filter(s => { if (seenLabels.has(s.label)) return false; seenLabels.add(s.label); return true; });
      specs.length = 0;
      specs.push(...deduped);
    }
  }

  // ── 商品参数 ──
  const params = [];
  const paramSection = document.querySelector('.paramsInfoArea, [class*="paramsInfoArea"]');
  if (paramSection) {
    const emphasisItems = Array.from(paramSection.querySelectorAll('[class*="emphasisParamsInfoItem"]'));
    for (const item of emphasisItems) {
      const value = item.querySelector('[class*="emphasisParamsInfoItemTitle"]')?.innerText?.trim();
      const label = item.querySelector('[class*="emphasisParamsInfoItemSubTitle"]')?.innerText?.trim();
      if (label && value) params.push({ label, value, type: 'emphasis' });
    }
    const generalItems = Array.from(paramSection.querySelectorAll('[class*="generalParamsInfoItem"]'));
    for (const item of generalItems) {
      const label = item.querySelector('[class*="generalParamsInfoItemTitle"]')?.innerText?.trim();
      const value = item.querySelector('[class*="generalParamsInfoItemSubTitle"]')?.innerText?.trim();
      if (label && value) params.push({ label, value, type: 'general' });
    }
  }

  // ── 价格（默认展示价） ──
  const priceEl = document.querySelector('[class*="price"] [class*="priceText"], [class*="Price"] em, [class*="price--"]');
  // ICE 兜底：取 sku2info 第一条的价格
  const iceFirstSkuPrice = Object.values(iceSku2info)[0]?.price?.priceText || null;
  const price = priceEl?.innerText?.trim() || iceFirstSkuPrice || '';

  // ── 已售数量 ──
  const soldEl = document.querySelector('[class*="sold"], [class*="Sold"]');
  const sold = soldEl?.innerText?.trim()?.replace(/[^\d万+]/g, '') || '';

  return { title, images, specs, skus, params, price, sold };
})()
```

> **⚠️ 关于 SKU 价格的交互增强（仅 webAuto popup 执行，Playwright 不适用）**  
> 当上述脚本返回 `skus: []`（即两条 ICE 路径都无法获取价格），webAuto popup 会自动逐一点击每个规格值（通过 `data-vid` 定位），读取页面更新后的展示价，构建合成 `skus` 并将价格回写到 `specs.values[i].price`。  
> Playwright 侧若需类似功能，请自行实现点击-采价逻辑，或接收 webAuto popup 保存后的结果。

---

## Python 注入示例（Playwright）

```python
from pathlib import Path
import json

def extract_taobao_product(page) -> dict:
    """
    在已打开的淘宝商品详情页中注入脚本，采集商品信息。

    Args:
        page: Playwright page 对象，需已导航到淘宝商品详情页

    Returns:
        dict 含 title, images, specs, skus, params, price, sold
        注意：Playwright 路径不含交互增强（点击规格抓价），
              若 skus 为空且 specs 有 vid，需自行点击规格后再次调用。
    """
    script_path = Path(r"C:\Users\yao\Desktop\work\webAuto\mcp-server\script\taobao-product-extract.js")
    if script_path.exists():
        code = script_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"脚本未找到：{script_path}")

    result = page.evaluate(code)
    return result

# 使用示例
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        page = browser.contexts[0].pages[0]
        info = extract_taobao_product(page)
        print(f"标题：{info['title']}")
        print(f"售价：{info['price']}，已售：{info['sold']}")
        print(f"图片数：{len(info['images'])}")
        print(f"规格：{json.dumps(info['specs'], ensure_ascii=False)}")
        print(f"SKU价格：{json.dumps(info['skus'], ensure_ascii=False)}")
        print(f"参数数：{len(info['params'])}")
```

---

## 返回值结构

```json
{
  "title": "【品牌】商品名称 特征描述 ...",
  "price": "39.9",
  "sold": "1000+",
  "images": [
    "https://img.alicdn.com/imgextra/i1/xxx/TB1xxx.jpg",
    "https://img.alicdn.com/imgextra/i2/xxx/TB1xxx.heic_.webp"
  ],
  "specs": [
    {
      "label": "净含量",
      "values": [
        { "text": "60ml（到手2瓶）", "img": "https://gw.alicdn.com/...heic_.webp", "vid": "45913",    "empty": false, "price": "259" },
        { "text": "30ml",           "img": null,                                   "vid": "75367145", "empty": false, "price": "149" }
      ]
    },
    {
      "label": "颜色分类",
      "values": [
        { "text": "白色", "img": "https://img.alicdn.com/...jpg", "vid": "123", "empty": false, "price": "39.9" },
        { "text": "黑色", "img": "https://img.alicdn.com/...jpg", "vid": "456", "empty": true,  "price": null  }
      ]
    }
  ],
  "skus": [
    { "skuId": "5812345678", "vids": ["45913"],    "names": ["60ml（到手2瓶）"], "price": "259", "empty": false },
    { "skuId": "5812345679", "vids": ["75367145"], "names": ["30ml"],           "price": "149", "empty": false }
  ],
  "params": [
    { "label": "使用部位",   "value": "面部",     "type": "emphasis" },
    { "label": "品牌",       "value": "某品牌",   "type": "general"  },
    { "label": "适用季节",   "value": "四季通用", "type": "general"  }
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | `string` | 商品标题 |
| `price` | `string` | 页面展示起步价（ICE 兜底 sku2info 第一条；可能为空字符串） |
| `sold` | `string` | 已售数量（纯数字或含「万」「+」，如 `"1000+"` / `"2万+"`） |
| `images` | `string[]` | 主图列表（已规范化 URL，优先 ICE 静态数据，兜底 DOM 缩略图） |
| `specs` | `object[]` | 规格列表（见下方 specs.values 说明） |
| `skus` | `object[]` | SKU 精确价格列表（见下方 skus 说明） |
| `params` | `object[]` | 商品参数，含 `label`、`value`、`type`（`emphasis`/`general`） |

#### specs.values 字段

| 子字段 | 类型 | 说明 |
|---|---|---|
| `text` | `string` | 规格值名称，如 `"红色"` |
| `img` | `string\|null` | 规格主图 URL（已规范化），无图为 `null` |
| `vid` | `string` | 淘宝规格值 ID（来自 ICE 数据），DOM 兜底路径可能为 `null` |
| `empty` | `boolean` | `true` = 该规格值缺货 |
| `price` | `string\|null` | 对应 SKU 价格（由 `skus` 回写；Playwright 直接注入时若 `skus` 为空则为 `null`） |

#### skus 字段

| 子字段 | 类型 | 说明 |
|---|---|---|
| `skuId` | `string\|null` | 淘宝 skuId；交互增强抓取时为 `null` |
| `vids` | `string[]` | 对应的 vid 组合（单规格为 1 个，多规格组合为 N 个） |
| `names` | `string[]` | 对应的规格值名称组合 |
| `price` | `string\|null` | 精确售价，如 `"21.9"` |
| `empty` | `boolean` | `true` = 该 SKU 缺货 |

> **推荐读取方式：**
> - 单规格商品 → 直接读 `specs.values[i].price`（已回写，自包含）
> - 多规格组合定价 → 读 `skus[i].names` + `skus[i].price`

---

## 图片 URL 规范化说明

| 原始 URL 后缀 | 处理方式 | 结果 |
|---|---|---|
| `~crop_0_0_800_800~.jpg` | 移除 `~crop...~` 部分 | `.jpg` |
| `_q50.jpg_.webp` | 移除压缩后缀 | `.jpg` |
| `.webp` | 移除 | 还原为原始后缀 |
| `.heic` | **追加** `_.webp` | `.heic_.webp`（让阿里 CDN 转码，直接改为 `.jpg` 会得到 1×1 空图）|

---

## 使用场景

- **批量竞品采集**：从竞品详情页采集商品参数，辅助选品决策。
- **商品同步上架**：采集数据后，传给 assistantService 保存到本地并进行图片下载和上架处理。
- **参数对比分析**：采集多个商品的 `params` 字段，用于商品规格对比。

---

## 注意事项

1. **需在商品详情页注入**：脚本选择器基于淘宝详情页的 DOM 结构，在列表页无效。
2. **ICE 数据优先**：优先从 `window.__ICE_APP_CONTEXT__` 读取静态结构化数据（图片、规格、SKU价格），避免 DOM 动态渲染问题。
3. **SKU 价格三路径兜底**：
   - 路径1：`skuBase.skus`（有 propPath，精确）
   - 路径2：`sku2info` 直接遍历（skuBase.skus 为空时）
   - 路径3：交互增强——逐一点击规格值读展示价（**仅 webAuto popup 执行**，Playwright 不含此逻辑）
4. **价格为展示价**：`price` 字段是页面展示的起步价，精确 SKU 价格在 `specs.values[i].price` 和 `skus[i].price`。
5. **参数加载**：商品参数区域需页面滚动到该位置后才渲染，若返回 `params: []` 可先 `page.evaluate("window.scrollTo(0, 3000)")` 再重新采集。

---

## 本地保存接口（assistantService）

采集到的商品数据可通过 webAuto popup「保存商品」按钮或直接 POST 到 assistantService 保存。

### 接口定义

```
POST http://127.0.0.1:8887/api/taobao/save-product
Content-Type: application/json
```

**请求体：**

```json
{
  "title": "商品标题",
  "price": "39.9",
  "sold": "1000+",
  "url": "https://item.taobao.com/item.htm?id=...",
  "images": ["https://img.alicdn.com/...jpg", "..."],
  "specs": [
    {
      "label": "净含量",
      "values": [
        { "text": "60ml（到手2瓶）", "img": "https://...", "vid": "45913", "empty": false, "price": "259" },
        { "text": "30ml",           "img": null,          "vid": "75367145","empty": false, "price": "149" }
      ]
    }
  ],
  "skus": [
    { "skuId": "5812345678", "vids": ["45913"],    "names": ["60ml（到手2瓶）"], "price": "259", "empty": false },
    { "skuId": "5812345679", "vids": ["75367145"], "names": ["30ml"],           "price": "149", "empty": false }
  ],
  "params": [
    { "label": "品牌", "value": "某品牌", "type": "emphasis" },
    { "label": "材质", "value": "纯棉",   "type": "general"  }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✓ | 商品标题，同时作为本地文件夹名（截断到 80 字符，去除非法字符） |
| `price` | string | | 起步售价 |
| `sold` | string | | 已售数量 |
| `url` | string | | 商品详情页 URL |
| `images` | string[] | | 主图 URL 列表（将全部下载到本地） |
| `specs` | object[] | | 规格列表；`values` 为对象数组（含 `text/img/vid/empty/price`） |
| `skus` | object[] | | SKU 价格列表（含 `skuId/vids/names/price/empty`） |
| `params` | object[] | | 参数列表（含 `label/value/type`） |

**响应体：**

```json
{
  "ok": true,
  "folder": "C:\\Users\\yao\\Desktop\\work\\电商数据\\淘宝\\商品标题",
  "imageTotal": 5,
  "imageOk": 5,
  "log": [
    "✓ 商品目录: C:\\...\\商品标题",
    "✓ 图片下载: 5/5 张成功",
    "✓ 单品 Excel 已写入",
    "✓ 汇总 Excel 已更新",
    "✓ 汇总 README.md 已更新"
  ]
}
```

### 保存目录结构

```
C:\Users\yao\Desktop\work\电商数据\淘宝\
├── README.md                     ← 汇总 Markdown（所有商品表格，每次追加/更新一行）
├── 淘宝商品汇总.xlsx              ← 汇总 Excel（每行一个商品，重复标题自动更新）
└── {商品标题}\                   ← 单商品文件夹（名称 = 商品标题，最长 80 字）
    ├── 商品信息.xlsx              ← 单品四 Sheet Excel（见下方）
    └── images\                   ← 下载的主图
        ├── 01.jpg
        ├── 02.jpg
        └── ...
```

### 单品 Excel 结构（`商品信息.xlsx`）

| Sheet | 列 | 说明 |
|---|---|---|
| **基本信息** | 字段 / 值 | 标题、价格、已售、商品URL、采集时间 |
| **规格** | 规格标签 / 规格值 / 价格 / 图片URL / vid / 缺货 | 每个规格值独立一行（兼容新旧格式） |
| **SKU价格** | skuId / 规格组合 / 价格 / 缺货 | 多规格组合精确定价（来自 `skus` 字段） |
| **参数** | 参数名 / 参数值 / 类型 | emphasis=强调参数，general=普通参数 |
| **图片** | 序号 / 原始URL / 本地文件名 / 下载状态 | 记录每张图片的下载结果 |

### 汇总 Excel 列说明（`淘宝商品汇总.xlsx`）

| 列 | 说明 |
|---|---|
| 商品标题 | 同文件夹名 |
| 价格 | 采集时起步售价 |
| 已售 | 已售数量 |
| 规格值数 | 所有规格值的总数 |
| 参数数 | 参数条目总数 |
| 图片数 | 图片 URL 总数（含下载失败） |
| 本地目录 | 商品文件夹完整路径 |
| 商品URL | 详情页链接 |
| 采集时间 | 保存时间戳 |
| 上架店铺 | 发布到的淘宝店铺名称（**上架后回填**，初始为空） |
| 上架时间 | 商品发布时间（**上架后回填**） |
| 上架链接 | 发布后淘宝商品详情链接（**上架后回填**，初始为空） |

### 源码位置

| 文件 | 路径 |
|---|---|
| 接口实现 | `assistantService/src/api/routes/taobao_routes.py` |
| popup 调用 | `webAuto/chrome-extension/src/popup/pages/TaobaoAssistant.jsx`（`onSaveProduct` 函数） |

### webAuto popup 调用方式

popup 通过 background CSP 绕过通道（`pddFeishuSync`）发起请求：

```javascript
// TaobaoAssistant.jsx 内的 postToAssistant 函数
chrome.runtime.sendMessage({
  type: 'pddFeishuSync',
  params: {
    url: 'http://127.0.0.1:8887/api/taobao/save-product',
    body: { title, price, sold, url, images, specs, skus, params }
  }
}, (res) => {
  console.log(res.json)  // { ok, folder, imageTotal, imageOk, log }
})
```

---

## 上架回填接口（assistantService）

商品在发布表单提交成功后，调用此接口将店铺名称等信息回填到汇总 Excel 与单品 Excel。

### 接口定义

```
POST http://127.0.0.1:8887/api/taobao/mark-uploaded
Content-Type: application/json
```

**请求体：**

```json
{
  "title":      "商品标题",
  "shopName":   "乐帮购精品",
  "itemUrl":    "https://item.taobao.com/item.htm?id=123456",
  "uploadTime": "2026-05-26 10:00:00"
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✓ | 商品标题（与 save-product 时一致，用于定位汇总表行） |
| `shopName` | string | | 上架店铺名称 |
| `itemUrl` | string | | 上架后淘宝商品链接 |
| `uploadTime` | string | | 上架时间（默认当前时间） |

**响应体：**

```json
{
  "ok": true,
  "found": true,
  "log": [
    "✓ 汇总 Excel 已回填上架信息",
    "✓ 单品 Excel 基本信息已更新",
    "✓ 汇总 README.md 已更新"
  ]
}
```

### 回填效果

- **汇总 Excel**（`淘宝商品汇总.xlsx`）：找到标题匹配行，将 `上架店铺`、`上架时间`、`上架链接` 三列写入。
- **单品 Excel**（`商品信息.xlsx` → `基本信息` Sheet）：在字段列表末尾追加/更新 `上架店铺`、`上架时间`、`上架链接` 三行。
- **汇总 README.md**：同步更新对应行末尾三列。

### webAuto popup 调用方式

商品发布成功后，`TaobaoAssistant.jsx` 的「标记已上架」面板触发：

```javascript
// TaobaoAssistant.jsx 内的 onMarkUploaded 函数
chrome.runtime.sendMessage({
  type: 'pddFeishuSync',
  params: {
    url: 'http://127.0.0.1:8887/api/taobao/mark-uploaded',
    body: { title, shopName, itemUrl }
  }
}, (res) => {
  console.log(res.json)  // { ok, found, log }
})
```

### 操作流程

1. 在淘宝商品详情页点「获取商品信息」→「保存商品」（调用 `save-product`，汇总表创建行）
2. 点「同步商品」→「开始上传」完成发布表单填写
3. 在淘宝后台手动提交（或自动提交后确认发布）
4. 回到 popup，点「**商品已提交？标记已上架并回填总表**」
5. 填写/确认店铺名称（可点「自动获取」从卖家中心标签页读取），可选填上架链接
6. 点「确认回填」→ 三处文件（汇总Excel / 单品Excel / README.md）同步更新
