@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
echo ============================================================
echo  Batch Video Processor
echo ============================================================
python "%~dp0run_videos.py" %*
echo.
pause
