"""Run the bot AND the 4-hour alerts together."""
import asyncio
from . import net  # noqa: F401  (IPv4 only)
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .bot import build_app
from .scheduler import scan_and_alert, check_mode_change, weekly_reminder, price_alert_job, practice_job, trend_portfolio_job, daily_paper_job, daily_nudge
from .config import load_config


async def main():
    app = build_app()
    chat = int(os.environ["TELEGRAM_CHAT_ID"])
    async with app:
        await app.start()
        await app.updater.start_polling()
        sch = AsyncIOScheduler(timezone="UTC", job_defaults={"misfire_grace_time": 6 * 3600, "coalesce": True})
        sch.add_job(scan_and_alert, "cron", hour="0,4,8,12,16,20", minute=5, args=[app.bot, chat])
        sch.add_job(check_mode_change, "cron", hour=0, minute=10, args=[app.bot, chat])
        sch.add_job(trend_portfolio_job, "cron", hour=0, minute=12, args=[app.bot, chat])
        sch.add_job(daily_paper_job, "cron", hour=0, minute=20, args=[app.bot, chat])
        sch.add_job(daily_nudge, "cron", hour=5, minute=0, args=[app.bot, chat])
        sch.add_job(price_alert_job, "interval", minutes=5, args=[app.bot, chat])
        sch.add_job(practice_job, "interval", minutes=5, args=[app.bot, chat])
        d = load_config()["dca"]
        sch.add_job(weekly_reminder, "cron", day_of_week=d["weekday"], hour=d["hour_utc"], minute=0, args=[app.bot, chat])
        sch.start()
        print("SignalScout is running: bot + 4-hour alerts. Ctrl+C to stop.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
