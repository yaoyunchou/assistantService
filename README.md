# 如意助手

一个基于Python开发的Windows桌面私人助手应用，提供脚本执行、工具管理等多种实用功能，支持模块化配置，资源占用低。

## 功能特性

- 🖥️ **现代化Web界面** - 基于Flask的响应式Web界面，美观易用
- 🐍 **Python脚本执行** - 支持执行Python脚本，支持参数传递和结果返回
- 🛒 **拼多多助手** - 拼多多商家后台自动化工具，支持登录管理和飞书通知
- 📋 **订单同步（ERP）** - 官方 ERP 全部订单表抓取，按「平台订单号」同步到指定飞书多维表格（独立页面 `/pdd-erp-order-sync`）
- ✅ **ERP 待审核 / 入库 / 打印** - `/tools/pinduoduo` 加载待审核列表并提交审核（SQLite + 可选飞书审核表）；独立页 `/pdd-erp-delivering-print` 一键「打印并发货」待发货列表
- 📡 **途强助手** - 途强智能设备管理平台（iot.tqiot.com）自动化，支持自动登录与最近 30 天记录获取
- 📦 **1688 订单提取** - 从 1688 待收货订单列表提取订单与收货信息，支持同步到飞书多维表格（Web 页与命令行脚本）
- ⚙️ **模块化配置** - 支持通过配置控制功能模块的启用/禁用和启动时机
- 🔧 **可扩展架构** - 工具管理器设计，方便添加新工具
- 📊 **资源监控** - 实时监控内存和CPU使用情况
- 🎯 **系统托盘** - 支持系统托盘图标，最小化到后台运行
- 🚀 **开机自启** - 支持开机自动启动
- 📱 **API接口** - 提供完整的RESTful API接口
- 🔌 **Socket.IO 客户端** - 对接 `docs/websocket-api.md`，连接 path `/ws`、监听事件 `forward`，默认测试环境 `http://localhost:3000`，Flask 启动时自动连接，支持管理页连接/断开与配置保存
- ⏰ **定时任务** - APScheduler，支持「拼多多 ERP 订单同步」「拼多多库存（飞书 ERP→库存/日志）」等类型；默认种子含每日 12:00 / 18:00 ERP 同步，执行后飞书私聊结果摘要
- 💾 **低资源占用** - 优化资源使用，空闲时内存占用<200MB

## 技术栈

- **后端**: Python 3.8+, Flask
- **前端**: HTML + CSS + JavaScript
- **浏览器自动化**: Playwright
- **系统托盘**: pystray
- **打包工具**: PyInstaller

## 项目结构

```
kuaidi/
├── src/
│   ├── main.py              # 主程序入口
│   ├── app.py               # Flask应用整合
│   ├── config.py            # 配置文件
│   ├── api/                 # API路由
│   ├── web/                 # Web界面
│   │   ├── routes.py        # Web路由
│   │   └── templates/       # HTML模板
│   ├── tools/               # 工具模块
│   │   ├── base.py          # 工具基类
│   │   ├── manager.py       # 工具管理器
│   │   └── spider_tool.py   # 爬虫工具
│   ├── tray/                # 系统托盘
│   ├── spider/              # 爬虫模块
│   └── utils/               # 工具函数
├── requirements.txt         # 依赖列表
└── README.md                # 项目说明
```

## 安装与运行

### 环境要求

- Windows 10/11 (64位)
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

5. **安装Playwright浏览器驱动**
```bash
playwright install chromium
```

6. **配置环境变量（可选，用于拼多多助手）**

如果需要使用拼多多助手的飞书通知功能，需要配置环境变量：

```bash
# 复制环境变量模板
copy .env.example .env

# 编辑 .env 文件，填入飞书应用配置
# FEISHU_APP_ID=your_app_id
# FEISHU_APP_SECRET=your_app_secret
# FEISHU_USER_ID=your_user_id
```

飞书应用配置获取方式：
- 访问 https://open.feishu.cn/app 创建应用
- 获取 App ID 和 App Secret
- 获取接收消息的用户ID（用于私聊消息的默认接收人）

同一套配置支持**文本消息**和**卡片消息**（`message_sender.send_card_message`），无需额外配置。

7. **配置模块（可选）**

如果需要自定义启用的模块，可以配置模块：

```bash
# 复制模块配置模板
copy module_config.json.example module_config.json

# 编辑 module_config.json 文件，启用/禁用需要的模块
```

默认情况下，只启用了脚本执行和拼多多助手，快递查询模块已禁用。

### 运行应用

```bash
python src/main.py
```

应用启动后：
- 会在系统托盘显示图标
- 自动打开窗口访问 `http://127.0.0.1:8889`
- 可以通过托盘图标控制应用

## 使用说明

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
