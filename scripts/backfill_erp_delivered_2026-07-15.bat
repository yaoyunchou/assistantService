@echo off
chcp 65001 >nul
cd /d "%~dp0.."
echo === 补刷 ERP 已发货：昨天 + 全部打印状态（修 2026-07-15 一类漏单）===
echo 请确认：助手已启动(8887)、拼多多 ERP 已登录
echo.
python scripts\backfill_erp_delivered.py --date-shortcut 昨天 --ship-date 2026-07-15 --base-url http://127.0.0.1:8887
echo.
echo exitCode=%ERRORLEVEL%
pause
