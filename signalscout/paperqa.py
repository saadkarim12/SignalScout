"""Daily paper run + independent QA + go-live checks for the Trend portfolio.

Plain English:
- Every day: record the pretend position (exposure per coin) and the pretend account value, strategy vs buy-and-hold.
- Every day: independent QA checks (fresh data, a SECOND separately written calculation agrees, a second exchange agrees on the price,
  no gaps in the record, news sources working).
- You: press "I checked today" once a day.
- Go-live rules (config.yaml, fixed in advance). Even when all pass, the next step is a TINY real test, never a big one.
"""
import json
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from . import journal
from . import trendportfolio as tp
from .config import load_config


# ---------- daily ledger ----------
def record_ledger(data: dict, start) -> int:
    """Store strategy vs hold value (start = 1.0) and each coin's exposure for every day since `start`. Safe to repeat."""
    se, he = tp.paper_curve(data, start)
    ens = {s: tp.ensemble(d) for s, d in data.items()}
    n = 0
    with journal._conn() as c:
        for day in se.index:
            expo = {s.split("/")[0]: float(e.get(day, float("nan"))) for s, e in ens.items()}
            c.execute("INSERT OR REPLACE INTO tp_ledger VALUES(?,?,?,?)",
                      (day.strftime("%Y-%m-%d"), float(se[day]), float(he[day]), json.dumps(expo)))
            n += 1
    return n


def ledger():
    with journal._conn() as c:
        return [dict(date=d, strat=a, hold=b, exposures=json.loads(e))
                for d, a, b, e in c.execute("SELECT date,strat,hold,exposures FROM tp_ledger ORDER BY date").fetchall()]


# ---------- independent recomputation (separately written, plain Python) ----------
def indep_exposure(closes: list[float]) -> float:
    c, n = list(closes), len(closes)
    votes = []
    votes.append(1.0 if n >= 50 and c[-1] > sum(c[-50:]) / 50 else 0.0)
    votes.append(1.0 if n >= 200 and c[-1] > sum(c[-200:]) / 200 else 0.0)
    for n_in, n_out in ((55, 20), (100, 50)):
        inside = False
        for i in range(n):
            if not inside and i >= n_in and c[i] > max(c[i - n_in:i]):
                inside = True
            elif inside and i >= n_out and c[i] < min(c[i - n_out:i]):
                inside = False
        votes.append(1.0 if inside else 0.0)
    return sum(votes) / 4


# ---------- QA checks ----------
def qa_checks(data: dict, news=None, other_prices=None, now=None) -> list[dict]:
    """Each check: dict(name, ok (True/False/None=could not check), detail)."""
    now = now or datetime.now(timezone.utc)
    out = []
    st = tp.live_status(data)
    # 1 fresh data
    for s, d in data.items():
        age = (now.date() - d.index[-1].date()).days
        out.append(dict(name=f"{s.split('/')[0]} data is fresh", ok=age <= 1, detail=f"last closed daily candle {d.index[-1].date()} ({age} day(s) old)"))
    # 2 numbers are real and allowed
    for s, v in st.items():
        ok = v["exposure"] in (0.0, 0.25, 0.5, 0.75, 1.0) and v["price"] > 0
        out.append(dict(name=f"{s.split('/')[0]} exposure is a valid step", ok=ok, detail=f"exposure {v['exposure']}, price {v['price']}"))
    # 3 second calculation agrees
    for s, d in data.items():
        a, b = st[s]["exposure"], indep_exposure(list(d["close"]))
        out.append(dict(name=f"{s.split('/')[0]} second calculation agrees", ok=abs(a - b) < 1e-9, detail=f"app {a:.2f}, independent {b:.2f}"))
    # 4 second exchange agrees on the price
    if other_prices:
        for s, (p1, p2) in other_prices.items():
            diff = abs(p1 / p2 - 1) * 100
            out.append(dict(name=f"{s.split('/')[0]} price agrees on a second exchange", ok=diff < 0.5, detail=f"Binance {p1:,.2f} vs second exchange {p2:,.2f} ({diff:.2f}% apart)"))
    else:
        out.append(dict(name="second exchange price check", ok=None, detail="could not reach the second exchange"))
    # 5 ledger has no gaps
    led = ledger()
    if led:
        days = pd.date_range(led[0]["date"], led[-1]["date"])
        missing = [x.strftime("%Y-%m-%d") for x in days if x.strftime("%Y-%m-%d") not in {r["date"] for r in led}]
        out.append(dict(name="daily record has no gaps", ok=not missing, detail=f"{len(led)} days recorded, missing: {missing[:3] or 'none'}"))
    # 6 news sources
    if news is not None:
        out.append(dict(name="news sources working", ok=len(news["ok"]) >= 4, detail=f"{len(news['ok'])} working, problems: {news['bad'] or 'none'}"))
    return out


