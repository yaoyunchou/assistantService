# 拼多多 ERP：服务端远程调用如意助手 API

本文面向 **业务后端 / Nest 网关 / 其它服务**：如何通过 HTTP（或经 Nest 代理）调用如意助手上的拼多多 ERP 能力；并说明 **CMS Nest** 侧固定标识 **`assistantKey`** 与 **`socket.id`** 的关系、握手与 JWT 用法。助手为本仓库 Flask 应用，蓝图前缀 **`/api/pinduoduo`**。

通用约定：

| 项目 | 说明 |
|------|------|
| **助手根地址** | `http://{HOST}:{PORT}`，开发默认 `8886`，生产常见 `8887`；也可用环境变量 **`ASSISTANT_HTTP_BASE`** |
| **浏览器池** | 下列「自动化」接口依赖 Playwright，需助手已初始化浏览器池；超时多为 **620s（列表类）** / **180s（打印发货）** |
| **登录** | 若跳转拼多多登录页，响应可能含 **`intercepted`**、二维码等，与 Web 端一致 |
| **Socket 转发** | 远端助手节点经 Socket.IO **`assistant_http`** 调本机 HTTP 时，见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) |

---

## 1. 接口总览

| # | 业务 | 方法 | 路径 | 后端超时 | 说明 |
|---|------|------|------|----------|------|
| 1 | 待审批列表 | `POST` | `/api/pinduoduo/erp-audit/pending` | 620s | 打开待审核页并抓取表格 |
| 2 | **提交审核**（选中订单） | `POST` | `/api/pinduoduo/erp-audit/submit` | 620s | 勾选并提交审核；成功后可写 SQLite + 飞书 |
| 3 | **今日已审核**（本地库） | `GET` | `/api/pinduoduo/erp-audit/today` | — | 读助手本地 SQLite，**非** ERP 网页 |
| 4 | 今日已打印快递单（已发货页） | `POST` | `/api/pinduoduo/erp-delivered/today-printed-query` | 620s | 筛选今日 + 已打印并抓表 |
| 5 | **待发货 · 实时列表**（不入库） | `POST` | `/api/pinduoduo/erp-delivering/pending-list` | 200s | 仅打开待发货页抓当前表 |
| 6 | **待发货 · 打印并发货** | `POST` | `/api/pinduoduo/erp-delivering/print-ship` | 180s | 待发货页一键流程 |

可选扩展：`POST /api/pinduoduo/erp-audit/sync-feishu`（本地审核记录同步飞书），详见路由与 Swagger。

---

## 2. Nest CMS 网关与 `assistantKey`

本节原独立文档《Nest 网关：assistantKey 固定标识与助手对接说明》，现合并于此。所述 **Nest** 指 **CMS Nest 后端（`backends/nest`）** 中为「多台如意助手」提供的统一入口。

### 2.1 背景

| 概念 | 说明 |
|------|------|
| **`socket.id`** | Socket.IO **服务端在本次连接建立时自动生成**的连接 id，**断开重连后通常会变**。 |
| **`assistantKey`** | 由业务约定的 **字符串常量**（如门店编码、终端编号、`erp-01`），在同一时刻映射到 **一条在线连接**，HTTP 调用可用该字符串选中助手，无需记录 `socket.id`。 |

两者至少满足其一即可调用下文中的 REST 映射接口；若同时传入，**优先使用 `assistantKey`**。

### 2.2 助手侧：如何绑定 `assistantKey`

Nest 在同一进程内维护映射：**`assistantKey → 当前 socket.id`**。绑定方式有两种（二选一或组合）。

**如意助手（本仓库）已支持自动握手 Query**：在环境变量或 `app_config.toml` 中配置 `WS_CLIENT_ASSISTANT_KEY` / 管理页「assistantKey」后，仅填写 **服务端 host、端口、path** 即可，连接时自动在根 URL 上附加 `?assistantKey=...`（实现见 `src/utils/websocket_client.py` 的 `append_assistant_key_query`）。

#### 2.2.1 方式 A：握手时在 URL Query 中带参（推荐）

连接 Nest 的根地址时附带 query（两种键名等价，任选其一）：

| Query 键名 | 示例值 |
|------------|--------|
| `assistantKey` | `erp-east-01` |
| `assistant_key` | `erp-east-01` |

**socket.io-client（JavaScript）示例：**

```javascript
import { io } from 'socket.io-client';

const SERVER = process.env.NEST_WS_URL ?? 'http://127.0.0.1:8080'; // 与 Nest 的 APP_PORT 一致

const socket = io(SERVER, {
  path: '/socket.io/',
  transports: ['websocket', 'polling'],
  query: {
    assistantKey: 'erp-east-01',
  },
});

socket.on('connect', () => {
  console.log('已连接 Nest，socket.id=', socket.id, 'assistantKey=erp-east-01');
});
```

