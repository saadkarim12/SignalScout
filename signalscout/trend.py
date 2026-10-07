"""Phase 3b: trend + momentum.

Plain English:
- Market mode: is BTC above its 200-day average? IN = uptrend (ok to hold coins), OUT = stay in cash.
- Strongest coins: among the most-traded coins, rank by price change over ~90 days; only coins above
  their own 200-day average qualify. Hold the top few in equal parts. Re-pick once a week.
- Exit: a coin is sold when its daily close falls below its 200-day average.
Uses closed daily candles only. Decisions use yesterday's data and act a day later (no look-ahead).
"""
import pandas as pd


def build_panel(data: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """data: {symbol: daily df with ts/open/high/low/close/volume} -> (close, dollar volume) tables by date."""
    C, V = {}, {}
    for s, d in data.items():
        idx = pd.to_datetime(d["ts"], unit="ms")
        C[s] = pd.Series(d["close"].to_numpy(), index=idx)
        V[s] = pd.Series((d["close"] * d["volume"]).to_numpy(), index=idx)
    return pd.DataFrame(C).sort_index(), pd.DataFrame(V).sort_index()


def compute(C: pd.DataFrame, V: pd.DataFrame, t: dict, hold_n=None, mom_days=None) -> dict:
    n = hold_n or t["hold_n"]
    m = mom_days or t["momentum_days"]
    sma = C.rolling(t["sma_days"]).mean()
    above = (C > sma) & sma.notna()
    mom = C.pct_change(m, fill_method=None)
    liquid = (C.mul(1).where(V.notna()) * 0 + V).rolling(30, min_periods=20).mean()
    liq_rank = liquid.rank(axis=1, ascending=False)
    eligible = (liq_rank <= t["liquid_top"]) & above & mom.notna()
    rank = mom.where(eligible).rank(axis=1, ascending=False)
    pick = (rank <= n)
    rebalance = pd.Series(C.index.dayofweek == t["rebalance_weekday"], index=C.index)
    chosen = pick.astype(float).where(rebalance, other=float("nan")).ffill().fillna(0) > 0
    held = chosen & above                                   # exit any day price closes under its 200-day
    return dict(above=above, mom=mom, eligible=eligible, pick=pick, held=held, n=n)


def weights(sig: dict) -> pd.DataFrame:
    """Equal parts of 1/N per held coin (rest is cash). Decided on day t close, acted on day t+1, earns from t+2."""
    return (sig["held"].astype(float) / sig["n"]).shift(2).fillna(0)


def market_mode(C: pd.DataFrame, t: dict) -> dict:
    btc = C["BTC/USDT"].dropna()
    s = btc.rolling(t["sma_days"]).mean()
    return dict(mode="IN" if btc.iloc[-1] > s.iloc[-1] else "OUT", price=btc.iloc[-1], sma=s.iloc[-1],
                gap_pct=(btc.iloc[-1] / s.iloc[-1] - 1) * 100)


def live_report(ex, t: dict) -> dict:
    """Needs only Bitcoin's daily candles (closed)."""
    from .data import fetch_ohlcv
    d = fetch_ohlcv(ex, "BTC/USDT", "1d", 300, cache_minutes=30)
    C = pd.DataFrame({"BTC/USDT": d["close"].to_numpy()}, index=pd.to_datetime(d["ts"], unit="ms"))
    return dict(date=C.index[-1], mode=market_mode(C, t))


def format_mode(rep: dict) -> str:
    m = rep["mode"]
    if m["mode"] == "IN":
        head = (f"🟢 Market mode: IN\nBitcoin ${m['price']:,.0f} is {m['gap_pct']:.1f}% ABOVE its 200-day average "
                f"(${m['sma']:,.0f}). The big trend is up.")
        tip = ("What it means: buying is more comfortable. A simple plan is small, equal buys every week "
               "(only money you can afford to lose).")
    else:
        head = (f"🔴 Market mode: OUT\nBitcoin ${m['price']:,.0f} is {abs(m['gap_pct']):.1f}% BELOW its 200-day average "
                f"(${m['sma']:,.0f}). The big trend is down.")
        tip = ("What it means: be careful. In past tests, staying in cash while below this line avoided "
               "most of the big falls. No new buying is the calm choice.")
    return "\n".join([head, "", tip, "", "Chart: https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT", "",
                       "In 3 years of tests this rule cut the worst fall (53% -> 35%) but earned less than just holding "
                       "in a strong rise. It is a safety filter, not a money machine.", "",
                       "Signal, not advice. You decide. Risk max 1%."])
