# Socket.IO 远程调用如意助手本地 HTTP（assistant_http）

如意助手作为 **Socket.IO 客户端**连接到你的业务网关时，除了接收 `forward`、`action` 外，还支持 **`assistant_http`**：由服务端下发「类 axios」的 HTTP 描述，助手在本机拼出完整 URL 并发起请求，再通过 **`assistant_http_response`** 把结果（含同一个 `messageId`）发回服务端，便于对接方用关联 ID 做请求-响应匹配。

---

## 一、事件名与方向

| 事件名 | 方向 | 说明 |
|--------|------|------|
| `assistant_http` | 服务端 → 助手客户端 | 下发一次 HTTP 调用描述 |
| `assistant_http_response` | 助手客户端 → 服务端 | 回传执行结果，**务必用 `messageId` 对应请求** |
| `forward`（可选） | 服务端 → 助手客户端 | 若 payload 含 `type: "assistant_http"`，与 `assistant_http` 等价 |

若你的网关只支持向所有客户端广播 **`forward`**，可使用第三节的「forward 包裹」格式，无需单独 emit `assistant_http`。

---

## 二、请求体（服务端发出）

与 axios 用法对齐的字段（JSON 对象）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messageId` | string | 建议 | 关联 ID；回包中原样返回，便于对接方 `Map`/`Promise` 配对 |
| `method` | string | 否 | 默认 `GET` |
| `url` | string | **是** | 完整 `http(s)://...` **或** 相对路径如 `/api/health`。相对路径会拼到助手本机 HTTP 根（见第五节） |
| `params` | object | 否 | 查询参数，等价 axios `params` |
| `headers` | object | 否 | 请求头 |
| `json` | any | 否 | 若存在，按 JSON body 发送（`requests` 的 `json=`） |
| `data` | any | 否 | 与 `json` 二选一优先使用 `json`。`data` 为 object/array 时按 JSON body；为字符串时原样 body |
| `timeout` | number | 否 | 秒，默认 `60` |

**示例（调用助手本机 API，无 host）：**

```json
{
  "messageId": "req-550e8400-e29b-41d4-a716-446655440000",
  "method": "POST",
  "url": "/api/pinduoduo/execute",
  "headers": {
    "Content-Type": "application/json"
  },
  "json": {
    "script": "example",
    "args": {}
  }
}
```

**示例（访问外网绝对地址）：**

```json
{
  "messageId": "req-2",
  "method": "GET",
  "url": "https://httpbin.org/get",
  "params": { "foo": "bar" }
}
```

---

## 三、forward 包裹（仅广播 forward 时）

若只能发到 `forward`，使用：

```json
{
  "type": "assistant_http",
  "messageId": "req-3",
  "method": "GET",
  "url": "/api/health"
}
```

除 `type` 外字段与第二节一致；助手会去掉 `type` 再执行。

---

## 四、响应体（助手回发给服务端）

助手向服务端 **`emit('assistant_http_response', payload)`**，结构如下：

| 字段 | 类型 | 说明 |
|------|------|------|
| `messageId` | string / null | 与请求一致（若请求未传则可能为 `null`） |
| `ok` | boolean | 是否视为成功：`true` 当且仅当 HTTP 状态码在 200–299 |
| `status` | number / null | HTTP 状态码；连接异常时多为 `null` |
| `headers` | object / null | 仅保留 `content-type`、`content-length` 等摘要 |
| `data` | any | 响应体：`Content-Type` 含 `application/json` 时尝试解析为对象，否则为文本（超长会截断） |
| `error` | string / null | 失败时的错误说明；成功时为 `null`，非 2xx 时可为 `HTTP 404` 等简短说明 |

**成功示例：**

```json
{
  "messageId": "req-550e8400-e29b-41d4-a716-446655440000",
  "ok": true,
  "status": 200,
  "headers": {
    "Content-Type": "application/json"
  },
  "data": { "success": true },
  "error": null
}
```

**异常示例（网络错误）：**

