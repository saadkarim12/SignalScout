"""A tiny local web page (no extra software needed) to see SignalScout in your browser.

Run:  make web      then open  http://127.0.0.1:8501
It only runs on YOUR computer (127.0.0.1) - nobody else can reach it.
"""
import html
import pandas as pd
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .config import ROOT, load_config
from .scan import run_scan
from .alerts import format_alert, tv_link
from .charts import make_chart
from . import settings

HOST, PORT = "127.0.0.1", 8501
STATE = {"results": [], "when": None}
LOCK = threading.Lock()

CSS = """
body{font-family:-apple-system,Helvetica,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d1d1f}
h1{margin-bottom:0} .sub{color:#666;margin-top:4px}
nav a,button{display:inline-block;padding:8px 14px;margin:4px 6px 4px 0;border-radius:8px;border:1px solid #ccc;
background:#f5f5f7;color:#000;text-decoration:none;font-size:15px;cursor:pointer}
table{border-collapse:collapse;width:100%;margin:12px 0} th,td{padding:8px;border-bottom:1px solid #e5e5e5;text-align:right}
th:first-child,td:first-child{text-align:left} th{font-size:13px;color:#555}
.STRONG{background:#d7f5dd}.WATCH{background:#fff4c9}.SKIP{background:#eee}.NO_TRADE{background:#fbdcdc}
.box{background:#f5f5f7;border-radius:10px;padding:12px 16px;margin:14px 0;font-size:14px}
pre{background:#111;color:#eee;padding:12px;border-radius:8px;overflow:auto;font-size:13px}
.ok{color:#1a7f37}.no{color:#c62828}.info{color:#555}
"""

WORDS = """
<div class=box><b>Learn: what the words mean</b><ul>
<li><b>Score</b> - the coin gets points for each good sign. 10 is the most.</li>
<li><b>STRONG</b> (8+) = a very good moment to consider buying. Risk only 1% of your money.<br>
<b>WATCH</b> (6-7) = okay, keep an eye on it. Risk only 0.5%.<br>
<b>SKIP</b> = not good enough. <b>NO_TRADE</b> = a must-have rule failed, so do not buy.</li>
<li><b>Entry</b> = the price to buy at (today's price).</li>
<li><b>Stop</b> = the price where you sell to keep your loss small if you were wrong. Always decide this BEFORE buying.</li>
<li><b>Target</b> = the price where you sell to take your profit.</li>
<li><b>R:R</b> = how much you can win compared to what you can lose. 2.0 means you can win 2 dollars for every 1 dollar you risk.</li></ul>
<b>Golden habit:</b> never risk more than 1% of your money on one trade. Signal, not advice. You decide.</div>"""


def page(title, body):
    return (f"<!doctype html><meta charset=utf-8><title>{title}</title><style>{CSS}</style>"
            "<h1>SignalScout</h1><p class=sub>Your trading helper. It only looks at prices. It never buys or sells for you.</p>"
            "<nav><a href='/portfolio'><b>Trend portfolio</b></a><a href='/'>Market check</a><a href='/news'>News</a><a href='/settings'>Settings</a><a href='/practice'>Practice trades</a><a href='/tutorial'>Tutorial</a><a href='/alerts'>Price alerts</a><a href='/weekly'>Weekly buys</a><a href='/mode'>Market mode</a><a href='/backtest'>Backtest</a><a href='/alert'>Alert preview</a><a href='/tests'>Safety check</a></nav>" + body)


def fmt(x):
    return f"{x:,.6g}" if x else "-"


def home():
    r = STATE["results"]
    btn = "<form action=/scan method=post><button>Check the market now (takes about 30 seconds, please wait)</button></form>"
    if not r:
        return page("SignalScout", btn + "<p>Nothing checked yet. Press the button above.</p>" + WORDS)
    rows = "".join(
        f"<tr class={x.verdict}><td><a href='/coin/{x.symbol.split('/')[0]}'>{x.symbol}</a></td><td><a href='/coin/{x.symbol.split('/')[0]}#why'>{x.score}/10</a></td>"
        f"<td>{x.verdict}</td><td>{fmt(x.entry)}</td><td>{fmt(x.stop)}</td><td>{fmt(x.target)}</td><td>{x.rr:.1f}</td></tr>"
        for x in r)
    return page("SignalScout", f"{btn}<p>Last checked: {STATE['when']:%Y-%m-%d %H:%M} (click a coin to see why it got its score)</p>"
                "<table><tr><th>Coin<th>Score<th>Verdict<th>Entry<th>Stop<th>Target<th>R:R</tr>" + rows + "</table>" + WORDS)


