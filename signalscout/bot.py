"""Telegram bot. Only answers YOU (the chat ID in .env)."""
import asyncio
from . import net  # noqa: F401  (IPv4 only)
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, ContextTypes, filters

from .alerts import format_alert, FOOTER, money
from .charts import make_chart
from .config import ROOT, load_config
from . import journal, settings
from .scan import run_scan
from .sentiment import fear_greed

load_dotenv(ROOT / ".env")

HELP = """Commands:
/scan - check the market now (top 10)
/coin BTC - see why a coin got its score, with a chart
/mode - is the big trend up (IN) or down (OUT)?
/alert BTC 90000 - tell me when BTC reaches a price
/alerts - your active price alerts
/delalert 3 - remove alert number 3
/weekly - your weekly buy diary and results
/setweekly 50 - change the weekly amount (USD)
/fear - is the market scared or greedy?
/paper BTC - practise: save a pretend trade
/journal - your pretend trades
/report - simple results summary
/settings - your account size and risk
/setaccount 1000 - change your account size (USD)
/help - this list

I only look at prices. I never buy or sell. You decide."""


def cfg_with_account():
    return load_config(), settings.get_account()


async def _scan(cfg):
    cfg = dict(cfg, account_size_usd=settings.get_account())
    return await asyncio.to_thread(run_scan, cfg, False)


async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("Hi! I'm SignalScout. I watch the top coins and message you when a good "
                               "chance appears, and I explain why.\n\nTry /scan or /coin BTC.\n\n" + HELP)


async def help_(u, c):
    await u.message.reply_text(HELP)


async def scan(u, c):
    await u.message.reply_text("Checking the market, about 30 seconds...")
    res = await _scan(load_config())
    if not res:
        return await u.message.reply_text("I could not get market data right now. Not guessing - try later.")
    lines = [f"{x.symbol}  {x.score}/10  {x.verdict}" + (f"  (reward vs risk {x.rr:.1f})" if x.rr else "")
             for x in res[:10]]
    await u.message.reply_text("Top 10:\n" + "\n".join(lines) +
                               "\n\nSTRONG=best, WATCH=okay, SKIP=weak, NO_TRADE=a must-have rule failed.\n" + FOOTER)


async def coin(u, c):
    if not c.args:
        return await u.message.reply_text("Tell me which coin, like: /coin BTC")
    sym = c.args[0].upper() + "/USDT"
    res = await _scan(load_config())
    x = next((r for r in res if r.symbol == sym), None)
    if not x:
        return await u.message.reply_text(f"{sym} is not in today's top 20 list.")
    text = f"{x.symbol}: {x.score}/10 - {x.verdict}\n" + "\n".join(
        ("ℹ️ " if k.max_points == 0 else "✅ " if k.passed else "❌ ") + k.text for k in x.checks) + "\n\n" + FOOTER
    png = await asyncio.to_thread(make_chart, x.df4h, x.symbol, x.entry, x.stop, x.target)
    await u.message.reply_photo(png, caption=text[:1024])


async def mode(u, c):
    from .trend import live_report, format_mode
    from .data import make_exchange
    cfg = load_config()
    rep = await asyncio.to_thread(live_report, make_exchange(cfg["data_exchange"]), cfg["trend"])
    await u.message.reply_text(format_mode(rep))


async def weekly(u, c):
    from . import dca
    from .data import make_exchange
    ex = make_exchange(load_config()["data_exchange"])
    price = float((await asyncio.to_thread(ex.fetch_ticker, "BTC/USDT"))["last"])
    await u.message.reply_text(dca.format_summary(dca.summarize(journal.dca_rows(), price)) +
                               f"\nWeekly amount: {money(settings.get_dca_amount())} (change: /setweekly 50)")


async def setweekly(u, c):
    try:
        v = float(c.args[0])
        assert v > 0
    except Exception:
        return await u.message.reply_text("Like this: /setweekly 50")
    settings.set_dca_amount(v)
    await u.message.reply_text(f"Done. Weekly amount is now {money(v)}.")


async def alert_add(u, c):
    from . import pricealerts as pa
    from .data import make_exchange
    try:
        sym, level = pa.normalize(c.args[0]), float(c.args[1].replace(",", "").replace("$", ""))
        assert sym
        ex = make_exchange(load_config()["data_exchange"])
        cur = float((await asyncio.to_thread(ex.fetch_ticker, sym))["last"])
        a = pa.add(sym, level, cur)
    except ValueError as e:
        return await u.message.reply_text(str(e))
    except Exception:
        return await u.message.reply_text("Like this: /alert BTC 90000  (coin, then the price)")
    await u.message.reply_text(f"Done. I'll tell you once when {sym.split('/')[0]} goes {a['direction']} {money(level)} "
                               f"(now {money(cur)}). Alert #{a['id']}.")


async def alerts_list(u, c):
    from . import pricealerts as pa
    await u.message.reply_text(pa.describe(pa.active()))


