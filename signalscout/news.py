"""Real news and event data from credible sources (no dummy data).

Scheduled big events (can move all markets):
- Federal Reserve (federalreserve.gov): FOMC interest-rate decisions.
- St. Louis Fed FRED (fred.stlouisfed.org, free key): release dates of US inflation (CPI), jobs, producer prices, GDP, spending.
  (The US labour statistics site blocks automatic access, FRED publishes the same dates.)
Headlines (can hit one coin or the whole market): RSS feeds of CoinDesk, Cointelegraph and The Block.

A coin loses the "news" point when a big event is within 24h OR a headline from the last 24h mentions the coin
(or a market-wide name like Binance or Tether) together with a risk word (hack, exploit, delist, lawsuit, ...).
If a source cannot be reached we SAY so; we never pretend it was checked.
"""
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from .config import ROOT

load_dotenv(ROOT / ".env")

UA = {"User-Agent": "Mozilla/5.0 SignalScout/1.0 (personal research)"}
CACHE = ROOT / "data" / "news_cache.json"
CACHE_MIN = 30
NY = ZoneInfo("America/New_York")

FEEDS = {
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "Cointelegraph": "https://cointelegraph.com/rss",
    "The Block": "https://www.theblock.co/rss.xml",
}
FRED_RELEASES = {"US inflation report (CPI)": 10, "US jobs report": 50, "US producer prices (PPI)": 46,
                 "US economic growth (GDP)": 53, "US spending and income (PCE)": 54}

RISK = re.compile(r"\b(hack(ed|s|ers)?|exploit(ed|s)?|drain(ed|s)?|stolen|theft|breach(ed)?|rug[ -]?pull|delist(s|ed|ing)?|"
                  r"halt(s|ed)?|suspend(s|ed)?|outage|insolven\w*|bankrupt\w*|de-?peg(s|ged)?|lawsuit|sues|sued|"
                  r"charges|bans?|banned|investigation|fraud|collapse[sd]?)\b", re.I)
# Market-wide danger needs BOTH a big platform name AND a serious incident word (a lawsuit against a small firm is not enough)
MARKET_WIDE = re.compile(r"\b(binance|coinbase|tether|usdt|usdc|kraken|okx)\b", re.I)
MARKET_RISK = re.compile(r"\b(hack(ed|s)?|exploit(ed)?|drain(ed)?|stolen|breach(ed)?|insolven\w*|bankrupt\w*|de-?peg(s|ged)?|"
                         r"collapse[sd]?|halts? (all )?(withdrawals|trading)|suspends? (all )?(withdrawals|trading))\b", re.I)
