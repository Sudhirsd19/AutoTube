@echo off
REM AutoTube Daily Autonomous Execution Script
cd /d "D:\AutoTube"
echo Starting AutoTube Daily Batch (2 Elite Space Videos)...
".venv\Scripts\python.exe" run.py autopilot --count 2 --niche space --lang en --upload --schedule >> "output\daily_run.log" 2>&1
echo Finished AutoTube Daily Batch.