def coin(base):
    x = next((c for c in STATE["results"] if c.symbol == f"{base}/USDT"), None)
    if not x:
        return page("Coin", "<p>No saved market check for this coin yet (it is cleared when the app restarts). "
                    "Go to <a href='/news'>News</a><a href='/practice'>Practice trades</a>, click <b>Check the market now</b>, then click the coin again.</p>")
    def why_extra(c):
        if c.name == "news":
            return f" <a href='/news?coin={base}'>See all news for {base} &rarr;</a>"
        return ""

    items = "".join(
        f"<li class={'info' if c.max_points == 0 else 'ok' if c.passed else 'no'}><details id='{c.name}'><summary>{'ℹ' if c.max_points == 0 else '✔' if c.passed else '✘'} {html.escape(c.text)} "
        f"<small>({'info only, no points' if c.max_points == 0 else str(c.points) + '/' + str(c.max_points) + (', MUST' if c.must else '')})</small> <u style='font-size:12px'>why?</u></summary>"
        f"<div style='color:#333;background:#f5f5f7;border-radius:8px;padding:8px 12px;margin:6px 0;font-size:14px'>"
        f"{html.escape(c.detail or 'No extra detail.')}{why_extra(c)}</div></details></li>" for c in x.checks)
    size = ""
    if x.size:
        size = (f"<div class=box><b>How much to buy</b>: about ${x.size['usd']:,.0f} "
                f"({x.size['coins']:.6g} coins). If it drops to your Stop, you lose only about ${x.size['max_loss']:,.2f}.</div>")
    sug = ""
    if x.verdict in ("STRONG", "WATCH"):
        from .advice import suggest
        from .data import make_exchange
        from .trend import live_report
        cfg = load_config()
        try:
            ex = make_exchange(cfg["data_exchange"])
            live = float(ex.fetch_ticker(x.symbol)["last"])
            mode = live_report(ex, cfg["trend"])["mode"]
        except Exception:
            live, mode = None, None
        a = suggest(x, live, mode, cfg["checklist"]["min_rr"])
        col = "#d7f5dd" if a["label"] == "BUY" else "#fff4c9"
        sug = (f"<div style='background:{col};border-radius:10px;padding:12px 16px;margin:14px 0'>"
               f"<b style='font-size:20px'>Advisor view: {a['label']}</b> <small>(for your reference only)</small>"
               + ("<p><b>Why not yet:</b></p><ul>" + "".join(f"<li>{html.escape(t)}</li>" for t in a["bad"]) + "</ul>" if a["bad"] else "")
               + ("<p><b>What is fine:</b></p><ul>" + "".join(f"<li>{html.escape(t)}</li>" for t in a["good"]) + "</ul>" if a["good"] else "")
               + "<small>Buy needs all five: signal, bounce candle, price close to the signal, reward vs risk 2+, "
                 "and Market mode IN. This is the advisor view, for your reference only. It does not change your 20-trade test. You decide.</small></div>")
    try:
        from . import news as nm
        from datetime import datetime, timezone
        hs = nm.about(x.symbol, nm.get_news()["headlines"], datetime.now(timezone.utc))
        newsbox = ("<div class=box><b>Latest headlines that mention " + base + "</b> (CoinDesk, Cointelegraph, The Block)<ul>"
                   + ("".join(f"<li>{h['time']:%d %b %H:%M} - <a href='{html.escape(h['link'])}' target=_blank rel=noopener>"
                              f"{html.escape(h['title'])}</a> ({h['source']})</li>" for h in hs) or "<li>None in the last 48 hours.</li>")
                   + "</ul></div>")
    except Exception:
        newsbox = ""
    return page(base, f"<h2>{x.symbol}: {x.score}/10 - {x.verdict}</h2>{sug}"
                f"<p>Entry {fmt(x.entry)} | Stop {fmt(x.stop)} | Target {fmt(x.target)} | R:R {x.rr:.1f}</p>"
                f"<h3 id='why'>Why this score? Click any line to see the numbers behind it</h3><ul>{items}</ul>{size}<p><a href='{tv_link(x.symbol)}' target=_blank rel=noopener>Open {x.symbol} in TradingView &rarr;</a></p>"
                f"{newsbox}<a href='javascript:history.back()'>&larr; back</a>")


def _first_signal():
    return next((x for x in STATE["results"] if x.verdict in ("STRONG", "WATCH")), None)


def alert():
    x = _first_signal()
    if not x:
        return page("Alert", "<p>No STRONG or WATCH coin yet. Do a market check first (Market check page). "
                    "This page shows the message you would get on your phone.</p>")
    return page("Alert", "<h2>This is what Telegram will send you</h2>"
                f"<pre>{html.escape(format_alert(x, settings.get_account()))}</pre><img src='/alert.png' width=700>")


def _latest(ext):
    fs = sorted((ROOT / "reports").glob(f"backtest_*.{ext}"))
    return fs[-1] if fs else None


def backtest():
    f = _latest("md")
    if not f:
        return page("Backtest", "<p>No backtest yet. Run <code>make backtest</code> (about 1-2 minutes).</p>")
    return page("Backtest", f"<pre style='white-space:pre-wrap'>{html.escape(f.read_text())}</pre>"
                "<img src='/backtest.png' width=800>")


def mode_page():
    from .trend import live_report, format_mode
    from .data import make_exchange
    cfg = load_config()
    rep = live_report(make_exchange(cfg["data_exchange"]), cfg["trend"])
    rows = ""
    f = sorted((ROOT / "reports").glob("trend_*.md"))
    note = f"<p><a href='/trendreport'>See the 3-year test behind this rule</a></p>" if f else ""
    return page("Market mode", f"<h2>Is the big trend up or down?</h2><pre style='white-space:pre-wrap'>"
                f"{html.escape(format_mode(rep))}</pre>{note}")


def trendreport():
    f = sorted((ROOT / "reports").glob("trend_*.md"))
    if not f:
        return page("Trend test", "<p>No report yet. Run <code>make trend-backtest</code>.</p>")
    return page("Trend test", f"<pre style='white-space:pre-wrap'>{html.escape(f[-1].read_text())}</pre>"
                f"<img src='/trend.png' width=800>")


