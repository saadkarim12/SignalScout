# Strategy: Trend portfolio (BTC + ETH)

## Why this strategy
The original 10-point dip-buying checklist failed: -0.10R per trade in a 3-year backtest, barely better than random entries
(95th percentile of random runs but still negative after costs), and 0 wins in the first 9 live practice trades.
So we researched long-only, spot, daily-candle strategies on 9 years of real Binance data (2017-2026), including the 2018 and 2022 crashes.

## Method (fixed before looking at results)
- Costs: 0.1% fee + 0.05% slippage per side. Signal decided on the close of day t-1, traded at the open of day t (no look-ahead).
- Training period 2017-2021, held-out test 2022-today.
- Pass rules: better return-per-worst-drop than buy-and-hold on at least 3 of 5 coins, worst drop at least 30% smaller, nearby settings also work, profitable after fees.
- Eight strategy families tested on BTC, ETH, BNB, XRP, ADA.

## What passed
Trend-following (hold a coin only while its trend is up). A vote of four rules per coin: above 50-day average, above 200-day average,
in a 55-day breakout (exit under the 20-day low), in a 100-day breakout (exit under the 50-day low). Exposure = share of rules saying IN.

BTC + ETH, equal slices:

| Period | Strategy return | Strategy worst drop | Buy and hold return | Buy and hold worst drop |
|---|---|---|---|---|
| 2017-2021 (training) | +1,309% | -43% | +1,342% | -88% |
| 2022-today (held out) | +134% | -25% | +17% | -68% |

Four different rule combinations gave a held-out return of +73% to +164% and a worst drop of -25% to -31%.

## What did not work
- Buying pullbacks (daily version of the checklist): -9% held-out return.
- XRP and ADA with the same rules: poor. BNB is mixed.
- Short-term (4-hour) dip signals: negative after costs.

## Honest limits
- Still loses in bad years (about -20% in 2018 and 2022). It roughly halves crashes; it does not avoid them.
- In strong bull years it earns less than holding (2020: +175% vs +396%).
- BTC and ETH are survivors that rose a lot. The future may differ.
- The four-rule vote was chosen after seeing single-rule results, so the held-out test is slightly contaminated. The forward paper test (from 2026-10-11, Trend portfolio page) is the clean test.
- Taxes, exchange problems and behaviour are not modelled.

## How to use it
Open the Trend portfolio tab once a day. A Slack message arrives only when a coin's exposure changes. Practice with pretend money first.
Reproduce the research: `python -m signalscout.research`.

## Independent audit (2026-10-22)
A separate reviewer re-implemented the four rules from the written description, without copying the code, and checked the code.
- **Numbers reproduced.** 2017-2021: +1309% / worst drop -43%. Held-out 2022-today: +132% to +135% / -25%. Buy and hold: +1346% / -88% and +18% / -68%.
- **No look-ahead or arithmetic bug found.** The signal is lagged one day. Same-day use of the signal would have shown a fake +13,376%, which the code does not do.
- **Stress tests (held-out return / worst drop):** costs doubled to 0.3% per side +118% / -26%; one extra day of delay +85% / -28%; BTC alone +133% / -26%; ETH alone +117% / -30%.
- **Sensitive to where the test period starts:** held-out from 2021 +449% / -37%, from 2023 +185% / -25%. The true edge is uncertain.
- **It does NOT beat buy and hold in raw return** in 2017-2021 (+1309% vs +1346%). It wins by cutting the crashes in half. After 2022 it won mostly because the market fell.

### Honest expectations
- About **15% to 30% a year** over the long run, with worst drops of **25% to 45%** (possibly worse). The full-period 46% a year was flattered by 2020-2021.
- **21% of all 12-month windows lost money.** The worst 12 months were -39%. The longest time under water was about **25 months**.
- Not modelled: taxes, exchange problems, free daily rebalancing between the two coins, and the delay of a human checking once a day.
- **No spot strategy can promise a daily profit.** Returns come in lumps. $100 a day is about $36,500 a year, which needs roughly $120,000 at 30% a year, $180,000 at 20%, or $240,000 at 15%.
