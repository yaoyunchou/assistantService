# `pdd-after-sale-return-logistics.js` — 拼多多 ERP 售后退货物流采集

> 脚本源路径：`C:\Users\yao\Desktop\work\webAuto\mcp-server\script\pdd-after-sale-return-logistics.js`

**目标页面**：`https://mms.pinduoduo.com/erp/after-sale/manage`  
**功能**：在售后管理页面，逐行 hover 物流信息 popover，批量采集退货物流轨迹（快递公司、单号、最新状态、全部节点）。

---

## Python 注入示例

```python
import json
from pathlib import Path

SCRIPT_DIR = Path(r"C:\Users\yao\Desktop\work\webAuto\mcp-server\script")

def collect_return_logistics(
    page,
    filter_text: str = "退回/退货签收待处理",
    sync_url: str = None
) -> dict:
    """
    采集拼多多 ERP 售后页退货物流信息。

    Args:
        page: Playwright page 对象，需已导航到 ERP 售后管理页
        filter_text: 筛选项文字，默认 '退回/退货签收待处理'
        sync_url: 数据上报地址（可选），传入则采集后自动 POST

    Returns:
        dict 含 ok, results, skipped, log, stats
    """
    code = (SCRIPT_DIR / "pdd-after-sale-return-logistics.js").read_text(encoding="utf-8")
    page.evaluate("window.__PDD_LOGISTICS_RUN_MODE = 'python';")
    page.evaluate(f"window.__PDD_LOGISTICS_FILTER_TEXT = {json.dumps(filter_text)};")
    if sync_url:
        page.evaluate(f"window.__PDD_LOGISTICS_SYNC_URL = {json.dumps(sync_url)};")

    result = page.evaluate(code)

    # Python 模式下手动上报（如需要）
    if sync_url and result.get("ok") and result.get("results"):
        import requests
        requests.post(sync_url, json={"results": result["results"]}, timeout=30)

    return result
```

### 完整调用示例（结合 assistantService 浏览器池）

```python
from src.spider.pinduoduo.after_sale_sync import collect_return_logistics
from src.spider.client import get_browser_page   # 取已登录的拼多多 ERP session

async def sync_return_logistics_to_feishu():
    async with get_browser_page("https://mms.pinduoduo.com/erp/after-sale/manage") as page:
        result = collect_return_logistics(
            page,
            filter_text="退回/退货签收待处理",
            sync_url="http://127.0.0.1:8887/api/pinduoduo/after-sale/sync-logistics"
        )
        if not result["ok"]:
            raise RuntimeError(f"采集失败：{result.get('log')}")
        print(f"采集到 {result['stats']['withLogistics']} 条物流，跳过 {result['stats']['withoutLogistics']} 条")
        return result
```

---

## 返回值结构

```json
{
  "ok": true,
  "results": [
    {
      "orderNo": "260501-123456789012345",
      "carrier": "极兔速递",
      "trackNo": "JT123456789CN",
      "latestStatus": "已签收",
      "allStatuses": [
        "2026-05-03 14:30 已签收，签收人：本人",
        "2026-05-03 09:15 派件中",
        "2026-05-02 18:00 到达派件网点"
      ],
      "fullText": "极兔速递 JT123456789CN\n2026-05-03 14:30 已签收..."
    }
  ],
  "skipped": ["260501-999888777666555"],
  "log": [
    "筛选：退回/退货签收待处理",
    "共 15 行，开始 hover 采集",
    "采集完成：12 条有物流，3 条无"
  ],
  "stats": {
    "total": 15,
    "withLogistics": 12,
    "withoutLogistics": 3,
    "carriers": { "极兔速递": 8, "圆通速递": 4 }
  }
}
```

---

## 可选配置参数

| `window` 变量 | 默认值 | 说明 |
|---|---|---|
| `__PDD_LOGISTICS_RUN_MODE` | `'extension'` | 运行模式，assistantService 设为 `'python'` |
| `__PDD_LOGISTICS_FILTER_TEXT` | `'退回/退货签收待处理'` | 筛选项文字（页面左侧筛选标签） |
| `__PDD_LOGISTICS_HOVER_WAIT` | `350` | hover 后等待 popover 出现的毫秒数 |
| `__PDD_LOGISTICS_SCROLL_STEP` | `400` | 每次滚动像素 |
| `__PDD_LOGISTICS_SCROLL_WAIT` | `600` | 每次滚动后等待虚拟渲染 ms |
| `__PDD_LOGISTICS_SYNC_URL` | `''` | Python 模式下的上报地址（设置后脚本内不自动上报，需 Python 侧调用） |

---

## 注意事项

1. **hover 超时**：popover 加载依赖网络，`HOVER_WAIT` 若设置过短可能导致 popover 未出现就读取（默认 350ms 在网络良好时足够，网络较差时可调至 600ms）。
2. **虚拟滚动**：列表超过一屏时，脚本会自动滚动并逐行 hover，每步滚动后等待 `SCROLL_WAIT` ms 渲染。
3. **筛选时机**：脚本会自动点击左侧筛选标签（通过文字匹配），需在页面完全加载后注入。
4. **对应 assistantService 模块**：`src/spider/pinduoduo/after_sale_sync.py`
