"""Send reminders to Slack (and Telegram if the bot is running). Secrets live in .env only."""
import os
import time

import requests
from dotenv import load_dotenv

from .config import ROOT

load_dotenv(ROOT / ".env")


def slack_url() -> str | None:
    u = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    return u if u.startswith("https://hooks.slack.com/") else None


def send_slack(text: str, tries: int = 3) -> bool:
    url = slack_url()
    if not url:
        return False
    for i in range(tries):
        try:
            r = requests.post(url, json={"text": text}, timeout=15)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


async def deliver(text: str, bot=None, chat_id=None, send=None) -> dict:
    """One place that decides where a message goes. Slack first, then Telegram (a failure never blocks the other)."""
    import asyncio
    if send:                                   # used by tests
        await send(text, None)
        return {"test": True}
    out = {}
    if slack_url():
        out["slack"] = await asyncio.to_thread(send_slack, text)
    if bot is not None and chat_id:
        try:
            await bot.send_message(chat_id, text)
            out["telegram"] = True
        except Exception:
            out["telegram"] = False
    return out
