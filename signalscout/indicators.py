"""Own indicator maths. Every function only looks at data it is given (no look-ahead)."""
import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _wilder(s: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing: seed with the simple average of the first n values."""
    out = pd.Series(np.nan, index=s.index)
    vals = s.to_numpy(dtype=float)
    valid = np.where(~np.isnan(vals))[0]
    if len(valid) < n:
        return out
    start = valid[0] + n - 1
    res = np.full(len(vals), np.nan)
    res[start] = vals[valid[0]:start + 1].mean()
    for i in range(start + 1, len(vals)):
        res[i] = (res[i - 1] * (n - 1) + vals[i]) / n
    return pd.Series(res, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = _wilder(d.clip(lower=0).where(d.notna()), n)
    loss = _wilder((-d).clip(lower=0).where(d.notna()), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0).where(gain.notna())


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return _wilder(tr, n)


def pivot_highs(high: pd.Series, bars: int) -> list[int]:
    """Positions of confirmed pivot highs (needs `bars` bars on each side)."""
    h = high.to_numpy()
    return [i for i in range(bars, len(h) - bars)
            if h[i] > h[i - bars:i].max() and h[i] >= h[i + 1:i + bars + 1].max()]


def pivot_lows(low: pd.Series, bars: int) -> list[int]:
    l = low.to_numpy()
    return [i for i in range(bars, len(l) - bars)
            if l[i] < l[i - bars:i].min() and l[i] <= l[i + 1:i + bars + 1].min()]


def hidden_bullish_divergence(df: pd.DataFrame, rsi_s: pd.Series, bars=3, lookback=60, recent=8) -> bool:
    """Higher price low but lower RSI low, second low within the last `recent` bars."""
    n = len(df)
    lo = max(0, n - lookback)
    sub = df["low"].iloc[lo:]
    piv = [lo + i for i in pivot_lows(sub, bars)]
    if len(piv) < 2:
        return False
    a, b = piv[-2], piv[-1]
    if b < n - recent:
        return False
    return bool(df["low"].iloc[b] > df["low"].iloc[a] and rsi_s.iloc[b] < rsi_s.iloc[a])
