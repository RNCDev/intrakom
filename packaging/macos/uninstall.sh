#!/usr/bin/env bash
set -euo pipefail

echo ""
echo " Intrakom Receiver - Uninstall"
echo " ================================"
echo ""

PLIST="$HOME/Library/LaunchAgents/com.intrakom.receiver.plist"

if [ ! -f "$PLIST" ]; then
    echo " Intrakom Receiver LaunchAgent not found. Nothing to remove."
    exit 0
fi

echo " Stopping receiver..."
launchctl unload "$PLIST" 2>/dev/null || true

echo " Removing LaunchAgent..."
rm -f "$PLIST"

echo ""
echo " Done. Intrakom Receiver has been uninstalled."
echo " (Logs remain at ~/Library/Logs/Intrakom/ — delete manually if desired.)"
echo ""
