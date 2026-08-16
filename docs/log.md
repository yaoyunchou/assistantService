# 变更日志

## 2026-08-06 - 拼多多桌面端 Cookie 复用调研（结论：不可行，保留代码默认关闭）

- **背景**：用户希望复用拼多多桌面客户端（`C:\Program Files (x86)\pinduoduo\PddWorkbench.exe`，内嵌 Chromium）的登录态，让助手每次进 ERP 时免扫码。
- **调研过程**：
  - 确认桌面端是 Chromium 104 内核（`pddbrowser104\chrome.dll`），通过运行进程命令行定位到 User Data 目录：`C:\Users\Public\Documents\PDD\PddBrowser104\User Data`，主 profile `StaticPddBrowser` 为空，登录态分散在多个 `cs_XXXXXXXX` profile（按店铺区分）
  - Cookie 用 AES-256-GCM 加密，主密钥用 Windows DPAPI 保护（`Local State` 的 `os_crypt.encrypted_key`）。本机已具备 `win32crypt` + `cryptography`，可成功解密
  - 写了通用模块 [`src/spider/pinduoduo/pdd_desktop_cookies.py`](../src/spider/pinduoduo/pdd_desktop_cookies.py)：读 `Local State` → DPAPI 解主密钥 → 复制 SQLite（避开浏览器锁）→ 解密 v10/v11 cookie → 转成 Playwright `add_cookies` 格式；自动挑「最近活跃且含 ERP 登录 cookie」的 profile
  - 端到端验证（`scripts/test_import_cookies_e2e.py`）：把桌面端 cookie 注入全新 Playwright context 后访问 `mms.pinduoduo.com/erp/order/audit`，**仍被重定向回登录页**；换 PddBrowser 风格 User-Agent 同样失败
- **结论**：桌面端 webview **没有 `PASS_ID` cookie**（MMS ERP 真正鉴权靠它），只有 `JSESSIONID` / `mms_b84d1838`（实为「授权店铺 ID 列表」非会话令牌）等。`PddWorkbench.exe` 是 C++ 外壳，通过**原生宿主注入 token/header** 鉴权 webview，这些 token 不落 Cookie 库，**无法被外部进程复制**。仅复制 Cookie 不能免扫码。
- **改动**：
  - 新增 [`src/spider/pinduoduo/pdd_desktop_cookies.py`](../src/spider/pinduoduo/pdd_desktop_cookies.py)：桌面端 Cookie 读取/解密/转换模块（含 `get_playwright_cookies` / `pick_best_profile` / `import_cookies_to_context`）
  - [`src/spider/pinduoduo/client.py`](../src/spider/pinduoduo/client.py)：`PinduoduoClient` 新增 `_import_desktop_cookies()`，并在 `show_login_qrcode`（非 `force_relogin`）前调用；注入后若仍在登录页会再尝试跳 ERP 验证会话
  - [`src/config.py`](../src/config.py)：新增 `PDD_DESKTOP_COOKIE_IMPORT`（**默认 0/关**）、`PDD_DESKTOP_USER_DATA_DIR`、`PDD_DESKTOP_PROFILE`
  - [`.env.example`](../.env.example)：新增「拼多多桌面客户端 Cookie 复用（实验性，默认关）」配置段
  - 新增脚本 `scripts/read_pdd_cookies.py` / `scan_pdd_profiles.py` / `test_pdd_cookies.py` / `test_import_cookies_e2e.py` / `dump_pdd_cookies.py` / `dump_all_domains.py` / `find_pdd_ua.py`（调研用，可留作运维诊断）
- **保留原因**：模块本身（DPAPI 解密 + Cookie 转换）是可复用基础设施；后续若走「共享 profile」方案（让 Playwright 直接用桌面端 User Data 目录，需关闭桌面端避免锁）仍可复用，故保留代码但默认关闭，不影响现有扫码流程
- **后续可选方向**：① 共享桌面端 profile（需关桌面端，有状态冲突风险）；② 继续优化扫码登录稳定性；③ 用桌面端原生协议（需逆向，成本高）

## 2026-08-04 - 拼多多扫码：出现「扫码成功」仍跳回登录页

- **日志证据**：曾打出「登录页已出现扫码成功提示」并 `goto /home`，随后 URL 变成 `login/?redirectUrl=.../home`，说明会话未真正建立就被拦回。
- **原因**：「扫码成功」多半只表示手机已扫、还需在 APP **确认登录**；此前把该文案当成已登录并立刻跳首页，会冲掉登录流程。
- **修复**：区分「已扫码待确认」与「登录成功/正在跳转」；前者只等待页面/其它标签自然跳转，不急着 `goto home`；跳转后若仍在 login 打明确 warning。二维码确认为页面 `.qr-code canvas` 截图。

## 2026-08-04 - 拼多多「重新登录」与二维码来源说明

- **二维码来源**：`show_login_qrcode` 对 **Playwright 内置 Chromium** 登录页截图（优先 `.qr-code canvas`），base64 给 Web 展示；与 APP 扫码会话绑定的是该后台窗口，不是用户桌面上的别的浏览器。
- **重新登录无效**：原逻辑只 `goto` 首页，Cookie 有效时直接 `ALREADY_LOGGED_IN`、不展示二维码；且与「刷新列表」共用单线程浏览器池，请求排队时按钮像没反应。
- **修复**：`POST /api/pinduoduo/login` 默认 `force: true`，打开 ERP 审核页/登录 URL 拉登录页；`ensure_visible`；超时 120s；前端点击即显示「正在打开登录页…」并提示勿与刷新并发。

## 2026-08-04 - 拼多多扫码登录：确认后前端无反应

- **现象**：APP 扫码并确认后，助手页仍显示「等待扫码」。
- **原因**：登录判定用整段 URL 含 `login` 即视为未登录；扫码成功后页面常短暂停在 `/login`，或只出现「扫码成功」文案未立刻跳转，轮询 `check_login_complete` 一直返回 `logged_in: false`。
- **修复**：`client.py` 改为按 **pathname** 判断是否登录页；识别登录页「扫码成功」等文案后 **主动 `goto` 商家首页**；放宽已登录路径（`/erp/`、`/orders` 等）；`GET /check_login_complete` 单次请求内 **最多轮询约 8s** 等待跳转。

## 2026-08-03 - 安特滑块截图识图后自动删除

- 每轮 attempt 在 Nest 识图/拖动流程结束后（`finally`）调用 `_remove_captcha_shot`，默认删除 `captcha_*.png`，避免 `antexiadan/captcha` 堆积。
- 配置 `ANTEXIADAN_CAPTCHA_DELETE_SCREENSHOTS`（默认开启）；联调保留样本可 `.env` 设 `0`/`false`。
- `.gitignore` 忽略 `antexiadan/captcha/*.png`、`nest_ai_chat_body.json`。

## 2026-08-03 - 安特滑块 Nest 切回线上 API

- 本地 `localhost:8080/api/v1` 多模态联调完成；`.env` / 打包 `.env` 改回 `NEST_API_BASE=https://nestapi.xfysj.top/xcx/api/v1`。
- 移除 `APP_ENV=development` 时强制本机 Nest 默认；未配置时由 `nest_client.resolve_nest_api_base()` 走线上默认。

## 2026-08-03 - 安特滑块拖动距离默认 -5px 修正

- `ANTEXIADAN_CAPTCHA_DRAG_OFFSET_PX` 默认 **-5**（Nest 识图后、随机抖动前叠加）；可 `.env` 改为 `0` 或其它值。

## 2026-07-31 - 安特滑块截图：iframe 优先 + 有效性校验

- **认知**：安特登录页上 `#tcaptcha_iframe` 即腾讯验证框本体；此前「先截外层 `#t_dialog`」易在 iframe 未就绪时用 clip 裁到主站侧栏（约 5KB 废图）。
- **实现**：[`captcha_solver.py`](../src/spider/antexiadan/captcha_solver.py) 等待 iframe/滑块就绪后**优先截 iframe**；外层弹框仅作含「安全验证」文案的兜底；截图后校验体积（≥12KB）与尺寸；修复误删的 `_clip_from_box`。
- **提示词**：明确 `distancePx = 缺口中心 x − 拼图块中心 x`（360 截图坐标、与拖动 1:1）；`test_nest_captcha_image.py` 与线上一致。样图 `captcha_1785491027_1.png` 本地 Nest 复测约 **195**（旧 prompt 曾 **160**，目测约 **224~227**）。
- **提示词 v2**：写入 5 步测距（x₁/x₂）；JSON 增加 `pieceCenterX`/`gapCenterX`。注意：**长 prompt 不等于更准**，且与 Nest 客户端 Cursor Agent 不是同一路径。
- **Nest 传参**：`nest_ai_chat` 仅传 `message`（text+image_url detail=high）、`systemPrompt`；可选 `NEST_CHAT_MODEL` → body `model`。
- **本地 Nest**：`NEST_API_BASE=http://localhost:8080/api/v1`；多模态 `/ai/chat` 经 Cursor Agent **单次约 4～5 分钟**属正常；默认 `NEST_CHAT_TIMEOUT_MULTIMODAL=360`。
- **config 循环导入**：`config.py` 不再在 exec 时加载 toml，改由 `config/__init__.py` 导出后再 `_load_config_from_file()`。

- **本地 `.env`**：已移除 `CURSOR_API_KEY` / `CURSOR_MODEL`；Nest 使用 `NEST_DEVICE_KEY`（非 JWT）。`nest_client` 接受登录/聊天 **HTTP 201**，并兼容误写在 `NEST_JWT` 的设备密钥。
- **Nest 鉴权**：原误写在 `NEST_JWT` 的 device key 已迁至 `NEST_DEVICE_KEY`；`nest_client._login_fresh` 兼容误标 JWT 并提示改名。

## 2026-07-31 - 全项目 AI 统一走 Nest API（移除本地 Cursor Agent）

### 变更说明

- **`src/ai/__init__.py`**：`ask` / `ask_vision` / `run_agent` / `run_agent_stream` 全部转发 **Nest** `POST /xcx/api/v1/ai/chat`（`integrations.nest_client`）；`tools=playwright` 仅打日志，不在本机执行。
- **`src/ai/agent.py`**：瘦身为兼容层，不再依赖 `cursor-sdk`。
- **安特滑块**、**拼多多库存 AI 匹配**：仅认 `NEST_DEVICE_KEY`（或账号密码 / JWT）。
- **打包**：`main.spec` / `setup.iss` 不再复制 `cursor_sdk_bridge`；`requirements.txt` 注释 `cursor-sdk`。
- **配置**：`.env.example` 以 `NEST_*` 为主；`CURSOR_API_KEY` 保留读取但已弃用。

## 2026-07-31 - 安特滑块识图改为 Nest `/ai/chat`（默认）

### 变更说明

- **背景**：打包版本地 Cursor SDK Agent（`cursor_sdk_bridge`）识图不稳定；Nest 小程序/CMS 侧 `/ai/chat` 多模态效果更好。
- **实现**：
  - 新增 [`src/integrations/nest_client.py`](../src/integrations/nest_client.py)：`device-key`/账号登录、`/ai/chat`（截图 base64 + OpenAI 风格 `image_url`）、`extract_chat_text` 解析响应。
  - [`captcha_solver.py`](../src/spider/antexiadan/captcha_solver.py) 默认 `ANTEXIADAN_CAPTCHA_AI_BACKEND=nest`；可降级 `cursor` / `vision`。
  - `config.py` / `.env.example` 增加 `NEST_*` 与 backend 开关；[`main.spec`](../main.spec) 说明 bridge 非滑块必需。
- **配置（打包推荐）**：`NEST_DEVICE_KEY=keyId.secret`，`NEST_API_BASE=https://nestapi.xfysj.top/xcx/api/v1`（可省略，由 `WS_CLIENT_HOST` 推导）。
- **联调**：`scripts/_spike_nest_ai_chat.py` 可本地验证多模态 body（需有效 `NEST_JWT` 或 `NEST_DEVICE_KEY`）。

## 2026-07-28 - 新增闲鱼（Goofish）模块：商品发布 + 在线商品管理

### 概述

