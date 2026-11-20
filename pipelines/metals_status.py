"""Metals desk data status and release calendar (lean port of the softs desk's data_status / release_calendar).

Writes data/metals/status.json (one row per source: latest data date, cadence, late limit, state) and
data/metals/release_calendar.json (when each report is due next; used by the desk calendar and the Data status tab).
Ages are business days for daily sources and calendar days for the rest. A source is late when its age is over its limit.
Manual sources (COMEX stocks, which need the Mac collector) are flagged "needs Mac" and never turn the catch-up job red.

Usage: python pipelines/metals_status.py [--strict]     --strict exits 1 if an automatic source is late or missing.
"""
import csv, json, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
RAW = D / "metals" / "raw"
TODAY = datetime.now(ZoneInfo("America/New_York")).date()


def J(p):
    return json.loads((D / p).read_text())


def max_csv(p, col="date", where=None):
    with open(RAW / p) as f:
        return max((r[col] for r in csv.DictReader(f) if r.get(col) and (where is None or where(r))), default=None)


def contracts_last(sym):
    with open(D / "contracts" / f"{sym}.csv") as f:
        return max((r["date"] for r in csv.DictReader(f)), default=None)


def tech_last(sym):
    t = J(f"technicals/{sym}.json")
    s = next((x for x in t["series"] if x["ticker"] == t.get("default")), t["series"][0])
    return s["bars"][-1][0]


def wgc_quarter_end():
    q = sorted(json.loads((RAW / "wgc_gdt.json").read_text()))[-1]          # e.g. "2026-Q3"
    return month_end(f"{q[:4]}-{3 * int(q[-1]):02d}")