NAMES = {"BTC": r"bitcoin(?![.\w])", "ETH": r"\bethereum\b|\bether\b", "BNB": r"\bbnb\b|binance coin", "XRP": r"\bxrp\b|ripple",
         "SOL": r"\bsolana\b", "DOGE": r"\bdogecoin\b|\bdoge\b", "ADA": r"\bcardano\b", "AVAX": r"avalanche", "LINK": r"chainlink",
         "UNI": r"uniswap", "NEAR": r"near protocol", "SUI": r"\bsui\b", "TON": r"toncoin|\bton\b", "TRX": r"\btron\b",
         "DOT": r"polkadot", "LTC": r"litecoin", "BCH": r"bitcoin cash", "SHIB": r"shiba", "PEPE": r"\bpepe\b",
         "AAVE": r"\baave\b", "ARB": r"arbitrum", "ATOM": r"\bcosmos\b", "ENA": r"\bethena\b|\bena\b",
         "WLD": r"worldcoin|\bwld\b", "TAO": r"bittensor", "ZEC": r"zcash", "HBAR": r"hedera", "XLM": r"stellar"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


# ---------- Federal Reserve ----------
def parse_fomc(page: str, year: int) -> list[dict]:
    i = page.find(f"{year} FOMC Meetings")
    if i < 0:
        return []
    j = page.find("FOMC Meetings", i + 20)
    seg = page[i: j if j > 0 else i + 40000]
    tokens = [t.strip() for t in re.sub(r"<[^>]+>", "|", seg).split("|") if t.strip()]
    out, month = [], None
    for t in tokens:
        low = t.lower()
        if re.fullmatch(r"[a-z]{3,9}(/[a-z]{3,9})?", low) and low[:3] in MONTHS:
            month = low
        elif month and re.fullmatch(r"\d{1,2}(-\d{1,2})?\*?", t):
            days = [int(x) for x in t.rstrip("*").split("-")]
            ms = [MONTHS[m[:3]] for m in month.split("/")]
            mo = ms[-1] if (len(ms) > 1 and days[-1] < days[0]) else ms[0]
            when = datetime(year, mo, days[-1], 14, 0, tzinfo=NY).astimezone(timezone.utc)   # decision 2:00 pm New York time
            out.append(dict(name="US interest-rate decision (Fed FOMC)", time=when, source="federalreserve.gov"))
            month = None
    return out


def fetch_fomc(now):
    r = requests.get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", headers=UA, timeout=20)
    r.raise_for_status()
    ev = []
    for y in (now.year, now.year + 1):
        ev += parse_fomc(r.text, y)
    return ev


# ---------- FRED ----------
def fetch_fred(key, now):
    ev = []
    for name, rid in FRED_RELEASES.items():
        r = requests.get("https://api.stlouisfed.org/fred/release/dates", timeout=20, headers=UA, params=dict(
            release_id=rid, api_key=key, file_type="json", include_release_dates_with_no_data="true",
            sort_order="desc", limit=40))
        r.raise_for_status()
        for d in r.json().get("release_dates", []):
            day = datetime.strptime(d["date"], "%Y-%m-%d")
            when = datetime(day.year, day.month, day.day, 8, 30, tzinfo=NY).astimezone(timezone.utc)   # 8:30 am New York time
            if when > now - timedelta(days=2):
                ev.append(dict(name=name, time=when, source="FRED (St. Louis Fed)"))
    return ev


# ---------- headlines ----------
def parse_rss(xml_text: str, source: str) -> list[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        try:
            t = parsedate_to_datetime(pub).astimezone(timezone.utc) if pub else None
        except Exception:
            t = None
        if title and t:
            out.append(dict(source=source, title=title, link=link, time=t))
    return out


def mentions(symbol: str, title: str) -> bool:
    base = symbol.split("/")[0]
    pat = NAMES.get(base)
    return bool((pat and re.search(pat, title, re.I)) or re.search(rf"\b{re.escape(base)}\b", title))


def risky(symbol: str, headlines, now, hours=24) -> list[dict]:
    """Headlines of the last `hours` that contain a risk word AND name this coin (or a market-wide name)."""
    out = []
    for h in headlines:
        if h.get("cat") == "delisting":           # a delisting notice stays relevant for 7 days
            if now - h["time"] <= timedelta(days=7) and mentions(symbol, h["title"]):
                out.append(h)
            continue
        if h.get("cat") in ("listing", "news"):   # listings and general Binance news are information, not risk
            continue
        if now - h["time"] > timedelta(hours=hours) or h["time"] > now + timedelta(minutes=5):
            continue
        t = h["title"]
        if (RISK.search(t) and mentions(symbol, t)) or (MARKET_RISK.search(t) and MARKET_WIDE.search(t)):
            out.append(h)
    return out


def about(symbol: str, headlines, now, hours=168, limit=8):
    return [h for h in headlines if now - h["time"] <= timedelta(hours=hours) and mentions(symbol, h["title"])][:limit]


# ---------- Binance official announcements ----------
BINANCE_URL = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
BINANCE_CATALOGS = {"delisting": 161, "listing": 48, "news": 49}      # Binance's own announcement categories


def parse_binance(payload: dict, cat: str) -> list[dict]:
    out = []
    for c in (payload.get("data") or {}).get("catalogs", []):
        for a in c.get("articles", []):
            try:
                t = datetime.fromtimestamp(a["releaseDate"] / 1000, timezone.utc)
                out.append(dict(source="Binance (official)", cat=cat, title=a["title"].strip(), time=t,
                                link="https://www.binance.com/en/support/announcement/detail/" + a["code"]))
            except Exception:
                continue
    return out


def fetch_binance() -> list[dict]:
    heads = []
    for cat, cid in BINANCE_CATALOGS.items():
        r = requests.get(BINANCE_URL, headers=UA, timeout=20, params=dict(type=1, pageNo=1, pageSize=20, catalogId=cid))
        r.raise_for_status()
        heads += parse_binance(r.json(), cat)
    return heads


# ---------- everything together ----------
def _ser(x):
    return {**x, "time": x["time"].isoformat()}


def _de(x):
    return {**x, "time": datetime.fromisoformat(x["time"])}


def get_news(force=False, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not force and CACHE.exists() and time.time() - CACHE.stat().st_mtime < CACHE_MIN * 60:
        try:
            d = json.loads(CACHE.read_text())
            d["events"] = [_de(e) for e in d["events"]]
            d["headlines"] = [_de(h) for h in d["headlines"]]
            return d
        except Exception:
            pass
    events, heads, ok, bad = [], [], [], []
    try:
        events += fetch_fomc(now)
        ok.append("Federal Reserve calendar")
    except Exception as e:
        bad.append(f"Federal Reserve calendar ({type(e).__name__})")
    key = (os.getenv("FRED_API_KEY") or "").strip()
    if key:
        try:
            events += fetch_fred(key, now)
            ok.append("FRED release dates (inflation, jobs, GDP)")
        except Exception as e:
            bad.append(f"FRED release dates ({type(e).__name__})")
    else:
        bad.append("FRED release dates (no free key set yet, so US inflation and jobs dates are NOT checked)")
    for name, url in FEEDS.items():
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            heads += parse_rss(r.text, name)
            ok.append(f"{name} headlines")
        except Exception as e:
            bad.append(f"{name} headlines ({type(e).__name__})")
    try:
        heads += fetch_binance()
        ok.append("Binance official announcements")
    except Exception as e:
        bad.append(f"Binance official announcements ({type(e).__name__})")
    heads.sort(key=lambda h: h["time"], reverse=True)
    d = dict(events=sorted(events, key=lambda e: e["time"]), headlines=heads[:300], ok=ok, bad=bad,
             fetched=now.isoformat())
    try:
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps({**d, "events": [_ser(e) for e in d["events"]], "headlines": [_ser(h) for h in d["headlines"]]}))
    except Exception:
        pass
    return d


def checked_note(d: dict) -> str:
    return "checked: " + ", ".join(d["ok"]) if d["ok"] else "NO news source could be reached"
