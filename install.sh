#!/usr/bin/env bash
# HoloMat API — install script for KJLC-AI-01
# Run once as kyle (not root). Installs deps + systemd service.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/holomat-api.service"

echo "=== HoloMat API install ==="

# 1. Python venv + deps
echo ""
echo "1. Creating venv and installing Python dependencies..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo "   ✅ Done"

# 2. Test Bambu connection before going further
echo ""
echo "2. Testing Bambu connection (Ctrl+C to skip)..."
python3 "$SCRIPT_DIR/test_bambu.py" || true

# 3. systemd service
echo ""
echo "3. Installing systemd service..."
sudo cp "$SERVICE_FILE" /etc/systemd/system/holomat-api.service
sudo systemctl daemon-reload
sudo systemctl enable holomat-api
sudo systemctl restart holomat-api
sleep 2
sudo systemctl status holomat-api --no-pager
echo ""
echo "=== Done! ==="
echo "  API running at: http://10.11.12.129:8100"
echo "  Health check:   curl http://10.11.12.129:8100/health"
echo "  View logs:      journalctl -u holomat-api -f"
