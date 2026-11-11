#!/bin/bash
# One-time setup on Ma's Mac: release-time phone alerts (local/flash_alerts.py) through ntfy.sh. No GitHub access needed.
# Usage (from the repo folder, after git pull):  bash local/install_alerts.sh
# Schedules use the Mac's local time and assume it is set to US Central.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
H="$HOME/.ags-desk"
mkdir -p "$H"
[ -x "$H/venv/bin/python" ] || python3 -m venv "$H/venv"
"$H/venv/bin/pip" install -q --upgrade pip requests pandas curl_cffi pypdf
if [ ! -s "$H/ntfy_topic" ]; then
  echo "bmr-flash-$(openssl rand -hex 12)" > "$H/ntfy_topic"     # private: only phones subscribed to this name get alerts
fi
chmod 600 "$H/ntfy_topic"
TOPIC="$(cat "$H/ntfy_topic")"

mk() {   # label, mode, StartCalendarInterval dicts
  local P="$HOME/Library/LaunchAgents/com.bmrcom.flash.$1.plist"
  cat > "$P" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.bmrcom.flash.$1</string>
  <key>ProgramArguments</key><array><string>$H/venv/bin/python</string><string>$REPO/local/flash_alerts.py</string><string>$2</string></array>
  <key>StartCalendarInterval</key><array>$3</array>
  <key>StandardOutPath</key><string>$H/alerts.out</string>
  <key>StandardErrorPath</key><string>$H/alerts.err</string>
</dict></plist>
PL
  launchctl unload "$P" 2>/dev/null || true
  launchctl load "$P"
}
d() { echo "<dict>$1<key>Hour</key><integer>$2</integer><key>Minute</key><integer>$3</integer></dict>"; }
# export sales: Thursday 7:28 (Friday 7:28 catches holiday weeks)
mk esr esr "$(d '<key>Weekday</key><integer>4</integer>' 7 28)$(d '<key>Weekday</key><integer>5</integer>' 7 28)"
# US macro: every weekday 7:28 (exits at once if the calendar has no tracked 8:30 ET release)
M=""; for w in 1 2 3 4 5; do M="$M$(d "<key>Weekday</key><integer>$w</integer>" 7 28)"; done
mk macro macro "$M"
# WASDE: 10:58 on days 8-14 (exits at once on other days or once the month's report is sent)
W=""; for day in 8 9 10 11 12 13 14; do W="$W$(d "<key>Day</key><integer>$day</integer>" 10 58)"; done
mk wasde wasde "$W"

"$H/venv/bin/python" "$REPO/local/flash_alerts.py" test
cat <<TXT

Installed. On your phone: install the free "ntfy" app, tap +, and subscribe to this topic (keep it private):

    $TOPIC

You should already see a "BMR-Com flash test" alert once subscribed (tap the topic to refresh).
Keep the Mac awake for the 7:30 CT releases (asks for your Mac password once):
    sudo pmset repeat wakeorpoweron MTWRF 07:20:00
Optional, faster CPI/jobs polling: register a free BLS API key (https://data.bls.gov/registrationEngine/) and run
    echo YOUR_KEY > $H/bls_key && chmod 600 $H/bls_key
Try now: $H/venv/bin/python $REPO/local/flash_alerts.py esr --now     (sends the latest export sales)
Log: $H/alerts.log
TXT
