# 如意助手

一个基于Python开发的Windows桌面私人助手应用，提供脚本执行、工具管理等多种实用功能，支持模块化配置，资源占用低。

## 功能特性

- 🖥️ **现代化Web界面** - 基于Flask的响应式Web界面，美观易用
- 🐍 **Python脚本执行** - 支持执行Python脚本，支持参数传递和结果返回
- 🛒 **拼多多助手** - 拼多多商家后台自动化工具，支持登录管理和飞书通知
- 📡 **途强助手** - 途强智能设备管理平台（iot.tqiot.com）自动化，支持自动登录与最近 30 天记录获取
- ⚙️ **模块化配置** - 支持通过配置控制功能模块的启用/禁用和启动时机
- 🔧 **可扩展架构** - 工具管理器设计，方便添加新工具
- 📊 **资源监控** - 实时监控内存和CPU使用情况
- 🎯 **系统托盘** - 支持系统托盘图标，最小化到后台运行
- 🚀 **开机自启** - 支持开机自动启动
- 📱 **API接口** - 提供完整的RESTful API接口
- 🔌 **Socket.IO 客户端** - 对接 `docs/websocket-api.md`，连接 path `/ws`、监听事件 `forward`，默认测试环境 `http://localhost:3000`，Flask 启动时自动连接，支持管理页连接/断开与配置保存
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

**API接口**：
- `GET /api/pinduoduo/status` - 获取最后执行状态
- `POST /api/pinduoduo/login` - 启动登录流程
- `GET /api/pinduoduo/check_login_complete` - 检查登录完成
- `POST /api/pinduoduo/logout` - 清除登录状态
- `POST /api/pinduoduo/execute` - 执行自动化操作（TODO）

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
user_dir = get_user_data_dir('JNTools')
file_path = user_dir / 'data' / 'my_data.json'
```

#### 路径选择逻辑

`get_safe_data_path()` 会自动选择安全的路径：

1. **开发环境且有权限**：使用项目根目录（便于开发调试）
2. **生产环境或无权限**：使用用户数据目录
   - Windows: `%LOCALAPPDATA%\JNTools\`（如 `C:\Users\用户名\AppData\Local\JNTools\`）
   - Linux: `~/.local/share/JNTools/`
   - Mac: `~/.local/share/JNTools/`

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
