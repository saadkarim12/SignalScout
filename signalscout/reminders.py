"""Run ONLY the reminders (weekly buy + market-mode change) - no Telegram bot needed. Sends to Slack."""
import asyncio
from . import net  # noqa: F401
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from .config import load_config
from .notify import slack_url, send_slack
from .scheduler import weekly_reminder, check_mode_change, price_alert_job, practice_job, scan_and_alert, trend_portfolio_job


async def main():
    if not slack_url():
        raise SystemExit("Slack is not set up yet. Put SLACK_WEBHOOK_URL=... in the .env file (see README).")
    d = load_config()["dca"]
    sch = AsyncIOScheduler(timezone="UTC", job_defaults={"misfire_grace_time": 6 * 3600, "coalesce": True})
    sch.add_job(check_mode_change, "cron", hour=0, minute=10)
    sch.add_job(trend_portfolio_job, "cron", hour=0, minute=12)
    sch.add_job(price_alert_job, "interval", minutes=5)
    sch.add_job(practice_job, "interval", minutes=5)
    sch.add_job(scan_and_alert, "cron", hour="0,4,8,12,16,20", minute=5)
    sch.add_job(weekly_reminder, "cron", day_of_week=d["weekday"], hour=d["hour_utc"], minute=0)
    sch.start()
    print("Reminders are on (Slack). Weekly buy day: Sunday 08:00 UTC. Price alerts checked every 5 minutes. Leave this window open. Ctrl+C to stop.", flush=True)
    await asyncio.Event().wait()


def test_message():
    ok = send_slack("✅ SignalScout test: Slack reminders work. Signal, not advice. You decide. Risk max 1%.")
    print("Slack test message sent. Check Slack." if ok else "Could not send. Check SLACK_WEBHOOK_URL in .env.")


if __name__ == "__main__":
    import sys
    test_message() if "--test" in sys.argv else asyncio.run(main())
