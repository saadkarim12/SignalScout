"""Every 4 hours (5 minutes after the candle closes, UTC): scan and send NEW alerts only."""
import asyncio
from . import net  # noqa: F401  (IPv4 only)
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telegram import Bot

from .alerts import format_alert
from .charts import make_chart
from .config import ROOT, load_config
from . import journal, settings
from .scan import run_scan
from .trend import live_report, format_mode
from .data import make_exchange
from . import dca as dcamod
from .notify import deliver
from . import pricealerts

load_dotenv(ROOT / ".env")


def pick_new(results):
    """STRONG/WATCH setups we have not already alerted in the last 24 hours."""
    return [r for r in results if r.verdict in ("STRONG", "WATCH") and not journal.already_alerted(r.symbol)]


async def scan_and_alert(bot=None, chat_id=None, send=None):
    cfg = dict(load_config(), account_size_usd=settings.get_account())
    res = await asyncio.to_thread(run_scan, cfg, False)
    new = pick_new(res)
    for r in new:
        text = format_alert(r, cfg["account_size_usd"]) + "\n\nTo practise this one: open http://127.0.0.1:8501/practice and click Log pretend buy."
        if send:
            await send(text, None)
        else:
            await deliver(text, bot, chat_id)
        journal.record_alert(r.symbol, r.verdict)
    return new


async def practice_job(bot=None, chat_id=None, send=None, ex=None):
    """Every few minutes: close practice trades whose stop or target was touched and tell you."""
    from . import practice
    if not practice.open_trades():
        return []
    ex = ex or make_exchange(load_config()["data_exchange"])
    done = await asyncio.to_thread(practice.check_open, ex)
    for t in done:
        await deliver(practice.close_message(t), bot, chat_id, send)
    return done


async def main():
    bot, chat = Bot(os.environ["TELEGRAM_BOT_TOKEN"]), int(os.environ["TELEGRAM_CHAT_ID"])
    sch = AsyncIOScheduler(timezone="UTC")
    sch.add_job(scan_and_alert, "cron", hour="0,4,8,12,16,20", minute=5, args=[bot, chat])
    sch.add_job(check_mode_change, "cron", hour=0, minute=10, args=[bot, chat])
    sch.add_job(price_alert_job, "interval", minutes=5, args=[bot, chat])
    sch.add_job(practice_job, "interval", minutes=5, args=[bot, chat])
    sch.add_job(weekly_reminder, "cron", day_of_week=load_config()["dca"]["weekday"], hour=load_config()["dca"]["hour_utc"], minute=0, args=[bot, chat])
    sch.start()
    print("Alerts are on: I check every 4 hours. Ctrl+C to stop.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())


async def check_mode_change(bot=None, chat_id=None, send=None):
    """Once a day: message only when the market mode flips (IN <-> OUT)."""
    cfg = load_config()
    ex = make_exchange(cfg["data_exchange"])
    rep = await asyncio.to_thread(live_report, ex, cfg["trend"])
    mode, last = rep["mode"]["mode"], settings.get_last_mode()
    settings.set_last_mode(mode)
    if last is not None and last != mode:
        text = "⚠️ Market mode CHANGED\n\n" + format_mode(rep)
        await deliver(text, bot, chat_id, send)
        return True
    return False


def run_weekly(ex, cfg, now=None):
    """Log this week's pretend buy (once per ISO week) and return the message (None if already done)."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    rep = live_report(ex, cfg["trend"])
    try:
        price = float(ex.fetch_ticker("BTC/USDT")["last"])
    except Exception:
        price = float(rep["mode"]["price"])
    amount = settings.get_dca_amount()
    dec = dcamod.weekly_decision(rep["mode"]["mode"], price, amount)
    iso = now.isocalendar()
    if not journal.dca_add(f"{iso[0]}-W{iso[1]:02d}", rep["mode"]["mode"], price, amount, dec["action"], dec["units"]):
        return None
    return dec["text"] + "\n\nSignal, not advice. You decide. Risk max 1%."


async def weekly_reminder(bot=None, chat_id=None, send=None):
    cfg = load_config()
    text = await asyncio.to_thread(run_weekly, make_exchange(cfg["data_exchange"]), cfg)
    if text:
        await deliver(text, bot, chat_id, send)
    return text


async def price_alert_job(bot=None, chat_id=None, send=None, ex=None):
    """Every few minutes: check active price alerts and message once when one is reached."""
    rows = pricealerts.active()
    if not rows:
        return []
    ex = ex or make_exchange(load_config()["data_exchange"])
    prices = {}
    for sym in {r[1] for r in rows}:
        try:
            prices[sym] = float((await asyncio.to_thread(ex.fetch_ticker, sym))["last"])
        except Exception:
            continue                                   # skip this round; try again next time
    hits = pricealerts.check(prices)
    for h in hits:
        await deliver(pricealerts.message(h), bot, chat_id, send)
    return hits
