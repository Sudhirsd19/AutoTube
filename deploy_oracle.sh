#!/bin/bash
# =================================================================
# AutoTube Oracle Cloud VM 1-Click Deployment Script (Ubuntu/Debian)
# =================================================================

set -e

echo "🚀 [1/5] Updating system and installing required packages (Python, FFmpeg, Fonts)..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg git fonts-dejavu-core curl

echo "📦 [2/5] Creating Python virtual environment..."
python3 -m venv .venv

echo "📥 [3/5] Installing AutoTube dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "🔍 [4/5] Verifying AutoTube setup..."
.venv/bin/python run.py init

echo "⏰ [5/5] Setting up automated daily Cron Job (Runs daily at 08:00 AM IST / 02:30 UTC)..."
AUTOTUBE_DIR=$(pwd)
CRON_CMD="30 2 * * * cd $AUTOTUBE_DIR && $AUTOTUBE_DIR/.venv/bin/python run.py autopilot --count 2 --niche space --lang en --upload --schedule >> $AUTOTUBE_DIR/output/cron.log 2>&1"

# Add cron job if not already present
(crontab -l 2>/dev/null | grep -F "$AUTOTUBE_DIR" ) || (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "================================================================="
echo "✅ AutoTube successfully installed and activated on Oracle Cloud VM!"
echo "• Cron Schedule: Runs daily at 08:00 AM IST (02:30 UTC) - Dynamic Slot Matrix"
echo "• Logs Location: $AUTOTUBE_DIR/output/cron.log"
echo "• Test Manual Run: .venv/bin/python run.py autopilot --count 1"
echo "================================================================="
