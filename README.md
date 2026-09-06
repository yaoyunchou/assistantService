# 如意助手

一个基于 Python 开发的 Windows 桌面私人助手应用，以 Flask 为后端、Playwright 为浏览器自动化引擎，内置 **AI 模块**（统一调用 Nest CMS `/xcx/api/v1/ai/*`），支持模块化配置，资源占用低。

## 功能特性

- 🤖 **AI 智能助手** — `src/ai/` 统一封装 Nest `/ai/chat` 等；业务通过 `from ai import ask / run_agent` 调用（需 `NEST_DEVICE_KEY` 等，见 `.env.example`）
- 🖥️ **现代化 Web 界面** — 基于 Flask 的响应式 Web 界面，美观易用
- 🐍 **Python 脚本执行** — 支持执行 Python 脚本，支持参数传递和结果返回
- 🛒 **拼多多助手** — 拼多多商家后台自动化工具，支持登录管理和飞书通知
- 📋 **订单同步（ERP）** - 官方 ERP 全部订单表抓取，按「平台订单号」同步到指定飞书多维表格（独立页面 `/pdd-erp-order-sync`）
- ✅ **ERP 待审核 / 入库 / 打印** - `/tools/pinduoduo` 加载待审核列表并提交审核（SQLite + 可选飞书审核表）；独立页 `/pdd-erp-delivering-print` 一键「打印并发货」待发货列表；**已发货页今日已打印快递单**：`POST /api/pinduoduo/erp-delivered/today-printed-query`（脚本 `pdd-erp-order-delivered-query.js`，结束飞书 Webhook 摘要）
- 📡 **途强助手** - 途强智能设备管理平台（iot.tqiot.com）自动化，支持自动登录与最近 30 天记录获取
- 📦 **1688 订单提取** - 从 1688 待收货订单列表提取订单与收货信息，支持同步到飞书多维表格（Web 页与命令行脚本）
- 🛍️ **淘宝商品上架** - Playwright 以图发品全链路（本地上传 → 主图审计/补救 → 类目确认 → 发布填表 → 提交 → Excel 回填）；数据目录 `C:\Users\yao\Desktop\work\电商数据\淘宝`；详见 `docs/淘宝商品上传/淘宝商品上传-Playwright开发文档.md`
- 🐟 **闲鱼商品** - Playwright 自动化闲鱼卖家工作台：本地 Excel 队列发布（`/tools/goofish`）+ 在线商品管理（`/goofish/items`，上下架/改价改描述/删除）；取数以 `lib.mtop` 直调为主、DOM 抓取兜底；内置接口探测器 `POST /api/goofish/probe`；数据目录 `C:\Users\yao\Desktop\work\电商数据\闲鱼`；详见 `docs/goofish/闲鱼模块-Playwright开发文档.md`
- ⚡ **安特限时秒杀采集** - 对接 `https://pc.antexiadan.com` pcapi；浏览器采集/搜索前自动登录门禁（`.env`：`ANTEXIADAN_USERNAME` / `ANTEXIADAN_PASSWORD`）；支持 Chrome 扩展页内注入与 Python 直连 CLI；采集结果 POST 入库（MySQL），提供 products / batch 查询；**预售抢购**页 `/antexiadan/presale-rush`：开售前 20 分钟加购、到点结算（支付页人工确认）
- ⚙️ **模块化配置** - 支持通过配置控制功能模块的启用/禁用和启动时机
- 🔧 **可扩展架构** - 工具管理器设计，方便添加新工具
- 📊 **资源监控** - 实时监控内存和CPU使用情况
- 🎯 **系统托盘** - 支持系统托盘图标，最小化到后台运行
- 🚀 **开机自启** - 支持开机自动启动
- 📱 **API接口** - 提供完整的RESTful API接口
- 🔌 **Socket.IO 客户端** - 对接 `docs/websocket-api.md`，Socket.IO path 默认 `/socket.io/`、监听事件 `forward`，默认连 `localhost:8080`（`assistantKey` 默认 `erp-001`，可由配置与环境变量覆盖），Flask/`main` 与开发模式子进程启动后自动连接，支持管理页连接/断开与配置保存；远端可通过 `assistant_http` / `forward`（`type: assistant_http`）下发类 axios 请求并由本机回包 `assistant_http_response`（含 `messageId`），详见 `docs/socketio-assistant-http.md`；多台助手经 CMS Nest 时使用固定 **`assistantKey`**；拼多多 ERP 直连助手或经 Nest 的路径、JWT、握手、`timeout`、`assistant_http` JSON 等一并见 **`docs/pinduoduo-erp-remote-api.md`**
- ⏰ **定时任务** - APScheduler，支持「拼多多 ERP 订单同步」「拼多多库存（飞书 ERP→库存/日志）」等类型；默认种子含每日 12:00 / 18:00 ERP 同步，执行后飞书私聊结果摘要
- 💾 **低资源占用** - 优化资源使用，空闲时内存占用<200MB

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端框架 | Python 3.10+, Flask |
| 前端 | HTML + CSS + Vanilla JS（无前端构建工具） |
| 浏览器自动化 | Playwright（Chromium）+ playwright-stealth |
| AI 大脑 | Cursor SDK（Agent），OpenAI 兼容 LLM，MCP 协议 |
| 定时任务 | APScheduler + croniter |
| 远程通信 | Socket.IO 客户端（对接 Nest 中转服务） |
| 系统集成 | pystray（系统托盘）、pywebview（原生窗口） |
| 打包 | PyInstaller（onedir 模式） |
| 配置 | python-dotenv（`.env`）+ TOML（`app_config.toml`） |

