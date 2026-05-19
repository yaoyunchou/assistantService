# 预售订单 · WebSocket 调用说明

本文只讲一件事：**业务服务器通过 Socket.IO 下发指令，让已连接的如意助手在本机执行「预售订单采集」HTTP，并把订单列表回传。**

通用协议（事件字段、回包结构、Nest / `assistantKey`、安全等）见 [`socketio-assistant-http.md`](./socketio-assistant-http.md)。

---

## 1. 调用链（预售）

1. 助手作为 **Socket.IO 客户端**连到你的网关。  
2. 服务器向该连接发送 **`assistant_http`**，其中 `url` 指向 **`POST /api/pinduoduo/erp-presell/collect`**（相对路径即可，拼到助手本机 HTTP，见 §5）。  
3. 助手打开拼多多 ERP **预售订单**页，执行列表脚本，**不入库**；结果放在 HTTP 响应 JSON 的 **`orders`** 里。  
4. 助手再通过 **`assistant_http_response`** 把整段 HTTP 响应放到 **`payload.data`**，并用 **`messageId`** 与请求对应。

若网关只支持广播 **`forward`**：载荷里加 **`"type": "assistant_http"`**，其余字段与下表相同（助手会去掉 `type` 再执行）。

---

## 2. 本机 HTTP 接口（预售采集）

| 项 | 值 |
|----|-----|
| 方法 | `POST` |
| 路径 | **`/api/pinduoduo/erp-presell/collect`** |
| 作用 | 采集 ERP 预售列表；**仅返回 JSON，由你们服务器落库或转发** |
| ERP 页面 | `https://mms.pinduoduo.com/erp/order/presell`（助手内配置可覆盖） |

### 2.1 请求 Body（JSON，均可选）

| 字段 | 类型 | 默认 / 说明 |
|------|------|-------------|
| `auto_scroll` | boolean | `false`。`true` 时滚动合并多屏，按 `orderNo` 去重（长列表、虚拟表） |
| `scroll_step` | int | 每次滚动像素，不传则用脚本默认 **420** |
| `scroll_pause_ms` | int | 每次滚动后等待毫秒，不传则默认 **550** |

### 2.2 超时（Socket 侧必配）

浏览器池执行该任务最长约 **600 秒**。`assistant_http` 默认 **60 秒**会先断。

| 建议 |
|------|
| **`"timeout": 650`**（秒，略大于后端上限） |

---

## 3. 业务响应（看 `assistant_http_response.data`）

HTTP 常为 200，仍要区分 **`data.success`** 与是否登录拦截。

### 3.1 采集成功

| 字段 | 说明 |
|------|------|
| `success` | `true` |
| `intercepted` | `false` |
| **`orders`** | **预售订单数组（主数据）** |
| `order_count` | 等于 `orders.length` |
| `extract_log` | 脚本日志，便于排查 |
| `page_url` | 采集结束时页面 URL |

### 3.2 需登录 / 登录拦截

| 字段 | 说明 |
|------|------|
| `intercepted` | 常为 `true` |
| `message` | 说明文案，可能配合二维码等字段（与助手其它 ERP 页一致） |
| `orders` | 可能为空；需在助手运行环境完成拼多多扫码登录后重试 |

### 3.3 失败（未进列表、脚本异常等）

| 字段 | 说明 |
|------|------|
| `success` | `false` |
| `message` | 原因说明 |
| `page_url` | 部分场景会带 |

### 3.4 `orders[]` 单条字段说明

与页面脚本一致，详细注释见仓库：`src/spider/pinduoduo/scripts/pdd-erp-order-presell-list.js`（文件头）。

| 字段 | 说明 |
|------|------|
| `orderNo` | 平台订单号，如 `260513-181749727613319` |
| `erpOrderNo` | ERP 订单编号（如 `FH…`，来自「订单编号/操作」列首行） |
| `发货剩余支付时间` | 单元格原文（含倒计时等文案） |
| `支付时间` | 稳定格式 **`yyyy/MM/dd HH:mm`**（无年份的按当年补全） |
| `支付时间原文` | 如 `05-13 17:20 支付` |
| `发货时间` | 预售列表无真实发货时间时为 **`''`**（与其它 ERP 列表字段对齐占位） |
| `图片` | 首张商品主图 URL（已去查询串） |
| `图片列表` | 本行所有商品图 URL |
| `goods` | 数组；每项含 **`imgSrc`**（必有键）、`title`、`spec`、`qty` 等 |

---

## 4. WebSocket 载荷（预售专用示例）

### 4.1 推荐：`emit('assistant_http', …)`

```json
{
  "messageId": "presell-20260517-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-presell/collect",
  "timeout": 650,
  "headers": {
    "Content-Type": "application/json"
  },
  "json": {
    "auto_scroll": true,
    "scroll_step": 420,
    "scroll_pause_ms": 550
  }
}
```

### 4.2 等价：`forward` 广播

```json
{
  "type": "assistant_http",
  "messageId": "presell-20260517-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-presell/collect",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

### 4.3 服务器取数

1. 监听 **`assistant_http_response`**。  
2. 用 **`messageId`** 匹配本次请求。  
3. **`payload.ok` 且 `payload.status` 为 2xx**：业务 JSON 在 **`payload.data`**。  
4. 再判断 **`payload.data.success`**；为 `true` 时读取 **`payload.data.orders`** 做入库或下游同步。

`assistant_http` 请求体还支持 `params`、`data` 等，见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) 第二节。

---

## 5. 本机 URL 与端口（运维）

- 相对路径 `url` 会拼到助手本机：`http://{HOST}:{PORT}`（`0.0.0.0` 时助手内部用 `127.0.0.1`）。  
- 可用环境变量 **`ASSISTANT_HTTP_BASE`** 覆盖 origin（无尾斜杠）。  
- 开发 / 生产端口与说明见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) §八（常见 **8886** / **8887**）。

---

## 6. 安全（一句话）

仅允许可信助手连接；建议网关做鉴权，可选 **URL 白名单**（仅允许 `/api/pinduoduo/erp-presell/collect` 等）。详见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) 第七节。

---

## 7. 代码位置

| 说明 | 路径 |
|------|------|
| HTTP 路由 | `src/api/routes/pinduoduo_routes.py` → `erp-presell/collect` |
| 打开页面 + 调脚本 | `src/spider/pinduoduo/presell_sync.py` |
| 列表字段解析 | `src/spider/pinduoduo/scripts/pdd-erp-order-presell-list.js` |
| 执行 `assistant_http` | `src/utils/assistant_http_invoke.py` |
| Socket 收发包 | `src/utils/websocket_client.py` |

远端经 Nest、JWT、`assistantKey` 选终端等，见 [`pinduoduo-erp-remote-api.md`](./pinduoduo-erp-remote-api.md)。
