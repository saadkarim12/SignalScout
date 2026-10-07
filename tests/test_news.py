from datetime import datetime, timedelta, timezone
import pytest
from signalscout import news
from signalscout.scoring import score_coin
from signalscout.config import load_config

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

FED = """<h5>2026 FOMC Meetings</h5><div><strong>January</strong><div>27-28</div><div>Statement:</div></div>
<div><strong>March</strong><div>17-18*</div></div><div><strong>Oct/Nov</strong><div>31-1</div></div>
<h5>2025 FOMC Meetings</h5><div><strong>December</strong><div>9-10</div></div>"""

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Binance hacked, $200M drained</title><link>http://x/1</link><pubDate>Wed, 07 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>DOGE rallies as whales buy</title><link>http://x/2</link><pubDate>Wed, 07 Oct 2026 09:00:00 +0000</pubDate></item>
<item><title>Conduit sues Tether over frozen funds</title><link>http://x/3</link><pubDate>Wed, 07 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Bitcoin.de trading remains halted</title><link>http://x/4</link><pubDate>Wed, 07 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>Old hack of SOL</title><link>http://x/5</link><pubDate>Mon, 05 Oct 2026 08:00:00 +0000</pubDate></item>
<item><title>No date item</title></item></channel></rss>"""


def test_fomc_parse_uses_decision_day_and_new_york_time():
    ev = news.parse_fomc(FED, 2026)
    days = [(e["time"].month, e["time"].day, e["time"].hour) for e in ev]
    assert days[0] == (1, 28, 19)          # January: winter time -> 19:00 UTC
    assert days[1] == (3, 18, 18)          # March: summer time -> 18:00 UTC
    assert days[2][:2] == (11, 1)          # meeting spanning two months: 31 Oct - 1 Nov
    assert len(ev) == 3 and all(e["source"] == "federalreserve.gov" for e in ev)    # 2025 panel not mixed in


def test_rss_parsing_skips_items_without_a_date():
    h = news.parse_rss(RSS, "T")
    assert len(h) == 5 and h[0]["time"].tzinfo is not None


def test_risk_logic():
    h = news.parse_rss(RSS, "T")
    assert [x["title"] for x in news.risky("ETH/USDT", h, NOW)] == ["Binance hacked, $200M drained"]  # market-wide big incident
    assert news.risky("DOGE/USDT", h, NOW)[0]["title"].startswith("Binance")
    titles = [x["title"] for x in news.risky("BTC/USDT", h, NOW)]
    assert "Conduit sues Tether over frozen funds" not in titles        # small lawsuit is not market-wide
    assert "Bitcoin.de trading remains halted" not in titles            # a different company, not Bitcoin
    assert all("Old hack" not in t for t in titles)                     # older than 24h is ignored
    assert "Old hack of SOL" in [x["title"] for x in news.risky("SOL/USDT", h, NOW, hours=72)]


def test_coin_mentions():
    assert news.mentions("DOGE/USDT", "Dogecoin jumps") and news.mentions("ENA/USDT", "ENA unlock soon")
    assert not news.mentions("ENA/USDT", "the arena opens")


def _frames():
    import numpy as np, pandas as pd
    n = 400
    d = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "volume": 1.0, "close": np.linspace(50, 150, n)})
    h = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=range(500))
    return h, d


def test_news_point_uses_real_flags():
    cfg = load_config()
    h, d = _frames()
    def news_check(**k):
        r = score_coin("X/USDT", h, d, (20, "Fear"), [], cfg, 1000, now=NOW, **k)
        return next(c for c in r.checks if c.name == "news")
    assert news_check().passed and "No big scheduled event" in news_check(news_note="checked: Fed").text
    risk = [dict(title="X exchange hacked", source="CoinDesk")]
    c = news_check(risk=risk)
    assert not c.passed and "Risky headline" in c.text
    ev = [dict(name="US interest-rate decision (Fed FOMC)", time=NOW + timedelta(hours=5))]
    r = score_coin("X/USDT", h, d, (20, "Fear"), ev, cfg, 1000, now=NOW)
    assert not next(c for c in r.checks if c.name == "news").passed


def test_no_fred_key_is_reported_not_hidden(monkeypatch, tmp_path):
    monkeypatch.setattr(news, "CACHE", tmp_path / "c.json")
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(news, "fetch_fomc", lambda now: [])
    monkeypatch.setattr(news, "FEEDS", {})
    d = news.get_news(force=True, now=NOW)
    assert any("FRED" in b and "NOT checked" in b for b in d["bad"])


def test_tether_is_not_ether():
    assert not news.mentions("ETH/USDT", "Conduit sues Tether over frozen funds")
    assert news.mentions("ETH/USDT", "Ether jumps 5%") and news.mentions("ETH/USDT", "Ethereum upgrade")


def test_binance_parse_and_delisting_window():
    payload = {"data": {"catalogs": [{"articles": [
        {"title": "Binance Will Delist ABC, XYZ on 2026-10-20", "code": "c1", "releaseDate": int((NOW - timedelta(days=3)).timestamp() * 1000)},
        {"title": "Binance Will List NEWCOIN (NEW)", "code": "c2", "releaseDate": int((NOW - timedelta(hours=2)).timestamp() * 1000)}]}]}}
    d = news.parse_binance(payload, "delisting")
    assert d[0]["link"].endswith("/c1") and d[0]["source"] == "Binance (official)"
    assert [h["title"] for h in news.risky("ABC/USDT", d, NOW)] == ["Binance Will Delist ABC, XYZ on 2026-10-20"]   # 3 days old, still counts
    assert news.risky("BTC/USDT", d, NOW) == []                       # does not name BTC
    old = news.parse_binance({"data": {"catalogs": [{"articles": [
        {"title": "Binance Will Delist ABC", "code": "c3", "releaseDate": int((NOW - timedelta(days=9)).timestamp() * 1000)}]}]}}, "delisting")
    assert news.risky("ABC/USDT", old, NOW) == []                      # older than 7 days
    listing = news.parse_binance(payload, "listing")
    assert news.risky("NEW/USDT", listing, NOW) == []                  # new listings are information, not risk


def test_score_lines_explain_themselves():
    cfg = load_config()
    h, d = _frames()
    r = score_coin("X/USDT", h, d, (20, "Fear"), [], cfg, 1000, now=NOW, news_note="checked: Fed")
    assert all(c.detail for c in r.checks)
    assert "200" in next(c for c in r.checks if c.name == "trend").detail
    assert "Binance" in next(c for c in r.checks if c.name == "news").detail


def test_divergence_line_is_information_only():
    cfg = load_config()
    h, d = _frames()
    r = score_coin("X/USDT", h, d, (20, "Fear"), [], cfg, 1000, now=NOW)
    div = next(c for c in r.checks if c.name == "divergence")
    assert div.max_points == 0 and div.points == 0                    # never changes the score
    assert r.score == sum(c.points for c in r.checks if c.max_points > 0)
    from signalscout.alerts import format_alert
    r.verdict, r.entry, r.stop, r.target, r.rr = "WATCH", 100, 95, 110, 2
    assert "ℹ️ Hidden bullish divergence" in format_alert(r, 1000)