## 项目结构

```
assistantService/
├── src/
│   ├── main.py                    # 应用入口（启动 Flask + 托盘 + WebView）
│   ├── dev.py                     # 开发模式启动（热重载）
│   ├── app.py                     # Flask 应用装配（init_tools + setup_app）
│   ├── config.py                  # 全局配置（Config 类，读 .env + 配置文件）
│   │
│   ├── ai/                        # ★ AI 大脑模块（系统唯一 AI 入口）
│   │   ├── __init__.py            #   公共 API：ask / run_agent / run_agent_stream
│   │   ├── client.py              #   LLM 客户端（OpenAI 兼容，AI_API_KEY）
│   │   ├── agent.py               #   Cursor SDK Agent + 会话持久化
│   │   └── mcp/
│   │       └── playwright_server.py  # Playwright MCP stdio 服务器（7 工具）
│   │
│   ├── api/                       # HTTP API 层
│   │   ├── routes/
│   │   │   ├── __init__.py        #   Blueprint 汇总 + Swagger 注册
│   │   │   ├── health.py          #   GET /health
│   │   │   ├── settings_routes.py #   系统配置（headless/port 等）
│   │   │   ├── browser_routes.py  #   浏览器状态
│   │   │   ├── ai_routes.py       #   ★ /api/ai/* （ask/run/stream/sessions）
│   │   │   ├── pinduoduo_routes.py#   拼多多（登录/同步/库存）
│   │   │   ├── tu_routes.py       #   途强
│   │   │   ├── feishu_routes.py   #   飞书消息/Webhook
│   │   │   ├── order_1688_routes.py #  1688 订单
│   │   │   ├── taobao_routes.py   #   淘宝商品
│   │   │   ├── goofish_routes.py  #   闲鱼商品（发布 + 在线管理）
│   │   │   ├── antexiadan_routes.py # 安特限时秒杀
│   │   │   ├── scheduler_routes.py# 定时任务
│   │   │   ├── script_routes.py   #   脚本执行
│   │   │   └── websocket_routes.py#   Socket.IO 配置
│   │   └── service/               #   跨路由业务逻辑（飞书数据比对等）
│   │
│   ├── web/                       # Web 页面层
│   │   ├── routes.py              #   页面路由（返回 HTML 模板）
│   │   └── templates/
│   │       ├── base.html          #   基础布局（侧边栏 + 导航）
│   │       ├── index.html         #   首页
│   │       ├── settings.html      #   设置页
│   │       ├── scheduler.html     #   定时任务管理
│   │       └── tools/             #   各工具独立页面
│   │           ├── ai_assistant.html    # ★ AI 智能助手（聊天 UI + SSE 流式）
│   │           ├── pinduoduo.html
│   │           ├── spider.html
│   │           ├── tu.html
│   │           ├── order_1688.html
│   │           └── script_executor.html
│   │
│   ├── tools/                     # 工具注册层（Web UI 入口）
│   │   ├── base.py                #   BaseTool 基类
│   │   ├── manager.py             #   ToolManager（注册/查找工具）
│   │   ├── ai_tool.py             #   ★ AiTool（ai_assistant）
│   │   ├── pinduoduo_tool.py      #   拼多多工具
│   │   ├── tu_tool.py             #   途强工具
│   │   ├── order_1688_tool.py     #   1688 工具
│   │   ├── script_tool.py         #   脚本执行工具
│   │   ├── spider_tool.py         #   通用爬虫工具
│   │   └── feishu/                #   飞书 SDK 封装
│   │       ├── feishu_client.py   #   多维表格 CRUD
│   │       ├── feishu_table_client.py
│   │       ├── message_sender.py  #   私聊 / 卡片消息
│   │       └── webhook/           #   Webhook Bot
│   │
│   ├── spider/                    # 爬虫与业务逻辑层
│   │   ├── pinduoduo/
│   │   │   ├── client.py          #   PDD 核心客户端（Playwright + 飞书）
│   │   │   ├── erp_order_sync.py  #   ERP 订单同步
│   │   │   ├── inventory_sync_job.py # 库存飞书同步（调用 ai.ask）
│   │   │   ├── presell_sync.py    #   预售订单
│   │   │   ├── after_sale_sync.py #   退货订单
│   │   │   ├── audit_store.py     #   待审核 SQLite
│   │   │   ├── feishutable.py     #   飞书表字段映射
│   │   │   └── scripts/           #   JS 注入脚本（ERP 页面数据抓取）
│   │   ├── antexiadan/
│   │   │   ├── login.py           #   Playwright 登录门禁（ensure_logged_in）
│   │   │   ├── seckill_store.py   #   安特限时秒杀 MySQL
│   │   │   ├── goods_search.py    #   商品搜索 search-goods-list
│   │   │   └── goods_search_store.py # 商品搜索缓存
│   │   ├── order_1688/
│   │   │   └── order_extract.py   #   1688 订单提取
│   │   ├── taobao/                #   淘宝以图发品自动上架（Playwright）
│   │   │   ├── client.py          #   上架客户端（API/CLI 入口）
│   │   │   ├── flows/publish_one.py
│   │   │   ├── pages/             #   类目页 / 发布页 / 图片空间
│   │   │   └── data/              #   Excel 加载与回填
│   │   ├── goofish/               #   闲鱼卖家工作台（Playwright）
│   │   │   ├── client.py          #   GoofishClient（对外唯一入口）
│   │   │   ├── mtop_bridge.py     #   页面内直调 mtop（取数主路径）
│   │   │   ├── login_gate.py      #   mtop 探针登录门禁
│   │   │   ├── api_probe.py       #   运行时接口探测
│   │   │   ├── item_list.py       #   在线列表（mtop → 自动识别 → DOM 兜底）
│   │   │   ├── flows/             #   publish_one / manage_items
│   │   │   ├── pages/             #   发布页 Page Object
│   │   │   ├── data/              #   Excel 加载与回填
│   │   │   └── scripts/           #   DOM 兜底 JS + 离线 fixture
│   │   └── tu/
│   │       └── client.py          #   途强平台 Playwright 客户端
│   │
│   ├── scheduler/                 # 定时任务
│   │   ├── manager.py             #   APScheduler 封装
│   │   ├── task_config.py         #   任务类型注册 + 种子合并
│   │   └── tasks.json             #   任务种子（随包打入 exe）
│   │
│   ├── tray/
│   │   └── tray_icon.py           # 系统托盘图标（pystray）
│   │
│   ├── config/
│   │   └── modules.py             # 模块启用/禁用配置
│   │
│   └── utils/
│       ├── path_helper.py         # 安全路径（开发 vs exe 自动切换）
│       ├── logger.py              # 统一日志
│       ├── config_manager.py      # TOML 配置读写
│       ├── module_manager.py      # 模块动态启停
│       ├── browser_path.py        # Chromium 可执行文件路径
│       ├── websocket_client.py    # Socket.IO 客户端
│       ├── assistant_http_invoke.py # assistant_http 代理调用
│       └── startup.py             # 开机自启注册
│
├── data/                          # 运行时数据（.gitignore）
│   └── ai/sessions.json           # ★ Agent 会话持久化
├── scheduler/                     # 运行时任务配置（.gitignore）
│   └── tasks.json
├── logs/                          # 日志文件（.gitignore）
├── docs/                          # 文档
│   ├── log.md                     # 变更日志
│   ├── 开发指南.md
│   └── webauto脚本文档/
├── .env                           # 本地环境变量（不提交）
├── .env.example                   # 环境变量说明模板
├── app_config.production.toml     # 生产默认配置（打包时复制为 dist 中的 app_config.toml）
├── requirements.txt               # Python 依赖
└── main.spec                      # PyInstaller 打包配置
```

