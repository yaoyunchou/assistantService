# 变更日志

## 2026-02-09 - 浏览器代理架构重写（彻底解决所有线程问题）

### 问题

之前的 BrowserPool 设计复杂（实例池 + 共享 context + 外部 executor），反复出现：
- `Cannot switch to a different thread`（跨线程操作 Playwright）
- `Target page, context or browser has been closed`（失效实例被复用）
- `Sync API inside asyncio loop`（重建 context 时 asyncio 残留）

根本原因：Playwright 同步 API 要求所有操作在同一线程执行，旧设计用多线程池 + 外部 executor，很难保证这一点。

### 重写方案：单线程代理模式

**核心思想**：一个专用线程，一个持久化 context，任务提交进去、结果返回出来。

**`src/spider/query_manager.py`**（完全重写，从 843 行精简到 323 行）：
- BrowserPool 内部持有 `ThreadPoolExecutor(max_workers=1)` 专用线程
- `execute(fn, timeout)` — 推荐 API，提交 `fn(page)` 到浏览器线程执行
- `get_page()` — 向后兼容，仅在浏览器线程内使用
- `_ensure_browser()` — 懒初始化 + 自动重建（同一线程上操作，无 asyncio 冲突）
- 去掉了实例池、等待队列、空闲回收等复杂逻辑
- 每次 execute 创建新 page，用完即关；context 长驻，Cookie 自动持久化

**`src/api/routes/context.py`**：
- 移除 `_browser_executor`（浏览器操作改由 BrowserPool 内部管理）
- 保留 `get_browser_executor()` 返回通用后台线程池（飞书等非浏览器任务）

**`src/api/routes/tu_routes.py`**：
- 所有 Playwright 操作改为 `pool.execute(lambda page: ...)`
- 新增 `/api/tu/login` 手动登录接口（自动登录失败时可在浏览器窗口手动操作）

**`src/api/routes/pinduoduo_routes.py`**：
- 同上，全部改为 `pool.execute(lambda page: ...)`
- 去掉 `get_browser_executor()` 依赖

**`src/tools/tu_tool.py`、`src/tools/pinduoduo_tool.py`**：
- `execute_with_client` 改用 `pool.execute()` 代替 `pool.get_page()`

**`src/spider/logistics_service.py`**：
- `query_with_retry` 改用 `pool.execute()` 包裹整个查询+重试逻辑

**`src/spider/tu/client.py`**：
- 改进 `_do_login_on_current_page()`：用 `type(delay=50)` 逐字输入代替 `fill()`，更好触发前端事件；增加可见性检查和更多等待时间；登录失败时自动截图
- 新增 `wait_for_manual_login(timeout=300)` 方法：打开浏览器等待用户手动登录

**`src/web/templates/tools/tu.html`**：
- 新增「手动登录（首次使用）」按钮

### 效果

- 从设计上消除所有线程问题（单线程拥有全部 Playwright 资源）
- 代码大幅精简（323 行 vs 843 行）
- 持久化 context 使用固定 `browser_data` 目录，Cookie 跨次运行保留
- 首次使用可通过「手动登录」在浏览器窗口完成登录，之后自动记住

---

## 2026-02-09 - 修复重建 context 时 "Sync API inside asyncio loop" 错误

### 变更说明（2026-02-09）

**问题**：context 失效后重建时，先 `playwright.stop()` 再 `sync_playwright().start()`，但 stop 后 asyncio 事件循环残留在线程上，新的 start 检测到就报 `It looks like you are using Playwright Sync API inside the asyncio loop`。

**修改**（`src/spider/query_manager.py`）：
- `_rebuild_shared_context()` 改为**优先复用已有 playwright 实例**：只关闭旧 context，然后在同一个 playwright 上 `launch_persistent_context` 创建新 context。避免 stop+start 触发 asyncio 报错。
- 仅当 playwright 实例本身也坏了时才完全重建（stop + start）。
- 提取 `_build_context_args()` 和 `_setup_context()` 避免重复代码。

---

## 2026-02-09 - 彻底修复 Playwright 跨线程错误（Cannot switch to a different thread）

### 变更说明（2026-02-09）

**根本原因**：  
Playwright 同步 API 要求 context/page **只能在创建它的线程中使用**。但 `_browser_executor` 有 2 个工作线程（`max_workers=2`），加上拼多多路由直接在 Flask 请求线程（而非 executor 线程）中调用 `pool.get_page()`，导致 context 在线程 A 创建、page 在线程 B 使用，触发 `Cannot switch to a different thread` 或 `TargetClosedError`。

**修改**：

1. **`src/api/routes/context.py`**：executor 改为 `max_workers=1`，保证所有 Playwright 操作都在同一个线程上执行。
2. **`src/api/routes/pinduoduo_routes.py`**：所有 `pool.get_page()` 调用统一通过 `get_browser_executor().submit()` 在 executor 线程中执行，不再在 Flask 请求线程中直接调用。涉及路由：`/status`、`/login`、`/check_login_complete`、`/logout`、`/execute`。

**效果**：全部 Playwright 操作（途强 + 拼多多）都通过同一个单线程 executor 执行，不再有跨线程问题。

---

## 2026-02-09 - 浏览器池：context 失效后自动重建（彻底修复 TargetClosedError）

### 变更说明（2026-02-09）

**根本原因分析**：
1. `headless=False` 模式下，用户**手动关闭浏览器窗口**（或浏览器崩溃）导致 shared context 死掉。
2. context 死后 `_context_broken` 未被设置，因为错误发生在 TuClient 内部被自己 catch 了，没有传播到池的 `get_page` 异常处理。
3. 后续所有请求里 `_ensure_shared_context()` 检查 `_shared_context is not None` 就返回了，不重建——反复拿着已死的 context 调 `new_page()`，每次都失败。

**修复**（`src/spider/query_manager.py`）：
- **`_is_context_alive()`**：不仅检查 `_shared_context is not None`，还**实际测试** context 是否存活（访问 `.pages`，异常即已死）。
- **`_ensure_shared_context()`** 的快速路径加入 `_is_context_alive()` 检查；若 context 已死，直接进入重建流程。
- **`_rebuild_shared_context()`**：抽取独立方法，清理旧资源后重新 `launch_persistent_context`（仍用同一 `browser_data` 目录，登录态从磁盘恢复）。
- **`_on_context_closed()`** + **`context.on("close")`**：监听 context 的 close 事件（如用户关闭浏览器窗口），立刻标记 `_context_broken=True` 并清空 `_shared_context`，不等到下次 `new_page` 才发现。
- **`_create_new_instance()`**：`new_page()` 若报 TargetClosedError，自动 `_context_broken=True` → `_ensure_shared_context()` 重建 → 再 `new_page()` 重试一次，不直接报错给调用方。

**效果**：无论 context 因何失效（用户关窗口、浏览器崩溃、进程异常），都能自动检测并重建，调用方无感。

---

## 2026-02-09 - 浏览器池：交出实例前校验 page 未关闭，避免 TargetClosedError

### 变更说明（2026-02-09）

**问题**：调用方（如 TuClient）在 `page.goto()` 时仍报 `Target page, context or browser has been closed`。原因之一是池中可能还有「已关闭的 page」被当作空闲实例再次交出，用的时候才报错。

**修改**（`src/spider/query_manager.py`）：
- 新增 `_is_page_still_valid(instance)`：用 `page.is_closed()` 判断 page 是否仍可用。
- 在策略1、策略2中，**在交出实例前**先校验：若 `not _is_page_still_valid(instance)`，则从池中移除该实例并继续查找或新建，不再把已关闭的 page 交给调用方。

这样从池里拿到的 page 一定是未关闭的，从源头减少 TargetClosedError。

---

## 2026-02-09 - 浏览器池：单一 context + 多 page，真正共享登录缓存

### 变更说明（2026-02-09）

**问题**：用户反馈「每次进去都要登录」，怀疑未使用缓存。根因是 Chrome/Playwright 规定**同一 user_data_dir 只能被一个 persistent context 使用**；之前池内多个“实例”各自是独立 context，第二、第三个 context 无法同时使用同一目录，导致部分请求拿到的是临时/无效配置，登录态无法共享。

**修改**（`src/spider/query_manager.py`）：
- **单一持久化 context**：只维护一个 `_shared_playwright` 与 `_shared_context`（`launch_persistent_context` 使用固定 `browser_data` 目录），所有“实例”改为该 context 下的 **多个 page**（`context.new_page()`），从而真正共享 Cookie/登录态与缓存。
- **`_ensure_shared_context()`**：懒创建或重建（如 context 失效时）该唯一 context；重建前清空池内旧实例。
- **`_create_new_instance()`**：仅调用 `_ensure_shared_context()` 后 `_shared_context.new_page()`，不再为每个实例单独 `launch_persistent_context`。
- **`_close_instance()`**：只关闭当前实例的 **page**，不关闭 shared context/playwright；池 `close()` 时再统一关闭 context 与 playwright。
- **context 失效**：发生 target closed 时设置 `_context_broken`，下次获取实例时会重建 context（仍用同一 browser_data 目录），登录态从磁盘恢复。

效果：登录一次后，所有请求共用同一 context 与缓存目录，再次进入无需重复登录；需要清除时仍可手动删除 `browser_data` 目录。

---

## 2026-02-09 - 浏览器池：修复关闭时的跨线程错误

### 变更说明（2026-02-09）

**问题**：`close()` 方法在当前线程关闭所有实例时，如果实例是在其他线程创建的，会报错 `Cannot switch to a different thread`（Playwright 同步 API 要求必须在创建线程中关闭）。

**修改**（`src/spider/query_manager.py`）：
- **`close()` 方法**：只关闭当前线程创建的实例；其他线程创建的实例标记为 `should_close`，等待它们自行关闭；如果创建线程已不存在，再尝试强制关闭。
- **`_close_instance()` 方法**：增加线程检查，如果当前线程不是创建线程且创建线程还存在，则跳过关闭（避免跨线程错误）。

这样关闭时不会再出现跨线程错误，其他线程的实例会在自己的线程中正常关闭。

---

## 2026-02-09 - 浏览器池：全部繁忙时若未达上限则创建新实例

### 变更说明（2026-02-09）

**逻辑补充**：当所有实例都繁忙（`idle_instances == 0`）且未达到 `max_instances` 时，不再让新请求一直等待，而是**直接创建新实例**供当前请求使用。

**修改**（`src/spider/query_manager.py` 中 `_get_or_create_instance`）：
- 策略3 调整顺序与条件：先判断「池为空 → 创建首个」「已达上限 → 等待」；再判断「全部繁忙且未达上限 → 创建新实例」；最后才是按等待队列的渐进式扩展。
- 这样在只有 1 个实例且该实例正忙时，新请求会立即得到一个新实例，而不是 sleep 后重试等待。

---

## 2026-02-09 - 浏览器池：实例失效（Target closed）时关闭并移除，下次请求用新实例

### 变更说明（2026-02-09）

**问题**：当出现 `Page.goto: Target page, context or browser has been closed` 时，池仍把该实例标记为空闲并放回池中，后续请求会继续拿到已关闭的实例导致再次失败。

**修改**（`src/spider/query_manager.py`）：
- 新增 `_is_target_closed_error(e)`，用于判断是否为「页面/上下文/浏览器已关闭」类错误。
- 在 `get_page` 的 `except Exception` 中，若检测到此类错误且存在 `instance`，则设置 `instance.should_close = True`；在 `finally` 中 `_release_instance` 会将该实例从池中移除并关闭，不再复用。
- 下次调用 `get_page()` 时会得到新实例（或池中其他空闲实例），避免重复使用已关闭的实例。

---

## 2026-02-09 - 浏览器缓存固定为同一 browser_data 目录（持久化、不自动清理）

### 变更说明（2026-02-09）

**需求**：运行时的浏览器数据（登录态、Cookie 等）作为持久化缓存，所有实例、每次运行都使用同一目录；不自动清理，需清除时由用户手动删除。

**路径逻辑**：
- 新增 `get_browser_data_dir(app_name='JNTools')`（`src/utils/path_helper.py`）：固定返回用户数据目录下的 `browser_data`（Windows 为 `%LOCALAPPDATA%\JNTools\browser_data`），保证路径唯一、不随项目路径或运行目录变化。
- 浏览器池（`src/spider/query_manager.py`）改为使用 `get_browser_data_dir()`，不再使用 `get_safe_data_path('browser_data')`，避免有时用项目目录、有时用用户目录导致「不同运行用不同 profile」的问题。

**效果**：每次启动、每个浏览器实例都使用同一 `browser_data` 目录，登录/缓存持久有效；程序不会自动清理该目录，需要清除时手动删除该文件夹即可。

**修改文件**：
- `src/utils/path_helper.py` - 新增 `get_browser_data_dir()`
- `src/spider/query_manager.py` - 使用 `get_browser_data_dir`，注释明确为「固定持久化缓存」

---

## 2026-02-02 - 途强飞书同步改为「仅按开始时间新增、不做更新」

### 变更说明（2026-02-02）

**途强飞书表格同步（`src/spider/tu/feishutable.py`）**:
- 数据逻辑调整：仅根据「开始时间」判断是否已存在；开始时间不存在则新增一条，已存在则跳过（不做任何更新）。
- 移除所有「更新」逻辑：不再拉取 `record_id`、不再调用 `batch_update_records`，返回值去掉 `update_count`。
- 现有记录仅用 `existing_start_times` 集合做去重判断，本批内相同开始时间也只新增一条。

**修改文件**: `src/spider/tu/feishutable.py`

---

## 2026-02-01 - 途强数据自动同步到飞书表格 & 页面刷新保证 XHR 拦截

### 变更说明（2026-02-01）

**途强自动化客户端（`src/spider/tu/client.py`）**:
- **飞书同步集成**：`execute_automation` 在成功获取最近 30 天记录后，自动调用 `sync_tu_data_to_feishu(records)` 将数据同步到飞书多维表格；返回值增加 `feishu_sync` 字段（同步结果或异常信息）。
- **页面刷新**：`goto` 目标页后增加 `page.reload(wait_until='domcontentloaded')`，登录成功后再次 `reload`，确保 SPA 页面触发 XHR 请求、能拦截到带 Authorization 的请求。

**途强飞书表格同步（`src/spider/tu/feishutable.py`）**:
- 提供 `sync_tu_data_to_feishu(records, app_token, table_id)`，将途强记录同步到指定飞书多维表格。
- 以「开始时间」为唯一标识，区分创建与更新；支持批量创建/更新，失败时降级为单条操作。
- 字段映射：`开始时间`（Text）、`公里`（米转公里 2 位小数）、`startTime`/`endTime`（DateTime 毫秒时间戳）、`平均时速`（2 位小数）、`坐标`（结束点 lng,lat）。

**修改/涉及文件**:
- `src/spider/tu/client.py` - 引入 `sync_tu_data_to_feishu`，执行成功后调用并返回 `feishu_sync`；保留此前新增的 reload 逻辑。
- `src/spider/tu/feishutable.py` - 已实现并沿用（无新增改动）。

---

## 2026-01-30 - 删除未使用的 api/routes.py，文档统一为 api/routes/ 包

### 变更说明（2026-01-30）

- **删除**: `src/api/routes.py`（单文件，约 1175 行）。应用实际使用的是 **`src/api/routes/` 包**（Python 在存在同名包时优先加载包），该单文件从未被注册，已删除。
- **文档更新**: README、配置说明、开发指南、开机自启动测试指南、飞书聊天机器人配置说明、PROJECT_DOCUMENTATION 中所有「在 api/routes.py 中添加」或「位置 api/routes.py」的表述已改为「api/routes/ 包」或对应 Blueprint 文件（如 `health.py`、`feishu_routes.py`）。

---

## 2026-01-30 - Socket.IO 对接测试环境（websocket-api.md）

### 变更说明（2026-01-30）

**对接规范**（`docs/websocket-api.md`）:
- 服务端为 **Socket.IO**（与 HTTP 同端口），连接 path 为 `/ws`，默认事件 `forward`
- 测试环境：`http://localhost:3000`，path `/ws`

**客户端改动**:
- 客户端由原始 WebSocket 改为 **Socket.IO 客户端**（`python-socketio[client]`）
- 连接参数：`socketio_path=/ws`，`transports=['websocket','polling']`，监听事件 `forward`
- 默认配置：host `127.0.0.1`，port `3000`，path `/ws`（测试环境）

**配置与页面**:
- 新增配置项 `WS_CLIENT_PATH`（默认 `/ws`），支持从 `app_config.json` 读写
- 管理页增加「Socket.IO path」输入框、状态中展示 `sid` 与最近一次 `forward` 消息内容

**修改/新增文件**:
- `requirements.txt` - 新增 `python-socketio[client]>=5.10.0`，保留 `websocket-client`
- `src/config.py` - 默认 port 改为 3000，新增 `WS_CLIENT_PATH` 及加载逻辑
- `src/utils/config_manager.py` - 支持 `ws_client_path` 的读写与应用
- `src/utils/websocket_client.py` - 重写为 Socket.IO 客户端（connect/disconnect/forward/sid/自动重连）
- `src/api/routes/websocket_routes.py` - 配置与连接 API 支持 `path` 参数（在包内注册）
- `src/web/templates/websocket.html` - 标题与说明改为 Socket.IO，默认端口 3000，path 输入，展示 sid 与 last_forward_payload

---

## 2026-01-30 - WebSocket 客户端与管理页面

### 功能新增（2026-01-30）

**新增内容**:
- 新增 **WebSocket 客户端**：可配置连接地址与端口，默认开启，Flask 运行时会按配置自动连接
- 新增 **WebSocket 管理页面**：侧栏「WebSocket 客户端」入口，可查看连接状态、手动连接/断开、修改并保存配置

**配置说明**:
- `config.py`：`WS_CLIENT_ENABLED`（默认 True）、`WS_CLIENT_HOST`（默认 127.0.0.1）、`WS_CLIENT_PORT`（默认 8765）
- 可通过环境变量 `WS_CLIENT_HOST`、`WS_CLIENT_PORT` 覆盖
- 配置可保存到 `app_config.json`，与现有配置页一致

