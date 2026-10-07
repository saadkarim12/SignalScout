from signalscout.advice import suggest, one_line
from signalscout.scoring import ScoreResult, Check
from signalscout import journal, practice
import pytest


def res(bounce=True, verdict="STRONG"):
    r = ScoreResult("X/USDT", score=8, verdict=verdict, entry=100, stop=95, target=115, rr=3)
    r.checks = [Check("bounce", bounce, int(bounce), 1, "b")]
    return r


IN, OUT = {"mode": "IN"}, {"mode": "OUT"}


def test_buy_needs_everything():
    a = suggest(res(), 100.2, IN)
    assert a["label"] == "BUY" and not a["bad"]


def test_wait_when_no_bounce():
    a = suggest(res(bounce=False), 100.2, IN)
    assert a["label"] == "WAIT" and "bounce" in a["bad"][0].lower()


def test_wait_when_price_ran_away_or_rr_collapsed():
    a = suggest(res(), 110, IN)                       # +10% and reward vs risk tiny
    assert a["label"] == "WAIT" and len(a["bad"]) == 2


def test_wait_when_market_mode_out():
    assert suggest(res(), 100, OUT)["label"] == "WAIT"


def test_skip_for_weak_signals():
    assert suggest(res(verdict="SKIP"), 100, IN)["label"] == "SKIP"


def test_works_without_live_price():
    assert suggest(res(), None, None)["label"] == "BUY"
    assert one_line(suggest(res(bounce=False), None, None)).endswith(".")


def test_suggestion_is_saved_and_compared(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "DB", tmp_path / "t.db")
    for label, exit_px in (("BUY", 110), ("WAIT", 95), ("WAIT", 95)):
        t = practice.open_trade(f"{label}{exit_px}/USDT", "STRONG", 100, 95, 110, 250, suggestion=label)
        practice.close_trade(practice.open_trades()[-1], exit_px, "target" if exit_px == 110 else "stop", 1)
    d = practice.by_suggestion()
    assert d["BUY"]["n"] == 1 and d["BUY"]["wins"] == 1 and d["WAIT"]["n"] == 2 and d["WAIT"]["wins"] == 0


def test_one_line_keeps_decimals():
    a = suggest(res(), 91.5, IN)
    assert "-8.5%" in one_line(a)
