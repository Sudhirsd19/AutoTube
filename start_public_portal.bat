@echo off
title AutoTube Public Guest Portal
cd /d "%~dp0"
echo ========================================================
echo   AutoTube AI - Public Guest Portal (2 Videos/Day Limit)
echo ========================================================
echo.
".venv\Scripts\python.exe" run_public_portal.py
pause
