@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3 scripts/launch_web.py
if errorlevel 1 pause
