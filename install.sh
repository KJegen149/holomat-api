#!/usr/bin/env bash
# Holomat — install script for KJLC-AI-01
# Run as a user with sudo (not root).
# Usage: bash install.sh [--with-samba] [--with-kiosk]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WITH_SAMBA=false
WITH_KIOSK=false

for arg in "$@"; do
  case $arg in
    --with-samba)  WITH_SAMBA=true ;;
    --with-kiosk)  WITH_KIOSK=true ;;
  esac
done

echo "=== Holomat install ==="
echo "  Script dir : $SCRIPT_DIR"
echo "  Samba      : $WITH_SAMBA"
echo "  Kiosk UI   : $WITH_KIOSK"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────
echo "1. Installing system dependencies..."
sudo apt-get update -q
sudo apt-get install -y \
    python3 python3-venv python3-pip \
    libgl1 libglib2.0-0 \
    v4l-utils \
    curl

echo "   ✅ System deps done"

# ── 2. Python venv + deps ─────────────────────────────────────────────────
echo ""
echo "2. Creating Python venv and installing dependencies..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install --quiet --upgrade pip
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
echo "   ✅ Python deps done"

# ── 3. Directory structure ────────────────────────────────────────────────
echo ""
echo "3. Ensuring runtime directories exist..."
mkdir -p "$SCRIPT_DIR/calibration_data"
mkdir -p "$SCRIPT_DIR/scan_data"
mkdir -p "$SCRIPT_DIR/smb_share"
mkdir -p "$SCRIPT_DIR/config"
mkdir -p "$SCRIPT_DIR/scripts"
chmod +x "$SCRIPT_DIR/scripts/"*.sh
echo "   ✅ Directories ready"

# ── 4. Bambu connectivity test (optional) ─────────────────────────────────
echo ""
echo "4. Testing Bambu P1S connection (Ctrl+C to skip)..."
"$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/test_bambu.py" || true

# ── 5. Samba share (optional) ─────────────────────────────────────────────
if [ "$WITH_SAMBA" = true ]; then
    echo ""
    echo "5. Setting up Samba gallery share..."
    bash "$SCRIPT_DIR/scripts/setup_samba.sh"
else
    echo ""
    echo "5. Samba skipped. Run later with:  bash scripts/setup_samba.sh"
fi

# ── 6. Holomat API systemd service ────────────────────────────────────────
echo ""
echo "6. Installing holomat-api systemd service..."
sudo cp "$SCRIPT_DIR/holomat-api.service" /etc/systemd/system/holomat-api.service
sudo systemctl daemon-reload
sudo systemctl enable holomat-api
sudo systemctl restart holomat-api
sleep 3
sudo systemctl status holomat-api --no-pager -l
echo "   ✅ holomat-api service installed"

# ── 7. Kiosk UI systemd service (optional) ────────────────────────────────
if [ "$WITH_KIOSK" = true ]; then
    echo ""
    echo "7. Installing holomat-ui kiosk service..."
    if ! command -v chromium-browser &> /dev/null && ! command -v chromium &> /dev/null; then
        echo "   Installing Chromium..."
        sudo apt-get install -y chromium-browser || sudo apt-get install -y chromium
    fi
    sudo cp "$SCRIPT_DIR/holomat-ui.service" /etc/systemd/system/holomat-ui.service
    sudo systemctl daemon-reload
    sudo systemctl enable holomat-ui
    echo "   ✅ holomat-ui service installed (starts on next graphical boot)"
else
    echo ""
    echo "7. Kiosk UI skipped. Run later with:"
    echo "     sudo cp holomat-ui.service /etc/systemd/system/"
    echo "     sudo systemctl enable --now holomat-ui"
fi

# ── Done ──────────────────────────────────────────────────────────────────
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "=== Install complete ==="
echo "  API        : http://${HOST_IP:-<host>}:8100"
echo "  Health     : curl http://${HOST_IP:-<host>}:8100/api/health"
echo "  API docs   : http://${HOST_IP:-<host>}:8100/api/docs"
echo "  Logs       : journalctl -u holomat-api -f"
echo ""
echo "Next: set GEMINI_API_KEY and CF_API_KEY via the Settings UI:"
echo "  Open http://${HOST_IP:-<host>}:8100/settings"
echo "  or:  sudo systemctl edit holomat-api"
echo "       Environment=GEMINI_API_KEY=your_key_here"
echo "       Environment=CF_API_KEY=your_key_here"
