# 拼多多 ERP 订单脚本集

> 脚本源路径：`C:\Users\yao\Desktop\work\webAuto\mcp-server\script\`  
> 目标域名：`https://mms.pinduoduo.com/erp/`

---

## 1. `pdd-erp-order-all-table.js` — 全部订单列表

**目标页面**：`https://mms.pinduoduo.com/erp/order/all`  
**功能**：全量抓取 ERP 全部订单列表，支持虚拟滚动翻页，字段与飞书多维表格对齐。

### Python 注入示例

```python
import json
from pathlib import Path

SCRIPT_DIR = Path(r"C:\Users\yao\Desktop\work\webAuto\mcp-server\script")

def collect_all_orders(page, sync_url: str = None) -> dict:
    code = (SCRIPT_DIR / "pdd-erp-order-all-table.js").read_text(encoding="utf-8")
    # 设置运行模式
    page.evaluate("window.__PDD_ERP_ORDER_ALL_RUN_MODE = 'python';")
    # 可选：开启自动滚动（默认已开启）
    page.evaluate("window.__PDD_ERP_ORDER_ALL_AUTO_SCROLL = true;")
    page.evaluate("window.__PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS = 600;")
    if sync_url:
        page.evaluate(f"window.__PDD_ERP_ORDER_ALL_SYNC_URL = {json.dumps(sync_url)};")
    result = page.evaluate(code)
    # python 模式下可手动上报
    if sync_url and result.get("syncBody"):
        import requests
        requests.post(sync_url, json=result["syncBody"], timeout=30)
    return result
```

### 返回值结构

```json
{
  "ok": true,
  "rows": [
    {
      "平台订单号": "260501-123456789012345",
      "店铺": "乐帮购精品",
      "系统订单号": "ERP-XXXX",
      "是否打印快递单": "已打印",
      "收件人": "张三",
      "收件电话": "138****8888",
      "收件省": "广东",
      "收件市": "深圳",
      "商品信息": "商品名称 规格 x1",
      "商品快照": "https://img.alicdn.com/...",
      "快递公司": "极兔速递",
      "快递单号": "JT123456789",
      "实收金额": "32.29",
      "付款时间": "2026/05/01 09:11"
    }
  ],
  "log": ["已采集 xx 行", "..."],
  "syncBody": { "rows": [] },
  "syncUrl": "http://127.0.0.1:8887/api/pinduoduo/...",
  "runMode": "python"
}
```

### 可选配置参数

| `window` 变量 | 默认值 | 说明 |
|---|---|---|
| `__PDD_ERP_ORDER_ALL_RUN_MODE` | `'extension'` | 运行模式，assistantService 设为 `'python'` |
| `__PDD_ERP_ORDER_ALL_AUTO_SCROLL` | `true` | 是否自动滚动加载全部 |
| `__PDD_ERP_ORDER_ALL_SCROLL_MAX_STEPS` | `600` | 最大滚动步数 |
| `__PDD_ERP_ORDER_ALL_SCROLL_PAUSE_MS` | `500` | 每步滚动后等待 ms |
| `__PDD_ERP_ORDER_ALL_SCROLL_STEP_RATIO` | `0.88` | 每步滚动视口高度比 |
| `__PDD_ERP_ORDER_ALL_RESTORE_SCROLL` | `true` | 结束后是否回到顶部 |
| `__PDD_ERP_ORDER_ALL_SYNC_URL` | `''` | 同步上报地址 |
| `__PDD_ERP_ORDER_ALL_INCLUDE_LEGACY` | `false` | 是否附带调试字段 `rowsLegacy` |
| `__PDD_ERP_REMINDER_TD_NTH` | `2` | 提醒列位置（从1起），0=关闭 |

**对应 assistantService 路由**：`spider/pinduoduo/erp_order_sync.py`

---

## 2. `pdd-erp-order-audit-goods.js` — 审核订单商品规格

**目标页面**：`https://mms.pinduoduo.com/erp/order/audit`  
**功能**：抓取待审核订单的商品规格信息；可联动勾选指定订单并自动提交审核。

### Python 注入示例

