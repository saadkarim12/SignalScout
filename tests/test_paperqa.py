import asyncio
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
from signalscout import paperqa, journal, trendportfolio as tp, scheduler, settings
from signalscout.config import load_config


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")
    monkeypatch.setattr(settings, "F", tmp_path / "s.json")


def coin(n=500, seed=1, end="2026-10-20"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, n)))
    idx = pd.date_range(end=end, periods=n, freq="D")
    return pd.DataFrame({"open": np.r_[c[0], c[:-1]], "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0}, index=idx)


NOW = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)


def test_independent_calculation_agrees_with_the_app_on_many_random_markets():
    for seed in range(40):
        d = coin(seed=seed)
        assert abs(tp.status(d)["exposure"] - paperqa.indep_exposure(list(d["close"]))) < 1e-9


def test_qa_passes_on_good_data_and_catches_stale_data():
    data = {"BTC/USDT": coin(), "ETH/USDT": coin(seed=2)}
    news = dict(ok=["a", "b", "c", "d", "e"], bad=[])
    good = paperqa.qa_checks(data, news, {"BTC/USDT": (100, 100.1), "ETH/USDT": (50, 50.1)}, now=NOW)
    assert all(c["ok"] is not False for c in good)
    stale = {"BTC/USDT": coin(end="2026-10-10"), "ETH/USDT": coin(seed=2)}
    assert any(c["ok"] is False and "fresh" in c["name"] for c in paperqa.qa_checks(stale, news, None, now=NOW))


def test_qa_catches_a_price_that_disagrees_between_exchanges():
    data = {"BTC/USDT": coin()}
    bad = paperqa.qa_checks(data, None, {"BTC/USDT": (100, 103)}, now=NOW)
    assert any(c["ok"] is False and "second exchange" in c["name"] for c in bad)


def test_unreachable_second_exchange_is_not_a_failure():
    r = paperqa.qa_checks({"BTC/USDT": coin()}, None, None, now=NOW)
    assert next(c for c in r if "second exchange" in c["name"])["ok"] is None


def test_ledger_is_repeatable_and_gapless():
    data = {"BTC/USDT": coin(), "ETH/USDT": coin(seed=2)}
    n1 = paperqa.record_ledger(data, "2026-09-01")
    n2 = paperqa.record_ledger(data, "2026-09-01")
    assert n1 == n2 and len(paperqa.ledger()) == n1
    assert all(c["ok"] is not False for c in paperqa.qa_checks(data, None, None, now=NOW) if "gaps" in c["name"])


def test_checkin_once_per_day():
    assert paperqa.checkin("ok", NOW) is True and paperqa.checkin("again", NOW) is False
    assert len(paperqa.checkins()) == 1


def test_go_live_needs_every_rule():
    cfg = load_config()
    led = [dict(date=f"2026-10-{d:02d}", strat=1.0 + d * 0.001, hold=1.0, exposures={"BTC": 1.0 if d < 10 else 0.75}) for d in range(1, 29)]
    qa = [dict(date=r["date"], ok=True, checks=[]) for r in led]
    ci = [(r["date"], "") for r in led]
    r = paperqa.go_live(cfg, led, qa, ci)
    assert not r["ready"] and next(x for x in r["rows"] if "long enough" in x[0])[1] is False       # only 28 of 90 days
    big = led * 4                                                                                  # pretend 112 days
    r2 = paperqa.go_live(cfg, big, qa * 4, ci * 4)
    assert next(x for x in r2["rows"] if "long enough" in x[0])[1] is True
    losing = [dict(l, strat=0.8) for l in big]
    r3 = paperqa.go_live(cfg, losing, qa * 4, ci * 4)
    assert not r3["ready"] and next(x for x in r3["rows"] if "90%" in x[0])[1] is False
    r4 = paperqa.go_live(cfg, big, [dict(q, ok=False) for q in qa * 4], ci * 4)
    assert not r4["ready"]                                                                         # QA failing blocks go-live


def test_failed_qa_sends_a_warning_and_good_qa_stays_quiet():
    sent = []

    async def send(t, p):
        sent.append(t)
    good = {"BTC/USDT": coin(end=(datetime.now(timezone.utc) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))}   # yesterday's closed candle = fresh
    news = dict(ok=list("abcde"), bad=[])
    asyncio.run(scheduler.daily_paper_job(send=send, data=good, news=news, other={"BTC/USDT": (100, 100.0)}))
    assert sent == []
    asyncio.run(scheduler.daily_paper_job(send=send, data=good, news=news, other={"BTC/USDT": (100, 110.0)}))
    assert len(sent) == 1 and "Daily QA found a problem" in sent[0] and sent[0].endswith("Risk max 1%.")


def test_daily_nudge_skips_when_already_checked_in():
    sent = []

    async def send(t, p):
        sent.append(t)
    data = {"BTC/USDT": coin()}
    asyncio.run(scheduler.daily_nudge(send=send, data=data))
    assert len(sent) == 1 and "I checked today" in sent[0]
    paperqa.checkin("done")
    asyncio.run(scheduler.daily_nudge(send=send, data=data))
    assert len(sent) == 1
