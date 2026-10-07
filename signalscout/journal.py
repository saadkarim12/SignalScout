"""Small notebook (SQLite) for sent alerts and paper trades."""
import sqlite3
import time
from .config import ROOT

DB = ROOT / "data" / "signalscout.db"


def _conn():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS alerts(symbol TEXT, verdict TEXT, ts REAL)")
    c.execute("""CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, symbol TEXT, kind TEXT, entry REAL,
                 stop REAL, target REAL, usd REAL, ts REAL, status TEXT DEFAULT 'open', result_r REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS dca(week TEXT PRIMARY KEY, ts REAL, mode TEXT, price REAL,
                 amount REAL, action TEXT, units REAL)""")
    for col, typ in (("exit_price", "REAL"), ("exit_ts", "REAL"), ("verdict", "TEXT"), ("note", "TEXT"),
                     ("usd_result", "REAL"), ("reason", "TEXT"), ("suggestion", "TEXT")):
        try:
            c.execute(f"ALTER TABLE trades ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass                                           # column already there
    c.execute("""CREATE TABLE IF NOT EXISTS price_alerts(id INTEGER PRIMARY KEY, symbol TEXT, direction TEXT,
                 level REAL, created REAL, triggered REAL, price_at_trigger REAL)""")
    return c


def already_alerted(symbol: str, hours: int = 24) -> bool:
    with _conn() as c:
        return c.execute("SELECT 1 FROM alerts WHERE symbol=? AND ts>?", (symbol, time.time() - hours * 3600)).fetchone() is not None


def record_alert(symbol: str, verdict: str):
    with _conn() as c:
        c.execute("INSERT INTO alerts VALUES(?,?,?)", (symbol, verdict, time.time()))


def add_trade(symbol, kind, entry, stop, target, usd) -> int:
    with _conn() as c:
        return c.execute("INSERT INTO trades(symbol,kind,entry,stop,target,usd,ts) VALUES(?,?,?,?,?,?,?)",
                         (symbol, kind, entry, stop, target, usd, time.time())).lastrowid


def list_trades(status=None):
    with _conn() as c:
        q = "SELECT id,symbol,kind,entry,stop,target,usd,status,result_r FROM trades"
        return c.execute(q + (" WHERE status=?" if status else ""), (status,) if status else ()).fetchall()


def dca_add(week, mode, price, amount, action, units) -> bool:
    """One row per ISO week. Returns False if this week was already logged."""
    with _conn() as c:
        cur = c.execute("INSERT OR IGNORE INTO dca VALUES(?,?,?,?,?,?,?)",
                        (week, time.time(), mode, price, amount, action, units))
        return cur.rowcount == 1


def dca_rows():
    with _conn() as c:
        return c.execute("SELECT ts,mode,price,amount,action,units FROM dca ORDER BY ts").fetchall()