## 分层架构说明

```
┌─────────────────────────────────────────────────────────┐
│              桌面壳 (main.py / tray / webview)           │
├─────────────────────────────────────────────────────────┤
│         Web 页面层 (web/routes.py + templates/)          │
├──────────────────────────┬──────────────────────────────┤
│   HTTP API 层             │   AI 大脑层                   │
│   (api/routes/*)         │   (ai/)                      │
│                          │   ├─ LLM 问答 (client.py)    │
│                          │   ├─ Cursor SDK Agent         │
│                          │   │  (agent.py + sessions)   │
│                          │   └─ Playwright MCP Server   │
│                          │      (mcp/playwright_server) │
├──────────────────────────┴──────────────────────────────┤
│              业务逻辑层 (tools/ + spider/)                │
│   工具注册 ←→ 爬虫客户端 ←→ 飞书 SDK ←→ SQLite          │
├─────────────────────────────────────────────────────────┤
│    基础设施 (utils/ + scheduler/ + config/)              │
│    路径安全 | 日志 | 配置 | 定时任务 | Socket.IO 客户端   │
└─────────────────────────────────────────────────────────┘
```

## 安装与运行

### 环境要求

- **Windows 桌面版**：Windows 10/11 (64位)
- **Mac / Linux Web 控制版**：macOS 12+ 或主流 Linux，Python 3.10+ 推荐
- Python 3.8 或更高版本

### 安装步骤

1. **克隆或下载项目**

2. **创建虚拟环境**
```bash
python -m venv venv
```

3. **激活虚拟环境**
```bash
# Windows CMD
venv\Scripts\activate.bat

# Windows PowerShell
venv\Scripts\Activate.ps1
```

4. **安装依赖**
```bash
pip install -r requirements.txt
```

5. **安装 Playwright 浏览器驱动**
```bash
playwright install chromium
```

6. **配置环境变量**

```bash
# 复制环境变量模板
copy .env.example .env

# 编辑 .env，填入以下关键配置：
# ── 飞书通知（可选）──
# FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_USER_ID
#
# ── AI 大脑：LLM 简单问答（可选）──
# AI_BASE_URL=https://www.dmxapi.cn/v1
# AI_API_KEY=your_ai_api_key_here
# AI_STOCK_LINK_MODEL=qwen-flash-2025-07-28
#
# ── AI 大脑：Cursor SDK Agent（启用 AI 助手工具必填）──
# CURSOR_API_KEY=your_cursor_api_key_here   获取：https://cursor.com/dashboard/api
# CURSOR_MODEL=composer-2.5
```

