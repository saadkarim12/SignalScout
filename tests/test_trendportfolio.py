import asyncio
import numpy as np
import pandas as pd
import pytest
from signalscout import trendportfolio as tp, research as rs, settings, scheduler


@pytest.fixture(autouse=True)
def tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "F", tmp_path / "s.json")


def coin(n=700, seed=1, drift=0.001, vol=0.03, start="2022-01-01"):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({"open": np.r_[c[0], c[:-1]], "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1.0}, index=idx)


def test_exposure_is_a_share_of_four_rules():
    e = tp.ensemble(coin()).dropna()
    assert set(np.round(e.unique(), 2)) <= {0.0, 0.25, 0.5, 0.75, 1.0}
    assert len(tp.rule_signals(coin()).columns) == 4


def test_uptrend_is_fully_in_and_downtrend_is_out():
    up = pd.DataFrame({"open": np.linspace(50, 300, 400), "high": 0, "low": 0, "close": np.linspace(50, 300, 400), "volume": 1.0},
                      index=pd.date_range("2022-01-01", periods=400))
    assert tp.ensemble(up).iloc[-1] == 1.0
    dn = up.assign(close=np.linspace(300, 50, 400), open=np.linspace(300, 50, 400))
    assert tp.ensemble(dn).iloc[-1] == 0.0


def test_signals_never_use_future_days():
    d = coin()
    full = tp.ensemble(d)
    cut = 500
    part = tp.ensemble(d.iloc[:cut])
    pd.testing.assert_series_equal(full.iloc[:cut], part)


def test_trading_engine_is_lagged_and_costs_money():
    d = coin(vol=0.02)
    eq_free, _ = rs.run(d, tp.ensemble(d))
    # changing only the LAST day must not change any earlier equity value
    d2 = d.copy()
    d2.iloc[-1, d2.columns.get_loc("close")] *= 0.5
    eq2, _ = rs.run(d2, tp.ensemble(d2))
    pd.testing.assert_series_equal(eq_free.iloc[:-1], eq2.iloc[:-1])
    old = rs.COST
    try:
        rs.COST = 0.01
        eq_cost, _ = rs.run(d, tp.ensemble(d))
    finally:
        rs.COST = old
    assert eq_cost.iloc[-1] < eq_free.iloc[-1]


def test_status_has_numbers_for_every_rule():
    st = tp.status(coin())
    assert set(st["votes"]) == set(tp.RULES) and all(st["details"][r] for r in tp.RULES)
    assert 0 <= st["exposure"] <= 1


def test_change_message_is_plain_and_ends_with_footer():
    st = dict(exposure=0.5, prev_exposure=0.75, votes={r: i < 2 for i, r in enumerate(tp.RULES)}, details={})
    m = tp.format_change("BTC/USDT", st, 500)
    assert "down from 75% to 50%" in m.replace("goes from 75% down to 50%", "down from 75% to 50%")
    assert "$250" in m and m.endswith("Signal, not advice. You decide. Risk max 1%.")


def test_job_stays_quiet_then_speaks_only_on_change():
    sent = []

    async def send(t, p):
        sent.append(t)
    d1 = {"BTC/USDT": coin(seed=3)}
    asyncio.run(scheduler.trend_portfolio_job(send=send, data=d1))          # first run: only remembers
    assert sent == []
    asyncio.run(scheduler.trend_portfolio_job(send=send, data=d1))          # same data: still quiet
    assert sent == []
    settings.set_tp_state({"BTC/USDT": 0.0 if tp.status(d1["BTC/USDT"])["exposure"] != 0.0 else 1.0})   # pretend yesterday differed
    asyncio.run(scheduler.trend_portfolio_job(send=send, data=d1))
    assert len(sent) == 1 and "BTC" in sent[0]


def test_backtest_summary_shape():
    b = tp.backtest_summary({"BTC/USDT": coin(2200, 1, start="2018-01-01"), "ETH/USDT": coin(2200, 2, start="2018-01-01")})
    assert {"strategy_is", "strategy_oos", "hold_is", "hold_oos", "years"} <= set(b)
    assert all(-1 <= v[0] for v in b["years"].values())


def test_short_history_does_not_crash():
    b = tp.backtest_summary({"BTC/USDT": coin(900, 1)})          # nothing before 2022: in-sample window is empty
    assert b["strategy_is"]["ret"] == 0.0
