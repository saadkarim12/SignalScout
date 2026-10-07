"""`make scan` - score the top coins and print a table."""
import sys
import time
from datetime import datetime, timezone
from .config import load_config
from .data import make_exchange, fetch_ohlcv
from .universe import pick_universe
from .sentiment import fear_greed
from .events import load_events
from .scoring import score_coin, rank
from . import news as newsmod


def connect(cfg):
    for name in (cfg["data_exchange"], cfg["fallback_exchange"]):
        try:
            ex = make_exchange(name)
            ex.load_markets()
            return ex, ex.fetch_tickers()
        except Exception as e:
            print(f"! {name} unavailable ({type(e).__name__}); trying fallback...")
    return None, None


def run_scan(cfg=None, verbose=True):
    cfg = cfg or load_config()
    ex, tickers = connect(cfg)
    if ex is None:
        print("No market data available right now. Not guessing - try again later.")
        return []
    symbols = pick_universe(tickers, ex.markets, cfg)
    fng = fear_greed()
    nw = newsmod.get_news()
    events = load_events() + nw["events"]
    now = datetime.now(timezone.utc)
    note = newsmod.checked_note(nw)
    data, btc4h = {}, None
    for s in symbols:
        try:
            data[s] = (fetch_ohlcv(ex, s, "4h", cfg["candles_4h"], cfg["cache_minutes"]),
                       fetch_ohlcv(ex, s, "1d", cfg["candles_daily"], cfg["cache_minutes"]))
        except Exception as e:
            print(f"! skipped {s}: {type(e).__name__}")
    if "BTC/USDT" in data:
        btc4h = data["BTC/USDT"][0]
    res = [score_coin(s, d4, dd, fng, events, cfg, cfg["account_size_usd"], btc4h, now=now,
                      risk=newsmod.risky(s, nw["headlines"], now), news_note=note)
           for s, (d4, dd) in data.items()]
    res = rank(res)
    if verbose:
        print_table(res, fng)
    return res


def fmt(x):
    return f"{x:,.6g}" if x else "-"


def print_table(res, fng):
    print(f"\nSignalScout scan - {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | "
          f"Fear & Greed: {fng[0] if fng else 'n/a'} ({fng[1] if fng else ''})\n")
    print(f"{'Coin':<11}{'Score':>6}  {'Verdict':<9}{'Entry':>12}{'Stop':>12}{'Target':>12}{'R:R':>6}")
    print("-" * 70)
    for x in res:
        print(f"{x.symbol:<11}{x.score:>4}/10  {x.verdict:<9}{fmt(x.entry):>12}{fmt(x.stop):>12}"
              f"{fmt(x.target):>12}{x.rr:>6.1f}")
    print("\nVerdicts: STRONG = best setups, WATCH = decent, SKIP = weak, NO_TRADE = a must-have rule failed.")
    print("Signal, not advice. You decide. Risk max 1%.")


if __name__ == "__main__":
    t = time.time()
    run_scan()
    print(f"({time.time() - t:.0f}s)")