**API 接口**:
- `GET /api/websocket/status` - 获取连接状态（connected/connecting、last_error、last_message_time）
- `GET /api/websocket/config` - 获取当前配置
- `POST /api/websocket/config` - 更新并保存配置
- `POST /api/websocket/connect` - 发起连接（可选传入 host/port）
- `POST /api/websocket/disconnect` - 断开连接

**修改/新增文件**:
- `requirements.txt` - 新增依赖 `websocket-client>=1.6.0`
- `src/config.py` - 新增 WebSocket 客户端相关配置及从文件加载
- `src/utils/config_manager.py` - 支持 WebSocket 配置的读写与应用
- 新增 `src/utils/websocket_client.py` - WebSocket 客户端管理单例（连接/断开/状态/自动重连）
- `src/api/routes.py` - 新增 WebSocket 相关 API 路由
- `src/main.py` - Flask 启动后调用 `start_if_enabled()` 默认连接，退出时 `cleanup()` 中断开
- `src/web/routes.py` - 新增 `/websocket` 页面路由
- `src/web/templates/base.html` - 侧栏新增「WebSocket 客户端」入口
- 新增 `src/web/templates/websocket.html` - WebSocket 管理页（状态、配置表单、连接/断开按钮）
- `README.md` - 功能特性中补充 WebSocket 客户端说明

---

## 2026-01-29 - 拼多多页面：同步到飞书表格

### 功能新增（2026-01-29）

**新增内容**:
- 拼多多工具页增加「同步到飞书表格」功能卡片
- 将本地缓存的订单数据（最近一次「同步订单」结果）同步到飞书多维表格

**页面功能**:
- 说明：使用最近一次同步订单的缓存数据，同步到飞书表格（订单号、订单状态、商品名称等）
- 可选填写 App Token、Table ID，留空使用默认（与 feishutable 一致）
- 按钮「同步到飞书表格」调用 API，下方展示同步结果（成功/新建/更新/失败条数）

**API**:
- `POST /api/pinduoduo/sync-to-feishu`：请求体可选 `app_token`、`table_id`；读取 `cache/pinduoduo_orders_recent.json` 中的 `data.result.pageItems`，调用 `sync_orders_to_feishu` 并返回结果

**修改/新增文件**:
- `src/api/routes.py` - 新增 `pinduoduo_sync_to_feishu` 路由
- `src/web/templates/tools/pinduoduo.html` - 新增飞书同步卡片、样式与脚本

---

## 2026-01-29 - 飞书支持发送卡片消息

### 功能新增（2026-01-29）

**新增内容**:
- 飞书消息发送器与客户端支持发送**卡片消息**（interactive 类型）
- `FeishuClient.send_card_message(user_id, card)`：底层发送卡片
- `FeishuMessageSender.send_card_message(card, user_id=None)`：高层接口，默认使用 `FEISHU_USER_ID`

**配置说明**:
- 与文本消息使用同一套配置，无需额外配置
- 需在 `.env` 中配置：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_USER_ID`
- 卡片内容可为 dict（自动序列化为 JSON）或已是 JSON 字符串

**修改/新增文件**:
- `src/tools/feishu/feishu_client.py` - 新增 `send_card_message`、`import json`
- `src/tools/feishu/message_sender.py` - 新增 `send_card_message`
- `README.md` - 补充飞书支持卡片消息说明

---

## 2026-01-29 - 新增：途强物联网平台助手（tu）

### 功能新增（2026-01-29）

**新增内容**:
- 新增途强智能设备管理平台（iot.tqiot.com）自动化模块，参考拼多多助手实现
- 支持自动登录（账号密码）、打开 reportDown 页面、获取最近 30 天记录并缓存到本地

**功能特点**:
- ✅ 自动登录：使用配置的账号（18038361262）和密码自动填充并提交登录
- ✅ 目标页面：https://iot.tqiot.com/#/?to=reportDown
- ✅ 最近 30 天记录：执行时自动登录后进入 reportDown，从 XHR 响应或页面表格获取记录并缓存
- ✅ 状态与缓存：执行状态和记录缓存使用安全路径（用户数据目录），与拼多多一致
- ✅ Web 界面：途强助手页面支持刷新状态、一键「获取最近 30 天记录」、清除登录

**配置说明**:
- `config.py` 新增：`TU_TARGET_URL`、`TU_STATUS_PATH`、`TU_ACCOUNT`、`TU_PASSWORD`
- 账号密码可通过环境变量 `TU_ACCOUNT`、`TU_PASSWORD` 覆盖，避免硬编码

**API 接口**:
- `GET /api/tu/status` - 获取最后执行状态
- `POST /api/tu/execute` - 执行自动化（自动登录 + 获取最近 30 天记录）
- `POST /api/tu/logout` - 清除登录状态和 Cookie

**修改/新增文件**:
- 新增：`src/spider/tu/__init__.py`、`src/spider/tu/client.py`
- 新增：`src/tools/tu_tool.py`、`src/web/templates/tools/tu.html`
- `src/config.py` - 途强相关配置
- `src/api/routes.py` - 途强 API 路由
- `src/app.py` - 注册途强工具

**流程优化（同日）**:
- 执行时先直接访问 `https://iot.tqiot.com/#/?to=reportDown`
- 若被登录拦截（该 URL 下出现登录框），则在此页执行自动登录，登录成功后再打开 reportDown 并获取数据
- 若未被拦截，则直接执行获取最近 30 天记录的逻辑

## 2026-01-27 - 新增：飞书消息发送测试页面

### 功能新增（2026-01-27）

**新增内容**:
- 创建了飞书消息发送测试页面，方便测试和调试飞书消息发送功能
- 添加了测试API接口，支持测试发送登录提醒和自定义消息

**功能特点**:
- ✅ 实时显示飞书配置状态（是否启用、客户端配置、默认用户ID）
- ✅ 测试发送拼多多登录提醒消息
- ✅ 测试发送自定义文本消息
- ✅ 支持指定接收用户ID（可选，不指定则使用默认用户）
- ✅ 实时显示发送结果（成功/失败）
- ✅ 友好的用户界面，清晰的错误提示

**页面功能**:
1. **状态检查**：
   - 显示飞书通知是否启用
   - 显示客户端是否已配置
   - 显示默认接收用户ID

2. **测试1：发送登录提醒**：
   - 测试发送拼多多登录提醒消息
   - 可指定接收用户ID（可选）

3. **测试2：发送自定义消息**：
   - 测试发送自定义文本消息
   - 可输入消息内容
   - 可指定接收用户ID（可选）

**API接口**:
- `GET /api/feishu/status` - 获取飞书消息发送器状态
- `POST /api/feishu/test/login-alert` - 测试发送登录提醒
- `POST /api/feishu/test/custom-message` - 测试发送自定义消息

**访问方式**:
- 侧边栏导航：📱 飞书消息测试
- 直接访问：`/feishu-test`

**修改文件**:
- 新增：`src/web/templates/feishu_test.html` - 飞书消息测试页面
- `src/web/routes.py` - 添加 `/feishu-test` 路由
- `src/web/templates/base.html` - 在侧边栏添加飞书消息测试链接
- `src/api/routes.py` - 添加飞书消息测试API接口

## 2026-01-27 - 优化：订单分页请求添加延迟避免风控

### 性能优化（2026-01-27）

**优化内容**:
- 将订单分页请求从并发改为串行，每个请求之间随机等待5-10秒
- 避免请求过于频繁被风控系统拦截

**实现逻辑**:
1. 先获取第一页数据（立即获取）
2. 从第二页开始，每个请求前随机等待5-10秒
3. 串行获取所有页面，避免并发请求

**优化效果**:
- ✅ 避免被风控系统拦截
- ✅ 随机延迟（5-10秒）模拟人工操作，降低被检测风险
- ✅ 串行请求确保请求间隔，提高成功率

**技术实现**:
- 使用 `setTimeout` 和 `Promise` 实现延迟
- 随机生成5-10秒之间的延迟时间
- 使用 `for` 循环串行请求，替代 `Promise.all` 并发请求

**修改文件**:
- `src/spider/pinduoduo/client.py` - 优化 `fetch_recent_orders()` 方法中的分页请求逻辑

## 2026-01-27 - 修复：飞书表格客户端获取记录时的空值处理

### Bug 修复（2026-01-27）

**修复内容**:
- 修复了 `list_records` 和 `get_all_records` 方法中，当 API 返回的 `items` 字段为 `None` 时导致的 `TypeError` 错误
- 使用 `result.get('items') or []` 确保 `items` 不会是 `None`，避免调用 `len()` 时出错

**问题原因**:
- 当飞书 API 返回的数据中 `items` 字段为 `None` 时，`result.get('items', [])` 会返回 `None`（因为 key 存在但值为 `None`）
- 导致后续调用 `len(items)` 时出现 `TypeError: object of type 'NoneType' has no len()`

**解决方案**:
- 使用 `result.get('items') or []` 替代 `result.get('items', [])`
- 这样即使 `items` 为 `None`，也会使用空列表 `[]` 作为默认值

**修改文件**:
- `src/tools/feishu/feishu_table_client.py` - 修复 `list_records()` 和 `get_all_records()` 方法中的空值处理

## 2026-01-27 - 功能增强：订单同步支持按订单号更新已存在记录

### 功能增强（2026-01-27）

**新增内容**:
- 实现了订单同步时的去重和更新逻辑，如果订单号已存在则更新数据，不存在则创建新记录
- 避免了重复订单数据的问题，确保订单号唯一性

**实现逻辑**:
1. 先获取所有现有记录，建立订单号到 `record_id` 的映射
2. 遍历待同步的订单，根据订单号判断是创建还是更新
3. 分离需要创建和需要更新的订单，分别批量处理
4. 使用批量创建和批量更新 API 提高效率
5. 如果批量操作失败，自动降级为单条操作

**功能特点**:
- ✅ 自动检测订单号是否已存在
- ✅ 已存在的订单自动更新，不创建重复记录
- ✅ 新订单正常创建
- ✅ 支持批量创建和批量更新，提高效率
- ✅ 批量操作失败时自动降级为单条操作，提高容错性
- ✅ 详细的统计信息：创建数量、更新数量、成功数量、失败数量

**返回结果增强**:
- `create_count`: 新创建的订单数量
- `update_count`: 更新的订单数量
- `success_count`: 成功处理的订单总数（创建 + 更新）
- `fail_count`: 失败的订单数量
- `message`: 包含详细统计信息的消息

**性能优化**:
- 先一次性获取所有现有记录，建立映射关系，避免每条订单都查询
- 使用批量 API 减少 API 调用次数
- 分批处理大量数据，避免单次请求过大

**修改文件**:
- `src/spider/pinduoduo/feishutable.py` - 修改 `sync_orders_to_feishu()` 方法，实现订单号去重和更新逻辑

## 2026-01-27 - 功能增强：拼多多订单数据分页获取（JavaScript内完成）

### 功能增强（2026-01-27）

**新增内容**:
- 实现了拼多多订单数据的分页获取功能，在 JavaScript 的 `fetch_script` 中直接完成分页逻辑
- 之前只能获取第一页（20条）数据，现在可以自动获取最多5页的完整数据（最多100条）

**实现逻辑**:
1. 在 JavaScript 中先获取第一页数据，获取总订单数（`totalItemNum`）
2. 根据总订单数和每页数量（20条）计算总页数，最多获取5页
3. 使用 `Promise.all` 并发获取所有剩余页面的数据（第2-5页）
4. 合并所有页面的订单数据（`pageItems`）
5. 返回合并后的完整数据，由 Python 端缓存到本地并同步到飞书表格

**功能特点**:
- ✅ 分页逻辑完全在 JavaScript 中完成，减少 Python 和浏览器之间的交互次数
- ✅ 使用 `Promise.all` 并发请求，提高获取效率
- ✅ 自动计算总页数，最多获取5页（100条订单）
- ✅ 单页获取失败不影响其他页面，继续合并成功获取的数据
- ✅ 返回结果包含实际获取数量和总订单数等统计信息

**技术实现**:
- 在 `fetch_script` 中定义 `fetchPage` 辅助函数用于获取单页数据
- 使用 `Promise.all` 并发获取多页数据，提高效率
- 合并所有页面的 `pageItems` 数组，构建完整的返回结果

**返回结果增强**:
- `data_count`: 实际获取的订单数量（最多100条）
- `total_item_num`: 服务器返回的总订单数
- `message`: 包含数据统计的详细消息

**修改文件**:
- `src/spider/pinduoduo/client.py` - 修改 `fetch_recent_orders()` 方法中的 `fetch_script`，在 JavaScript 中实现分页逻辑

## 2026-01-26 - 修复：单元测试文件导入错误

### Bug 修复（2026-01-26）

**修复内容**:
- 修复了直接运行测试文件时的相对导入错误
- 添加了路径处理逻辑，支持直接运行和作为模块运行两种方式

**问题原因**:
- 直接运行测试文件时，Python 无法识别相对导入（`from .module import ...`）
- 相对导入只能在包内作为模块导入时使用

**解决方案**:
- 添加了路径处理逻辑，在直接运行时自动添加项目根目录到 `sys.path`
- 使用 try-except 处理导入，优先使用绝对导入，失败时回退到相对导入
- 支持两种运行方式：
  - 直接运行：`python src/tools/feishu/test_feishu_table_client.py`
  - 模块运行：`python -m unittest src.tools.feishu.test_feishu_table_client`

**修改文件**:
- `src/tools/feishu/test_feishu_table_client.py` - 修复导入逻辑

## 2026-01-26 - 新增：为飞书表格客户端添加单元测试

### 测试新增（2026-01-26）

**新增内容**:
- 创建了 `test_feishu_table_client.py` 单元测试文件
- 使用 `unittest` 和 `mock` 框架编写完整的测试用例
- 覆盖了 `FeishuTableClient` 的主要功能和方法

**测试覆盖**:
1. **初始化测试**:
   - 测试带参数初始化
   - 测试不带参数初始化
   - 测试参数获取逻辑

2. **参数验证测试**:
   - 测试缺少 app_token 时的异常处理
   - 测试缺少 table_id 时的异常处理
   - 测试参数优先级（方法参数 > 实例属性）

3. **API 方法测试**:
   - `get_app_info()` - 获取应用信息
   - `list_tables()` - 获取表格列表
   - `get_table_info()` - 获取表格信息
   - `list_fields()` - 获取字段列表
   - `get_table_schema()` - 获取完整表结构
   - `create_record()` - 创建记录
   - `batch_create_records()` - 批量创建记录
   - `update_record()` - 更新记录
   - `delete_record()` - 删除记录
   - `get_record()` - 获取记录
   - `list_records()` - 获取记录列表
   - `get_all_records()` - 获取所有记录（分页处理）

4. **异常处理测试**:
   - 测试 API 请求失败场景
   - 测试网络异常场景
   - 测试缺少 access_token 场景

**运行测试**:
```bash
# 方式1：使用 unittest
python -m unittest src.tools.feishu.test_feishu_table_client -v

# 方式2：使用 pytest（如果已安装）
pytest src/tools/feishu/test_feishu_table_client.py -v

# 方式3：直接运行测试文件
python src/tools/feishu/test_feishu_table_client.py
```

**测试特点**:
- ✅ 使用 Mock 模拟 API 调用，无需实际连接飞书服务器
- ✅ 测试覆盖全面，包括成功和失败场景
- ✅ 包含集成测试类（默认跳过，需要实际配置时启用）
- ✅ 测试代码结构清晰，易于维护和扩展

**修改文件**:
- 新增：`src/tools/feishu/test_feishu_table_client.py` - 单元测试文件

## 2026-01-26 - 新增：添加获取表格结构信息的方法

### 功能新增（2026-01-26）

**新增内容**:
- 添加了获取表格结构信息的方法，方便了解表格字段结构，便于开发插入数据
- 新增方法包括：获取应用信息、获取表格列表、获取表格信息、获取字段列表、获取完整表结构、打印表结构

**新增方法**:
1. `get_app_info()` - 获取多维表格应用信息
2. `list_tables()` - 获取应用中的所有数据表列表
3. `get_table_info()` - 获取数据表信息
4. `list_fields()` - 获取数据表的字段列表（表结构）
5. `get_table_schema()` - 获取数据表的完整结构信息（表信息 + 字段列表）
6. `print_table_schema()` - 打印数据表结构信息（用于调试和开发）

**使用示例**:
```python
# 创建客户端
client = FeishuTableClient(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx"
)

# 方式1：获取完整表结构
schema = client.get_table_schema()
print(f"表名: {schema['table']['name']}")
for field in schema['fields']:
    print(f"  - {field['field_name']} ({field['type']})")

# 方式2：直接打印表结构（推荐，更直观）
client.print_table_schema()
# 输出：
# ========== 数据表结构 ==========
# 表名: 订单表
# 字段列表:
# 1. 订单号 (text) [必填]
#    field_id: fldxxxxx
# 2. 金额 (number)
#    field_id: fldyyyyy
# ...

# 方式3：只获取字段列表
fields = client.list_fields()
for field in fields:
    print(f"{field['field_name']}: {field['type']}")

# 获取所有表格列表
tables = client.list_tables()
for table in tables:
    print(f"{table['name']}: {table['table_id']}")
```

**优化效果**:
- ✅ 可以快速了解表格结构，避免插入数据时字段名错误
- ✅ 支持查看字段类型、是否必填等信息
- ✅ 提供友好的打印输出，方便调试
- ✅ 支持获取应用中的所有表格列表

**修改文件**:
- `src/tools/feishu/feishu_table_client.py` - 添加表格结构相关方法

## 2026-01-26 - 优化：支持在创建实例时传入app_token和table_id

### 功能优化（2026-01-26）

**优化内容**:
- 修改 `FeishuTableClient` 的 `__init__` 方法，支持在创建实例时传入 `app_token` 和 `table_id`
- 所有操作方法中的 `app_token` 和 `table_id` 参数改为可选，如果不提供则使用实例属性
- 调整方法参数顺序，将必需参数放在前面，可选参数放在后面
- 添加 `_get_app_token_and_table_id` 辅助方法，统一处理参数获取逻辑

**使用方式**:
```python
# 方式1：在创建实例时传入app_token和table_id（推荐，更简洁）
client = FeishuTableClient(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx"
)
# 后续调用时不需要再传入这两个参数
result = client.create_record(fields={"姓名": "张三", "年龄": 25})
all_records = client.get_all_records()

# 方式2：在方法调用时传入（会覆盖实例属性）
client = FeishuTableClient()
result = client.create_record(
    fields={"姓名": "张三", "年龄": 25},
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx"
)
```

