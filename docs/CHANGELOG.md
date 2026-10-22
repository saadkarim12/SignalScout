# Changelog
## Phase 1 — Scanner (CLI)
- Data (ccxt, closed candles only, cached), top-20 universe, indicators (SMA/EMA/RSI/ATR/pivots/divergence), support levels, 10-point scoring, position sizing, `make scan`.
- Local test web page (`make web`, http://127.0.0.1:8501): scan table, per-coin checklist, run tests.
## Phase 2 — Telegram alerts + bot
- Alert text + chart picture, bot commands (/start /scan /coin /fear /paper /journal /report /settings /setaccount /help), only answers the owner chat ID.
- 4-hour scheduler (5 min after candle close, UTC), no repeat alert for the same coin within 24h.
- Web page "Alert preview" shows the message without sending it. `make alert-preview`, `make bot`.
## Phase 3 — Backtest
- Walk-forward replay of 3 years of 4H data, 12 coins, next-bar-open entry, stop-first on ties, 0.1% fee + 0.05% slippage per side, real Fear & Greed history, 70/30 train/test split. Report + chart in `reports/`, web page "Backtest" tab.
- Result 2026-10-02: **FAIL** (expectancy about -0.12R). No rules changed.
- Option A (target capped at 2R) tested: expectancy -0.17R, still FAIL. Switched off (`target_cap_rr: null`). Reports in `reports/history/`.
## Phase 3b — Trend and market mode
- Tested trend + momentum on daily candles with a rule set fixed beforehand: **FAIL** (the earlier +806% was survivorship bias; with at-the-time liquidity it lost 30% in the test period). Report: `reports/trend_*.md`.
- Kept only the simple safety filter: Market mode IN/OUT (BTC vs its 200-day average). Cut worst drop 53% -> 35% over 3 years, +16% in the test period vs -18% for holding.
- `/mode` Telegram command, daily check (00:10 UTC) that messages only when the mode flips, web tab "Market mode".
## Phase 4 — Weekly buy reminder (new)
- Weekly buy diary (pretend), both plans tracked: plain (buy every week) and cautious (skip when Market mode is OUT).
- 3-year history check: plain weekly buying ended richer than skipping OUT weeks, so the filter is information, not a rule.
- Telegram: weekly reminder (Sunday 08:00 UTC), `/weekly`, `/setweekly 50`. Web tab "Weekly buys" with a "Log this week now" button.
- Phase 4 signed off by owner. Weekly amount set to $100. Slack reminders added (`make slack-test`, `make reminders`); Telegram stays optional.
- Price alerts: "tell me when BTC reaches $X" (web tab "Price alerts", Telegram `/alert BTC 90000`, `/alerts`, `/delalert`). One message per alert, checked every 5 minutes. TradingView links added to messages and coin pages.
- Tutorial: docs/TUTORIAL.md, also the 'Tutorial' tab on the web page.
- Background service (./service.sh install|status|restart|uninstall): web page + reminders start at login, restart on crash, keep the Mac from idle-sleeping.
- Practice track: pretend trades from signals with automatic stop/target tracking (15-minute candles, stop first on ties, costs included), 20-trade goal with PASS / NOT PROVEN result, web tab 'Practice trades', /paper /journal /report updated, 4-hour signal alerts now also go to Slack as text.
- Real news: Fed calendar + FRED release dates (needs free key) + CoinDesk/Cointelegraph/The Block headlines replace the empty events.yaml check; News tab; coin pages show headlines. Risk words are kept strict to avoid false alarms.
- News: Binance official announcements added (delisting notices count 7 days). News dashboard per coin + general news. Score lines are clickable with the numbers behind them.
- Trend portfolio strategy (BTC+ETH, 4-rule vote) from 9-year research; daily job messages only when exposure changes; Trend portfolio tab with live forward test; old checklist marked paused. docs/STRATEGY.md.