def weekly_page():
    from . import dca, journal
    from .data import make_exchange, fetch_history
    cfg = load_config()
    ex = make_exchange(cfg["data_exchange"])
    amt = settings.get_dca_amount()
    h = dca.simulate_history(fetch_history(ex, "BTC/USDT", "1d", 4), amt, cfg["dca"]["weekday"], cfg["trend"]["sma_days"])
    p, m = h["plain"], h["mode"]
    row = lambda n, a, b, c, d: f"<tr><td>{n}<td>${a:,.0f}<td>${b:,.0f}<td>${c:,.0f}<td>{d*100:+.0f}%"
    hist = ("<table><tr><th>Plan<th>Money put in<th>Worth now<th>Total (incl. cash kept)<th>Gain on total"
            + row("Plain: buy every week", p["invested"], p["value"], p["value"], p["value"] / p["invested"] - 1)
            + row("Cautious: skip when mode is OUT", m["invested"], m["value"], m["wealth"], m["wealth"] / (p["invested"]) - 1)
            + "</table>")
    price = float(ex.fetch_ticker("BTC/USDT")["last"])
    mine = dca.format_summary(dca.summarize(journal.dca_rows(), price))
    return page("Weekly buys", f"<h2>Weekly buying with ${amt:,.0f} of BTC</h2>"
                f"<div class=box><b>What it is:</b> buy the same small amount every week, no guessing. "
                f"We tested {h['weeks']} weeks of real history ({h['start']:%Y-%m-%d} to {h['end']:%Y-%m-%d}) with the same ${amt:,.0f} each week.</div>"
                f"{hist}<div class=box><b>What this teaches:</b> skipping weeks when the trend was down "
                f"({h['skipped']} of {h['weeks']} weeks) kept cash safe but ended with less money, because buying in "
                "downtrends gets cheap coins. So the Market mode filter did NOT improve weekly buying. "
                "Past results do not promise future results.</div>"
                f"<h3>Your diary (pretend buys)</h3><pre style='white-space:pre-wrap'>{html.escape(mine)}</pre>"
                "<form action=/weeklylog method=post><button>Log this week now (pretend)</button></form>")


def alerts_page(msg=""):
    from . import pricealerts as pa
    rows = "".join(f"<tr><td>#{i}<td>{s.split('/')[0]}<td>{d}<td>{fmt(l)}"
                   f"<td><form action=/alerts/delete method=post style='margin:0'><input type=hidden name=id value={i}>"
                   "<button>Remove</button></form>" for i, s, d, l in pa.active())
    done = "".join(f"<tr><td>#{i}<td>{s.split('/')[0]}<td>{d}<td>{fmt(l)}<td>reached at {fmt(p)}"
                   for i, s, d, l, p, t in pa.history())
    note = f"<div class=box>{html.escape(msg)}</div>" if msg else ""
    return page("Price alerts", f"<h2>Tell me when a price is reached</h2>{note}"
                "<form action=/alerts/add method=post>Coin <input name=coin value=BTC size=6> "
                "Price (USD) <input name=level size=10 placeholder=90000> <button>Add alert</button></form>"
                "<p>You get one message in Slack (and Telegram if connected), then the alert switches itself off. "
                "It only says the price was touched. It is not a buy or sell signal by itself. "
                "Checked every 5 minutes while the reminders window is running.</p>"
                "<h3>Active</h3><table><tr><th>#<th>Coin<th>When<th>Price<th>"
                + (rows or "<tr><td colspan=5>None yet</td></tr>") + "</table>"
                "<h3>Already reached</h3><table>" + (done or "<tr><td colspan=5>None yet</td></tr>") + "</table>")


def md_to_html(md: str) -> str:
    """Tiny converter for our own tutorial file (headings, lists, bold)."""
    import re
    out, in_ul, in_ol = [], False, False

    def close():
        nonlocal in_ul, in_ol
        out.append("</ul>" if in_ul else "</ol>" if in_ol else "")
        in_ul = in_ol = False

    for line in md.splitlines():
        t = html.escape(line)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        if line.startswith("- "):
            if not in_ul:
                close(); out.append("<ul>"); in_ul = True
            out.append(f"<li>{t[2:]}</li>")
        elif re.match(r"\d+\. ", line):
            if not in_ol:
                close(); out.append("<ol>"); in_ol = True
            out.append(f"<li>{re.sub(r'^\d+\. ', '', t)}</li>")
        else:
            close()
            if line.startswith("## "):
                out.append(f"<h2>{t[3:]}</h2>")
            elif line.startswith("# "):
                out.append(f"<h2>{t[2:]}</h2>")
            elif line.strip():
                out.append(f"<p>{t}</p>")
    close()
    return "".join(out)


def tutorial():
    return page("Tutorial", md_to_html((ROOT / "docs" / "TUTORIAL.md").read_text()))