```python
def collect_audit_orders(page, filter_order_nos: list = None, do_audit: bool = False) -> dict:
    code = (SCRIPT_DIR / "pdd-erp-order-audit-goods.js").read_text(encoding="utf-8")
    page.evaluate("window.__PDD_ERP_AUDIT_GOODS_RUN_MODE = 'python';")
    if filter_order_nos:
        page.evaluate(f"window.__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS = {json.dumps(filter_order_nos)};")
    if do_audit:
        page.evaluate("window.__PDD_ERP_AUDIT_GOODS_DO_AUDIT = true;")
    return page.evaluate(code)
```

### 返回值结构

```json
{
  "ok": true,
  "rows": [
    {
      "平台订单号": "260501-123456789012345",
      "shopName": "乐帮购精品",
      "actualAmount": "¥32.29",
      "goods": [
        {
          "imgSrc": "https://img.alicdn.com/...",
          "title": "商品名称",
          "spec": "规格描述",
          "qty": "x1"
        }
      ]
    }
  ],
  "log": ["采集到 xx 条订单"]
}
```

### 可选配置参数

| `window` 变量 | 默认值 | 说明 |
|---|---|---|
| `__PDD_ERP_AUDIT_GOODS_RUN_MODE` | `'extension'` | 运行模式 |
| `__PDD_ERP_AUDIT_GOODS_AUTO_SCROLL` | `true` | 自动滚动 |
| `__PDD_ERP_AUDIT_GOODS_SCROLL_MAX_STEPS` | `600` | 最大滚动步数 |
| `__PDD_ERP_AUDIT_GOODS_FILTER_ORDER_NOS` | `null` | 订单号白名单（仅返回指定订单） |
| `__PDD_ERP_AUDIT_GOODS_CHECK_ORDER_NOS` | `null` | 勾选指定订单（`true` 则与 FILTER 联动） |
| `__PDD_ERP_AUDIT_GOODS_DO_AUDIT` | `false` | ⚠️ 勾选后自动点击「审核」提交，谨慎使用！ |

**对应 assistantService 路由**：`spider/pinduoduo/erp_audit.py`

---

## 3. `pdd-erp-order-presell-list.js` — 预售订单

**目标页面**：`https://mms.pinduoduo.com/erp/order/presell`  
**功能**：抓取预售订单列表，字段含商品图片、支付时间（自动补年份）、goods 数组。

### Python 注入示例

```python
def collect_presell_orders(page, auto_scroll: bool = False) -> dict:
    code = (SCRIPT_DIR / "pdd-erp-order-presell-list.js").read_text(encoding="utf-8")
    page.evaluate("window.__PDD_ERP_PRESELL_RUN_MODE = 'python';")
    if auto_scroll:
        page.evaluate("window.__PDD_ERP_PRESELL_AUTO_SCROLL = true;")
    return page.evaluate(code)
```

### 返回值结构

```json
{
  "ok": true,
  "orders": [
    {
      "orderNo": "260513-181749727613319",
      "erpOrderNo": "FH2026051300001",
      "支付时间": "2026/05/13 17:20",
      "支付时间原文": "05-13 17:20 支付",
      "图片": "https://img.alicdn.com/...",
      "图片列表": ["https://..."],
      "goods": [{ "imgSrc": "...", "title": "...", "spec": "...", "qty": "x1" }]
    }
  ],
  "log": ["采集到 xx 条预售订单"],
  "syncBody": { "orders": [] },
  "runMode": "python"
}
```

### 可选配置参数

| `window` 变量 | 默认值 | 说明 |
|---|---|---|
| `__PDD_ERP_PRESELL_RUN_MODE` | `'extension'` | 运行模式 |
| `__PDD_ERP_PRESELL_AUTO_SCROLL` | `false` | 是否自动滚动（列表较长时开启） |
| `__PDD_ERP_PRESELL_SCROLL_MAX_STEPS` | `200` | 最大滚动步数 |
| `__PDD_ERP_PRESELL_SCROLL_PAUSE_MS` | `500` | 每步暂停 ms |

**对应 assistantService 路由**：`spider/pinduoduo/presell_sync.py`

---

## 4. `pdd-erp-order-delivered-query.js` — 已发货查询

**目标页面**：`https://mms.pinduoduo.com/erp/order/delivered`  
**功能**：自动筛选（时间类型+日期范围+打印状态）后抓取已发货订单，默认抓「今天·已打印快递单」。

### Python 注入示例

