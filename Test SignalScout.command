#!/bin/zsh
# Double-click to test each phase. Add new phases to the menu as they are built.
cd "$(dirname "$(readlink -f "$0" 2>/dev/null || echo "$0")")" || exit 1
[ -d .venv ] || make setup
while true; do
  echo ""
  echo "===== SignalScout - test menu ====="
  echo "1) Phase 1: run automatic tests (QA)"
  echo "2) Phase 1: run the scanner (live coin table)"
  echo "3) Open the web page (http://127.0.0.1:8501)"
  echo "4) Phase 2: start the Telegram bot (needs .env with your token)"
  echo "5) Phase 3: run the backtest (1-2 minutes)"
  echo "6) Phase 3b: trend backtest (about 1 minute)"
  echo "7) Phase 4: weekly buy test (see the Weekly buys tab on the web page)"
  echo "8) Slack: send a test message"
  echo "9) Slack: start weekly reminders (leave window open)"
  echo "s) Is SignalScout running in the background? (status)"
  echo "r) Restart the background programs"
  echo "q) Quit"
  read "c?Choose: " || exit 0
  case $c in
    1) make test ;;
    2) make scan ;;
    3) (sleep 1; open http://127.0.0.1:8501) & make web ;;
    4) make bot ;;
    5) make backtest ;;
    6) make trend-backtest ;;
    7) (sleep 1; open http://127.0.0.1:8501/weekly) & make web ;;
    8) make slack-test ;;
    9) make reminders ;;
    s) ./service.sh status ;;
    r) ./service.sh restart ;;
    q) exit 0 ;;
  esac
done
