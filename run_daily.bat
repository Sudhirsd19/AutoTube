@echo off
REM AutoTube Daily Autonomous Execution Script (7-Day Universal Mirror Schedule)
cd /d "D:\AutoTube"
echo. >> "output\daily_run.log"
echo ================================================================= >> "output\daily_run.log"
echo [RUN STARTED: %DATE% %TIME%] AutoTube Daily Batch >> "output\daily_run.log"
echo ================================================================= >> "output\daily_run.log"
".venv\Scripts\python.exe" run.py autopilot --upload --schedule >> "output\daily_run.log" 2>&1
echo [RUN COMPLETED: %DATE% %TIME%] >> "output\daily_run.log"