7. **配置模块（可选）**

如果需要自定义启用的模块，可以配置模块：

```bash
# 复制模块配置模板
copy module_config.json.example module_config.json

# 编辑 module_config.json 文件，启用/禁用需要的模块
```

默认情况下，只启用了脚本执行和拼多多助手，快递查询模块已禁用。

### 运行应用

**Windows 桌面版**（托盘 + 原生窗口）：

```bash
python src/main.py
```

应用启动后：
- 会在系统托盘显示图标
- 自动打开窗口访问 `http://127.0.0.1:8889`
- 可以通过托盘图标控制应用

**Mac / Linux Web 控制版**（Flask + 系统浏览器，无托盘/pywebview）：

```bash
cd src
python -m venv ../venv
source ../venv/bin/activate   # Windows: ..\venv\Scripts\Activate.ps1
pip install -r ../requirements.txt
playwright install chromium
cp ../.env.example ../.env    # 填入 Nest、飞书等

# Mac 上使用淘宝/闲鱼模块时必填：
export TAOBAO_DATA_DIR="$HOME/电商数据/淘宝"
export GOOFISH_DATA_DIR="$HOME/电商数据/闲鱼"

python web.py
# 浏览器访问 http://127.0.0.1:8887（端口以 PORT / app_config.toml 为准）
```

说明：
- 入口为 [`src/web.py`](src/web.py)，不依赖 Windows 注册表与 pywebview
- Mac 可不安装 `pywebview`、`pystray`（若 `pip install -r requirements.txt` 报错，可跳过这两个包）
- 拼多多等 Playwright 功能需先执行 `playwright install chromium`
- `/health` 在非 Windows 上 `startup_enabled` 为 `false`（开机自启仅 Windows 支持）

**开发模式**（热重载，端口 8886）：

```bash
cd src && python dev.py
```

## 使用说明

### AI 智能助手

入口：侧栏「AI 智能助手」或 `/tools/ai_assistant`。

**两种工作模式**：

| 模式 | 触发条件 | 底层引擎 | 适用场景 |
|------|---------|---------|---------|
| 问答模式 | 默认（不勾选工具） | OpenAI 兼容 LLM（`AI_API_KEY`） | 文本分析、问答、数据解读 |
| Agent 模式 | 勾选「浏览器控制」 | Cursor SDK + Playwright MCP（`CURSOR_API_KEY`） | 网页操作、截图、自动化任务 |

**会话持久化**：同名 session 跨页面自动 resume 同一 Cursor Agent。

**爬虫移交协议**：当爬虫遇到验证码、登录失效等障碍时，可把当前浏览器状态交给 Agent 接管：

```python
from ai import run_agent

result = await run_agent(
    "帮我处理验证码并继续抓取订单",
    tools=["playwright"],
    browser_context={
        "url": page.url,
        "cookies": await page.context.cookies(),
        "screenshot": await page.screenshot(),
    }
)
```

**API 接口**：
- `POST /api/ai/ask` — LLM 简单问答
- `POST /api/ai/run` — Agent 同步运行
- `POST /api/ai/run-stream` — Agent SSE 流式输出
- `GET /api/ai/sessions` — 列出持久化会话
- `DELETE /api/ai/sessions/<name>` — 删除会话

### Web界面

1. 启动应用后，浏览器会自动打开Web界面
2. 左侧导航栏显示所有可用工具
3. 点击工具名称进入相应工具页面
4. 在工具页面使用相应功能
5. **定时任务**（`/scheduler`）：查看/新增 APScheduler 任务；需 `SCHEDULER_ENABLED` 为真且应用保持运行，任务才会在指定时间触发

### 拼多多助手

拼多多助手提供商家后台自动化管理功能，支持登录管理和飞书通知。

**功能特点**：
- 🔐 **登录管理** - 支持扫码登录，Cookie持久化保存
- 📢 **飞书通知** - 登录失效时自动发送飞书消息提醒
- 💾 **状态记录** - 记录最后执行状态，基于执行结果判断登录有效性
- 🔄 **自动化执行** - 执行时自动检测登录状态，登录成功后自动抓取最近30天订单数据
- 📦 **数据缓存** - 自动将抓取的订单数据缓存到本地，支持后续离线查看和处理
- 🔒 **安全存储** - Cookie、状态文件和缓存文件自动保存到用户数据目录，避免权限问题

**使用步骤**：

1. **配置飞书通知**（可选）
   - 创建飞书应用并获取凭证
   - 在 `.env` 文件中配置飞书应用信息
   - 如不配置，工具仍可使用，但不会发送通知

2. **首次登录**
   - 打开拼多多助手页面
   - 点击"重新登录"按钮
   - 扫描显示的二维码
   - 登录成功后Cookie自动保存

3. **查看状态**
   - 页面显示最后执行状态
   - 显示最后成功/失败时间
   - 绿色表示登录有效，红色表示需要重新登录

4. **自动化操作**（后续扩展）
   - 执行自动化操作时会自动检测登录状态
   - 如被拦截到登录页面，自动发送飞书通知
   - 需要重新登录后才能继续使用

**订单同步（ERP）**：