def store_qa(day: str, checks: list[dict]):
    ok = all(c["ok"] is not False for c in checks)
    with journal._conn() as c:
        c.execute("INSERT OR REPLACE INTO qa_log VALUES(?,?,?)", (day, int(ok), json.dumps(checks)))
    return ok


def qa_rows(limit=30):
    with journal._conn() as c:
        return [dict(date=d, ok=bool(o), checks=json.loads(x)) for d, o, x in
                c.execute("SELECT date,ok,details FROM qa_log ORDER BY date DESC LIMIT ?", (limit,)).fetchall()]


# ---------- the human daily check-in ----------
def checkin(note="", today=None) -> bool:
    day = (today or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    with journal._conn() as c:
        return c.execute("INSERT OR IGNORE INTO checkins VALUES(?,?,?)", (day, note[:300], time.time())).rowcount == 1


def checkins():
    with journal._conn() as c:
        return c.execute("SELECT date,note FROM checkins ORDER BY date DESC").fetchall()


# ---------- go-live rules ----------
def go_live(cfg=None, led=None, qa=None, ci=None) -> dict:
    g = (cfg or load_config())["go_live"]
    led = ledger() if led is None else led
    qa = qa_rows(1000) if qa is None else qa
    ci = checkins() if ci is None else ci
    days = len(led)
    rows = []
    rows.append(("Forward test long enough", days >= g["min_days"], f"{days} of {g['min_days']} days"))
    qp = (sum(r["ok"] for r in qa) / len(qa) * 100) if qa else 0
    rows.append(("Independent QA checks passing", qp >= g["min_qa_pass_pct"] and bool(qa), f"{qp:.0f}% of {len(qa)} days (need {g['min_qa_pass_pct']}%)"))
    cp = (len(ci) / days * 100) if days else 0
    rows.append(("You did the daily check-in", cp >= g["min_checkin_pct"], f"{len(ci)} of {days} days = {cp:.0f}% (need {g['min_checkin_pct']}%)"))
    if led:
        s = pd.Series([r["strat"] for r in led]); h = pd.Series([r["hold"] for r in led])
        dds, ddh = abs(float((s / s.cummax() - 1).min())) * 100, abs(float((h / h.cummax() - 1).min())) * 100
        rows.append(("Paper drawdown acceptable", dds <= g["max_paper_drawdown_pct"] or dds <= ddh,
                     f"strategy worst drop {dds:.1f}% (limit {g['max_paper_drawdown_pct']}% or no worse than buy-and-hold's {ddh:.1f}%)"))
        rows.append(("Paper account above 90% of start", float(s.iloc[-1]) * 100 >= g["min_equity_pct"], f"{float(s.iloc[-1]) * 100:.1f}% of start"))
        changes = sum(1 for a, b in zip(led, led[1:]) if a["exposures"] != b["exposures"])
        rows.append(("Position changes seen (mechanics proven)", changes >= g["min_exposure_changes"], f"{changes} of {g['min_exposure_changes']} needed"))
    else:
        rows += [("Paper drawdown acceptable", False, "no data yet"), ("Paper account above 90% of start", False, "no data yet"),
                 ("Position changes seen (mechanics proven)", False, "no data yet")]
    ready = all(r[1] for r in rows)
    return dict(rows=rows, ready=ready)
