"""Every 4 hours (5 minutes after the candle closes, UTC): scan and send NEW alerts only."""
import asyncio
from . import net  # noqa: F401  (IPv4 only)
import os
from datetime import datetime, timezone
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
from . import trendportfolio as tpmod
from . import paperqa

load_dotenv(ROOT / ".env")


def pick_new(results):
    """STRONG/WATCH setups we have not already alerted in the last 24 hours."""
    return [r for r in results if r.verdict in ("STRONG", "WATCH") and not journal.already_alerted(r.symbol)]


async def scan_and_alert(bot=None, chat_id=None, send=None):
    cfg = dict(load_config(), account_size_usd=settings.get_account())
    if not cfg.get("signal_alerts", True):
        return []                                   # switched off in config.yaml
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
    sch = AsyncIOScheduler(timezone="UTC", job_defaults={"misfire_grace_time": 6 * 3600, "coalesce": True})
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


def load_tp_data(ex, cfg):
    import pandas as pd
    from .data import fetch_history
    t = cfg["trend_portfolio"]
    data = {}
    for sym in t["coins"]:
        d = fetch_history(ex, sym, "1d", t["history_years"])
        d.index = pd.to_datetime(d["ts"], unit="ms")
        data[sym] = d
    return data


async def trend_portfolio_job(bot=None, chat_id=None, send=None, ex=None, data=None):
    """Once a day after the daily candle closes: message only when a coin's exposure changes."""
    cfg = load_config()
    if data is None:
        ex = ex or make_exchange(cfg["data_exchange"])
        data = await asyncio.to_thread(load_tp_data, ex, cfg)
    st = tpmod.live_status(data)
    old = settings.get_tp_state()
    new = {s: v["exposure"] for s, v in st.items()}
    settings.set_tp_state(new)
    slice_usd = settings.get_account() / max(len(st), 1)
    sent = []
    for sym, v in st.items():
        if sym in old and abs(old[sym] - v["exposure"]) > 1e-9:
            v = dict(v, prev_exposure=old[sym])
            text = tpmod.format_change(sym, v, slice_usd)
            await deliver(text, bot, chat_id, send)
            sent.append(sym)
    return sent


def _other_prices(ex, coins):
    """Binance vs a second exchange live price for a sanity check (None if the second exchange cannot be reached)."""
    try:
        okx = make_exchange(load_config().get("qa_exchange", "kraken"))
        return {s: (float(ex.fetch_ticker(s)["last"]), float(okx.fetch_ticker(s)["last"])) for s in coins}
    except Exception:
        return None


async def daily_paper_job(bot=None, chat_id=None, send=None, ex=None, data=None, news=None, other=None):
    """After the daily candle closes: record the pretend position and value, run the independent QA, speak only on a failure."""
    from . import news as newsmod
    cfg = load_config()
    if data is None:
        ex = ex or make_exchange(cfg["data_exchange"])
        data = await asyncio.to_thread(load_tp_data, ex, cfg)
        other = await asyncio.to_thread(_other_prices, ex, list(data))
        news = await asyncio.to_thread(newsmod.get_news)
    paperqa.record_ledger(data, cfg["trend_portfolio"]["start_date"])
    checks = paperqa.qa_checks(data, news, other)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ok = paperqa.store_qa(day, checks)
    if not ok:
        bad = [c for c in checks if c["ok"] is False]
        text = ("⚠️ Daily QA found a problem with the Trend portfolio:\n" + "\n".join(f"- {c['name']}: {c['detail']}" for c in bad)
                + "\nDo not rely on today's numbers until this is checked.\n\nSignal, not advice. You decide. Risk max 1%.")
        await deliver(text, bot, chat_id, send)
    return ok


async def daily_nudge(bot=None, chat_id=None, send=None, data=None):
    """Morning message: today's pretend position and a reminder to do the daily check-in (skipped if you already did)."""
    cfg = load_config()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if any(d == day for d, _ in paperqa.checkins()):
        return None
    if data is None:
        data = await asyncio.to_thread(load_tp_data, make_exchange(cfg["data_exchange"]), cfg)
    st = tpmod.live_status(data)
    lines = [f"{s.split('/')[0]}: {v['exposure'] * 100:.0f}% invested ({'unchanged' if abs(v['exposure'] - v['prev_exposure']) < 1e-9 else 'CHANGED'})"
             for s, v in st.items()]
    led = paperqa.ledger()
    prog = f"Day {len(led)} of {cfg['go_live']['min_days']} of the paper test." if led else "Paper test starting."
    text = ("☀️ Daily paper check\n" + "\n".join(lines) + f"\n{prog}\nOpen http://127.0.0.1:8501/paperlab and press 'I checked today'."
            "\n\nSignal, not advice. You decide. Risk max 1%.")
    await deliver(text, bot, chat_id, send)
    return text
