"""Support levels: daily SMA50, broken swing highs, round numbers."""
import math
import pandas as pd
from .indicators import pivot_highs, sma


def round_support(price: float, symbol: str) -> float:
    base = symbol.split("/")[0]
    if base == "BTC":
        step = 5000
        return math.floor(price / step) * step
    if base == "ETH":
        step = 250
        return math.floor(price / step) * step
    mag = 10 ** (math.floor(math.log10(price)) - 1)  # 2 significant digits
    return math.floor(price / mag) * mag


def find_support(df4h: pd.DataFrame, daily: pd.DataFrame, symbol: str, cfg: dict):
    """Nearest support below the last close -> (price, label) or None."""
    close = df4h["close"].iloc[-1]
    cands = []
    s50 = sma(daily["close"], cfg["sma_fast"]).iloc[-1]
    if pd.notna(s50):
        cands.append((s50, "daily 50-day average"))
    bars, look = cfg["pivot_bars"], cfg["swing_lookback"]
    start = max(0, len(df4h) - look)
    sub = df4h.iloc[start:].reset_index(drop=True)
    for i in pivot_highs(sub["high"], bars):
        lvl = sub["high"].iloc[i]
        if close > lvl:  # price has closed above it -> old resistance is now support
            cands.append((lvl, "broken swing high"))
    rn = round_support(close, symbol)
    if rn > 0:
        cands.append((rn, "round number"))
    below = [c for c in cands if c[0] < close]
    return max(below, key=lambda c: c[0]) if below else None
