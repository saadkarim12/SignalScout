"""Backtest: replay history bar by bar and see if the rules would have made money.

Honesty rules:
- At every step the scorer only sees candles that were CLOSED at that moment.
- Entry is the NEXT candle's open. If stop and target are both touched in one candle, we assume the STOP.
- Costs: 0.1% fee each side + 0.05% slippage each side.
"""
import bisect
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import ROOT, load_config
from .data import make_exchange, fetch_history, TF_MS
from .indicators import sma
from .scoring import score_coin
from .sentiment import fear_greed_history
from .universe import pick_universe

FEE, SLIP = 0.001, 0.0005
YEARS = 3
GATE_EXPECTANCY, GATE_TRADES = 0.15, 40


# ---------- 1. find signals (no look-ahead) ----------
def find_signals(args):
    symbol, df4h, daily, fng_hist, cfg = args
    c = cfg["checklist"]
    n4 = cfg["candles_4h"]
    close_d = daily["close"]
    s200 = sma(close_d, c["sma_trend"])
    d_close_time = (daily["ts"] + TF_MS["1d"]).to_numpy()
    out = []
    for i in range(60, len(df4h) - 1):
        t = int(df4h["ts"].iloc[i] + TF_MS["4h"])           # moment this candle closed
        k = bisect.bisect_right(d_close_time, t)              # daily candles closed by then
        if k < c["sma_trend"] + 1:
            continue
        if not close_d.iloc[k - 1] > s200.iloc[k - 1]:        # MUST rule 1 fails -> NO_TRADE, skip fast
            continue
        day = datetime.fromtimestamp(t / 1000, timezone.utc)
        prev = (day - timedelta(days=1)).strftime("%Y-%m-%d")  # yesterday's value: known at that time
        fng = (fng_hist[prev], "history") if prev in fng_hist else None
        w4 = df4h.iloc[max(0, i + 1 - n4): i + 1].reset_index(drop=True)
        wd = daily.iloc[max(0, k - cfg["candles_daily"]): k].reset_index(drop=True)
        r = score_coin(symbol, w4, wd, fng, [], cfg, 1000, None, now=day)
        if r.verdict in ("STRONG", "WATCH"):
            out.append(dict(symbol=symbol, i=i, verdict=r.verdict, stop=r.stop, target=r.target))
    return symbol, out


# ---------- 2. simulate trades ----------
def simulate(signals, data, verdicts, cfg):
    v = cfg["verdict"]
    trades = []
    for sym in {s["symbol"] for s in signals}:
        df = data[sym]
        O, H, L, C, TS = (df[k].to_numpy() for k in ("open", "high", "low", "close", "ts"))
        n = len(df)
        busy = -1
        for s in sorted((x for x in signals if x["symbol"] == sym and x["verdict"] in verdicts), key=lambda x: x["i"]):
            j = s["i"] + 1
            if j <= busy or j >= n:
                continue
            entry = O[j] * (1 + SLIP)
            stop, target = s["stop"], s["target"]
            if entry <= stop or entry >= target:
                continue
            exit_px, k = None, j
            for k in range(j, n):
                if L[k] <= stop:                                  # stop first (conservative)
                    exit_px = min(O[k], stop) * (1 - SLIP) if k > j else stop * (1 - SLIP)
                    break
                if H[k] >= target:
                    exit_px = target * (1 - SLIP)
                    break
            still_open = exit_px is None
            if still_open:
                k = n - 1
                exit_px = C[k]
            risk = entry - stop
            pnl = exit_px - entry - FEE * (entry + exit_px)
            risk_pct = v["strong_risk_pct"] if s["verdict"] == "STRONG" else v["watch_risk_pct"]
            size = min(risk_pct / 100 / (risk / entry), v["max_position_pct"] / 100)
            trades.append(dict(symbol=sym, verdict=s["verdict"], entry_ts=int(TS[j]),
                               exit_ts=int(TS[k]), r=pnl / risk, ret=pnl / entry, size=size,
                               open_at_end=still_open, stopdist=risk / entry))
            busy = k
    return sorted(trades, key=lambda t: t["exit_ts"])


