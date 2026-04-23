#!/usr/bin/env bash
# Intrakom Hub installer for Raspberry Pi / Linux
# Run once on your always-on device:
#   bash <(curl -fsSL https://raw.githubusercontent.com/RNCDev/intrakom/main/packaging/linux/install-hub.sh)

set -euo pipefail

REPO="https://github.com/RNCDev/intrakom.git"
INSTALL_DIR="$HOME/intrakom"
SERVICE="intrakom-hub"
SYSTEMD_DIR="$HOME/.config/systemd/user"

echo ""
echo "=================================================="
echo "  Intrakom Hub Installer"
echo "=================================================="
echo ""

# ── Prerequisites ─────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install it with: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
if ! command -v git &>/dev/null; then
    echo "ERROR: git not found. Install it with: sudo apt install git"
    exit 1
fi

# ── Clone or update repo ──────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "Updating existing installation at $INSTALL_DIR ..."
    git -C "$INSTALL_DIR" pull
else
    echo "Cloning Intrakom into $INSTALL_DIR ..."
    git clone "$REPO" "$INSTALL_DIR"
fi

# ── Python venv ───────────────────────────────────────
echo "Setting up Python environment ..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

PYTHON="$INSTALL_DIR/venv/bin/python"

# ── Tailscale HTTPS cert (optional) ──────────────────
CERT_FILE=""
KEY_FILE=""
if command -v tailscale &>/dev/null; then
    TS_HOSTNAME=$(tailscale status --json 2>/dev/null | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(d['Self']['DNSName'].rstrip('.'))" 2>/dev/null || true)
    if [ -n "$TS_HOSTNAME" ]; then
        echo ""
        echo "Tailscale detected. Setting up HTTPS certificate for $TS_HOSTNAME ..."
        sudo tailscale set --operator="$USER" 2>/dev/null || true
        if tailscale cert "$TS_HOSTNAME" 2>/dev/null; then
            # Move certs into install dir
            mv "${TS_HOSTNAME}.crt" "$INSTALL_DIR/" 2>/dev/null || true
            mv "${TS_HOSTNAME}.key" "$INSTALL_DIR/" 2>/dev/null || true
            CERT_FILE="$INSTALL_DIR/${TS_HOSTNAME}.crt"
            KEY_FILE="$INSTALL_DIR/${TS_HOSTNAME}.key"
            echo "HTTPS certificate installed. Hub will serve https://$TS_HOSTNAME:8000"
        else
            echo "Could not get Tailscale cert (HTTPS disabled in admin console?). Continuing with HTTP."
        fi
    fi
fi

# ── systemd user service ──────────────────────────────
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/${SERVICE}.service" << EOF
[Unit]
Description=Intrakom Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON hub.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE"
systemctl --user restart "$SERVICE"

# Allow service to run without being logged in
loginctl enable-linger "$USER" 2>/dev/null || true

# ── Done ──────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  Hub installed and running!"
echo ""

# Show the URL
if [ -n "$CERT_FILE" ]; then
    echo "  Open: https://$TS_HOSTNAME:8000"
else
    LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<your-pi-ip>")
    echo "  Open: http://$LAN_IP:8000"
fi

echo ""
echo "  Admin page: (above URL)/admin"
echo ""
echo "  To check status:  systemctl --user status $SERVICE"
echo "  To view logs:     journalctl --user -u $SERVICE -f"
echo "  To update:        bash $INSTALL_DIR/packaging/linux/install-hub.sh"
echo "=================================================="
echo ""