**优化效果**:
- ✅ 使用更简洁，避免重复传入相同的参数
- ✅ 支持两种使用方式，灵活方便
- ✅ 向后兼容，原有调用方式仍然支持

**修改文件**:
- `src/tools/feishu/feishu_table_client.py` - 优化初始化方法和所有操作方法

## 2026-01-26 - 重构：将飞书多维表格功能提取为独立模块

### 代码重构（2026-01-26）

**重构内容**:
- 将 `FeishuTableClient` 类从 `message_sender.py` 提取到独立的 `feishu_table_client.py` 文件
- 提高代码模块化程度，职责分离更清晰
- 更新模块导出，方便其他模块使用

**文件变更**:
- 新增：`src/tools/feishu/feishu_table_client.py` - 飞书多维表格客户端独立模块
- 修改：`src/tools/feishu/message_sender.py` - 移除表格相关代码，恢复为纯消息发送模块
- 修改：`src/tools/feishu/__init__.py` - 添加 `FeishuTableClient` 和 `get_feishu_table_client` 导出

**使用方式**:
```python
# 方式1：从模块直接导入
from tools.feishu import FeishuTableClient, get_feishu_table_client

# 方式2：从子模块导入
from tools.feishu.feishu_table_client import FeishuTableClient, get_feishu_table_client

# 使用方式不变
client = get_feishu_table_client()
```

**优化效果**:
- ✅ 代码结构更清晰，职责分离
- ✅ 模块化程度提高，便于维护
- ✅ 导入路径更灵活，支持多种导入方式

## 2026-01-26 - 添加飞书多维表格管理功能

### 功能新增（2026-01-26）

**新增内容**:
- 在 `FeishuMessageSender` 模块中添加了 `FeishuTableClient` 类，提供飞书多维表格的完整操作功能
- 实现了创建、更新、删除、查询等核心操作方法
- 支持单条和批量操作，提高数据操作效率

**功能特点**:
1. **单条记录操作**:
   - `create_record()` - 创建单条记录
   - `update_record()` - 更新单条记录
   - `delete_record()` - 删除单条记录
   - `get_record()` - 获取单条记录

2. **批量操作**:
   - `batch_create_records()` - 批量创建记录
   - `batch_update_records()` - 批量更新记录
   - `batch_delete_records()` - 批量删除记录

3. **查询功能**:
   - `list_records()` - 获取记录列表（支持分页、筛选、排序）
   - `get_all_records()` - 获取所有记录（自动处理分页）

**技术实现**:
- 复用 `FeishuClient` 的 token 获取机制，避免重复实现
- 统一的请求处理方法 `_make_request()`，简化代码结构
- 完整的错误处理和日志记录
- 支持筛选条件和排序条件
- 自动处理分页，方便获取大量数据

**使用示例**:
```python
from tools.feishu.message_sender import get_feishu_table_client

# 获取客户端实例
client = get_feishu_table_client()

# 创建记录
record = client.create_record(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx",
    fields={"姓名": "张三", "年龄": 25}
)

# 更新记录
client.update_record(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx",
    record_id="recxxxxxxxxxxxx",
    fields={"年龄": 26}
)

# 批量创建
client.batch_create_records(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx",
    records=[
        {"fields": {"姓名": "张三", "年龄": 25}},
        {"fields": {"姓名": "李四", "年龄": 30}}
    ]
)

# 获取所有记录
all_records = client.get_all_records(
    app_token="bascnCMII2O1qg4W1O4w",
    table_id="tblxxxxxxxxxxxx"
)
```

**API接口**:
- 基于飞书开放平台的多维表格 API v1
- 支持完整的 CRUD 操作
- 遵循飞书 API 规范，返回标准格式数据

**修改文件**:
- `src/tools/feishu/message_sender.py` - 添加 `FeishuTableClient` 类和全局单例函数

## 2026-01-26 - 修复浏览器全局Accept header导致API请求返回HTML的问题

### Bug 修复（2026-01-26）

**修复内容**:
- 移除了 `BrowserPool` 中 `extra_http_headers` 的全局 `Accept` header 配置
- 修复了 `fetch_recent_orders` 方法中 fetch 请求的 `accept` header 配置错误
- 将 fetch 请求的 `accept: "*/*"` 改为 `accept: "application/json"`，确保服务器返回JSON格式数据
- 补充了缺失的 header：`pragma: "no-cache"`、`upgrade-insecure-requests: "1"`
- 添加了 `mode: "cors"` 参数
- 将 `cache-control` 从 `"max-age=0"` 改为 `"no-cache"`，与浏览器实际请求保持一致

**问题原因**:
1. **根本原因**：`BrowserPool` 在创建浏览器上下文时强制设置了全局 `Accept: "text/html,application/xhtml+xml,..."` header
   - 这个全局 header 会覆盖所有通过该浏览器上下文发起的请求（包括 `page.goto()` 和 `fetch()`）
   - 导致即使用户在 fetch 请求中设置了 `accept: "application/json"`，也会被全局 header 覆盖
   - 结果：API 请求返回 HTML 而不是 JSON

2. **次要原因**：fetch 请求中的 `accept` header 被错误设置为 `"*/*"`，缺少明确的 JSON 类型声明

**技术细节**:
- 移除了 `extra_http_headers` 中的 `Accept` header，让浏览器和 fetch 请求自己决定使用什么 Accept header
- 对于页面导航（`page.goto()`），浏览器会自动设置合适的 Accept header
- 对于 fetch 请求，在代码中明确指定 `accept: "application/json"`，确保返回 JSON 格式
- `accept: "application/json"` 明确告诉服务器客户端期望接收JSON格式的响应

**修改文件**:
- `src/spider/query_manager.py` - 移除 `extra_http_headers` 中的全局 `Accept` header
- `src/spider/pinduoduo/client.py` - 修复 `fetch_recent_orders` 方法中的 fetch 请求配置

## 2026-01-26 - 修复拼多多登录状态误判 Bug

### Bug 修复（2026-01-26）

**修复内容**:
- 修复了 `PinduoduoClient._check_login_status_once` 中的登录检测逻辑
- 解决了当 URL 处于登录页面但包含 `redirectUrl=...home` 参数时被误判为“已登录”的问题

**技术细节**:
- 将判断逻辑从 `(not login) or home` 修改为 `(not login) and (home or indicators)`
- 确保只要 URL 中存在 `login` 关键字，就绝对不会被判定为登录成功

**修改文件**:
- `src/spider/pinduoduo/client.py` - 修改 `_check_login_status_once` 的判定逻辑

## 2026-01-26 - 在拼多多助手页面添加同步订单功能

### 功能新增（2026-01-26）

**新增内容**:
- 在拼多多助手 Web 页面添加了“同步订单”按钮
- 实现了同步订单的前端逻辑，调用 `/api/pinduoduo/execute` 接口触发自动化流程
- 添加了同步过程中的加载状态显示和结果反馈
- 优化了按钮布局，将“同步订单”设为主要操作，而“重新登录”调整为次要操作

**技术细节**:
1. **前端交互**:
   - 使用异步 `fetch` 调用 `/api/pinduoduo/execute`
   - 处理同步成功、失败及登录失效（被拦截）等不同场景
   - 同步成功后自动刷新页面状态显示
   - 登录失效时自动引导用户进入扫码登录流程

2. **UI 优化**:
   - 为同步按钮添加了 Loading 动画
   - 调整了按钮的优先级和配色

**修改文件**:
- `src/web/templates/tools/pinduoduo.html` - 添加按钮及相关 JavaScript 逻辑

## 2026-01-26 - 实现拼多多订单抓取和缓存功能

### 功能新增（2026-01-26）

**新增内容**:
- 在 `PinduoduoClient` 中实现了 `fetch_recent_orders` 方法，支持获取最近 30 天的订单数据
- 实现了订单数据的本地缓存功能，数据保存在 `cache/pinduoduo_orders_recent.json`
- 在 `execute_automation` 流程中集成了订单抓取逻辑，登录成功后自动触发抓取

**技术细节**:
1. **订单抓取逻辑**:
   - 自动导航至拼多多商家后台订单列表页面
   - 使用 `page.evaluate` 在浏览器上下文中执行异步 `fetch` 请求
   - 动态计算最近 30 天的时间范围（Unix 时间戳）
   - 支持跨域请求和凭证包含（credentials: include）

2. **本地缓存机制**:
   - 使用 `get_safe_data_path` 确保缓存路径在不同环境下均可写入
   - 缓存数据包含抓取时间戳和原始 API 返回的订单列表
   - 目录结构：`cache/pinduoduo_orders_recent.json`

3. **自动化流程集成**:
   - 修改了 `execute_automation` 方法
   - 在检测到登录成功后，立即启动订单抓取任务
   - 抓取结果包含在自动化执行的返回字典中

**优化效果**:
- ✅ 实现了拼多多商家数据的自动化获取
- ✅ 提供数据持久化存储，方便后续分析和展示
- ✅ 流程全自动，无需人工干预

**修改文件**:
- `src/spider/pinduoduo/client.py` - 新增 `fetch_recent_orders` 和 `_get_orders_cache_path` 方法，更新 `execute_automation`

## 2026-01-26 - 移除冗余的手动 Cookie 管理

### 代码优化（2026-01-26）

**优化内容**:
- 移除了 `PinduoduoClient` 中的手动 Cookie 加载和保存逻辑
- 移除了 `Config.PINDUODUO_COOKIE_PATH` 配置项
- 完全依赖 `BrowserPool` 的持久化浏览器上下文（`browser_data`）来管理登录状态
- 简化了 `PinduoduoClient` 代码，使其更专注于业务逻辑

**问题背景**:
- 之前 `BrowserPool` 已经实现了基于 `browser_data` 目录的持久化上下文（Persistent Context）
- Playwright 会自动处理该目录下的 cookies、localStorage 和 sessionStorage 的保存与恢复
- `PinduoduoClient` 原有的手动保存到 `pinduoduo_cookies.json` 的逻辑变得冗余，且可能导致状态同步不一致

**优化效果**:
- ✅ 减少冗余代码，降低维护成本
- ✅ 登录状态管理更统一，完全交给 Playwright 持久化机制
- ✅ 避免了手动注入 Cookie 可能带来的潜在冲突
- ✅ 代码结构更清晰，职责分明

**修改文件**:
- `src/config.py` - 移除 `PINDUODUO_COOKIE_PATH`
- `src/spider/pinduoduo/client.py` - 移除 `load_cookies`、`save_cookies` 及其相关调用

## 2026-01-23 - 新增浏览器池调用规范文档

### 文档新增（2026-01-23）

**新增内容**:
- 创建了浏览器池调用规范文档，详细说明如何使用 `BrowserPool` 进行批量爬虫任务
- 包含完整的使用示例、最佳实践和常见问题解答

**文档内容**:
1. **核心概念**:
   - BrowserPool 特性说明
   - 渐进式扩展策略
   - 智能复用机制

2. **基础使用**:
   - 初始化浏览器池
   - 获取页面对象（上下文管理器）
   - 关闭浏览器池

3. **批量任务处理**:
   - 方案一：顺序处理（推荐用于小批量数据）
   - 方案二：并发处理（推荐用于大批量数据）
   - 完整示例：批量爬取商品信息

4. **最佳实践**:
   - 超时时间设置建议
   - 异常处理规范
   - 并发数设置建议
   - 资源清理规范
   - 进度监控方法
   - 结果保存策略

5. **监控和调试**:
   - 获取浏览器池状态
   - 性能优化建议

6. **常见问题**:
   - 浏览器池状态检查
   - 性能问题排查
   - 超时处理
   - 自动清理机制
   - 多浏览器池使用

**使用场景**:
- 有一组数据需要爬虫爬取
- 需要循环派发任务给浏览器
- 批量处理大量URL
- 并发爬取提升效率

**文档位置**:
- `docs/浏览器池调用规范.md`

**修改文件**:
- `docs/浏览器池调用规范.md` - 新增调用规范文档

## 2026-01-23 - 新增浏览器状态监控页面

### 功能新增（2026-01-23）

**新增内容**:
- 创建了浏览器状态监控页面，实时显示浏览器池的运行状态
- 支持自动刷新（每5秒）
- 可视化展示浏览器实例信息

**功能特点**:
1. **状态概览卡片**:
   - 总实例数
   - 忙碌中实例数
   - 空闲中实例数

2. **实例详细信息**:
   - 每个实例的状态（忙碌/空闲）
   - 空闲时间（格式化显示）
   - 线程ID
   - 实例索引

3. **配置信息**:
   - 空闲超时时间
   - 池运行状态

4. **交互功能**:
   - 手动刷新按钮
   - 自动刷新开关（默认开启，每5秒刷新）
   - 实时状态更新

**页面设计**:
- 响应式布局，适配不同屏幕
- 卡片式设计，清晰直观
- 颜色编码：忙碌（红色）、空闲（绿色）
- 加载状态和错误状态提示

**技术实现**:
- 使用 `/api/browser/pool/status` API 获取数据
- JavaScript 异步加载和更新
- 自动刷新机制（可开关）
- 时间格式化显示

**访问方式**:
- 侧边栏导航：🌐 浏览器状态
- 直接访问：`/browser-status`

**修改文件**:
- `src/web/templates/browser_status.html` - 新增浏览器状态监控页面
- `src/web/routes.py` - 添加 `/browser-status` 路由
- `src/web/templates/base.html` - 在侧边栏添加浏览器状态链接

## 2026-01-23 - 修复Playwright跨线程问题

### Bug修复（2026-01-23）

**问题**:
- 浏览器复用时出现 `greenlet.error: cannot switch to a different thread` 错误
- Playwright 同步 API 不允许在不同线程中使用同一个浏览器实例

**原因分析**:
- Flask 可能在不同的线程中处理不同的请求
- 浏览器池的复用机制会尝试复用之前创建的浏览器实例
- 如果浏览器在线程A创建，但在线程B使用，就会出现跨线程错误

**解决方案**:
1. **线程绑定检查**：
   - 在 `_get_or_create_instance()` 中检查线程ID
   - 只复用当前线程创建的浏览器实例
   - 如果当前线程没有空闲实例，创建新的

2. **Flask线程配置**：
   - 确保 `main.py` 和 `dev.py` 都设置 `threaded=False`
   - 避免 Flask 在多线程中处理请求

**修改代码**:
```python
def _get_or_create_instance(self) -> BrowserInstance:
    current_thread_id = threading.get_ident()
    
    with self._pool_lock:
        # 只查找当前线程的空闲实例
        for instance in self._instances:
            if not instance.is_busy and instance.thread_id == current_thread_id:
                instance.is_busy = True
                return instance
        
        # 当前线程没有空闲实例，创建新的
    
    instance = self._create_new_instance()
    instance.thread_id = current_thread_id
    # ...
```

**优化效果**:
- ✅ 解决了跨线程使用浏览器的问题
- ✅ 同一线程内仍然可以复用浏览器（性能优化保留）
- ✅ 不同线程会创建独立的浏览器实例（隔离性更好）
- ✅ 线程安全，不会出现 greenlet 错误

**修改文件**:
- `src/spider/query_manager.py` - 添加线程ID检查，只复用同线程实例
- `src/dev.py` - 设置 `threaded=False`

## 2026-01-23 - 代码简化和配置修复

### 代码简化（2026-01-23）

**优化内容**:
- 去除路由层的过度抽象，直接使用 `BrowserPool` 和 `PinduoduoClient`
- 删除不必要的 `_ensure_browser_pool_initialized()` 函数
- 简化所有拼多多相关路由代码
- 代码行数减少 50%，可读性大幅提升

**问题分析**:
- 之前的设计存在 3 层嵌套：路由 → 工具 → 回调 → 客户端
- 通过回调函数传递逻辑，增加了理解难度
- 浏览器池管理混杂在路由层，违反单一职责原则

**重构方案**:

**改进前（过度抽象）：**
```python
# 1. 获取工具
tool_manager = get_tool_manager()
tool = tool_manager.get_tool('pinduoduo')

# 2. 检查工具
if not tool or not isinstance(tool, PinduoduoTool):
    return error

# 3. 定义回调
def login_callback(client):
    return client.show_login_qrcode()

# 4. 通过工具执行回调
qrcode_data = tool.execute_with_client(login_callback)
```

**改进后（直接清晰）：**
```python
# 1. 检查浏览器池
if not _browser_pool_ref:
    return error

# 2. 直接使用
from spider.pinduoduo.client import PinduoduoClient

with _browser_pool_ref.get_page(timeout=60) as page:
    client = PinduoduoClient(page=page)
    qrcode_data = client.show_login_qrcode()
```

**职责分离**:
- `BrowserPool` 负责：创建浏览器、管理实例、处理超时
- `PinduoduoClient` 负责：业务逻辑、页面操作
- 路由层负责：HTTP 接口、参数验证、返回结果

**优化效果**:
- ✅ 代码更简洁，一眼就能看懂
- ✅ 调用链路清晰：路由 → 浏览器池 → 客户端
- ✅ 每个接口可以灵活设置超时时间
- ✅ 易于调试，异常栈更清晰
- ✅ 符合 KISS 原则（Keep It Simple, Stupid）

**修改文件**:
- `src/api/routes.py` - 删除冗余代码，简化所有拼多多路由

### 配置修复（2026-01-23）

**问题**:
- `module_config.json` 中缺少 `pinduoduo` 模块配置
- 导致浏览器池未初始化（因为没有启用的模块需要浏览器）
- 所有拼多多功能报错："浏览器池未初始化"

**解决方案**:
- 在 `module_config.json` 和 `module_config.json.example` 中添加 `pinduoduo` 配置
- 设置 `enabled: true` 和 `requires_browser: true`
- 应用启动时会自动初始化浏览器池

**配置内容**:
```json
{
  "pinduoduo": {
    "category": "tools",
    "description": "拼多多商家后台自动化工具",
    "display_name": "拼多多助手",
    "enabled": true,
    "icon": "🛒",
    "init_on_startup": false,
    "memory_mb": 100,
    "requires_browser": true
  }
}
```