def equity_curve(trades, start=1000.0):
    eq, pts = start, [(trades[0]["entry_ts"] if trades else 0, start)]
    for t in trades:
        eq *= 1 + t["size"] * t["ret"]
        pts.append((t["exit_ts"], eq))
    return pts


def max_drawdown(values):
    peak, worst = -1e18, 0.0
    for x in values:
        peak = max(peak, x)
        worst = min(worst, x / peak - 1)
    return worst


def metrics(trades):
    if not trades:
        return dict(n=0, win=0, avg_r=0, expectancy=0, pf=0, dd=0, total_return=0)
    rs = np.array([t["r"] for t in trades])
    wins, losses = rs[rs > 0].sum(), -rs[rs <= 0].sum()
    pts = equity_curve(trades)
    return dict(n=len(rs), win=float((rs > 0).mean()), avg_r=float(rs.mean()), expectancy=float(rs.mean()),
                pf=float(wins / losses) if losses > 0 else float("inf"),
                dd=max_drawdown([p[1] for p in pts]), total_return=pts[-1][1] / 1000 - 1)


# ---------- 3. benchmarks ----------
def benchmarks(btc, start_ts):
    b = btc[btc["ts"] >= start_ts].reset_index(drop=True)
    hold = b["close"].iloc[-1] / b["open"].iloc[0] - 1
    hold_dd = max_drawdown(list(b["close"] / b["open"].iloc[0]))
    buys = b.iloc[::42]                                   # one buy per week (42 four-hour candles)
    units = (1.0 / buys["open"]).sum()
    dca = units * b["close"].iloc[-1] / len(buys) - 1
    return dict(hold=float(hold), hold_dd=float(hold_dd), dca=float(dca))


# ---------- 4. run + report ----------
def gate_text(m_all, m_oos):
    ok = m_all["n"] >= GATE_TRADES and m_all["expectancy"] > GATE_EXPECTANCY and m_oos["expectancy"] > GATE_EXPECTANCY
    return ok


def fmt_m(m):
    pf = "n/a" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
    return (f"{m['n']} | {m['win']*100:.0f}% | {m['avg_r']:+.2f}R | {m['expectancy']:+.2f}R | "
            f"{pf} | {m['dd']*100:.1f}% | {m['total_return']*100:+.1f}%")


def run(progress=print):
    cfg = load_config()
    ex = make_exchange(cfg["data_exchange"])
    ex.load_markets()
    syms = pick_universe(ex.fetch_tickers(), ex.markets, dict(cfg, universe_size=12))
    if "ETH/USDT" not in syms:
        syms = syms[:-1] + ["ETH/USDT"]
    data4, datad = {}, {}
    for s in syms:
        progress(f"Downloading history: {s}")
        try:
            d4 = fetch_history(ex, s, "4h", YEARS)
            dd = fetch_history(ex, s, "1d", YEARS + 1)
            if len(d4) > 600:
                data4[s], datad[s] = d4, dd
        except Exception as e:
            progress(f"  skipped {s}: {type(e).__name__}")
    fng_hist = fear_greed_history()
    progress(f"Replaying history for {len(data4)} coins (a few minutes)...")
    jobs = [(s, data4[s], datad[s], fng_hist, cfg) for s in data4]
    signals = []
    with ProcessPoolExecutor() as pool:
        for s, sig in pool.map(find_signals, jobs):
            progress(f"  {s}: {len(sig)} signals")
            signals += sig

    t0 = min(df["ts"].iloc[60] for df in data4.values())
    t1 = max(df["ts"].iloc[-1] for df in data4.values())
    split = t0 + 0.7 * (t1 - t0)
    modes = {"STRONG only": {"STRONG"}, "WATCH only": {"WATCH"}, "STRONG + WATCH": {"STRONG", "WATCH"}}
    res = {}
    for name, vs in modes.items():
        tr = simulate(signals, data4, vs, cfg)
        res[name] = dict(trades=tr, all=metrics(tr),
                         train=metrics([t for t in tr if t["entry_ts"] < split]),
                         test=metrics([t for t in tr if t["entry_ts"] >= split]))
    bench = benchmarks(data4["BTC/USDT"], t0)
    return res, bench, t0, t1, split, list(data4)


