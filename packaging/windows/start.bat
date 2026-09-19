@echo off
chcp 65001 >nul
title Homa Task Bot
cd /d "%~dp0"

echo ========================================================
echo               Homa Task Telegram Bot
echo ========================================================
echo.

if not exist ".env" (
    echo [ERROR] .env file not found!
    echo Please copy .env.example to .env and fill in the required settings.
    echo.
    pause
    exit /b 1
)

if exist "python\python.exe" (
    echo Starting bot using bundled Python runtime...
    python\python.exe run.py
) else (
    echo Starting bot using system Python...
    python run.py
)

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Bot exited with code %errorlevel%.
    pause
)
