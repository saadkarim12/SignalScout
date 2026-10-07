from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest
from signalscout.indicators import sma, rsi, atr, pivot_highs, pivot_lows, hidden_bullish_divergence
from signalscout.sizing import position_size
from signalscout.data import drop_unclosed
from signalscout.universe import pick_universe
from signalscout.events import upcoming
from signalscout.levels import round_support
from signalscout.scoring import score_coin
from signalscout.config import load_config


def ref_rsi(closes, n=14):
    """Plain-python Wilder RSI, written independently as a cross-check."""
    ch = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    g = [max(c, 0) for c in ch]
    l = [max(-c, 0) for c in ch]
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    out = {n: 100 - 100 / (1 + ag / al)}
    for i in range(n, len(ch)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out[i + 1] = 100 - 100 / (1 + ag / al)
    return out


def test_sma():
    assert sma(pd.Series([1, 2, 3, 4, 5.0]), 3).tolist()[2:] == [2, 3, 4]


def test_rsi_matches_reference_and_known_value():
    rng = np.random.default_rng(1)
    closes = list(100 + np.cumsum(rng.normal(0, 1, 80)))
    got = rsi(pd.Series(closes))
    ref = ref_rsi(closes)
    for i, v in ref.items():
        assert got.iloc[i] == pytest.approx(v, abs=1e-9)
    # Hand-checked: 14 gains of +1 then one -1 -> avg gain 14/14=1 -> (1*13+0)/14, avg loss 1/14
    s = pd.Series([float(i) for i in range(15)] + [13.0])
    assert rsi(s).iloc[-1] == pytest.approx(100 - 100 / (1 + (13 / 14) / (1 / 14)))


def test_rsi_all_up_is_100():
    assert rsi(pd.Series(np.arange(30.0))).iloc[-1] == 100


def test_atr_constant_range():
    df = pd.DataFrame({"high": [11.0] * 30, "low": [9.0] * 30, "close": [10.0] * 30})
    assert atr(df).iloc[-1] == pytest.approx(2.0)


def test_pivots():
    h = pd.Series([1, 2, 3, 9, 3, 2, 1, 2, 3.0])
    assert pivot_highs(h, 3) == [3]
    l = pd.Series([9, 8, 7, 1, 7, 8, 9, 8, 7.0])
    assert pivot_lows(l, 3) == [3]


def test_hidden_divergence():
    low = [10.0] * 40
    df = pd.DataFrame({"low": low})
    # two pivot lows: A=5 at idx 20, B=6 at idx 34 (higher low); RSI lower at B
    for i, v in {17: 8, 18: 7, 19: 6, 20: 5, 21: 6, 22: 7, 23: 8, 31: 9, 32: 8, 33: 7, 34: 6, 35: 7, 36: 8, 37: 9}.items():
        df.loc[i, "low"] = v
    rs = pd.Series(50.0, index=df.index)
    rs[20], rs[34] = 30, 25
    assert hidden_bullish_divergence(df, rs, 3, 60, 8) is True
    rs[34] = 35
    assert hidden_bullish_divergence(df, rs, 3, 60, 8) is False


def test_no_lookahead_unclosed_candle_dropped():
    h4 = 4 * 3600_000
    df = pd.DataFrame({"ts": [0, h4, 2 * h4]})
    now = 2 * h4 + 1000  # third candle still forming
    assert drop_unclosed(df, "4h", now)["ts"].tolist() == [0, h4]


def test_sizing_one_percent_rule():
    s = position_size(1000, 1, 100, 96)  # 4% stop
    assert s["usd"] == pytest.approx(250) and s["max_loss"] == pytest.approx(10)
    s = position_size(1000, 1, 100, 99)  # 1% stop -> capped at 25%
    assert s["usd"] == 250 and s["max_loss"] == pytest.approx(2.5)


def test_universe_filters():
    cfg = dict(load_config(), min_quote_volume_usd=0, universe_size=20)
    mk = lambda b, q="USDT", spot=True: {"base": b, "quote": q, "spot": spot, "active": True}
    markets = {f"{b}/USDT": mk(b) for b in ["BTC", "ETH", "USDC", "BTCUP", "WBTC", "SOL"]}
    markets["ETH/USDC"] = mk("ETH", "USDC")
    tickers = {s: {"quoteVolume": v} for s, v in
               {"BTC/USDT": 1, "ETH/USDT": 9, "USDC/USDT": 99, "BTCUP/USDT": 98, "WBTC/USDT": 97,
                "SOL/USDT": 5, "ETH/USDC": 100}.items()}
    assert pick_universe(tickers, markets, cfg) == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_events_window():
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    ev = [{"name": "CPI", "time": "2026-01-01 12:00"}, {"name": "later", "time": "2026-01-03 12:00"}]
    assert [e["name"] for e in upcoming(ev, now, 24)] == ["CPI"]


def test_round_numbers():
    assert round_support(83068, "BTC/USDT") == 80000
    assert round_support(2674, "ETH/USDT") == 2500
    assert round_support(14.798, "LINK/USDT") == pytest.approx(14)
    assert round_support(0.09373, "DOGE/USDT") == pytest.approx(0.093)


def _frames(daily_trend_up=True):
    n = 400
    d = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "volume": 1.0,
                      "close": np.linspace(50, 150, n) if daily_trend_up else np.linspace(150, 50, n)})
    h = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=range(500))
    return h, d


def test_must_rule_forces_no_trade():
    cfg = load_config()
    h, d = _frames(daily_trend_up=False)  # below SMA200 -> MUST fails
    r = score_coin("BTC/USDT", h, d, (20, "Fear"), [], cfg, 1000)
    assert r.verdict == "NO_TRADE"


def test_insufficient_data_is_no_trade():
    cfg = load_config()
    h, d = _frames()
    r = score_coin("X/USDT", h, d.iloc[:50], None, [], cfg, 1000)
    assert r.verdict == "NO_TRADE" and r.score == 0


def test_universe_skips_thin_coins():
    cfg = dict(load_config(), min_quote_volume_usd=1000, universe_size=20)
    mk = lambda b: {"base": b, "quote": "USDT", "spot": True, "active": True}
    markets = {f"{b}/USDT": mk(b) for b in ["BTC", "ETH", "THIN"]}
    tickers = {"BTC/USDT": {"quoteVolume": 5}, "ETH/USDT": {"quoteVolume": 5000}, "THIN/USDT": {"quoteVolume": 10}}
    assert pick_universe(tickers, markets, cfg) == ["BTC/USDT", "ETH/USDT"]   # BTC always stays
