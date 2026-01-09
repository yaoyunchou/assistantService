# JNSpider 项目开发文档

## 文档版本
- **文档版本**: 1.0.0
- **最后更新**: 2026-01-06
- **适用项目版本**: 1.0.15

---

## 目录

1. [项目概述](#1-项目概述)
2. [功能详细说明](#2-功能详细说明)
3. [技术架构](#3-技术架构)
4. [项目结构详解](#4-项目结构详解)
5. [开发环境配置](#5-开发环境配置)
6. [编译打包流程](#6-编译打包流程)
7. [部署说明](#7-部署说明)
8. [API接口文档](#8-api接口文档)
9. [开发规范](#9-开发规范)
10. [测试指南](#10-测试指南)
11. [常见问题与解决方案](#11-常见问题与解决方案)
12. [版本历史](#12-版本历史)

---

## 1. 项目概述

### 1.1 项目简介

本项目是一个基于 Python 开发的 Windows 桌面应用程序，提供快递物流信息查询 HTTP 服务：

**JNSpider** - 快递物流信息查询 HTTP 服务
- 基于 Flask 的 HTTP API 服务
- 提供快递单号查询接口（单个和批量）
- 集成 Playwright 浏览器自动化爬虫
- 支持开机自启动

### 1.2 技术栈

- **开发语言**: Python 3.x
- **Web框架**: Flask 2.3.0+
- **浏览器自动化**: Playwright 1.40.0+
- **打包工具**: PyInstaller 6.0.0+
- **HTTP请求**: requests 2.31.0+

### 1.3 系统要求

- **操作系统**: Windows 10/11 (64位)
- **Python版本**: 3.8+
- **内存**: 建议 4GB 以上（JNSpider 需要运行浏览器）
- **磁盘空间**: 至少 500MB（包含浏览器驱动）
- **网络**: 需要网络连接（用于查询快递信息）

---

## 2. 功能详细说明

### 2.1 JNSpider 功能

#### 2.1.1 HTTP API 服务

**服务地址**: `http://127.0.0.1:8099`

**服务特性**:
- 基于 Flask 框架
- 单线程处理（避免 Playwright 线程切换问题）
- 支持健康检查、单个查询、批量查询、自启动管理

#### 2.1.2 快递单号查询

**查询流程**:
1. 接收查询请求（单个或批量）
2. 识别快递类型（通过快递100 API 或百度搜索）
3. 选择最佳查询方案
4. 使用 Playwright 浏览器自动化查询
5. 解析查询结果并返回

**支持的快递类型**:
- 京东快递 (JD)
- 顺丰快递 (SF)
- 其他快递（通过百度搜索查询）

**查询方案**:
- **方案1**: 快递100 API（适用于京东等）
- **方案2**: 百度搜索（适用于其他快递）

#### 2.1.3 浏览器池管理

**功能说明**:
- 维护 2 个专用浏览器页面：
  - JD 页面：用于快递100查询
  - 百度页面：用于百度搜索查询
- 浏览器实例复用，提高查询效率
- 支持无头模式（headless）运行

**浏览器配置**:
- 使用 Chromium 浏览器
- 禁用自动化特征检测
- 禁用 CORS 检查
- 禁用通知和弹窗

#### 2.1.4 开机自启动

**功能说明**:
- 程序首次运行自动添加到 Windows 开机启动项
- 支持通过 API 接口管理自启动状态
- 使用 Windows 注册表实现

**注册表位置**:
```
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
键名: JNSpider
值: "C:\Program Files\JNSpider\JNSpider.exe"
```

#### 2.1.5 错误处理和重试机制

**重试策略**:
- 默认最大重试次数：3 次
- 每次重试前随机延迟（0.3-0.6 秒）
- 重试失败后返回错误信息

**错误处理**:
- 参数验证
- 浏览器池状态检查
- 异常捕获和错误信息返回

---

## 3. 技术架构

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     用户层                               │
│  (HTTP API 调用)                                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                   应用层                                  │
│  ┌──────────────┐                                       │
│  │   JNSpider   │                                       │
│  │  (HTTP服务)  │                                       │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                   业务逻辑层                               │
│  ┌──────────────┐                                       │
│  │  查询管理    │                                       │
│  │  浏览器池    │                                       │
│  │  物流查询    │                                       │
│  └──────────────┘                                       │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                   工具层                                   │
│  ┌──────────────┐          ┌──────────────┐             │
│  │  浏览器路径  │          │  自启动管理  │             │
│  │  查找工具    │          │  工具        │             │
│  └──────────────┘          └──────────────┘             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                   系统层                                   │
│  (Windows API / Playwright / Flask)                      │
└─────────────────────────────────────────────────────────┘
```

### 3.2 JNSpider 架构

```
HTTP请求
    ↓
Flask App (JNSpider.py)
    ↓
Routes (api/routes.py)
    ↓
Query Manager (spider/query_manager.py)
    ↓
Browser Pool (浏览器池管理)
    ↓
Logistics Query (spider/logistics_query.py)
    ↓
Playwright Browser (浏览器自动化)
```

### 3.3 模块依赖关系

```
JNSpider.py
    ├── Flask (app)
    ├── BrowserPool (spider/query_manager.py)
    ├── Config (config.py)
    ├── Routes (api/routes.py)
    ├── Browser Path (utils/browser_path.py)
    └── Startup (utils/startup.py)

api/routes.py
    ├── Query Manager (spider/query_manager.py)
    ├── Config (config.py)
    └── Startup (utils/startup.py)

spider/query_manager.py
    ├── Playwright
    ├── Logistics Query (spider/logistics_query.py)
    └── Config (config.py)

spider/logistics_query.py
    ├── Playwright
    └── Requests
```

---

## 4. 项目结构详解

### 4.1 目录结构

```
kaidi/
├── src/                          # 源代码目录
│   ├── __init__.py
│   ├── JNSpider.py               # JNSpider HTTP 服务主程序
│   ├── config.py                 # 应用配置文件
│   ├── api/                      # API 模块
│   │   ├── __init__.py
│   │   └── routes.py             # Flask 路由处理
│   ├── spider/                    # 爬虫模块
│   │   ├── __init__.py
│   │   ├── logistics_query.py    # 物流查询逻辑
│   │   ├── query_manager.py      # 查询管理器（浏览器池）
│   │   └── waybill_extractor.py  # 运单号提取
│   └── utils/                     # 工具模块
│       ├── __init__.py
│       ├── browser_path.py       # 浏览器路径查找
│       └── startup.py             # 开机自启动管理
├── venv/                         # Python 虚拟环境（不纳入版本控制）
├── dist/                         # PyInstaller 编译输出目录
│   ├── JNSpider.exe              # JNSpider 可执行文件
│   └── playwright_drivers/       # Playwright 浏览器驱动
│       └── chromium-XXXX/
│           └── chrome-win/
│               └── chrome.exe
├── build/                        # PyInstaller 临时文件目录
├── JNSpider.spec                 # JNSpider PyInstaller 配置文件
├── requirements.txt              # Python 依赖列表
├── get_playwright_path.py        # 辅助脚本（获取 Playwright 路径）
├── install_playwright_chromium.bat # 安装浏览器驱动脚本
├── readme.md                     # 项目说明文档
├── log.md                        # 变更日志
└── PROJECT_DOCUMENTATION.md      # 项目开发文档（本文档）
```

### 4.2 核心文件说明

**src/JNSpider.py**
- **功能**: JNSpider HTTP 服务主入口
- **主要功能**:
  - 初始化 Flask 应用
  - 管理浏览器池生命周期
  - 处理信号和优雅关闭
  - 自动添加开机自启动
- **依赖**: Flask, Playwright, BrowserPool

**src/api/routes.py**
- **功能**: Flask 路由处理
- **主要路由**:
  - `GET /health`: 健康检查
  - `GET /query?waybill=xxx`: 单个查询
  - `POST /batch`: 批量查询
  - `GET/POST/DELETE /startup`: 自启动管理

**src/spider/query_manager.py**
- **功能**: 查询管理和浏览器池
- **主要类**:
  - `BrowserPool`: 浏览器实例池管理
- **主要函数**:
  - `query_with_retry()`: 带重试的查询
  - `batch_query_waybill_numbers()`: 批量查询

**src/spider/logistics_query.py**
- **功能**: 物流信息查询逻辑
- **主要函数**:
  - `get_express_type()`: 获取快递类型
  - `get_logistics_info()`: 获取物流信息
  - `query_from_kuaidi100()`: 从快递100查询
  - `query_from_baidu()`: 从百度搜索查询

**src/utils/browser_path.py**
- **功能**: 浏览器路径查找
- **主要函数**:
  - `find_chrome_executable()`: 查找 chrome.exe 路径
- **查找顺序**:
  1. exe 同目录的 `playwright_drivers` 目录
  2. 系统安装的 Playwright 浏览器

**src/utils/startup.py**
- **功能**: 开机自启动管理
- **主要函数**:
  - `is_startup_enabled()`: 检查自启动状态
  - `add_to_startup()`: 添加自启动
  - `remove_from_startup()`: 移除自启动
  - `get_exe_path()`: 获取 exe 路径

**src/config.py**
- **功能**: 应用配置
- **配置项**:
  - `HOST`: HTTP 服务地址（默认 127.0.0.1）
  - `PORT`: HTTP 服务端口（默认 8099）
  - `HEADLESS`: 浏览器无头模式（默认 True）
  - `MAX_RETRY`: 最大重试次数（默认 3）

**JNSpider.spec**
- **功能**: PyInstaller 打包配置
- **特殊处理**:
  - 自动复制 Playwright 浏览器驱动到 `dist/playwright_drivers/`
  - 单文件打包，控制台模式
- **输出**: `dist/JNSpider.exe` 和 `dist/playwright_drivers/`

---

## 5. 开发环境配置

### 5.1 环境要求

- **操作系统**: Windows 10/11 (64位)
- **Python**: 3.8 或更高版本
- **IDE**: VS Code / PyCharm（推荐）
- **版本控制**: Git（可选）

### 5.2 环境搭建步骤

#### 步骤 1: 安装 Python

1. 从 [Python 官网](https://www.python.org/downloads/) 下载 Python 3.8+
2. 安装时勾选 "Add Python to PATH"
3. 验证安装：
```bash
python --version
```

#### 步骤 2: 创建虚拟环境

在项目根目录执行：
```bash
python -m venv venv
```

#### 步骤 3: 激活虚拟环境

**Windows CMD**:
```bash
venv\Scripts\activate.bat
```

**Windows PowerShell**:
```bash
venv\Scripts\Activate.ps1
```

如果 PowerShell 执行策略限制，运行：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### 步骤 4: 安装依赖

**方法一：使用 requirements.txt（推荐）**
```bash
pip install -r requirements.txt
```

**方法二：手动安装**
```bash
pip install requests>=2.31.0
pip install pyinstaller>=6.0.0
pip install flask>=2.3.0
pip install playwright>=1.40.0
```

#### 步骤 5: 安装 Playwright 浏览器驱动

**重要**: 这是 JNSpider 运行的必要条件！

```bash
# 方法1：使用虚拟环境中的Python（推荐）
venv\Scripts\python.exe -m playwright install chromium

# 方法2：激活虚拟环境后运行
venv\Scripts\activate.bat
playwright install chromium
```

**注意**: 
- 首次安装需要下载约 170MB 的浏览器文件
- 如果网络不稳定，可以使用国内镜像：
```bash
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright
venv\Scripts\python.exe -m playwright install chromium
```

### 5.3 IDE 配置

#### VS Code 配置

创建 `.vscode/launch.json`:
```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "调试 JNSpider",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/src/JNSpider.py",
            "console": "integratedTerminal",
            "cwd": "${workspaceFolder}",
            "env": {
                "PYTHONPATH": "${workspaceFolder}"
            }
        },
    ]
}
```

#### PyCharm 配置

1. 打开项目
2. 设置 Python 解释器为虚拟环境中的 Python
3. 创建运行配置：
   - 脚本路径: `src/JNSpider.py`
   - Python 解释器: 虚拟环境中的 Python

### 5.4 验证环境

运行以下命令验证环境配置：

```bash
# 检查 Python 版本
python --version

# 检查依赖安装
pip list

# 测试 JNSpider（需要先激活虚拟环境）
python src/JNSpider.py
```

---

## 6. 编译打包流程

### 6.1 编译前准备

#### 6.1.1 确保依赖已安装

```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 检查依赖
pip list | findstr "pyinstaller flask playwright requests"
```

#### 6.1.2 安装 Playwright 浏览器驱动（JNSpider 必需）

```bash
# 必须安装，否则 JNSpider 无法运行
venv\Scripts\python.exe -m playwright install chromium
```

### 6.2 编译 JNSpider

#### 步骤 1: 确保浏览器驱动已安装

```bash
# 如果还没安装，先安装
venv\Scripts\python.exe -m playwright install chromium
```

#### 步骤 2: 执行编译

```bash
# 激活虚拟环境
venv\Scripts\activate.bat

# 编译
pyinstaller JNSpider.spec
```

或者：
```bash
venv\Scripts\pyinstaller.exe JNSpider.spec
```

#### 步骤 3: 检查输出

编译完成后，检查 `dist` 目录：
- `dist/JNSpider.exe` - 可执行文件
- `dist/playwright_drivers/chromium-XXXX/` - 浏览器驱动目录

**重要**: 浏览器驱动必须与 exe 文件在同一目录（`dist`），否则程序无法运行。

### 6.3 编译注意事项

1. **虚拟环境**: 必须在虚拟环境中编译，确保依赖版本一致
2. **浏览器驱动**: JNSpider 编译前必须安装 Playwright 浏览器驱动
3. **路径问题**: 确保所有路径使用相对路径或正确配置
4. **文件大小**: 
   - JNSpider.exe: 约 50-100MB（不含浏览器驱动）
   - 浏览器驱动: 约 170MB
5. **测试**: 编译后务必在干净的 Windows 系统上测试

---

## 7. 部署说明

### 7.1 JNSpider 部署

#### 7.1.1 文件部署

1. 复制以下文件到目标目录：
   - `dist/JNSpider.exe`
   - `dist/playwright_drivers/` 目录（整个目录）

**目录结构**:
```
目标目录/
├── JNSpider.exe
└── playwright_drivers/
    └── chromium-XXXX/
        └── chrome-win/
            └── chrome.exe
```

#### 7.1.2 运行服务

1. 双击运行 `JNSpider.exe`
2. 程序会自动：
   - 添加到开机自启动（首次运行）
   - 初始化浏览器池
   - 启动 HTTP 服务（127.0.0.1:8099）

#### 7.1.3 验证部署

使用浏览器或 curl 测试：
```bash
# 健康检查
curl http://127.0.0.1:8099/health

# 单个查询
curl "http://127.0.0.1:8099/query?waybill=JD1234567890"
```

### 7.2 部署检查清单

- [ ] JNSpider.exe 已复制到目标目录
- [ ] playwright_drivers 目录已复制
- [ ] 端口 8099 未被占用
- [ ] 网络连接正常
- [ ] 开机自启动已配置（首次运行自动配置）

---

## 8. API接口文档

### 8.1 基础信息

- **服务地址**: `http://127.0.0.1:8099`
- **协议**: HTTP
- **数据格式**: JSON
- **字符编码**: UTF-8

### 8.2 接口列表

#### 8.2.1 健康检查

**接口**: `GET /health`

**描述**: 检查服务状态和浏览器池初始化状态

**请求示例**:
```bash
curl http://127.0.0.1:8099/health
```

**响应示例**:
```json
{
  "status": "ok",
  "service": "JNSpider",
  "browser_pool_initialized": true,
  "startup_enabled": true
}
```

**响应字段说明**:
- `status`: 服务状态（"ok" 表示正常）
- `service`: 服务名称
- `browser_pool_initialized`: 浏览器池是否已初始化
- `startup_enabled`: 是否已启用开机自启动

#### 8.2.2 单个快递单号查询

**接口**: `GET /query`

**描述**: 查询单个快递单号的物流信息

**请求参数**:
- `waybill` (必需): 快递单号（字符串）

**请求示例**:
```bash
curl "http://127.0.0.1:8099/query?waybill=JD1234567890"
```

**响应示例（成功）**:
```json
{
  "success": true,
  "waybill": "JD1234567890",
  "data": {
    "success": true,
    "company": "京东快递",
    "state": "3",
    "data": [
      {
        "time": "2024-01-01 12:00:00",
        "context": "快件已签收",
        "location": "北京市"
      }
    ]
  }
}
```

**响应示例（失败）**:
```json
{
  "success": false,
  "waybill": "JD1234567890",
  "data": {
    "success": false,
    "error": "查询失败，未找到物流信息"
  }
}
```

**响应字段说明**:
- `success`: 请求是否成功
- `waybill`: 查询的快递单号
- `data`: 查询结果
  - `success`: 查询是否成功
  - `company`: 快递公司名称
  - `state`: 物流状态（"0"=在途, "1"=揽收, "2"=疑难, "3"=已签收, "4"=已退回）
  - `data`: 物流详情数组
    - `time`: 时间
    - `context`: 物流信息
    - `location`: 位置

**错误码**:
- `400`: 参数错误（缺少 waybill 参数或参数格式错误）
- `500`: 服务器内部错误（浏览器池未初始化或查询失败）

#### 8.2.3 批量快递单号查询

**接口**: `POST /batch`

**描述**: 批量查询多个快递单号的物流信息

**请求体**:
```json
{
  "waybills": ["JD1234567890", "SF9876543210"]
}
```

**请求示例**:
```bash
curl -X POST http://127.0.0.1:8099/batch \
  -H "Content-Type: application/json" \
  -d "{\"waybills\": [\"JD1234567890\", \"SF9876543210\"]}"
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "JD1234567890": {
      "success": true,
      "company": "京东快递",
      "state": "3",
      "data": [...]
    },
    "SF9876543210": {
      "success": true,
      "company": "顺丰快递",
      "state": "0",
      "data": [...]
    }
  }
}
```

**响应字段说明**:
- `success`: 请求是否成功
- `data`: 查询结果字典，键为快递单号，值为查询结果（格式同单个查询）

**错误码**:
- `400`: 参数错误（请求体为空、缺少 waybills 参数、waybills 不是数组、数组为空、数组中没有有效单号）
- `500`: 服务器内部错误

**注意事项**:
- 批量查询会顺序处理，耗时较长，请耐心等待
- 建议批量查询的单号数量不超过 50 个

#### 8.2.4 开机自启动管理

##### 查询自启动状态

**接口**: `GET /startup`

**描述**: 查询当前开机自启动状态

**请求示例**:
```bash
curl http://127.0.0.1:8099/startup
```

**响应示例**:
```json
{
  "success": true,
  "startup_enabled": true,
  "exe_path": "C:\\Program Files\\JNSpider\\JNSpider.exe"
}
```

##### 启用自启动

**接口**: `POST /startup`

**描述**: 启用开机自启动

**请求示例**:
```bash
curl -X POST http://127.0.0.1:8099/startup
```

**响应示例**:
```json
{
  "success": true,
  "message": "已启用开机自启动",
  "startup_enabled": true
}
```

##### 禁用自启动

**接口**: `DELETE /startup`

**描述**: 禁用开机自启动

**请求示例**:
```bash
curl -X DELETE http://127.0.0.1:8099/startup
```

**响应示例**:
```json
{
  "success": true,
  "message": "已禁用开机自启动",
  "startup_enabled": false
}
```

### 8.3 错误处理

所有接口在发生错误时都会返回 JSON 格式的错误信息：

```json
{
  "success": false,
  "error": "错误描述"
}
```

**HTTP 状态码**:
- `200`: 成功
- `400`: 客户端错误（参数错误）
- `404`: 接口不存在
- `500`: 服务器内部错误

---

## 9. 开发规范

### 9.1 代码规范

#### 9.1.1 Python 代码风格

- 遵循 PEP 8 代码风格规范
- 使用 4 个空格缩进
- 行长度不超过 120 字符
- 函数和类使用文档字符串（docstring）

**示例**:
```python
def query_waybill(waybill_number: str) -> dict:
    """
    查询快递单号
    
    Args:
        waybill_number: 快递单号
        
    Returns:
        查询结果字典
    """
    # 实现代码
    pass
```

#### 9.1.2 命名规范

- **模块名**: 小写字母，单词间用下划线（如 `logistics_query.py`）
- **类名**: 驼峰命名（如 `BrowserPool`）
- **函数名**: 小写字母，单词间用下划线（如 `get_logistics_info`）
- **变量名**: 小写字母，单词间用下划线（如 `waybill_number`）
- **常量名**: 全大写，单词间用下划线（如 `MAX_RETRY`）

#### 9.1.3 注释规范

- 每个模块开头添加模块说明
- 每个函数添加文档字符串
- 复杂逻辑添加行内注释
- 使用中文注释（项目要求）

**示例**:
```python
"""
物流信息查询模块
"""
import requests

def get_logistics_info(waybill_number: str) -> dict:
    """
    获取物流信息
    
    Args:
        waybill_number: 快递单号
        
    Returns:
        物流信息字典，包含 company, state, data 等字段
    """
    # 先获取快递类型
    express_type = get_express_type(waybill_number)
    # 然后根据类型查询物流信息
    # ...
```

### 9.2 项目结构规范

#### 9.2.1 模块组织

- **主程序**: 放在 `src/` 目录根目录
- **功能模块**: 按功能分类，放在子目录中
  - `api/`: API 相关模块
  - `spider/`: 爬虫相关模块
  - `utils/`: 工具模块
- **配置文件**: 放在 `src/` 目录根目录

#### 9.2.2 导入规范

- 标准库导入
- 第三方库导入
- 本地模块导入

**示例**:
```python
# 标准库
import sys
import os
from pathlib import Path

# 第三方库
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

# 本地模块
from config import Config
from spider.query_manager import BrowserPool
```

### 9.3 错误处理规范

#### 9.3.1 异常捕获

- 使用 try-except 捕获异常
- 记录详细的错误信息
- 返回用户友好的错误消息

**示例**:
```python
try:
    result = query_waybill(waybill_number)
    return jsonify({'success': True, 'data': result})
except Exception as e:
    print(f"查询异常: {e}")
    import traceback
    traceback.print_exc()
    return jsonify({
        'success': False,
        'error': f'服务器内部错误: {str(e)}'
    }), 500
```

#### 9.3.2 参数验证

- 验证必需参数是否存在
- 验证参数类型和格式
- 返回明确的错误信息

**示例**:
```python
waybill = request.args.get('waybill')
if not waybill:
    return jsonify({
        'success': False,
        'error': '缺少必需参数: waybill'
    }), 400

if not isinstance(waybill, str) or not waybill.strip():
    return jsonify({
        'success': False,
        'error': 'waybill参数必须是非空字符串'
    }), 400
```

### 9.4 日志规范

#### 9.4.1 日志级别

- **INFO**: 正常流程信息（服务启动、查询开始等）
- **WARNING**: 警告信息（路径未找到、使用默认值等）
- **ERROR**: 错误信息（查询失败、异常等）

#### 9.4.2 日志格式

使用 print 语句输出日志（当前实现）：
```python
print(f"[模块名] 日志信息")
```

**示例**:
```python
print(f"[JNSpider] 服务启动中...")
print(f"[BrowserPool] 正在初始化浏览器池...")
print(f"[查询] 正在查询单号: {waybill_number}")
```

### 9.5 版本管理规范

#### 9.5.1 版本号格式

使用语义化版本号：`主版本号.次版本号.修订号`

- **主版本号**: 不兼容的 API 修改
- **次版本号**: 向下兼容的功能性新增
- **修订号**: 向下兼容的问题修正

**示例**: `1.0.15`

#### 9.5.2 变更日志

- 所有变更记录在 `log.md` 文件中
- 变更记录格式：
  - 日期
  - 变更类型（新增/修改/删除）
  - 变更内容
  - 技术细节

---

## 10. 测试指南

### 10.1 单元测试

#### 10.1.1 测试框架

推荐使用 `pytest` 或 `unittest`。

#### 10.1.2 测试示例

**测试查询功能**:
```python
import pytest
from spider.logistics_query import get_logistics_info

def test_get_logistics_info():
    """测试获取物流信息"""
    result = get_logistics_info("JD1234567890")
    assert result is not None
    assert 'company' in result
    assert 'state' in result
```

### 10.2 集成测试

#### 10.2.1 API 测试

使用 `requests` 库测试 API 接口：

```python
import requests

def test_health_check():
    """测试健康检查接口"""
    response = requests.get('http://127.0.0.1:8099/health')
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'ok'

def test_query_single():
    """测试单个查询接口"""
    response = requests.get(
        'http://127.0.0.1:8099/query',
        params={'waybill': 'JD1234567890'}
    )
    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
```

### 10.3 功能测试

#### 10.3.1 JNSpider 功能测试

1. **服务启动测试**:
   - 运行 `JNSpider.exe`
   - 验证服务是否正常启动
   - 验证浏览器池是否初始化成功

2. **API 接口测试**:
   - 使用 curl 或 Postman 测试所有接口
   - 验证响应格式和状态码

3. **查询功能测试**:
   - 测试单个查询
   - 测试批量查询
   - 测试不同快递类型的查询

4. **自启动测试**:
   - 测试添加自启动
   - 测试移除自启动
   - 重启系统验证自启动是否生效

### 10.4 性能测试

#### 10.4.1 查询性能

- 单个查询响应时间（目标: < 5 秒）
- 批量查询性能（10 个单号，目标: < 60 秒）

#### 10.4.2 资源占用

- 内存占用（目标: < 500MB）
- CPU 占用（空闲时 < 5%）

### 10.5 兼容性测试

#### 10.5.1 操作系统兼容性

- Windows 10 (64位)
- Windows 11 (64位)

#### 10.5.2 Python 版本兼容性

- Python 3.8
- Python 3.9
- Python 3.10
- Python 3.11
- Python 3.12

---

## 11. 常见问题与解决方案

### 11.1 编译问题

#### Q1: PyInstaller 编译失败

**问题**: 编译时提示找不到模块或依赖

**解决方案**:
1. 确保在虚拟环境中编译
2. 检查 `requirements.txt` 中的依赖是否都已安装
3. 检查 `.spec` 文件中的 `hiddenimports` 是否包含所有需要的模块

#### Q2: 编译后的 exe 无法运行

**问题**: 双击 exe 后立即退出或报错

**解决方案**:
1. 在命令行运行 exe，查看错误信息
2. 检查是否缺少必要的依赖
3. 检查路径问题（相对路径 vs 绝对路径）
4. 在开发环境先测试 Python 脚本是否正常

#### Q3: JNSpider 编译后找不到浏览器驱动

**问题**: 运行 exe 时提示 "Executable doesn't exist"

**解决方案**:
1. 确保编译前已安装 Playwright 浏览器驱动
2. 检查 `dist/playwright_drivers/` 目录是否存在
3. 检查浏览器驱动路径是否正确

### 11.2 运行问题

#### Q1: JNSpider 服务启动失败

**问题**: 服务无法启动，提示端口被占用

**解决方案**:
```bash
# 检查端口占用
netstat -ano | findstr :8099

# 结束占用端口的进程
taskkill /PID <进程ID> /F
```

#### Q2: 浏览器池初始化失败

**问题**: 提示 "Playwright 浏览器驱动未安装"

**解决方案**:
1. 开发环境: 运行 `playwright install chromium`
2. 打包后: 确保 `playwright_drivers` 目录与 exe 同目录
3. 检查浏览器驱动路径是否正确

#### Q3: 查询失败

**问题**: API 返回查询失败

**可能原因**:
1. 网络连接问题
2. 快递单号格式错误
3. 快递公司不支持
4. 网站反爬虫机制

**解决方案**:
1. 检查网络连接
2. 验证单号格式
3. 尝试其他查询方案
4. 查看控制台错误信息

### 11.3 部署问题

#### Q1: 开机自启动不生效

**问题**: 重启后服务未自动启动

**解决方案**:
1. 检查注册表中是否已添加启动项
2. 检查 exe 路径是否正确
3. 检查是否有杀毒软件拦截

#### Q2: 服务无法访问

**问题**: 无法通过 HTTP 访问服务

**解决方案**:
1. 检查防火墙设置
2. 检查服务是否正在运行
3. 检查端口是否正确

---

## 12. 版本历史

详见 [log.md](./log.md) 文件。

### 主要版本里程碑

- **v1.0.15** (2026-01-06): 当前版本
  - 代码重构，模块化设计
  - 浏览器驱动路径优化
  - 开机自启动功能完善

- **v1.0.0** (2026-01-06): 初始版本
  - JNSpider HTTP 服务
  - 快递查询功能

---

## 附录

### A. 相关链接

- [Python 官网](https://www.python.org/)
- [Flask 文档](https://flask.palletsprojects.com/)
- [Playwright 文档](https://playwright.dev/python/)
- [PyInstaller 文档](https://pyinstaller.org/)

### B. 联系方式

如有问题或建议，请联系项目维护者。

### C. 许可证

本项目为内部使用项目。

---

**文档结束**