- 侧栏进入 **订单同步**，或访问 `http://127.0.0.1:8889/pdd-erp-order-sync`（端口以实际配置为准）。
- 使用 `src/spider/pinduoduo/scripts/pdd-erp-order-all-table.js` 在 `https://mms.pinduoduo.com/erp/order/all` 页抓取 `beast-core-table` 数据；默认写入飞书表 `tblyAX9t4DJK2wuJ`（与视图 `vew1HQrDsN` 同属应用 `ORSHbpajoaANQ4sFg25c917jnTc`），可通过环境变量 `PINDUODUO_ERP_FEISHU_TABLE_ID` / 页面输入覆盖。
- 若被登录拦截：发送飞书提醒、Webhook 卡片（若已配置）、并返回二维码供页面展示（与「同步 PDD 订单地址」一致）。
- 飞书写入若有失败，`feishu_sync.message` 与接口 JSON 中的 `feishu_sync.failed_order_sns` 会列出对应**平台订单号**；应用日志与定时任务摘要中也会打印「失败订单号」行。
- 新建行时默认**不传**「发货剩余」至飞书（`feishutable.ERP_FEISHU_OMIT_FIELD_KEYS`），避免表内未建该列时出现 `FieldNameNotFound`；若日后在多维表格增加同名列，可从该集合中移除对应字段名。
- **定时同步**：侧栏 **定时任务** 中类型为「拼多多 ERP 订单同步」的任务会按 cron 调用 `POST /api/pinduoduo/sync-erp-orders`。仓库种子 `src/scheduler/tasks.json` 含一条 **`0 12,18 * * *`**（每天 12:00 与 18:00）。首次运行若用户数据目录无 `scheduler/tasks.json`，会从种子复制；若你已有旧配置，需在定时任务页手动添加该任务或删掉旧文件后重启。每次执行结束会向飞书 **私聊**（`.env` 中 `FEISHU_USER_ID`，须为有效 open_id 等）发送结果摘要；未配置飞书则仅写日志。任务 `data` 可选：`url`（默认本机 API）、`data`（请求体）、`timeout`（默认 780 秒）、`feishu_user_id`（覆盖默认接收人）。

**库存飞书同步（定时，无需浏览器）**：

- 逻辑在 `src/spider/pinduoduo/inventory_sync_job.py`：读取飞书 ERP 全部店铺表（默认 `tblyAX9t4DJK2wuJ`），对「付款时间严格晚于配置日整天」且有平台订单号的行，在 **库存信息表** 中按订单号补建记录，并在 **扣减库存日志表** 中维护出库/退货等列（与表内已有值相同则跳过更新）。
- **表 ID**：库存信息表默认 `tbljLwzLLKafXl0h`，扣减日志表默认 `tblXXipFcgH1EQH7`，分别可用 `PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID`、`PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID` 覆盖（与你们飞书实际表不一致时必改）。
- **选配**：`PINDUODUO_INVENTORY_PAY_AFTER_DATE`（默认 `2026-04-07`，语义为仅 **4 月 8 日 0 点起**的付款满足条件）、`PINDUODUO_INVENTORY_LOG_REQUIRE_EXPRESS`（默认要求快递单号非空才写日志）、`PINDUODUO_INVENTORY_RETURN_KEYWORDS`（提醒列命中则写退货时间/数量）。
- **库存关联**（扣减日志表列）：用**库存信息表**中的短名称与 ERP「商品信息」算分。名称列默认依次尝试配置列、`商品名称`、`名称`、`产品名称` 及表头含「商品」且以「名称」结尾的列；也可用 **`PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD`** 指定与飞书完全一致的列名。**分数 ≥ `PINDUODUO_INVENTORY_STOCK_LINK_MATCH_MIN_SCORE`（默认 80）且解析到名称**时写入该名称原文。**达标但未解析到名称**时写说明。**未匹配**时写入 `未匹配(分数/阈值)｜原因：…｜商品信息：…｜店铺：…`。权重见 **`PINDUODUO_INVENTORY_STOCK_LINK_WEIGHTS_JSON`** 或 `data.stock_link_score_weights`。
- **手动触发**：`POST /api/pinduoduo/inventory-sync-from-erp-feishu`（JSON 可覆盖表 id、日期等，与任务 `data` 字段一致）。
- **定时任务**：种子含 **`pdd_inventory_sync_from_erp_feishu`**（`pdd_inventory_sync`，默认 **`enabled`: false**），表 id 有默认值；确认指向正确飞书表后在任务页启用并调整 cron 即可。

**API接口**：
- `GET /api/pinduoduo/status` - 获取最后执行状态
- `POST /api/pinduoduo/login` - 启动登录流程
- `GET /api/pinduoduo/check_login_complete` - 检查登录完成
- `POST /api/pinduoduo/logout` - 清除登录状态
- `POST /api/pinduoduo/execute` - 执行自动化操作（TODO）
- `POST /api/pinduoduo/sync-erp-orders` - ERP 全部订单表抓取并同步飞书（JSON 可选 `app_token`、`table_id`、`scroll_max_steps`）
- `POST /api/pinduoduo/inventory-sync-from-erp-feishu` - 仅飞书 API：ERP 表 → 库存信息表 + 扣减日志表（无需浏览器）

**定时执行（中午 12:00、下午 18:00）**：

