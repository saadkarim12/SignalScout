import numpy as np
import pandas as pd
import pytest
from signalscout import backtest as bt
from signalscout.config import load_config

H4 = 4 * 3600_000


def frame(opens, highs, lows, closes):
    n = len(opens)
    return pd.DataFrame({"ts": np.arange(n) * H4, "open": opens, "high": highs, "low": lows,
                         "close": closes, "volume": 1.0})


def run_one(df, stop, target, i=0, verdict="STRONG"):
    sig = [dict(symbol="X", i=i, verdict=verdict, stop=stop, target=target)]
    return bt.simulate(sig, {"X": df}, {verdict}, load_config())


def test_target_hit_is_a_win_after_costs():
    df = frame([100, 100, 100], [100, 111, 100], [100, 99, 100], [100, 110, 100])
    t = run_one(df, 95, 110)[0]
    entry = 100 * (1 + bt.SLIP)
    assert t["entry_ts"] == df["ts"].iloc[1]                       # enters on NEXT candle
    exit_px = 110 * (1 - bt.SLIP)
    expected = (exit_px - entry - bt.FEE * (entry + exit_px)) / (entry - 95)
    assert t["r"] == pytest.approx(expected) and t["r"] > 0


def test_stop_and_target_same_candle_assumes_stop():
    df = frame([100, 100], [100, 120], [100, 90], [100, 100])
    t = run_one(df, 95, 110)[0]
    assert t["r"] < 0


def test_stop_hit_is_about_minus_one_r_plus_costs():
    df = frame([100, 100, 100], [100, 101, 100], [100, 94, 100], [100, 95, 100])
    t = run_one(df, 95, 110)[0]
    assert -1.5 < t["r"] < -1.0


def test_no_overlapping_trades_on_same_coin():
    df = frame([100] * 6, [100] * 6, [100] * 6, [100] * 6)
    sig = [dict(symbol="X", i=0, verdict="STRONG", stop=95, target=110),
           dict(symbol="X", i=1, verdict="STRONG", stop=95, target=110)]
    out = bt.simulate(sig, {"X": df}, {"STRONG"}, load_config())
    assert len(out) == 1


def test_strong_only_ignores_watch():
    df = frame([100, 100, 100], [100, 111, 100], [100, 99, 100], [100, 110, 100])
    assert run_one(df, 95, 110, verdict="WATCH") and not bt.simulate(
        [dict(symbol="X", i=0, verdict="WATCH", stop=95, target=110)], {"X": df}, {"STRONG"}, load_config())


def test_metrics():
    tr = [dict(r=2.0, ret=.02, size=.1, entry_ts=0, exit_ts=1), dict(r=-1.0, ret=-.01, size=.1, entry_ts=1, exit_ts=2)]
    m = bt.metrics(tr)
    assert m["n"] == 2 and m["win"] == 0.5 and m["expectancy"] == pytest.approx(0.5) and m["pf"] == pytest.approx(2.0)


def test_drawdown():
    assert bt.max_drawdown([100, 120, 90, 130]) == pytest.approx(-0.25)


def test_signals_never_use_future_candles():
    """Signals found on the full history must equal signals found when the future is cut off."""
    rng = np.random.default_rng(3)
    n4, nd = 900, 400
    c4 = 100 * np.exp(np.cumsum(rng.normal(0.0006, 0.012, n4)))
    d4 = pd.DataFrame({"ts": np.arange(n4) * H4, "open": c4, "high": c4 * 1.01, "low": c4 * 0.99,
                       "close": c4, "volume": rng.uniform(1, 3, n4)})
    cd = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.03, nd)))
    day = pd.DataFrame({"ts": np.arange(nd) * 6 * H4 - 150 * 6 * H4, "open": cd, "high": cd * 1.02,
                        "low": cd * 0.98, "close": cd, "volume": 1.0})
    cfg = load_config()
    full = bt.find_signals(("X", d4, day, {}, cfg))[1]
    cut = 700
    part = bt.find_signals(("X", d4.iloc[:cut], day, {}, cfg))[1]
    assert [s for s in full if s["i"] < cut - 1] == part
