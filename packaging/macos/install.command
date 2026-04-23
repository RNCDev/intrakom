#!/usr/bin/env bash
set -euo pipefail

echo ""
echo " Intrakom Receiver - Install"
echo " ============================"
echo ""

# Determine binary path (same directory as this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE="$SCRIPT_DIR/intrakom-receiver"

if [ ! -f "$EXE" ]; then
    echo "ERROR: intrakom-receiver not found in $SCRIPT_DIR"
    echo "Please unzip the release package and run install.sh from inside the folder."
    exit 1
fi

chmod +x "$EXE"
xattr -dr com.apple.quarantine "$EXE" 2>/dev/null || true

# Get receiver name
RECEIVER_NAME="${1:-}"
if [ -z "$RECEIVER_NAME" ]; then
    read -rp "Enter a name for this receiver (e.g. Living Room, Office): " RECEIVER_NAME
fi
if [ -z "$RECEIVER_NAME" ]; then
    echo "ERROR: Receiver name cannot be empty."
    exit 1
fi

# Get hub URL
HUB_URL="${2:-}"
if [ -z "$HUB_URL" ]; then
    read -rp "Enter the hub URL (e.g. http://192.168.1.10:8000): " HUB_URL
fi
if [ -z "$HUB_URL" ]; then
    echo "ERROR: Hub URL cannot be empty."
    exit 1
fi

echo ""
echo " Installing receiver \"$RECEIVER_NAME\" pointing to $HUB_URL"
echo ""

PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/com.intrakom.receiver.plist"
LOG_DIR="$HOME/Library/Logs/Intrakom"

mkdir -p "$PLIST_DIR"
mkdir -p "$LOG_DIR"

# Unload any existing plist before overwriting
if launchctl list | grep -q "com.intrakom.receiver" 2>/dev/null; then
    echo " Stopping existing receiver..."
    launchctl unload "$PLIST" 2>/dev/null || true
fi

# Write plist from template
TEMPLATE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$TEMPLATE_DIR/com.intrakom.receiver.plist.template" ]; then
    sed \
        -e "s|BINARY_PATH|$EXE|g" \
        -e "s|RECEIVER_NAME|$RECEIVER_NAME|g" \
        -e "s|HUB_URL|$HUB_URL|g" \
        -e "s|LOG_DIR|$LOG_DIR|g" \
        "$TEMPLATE_DIR/com.intrakom.receiver.plist.template" > "$PLIST"
else
    # Inline fallback if template not present
    cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.intrakom.receiver</string>
  <key>ProgramArguments</key>
  <array>
    <string>$EXE</string>
    <string>--name</string><string>$RECEIVER_NAME</string>
    <string>--hub</string><string>$HUB_URL</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG_DIR/receiver.log</string>
  <key>StandardErrorPath</key><string>$LOG_DIR/receiver.log</string>
  <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
PLISTEOF
fi

launchctl load "$PLIST"

echo ""
echo " Done! The receiver will start automatically at every login."
echo ""
echo " To verify it's running, open the hub admin page in your browser:"
echo "   $HUB_URL/admin"
echo ""
echo " To check logs:"
echo "   tail -f $LOG_DIR/receiver.log"
echo ""
echo " To uninstall, run uninstall.sh in this folder."
echo ""
