; Inno Setup 安装包脚本
; 用于打包如意助手应用程序

[Setup]
; 注意: AppId的值唯一标识你的应用程序。
; 不要使用相同的AppId值为不同的应用程序。
; (若要生成新的 GUID，可在菜单中选择 "工具" -> "生成 GUID")
AppId={{2024AABB-CCDD-EEFF-0123-456789ABCDEE}}
AppName=如意助手
AppVersion=2.0.1
AppPublisher=如意助手
AppPublisherURL=
AppSupportURL=
AppUpdatesURL=
; 应用程序的默认安装目录
DefaultDirName={commonpf}\如意助手
DefaultGroupName=如意助手
; 允许用户选择安装目录
AllowNoIcons=yes
; 压缩方式
Compression=lzma2/ultra
SolidCompression=yes
; 输出目录和文件名
OutputDir=.
OutputBaseFilename=如意助手_Setup_v2.0.1
; 需要管理员权限（用于安装到 Program Files）
PrivilegesRequired=admin
; 安装程序图标（可选，如果有的话）
; SetupIconFile=src\static\images\icon.ico
; 安装程序窗口信息
WizardStyle=modern
LicenseFile=
InfoBeforeFile=
InfoAfterFile=
; 卸载时删除用户数据（可选）
UninstallDisplayIcon={app}\如意助手.exe
UninstallDisplayName=如意助手

[Languages]
; 方案1：使用中文界面（需要下载中文语言包）
; 下载地址：https://jrsoftware.org/files/istrans/
; 下载 ChineseSimplified.isl 文件，放到 Inno Setup 的 Languages 目录
; 通常路径：C:\Program Files (x86)\Inno Setup 6\Languages\
; Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

; 方案2：使用默认英文界面（推荐，无需额外文件）
; 如果上面的中文配置报错，注释掉上面的行，使用下面的默认配置
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked
Name: "quicklaunchicon"; Description: "创建快速启动栏快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; 主程序文件
Source: "dist\如意助手\如意助手.exe"; DestDir: "{app}"; Flags: ignoreversion
; 依赖文件目录（_internal 包含所有 Python 依赖）
Source: "dist\如意助手\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; 浏览器驱动目录
Source: "dist\如意助手\playwright_drivers\*"; DestDir: "{app}\playwright_drivers"; Flags: ignoreversion recursesubdirs createallsubdirs
; 注意：logs 目录不需要打包，会在运行时自动创建

[Icons]
; 开始菜单快捷方式
Name: "{group}\如意助手"; Filename: "{app}\如意助手.exe"; WorkingDir: "{app}"
Name: "{group}\卸载如意助手"; Filename: "{uninstallexe}"
; 桌面快捷方式（可选，由用户选择）
Name: "{commondesktop}\如意助手"; Filename: "{app}\如意助手.exe"; WorkingDir: "{app}"; Tasks: desktopicon
; 快速启动栏快捷方式（可选，由用户选择）
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\如意助手"; Filename: "{app}\如意助手.exe"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Run]
; 安装完成后运行程序（可选）
; Filename: "{app}\如意助手.exe"; Description: "启动如意助手"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时删除日志目录（可选）
Type: filesandordirs; Name: "{app}\logs"

[Code]
// 自定义安装后处理（可选）
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 安装完成后的处理
    // 例如：创建必要的目录、设置权限等
  end;
end;