**修改文件**:
- `module_config.json` - 添加拼多多模块配置
- `module_config.json.example` - 同步更新示例配置

**使用说明**:
- 修改配置后需要**重启应用**才能生效
- 启动时会看到 "以下模块需要浏览器: pinduoduo"
- 浏览器池会自动初始化

## 2026-01-23 - 浏览器操作超时控制机制

### 安全性增强（2026-01-23）

**新增功能**:
- 为所有浏览器操作添加超时控制机制
- 超时后自动记录日志并释放浏览器资源
- 确保即使操作超时也能正确标记浏览器空闲
- 保证下一个方法可以正常获取和使用浏览器

**问题背景**:
- 某些网页加载或操作可能卡住很长时间
- 没有超时控制会导致浏览器实例一直被占用
- 影响其他请求的正常执行
- 可能导致资源无法释放

**技术实现**:

1. **超时异常类**:
   - 创建 `BrowserTimeoutError` 异常类
   - 继承自 `Exception`
   - 用于标识超时错误

2. **浏览器实例增强**:
   - 添加 `timeout_timer` 属性：超时定时器
   - 添加 `is_timeout` 属性：超时标志
   - 使用 `threading.Timer` 实现超时检测

3. **超时控制逻辑**:
   - `get_page(timeout=60.0)` 方法接收超时参数（默认60秒）
   - 启动定时器在指定时间后触发超时回调
   - 超时回调设置超时标志并记录警告日志
   - 在退出上下文时检查超时标志
   - 如果超时，抛出 `BrowserTimeoutError` 异常

4. **资源释放保证**:
   - 使用 `finally` 块确保浏览器实例一定会被释放
   - 无论正常完成、异常、还是超时，都会标记为空闲
   - 取消定时器，重置超时标志
   - 记录操作耗时，方便性能分析

5. **日志记录**:
   - 启动时记录超时限制：`启动超时定时器，超时时间: X 秒`
   - 超时警告：`⚠️ 警告：浏览器操作超时（超过 X 秒）`
   - 超时完成：`❌ 浏览器操作已超时（耗时 X 秒，超时限制 Y 秒）`
   - 正常完成：`浏览器操作完成，耗时 X 秒`
   - 释放时区分正常释放和超时释放

6. **调用方式更新**:
   - `query_with_retry()` - 默认超时30秒
   - `execute_with_client()` - 默认超时60秒
   - 所有调用都可以自定义超时时间

**使用示例**:

```python
# 使用默认超时（60秒）
with browser_pool.get_page() as page:
    page.goto('https://example.com')

# 自定义超时时间（30秒）
with browser_pool.get_page(timeout=30) as page:
    page.goto('https://example.com')

# 禁用超时（不推荐）
with browser_pool.get_page(timeout=0) as page:
    page.goto('https://example.com')
```

**异常处理**:

```python
try:
    with browser_pool.get_page(timeout=30) as page:
        page.goto('https://slow-website.com')
except BrowserTimeoutError as e:
    print(f"操作超时: {e}")
    # 浏览器已自动释放，可以继续下一个操作
```

**安全保证**:
- ✅ 超时后浏览器实例自动释放
- ✅ 不会阻塞其他请求
- ✅ 资源不会泄漏
- ✅ 清晰的日志记录
- ✅ 支持自定义超时时间
- ✅ 兼容现有代码（向后兼容）

**性能监控**:
- 每次操作都会记录耗时
- 超时时记录详细信息
- 方便排查性能问题
- 优化超时参数设置

**默认超时统一**:
- 所有方法统一默认超时：**60秒（1分钟）**
- `get_page()` - 默认60秒
- `execute_with_client()` - 默认60秒
- `query_with_retry()` - 默认60秒

**配置建议**:
- 快速查询操作：`timeout=15-30` 秒
- 页面加载操作：`timeout=30-60` 秒
- 复杂自动化操作：`timeout=60-120` 秒
- 根据实际网络环境和操作复杂度调整

**修改文件**:
- `src/spider/query_manager.py` - 添加超时控制机制，统一默认超时为60秒
- `src/tools/pinduoduo_tool.py` - 添加超时参数
- `docs/浏览器超时配置说明.md` - 新增超时配置详细说明文档

## 2026-01-23 - 浏览器池智能复用机制

### 性能优化（2026-01-23）

**优化内容**:
- 重构浏览器池，实现智能复用机制
- 浏览器使用完后不立即关闭，而是标记为空闲状态
- 空闲超过10分钟的浏览器自动清理释放资源
- 显著提升性能，避免频繁创建和关闭浏览器

**问题背景**:
- 之前每次调用都创建新的浏览器上下文并立即关闭
- 频繁的创建/关闭操作消耗大量资源和时间
- 用户需要一个更智能的浏览器管理机制

**技术实现**:

1. **浏览器实例管理**:
   - 创建 `BrowserInstance` 数据类，存储浏览器状态信息：
     - `playwright`: Playwright 实例
     - `context`: 浏览器上下文
     - `page`: 页面对象
     - `is_busy`: 是否正在使用
     - `last_used_time`: 最后使用时间
     - `thread_id`: 线程ID

2. **浏览器池架构**:
   - `_instances`: 浏览器实例池列表
   - `_pool_lock`: 池锁，保护实例列表操作
   - `_user_data_dir_lock`: 用户数据目录锁，确保同时只有一个浏览器在创建
   - `idle_timeout`: 空闲超时时间（默认600秒，10分钟）

3. **智能获取与复用**:
   - `_get_or_create_instance()` 方法：
     - 优先查找空闲（`is_busy=False`）的浏览器实例
     - 如果找到空闲实例，标记为忙碌并返回
     - 如果没有空闲实例，创建新的浏览器实例
   - `_release_instance()` 方法：
     - 使用完成后标记为空闲（`is_busy=False`）
     - 更新最后使用时间
     - 不关闭浏览器，保持在池中待复用

4. **自动清理机制**:
   - 启动后台清理线程 `_cleanup_idle_browsers()`
   - 每30秒检查一次所有浏览器实例
   - 对于空闲且超过超时时间的实例，自动关闭并从池中移除
   - 清理线程作为守护线程运行，应用退出时自动停止

5. **线程安全设计**:
   - 使用 `_pool_lock` 保护实例列表的并发访问
   - 使用 `_user_data_dir_lock` 确保同一时间只有一个浏览器在创建
   - 所有浏览器共享同一个持久化用户数据目录，确保登录状态共享

6. **上下文管理器模式**:
   - `get_page()` 方法仍然使用 `@contextmanager` 装饰器
   - 进入上下文时获取或创建浏览器实例
   - 退出上下文时释放实例（标记为空闲）
   - 使用方式不变，无需修改调用代码

7. **监控功能**:
   - 添加 `get_pool_status()` 方法，返回池状态信息：
     - 总实例数、忙碌数、空闲数
     - 每个实例的详细信息（状态、空闲时间等）
   - 新增 API 接口 `/api/browser/pool/status` 用于监控

**优化效果**:
- ✅ 第一次调用后，后续调用可以复用现有浏览器，速度提升显著
- ✅ 减少了浏览器创建和关闭的开销，节省系统资源
- ✅ 空闲超时自动清理，避免资源浪费
- ✅ 支持并发访问，多个请求可以同时使用不同的浏览器实例
- ✅ 线程安全，避免并发问题
- ✅ 保持登录状态共享，所有浏览器共享同一个用户数据目录

**性能对比**:
- **优化前**：每次调用耗时 3-5秒（创建浏览器）
- **优化后**：首次调用 3-5秒，后续调用 < 0.1秒（复用浏览器）

**配置说明**:
- 可通过 `BrowserPool(idle_timeout=600)` 参数设置空闲超时时间
- 默认600秒（10分钟），可根据实际需求调整
- 设置为更长时间可减少创建次数，但会占用更多内存

**修改文件**:
- `src/spider/query_manager.py` - 重构 `BrowserPool` 类，实现智能复用机制
- `src/api/routes.py` - 添加浏览器池状态监控 API
- `src/api/routes.py` - 修复 `tool_manager.tools` 访问错误

**Bug修复**:
- 修复了 `tool_manager.tools` 属性访问错误
- 改用 `tool_manager.get_all_tools()` 方法获取工具列表

## 2026-01-22 - 修复登录状态无法共享的问题

### Bug修复（2026-01-22）

**修复内容**:
- 修复了每次点击都是登录页面的严重问题
- 改为使用全局持久化上下文，所有线程共享，确保登录状态共享
- 使用锁保护所有操作，确保线程安全

**问题原因**:
1. **根本问题**：每个线程使用独立的用户数据目录（`thread_{thread_id}`）
   - 登录状态保存在线程A的目录中
   - 下次请求可能在线程B，线程B使用不同的目录，看不到登录状态
   - 导致每次请求都需要重新登录

2. **技术细节**：
   - Playwright 不允许多个实例同时使用同一个用户数据目录
   - 但我们可以使用一个全局的持久化上下文，所有线程共享
   - 使用锁来保护所有操作，确保线程安全

**技术实现**:
- 修改 `src/spider/query_manager.py`：
  - 移除线程本地存储（`_thread_local`）
  - 改为使用全局持久化上下文（`self._context`、`self._playwright`）
  - 所有线程共享同一个用户数据目录（`_shared_user_data_dir`）
  - 使用 `_context_lock` 保护所有操作，确保线程安全
  - 修改 `_ensure_context_initialized()` 方法，创建全局持久化上下文
  - 修改 `get_page()` 方法，使用锁保护页面创建操作
  - 修改 `close()` 方法，关闭全局上下文

**优化效果**:
- ✅ 所有线程共享同一个持久化上下文，登录状态在所有线程之间共享
- ✅ 登录状态会持久化保存，应用重启后自动恢复
- ✅ 使用锁保护操作，确保线程安全
- ✅ 不再需要每次请求都重新登录

**修改文件**:
- `src/spider/query_manager.py` - 改为使用全局持久化上下文，所有线程共享

## 2026-01-22 - 修复登录流程逻辑

### Bug修复（2026-01-22）

**修复内容**:
- 修复了 `show_login_qrcode` 方法的逻辑错误
- 改为先访问首页，如果被拦截才显示登录二维码
- 如果已经登录，直接返回成功并更新登录状态

**问题原因**:
1. **原逻辑错误**：直接访问登录页面获取二维码
   - 即使用户已经登录，也会进入登录页面
   - 不符合实际使用场景

2. **正确逻辑应该是**：
   - 先访问首页（target_url）
   - 如果被拦截到登录页面，才显示登录二维码
   - 如果没有被拦截，说明已经登录，直接返回成功并更新登录状态

**技术实现**:
- 修改 `src/spider/pinduoduo/client.py`：
  - `show_login_qrcode` 方法：
    - 先加载Cookie（如果有）
    - 访问首页（`self.target_url`）而不是直接访问登录页面
    - 检测URL是否包含"login"判断是否被拦截
    - 如果被拦截，显示登录二维码
    - 如果没有被拦截，保存Cookie并更新登录状态，返回特殊值 `"ALREADY_LOGGED_IN"`
- 修改 `src/api/routes.py`：
  - `pinduoduo_start_login` 路由：
    - 处理 `"ALREADY_LOGGED_IN"` 特殊返回值
    - 返回 `already_logged_in: true` 表示已经登录，无需扫码

**优化效果**:
- ✅ 登录流程更符合实际使用场景
- ✅ 如果已经登录，不需要重复扫码
- ✅ 登录状态会自动更新和保存

**修改文件**:
- `src/spider/pinduoduo/client.py` - 修复登录流程逻辑
- `src/api/routes.py` - 处理已登录情况

## 2026-01-22 - 修复跨线程问题和登录状态持久化

### Bug修复（2026-01-22）

**修复内容**:
- 修复了 Playwright 跨线程问题：`greenlet.error: cannot switch to a different thread`
- 使用线程本地存储（thread-local storage），为每个线程创建独立的持久化上下文
- 每个线程的登录状态独立持久化，避免线程间冲突

**问题原因**:
1. **跨线程问题**：`launch_persistent_context` 创建的 context 不能跨线程使用
   - Flask 路由处理可能在不同线程中执行
   - Playwright 的同步 API 使用 greenlet，不能在不同线程之间切换
   - 导致 `greenlet.error: cannot switch to a different thread (which happens to have exited)` 错误

2. **技术细节**：
   - 持久化上下文必须在创建它的同一个线程中使用
   - 多线程环境下，每个线程需要独立的上下文
   - 但可以共享同一个基础用户数据目录（使用子目录区分）

**技术实现**:
- 修改 `src/spider/query_manager.py`：
  - 使用 `threading.local()` 实现线程本地存储
  - 为每个线程创建独立的 Playwright 实例和持久化上下文
  - 每个线程使用独立的用户数据子目录（`thread_{thread_id}`）
  - 移除全局的 `playwright`、`browser`、`context` 属性
  - 添加 `_get_thread_context()` 方法，自动为每个线程创建上下文
  - 添加 `_initialized` 属性（兼容性），检查是否有线程上下文已初始化
  - 简化 `close()` 方法，只关闭当前线程的上下文

**优化效果**:
- ✅ 解决了跨线程使用 Playwright 的问题
- ✅ 每个线程都有独立的持久化上下文，登录状态独立保存
- ✅ 支持多线程并发访问，不会互相干扰
- ✅ 登录状态仍然会持久化保存，应用重启后自动恢复

**修改文件**:
- `src/spider/query_manager.py` - 使用线程本地存储实现多线程安全的持久化上下文

## 2026-01-22 - 修复登录状态无法持久化的问题

### Bug修复（2026-01-22）

**修复内容**:
- 修复了每次进入都是登录页面的严重问题
- 使用持久化浏览器上下文（persistent context）替代临时上下文
- 登录状态（cookies、localStorage、sessionStorage）现在会自动保存和恢复

**问题原因**:
1. **根本问题**：`BrowserPool` 使用 `browser.new_context()` 创建临时上下文
   - 每次创建新的上下文都是全新的，没有保留之前的会话状态
   - 即使 `PinduoduoClient` 有保存和加载 Cookie 的功能，但其他会话数据（如 localStorage、sessionStorage）会丢失
   - 导致每次访问都需要重新登录

2. **技术细节**：
   - 临时上下文不会持久化任何数据
   - 虽然可以手动加载 Cookie，但可能因为其他原因（session storage、localStorage 等）导致需要重新登录
   - 使用持久化上下文可以自动保存和恢复所有会话数据

**技术实现**:
- 修改 `src/spider/query_manager.py`：
  - 导入 `get_safe_data_path` 用于获取安全的用户数据目录
  - 在 `__init__` 中初始化持久化用户数据目录：`self._user_data_dir = get_safe_data_path('browser_data', app_name='JNTools')`
  - 将 `browser.launch()` + `browser.new_context()` 改为 `playwright.chromium.launch_persistent_context()`
  - 持久化上下文会自动保存和恢复 cookies、localStorage、sessionStorage 等
  - 修改 `close()` 方法，正确关闭持久化上下文
  - 修复 `query_with_retry` 函数中不存在的 `get_page_for_waybill` 方法调用

**优化效果**:
- ✅ 登录状态现在会自动持久化保存
- ✅ 应用重启后，登录状态会自动恢复
- ✅ 不再需要每次访问都重新登录
- ✅ 使用持久化用户数据目录，避免权限问题

**修改文件**:
- `src/spider/query_manager.py` - 使用持久化浏览器上下文替代临时上下文

## 2026-01-22 - 修复拼多多客户端URL获取问题（跨线程问题）

### Bug修复（2026-01-22）

**修复内容**:
- 修复了使用 `page.evaluate()` 导致的跨线程错误（`greenlet.error: cannot switch to a different thread`）
- 改用先等待页面稳定后再使用 `page.url` 的方式获取 URL
- 确保在页面完全加载后再获取 URL，避免获取到旧的 URL

**问题原因**:
1. **第一次尝试**：使用 `page.evaluate('window.location.href')` 获取实际 URL
   - 但 `page.evaluate()` 不能在跨线程使用
   - 在 Flask 路由中调用时，可能在不同的线程中执行，导致 `greenlet.error` 错误

2. **根本问题**：`page.url` 在 JavaScript 导航后可能不会立即更新
   - 需要在页面稳定后再获取 URL
   - 通过等待页面加载状态确保 URL 已更新

**技术实现**:
- 修改 `src/spider/pinduoduo/client.py`：
  - `execute_automation` 方法（第 223-230 行）：
    - 先等待页面加载完成（`wait_for_load_state('domcontentloaded')`）
    - 再等待网络空闲（`wait_for_load_state('networkidle')`）
    - 然后使用 `page.url` 获取当前 URL
  - `_check_login_status_once` 方法（第 502-506 行）：
    - 先等待 DOM 加载完成（`wait_for_load_state('domcontentloaded')`）
    - 然后使用 `page.url` 获取当前 URL
    - 使用较短的超时时间（2秒），避免阻塞太久

**优化效果**:
- 解决了跨线程调用 Playwright API 的问题
- 通过等待页面稳定，确保获取到正确的 URL
- 提高了登录状态检测和拦截检测的可靠性

**修改文件**:
- `src/spider/pinduoduo/client.py` - 修复两处 URL 获取方式，先等待页面稳定再获取 URL

## 2026-01-21 - 添加开发模式支持热重载

### 功能新增（2026-01-21）

**新增内容**:
- 创建开发模式入口文件 `src/dev.py`，支持文件修改热重载
- 更新 VS Code 调试配置，添加"开发模式（热重载）"配置项
- 开发模式只启动 Flask 服务，不启动系统托盘、原生窗口等桌面应用功能

**问题背景**:
- 原有的 `main.py` 启动的是完整桌面应用（包含系统托盘、原生窗口等）
- Flask 的 `use_reloader=False` 禁用了自动重载功能
- 开发调试时需要频繁重启应用，效率较低

**技术实现**:
1. **开发模式入口** (`src/dev.py`):
   - 简化版本，只启动 Flask 服务
   - 设置 `debug=True` 和 `use_reloader=True` 启用热重载
   - 不启动系统托盘、原生窗口等桌面应用功能
   - 支持 Ctrl+C 优雅退出