新增 `src/spider/goofish/`，对接[闲鱼卖家工作台](https://seller.goofish.com/)，交付两块能力：
本地 Excel 队列**商品发布**（`/tools/goofish`）与**在线商品管理**（`/goofish/items`，上下架 / 改价改描述 / 删除）。

### Phase 0 探测的三个关键发现（决定了实现方式）

对未登录态站点与前端 bundle（`idle-pc/seller-workbench/0.1.56`）做了静态分析，产出
`docs/goofish/闲鱼后台-探测记录.md`。三个发现直接改变了原定方案：

1. **`lib.mtop` 全局可用且可直调** —— 实测 `window.lib.mtop.request({api, v, data})` 可用，
   未登录时返回 `ret: ["FAIL_SYS_SESSION_EXPIRED::Session过期"]`。
   因此取数改为**直调 mtop 为主**（分页可控、不受 DOM 改版影响、复用页面签名），
   而不是原计划的「拦截 XHR 为主」；登录判定也改用 **mtop 探针**，比 URL/DOM 可靠得多。
2. **业务页在 iframe 内** —— shell 路由表只有 `login / iframe / im / ...`，**没有** `seller-item/publish`。
   发布页与列表页都由 `iframe` 路由承载，所以 DOM 操作必须先 `find_business_frame(page)`，
   在主 frame 上 `evaluate` 找不到表单。登录页主 frame 的 `innerText` 实测为**空**。
3. **class 名带 CSS Modules 构建哈希**（如 `loginPage--ScuLfa2N`），每次前端发版都变。
   已在 `config.py` 与 `pages/__init__.py` 立为硬性约束：禁止哈希 class 选择器，
   只用稳定 ID / 语义属性 / 文本匹配。

商品列表、发布、上下架接口**不在** shell bundle 里（只在登录后的 iframe 应用中加载），
未登录态确实拿不到 —— 这部分交由下述探测器自助补全。

### 主要文件

- **`src/spider/goofish/`**
  - `config.py` — URL / 选择器 / mtop 接口名 / 缺省值集中配置，改版单点修正
  - `mtop_bridge.py` — 页面内直调 mtop，识别 `SUCCESS` 与 `SESSION_EXPIRED`
  - `page_guard.py` — mtop 探针登录判定、业务 iframe 定位、窗口最大化
  - `login_gate.py` — `ensure_logged_in`，支持轮询等待扫码
  - `api_probe.py` — 运行时接口探测，把「登录后才可见的接口」变成一键自助采集
  - `item_list.py` — 三级取数：`mtop` 直调 → `capture` 自动识别 → `dom-fallback`
  - `flows/publish_one.py`、`flows/manage_items.py`、`pages/publish_page.py`
  - `data/loader.py`、`data/backfill.py` — Excel 队列与回填（openpyxl 只写目标单元格）
  - `scripts/goofish-item-list.js`、`scripts/goofish-item-action.js`（上下架/删除合并为一个脚本 + `action` 参数）
  - `test_item_list.py` + `scripts/fixtures/` — 12 个离线用例
- **`src/api/routes/goofish_routes.py`** — 13 个端点，业务失败统一 `200 + {ok:false}`
- **`src/tools/goofish_tool.py`**、**`src/web/templates/tools/goofish.html`**、**`src/web/templates/goofish_items.html`**
- **文档** — `docs/goofish/闲鱼模块-Playwright开发文档.md`、`docs/goofish/闲鱼后台-探测记录.md`

### 集成改动

| 文件 | 改动 |
|------|------|
| `main.spec` | `_pack_datas` 加 `spider/goofish/scripts`（否则打包后 JS 丢失，运行时 `FileNotFoundError`） |
| `src/web/templates/base.html` | 三处工具名元组加 `'goofish'`、`_ec_endpoints` 加 `'goofish_items'`（否则闲鱼会同时出现在「电商」和「工具」两个分组）；电商分组加两个入口 |
| `src/notify/__init__.py` | `_SOURCE_DISPLAY` 加 `"goofish": "闲鱼助手"` |
| `src/api/routes/__init__.py` | 注册 `goofish_bp` + Swagger tag「闲鱼」 |
| `src/app.py` | `init_tools()` 注册 `GoofishTool` |
| `src/web/routes.py` | 新增 `/goofish/items` 路由 |
| `README.md` | 功能列表、目录树、模块说明 |

`src/config/modules.py` **未**加 `goofish` 条目 —— 与 `taobao` 保持一致（浏览器池已因
`pinduoduo.requires_browser=True` 必然启动，加了还需同步 exe 旁的 `module_config.toml`）。

### 几个刻意的设计选择

- **发布点了但解析不到商品 ID** → 返回 `needs_manual_check: True` 而非失败，
  提示用人工确认 + `mark-uploaded` 回填。若报成失败，用户重试会造成**重复铺货**。
- **价格不做「分转元」猜测**（`item_list._norm_price`）—— 接口价格单位未经登录态确认，
  而该值会回显到编辑弹窗，猜错就是直接改错价。单位确认后再统一换算。
- **选择器定位不到就抛错**，错误信息里直接写「怎么补全」（跑探测 + 改 config），
  不静默点就近元素。非致命属性（成色/分类/包邮）未命中只记 warning，不中断整单。
- **删除强制 `confirm: true`**，前端另有二次确认弹窗；JS 脚本在 `confirm=false` 时只做定位演练。

### 验证

- `python -m unittest spider.goofish.test_item_list -v` → **12 passed**
  - 该测试抓到一个真实 bug：DOM 脚本把标题「机械键盘 **87**键」里的 87 当成了价格。
    已改为价格必须带货币符号，无符号时先剔除标题再找裸数字。
- Flask 集成自检：13 个闲鱼路由全部注册；`/tools/goofish` 与 `/goofish/items` 均渲染 200；
  侧边栏两个入口就位且未在「工具」分组重复；无汇总表时 `/api/goofish/pending` 返回 200 + `ok:false`（不是 500）。

### 待办（需登录态校准）

发布表单精确选择器、`ITEM_LIST_API`、价格单位、`ITEM_URL_TEMPLATE` 详情域名、成色/分类枚举文案。
登录后在管理页点一次「探测接口」即可采集，详见开发文档第 6 节。

## 2026-07-27 - 安特采集页卡住：登录已成功但前端仍「采集中」

- **现象**：浏览器已登录成功，功能页一直显示「打开浏览器采集中」无响应。
- **根因**：后端滑块第 1 次拖动失败后仍在循环（最多 5 次 × 每次 Agent ~50s）；`has_captcha` 对隐藏 iframe 误判；未检测「已离开登录页」导致手动/自动登录成功后仍继续调 Agent。
- **修复**：`login.has_captcha` 仅在登录页且元素可见时判真；`captcha_solver` / `do_login` 在每次重试前检测已登录则立即通过；前端提示改为「最多约 10 分钟」并显示已等待秒数。

## 2026-07-24 - Cursor Bridge 黑窗：关闭后 AI 失效

- **现象**：运行助手时弹出黑色控制台；窗口开着时 AI/滑块识别正常，关掉后报 `WinError 10061`。
- **根因**：Cursor SDK 通过 `cursor-sdk-bridge.cmd` 启动 `node.exe`，Windows 会附带控制台；用户关闭该窗口等于终止 Bridge 进程。
- **修复**：`src/ai/agent.py` 对 `Bridge.launch` 打 `CREATE_NO_WINDOW` 补丁，Bridge 后台启动不再弹黑窗；`.env.example` 补充可选 `CURSOR_SDK_BRIDGE_BIN` 说明（打包版默认自动设置，不必写进 `.env`）。

## 2026-07-16 - 打包版安特滑块：打入 cursor-sdk-bridge（方案 B）

- **现象**：`dist/如意助手` 跑安特登录滑块时 Agent 报错 `Unable to locate cursor-sdk-bridge`，滑块从不拖动（日志只有「Agent 未返回有效 distancePx」+ 点刷新）。
- **根因**：PyInstaller 只打了 `cursor_sdk` Python 包，未包含 wheel 自带的 `_vendor/bridge/`（含 `node.exe` + `cursor-sdk-bridge.cmd`，约 126MB）。
- **修复**：
  - **`main.spec`**：打包后复制 `cursor_sdk/_vendor/bridge` → `dist/如意助手/cursor_sdk_bridge/`（与 `playwright_drivers` 同级）；`hiddenimports` 补充 `cursor_sdk` 相关模块。
  - **`src/ai/agent.py`**：打包版（`sys.frozen`）启动 Agent 前自动设置 `CURSOR_SDK_BRIDGE_BIN` 指向 `exe同目录/cursor_sdk_bridge/bin/cursor-sdk-bridge.cmd`。
  - **`setup.iss`**：安装包一并打入 `cursor_sdk_bridge/`。
- **验证**：重新 `build.bat` 后，日志应出现 `已设置 CURSOR_SDK_BRIDGE_BIN=...` 和 `第 X/Y 次拖动滑块 distancePx=...`。

## 2026-07-16 - 新增「已发货数据补录」操作手册（复盘为什么这次弄了很久）

- **背景**：补录 2026-07-15 数据这件「本应很常见」的小事，实际排查链路很长（虚拟滚动漏单、助手跑的是旧打包 EXE、Nest base path 少了 `/xcx` 前缀等好几个独立坑叠在一起）。用户要求把经验总结成文档，避免下次重复排查。
- **新文档**：`docs/pinduoduo-erp-delivered-backfill-runbook.md`
  - TL;DR：以后补任意一天数据，只需 `run_delivered_sync_standalone.py`（抓）+ `push_erp_delivered_to_nest.py`（写库）两条命令。
  - 复盘表格：列出这次 6 个卡点、现象、根因。
  - 「关键事实」清单：抓数据/写库解耦、Nest 真实网关前缀 `/xcx/api/v1`、三种鉴权方式、默认筛选「已打印」的坑、助手可能跑的是旧 EXE 而非 `src/` 源码等——都是一次性排查出来、以后不该再重复验证的事实。

## 2026-07-16 - 直连 Nest 补录 2026-07-15 已发货数据（跳过助手转发链路）

- **背景**：`backfill_erp_delivered.py` / 独立脚本走「助手浏览器打开 ERP 页」这条链路时反复 `Page.goto` 超时（登录态/浏览器实例卡死等环境问题），且走 Nest 的 `today-printed-query` 也要先经 Socket 转发给在线助手，等于同一条脆弱链路。
- **改法**：Nest 侧文档（`https://nestapi.xfysj.top/xcx/api-json`）里其实还有一个**直接写库、不用助手**的接口：`POST /xcx/api/v1/assistant/pinduoduo/erp-delivered/today-printed-records`（`ErpDeliveredTodayPrintedRecordController_create`，按 `orderNo` upsert）。已用 `scripts/run_delivered_sync_standalone.py` 独立抓到的 2026-07-15 全量 50 条真实数据（`data/erp_delivered_2026-07-15.json`），直接映射字段后逐条 POST 进这个接口，不再依赖助手浏览器。
- **新脚本**：`scripts/push_erp_delivered_to_nest.py`
  - 字段映射：本地抓取行 → `CreateErpDeliveredTodayPrintedRecordDto`（`orderNo/actualAmount/erpOrderNo/express/goods[imgSrc,qty,spec,title]/imgUrl/orderStatus/printStatus/shippingTime/shopName`），字段名几乎一一对应。
  - 鉴权：支持 `--jwt` / `--device-key`（`/auth/login-with-device-key`，推荐用于自动化）/ `--username`+`--password`（`/auth/login`）三种换取 Nest `access_token` 的方式；也可用 `.env` 里的 `NEST_JWT` / `NEST_DEVICE_KEY` / `NEST_USERNAME`+`NEST_PASSWORD`。
  - **易错点**：Nest 真实网关路径带 `/xcx` 前缀——`https://nestapi.xfysj.top/xcx/api/v1/...`；Swagger JSON 里的 `paths` 键（`/api/v1/...`）不含这个前缀，直接拼会全部 404。
  - `--dry-run` 只打印第一条 DTO 不发请求；失败的行会落盘到 `<file>_push_failed.json` 方便重试。
- **验证**：50/50 推送成功（HTTP 201），随后用 `GET .../today-printed-records?shippingDateStart=2026-07-15&shippingDateEnd=2026-07-15` 查询 `total=50`，确认库里数据已从 35 条修复为完整 50 条。

## 2026-07-16 - 已发货同步：35/50 漏单根因与补抓

- **澄清**：库里的发货数据来自 `POST /api/pinduoduo/erp-delivered/today-printed-query`（`pdd-erp-order-delivered-query.js`），不是待发货 `pending-list`（不入库）。
- **漏数原因**：
  1. 默认筛「已打印快递单」——未打印单不会进库（50 发货可能只有 35 已打印）；
  2. 旧滚动只改 `scrollTop`、连续 3 步无新增就停，虚拟列表易提前结束。
- **修复**：`delivered-query` 改为 `scrollTop+wheel`、连续 5 步才停；读页脚「共 N 条」；不足则翻「下一页」继续采；返回 `pageTotal`/`incomplete`。
- **补数脚本**：`python scripts/backfill_erp_delivered.py --date-shortcut 昨天`（或双击 `scripts/backfill_erp_delivered_2026-07-15.bat`）；Nest 落库加 `--via-nest`。须助手浏览器能打开 ERP。

## 2026-07-16 - 待发货列表：虚拟滚动漏单修复

- **现象**：`pdd-erp-order-delivering-list-query.js` 只采当前视口 DOM；以 2026-07-15 共 50 单为例，视口约 12 行时旧逻辑只能拿到约 12 条。
- **复现**：`node src/spider/pinduoduo/scripts/_test_delivering_scroll_logic.js`（旧 12 / 新 50）。
- **单元测试**：仓库根目录执行：
  ```bat
  set PYTHONPATH=src
  python -m unittest spider.pinduoduo.test_delivering_list_query -v
  ```
  或 `python src/spider/pinduoduo/test_delivering_list_query.py`（Playwright + `fixtures/delivering-virtual-list.html`，断言静态 &lt;50、滚动=50）。
- **修复**：默认 `scrollTop + wheel` 滚动采集，按 `orderNo` 去重；连续 3 步无新数据触底停止；测试可覆盖 `MIN/MAX_WAIT_MS`。
- **入口**：`run_delivering_list_query` / `POST /api/pinduoduo/erp-delivering/pending-list` 支持 `autoScroll`、`scrollMaxSteps`、`scrollPauseMs`；响应增加 `count`、`scroll`。
- **文档**：`docs/pinduoduo-erp-remote-api.md` §3.5。

## 2026-07-10 - 预售抢购候选：仅未标记预售单

- **问题**：候选列表混入了「正在预售·未下架」秒杀池，已标记（已采购）的预售单对应商品会以无单号行再次出现。
- **规则**：只展示 `purchased=0` 且对照命中的条目；跳过 `purchased=1`；不再补充无预售单关联的秒杀商品。
- **文件**：`presale_rush.py`、`antexiadan_presale_rush.html`、API 摘要文案。

## 2026-07-10 - 预售×秒杀匹配：性别 + 品类硬约束

- **问题**：`title_overlap` 仅靠「国内一线代工女士无痕」等营销前缀，把文胸误配成内裤。
- **数据依据**：当前 online 未标记预售 9 条、秒杀中约 30 条；原对照命中 2 条均为文胸↔内裤误配；货号命中 0；秒杀大量无性别/无品类（美妆）。
- **规则**：双方都能识别到性别且不一致 → 否决；双方都抽到互斥叶子品类（文胸/内裤/上衣/裤子/鞋子/拖鞋）且无交集 → 否决；**货号命中同样受此约束**。任一侧未知则不拦截。「内衣」作为父类可与文胸/内裤兼容。
- **其它**：归一化去掉「国内一线代工」等噪声；`title_overlap` 最短公共子串由 10 提到 12。
- **文件**：`src/spider/pinduoduo/presell_seckill_match.py`；返回增加 `matchGender` / `matchCategories` / `seckillGender` / `seckillCategories`。

## 2026-07-09 - 预售抢购：结算成功后标记预售单已采购

- **逻辑**：`checkout_cart` 成功（提交结算 / 进入支付页）后，按任务 `items[].presellOrderNo` 写 `erp_order_presell.purchased=1`。
- **存储**：`presell_store.mark_purchased(order_nos)`。
- **补标**：`POST /api/antexiadan/presale-rush/mark-presell`；创建计划时前端会带上 `presellOrderNo`。

## 2026-07-09 - 预售抢购：展示并带上颜色/规格

- **来源**：拼多多预售单 `goods[].spec`（如「肤透色,34码BC杯」）；对照命中后挂到候选商品。
- **页面**：候选表新增「颜色/规格」列；创建计划时写入任务 `items[].spec`。
- **加购**：详情页按规格片段尝试点选 SKU，再设数量并加入购物车。

## 2026-07-09 - 预售抢购：开售时间显示改为中文本地格式

- **现象**：分组标题出现 `Thu, 09 Jul 2026 21:20:00 GMT`（MySQL datetime 被 jsonify 成英文）。
- **修复**：`presale_rush.list_candidates` 用 `start_unix` 格式化为 `YYYY-MM-DD HH:mm`。

## 2026-07-09 - 安特预售抢购控制台（提前加购 + 到点结算）

- **页面**：`/antexiadan/presale-rush`，侧边栏「安特 → 预售抢购」。
- **流程**：选「正在预售」商品 → 按开售时间合并计划 → **开售前 20 分钟加购** → **开售时刻结算/提交**；支付页停住并发飞书通知。
- **数量**：能对上拼多多预售单则用规格里的 qty，否则 1；页面可改。
- **调度**：新任务类型 `antexiadan_presale_cart` / `antexiadan_presale_checkout`；Scheduler 支持一次性 `run_at`（DateTrigger）。
- **模块**：`src/spider/antexiadan/presale_rush.py`；设计见 `docs/superpowers/specs/2026-07-09-antexiadan-presale-rush-design.md`。
- **配置**：`ANTEXIADAN_PRESALE_CART_ADVANCE_MIN`（默认 20）。

## 2026-07-09 - 安特滑块：只截验证码弹框/iframe，仍用 Cursor Agent

- **保留**：识别仍走 Cursor Agent（实测准），不改方案。
- **优化**：截图优先 `#t_dialog` / `.tcaptcha-transform`，再 `#tcaptcha_iframe(_dy)`；元素截失败用 `page.screenshot(clip=...)`；**不再全页截图**。
- **效果**：Agent 读图更小更快，距离估算更聚焦弹框内容。

## 2026-07-09 - 安特滑块选择器：#tcOperation > div.tc-fg-item.tc-slider-normal

- **实测**：iframe 内滑块为 `#tcOperation > div.tc-fg-item.tc-slider-normal`，已作为首选选择器。

## 2026-07-09 - 安特滑块：进入腾讯 iframe 定位 #tcaptcha_drag_thumb

- **现象**：Agent 已返回 `distancePx`，但报「未找到滑块按钮」——验证整体在 `#tcaptcha_iframe` 内。
- **修复**：`captcha_solver` 优先 `frame_locator('#tcaptcha_iframe')` / `#tcaptcha_iframe_dy`，再找滑块；刷新也只点 iframe 内按钮；日志打印 frames 便于排查。
- **注意**：`bounding_box()` 已含 iframe 页面偏移，拖动仍用 `page.mouse`。

## 2026-07-09 - 安特滑块：Cursor Agent 最多尝试 5 次，失败发 Webhook

- **策略**：本页截图 → Cursor Agent 估算 `distancePx` → 本页拟人拖动；最多 5 次；仍失败发飞书 Webhook。
- **原因**：Agent 自带 Playwright MCP 是另一浏览器，不能直接操作登录页，故「识别归 Agent、拖动归本页」。
- **新增**：`src/spider/antexiadan/captcha_solver.py`；`login.handle_captcha` 替换人工等待。
- **配置**：
  - `ANTEXIADAN_CAPTCHA_MAX_ATTEMPTS`（默认 5）
  - `FEISHU_WEBHOOK_ANTEXIADAN`（可选，不配回退通用 Webhook）
  - 需 `CURSOR_API_KEY`
- **渠道**：`qudao_notify.CHANNEL_ANTEXIADAN`；关键词默认「安特」。

## 2026-07-09 - 安特登录后「安全验证」滑块：人工拖完再继续

- **现象**：点击登录后出现 `#t_mask` /「拖动下方滑块完成拼图」。
- **处理**：`login.py` 检测滑块后 `bring_to_front`，轮询等待遮罩消失（默认 120 秒），不自动破解。
- **配置**：可选 `ANTEXIADAN_CAPTCHA_TIMEOUT_SEC`（默认 120）；浏览器 `pool.execute` 超时提到 180s。
- **使用**：采集时请保持 Playwright 窗口可见，出现验证后手动拖完即可继续。
- **后续**：已升级为 Agent 自动尝试（见上条）。

## 2026-07-09 - 安特 Playwright 登录门禁（自动密码登录）

- **目标**：浏览器相关安特逻辑开始前先检查登录；未登录则自动密码登录，成功后再执行采集/搜索。
- **新增**：`src/spider/antexiadan/login.py`（`ensure_logged_in` / `do_login` / `is_logged_in`）。
- **挂接**：`seckill-list/fetch-browser`、`goods_search.capture_pcapi_credentials`（含预售对照批量搜索）。
- **配置**（`.env`）：
  - `ANTEXIADAN_USERNAME` — 手机号/账号
  - `ANTEXIADAN_PASSWORD` — 密码
- **登录页**：未登录访问 homepage 会跳到 `https://pc.antexiadan.com/login`；自动切「密码登录」后填表提交。
- **设计文档**：`docs/superpowers/specs/2026-07-09-antexiadan-login-gate-design.md`
- **注意**：修改后需重启服务；请在本地 `.env` 填入真实账号密码（勿提交 git）。

- **上传入口**：`https://item.upload.taobao.com/sell/ai/category.htm`（以图发品）；「打开以图发品」直达该页，已登录则无需再走 login.taobao.com。

## 2026-06-16 - 拼多多库存 AI 匹配改用 Cursor Agent

- **变更**：`inventory_sync_job._ai_match_product_name` 从 OpenAI 兼容 `ask()` 改为 `run_agent()`（Cursor SDK）。
- **配置**：需配置 `CURSOR_API_KEY` 与 `CURSOR_MODEL`；不再依赖 `AI_API_KEY` / `AI_BASE_URL` 做库存关联匹配。
- **行为**：新增 `_parse_ai_match_result` 解析 Agent 回复；日志前缀 `[Cursor AI匹配]`；同次任务 `ai_cache` 去重逻辑不变。
- **注意**：单次匹配耗时显著增加（数秒级），批量订单同步整体会变慢；修改后需重启 `dev.py`。

## 2026-06-16 - 上传确认条误匹配「确认，下一步」

- **现象**：报错 `上传确认条可见但未找到可点的确认按钮`，probe 为 `确认，下一步` 且 `disabled=true`。
- **原因**：`[class*="image-mode-footer"]` 误匹配类目页底栏，非 `#ai-category-image-mode-footer`；该类目按钮本就不能在上传阶段点击。
- **修复**：仅识别 `ai-category-image-mode-footer`；排除含「下一步」的底栏；等待真正上传确认条；移除 `set_viewport_size` 兜底避免 no_viewport 比例错乱。

## 2026-06-16 - 主图流程梳理（本地上传 → 审计 → 图库 1:1）

- **流程**：`flows/category_images.py` 统一三步——① 逐张本地上传+底部确认 ② 审计主图/更多图 ③ 主图不足则从图库勾选**最近 N 张**做 1:1 入主图。
- **日志**：`[主图流程]`、`[浏览器状态]` 写入 app 日志与 `step.jsonl`（`images_*` 阶段）。
- **调试浏览器**：上架时**不再关闭**用户手动打开的标签页；自动化占用主标签页时请在**新 tab** 手动操作。

## 2026-06-16 - 本地上传确认条不出现（绕过 image-mode）

- **现象**：选完文件后 `#ai-category-image-mode-footer` 始终不出现，底部确认按钮看不到。
- **原因**：页面存在 hidden `input[type=file]` 时代码直接 `set_input_files`，**跳过了「从本地上传」→ image-mode**；另 `dismiss_overlays` 的 Escape 会关掉 image-mode。
- **修复**：每张图必须「点从本地上传 → 文件选择器 → 等底部确认条 → 点确认」；去掉上传前 Escape；确认条轮询 60s + fixed 底栏兜底探测。

## 2026-06-16 - 淘宝浏览器窗口恢复默认最大化

- **现象**：`ai-category-image-mode-footer` 确认条在页面最底部，窗口较小时看不见、点不到。
- **原因**：BrowserPool 固定 `viewport=1920x1080` 与持久化窗口尺寸冲突；设置页 `window_width/height` 只影响助手桌面窗口，不影响 Chromium。
- **修复**：BrowserPool 改为 `no_viewport=True`（跟随真实窗口）；淘宝流程启动时 CDP 最大化；点击确认条前 `scrollIntoView`。
- **注意**：修改后需**重启** `dev.py`；若仍偏小，可在 Chromium 窗口手动拖大一次后会记住。

## 2026-06-16 - 本地上传缺少 ai-category-image-mode-footer 确认

- **现象**：选文件后页面应出现 `#ai-category-image-mode-footer` 确认条，但自动化未点击，审计 main/more 全 0。
- **原因**：`upload_one_local` 仅 `set_input_files` + sleep，未点确认条；`dismiss_overlays` 的 Escape 还可能误关确认条。
- **修复**：新增 `confirm_upload_footer()` 等待并点击确认条；确认条可见时跳过 dismiss/Escape；审计 debug 增加 `uploadFooter` 探测。
- **说明**：多数情况不是反爬，而是图片仍在「预览态」未入库；若确认条 30s 内仍不出现再排查登录/验证码/页面改版。

## 2026-06-16 - 淘宝非 1:1 主图补救未触发

- **现象**：3 张非 1:1 图本地上传后进「更多图片」，审计 `main=0 more=0 hint=null`，`needs_main_recovery=False`，未走图片空间补救即报「商品主图仍为空」。
- **原因**：补救闸门仅依赖 DOM 审计到的 `more_count` / `uploaded_hint`；页面结构或文案变化时审计漏数，本地上传张数未参与判断。
- **修复**：`should_recover_main()` — 本地上传后主图仍空则**强制**走图片空间；审计 JS 增加 relaxed 计数、多 hint 正则、`raw_debug`（section 预览、page CDN 图数）；上传/补救全流程加详细日志。
- **注意**：修改后需**重启** `dev.py` 调试进程。

## 2026-06-15 - 修复淘宝「已有上架链接」误报失败

- **现象**：点击上架时日志显示 `[publish] 失败 msg=商品已有上架链接，跳过`，但商品仍出现在待上架列表。
- **原因**：汇总表 `淘宝商品汇总.xlsx` 的「上架链接」为空，但单品 `商品信息.xlsx` 基本信息里已有链接（如 2026-05-27 回填）；`load_pending_products` 只查汇总表，而 `publish_one` 以单品链接为准跳过。
- **修复**：`load_pending_products` 加载单品后也排除已有链接的商品；跳过上架时输出详细日志（链接、时间、目录、是否同步汇总表），并自动将单品链接回填到汇总表；API 将 `skipped` 与真正失败区分日志级别（info vs warning）。
- **注意**：修改后需**重启** `dev.py` 调试进程。

## 2026-06-14 - 修复淘宝模块循环引用 ImportError

- **现象**：`POST /api/taobao/publish`、`GET /api/taobao/pending` 返回 500，`login_intercept` ↔ `browser_visible` 互相 import。
- **修复**：新增 `spider/taobao/page_guard.py` 集中 `is_login_page` / `is_category_page` / `focus_browser_page`；`login_intercept`、`browser_visible` 均改从 `page_guard` 导入；`taobao/__init__.py` 改为惰性加载 `TaobaoPublishClient`，避免包初始化时拉起整条依赖链。
- **注意**：修改后需**重启** `dev.py` 调试进程，否则仍可能命中旧模块缓存。

## 2026-06-14 - 修复淘宝操作误显示拼多多页面

- **原因**：BrowserPool 长驻复用同一 page，预热时 `bring_to_front` 仍停留在拼多多 ERP 登录页。
- **修复**：`prepare_taobao_browser` 强制 `goto` 淘宝 URL；移除 `ensure_visible` 的无导航预热。

## 2026-06-14 - 淘宝登录页不可见：强制弹出浏览器窗口

- **`BrowserPool.ensure_visible()`**：淘宝操作前自动关闭 headless、软重启并预热可见 Chromium。
- **`spider/taobao/browser_visible.py`**：`open_url_visible` / `focus_browser_page`。
- **`open-login` / `publish`**：调用前强制可见窗口；页面增加操作指引与 Alt+Tab 提示。

## 2026-06-14 - 修复淘宝上架 Web 端 500（未登录）

- **原因**：Web 请求 `pause_on_captcha=false`，未登录时直接失败；API 将 `ok:false` 当成 HTTP 500。
- **修复**：`login_intercept` 增加 `wait_login_timeout_sec` 轮询等待浏览器登录；`publish`/`publish-next` 默认 `wait_for_login=true`（180s）；业务失败统一返回 200 + `need_login`；页面展示明确提示。

## 2026-06-14 - 淘宝商品上架 Web 页面

- **`src/tools/taobao_tool.py`**、`src/web/templates/tools/taobao.html`：独立操作页（待上架列表、检查/打开登录、关键词上架、逐条/下一个上架、执行日志）。
- **`src/web/templates/base.html`**：电商分组新增 **淘宝上架** 菜单（`/tools/taobao`），从「工具」分组中排除避免重复。
- **`src/app.py`**：注册 `TaobaoTool`。
- **`POST /api/taobao/open-login`**：Web 页一键打开淘宝登录页。

## 2026-06-14 - 淘宝商品 Playwright 自动上架

- **`src/spider/taobao/`**（新增）：按 `docs/淘宝商品上传/淘宝商品上传-Playwright开发文档.md` 落地以图发品全链路——数据加载（`data/loader.py`）、图片审计与主图补救（`audit/image_lists.py`、`pages/media_popup.py`）、类目页上传（`pages/category_page.py`）、发布页填表提交（`pages/publish_page.py`）、备案号参考页抓取（`pages/reference_page.py`）、单商品状态机（`flows/publish_one.py`）、步骤日志（`step_logger.py`）。
- **数据目录**：`C:\Users\yao\Desktop\work\电商数据\淘宝`（总表 `淘宝商品汇总.xlsx` + 单品 `商品信息.xlsx` + `images/`）。
- **`src/api/routes/taobao_routes.py`**：新增 `GET /api/taobao/pending`、`GET /api/taobao/login-status`、`POST /api/taobao/publish`、`POST /api/taobao/publish-next`。
- **CLI**：`python -m spider.taobao.cli --list-pending` / `--keyword` / `--next-pending` / `--stop-after audit`。

## 2026-06-09 - ERP 待审核列表加锁（与小程序 order-center 共用）

- **`src/spider/pinduoduo/audit_lock_store.py`**：锁单读写改直连 Nest 共用 MySQL 表 `dictionary`（`category=pingduoduo`,`name=lockGoods`，与 `.env` 的 `DB_*` 一致）；DB 失败回退本地 `data/pdd_audit_locked_orders.json`；`validate_submit_order_nos` 供提交过滤。
- **锁状态回显修复**：`pinduoduo.html` 待审核列表拉完后再 `GET locked-orders`；`pickOrderNo` 与小程序字段对齐；PUT 成功后用服务端 `order_nos` 回写。
- **`src/api/routes/pinduoduo_routes.py`**：新增 `GET/PUT /api/pinduoduo/erp-audit/locked-orders`；**`POST /api/pinduoduo/erp-audit/submit`** 提交前拉取 lockGoods，**自动过滤已锁单号** 仅执行未锁订单；全被锁时 400；响应含 `skipped_locked_order_nos`。
- **`src/web/templates/tools/pinduoduo.html`**：待审核表格增加锁列；已锁订单不可勾选、排序置底、全选/提交均跳过；状态栏显示「已锁 N 单」。

## 2026-06-06 - 预售×秒杀对照排除已结束活动

- **原因**：选「全部」时会匹配 `activity_status=已结束` 或 `end_time` 已过的历史活动，仍显示「有秒杀」。
- **修复**：`list_products(exclude_ended=True)`；匹配循环内 `_is_seckill_active()` 二次校验。

## 2026-06-06 - 修复秒杀预购「全部」筛选无效

- **原因**：选「全部」时前端未传 `seckill_status`，后端 `get(..., '秒杀中')` 仍按「秒杀中」过滤。
- **修复**：前端始终传 `seckill_status`（空字符串表示全部）；后端仅在参数缺失时默认「秒杀中」。

## 2026-06-06 - 秒杀预购列表「适配」列展示活动时间

- **`pinduoduo_erp_presell_seckill.html`**：有秒杀匹配时在「适配」列显示 `start_time ~ end_time`。

## 2026-06-06 - 秒杀预购页联动安特商品搜索（方案 A）

- **`src/spider/antexiadan/goods_search.py`**（新增）：浏览器拦截 pcapi key，调用 `search-goods-list` 并 UPSERT；`ensure_goods_search` / `ensure_goods_search_batch`。
- **`src/spider/pinduoduo/presell_seckill_match.py`**：对照时按货号查 `antexiadan_goods_search`，无缓存则一次浏览器会话批量搜索；返回 `goodsSearch` / `searchKeyword` / `searchFromCache`。
- **`GET /api/pinduoduo/erp-order/presell-seckill-compare`**：默认 `use_goods_search=true`，传入浏览器池。
- **`POST /api/antexiadan/goods-search/fetch-browser`**、**`GET /api/antexiadan/goods-search`**：单条搜索入库与本地缓存查询。
- **`pinduoduo_erp_presell_seckill.html`**：新增「安特商品（搜索）」列，展示搜索词、goods_id、seckill_id、价格与缓存状态。

## 2026-06-06 - 安特商品搜索缓存表 antexiadan_goods_search

- **`docs/sql/antexiadan-seckill-db-schema.mysql.sql`**：新增 `antexiadan_goods_search` 表 DDL（按 keyword 唯一，缓存 search-goods-list 商品信息）。
- **`src/spider/antexiadan/goods_search_store.py`**（新增）：`init_db`、`get_by_keyword`、`get_by_keywords`、`upsert_from_search`、`upsert_from_api_response`、`list_records`、`serialize_row`。

## 2026-06-06 - 秒杀预购列表移至安特导航

- 页面路径由 `/ecommerce/presell-seckill` 改为 **`/antexiadan/presell-seckill`**；旧路径 301 重定向。
- 侧边栏从「电商」分组移至 **「安特」** 分组。

## 2026-06-06 - 秒杀预购列表页面

- **`src/web/templates/pinduoduo_erp_presell_seckill.html`**（新增）：打开即加载 `presell-seckill-compare` 接口，展示 online + 未标记预售与安特秒杀适配结果；支持刷新与秒杀状态筛选。
- **`src/web/routes.py`**：新增 `GET /ecommerce/presell-seckill` → `ecommerce_presell_seckill`。
- **`src/web/templates/base.html`**：电商分组增加「秒杀预购列表」导航。
- **`pinduoduo_erp_presell.html`**：移除临时对照按钮（功能迁移至新页）。

## 2026-06-06 - 预售订单 × 安特限时秒杀对照

- **`src/spider/pinduoduo/presell_seckill_match.py`**（新增）：读取 `erp_order_presell`（online + unmarked）与 `antexiadan_seckill_product`（默认秒杀中），按货号/标题匹配，输出 `inActivity` / `notInActivity`。
- **`GET /api/pinduoduo/erp-order/presell-seckill-compare`**：对照接口，参数 `online`、`markFilter`、`seckill_status`。
- **`pinduoduo_erp_presell.html`**：新增「对照限时秒杀」按钮与结果表格。

## 2026-06-06 - 拼多多预售表查询接口（erp_order_presell）

- **`src/spider/pinduoduo/presell_store.py`**（新增）：读取 MySQL 表 `erp_order_presell`，支持 `online`、`markFilter`（`unmarked`→`purchased=0`，`marked`→`purchased=1`）分页。
- **`src/api/routes/pinduoduo_routes.py`**：新增 `GET /api/pinduoduo/erp-order/presell-records?page=1&pageSize=10&online=true&markFilter=unmarked`（与 Nest 筛选语义对齐）。

## 2026-06-06 - 安特预售：正在预售且未下架商品查询

- **`src/spider/antexiadan/seckill_store.py`**：
  - `list_products()` 新增 `exclude_offline`，排除 `goods_is_offline=1`（平台已标记下架）。
  - 新增 `list_presale_active_unmarked()`：`activity_status=预热/待开始` + `group_title=预热中` + 未下架。
- **`src/api/routes/antexiadan_routes.py`**：
  - `GET /api/antexiadan/seckill-list/products` 支持 `presale_active`、`exclude_offline` 查询参数。
  - 新增 `GET /api/antexiadan/seckill-list/products/presale-active-unmarked` 专用接口。
- **`src/web/templates/antexiadan_seckill.html`**：筛选栏增加「未下架」勾选与「正在预售·未下架」快捷按钮。

## 2026-06-05 - 安特限时秒杀商品详情 Modal

### 新增功能
- **`src/web/templates/antexiadan_seckill.html`**：
  - 商品列表末尾新增「操作」列，每行有「详情」按钮。
  - 点击详情弹出 Modal，展示该商品的完整字段：商品图片（若有）、秒杀价/原价、活动状态、场次、开始/结束时间、已售/库存/限购数量、秒杀ID、商品ID、批次ID、入库/更新时间、优惠信息、扩展字段。
  - Modal 支持点击遮罩、右上角 × 按钮、按 Escape 键关闭。
  - `colspan` 从 9 改为 10 适配新增列。

## 2026-06-04 - 架构重构第一阶段：模块解耦（notify / storage / workflow）

### 第一步：建立 `notify/` 统一通知模块

- **`src/notify/__init__.py`**（新增）：统一通知入口，暴露 `notify(event)`、`login_alert(source)`、`task_result(source, title, desc, success)`、`custom(message)` 四个便捷函数。
- **`src/notify/event.py`**（新增）：`NotifyEvent`、`NotifyLevel`、`NotifyChannel` 数据结构。
- **`src/notify/filter.py`**（新增）：AI 通知过滤器。ERROR 级别强制发送；其他级别调用 `ai.ask()` 判断是否值得通知；AI 调用失败则降级直接发送。
- **`src/notify/channels/feishu_dm.py`**（新增）：飞书私信渠道，封装 `FeishuMessageSender`。
- **`src/notify/channels/feishu_webhook.py`**（新增）：飞书 Webhook 渠道，封装 `qudao_notify`。
- **调用点替换**（6 处）：
  - `spider/pinduoduo/client.py`：移除 `feishu_sender` 属性，改用 `notify.login_alert("pinduoduo")`
  - `spider/pinduoduo/login_intercept.py`：改用 `notify.login_alert` 和 `notify.notify(NotifyEvent(...))`
  - `spider/pinduoduo/erp_order_sync.py`：改用 `notify.task_result`
  - `spider/pinduoduo/after_sale_sync.py`：改用 `notify.task_result`
  - `spider/pinduoduo/erp_audit.py`：改用 `notify.task_result`
  - `spider/pinduoduo/order_address_sync.py`：改用 `notify.login_alert`
  - `scheduler/manager.py`：改用 `notify.custom`
  - `api/routes/feishu_routes.py`：API 层改用 `notify.login_alert`、`notify.custom`

### 第二步：拆分 storage 层

- **`src/storage/__init__.py`**（新增）：存储层包入口。
- **`src/storage/feishu/__init__.py`**（新增）：飞书多维表格存储子包。
- **`src/storage/feishu/pdd_table.py`**（新增）：从 `spider/pinduoduo/feishutable.py` 迁移，内容不变，这是新的「源文件」。
- **`src/storage/feishu/tu_table.py`**（新增）：从 `spider/tu/feishutable.py` 迁移。
- **`src/spider/pinduoduo/feishutable.py`**：改为转发 stub，`from storage.feishu.pdd_table import ...`，保持所有现有 import 不变。
- **`src/spider/tu/feishutable.py`**：改为转发 stub，`from storage.feishu.tu_table import ...`。

### 第三步：建立 `workflow/` 骨架

- **`src/workflow/step.py`**（新增）：`BaseStep`（抽象基类）、`StepContext`（上下文容器）、`StepResult`（执行结果）。
- **`src/workflow/registry.py`**（新增）：`StepRegistry`（步骤注册表），支持手动注册和 `auto_discover()` 自动发现；全局单例 `get_registry()`。
- **`src/workflow/engine.py`**（新增）：`WorkflowEngine`，支持条件执行（`condition`）、错误策略（`on_error: abort/skip/continue`）、步骤结果写入上下文。
- **`src/workflow/steps/notify_steps.py`**（新增）：`notify.task_result`、`notify.login_alert` 两个内置步骤，验证 workflow ↔ notify 联动。
- **`workflows/pdd_erp_full_sync.json`**（新增）：ERP 订单全量同步工作流示例配置。

### 第四步：AI 融入通知过滤

- **`src/notify/filter.py`**：完善 AI 过滤逻辑，`_ai_should_notify()` 调用 `ai.ask()` 对非 ERROR 事件进行分析，AI 不可用时自动降级发送。

## 2026-06-04 - 架构规划：下一阶段模块解耦方向

- **`docs/next/README.md`**（新增）：整理 `docs/next/` 目录下所有规划文档，形成下一阶段改造总览。
  - 梳理现有架构核心耦合问题（spider 三职混合、飞书能力散落、通知无统一入口）
  - 确定目标模块边界：`automation/`（执行）、`workflow/`（编排）、`storage/`（数据）、`notify/`（通知）、`ai/`（思考）
  - 明确各模块调用规则，确保 AI 模块与业务解耦
  - 设计 AI 融入通知过滤（小场景）和工作流步骤（深度融入）两种方案
  - 制定五步渐进迁移路线图，每步独立可验证

## 2026-06-03 - AI 大脑模块：Windows WinError 10038 修复

- **`src/ai/agent.py`**：修复 `OSError: [WinError 10038] 在一个非套接字上尝试了一个操作`。
  - **根因**：`cursor_sdk._bridge._read_discovery` 用 `selectors.DefaultSelector`（底层 `select.select`）监听子进程 stderr 管道。Windows 上 `select.select` 仅支持 socket，不支持 pipe，因此抛出 WinError 10038。
  - **修复**：模块加载时（`sys.platform == 'win32'`）自动执行 `_patch_bridge_for_windows()`，将 `_read_discovery` 替换为 `_read_discovery_win`——后者在独立守护线程中阻塞迭代 `process.stderr`，通过 `queue.Queue` 回传发现数据，完全绕过 `select.select`。



- **`src/ai/agent.py`**：修复 `Agent.create() got an unexpected keyword argument 'mcp_servers'`。
  - **根因**：`mcp_servers` 不属于 `Agent.create()` / `Agent.resume()`，而是属于 `agent.send()` 的第二个参数 `SendOptions(mcp_servers=...)`。
  - **修复**：拆分 `_get_or_create_agent()`（只负责创建/恢复 Agent，不传 MCP 配置）和 `_build_mcp_servers()`（构建 mcp_servers 字典），在 `agent.send(full_instruction, SendOptions(mcp_servers=mcp_servers))` 时注入。
  - **同步修正**：`Agent.resume(agent_id)` 只传 `agent_id`（不需要 AgentOptions）；流式消息解析改用真实 `run.stream() -> Iterator[SDKMessage]` API（`SDKAssistantMessage.message.content`、`SDKThinkingMessage.text`、`SDKToolUseMessage.name/status/result`）。



### 新增：`src/ai/` 独立 AI 模块（系统 AI 大脑）

- **`src/ai/__init__.py`**：公共 API，系统所有模块唯一导入点。
  - `ask(prompt, *, system, model, max_tokens)` — 同步 LLM 问答（OpenAI 兼容，使用 `AI_API_KEY`）
  - `run_agent(instruction, *, tools, session_name, browser_context, stream_callback)` — Cursor SDK Agent
  - `run_agent_stream(...)` — Agent 流式版本，yield dict 事件
  - `list_sessions()` / `delete_session(name)` — 会话管理
- **`src/ai/client.py`**：`LLMClient` — 封装 OpenAI SDK，懒加载，支持同步和流式补全。
- **`src/ai/agent.py`**：`AgentRunner` — 封装 cursor_sdk.Agent，支持：
  - 会话持久化（`agent_id` 保存到 `ai/sessions.json`，同名 session 自动 resume）
  - Playwright MCP 子进程配置（通过环境变量传递浏览器路径和 Cookie 目录）
  - 爬虫移交协议（`browser_context={url, cookies, screenshot}` 参数）
- **`src/ai/mcp/playwright_server.py`**：Playwright MCP stdio 服务器，7 个工具：
  `navigate`、`screenshot`（返回 base64）、`click`、`fill`、`evaluate`、`get_text`、`wait_for`。
  启动时自动加载 `AI_BROWSER_CONTEXT_FILE` 指定的移交协议 Cookie。

### 新增：Web UI 入口

- **`src/tools/ai_tool.py`**：`AiTool`，工具名 `ai_assistant`，注册为系统工具。
- **`src/api/routes/ai_routes.py`**：Blueprint `/api/ai/`，端点：
  - `POST /api/ai/ask` — LLM 简单问答
  - `POST /api/ai/run` — Agent 同步运行
  - `POST /api/ai/run-stream` — Agent SSE 流式输出
  - `GET /api/ai/sessions` — 列出持久化会话
  - `DELETE /api/ai/sessions/<name>` — 删除会话
- **`src/web/templates/tools/ai_assistant.html`**：聊天式 UI，支持：
  - 左侧历史会话列表（可新建/切换/删除）
  - 工具开关（启用「浏览器控制」切换为 Agent 模式）
  - 流式消息气泡（文本/思考/工具调用）
  - 截图内嵌展示（点击放大预览）
  - 快捷指令按钮

### 修改：配置与依赖

- **`requirements.txt`**：新增 `cursor-sdk>=0.1.0`、`mcp>=1.0.0`
- **`.env.example`**：新增 `AI_BASE_URL`、`AI_API_KEY`、`AI_STOCK_LINK_MODEL`、`CURSOR_API_KEY`、`CURSOR_MODEL` 示例
- **`src/config.py`**：新增 `Config.CURSOR_API_KEY`、`Config.CURSOR_MODEL`
- **`src/api/routes/__init__.py`**：注册 `ai_bp`，Swagger 新增「AI」标签
- **`src/app.py`**：`init_tools()` 中注册 `AiTool`

### 迁移：inventory_sync_job.py

- **`src/spider/pinduoduo/inventory_sync_job.py`** — `_ai_match_product_name()` 不再直接 `from openai import OpenAI`，改为通过 `from ai import ask` / `ai.client.LLMClient` 调用，保持行为不变，解耦业务与 AI SDK。



- **`src/api/routes/antexiadan_routes.py`**：`POST /api/antexiadan/seckill-list/sync`、`GET .../products`、`GET .../batch/latest`。
- **`src/spider/antexiadan/seckill_store.py`**：批次表 + 商品 UPSERT + 可选快照；默认 `data/antexiadan_seckill.sqlite`。
- **`docs/webauto脚本文档/antexiadan-限时秒杀列表.md`**、**`docs/sql/antexiadan-seckill-db-schema.mysql.sql`**。
- 与 webAuto `antexiadan-seckill-list.js` / `antexiadan-seckill-fetch.py` 联动。

## 2026-05-27 - 预售订单脚本：自动筛选付款时间近30天

- **`src/spider/pinduoduo/scripts/pdd-erp-order-presell-list.js`**：
  - 新增筛选表单自动操作逻辑（仿 `pdd-erp-order-delivered-query.js`），在解析表格前先操控 ERP 筛选栏：
    1. 等待 `#timeType` / `#timeRange` 表单加载（最多 12s）
    2. 选择「时间类型」= **付款时间**（可通过 `window.__PDD_ERP_PRESELL_TIME_TYPE` 覆盖）
    3. 点击日期快捷按钮 = **近30天**（可通过 `window.__PDD_ERP_PRESELL_DATE_SHORTCUT` 覆盖，如 `'今天'`、`'近7天'`）
    4. 点击「查询」按钮并等待结果表格出现
  - 新增 `window.__PDD_ERP_PRESELL_SKIP_FILTER = true` 开关：为 `true` 时跳过表单操作、直接解析当前页（兼容旧用法）
  - 新增 `selectOption` 内部工具函数（与 delivered 脚本保持一致的 beast-core-select 操作方式）
  - 新增 `normOpt` / `SCHEMA_PLACEHOLDER` 防止 OpenAPI 传入类型占位符导致配置错误

---

## 2026-05-27 - 开发/生产浏览器 Profile 隔离

- **`src/utils/path_helper.py` → `get_browser_data_dir()`**：按 `APP_ENV` 区分目录——生产 `browser_data`，开发 `browser_data_dev`。修复 dev.py（8886）与 main/打包版（8887）同时运行时共用 `%LOCALAPPDATA%\如意助手\browser_data` 导致 Chromium profile 锁互抢、登录态被踢的问题。
- 开发环境首次使用需在 dev 浏览器里重新登录各平台；生产登录态不变。

---

## 2026-04-20 - 修复 app_config.toml 永远读不到的循环导入 Bug

**根本原因**：`src/config/` 是 Python 包，`src/config.py` 是模块，包优先级高于模块，PyInstaller 打包后 `_internal/` 下同时存在两者。`config/__init__.py` 用 `exec_module` 动态加载 `config.py`，但 `config.py` 底部的 `_load_config_from_file()` 会导入 `utils.config_manager`，而 `config_manager.py` 的**模块级** `from config import Config` 在 `config` 包还未完成初始化时执行，引发 `ImportError`，被 `except: pass` 静默吞掉，toml 配置永远无法加载，ws_client_host 等字段始终保持代码默认值（localhost:8080）。

- **`src/utils/config_manager.py`**：移除顶层 `from config import Config`；新增 `_cfg()` 懒加载辅助函数（`from config import Config` 移到函数内部）；`get_config()` 和 `_apply_single_config()` 改用 `C = _cfg()` 取类引用，彻底打破循环导入。
- **`src/config.py` → `_load_config_from_file()`**：`except Exception: pass` 改为 `print` 完整 traceback，不再静默吞错；外层 `except: pass` 同理，保证日志可见。
- **`src/config.py` → `.env` 加载**：`load_dotenv` 改为依次尝试 `utf-8`、`gbk`、`utf-8-sig` 三种编码（兼容中文注释 GBK 编码的 .env），解决 `UnicodeDecodeError` 导致飞书/AI 密钥加载失败的问题。

---

## 2026-04-20 - WebSocket 配置页：展示「实际握手地址」，消除显示与实际不一致

- **`src/utils/websocket_client.py` → `get_config()`**：新增 `resolved_base_url`、`resolved_path`、`resolved_full_url` 三个服务端预计算字段（调用现有 `build_socket_io_server_url` / `normalize_socketio_path` / `append_assistant_key_query`），由 `/api/websocket/config` 一并返回。
- **`src/web/templates/websocket.html`**：
  - 去掉表单输入框上的硬编码 `value=`（`localhost`、`8080`、`/socket.io/`），改为从服务端加载前显示「加载中…」占位、加载完成后解除遮罩。
  - 新增「实际握手地址」蓝色只读展示区，显示服务端预计算的根地址 / Path / Key / 完整握手 URL；与程序启动日志一致，便于直接验证。
  - 表单输入时实时预览变更后的 URL（黄色背景提示与已加载配置不同），点击「保存」或「连接」后恢复蓝色权威展示。

---

## 2026-04-18 - 打包：`app_config.production.toml` → dist `app_config.toml`

- **新增** `app_config.production.toml`（生产 Nest WebSocket 等）；**`main.spec`** 在复制 `.env`/驱动前调用 **`copy_app_config_production_to_dist`**，写入 `dist/如意助手/app_config.toml`。
- **`README`**：更新打包说明。

---

## 2026-04-18 - WebSocket：`https://` 域名未写端口时用 443（不再误拼 ``:8080``）

- **`build_socket_io_server_url`**：`WS_CLIENT_HOST` 为带协议的 URL 且无端口时按 https→443、http→80；默认端口在连接串中省略。
- **`config.py` / `app_config.toml`**：注释说明生产可写 `https://nestapi.xfysj.top`。

---

## 2026-04-18 - Socket `assistantKey`：生产 erp-001 / 开发 erp-dev-001

- **`src/config.py`**：`APP_ENV=development` 且未设置环境变量 `WS_CLIENT_ASSISTANT_KEY` 时，在加载 `app_config.toml` 后覆盖为 **`erp-dev-001`**；生产仍为 toml / 默认 **`erp-001`**。显式设置 `WS_CLIENT_ASSISTANT_KEY` 时始终优先。
- **`app_config.toml`**：注释说明生产写 `erp-001`，开发入口自动换开发 key。

---

## 2026-04-18 - 待发货页第二块：改为 ERP 实时列表（`/erp-delivering/pending-list`）

- **新**：`POST /api/pinduoduo/erp-delivering/pending-list`、`pdd-erp-order-delivering-list-query.js`、`run_delivering_list_query`；第二块卡片不再调用 `erp-audit/today`。
- **`docs/pinduoduo-erp-remote-api.md`**：接口总览与 §3 增补 pending-list。

---

## 2026-04-18 - 待发货页：今日列表默认「待打印」+ SQLite `printed_at`

- **`audit_events.printed_at`**：迁移新增列；「打印并发货」脚本成功且待发货列表按逻辑清空时，按页面订单号回写，用于与「仅待打印」列表联动。
- **API**：`GET /api/pinduoduo/erp-audit/today?unprinted=1` 仅 `printed_at` 为空的记录；响应含 `filter_unprinted`。
- **页面** `pinduoduo_erp_delivering_print.html`：默认仅待打印；勾选可显示今日全部（含「本地打印」列）；`print_ship_success` 后自动刷新。
- **脚本** `pdd-erp-order-delivering-print-ship.js`：返回 `orderNos`；《远程 API》§3.3 已补充 query 说明。

---

## 2026-04-18 - WebSocket 默认连接：`localhost:8080`、`socket.io`、`erp-001`；开发模式自动连接

- **`src/config.py`**：`WS_CLIENT_HOST`/`PORT`/`PATH`/`ASSISTANT_KEY` 默认值调整为与常见 Nest 本地一致；新增 `WS_CLIENT_PATH_DEFAULT`；环境变量未设置时 `assistantKey` 默认为 `erp-001`，`WS_CLIENT_ASSISTANT_KEY=` 空串表示不携带。
- **`src/utils/websocket_client.py`**：`normalize_socketio_path`，配置为 `socket.io` 时规范为 `/socket.io/`。
- **`src/dev.py`**：热重载子进程（`WERKZEUG_RUN_MAIN`）内调用 `start_if_enabled`，与 `main.py` 一样启动后自动连 Socket.IO。
- **页面**：`websocket.html` 默认展示与上述一致；`README` 一句说明更新。

---

## 2026-04-18 - 文档合并：`nest-gateway-assistant-key.md` → `pinduoduo-erp-remote-api.md`

- **合并**：Nest 网关 `assistantKey`、JWT、握手、`register_assistant`、HTTP 路径表、安全提示、Nest 仓库路径等全文并入 **`docs/pinduoduo-erp-remote-api.md`** §2，并删除 **`docs/nest-gateway-assistant-key.md`**。
- **引用**：`readme.md`、`docs/socketio-assistant-http.md`、`src/config.py`、`src/utils/websocket_client.py` 已改为指向合并后文档。

---

## 2026-04-18 - 拼多多 ERP：服务端调用文档（提交审核 / 今日已审核 / 打印并发货）

- **文档**：新增 `docs/pinduoduo-erp-remote-api.md`（助手路径、Nest `/api/v1` 相对路径、`assistant_http` 示例、`timeout`）；更新 `docs/socketio-assistant-http.md` §8、`docs/nest-gateway-assistant-key.md` §4、`readme.md` 引用。
- **Swagger**：`POST .../erp-audit/submit` 补充 body 字段说明（`order_nos` / `orderNos` 等）。
- **说明**：上述路由在 `pinduoduo_routes.py` 已存在，本次以文档与 OpenAPI 对齐为主。

---

## 2026-04-18 - 已发货「打印状态」默认恢复为「已打印快递单」

- **原因**：`_EVAL` 曾把 Python `None` 落成 JS `null`，仍满足 `!== undefined`，把 window 设为 `null` → 脚本里变成空串 → 走「不筛选」；Swagger 空串同理。
- **修复**：`_EVAL` 仅在 `filterPrintStatus != null` 时写入 window；脚本用 `resolvePrintStatus()`，`__ALL__`/`*` 才表示不筛选，空串/null/未设置一律默认「已打印快递单」。
- **HTTP**：`filter_print_status` 支持 `__ALL__`/`all`/`*` 表示全部；空串视为未指定。

---

## 2026-04-18 - 已发货查询脚本：默认「今天 / 发货时间 / 已打印」与占位符过滤

- **现象**：Swagger 等把字段类型 `string` 当成 JSON 值提交 → 页内 `timeType` 变成字面量 `"string"`，下拉选不到选项。
- **脚本**：`pdd-erp-order-delivered-query.js` 对 `string`/`number` 等 schema 占位符忽略，回退到默认 `发货时间`、`今天`、`已打印快递单`；`printStatus` 与 Python 注入的「显式空串不筛选」语义保留。
- **API**：`erp-delivered/today-printed-query` 对 `time_type`/`date_shortcut`/`filter_print_status` 做同类过滤。

---

## 2026-04-18 - Socket.IO：`connect` 返回语义说明 + 连接错误日志节流

- **返回**：`POST /api/websocket/connect` 增加 `started`、`note`，说明 **success 仅表示已启动后台线程**，握手异步；`assistant_key_configured` 仍为是否带 query。
- **日志**：`connect_error` 同类日志 **15s 内合并一条**，避免刷屏；若本次连接未配 assistantKey，**首次**失败时打一条 Nest 提示。

---

## 2026-04-18 - Socket.IO 握手自动附加 `assistantKey`（仅配 host/端口 + key）

- **配置**：`Config.WS_CLIENT_ASSISTANT_KEY` / 环境变量 `WS_CLIENT_ASSISTANT_KEY`；持久化键 `ws_client_assistant_key`（`app_config.toml`）。
- **逻辑**：`websocket_client.append_assistant_key_query` 在连接根 URL 上追加 `assistantKey`；日志中对 query 脱敏。
- **`connect(assistant_key)`**：缺省沿用 Config；显式 `None`/空串表示本次不带 query。
- **API / 页面**：`/api/websocket/config` 与 `/connect` 支持 `assistant_key`；`websocket.html` 增加输入框。
- **文档**：`docs/nest-gateway-assistant-key.md` 增加如意助手自动附加说明。

---

## 2026-04-18 - Socket.IO 客户端连接 URL 规范化（修复 https host 握手失败）

- **原因**：`WS_CLIENT_HOST` 默认等为 `https://...` 时，旧逻辑拼成 `http://https://host:port`，WebSocket 握手异常（`Connection to remote host was lost` / `Connection error`）。
- **改动**：`src/utils/websocket_client.py` 新增 `build_socket_io_server_url`，支持带协议的 host；连接前打一行解析后的 URL 日志便于排查。
- **配置**：`src/config.py` 对 `WS_CLIENT_HOST` 注释补充说明。

---

## 2026-04-18 - Nest 网关 `assistantKey` 对接文档入库

- **新增**：`docs/nest-gateway-assistant-key.md`（握手 Query、`register_assistant`、`assistantKey`/`socketId`、Nest `/api/v1/assistant/pinduoduo/...`、安全提示；Nest 仓库路径见文内 §7）。
- **`docs/socketio-assistant-http.md`**：新增 **第十节**，指向上述文档。

---

## 2026-04-18 - socketio-assistant-http：§8.0 两个核心业务接口专页

- **文档**：在 `docs/socketio-assistant-http.md` 第八节前新增 **§8.0**，专门整理 **`POST .../erp-audit/pending`** 与 **`POST .../erp-delivered/today-printed-query`**：开发/生产端口（8886 / 8887）、对照表、请求/响应字段、`assistant_http_response.data` 取数说明、两段最小 Socket JSON；§8.3 / §8.4 增加「详见 §8.0」引用。

---

## 2026-04-18 - ERP 已发货「今日已打印快递单」查询接口 + Webhook

- **脚本**：`pdd-erp-order-delivered-query.js`（页面筛选 + 表格抓取）已由 `erp_audit.fetch_delivered_today_printed_rows` 接入；打开 `Config.PINDUODUO_ERP_ORDER_DELIVERED_URL`，登录与其它 ERP 页一致走 `handle_pdd_login_intercept`。
- **HTTP**：`POST /api/pinduoduo/erp-delivered/today-printed-query`，可选 body：`filter_print_status`、`time_type`、`date_shortcut`、`auto_scroll`、`scroll_max_steps`、`scroll_pause_ms`；浏览器池超时 620s。
- **通知**：非登录拦截场景下，执行结束经拼多多渠道 `send_success` / `send_warning` 推送摘要（条数 + 文案）。
- **配置**：`PINDUODUO_ERP_ORDER_DELIVERED_URL`（默认 `https://mms.pinduoduo.com/erp/order/delivered`）。
- **文档**：`docs/socketio-assistant-http.md` 第八节更新为「今日打印单」以本接口为准。

---

## 2026-04-18 - socketio-assistant-http：拼多多 ERP 待审批 / 今日订单对接示例

- **文档**：在 `docs/socketio-assistant-http.md` 新增第八节，整理 **`POST /api/pinduoduo/erp-audit/pending`**（待审批列表）、**`GET /api/pinduoduo/erp-audit/today`**（今日本地记录）、可选 **`POST .../erp-delivering/print-ship`**（打印并发货）；补充 **`assistant_http` 的 `timeout`**（pending 建议 650s 量级），并给出可直接用于 Socket 的 JSON 示例。

---

## 2026-04-18 - Socket.IO assistant_http（远端 axios 风格调本机 HTTP + messageId 回包）

- **能力**：对已连接的如意助手 Socket.IO 客户端下发 `assistant_http`（或在 `forward` 中带 `type: assistant_http`），载荷为 axios 风格字段（`method`、`url`、`params`、`headers`、`json`/`data`、`timeout`、`messageId`）；助手在本机解析 URL（无 host 时拼到 `http://HOST:PORT`，可用环境变量 `ASSISTANT_HTTP_BASE` 覆盖），执行后用 **`assistant_http_response`** 把同一 `messageId` 与结果回给服务端。
- **文档**：新增 `docs/socketio-assistant-http.md`（事件名、字段、Nest/浏览器示例、安全提示）。
- **改动文件**：`src/utils/assistant_http_invoke.py`（新建）、`src/utils/websocket_client.py`（注册事件与异步执行）、`src/config.py`（`ASSISTANT_HTTP_BASE`）、`README.md`。

---

## 2026-04-18 - 侧边栏头部新增 headless 快捷开关（即时生效）

- **背景**：`headless=false` 用完容易忘记关回去，每次都要去配置页改太繁琐。
- **新增**：`base.html` 侧边栏头部加 toggle 开关，开 = 后台运行（headless=true），关 = 显示浏览器窗口（headless=false）；变更后立即调 `POST /api/settings/headless`，由后端：
  1. 合并写入 `app_config.toml`（注意：`config_manager.save_config` 已改为合并保存，避免覆盖未传字段）；
  2. 同步 `Config.HEADLESS` 与 `BrowserPool.headless`；
  3. 触发 `BrowserPool.restart_browser_context()` 软重启（关闭当前 context 与 page，下次 `execute()` 自动用新 headless 重建）；executor 单线程能保证排队在当前任务之后，不会拦腰打断。
- **改动文件**：
  - `src/spider/query_manager.py`：新增 `restart_browser_context()`，仅关 context+page，不关 playwright/executor，下次任务自动重建。
  - `src/utils/config_manager.py`：`save_config` 改为「合并保存」（先 `load_config()` 再 `update`），修复部分保存会清空其他键的潜在问题。
  - `src/api/routes/settings_routes.py`：新增 `GET/POST /api/settings/headless`，支持「持久化 + 立即生效 + 浏览器软重启」一站式切换。
  - `src/web/templates/base.html`：sidebar-header 新增开关 + 内联 CSS + 内联 JS（绿色拨杆，附 tooltip 说明）。
- **不影响**：现有配置页 `/settings` → `POST /api/settings/app` 仍可用；现 `save_config` 合并语义对其完全透明（仅更新自己提交的字段，反而更安全）。

---

## 2026-04-18 - 「拼多多助手」改名「订单助手」（弱化平台品牌）

- **改名**：侧边栏导航 + 页面 `<h2>` + 浏览器 tab 标题中的「拼多多助手」统一改为「订单助手」（含 description 配套调整为「订单后台自动化工具，支持登录管理和自动化操作」）。
- **改动文件**：
  - `src/tools/pinduoduo_tool.py`：`PinduoduoTool.__init__` 的 `display_name`/`description`（这是 `tool.display_name` 真正的数据源——`tool_manager.get_tools_info()` → `tool.get_info()`）。
  - `module_config.toml`：`[pinduoduo]` 段 `display_name`/`description`（保持与 toml 一致，仅 enable/初始化时使用）。
  - `src/config/modules.py`：`DEFAULT_MODULES['pinduoduo']` 默认值同步（打包后无 toml 时的兜底）。
- **未改**：`tool.name` 仍为 `pinduoduo`，所有路由 `/api/pinduoduo/*` 与 `/tools/pinduoduo` URL 保持不变；图标 `🛒` 暂保留。其他历史 `docs/`、`README` 等文档以及 `pinduoduo_routes.py` 模块描述未做大规模改名，保留以便检索历史脉络。

---

## 2026-04-18 - 待审核列表前端新增「店铺 / 实收」列

- **前端**：`/tools/pinduoduo` 待审核表格新增「店铺 / 实收」列（位于「商品/规格/数量」与「平台订单号」之间），渲染脚本返回的 `row.shopName`（蓝色徽标）与 `row.actualAmount`（橙色「实收 ¥xx.xx」）。
- **改动文件**：`src/web/templates/tools/pinduoduo.html`：`<thead>` 加 `<th>店铺 / 实收</th>`，所有 `colspan="4"` 同步改为 `colspan="5"`；`renderTable` 增加 `escapeHtml`、`shopHtml` 拼接。
- **范围**：纯展示，不改 `audit_store` / 飞书同步链路；店铺写入飞书表 / SQLite 仍待后续按 `docs/next/pinduoduo-erp-audit-feishu-table.md` 增列后实现。

---

## 2026-04-18 - 拼多多 ERP 待审核列表、SQLite、飞书审核表与待发货打印

- **前端**：`/tools/pinduoduo` 顶部新增「待审核订单」卡片，进入页面自动调用 `POST /api/pinduoduo/erp-audit/pending`，支持勾选、`POST .../erp-audit/submit`、登录二维码与 `/api/pinduoduo/login`（与 ERP 同步页一致的拦截处理）；侧链「待发货打印」。
- **后端**：新增 `login_intercept.py`、`erp_audit.py`、`audit_store.py`（SQLite：`data/pdd_erp_audit.sqlite`）；`feishutable.sync_audit_events_to_feishu`；路由 `erp-audit/pending|submit|today|sync-feishu`、`erp-delivering/print-ship`。`erp_order_sync` 改用公共登录拦截。
- **脚本**：`pdd-erp-order-audit-goods.js` 勾选阶段改为虚拟列表下按订单号滚动定位后再勾。
- **文档**：飞书审核表字段说明见 `docs/next/pinduoduo-erp-audit-feishu-table.md`。独立路由 `/pdd-erp-delivering-print`，侧栏「待发货打印」。
- **配置**：`PINDUODUO_ERP_ORDER_AUDIT_URL`、`PINDUODUO_ERP_ORDER_DELIVERING_URL`、`PINDUODUO_ERP_AUDIT_FEISHU_TABLE_ID`（默认 `tblVgYVKU5DbyKdM`，与文档一致；未配置时不再静默跳过同步）、`PINDUODUO_ERP_AUDIT_DB_PATH`（可选）。
- **修复**：`/api/pinduoduo/erp-audit/submit` 在 SQLite 入库后增加飞书同步进度日志；当未配置 table_id 时输出 WARNING 而非静默跳过。`/tools/pinduoduo` 待审核缩略图放大并支持悬停预览/点击查看原图；`pdd-erp-order-delivering-print-ship.js` 在判空前增加 5–15s 弹性等待，避免列表请求慢被误判为空。

---

## 2026-04-13 - 打包后库存映射配置不回显（PyInstaller 6 _internal 路径不匹配）

- **现象**：打包后页面「库存映射配置」加载数据时，已保存的映射全部为空，不能正常回显。
- **原因**：PyInstaller 6 onedir 模式下 `datas` 文件放在 `_internal/` 子目录，而 `load_mappings()` 用 `get_project_root()`（= `exe_dir/`）拼接路径，实际去找 `exe_dir/config/inventory_product_mapping.json`；真实文件在 `exe_dir/_internal/config/`，路径不匹配导致读到空字典。
- **修复**：`path_helper.py` 新增 `get_bundled_data_root()` 函数，frozen 时优先返回 `_internal` 目录；`inventory_mapping.load_mappings()` 改用 `get_bundled_data_root()` 读默认内嵌文件，`get_project_root()` 作为回退兼容手动放置场景。

---

## 2026-04-13 - 打包遗漏 Playwright 注入脚本导致 ERP 订单同步失败

- **现象**：打包后执行「拼多多 ERP 订单同步」报 `No such file or directory: ..._internal\spider\pinduoduo\scripts\pdd-erp-order-all-table.js`。
- **原因**：`erp_order_sync.py` 和 `order_address_sync.py` 通过 `Path(__file__) / 'scripts' / *.js` 加载注入脚本，但 `main.spec` 的 `datas` 未包含 `src/spider/pinduoduo/scripts/` 目录，打包后 `_internal` 下缺少该文件夹。
- **修复**：`main.spec` 的 `datas` 增加 `(src/spider/pinduoduo/scripts, spider/pinduoduo/scripts)`，将整个 scripts 目录（含 `pdd-erp-order-all-table.js`、`pdd-order-search-receiver.js`）打入包。

---

## 2026-04-12 - 定时任务 `scheduler/tasks.toml` 随 exe 分发

- **现象**：打包后定时任务列表为空或恢复默认，与仓库里编辑的 `scheduler/tasks.toml` 不一致。
- **原因**：运行时数据在 `get_safe_data_path("scheduler")/tasks.toml`（exe 旁 `scheduler/`）；`main.spec` 未打入该文件；且种子原仅从 `src/scheduler/tasks.toml` 读取，与仓库根目录 `scheduler/tasks.toml` 易脱节。
- **修复**：`main.spec` 的 `datas` 增加 `scheduler/tasks.toml` → 输出目录 `scheduler/`；`task_config._load_seed` 优先读 `get_project_root()/scheduler/tasks.toml`；`src/scheduler/tasks.toml` 与根目录种子对齐作兼容回退。

---

## 2026-04-12 - 库存映射 JSON 随 exe 打包与合并加载

- **需求**：`config/inventory_product_mapping.json` 需在打包后可用，避免每次重新生成；支持在本地增改配置。
- **说明**：映射由 `inventory_mapping.load_mappings` 使用，库存同步与 `/inventory-mapping/*` API 均依赖。
- **实现**：`main.spec` 的 `datas` 增加该文件到输出目录 `config/`；`load_mappings` 先读安装目录（项目根 / exe 同目录）默认文件，再与 `get_safe_data_path` 可写路径合并，后者覆盖同名键；`save_mappings` 仍只写入可写路径。

---

## 2026-04-12 - 打包 exe 后读不到根目录 .env（AI 配置失效）

- **原因**：开发时 `.env` 在项目根；PyInstaller **不会**自动把 `.env` 打进包，冻结模式下原逻辑只从 **`exe 同目录`** 加载，若未手动复制则 `AI_BASE_URL` / `AI_API_KEY` 等为空。
- **修复**：`src/config.py` 冻结时依次尝试 **exe 目录**、**当前工作目录** 的 `.env`；`main.spec` 打包结束若项目根存在 `.env` 则 **复制到 `dist/<应用名>/`**；README「打包注意事项」补充说明。

---

## 2026-04-11 - 打包 exe：默认启用拼多多模块以初始化浏览器池

- **现象**：`task_*.log` 中 ERP 同步返回 `浏览器池未初始化`，与飞书字段无关。
- **原因**：冻结模式下 `module_config.toml` 需在 exe 同目录；若缺失则仅用 `DEFAULT_MODULE_CONFIG`，原默认无 `pinduoduo`，`get_modules_requiring_browser()` 为空，跳过 `init_browser_pool()`。
- **修复**：`config/modules.py` 的 `DEFAULT_MODULE_CONFIG` 增加 `pinduoduo`（enabled + requires_browser）；`main.spec` 的 `datas` 增加 `module_config.toml` 复制到打包根目录。

---

## 2026-04-11 - ERP 写飞书：默认不传「发货剩余」

- **原因**：飞书表未建「发货剩余」列时，新建记录报 `1254045 FieldNameNotFound`。
- **实现**：`feishutable._erp_row_to_fields` 跳过 `ERP_FEISHU_OMIT_FIELD_KEYS`（当前仅 `发货剩余`）。增量更新子集本就不含该列。

---

## 2026-04-11 - ERP 同步失败：日志中带飞书 API 错误与字段快照

- **需求**：某平台订单号写入失败时需明确原因（如单选字段选项不匹配）。
- **实现**：`FeishuTableClient` 增加 `_make_request_detail`、`create_record_with_error`、`update_record_with_error`；`sync_erp_order_rows_to_feishu` 在单条失败及批量部分失败路径调用并打 `ERP 同步飞书写入失败 reason=… 平台订单号=… err=… fields=…`。

---

## 2026-04-11 - ERP 订单同步：日志与摘要中输出失败的平台订单号

- **需求**：飞书同步统计「失败 N 条」时无法对应到具体订单。
- **实现**：`feishutable.sync_erp_order_rows_to_feishu` 在各类失败路径收集 `failed_order_sns`，写入返回字段并在 `message` 中追加「失败订单号: …」；`logger.warning` 同步打印。调度器 `_format_pdd_erp_sync_summary` 增加一行「失败订单号: …」。Webhook 详情沿用完整 `message`，已含失败单号。

---

## 2026-04-08 - 恢复调度器 `pdd_inventory_sync` 任务类型

- **问题**：`tasks.json` 中「拼多多库存」任务类型为 `pdd_inventory_sync`，但 `manager.get_task_handlers()` 未注册，定时触发报「未知任务类型」。
- **修复**：恢复 `_run_pdd_inventory_sync`、`get_task_handlers` / `get_task_type_schemas` 中对该类型的注册；成功/失败用返回元组第一元 `(eligible_count | -1)` 配合 `_infer_handler_success` 区分。

---

## 2026-04-08 - 修复定时任务重启后错过触发（misfire）问题

- **问题**：「拼多多 ERP 订单同步（12点与18点）」cron `0 12,18 * * *` 未在 12:00 执行。
- **根因**：服务在 `11:56:54` 关停，`12:05:34` 才重启，跨过了 12:00 窗口；APScheduler 默认 `misfire_grace_time=1秒`，超时即跳过，不会补跑。
- **修复**：在 `src/scheduler/manager.py` 的所有 `add_job` 调用中加入 `misfire_grace_time=600`（允许 10 分钟内补跑）和 `coalesce=True`（多次 misfire 只补跑一次），影响 `_register_jobs_from_config`、`add_task_and_register`、`resume_task` 三处。

## 2026-04-08 - 定时任务：启动漏跑补执行（方案 2）

- **场景**：进程在 12:00 前后长时间未运行，14:00 启动时仍希望补跑「上一档」cron（如当天 12:00），仅靠 misfire 无法覆盖冷启动。
- **实现**：
  - 依赖 `croniter` 计算当前时刻之前最近一次计划触发点；若距该点不超过 24 小时，且持久化中该任务的「上次成功时间」早于该点（或无记录），则在 `sched.start()` 后由后台线程执行一次 `_run_task_by_id(..., trigger_label="启动补跑")`。
  - 成功完成时写入 `scheduler/task_last_success.json`（路径同 `get_safe_data_path("scheduler")`）。
  - 任务项可选 `catch_up_on_start`（默认不补跑）；种子与 `scheduler/tasks.json` 中为「拼多多 ERP 订单同步（12点与18点）」设为 `true`。
  - `task_config._merge_seed_fields_for_existing_tasks_inplace`：从种子为已存在任务补全缺失的 `catch_up_on_start`，不覆盖用户已有键。
  - `_infer_handler_success`：按任务类型推断业务成败，修正原先「凡返回 tuple 即记成功」的问题；`pdd_erp_order_sync` 依据摘要中的 `成功: 是`。
- **依赖**：`requirements.txt` 增加 `croniter>=2.0.0`。

---

## 2026-04-08 - 扣减日志表新增三列：商品名称 / 商品信息 / 组合

- **需求**：在日志表 `tblXXipFcgH1EQH7` 新增三个字段，便于区分套装和非套装、查询单品名称。
- **字段说明**：
  | 字段 | 非套装 | 套装（充电头行）| 套装（数据线行）|
  |---|---|---|---|
  | 商品信息 | ERP 原始商品信息文本 | 同左 | 同左 |
  | 商品名称 | 同商品信息（ERP 原文）| 匹配到的充电头 SKU 名（同库存关联）| 匹配到的数据线 SKU 名（同库存关联）|
  | 组合 | "否" | "是" | "是" |
- **变更**：
  - `inventory_sync_job.py`：新增三个列名常量 `_LOG_COL_PRODUCT_INFO` / `_LOG_COL_PRODUCT_NAME` / `_LOG_COL_IS_BUNDLE`。
  - 主循环提前提取 `info_raw`，套装先计算 `charger_link` / `cable_link`，再将三个新字段写入 `proposed_log_fields_list`。
  - `_filter_delta` 自动将三个新字段按文本比对，无需额外修改。

---

## 2026-04-08 - 库存同步：修复套装数据线颜色匹配过严问题

- **问题**：套装 `【蓝色套装】...1.2米PD快充线` 中，线材用的是套装整体颜色（蓝色）去约束匹配，但库存里 1.2米 PD线可能只有粉色/橙色，导致 AI 无法匹配。
- **根因**：套装颜色标签（如`【蓝色套装】`）代表充电头颜色，不代表线材颜色。
- **修复**：
  - 新增三个常量 prompt：`_SYSTEM_PROMPT_NORMAL`（普通订单）、`_SYSTEM_PROMPT_BUNDLE_CHARGER`（套装充电头，颜色=套装颜色）、`_SYSTEM_PROMPT_BUNDLE_CABLE`（套装数据线，颜色不强制对齐套装颜色，优先按长度和接口类型匹配）。
  - `_ai_match_product_name` 新增 `system_prompt` 参数（默认 `_SYSTEM_PROMPT_NORMAL`）。
  - `_find_stock_link_for_kind` 新增 `system_prompt` 参数并透传。
  - 主循环中充电头传 `_SYSTEM_PROMPT_BUNDLE_CHARGER`，数据线传 `_SYSTEM_PROMPT_BUNDLE_CABLE`。

---

## 2026-04-08 - 库存同步：套装订单拆两条日志（方案 A）

- **背景**：ERP 中"套装"订单（充电头 + 数据线组合）原来只写一条日志记录，无法分别扣减两个 SKU 的库存。
- **方案 A 实现**：
  - `log_by_order` 数据结构从 `Dict[str, Dict]` 改为 `Dict[str, List[Dict]]`，允许一个订单号对应多条日志行（套装最多 2 条）。
  - **新增 `_find_stock_link_for_kind`**：针对套装拆解场景，接受"充电头候选列表"或"数据线候选列表"，分别调 AI 匹配，cache_key 包含类别标签避免与非套装缓存冲突。
  - **主循环**：检测到套装 (`_detect_is_bundle`) 时生成 2 条 `log_fields`（第 0 条=充电头，第 1 条=数据线），按位置与 `log_by_order` 已有条目对应：若不存在则新建，若已存在则计算 delta 更新。
  - **`flush_log`**：新建成功后用 `setdefault(...,[]).append(...)` 追加到 list，避免覆盖套装另一条。
  - **退货处理**：改为 `for entry in log_by_order.get(pk_key, [])` 遍历，套装两条日志都写入退货时间/数量。
  - **`outbound_updates` / `return_updates` 缓存回写**：改为双层循环 `for entries in ... for meta in entries` 按 record_id 精确定位。
- **文件**：`src/spider/pinduoduo/inventory_sync_job.py`（763 → 818 行）。

---

## 2026-04-07 - 库存同步：AI 匹配「库存关联」，替换旧加权打分

- **方案**：接入 DMXAPI（OpenAI 兼容接口），用 `deepseek-v3` 模型做商品名称匹配，彻底解决功率/颜色/类型/长度/套装等复杂变体问题。
- **主要变更**：
  - `requirements.txt`：新增 `openai>=1.0.0`。
  - `config.py`：新增 `AI_BASE_URL`、`AI_API_KEY`、`AI_STOCK_LINK_MODEL`（从 `.env` 读取，已有配置无需改动）。
  - `inventory_sync_job.py`（852→763 行）：
    - 删除所有旧打分基础设施：`_parse_stock_link_match_min_score`、`_extract_wattages`、`_norm_stock_match_text`、`_char_counter`、`_multiset_cover_name_in_info`、`_multiset_jaccard`、`_score_power_match`、`_score_kind_match`、`compute_stock_link_match_score`、`_failure_reasons_from_parts`。
    - 新增 `_detect_is_bundle`：识别套装（充电头+线组合或含"套装"字）。
    - 扩充 `_detect_accessory_kind` 关键词：新增 `PD线`、`双C线`、`C线`、`L线` 等缩写。
    - 新增 `_ai_match_product_name`：lazy import openai，调用 AI 从候选列表选最佳名称；含 ImportError 和网络异常兜底。
    - `_find_best_stock_link` 重写：① 类型预筛（套装/充电头/线分开）→ ② AI 匹配 → ③ 同次任务内 `ai_cache` 去重复用。
    - `_stock_link_unmatched_text` 简化：去掉 score/min_score 参数。
    - `run_inventory_sync_job`：读取 AI 配置，初始化 `ai_cache`，传入 `_find_best_stock_link`。
- **行数变化**：852 → 763 行。

---

## 2026-04-07 - 库存同步：重构「库存关联」匹配逻辑

- **问题根因**：原实现按订单号从库存表找对应行再读「商品名称」，但库存表里的订单行是由同步任务自动新建的（不含「商品名称」列），导致永远读不到名称。
- **修复思路**：库存信息表本身就是一个 SKU 产品目录（含「30W 充电头-白色」等短名），匹配应**扫描全部行的「商品名称」作为候选集**，对每个候选打分后取最优——这才是 ERP「商品信息」包含库存表「商品名称」字符的正确利用方式。
- **主要变更**（`inventory_sync_job.py`）：
  - 删除 `_inventory_product_name_from_fields`、`_inv_record_quality`、`_stock_link_text` 三个函数。
  - 新增 `_find_best_stock_link(erp_fields, product_names, ...)` ：接收预先从库存表提取的所有「商品名称」列表，逐一打分取最优，达标则写入名称，不达标则写原因说明。
  - `inv_by_order: Dict` → `inv_order_keys: Set[str]`（只需判断订单是否已建库存行，不再存字段）。
  - 去掉主循环里的 `pending_inv_f` 临时缓存逻辑。
  - `flush_inv` 简化为只往 `inv_order_keys` 中 `.add()`，无需 `_merge_feishu_fields`。
  - 初始化阶段同时建 `product_names` 候选列表（去重），日志打印候选数量。
- **行数变化**：949 → 893 行（减少约 56 行）。

---

## 2026-04-07 - 库存同步：名称列多别名 + 飞书单元格结构扩展

- **说明**：用户反馈库存表可见「30W 充电头-白色」等仍报名称为空。增加 `_inventory_product_name_from_fields`：在配置列外依次尝试 `商品名称/名称/产品名称/…` 及表头含「商品」且以「名称」结尾的列；`feishu_field_to_text` 增加 `name/caption/display_value` 等键以兼容单选、关联返回值。同订单多行选优时「有名称」判定与此一致。
- **涉及文件**：`inventory_sync_job.py`、`feishutable.py`、`README.md`。

---

## 2026-04-07 - 库存同步：扣减日志「库存关联」仅写库存表「商品名称」

- **规则**：匹配达标时「库存关联」只填库存信息表 `商品名称` 列原文，不再用「商品信息」长文案顶替；达标但该列为空时写说明（请补名称后重跑）。未达标仍为未匹配原因 + 商品信息/店铺等。
- **涉及文件**：`inventory_sync_job.py`。

---

## 2026-04-07 - 库存同步：库存关联「无商品名称」误报与同订单多行

- **原因**：仅读 `商品名称` 做比对，而任务新建库存行只从 ERP 复制了「商品信息」；或同「平台订单号」多行时原先只保留飞书返回的**第一条**，易拿到无名称行。
- **修复**：`_stock_link_text` 在名称为空时用库存「商品信息」参与 `compute_stock_link_match_score`；达标后若有短名写短名否则写比对文案。`inv_by_order` 合并同订单多行时按「有名称 > 信息更长 > 复制列更多」选优。
- **涉及文件**：`inventory_sync_job.py`。

---

## 2026-04-07 - 库存同步：临时付款对比日覆盖（测试）

- **说明**：`inventory_sync_job.py` 增加 `INVENTORY_SYNC_PAY_AFTER_OVERRIDE = '2026-04-05'`，在未传 `pay_after_date` 时覆盖 Config，便于多看数据；测完改为 `None` 即恢复环境变量默认。
- **涉及文件**：`inventory_sync_job.py`。

---

## 2026-04-07 - 库存同步：默认 table_id 与模块注释对齐

- **说明**：`PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID` 与日志表一样提供代码默认（`tbljLwzLLKafXl0h`）；`inventory_sync_job.py` 顶部 docstring 列出 ERP / 库存 / 日志三张默认表 id，并标明对应 `Config` 项及 env、options 可覆盖。
- **涉及文件**：`config.py`、`README.md`、`.env.example`、`inventory_sync_job.py`。

---

## 2026-04-07 - 库存同步：同批新建库存行时「库存关联」误报未找到

- **问题**：同一轮循环里先排队 `batch_create` 库存信息、再写扣减日志时，`inv_by_order` 尚未包含该订单（要等 `flush_inv`），`_stock_link_text` 收到 `inv_fields=None`，误显示「未找到该订单对应的库存信息记录」，且无法按商品名称算分。
- **修复**：排队新建库存时保留 `pending_inv_f`；解析库存关联时优先 `inv_by_order`，否则用本行待写入的库存字段。
- **涉及文件**：`src/spider/pinduoduo/inventory_sync_job.py`。

---

## 2026-04-07 - 库存同步：「库存关联」匹配分 + 达标写商品名称原文

- **需求**：库存信息「商品名称」与 ERP「商品信息」顺序不同、需区分功率与头/线；**达标后「库存关联」与库存表「商品名称」文字一致**。
- **实现**：`compute_stock_link_match_score`（multiset 覆盖、Jaccard、功率、头/线）；**分数 ≥ 阈值则「库存关联」=「商品名称」原文**；**未匹配**时写 `未匹配(分/阈值)｜原因：…｜商品信息：…｜店铺：…`（区分无库存行、无商品名称、功率/字符/类别等原因）。权重与阈值见 `README`。
- **涉及文件**：`inventory_sync_job.py`、`config.py`、`README.md`、`pinduoduo_routes.py`。

---

## 2026-04-07 - 拼多多：飞书 ERP → 库存信息表 + 扣减日志（定时任务 + API）

- **业务**：定时读取飞书「全部店铺」ERP 订单表，筛选付款时间晚于配置日、有平台订单号的行；在 **库存信息表** 按订单号补建记录；在 **扣减库存日志表** 写入/更新出库列（默认需快递单号）；「提醒」列命中退货关键词时在日志中更新退货时间/数量；待写字段与表中已有值一致则跳过 API。
- **实现**：新增 `src/spider/pinduoduo/inventory_sync_job.py`；`config.py` 增加 `PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID`、`PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID` 等环境项；`POST /api/pinduoduo/inventory-sync-from-erp-feishu`；调度器类型 `pdd_inventory_sync` 与种子任务 `pdd_inventory_sync_from_erp_feishu`（默认 `enabled: false`）；种子合并版本号递增至 `2`。
- **涉及文件**：`inventory_sync_job.py`、`config.py`、`api/routes/pinduoduo_routes.py`、`scheduler/manager.py`、`scheduler/task_config.py`、`src/scheduler/tasks.json`、`scheduler/tasks.json`、`web/templates/scheduler_add.html`、`README.md`。

---

## 2026-04-07 - 修复：定时任务手动触发死锁

- **问题**：Flask 使用 `threaded=False` 单线程模式，点击"立即执行"时，`/api/scheduler/trigger/` 路由同步调用 `run_task_by_id()`，任务内部又 `requests.post()` 回调本机 Flask API（如 `/api/pinduoduo/sync-erp-orders`），形成死锁——Flask 被第一个请求占用，无法处理第二个请求。
- **修复**：将 `trigger_job` 端点改为异步执行——任务放到后台线程 `threading.Thread`，接口立即返回 `202 Accepted`。增加防重复触发检查（任务正在执行时返回 `409 Conflict`）。
- **前端适配**：`scheduler.html` 中 `triggerTask` 函数适配异步流程，提交后自动启动轮询（每 3 秒查询 `/tasks/<id>/status`），任务完成后自动显示执行结果并刷新列表。
- **涉及文件**：`src/api/routes/scheduler_routes.py`、`src/web/templates/scheduler.html`。

---

## 2026-04-07 - 单实例互斥锁：防止软件重复打开

- **问题**：多次点击 exe 会打开多个实例，端口冲突、资源浪费。
- **新增**：`src/utils/single_instance.py`，使用 Windows 命名 Mutex（`CreateMutexW`）实现进程级单实例锁。
  - 第一个实例正常启动并持有 Mutex。
  - 第二个实例检测到 Mutex 已存在后，通过 `FindWindowW` 找到已有窗口，`ShowWindow` + `SetForegroundWindow` 将其激活到前台，然后自身退出。
- **集成**：在 `main.py` 的 `main()` 最开头调用 `ensure_single_instance(Config.WINDOW_TITLE)`，所有后续逻辑之前完成检查。
- **涉及文件**：`src/utils/single_instance.py`（新增）、`src/main.py`。

---

## 2026-04-07 - 通用渠道 Webhook 通知（成功/警告/失败）+ ERP 订单同步运行报告

- **问题**：`erp_order_sync.py` 仅在登录拦截时通过 Webhook 发送飞书通知，同步成功后不发送任何消息。
- **新增通用函数**：在 `tools/feishu/webhook/qudao_notify.py` 中新增四个通知函数，各业务模块按语义一行调用：
  - `send_channel_notification(channel, *, title, description, header_template, ...)` — 基础通用入口，可自定义颜色。
  - `send_success(channel, *, title, description, ...)` — 成功通知，绿色卡片，标题自动加 ✅。
  - `send_warning(channel, *, title, description, ...)` — 警告通知，橙色卡片，标题自动加 ⚠️。
  - `send_error(channel, *, title, description, ...)` — 失败通知，红色卡片，标题自动加 ❌。
- **ERP 同步报告**：`erp_order_sync.py` 在飞书表写入完成后，成功调 `send_success`、部分失败调 `send_warning`。
- **涉及文件**：`src/tools/feishu/webhook/qudao_notify.py`、`src/spider/pinduoduo/erp_order_sync.py`。

---

## 2026-04-07 - 修复：开发模式下定时任务不运行

- **问题**：`dev.py`（开发模式入口）没有调用 `start_scheduler()`，导致定时任务（如拼多多 ERP 订单同步 12:00/18:00）在开发模式下完全不执行。只有 `main.py`（生产模式）才会启动调度器。
- **修复**：在 `dev.py` 中添加调度器启动逻辑。由于开发模式启用了 `use_reloader=True`（Flask 热重载会启动两个进程），仅在子进程（`WERKZEUG_RUN_MAIN='true'`）中启动调度器，避免重复执行。退出时同步调用 `shutdown_scheduler()` 清理。
- **涉及文件**：`src/dev.py`。

---

## 2026-04-07 - 自动化构建脚本 + 版本号统一管理

- **`build.py`（新增）**：自动化构建脚本，以 `config.py` 的 `APP_VERSION` 为唯一版本来源，构建时自动同步到 `setup.iss`，然后依次执行 PyInstaller 打包和（可选）Inno Setup 安装包编译。
  - `python build.py` — 同步版本 + PyInstaller 打包
  - `python build.py --installer` — 同步版本 + PyInstaller + Inno Setup 安装包
  - `python build.py --sync-only` — 只同步版本号到 setup.iss
  - `python build.py --version` — 查看当前版本号
- **`build.bat`（新增）**：Windows 双击构建脚本，自动激活 `.venv` 虚拟环境并调用 `build.py`。
  - 双击 / `build.bat` — 完整构建（PyInstaller + Inno Setup）
  - `build.bat --no-inst` — 仅 PyInstaller 打包
  - `build.bat --version` — 查看版本号
- **`setup.iss`**：版本从 `1.0.4` 更新为 `2.0.0`，与 `config.py` 保持一致；后续由 `build.py` 自动维护，无需手动修改。
- **涉及文件**：`build.py`（新增）、`build.bat`（新增）、`setup.iss`。

---

## 2026-04-07 - 开发/生产环境端口区分

- **端口区分**：开发模式 (`dev.py`) 默认端口 `8886`，生产模式 (`main.py`) 默认端口 `8887`，互不冲突，可同时运行。
- **环境标识**：`Config.APP_ENV` 标记当前环境（`development` / `production`）；`dev.py` 启动时自动设置。
- **页面区分**：开发环境下浏览器标签页标题追加 `[DEV:8886]`，侧栏版本号旁显示橙色 `DEV` 徽章，一眼区分。
- **环境变量**：可通过 `PORT`、`DEV_PORT`、`APP_ENV` 环境变量覆盖默认值。
- **涉及文件**：`config.py`、`dev.py`、`base.html`。

---

## 2026-04-07 - 定时任务扩展：新增 HTTP 请求 / Python 脚本类型 + 新建任务独立页面

### 新增任务类型

- **HTTP 定时请求**（`http_request`）：通用 HTTP 定时调用，支持 GET/POST/PUT/DELETE，可配置 URL、请求头、请求体、超时时间。适用于调用任意 API、Webhook 等场景。
- **Python 脚本**（`python_script`）：定时执行 Python 脚本，支持内联代码或指定脚本文件路径，可配置超时时间。脚本在独立子进程中执行，stdout/stderr 均捕获到日志。

### 页面重构

- **任务列表页** `/scheduler`：移除内嵌新增表单，顶部改为「+ 新建任务」按钮跳转至独立页面，列表页更简洁。
- **新建任务页** `/scheduler/add`（新增）：
  - 任务类型以卡片网格展示，每种类型显示图标、名称、描述。
  - Cron 定时规则提供 10 种常用预设（每 5 分钟、每小时整点、每天 09:00 等），点击即填入，并实时预览中文描述。
  - 选择类型后，下方动态渲染该类型的参数表单（字段、类型、必填、默认值、placeholder 均由后端 schema 驱动）。
  - 支持 text / number / select / json / code 五种字段渲染。

### 后端变更

- `scheduler/manager.py`：新增 `_run_http_request`、`_run_python_script` handler；新增 `get_task_type_schemas()` 返回每种类型的表单字段 schema。
- `api/routes/scheduler_routes.py`：`GET /api/scheduler/types?detail=1` 返回带 `fields` 和 `description` 的完整类型信息。
- `web/routes.py`：新增 `/scheduler/add` 页面路由。
- `base.html`：侧栏「定时任务」在新建页面也高亮。

### 涉及文件

- `src/scheduler/manager.py` — 新增 handler + schema
- `src/scheduler/__init__.py` — 导出 `get_task_type_schemas`
- `src/api/routes/scheduler_routes.py` — types API 增强
- `src/web/routes.py` — 新增 /scheduler/add 路由
- `src/web/templates/base.html` — 侧栏高亮条件
- `src/web/templates/scheduler.html` — 移除新增表单，改为按钮
- `src/web/templates/scheduler_add.html` — 新建任务独立页面（新增）

---

## 2026-04-07 - 任务运行日志独立分离 + 页面日志查看面板

### 功能增强

- **任务日志独立文件**（`utils/logger.py`）：新增 `get_task_logger()` 创建独立的 `TaskExec` 日志器，写入 `task_YYYY-MM-DD.log`（与 `app_*.log` 同目录）。该 logger 设置 `propagate=False`，不会混入应用日志文件，实现任务执行日志与页面/路由日志的完全分离。新增 `get_task_log_path()` 供 API 读取当天日志文件。

- **任务执行路径日志分离**（`scheduler/manager.py`）：
  - 引入 `tlog = get_task_logger("TaskExec")`，所有任务执行路径（`_run_task_by_id`、`run_task_by_id`）及 handler（`_run_order_1688_fill_detail`、`_run_pdd_erp_order_sync`、`_notify_pdd_erp_sync_result`）的日志改用 `_task_log()` / `tlog`，不再写入 app 日志。
  - 调度器基础设施日志（启动、注册、配置加载等）仍使用原 `logger`（Scheduler）写入 `app_*.log`。
  - 新增每个任务最近 200 条执行日志的内存缓冲（`_task_log_lines`），供页面实时查看。
  - Handler 函数签名增加 `_tid` 参数，执行时自动关联 task_id。

- **任务日志 API**（`api/routes/scheduler_routes.py`）：
  - `GET /api/scheduler/tasks/<id>/logs?n=50`：获取指定任务最近 N 条内存日志行。
  - `GET /api/scheduler/logs?n=100`：读取当天 `task_*.log` 文件最后 N 行（全局任务日志）。

- **定时任务页面日志面板**（`scheduler.html`）：
  - 每个任务卡片新增「日志」按钮，点击展开底部日志面板，显示该任务的执行日志。
  - 日志面板支持 Tab 切换：「全部任务日志」（读取 task_*.log 文件）/ 各任务独立日志（内存缓冲）。
  - 日志内容按级别着色：INFO 绿色、WARNING 黄色、ERROR 红色、DEBUG 蓝色。
  - 日志面板每 5 秒自动刷新（打开时），支持手动刷新和关闭。

### 日志分离策略

| 日志文件 | 内容 | Logger |
|---|---|---|
| `app_YYYY-MM-DD.log` | 应用全局日志（路由、启动、调度器注册等） | `Scheduler` / 根 logger |
| `task_YYYY-MM-DD.log` | 任务执行日志（开始、API 调用、结果、异常） | `TaskExec`（不 propagate） |

### 涉及文件

- `src/utils/logger.py` — 新增 `get_task_logger()`、`get_task_log_path()`
- `src/scheduler/manager.py` — `_task_log()`、`get_task_log_lines()`、执行路径改用 tlog
- `src/scheduler/__init__.py` — 导出 `get_task_log_lines`
- `src/api/routes/scheduler_routes.py` — 新增日志读取 API
- `src/web/templates/scheduler.html` — 日志面板 UI

---

## 2026-04-07 - 定时任务页面优化：执行状态追踪 + 任务暂停/恢复 + UI 重构

### 功能增强

- **执行状态追踪**（`scheduler/manager.py`）：新增内存级任务状态管理（`_task_status`），记录每个任务的 **运行中状态**、**开始时间**、**最后执行时间**、**最后执行结果**（成功/失败 + 消息摘要）。定时触发（`_run_task_by_id`）和手动触发（`run_task_by_id`）均自动追踪。`list_jobs` 返回字段增加 `running`、`started_at`、`last_run`、`last_success`、`last_message`、`type_name`、`enabled`。

- **任务暂停/恢复**：
  - `task_config.py`：新增 `update_task_field(task_id, field, value)` 方法，支持更新任务配置的任意字段（如 `enabled`）。
  - `manager.py`：新增 `pause_task(task_id)` 从调度器移除 job 并标记 `enabled=false`；`resume_task(task_id)` 恢复注册。`_register_jobs_from_config` 跳过 `enabled=false` 的任务。
  - API：`POST /api/scheduler/tasks/<id>/pause`、`POST /api/scheduler/tasks/<id>/resume`、`GET /api/scheduler/tasks/<id>/status`。

- **定时任务页面 UI 重构**（`scheduler.html`）：
  - 从表格布局改为 **任务卡片** 布局，每个任务一张卡片。
  - **状态徽章**：实时显示「执行中」（蓝色脉冲动画）、「✓ 成功」（绿色）、「✗ 失败」（红色）、「已暂停」（黄色）、「待运行」（灰色）。
  - **开关控件**：每个任务卡片内含启用/禁用 toggle switch，可直接暂停或恢复任务。
  - **cron 可读描述**：除显示原始 cron 外，增加中文周期描述（如 `0 12,18 * * *` → `每天 12:00、18:00`）。
  - **最后执行结果**：卡片底部展示上次执行的消息摘要，成功/失败用不同颜色左边框区分。
  - **下次执行时间**、**上次执行时间**、**任务 ID** 等元数据行。
  - **自动刷新**：默认每 10 秒轮询刷新（可关闭），执行中任务可实时看到状态变化。
  - **新增表单默认折叠**，减少页面干扰。

### 设计理念

所有功能都遵循「对应功能页面可交互运行 + 定时任务配置自动运行」的模式：功能页面（如订单同步 `/pdd-erp-order-sync`）负责单次交互执行，定时任务页面 `/scheduler` 负责配置周期性自动执行。新增功能只需在 `manager.py` 的 `get_task_handlers()` 注册 type + handler 即可同时支持两种运行方式。

### 涉及文件

- `src/scheduler/manager.py` — 状态追踪 + pause/resume + list_jobs 增强
- `src/scheduler/task_config.py` — `update_task_field`
- `src/scheduler/__init__.py` — 导出 `pause_task`、`resume_task`、`get_task_status`
- `src/api/routes/scheduler_routes.py` — 新增 pause / resume / status API
- `src/web/templates/scheduler.html` — UI 重构

---

## 2026-04-06 - 定时任务：拼多多 ERP 订单同步（12:00 / 18:00）+ 飞书结果通知

- **`scheduler/manager.py`**：新增任务类型 **`pdd_erp_order_sync`**，对本机 **`POST /api/pinduoduo/sync-erp-orders`** 发起请求（`timeout` 默认 780s）；结束后 **`_notify_pdd_erp_sync_result`** 向飞书私聊发送摘要（需 `FEISHU_ENABLED`、应用凭证及 **`FEISHU_USER_ID`** 或任务 **`data.feishu_user_id`**）。
- **双份配置**：界面读**运行时** `scheduler/tasks.json`（开发多为**仓库根** `scheduler/tasks.json`），种子为 **`src/scheduler/tasks.json`**；根目录 `scheduler/tasks.json` 已与种子同步包含 ERP 任务。
- **`task_config`**：版本文件 **`scheduler/.scheduler_seed_merge_version`** + **`_SCHEDULER_SEED_MERGE_VERSION`**，版本递增时把种子里缺失的 **任务 id** 自动合并进本地列表。

---

## 2026-04-06 - ERP 订单同步：注释与飞书「仅增量字段」更新

- **`erp_order_sync.py`**：补充模块/步骤中文注释，说明登录拦截、脚本注入与飞书调用关系。
- **`sync_erp_order_rows_to_feishu`**：仍以 **「平台订单号」** 判重；**新建** 仍写全量解析字段；**已存在** 时仅更新 **`ERP_FEISHU_PARTIAL_UPDATE_FIELD_KEYS`**（快递公司、快递单号、订单状态、提醒、运费、是否打印快递单、是否有售后）。若已存在行且上述列在当次抓取中均为空，则 **不调飞书更新接口**，统计 **`update_skipped_no_delta`**。

---

## 2026-04-06 - ERP 同步飞书：数字/日期列类型与失败日志

- **`feishutable._erp_row_to_fields`**：对 **`ERP_FEISHU_NUMBER_FIELD_KEYS`**（重量、体积、商品总数、金额类等）写入 **float**；对 **`ERP_FEISHU_DATETIME_FIELD_KEYS`**（付款/审核/发货时间）写入 **Unix 毫秒 int**，避免 **`NumberFieldConvFail` / `DatetimeFieldConvFail`**。无法解析时 **warning** 并跳过该字段，不再把字符串强写给数字/日期列。
- **`FeishuTableClient`**：`_make_request` 在 `code!=0` 时记录 **http_status** 与 **完整 JSON 体**（截断 4k）；**create / update / batch_create / batch_update** 失败时附加 **`_feishu_fields_debug_str`**（字段名、Python 类型、截断值）。

---

## 2026-04-06 - 订单同步（拼多多官方 ERP → 飞书）

- **页面**：侧栏「订单同步」、`/pdd-erp-order-sync`，模板 **`src/web/templates/pinduoduo_erp_order_sync.html`**。
- **API**：`POST /api/pinduoduo/sync-erp-orders`（可选 `app_token`、`table_id`、`scroll_max_steps`），浏览器池超时 720s；执行 **`src/spider/pinduoduo/erp_order_sync.py`**，页面脚本 **`pdd-erp-order-all-table.js`**（`__PDD_ERP_ORDER_ALL_RUN_MODE='python'`）。
- **飞书**：新增 **`sync_erp_order_rows_to_feishu`**（按 **`平台订单号`** upsert；收件类字段与表格已加密 `*` 较多时不覆盖）。默认表 **`tblyAX9t4DJK2wuJ`**，配置项 **`PINDUODUO_ERP_ORDER_ALL_URL`**、**`PINDUODUO_ERP_FEISHU_TABLE_ID`**、**`PINDUODUO_ERP_FEISHU_VIEW_ID`**（视图 ID 供与多维表格 URL 对齐文档，同步接口仍扫全表记录）。
- **登录拦截**：与订单地址同步一致——飞书应用消息、拼多多渠道 Webhook 卡片、返回 **`qrcode`** 供前端展示。

---

## 2026-03-29 - 拼多多订单地址同步：仅最近 N 天订单（默认 2 天）

扫描 `need_fill` 时要求订单时间在 **`Config.PINDUODUO_ADDRESS_SYNC_RECENT_DAYS`**（默认 **2**，环境变量 **`PINDUODUO_ADDRESS_SYNC_RECENT_DAYS`**，限制 1–90）内；时间列依次尝试 **`订单时间`**、**`订单提交时间`**、**`order_time`**。`checked` 增加 **`order_in_recent_days`**。可选 **`PINDUODUO_ADDRESS_SYNC_SORT_FIELD`**（如 `订单时间`）按列降序拉取；整页「最新单」仍早于窗口则提前停止翻页；带排序若接口失败会退化为无排序。

---

## 2026-03-29 - 拼多多订单地址同步：top_n 表示「缺手机号条数」而非只扫前 N 行

`sync_order_addresses_from_feishu_top_records` 改为按 **`list_records` 分页** 扫描当前 **view**，直到凑满 **top_n 条**「有订单号、无手机号」或表结束（最多 500 页、每页最多 500 条，防死循环）。响应增加 **`rows_scanned`**（本轮实际遍历行数）。非「只取接口前 top_n 行」。

---

## 2026-03-29 - pdd-order-search-receiver：座机号识别（如 021-53395199）

`extractPhone` 增加国内座机 **`0+区号-号码`**（ hyphen 左右可有空格、支持全角－），并在标签中增加 **固定电话 / 座机**；仍优先匹配带「手机 / 联系电话 / 收货电话…」前缀的片段，再兜底 11 位手机与隐私号。

---

## 2026-03-29 - 拼多多订单地址同步：飞书列名改为「手机号」「收货信息」

`order_address_sync` 写回与缺数检测统一使用 **`FEISHU_COL_PHONE`=`手机号`**、**`FEISHU_COL_RECEIVER_INFO`=`收货信息`**（与表格实际表头一致）。`FeishuTableClient.update_record` 对 **`data` 为空 `{}` 的成功响应** 不再误判为失败；调用方以 **`updated is not None`** 判定成功。

---

## 2026-03-29 - 飞书 Webhook 按模块拆分（qudao_notify）

新增 **`src/tools/feishu/webhook/qudao_notify.py`**：`CHANNEL_PINDUODUO`、`get_webhook_url`、`get_custom_bot_keyword`；拼多多默认使用指定 Hook，可用 **`FEISHU_WEBHOOK_PINDUODUO`** 覆盖；关键词默认 **拼多多**（规避 **19024 Key Words Not Found**），可用 **`FEISHU_WEBHOOK_PINDUODUO_KEYWORD`** 覆盖，若变量存在且为空则不再注入。`notify.build_sync_notification_card` / `send_sync_notification` 增加 **`custom_bot_keyword`**。拼多多订单地址同步登录拦截改为走 **`get_webhook_url(CHANNEL_PINDUODUO)`**。

---

## 2026-03-29 - 拼多多订单地址同步：Webhook 登录通知修复

`order_address_sync` 在检测到登录拦截发送 **`send_sync_notification`** 时改为分支内 **延迟 import**，避免运行时报 **`NameError: send_sync_notification is not defined`**。二维码参数改为 **`image_base64`**（与 `show_login_qrcode` 返回的 `data:image/png;base64,...` 一致）。仅在配置 **`FEISHU_SYNC_WEBHOOK_URL`** 时发送；失败记录 warning。

---

## 2026-03-29 - 飞书 Webhook 卡片：Base64 二维码 → 上传得 img_key

`build_sync_notification_card` / `send_sync_notification` 新增 **`image_base64`**（支持 `data:image/png;base64,...` 或纯 base64）。内部解码后调用开放平台 **`im/v1/images`**（`upload_image_get_img_key`），将返回的 **`image_key`** 写入卡片 **`img`** 组件；需在 `.env` 配置 **`FEISHU_APP_ID` / `FEISHU_APP_SECRET`** 且应用具备上传图片相关权限。上传失败时在正文中提示检查凭据与权限。与 **`image_url`** 并存时：Base64 成功后不再在 `lark_md` 里嵌外链图。

---

## 2026-03-29 - 飞书 Webhook 同步通知卡片模板

新增 **`src/tools/feishu/webhook/`**：`build_sync_notification_card`、`send_sync_notification`、`send_webhook_raw`；交互卡片含标题（对应系统）、`lark_md` 描述与链接、`![](url)` 配图、主按钮与底栏时间。配置 **`FEISHU_SYNC_WEBHOOK_URL`**（`.env`）。详见 [自定义机器人](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)。

---

## 2026-03-29 - 拼多多订单列表 `tab=0` 与登录拦截返回二维码

- **`PINDUODUO_ORDERS_LIST_URL`**（默认 `orders/list?tab=0`，可环境变量覆盖）。
- 同步地址打开列表后若 **login**：飞书提醒 + **`show_login_qrcode(skip_initial_navigation=True)`**，API **`intercepted` + `qrcode`**；`pinduoduo.html` 同步按钮侧展示二维码并轮询登录。

---

## 2026-03-29 - 拼多多飞书：清理无订单号、同步 PDD 订单地址 API 与页面按钮

### 功能

1. **删除无「订单号」行**：`POST /api/pinduoduo/feishu/cleanup-empty-order-sn`，全表扫描后批量删除订单号为空的记录。
2. **同步 PDD 订单地址**：`POST /api/pinduoduo/sync-order-addresses`，`list_records` 增参 **`view_id`**（与多维表格 URL `view=` 一致，默认 `Config.PINDUODUO_FEISHU_VIEW_ID`），避免接口返回 0 条导致从不 `goto` 订单页；打开列表后 **`page.bring_to_front()`** 便于看见 Playwright 窗口。缺「收件人手机号」则执行 `pdd-order-search-receiver.js` 并回写飞书。
3. **页面**：`pinduoduo.html` 增加对应按钮；默认 App Token / Table ID 与 `Config` 一致（表 `tblyxGarbBwHi25M`）。

### 涉及文件

- 新增 **`src/spider/pinduoduo/order_address_sync.py`**
- **`src/spider/pinduoduo/feishutable.py`**、`src/api/routes/pinduoduo_routes.py`、`src/config.py`、`src/web/templates/tools/pinduoduo.html**

---

## 2026-03-29 - 浏览器驱动目录改为与 `playwright install` 一致

本地 `playwright_drivers` 已由平铺的 `chrome-win64/` 调整为官方布局：`playwright_drivers/chromium-1208/chrome-win64/chrome.exe`（与当前 Playwright 期望的 `chromium-1208` 一致）。代码仍兼容平铺路径，便于他人或临时解压。

---

## 2026-03-29 - `browser_path`：支持 `playwright_drivers/chrome-win64` 平铺布局

### 说明

手动解压官方 `chrome-win64.zip` 时，常见目录为 **`项目根/playwright_drivers/chrome-win64/chrome.exe`**，中间没有 **`chromium-****` 子目录**。原 `find_chrome_executable()` 只识别 `playwright_drivers/chromium-*`，导致未设置 `executable_path`，Playwright 仍去 **`%LOCALAPPDATA%\ms-playwright\chromium-1208\...`** 并报 `Executable doesn't exist`。

### 改动

- **`src/utils/browser_path.py`**：在无匹配的 `chromium-*` 时，再尝试 `playwright_drivers/chrome-win64/chrome.exe` 与 `playwright_drivers/chrome-win/chrome.exe`，并设置 `PLAYWRIGHT_BROWSERS_PATH`。

---

## 2026-03-29 - Windows：VC++ 已注册但 System32 无 `msvcp140` 时的 DLL 兜底

### 现象

「已安装」VC++ x64（控制面板可见），仍报 `greenlet` / `_greenlet` DLL 加载失败。

### 原因

注册表中有卸载项，但 **`C:\Windows\System32\msvcp140.dll` 未部署**（常见于此前安装报 `0x80070005` 等，只登记、未复制 CRT）。同机 `System32\Microsoft-Edge-WebView` 下往往已有同名 CRT，可被 `os.add_dll_directory` 用于加载扩展。

### 代码

- 新增 **`src/utils/win32_msvc_runtime.py`**：`add_dll_search_paths_if_needed()`，在 System32 缺 `msvcp140.dll` 时把 Edge WebView CRT 目录加入 DLL 搜索路径。
- **`src/dev.py`**、**`src/main.py`**：在其余导入前调用上述函数。

**仍建议**：在「程序和功能」中对 *Microsoft Visual C++ 2015–2022 Redistributable (x64)* 执行**修复**或**卸载后管理员重装**，使 CRT 回到 System32，避免依赖 Edge 目录。

---

## 2026-03-29 - 环境问题：`greenlet` DLL 加载失败（缺 VC++ 运行库）

### 现象

调试 `dev.py` 时在 `import playwright.sync_api` 链上报错：`ImportError: DLL load failed while importing _greenlet`（找不到指定模块）。

### 原因

`_greenlet.cp312-win_amd64.pyd` 依赖系统上的 **MSVC 运行库**（如 `msvcp140.dll` 等）。当前环境 `C:\Windows\System32\msvcp140.dll` 不存在；`pip reinstall greenlet` 无效。

### 处理

1. 以**管理员**身份安装 **[Visual C++ Redistributable for Visual Studio 2015–2022 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)**（或从微软下载中心获取同名安装包）。
2. 若公司策略限制安装，需 IT 放行；本机曾出现安装程序 `0x80070005`（写注册表被拒绝），与权限或策略有关。

---

## 2026-03-29 - 还原 VS Code `launch.json`（按历史日志）

### 变更说明

`.vscode/launch.json` 丢失后，根据 `docs/log.md` 中 **2026-01-21 - 添加开发模式支持热重载** 的说明与 `docs/开发指南.md` 中的调试配置结构重新写入。

**配置项**：
- **调试主程序（完整版）**：入口 `${workspaceFolder}/src/main.py`，`PYTHONPATH` 指向工作区，`cwd` 为工作区根目录。
- **开发模式（热重载）**：入口 `${workspaceFolder}/src/dev.py`，同上并增加 `FLASK_ENV=development`、`FLASK_DEBUG=1`。

**说明**：仓库 `HEAD` 中此前未跟踪该文件，故无法从 git 直接取回；内容与文档记载一致。

---

## 2026-02-24 - 1688 订单缓存目录迁入 cache

### 变更说明

将 1688 订单相关缓存从项目根目录的 `order_1688/catch` 迁入统一缓存目录 `cache/order_1688`，并去掉中间的 `catch` 子目录，文件直接存放在 `cache/order_1688` 下。

**目录与文件**：
- **迁移**：原 `order_1688/catch/orders_*.json`、`detail_quota.json` 等 → `cache/order_1688/` 下同名文件；已将 `orders_2026-02-24.json` 迁移至 `cache/order_1688/`。
- **删除**：已删除原 `order_1688/` 目录（含 `catch` 子目录）。

**代码**（`src/spider/order_1688/order_extract.py`）：
- `get_catch_dir()` 重命名为 `get_order_1688_cache_dir()`，路径由 `order_1688/catch` 改为 `cache/order_1688`。
- `cleanup_old_catch_files()` 重命名为 `cleanup_old_cache_files()`，清理逻辑改为针对 `cache/order_1688` 下非当日 JSON 文件。
- 当日订单缓存路径仍为 `orders_YYYY-MM-DD.json`，详情配额文件仍为 `detail_quota.json`，均位于 `cache/order_1688` 下。

---

## 2026-02-24 - 定时任务模块（APScheduler）

### 变更说明

新增统一定时任务模块，用于管理如「1688 订单补详情」等按周期执行的任务，支持配置开关与 cron 表达式。

**配置**（`config.Config`）：
- `SCHEDULER_ENABLED`：是否启用定时任务模块（默认 True）。
- `SCHEDULER_ORDER_1688_FILL_CRON`：1688 补详情任务的 cron 表达式，五段「分 时 日 月 周」（默认 `0 * * * *`，即每小时整点）。可通过环境变量覆盖。

**新增**：
- **`src/scheduler/`**：定时任务包。`manager.py` 基于 APScheduler 的 BackgroundScheduler，注册任务 `order_1688_fill_detail`，提供 `start_scheduler()`、`shutdown_scheduler()`、`list_jobs()`。
- **`src/api/routes/scheduler_routes.py`**：`GET /api/scheduler/jobs` 列出任务，`POST /api/scheduler/trigger/<job_id>` 手动触发。
- **`requirements.txt`**：新增 `APScheduler>=3.10.0`。
- **`main.py`**：Flask 启动后调用 `start_scheduler()`，`cleanup()` 时调用 `shutdown_scheduler()`。

---

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

## 2026-04-10 - 项目架构与逻辑全面梳理

### 文档新增（2026-04-10）

**新增内容**:
- 创建 `docs/project.md` — 项目架构与逻辑完整梳理文档

**文档覆盖范围**:
- 项目概览与核心功能矩阵（10 个功能模块）
- 技术栈与依赖清单（13 个核心依赖）
- 完整目录结构（74 个 Python 源文件、15 个 HTML 模板）
- 启动流程与生命周期（10 步启动序列、7 个线程模型）
- 核心架构设计：分层架构、BrowserPool 流程、BaseTool 体系
- 6 大业务模块详细梳理：拼多多（含 ERP 同步/库存同步）、途强、1688、快递查询、脚本执行器
- API 路由总览：10 个 Blueprint、30+ 端点
- Web 页面与模板体系
- 定时任务系统：5 种任务类型、种子合并机制、启动补跑
- 飞书集成：7 个同步场景、12 个配置项
- WebSocket 客户端：Socket.IO + action 映射
- 配置体系：5 层优先级、20+ 配置项
- 数据存储与路径策略
- 打包与部署
- 已知问题与优化方向（架构/代码/性能/安全 4 个维度、20+ 条优化建议）
- 附录：数据流总图、环境变量完整列表（30+ 变量）

**新增文件**:
- `docs/project.md` — 项目完整架构梳理文档

## 2026-04-10 - 配置文件格式从 JSON 迁移到 TOML

### 重构（2026-04-10）

**变更原因**:
- JSON 不支持注释，配置项无法附带说明，维护体验差
- TOML 是 Python 生态事实标准（pyproject.toml），语法简洁、类型原生、支持 `#` 注释

**变更内容**:
- `app_config.json` → `app_config.toml`（应用配置）
- `module_config.json` → `module_config.toml`（模块配置）
- `scheduler/tasks.json` → `scheduler/tasks.toml`（定时任务配置）
- `src/scheduler/tasks.json` → `src/scheduler/tasks.toml`（种子配置）
- `task_last_success.json` 保持 JSON（纯内部数据，不需要注释）

**新增文件**:
- `src/utils/toml_helper.py` — TOML 读写兼容层（Python 3.8-3.10 用 tomli，3.11+ 用内置 tomllib）

**修改文件**:
- `src/utils/config_manager.py` — 读写逻辑从 json 切换到 toml_helper
- `src/config.py` — module_config 读写逻辑切换到 toml_helper
- `src/scheduler/task_config.py` — 任务配置读写切换到 toml_helper，种子加载兼容 .toml 和旧 .json
- `src/api/routes/websocket_routes.py` — 更新注释引用
- `requirements.txt` — 新增 tomli>=2.0.0、tomli-w>=1.0.0

**迁移兼容**:
- 首次升级时自动把旧 JSON 迁移为 TOML（迁移后删除旧 JSON）
- 种子文件加载优先 .toml，兼容旧 .json
- 已有用户无需手动操作，程序自动完成迁移

## 2026-04-10 - 库存扣减测算逻辑（带开关）

### 新增功能（2026-04-10）

**变更原因**:
- `inventory_sync_job.py` 原来只写日志表（出库/退货记录），不做实际库存扣减
- 参考 `xixidan_inventory_reconcile.py` 的扣减逻辑，在同一文件中实现真实库存扣减

**实现要点**:
- 新增常量 `_INVENTORY_DEDUCT_APPLY`（默认 `False`），作为库存扣减开关
- 开关关闭时：只打印测算日志（汇总每个商品的净出库量、当前库存、扣后库存），不写飞书
- 开关开启时：写回库存信息表 `数量` 列，并勾选日志行 `库存已核销` 复选框
- 扣减公式：`净出库 = 出库数量 - 退货数量`，按 `库存关联`（商品名称）分组汇总
- 自动跳过已核销、空链接、未匹配的日志行
- 孤儿链接（日志有分组但库存表无同名商品）单独 warning 日志

**修改文件**:
- `src/spider/pinduoduo/inventory_sync_job.py`
  - 新增常量：`_LOG_COL_CONSUMED`、`_INV_COL_STOCK`、`_INVENTORY_DEDUCT_APPLY`
  - 新增辅助函数：`_is_consumed()` — 判断飞书复选框值
  - 在 `run_inventory_sync_job()` 退货更新之后新增库存扣减测算阶段
  - 返回值增加 `deduct_*` 系列字段

## 2026-04-12 - 库存映射配置页面

### 新增功能（2026-04-12）

**变更原因**:
- AI 匹配商品名称过程不够直观，用户无法控制哪些商品信息对应哪些库存商品
- 需要人工维护「商品信息 → 商品名称」的映射关系，替代或优先于 AI 匹配
- 部分商品不需要库存匹配，需要提供「空」占位符来跳过

**实现要点**:
- 在 `/tools/pinduoduo` 页面新增「库存映射配置」卡片
- 左列显示扣减日志表的「商品信息」（去重、可搜索过滤）
- 右列为库存信息表「商品名称」的多选下拉（含搜索、标签展示）
- 特殊选项「空」表示跳过该商品的库存匹配
- 映射数据以 JSON 持久化到本地 `config/inventory_product_mapping.json`

**新增文件**:
- `src/spider/pinduoduo/inventory_mapping.py` — 映射持久化模块（load/save/query）

**修改文件**:
- `src/api/routes/pinduoduo_routes.py`
  - `GET /api/pinduoduo/inventory-mapping/data` — 获取商品信息列表 + 商品名称列表 + 已保存映射
  - `POST /api/pinduoduo/inventory-mapping/save` — 保存映射到本地
- `src/web/templates/tools/pinduoduo.html` — 新增映射配置 UI 卡片（CSS + JS 内联）

## 2026-04-18 - 移除拼多多页面冗余卡片

### UI 清理（2026-04-18）

**变更原因**:
- 「登录状态」卡片、「同步到飞书表格」卡片、「🚀 自动化功能（开发中）」TODO 卡片不再需要，予以移除

**修改文件**:
- `src/web/templates/tools/pinduoduo.html`
  - 删除「登录状态」`.status-card` 区块（登录/同步订单/刷新/清除登录按钮）
  - 删除「同步到飞书表格」`.feishu-sync-card` 区块（飞书同步、清理订单号、同步地址按钮）
  - 删除「🚀 自动化功能（开发中）」`.todo-card` 区块及二维码展示区块
  - 移除与上述卡片相关的 CSS（`.status-indicator*`、`.status-info*`、`.qrcode-*`、`.todo-*`、`.feishu-sync-*`）
  - 移除与上述卡片相关的所有 JS 事件监听和函数（refreshStatus、syncOrders、startLogin、clearCookies、syncToFeishu 等）
  - 页面现仅保留「库存映射配置」卡片

---

## 2026-04-12 - 库存映射集成到同步任务

### 修复（2026-04-12）

**变更原因**:
- 库存映射配置页面已可保存映射数据，但 `inventory_sync_job.py` 未使用该映射
- 所有订单仍走 AI 匹配，导致大量不必要的 API 调用

**修改文件**:
- `src/spider/pinduoduo/inventory_sync_job.py`
  - 导入 `load_mappings` 和 `SKIP_PLACEHOLDER`
  - 在匹配逻辑前加载手动映射，优先查映射：
    - 映射为 `["空"]` → 跳过该订单（不写日志行）
    - 映射命中 → 直接使用映射的商品名称作为库存关联，跳过 AI
    - 多个映射名称 → 按套装逻辑生成多条日志行
    - 未配置映射 → 走原有 AI 匹配流程
  - 返回值和日志增加 `mapping_hit` / `mapping_skip` 统计

---

## 2026-05-26 - 淘宝商品采集接口同步升级（SKU价格 + 规格结构）

### 功能增强（2026-05-26）

**变更原因**:
- `docs/webauto脚本文档/taobao-商品信息采集.md` 同步了最新采集脚本（2026-05-26）
- 采集脚本新增 `skus` 字段（SKU精确价格列表），`specs.values` 改为对象数组（含 `text/img/vid/empty/price`）
- 原接口不支持 `skus` 字段保存，规格 Sheet 也缺少新增的价格/图片/vid/缺货列

**修改文件**:
- `src/api/routes/taobao_routes.py`
  - 模块注释更新：单品 Excel 从「四个 Sheet」改为「五个 Sheet（含 SKU价格）」
  - `SUMMARY_HEADERS`：`规格数` 改为 `规格值数`（与文档对齐）
  - `_write_product_excel`：
    - Sheet 2 规格：表头扩展为 `规格标签 / 规格值 / 价格 / 图片URL / vid / 缺货`，兼容旧格式（字符串）和新格式（对象）
    - 新增 Sheet 3 SKU价格：`skuId / 规格组合 / 价格 / 缺货`，来自 `skus` 字段
    - Sheet 编号顺序后移：参数→Sheet4，图片→Sheet5
  - Swagger 文档：新增 `skus` 参数描述，更新 `specs` 描述

---

## 2026-06-04 - 安特限时秒杀列表采集入库功能上线

### 新功能

**变更原因**：
- 安特 PC 商城（`https://pc.antexiadan.com`）限时秒杀商品需要定期采集存档，用于选品分析与历史对比

**新增文件**：
- `src/api/routes/antexiadan_routes.py` — Flask Blueprint，`url_prefix=/api/antexiadan`，三条路由：
  - `POST /api/antexiadan/seckill-list/sync` — 接收 webAuto 采集结果，写批次 + UPSERT 商品 + 可选快照
  - `GET /api/antexiadan/seckill-list/products` — 查询当前态商品（支持 `activity_status`、`group_title`、`slot_time`、`limit`、`offset`）
  - `GET /api/antexiadan/seckill-list/batch/latest` — 查询最近一次抓取批次元数据
- `src/spider/antexiadan/seckill_store.py` — SQLite 存储层（默认 `data/antexiadan_seckill.sqlite`，可由 `ANTEXIADAN_SECKILL_DB_PATH` 覆盖），包含：
  - `init_db()` — 建三张表（`antexiadan_seckill_fetch_batch` / `antexiadan_seckill_product` / `antexiadan_seckill_product_snapshot`）及索引
  - `sync_payload()` — 事务写入：插入批次 → UPSERT 商品 → 按 `writeSnapshot` 决定是否写快照
  - `list_products()` / `get_latest_batch()` — 查询接口
- `src/spider/antexiadan/__init__.py` — 包初始化

**webAuto 侧脚本**（`C:\Users\yao\Desktop\work\webAuto\mcp-server\script\`）：
- `antexiadan-seckill-list.js` — 页面内 fetch pcapi，双运行时（`extension` 走扩展桥 POST；`python` 返回 `syncUrl/syncBody` 由 Python 调用）；支持 `window.__ANTEXI_SECKILL_API_KEY` / `__ANTEXI_SECKILL_SYNC_URL` / `__ANTEXI_SECKILL_SYNC` 配置
- `antexiadan-seckill-fetch.py` — Python 直连 pcapi（不依赖浏览器），支持 `--sync` 直接 POST 入库、`-o` 导出 JSON/CSV，key 通过 `ANTEXI_API_KEY` 环境变量或 `--key` 传入

**注册变更**：
- `src/api/routes/__init__.py` — 已注册 `antexiadan_bp`，Swagger 标签 `安特`

---

## 2026-06-04 - 安特限时秒杀页面

### 新增文件
- `src/web/templates/antexiadan_seckill.html` — 限时秒杀商品列表页，功能：
  - 顶部批次卡：显示最近一次抓取时间、服务端时间、商品数、来源
  - 统计标签：总数 / 秒杀中 / 预热中 / 已结束分色显示
  - 多维筛选栏：活动状态、分组、时段、关键词（标题/ID）
  - 商品表格：状态徽章、分组、时段、标题、价格、开始/结束时间、秒杀ID、商品ID
  - 前端排序（点击表头切换升降序）、分页（每页 50/100/200/500 可选）
  - 页面打开自动加载，「刷新数据」按钮手动触发

### 修改文件
- `src/web/routes.py` — 新增 `GET /antexiadan/seckill` → 渲染 `antexiadan_seckill.html`
- `src/web/templates/base.html` — 侧边栏「电商」分组后新增「安特」折叠分组，子项「限时秒杀」链接至 `/antexiadan/seckill`
**数据库表结构**：
- `antexiadan_seckill_fetch_batch` — 每次抓取批次元数据（`fetched_at`、`server_time`、`item_count` 等）
- `antexiadan_seckill_product` — 商品当前态（按 `seckill_id` UPSERT，含 `last_fetch_batch_id`、`updated_at`）
- `antexiadan_seckill_product_snapshot` — 每批次全量快照（`UNIQUE(fetch_batch_id, seckill_id)`）

**关联文档**：
- `docs/webauto脚本文档/安特/antexiadan-限时秒杀列表.md`
- `docs/sql/antexiadan-seckill-db-schema.mysql.sql`（MySQL DDL，已由用户手动初始化）
- webAuto：`docs/安特/antexiadan-seckill-list.md`

---

## 2026-06-04 - 安特秒杀存储层改为 MySQL

### 变更原因

用户使用 MySQL，已通过 `docs/sql/antexiadan-seckill-db-schema.mysql.sql` 初始化三张表。

### 修改文件

- `requirements.txt` — 新增 `pymysql>=1.1.0`
- `src/config.py`
  - 移除 `ANTEXIADAN_SECKILL_DB_PATH`（SQLite 路径）
  - 新增 MySQL 连接参数（均可通过 `.env` 覆盖）：
    - `ANTEXIADAN_DB_HOST`（默认 `localhost`）
    - `ANTEXIADAN_DB_PORT`（默认 `3306`）
    - `ANTEXIADAN_DB_USER`（默认 `root`）
    - `ANTEXIADAN_DB_PASSWORD`
    - `ANTEXIADAN_DB_NAME`（默认 `antexiadan`）
    - `ANTEXIADAN_DB_CHARSET`（默认 `utf8mb4`）
- `src/spider/antexiadan/seckill_store.py` — 完全重写：
  - 移除 `sqlite3` / `init_db()`，改用 `pymysql.connect()` + `DictCursor`
  - `_PRODUCT_UPSERT_SQL` 改为 `INSERT ... ON DUPLICATE KEY UPDATE`
  - `_SNAPSHOT_INSERT_SQL` 改为 `INSERT IGNORE INTO ...`
  - `_row_tuple` 空字符串改为 `None`（MySQL NULL 友好）
  - 去掉 `dbPath` 返回字段（MySQL 无路径概念）
