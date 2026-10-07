# SignalScout — Developer Spec (read this first)

You are the **developer**. Saad is the **product owner** and a beginner trader.
Build an easy-to-use crypto **spot** signal scanner that scores coins against a
10-point checklist and alerts Saad on Telegram. Saad decides and places every
trade himself on his exchange.

Product roadmap and phase gates: `docs/PRODUCT_ROADMAP.md`
Account setup (owner tasks): `docs/ACCOUNT_SETUP.md`

---

## 1. Non-negotiable guardrails

1. **No order placement** in phases 1–5. The app reads public market data only.
   Never ask for, store, or use exchange API keys until Phase 6 is explicitly approved.
2. **Spot only.** Never add leverage, margin, futures, or shorting logic.
3. **Secrets** (Telegram token, chat ID) live in `.env` only. `.env` is in `.gitignore`.
   Commit a `.env.example` with placeholder values.
4. **No look-ahead bias.** Signals use **closed candles only**. The backtester must
   only see data up to the bar being evaluated.
5. **Every alert ends with**: "Signal, not advice. You decide. Risk max 1%."
6. **Plain English** in all user-facing text. Saad is a beginner. No jargon without a
   short explanation.
7. Respect exchange rate limits (ccxt `enableRateLimit=True`). Cache OHLCV locally.
8. Do not scrape TradingView (violates its ToS). Market data comes from exchange APIs via `ccxt`.

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Market data | `ccxt` — primary `binance` public API, fallback `okx` (config) |
| Data handling | `pandas`, `numpy` |
| Indicators | Own module `indicators.py` (SMA, EMA, RSI(14) Wilder, ATR(14), swing pivots). Unit-tested. Do not depend on unmaintained TA libraries. |
| Sentiment | Fear & Greed Index: `https://api.alternative.me/fng/` (free, no key) |
| Alerts / UI | `python-telegram-bot` (v21+, async) |
| Charts in alerts | `mplfinance` → PNG attached to Telegram message |
| Scheduling | `APScheduler` (every 4h, 5 minutes after candle close UTC) |
| Storage | SQLite via `sqlite3` or `SQLModel` (`data/signalscout.db`) |
| Dashboard (Phase 5) | `streamlit` + `plotly` |
| Config | `config.yaml` + `.env` (`python-dotenv`) |
| Tests | `pytest` |
| Packaging | `uv` or `pip` + `requirements.txt`; `Makefile` with `setup`, `scan`, `bot`, `backtest`, `test` |
| Deploy (Phase 6) | Docker → Azure Container Apps (or a small VM). |

## 3. Folder structure

```
SignalScout/
├── CLAUDE.md
├── README.md                 # 5-step "how to run" for a beginner
├── .env.example
├── config.yaml
├── requirements.txt
├── Makefile
├── docs/
│   ├── PRODUCT_ROADMAP.md
│   └── ACCOUNT_SETUP.md
├── signalscout/
│   ├── data.py               # fetch + cache OHLCV (ccxt)
│   ├── universe.py           # pick top-N coins by volume
│   ├── indicators.py         # SMA, RSI, ATR, pivots, divergence
│   ├── levels.py             # support/resistance, round numbers
│   ├── scoring.py            # the 10-point checklist → ScoreResult
│   ├── sizing.py             # position size from 1% rule
│   ├── sentiment.py          # Fear & Greed
│   ├── events.py             # reads events.yaml (CPI/FOMC dates)
│   ├── charts.py             # PNG chart with entry/stop/target lines
│   ├── alerts.py             # Telegram formatting + sending
│   ├── bot.py                # Telegram commands
│   ├── scheduler.py          # 4h scan loop
│   ├── backtest.py           # walk-forward simulation
│   ├── journal.py            # paper/live trade log (SQLite)
│   └── dashboard.py          # Streamlit (Phase 5)
├── data/                     # cache + db (gitignored)
├── events.yaml               # manually maintained high-impact news dates
└── tests/
```

## 4. Universe and timeframes

- **Universe**: top 20 USDT spot pairs by 24h quote volume on the data exchange.
  Exclude stablecoins (USDC, FDUSD, DAI, TUSD, USDE, etc.), leveraged tokens (UP/DOWN/BULL/BEAR)
  and wrapped duplicates. BTC/USDT always included and always listed first.
- **Trend timeframe**: 1D. **Setup timeframe**: 4H.
- Fetch at least 300 daily and 500 4H candles per symbol.

## 5. The 10-point checklist (core logic)

Compute on the **last closed** 4H candle. Weights in brackets. Items marked MUST
are required; if any MUST fails, verdict = `NO_TRADE` regardless of score.

| # | Check | Rule | Pts |
|---|---|---|---|
| 1 | Trend (MUST) | Last daily close > SMA200 (daily) | 2 |
| 2 | Golden-cross zone | SMA50 (daily) > SMA200 (daily) | 1 |
| 3 | Location: at support | 4H low of last 3 candles within 1.5% of a support level (see §6) | 2 |
| 4 | Momentum cooled | RSI14 (4H) touched 38–52 in last 5 candles **OR** hidden bullish divergence (§7) | 1 |
| 5 | Bounce confirmation | Last 4H candle: close > open AND close in top 40% of its range AND volume > 1.2 × SMA20(volume) | 1 |
| 6 | Sentiment | Fear & Greed value < 35 | 1 |
| 7 | News-clear | No `events.yaml` entry within next 24h | 1 |
| 8 | Reward:Risk (MUST) | R:R ≥ 2.0 using §8 | 1 |
|   | **Total** | | **10** |

Verdicts:
- `STRONG` score ≥ 8 → alert, risk 1% of account
- `WATCH` score 6–7 → alert (lower priority), risk 0.5%
- `SKIP` score < 6 → no alert (visible in `/scan` only)
- `NO_TRADE` any MUST failed

