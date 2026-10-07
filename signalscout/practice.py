"""Practice track: pretend trades from STRONG/WATCH signals, tracked automatically.

Plain English:
- You log a pretend buy (price now) with the stop and target from the signal.
- Every few minutes SignalScout looks at the price candles since your buy.
  Stop touched first -> loss. Target touched -> win. If both in one candle we assume the STOP (cautious).
- Costs are included (0.1% fee + 0.05% slippage each side), so results are not too rosy.
- A trade still open after 21 days is closed at the market price ("expired").
"""
import time

from . import journal
from .alerts import FOOTER, tv_link, money
from .config import load_config

FEE, SLIP = 0.001, 0.0005
Q15 = 15 * 60 * 1000


def open_trade(symbol, verdict, price, stop, target, usd, note="", suggestion=None) -> dict:
    if any(t["symbol"] == symbol for t in open_trades()):
        raise ValueError(f"You already have an open practice trade on {symbol.split('/')[0]}. "
                         "Wait for it to finish before logging another one on the same coin.")
    if not (stop < price < target):
        raise ValueError("The price has already moved past the stop or the target, so this signal is out of date. "
                         "Skip it and wait for the next one.")
    rr = (target - price) / (price - stop)
    need = load_config()["checklist"]["min_rr"]
    if rr < need - 1e-9:
        raise ValueError(f"Since the signal appeared the price has moved, and the reward vs risk is now only {rr:.1f} "
                         f"(it needs {need:.0f}+). The signal is out of date. Skip it and wait for the next one.")
    with journal._conn() as c:
        tid = c.execute("INSERT INTO trades(symbol,kind,entry,stop,target,usd,ts,verdict,note,suggestion) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (symbol, "practice", price, stop, target, usd, time.time(), verdict, note, suggestion)).lastrowid
    return dict(id=tid, symbol=symbol, entry=price, stop=stop, target=target, usd=usd)


COLS = "id,symbol,entry,stop,target,usd,ts,status,result_r,exit_price,exit_ts,verdict,note,usd_result,reason,suggestion"


def _rows(where, args=()):
    with journal._conn() as c:
        return [dict(zip(COLS.split(","), r)) for r in
                c.execute(f"SELECT {COLS} FROM trades WHERE kind='practice' AND {where} ORDER BY id", args).fetchall()]


def open_trades():
    return _rows("status='open'")


def closed_trades():
    return _rows("status!='open'")


def result(entry, stop, exit_px, usd):
    """R multiple and dollar result with costs."""
    e = entry * (1 + SLIP)
    x = exit_px * (1 - SLIP)
    pnl = x - e - FEE * (e + x)
    return pnl / (e - stop), usd * pnl / e


def close_trade(t, exit_px, reason, exit_ts):
    r, dollars = result(t["entry"], t["stop"], exit_px, t["usd"])
    status = "win" if r > 0 else "loss"
    with journal._conn() as c:
        c.execute("UPDATE trades SET status=?, result_r=?, exit_price=?, exit_ts=?, usd_result=?, reason=? WHERE id=?",
                  (status, r, exit_px, exit_ts, dollars, reason, t["id"]))
    return dict(t, status=status, result_r=r, exit_price=exit_px, usd_result=dollars, reason=reason)


def evaluate(t, candles, now_ms, max_days=21):
    """candles: [[ts,o,h,l,c,v],...] 15-minute. Returns (exit_price, reason, exit_ts) or None. Stop first on ties."""
    start = int(t["ts"] * 1000)
    last_close = None
    for ts, o, h, l, c, v in candles:
        if ts <= start or ts + Q15 > now_ms:            # skip the candle we bought in, and unfinished candles
            continue
        last_close = (c, ts)
        if l <= t["stop"]:
            return min(o, t["stop"]), "stop", ts
        if h >= t["target"]:
            return t["target"], "target", ts
    if last_close and now_ms - start > max_days * 86400_000:
        return last_close[0], "expired", last_close[1]
    return None


def check_open(ex, now_ms=None) -> list[dict]:
    now_ms = now_ms or int(time.time() * 1000)
    max_days = load_config()["practice"]["max_open_days"]
    done = []
    for t in open_trades():
        try:
            candles = ex.fetch_ohlcv(t["symbol"], "15m", since=int(t["ts"] * 1000), limit=1000)
        except Exception:
            continue                                     # try again next time
        hit = evaluate(t, candles, now_ms, max_days)
        if hit:
            done.append(close_trade(t, *hit))
    return done


def stats(goal=None) -> dict:
    goal = goal or load_config()["practice"]["goal_trades"]
    cl = closed_trades()
    rs = [t["result_r"] for t in cl]
    wins = sum(r > 0 for r in rs)
    cfg = load_config()["practice"]
    total = sum(rs)
    avg = total / len(rs) if rs else 0.0
    verdict = None
    if len(rs) >= goal:
        verdict = "PASS" if (total > 0 and avg >= cfg["pass_avg_r"]) else "NOT PROVEN"
    return dict(done=len(rs), goal=goal, wins=wins, losses=len(rs) - wins, win_rate=wins / len(rs) if rs else 0.0,
                total_r=total, avg_r=avg, dollars=sum(t["usd_result"] or 0 for t in cl),
                open=len(open_trades()), verdict=verdict)


def close_message(t) -> str:
    why = {"target": "hit your TARGET", "stop": "hit your STOP", "expired": "ran out of time (21 days) and was closed"}[t["reason"]]
    s = stats()
    lead = "✅" if t["status"] == "win" else "🛑"
    return (f"{lead} Practice trade #{t['id']}: {t['symbol'].split('/')[0]} {why}.\n"
            f"Result: {t['result_r']:+.2f}R (about {'+' if t['usd_result'] >= 0 else '-'}{money(abs(t['usd_result']))} "
            f"on a {money(t['usd'])} pretend position, costs included).\n"
            f"Progress: {s['done']} of {s['goal']} trades finished, total {s['total_r']:+.2f}R.\n"
            f"Chart: {tv_link(t['symbol'])}\n\n{FOOTER}")


def verdict_text(s) -> str:
    if not s["verdict"]:
        return f"Keep going: {s['goal'] - s['done']} more finished trades to reach {s['goal']}."
    if s["verdict"] == "PASS":
        return (f"PASS: after {s['done']} trades the total is {s['total_r']:+.2f}R (average {s['avg_r']:+.2f}R). "
                "That is encouraging, but 20 trades is a small sample. If you go real, start tiny and keep tracking.")
    return (f"NOT PROVEN: after {s['done']} trades the total is {s['total_r']:+.2f}R (average {s['avg_r']:+.2f}R). "
            "Do not trade this with real money yet. We review what happened before changing anything.")


def by_suggestion() -> dict:
    """Finished trades split by the advice we gave when they were logged: does 'BUY' really do better than 'WAIT'?"""
    out = {}
    for t in closed_trades():
        k = t["suggestion"] or "not recorded"
        d = out.setdefault(k, dict(n=0, wins=0, total_r=0.0))
        d["n"] += 1
        d["wins"] += t["result_r"] > 0
        d["total_r"] += t["result_r"]
    return out