def practice_page(msg=""):
    from . import practice
    from .data import make_exchange
    cfg = load_config()
    st = practice.stats()
    pct = min(100, st["done"] * 100 // st["goal"])
    bar = (f"<div style='background:#e5e5e5;border-radius:6px;height:14px;width:100%'>"
           f"<div style='background:#1a7f37;height:14px;border-radius:6px;width:{pct}%'></div></div>")
    note = f"<div class=box>{html.escape(msg)}</div>" if msg else ""
    ex = make_exchange(cfg["data_exchange"])

    def now_price(sym):
        try:
            return float(ex.fetch_ticker(sym)["last"])
        except Exception:
            return None

    # 0. market now (plain words)
    try:
        from .trend import live_report
        from .sentiment import fear_greed
        tk = ex.fetch_tickers(["BTC/USDT"] + [t["symbol"] for t in practice.open_trades()])
        mode = live_report(ex, cfg["trend"])["mode"]
        fg = fear_greed()
        b = tk["BTC/USDT"]
        d24 = b.get("percentage") or 0
        mood = "rising" if d24 > 0.5 else "falling" if d24 < -0.5 else "flat"
        lines = [f"Bitcoin: {fmt(b['last'])} ({d24:+.1f}% in the last 24 hours) - today it is <b>{mood}</b>.",
                 f"Big trend: Market mode is <b>{mode['mode']}</b> (Bitcoin is {abs(mode['gap_pct']):.0f}% "
                 f"{'above' if mode['mode'] == 'IN' else 'below'} its 200-day average)."]
        if fg:
            lines.append(f"Mood: Fear &amp; Greed is {fg[0]} ({fg[1]}). Under 35 = scared market, over 65 = greedy market.")
        for t in practice.open_trades():
            x = tk.get(t["symbol"])
            if x and x.get("percentage") is not None:
                lines.append(f"{t['symbol']}: {x['percentage']:+.1f}% in the last 24 hours.")
        now_box = "<div class=box><b>Market right now</b><br>" + "<br>".join(lines) + "</div>"
    except Exception:
        now_box = "<div class=box>Market summary is not available right now. Try again in a minute.</div>"
    # 1. signals
    from .advice import suggest, one_line
    sig = [x for x in STATE["results"] if x.verdict in ("STRONG", "WATCH") and x.entry]
    try:
        live = {k: v["last"] for k, v in ex.fetch_tickers([x.symbol for x in sig]).items()} if sig else {}
    except Exception:
        live = {}
    try:
        _mode = mode
    except NameError:
        _mode = None
    adv = {x.symbol: suggest(x, live.get(x.symbol), _mode, cfg["checklist"]["min_rr"]) for x in sig}
    if STATE["results"]:
        rows = "".join(
            f"<tr class={x.verdict}><td><a href='/coin/{x.symbol.split('/')[0]}'>{x.symbol}</a><td>{x.verdict}<td><a href='/coin/{x.symbol.split('/')[0]}#why'>{x.score}/10</a>"
            f"<td><b>{adv[x.symbol]['label']}</b><br><small>{html.escape(one_line(adv[x.symbol]))}</small><td>{fmt(x.entry)}<td>{fmt(x.stop)}<td>{fmt(x.target)}<td>{x.rr:.1f}"
            f"<td><a href='{tv_link(x.symbol)}' target=_blank rel=noopener>Chart</a>"
            f"<td><form action=/practice/log method=post style='margin:0'><input type=hidden name=symbol value='{x.symbol}'>"
            "<button>Log pretend buy</button></form>" for x in sig)
        sigs = ("<table><tr><th>Coin<th>Verdict<th>Score<th>Advisor view (reference only)<th>Buy price (last candle)<th>Stop<th>Target<th>R:R<th>Chart<th>"
                + (rows or "<tr><td colspan=10>No STRONG or WATCH coin right now. That is normal. Waiting is part of the plan.</td></tr>")
                + "</table>")
    else:
        sigs = "<p>Press the button to check the market first.</p>"
    # 2. open trades
    orows = ""
    for t in practice.open_trades():
        p = now_price(t["symbol"])
        link = f"<a href='/coin/{t['symbol'].split('/')[0]}'>{t['symbol']}</a>"
        orows += (f"<tr><td>#{t['id']}<td>{link}<td>{fmt(t['entry'])}<td>{fmt(t['stop'])}<td>{fmt(t['target'])}"
                  f"<td>{fmt(p) if p else '-'}<td>{(p / t['entry'] - 1) * 100:+.1f}%" if p else
                  f"<tr><td>#{t['id']}<td>{link}<td>{fmt(t['entry'])}<td>{fmt(t['stop'])}<td>{fmt(t['target'])}<td>-<td>-")
    open_tbl = ("<table><tr><th>#<th>Coin<th>Pretend buy<th>Stop (loss)<th>Target (win)<th>Price now<th>Change"
                + (orows or "<tr><td colspan=7>None open.</td></tr>") + "</table>")
    # 3. finished
    crow = "".join(f"<tr class={'STRONG' if t['status'] == 'win' else 'NO_TRADE'}><td>#{t['id']}<td><a href='/coin/{t['symbol'].split('/')[0]}'>{t['symbol']}</a>"
                   f"<td>{t['reason']}<td>{t['result_r']:+.2f}R<td>{'+' if t['usd_result'] >= 0 else '-'}${abs(t['usd_result']):,.0f}"
                   for t in practice.closed_trades())
    done_tbl = ("<table><tr><th>#<th>Coin<th>How it ended<th>Result<th>Pretend money"
                + (crow or "<tr><td colspan=5>None finished yet.</td></tr>") + "</table>")
    return page("Practice trades", f"<h2>Practice: {st['goal']} pretend trades</h2>{note}"
                f"<div class=box><b>Your progress: {st['done']} of {st['goal']} finished</b> "
                f"({st['wins']} won, {st['losses']} lost, total {st['total_r']:+.2f}R, pretend money {'+' if st['dollars'] >= 0 else '-'}${abs(st['dollars']):,.0f})"
                f"<br>{bar}<br>{html.escape(practice.verdict_text(st))}"
                + ("<br><small>Did the advisor view help? " + "; ".join(
                    f"{k}: {v['n']} finished, {v['wins']} won, total {v['total_r']:+.1f}R"
                    for k, v in practice.by_suggestion().items()) + "</small>" if practice.closed_trades() else "")
                + "</div>"
                "<div class=box style='background:#fff4c9'><b>Status: paused as the main strategy.</b> The first 9 practice trades "
                "all hit their stop (-11R), and the 3-year backtest was also negative. The strategy we now follow is the "
                "<a href='/portfolio'>Trend portfolio</a>. You can keep logging here for learning, but do not trade this method with real money.</div>"
                "<div class=box><b>How this works in 4 steps</b><ol>"
                "<li>Press <b>Check the market now</b>. Coins marked STRONG or WATCH are signals.</li>"
                "<li>Click <b>Log pretend buy</b> on a signal. It saves the buy price, the stop and the target.</li>"
                "<li>Wait. SignalScout checks the price every 5 minutes. You do nothing.</li>"
                "<li>When the stop or target is touched, you get a Slack message with the result.</li></ol>"
                "<b>Golden rule:</b> log EVERY signal you get, not only the ones you like. Otherwise the test is not honest.</div>"
                + now_box + "<form action=/practice/scan method=post><button>Check the market now (about 30 seconds)</button></form>"
                f"<h3>1. Signals right now</h3>{sigs}<h3>2. Your open pretend trades</h3>{open_tbl}"
                f"<h3>3. Finished trades</h3>{done_tbl}"
                "<div class=box><b>Words:</b> Stop = the price where the pretend trade is closed as a loss. "
                "Target = where it is closed as a win. R = your result in units of risk (+2R means you won twice what you risked; "
                "-1R means you lost what you risked).</div>")


DEFAULT_COINS = ["BTC", "ETH", "BNB", "XRP", "SOL", "DOGE", "ADA", "AVAX", "LINK", "UNI", "SUI", "NEAR"]


def news_page(coin=None):
    """News dashboard: general market news, plus news for one coin with the reason behind its news score."""
    from . import news as nm
    from .events import upcoming, load_events
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    d = nm.get_news()
    heads = d["headlines"]
    coins = sorted({x.symbol.split("/")[0] for x in STATE["results"]}) or DEFAULT_COINS
    coin = (coin or "").upper() or None
    nav = "<a href='/news'><b>General news</b></a>" if not coin else "<a href='/news'>General news</a>"
    nav += "".join(f"<a href='/news?coin={c}'>{'<b>' + c + '</b>' if c == coin else c}</a>" for c in coins)
    ok = "".join(f"<li class=ok>{html.escape(x)}</li>" for x in d["ok"])
    bad = "".join(f"<li class=no>{html.escape(x)}</li>" for x in d["bad"])
    src = (f"<details><summary>Sources ({len(d['ok'])} working{', ' + str(len(d['bad'])) + ' with problems' if d['bad'] else ''}) - "
           f"updated {datetime.fromisoformat(d['fetched']):%H:%M} UTC</summary><ul>{ok}{bad}</ul>"
           "<form action=/news/refresh method=post><button>Refresh now</button></form></details>")

    def hrow(h):
        flag = nm.RISK.search(h["title"]) or nm.MARKET_RISK.search(h["title"]) or h.get("cat") == "delisting"
        tag = {"delisting": "delisting", "listing": "new listing", "news": "Binance news"}.get(h.get("cat"), "")
        return (f"<tr class={'NO_TRADE' if flag else ''}><td>{h['time']:%d %b %H:%M}<td>{html.escape(h['source'])}"
                f"<td><a href='{html.escape(h['link'])}' target=_blank rel=noopener>{html.escape(h['title'])}</a>"
                f"<td>{tag}{' / risk word' if flag and h.get('cat') != 'delisting' else ''}")

    head = "<tr><th>Time (UTC)<th>Source<th>Headline<th>Tag"
    explain = ("<p>A coin gets its <b>news point</b> when there is no big scheduled event in the next 24 hours and no risky headline: "
               "one that names the coin (or a big platform like Binance or Tether) together with a serious word such as hack, exploit "
               "or delisting. A Binance delisting notice that names the coin counts for 7 days. Red rows contain a risk word. "
               "You judge them, the app only warns.</p>")

    if coin:
        sym = f"{coin}/USDT"
        evs = upcoming(load_events() + d["events"], now, 24)
        flags = nm.risky(sym, heads, now)
        score = 0 if (evs or flags) else 1
        col = "#d7f5dd" if score else "#fbdcdc"
        lines = ["<li><b>Big scheduled events in the next 24 hours:</b> " + (
            "; ".join(f"{html.escape(e['name'])} ({e['time']:%a %d %b %H:%M} UTC)" for e in evs) if evs else "none") + "</li>",
                 "<li><b>Risky headlines about " + coin + " (or Binance/Tether-type incidents):</b> " + (
                     "<ul>" + "".join(f"<li><a href='{html.escape(h['link'])}' target=_blank rel=noopener>{html.escape(h['title'])}</a> "
                                     f"({html.escape(h['source'])}, {h['time']:%d %b %H:%M} UTC)</li>" for h in flags) + "</ul>"
                     if flags else "none found") + "</li>",
                 "<li><b>Sources checked:</b> " + (", ".join(html.escape(x) for x in d["ok"]) or "none reachable") + "</li>"]
        if d["bad"]:
            lines.append("<li class=no><b>Not checked:</b> " + "; ".join(html.escape(x) for x in d["bad"]) + "</li>")
        mine = nm.about(sym, heads, now)
        rows = "".join(hrow(h) for h in mine) or "<tr><td colspan=4>No headline in the last 7 days names " + coin + ".</td></tr>"
        full = (f"<p><a href='/coin/{coin}#news'>See the full score for {coin} &rarr;</a></p>"
                if any(x.symbol == sym for x in STATE["results"]) else "")
        body = (f"<h2>News for {coin}</h2><div style='background:{col};border-radius:10px;padding:12px 16px;margin:14px 0'>"
                f"<b style='font-size:20px'>News score: {score} of 1</b><ul>{''.join(lines)}</ul></div>{full}"
                f"<h3>Headlines that mention {coin} (last 7 days)</h3><table>{head}{rows}</table>{explain}")
    else:
        ev = [e for e in d["events"] if e["time"] > now - nm.timedelta(hours=2)][:8]
        evrows = "".join(f"<tr><td>{e['time']:%a %d %b %H:%M} UTC ({(e['time'] + nm.timedelta(hours=4)):%H:%M} UAE)<td>{html.escape(e['name'])}"
                         f"<td>{e['source']}<td>{'<b>within 24h</b>' if e['time'] - now < nm.timedelta(hours=24) else ''}" for e in ev)
        media = [h for h in heads if not h.get("cat")][:20]
        bn = lambda cat: "".join(hrow(h) for h in heads if h.get("cat") == cat)[:100000]
        body = ("<h2>General news and big events</h2>" + explain
                + "<h3>Next big scheduled events</h3><table><tr><th>When<th>Event<th>Source<th>"
                + (evrows or "<tr><td colspan=4>None found.</td></tr>") + "</table>"
                + f"<h3>Latest crypto headlines</h3><table>{head}{''.join(hrow(h) for h in media)}</table>"
                + "<h3>Binance official: delistings (most important for risk)</h3><table>" + head + (bn("delisting") or "<tr><td colspan=4>None</td></tr>") + "</table>"
                + "<h3>Binance official: new listings and news</h3><table>" + head + (bn("listing") + bn("news")) + "</table>")
    return page("News", f"<div class=box><b>Pick a coin to see its news</b><br>{nav}</div>{src}{body}")


def settings_page(msg=""):
    note = f"<div class=box>{html.escape(msg)}</div>" if msg else ""
    a, w = settings.get_account(), settings.get_dca_amount()
    return page("Settings", f"<h2>Your numbers</h2>{note}"
                "<div class=box>These two numbers are used for position sizes and the weekly buy. "
                "Put in your <b>real</b> numbers. Everything on the practice pages is pretend, but the size of a trade is worked out from them.</div>"
                "<form action=/settings/save method=post><p>Account size in USD (your learning budget): "
                f"<input name=account value='{a:g}' size=10></p>"
                f"<p>Weekly buy amount in USD: <input name=weekly value='{w:g}' size=10></p>"
                "<button>Save</button></form>"
                "<div class=box><b>Good to know:</b> a trade risks at most 1% of the account (STRONG) or 0.5% (WATCH), and one trade never uses "
                "more than 25% of it. Trades already logged keep the size they were logged with.</div>")


_TP = {"t": 0, "data": None, "bt": None}


def _tp_data():
    import time as _t
    from .scheduler import load_tp_data
    from .data import make_exchange
    from . import trendportfolio as tpm
    if _TP["data"] is None or _t.time() - _TP["t"] > 1800:
        cfg = load_config()
        _TP["data"] = load_tp_data(make_exchange(cfg["data_exchange"]), cfg)
        _TP["bt"] = tpm.backtest_summary(_TP["data"])
        _TP["t"] = _t.time()
    return _TP["data"], _TP["bt"]


def portfolio_page():
    from . import trendportfolio as tp
    cfg = load_config()
    t = cfg["trend_portfolio"]
    data, bt = _tp_data()
    st = tp.live_status(data)
    acct = settings.get_account()
    slice_usd = acct / len(st)
    cards = ""
    for sym, v in st.items():
        base = sym.split("/")[0]
        rows = "".join(f"<tr class={'STRONG' if ok else 'NO_TRADE'}><td>{r}<td>{'IN' if ok else 'OUT'}<td style='text-align:left'>{html.escape(v['details'][r])}"
                       for r, ok in v["votes"].items())
        change = "" if abs(v["exposure"] - v["prev_exposure"]) < 1e-9 else f" <b>(changed from {v['prev_exposure'] * 100:.0f}%)</b>"
        cards += (f"<div class=box><b style='font-size:18px'>{base}: hold {v['exposure'] * 100:.0f}% of its slice</b>{change}<br>"
                  f"Price {fmt(v['price'])} at the close of {v['date']:%Y-%m-%d}. Slice ${slice_usd:,.0f} -> about "
                  f"<b>${slice_usd * v['exposure']:,.0f} invested</b>, ${slice_usd * (1 - v['exposure']):,.0f} in cash."
                  f"<table><tr><th>Rule<th>Says<th style='text-align:left'>Numbers{rows}</table></div>")
    se, he = tp.paper_curve(data, t["start_date"])
    live = ""
    if len(se) >= 2:
        live = (f"<p>Pretend ${acct:,.0f} since {t['start_date']}: <b>strategy ${acct * se.iloc[-1]:,.0f}</b> versus "
                f"buy-and-hold ${acct * he.iloc[-1]:,.0f} ({len(se)} days).</p>")
    else:
        live = f"<p>The forward test starts on {t['start_date']}. Results will appear here day by day.</p>"
    a, b, c, d = bt["strategy_is"], bt["strategy_oos"], bt["hold_is"], bt["hold_oos"]
    row = lambda n, x: f"<tr><td>{n}<td>{x['ret'] * 100:+,.0f}%<td>{x['dd'] * 100:.0f}%<td>{x['sharpe']:.2f}"
    yrs = "".join(f"<tr><td>{y}<td>{s_ * 100:+.0f}%<td>{h_ * 100:+.0f}%" for y, (s_, h_) in bt["years"].items())
    return page("Trend portfolio", "<h2>Trend portfolio: the strategy that survived the tests</h2>"
                "<div class=box><b>The idea in one paragraph:</b> Hold Bitcoin and Ethereum only while their trends are up, and step "
                "out in downtrends. Four simple rules vote every day. The more rules say IN, the more of that coin's slice you hold; "
                "the rest stays cash. You check once a day, and the app messages you when something changes. "
                "It does not try to buy the dip or pick the exact bottom.</div>"
                f"<h3>Today</h3>{cards}"
                "<h3>Pretend test going forward (live)</h3>" + live
                + "<img src='/portfolio.png' width=820>"
                "<h3>What 9 years of history showed (BTC + ETH, fees included)</h3>"
                "<table><tr><th>Period<th>Total return<th>Worst drop<th>Sharpe"
                + row("2017-2021 trend strategy", a) + row("2017-2021 buy and hold", c)
                + row("2022-now trend strategy (held out)", b) + row("2022-now buy and hold", d) + "</table>"
                "<h3>Year by year</h3><table><tr><th>Year<th>Strategy<th>Buy and hold" + yrs + "</table>"
                "<div class=box><b>Please read the limits:</b><ul>"
                "<li>It still loses money in bad years (about -20% in 2018 and 2022). It cuts the crashes roughly in half, it does not avoid them.</li>"
                "<li>In strong bull years it earns LESS than holding (for example 2020 and 2021). That is the price of the protection.</li>"
                "<li>Only BTC and ETH, survivors that went up a lot. The future may be different. XRP and ADA did badly with the same rules.</li>"
                "<li>I chose the four-rule vote after seeing single-rule results, so the held-out test is not perfectly clean. "
                "The forward test above is the clean one.</li>"
                "<li>An independent audit reproduced the numbers and found no look-ahead bug. Honest long-run expectation: about 15% to 30% a year, "
                "worst drops of 25% to 45%, and it can sit under water for up to about 2 years. 1 in 5 twelve-month periods lost money.</li>"
                "<li>Fees and slippage are included. Taxes, exchange problems and your own emotions are not.</li></ul>"
                "Signal, not advice. You decide. Only money you can afford to lose.</div>")


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    verdict = "<h2 class=ok>Everything is working correctly</h2>" if p.returncode == 0 else "<h2 class=no>Something is wrong - tell Claude</h2>"
    return page("Tests", verdict + f"<pre>{html.escape(p.stdout + p.stderr)}</pre>"
                "<p>These are small automatic checks that the app's calculations are correct.</p>")


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send(home())
        elif path == "/portfolio":
            self._send(portfolio_page())
        elif path == "/portfolio.png":
            import io
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from . import trendportfolio as tp
            data, bt = _tp_data()
            fig, ax = plt.subplots(figsize=(9, 4))
            ax.plot(bt["se"].index, bt["se"] * 1000, label="Trend portfolio")
            ax.plot(bt["he"].index, bt["he"] * 1000, label="Buy and hold", alpha=0.7)
            ax.axvline(pd.Timestamp("2022-01-01"), color="grey", ls="--")
            ax.set_yscale("log")
            ax.set_title("$1,000 from 2017 (log scale). Dashed line = start of the held-out test")
            ax.legend()
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=100)
            plt.close(fig)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(buf.getvalue())
        elif path == "/settings":
            self._send(settings_page())
        elif path == "/news":
            from urllib.parse import parse_qs
            self._send(news_page(parse_qs(urlparse(self.path).query).get("coin", [None])[0]))
        elif path == "/practice":
            self._send(practice_page())
        elif path == "/tutorial":
            self._send(tutorial())
        elif path == "/alerts":
            self._send(alerts_page())
        elif path == "/weekly":
            self._send(weekly_page())
        elif path == "/mode":
            self._send(mode_page())
        elif path == "/trendreport":
            self._send(trendreport())
        elif path == "/trend.png":
            fs = sorted((ROOT / "reports").glob("trend_*.png"))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(fs[-1].read_bytes() if fs else b"")
        elif path == "/backtest":
            self._send(backtest())
        elif path == "/backtest.png":
            f = _latest("png")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(f.read_bytes() if f else b"")
        elif path == "/alert":
            self._send(alert())
        elif path == "/alert.png":
            x = _first_signal()
            png = make_chart(x.df4h, x.symbol, x.entry, x.stop, x.target) if x else b""
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(png)
        elif path == "/tests":
            self._send(tests())
        elif path.startswith("/coin/"):
            self._send(coin(html.escape(path[6:].upper())))
        else:
            self._send(page("Not found", "<p>Page not found.</p>"), 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/settings/save":
            from urllib.parse import parse_qs
            n = int(self.headers.get("Content-Length") or 0)
            f = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 2000)).decode()).items()}
            try:
                a = float(f.get("account", "").replace(",", "").replace("$", ""))
                w = float(f.get("weekly", "").replace(",", "").replace("$", ""))
                if not (10 <= a <= 10_000_000) or not (1 <= w <= a):
                    raise ValueError
                settings.set_account(a)
                settings.set_dca_amount(w)
                msg = f"Saved. Account size ${a:,.0f}, weekly buy ${w:,.0f}."
            except ValueError:
                msg = "Please enter two numbers: account size (10 to 10,000,000) and a weekly amount that is not bigger than the account."
            return self._send(settings_page(msg))
        if path == "/news/refresh":
            from . import news as nm
            nm.get_news(force=True)
            self.send_response(303)
            self.send_header("Location", "/news")
            self.end_headers()
            return
        if path == "/practice/scan":
            with LOCK:
                STATE["results"], STATE["when"] = run_scan(load_config(), verbose=False), datetime.now()
            self.send_response(303)
            self.send_header("Location", "/practice")
            self.end_headers()
            return
        if path == "/practice/log":
            from urllib.parse import parse_qs
            from . import practice
            from .data import make_exchange
            from .sizing import position_size
            n = int(self.headers.get("Content-Length") or 0)
            sym = parse_qs(self.rfile.read(min(n, 2000)).decode()).get("symbol", [""])[0]
            x = next((r for r in STATE["results"] if r.symbol == sym and r.verdict in ("STRONG", "WATCH")), None)
            try:
                if not x:
                    raise ValueError("Run a market check first, then log from the list.")
                cfg = load_config()
                price = float(make_exchange(cfg["data_exchange"]).fetch_ticker(sym)["last"])
                risk = cfg["verdict"]["strong_risk_pct" if x.verdict == "STRONG" else "watch_risk_pct"]
                usd = position_size(settings.get_account(), risk, price, x.stop, cfg["verdict"]["max_position_pct"])["usd"] if price > x.stop else 0
                from .advice import suggest
                from .trend import live_report
                try:
                    md = live_report(make_exchange(cfg["data_exchange"]), cfg["trend"])["mode"]
                except Exception:
                    md = None
                label = suggest(x, price, md, cfg["checklist"]["min_rr"])["label"]
                t = practice.open_trade(sym, x.verdict, price, x.stop, x.target, usd, suggestion=label)
                msg = (f"Logged pretend trade #{t['id']} (advisor view at the time: {label}, for reference only): {sym} bought at {fmt(price)}. Stop {fmt(x.stop)} (loss), target "
                       f"{fmt(x.target)} (win). Pretend position ${usd:,.0f}. Now just wait. You will get a message when it ends.")
            except ValueError as e:
                msg = str(e)
            except Exception:
                msg = "Could not get the live price right now. Try again in a minute."
            return self._send(practice_page(msg))
        if path in ("/alerts/add", "/alerts/delete"):
            from urllib.parse import parse_qs
            from . import pricealerts as pa
            from .data import make_exchange
            n = int(self.headers.get("Content-Length") or 0)
            f = {k: v[0] for k, v in parse_qs(self.rfile.read(min(n, 2000)).decode()).items()}
            msg = ""
            try:
                if path == "/alerts/delete":
                    msg = "Removed." if pa.delete(int(f.get("id", ""))) else "Could not find that alert."
                else:
                    sym = pa.normalize(f.get("coin", ""))
                    if not sym:
                        raise ValueError("Type a coin like BTC or ETH.")
                    ex = make_exchange(load_config()["data_exchange"])
                    try:
                        cur = float(ex.fetch_ticker(sym)["last"])
                    except Exception:
                        raise ValueError(f"I could not find {sym} on the exchange.")
                    a = pa.add(sym, float(f.get("level", "0").replace(",", "")), cur)
                    msg = f"Added: tell me when {sym.split('/')[0]} goes {a['direction']} {fmt(a['level'])} (now {fmt(cur)})."
            except ValueError as e:
                msg = str(e)
            return self._send(alerts_page(msg))
        if urlparse(self.path).path == "/weeklylog":
            from .scheduler import run_weekly
            from .data import make_exchange
            cfg = load_config()
            run_weekly(make_exchange(cfg["data_exchange"]), cfg)
            self.send_response(303)
            self.send_header("Location", "/weekly")
            self.end_headers()
            return
        if urlparse(self.path).path == "/scan":
            with LOCK:
                STATE["results"], STATE["when"] = run_scan(load_config(), verbose=False), datetime.now()
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"SignalScout page is running: http://{HOST}:{PORT}   (press Ctrl+C to stop)")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
