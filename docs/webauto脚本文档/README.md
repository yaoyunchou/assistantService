# webAuto 脚本文档索引

> 本目录记录由 **webAuto** 项目（`mcp-server/script/`）维护的页面注入 JS 脚本在 **assistantService** 中的使用方式。
>
> 脚本源文件路径：`C:\Users\yao\Desktop\work\webAuto\mcp-server\script\`

## 双运行时说明

每个脚本均支持两种运行模式，执行前通过 `window.__*_RUN_MODE` 切换：

| 模式 | 触发方 | 行为 |
|---|---|---|
| `extension`（默认） | webAuto chrome-robot | 采集后经扩展桥 background POST 同步到 8887 |
| `python` / `py` | assistantService Playwright | 不自动上传，返回 `syncBody` + `syncUrl` 供 Python `requests.post` |

**assistantService 标准注入方式：**

```python
from pathlib import Path

SCRIPT_DIR = Path(r"C:\Users\yao\Desktop\work\webAuto\mcp-server\script")

def run_script(page, script_name: str, config: dict = None):
    """注入 webAuto 脚本并返回结果"""
    code = (SCRIPT_DIR / script_name).read_text(encoding="utf-8")
    # 设置运行模式和可选配置
    if config:
        for key, val in config.items():
            page.evaluate(f"window.{key} = {json.dumps(val)};")
    page.evaluate("window.__RUN_MODE_PLACEHOLDER = 'python';")  # 每个脚本有自己的 MODE key
    return page.evaluate(code)
```

---

## 脚本索引

| 脚本文件 | 目标页面 | 功能 | 文档 |
|---|---|---|---|
| `pdd-erp-order-all-table.js` | ERP 全部订单 | 全量抓取订单列表（含虚拟滚动） | [→](pdd-erp-订单脚本集.md#1-pdd-erp-order-all-tablejs--全部订单列表) |
| `pdd-erp-order-audit-goods.js` | ERP 待审核 | 审核订单+商品规格抓取，可联动勾选提交 | [→](pdd-erp-订单脚本集.md#2-pdd-erp-order-audit-goodsjs--审核订单商品规格) |
| `pdd-erp-order-presell-list.js` | ERP 预售订单 | 预售订单列表抓取 | [→](pdd-erp-订单脚本集.md#3-pdd-erp-order-presell-listjs--预售订单) |
| `pdd-erp-order-delivered-query.js` | ERP 已发货 | 按筛选条件（今天/已打印）查询已发货订单 | [→](pdd-erp-订单脚本集.md#4-pdd-erp-order-delivered-queryjs--已发货查询) |
| `pdd-erp-order-delivering-print-ship.js` | ERP 待发货 | 全选→打印快递单→打印并发货（操作脚本） | [→](pdd-erp-订单脚本集.md#5-pdd-erp-order-delivering-print-shipjs--待发货打印发货) |
| `pdd-after-sale-return-logistics.js` | ERP 售后管理 | 批量 hover 采集退货物流信息 | [→](pdd-售后物流脚本.md) |
| `get_pdd_orders.js` | 拼多多管理后台 | 订单列表采集并同步飞书 | [→](pdd-erp-订单脚本集.md#6-get_pdd_ordersjs--拼多多管理后台订单) |
| `pdd-order-search-receiver.js` | ERP 订单搜索 | 按收件人姓名搜索订单 | （待补充） |
| `xhs-publish.js` | 小红书创作平台 | 图文笔记发布（含图片上传） | （assistantService 不使用） |
| *(内嵌于 TaobaoAssistant.jsx)* | 淘宝商品详情页 | 采集标题/图片/SKU规格/商品参数/价格 | [→](taobao-商品信息采集.md) |
| `POST /api/taobao/save-product` | assistantService Flask | 下载图片 + 写单品Excel + 更新汇总（`taobao_routes.py`） | [→](taobao-商品信息采集.md#本地保存接口assistantservice) |

---

## 新增脚本登记规范

当 webAuto 生成新脚本并需在 assistantService 中使用时，按以下模板在本目录新建 `.md` 文件并更新上方索引表：

```markdown
## 脚本名称

**脚本文件**：`xxx.js`  
**目标页面**：URL  
**功能**：简要说明  

### Python 注入示例

```python
# 代码示例
```

### 返回值结构

```json
// 结构说明
```

### 可选配置参数

| window 变量 | 默认值 | 说明 |
|---|---|---|
```
