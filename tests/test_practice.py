import asyncio
import time
import pytest
from signalscout import journal, practice, scheduler
from signalscout.config import load_config


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")


NOW = int(time.time() * 1000)
Q = 15 * 60 * 1000


def mk(entry=100, stop=95, target=110, age_min=60):
    t = practice.open_trade("BTC/USDT", "STRONG", entry, stop, target, 250)
    with journal._conn() as c:
        c.execute("UPDATE trades SET ts=? WHERE id=?", ((NOW - age_min * 60_000) / 1000, t["id"]))
    return practice.open_trades()[0]


def candle(i, o, h, l, c, base=None):
    base = base or (NOW - 60 * 60_000)
    return [base - base % Q + (i + 1) * Q, o, h, l, c, 1]


def test_refuses_stale_signal():
    with pytest.raises(ValueError):
        practice.open_trade("BTC/USDT", "STRONG", 94, 95, 110, 250)      # already below stop
    with pytest.raises(ValueError):
        practice.open_trade("BTC/USDT", "STRONG", 111, 95, 110, 250)     # already above target


def test_target_hit_is_a_win():
    t = mk()
    hit = practice.evaluate(t, [candle(0, 100, 101, 99, 100), candle(1, 100, 111, 100, 110)], NOW)
    assert hit[1] == "target" and hit[0] == 110
    done = practice.close_trade(t, *hit)
    assert done["status"] == "win" and 1.5 < done["result_r"] < 2.1 and done["usd_result"] > 0


def test_stop_hit_is_a_loss_minus_one_ish():
    t = mk()
    hit = practice.evaluate(t, [candle(0, 100, 101, 94, 95)], NOW)
    done = practice.close_trade(t, *hit)
    assert hit[1] == "stop" and done["status"] == "loss" and -1.5 < done["result_r"] < -1.0


def test_both_touched_same_candle_counts_as_stop():
    t = mk()
    assert practice.evaluate(t, [candle(0, 100, 120, 90, 100)], NOW)[1] == "stop"


def test_gap_below_stop_fills_at_the_worse_open():
    t = mk()
    hit = practice.evaluate(t, [candle(0, 90, 92, 89, 91)], NOW)
    assert hit[0] == 90


def test_candle_of_the_buy_and_unfinished_candles_are_ignored():
    t = mk(age_min=60)
    start = int(t["ts"] * 1000)
    inside_buy = [start - start % Q, 100, 200, 1, 100, 1]             # contains the buy moment
    unfinished = [NOW - 5 * 60_000, 100, 200, 1, 100, 1]               # still forming
    assert practice.evaluate(t, [inside_buy, unfinished], NOW) is None


def test_expiry_after_21_days():
    t = mk(age_min=22 * 24 * 60)
    hit = practice.evaluate(t, [candle(0, 100, 101, 99, 100, base=NOW - 30 * 60_000)], NOW)
    assert hit and hit[1] == "expired"


def test_stats_and_verdicts():
    for r_stop in range(20):
        t = mk()
        practice.close_trade(t, 110 if r_stop % 2 == 0 else 95, "target" if r_stop % 2 == 0 else "stop", NOW)
    s = practice.stats()
    assert s["done"] == 20 and s["wins"] == 10 and s["verdict"] in ("PASS", "NOT PROVEN")
    assert "20" in practice.verdict_text(s)


def test_not_proven_when_losing():
    for _ in range(20):
        practice.close_trade(mk(), 95, "stop", NOW)
    s = practice.stats()
    assert s["verdict"] == "NOT PROVEN" and "Do not trade" in practice.verdict_text(s)


def test_job_tells_you_once(monkeypatch):
    class Ex:
        def fetch_ohlcv(self, sym, tf, since=None, limit=None):
            return [candle(0, 100, 111, 100, 110)]
    mk()
    sent = []

    async def send(t, p):
        sent.append(t)
    asyncio.run(scheduler.practice_job(send=send, ex=Ex()))
    asyncio.run(scheduler.practice_job(send=send, ex=Ex()))
    assert len(sent) == 1 and "hit your TARGET" in sent[0] and "Signal, not advice" in sent[0]


def test_job_survives_exchange_error():
    class Ex:
        def fetch_ohlcv(self, *a, **k):
            raise RuntimeError("down")
    mk()
    assert asyncio.run(scheduler.practice_job(send=lambda *a: None, ex=Ex())) == []
    assert len(practice.open_trades()) == 1


def test_no_second_open_trade_on_same_coin():
    practice.open_trade("BTC/USDT", "STRONG", 100, 95, 110, 250)
    with pytest.raises(ValueError, match="already have an open"):
        practice.open_trade("BTC/USDT", "STRONG", 101, 95, 110, 250)
    practice.open_trade("ETH/USDT", "STRONG", 100, 95, 110, 250)          # other coins are fine


def test_refuses_when_live_reward_vs_risk_collapsed():
    # like ORCA: price ran up toward the target, stop is now far away
    with pytest.raises(ValueError, match="out of date"):
        practice.open_trade("ORCA/USDT", "WATCH", 2.961, 2.52359, 3.10402, 250)
    practice.open_trade("ENA/USDT", "WATCH", 0.2371, 0.226307, 0.2627, 250)   # still fine (about 2.4)