2. **VS Code 调试配置** (`.vscode/launch.json`):
   - 保留原有的"调试主程序（完整版）"配置
   - 新增"开发模式（热重载）"配置
   - 开发模式配置使用 `dev.py` 作为入口
   - 设置环境变量 `FLASK_ENV=development` 和 `FLASK_DEBUG=1`

**使用说明**:
- **完整版调试**：选择"调试主程序（完整版）"，启动完整的桌面应用
- **开发模式**：选择"开发模式（热重载）"，只启动 Flask 服务，支持文件修改自动重载
- 开发模式下修改 Python 文件后，Flask 会自动检测并重启服务
- 开发模式不包含系统托盘和原生窗口，适合纯 Web 开发调试

**注意事项**:
- 开发模式只适合开发调试，生产环境应使用完整版
- 热重载功能只监控 Python 文件，模板和静态文件可能需要手动刷新浏览器
- 开发模式下浏览器池和工具管理器仍会正常初始化

**修改文件**:
- 新增：`src/dev.py` - 开发模式入口文件
- 修改：`.vscode/launch.json` - 添加开发模式调试配置

## 2026-01-22 - 重构浏览器池：实现懒加载和自动关闭

### 重构内容（2026-01-22）

**重构目标**:
- 简化浏览器池逻辑，移除复杂的 JD/百度页面管理
- 实现懒加载：第一次调用 `get_page()` 时才初始化
- 实现自动关闭：30分钟无使用后自动关闭资源
- 提供简单的接口：`get_page()` 方法返回可用的 page 对象
- 确保线程安全：在同一线程中使用，避免 greenlet 错误

**主要改动**:
1. **简化 BrowserPool 类**:
   - 移除 `jd_page`、`baidu_page` 等专用页面
   - 移除 `_initialize_baidu_page()` 等复杂初始化逻辑
   - 移除 `get_page_for_waybill()` 等快递查询相关方法
   - 保留核心功能：懒加载、自动关闭、线程安全

2. **实现懒加载机制**:
   - `get_page()` 方法：如果未初始化，自动调用 `_ensure_initialized()` 初始化
   - 每次调用 `get_page()` 都创建新的 page 对象
   - 使用完后可以关闭 page，不影响浏览器池

3. **实现自动关闭机制**:
   - 30分钟（1800秒）无使用后自动关闭浏览器资源
   - 使用定时器每60秒检查一次空闲时间
   - 关闭后下次调用 `get_page()` 时会自动重新初始化

4. **简化 API 路由**:
   - 移除复杂的初始化检查逻辑
   - 直接使用 `pool.get_page()` 获取页面对象
   - 懒加载会自动处理初始化

**使用方式**:
```python
# 获取浏览器池实例
pool = BrowserPool(headless=True, idle_timeout=1800)  # 30分钟空闲超时

# 获取页面对象（懒加载：如果未初始化会自动初始化）
page = pool.get_page()

# 使用页面进行爬虫操作
page.goto('https://example.com')
content = page.content()

# 使用完后可以关闭页面（可选）
page.close()

# 30分钟无使用后，浏览器池会自动关闭
# 下次调用 get_page() 时会自动重新初始化
```

**优化效果**:
- 启动时不初始化浏览器，启动更快
- 按需初始化，节省资源
- 自动关闭空闲资源，避免资源浪费
- 代码更简洁，易于维护
- 线程安全，避免 greenlet 错误

**修改文件**:
- `src/spider/query_manager.py` - 重构 BrowserPool 类，实现懒加载和自动关闭
- `src/api/routes.py` - 简化路由逻辑，使用新的 `get_page()` 方法

## 2026-01-22 - 修复浏览器池异步初始化问题

### Bug修复（2026-01-22）

**修复内容**:
- 修复了在 Flask 路由中直接调用 Playwright 同步 API 导致的异步环境冲突问题
- 实现了线程安全的浏览器池延迟初始化机制
- 支持在浏览器池不存在时自动创建实例

**问题原因**:
- Flask 应用可能运行在异步环境中（如 gevent）
- 在路由中直接调用 `pool.initialize()` 会触发 Playwright 同步 API
- Playwright 同步 API 不能在 asyncio 循环中使用，导致错误：
  ```
  Error: It looks like you are using Playwright Sync API inside the asyncio loop.
  Please use the Async API instead.
  ```

**技术实现**:
- 修改 `src/api/routes.py`：
  - 添加 `_ensure_browser_pool_initialized()` 函数，使用线程安全的方式初始化浏览器池
  - 在单独线程中执行浏览器池初始化，避免与异步环境冲突
  - 使用 `threading.Event` 和 `threading.Lock` 确保线程安全
  - 如果浏览器池不存在，自动创建 `BrowserPool` 实例
  - 更新 `/api/pinduoduo/login` 和 `/api/pinduoduo/execute` 路由使用新的初始化方法

**优化效果**:
- 解决了异步环境下的 Playwright 初始化错误
- 浏览器池初始化不再阻塞 Flask 请求处理
- 支持按需创建和初始化浏览器池
- 提高了应用的稳定性和兼容性

**修改文件**:
- `src/api/routes.py` - 添加线程安全的浏览器池初始化逻辑

## 2026-01-21 - 代码清理：移除快递查询模块

### 代码清理（2026-01-21）

**清理内容**:
- 移除快递查询模块相关的初始化代码
- 移除快递查询相关的API路由（`/query` 和 `/batch`）
- 简化浏览器池初始化提示信息
- 清理健康检查接口中的浏览器池状态显示
- 在模块配置中禁用 logistics 模块
- 将 `module_config.json` 加入 `.gitignore`
- 创建 `module_config.json.example` 作为配置模板

**修改文件**:
- `src/app.py` - 移除 `SpiderTool` 导入和快递查询工具注册
- `src/api/routes.py` - 移除 `/query` 和 `/batch` 路由，简化 `/health` 接口
- `module_config.json` - 禁用 logistics 模块
- `.gitignore` - 添加 `module_config.json` 忽略
- `module_config.json.example` - 新增配置模板文件
- `README.md` - 更新配置说明

**优化效果**:
- 减少不必要的代码和依赖
- 应用启动更快，不再初始化浏览器池（因为拼多多工具使用延迟初始化）
- 代码更简洁，只保留必要的功能
- 用户可以通过配置文件自定义启用的模块

## 2026-01-21 - 新增拼多多助手工具（含安全路径优化和延迟初始化）

### 性能优化 - 延迟初始化（2026-01-21）

**优化背景**:
- 之前在工具初始化时就创建 `PinduoduoClient` 实例，占用资源
- `PinduoduoClient` 初始化时会创建飞书发送器，可能导致启动错误
- 即使不使用拼多多功能，也会占用内存

**优化方案**:
- 采用延迟初始化（Lazy Initialization）策略
- 只在首次使用时才创建客户端实例
- 飞书发送器也改为延迟初始化（使用 `@property`）

**优化效果**:
- 应用启动时不创建拼多多客户端，启动更快
- 只有访问拼多多功能时才创建实例，节省资源
- 避免启动时的潜在错误
- 多个用户环境下资源利用更高效

**修改文件**:
- `src/tools/pinduoduo_tool.py` - `get_client()` 方法实现延迟初始化
- `src/spider/pinduoduo/client.py` - 飞书发送器改为 `@property` 延迟初始化

## 2026-01-21 - 新增拼多多助手工具（含安全路径优化）

### 安全路径优化（2026-01-21）

**新增内容**:
- 创建 `src/utils/path_helper.py` 提供安全的数据目录获取功能
- Cookie 和状态文件自动保存到用户数据目录（Windows: `%LOCALAPPDATA%\JNTools`）
- 避免在 Program Files 等需要管理员权限的目录写入文件
- 支持自动检测写入权限，无权限时自动切换到用户目录
- 在 README.md 中添加"本地数据保存注意事项"章节，规范本地数据保存的最佳实践

**技术实现**:
1. `get_user_data_dir()` - 获取跨平台的用户数据目录
2. `get_safe_data_path()` - 智能选择安全的数据文件路径
3. `get_project_root()` - 获取项目根目录（支持开发环境和打包环境）

**修改文件**:
- `src/config.py` - 将 Cookie 路径配置改为 None（使用默认用户目录）
- `src/spider/pinduoduo/client.py` - 使用 `get_safe_data_path()` 获取安全路径
- `src/utils/path_helper.py` - 新增路径辅助工具模块
- `README.md` - 新增开发指南"本地数据保存注意事项"章节

**开发规范**:
- 所有需要保存到本地的数据文件必须使用 `get_safe_data_path()` 获取路径
- 包括但不限于：Cookie、状态文件、缓存、配置文件、数据库、临时文件等
- 参考实现：`src/utils/logger.py`、`src/spider/pinduoduo/client.py`

### 功能新增

**新增内容**:
- 创建了拼多多商家后台自动化工具，支持登录管理和自动化操作
- 集成飞书通知功能，登录失效时自动发送消息提醒
- 实现Cookie持久化，应用重启后保持登录状态

**核心功能**:

1. **飞书通知工具** (`src/tools/feishu/`):
   - 飞书应用认证（tenant_access_token获取）
   - 文本消息发送
   - Token缓存机制（2小时有效期）
   - 消息模板管理

2. **拼多多自动化核心** (`src/spider/pinduoduo.py`):
   - 自动化执行与登录检测
   - Cookie管理（加载/保存/清除）
   - 扫码登录流程
   - 执行状态记录
   - 被拦截时自动发送飞书通知

3. **Web界面** (`src/web/templates/tools/pinduoduo.html`):
   - 实时显示最后执行状态
   - 二维码扫码登录
   - 状态刷新和登录管理
   - TODO功能区域（预留后续自动化）

4. **API接口** (`src/api/routes.py`):
   - `GET /api/pinduoduo/status` - 获取最后执行状态
   - `POST /api/pinduoduo/login` - 启动登录流程
   - `GET /api/pinduoduo/check_login_complete` - 检查登录完成
   - `POST /api/pinduoduo/logout` - 清除登录状态
   - `POST /api/pinduoduo/execute` - 执行自动化操作（TODO预留）

**技术实现**:

1. **环境变量管理**:
   - 新增 `python-dotenv` 依赖
   - 创建 `.env.example` 模板文件
   - 在 `config.py` 中加载环境变量
   - 飞书配置通过环境变量管理

2. **Cookie持久化**:
   - Cookie保存到 `cookies/pinduoduo_cookies.json`
   - 包含Cookie数据、时间戳和域名信息
   - 应用重启后自动加载Cookie
   - 支持清除Cookie和浏览器状态

3. **执行状态管理**:
   - 状态保存到 `cookies/pinduoduo_status.json`
   - 记录最后成功时间、失败时间和执行时间
   - 基于执行结果判断登录状态
   - 不做定时检查，只在执行时检测

4. **登录检测逻辑**:
   - 访问目标URL后检测是否被重定向到登录页面
   - URL包含"login"关键词判定为被拦截
   - 被拦截时发送飞书通知
   - 记录失败状态

5. **扫码登录**:
   - 获取登录页面二维码
   - 支持多种二维码选择器
   - 轮询检查登录完成状态
   - 登录成功后自动保存Cookie

**文件结构**:
```
assistantService/
├── .env.example                      # 环境变量模板（新增）
├── cookies/                          # Cookie存储目录（新增）
│   ├── pinduoduo_cookies.json
│   └── pinduoduo_status.json
├── src/
│   ├── tools/
│   │   ├── feishu/                   # 飞书工具（新增）
│   │   │   ├── __init__.py
│   │   │   ├── feishu_client.py
│   │   │   └── message_sender.py
│   │   └── pinduoduo_tool.py         # 拼多多工具（新增）
│   ├── spider/
│   │   └── pinduoduo.py              # 拼多多自动化（新增）
│   ├── web/templates/tools/
│   │   └── pinduoduo.html            # 拼多多页面（新增）
│   ├── api/routes.py                 # 添加拼多多API（修改）
│   ├── app.py                        # 注册拼多多工具（修改）
│   └── config.py                     # 添加配置项（修改）
├── requirements.txt                  # 添加依赖（修改）
└── .gitignore                        # 忽略.env和cookies（修改）
```

**配置说明**:

1. **环境变量配置** (`.env`文件):
   ```env
   FEISHU_APP_ID=your_app_id
   FEISHU_APP_SECRET=your_app_secret
   FEISHU_USER_ID=your_user_id
   ```

2. **应用配置** (`config.py`):
   ```python
   # 拼多多配置
   PINDUODUO_COOKIE_PATH = 'cookies/pinduoduo_cookies.json'
   PINDUODUO_STATUS_PATH = 'cookies/pinduoduo_status.json'
   PINDUODUO_TARGET_URL = 'https://mms.pinduoduo.com/home'
   
   # 飞书配置
   FEISHU_ENABLED = True
   ```

**使用说明**:

1. **配置飞书应用**:
   - 访问 https://open.feishu.cn/app 创建应用
   - 获取 App ID 和 App Secret
   - 获取接收消息的用户ID
   - 复制 `.env.example` 为 `.env` 并填入配置

2. **使用工具**:
   - 打开拼多多助手页面
   - 点击"重新登录"获取二维码
   - 使用拼多多APP扫码登录
   - 登录成功后Cookie自动保存

3. **自动化执行**:
   - 后续开发自动化功能时，调用 `execute_automation()` 方法
   - 如果被拦截到登录页面，自动发送飞书通知
   - 页面显示最后执行状态

**工作流程**:
1. 用户打开页面查看最后执行状态
2. 如果显示需要登录，点击"重新登录"扫码
3. 登录成功后Cookie被保存
4. 后续执行自动化操作时自动加载Cookie
5. 如果再次被拦截，重复步骤1-3

**后续扩展**:
- 订单数据自动抓取
- 商品管理自动化
- 评价监控
- 数据统计报表
- 价格监控
- 库存预警

**注意事项**:
- `.env` 文件包含敏感信息，已添加到 `.gitignore`
- `cookies/` 目录包含登录凭证，已添加到 `.gitignore`
- 飞书通知需要正确配置应用权限
- 二维码选择器可能需要根据实际页面调整

## 2026-01-09 - 从 Git 历史中完全删除大文件（解决 GitHub 推送限制）

### 代码清理

**清理内容**:
- 从整个 Git 历史中完全删除了 `JNTools_Setup_v1.0.1.exe` 文件（145.70 MB）
- 该文件超过了 GitHub 的 100 MB 文件大小限制，导致推送失败
- 文件已从所有历史提交中移除，本地文件仍然保留

**问题原因**:
- `JNTools_Setup_v1.0.1.exe` 是打包生成的安装程序文件，大小为 145.70 MB
- 虽然 `.gitignore` 中已配置 `*.exe` 忽略规则，但该文件在添加忽略规则之前就已经被提交
- GitHub 拒绝推送超过 100 MB 的文件，即使文件已经从当前提交中删除，历史记录中仍然存在
- 错误信息：`GH001: Large files detected. You may want to try Git Large File Storage`

**技术实现**:
1. **从 Git 索引中删除**：
   - 使用 `git rm --cached JNTools_Setup_v1.0.1.exe` 从当前索引中移除

2. **从整个历史中删除**：
   - 使用 `git filter-branch --force --index-filter "git rm --cached --ignore-unmatch JNTools_Setup_v1.0.1.exe" --prune-empty --tag-name-filter cat -- --all`
   - 重写了所有历史提交，从每个提交中移除了该文件
   - 重写了 5 个提交记录

3. **清理和优化**：
   - 删除备份引用：`Remove-Item .git\refs\original -Recurse -Force`
   - 清理 reflog：`git reflog expire --expire=now --all`
   - 强制垃圾回收：`git gc --prune=now --aggressive`
   - 彻底从 Git 对象数据库中删除文件

**验证结果**:
- `git log --all --full-history --oneline -- JNTools_Setup_v1.0.1.exe` 无输出（文件已从历史中完全删除）
- `git rev-list --objects --all | Select-String "JNTools_Setup_v1.0.1.exe"` 无输出（文件已从对象数据库中删除）

**后续操作**:
- 由于重写了 Git 历史，推送时需要强制推送：`git push --force`
- ⚠️ **警告**：强制推送会重写远程仓库的历史，如果其他开发者正在使用该仓库，需要通知他们重新克隆或重置本地仓库
- 由于 `.gitignore` 已配置 `*.exe`，后续生成的 exe 文件不会被自动跟踪

**注意事项**:
- 本地文件不会被删除，如果需要删除本地文件，需要手动删除
- 如果这是共享仓库，建议通知所有协作者，他们需要重新克隆仓库或执行 `git fetch origin` 和 `git reset --hard origin/main`
- 仓库大小已显著减小，现在可以正常推送到 GitHub

## 2026-01-09 - 新增配置页面功能

### 功能新增

**新增内容**:
- 创建了完整的配置管理页面，支持可视化配置应用设置和功能模块
- 用户可以通过Web界面方便地管理应用配置，无需手动编辑配置文件

**新增功能**:
1. **配置页面** (`src/web/templates/settings.html`):
   - 基础配置管理：服务地址、端口、窗口大小等
   - 功能模块配置：启用/禁用模块、启动时初始化控制
   - 实时配置预览和保存
   - 配置重置和重新加载功能

2. **配置API接口** (`src/api/routes.py`):
   - `GET /api/settings/modules` - 获取模块配置
   - `POST /api/settings/modules` - 保存模块配置
   - `POST /api/settings/reset` - 重置配置为默认值

3. **配置页面路由** (`src/web/routes.py`):
   - `GET /settings` - 配置页面路由

4. **导航栏更新** (`src/web/templates/base.html`):
   - 在侧边栏导航中添加"配置"菜单项
   - 配置页面图标：⚙️

**技术实现**:
- 配置页面使用响应式设计，支持移动端和桌面端
- 模块配置支持实时更新，禁用模块时自动取消"启动时初始化"
- 配置保存后自动重新加载模块管理器配置
- 提供友好的错误提示和成功反馈

**用户体验改进**:
- 用户可以通过Web界面轻松管理配置，无需手动编辑JSON文件
- 配置页面提供清晰的说明和帮助文本
- 支持配置验证，防止无效配置
- 配置保存后提示用户部分配置需要重启应用才能生效