def month_end(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return str(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def icsg_issued():
    idx = sorted(p for p in (RAW / "icsg").glob("*.json") if p.name != "index.json")
    return json.loads(idx[-1].read_text()).get("issued")


def iai_month():
    return month_end(max_csv("iai_primary.csv", "month"))


def usgs_year():
    fs = sorted(RAW.glob("usgs_mcs*.csv"))
    return f"{fs[-1].stem[-4:]}-01-31" if fs else None


B, C = "bd", "d"
# (group, source, cadence, limit, unit, manual, getter, used in)
SOURCES = [
    ("Prices", "COMEX gold, silver, copper, aluminum futures (Yahoo, TradingView fallback)", "daily", 2, B, False, lambda: min(tech_last(s) for s in ("GC", "SI", "HG")), "prices, curve, technicals, overview"),
    ("Prices", "Aluminum Midwest premium futures, AUP (Yahoo/TradingView)", "daily", 3, B, False, lambda: tech_last("AUP"), "aluminum desk"),
    ("Prices", "Per-contract history (TradingView)", "daily", 3, B, False, lambda: contracts_last("GC"), "seasonality, spreads, COT money-under-water"),
    ("Positions", "CFTC COT, positions date (gold, silver, copper, aluminum MWP)", "weekly (Tue, out Fri)", 10, C, False, lambda: min(J(f"cot_desk/{s}.json")["date"] for s in ("GC", "SI", "HG", "AUP")), "COT panels, overview"),
    ("Gold", "SPDR GLD holdings", "daily", 3, B, False, lambda: max_csv("etf_gld.csv"), "ETF flows"),
    ("Gold", "iShares IAU holdings (daily snapshot)", "daily", 3, B, False, lambda: max_csv("etf_ishares.csv", where=lambda r: r["fund"] == "IAU"), "ETF flows"),
    ("Gold", "US 10-yr real yield (Treasury)", "daily", 3, B, False, lambda: max_csv("real_yields.csv"), "gold drivers"),
    ("Gold", "US dollar index (Yahoo)", "daily", 3, B, False, lambda: max_csv("dxy.csv"), "gold drivers"),
    ("Gold", "World Gold Council supply and demand (quarter end)", "quarterly (~5 weeks after quarter end)", 135, C, False, wgc_quarter_end, "gold S&D"),
    ("Silver", "iShares SLV holdings (daily snapshot)", "daily", 3, B, False, lambda: max_csv("etf_ishares.csv", where=lambda r: r["fund"] == "SLV"), "silver ETF"),
    ("Silver", "Silver Institute supply and demand (page checked daily; survey annual, April)", "annual", 400, C, False, lambda: json.loads((RAW / "silver_institute.json").read_text())["fetched"], "silver S&D"),
    ("Copper", "LME copper cash, 3-month, stocks (westmetall.com)", "daily", 3, B, False, lambda: max_csv("lme_cu.csv"), "copper desk, COMEX–LME arbitrage"),
    ("Copper", "ICSG monthly press release (issue date)", "monthly (3rd-4th week)", 40, C, False, icsg_issued, "copper balance"),
    ("Aluminum", "LME aluminium cash, 3-month, stocks (westmetall.com)", "daily", 3, B, False, lambda: max_csv("lme_al.csv"), "aluminum desk"),
    ("Aluminum", "IAI primary aluminium production (data month)", "monthly (~20th of next month)", 55, C, False, iai_month, "aluminum supply"),
    ("All metals", "USGS Mineral Commodity Summaries (edition)", "annual (late January)", 400, C, False, usgs_year, "world production and reserves"),
    ("All metals", "COMEX warehouse stocks (CME daily reports; via Mac collector)", "daily", 3, B, True, lambda: max_csv("comex_stocks.csv"), "exchange stocks"),
]


def bd_between(a, b):
    return int(np.busday_count(a, b))


def status():
    rows = []
    for g, name, cad, lim, unit, manual, fn, used in SOURCES:
        try:
            latest = fn()
        except Exception:
            latest = None
        age = None
        if latest:
            d0 = date.fromisoformat(latest[:10])
            age = bd_between(d0, TODAY) if unit == B else (TODAY - d0).days
        st = "missing" if latest is None else "late" if age > lim else "ok"
        if manual and st != "ok":
            st = "needs Mac"
        rows.append({"group": g, "source": name, "latest": latest, "age": age, "age_unit": "bd" if unit == B else "days", "limit": lim, "cadence": cad, "manual": manual, "state": st, "used_in": used})
    return rows


def nth_weekday(y, m, wd, n):
    d = date(y, m, 1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d + timedelta(days=7 * (n - 1))


def bday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def calendar(rows):
    up = []
    end = TODAY + timedelta(days=120)
    d = TODAY
    while d <= end:
        if d.weekday() == 4:
            up.append({"date": str(d), "time_ct": "2:30 PM CT", "event": "CFTC Commitments of Traders (metals)", "markets": ["GC", "SI", "HG", "ALI"], "importance": 1, "calendar": False, "estimated": False})
        d += timedelta(days=1)
    for k in range(0, 5):
        y, m = (TODAY.year + (TODAY.month - 1 + k) // 12), (TODAY.month - 1 + k) % 12 + 1
        up.append({"date": str(bday(date(y, m, 20))), "time_ct": "", "event": "IAI primary aluminium production (monthly)", "markets": ["ALI"], "importance": 2, "estimated": True,
                   "link": "https://international-aluminium.org/statistics/primary-aluminium-production/"})
        up.append({"date": str(bday(date(y, m, 22))), "time_ct": "", "event": "ICSG copper market press release (monthly)", "markets": ["HG"], "importance": 2, "estimated": True,
                   "link": "https://icsg.org/press-releases/"})
        if m in (1, 4, 7, 10):
            up.append({"date": str(nth_weekday(y, m, 3, 5) if nth_weekday(y, m, 3, 5).month == m else nth_weekday(y, m, 3, 4)), "time_ct": "", "event": "World Gold Council Gold Demand Trends (quarterly)",
                       "markets": ["GC", "SI"], "importance": 2, "estimated": True, "link": "https://www.gold.org/goldhub/research/gold-demand-trends"})
        if m == 1:
            up.append({"date": str(bday(date(y, 1, 31))), "time_ct": "", "event": "USGS Mineral Commodity Summaries (annual)", "markets": ["GC", "SI", "HG", "ALI"], "importance": 1, "estimated": True,
                       "link": "https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries"})
        if m == 4:
            up.append({"date": str(nth_weekday(y, m, 2, 3)), "time_ct": "", "event": "Silver Institute World Silver Survey (annual)", "markets": ["SI"], "importance": 2, "estimated": True,
                       "link": "https://silverinstitute.org/silver-supply-demand/"})
        if m == 11:
            up.append({"date": str(nth_weekday(y, m, 2, 3)), "time_ct": "", "event": "Silver Institute interim silver market review", "markets": ["SI"], "importance": 1, "estimated": True,
                       "link": "https://silverinstitute.org/"})
    up = sorted([u for u in up if str(TODAY - timedelta(days=3)) <= u["date"] <= str(end)], key=lambda u: u["date"])
    timing = [
        {"report": "COMEX futures settlement", "when": "Daily, 1:30 pm ET (gold, silver), 1:00 pm ET (copper)", "desk": "metals workflow 5:50 pm ET weekdays (clock), 9:10 am ET refresh"},
        {"report": "CFTC Commitments of Traders", "when": "Friday 3:30 pm ET (Tuesday positions)", "desk": "metals workflow 3:45 pm ET Friday (clock), retry 5:50 pm; data workflow 4:40 pm CT"},
        {"report": "ETF holdings (GLD, IAU, SLV)", "when": "Each trading day, evening / next morning", "desk": "9:10 am and 5:50 pm ET weekdays"},
        {"report": "LME official prices and stocks", "when": "Each LME day, London afternoon (stocks 9:00 am London, a day's lag)", "desk": "9:10 am and 5:50 pm ET weekdays"},
        {"report": "COMEX warehouse stocks", "when": "Each trading day, evening", "desk": "Mac collector (cmegroup.com blocks GitHub); parsed at the next metals run"},
        {"report": "ICSG monthly press release", "when": "3rd-4th week of the month (data two months back)", "desk": "checked every metals run; catch-up job daily"},
        {"report": "IAI primary aluminium production", "when": "Around the 20th (previous month)", "desk": "checked every metals run; catch-up job daily"},
        {"report": "World Gold Council Gold Demand Trends", "when": "Quarterly, about 4-5 weeks after quarter end", "desk": "checked every metals run; catch-up job daily"},
        {"report": "Silver Institute World Silver Survey", "when": "Annual (April), interim review (November)", "desk": "page checked every run"},
        {"report": "USGS Mineral Commodity Summaries", "when": "Annual (late January)", "desk": "checked every run until the new edition is stored"},
    ]
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "upcoming": up, "timing": timing}


def main():
    rows = status()
    (D / "metals").mkdir(parents=True, exist_ok=True)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "today": str(TODAY), "sources": rows}
    (D / "metals" / "status.json").write_text(json.dumps(out, indent=1))
    (D / "metals" / "release_calendar.json").write_text(json.dumps(calendar(rows), indent=1))
    bad = [r for r in rows if r["state"] in ("late", "missing") and not r["manual"]]
    for r in rows:
        print(f"{r['state']:10} {str(r['latest']):12} {r['source']}")
    if bad and "--strict" in sys.argv:
        print("::error::metals sources late or missing: " + "; ".join(r["source"] for r in bad))
        sys.exit(1)


if __name__ == "__main__":
    main()