def write_report(res, bench, t0, t1, split, coins):
    day = datetime.now().strftime("%Y-%m-%d")
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    d = lambda ts: datetime.fromtimestamp(ts / 1000, timezone.utc).strftime("%Y-%m-%d")
    main = res["STRONG + WATCH"]
    passed = gate_text(main["all"], main["test"])
    head = "| Trades | Win rate | Avg R | Expectancy | Profit factor | Worst drop | Total return |\n|---|---|---|---|---|---|---|\n"
    L = [f"# SignalScout backtest - {day}", "",
         f"## Result: {'PASS' if passed else 'FAIL'}", "",
         f"The gate: at least **{GATE_TRADES} trades** and expectancy above **+{GATE_EXPECTANCY}R** over the whole period, "
         f"AND above +{GATE_EXPECTANCY}R on the last 30% of time (the part the rules were never tuned on).", "",
         f"Period tested: {d(t0)} to {d(t1)}. Train = up to {d(split)}, Test = after. Coins: {', '.join(coins)}.", "",
         "## Results (all costs included: 0.1% fee + 0.05% slippage each side)", ""]
    for name, r in res.items():
        L += [f"### {name}", head + f"| {fmt_m(r['all'])} |", "",
              f"- First 70% (train): {fmt_m(r['train'])}", f"- Last 30% (test): {fmt_m(r['test'])}", ""]
    L += ["## Compared with simply holding", "",
          f"- Buy and hold BTC the whole time: **{bench['hold']*100:+.1f}%** (worst drop {bench['hold_dd']*100:.1f}%)",
          f"- Buy BTC every week (DCA): **{bench['dca']*100:+.1f}%** on the money put in",
          f"- SignalScout rules (STRONG + WATCH, 1%/0.5% risk): **{main['all']['total_return']*100:+.1f}%** (worst drop {main['all']['dd']*100:.1f}%)", "",
          "## Plain-English guide", "",
          "- **R** = one unit of risk. +1R means you won as much as you risked. -1R means the stop was hit.",
          "- **Expectancy** = average R per trade. Above 0 means it made money on average after costs.",
          "- **Profit factor** = total wins / total losses. Above 1 is good.",
          "- **Worst drop** = biggest fall from a high point in your account.", "",
          "## Warnings (please read)", "",
          "- Coins were picked by TODAY's trading volume, so the test is a bit flattering (survivorship bias).",
          "- Past results do not promise future results. The news check is ignored; Fear & Greed uses real history.",
          "- If it FAILS: do not lower the gate. We change ONE rule at a time and retest. Too much tweaking only fits the past (overfitting).",
          "", "Signal, not advice. You decide. Risk max 1%."]
    (out / f"backtest_{day}.md").write_text("\n".join(L))
    # picture
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for name, r in res.items():
        p = equity_curve(r["trades"])
        ax.plot(pd.to_datetime([x[0] for x in p], unit="ms"), [x[1] for x in p], label=name)
    ax.axvline(pd.to_datetime(split, unit="ms"), color="grey", ls="--")
    ax.text(pd.to_datetime(split, unit="ms"), ax.get_ylim()[0], " test period ->", color="grey", va="bottom")
    ax.axhline(1000, color="black", lw=0.5)
    ax.set_title(f"Account value starting at $1,000 (BTC buy-and-hold: {bench['hold']*100:+.0f}%)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"backtest_{day}.png", dpi=110)
    return passed, out / f"backtest_{day}.md"


if __name__ == "__main__":
    t = time.time()
    r = run()
    passed, path = write_report(*r)
    print(f"\nBacktest {'PASS' if passed else 'FAIL'} - report: {path} ({time.time() - t:.0f}s)")