```json
{
  "messageId": "req-550e8400-e29b-41d4-a716-446655440000",
  "ok": false,
  "status": null,
  "data": null,
  "error": "Connection refused ..."
}
```

---

## 五、本机 URL 如何拼接（对接运维）

- 默认：`http://{HOST}:{PORT}`，其中 `HOST`、`PORT` 为如意助手当前 Flask 配置（如 `127.0.0.1:8887`）。
- 若 `Config.HOST` 为 `0.0.0.0`，助手内部会改用 **`127.0.0.1`** 访问本机服务。
- 可通过环境变量 **`ASSISTANT_HTTP_BASE`** 覆盖完整起点（无尾部斜杠），例如：`http://127.0.0.1:8887`。

---

## 六、对接方示例（Node / NestJS @WebSocketGateway）

服务端向**已连接的某一 socket**（或广播到房间）发送：

```typescript
// 发给指定客户端 socket
client.emit('assistant_http', {
  messageId: crypto.randomUUID(),
  method: 'GET',
  url: '/api/health',
});

// 监听助手回包（同一 Gateway 内）
@SubscribeMessage('assistant_http_response')
handleAssistantHttpResponse(@MessageBody() body: any) {
  // 按 body.messageId 匹配挂起的 Promise / Map
  this.pending.get(body.messageId)?.resolve(body);
}
```

注意：具体 API 以你使用的 Socket.IO 服务端封装为准（有的项目用 `server.to(socketId).emit('assistant_http', ...)`）。

**浏览器 / socket.io-client（调试）：**

```javascript
socket.emit('assistant_http', {
  messageId: 'm1',
  method: 'GET',
  url: '/api/health',
});

socket.on('assistant_http_response', (payload) => {
  console.log('matched', payload.messageId, payload);
});
```

---

## 七、安全说明

该能力等价于允许远端用户让助手发起 **任意本机可达 HTTP**（含内网），请务必在网关侧做：

- 鉴权（仅可信助手连接）
- 可选：白名单路径、仅允许 `127.0.0.1` 上的部分前缀

---

## 八、业务示例：拼多多 ERP（待审批 · 提交审核 · 今日记录 · 已发货查询 · 打印发货）

以下接口均在蓝图前缀 **`/api/pinduoduo`** 下（完整路径见表）。通过 **`assistant_http`** 调用时，`url` 写相对路径即可拼到本机助手（第五节）。

**服务端对接总表（含 Nest 代理路径、`timeout`、请求体摘要）**：见 **[`pinduoduo-erp-remote-api.md`](./pinduoduo-erp-remote-api.md)**。

### 8.0 核心业务接口（专项对接）

以下接口中，**①②③⑤** 走 **浏览器池 + Playwright**，耗时长；**④** `GET .../erp-audit/today` **仅读本地 SQLite**，与其它轻量接口一致，可用较短 **`timeout`**。对接时请按本小节配置 **`timeout`** 并解析 **`assistant_http_response.data`**。

#### 端口与环境（与 `dev.py` / 生产一致）

| 运行方式 | 默认监听端口（`Config.PORT`） | 说明 |
|----------|------------------------------|------|
| 开发：`src/dev.py`（`APP_ENV=development`） | **8886**（`DEV_PORT`） | 热重载；相对路径拼本机时请用助手实际日志里打印的地址 |
| 生产 / 主程序入口 | **8887**（`PORT`） | 与 `README` 常见说明一致 |

`assistant_http` 使用相对路径 `url` 时，助手会拼 **`http://{绑定主机}:{当前 PORT}`**（第五节、`ASSISTANT_HTTP_BASE`）。远端服务调用前请确认网络能访问该端口，或在助手环境配置 **`ASSISTANT_HTTP_BASE`** 为可达的完整 origin。

#### 对照速查