Tie-breaker ranking (same score): higher R:R, then relative strength vs BTC over 30 days (alts only).

Make all thresholds configurable in `config.yaml`.

## 6. Support levels (`levels.py`)

A support level is any of:
1. **Daily SMA50** value.
2. **Broken swing high**: a 4H pivot high (5 bars left/right) from the last 120 bars
   that price has since closed above.
3. **Round number** below price: BTC multiples of 5,000; ETH multiples of 250;
   others: nearest "nice" number at 2 significant digits.
Return the nearest support below the current close.

## 7. Hidden bullish divergence (`indicators.py`)

Within last 60 4H bars, find the two most recent pivot lows (3 bars left/right) A and B (B later):
`price_low[B] > price_low[A]` AND `rsi[B] < rsi[A]` AND B within the last 8 bars → True.

## 8. Entry, stop, target, R:R

- `entry` = last close
- `stop` = support − 0.5 × ATR14(4H)
- `target` = most recent 4H swing high above entry (lookback 120 bars); if none, entry + 3 × ATR14(daily)
- `rr` = (target − entry) / (entry − stop)

## 9. Position sizing (`sizing.py`)

`account_size` from config (USD). `risk_pct` = 1% (STRONG) or 0.5% (WATCH).
`position_usd = account_size × risk_pct / ((entry − stop)/entry)`, capped at 25% of account.
Show: coins to buy, USD amount, max loss in USD.

## 10. Telegram alert format

```
🟢 STRONG setup — BTC/USDT (score 8/10)
Entry  ~ $62,150
Stop     $60,400  (−2.8%)
Target   $66,300  (+6.7%)   R:R 2.4
Size     $357 → max loss $10 (1% of $1,000)

Why:
✅ Above 200-day average (uptrend)
✅ Pulled back to support $60,000 (round number)
✅ RSI cooled to 44
✅ Green bounce candle, volume 1.6× normal
❌ Fear & Greed 58 (neutral) — not fearful
✅ No big news next 24h

Signal, not advice. You decide. Risk max 1%.
```
Attach a chart PNG (4H, last 120 candles, SMA50/200, entry/stop/target lines).
Emojis are allowed in Telegram messages only.

## 11. Telegram commands (`bot.py`)

| Command | Action |
|---|---|
| `/start` | Welcome + short how-to |
| `/scan` | Run scan now; list top 10 with score and verdict |
| `/coin BTC` | Full checklist breakdown for one coin with chart |
| `/fear` | Current Fear & Greed |
| `/paper BTC` | Log a paper trade from the latest signal |
| `/journal` | Open paper/live trades and results |
| `/report` | Weekly stats: win rate, avg R, total R |
| `/settings` | Show account size and risk; `/setaccount 1000` to change |
| `/help` | Command list in plain English |

Only respond to the chat ID in `.env` (single-user bot).

## 12. Backtester (`backtest.py`)

- Walk forward bar-by-bar over 2–3 years of 4H data for BTC, ETH + top 10.
- Trigger on STRONG (and separately WATCH). Enter at next bar open.
- Exit on stop or target (if both touched in same bar, assume **stop** — conservative).
- Include fees 0.1% per side and 0.05% slippage.
- Ignore sentiment/news checks in backtest unless historical F&G is fetched
  (the API supports `?limit=0` for full history — use it).
- Output `reports/backtest_<date>.md` + equity-curve PNG: number of trades,
  win rate, average R, expectancy (R per trade), max drawdown, profit factor,
  and comparison against **buy-and-hold BTC** and **weekly DCA**.
- Gate for Phase 4: expectancy > 0.15R and ≥ 40 trades. Report PASS/FAIL clearly.

## 13. Phase plan (build in this order; stop at each gate for owner sign-off)

**Phase 1 — Scanner (CLI)**
- `make scan` prints a table: coin, score, verdict, entry, stop, target, R:R.
- Acceptance: runs in < 60s for 20 coins; tests for indicators pass (RSI/SMA/ATR vs known values).

**Phase 2 — Telegram alerts + bot**
- Scheduler every 4H; alert only on new STRONG/WATCH (no duplicate alerts for the same setup within 24h).
- Acceptance: owner receives a formatted alert with chart; all commands work.

**Phase 3 — Backtest**
- Acceptance: report generated with PASS/FAIL gate. If FAIL, propose (don't silently apply)
  parameter changes, and warn about overfitting; use a train/test split (first 70% / last 30%).

**Phase 4 — Paper trading and journal**
- `/paper` logging, automatic outcome tracking against live prices, weekly `/report` push on Sundays.
- Gate for Phase 5: ≥ 30 paper trades, positive total R.

**Phase 5 — Go live (manual) + dashboard**
- `/live` logging for real trades placed manually by owner. Streamlit dashboard:
  current scan, open trades, equity curve, win rate.

**Phase 6 — Cloud and scale (owner approval required)**
- Dockerfile, deploy to Azure Container Apps with secrets in Key Vault; health-check ping to Telegram daily.
- Optional later: exchange API keys with **trade-only, no-withdrawal, IP-whitelisted** permissions,
  one-tap "confirm order" button, hard daily loss cap. Never fully automatic without explicit sign-off.

## 14. Definition of done (every phase)

- `pytest` green; new logic has tests.
- README updated with beginner-level run steps.
- Short changelog entry in `docs/CHANGELOG.md`.
- Demo message/screenshot shown to owner before moving to next phase.

## 15. How to work with the owner

- Explain what you built in 3–5 plain-English bullets.
- Ask before adding dependencies beyond §2 or changing checklist rules.
- When a phase gate fails, say so plainly. Do not move the goalposts.