```python
def collect_delivered_orders(page, date_shortcut: str = "今天", print_status: str = "已打印快递单") -> dict:
    code = (SCRIPT_DIR / "pdd-erp-order-delivered-query.js").read_text(encoding="utf-8")
    page.evaluate(f"window.__PDD_ERP_DELIVERED_DATE_SHORTCUT = {json.dumps(date_shortcut)};")
    page.evaluate(f"window.__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS = {json.dumps(print_status)};")
    return page.evaluate(code)
```

### 返回值结构

```json
{
  "ok": true,
  "rows": [
    {
      "orderNo": "260501-123456789012345",
      "erpOrderNo": "ERP-XXXX",
      "goods": [{ "imgSrc": "...", "title": "...", "spec": "...", "qty": "x1" }],
      "imgUrl": "https://img.alicdn.com/...",
      "express": "极兔速递 JT123456789",
      "deliveredAt": "2026/05/01 14:30",
      "printStatus": "已打印快递单"
    }
  ],
  "log": ["筛选完成，采集到 xx 条"]
}
```

### 可选配置参数

| `window` 变量 | 默认值 | 说明 |
|---|---|---|
| `__PDD_ERP_DELIVERED_FILTER_PRINT_STATUS` | `'已打印快递单'` | `''` 表示不筛选 |
| `__PDD_ERP_DELIVERED_TIME_TYPE` | `'发货时间'` | 可选 `'付款时间'` / `'审核时间'` |
| `__PDD_ERP_DELIVERED_DATE_SHORTCUT` | `'今天'` | 可选 `'昨天'` / `'近7天'` / `'近30天'` |
| `__PDD_ERP_DELIVERED_AUTO_SCROLL` | `true` | 是否滚动加载全部 |
| `__PDD_ERP_DELIVERED_SCROLL_MAX_STEPS` | `200` | 最大滚动步数 |

**对应 assistantService 路由**：`/api/pinduoduo/erp-delivered/today-printed-query`

---

## 5. `pdd-erp-order-delivering-print-ship.js` — 待发货打印发货

**目标页面**：`https://mms.pinduoduo.com/erp/order/delivering`  
**功能**：操作脚本（非采集）。全选订单 → 打印快递单 → 打印并发货，全程自动点击。

> ⚠️ **此脚本会触发真实发货操作，请在确认订单无误后执行。**

### Python 注入示例

```python
def print_and_ship(page) -> dict:
    """在待发货页执行全选→打印→发货流程，建议 timeout >= 30s"""
    code = (SCRIPT_DIR / "pdd-erp-order-delivering-print-ship.js").read_text(encoding="utf-8")
    # 此脚本无运行模式切换，直接注入执行
    result = page.evaluate(code)
    # result['empty'] = True 时列表无订单，result['success'] 表示操作是否成功
    return result
```

### 返回值结构

```json
{
  "success": true,
  "empty": false,
  "log": [
    "检测到 xx 条待发货订单",
    "全选 checkbox 已勾选",
    "点击「打印快递单」",
    "确认选择",
    "打印并发货 clicked",
    "列表已清空，发货成功"
  ]
}
```

**无需配置参数**，脚本默认全选当前页所有订单。

**对应 assistantService 路由**：`/api/pinduoduo/erp-delivering/print-ship`

---

## 6. `get_pdd_orders.js` — 拼多多管理后台订单

**目标页面**：`https://mms.pinduoduo.com/order/manage`（拼多多官方管理后台，非 ERP）  
**功能**：采集管理后台订单列表并同步飞书。

### Python 注入示例

```python
def collect_pdd_orders(page, sync_url: str = "http://127.0.0.1:8887/api/pinduoduo/feishu-order-list/sync") -> dict:
    code = (SCRIPT_DIR / "get_pdd_orders.js").read_text(encoding="utf-8")
    page.evaluate("window.__PDD_ORDERS_RUN_MODE = 'python';")
    page.evaluate(f"window.__PDD_ORDERS_SYNC_URL = {json.dumps(sync_url)};")
    result = page.evaluate(code)
    if result.get("syncBody"):
        import requests
        requests.post(sync_url, json=result["syncBody"], timeout=30)
    return result
```

**对应 assistantService 路由**：`/api/pinduoduo/sync-to-feishu`（⚠️ 注意：webAuto 默认调用 `/feishu-order-list/sync`，路径需对齐）
