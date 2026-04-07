@echo off
chcp 65001 >nul 2>&1
title 如意助手 - 自动构建

echo ============================================================
echo   如意助手 自动构建脚本
echo   用法:
echo     build.bat              打包 + 生成安装包
echo     build.bat --no-inst    只打包 (不生成安装包)
echo     build.bat --version    查看版本号
echo ============================================================
echo.

:: 定位项目根目录 (build.bat 所在目录)
cd /d "%~dp0"

:: 激活虚拟环境
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] 未找到虚拟环境，使用系统 Python
)

:: 判断参数
if "%1"=="--version" (
    python build.py --version
    goto :end
)

if "%1"=="--no-inst" (
    echo [模式] 仅 PyInstaller 打包 (不生成安装包)
    echo.
    python build.py
) else (
    echo [模式] 完整构建: PyInstaller + Inno Setup 安装包
    echo.
    python build.py --installer
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo   构建失败！请查看上方错误信息
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo   构建成功！
    echo ============================================================
)

:end
echo.
pause