**Python（`python-socketio` Client）**：在 **`connect` 的根 URL 上附带 query**（与服务端 handshake 读取的 query 一致即可）：

```python
import socketio

sio = socketio.Client(engineio_logger=False, logger=False)

@sio.event
def connect():
    print('connected sid=', sio.sid)

# 示例：握手 URL 中带 assistantKey（端口与 Nest APP_PORT 一致）
sio.connect(
    'http://127.0.0.1:8080/?assistantKey=erp-east-01',
    transports=['websocket', 'polling'],
    socketio_path='/socket.io/',
)

sio.wait()
```

> 若所使用的 Socket.IO 客户端版本不支持在 URL 中加 query，请改用 **§2.2.2 方式 B（`register_assistant`）**。

#### 2.2.2 方式 B：连上后再注册（URL 不便改 query 时）

连接成功后，向服务端发送事件 **`register_assistant`**，Body 为 JSON 对象：

```json
{ "assistantKey": "erp-east-01" }
```

**JavaScript：**

```javascript
socket.emit('register_assistant', { assistantKey: 'erp-east-01' }, (ack) => {
  console.log(ack); // { ok: true, assistantKey: "erp-east-01" } 或 { ok: false, error: "..." }
});
```

若服务端使用 Socket.IO 的 acknowledge 回调，则以实际 Nest 网关实现为准；当前实现会同步返回 `{ ok, assistantKey?, error? }` 形态的应答对象（具体以运行时为准）。

### 2.3 服务端行为摘要（便于助手团队预期）

1. **连接建立**：若握手带 `assistantKey` / `assistant_key`，该连接会登记到 **`assistantKey → socket.id`**。
2. **`register_assistant`**：在同一连接上更新绑定；若 **`assistantKey` 已被另一条连接占用**，新连接会「抢占」该 key（旧连接仍存在，但 HTTP 不能再通过该 key 命中，除非旧连接重新 `register_assistant`）。
3. **断开**：该 `socket.id` 释放；若当前 key 指向这条连接，则 **`assistantKey` 映射一并删除**，直到同一 key 再次被绑定。

助手日志建议打印：**自身选用的 `assistantKey`**、以及 **`socket.id`**（便于现场排查）。

### 2.4 HTTP 调用方（业务系统 / 前端）

前提：已通过 **JWT 登录**（与其它受保护接口相同），请求头：`Authorization: Bearer <token>`。

全局前缀：**`/api/v1`**。

以下拼多多 ERP 代理接口需 **至少** 提供 **`assistantKey` 或 `socketId` 其一**（Query）。助手蓝图前缀为 **`/api/pinduoduo`**，经 Nest 时挂在 **`/api/v1`** 下相对路径 **`/assistant/pinduoduo/...`**：

| # | 业务 | 助手路径 | Nest 路径（相对 `/api/v1`） |
|---|------|----------|---------------------------|
| ① | 待审批 | `POST /api/pinduoduo/erp-audit/pending` | `POST /assistant/pinduoduo/erp-audit/pending` |
| ② | 今日已打印快递单（已发货页） | `POST /api/pinduoduo/erp-delivered/today-printed-query` | `POST /assistant/pinduoduo/erp-delivered/today-printed-query` |
| ③ | 提交审核（勾选订单） | `POST /api/pinduoduo/erp-audit/submit` | `POST /assistant/pinduoduo/erp-audit/submit` |
| ④ | 今日已审核（本地 SQLite） | `GET /api/pinduoduo/erp-audit/today` | `GET /assistant/pinduoduo/erp-audit/today` |
| ⑤ | 待发货 · 实时列表（不入库） | `POST /api/pinduoduo/erp-delivering/pending-list` | `POST /assistant/pinduoduo/erp-delivering/pending-list` |
| ⑥ | 待发货 · 打印并发货 | `POST /api/pinduoduo/erp-delivering/print-ship` | `POST /assistant/pinduoduo/erp-delivering/print-ship` |

**示例（固定标识）：**

```http
POST /api/v1/assistant/pinduoduo/erp-audit/pending?assistantKey=erp-east-01
Authorization: Bearer <jwt>
Content-Type: application/json

{"scroll_max_steps": 80, "scroll_pause_ms": 400}
```

返回体最外层仍受 Nest **统一包装**（如 `code`、`message`、`data`）；助手协议层内容在 **`data`** 字段内（含 `ok`、`status`、`data` 业务 JSON、`error` 等），详见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) 与本文件 **§3**。