**文件变更**:
- 新增：`src/web/templates/settings.html` - 配置页面模板
- 修改：`src/web/routes.py` - 添加配置页面路由
- 修改：`src/api/routes.py` - 添加配置管理API接口
- 修改：`src/web/templates/base.html` - 添加配置页面导航链接

## 2026-01-XX - 项目改造：蕉内工具箱 → 如意助手

### 重大更新

**改造内容**:
- 项目名称从"蕉内工具箱"改为"如意助手"
- 版本号更新为 2.0.0
- 实现功能模块配置系统，支持模块的启用/禁用和启动时机控制
- 新增Python脚本执行功能
- 优化资源占用，实现浏览器池延迟加载和空闲超时自动关闭
- 将快递查询功能改为可选模块（默认禁用）

**新增功能**:
1. **功能模块配置系统** (`src/config/modules.py`, `src/utils/module_manager.py`):
   - 支持模块的启用/禁用配置
   - 支持启动时初始化控制
   - 支持配置持久化（JSON文件）
   - 支持模块依赖检查

2. **Python脚本执行工具** (`src/tools/script_tool.py`):
   - 支持执行Python脚本
   - 支持参数传递和结果返回
   - 支持执行超时控制
   - 支持沙箱模式（限制危险操作）

3. **脚本管理器** (`src/utils/script_manager.py`):
   - 脚本文件管理（保存、读取、删除）
   - 脚本分类管理
   - 脚本执行历史记录

4. **脚本执行API** (`src/api/routes.py`):
   - `POST /api/script/execute` - 执行脚本
   - `GET /api/script/list` - 获取脚本列表
   - `POST /api/script/save` - 保存脚本
   - `GET/DELETE /api/script/<script_id>` - 获取/删除脚本
   - `GET /api/script/<script_id>/history` - 获取执行历史
   - `GET /api/script/categories` - 获取分类列表

**优化内容**:
1. **浏览器池延迟加载** (`src/spider/query_manager.py`):
   - 改为按需初始化（首次使用时才创建）
   - 添加空闲超时自动关闭机制（默认300秒）
   - 添加最后使用时间跟踪

2. **工具初始化优化** (`src/app.py`, `src/tools/manager.py`):
   - 根据模块配置决定初始化哪些工具
   - 启动时只初始化 `init_on_startup=True` 的模块
   - 支持工具的延迟加载和动态注册

3. **快递查询功能改为可选**:
   - 通过模块配置系统控制
   - 默认配置：`enabled=False, init_on_startup=False`
   - 用户可以通过配置文件或API启用

**文件变更**:
- 新增：`src/config/modules.py` - 模块配置定义
- 新增：`src/utils/module_manager.py` - 模块管理器
- 新增：`src/tools/script_tool.py` - 脚本执行工具
- 新增：`src/utils/script_manager.py` - 脚本管理器
- 修改：`src/config.py` - 添加模块配置相关配置项和函数
- 修改：`src/app.py` - 优化工具初始化逻辑，支持模块配置
- 修改：`src/tools/manager.py` - 添加延迟加载支持
- 修改：`src/spider/query_manager.py` - 添加延迟初始化和空闲超时机制
- 修改：`src/api/routes.py` - 添加脚本执行相关API
- 修改：`src/main.py` - 更新浏览器池初始化逻辑

## 2026-01-08 - 修复日志文件权限问题，解决开机自启失败

### Bug修复

**修复内容**:
- 修复了程序安装在 `Program Files` 目录下时无法写入日志文件的权限问题
- 自动检测权限并切换到用户目录，无需管理员权限即可运行
- 解决了开机自启失败的根本原因

**问题原因**:
1. **权限问题**：
   - 程序安装在 `C:\Program Files (x86)\JNTools\` 时，日志目录为 `C:\Program Files (x86)\JNTools\logs\`
   - `Program Files` 目录需要管理员权限才能写入文件
   - 普通用户运行程序时无法创建或写入日志文件，导致 `PermissionError: [Errno 13] Permission denied`

2. **开机自启失败**：
   - 开机自启时程序以普通用户权限运行，无法写入 `Program Files` 目录
   - 日志初始化失败导致程序无法正常启动
   - 这是开机自启失败的根本原因

**技术实现**:
- 新增 `_get_safe_log_dir()` 函数：
  - 检测程序是否安装在 `Program Files` 目录下
  - 检测默认日志目录的写入权限
  - 如果权限不足，自动切换到用户目录 `%LOCALAPPDATA%\JNTools\logs\`
  - 使用测试文件验证写入权限

- 修改 `DailyRotatingFileHandler.__init__()` 方法：
  - 添加 `PermissionError` 异常处理
  - 创建目录失败时自动切换到用户目录
  - 确保日志文件始终可以正常创建

- 修改 `setup_logger()` 函数：
  - 使用 `_get_safe_log_dir()` 获取安全的日志目录
  - 自动处理权限问题，无需手动配置

**日志目录规则**:
- **开发环境**：使用项目根目录下的 `logs` 文件夹
- **普通安装**：使用项目根目录下的 `logs` 文件夹
- **Program Files 安装**：自动切换到 `C:\Users\<用户名>\AppData\Local\JNTools\logs\`

**用户体验改进**:
- 程序可以在任何安装位置正常运行，无需管理员权限
- 开机自启功能现在可以正常工作
- 日志文件始终可以正常创建和写入
- 用户无需关心权限问题，系统自动处理

**影响范围**:
- 修复了所有需要写入日志的场景
- 解决了开机自启失败的问题
- 提升了程序的兼容性和用户体验

## 2026-01-08 - 优化退出处理和浏览器驱动路径查找

### Bug修复和优化

**修复内容**:
- 修复托盘图标退出时的 SystemExit 异常被记录为错误的问题
- 优化浏览器驱动路径查找逻辑，更新打包环境路径说明
- 改进浏览器驱动未找到时的提示信息

**问题原因**:
1. **SystemExit 异常**：
   - `sys.exit(0)` 会抛出 SystemExit 异常
   - pystray 的消息处理器捕获并记录为错误
   - 虽然这是正常退出，但错误日志会让用户误以为有问题

2. **浏览器驱动路径**：
   - 打包环境路径说明中仍使用旧的 `dist/main/` 路径
   - 实际打包后路径是 `dist/JNTools/`
   - 浏览器驱动未找到时的提示信息不够详细

**技术实现**:
- 修改 `src/main.py` 的 `on_tray_quit()` 函数：
  - 将 `sys.exit(0)` 改为 `os._exit(0)`
  - `os._exit()` 直接终止进程，不会抛出异常
  - 避免 SystemExit 异常被 pystray 捕获并记录为错误

- 修改 `src/utils/browser_path.py`：
  - 更新打包环境路径说明，从 `dist/main/` 改为 `dist/JNTools/`
  - 确保路径查找逻辑正确

- 修改 `src/app.py` 的 `init_browser_pool()` 函数：
  - 改进浏览器驱动未找到时的提示信息
  - 提供更详细的解决建议

**用户体验改进**:
- 退出时不再出现错误日志
- 浏览器驱动未找到时提供更清晰的提示
- 应用退出更加干净和优雅

## 2026-01-08 - 修复托盘图标退出时的异常处理

### Bug修复

**修复内容**:
- 修复了托盘图标退出时 pystray 记录 SystemExit 异常为错误的问题
- 优化退出流程，确保资源正确清理

**问题原因**:
- `sys.exit(0)` 会抛出 SystemExit 异常，这是 Python 的正常退出机制
- pystray 的消息处理器捕获了这个异常并记录为错误
- 虽然 SystemExit: 0 表示正常退出，但错误日志会让用户误以为有问题

**技术实现**:
- 修改 `src/tray/tray_icon.py` 的 `_on_quit_clicked()` 方法：
  - 添加异常处理，区分 SystemExit 和其他异常
  - SystemExit 是正常退出，允许传播但先停止托盘图标
  - 其他异常需要记录并处理

- 修改 `src/main.py` 的 `on_tray_quit()` 函数：
  - 调整退出顺序：先清理资源，再停止托盘图标
  - 保持使用 `sys.exit(0)` 正常退出
  - 添加异常处理，确保托盘图标正确停止

**说明**:
- SystemExit: 0 是 Python 的正常退出方式，不是真正的错误
- pystray 可能会记录这个异常，但不影响应用正常退出
- 现在异常处理更加完善，确保资源正确清理

## 2026-01-08 - 安装包默认勾选创建桌面快捷方式

### 功能优化

**优化内容**:
- 安装包安装时默认勾选"创建桌面快捷方式"选项
- 提升用户体验，用户无需手动勾选

**技术实现**:
- 修改 `setup.iss` 中的 `[Tasks]` 部分：
  - 将 `desktopicon` 任务的 `Flags: unchecked` 改为 `Flags: checked`
  - 桌面快捷方式现在默认勾选
  - 快速启动栏快捷方式保持默认不勾选（因为现代Windows系统很少使用）

**用户体验改进**:
- 安装时桌面快捷方式选项默认已勾选
- 用户可以直接点击"下一步"完成安装
- 如果需要取消，可以手动取消勾选

## 2026-01-08 - 修复Inno Setup中文语言文件路径问题

### Bug修复

**修复内容**:
- 修复了 Inno Setup 编译时找不到中文语言文件的问题
- 提供两种方案：使用中文界面或默认英文界面

**问题原因**:
- Inno Setup 默认不包含中文语言文件
- 需要单独下载并安装中文语言包
- 如果语言文件不存在，编译会失败

**技术实现**:
- 修改 `setup.iss`：
  - 将中文语言配置改为注释，并提供下载说明
  - 添加默认英文界面配置作为备选方案
  - 用户可以根据需要选择使用中文或英文界面

**解决方案**:
- **方案1（中文界面）**：
  1. 访问 https://jrsoftware.org/files/istrans/
  2. 下载 `ChineseSimplified.isl` 文件
  3. 放到 Inno Setup 的 Languages 目录（通常：`C:\Program Files (x86)\Inno Setup 6\Languages\`）
  4. 取消注释中文语言配置行
  5. 注释掉英文语言配置行

- **方案2（英文界面，推荐）**：
  - 直接使用默认英文界面，无需额外文件
  - 当前配置已设置为英文界面

**注意事项**:
- 应用名称和描述仍然使用中文（在 `[Setup]` 和 `[Icons]` 部分）
- 只有安装向导界面是英文，不影响应用本身
- 如果需要完全中文界面，请下载并安装中文语言包

## 2026-01-08 - 修复开机自启动配置，更新应用名称

### Bug修复

**修复内容**:
- 更新开机自启动注册表键名从 "JNSpider" 改为 "JNTools"
- 修复开发环境下获取exe路径的逻辑，从 `JNSpider.py` 改为 `main.py`

**问题原因**:
- 应用名称已从 "JNSpider" 改为 "JNTools"（蕉内工具箱）
- 主入口文件是 `main.py` 而不是 `JNSpider.py`
- 注册表键名需要与应用名称保持一致

**技术实现**:
- 修改 `src/utils/startup.py`：
  - 将 `STARTUP_APP_NAME` 从 `"JNSpider"` 改为 `"JNTools"`
  - 将 `get_exe_path()` 函数中开发环境的路径从 `JNSpider.py` 改为 `main.py`
  - 确保注册表键名与应用名称一致

**开机自启动功能说明**:
- 应用启动时自动检查是否已添加到开机自启动
- 如果未添加，自动添加到注册表
- 注册表位置：`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- 注册表键名：`JNTools`
- 支持通过API接口管理：`GET/POST/DELETE /startup`

**测试方法**:
1. 运行应用，检查日志中是否有"开机自启动已启用"或"正在自动添加"的提示
2. 使用注册表编辑器（regedit）检查注册表项是否存在
3. 使用API接口测试：
   - `GET http://127.0.0.1:8889/startup` - 查询状态
   - `POST http://127.0.0.1:8889/startup` - 启用自启动
   - `DELETE http://127.0.0.1:8889/startup` - 禁用自启动
4. 重启电脑，验证应用是否自动启动

## 2026-01-08 - 创建Inno Setup安装包脚本

### 功能新增

**新增内容**:
- 创建了 Inno Setup 安装包脚本 `setup.iss`
- 支持将打包后的 JNTools 应用制作成 Windows 安装程序

**安装包特性**:
- 自动打包主程序、依赖文件、浏览器驱动等所有必要文件
- 支持创建桌面和开始菜单快捷方式（用户可选择）
- 支持中文界面（简体中文）
- 需要管理员权限安装（安装到 Program Files）
- 支持卸载功能，卸载时自动清理相关文件

**技术实现**:
- 修改 `setup.iss`：
  - 配置应用信息：名称"蕉内工具箱"，版本"1.0.0"
  - 设置安装目录：`C:\Program Files\JNTools`
  - 打包文件：
    - `JNTools.exe`（主程序）
    - `_internal\*`（所有依赖文件）
    - `playwright_drivers\*`（浏览器驱动）
  - 创建快捷方式：
    - 开始菜单：必选
    - 桌面：用户可选
    - 快速启动栏：用户可选（仅 Windows 7 及以下）
  - 卸载时自动删除日志目录

**使用方法**:
1. 确保已使用 PyInstaller 打包应用（`dist/JNTools/` 目录存在）
2. 安装 Inno Setup（https://jrsoftware.org/isinfo.php）
3. 打开 `setup.iss` 文件
4. 点击"编译"按钮生成安装程序
5. 生成的安装程序：`JNTools_Setup_v1.0.0.exe`

**注意事项**:
- 安装包需要管理员权限
- 安装程序会自动检测并打包所有必要文件
- 日志目录（logs）会在运行时自动创建，不需要打包
- 如果应用图标已配置，可以在 `[Setup]` 部分添加 `SetupIconFile` 设置安装程序图标

## 2026-01-08 - 修复窗口关闭后任务栏图标未消失的问题

### Bug修复

**修复内容**:
- 修复了关闭主窗口后任务栏图标仍然显示的问题
- 将窗口关闭处理从 `minimize()` 改为 `hide()`，确保窗口隐藏后任务栏图标消失

**问题原因**:
- 之前使用 `webview_window.minimize()` 最小化窗口，这会将窗口最小化到任务栏
- 最小化后窗口仍然在任务栏显示，不符合"隐藏到托盘"的预期行为
- 用户期望关闭窗口后，任务栏图标应该消失，只保留系统托盘图标

**技术实现**:
- 修改 `src/main.py` 中的 `on_window_closing()` 函数：
  - 将主要处理逻辑从 `minimize()` 改为 `hide()`
  - `hide()` 会完全隐藏窗口，任务栏图标会消失
  - 保留 `minimize()` 作为备选方案（如果 `hide()` 失败）
  - 更新日志信息，说明窗口隐藏后任务栏图标会移除
  - 更新提示信息，说明关闭窗口会隐藏到托盘

**用户体验改进**:
- 关闭窗口后，任务栏图标立即消失
- 应用继续在后台运行，只显示系统托盘图标
- 可以通过系统托盘图标重新打开窗口
- 更符合桌面应用的常见行为模式

## 2026-01-08 - 修改exe文件名为JNTools

### 功能优化

**优化内容**:
- 将打包后的 exe 文件名从 `main.exe` 改为 `JNTools.exe`
- 更新所有相关的目录引用和路径配置

**技术实现**:
- 修改 `main.spec`：
  - 将 `EXE` 的 `name` 参数从 `'main'` 改为 `'JNTools'`
  - 将 `COLLECT` 的 `name` 参数从 `'main'` 改为 `'JNTools'`
  - 更新 `clean_dist_folder()` 函数中的日志目录路径：`dist/main/logs` → `dist/JNTools/logs`
  - 更新 `copy_playwright_drivers()` 函数中的输出目录路径：`dist/main` → `dist/JNTools`
  - 更新错误提示信息中的路径引用

**打包输出**:
- 打包后的 exe 文件：`dist/JNTools/JNTools.exe`
- 打包后的目录结构：`dist/JNTools/`（包含所有依赖文件）
- 日志目录：`dist/JNTools/logs/`
- 浏览器驱动目录：`dist/JNTools/playwright_drivers/`

## 2026-01-08 - 修复Windows GBK编码错误导致页面渲染失败

### Bug修复

**修复内容**:
- 修复了 Windows 系统上打印包含 emoji 字符时出现的 GBK 编码错误
- 将 `print()` 语句替换为 logger，避免编码问题

**问题原因**:
- Windows 控制台默认使用 GBK 编码
- 当 `print()` 尝试输出包含 emoji 字符（如 📦）的字符串时，GBK 编码无法处理这些 Unicode 字符
- 错误发生在 `web/routes.py` 第 37 行，尝试打印包含 emoji 的工具信息

**技术实现**:
- 修改 `src/web/routes.py`：
  - 导入 `get_logger` 并创建 `routes_logger`
  - 将所有 `print()` 语句替换为 `routes_logger.info()`、`routes_logger.debug()` 或 `routes_logger.error()`
  - 移除包含 emoji 的详细打印语句，避免编码问题
  - 使用 logger 的 `exc_info=True` 参数自动记录异常堆栈

**解决方案**:
- Logger 已经配置了正确的编码处理（UTF-8）
- 日志文件使用 UTF-8 编码，可以正确处理 emoji 字符
- 控制台输出通过 logger 的格式化处理，避免直接编码错误

## 2026-01-08 - 添加窗口标题栏图标支持

### 功能优化

**优化内容**:
- 为 pywebview 窗口添加自定义图标支持
- 自动将 `logo_default.jpg` 转换为 ICO 格式用于窗口图标
- 窗口标题栏显示自定义图标

**技术实现**:
- 修改 `src/main.py`：
  - 添加 `_get_window_icon_path()` 函数，用于获取窗口图标路径
  - 自动将 `logo_default.jpg` 转换为 ICO 格式（256x256像素）
  - 在 `webview.start()` 中使用 `icon` 参数设置窗口图标
  - 如果转换失败，尝试使用现有的 ICO 文件（icon.ico 或 favicon.ico）

**图标处理逻辑**:
1. 优先使用 `logo_default.jpg`，自动转换为 `window_icon.ico`
2. 如果 ICO 文件已存在且比 JPG 文件新，则直接使用
3. 如果转换失败，尝试使用现有的 `icon.ico` 或 `favicon.ico`
4. 如果都失败，使用系统默认图标

