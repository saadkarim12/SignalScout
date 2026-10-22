"""Trend portfolio: the strategy that held up in 9 years of tests (BTC + ETH, daily candles, long-only spot).

Plain English:
- For each coin, 4 simple trend rules vote every day, using the CLOSE of the last finished daily candle:
    1. price above its 50-day average        2. price above its 200-day average
    3. in a 55-day breakout (entered when the close beats the last 55 days' high, left when it falls under the last 20 days' low)
    4. in a 100-day breakout (same idea with 100 and 50 days)
- Exposure = share of rules that say "in": 0%, 25%, 50%, 75% or 100% of that coin's slice. The rest stays cash.
- Each coin gets an equal slice of your money. You check once a day; changes are rare (a few per year).
Decisions use yesterday's close and are traded at the next open (no look-ahead). Fees and slippage are counted in tests.
"""
import numpy as np
import pandas as pd

from .research import sig_sma, sig_donchian, run, stats, SPLIT

RULES = ["Above 50-day average", "Above 200-day average", "In 55-day breakout", "In 100-day breakout"]


def rule_signals(d: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({RULES[0]: sig_sma(d, 50), RULES[1]: sig_sma(d, 200),
                         RULES[2]: sig_donchian(d, 55, 20), RULES[3]: sig_donchian(d, 100, 50)})


def ensemble(d: pd.DataFrame) -> pd.Series:
    return rule_signals(d).mean(axis=1)


def status(d: pd.DataFrame) -> dict:
    """Latest vote for one coin from its closed daily candles, with the numbers behind each rule."""
    sig = rule_signals(d)
    last, prev = sig.iloc[-1], sig.iloc[-2]
    c = d["close"]
    s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
    lo20, lo50 = c.rolling(20).min().iloc[-1], c.rolling(50).min().iloc[-1]
    hi55, hi100 = c.shift(1).rolling(55).max().iloc[-1], c.shift(1).rolling(100).max().iloc[-1]
    price = float(c.iloc[-1])
    details = {
        RULES[0]: f"close {price:,.6g} vs 50-day average {s50:,.6g}",
        RULES[1]: f"close {price:,.6g} vs 200-day average {s200:,.6g}",
        RULES[2]: f"enters above the previous 55-day high {hi55:,.6g}; leaves below the 20-day low {lo20:,.6g}",
        RULES[3]: f"enters above the previous 100-day high {hi100:,.6g}; leaves below the 50-day low {lo50:,.6g}",
    }
    return dict(date=d.index[-1], price=price, exposure=float(last.mean()), prev_exposure=float(prev.mean()),
                votes={r: bool(last[r]) for r in RULES}, details=details)


def live_status(data: dict) -> dict:
    return {s: status(d) for s, d in data.items()}


def action_text(exposure: float, prev: float) -> str:
    if exposure > prev:
        return f"More rules say IN, exposure goes from {prev * 100:.0f}% up to {exposure * 100:.0f}%."
    if exposure < prev:
        return f"Fewer rules say IN, exposure goes from {prev * 100:.0f}% down to {exposure * 100:.0f}%."
    return f"No change, exposure stays at {exposure * 100:.0f}%."


def format_change(sym: str, st: dict, slice_usd: float) -> str:
    base = sym.split("/")[0]
    yes = [r for r, v in st["votes"].items() if v]
    no = [r for r, v in st["votes"].items() if not v]
    target = slice_usd * st["exposure"]
    return (f"📈 Trend portfolio: {base} changed\\n{action_text(st['exposure'], st['prev_exposure'])}\\n"
            f"Rules saying IN: {', '.join(yes) or 'none'}.\\nRules saying OUT: {', '.join(no) or 'none'}.\\n"
            f"With your plan, about ${target:,.0f} of {base}'s ${slice_usd:,.0f} slice should be invested; the rest stays cash.\\n"
            f"Decide and place any real trade yourself. Practice first.\\n\\nSignal, not advice. You decide. Risk max 1%.")


def paper_curve(data: dict, start) -> tuple[pd.Series, pd.Series]:
    """Equity of the strategy and of buy-and-hold since `start` (equal slices, strategy vs hold)."""
    s_r, h_r = {}, {}
    for sym, d in data.items():
        eq, _ = run(d, ensemble(d))
        s_r[sym] = eq.pct_change().fillna(0)
        h, _ = run(d, pd.Series(1.0, index=d.index))
        h_r[sym] = h.pct_change().fillna(0)
    sr, hr = pd.DataFrame(s_r).mean(axis=1), pd.DataFrame(h_r).mean(axis=1)
    sr, hr = sr[sr.index >= pd.Timestamp(start)], hr[hr.index >= pd.Timestamp(start)]
    return (1 + sr).cumprod(), (1 + hr).cumprod()


def backtest_summary(data: dict) -> dict:
    """In-sample (before 2022) and out-of-sample (2022 on) for the equal-slice portfolio, strategy vs hold."""
    s_r, h_r = {}, {}
    for sym, d in data.items():
        eq, _ = run(d, ensemble(d))
        h, _ = run(d, pd.Series(1.0, index=d.index))
        s_r[sym], h_r[sym] = eq.pct_change().fillna(0), h.pct_change().fillna(0)
    start = max(d.index[0] for d in data.values())
    sr = pd.DataFrame(s_r).mean(axis=1)
    hr = pd.DataFrame(h_r).mean(axis=1)
    sr, hr = sr[sr.index >= start], hr[hr.index >= start]
    se, he = (1 + sr).cumprod(), (1 + hr).cumprod()
    years = {}
    for y in sorted({i.year for i in se.index}):
        def yr(e):
            cur = e[e.index.year == y]
            prev = e[e.index < cur.index[0]]
            return float(cur.iloc[-1] / (prev.iloc[-1] if len(prev) else 1) - 1)
        years[y] = (yr(se), yr(he))
    return dict(strategy_is=stats(se, None, None, SPLIT), strategy_oos=stats(se, None, SPLIT, None),
                hold_is=stats(he, None, None, SPLIT), hold_oos=stats(he, None, SPLIT, None), years=years, se=se, he=he)
