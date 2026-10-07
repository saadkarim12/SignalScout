# SignalScout - QA guide

SignalScout reads public crypto prices and news, scores coins on a 10-point checklist, and tracks PRETEND trades.
It never places orders and never asks for exchange keys. No real money is involved.

## 1. Set up (10 minutes)
Needs Python 3.11 or newer and internet access.

```bash
git clone <repo-url> && cd SignalScout
make setup            # creates .venv and installs requirements
make test             # 90+ automatic tests, all must pass
make web              # starts the page at http://127.0.0.1:8501 (Ctrl+C to stop)
```
Optional (the app works without them): copy `.env.example` to `.env` and add a Slack webhook, a Telegram bot token, and a free FRED API key
(https://fred.stlouisfed.org, My Account > API Keys). Never commit `.env`.

If your network blocks Binance, set `data_exchange: okx` in `config.yaml`.

## 2. What to test (open http://127.0.0.1:8501)

| # | Area | Steps | Expected |
|---|---|---|---|
| 1 | Market check | Home page, click **Check the market now** | Table of ~30 coins in under a minute, colour coded (STRONG green, WATCH yellow, SKIP grey, NO_TRADE red) |
| 2 | Score breakdown | Click a coin name, then click each line under **Why this score?** | Each line opens real numbers (prices, averages, RSI, volume). Points add up to the score. A grey line says whether hidden bullish divergence was seen (no points) |
| 3 | Score link | Click a score such as 8/10 | Opens that coin's page at the "Why this score?" section |
| 4 | Verdict rules | Find a NO_TRADE coin | One of the two must-haves failed (uptrend, or reward vs risk below 2) |
| 5 | Advisor view | Open a STRONG or WATCH coin | Box says BUY or WAIT with reasons. Marked "for your reference only" |
| 6 | News | **News** tab, click a coin | Sources listed, news score 0 or 1 with the reason, headlines with working links. Sources that failed are named, not hidden |
| 7 | Practice trades | **Practice trades** tab, click **Log pretend buy** on a signal | Green message, trade appears under "Your open pretend trades" with buy, stop, target |
| 8 | Duplicate protection | Click **Log pretend buy** on the same coin again | Refused: you already have an open trade on that coin |
| 9 | Stale signal protection | Try a coin whose price already passed its stop or whose reward vs risk fell below 2 | Refused with a plain explanation |
| 10 | Price alerts | **Price alerts** tab, add BTC at a far price, then remove it | Appears in Active, then disappears. Bad input (negative, text, unknown coin) shows a clear message |
| 11 | Weekly buys | **Weekly buys** tab | History table and diary render. Amount matches **Settings** |
| 12 | Settings | **Settings** tab, change account size, save | Saved message. Letters or negative numbers rejected |
| 13 | Market mode | **Market mode** tab | IN or OUT with Bitcoin versus its 200-day average |
| 14 | Safety check | **Safety check** tab | "Everything is working correctly" |
| 15 | Language | Read every page | Plain English, no unexplained jargon. Footer text "Signal, not advice. You decide. Risk max 1%." on alerts |

## 3. Things that must never happen
- Any button that buys or sells for real, or asks for exchange keys or passwords.
- Leverage, margin, futures or shorting anywhere.
- A secret (token, webhook, key) shown on a page or written to a log.
- A signal built from a candle that has not closed yet.

## 4. Known limits (not bugs)
- Checklist rules lost money in the 3-year backtest. This is why the app is practice-only. Run `make backtest` and open the **Backtest** tab (reports are not stored in the repo).
- News risk words are a simple keyword match.
- Telegram may be unreliable on some networks. Slack and the web page are the main channels.
- Backtests use a coin list picked by today's volume (survivorship bias).

## 5. Reporting a bug
Please include: page and step, what you expected, what happened, a screenshot, and the time (UTC). Do not paste tokens or `.env` contents.
