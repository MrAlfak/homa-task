@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Homa Task Bot (@Homatask_bot)

cd /d "%~dp0"

echo ========================================================
echo               Homa Task Telegram Bot
echo                  @Homatask_bot
echo ========================================================
echo.

:: Check .env
if not exist ".env" (
    echo [ERROR] .env file not found in %CD%!
    echo Please make sure .env exists with BOT_TOKEN and GOOGLE_SHEET_ID.
    echo.
    pause
    exit /b 1
)

:: Locate Python
set "PY_BIN="
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PY_BIN=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
) else (
    where python >nul 2>&1
    if !errorlevel! equ 0 (
        set "PY_BIN=python"
    ) else if exist "C:\Users\Administrator\Desktop\HomaTask-windows\HomaTask\python\python.exe" (
        set "PY_BIN=C:\Users\Administrator\Desktop\HomaTask-windows\HomaTask\python\python.exe"
    )
)

if "!PY_BIN!"=="" (
    echo [ERROR] Python was not found!
    echo Please ensure Python is installed and added to PATH.
    echo.
    pause
    exit /b 1
)

set PYTHONNOUSERSITE=1
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

echo [INFO] Using Python: !PY_BIN!
echo [INFO] Starting Homa Task Bot...
echo.

:loop
"!PY_BIN!" run.py
set "EXIT_CODE=%errorlevel%"

echo.
echo [WARN] Bot stopped with exit code !EXIT_CODE!.
echo [INFO] Restarting in 5 seconds... (Press Ctrl+C to stop)
timeout /t 5 /nobreak >nul
goto loop
