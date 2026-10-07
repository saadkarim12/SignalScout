"""Honest backtest of the trend + momentum idea (daily candles).

Pass rules were fixed BEFORE running (see gate()).
Remaining bias (please remember): the 60-coin pool is chosen by TODAY's volume, so coins that died are missing.
We reduce (not remove) this by only allowing the 15 most-traded coins AT EACH DATE.
"""
import time
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import ROOT, load_config
from .data import make_exchange, fetch_history
from .indicators import sma
from .trend import build_panel, compute, weights
from .universe import pick_universe


def run_strategy(C, V, t, hold_n=None, mom_days=None):
    sig = compute(C, V, t, hold_n, mom_days)
    w = weights(sig)
    rets = C.pct_change(fill_method=None).fillna(0)
    turnover = w.diff().abs().sum(axis=1).fillna(0)
    daily = (w * rets).sum(axis=1) - turnover * t["cost_per_side"]
    return (1 + daily).cumprod(), w


def window_stats(eq, a, b):
    e = eq[(eq.index >= a) & (eq.index <= b)]
    e = e / e.iloc[0]
    ret = e.iloc[-1] - 1
    dd = (e / e.cummax() - 1).min()
    return dict(ret=float(ret), dd=float(dd), ratio=float(ret / abs(dd)) if dd < 0 else float("inf"))


def gate(test_main, test_btc, grid_test_rets):
    c1 = test_main["ret"] > 0
    c2 = test_main["ratio"] >= test_btc["ratio"]
    c3 = sum(r > 0 for r in grid_test_rets) >= 6
    return c1 and c2 and c3, (c1, c2, c3)


def run():
    cfg = load_config()
    t = cfg["trend"]
    ex = make_exchange(cfg["data_exchange"])
    ex.load_markets()
    syms = pick_universe(ex.fetch_tickers(), ex.markets, dict(cfg, universe_size=t["pool_size"]))
    data = {}
    for i, s in enumerate(syms):
        print(f"Downloading {i + 1}/{len(syms)} {s}", flush=True)
        try:
            d = fetch_history(ex, s, "1d", 4)
            if len(d) > 250:
                data[s] = d
        except Exception as e:
            print("  skipped", s, type(e).__name__)
    C, V = build_panel(data)
    end = C.index[-1]
    start = end - pd.Timedelta(days=365 * 3)
    split = start + (end - start) * 0.7

    main, w = run_strategy(C, V, t)
    btc = (1 + C["BTC/USDT"].pct_change(fill_method=None).fillna(0)).cumprod()
    btc200 = (1 + (C["BTC/USDT"].pct_change(fill_method=None).fillna(0) *
                   (C["BTC/USDT"] > sma(C["BTC/USDT"], 200)).shift(2).fillna(False).astype(float))).cumprod()

    grid = {}
    for n in (2, 3, 5):
        for m in (60, 90, 120):
            eq, _ = run_strategy(C, V, t, n, m)
            grid[(n, m)] = (window_stats(eq, start, split), window_stats(eq, split, end))

    rows = {}
    for name, eq in {"Trend + momentum (this strategy)": main, "BTC buy and hold": btc,
                     "BTC held only above 200-day average": btc200}.items():
        rows[name] = (window_stats(eq, start, end), window_stats(eq, start, split), window_stats(eq, split, end))
    test_main, test_btc = rows["Trend + momentum (this strategy)"][2], rows["BTC buy and hold"][2]
    ok, parts = gate(test_main, test_btc, [g[1]["ret"] for g in grid.values()])
    changes = int((w.diff().abs().sum(axis=1) > 0).sum())
    return dict(ok=ok, parts=parts, rows=rows, grid=grid, start=start, split=split, end=end, coins=len(data),
                main=main, btc=btc, btc200=btc200, trades_days=changes, test_main=test_main, test_btc=test_btc)


def pct(x):
    return f"{x * 100:+.0f}%"


def write(res):
    day = datetime.now().strftime("%Y-%m-%d")
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    d = lambda x: x.strftime("%Y-%m-%d")
    L = [f"# Trend + momentum backtest - {day}", "", f"## Result: {'PASS' if res['ok'] else 'FAIL'}", "",
         "Rules fixed before the test (all three must be true on the last 30% of time):", "",
         f"1. Positive return in the test period: {'yes' if res['parts'][0] else 'NO'}",
         f"2. Return-per-worst-drop at least as good as holding BTC: {'yes' if res['parts'][1] else 'NO'}",
         f"3. At least 6 of 9 nearby settings also positive in the test period: {'yes' if res['parts'][2] else 'NO'}", "",
         f"Period {d(res['start'])} to {d(res['end'])}; test period starts {d(res['split'])}. "
         f"{res['coins']} coins in the pool, costs 0.15% each side included.", "",
         "| Strategy | Whole period | Worst drop | First 70% | Last 30% (test) | Test worst drop |", "|---|---|---|---|---|---|"]
    for k, (a, tr, te) in res["rows"].items():
        L.append(f"| {k} | {pct(a['ret'])} | {pct(a['dd'])} | {pct(tr['ret'])} | {pct(te['ret'])} | {pct(te['dd'])} |")
    L += ["", "## Do nearby settings agree? (test-period return)", "", "| Hold N coins \\ Momentum days | 60 | 90 | 120 |", "|---|---|---|---|"]
    for n in (2, 3, 5):
        L.append(f"| {n} | " + " | ".join(pct(res["grid"][(n, m)][1]["ret"]) for m in (60, 90, 120)) + " |")
    L += ["", "## Warnings (please read)", "",
          "- The coin pool comes from today's volume, so dead coins are missing. Real results would likely be lower.",
          "- I looked at a quick full-period test before fixing these settings, so the 'test' period is only a partial check.",
          "- A few coins that went up hugely can drive the whole result. Watch the worst drop, not only the return.",
          "- Past results do not promise future results.", "", "Signal, not advice. You decide. Risk max 1%."]
    (out / f"trend_{day}.md").write_text("\n".join(L))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for name, eq in (("Trend + momentum", res["main"]), ("BTC buy and hold", res["btc"]), ("BTC above 200-day only", res["btc200"])):
        e = eq[eq.index >= res["start"]]
        ax.plot(e.index, e / e.iloc[0] * 1000, label=name)
    ax.axvline(res["split"], color="grey", ls="--")
    ax.set_yscale("log")
    ax.set_title("Account value from $1,000 (log scale). Dashed line = start of test period")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"trend_{day}.png", dpi=110)
    return out / f"trend_{day}.md"


if __name__ == "__main__":
    t0 = time.time()
    r = run()
    p = write(r)
    print(f"\nTrend backtest {'PASS' if r['ok'] else 'FAIL'} - {p} ({time.time() - t0:.0f}s)")
