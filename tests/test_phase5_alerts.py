import asyncio
import pytest
from signalscout import journal, pricealerts as pa, scheduler


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")


def test_normalize():
    assert pa.normalize("btc") == "BTC/USDT" and pa.normalize("ETH/USDT") == "ETH/USDT"
    assert pa.normalize("bad coin!") is None and pa.normalize("") is None


def test_direction_is_chosen_from_current_price():
    assert pa.add("BTC/USDT", 90000, 85000)["direction"] == "above"
    assert pa.add("BTC/USDT", 80000, 85000)["direction"] == "below"


def test_rejects_silly_levels():
    for bad in (0, -5, float("nan")):
        with pytest.raises(ValueError):
            pa.add("BTC/USDT", bad, 85000)
    with pytest.raises(ValueError):
        pa.add("BTC/USDT", 85010, 85000)             # basically the current price


def test_limit_of_active_alerts():
    for i in range(pa.MAX_ACTIVE):
        pa.add("BTC/USDT", 90000 + i * 10, 85000)
    with pytest.raises(ValueError):
        pa.add("BTC/USDT", 99999, 85000)


def test_triggers_once_only_when_reached():
    pa.add("BTC/USDT", 90000, 85000)
    assert pa.check({"BTC/USDT": 89999}) == []
    hit = pa.check({"BTC/USDT": 90100})
    assert len(hit) == 1 and hit[0]["price"] == 90100
    assert pa.check({"BTC/USDT": 95000}) == []        # already used up
    assert pa.active() == [] and len(pa.history()) == 1


def test_below_alert_and_missing_price():
    pa.add("ETH/USDT", 2000, 2500)
    assert pa.check({}) == []                         # no price data -> nothing happens
    assert len(pa.check({"ETH/USDT": 1990})) == 1


def test_delete_only_active():
    a = pa.add("BTC/USDT", 90000, 85000)
    assert pa.delete(a["id"]) is True and pa.delete(a["id"]) is False


def test_message_has_link_and_footer():
    m = pa.message(dict(symbol="BTC/USDT", direction="above", level=90000, price=90100))
    assert "BINANCE:BTCUSDT" in m and m.endswith(pa.FOOTER) and "not a buy or sell signal" in m


def test_job_sends_one_message(monkeypatch):
    class Ex:
        def fetch_ticker(self, s):
            return {"last": 91000.0}
    sent = []

    async def send(t, p):
        sent.append(t)
    pa.add("BTC/USDT", 90000, 85000)
    asyncio.run(scheduler.price_alert_job(send=send, ex=Ex()))
    asyncio.run(scheduler.price_alert_job(send=send, ex=Ex()))
    assert len(sent) == 1 and "Price alert" in sent[0]


def test_job_survives_price_fetch_error():
    class Ex:
        def fetch_ticker(self, s):
            raise RuntimeError("down")
    pa.add("BTC/USDT", 90000, 85000)
    assert asyncio.run(scheduler.price_alert_job(send=lambda *a: None, ex=Ex())) == []
    assert len(pa.active()) == 1                        # still waiting, not lost
