"""Fetch and cache OHLCV candles. Only CLOSED candles are returned."""
import time
import ccxt
import pandas as pd
from .config import ROOT

TF_MS = {"4h": 4 * 3600_000, "1d": 24 * 3600_000}
CACHE = ROOT / "data" / "cache"


def make_exchange(name: str):
    return getattr(ccxt, name)({"enableRateLimit": True})


def drop_unclosed(df: pd.DataFrame, tf: str, now_ms: int | None = None) -> pd.DataFrame:
    now_ms = now_ms or int(time.time() * 1000)
    return df[df["ts"] + TF_MS[tf] <= now_ms].reset_index(drop=True)


def fetch_ohlcv(ex, symbol: str, tf: str, limit: int, cache_minutes: int = 10) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{ex.id}_{symbol.replace('/', '-')}_{tf}.csv"
    if f.exists() and time.time() - f.stat().st_mtime < cache_minutes * 60:
        df = pd.read_csv(f)
        if len(df) >= limit * 0.9:
            return drop_unclosed(df, tf)
    rows = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df.to_csv(f, index=False)
    return drop_unclosed(df, tf)


def fetch_history(ex, symbol: str, tf: str, years: float, cache_hours: int = 12) -> pd.DataFrame:
    """Download a long history (several requests of 1000 candles). Closed candles only."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"hist_{ex.id}_{symbol.replace('/', '-')}_{tf}_{years}.csv"
    if f.exists() and time.time() - f.stat().st_mtime < cache_hours * 3600:
        return drop_unclosed(pd.read_csv(f), tf)
    since = int(time.time() * 1000 - years * 365 * 24 * 3600_000)
    rows = []
    while True:
        batch = ex.fetch_ohlcv(symbol, tf, since=since, limit=1000)
        if not batch:
            break
        rows += batch
        nxt = batch[-1][0] + TF_MS[tf]
        if nxt <= since or len(batch) < 2:
            break
        since = nxt
        if nxt > time.time() * 1000:
            break
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    df = df.sort_values("ts").reset_index(drop=True)
    df.to_csv(f, index=False)
    return drop_unclosed(df, tf)
