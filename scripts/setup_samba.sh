#!/usr/bin/env bash
# Holomat — Samba share setup script.
# Sets up \\KJLC-AI-01\HolomatGallery as a guest-accessible write share.
# Run once as a user with sudo: bash scripts/setup_samba.sh
set -euo pipefail

SHARE_DIR="/home/jarvis/holomat-api/smb_share"
HOLOMAT_CONF="/home/jarvis/holomat-api/config/samba.conf"
SAMBA_MAIN="/etc/samba/smb.conf"
INCLUDE_LINE="include = $HOLOMAT_CONF"

echo "=== Holomat — Samba share setup ==="

# 1. Install Samba if not present
if ! command -v smbd &> /dev/null; then
    echo "Installing Samba..."
    sudo apt-get update -q
    sudo apt-get install -y samba
fi

# 2. Create the share directory
echo "Creating share directory: $SHARE_DIR"
mkdir -p "$SHARE_DIR"
chmod 775 "$SHARE_DIR"
# Allow guest writes — samba will use force user=jarvis
sudo chown jarvis:jarvis "$SHARE_DIR"

# 3. Wire our config into /etc/samba/smb.conf (idempotent)
if ! grep -qF "$INCLUDE_LINE" "$SAMBA_MAIN" 2>/dev/null; then
    echo "Adding include to $SAMBA_MAIN"
    echo "" | sudo tee -a "$SAMBA_MAIN" > /dev/null
    echo "$INCLUDE_LINE" | sudo tee -a "$SAMBA_MAIN" > /dev/null
else
    echo "Include already present in $SAMBA_MAIN — skipping"
fi

# 4. Restart + enable Samba
echo "Restarting Samba services..."
sudo systemctl restart smbd nmbd
sudo systemctl enable smbd nmbd

# 5. Open firewall if ufw is active
if sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    echo "Opening Samba ports in ufw..."
    sudo ufw allow samba
fi

echo ""
echo "=== Done ==="
HOSTNAME=$(hostname)
echo "  Share name : HolomatGallery"
echo "  Windows    : \\\\${HOSTNAME}\\HolomatGallery"
echo "  macOS      : smb://${HOSTNAME}/HolomatGallery"
echo "  Local path : $SHARE_DIR"
echo ""
echo "Drop images here from any device on your network."
echo "Supported: jpg, jpeg, png, webp, heic, heif, gif"
