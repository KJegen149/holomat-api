#!/usr/bin/env bash
# Holomat pre-start script — runs before uvicorn starts.
# Validates calibration freshness. If stale or missing, removes
# the calibration file so the UI boots into calibration wizard mode.
set -euo pipefail

CALIB_FILE="/home/jarvis/holomat-api/calibration_data/current.json"
MAX_AGE_DAYS=30
LOG_PREFIX="[pre_start]"

echo "$LOG_PREFIX Holomat pre-start check"

if [ -f "$CALIB_FILE" ]; then
    file_mtime=$(stat -c %Y "$CALIB_FILE")
    now=$(date +%s)
    age_seconds=$(( now - file_mtime ))
    age_days=$(( age_seconds / 86400 ))

    if [ "$age_days" -ge "$MAX_AGE_DAYS" ]; then
        echo "$LOG_PREFIX Calibration is ${age_days} days old (max $MAX_AGE_DAYS) — clearing for recalibration"
        rm -f "$CALIB_FILE"
    else
        echo "$LOG_PREFIX Calibration valid — ${age_days} days old"
    fi
else
    echo "$LOG_PREFIX No calibration data found — calibration wizard will run on first load"
fi

# Ensure share and data directories exist
mkdir -p /home/jarvis/holomat-api/smb_share
mkdir -p /home/jarvis/holomat-api/calibration_data

echo "$LOG_PREFIX Pre-start complete"
