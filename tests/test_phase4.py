import asyncio
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
from signalscout import dca, journal, settings, scheduler
from signalscout.config import load_config


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")
    monkeypatch.setattr(settings, "F", tmp_path / "s.json")


def daily(prices, start="2022-01-03"):
    idx = pd.date_range(start, periods=len(prices), freq="D")
    p = np.array(prices, float)
    return pd.DataFrame({"ts": idx.astype("datetime64[ms]").astype("int64"), "open": p, "close": p})


def test_plain_dca_math_on_flat_prices():
    d = daily([100.0] * 400)
    r = dca.simulate_history(d, 50, 6)
    assert r["plain"]["gain"] == pytest.approx(0) and r["plain"]["invested"] == r["weeks"] * 50


def test_uptrend_never_skips_and_downtrend_skips():
    up = dca.simulate_history(daily(np.linspace(50, 300, 500)), 50, 6)
    dn = dca.simulate_history(daily(np.linspace(300, 50, 500)), 50, 6)
    assert up["skipped"] == 0 and dn["skipped"] == dn["weeks"]


def test_decision_does_not_peek_at_buy_day_close():
    """Changing only the LAST day's close must not change earlier decisions."""
    base = np.concatenate([np.linspace(50, 300, 400)])
    a = dca.simulate_history(daily(base), 50, 6)
    b = base.copy(); b[-1] = 1.0
    d = daily(b); d["open"] = daily(base)["open"]
    r = dca.simulate_history(d, 50, 6)
    assert r["bought"] == a["bought"] and r["weeks"] == a["weeks"]


def test_weekly_messages():
    buy = dca.weekly_decision("IN", 100.0, 50)
    skip = dca.weekly_decision("OUT", 100.0, 50)
    assert buy["action"] == "buy" and buy["units"] == pytest.approx(0.5)
    assert skip["action"] == "skip" and skip["units"] == 0 and "plain plan" in skip["text"].lower()


def test_one_row_per_week():
    assert journal.dca_add("2026-W40", "IN", 100, 50, "buy", 0.5) is True
    assert journal.dca_add("2026-W40", "IN", 101, 50, "buy", 0.49) is False
    assert len(journal.dca_rows()) == 1


def test_summary_compares_plans():
    rows = [(1, "IN", 100.0, 50, "buy", 0.5), (2, "OUT", 50.0, 50, "skip", 0.0)]
    s = dca.summarize(rows, 100.0)
    assert s["invested"] == 50 and s["bought"] == 1 and s["skipped"] == 1
    assert s["value"] == pytest.approx(50) and s["plain_value"] == pytest.approx(0.5 * 100 + 1.0 * 100)
    assert s["mode_wealth"] == pytest.approx(100)
    assert "Plain plan" in dca.format_summary(s)
    assert "No weekly buys" in dca.format_summary({})


def test_weekly_runs_once_per_week(monkeypatch):
    class Ex:
        def fetch_ticker(self, s):
            return {"last": 100.0}
    monkeypatch.setattr(scheduler, "live_report", lambda ex, t: dict(mode=dict(mode="IN", price=100, sma=90, gap_pct=11)))
    cfg = load_config()
    now = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
    first = scheduler.run_weekly(Ex(), cfg, now)
    again = scheduler.run_weekly(Ex(), cfg, now)
    assert first and "Weekly buy day" in first and "Signal, not advice" in first and again is None
    assert len(journal.dca_rows()) == 1


def test_weekly_amount_setting():
    assert settings.get_dca_amount() == 50
    settings.set_dca_amount(25)
    assert settings.get_dca_amount() == 25
    settings.set_account(2000)           # saving one setting must not erase the other
    assert settings.get_dca_amount() == 25


def test_slack_only_with_a_real_webhook(monkeypatch):
    from signalscout import notify
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    assert notify.slack_url() is None and notify.send_slack("x") is False
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://evil.example.com/x")
    assert notify.slack_url() is None                       # only genuine Slack webhook addresses are accepted
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    assert notify.slack_url()


def test_deliver_goes_to_slack_and_survives_telegram_failure(monkeypatch):
    from signalscout import notify
    sent = []
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/X")
    monkeypatch.setattr(notify, "send_slack", lambda t, tries=3: sent.append(t) or True)

    class BadBot:
        async def send_message(self, *a):
            raise RuntimeError("telegram down")
    out = asyncio.run(notify.deliver("hello", BadBot(), 1))
    assert sent == ["hello"] and out == {"slack": True, "telegram": False}


def test_tradingview_links_in_messages():
    from signalscout.alerts import tv_link, format_alert, FOOTER
    from signalscout.scoring import ScoreResult, Check
    assert tv_link("BTC/USDT") == "https://www.tradingview.com/chart/?symbol=BINANCE:BTCUSDT"
    r = ScoreResult("SOL/USDT", score=8, verdict="STRONG", entry=100, stop=96, target=110, rr=2.5)
    r.checks = [Check("trend", True, 2, 2, "ok", True)]
    t = format_alert(r, 1000)
    assert "BINANCE:SOLUSDT" in t and t.endswith(FOOTER)
    assert "tradingview.com" in dca.weekly_decision("IN", 100.0, 50)["text"]
    assert "tradingview.com" in dca.weekly_decision("OUT", 100.0, 50)["text"]


def test_four_hour_signal_alerts_can_be_switched_off(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler, "load_config", lambda: dict(load_config(), signal_alerts=False))
    monkeypatch.setattr(scheduler, "run_scan", lambda cfg, v: (_ for _ in ()).throw(AssertionError("scan must not run")))

    async def send(t, p):
        sent.append(t)
    assert asyncio.run(scheduler.scan_and_alert(send=send)) == [] and sent == []
