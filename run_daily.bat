@echo off
REM AutoTube Daily Autonomous Execution Script
cd /d "D:\AutoTube"
echo Starting AutoTube Daily Batch...
".venv\Scripts\python.exe" run.py autopilot --count 5 --niche space --upload --schedule >> "output\daily_run.log" 2>&1
echo Finished AutoTube Daily Batch.
