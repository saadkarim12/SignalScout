import asyncio
import numpy as np
import pandas as pd
import pytest
from signalscout import journal, settings, scheduler, trend
from signalscout.config import load_config
from signalscout.backtest_trend import gate, window_stats, run_strategy

T = load_config()["trend"]


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "F", tmp_path / "s.json")


def panel(n=500, seed=1, coins=6):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    C = pd.DataFrame({f"C{i}/USDT": 100 * np.exp(np.cumsum(rng.normal(0.001, 0.03, n))) for i in range(coins)}, index=idx)
    C["BTC/USDT"] = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    V = C * 1000
    return C, V


def test_market_mode_in_and_out():
    idx = pd.date_range("2022-01-01", periods=300, freq="D")
    up = pd.DataFrame({"BTC/USDT": np.linspace(50, 150, 300)}, index=idx)
    dn = pd.DataFrame({"BTC/USDT": np.linspace(150, 50, 300)}, index=idx)
    assert trend.market_mode(up, T)["mode"] == "IN" and trend.market_mode(dn, T)["mode"] == "OUT"
    assert "OUT" in trend.format_mode(dict(mode=trend.market_mode(dn, T), date=idx[-1]))


def test_decisions_never_use_future_days():
    """Weights computed on full history must equal weights computed with the future cut off."""
    C, V = panel()
    full = trend.weights(trend.compute(C, V, T))
    cut = 400
    part = trend.weights(trend.compute(C.iloc[:cut], V.iloc[:cut], T))
    pd.testing.assert_frame_equal(full.iloc[:cut], part)


def test_weights_are_equal_parts_and_never_leveraged():
    C, V = panel()
    w = trend.weights(trend.compute(C, V, T))
    assert (w.sum(axis=1) <= 1 + 1e-9).all() and (w >= 0).all().all()


def test_costs_reduce_return():
    C, V = panel()
    free = run_strategy(C, V, dict(T, cost_per_side=0))[0].iloc[-1]
    paid = run_strategy(C, V, dict(T, cost_per_side=0.01))[0].iloc[-1]
    assert paid < free


def test_gate_logic():
    good = dict(ret=0.1, ratio=2.0)
    assert gate(good, dict(ret=0, ratio=1.0), [0.1] * 6 + [-0.1] * 3)[0] is True
    assert gate(dict(ret=-0.1, ratio=-1), dict(ret=0, ratio=1.0), [0.1] * 9)[0] is False
    assert gate(good, dict(ret=0, ratio=1.0), [0.1] * 5 + [-0.1] * 4)[0] is False


def test_mode_change_alert_only_on_flip(monkeypatch):
    sent = []

    async def send(text, png):
        sent.append(text)
    modes = iter(["IN", "IN", "OUT"])
    monkeypatch.setattr(scheduler, "make_exchange", lambda n: None)
    monkeypatch.setattr(scheduler, "live_report", lambda ex, t: dict(
        date=None, mode=dict(mode=next(modes), price=1, sma=1, gap_pct=1)))
    assert asyncio.run(scheduler.check_mode_change(send=send)) is False   # first run: just remembers
    assert asyncio.run(scheduler.check_mode_change(send=send)) is False   # no change
    assert asyncio.run(scheduler.check_mode_change(send=send)) is True    # flip -> alert
    assert len(sent) == 1 and "CHANGED" in sent[0]
