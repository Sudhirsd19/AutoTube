@echo off
REM AutoTube Daily Autonomous Execution Script (7-Day Universal Mirror Schedule)
cd /d "D:\AutoTube"
echo Starting AutoTube Daily Batch (7-Day English + Hindi Mirror Videos)...
".venv\Scripts\python.exe" run.py autopilot --upload --schedule >> "output\daily_run.log" 2>&1
echo Finished AutoTube Daily Batch.
