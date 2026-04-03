@echo off
chcp 65001 >nul
echo Chon pipeline:
echo   1. Batch Video (co san am thanh + nhac nen + text)
echo   2. Voice Video (generate TTS + subtitle + text)
echo.
set /p choice="Nhap 1 hoac 2: "
if "%choice%"=="1" call "%~dp0run_videos.bat"
if "%choice%"=="2" call "%~dp0run_voice.bat"
