"""Strategy research on long daily history (long-only spot, fees included, no look-ahead).
Signal is decided on the CLOSE of day t-1 and traded at the OPEN of day t."""
import numpy as np
import pandas as pd
from .config import load_config
from .data import make_exchange, fetch_history

COST = 0.0015            # 0.1% fee + 0.05% slippage per side
COINS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]
SPLIT = pd.Timestamp("2022-01-01")


def load(years=9.5):
    ex = make_exchange(load_config()["data_exchange"])
    out = {}
    for s in COINS:
        d = fetch_history(ex, s, "1d", years)
        d.index = pd.to_datetime(d["ts"], unit="ms")
        out[s] = d[["open", "high", "low", "close", "volume"]]
    return out


# ---- signals: return a 0/1 (or 0..1) series decided at each day's close ----
def sig_buyhold(d):
    return pd.Series(1.0, index=d.index)


def sig_sma(d, n):
    return (d["close"] > d["close"].rolling(n).mean()).astype(float)


def sig_donchian(d, n_in, n_out):
    c = d["close"].to_numpy()
    hi = d["close"].shift(1).rolling(n_in).max().to_numpy()
    lo = d["close"].shift(1).rolling(n_out).min().to_numpy()
    pos, out = 0.0, np.zeros(len(c))
    for i in range(len(c)):
        if pos == 0 and c[i] > hi[i]:
            pos = 1.0
        elif pos == 1 and c[i] < lo[i]:
            pos = 0.0
        out[i] = pos
    return pd.Series(out, index=d.index)


def sig_mom(d, m, n_sma=200):
    return ((d["close"] / d["close"].shift(m) - 1 > 0) & (d["close"] > d["close"].rolling(n_sma).mean())).astype(float)


def sig_dip_in_trend(d, n_sma=200, rsi_n=14, rsi_lo=40):
    """What SignalScout does in spirit: buy a pullback inside an uptrend, exit when trend breaks (daily version)."""
    c = d["close"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / rsi_n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_n, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn)
    trend = c > c.rolling(n_sma).mean()
    pos, out = 0.0, np.zeros(len(c))
    for i in range(len(c)):
        if pos == 0 and trend.iloc[i] and rsi.iloc[i] < rsi_lo:
            pos = 1.0
        elif pos == 1 and (not trend.iloc[i] or rsi.iloc[i] > 65):
            pos = 0.0
        out[i] = pos
    return pd.Series(out, index=d.index)


def run(d, sig):
    """Equity curve of a signal. pos[t] = sig[t-1] (decided at yesterday's close, traded at today's open)."""
    pos = sig.shift(1).fillna(0.0)
    prev = pos.shift(1).fillna(0.0)
    o, c = d["open"], d["close"]
    ret = prev * (o / c.shift(1) - 1) + pos * (c / o - 1) - (pos - prev).abs() * COST
    return (1 + ret.fillna(0)).cumprod(), pos


def stats(eq, pos=None, start=None, end=None):
    e = eq[(eq.index >= (start or eq.index[0])) & (eq.index < (end or eq.index[-1] + pd.Timedelta(days=1)))]
    if len(e) < 3:                      # not enough days in this window
        return dict(ret=0.0, cagr=0.0, dd=0.0, sharpe=0.0, calmar=0.0, time_in=0.0, trades=0)
    e = e / e.iloc[0]
    r = e.pct_change().dropna()
    yrs = max(len(e) / 365, 1e-9)
    dd = float((e / e.cummax() - 1).min())
    cagr = float(e.iloc[-1] ** (1 / yrs) - 1)
    sharpe = float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0
    out = dict(ret=float(e.iloc[-1] - 1), cagr=cagr, dd=dd, sharpe=sharpe, calmar=float(cagr / abs(dd)) if dd < 0 else 0.0)
    if pos is not None:
        p = pos[(pos.index >= e.index[0]) & (pos.index <= e.index[-1])]
        out["time_in"] = float(p.mean())
        out["trades"] = int((p.diff().abs() > 0).sum() / 2)
    return out


STRATS = {
    "Buy and hold": lambda d: sig_buyhold(d),
    "Above 200-day avg": lambda d: sig_sma(d, 200),
    "Above 100-day avg": lambda d: sig_sma(d, 100),
    "Above 50-day avg": lambda d: sig_sma(d, 50),
    "Breakout 55 in / 20 out": lambda d: sig_donchian(d, 55, 20),
    "Breakout 100 in / 50 out": lambda d: sig_donchian(d, 100, 50),
    "Momentum 90d + 200-day": lambda d: sig_mom(d, 90),
    "Dip in uptrend (daily, like SignalScout)": lambda d: sig_dip_in_trend(d),
}


if __name__ == "__main__":
    data = load()
    for s, d in data.items():
        print(s, d.index[0].date(), "->", d.index[-1].date(), len(d), "days")
    res = {}
    for name, f in STRATS.items():
        for coin, d in data.items():
            eq, pos = run(d, f(d))
            res[(name, coin)] = dict(ins=stats(eq, pos, None, SPLIT), oos=stats(eq, pos, SPLIT, None))
    import pickle
    pickle.dump(res, open("data/research.pkl", "wb"))
    print("\\nOUT-OF-SAMPLE (2022 -> today), average over the 5 coins; hold = buy and hold")
    hold = {c: res[("Buy and hold", c)]["oos"] for c in COINS}
    print(f"{'strategy':44s}{'return':>8s}{'worst':>8s}{'calmar':>8s}{'beats hold calmar':>19s}{'dd 30% smaller':>16s}")
    for name in STRATS:
        r = [res[(name, c)]["oos"] for c in COINS]
        beat = sum(x["calmar"] > hold[c]["calmar"] for x, c in zip(r, COINS))
        smaller = sum(abs(x["dd"]) <= 0.7 * abs(hold[c]["dd"]) for x, c in zip(r, COINS))
        print(f"{name:44s}{np.mean([x['ret'] for x in r])*100:7.0f}%{np.mean([x['dd'] for x in r])*100:7.0f}%"
              f"{np.mean([x['calmar'] for x in r]):8.2f}{beat:>14d}/5{smaller:>13d}/5")
