@echo off
:: AutoTikTok Daily Content Generator
:: Usage: run_daily.bat [count] [min-score]
:: Example: run_daily.bat 3 65

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

"C:\ProgramData\anaconda3\python.exe" "%~dp0run_daily.py" %*
