# 蕉内工具箱

一个基于Python开发的Windows桌面应用程序，提供快递物流信息查询等多种实用工具。

## 功能特性

- 🖥️ **现代化Web界面** - 基于Flask的响应式Web界面，美观易用
- 📦 **快递查询工具** - 支持单个和批量快递单号查询
- 🔧 **可扩展架构** - 工具管理器设计，方便添加新工具
- 🎯 **系统托盘** - 支持系统托盘图标，最小化到后台运行
- 🚀 **开机自启** - 支持开机自动启动
- 📱 **API接口** - 提供完整的RESTful API接口

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

### 运行应用

```bash
python src/main.py
```

应用启动后：
- 会在系统托盘显示图标
- 自动打开浏览器访问 `http://127.0.0.1:8099`
- 可以通过托盘图标控制应用

## 使用说明

### Web界面

1. 启动应用后，浏览器会自动打开Web界面
2. 左侧导航栏显示所有可用工具
3. 点击工具名称进入相应工具页面
4. 在工具页面使用相应功能

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

4. **添加API路由**（如需要），在 `api/routes.py` 中

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