async def alert_del(u, c):
    from . import pricealerts as pa
    try:
        ok = pa.delete(int(c.args[0]))
    except Exception:
        return await u.message.reply_text("Like this: /delalert 3")
    await u.message.reply_text("Removed." if ok else "I could not find that active alert.")


async def fear(u, c):
    f = fear_greed()
    if not f:
        return await u.message.reply_text("Could not read the Fear & Greed number right now.")
    await u.message.reply_text(f"Fear & Greed: {f[0]} ({f[1]}).\n0 = very scared market, 100 = very greedy. "
                               "Buying when others are scared often works better than when everyone is excited.")


async def paper(u, c):
    from . import practice
    from .sizing import position_size
    from .data import make_exchange
    if not c.args:
        return await u.message.reply_text("Like this: /paper BTC  (logs a pretend buy from today's signal)")
    sym = c.args[0].upper() + "/USDT"
    cfg = load_config()
    res = await _scan(cfg)
    x = next((r for r in res if r.symbol == sym), None)
    if not x or not x.entry or x.verdict not in ("STRONG", "WATCH"):
        return await u.message.reply_text("That coin has no STRONG or WATCH signal now, so I did not log a pretend trade.")
    price = float((await asyncio.to_thread(make_exchange(cfg["data_exchange"]).fetch_ticker, sym))["last"])
    risk = cfg["verdict"]["strong_risk_pct" if x.verdict == "STRONG" else "watch_risk_pct"]
    try:
        usd = position_size(settings.get_account(), risk, price, x.stop, cfg["verdict"]["max_position_pct"])["usd"]
        t = practice.open_trade(sym, x.verdict, price, x.stop, x.target, usd)
    except (ValueError, ZeroDivisionError) as e:
        return await u.message.reply_text(str(e))
    await u.message.reply_text(f"Saved pretend trade #{t['id']}: {sym} at {money(price)}, stop {money(x.stop)}, "
                               f"target {money(x.target)}. No real money. I will tell you when it ends.")


async def journal_(u, c):
    from . import practice
    o, d = practice.open_trades(), practice.closed_trades()
    lines = [f"OPEN #{t['id']} {t['symbol']} buy {money(t['entry'])} stop {money(t['stop'])} target {money(t['target'])}" for t in o]
    lines += [f"DONE #{t['id']} {t['symbol']} {t['reason']} {t['result_r']:+.2f}R" for t in d[-10:]]
    await u.message.reply_text("\n".join(lines) or "No practice trades yet. Use /paper BTC when there is a signal.")


async def report(u, c):
    from . import practice
    s = practice.stats()
    await u.message.reply_text(f"Practice: {s['done']} of {s['goal']} finished ({s['wins']} won, {s['losses']} lost), "
                               f"total {s['total_r']:+.2f}R, average {s['avg_r']:+.2f}R, {s['open']} still open.\n"
                               + practice.verdict_text(s))


async def settings_(u, c):
    a = settings.get_account()
    await u.message.reply_text(f"Account size: {money(a)}\nRisk per trade: 1% (STRONG) = {money(a * 0.01)}, "
                               f"0.5% (WATCH) = {money(a * 0.005)}\nChange with /setaccount 1000")


async def setaccount(u, c):
    try:
        v = float(c.args[0])
        assert v > 0
    except Exception:
        return await u.message.reply_text("Like this: /setaccount 1000")
    settings.set_account(v)
    await u.message.reply_text(f"Done. Account size is now {money(v)}.")


class RetryRequest(HTTPXRequest):
    """Telegram is slow/flaky on some networks: try each request up to 4 times."""

    async def do_request(self, *a, **k):
        for i in range(4):
            try:
                return await super().do_request(*a, **k)
            except (TimedOut, NetworkError):
                if i == 3:
                    raise
                await asyncio.sleep(2)


def build_app():
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat or "your-" in token:
        raise SystemExit("Missing Telegram details. Copy .env.example to .env and fill in the token and chat ID.")
    kw = dict(connect_timeout=15, read_timeout=20, write_timeout=20)
    app = (Application.builder().token(token).request(RetryRequest(**kw))
           .get_updates_request(RetryRequest(**dict(kw, read_timeout=40))).build())
    only_me = filters.Chat(chat_id=int(chat))
    for name, fn in [("start", start), ("help", help_), ("scan", scan), ("coin", coin), ("fear", fear), ("alert", alert_add), ("alerts", alerts_list), ("delalert", alert_del), ("mode", mode), ("weekly", weekly), ("setweekly", setweekly),
                     ("paper", paper), ("journal", journal_), ("report", report),
                     ("settings", settings_), ("setaccount", setaccount)]:
        app.add_handler(CommandHandler(name, fn, filters=only_me))
    return app


if __name__ == "__main__":
    print("Bot is running. Send /start to it in Telegram. Ctrl+C to stop.")
    build_app().run_polling()
