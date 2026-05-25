# 淘宝商品信息采集脚本

> 采集逻辑维护在 webAuto Chrome 扩展 popup 组件中：
> `C:\Users\yao\Desktop\work\webAuto\chrome-extension\src\popup\pages\TaobaoAssistant.jsx`  
> 内嵌脚本常量名：`EXTRACT_CODE`

**目标页面**：淘宝商品详情页（`https://item.taobao.com/item.htm?id=...`）  
**功能**：采集商品标题、主图列表（还原原图 URL）、销售规格（SKU）、商品参数、售价、已售量。

---

## 采集脚本（可直接用于 Playwright 注入）

```javascript
// taobao-product-extract.js
// 在淘宝商品详情页注入，返回商品完整信息
(function () {
  // ── 标题 ──
  const titleEl = document.querySelector('[class*="mainTitle"]');
  const title = titleEl?.innerText?.trim() || document.title;

  // ── 主图缩略图 → 还原原图 URL ──
  const thumbEls = Array.from(document.querySelectorAll('[class*="thumbnailPic"]'));
  const images = thumbEls.map(img => {
    let src = img.src || '';
    src = src.replace(/~crop[^~]*~/, '');
    src = src.replace(/_q50\.jpg_\.(webp|web)$/, '')
             .replace(/\.webp$/, '')
             .replace(/\.heic$/, '.jpg');
    return src;
  }).filter(Boolean);

  // ── 销售规格（SKU）──
  const specs = [];
  const skuWrapper = document.querySelector('[class*="skuWrapper"]');
  if (skuWrapper) {
    const skuItems = Array.from(skuWrapper.querySelectorAll('[class*="skuItem"]'));
    for (const item of skuItems) {
      const labelEl = item.querySelector('[class*="labelWrapTitle"] span') ||
                      item.querySelector('[class*="ItemLabel"] span');
      const label = labelEl?.innerText?.trim();
      if (!label) continue;
      const values = Array.from(item.querySelectorAll('[class*="valueItem"]'))
        .map(v => v.innerText?.trim()?.split('\n')[0])
        .filter(Boolean);
      const unique = [...new Set(values)];
      if (unique.length) specs.push({ label, values: unique });
    }
    const seenLabels = new Set();
    const deduped = specs.filter(s => {
      if (seenLabels.has(s.label)) return false;
      seenLabels.add(s.label);
      return true;
    });
    specs.length = 0;
    specs.push(...deduped);
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

  // ── 价格 ──
  const priceEl = document.querySelector('[class*="price"] [class*="priceText"], [class*="Price"] em, [class*="price--"]');
  const price = priceEl?.innerText?.trim();

  // ── 已售数量 ──
  const soldEl = document.querySelector('[class*="sold"], [class*="Sold"]');
  const sold = soldEl?.innerText?.trim()?.replace(/[^\d万+]/g, '') || '';

  return { title, images, specs, params, price, sold };
})()
```

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
        dict 含 title, images, specs, params, price, sold
    """
    script_path = Path(r"C:\Users\yao\Desktop\work\webAuto\mcp-server\script\taobao-product-extract.js")
    if script_path.exists():
        code = script_path.read_text(encoding="utf-8")
    else:
        # 也可直接内嵌脚本字符串（见上方）
        raise FileNotFoundError(f"脚本未找到：{script_path}")

    result = page.evaluate(code)
    return result

# 使用示例
async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")  # 连接已有 Chrome
        page = browser.contexts[0].pages[0]  # 取已打开的淘宝详情页
        info = extract_taobao_product(page)
        print(f"标题：{info['title']}")
        print(f"售价：{info['price']}，已售：{info['sold']}")
        print(f"图片数：{len(info['images'])}")
        print(f"规格：{json.dumps(info['specs'], ensure_ascii=False)}")
        print(f"参数数：{len(info['params'])}")
```

---

## 返回值结构

```json
{
  "title": "【品牌】商品名称 特征描述 ...",
  "images": [
    "https://img.alicdn.com/imgextra/i1/xxx/TB1xxx.jpg",
    "https://img.alicdn.com/imgextra/i2/xxx/TB2xxx.jpg"
  ],
  "specs": [
    {
      "label": "颜色分类",
      "values": ["白色", "黑色", "蓝色"]
    },
    {
      "label": "尺码",
      "values": ["S", "M", "L", "XL"]
    }
  ],
  "params": [
    { "label": "品牌", "value": "某品牌", "type": "emphasis" },
    { "label": "材质", "value": "纯棉", "type": "general" },
    { "label": "适用季节", "value": "春秋", "type": "general" }
  ],
  "price": "39.9",
  "sold": "1000+"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `title` | `string` | 商品标题（来自 `[class*="mainTitle"]`） |
| `images` | `string[]` | 主图列表，已去除裁剪参数，还原为原图 `.jpg` URL |
| `specs` | `object[]` | SKU 规格，每项含 `label`（规格名）和 `values`（规格值列表） |
| `params` | `object[]` | 商品参数，含 `label`、`value`、`type`（`emphasis`=强调参数/`general`=普通参数） |
| `price` | `string` | 页面展示售价（字符串，含小数，如 `"39.9"`） |
| `sold` | `string` | 已售数量（纯数字或含「万」「+」，如 `"1000+"` / `"2万+"`） |

---

## 图片 URL 还原说明

淘宝缩略图 URL 通常包含裁剪参数，脚本会自动清理：

| 原始 URL 后缀 | 处理方式 | 结果 |
|---|---|---|
| `~crop_0_0_800_800~.jpg` | 移除 `~crop...~` 部分 | `.jpg` |
| `_q50.jpg_.webp` | 移除后缀 | `.jpg` |
| `.webp` | 移除 | （还原为原始后缀） |
| `.heic` | 替换 | `.jpg` |

---

## 使用场景

- **批量竞品采集**：从竞品详情页采集商品参数，辅助选品决策。
- **商品同步上架**：采集商品数据后，传给 assistantService 进行图片下载和淘宝卖家平台上架（通过 `pyautogui` 上传图片）。
- **参数对比分析**：采集多个商品的 `params` 字段，用于商品规格对比。

---

## 注意事项

1. **需在商品详情页注入**：脚本选择器基于淘宝详情页的 DOM 结构，在列表页无效。
2. **图片数量**：`images` 取自页面底部缩略图列表，部分商品主图与缩略图不完全一致。
3. **价格为展示价**：采集的是页面当前显示价格，可能是活动价或区间价起始值。
4. **参数加载**：商品参数区域（`paramsInfoArea`）需页面滚动到该位置后才渲染，若返回 `params: []` 可先 `page.evaluate("window.scrollTo(0, 3000)")` 再重新采集。

---

## 本地保存接口（assistantService）

采集到的商品数据可通过 webAuto popup「保存商品」按钮或直接 POST 到 assistantService 保存到本地磁盘。

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
    { "label": "颜色分类", "values": ["白色", "黑色"] }
  ],
  "params": [
    { "label": "品牌", "value": "某品牌", "type": "emphasis" },
    { "label": "材质", "value": "纯棉", "type": "general" }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | ✓ | 商品标题，同时作为本地文件夹名（截断到 80 字符，去除非法字符） |
| `price` | string | | 售价 |
| `sold` | string | | 已售数量 |
| `url` | string | | 商品详情页 URL |
| `images` | string[] | | 主图 URL 列表（将全部下载到本地） |
| `specs` | object[] | | 规格列表，结构同采集脚本返回值 |
| `params` | object[] | | 参数列表，结构同采集脚本返回值 |

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
| **规格** | 规格标签 / 规格值 | 每个规格值独立一行 |
| **参数** | 参数名 / 参数值 / 类型 | emphasis=强调参数，general=普通参数 |
| **图片** | 序号 / 原始URL / 本地文件名 / 下载状态 | 记录每张图片的下载结果 |

### 汇总 Excel 列说明（`淘宝商品汇总.xlsx`）

| 列 | 说明 |
|---|---|
| 商品标题 | 同文件夹名 |
| 价格 | 采集时售价 |
| 已售 | 已售数量 |
| 规格值数 | 所有规格值的总数 |
| 参数数 | 参数条目总数 |
| 图片数 | 图片 URL 总数（含下载失败） |
| 本地目录 | 商品文件夹完整路径 |
| 商品URL | 详情页链接 |
| 采集时间 | 保存时间戳 |

### 源码位置

| 文件 | 路径 |
|---|---|
| 接口实现 | `assistantService/src/api/routes/taobao_routes.py` |
| popup 调用 | `webAuto/chrome-extension/src/popup/pages/TaobaoAssistant.jsx`（`onSaveProduct` 函数） |

### webAuto popup 调用方式

popup 通过 background CSP 绕过通道 (`pddFeishuSync`) 发起请求，无需用户关心跨域问题：

```javascript
// TaobaoAssistant.jsx 内的 postToAssistant 函数
chrome.runtime.sendMessage({
  type: 'pddFeishuSync',
  params: {
    url: 'http://127.0.0.1:8887/api/taobao/save-product',
    body: { title, price, sold, url, images, specs, params }
  }
}, (res) => {
  console.log(res.json)  // { ok, folder, imageTotal, imageOk, log }
})
```
