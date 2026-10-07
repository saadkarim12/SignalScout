"""Does the score add anything? Compare the real signals with RANDOM entries that have the same
stop distance and target distance, on the same coins, only in uptrends (so only the rest of the score is tested).
"""
import bisect
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import numpy as np

from .backtest import find_signals, simulate, metrics, YEARS
from .config import ROOT, load_config
from .data import make_exchange, fetch_history, TF_MS
from .indicators import sma
from .sentiment import fear_greed_history
from .universe import pick_universe

RUNS = 100


def uptrend_bars(df4h, daily, c):
    s200 = sma(daily["close"], c["sma_trend"]).to_numpy()
    close = daily["close"].to_numpy()
    d_close_time = (daily["ts"] + TF_MS["1d"]).to_numpy()
    out = []
    for i in range(60, len(df4h) - 1):
        t = int(df4h["ts"].iloc[i] + TF_MS["4h"])
        k = bisect.bisect_right(d_close_time, t)
        if k >= c["sma_trend"] + 1 and close[k - 1] > s200[k - 1]:
            out.append(i)
    return out


def run():
    cfg = load_config()
    ex = make_exchange(cfg["data_exchange"])
    ex.load_markets()
    syms = pick_universe(ex.fetch_tickers(), ex.markets, dict(cfg, universe_size=12))
    if "ETH/USDT" not in syms:
        syms = syms[:-1] + ["ETH/USDT"]
    d4, dd = {}, {}
    for s in syms:
        try:
            a, b = fetch_history(ex, s, "4h", YEARS), fetch_history(ex, s, "1d", YEARS + 1)
            if len(a) > 600:
                d4[s], dd[s] = a, b
        except Exception:
            pass
    fh = fear_greed_history()
    with ProcessPoolExecutor() as pool:
        sigs = [x for _, sg in pool.map(find_signals, [(s, d4[s], dd[s], fh, cfg) for s in d4]) for x in sg]
    real = simulate(sigs, d4, {"STRONG", "WATCH"}, cfg)
    real_avg = float(np.mean([t["r"] for t in real]))
    elig = {s: uptrend_bars(d4[s], dd[s], cfg["checklist"]) for s in d4}
    shapes = []
    for sg in sigs:
        df = d4[sg["symbol"]]
        e = df["close"].iloc[sg["i"]]
        shapes.append((sg["symbol"], sg["verdict"], (e - sg["stop"]) / e, (sg["target"] - e) / e))
    rng = np.random.default_rng(7)
    avgs, wins = [], []
    for _ in range(RUNS):
        fake = []
        for sym, v, sp, tp in shapes:
            j = int(rng.choice(elig[sym]))
            e = d4[sym]["close"].iloc[j]
            fake.append(dict(symbol=sym, i=j, verdict=v, stop=e * (1 - sp), target=e * (1 + tp)))
        tr = simulate(fake, d4, {"STRONG", "WATCH"}, cfg)
        if tr:
            avgs.append(float(np.mean([t["r"] for t in tr])))
            wins.append(float(np.mean([t["r"] > 0 for t in tr])))
    return dict(real_n=len(real), real_avg=real_avg, real_win=float(np.mean([t["r"] > 0 for t in real])),
                rand_avg=float(np.mean(avgs)), rand_lo=float(np.percentile(avgs, 5)), rand_hi=float(np.percentile(avgs, 95)),
                rand_win=float(np.mean(wins)), pct_better=float(np.mean([a < real_avg for a in avgs]) * 100), runs=len(avgs))


def write(r):
    day = datetime.now().strftime("%Y-%m-%d")
    verdict = ("The score looks like it adds something." if r["pct_better"] >= 95 else
               "The score does NOT clearly beat random entries." if r["pct_better"] < 80 else
               "Borderline: better than most random runs, but not clearly.")
    L = [f"# Does the score beat random entries? - {day}", "", f"## {verdict}", "",
         "We took the real STRONG/WATCH signals from the last 3 years and compared them with random entries on the same coins, "
         "in uptrends only, with the same stop distance and target distance, same fees and slippage.", "",
         "| | Trades | Win rate | Average result |", "|---|---|---|---|",
         f"| Real signals | {r['real_n']} | {r['real_win']*100:.0f}% | {r['real_avg']:+.2f}R |",
         f"| Random entries (average of {r['runs']} runs) | similar | {r['rand_win']*100:.0f}% | {r['rand_avg']:+.2f}R |", "",
         f"Random entries ranged from {r['rand_lo']:+.2f}R to {r['rand_hi']:+.2f}R (middle 90% of runs).",
         f"The real signals did better than **{r['pct_better']:.0f}%** of the random runs.", "",
         "Plain English: if the real signals are not clearly better than random buying in an uptrend, the 10-point score is not adding value "
         "beyond 'buy in an uptrend with this stop and target'.", "", "Signal, not advice. You decide. Risk max 1%."]
    p = ROOT / "reports" / f"baseline_{day}.md"
    p.write_text("\n".join(L))
    return p


if __name__ == "__main__":
    t0 = time.time()
    r = run()
    print(r)
    print(write(r), f"({time.time() - t0:.0f}s)")