| # | **HTTP** | **助手行为（摘要）** | **`timeout` 建议** |
|---|----------|----------------------|---------------------|
| ① 待审批 | `POST .../erp-audit/pending` | 打开「待审核」页，拉取待审核 `rows` | **≥ 650**（池约 620s） |
| ② 今日已打印 | `POST .../erp-delivered/today-printed-query` | 「已发货」页：今日 + 已打印快递单，`rows`；结束可发飞书卡片 | **≥ 650** |
| **③ 提交审核** | `POST .../erp-audit/submit` | 在待审核列表中勾选给定 `order_nos` 并提交审核；可写 SQLite / 飞书 | **≥ 650** |
| **④ 今日已审核（本地）** | `GET .../erp-audit/today` | 读助手本地库今日审核记录（**非** ERP 网页） | **30** 左右即可 |
| **⑤ 打印并发货** | `POST .../erp-delivering/print-ship` | 待发货页执行「打印并发货」流程 | **200**（后端约 180s） |

**执行后 Webhook**：② 成功/告警可推拼多多渠道飞书卡片；①③⑤ 按各自脚本逻辑。**登录拦截**时与其它 ERP 页一致（二维码等）。

#### ① `POST .../erp-audit/pending` — 请求与响应

**HTTP 请求 Body（可选，JSON）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `scroll_max_steps` | int | 列表虚拟滚动最大步数，传给页内脚本 |
| `scroll_pause_ms` | int | 每步等待毫秒 |

**HTTP 响应体（即 `assistant_http_response.data`；200 时）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否抓取成功（未登录拦截且脚本跑通） |
| `intercepted` | boolean | 为 `true` 时表示登录拦截，响应内可能含二维码等（与 Web 端一致） |
| `message` | string | 概要说明 |
| `rows` | array | 待审核订单行（含订单号、商品信息、店铺等，以实际脚本为准） |
| `extract` | object | 如 `count`、`log` 等脚本附属信息 |
| `page_url` | string | 结束时页面 URL |

#### ② `POST .../erp-delivered/today-printed-query` — 请求与响应

**HTTP 请求 Body（可选，JSON）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `filter_print_status` | string | 默认「已打印快递单」；传 `__ALL__`/`all`/`*` 表示不筛选；空串与缺省相同 |
| `time_type` | string | 如 `发货时间`（与脚本默认一致时可不传） |
| `date_shortcut` | string | 如 `今天`（与脚本默认一致时可不传） |
| `auto_scroll` | boolean | 是否自动滚动加载全部 |
| `scroll_max_steps` | int | 最大滚动步数 |
| `scroll_pause_ms` | int | 每步等待毫秒 |

**HTTP 响应体（即 `assistant_http_response.data`；200 时）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否筛选并抓取成功 |
| `intercepted` | boolean | 登录拦截时含义同 ① |
| `message` | string | 概要说明（如条数说明） |
| `rows` | array | 已发货订单行：`orderNo`、`goods`、`express`、`shippingTime`、`printStatus`、`shopName`、`actualAmount` 等 |
| `extract` | object | 如 `count`、`log` |
| `page_url` | string | 结束时页面 URL |

#### ③ `POST .../erp-audit/submit` — 勾选订单提交审核

**HTTP 请求 Body（JSON）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `order_nos` | string[] | 平台订单号列表（与 ① 返回的 `orderNo` 一致）；或写 **`orderNos`** |
| `scroll_max_steps` | int | 可选，列表滚动 |
| `scroll_pause_ms` | int | 可选 |

**HTTP 响应体要点**：`success`、`message`、`rows`、`audit_result`、`check_result`；成功且配置飞书表时可能含 **`feishu_sync`**、`sqlite_inserted`。

#### ④ `GET .../erp-audit/today` — 今日已审核（本地 SQLite）

无 Body。**响应**：`success`、`rows`、`count`（今日写入本地的审核相关记录）。

#### ⑤ `POST .../erp-delivering/print-ship` — 待发货 · 打印并发货

Body 可无或 `{}`。**响应要点**：`success`、`message`、`script_result`、`empty`、`print_ship_success` 等。

#### Socket 最小示例（`assistant_http`）

**① 待审批**

```json
{
  "messageId": "erp-pending-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-audit/pending",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {
    "scroll_max_steps": 80,
    "scroll_pause_ms": 400
  }
}
```

