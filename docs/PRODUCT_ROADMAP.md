# SignalScout — Product Roadmap

**Owner:** Saad · **Developer:** Claude Code · **Coach / PO support:** Claude (Cowork)

## Vision
A calm, easy-to-use assistant that watches the crypto market 24/7 and tells a beginner,
in plain English, **when a high-quality spot setup appears, why, and how much to risk** —
so Saad trades less, trades better, and never risks more than he can afford.

## Product principles
1. **Protect capital first.** Every feature serves the 1% rule and spot-only trading.
2. **Explain, don't command.** Every alert says *why*. The human decides.
3. **Prove before money.** Backtest → paper trade → small real money. Gates are never skipped.
4. **Simple UI.** Telegram is the app. No dashboards needed to use it.
5. **Few, good signals** beat many noisy ones.

## Success metrics
| Metric | Target |
|---|---|
| Backtest expectancy | > +0.15R per trade over ≥ 40 trades (out-of-sample) |
| Paper trading | ≥ 30 trades, positive total R |
| Live (first 3 months) | Max drawdown < 10% of learning budget; rules followed on 100% of trades |
| Usability | Owner can act on an alert in < 2 minutes without opening a chart |

## Phases

| Phase | Goal | Owner (Saad) does | Developer builds | Exit gate |
|---|---|---|---|---|
| **0. Accounts** (week 1) | Safe accounts ready | Follow `ACCOUNT_SETUP.md` | — | Exchange verified + 2FA; Telegram token; Claude Code running |
| **1. Scanner** (weeks 1–2) | Score top 20 coins | Review first scan output with Claude (Cowork) | Data, indicators, 10-point scoring, CLI table | Tests pass; output makes sense to owner |
| **2. Alerts** (week 3) | Get signals on phone | Use `/scan`, `/coin BTC` daily | Telegram bot, charts, 4H scheduler | Alerts arrive, clear and correct |
| **3. Backtest** (weeks 3–4) | Prove the logic | Read report; decide go/no-go | Walk-forward backtester vs buy-and-hold and DCA | **Expectancy > 0.15R, ≥ 40 trades** |
| **4. Paper trade** (weeks 5–8) | Practise with fake money | Log every signal with `/paper`; weekly review | Journal, outcome tracking, weekly report | **≥ 30 trades, total R positive** |
| **5. Go live small** (month 3) | First real trades | Trade manually, $200–500 budget, 1% risk | `/live` log, Streamlit dashboard | 3 months within drawdown limit |
| **6. Cloud & scale** (month 4+) | Always-on, more coins | Approve any automation explicitly | Docker + Azure, health checks; optional one-tap confirmed orders | Owner sign-off |

If a gate fails: stop, review with Claude (Cowork), adjust **one** thing, re-test. Never lower the gate to pass it.

## Backlog (after Phase 5, prioritise later)
- Weekly DCA reminder mode (buy fixed amount every week) as the "core" strategy alongside active signals
- Relative-strength ranking of altcoins vs BTC
- Market regime banner (bull / sideways / bear) at top of each scan
- Automatic economic-calendar feed (replace manual `events.yaml`)
- Multi-language alerts (English / Urdu)
- Price-level alerts ("tell me when BTC touches $X")

## Risks and mitigations
| Risk | Mitigation |
|---|---|
| Strategy stops working (markets change) | Monthly re-backtest; weekly paper/live review |
| Overfitting parameters to history | 70/30 train/test split; change one parameter at a time |
| Emotional overriding of rules | Alert shows size and max loss; journal tracks rule breaks |
| Account hacking / scams | 2FA, whitelist, no API keys until Phase 6, never share codes |
| Exchange data outage | ccxt fallback exchange; bot reports "no data" instead of guessing |
| Treating signals as guarantees | Every alert footer: "Signal, not advice." |

## Ceremonies (lightweight)
- **Daily (5 min):** glance at Telegram alerts.
- **Weekly (Sunday, 20 min):** `/report` review with Claude (Cowork): what worked, what broke a rule.
- **End of each phase:** demo from developer → owner sign-off → next phase.

*Not financial advice. Trading involves risk of loss.*
