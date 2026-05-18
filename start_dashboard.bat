@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements.txt
python dashboard.py --host 127.0.0.1 --port 7860