- 侧栏 **定时任务** 读取的是**运行时**的 `scheduler/tasks.json`（开发环境一般为**项目根目录**下的 `scheduler/tasks.json`），与源码里的 `src/scheduler/tasks.json`（种子）不是同一路径；仅改 `src/scheduler/tasks.json` 时，若本地已有旧配置，需**重启应用**后由程序按版本合并缺失任务，或直接把 ERP 任务段复制进根目录 `scheduler/tasks.json`。
- 种子合并：首次启动或 `scheduler/.scheduler_seed_merge_version` 版本低于代码内版本时，会自动把种子里有、本地没有的 **任务 id** 追加进去（升级种子时需递增 `task_config._SCHEDULER_SEED_MERGE_VERSION`）。
- 任务类型 **`pdd_erp_order_sync`**：请求本机 `POST /api/pinduoduo/sync-erp-orders`，执行结束后向飞书 **`FEISHU_USER_ID`** 发一条结果摘要（需已配置飞书应用）。
- 任务类型 **`pdd_inventory_sync`**：进程内直接调用 `run_inventory_sync_job`（不调 HTTP）；库存/日志表 `table_id` 有默认值，可按需在 `.env` 覆盖并在任务页启用。

### 淘宝商品上架

基于 Playwright 的「以图发品」自动上架，数据来自 `C:\Users\yao\Desktop\work\电商数据\淘宝`（总表 `淘宝商品汇总.xlsx` + 单品目录 `商品信息.xlsx` + `images/`）。

**前置**：首次需在浏览器中登录淘宝/千牛卖家账号（复用 BrowserPool 持久化 Profile）。

**页面**：侧栏 **电商 → 淘宝上架**（`/tools/taobao`）

**CLI（在 `src` 目录）**：

```bash
python -m spider.taobao.cli --list-pending
python -m spider.taobao.cli --keyword "宋朝" --stop-after audit
python -m spider.taobao.cli --next-pending
```

**API**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/taobao/pending` | 待上架列表 |
| GET | `/api/taobao/login-status` | 检查卖家登录 |
| POST | `/api/taobao/publish` | 按 `keyword` 或 `title` 上架 |
| POST | `/api/taobao/publish-next` | 上架下一个待上架商品 |

步骤日志与失败截图：`data/logs/taobao-pw/YYYY-MM-DD/{商品slug}/`。

开发文档：`docs/淘宝商品上传/淘宝商品上传-Playwright开发文档.md`。

### 闲鱼商品

基于 Playwright 的闲鱼卖家工作台自动化，覆盖**商品发布**与**在线商品管理**两块。
数据来自 `C:\Users\yao\Desktop\work\电商数据\闲鱼`（总表 `闲鱼商品汇总.xlsx` + 单品目录 `商品信息.xlsx` + `images/`）。

**前置**：首次需在弹出的 Chromium 窗口扫码登录闲鱼卖家账号（复用 BrowserPool 持久化 Profile，日常 Chrome 的登录不算）。

**页面**：

- 侧栏 **电商 → 闲鱼发布**（`/tools/goofish`）：本地待发布队列、单条发布、发布下一个
- 侧栏 **电商 → 闲鱼商品管理**（`/goofish/items`）：在线商品列表、上下架、改价/改描述、删除（二次确认）

**取数策略**（返回体 `source` 字段标明实际路径）：

1. `mtop` — `config.ITEM_LIST_API` 已配置时用 `lib.mtop` 直调，分页可控，最可靠
2. `capture` — 未配置时打开列表页拦截 mtop 响应自动识别接口
3. `dom-fallback` — 前两者失败才回落 `goofish-item-list.js` 抓 DOM

**接口探测**：商品列表等接口只在登录后的 iframe 业务应用里加载，未登录拿不到。
登录后在管理页点「探测接口」（`POST /api/goofish/probe`），结果落在
`logs/goofish-pw/probe/<时间戳>/`，把商品列表接口名填进 `src/spider/goofish/config.py`
的 `ITEM_LIST_API` 即切到最可靠路径。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/goofish/login-status` | 登录态（mtop 探针判定） |
| GET | `/api/goofish/pending` | 本地待发布队列 |
| POST | `/api/goofish/publish` | 按 `keyword` / `title` 发布单条 |
| POST | `/api/goofish/publish-next` | 发布队列第一条 |
| POST | `/api/goofish/mark-uploaded` | 手动回填上架信息 |
| POST | `/api/goofish/probe` | 探测真实 mtop 接口 |
| GET | `/api/goofish/items` | 在线商品列表 |
| POST | `/api/goofish/items/<id>/online` / `offline` | 上架 / 下架 |
| POST | `/api/goofish/items/<id>/delete` | 删除（必须 `{"confirm": true}`） |
| POST | `/api/goofish/items/<id>/edit` | 改价 / 改描述 |

步骤日志与失败截图：`logs/goofish-pw/YYYY-MM-DD/{商品slug}/`。

**注意**：BrowserPool 是单线程单 page，闲鱼长任务会独占浏览器并阻塞其它模块，
批量操作请避开 12:00 / 18:00 的 ERP 定时同步。

离线测试（12 个用例，不依赖登录与网络）：

```bash
set PYTHONPATH=src
python -m unittest spider.goofish.test_item_list -v
```

开发文档：`docs/goofish/闲鱼模块-Playwright开发文档.md`；
后台探测记录：`docs/goofish/闲鱼后台-探测记录.md`。

