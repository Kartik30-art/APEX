@echo off
setlocal
cd /d "%~dp0"
echo APEX MT5 DEMO bridge setup
echo This installs the bridge on this Windows PC. It does not enable live trading.
py -3 -m venv .venv
if errorlevel 1 goto error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto error
pip install MetaTrader5 requests
if errorlevel 1 goto error
python apex_mt5_bridge.py
goto end
:error
echo Setup failed. Install 64-bit Python 3.11+ and try again.
pause
:end
endlocal
