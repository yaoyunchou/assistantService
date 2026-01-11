# 变更日志

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
