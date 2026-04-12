#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# IITDH Attendance System — Boot Launcher
# Boot delay lives here so systemd's ExecStartPre never times out.
# ─────────────────────────────────────────────────────────────────

ENV_DIR="/home/bio_user_iitdh/new_env"
MAIN_SCRIPT="$ENV_DIR/01marchrunningcode.py"
LOG_FILE="$ENV_DIR/logs/attendance.log"

mkdir -p "$ENV_DIR/logs"

echo "========================================" | tee -a "$LOG_FILE"
echo "  IITDH Attendance System Starting..."   | tee -a "$LOG_FILE"
echo "  $(date)"                               | tee -a "$LOG_FILE"
echo "========================================"  | tee -a "$LOG_FILE"

# Wait for GPIO/SPI/I2C/fingerprint sensor to be fully ready after boot.
# This runs INSIDE the script so systemd never sees a pre-start timeout.
echo "⏳ Waiting 10s for hardware to settle..." | tee -a "$LOG_FILE"
sleep 10

cd "$ENV_DIR" || { echo "❌ Cannot find $ENV_DIR" | tee -a "$LOG_FILE"; exit 1; }
source "$ENV_DIR/bin/activate" || { echo "❌ Cannot activate venv" | tee -a "$LOG_FILE"; exit 1; }

echo "✅ venv active: $(which python3)" | tee -a "$LOG_FILE"

python3 "$MAIN_SCRIPT" 2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}
echo "⚠️  Exited with code: $EXIT_CODE  ($(date))" | tee -a "$LOG_FILE"

# Exit code 42 = admin requested desktop
if [ "$EXIT_CODE" -eq 42 ]; then
    echo "🖥️  Opening desktop..." | tee -a "$LOG_FILE"
    DISPLAY=:0 startx &
fi