### 途强助手

途强助手提供途强智能设备管理平台（https://iot.tqiot.com）的自动化功能，支持自动登录与最近 30 天记录获取。

**功能特点**：
- 🔐 **自动登录** - 使用配置的账号密码自动填充并提交登录
- 📄 **目标页面** - 自动打开 reportDown 页面（上报/下发相关）
- 📊 **最近 30 天记录** - 执行时自动获取最近 30 天记录并缓存到本地
- 💾 **状态与缓存** - 执行状态和记录缓存保存在用户数据目录

**配置说明**：
- 账号密码在 `src/config.py` 中配置（默认账号 18038361262），也可通过环境变量 `TU_ACCOUNT`、`TU_PASSWORD` 覆盖

**API接口**：
- `GET /api/tu/status` - 获取最后执行状态
- `POST /api/tu/execute` - 执行自动化（自动登录 + 获取最近 30 天记录）
- `POST /api/tu/logout` - 清除登录状态和 Cookie

### 系统托盘

- **双击图标**: 打开Web界面
- **右键菜单**:
  - 打开界面: 在浏览器中打开Web界面
  - 退出: 关闭应用

### API接口

应用提供完整的RESTful API接口，详见 [API文档](docs/PROJECT_DOCUMENTATION.md#8-api接口文档)

详细开发指南请参考：
- [开发指南.md](docs/开发指南.md) - 完整开发技术文档
- [配置说明.md](docs/配置说明.md) - 配置问题快速查找（系统托盘、开机自启动、打包配置）
- [浏览器超时配置说明.md](docs/浏览器超时配置说明.md) - 浏览器操作超时控制详细说明

主要接口：
- `GET /health` - 健康检查
- `GET /query?waybill=单号` - 单个查询
- `POST /batch` - 批量查询
- `GET/POST/DELETE /startup` - 自启动管理

## 打包为EXE

### 使用PyInstaller打包

1. **确保所有依赖已安装**

2. **打包应用**
```bash
pyinstaller main.spec
```

3. **打包输出**
- `dist/main/` - 打包后的应用目录
- `dist/main/main.exe` - 可执行文件

### 打包注意事项

- 确保Playwright浏览器驱动已安装
- 打包后的exe需要与浏览器驱动在同一目录
- **`.env`**：程序从 **exe 同目录** 读取 `.env`（含 `AI_BASE_URL`、`AI_API_KEY`、飞书等）。执行 `pyinstaller main.spec` 时若项目根已有 `.env`，会**自动复制**到 `dist/如意助手/`；若未复制，请手动把 `.env` 放到与 `如意助手.exe` 同一文件夹。
- **`app_config.toml`**：运行时在 **`如意助手.exe` 同目录** 读写（见 `config_manager`）。打包完成后 **`main.spec` 会将项目根的 `app_config.production.toml` 复制为 `dist/如意助手/app_config.toml`**（生产 Nest：`https://nestapi.xfysj.top`、`erp-001` 等）。修改线上默认值请编辑 **`app_config.production.toml`** 后重新打包；仅在 `dist` 里改会被下次全量清理覆盖。也可用 exe 同目录 **`.env`** 覆盖：`WS_CLIENT_HOST`、`WS_CLIENT_ASSISTANT_KEY` 等。
- **`cursor_sdk_bridge/`**：安特滑块 Agent 依赖的 Cursor SDK bridge（含 `node.exe`），打包后位于 **`dist/如意助手/cursor_sdk_bridge/`**（与 exe 同级）。构建前需 `.venv` 内已安装 `cursor-sdk`；打包版会自动设置 `CURSOR_SDK_BRIDGE_BIN`，也可在 `.env` 手动指定绝对路径。
- **库存映射**：`config/inventory_product_mapping.json` 会打入 `dist/如意助手/_internal/config/`（PyInstaller 6 onedir 模式）；代码通过 `get_bundled_data_root()` 读取默认值，用户修改的映射写入可写路径并与默认合并。
- **定时任务**：仓库根目录 `scheduler/tasks.toml` 会打入 `dist/如意助手/_internal/scheduler/`。重新打包前请在该文件中保存你的任务；若只改过 `dist` 里文件，`main.spec` 会清空 `dist` 后重建，未写回仓库的修改会丢失。
- **JS 注入脚本**：`src/spider/pinduoduo/scripts/` 目录会打入 `_internal/spider/pinduoduo/scripts/`；新增脚本文件时务必检查 `main.spec` 的 `datas` 是否已包含。
- 首次运行会自动添加到开机启动项

## 开发指南

### 添加新工具

1. **创建工具类**，继承 `BaseTool`:
```python
from tools.base import BaseTool

class MyTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            display_name="我的工具",
            description="工具描述"
        )
    
    def get_info(self):
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": "🔧"
        }
    
    def initialize(self, **kwargs):
        # 初始化逻辑
        return True
    
    def cleanup(self):
        # 清理逻辑
        pass
```

2. **注册工具**，在 `app.py` 中：
```python
from tools.my_tool import MyTool

tool = MyTool()
tool_manager.register_tool(tool)
```

3. **创建工具页面模板**，在 `web/templates/tools/my_tool.html`

4. **添加API路由**（如需要），在 `api/routes/` 下对应 Blueprint 中（如 `script_routes.py`、`feishu_routes.py`）

### 本地数据保存注意事项

**⚠️ 重要：所有需要保存到本地的数据文件必须使用安全路径处理**

#### 为什么需要安全路径

应用可能被安装在需要管理员权限的目录（如 `C:\Program Files`），直接在安装目录保存数据会导致权限错误。因此，**所有本地数据保存都必须使用安全路径工具**。

#### 使用方法

项目提供了 `src/utils/path_helper.py` 工具模块，所有需要保存本地数据的功能都应使用该工具：

```python
from utils.path_helper import get_safe_data_path, get_user_data_dir

# 方式1: 获取安全的数据文件路径（推荐）
# 会自动选择有写入权限的目录
file_path = get_safe_data_path('data/my_data.json')

# 方式2: 直接获取用户数据目录
user_dir = get_user_data_dir('如意助手')
file_path = user_dir / 'data' / 'my_data.json'
```

#### 路径选择逻辑

`get_safe_data_path()` 会自动选择安全的路径：

1. **开发环境且有权限**：使用项目根目录（便于开发调试）
2. **生产环境或无权限**：使用用户数据目录
   - Windows: `%LOCALAPPDATA%\如意助手\`（如 `C:\Users\用户名\AppData\Local\如意助手\`）
   - Linux: `~/.local/share/如意助手/`
   - Mac: `~/.local/share/如意助手/`

#### 应用场景

所有需要写入本地文件的场景都应使用安全路径：

- ✅ Cookie 文件
- ✅ 状态记录文件
- ✅ 缓存文件
- ✅ 配置文件（用户级）
- ✅ 数据库文件
- ✅ 临时文件
- ✅ 日志文件

#### 示例代码

```python
from pathlib import Path
from utils.path_helper import get_safe_data_path
import json

class MyTool:
    def __init__(self):
        # 获取安全的数据文件路径
        self.data_file = get_safe_data_path('my_tool/data.json')
        self.cache_file = get_safe_data_path('my_tool/cache.json')
        
        # 确保目录存在
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_data(self, data):
        """保存数据到本地"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存数据失败: {e}")
            return False
    
    def load_data(self):
        """从本地加载数据"""
        if not self.data_file.exists():
            return None
        
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载数据失败: {e}")
            return None
```

#### 参考实现

可以参考以下模块的实现：

- `src/utils/logger.py` - 日志文件的安全路径处理
- `src/spider/pinduoduo/client.py` - Cookie 和状态文件的安全路径处理

### 性能优化 - 延迟初始化

**⚠️ 建议：资源密集型组件应使用延迟初始化**

对于占用资源较多的组件（如浏览器客户端、数据库连接等），建议使用延迟初始化策略，只在实际使用时才创建实例。

#### 延迟初始化示例

```python
from typing import Optional

class MyTool:
    def __init__(self):
        self._client = None  # 不立即创建实例
    
    def get_client(self):
        """延迟初始化：首次调用时才创建实例"""
        if self._client is None:
            self._client = HeavyResourceClient()
        return self._client
    
    # 或者使用 @property 装饰器
    @property
    def client(self):
        """使用属性方式实现延迟初始化"""
        if self._client is None:
            self._client = HeavyResourceClient()
        return self._client
```

#### 延迟初始化的优势

1. **启动更快** - 应用启动时不创建未使用的资源
2. **节省内存** - 只创建真正需要的实例
3. **避免错误** - 延迟到使用时才处理可能的初始化错误
4. **按需加载** - 多用户环境下资源利用更高效

#### 参考实现

- `src/tools/pinduoduo_tool.py` - 拼多多客户端的延迟初始化
- `src/spider/pinduoduo/client.py` - 飞书发送器的延迟初始化（使用 `@property`）

## 配置说明

在 `src/config.py` 中可以配置：

- `HOST`: 服务地址（默认: 127.0.0.1）
- `PORT`: 服务端口（默认: 8099）
- `HEADLESS`: 浏览器无头模式（默认: True）
- `AUTO_OPEN_BROWSER`: 启动时自动打开浏览器（默认: True）
- `TRAY_ENABLED`: 是否启用系统托盘（默认: True）

## 常见问题

### 1. 浏览器驱动未找到

**问题**: 提示 "Playwright 浏览器驱动未安装"

**解决**: 运行 `playwright install chromium`

### 2. 端口被占用

**问题**: 提示端口8099已被占用

**解决**: 修改 `config.py` 中的 `PORT` 配置，或关闭占用端口的程序

### 3. 系统托盘图标不显示

**问题**: 托盘图标未显示

**解决**: 
- 检查是否安装了 `pystray` 和 `Pillow`
- 检查系统托盘区域是否被隐藏
- 详细说明请参考 [配置说明.md](docs/配置说明.md#1-系统托盘配置右下角任务栏)

### 4. 开机自启动不生效

**问题**: 应用未在开机时自动启动

**解决**: 详细说明请参考 [配置说明.md](docs/配置说明.md#2-开机自启动配置)

### 5. 打包相关问题

**问题**: 打包后exe无法运行或功能异常

**解决**: 详细说明请参考 [配置说明.md](docs/配置说明.md#3-打包配置详解)

## 版本历史

详见 [log.md](docs/log.md)

## 许可证

本项目为内部使用项目。

## 联系方式

如有问题或建议，请联系项目维护者。