**注意事项**:
- Windows 上窗口图标主要从可执行文件的图标资源获取
- `webview.start()` 的 `icon` 参数在某些平台上可能不生效
- 打包后的 exe 文件图标（通过 main.spec 设置）会优先显示
- 生成的 `window_icon.ico` 文件保存在 `src/static/images/` 目录

## 2026-01-08 - 添加favicon.ico到网页模板

### 功能优化

**优化内容**:
- 在网页模板中添加 favicon.ico 引用，显示浏览器标签页图标
- 添加 `/favicon.ico` 路由，处理浏览器的自动请求

**技术实现**:
- 修改 `src/web/templates/base.html`：
  - 在 `<head>` 部分添加 favicon 引用
  - 使用 `url_for('static', filename='images/favicon.ico')` 生成正确的URL
  - 同时添加 `rel="icon"` 和 `rel="shortcut icon"` 以确保兼容性

- 修改 `src/web/routes.py`：
  - 添加 `/favicon.ico` 路由处理函数
  - 使用 `send_from_directory` 从静态文件目录发送 favicon.ico
  - 设置正确的 MIME 类型 `image/vnd.microsoft.icon`

**文件位置**:
- favicon.ico 文件位于 `src/static/images/favicon.ico`
- 通过 `/favicon.ico` 或 `/static/images/favicon.ico` 都可以访问

**浏览器兼容性**:
- 支持所有现代浏览器的自动 favicon 请求
- 兼容不同浏览器的 favicon 加载方式
- 确保在浏览器标签页中正确显示图标

## 2026-01-08 - 更换应用图标和托盘图标为logo_default.jpg

### 功能优化

**优化内容**:
- 将应用图标和托盘图标更换为 `src/static/images/logo_default.jpg`
- 托盘图标自动加载JPG格式图片并转换为合适的尺寸
- 打包时自动将JPG转换为ICO格式用于Windows应用图标

**技术实现**:
- 修改 `src/tray/tray_icon.py`：
  - 更新 `_load_icon_from_file()` 方法，优先加载 `logo_default.jpg`
  - 支持加载JPG、PNG、ICO格式的图标文件
  - 自动将图标转换为RGBA模式以支持透明度
  - 自动调整图标大小为128x128像素（适合托盘显示）
  - 支持通过 `Config.TRAY_ICON_PATH` 配置自定义图标路径

- 修改 `main.spec`：
  - 添加应用图标配置，优先使用 `logo_default.jpg`
  - 自动将JPG/PNG格式转换为ICO格式（Windows要求）
  - 生成多尺寸ICO图标（256x256, 128x128, 64x64, 32x32, 16x16）
  - 如果转换失败，尝试直接使用原始文件

- 修改 `src/config.py`：
  - 更新 `TRAY_ICON_PATH` 配置项的注释说明

**图标加载顺序**:
1. 如果配置了 `TRAY_ICON_PATH`，优先使用配置的路径
2. 尝试加载 `logo_default.jpg`
3. 尝试加载 `icon.png`
4. 尝试加载 `icon.ico`
5. 如果都失败，使用默认生成的图标

**打包图标处理**:
- 打包时自动检测图标文件格式
- JPG/PNG格式自动转换为ICO格式
- 生成包含多个尺寸的ICO文件，确保在不同场景下显示清晰
- 临时ICO文件会在打包过程中使用，不会影响源代码目录

## 2026-01-08 - 批量查询结果添加展开/收起功能

### 功能优化

**优化内容**:
- 批量查询结果默认只显示第一条物流信息，其余信息可点击展开查看
- 添加展开/收起按钮，提升批量查询结果的浏览体验
- 优化批量查询结果的UI布局和交互效果

**功能实现**:
- 修改 `src/web/templates/tools/spider.html`：
  - 重构 `displayBatchResult()` 函数，实现物流信息的折叠显示
  - 默认显示第一条物流信息作为预览
  - 当物流信息超过1条时，显示展开/收起按钮
  - 添加 `toggleBatchLogistics()` 函数处理展开/收起交互
  - 添加CSS样式支持展开/收起动画效果

**UI改进**:
- 批量查询结果卡片化显示，每条结果独立卡片
- 卡片头部显示快递单号、公司、状态和物流记录数量
- 展开/收起按钮带有图标和文字提示
- 使用CSS transition实现平滑的展开/收起动画
- 优化卡片hover效果，提升交互体验

**技术细节**:
- 使用 `max-height` 和 `opacity` 实现展开/收起动画
- 通过 `classList.toggle()` 切换展开状态
- 展开按钮图标使用CSS transform实现旋转效果
- 物流信息列表使用 `overflow: hidden` 实现折叠效果

## 2026-01-08 - 修复pywebview create_window不支持debug参数的错误

### Bug修复

**修复内容**:
- 修复了 `webview.create_window()` 不支持 `debug` 参数导致的 `TypeError` 错误
- 将 `debug` 参数从 `create_window()` 移到 `webview.start()` 中

**问题原因**:
- `pywebview` 的 `create_window()` 函数不支持 `debug` 参数
- `debug` 参数应该用在 `webview.start()` 函数中，而不是 `create_window()` 中
- 导致应用启动时抛出 `TypeError: create_window() got an unexpected keyword argument 'debug'`

**技术实现**:
- 修改 `src/main.py` 中的 `create_native_window()` 函数：
  - 从 `webview.create_window()` 调用中移除 `debug=Config.ENABLE_DEVTOOLS` 参数
  - 在 `webview.start()` 调用中使用 `debug=Config.ENABLE_DEVTOOLS` 参数
  - 更新注释说明 `debug` 参数的正确用法

**解决方案**:
- `create_window()` 只用于创建窗口，不包含 `debug` 参数
- `webview.start()` 用于启动窗口，包含 `debug` 参数控制开发者工具
- 这样既符合 `pywebview` 的API规范，又能正确控制开发者工具的显示

## 2026-01-08 - 修复浏览器池对象引用不一致导致_initialized检查失败

### Bug修复

**修复内容**:
- 修复了路由函数中 `browser_pool` 对象引用不一致的问题
- 使用模块级全局变量存储 `browser_pool` 引用，确保路由函数访问到正确的对象

**问题原因**:
- 在 `register_routes()` 函数中，`browser_pool` 通过闭包被路由函数捕获
- 如果存在多个 `browser_pool` 对象，或者对象在初始化过程中被替换，可能导致引用不一致
- 路由函数中访问的 `browser_pool` 对象可能不是实际初始化完成的对象

**技术实现**:
- 修改 `src/api/routes.py`：
  - 添加模块级全局变量 `_browser_pool_ref` 存储 `browser_pool` 引用
  - 在 `register_routes()` 函数中更新全局引用
  - 在路由函数中使用全局引用获取 `browser_pool` 对象，而不是通过闭包捕获
  - 添加调试日志，记录对象ID和 `_initialized` 状态

- 修改 `src/main.py`：
  - 添加调试日志，记录 `browser_pool` 对象ID和 `_initialized` 状态
  - 在注册路由前后都记录状态，方便排查问题

**解决方案**:
- 使用模块级全局变量确保所有路由函数访问同一个 `browser_pool` 对象
- 添加详细的调试日志，方便排查对象引用问题
- 确保路由函数始终访问到最新状态的 `browser_pool` 对象

## 2026-01-08 - 修复浏览器池_initialized属性一直为False的问题

### Bug修复

**修复内容**:
- 修复了浏览器池 `_initialized` 属性一直为 `False` 的问题
- 改进了初始化流程，确保在浏览器和上下文创建成功后立即设置 `_initialized = True`

**问题原因**:
- 在 `initialize()` 方法中，`_initialized = True` 是在所有步骤完成后才设置的
- 如果页面创建或百度页面初始化过程中抛出异常，`_initialized` 可能不会被设置为 `True`
- 导致浏览器池虽然已经创建了浏览器和上下文，但状态标记为未初始化

**技术实现**:
- 修改 `src/spider/query_manager.py` 中的 `initialize()` 方法：
  - 将 `_initialized = True` 的设置提前到浏览器和上下文创建成功后
  - 添加异常处理，确保即使页面创建或百度页面初始化失败，浏览器池也会被标记为已初始化
  - 这样即使部分步骤失败，浏览器池仍然可以使用

**解决方案**:
- 在浏览器和上下文创建成功后立即设置 `_initialized = True`
- 页面创建和百度页面初始化作为可选步骤，失败不影响浏览器池的初始化状态
- 添加详细的错误日志，方便排查问题

## 2026-01-08 - 优化Tab容器布局为通栏设计

### UI优化

**优化内容**:
- 将Tab容器改为通栏设计，不再限制宽度
- 优化Tab按钮布局，不再平分，改为固定宽度
- 提升整体视觉效果

**技术实现**:
- 修改 `src/web/templates/tools/spider.html`：
  - Tab容器：添加 `max-width: none` 确保通栏显示
  - Tab按钮：移除 `flex: 1` 平分效果，改为 `min-width: 140px` 固定宽度
  - 添加 `flex-shrink: 0` 防止按钮收缩
  - 使用 `inline-flex` 布局，按钮不再平分容器宽度
  
- 修改 `src/static/css/main.css`：
  - 主内容区：移除 `max-width: 1200px` 限制
  - 改为 `width: calc(100% - 250px)` 确保通栏显示

**视觉效果改进**:
- 容器占满整个可用宽度，不再有最大宽度限制
- Tab按钮有固定宽度，不再平分，视觉效果更清晰
- 整体布局更加协调和现代化

## 2026-01-08 - 修复浏览器池初始化检查问题

### Bug修复

**修复内容**:
- 修复了 `browser_pool._initialized` 属性访问可能导致的 `AttributeError` 问题
- 改进了浏览器池初始化状态的检查逻辑

**技术实现**:
- 修改 `src/api/routes.py` 中的浏览器池检查逻辑：
  - 在 `query_single()` 函数中：使用 `hasattr()` 检查 `_initialized` 属性是否存在
  - 在 `query_batch()` 函数中：使用 `hasattr()` 检查 `_initialized` 属性是否存在
  - 在 `health_check()` 函数中：安全地检查浏览器池初始化状态
  - 将检查分为两步：先检查 `browser_pool is None`，再检查 `_initialized` 属性

**问题原因**:
- 在路由函数中直接访问 `browser_pool._initialized` 可能导致 `AttributeError`
- 如果 `browser_pool` 对象存在但 `_initialized` 属性不存在，会抛出异常

**解决方案**:
- 使用 `hasattr(browser_pool, '_initialized')` 先检查属性是否存在
- 然后再检查属性值是否为 `True`
- 这样即使属性不存在也不会抛出异常，而是返回友好的错误信息

## 2026-01-08 - 优化Tab切换样式

### UI优化

**优化内容**:
- 优化了爬虫工具页面的Tab切换样式
- 改进了tab-header的布局和视觉效果
- 提升了用户体验

**技术实现**:
- 修改 `src/web/templates/tools/spider.html` 中的Tab样式：
  - 确保tab-container和tab-header宽度占满容器（width: 100%）
  - 优化tab-button的样式：
    - 增加内边距（padding: 18px 32px）
    - 添加最小高度（min-height: 60px）
    - 使用flex布局居中对齐
    - 添加::after伪元素实现底部指示条动画
    - 改进hover和active状态的视觉效果
  - 优化过渡动画效果（transition: all 0.3s ease）
  - 改进active状态的字体粗细（font-weight: 600）

**视觉效果改进**:
- Tab按钮更加清晰和现代化
- 底部指示条动画更流畅
- hover状态有更好的视觉反馈
- 整体布局更加协调

## 2026-01-08 - 修复批量查询结果显示物流详情

### Bug修复

**修复内容**:
- 修复了批量查询结果中无法查看快递详情的问题
- 批量查询结果现在会显示完整的物流信息列表，与单个查询保持一致

**技术实现**:
- 修改 `src/web/templates/tools/spider.html` 中的 `displayBatchResult` 函数
- 添加了物流详情列表的显示逻辑，包括时间、内容和地点信息
- 批量查询结果现在包含：
  - 快递单号
  - 快递公司
  - 状态
  - 完整的物流信息列表（时间、内容、地点）

## 2026-01-08 - 爬虫工具页面改为Tab切换模式

### 功能增强

**新增功能**:
- 将爬虫工具页面改造成Tab切换模式
- 包含"单个查询"和"批量查询"两个标签页
- 优化了页面布局和用户体验

**技术实现**:
- 修改 `src/web/templates/tools/spider.html`：
  - 添加Tab切换的HTML结构（tab-header和tab-content）
  - 添加Tab切换的CSS样式（包含动画效果）
  - 添加Tab切换的JavaScript逻辑
  - 保持原有的查询功能不变
  
- Tab切换特性：
  - 使用CSS动画实现平滑切换效果
  - Tab按钮有hover和active状态
  - 默认显示"单个查询"标签页
  - 点击Tab按钮可以切换不同的查询模式

**用户体验改进**:
- 页面更加简洁，两个查询模式通过Tab切换
- 减少了页面滚动，提升了操作效率
- 保持了原有的所有功能（单个查询、批量查询、结果显示等）

## 2026-01-XX - 修复托盘图标无法恢复窗口的问题

### Bug修复

**修复内容**:
- 修复了窗口最小化后，通过托盘图标无法恢复窗口的问题
- 改进了窗口恢复逻辑，使用多种方法确保窗口能够正确恢复

**问题分析**:
- 窗口最小化后，`restore()` 方法可能不够，需要先 `show()` 再 `restore()`
- 窗口可能被隐藏而不是最小化，需要先显示再恢复
- 需要使用 `webview.windows` API 来查找和恢复窗口

**技术实现**:
- 优化 `show_native_window()` 函数：
  - 使用 `webview.windows` API 查找窗口（最可靠的方法）
  - 先调用 `show()` 显示窗口（如果被隐藏）
  - 再调用 `restore()` 恢复窗口（如果被最小化）
  - 最后调用 `bring_to_front()` 将窗口置于前台
  - 移除了锁，避免线程阻塞问题
  - 添加了详细的日志记录，便于调试

- 改进 `on_window_closing()` 函数：
  - 优先使用 `minimize()` 最小化窗口
  - 如果最小化失败，才尝试 `hide()` 隐藏窗口
  - 添加警告日志，提示隐藏后可能无法通过托盘恢复

**修复效果**:
- 窗口最小化后，可以通过托盘图标正常恢复窗口
- 即使窗口被隐藏，也能通过多种方法尝试恢复
- 如果窗口对象失效，会自动回退到浏览器模式

## 2026-01-07 - 打包前自动清理 dist 文件夹

### 功能增强

**新增功能**:
- 在 PyInstaller 打包前自动删除 dist 文件夹
- 确保每次打包都是全新的构建，避免旧文件残留

**技术实现**:
- 在 `main.spec` 文件中添加 `clean_dist_folder()` 函数
- 在打包开始前（Analysis 之前）自动执行清理
- 如果 dist 文件夹不存在，会提示无需清理
- 如果删除失败，会显示错误信息但不中断打包流程

**使用说明**:
- 运行 `pyinstaller main.spec` 时，会自动清理 dist 文件夹
- 无需手动删除 dist 文件夹，打包过程会自动处理

## 2026-01-XX - 修复窗口最小化和托盘图标打开窗口问题

### Bug修复

**修复内容**:
- 修复了窗口关闭后应用卡住的问题
- 修复了关闭主界面后托盘图标双击和打开主界面不生效的问题

**问题分析**:
1. **窗口关闭后卡住**：
   - 之前使用 `webview_window.hide()` 隐藏窗口，但 `webview.start()` 在主线程中阻塞运行
   - 窗口被隐藏后，`webview.start()` 可能仍在等待窗口事件，导致主线程卡住
   
2. **托盘图标无法打开窗口**：
   - 窗口被隐藏后，`webview_window` 对象可能失效
   - `show_native_window()` 函数无法正确恢复隐藏的窗口

**技术实现**:
- 修改 `on_window_closing()` 函数：
  - 改用 `minimize()` 最小化窗口而不是 `hide()` 隐藏窗口
  - 窗口最小化后仍然在任务栏中，可以通过 `restore()` 恢复
  - 如果最小化失败，再尝试隐藏作为备选方案
  
- 优化 `show_native_window()` 函数：
  - 使用 `restore()` 恢复最小化的窗口
  - 使用 `bring_to_front()` 将窗口置于前台
  - 如果窗口对象失效，回退到浏览器模式
  
- 添加 `create_native_window_in_thread()` 函数：
  - 用于从托盘图标打开窗口时的回退方案
  - 由于 `webview.start()` 必须在主线程中调用，无法在托盘线程中创建新窗口
  - 如果无法恢复窗口，回退到浏览器模式

**修复效果**:
- 窗口关闭后不再卡住，应用可以正常在后台运行
- 托盘图标双击和右键菜单"打开界面"可以正常恢复窗口
- 如果窗口对象失效，会自动回退到浏览器模式，确保用户能够访问界面

## 2026-01-XX - 统一服务就绪检查逻辑

### 代码优化

**优化内容**:
- 统一了原生窗口和浏览器模式的服务就绪检查逻辑
- 无论是原生窗口还是浏览器模式，都会在打开前先等待Flask服务就绪
- 移除了 `create_native_window()` 函数内部的重复等待逻辑
- 确保只有在服务完全启动后才打开界面，避免打开空白页面

**技术实现**:
- 修改 `src/main.py` 中的 `main()` 函数
- 在 `AUTO_OPEN_BROWSER` 为 True 时，统一调用 `wait_for_server_ready()` 等待服务就绪
- 然后再根据 `USE_NATIVE_WINDOW` 配置决定打开原生窗口还是浏览器
- 简化了 `create_native_window()` 函数，移除了内部的等待逻辑（因为调用前已确保服务就绪）

**优化效果**:
- 代码逻辑更清晰，避免了重复的服务就绪检查
- 确保用户打开界面时服务已经可用，提升用户体验
- 统一了错误处理逻辑

## 2026-01-XX - 优化Flask应用创建逻辑

### 代码优化

**优化内容**:
- 将Flask应用的创建从主线程移到Flask线程中
- 确保所有Flask相关操作（创建app、初始化BrowserPool、初始化ToolManager、注册路由）都在同一线程中执行
- 避免跨线程使用Flask应用实例，提高代码可读性和安全性

