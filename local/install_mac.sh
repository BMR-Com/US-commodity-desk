#!/bin/bash
# One-time setup on Ma's Mac: nightly CME + USDA flash collector that runs without Claude.
# Usage (from the repo folder):  bash local/install_mac.sh
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME/.ags-desk"
mkdir -p "$HOME_DIR"
python3 -m venv "$HOME_DIR/venv"
"$HOME_DIR/venv/bin/pip" install -q --upgrade pip playwright pandas
"$HOME_DIR/venv/bin/python" -m playwright install chromium   # fallback if Google Chrome is not installed
PLIST="$HOME/Library/LaunchAgents/com.bmrcom.agsdesk.collector.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.bmrcom.agsdesk.collector</string>
  <key>ProgramArguments</key><array><string>$HOME_DIR/venv/bin/python</string><string>$REPO/local/mac_collector.py</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>35</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>35</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$HOME_DIR/launchd.out</string>
  <key>StandardErrorPath</key><string>$HOME_DIR/launchd.err</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed. Runs weekdays 9:35 pm (Mac local time). Test now with:"
echo "  $HOME_DIR/venv/bin/python $REPO/local/mac_collector.py"
echo "Log: $HOME_DIR/collector.log"
