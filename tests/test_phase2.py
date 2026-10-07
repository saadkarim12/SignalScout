import asyncio
import pytest
from signalscout import journal, settings, scheduler
from signalscout.alerts import format_alert, FOOTER
from signalscout.charts import make_chart
from signalscout.scoring import ScoreResult, Check
from signalscout.sizing import position_size
import pandas as pd
import numpy as np


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")
    monkeypatch.setattr(settings, "F", tmp_path / "s.json")


def result(sym="BTC/USDT", verdict="STRONG"):
    r = ScoreResult(sym, score=8, verdict=verdict, entry=100, stop=96, target=110, rr=2.5)
    r.size = position_size(1000, 1, 100, 96)
    r.checks = [Check("trend", True, 2, 2, "Above 200-day average (uptrend)", True),
                Check("sentiment", False, 0, 1, "Fear & Greed 58 - not fearful")]
    return r


def test_alert_text_has_footer_reasons_and_size():
    t = format_alert(result(), 1000)
    assert t.endswith(FOOTER)
    assert "✅ Above 200-day" in t and "❌ Fear & Greed" in t
    assert "most you can lose $10" in t and "STRONG" in t


def test_watch_alert_uses_half_percent():
    assert "0.5% of $1,000" in format_alert(result(verdict="WATCH"), 1000)


def test_no_duplicate_alerts_within_24h():
    r = result()
    assert scheduler.pick_new([r]) == [r]
    journal.record_alert("BTC/USDT", "STRONG")
    assert scheduler.pick_new([r]) == []
    assert not journal.already_alerted("BTC/USDT", hours=0)  # older than the window -> allowed again


def test_skip_and_no_trade_never_alert():
    assert scheduler.pick_new([result(verdict="SKIP"), result(verdict="NO_TRADE")]) == []


def test_scan_and_alert_sends_once(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler, "run_scan", lambda cfg, v: [result("A/USDT"), result("B/USDT", "SKIP")])
    monkeypatch.setattr(scheduler, "make_chart", lambda *a: b"png")

    async def send(text, png):
        sent.append(text)
    asyncio.run(scheduler.scan_and_alert(send=send))
    asyncio.run(scheduler.scan_and_alert(send=send))  # second run = duplicate -> silent
    assert len(sent) == 1 and "A/USDT" in sent[0]


def test_paper_trade_saved_and_listed():
    tid = journal.add_trade("BTC/USDT", "paper", 100, 96, 110, 250)
    rows = journal.list_trades()
    assert rows[0][0] == tid and rows[0][7] == "open"


def test_account_setting_saved():
    assert settings.get_account() == 1000
    settings.set_account(2500)
    assert settings.get_account() == 2500


def test_chart_makes_png():
    n = 300
    c = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n))
    df = pd.DataFrame({"ts": np.arange(n) * 14_400_000, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 5.0})
    assert make_chart(df, "X/USDT", 100, 95, 110)[:4] == b"\x89PNG"


def test_bot_refuses_without_secrets(monkeypatch):
    from signalscout import bot
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(SystemExit):
        bot.build_app()


def test_bot_only_answers_owner_chat(monkeypatch):
    from signalscout import bot
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    app = bot.build_app()
    handlers = [h for g in app.handlers.values() for h in g]
    names = {next(iter(h.commands)) for h in handlers}
    assert names == {"start", "help", "scan", "coin", "fear", "alert", "alerts", "delalert", "mode", "weekly", "setweekly", "paper", "journal", "report", "settings", "setaccount"}
    assert all(h.filters is not None and 42 in h.filters.chat_ids for h in handlers)
