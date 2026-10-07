# SignalScout

Scans the top 20 crypto coins and scores each on a 10-point checklist.
It only **reads** public prices. It never trades. You decide every trade.

## Run it (5 steps)
1. Open Terminal in this folder.
2. `make setup`  (one time; installs everything)
3. `make test`   (should say all passed)
4. `make scan`   (prints the table, ~20-60 seconds)
5. Read the table: STRONG = best, WATCH = decent, SKIP = weak, NO_TRADE = a must-have rule failed.

6. Prefer a web page? `make web`, then open http://127.0.0.1:8501 (Ctrl+C to stop).

Settings live in `config.yaml`. Add big news dates to `events.yaml`.

*Signal, not advice. You decide. Risk max 1%.*

## Phase 2: Telegram
1. Follow `docs/ACCOUNT_SETUP.md` section C to get your bot token and chat ID.
2. Copy `.env.example` to `.env` and paste the two values in.
3. Preview first (sends nothing): open the web page, tab "Alert preview".
4. `make bot` - then send /start to your bot in Telegram.

## Slack reminders (works without Telegram)
1. Create an Incoming Webhook in Slack (api.slack.com/apps -> Create New App -> From scratch -> Incoming Webhooks -> Add New Webhook to Workspace).
2. Paste the URL into `.env` after `SLACK_WEBHOOK_URL=`.
3. `make slack-test` (you should get a message), then `make reminders` and leave it running.


## For testers
See `docs/QA_GUIDE.md` for setup and a step-by-step test table. Automatic tests: `make test`.
