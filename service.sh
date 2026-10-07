#!/bin/zsh
# SignalScout background service: ./service.sh install | uninstall | status | restart
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$DIR/.venv/bin/python"
AGENTS="$HOME/Library/LaunchAgents"
UID_=$(id -u)

plist() {  # name, extra command words
  cat > "$AGENTS/com.signalscout.$1.plist" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.signalscout.$1</string>
<key>ProgramArguments</key><array>$2</array>
<key>WorkingDirectory</key><string>$DIR</string>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
<key>ThrottleInterval</key><integer>30</integer>
<key>EnvironmentVariables</key><dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
<key>StandardOutPath</key><string>$DIR/data/$1-service.log</string>
<key>StandardErrorPath</key><string>$DIR/data/$1-service.log</string>
</dict></plist>
P
}

case "$1" in
  install)
    mkdir -p "$AGENTS" "$DIR/data"
    pkill -f "signalscout.web" 2>/dev/null; pkill -f "signalscout.reminders" 2>/dev/null
    plist web "<string>/usr/bin/caffeinate</string><string>-i</string><string>$PY</string><string>-m</string><string>signalscout.web</string>"
    plist reminders "<string>/usr/bin/caffeinate</string><string>-i</string><string>$PY</string><string>-m</string><string>signalscout.reminders</string>"
    for n in web reminders; do
      launchctl bootout gui/$UID_ "$AGENTS/com.signalscout.$n.plist" 2>/dev/null
      launchctl bootstrap gui/$UID_ "$AGENTS/com.signalscout.$n.plist"
    done
    echo "Installed. SignalScout now runs in the background and starts when you log in." ;;
  uninstall)
    for n in web reminders; do
      launchctl bootout gui/$UID_ "$AGENTS/com.signalscout.$n.plist" 2>/dev/null
      rm -f "$AGENTS/com.signalscout.$n.plist"
    done
    echo "Removed. SignalScout no longer runs by itself." ;;
  restart)
    for n in web reminders; do launchctl kickstart -k gui/$UID_/com.signalscout.$n; done ;;
  status)
    for n in web reminders; do
      if launchctl print gui/$UID_/com.signalscout.$n 2>/dev/null | grep -q "state = running"; then echo "$n: RUNNING"; else echo "$n: NOT running"; fi
    done
    curl -s -m 5 -o /dev/null -w "web page: %{http_code}\n" http://127.0.0.1:8501/ ;;
  *) echo "Use: ./service.sh install | uninstall | status | restart" ;;
esac
