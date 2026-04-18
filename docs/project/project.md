# 如意助手 — 项目架构与逻辑梳理

> **梳理日期**: 2026-04-10
> **项目版本**: 2.0.0
> **项目名称**: 如意助手（assistantService）

---

## 目录

1. [项目概览](#1-项目概览)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [完整目录结构](#3-完整目录结构)
4. [启动流程与生命周期](#4-启动流程与生命周期)
5. [核心架构设计](#5-核心架构设计)
6. [模块详细梳理](#6-模块详细梳理)
7. [API 路由总览](#7-api-路由总览)
8. [Web 页面与模板](#8-web-页面与模板)
9. [定时任务系统](#9-定时任务系统)
10. [飞书集成](#10-飞书集成)
11. [WebSocket 客户端](#11-websocket-客户端)
12. [配置体系](#12-配置体系)
13. [数据存储与路径](#13-数据存储与路径)
14. [打包与部署](#14-打包与部署)
15. [已知问题与优化方向](#15-已知问题与优化方向)

---

## 1. 项目概览

### 1.1 产品定位

「如意助手」是一个基于 Python 开发的 **Windows 桌面私人助手应用**，以 Flask HTTP 服务为核心，结合 pywebview 原生窗口、pystray 系统托盘、Playwright 浏览器自动化，提供多种电商运营自动化功能。

### 1.2 核心功能矩阵

| 功能模块 | 说明 | 是否需要浏览器 | 默认启用 |
|----------|------|:---------:|:------:|
| **拼多多助手** | 商家后台自动化：登录管理、订单抓取、飞书同步 | 是 | 是 |
| **拼多多 ERP 订单同步** | 官方 ERP 全部订单表 → 飞书多维表格 | 是 | 是 |
| **拼多多库存同步** | 飞书 ERP 表 → 库存信息表 + 扣减日志表 | 否（纯 API） | 否 |
| **途强助手** | iot.tqiot.com 自动登录 + 最近 30 天记录 | 是 | 是 |
| **1688 订单提取** | 待收货订单列表提取 + 飞书多维表格同步 | 是 | 是 |
| **脚本执行器** | Python 脚本执行，支持参数传递 | 否 | 是 |
| **快递查询** | 快递100/百度搜索物流信息查询 | 是 | 否（已禁用） |
| **定时任务** | APScheduler 定时触发各种任务 | 按任务类型 | 是 |
| **WebSocket 客户端** | Socket.IO 对接远程服务端 | 否 | 是 |
| **飞书通知** | 登录失效提醒、任务结果推送、Webhook | 否 | 是 |

### 1.3 运行架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                    主线程 (main.py)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  系统托盘    │  │  原生窗口    │  │   信号处理/生命周期  │   │
│  │  (pystray)   │  │  (pywebview) │  │   (shutdown_event)  │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                            ↕ 控制
┌─────────────────────────────────────────────────────────────────┐
│                   Flask 线程 (daemon)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Flask App   │  │  浏览器池    │  │  工具管理器  │          │
│  │  (HTTP API)  │  │ (BrowserPool)│  │ (ToolManager)│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│  ┌──────────────┐  ┌──────────────┐                             │
│  │  定时任务    │  │  WebSocket   │                             │
│  │ (APScheduler)│  │  (Socket.IO) │                             │
│  └──────────────┘  └──────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
                            ↕
┌─────────────────────────────────────────────────────────────────┐
│              Playwright 专用线程 (ThreadPoolExecutor)            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  持久化 BrowserContext (chromium) + 复用 Page             │   │
│  │  cookie/localStorage/sessionStorage 跨次运行持久化        │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 技术栈与依赖

### 2.1 核心依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 运行时 |
| Flask | ≥2.3.0 | HTTP API + Web 界面 |
| flasgger | ≥0.9.7 | Swagger API 文档（`/api/docs`） |
| Playwright | ≥1.40.0 | 浏览器自动化（Chromium） |
| requests | ≥2.31.0 | HTTP 请求 |
| pystray | ≥0.19.0 | Windows 系统托盘 |
| Pillow | ≥10.0.0 | 图标处理 |
| pywebview | ≥4.4.0 | 原生桌面窗口 |
| python-dotenv | ≥1.0.0 | `.env` 环境变量 |
| python-socketio[client] | ≥5.10.0 | Socket.IO 客户端 |
| APScheduler | ≥3.10.0 | 定时任务调度 |
| croniter | ≥2.0.0 | Cron 表达式解析 |
| openai | ≥1.0.0 | AI API（库存关联匹配） |
| PyInstaller | ≥6.0.0 | 打包为 exe |

### 2.2 运行环境

- **操作系统**: Windows 10/11 (64 位)
- **内存**: 建议 4GB+（Playwright 浏览器 + Flask 服务）
- **网络**: 需要（爬虫、飞书 API、Socket.IO）

---

## 3. 完整目录结构

```
assistantService/
├── src/                              # ===== 源代码 =====
│   ├── main.py                       # 主程序入口（托盘、窗口、Flask线程）
│   ├── app.py                        # Flask 应用工厂 + 浏览器池/工具初始化
│   ├── config.py                     # 全局配置类（Config）
│   ├── dev.py                        # 开发模式入口
│   ├── JNSpider.py                   # 旧版快递查询服务入口（独立运行）
│   ├── JNTools.py                    # 旧版工具入口（已整合到 main.py）
│   │
│   ├── config/                       # 配置子模块
│   │   ├── __init__.py               # 动态导入 config.py 避免循环引用
│   │   └── modules.py                # 功能模块默认配置定义
│   │
│   ├── api/                          # ===== API 路由层 =====
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py           # Blueprint 注册中心 + Swagger 配置
│   │   │   ├── context.py            # 共享上下文（browser_pool 引用）
│   │   │   ├── health.py             # GET /health, GET/POST/DELETE /startup
│   │   │   ├── script_routes.py      # POST /api/scripts/run
│   │   │   ├── settings_routes.py    # GET/PUT /api/settings, /api/modules
│   │   │   ├── browser_routes.py     # GET /api/browser/status
│   │   │   ├── pinduoduo_routes.py   # /api/pinduoduo/* (登录/状态/同步)
│   │   │   ├── tu_routes.py          # /api/tu/* (途强)
│   │   │   ├── feishu_routes.py      # /api/feishu/* (飞书消息/表格)
│   │   │   ├── order_1688_routes.py  # /api/order_1688/* (1688订单)
│   │   │   ├── websocket_routes.py   # /api/ws/* (WebSocket管理)
│   │   │   └── scheduler_routes.py   # /api/scheduler/* (定时任务)
│   │   └── service/
│   │       ├── __init__.py
│   │       └── feishu_compare.py     # 飞书数据比对服务
│   │
│   ├── spider/                       # ===== 爬虫/自动化层 =====
│   │   ├── __init__.py
│   │   ├── query_manager.py          # BrowserPool — 浏览器代理核心
│   │   ├── logistics_query.py        # 物流查询逻辑（快递100/百度）
│   │   ├── logistics_service.py      # 物流查询服务封装
│   │   ├── waybill_extractor.py      # 运单号提取
│   │   ├── pinduoduo/                # 拼多多自动化
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # PinduoduoClient — 登录/订单/状态
│   │   │   ├── feishutable.py        # 订单 → 飞书多维表格同步
│   │   │   ├── order_address_sync.py # 订单地址同步
│   │   │   ├── erp_order_sync.py     # ERP 全部订单表抓取
│   │   │   ├── inventory_sync_job.py # 库存飞书同步（ERP→库存/日志）
│   │   │   └── scripts/              # 浏览器端注入的 JS 脚本
│   │   │       └── pdd-erp-order-all-table.js
│   │   ├── tu/                       # 途强自动化
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # TuClient — 登录/数据获取
│   │   │   └── feishutable.py        # 途强数据 → 飞书同步
│   │   └── order_1688/               # 1688 订单提取
│   │       └── order_extract.py      # 列表页提取 + 详情补全 + 飞书同步
│   │
│   ├── tools/                        # ===== 工具层（BaseTool 体系） =====
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseTool 抽象基类
│   │   ├── manager.py                # ToolManager 单例 — 工具注册/查找
│   │   ├── script_tool.py            # ScriptTool — 脚本执行器
│   │   ├── spider_tool.py            # SpiderTool — 快递查询工具
│   │   ├── pinduoduo_tool.py         # PinduoduoTool — 拼多多助手
│   │   ├── tu_tool.py                # TuTool — 途强助手
│   │   ├── order_1688_tool.py        # Order1688Tool — 1688订单
│   │   └── feishu/                   # 飞书集成
│   │       ├── __init__.py
│   │       ├── feishu_client.py      # FeishuClient — 飞书 API 封装
│   │       ├── feishu_table_client.py# FeishuTableClient — 多维表格 CRUD
│   │       ├── message_sender.py     # FeishuMessageSender — 消息发送
│   │       ├── test_feishu_table_client.py
│   │       └── webhook/
│   │           ├── __init__.py
│   │           ├── notify.py         # 通用 Webhook 通知
│   │           └── qudao_notify.py   # 渠道分类 Webhook
│   │
│   ├── web/                          # ===== Web 前端层 =====
│   │   ├── __init__.py
│   │   ├── routes.py                 # Web 页面路由（首页/工具页/设置页等）
│   │   └── templates/                # Jinja2 HTML 模板
│   │       ├── base.html             # 基础布局（侧栏 + 内容区）
│   │       ├── index.html            # 首页（仪表盘）
│   │       ├── error.html            # 错误页
│   │       ├── settings.html         # 配置页
│   │       ├── browser_status.html   # 浏览器状态监控
│   │       ├── feishu_test.html      # 飞书消息测试
│   │       ├── websocket.html        # WebSocket 管理
│   │       ├── scheduler.html        # 定时任务列表
│   │       ├── scheduler_add.html    # 新建定时任务
│   │       ├── pinduoduo_erp_order_sync.html  # ERP 订单同步
│   │       └── tools/                # 各工具页面
│   │           ├── pinduoduo.html
│   │           ├── tu.html
│   │           ├── order_1688.html
│   │           ├── spider.html
│   │           └── script_executor.html
│   │
│   ├── tray/                         # ===== 系统托盘 =====
│   │   ├── __init__.py
│   │   └── tray_icon.py              # TrayIcon — 托盘图标管理
│   │
│   ├── scheduler/                    # ===== 定时任务模块 =====
│   │   ├── __init__.py               # 模块导出
│   │   ├── manager.py                # 调度器管理 + 任务 handler 注册
│   │   ├── task_config.py            # 任务配置持久化（JSON）
│   │   └── tasks.json                # 种子任务配置（首次运行复制到运行目录）
│   │
│   ├── utils/                        # ===== 工具函数层 =====
│   │   ├── __init__.py
│   │   ├── browser_path.py           # 浏览器驱动路径查找
│   │   ├── config_manager.py         # 应用配置持久化（app_config.json）
│   │   ├── logger.py                 # 日志系统（按天轮转）
│   │   ├── module_manager.py         # ModuleManager — 模块启用/禁用管理
│   │   ├── path_helper.py            # 安全路径（避免 Program Files 权限问题）
│   │   ├── script_manager.py         # 脚本管理
│   │   ├── single_instance.py        # 单实例锁（防止重复运行）
│   │   ├── startup.py                # Windows 开机自启动（注册表）
│   │   ├── websocket_client.py       # Socket.IO 客户端管理器
│   │   ├── websocket_action_config.py# WebSocket action → 本地 URL 映射
│   │   ├── win32_msvc_runtime.py     # MSVC 运行时 DLL 路径
│   │   └── process_test_data.py      # 测试数据处理
│   │
│   ├── static/                       # 静态资源（CSS/JS/图片）
│   │   └── images/
│   └── testData/                     # 测试数据
│
├── scheduler/                        # 运行时任务配置（由程序自动管理）
│   ├── tasks.json                    # 当前任务列表
│   ├── task_last_success.json        # 任务上次成功时间
│   └── .scheduler_seed_merge_version # 种子合并版本标记
│
├── cache/                            # 运行时缓存
│   ├── pinduoduo_orders_recent.json
│   ├── pinduoduo_request_info.json
│   ├── tu_report_recent_30d.json
│   └── order_1688/
│
├── docs/                             # 文档
│   ├── project.md                    # 本文档
│   ├── PROJECT_DOCUMENTATION.md      # 旧版开发文档
│   ├── log.md                        # 变更日志
│   ├── 开发指南.md
│   ├── 配置说明.md
│   ├── 浏览器超时配置说明.md
│   ├── 浏览器池动态扩展说明.md
│   ├── 浏览器池调用规范.md
│   ├── 浏览器驱动部署说明.md
│   ├── 定时任务对接说明.md
│   ├── 飞书聊天机器人配置说明.md
│   ├── websocket-api.md
│   └── next/
│       └── workflow-engine-plan.md
│
├── requirements.txt                  # Python 依赖
├── main.spec                         # PyInstaller 打包配置
├── build.py / build.bat              # 构建脚本
├── .env                              # 环境变量（飞书凭证等，不入版本控制）
├── module_config.json                # 模块配置
├── app_config.json                   # 应用配置持久化
└── README.md                         # 项目说明
```

---

## 4. 启动流程与生命周期

### 4.1 启动序列图

```
main.py::main()
    │
    ├─ 1. win32_msvc_runtime.add_dll_search_paths_if_needed()  # MSVC DLL 兼容
    ├─ 2. init_logging() → 初始化日志系统（按天轮转 app_*.log / task_*.log）
    ├─ 3. find_chrome_executable() → 查找 Chromium 浏览器路径
    ├─ 4. ensure_single_instance() → Mutex 锁，防止重复运行
    ├─ 5. is_startup_enabled() / add_to_startup() → 检查并设置开机自启动
    │
    ├─ 6. TrayIcon(on_open, on_quit).start() → 启动系统托盘（后台线程）
    │
    ├─ 7. Thread(run_flask_app).start() → Flask 线程（daemon）
    │      │
    │      ├─ 7a. create_app() → 创建 Flask 实例
    │      │       - 确定 template_folder / static_folder（开发/打包模式）
    │      │
    │      ├─ 7b. init_browser_pool() → 创建 BrowserPool
    │      │       - 检查 ModuleManager 是否有模块需要浏览器
    │      │       - BrowserPool(headless, idle_timeout, max_instances)
    │      │       - 内部创建 ThreadPoolExecutor(max_workers=1)
    │      │       - 浏览器在首次 execute() 时才启动（懒加载）
    │      │
    │      ├─ 7c. init_tools(browser_pool) → 初始化工具管理器
    │      │       - 注册 ScriptTool, PinduoduoTool, TuTool, Order1688Tool
    │      │       - 每个工具接收 browser_pool 引用
    │      │
    │      ├─ 7d. setup_app(app, browser_pool, tool_manager)
    │      │       - register_api_routes() → 10 个 Blueprint
    │      │       - register_web_routes() → 页面路由
    │      │       - Swagger(/api/docs)
    │      │
    │      ├─ 7e. start_scheduler() → APScheduler 启动
    │      │       - 从 tasks.json 加载任务配置
    │      │       - 注册 CronTrigger jobs
    │      │       - 启动补跑线程（catch_up_on_start）
    │      │
    │      ├─ 7f. get_websocket_client().start_if_enabled() → Socket.IO 连接
    │      │
    │      └─ 7g. app.run(threaded=False) → 启动 Flask HTTP 服务
    │
    ├─ 8. wait_for_server_ready() → 轮询等待 HTTP 服务可用
    │
    ├─ 9. create_native_window() 或 open_browser()
    │      → pywebview 原生窗口（阻塞主线程）
    │      → 关闭按钮 = 隐藏到托盘（非退出）
    │
    └─ 10. cleanup() → 退出时资源清理
            - WebSocket 断开
            - 托盘停止
            - 工具清理
            - 调度器关闭
            - 浏览器池关闭
```

### 4.2 线程模型

| 线程 | 名称 | 职责 | 生命周期 |
|------|------|------|---------|
| **主线程** | MainThread | pywebview 窗口事件循环 | 应用全生命周期 |
| **Flask 线程** | Thread (daemon) | HTTP 服务 + 初始化 | daemon，主线程退出即终止 |
| **Playwright 线程** | playwright-0 | 所有浏览器操作串行执行 | 首次 execute() 到 close() |
| **托盘线程** | pystray 内部 | 系统托盘图标 + 菜单 | start() 到 stop() |
| **调度器线程** | APScheduler 内部 | 定时任务触发 | start_scheduler() 到 shutdown |
| **WebSocket 线程** | daemon | Socket.IO 连接 + 重连 | connect() 到 disconnect() |
| **补跑线程** | scheduler-catch-up | 启动时漏跑检查 | 一次性，完成即终止 |

### 4.3 关键设计决策

1. **Flask 单线程运行** (`threaded=False`): 避免 Playwright 线程切换问题
2. **BrowserPool 单工作线程**: 所有浏览器操作通过 `execute(fn)` 提交到同一个 `ThreadPoolExecutor(max_workers=1)` 串行执行
3. **持久化 BrowserContext**: 使用 `launch_persistent_context` + 固定 `user_data_dir`，Cookie/localStorage 跨次运行保持
4. **Page 复用**: 长驻同一个 Page，sessionStorage/JS 内存中的登录态在 Page 存活期间保持
5. **窗口关闭 = 隐藏**: 点击关闭按钮只是隐藏窗口到托盘，不退出应用

---

## 5. 核心架构设计

### 5.1 分层架构

```
┌──────────────────────────────────────────────────────────────┐
│  表现层 (Web / 原生窗口 / 托盘)                               │
│  - Jinja2 HTML 模板 + 静态资源                                │
│  - pywebview 原生窗口                                         │
│  - pystray 系统托盘                                           │
└──────────────────────────────────────────────────────────────┘
                          ↕ HTTP / 模板渲染
┌──────────────────────────────────────────────────────────────┐
│  路由层 (Flask Blueprint)                                     │
│  - api/routes/*.py → JSON API（10 个 Blueprint）             │
│  - web/routes.py   → HTML 页面路由                            │
│  - Swagger /api/docs                                          │
└──────────────────────────────────────────────────────────────┘
                          ↕ 调用
┌──────────────────────────────────────────────────────────────┐
│  业务层                                                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                │
│  │ ToolManager│ │ Scheduler  │ │ WebSocket  │                │
│  │ (工具管理) │ │ (定时任务) │ │ (实时通信) │                │
│  └────────────┘ └────────────┘ └────────────┘                │
│  ┌────────────────────────────────────────────┐              │
│  │  Tools (BaseTool 子类)                      │              │
│  │  Pinduoduo / Tu / Order1688 / Script / ...  │              │
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
                          ↕ 调用
┌──────────────────────────────────────────────────────────────┐
│  爬虫/自动化层 (spider/)                                      │
│  ┌────────────────────────────────────────────┐              │
│  │  BrowserPool → Playwright (持久化 context) │              │
│  │  PinduoduoClient / TuClient / ...          │              │
│  │  feishutable.py (飞书多维表格同步)          │              │
│  └────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
                          ↕ 调用
┌──────────────────────────────────────────────────────────────┐
│  基础设施层 (utils/ + tools/feishu/)                          │
│  - path_helper: 安全路径                                      │
│  - logger: 按天轮转日志                                       │
│  - browser_path: 浏览器驱动查找                               │
│  - config_manager: 配置持久化                                 │
│  - module_manager: 模块启用管理                               │
│  - FeishuClient / FeishuTableClient: 飞书 API                │
│  - startup: Windows 注册表自启动                              │
│  - single_instance: 互斥锁                                   │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 BrowserPool 核心流程

```
调用方                  BrowserPool                  Playwright 线程
  │                        │                               │
  │  execute(fn, timeout)  │                               │
  │ ──────────────────────>│                               │
  │                        │   submit(_task)               │
  │                        │ ─────────────────────────────>│
  │                        │                               │ _ensure_browser()
  │                        │                               │  → start playwright
  │                        │                               │  → launch_persistent_context
  │                        │                               │ _ensure_page()
  │                        │                               │  → new_page() 或复用
  │                        │                               │ fn(page)
  │                        │                               │  → 执行业务逻辑
  │                        │       result / exception      │
  │                        │ <─────────────────────────────│
  │       返回结果          │                               │
  │ <──────────────────────│                               │
  │                        │                               │
  │  （若 page 失效）       │                               │
  │                        │   自动 _reset_all() 重建并重试 │
```

### 5.3 工具体系（BaseTool）

```python
BaseTool (ABC)
  ├── name: str              # 唯一标识（如 'pinduoduo'）
  ├── display_name: str      # 显示名（如 '拼多多助手'）
  ├── get_info() → Dict      # 返回工具信息（图标、模板等）
  ├── initialize(**kwargs)   # 初始化（接收 browser_pool）
  ├── cleanup()              # 资源清理
  ├── get_template_name()    # → 'tools/{name}.html'
  └── get_api_prefix()       # → '/api/tools/{name}'

ToolManager (单例)
  ├── register_tool(tool)    # 注册工具
  ├── get_tool(name)         # 按名获取
  ├── get_tools_info()       # 所有工具信息（给前端侧栏）
  ├── register_lazy_tool()   # 延迟加载注册
  └── cleanup_all()          # 退出时清理
```

---

## 6. 模块详细梳理

### 6.1 拼多多助手 (`spider/pinduoduo/`)

**核心类**: `PinduoduoClient(page)`

**功能链路**:

```
Web 页面 / API
    ↓
pinduoduo_routes.py (Blueprint)
    ↓
PinduoduoTool.execute_with_client(callback)
    ↓
BrowserPool.execute(fn)  → 在 Playwright 线程执行
    ↓
PinduoduoClient
    ├── execute_automation()    → 登录检测 + 自动化
    ├── check_login_status()   → 检测登录状态
    ├── get_orders_and_sync()  → 抓取订单 + 飞书同步
    └── get_qr_code()          → 登录二维码
         ↓
    feishutable.sync_orders_to_feishu()  → 飞书多维表格写入
```

**关键 API**:
- `GET /api/pinduoduo/status` — 最后执行状态
- `POST /api/pinduoduo/login` — 启动登录流程
- `GET /api/pinduoduo/check_login_complete` — 检查登录完成
- `POST /api/pinduoduo/logout` — 清除登录状态
- `POST /api/pinduoduo/sync-erp-orders` — ERP 订单同步到飞书

**数据文件**:
- Cookie/状态: `%LOCALAPPDATA%/如意助手/cookies/pinduoduo_status.json`
- 浏览器缓存: `%LOCALAPPDATA%/如意助手/browser_data/`

#### 6.1.1 ERP 订单同步 (`erp_order_sync.py`)

**流程**:
1. Playwright 打开 ERP 全部订单页（`mms.pinduoduo.com/erp/order/all`）
2. 检测登录拦截 → 若被拦截：飞书通知 + 返回二维码
3. 等待 `beast-core` 表头挂载
4. 注入 `pdd-erp-order-all-table.js` 脚本（设置 `python` 运行模式）
5. 脚本在页内滚动采集表格数据
6. 返回 `rows` 数据 → `sync_erp_order_rows_to_feishu()` 写入飞书
7. 按「平台订单号」判断新建或增量更新

#### 6.1.2 库存同步 (`inventory_sync_job.py`)

**流程**（纯飞书 API，无需浏览器）:
1. 读取飞书 ERP 全部店铺表
2. 过滤：付款时间 > 配置日 + 有平台订单号
3. 库存信息表：按订单号，无则新增
4. 扣减日志表：
   - 快递单号非空 → 写出库时间/数量
   - 提醒列命中退货关键词 → 写退货时间/数量
5. 库存关联匹配：用字符多集覆盖+功率+类别+Jaccard 综合打分
6. 分数 ≥ 80 → 写商品名称；否则写未匹配说明

### 6.2 途强助手 (`spider/tu/`)

**核心类**: `TuClient(page)`

**流程**:
1. 打开 `iot.tqiot.com`
2. 检测登录页（账号+密码输入框同时存在）
3. 自动填充账号密码并提交
4. 导航到目标页面（reportDown）
5. 获取最近 30 天记录
6. 缓存数据 + 可选同步到飞书

**关键 API**:
- `GET /api/tu/status` — 执行状态
- `POST /api/tu/execute` — 执行自动化
- `POST /api/tu/logout` — 清除登录

### 6.3 1688 订单提取 (`spider/order_1688/`)

**核心模块**: `order_extract.py`

**流程**:
1. Playwright 打开 1688 待收货订单列表页
2. 注入 JS 脚本 `EXTRACT_JS` 提取订单数据
3. 解析 Shadow DOM 中的订单信息（订单号/商品/价格/物流号等）
4. 与当日缓存合并去重
5. 详情补全：定时任务每小时最多 20 次进入详情页（防封控）
6. 可选同步到飞书多维表格

**关键 API**:
- `GET /api/order_1688/list` — 获取订单列表
- `POST /api/order_1688/extract` — 执行提取
- `POST /api/order_1688/fill_detail` — 补详情
- `POST /api/order_1688/sync_feishu` — 同步到飞书

### 6.4 快递查询 (`spider/logistics_query.py`)

**状态**: 默认禁用（`modules.py` 中 `logistics.enabled = False`）

**流程**:
1. 接收快递单号
2. 识别快递类型（快递100 API 或百度搜索）
3. 选择查询方案：方案1=快递100, 方案2=百度
4. Playwright 自动化查询
5. 解析结果并返回

**关键 API**:
- `GET /query?waybill=xxx` — 单个查询
- `POST /batch` — 批量查询

### 6.5 脚本执行器 (`tools/script_tool.py`)

轻量工具，支持：
- 执行 Python 脚本
- 参数传递
- 结果返回

---

## 7. API 路由总览

### 7.1 Blueprint 一览

| Blueprint | 前缀 | 文件 | 主要端点 |
|-----------|------|------|---------|
| `health_bp` | `/` | health.py | `/health`, `/startup` |
| `script_bp` | `/api` | script_routes.py | `/api/scripts/run` |
| `settings_bp` | `/api` | settings_routes.py | `/api/settings`, `/api/modules` |
| `browser_bp` | `/api` | browser_routes.py | `/api/browser/status` |
| `pinduoduo_bp` | `/api/pinduoduo` | pinduoduo_routes.py | `/api/pinduoduo/*` |
| `tu_bp` | `/api/tu` | tu_routes.py | `/api/tu/*` |
| `feishu_bp` | `/api/feishu` | feishu_routes.py | `/api/feishu/*` |
| `order_1688_bp` | `/api/order_1688` | order_1688_routes.py | `/api/order_1688/*` |
| `websocket_bp` | `/api/ws` | websocket_routes.py | `/api/ws/*` |
| `scheduler_bp` | `/api/scheduler` | scheduler_routes.py | `/api/scheduler/*` |

### 7.2 主要 API 端点

**系统**:
- `GET /health` — 健康检查
- `GET/POST/DELETE /startup` — 开机自启动管理

**拼多多**:
- `GET /api/pinduoduo/status` — 登录状态
- `POST /api/pinduoduo/login` — 启动登录
- `POST /api/pinduoduo/sync-erp-orders` — ERP 订单同步
- `POST /api/pinduoduo/inventory-sync-from-erp-feishu` — 库存同步

**途强**:
- `GET /api/tu/status` — 执行状态
- `POST /api/tu/execute` — 执行自动化

**1688**:
- `POST /api/order_1688/extract` — 订单提取
- `POST /api/order_1688/fill_detail` — 补详情

**定时任务**:
- `GET /api/scheduler/jobs` — 任务列表
- `POST /api/scheduler/jobs` — 新增任务
- `POST /api/scheduler/jobs/<id>/run` — 手动执行
- `POST /api/scheduler/jobs/<id>/pause` — 暂停
- `POST /api/scheduler/jobs/<id>/resume` — 恢复

**WebSocket**:
- `GET /api/ws/status` — 连接状态
- `POST /api/ws/connect` — 连接
- `POST /api/ws/disconnect` — 断开

**Swagger**: `GET /api/docs` — 交互式 API 文档

---

## 8. Web 页面与模板

### 8.1 页面路由

| URL | 模板 | 功能 |
|-----|------|------|
| `/` | index.html | 首页仪表盘（工具列表） |
| `/tools/<name>` | tools/<name>.html | 各工具功能页 |
| `/settings` | settings.html | 全局配置 |
| `/browser-status` | browser_status.html | 浏览器状态监控 |
| `/scheduler` | scheduler.html | 定时任务列表 |
| `/scheduler/add` | scheduler_add.html | 新建定时任务 |
| `/pdd-erp-order-sync` | pinduoduo_erp_order_sync.html | ERP 订单同步 |
| `/websocket` | websocket.html | WebSocket 管理 |
| `/feishu-test` | feishu_test.html | 飞书消息测试 |

### 8.2 模板体系

- **base.html**: 基础布局，包含左侧导航栏（工具列表由 `ToolManager.get_tools_info()` 动态生成）
- **tools/*.html**: 各工具的功能页面，继承 base.html
- 所有模板使用 Jinja2 渲染，通过 `config=Config` 传入配置

---

## 9. 定时任务系统

### 9.1 架构

```
scheduler/
├── __init__.py          # 模块导出
├── manager.py           # 核心：调度器 + 任务 handler + 状态追踪
├── task_config.py       # 任务配置持久化 (tasks.json)
└── tasks.json           # 种子配置（src 下，首次运行复制到运行目录）
```

### 9.2 任务类型 (handler)

| 类型 Key | 名称 | Handler | 说明 |
|----------|------|---------|------|
| `http_request` | HTTP 定时请求 | `_run_http_request` | GET/POST/PUT/DELETE |
| `python_script` | Python 脚本 | `_run_python_script` | 内联代码或文件路径 |
| `order_1688_fill_detail` | 1688 订单补详情 | `_run_order_1688_fill_detail` | 调用本机 API |
| `pdd_erp_order_sync` | 拼多多 ERP 订单同步 | `_run_pdd_erp_order_sync` | POST 本机 API → 飞书 |
| `pdd_inventory_sync` | 拼多多库存同步 | `_run_pdd_inventory_sync` | 进程内调用（不走 HTTP） |

### 9.3 种子合并机制

- `src/scheduler/tasks.json` 为种子文件
- 首次运行：复制到 `scheduler/tasks.json`（运行目录）
- 后续升级：通过 `_SCHEDULER_SEED_MERGE_VERSION` 版本号控制
  - 版本号递增时，自动追加种子中新增的任务 id（不覆盖已有配置）
  - 同时补全已有任务缺少的字段（如 `catch_up_on_start`）

### 9.4 启动补跑

- `catch_up_on_start = true` 的任务
- 启动时检查上一个 cron 触发点
- 若上次成功时间 < cron 触发点 且 距今 < 24h → 自动补跑
- 在独立后台线程中执行，不阻塞启动

### 9.5 任务状态

- **内存中追踪**: `_task_status` Dict，记录 running/last_run/last_success/last_message
- **持久化成功时间**: `task_last_success.json`
- **执行日志缓冲**: 每个任务最近 200 条日志行（内存，可通过 API 查看）

---

## 10. 飞书集成

### 10.1 组件架构

```
tools/feishu/
├── feishu_client.py          # FeishuClient — 底层 API 封装
│                               - tenant_access_token 获取与缓存
│                               - send_message() 发送消息
│                               - is_configured() 配置检查
├── feishu_table_client.py    # FeishuTableClient — 多维表格 CRUD
│                               - list_records() 列出记录
│                               - create_records() 批量新建
│                               - update_record() 单条更新
│                               - batch_update_records() 批量更新
├── message_sender.py         # FeishuMessageSender — 高层消息接口
│                               - send_pinduoduo_login_alert()
│                               - send_custom_message()
│                               - send_card_message()
└── webhook/
    ├── notify.py              # 通用 Webhook 通知
    └── qudao_notify.py        # 渠道分类 Webhook
```

### 10.2 配置项

| 环境变量 | 说明 |
|---------|------|
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_USER_ID` | 默认消息接收人（open_id） |
| `FEISHU_SYNC_WEBHOOK_URL` | 通用 Webhook URL |
| `PINDUODUO_FEISHU_APP_TOKEN` | 飞书多维表格应用 Token |
| `PINDUODUO_FEISHU_TABLE_ID` | 订单表 table_id |
| `PINDUODUO_ERP_FEISHU_TABLE_ID` | ERP 订单表 table_id |
| `PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID` | 库存信息表 table_id |
| `PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID` | 扣减日志表 table_id |

### 10.3 飞书同步场景

1. **拼多多订单 → 飞书多维表格**: `feishutable.sync_orders_to_feishu()`
2. **ERP 全部订单 → 飞书多维表格**: `feishutable.sync_erp_order_rows_to_feishu()`
3. **库存同步**: `inventory_sync_job.run_inventory_sync_job()`
4. **1688 订单 → 飞书**: `order_extract` 模块
5. **途强数据 → 飞书**: `tu/feishutable.sync_tu_data_to_feishu()`
6. **登录失效通知**: `message_sender.send_pinduoduo_login_alert()`
7. **定时任务结果通知**: `_notify_pdd_erp_sync_result()`

---

## 11. WebSocket 客户端

### 11.1 架构

- **协议**: Socket.IO（兼容 websocket + polling 传输）
- **服务端**: 由 `WS_CLIENT_HOST:WS_CLIENT_PORT` + `WS_CLIENT_PATH` 配置
- **默认服务端**: `https://nestapi.xfysj.top:8080/xcx/ws`

### 11.2 事件监听

| 事件 | 处理 |
|------|------|
| `forward` | 记录 payload，供页面查看 |
| `action` | 查找 `ws_actions.json` 映射，POST 到本地 URL |
| `connect` / `disconnect` | 状态更新 |
| `connect_error` | 错误记录 + 自动重连 |

### 11.3 Action 映射

- 配置文件: `websocket_action_config.py`
- 收到 action 事件时，根据 `action` 字段查找对应的本地 URL
- 自动 POST 请求到该 URL（实现远程触发本地操作）

---

## 12. 配置体系

### 12.1 配置层级（优先级从高到低）

1. **环境变量** (`.env` 文件 或系统环境变量)
2. **持久化配置** (`app_config.json` — 通过设置页面保存)
3. **模块配置** (`module_config.json` — 模块启用/禁用)
4. **代码默认值** (`config.py::Config` 类属性)
5. **模块默认配置** (`config/modules.py::DEFAULT_MODULE_CONFIG`)

### 12.2 Config 类关键配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HOST` | 127.0.0.1 | HTTP 绑定地址 |
| `PORT` | 8887 | HTTP 端口（生产） |
| `DEV_PORT` | 8886 | HTTP 端口（开发） |
| `HEADLESS` | False | 浏览器无头模式 |
| `USE_NATIVE_WINDOW` | True | 使用原生窗口 |
| `TRAY_ENABLED` | True | 系统托盘 |
| `SCHEDULER_ENABLED` | True | 定时任务 |
| `WS_CLIENT_ENABLED` | True | WebSocket |
| `MAX_RETRY` | 3 | 查询最大重试 |
| `BROWSER_LAZY_INIT` | True | 浏览器延迟初始化 |
| `BROWSER_IDLE_TIMEOUT` | 300 | 浏览器空闲超时（秒） |

### 12.3 模块配置 (`module_config.json`)

```json
{
  "logistics": { "enabled": false, "requires_browser": true },
  "script_executor": { "enabled": true, "init_on_startup": true },
  "resource_monitor": { "enabled": true }
}
```

拼多多/途强/1688 工具**不受** `module_config.json` 控制（直接硬编码注册），只有 logistics 和 script_executor 通过模块管理器控制。

---

## 13. 数据存储与路径

### 13.1 安全路径策略

使用 `utils/path_helper.py` 处理所有数据文件路径：

```
开发环境 + 有写入权限 → 项目根目录
                                    > get_safe_data_path(relative)
打包后 / 无权限 → %LOCALAPPDATA%/如意助手/
```

### 13.2 数据文件分布

| 文件 | 路径 | 说明 |
|------|------|------|
| 浏览器缓存 | `%LOCALAPPDATA%/如意助手/browser_data/` | 持久化 context（Cookie/localStorage） |
| 拼多多状态 | `cookies/pinduoduo_status.json` | 登录状态记录 |
| 途强状态 | `tu/tu_status.json` | 登录状态记录 |
| 任务配置 | `scheduler/tasks.json` | 定时任务列表 |
| 任务成功记录 | `scheduler/task_last_success.json` | 上次成功时间 |
| 应用配置 | `app_config.json` | 设置页面保存的配置 |
| 模块配置 | `module_config.json` | 模块启用/禁用 |
| 订单缓存 | `cache/pinduoduo_orders_recent.json` | 拼多多订单缓存 |
| 1688 订单缓存 | `cache/order_1688/orders_*.json` | 按日期缓存 |
| 途强缓存 | `cache/tu_report_recent_30d.json` | 途强 30 天记录 |
| 日志文件 | `logs/app_YYYY-MM-DD.log` | 应用日志 |
| 任务日志 | `logs/task_YYYY-MM-DD.log` | 定时任务日志 |

---

## 14. 打包与部署

### 14.1 打包配置 (`main.spec`)

- 模式: `onedir`（输出到 `dist/main/`）
- 包含: web 模板、静态资源、浏览器驱动
- 输出: `dist/main/main.exe` + `_internal/` 资源目录

### 14.2 部署清单

```
dist/main/
├── main.exe                    # 可执行文件
├── _internal/                  # Python 运行时 + 依赖
│   ├── web/templates/          # HTML 模板
│   ├── static/                 # 静态资源
│   └── ...
└── playwright_drivers/         # Chromium 浏览器驱动
    └── chromium-XXXX/
        └── chrome-win/
            └── chrome.exe
```

### 14.3 首次运行行为

1. 自动添加到 Windows 开机启动项（注册表）
2. 初始化浏览器池（首次 execute 时启动浏览器）
3. 从种子 `tasks.json` 初始化定时任务配置
4. 启动 HTTP 服务 → 打开原生窗口

---

## 15. 已知问题与优化方向

### 15.1 架构层面

| 问题 | 影响 | 优化建议 |
|------|------|---------|
| **Flask 单线程** (`threaded=False`) | 同一时刻只能处理一个 HTTP 请求，浏览器操作时接口会阻塞 | 考虑异步化（FastAPI/ASGI）或将耗时操作改为后台任务 |
| **BrowserPool 单 Page** | 所有工具共享一个 Page，一个工具操作时其他工具被阻塞 | 可按工具分配独立 Page，或使用 Page 池 |
| **配置分散** | Config 类属性 + .env + app_config.json + module_config.json 四处配置 | 统一配置源，减少加载链路 |
| **config/__init__.py 动态导入** | 使用 `importlib.util` 动态加载父级 config.py，增加复杂度 | 重构包结构，消除循环导入 |
| **工具注册硬编码** | PinduoduoTool/TuTool/Order1688Tool 在 app.py 中硬编码注册 | 统一走 ModuleManager 配置驱动 |
| **日志混用 print + logger** | 部分模块使用 print 而非 logger | 统一使用 logger |

### 15.2 代码层面

| 问题 | 位置 | 优化建议 |
|------|------|---------|
| **main.py 过长** (~717行) | src/main.py | 窗口管理、Flask 启动、托盘回调拆分到独立模块 |
| **app.py init_tools 硬编码** | src/app.py | 工具注册改为配置驱动或自动发现 |
| **browser_path 多处调用** | main.py + app.py 都调用 find_chrome_executable | 只需初始化一次 |
| **异常处理宽泛** | 多处 `except Exception as e` | 细化异常类型 |
| **inventory_sync_job 临时覆盖** | `INVENTORY_SYNC_PAY_AFTER_OVERRIDE` 硬编码日期 | 应删除或改为仅环境变量控制 |

### 15.3 性能层面

| 问题 | 影响 | 优化建议 |
|------|------|---------|
| **浏览器常驻内存** | ~200-300MB | 已有空闲超时设计但未实现关闭 |
| **飞书 API 无批量优化** | 大量记录逐条更新 | 使用批量 API + 增量标记 |
| **模板每次请求都获取 tools_info** | 轻微性能浪费 | 缓存工具信息 |
| **WebSocket 重连无退避** | 固定 5 秒重连间隔 | 指数退避 |

### 15.4 安全层面

| 问题 | 影响 | 优化建议 |
|------|------|---------|
| `SECRET_KEY` 硬编码 | Flask session 安全 | 改为环境变量 |
| `TU_PASSWORD` 明文配置 | 密码泄露风险 | 加密存储或使用密钥管理 |
| `HEADLESS = False` 生产默认 | 浏览器窗口可见 | 生产环境应为 True |
| API 无认证 | 本地回环接口 | 如需外网访问需增加认证 |

### 15.5 旧代码清理

| 文件 | 说明 |
|------|------|
| `src/JNSpider.py` | 旧版快递查询服务入口，已整合到 main.py 体系 |
| `src/JNTools.py` | 旧版工具入口，已废弃 |
| `docs/PROJECT_DOCUMENTATION.md` | 旧版文档，部分内容已过时 |
| `test_flask.py` | 根目录测试文件 |
| `order_list.json` | 根目录数据文件 |

---

## 附录 A: 数据流总图

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  拼多多 MMS  │     │  1688 平台   │     │  途强 IoT    │
│  (mms.pdd)   │     │  (air.1688)  │     │ (iot.tqiot)  │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ Playwright         │ Playwright         │ Playwright
       ↓                    ↓                    ↓
┌──────────────────────────────────────────────────────────┐
│              BrowserPool (持久化 Context)                  │
│              → 单 Page 复用, 登录态保持                    │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────────┐
│              Flask HTTP API 层                            │
│              → 10 个 Blueprint                           │
└────────────────────────┬─────────────────────────────────┘
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
    ┌─────────────┐ ┌──────────┐ ┌───────────┐
    │ 飞书多维表格 │ │ 飞书消息 │ │  Webhook  │
    │ (API CRUD)  │ │ (私聊)   │ │ (机器人)  │
    └─────────────┘ └──────────┘ └───────────┘
```

## 附录 B: 环境变量完整列表

| 变量名 | 必填 | 默认值 | 说明 |
|--------|:----:|--------|------|
| `APP_ENV` | 否 | production | 运行环境 |
| `PORT` | 否 | 8887 | HTTP 端口 |
| `DEV_PORT` | 否 | 8886 | 开发端口 |
| `FEISHU_APP_ID` | 否 | - | 飞书 App ID |
| `FEISHU_APP_SECRET` | 否 | - | 飞书 App Secret |
| `FEISHU_USER_ID` | 否 | - | 飞书消息接收人 |
| `FEISHU_SYNC_WEBHOOK_URL` | 否 | - | 飞书 Webhook |
| `PINDUODUO_FEISHU_APP_TOKEN` | 否 | ORSHbp... | 飞书多维表格 Token |
| `PINDUODUO_FEISHU_TABLE_ID` | 否 | tblyxG... | 订单表 ID |
| `PINDUODUO_ERP_FEISHU_TABLE_ID` | 否 | tblyAX... | ERP 表 ID |
| `PINDUODUO_FEISHU_INVENTORY_INFO_TABLE_ID` | 否 | tbljLw... | 库存信息表 ID |
| `PINDUODUO_FEISHU_INVENTORY_LOG_TABLE_ID` | 否 | tblXXi... | 扣减日志表 ID |
| `PINDUODUO_INVENTORY_PAY_AFTER_DATE` | 否 | 2026-04-07 | 付款截止日 |
| `PINDUODUO_INVENTORY_PRODUCT_NAME_FIELD` | 否 | 商品名称 | 库存表商品名列 |
| `PINDUODUO_INVENTORY_STOCK_LINK_MATCH_MIN_SCORE` | 否 | 80 | 匹配分阈值 |
| `TU_ACCOUNT` | 否 | 18038... | 途强账号 |
| `TU_PASSWORD` | 否 | yao625... | 途强密码 |
| `TU_DEVICE_ID` | 否 | 14165... | 途强设备 ID |
| `WS_CLIENT_HOST` | 否 | nestapi... | WebSocket 服务端 |
| `WS_CLIENT_PORT` | 否 | 8080 | WebSocket 端口 |
| `WS_CLIENT_PATH` | 否 | /xcx/ws | Socket.IO path |
| `AI_BASE_URL` | 否 | - | AI API 地址 |
| `AI_API_KEY` | 否 | - | AI API 密钥 |
| `AI_STOCK_LINK_MODEL` | 否 | qwen-flash... | AI 匹配模型 |

---

**文档结束** — 本文档提供了项目的完整架构梳理，可作为后续优化工作的基础参考。