### 2.5 多台助手并存时的约定

- 每台助手使用 **互不相同的 `assistantKey`**（由运维/产品在部署时分配）。
- 同一 key **不允许** 同时在两台机器上冒充在线（后连接者会抢占映射）；部署时需避免重复 key。

### 2.6 安全提示

- `assistantKey` 若可被任意客户端注册，存在 **抢占** 风险；生产环境应对 Nest 访问做 **网络隔离 / 鉴权**，并可后续增加 **服务端白名单**（环境变量配置允许的 key 列表）— 当前是否启用以代码为准。
- Socket 与 REST 均应使用 **HTTPS/WSS**（生产环境由网关/Nginx 终止 TLS）。

### 2.7 Nest 仓库相关代码（参考）

- 工具类：`src/shared/assistant-http/`（`AssistantHttpClient`、`PinduoduoErpAssistantHttp`）。
- Socket 网关与注册：`src/modules/assistant/`。

（以上路径相对于 **Nest** 仓库，非本助手仓库。）

---

## 3. 请求 / 响应摘要

### 3.1 `POST .../erp-audit/pending`

**Body（可选 JSON）**：`scroll_max_steps`、`scroll_pause_ms`

**响应要点**：`success`、`rows`、`message`、`intercepted?`、`page_url`

---

### 3.2 `POST .../erp-audit/submit` —— **选中商品提交审核**

**Body（JSON）**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `order_nos` | string[] | **是** | 平台订单号列表（与 pending 返回的 `orderNo` 一致）；兼容别名 `orderNos` |
| `scroll_max_steps` | int | 否 | 列表滚动 |
| `scroll_pause_ms` | int | 否 | 每步等待 ms |

**示例**：

```http
POST /api/pinduoduo/erp-audit/submit
Content-Type: application/json

{
  "order_nos": ["260419-1234567890123", "260419-9876543210987"],
  "scroll_max_steps": 80,
  "scroll_pause_ms": 400
}
```

**响应要点**：`success`、`message`、`rows`、`audit_result`、`check_result`；审核成功且配置飞书表时可能含 **`feishu_sync`**、`sqlite_inserted`。

---

### 3.3 `GET .../erp-audit/today` —— **今日已审核（本地）**

无 Body。Query **`unprinted=1`**（或 `true`）时仅返回尚未经本机「打印并发货」回写 `printed_at` 的记录；缺省为今日全部。

**响应**：`success`、`rows`、`count`、**`filter_unprinted`**（是否启用上述筛选）。

---

### 3.4 `POST .../erp-delivered/today-printed-query`

见 [`socketio-assistant-http.md`](./socketio-assistant-http.md) §8 与脚本注释；Body 可选 `filter_print_status`、`time_type`、`date_shortcut` 等。

---

### 3.5 `POST .../erp-delivering/pending-list` —— **待发货 · 实时列表（不入库）**

Body 可无（`{}`）。打开待发货页并抓取当前表格行 **`orderNo` + `goods`**，**不写 SQLite**；虚拟滚动下列表可能仅为当前视区可见行。

**响应要点**：`success`、`empty`、`rows`、`message`、`script_result`、`page_url`。

---

### 3.6 `POST .../erp-delivering/print-ship` —— **待发货 · 打印并发货**

无必填 Body（可传 `{}`）。

**响应要点**：`success`、`message`、`script_result`、`empty`、`print_ship_success` 等。

---

## 4. 使用 `assistant_http` 调用（Socket）

下列 JSON 发往已连接的助手客户端（事件 `assistant_http`），**`timeout` 勿用默认 60s**。

### 4.1 提交审核

```json
{
  "messageId": "audit-submit-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-audit/submit",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {
    "order_nos": ["260419-1234567890123"]
  }
}
```

### 4.2 今日已审核（GET）

```json
{
  "messageId": "audit-today-001",
  "method": "GET",
  "url": "/api/pinduoduo/erp-audit/today",
  "timeout": 30
}
```

### 4.3 打印并发货

```json
{
  "messageId": "deliver-print-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-delivering/print-ship",
  "timeout": 200,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

回包在 **`assistant_http_response`**，业务 JSON 在 **`payload.data`**（与直连 HTTP 响应体一致）。

---

## 5. 实现位置（本仓库）

- 路由：`src/api/routes/pinduoduo_routes.py`
- 审核逻辑：`src/spider/pinduoduo/erp_audit.py`

---

## 6. 相关文档

- [`socketio-assistant-http.md`](./socketio-assistant-http.md)：事件 `assistant_http` / `assistant_http_response` 载荷约定。
