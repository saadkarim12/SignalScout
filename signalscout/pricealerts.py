"""Price alerts: "tell me when BTC reaches $X". One message, then the alert switches itself off.

Plain English: this only tells you that a price was touched. It is NOT a buy or sell signal by itself.
"""
import re
import time

from . import journal
from .alerts import FOOTER, tv_link

MAX_ACTIVE = 20


def normalize(coin: str) -> str | None:
    c = coin.strip().upper().replace("/USDT", "").replace("USDT", "")
    return f"{c}/USDT" if re.fullmatch(r"[A-Z0-9]{2,10}", c) else None


def add(symbol: str, level: float, current: float) -> dict:
    if not level > 0 or level != level:
        raise ValueError("The price must be a number above 0.")
    if abs(level / current - 1) < 0.0005:
        raise ValueError("That is almost the current price. Pick a different level.")
    if len(active()) >= MAX_ACTIVE:
        raise ValueError(f"You already have {MAX_ACTIVE} alerts. Delete one first.")
    direction = "above" if level > current else "below"
    with journal._conn() as c:
        aid = c.execute("INSERT INTO price_alerts(symbol,direction,level,created) VALUES(?,?,?,?)",
                        (symbol, direction, level, time.time())).lastrowid
    return dict(id=aid, symbol=symbol, direction=direction, level=level)


def active():
    with journal._conn() as c:
        return c.execute("SELECT id,symbol,direction,level FROM price_alerts WHERE triggered IS NULL ORDER BY id").fetchall()


def history(limit=10):
    with journal._conn() as c:
        return c.execute("SELECT id,symbol,direction,level,price_at_trigger,triggered FROM price_alerts "
                         "WHERE triggered IS NOT NULL ORDER BY triggered DESC LIMIT ?", (limit,)).fetchall()


def delete(aid: int) -> bool:
    with journal._conn() as c:
        return c.execute("DELETE FROM price_alerts WHERE id=? AND triggered IS NULL", (aid,)).rowcount == 1


def check(prices: dict) -> list[dict]:
    """prices: {symbol: last price}. Returns alerts that were just reached and switches them off."""
    hit = []
    with journal._conn() as c:
        for aid, sym, d, lvl in c.execute("SELECT id,symbol,direction,level FROM price_alerts WHERE triggered IS NULL").fetchall():
            p = prices.get(sym)
            if p is None:
                continue
            if (d == "above" and p >= lvl) or (d == "below" and p <= lvl):
                c.execute("UPDATE price_alerts SET triggered=?, price_at_trigger=? WHERE id=?", (time.time(), p, aid))
                hit.append(dict(id=aid, symbol=sym, direction=d, level=lvl, price=p))
    return hit


def money(x):
    return f"${x:,.2f}" if x < 100 else f"${x:,.0f}"


def message(h: dict) -> str:
    word = "reached or gone above" if h["direction"] == "above" else "reached or fallen below"
    return (f"🔔 Price alert: {h['symbol'].split('/')[0]} is {money(h['price'])}. "
            f"It has {word} your level {money(h['level'])}.\n"
            "This only says the price was touched. It is not a buy or sell signal by itself.\n"
            f"Chart: {tv_link(h['symbol'])}\n\n{FOOTER}")


def describe(rows) -> str:
    if not rows:
        return "No active price alerts. Add one like this: /alert BTC 90000"
    return "\n".join(f"#{i}  {s.split('/')[0]} {d} {money(l)}" for i, s, d, l in rows)
