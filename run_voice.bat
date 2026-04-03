@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo ============================================================
echo  Voice Video Processor
echo ============================================================
python "%~dp0run_voice.py" %*
echo.
pause