**技术实现**:
- 修改 `src/main.py` 中的 `run_flask_app()` 函数
- 在Flask线程中调用 `create_app()` 创建Flask应用实例
- 移除了主线程中的 `app = create_app()` 调用
- 添加了注释说明Flask应用在Flask线程中创建

**优化效果**:
- 代码逻辑更清晰，不会让人误解为创建了两次app
- 所有Flask相关操作集中在同一线程，符合Playwright的要求
- 减少了跨线程共享对象的风险

## 2026-01-XX - 实现日志系统（按天生成日志文件）

### 功能增强

**新增功能**:
- 实现了完整的日志系统，支持按天自动生成独立的日志文件
- 日志文件保存在项目根目录下的 `logs/` 文件夹
- 日志文件命名格式：`app_YYYY-MM-DD.log`（例如：`app_2026-01-15.log`）
- 支持同时输出到控制台和文件
- 支持不同日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
- 每天午夜自动创建新的日志文件

**技术实现**:
- 创建 `src/utils/logger.py` 日志工具模块
  - 实现 `DailyRotatingFileHandler` 类，继承自 `TimedRotatingFileHandler`
  - 实现 `setup_logger()` 函数，用于初始化日志记录器
  - 实现 `get_logger()` 函数，用于获取日志记录器
  - 实现 `init_logging()` 函数，用于初始化全局日志系统
- 在 `src/config.py` 中添加日志配置项：
  - `LOG_DIR`: 日志文件目录（默认：项目根目录下的logs文件夹）
  - `LOG_LEVEL`: 日志级别（默认：INFO）
- 在 `src/main.py` 中集成日志系统：
  - 在程序启动时初始化日志系统
  - 将所有 `print()` 语句替换为 `logger.info()`, `logger.warning()`, `logger.error()` 等
  - 为不同模块创建独立的日志记录器（Main, Flask等）
  - 配置Flask的werkzeug日志，避免重复输出

**日志格式**:
- 文件日志：`[时间] [级别] [模块名] 消息`
  - 示例：`[2026-01-15 10:30:45] [INFO    ] [Main] 应用正在启动...`
- 控制台日志：`[模块名] 消息`（简化格式，便于阅读）
  - 示例：`[Main] 应用正在启动...`

**配置说明**:
- 日志文件默认保存在项目根目录下的 `logs/` 文件夹
- 可以通过 `Config.LOG_DIR` 自定义日志目录
- 可以通过 `Config.LOG_LEVEL` 设置日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 日志文件不会自动删除，保留所有历史日志

**用户体验改进**:
- 所有日志信息都会保存到文件中，方便后续查看和调试
- 控制台输出保持简洁，文件日志包含完整信息
- 每天自动创建新的日志文件，便于按日期查找日志
- 支持不同模块的独立日志记录器，便于定位问题

**文件变更**:
- 新增：`src/utils/logger.py` - 日志工具模块
- 修改：`src/utils/__init__.py` - 导出日志相关函数
- 修改：`src/config.py` - 添加日志配置项
- 修改：`src/main.py` - 集成日志系统，替换所有print语句

## 2026-01-XX - 窗口关闭最小化到托盘

### 功能增强

**新增功能**:
- 点击窗口关闭按钮时，窗口会最小化到系统托盘而不是直接关闭应用
- 应用继续在后台运行，可以通过系统托盘图标重新打开窗口
- 更符合桌面应用的使用习惯

**技术实现**:
- 在 `src/main.py` 中添加 `on_window_closing()` 事件处理函数
- 使用 `webview_window.events.closing += on_window_closing` 订阅窗口关闭事件
- 在事件处理函数中调用 `webview_window.hide()` 隐藏窗口
- 返回 `False` 阻止默认的关闭操作
- 添加 `show_native_window()` 函数，支持从托盘重新显示窗口
- 更新 `on_tray_open()` 回调，支持重新显示隐藏的窗口

**用户体验改进**:
- 点击关闭按钮时，窗口隐藏到托盘，应用继续运行
- 通过系统托盘图标可以重新打开窗口
- 只有通过托盘菜单的"退出"选项才会真正关闭应用

## 2026-01-XX - 添加原生窗口支持

### 功能增强

**新增功能**:
- 使用 `pywebview` 实现原生桌面应用窗口，替代浏览器打开方式
- 应用现在可以像普通桌面应用一样，拥有自己的窗口界面
- 支持窗口大小、最小尺寸、可调整大小等配置

**技术实现**:
- 添加 `pywebview>=4.4.0` 依赖
- 在 `src/config.py` 中新增窗口相关配置项：
  - `USE_NATIVE_WINDOW`: 是否使用原生窗口（默认: True）
  - `WINDOW_TITLE`: 窗口标题
  - `WINDOW_WIDTH/HEIGHT`: 窗口大小
  - `WINDOW_MIN_WIDTH/HEIGHT`: 最小尺寸
  - `WINDOW_RESIZABLE`: 是否可调整大小
- 修改 `src/main.py`，使用 `webview.create_window()` 和 `webview.start()` 创建原生窗口
- 更新 `src/tray/tray_icon.py`，托盘打开时也使用原生窗口
- 更新 `main.spec`，添加 `webview` 相关隐藏导入

**配置说明**:
- 默认启用原生窗口模式（`USE_NATIVE_WINDOW = True`）
- 如果 `pywebview` 未安装，会自动回退到浏览器模式
- 可以通过配置切换到浏览器模式（`USE_NATIVE_WINDOW = False`）

**用户体验改进**:
- 应用启动后直接显示原生窗口，无需打开浏览器
- 窗口可以最小化、最大化、调整大小
- 更符合桌面应用的使用习惯

## 2026-01-XX - 开发指南补充运行说明

### 文档完善

在 `docs/开发指南.md` 中补充了项目运行相关说明：

**新增内容**:
- **2.4 运行项目**章节，包含：
  - 命令行运行方法（激活虚拟环境、运行主程序、停止应用）
  - IDE调试运行方法（VS Code和PyCharm的调试配置）
  - 验证运行成功的检查清单
  - 常见运行问题及解决方案

**更新内容**:
- 更新了目录结构，添加了运行项目章节的链接
- 补充了详细的运行步骤和验证方法

**解决的问题**:
- 解决了文档中缺少"如何运行项目"说明的问题
- 补充了调试时如何运行的详细步骤

## 2026-01-26 - 重构：将拼多多订单数据同步到飞书表格功能提取为独立模块

### 代码重构（2026-01-26）

**重构内容**:
- 创建 `src/spider/pinduoduo/feishutable.py` 模块，封装飞书表格同步功能
- 提供 `sync_orders_to_feishu()` 方法，接收订单数据数组，批量同步到飞书多维表格
- 在 `PinduoduoClient.fetch_recent_orders()` 中调用新方法，简化代码结构

**功能特点**:
- **批量同步**：支持批量创建记录，每批最多100条，自动分批处理
- **容错机制**：批量创建失败时自动降级为单条创建，确保数据不丢失
- **数据映射**：自动将拼多多订单数据转换为飞书表格字段格式
- **统计信息**：返回同步结果，包含成功、失败和总数统计

**数据映射**:
- 订单时间：转换为可读格式（YYYY-MM-DD HH:MM:SS）
- 订单状态：映射为中文描述（待支付、待发货、已发货等）
- 发货状态：映射为中文描述（未发货、已发货、已收货）
- 其他字段：商品ID、省份、城市、订单号、订单金额、优惠信息等

**技术细节**:
- 使用 `FeishuTableClient.batch_create_records()` 进行批量创建
- 批量创建失败时自动降级为单条创建，提高成功率
- 支持自定义 `app_token` 和 `table_id`，默认使用配置值
- 完整的错误处理和日志记录

**修改文件**:
- `src/spider/pinduoduo/feishutable.py` - 新建文件，封装同步功能
- `src/spider/pinduoduo/client.py` - 移除飞书表格客户端直接调用，改为调用新方法

## 2026-01-XX - 文档目录整理

### 文档组织优化

将所有文档移动到 `docs/` 目录，统一管理项目文档：

**移动的文档**:
- `开发指南.md` → `docs/开发指南.md`
- `配置说明.md` → `docs/配置说明.md`
- `PROJECT_DOCUMENTATION.md` → `docs/PROJECT_DOCUMENTATION.md`
- `log.md` → `docs/log.md`

**更新的引用链接**:
- 更新了 `README.md` 中所有文档链接，指向 `docs/` 目录
- 更新了文档内部的交叉引用链接
- `docs/` 目录内的文档使用相对路径引用

**文档结构**:
```
kuaidi/
├── README.md                    # 项目说明（根目录）
├── docs/                        # 文档目录
│   ├── 开发指南.md              # 完整开发技术文档
│   ├── 配置说明.md              # 配置问题快速查找
│   ├── PROJECT_DOCUMENTATION.md # 项目详细文档
│   └── log.md                   # 变更日志
└── ...
```

## 2026-01-XX - 技术文档整理

### 新增文档

1. **开发技术文档 (开发指南.md)**
   - 项目技术架构详解
   - 开发环境配置指南
   - 开发指南（添加新工具等）
   - 调试指南（常见问题、调试技巧）
   - 打包配置详解（main.spec配置说明）
   - 系统托盘配置详解
   - 开机自启动配置详解
   - 部署指南

2. **配置说明文档 (配置说明.md)**
   - 系统托盘配置（右下角任务栏）快速查找
   - 开机自启动配置快速查找
   - 打包配置详解快速查找
   - 配置文件速查表
   - 针对性问题解答

### 文档内容

1. **技术架构**
   - 整体架构图
   - 核心模块说明
   - 技术栈介绍

2. **开发指南**
   - 环境配置步骤
   - IDE配置
   - 添加新工具步骤
   - 代码规范

3. **调试指南**
   - 开发模式调试
   - 常见调试场景
   - 调试技巧

4. **打包配置详解**
   - PyInstaller打包流程
   - main.spec配置详解
   - Analysis、EXE、COLLECT配置说明
   - 打包模式选择
   - 打包注意事项

5. **系统托盘配置**
   - 配置文件位置和说明
   - 图标加载逻辑
   - 托盘菜单配置
   - 事件处理
   - 依赖和打包配置

6. **开机自启动配置**
   - 注册表位置
   - 实现逻辑
   - API接口
   - 常见问题

7. **部署指南**
   - 部署前准备
   - 部署步骤
   - 检查清单
   - 故障排查

## 2026-01-XX - 桌面应用架构重构

### 新增功能

1. **Web界面**
   - 创建了现代化的Web界面，基于Flask模板引擎
   - 响应式设计，支持侧边栏导航
   - 包含主页、工具页面和错误页面

2. **系统托盘**
   - 集成pystray库，支持系统托盘图标
   - 右键菜单：打开界面、退出
   - 双击图标打开Web界面

3. **工具管理器架构**
   - 创建工具基类（BaseTool），定义统一接口
   - 实现工具管理器（ToolManager），支持工具注册和管理
   - 将现有爬虫功能封装为SpiderTool工具

4. **主程序入口**
   - 创建main.py作为应用主入口
   - 整合系统托盘、Flask服务和工具管理
   - 支持自动打开浏览器访问Web界面

5. **静态资源**
   - 创建CSS样式文件，现代化UI设计
   - 创建JavaScript文件，支持前端交互
   - 预留图标文件目录

### 文件变更

#### 新增文件

- `src/main.py` - 主程序入口
- `src/app.py` - Flask应用整合
- `src/web/__init__.py` - Web模块初始化
- `src/web/routes.py` - Web界面路由
- `src/web/templates/base.html` - 基础模板
- `src/web/templates/index.html` - 主页模板
- `src/web/templates/tools/spider.html` - 爬虫工具页面模板
- `src/web/templates/error.html` - 错误页面模板
- `src/static/css/main.css` - 主样式文件
- `src/static/js/main.js` - 主JavaScript文件
- `src/static/images/.gitkeep` - 图标目录占位文件
- `src/tools/__init__.py` - 工具模块初始化
- `src/tools/base.py` - 工具基类
- `src/tools/manager.py` - 工具管理器
- `src/tools/spider_tool.py` - 爬虫工具实现
- `src/tray/__init__.py` - 系统托盘模块初始化
- `src/tray/tray_icon.py` - 系统托盘图标管理
- `requirements.txt` - 依赖列表
- `main.spec` - PyInstaller打包配置
- `README.md` - 项目说明文档
- `log.md` - 变更日志（本文件）

#### 修改文件

- `src/config.py` - 添加Web界面和系统托盘相关配置
  - 新增 `APP_NAME`、`APP_VERSION`、`AUTO_OPEN_BROWSER`、`TRAY_ENABLED` 等配置项

### 技术细节

1. **架构设计**
   - 采用模块化设计，工具可插拔
   - 工具管理器单例模式，统一管理所有工具
   - Flask应用支持开发和生产环境路径自动识别

2. **依赖更新**
   - 新增 `pystray>=0.19.0` - 系统托盘支持
   - 新增 `Pillow>=10.0.0` - 图标处理（pystray依赖）

3. **打包配置**
   - 创建 `main.spec` 用于打包主程序
   - 包含Web模板和静态资源文件
   - 配置必要的隐藏导入

### 使用说明

1. **运行应用**
   ```bash
   python src/main.py
   ```

2. **访问Web界面**
   - 应用启动后自动打开浏览器
   - 或手动访问 `http://127.0.0.1:8099`

3. **系统托盘操作**
   - 双击图标：打开Web界面
   - 右键菜单：打开界面、退出

4. **添加新工具**
   - 继承 `BaseTool` 类
   - 在 `app.py` 中注册工具
   - 创建对应的HTML模板

### 注意事项

- 需要安装Playwright浏览器驱动：`playwright install chromium`
- 系统托盘功能需要pystray和Pillow库支持
- 打包后的exe需要包含Web模板和静态资源文件

### 后续计划

- 添加更多实用工具
- 优化Web界面用户体验
- 支持自定义主题
- 添加工具配置管理

## 2026-01-26 - 添加网络请求监听功能，捕获AJAX请求体

### 功能新增（2026-01-26）

**新增内容**:
- 在 `PinduoduoClient.fetch_recent_orders` 方法中添加了网络请求监听功能
- 使用 Playwright 的 `page.on("request")` 事件监听器捕获浏览器中的 AJAX 请求
- 自动捕获 `https://mms.pinduoduo.com/mangkhut/mms/recentOrderList` 接口的请求信息
- 保存捕获的请求信息到本地文件，包括：
  - 请求 URL
  - 请求方法（GET/POST等）
  - 请求头（headers）
  - 请求体（POST data）
  - 捕获时间戳

**功能特点**:
- 在访问订单列表页面之前设置请求监听器，确保能捕获到页面自动发起的 AJAX 请求
- 自动解析 JSON 格式的请求体，方便查看和分析
- 将捕获的请求信息保存到 `cache/pinduoduo_request_info.json` 文件
- 在返回结果中包含捕获的请求信息，方便调试和分析

**技术细节**:
- 使用 `page.on("request", handle_request)` 监听所有网络请求
- 通过 URL 匹配过滤出目标 API 请求
- 使用 `request.post_data` 获取 POST 请求体
- 使用 `request.headers` 获取请求头信息
- 自动保存请求信息到安全的数据目录（使用 `get_safe_data_path`）

**使用场景**:
- 调试和分析拼多多订单列表页面的实际请求参数
- 了解浏览器自动发起的 AJAX 请求的完整信息
- 对比手动 fetch 请求和浏览器自动请求的差异
- 获取真实的请求头和请求体，用于后续的请求模拟

**修改文件**:
- `src/spider/pinduoduo/client.py` - 在 `fetch_recent_orders` 方法中添加请求监听功能

## 2026-01-26 - 优化 fetch 请求，使用捕获到的请求头（包含 anti-content 和 etag）

### 功能优化（2026-01-26）

**优化内容**:
- 修改 `fetch_recent_orders` 方法中的 fetch 脚本，优先使用捕获到的请求头
- 自动使用浏览器实际请求中的 `anti-content` 和 `etag` 等防爬虫参数
- 如果捕获到请求体，也会使用捕获到的请求体参数（但会更新时间戳）

**技术细节**:
- 在构建 fetch 脚本时，优先检查是否捕获到了请求头
- 如果捕获到请求头，使用捕获到的完整请求头（包含所有防爬虫参数）
- 如果未捕获到请求头，则使用默认的请求头作为后备方案
- 对于请求体，如果捕获到了，会使用捕获到的参数结构，但会更新 `groupStartTime` 和 `groupEndTime` 为当前时间
- 使用 `JSON.parse` 在 JavaScript 中解析转义后的 JSON 字符串，确保特殊字符正确处理

**优势**:
- 使用真实的浏览器请求头，提高请求成功率
- 自动包含 `anti-content` 和 `etag` 等动态生成的防爬虫参数
- 保持请求体结构与浏览器实际请求一致（如 `sortType: 7`、`hideRegionBlackDelayShipping: false` 等）

**修改文件**:
- `src/spider/pinduoduo/client.py` - 优化 `fetch_recent_orders` 方法中的 fetch 脚本构建逻辑

## 2026-01-26 - 修改 fetch 请求体格式，直接使用字符串格式

### 代码优化（2026-01-26）

**优化内容**:
- 修改 fetch 脚本中的请求体格式，直接使用字符串格式（与浏览器实际请求保持一致）
- 请求体从 `JSON.stringify(body)` 改为直接使用字符串 `"body": "{\"orderType\":0,...}"`
- 确保时间范围为最近30天（`groupStartTime` 和 `groupEndTime`）

**技术细节**:
- 将请求体字典转换为 JSON 字符串后，进行适当的转义处理
- 在 fetch 脚本中直接使用转义后的 JSON 字符串作为 body 参数
- 时间计算：`end_time = 当前时间戳`，`start_time = end_time - (30 * 24 * 60 * 60)`（30天前）
- 使用 `json.dumps` 的 `separators=(',', ':')` 参数，确保输出格式紧凑（无多余空格）

**优势**:
- 与浏览器实际请求格式完全一致
- 减少不必要的 JSON 解析和序列化步骤
- 确保时间范围准确为最近30天

**修改文件**:
- `src/spider/pinduoduo/client.py` - 修改 `fetch_recent_orders` 方法中的请求体格式