**② 今日已打印快递单**

```json
{
  "messageId": "erp-delivered-print-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-delivered/today-printed-query",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

**③ 提交审核（勾选订单号）**

```json
{
  "messageId": "erp-audit-submit-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-audit/submit",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {
    "order_nos": ["260419-1234567890123", "260419-9876543210987"]
  }
}
```

**④ 今日已审核（本地库）**

```json
{
  "messageId": "erp-audit-today-001",
  "method": "GET",
  "url": "/api/pinduoduo/erp-audit/today",
  "timeout": 30
}
```

**⑤ 打印并发货**

```json
{
  "messageId": "erp-print-ship-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-delivering/print-ship",
  "timeout": 200,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

**服务端取数**：监听 `assistant_http_response`，按 `messageId` 匹配后，**业务数据**在 **`payload.data`**（即上表 HTTP 响应体）；同时看 **`payload.ok`** 与 **`payload.status`** 判断 HTTP 层是否 2xx。

---

### 8.1 接口一览

| 业务 | 方法 | 路径 | 助手后端说明 |
|------|------|------|----------------|
| **订单待审批列表** | `POST` | `/api/pinduoduo/erp-audit/pending` | 打开 ERP 待审核页并抓取列表（浏览器自动化，**耗时长**） |
| **勾选订单提交审核** | `POST` | `/api/pinduoduo/erp-audit/submit` | Body：`order_nos` / `orderNos`，在页面上勾选并提交审核（同 **耗时长**） |
| **今日已打印快递单（ERP 页查询）** | `POST` | `/api/pinduoduo/erp-delivered/today-printed-query` | 已发货页筛选「今日 + 已打印快递单」并表格抓取；执行结束后向拼多多渠道 **飞书 Webhook** 推送摘要 |
| **今日已审核（本地 SQLite）** | `GET` | `/api/pinduoduo/erp-audit/today` | 读取**今日已写入本地 SQLite**的审核记录（轻量，**不是** ERP 页「今日打印单」） |
| **待发货 · 打印并发货** | `POST` | `/api/pinduoduo/erp-delivering/print-ship` | 待发货页执行「打印并发货」流程（**动作执行**，约 180s） |

说明：**「今日打印单」以 ERP 已发货页为准时**，请用 **`POST .../erp-delivered/today-printed-query`**；若只需读助手本地库里的今日审核记录，用 **`GET .../erp-audit/today`**。

### 8.2 `timeout`（重要）

`assistant_http` 默认 **`timeout` 为 60 秒**。  
`erp-audit/pending`、`erp-audit/submit`、`erp-delivered/today-printed-query` 在服务端内部最长可执行约 **620 秒**（浏览器池脚本）。若不下发更大 `timeout`，HTTP 客户端会先超时断开，拿不到完整 JSON。

建议：

- **`erp-audit/pending`** / **`erp-audit/submit`** / **`erp-delivered/today-printed-query`**：`"timeout": 650`（或 `700`，略大于后端执行上限）。
- **`erp-audit/today`**：`"timeout": 30` 即可。
- **`erp-delivering/print-ship`**：可按 `"timeout": 200`（后端约 180s）。

### 8.3 ① 获取订单待审批列表

字段与 Socket 示例以 **§8.0「① 待审批」** 为准；以下为同内容展开（含 `forward` 写法）。

- **HTTP**：`POST /api/pinduoduo/erp-audit/pending`
- **Body（可选）**：`scroll_max_steps`、`scroll_pause_ms`（整数，控制列表滚动加载）
- **成功时 JSON 要点**：`success`、`rows`（待审核行）、`message`、`page_url`；若未登录可能返回二维码相关拦截字段（与页面端一致）。

**Socket 侧示例（发给助手客户端）：**

```json
{
  "messageId": "erp-pending-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-audit/pending",
  "timeout": 650,
  "headers": {
    "Content-Type": "application/json"
  },
  "json": {
    "scroll_max_steps": 80,
    "scroll_pause_ms": 400
  }
}
```

**`forward` 广播等价写法：**

```json
{
  "type": "assistant_http",
  "messageId": "erp-pending-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-audit/pending",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

服务端监听 **`assistant_http_response`**，`messageId === 'erp-pending-001'` 时读取 `data` 即为助手返回的 JSON（与浏览器直接调该 API 一致）。

### 8.3a 勾选订单提交审核（`erp-audit/submit`）

- **HTTP**：`POST /api/pinduoduo/erp-audit/submit`
- **Body（JSON）**：`order_nos`（或 `orderNos`）为字符串数组；可选 `scroll_max_steps`、`scroll_pause_ms`
- **Socket / `timeout`**：与 **§8.0「③」**、`§8.2` 一致，建议 **650**
- **成功时 JSON 要点**：`success`、`message`、`rows`、`audit_result` 等（与 §8.0「③」一致）

**Socket 侧示例：** 见 **§8.0「③ 提交审核」** JSON 块。

### 8.4 ② 今日已打印快递单（ERP 已发货页）

字段与 Socket 示例以 **§8.0「② 今日已打印」** 为准。

- **HTTP**：`POST /api/pinduoduo/erp-delivered/today-printed-query`
- **Body（可选）**：`filter_print_status`（默认「已打印快递单」；`__ALL__`/`all`/`*` 表示不筛选）、`time_type`、`date_shortcut`、`auto_scroll`、`scroll_max_steps`、`scroll_pause_ms`
- **成功时 JSON 要点**：`success`、`rows`（平台订单号、商品、快递、发货时间、打印状态等）、`message`、`page_url`
- **侧链**：完成后会往 **拼多多渠道**飞书机器人发一条卡片（成功绿 / 失败橙）；若进门即登录拦截，仍走与其它 ERP 页相同的二维码逻辑。

**Socket 侧示例：**

```json
{
  "messageId": "erp-delivered-print-001",
  "method": "POST",
  "url": "/api/pinduoduo/erp-delivered/today-printed-query",
  "timeout": 650,
  "headers": { "Content-Type": "application/json" },
  "json": {}
}
```

### 8.5 ④ 今日订单（本地 SQLite，轻量）

- **HTTP**：`GET /api/pinduoduo/erp-audit/today`
- **Body**：无
- **成功时 JSON 要点**：`success`、`rows`、`count`

**Socket 侧示例：**

```json
{
  "messageId": "erp-today-001",
  "method": "GET",
  "url": "/api/pinduoduo/erp-audit/today",
  "timeout": 30
}
```

### 8.6 ⑤ 待发货「打印并发货」（动作执行）

若业务需要在待发货页**执行打印并发货**（而非仅查询列表），见 **§8.0「⑤」** 的 Socket 示例；**`timeout`** 建议 **200**。

### 8.7 实现代码位置（便于核对字段）

- 路由：`src/api/routes/pinduoduo_routes.py`（含 `erp-audit/pending`、`erp-audit/submit`、`erp-audit/today`、`erp-delivered/today-printed-query`、`erp-delivering/print-ship`）
- 抓取逻辑：`src/spider/pinduoduo/erp_audit.py`；脚本：`src/spider/pinduoduo/scripts/pdd-erp-order-delivered-query.js`

---

## 九、相关代码位置（通用）

- 执行逻辑：`src/utils/assistant_http_invoke.py`
- Socket 注册与线程执行：`src/utils/websocket_client.py`
- 配置：`ASSISTANT_HTTP_BASE`（`src/config.py`）

更多 Socket.IO 连接说明见 `docs/websocket-api.md`。

---

## 十、Nest 网关与 `assistantKey`（多台助手）

业务侧通过 **CMS Nest** 使用固定 **`assistantKey`**（如门店/终端编码）选中某台如意助手转发 HTTP，无需记录易变的 **`socket.id`**；握手 Query、`register_assistant`、Nest 侧 **`/api/v1/assistant/pinduoduo/...`** 与 JWT 说明见 **[`pinduoduo-erp-remote-api.md`](./pinduoduo-erp-remote-api.md)** §2。
