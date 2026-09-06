@echo off
cd /d "%~dp0"

echo ========================================
echo   AI TRADER - TradingView Webhook
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: .venv Python not found.
    echo Expected: %CD%\.venv\Scripts\python.exe
    pause
    exit /b 1
)

.venv\Scripts\python.exe run_tradingview.py

pause