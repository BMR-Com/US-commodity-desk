"""Key-events calendar for the desk (runs in GitHub Actions).

- USDA NASS releases scraped from the NASS calendar (current and next months), filtered to reports that move
  these markets (Crop Progress, Crop Production, Grain Stocks, Acreage, Hogs and Pigs, Cattle on Feed, Cold Storage,
  Milk Production, Dairy Products, Livestock Slaughter, ...).
- WASDE: official 2026 dates (USDA schedule as published by CME Group); later dates estimated until USDA publishes them.
- Weekly fixtures: export inspections (Mon), export sales (Thu), CFTC COT (Fri), NDPSR dairy prices (Wed),
  Buenos Aires Grain Exchange crop progress (Thu); CONAB monthly crop report (estimated).
- CME contract dates for the live contracts in data/technicals: first notice / last trade (rule-based, approximate).
All times US Central. Writes data/calendar/calendar.json.
"""
import json, re, time
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "calendar"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)"}
NASS = {  # report title -> (markets, importance 1-3)
    "Crop Progress": (["ZC", "ZS", "ZW", "KE"], 2), "Crop Production": (["ZC", "ZS", "ZW", "KE"], 3), "Crop Production Annual": (["ZC", "ZS", "ZW", "KE"], 3),
    "Grain Stocks": (["ZC", "ZS", "ZW", "KE"], 3), "Acreage": (["ZC", "ZS", "ZW", "KE"], 3), "Prospective Plantings": (["ZC", "ZS", "ZW", "KE"], 3),
    "Small Grains Summary": (["ZW", "KE"], 2), "Winter Wheat and Canola Seedings": (["ZW", "KE"], 2), "Fats & Oils": (["ZL", "ZM"], 1),
    "Grain Crushings and Co-Products Production": (["ZC"], 1), "Oilseed Crushings": (["ZS", "ZM", "ZL"], 1),
    "Hogs and Pigs": (["HE"], 3), "Quarterly Hogs and Pigs": (["HE"], 3), "Cattle on Feed": (["LE", "GF"], 3), "Cattle": (["LE", "GF"], 2),
    "Cold Storage": (["HE", "LE", "CB", "CSC"], 2), "Livestock Slaughter": (["HE", "LE"], 1), "Milk Production": (["DC", "GDK"], 2),
    "Dairy Products": (["DC", "GDK", "CSC", "CB", "GNF", "DY"], 2), "Agricultural Prices": (["ZC", "ZS", "DC"], 1), "Crop Values": (["ZC", "ZS"], 1),
}
WASDE_2026 = ["2026-01-12", "2026-02-10", "2026-03-10", "2026-04-09", "2026-05-12", "2026-06-11", "2026-07-10", "2026-08-12",
              "2026-09-11", "2026-10-09", "2026-11-10", "2026-12-10"]
HOLIDAYS = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05",
            "2027-09-06", "2027-11-25", "2027-12-24"]
CODES = "FGHJKMNQUVXZ"


def bday(d):
    return d.weekday() < 5 and str(d.date()) not in HOLIDAYS


def nass_events():
    ev = []
    seen_months = set()
    today = pd.Timestamp.now()
    urls = ["https://www.nass.usda.gov/Publications/Calendar/reports_by_date.php"]
    for k in range(0, 4):
        m = (today + pd.DateOffset(months=k))
        urls += [f"https://www.nass.usda.gov/Publications/Calendar/reports_by_date.php?month={m.month}&year={m.year}",
                 f"https://www.nass.usda.gov/Publications/Calendar/reports_by_date.php?month={m.month:02d}&year={m.year % 100:02d}"]
    for u in urls:
        try:
            t = requests.get(u, headers=H, timeout=60).text
        except Exception:
            continue
        for cell in re.findall(r'<td class="calendar[^"]*"\s*>(.*?)</td>', t, re.S):
            cur_time = None
            for tok in re.finditer(r'<span class="boldThis"><br>([^<]+)</span>|<a href="\./calendar-landing\.php\?source=n&amp;year=(\d+)&amp;month=(\d+)&amp;day=(\d+)&amp;report_id=(\d+)">([^<]+)</a>', cell):
                if tok.group(1):
                    cur_time = tok.group(1).strip()
                    continue
                y, mo, dd, rid, title = tok.group(2), tok.group(3), tok.group(4), tok.group(5), tok.group(6).strip()
                seen_months.add((y, mo))
                if title not in NASS:
                    continue
                mk, imp = NASS[title]
                tct = None
                if cur_time and "ET" in cur_time:
                    hh = pd.to_datetime(cur_time.replace(" ET", ""), format="%I:%M %p")
                    tct = (hh - pd.Timedelta(hours=1)).strftime("%-I:%M %p") + " CT"
                ev.append({"date": f"20{int(y):02d}-{int(mo):02d}-{int(dd):02d}", "time": tct, "event": f"NASS {title}", "cat": "USDA", "markets": mk, "importance": imp,
                           "link": f"https://www.nass.usda.gov/Publications/Calendar/calendar-landing.php?source=n&year={y}&month={mo}&day={dd}&report_id={rid}"})
        time.sleep(1)
    print("NASS months parsed:", sorted(seen_months))
    return ev


def rules(start, end):
    ev = []
    for d in pd.date_range(start, end):
        ds = str(d.date())
        wd = d.weekday()
        if wd == 0 and bday(d):
            ev.append({"date": ds, "time": "10:00 AM CT", "event": "USDA export inspections", "cat": "USDA", "markets": ["ZC", "ZS", "ZW", "KE"], "importance": 1})
        if wd == 1 and not bday(d - pd.Timedelta(days=1)):
            ev.append({"date": ds, "time": "10:00 AM CT", "event": "USDA export inspections (holiday-delayed)", "cat": "USDA", "markets": ["ZC", "ZS", "ZW", "KE"], "importance": 1})
        if wd == 3:
            dd = d if bday(d) else d + pd.Timedelta(days=1)
            ev.append({"date": str(dd.date()), "time": "7:30 AM CT", "event": "USDA weekly export sales", "cat": "USDA", "markets": ["ZC", "ZS", "ZM", "ZL", "ZW", "KE", "HE", "LE"], "importance": 2})
            ev.append({"date": ds, "time": "", "event": "Buenos Aires Grain Exchange crop progress (weekly)", "cat": "South America", "markets": ["ZS", "ZC", "ZW"], "importance": 1})
        if wd == 4:
            dd = d if bday(d) else d + pd.Timedelta(days=3)
            ev.append({"date": str(dd.date()), "time": "2:30 PM CT", "event": "CFTC Commitments of Traders", "cat": "CFTC", "markets": ["ALL"], "importance": 1})
        if wd == 2 and bday(d):
            ev.append({"date": ds, "time": "11:00 AM CT", "event": "USDA NDPSR dairy product prices (weekly)", "cat": "Dairy", "markets": ["DC", "GDK", "CSC", "CB", "GNF", "DY"], "importance": 2})
        if d.day == 1 or (d.day <= 3 and wd == 0):
            pass
    # WASDE
    for w in WASDE_2026:
        if start <= pd.Timestamp(w) <= end:
            ev.append({"date": w, "time": "11:00 AM CT", "event": "USDA WASDE", "cat": "USDA", "markets": ["ZC", "ZS", "ZM", "ZL", "ZW", "KE", "HE", "LE", "DC"], "importance": 3,
                       "link": "https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates"})
    for m in pd.date_range(pd.Timestamp("2027-01-01"), end, freq="MS"):
        d = m + pd.Timedelta(days=8)
        while not bday(d):
            d += pd.Timedelta(days=1)
        if d >= start:
            ev.append({"date": str(d.date()), "time": "11:00 AM CT", "event": "USDA WASDE (date estimated; USDA has not published the 2027 schedule here)", "cat": "USDA",
                       "markets": ["ZC", "ZS", "ZM", "ZL", "ZW", "KE"], "importance": 3, "estimated": True})
    # CONAB (Brazil) monthly grain survey: usually mid-month (estimated)
    for m in pd.date_range(start - pd.Timedelta(days=31), end, freq="MS"):
        d = m + pd.Timedelta(days=11)
        while d.weekday() != 3:
            d += pd.Timedelta(days=1)
        if start <= d <= end:
            ev.append({"date": str(d.date()), "time": "8:00 AM CT", "event": "CONAB Brazil crop survey (date estimated)", "cat": "South America", "markets": ["ZS", "ZC"], "importance": 3, "estimated": True})
    # Class & component prices (USDA AMS), Wednesday on or before the 5th
    for m in pd.date_range(start - pd.Timedelta(days=31), end, freq="MS"):
        d = m + pd.Timedelta(days=4)
        while d.weekday() != 2:
            d -= pd.Timedelta(days=1)
        if d < m:
            d += pd.Timedelta(days=7)
        if start <= d <= end:
            ev.append({"date": str(d.date()), "time": "11:00 AM CT", "event": "USDA class & component milk prices (DC/GDK settle)", "cat": "Dairy", "markets": ["DC", "GDK"], "importance": 3, "estimated": True})
    return ev


def contract_events(start, end):
    ev = []
    for f in sorted((ROOT / "data" / "technicals").glob("*.json")):
        t = json.loads(f.read_text())
        sym = t["sym"]
        for s in t["series"]:
            c = s["ticker"]
            if c == "cont" or s.get("kind") == "spread":
                continue
            L, y = c[len(sym)], int(c[len(sym) + 1:])
            m = CODES.index(L) + 1
            mstart = pd.Timestamp(y, m, 1)
            out = []
            if sym in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE"):
                fnd = mstart - pd.Timedelta(days=1)
                while not bday(fnd):
                    fnd -= pd.Timedelta(days=1)
                ltd = pd.Timestamp(y, m, 15) - pd.Timedelta(days=1)
                while not bday(ltd):
                    ltd -= pd.Timedelta(days=1)
                out = [(fnd, "first notice day"), (ltd, "last trading day")]
            elif sym == "HE":
                d, n = mstart, 0
                while True:
                    if bday(d):
                        n += 1
                        if n == 10:
                            break
                    d += pd.Timedelta(days=1)
                out = [(d, "last trading day (settles to Lean Hog Index)")]
            elif sym == "LE":
                d = mstart + pd.offsets.MonthEnd(0)
                while not bday(d):
                    d -= pd.Timedelta(days=1)
                out = [(d, "last trading day"), (mstart + pd.Timedelta(days=0), "delivery month begins")]
            elif sym == "GF":
                d = mstart + pd.offsets.MonthEnd(0)
                while d.weekday() != 3:
                    d -= pd.Timedelta(days=1)
                while not bday(d):  # holiday Thursday (Thanksgiving): the Thursday before
                    d -= pd.Timedelta(days=7)
                out = [(d, "last trading day (settles to CME Feeder Index)")]
            for d, what in out:
                if start <= d <= end:
                    ev.append({"date": str(d.date()), "time": "", "event": f"{t['name']} {s['label']}: {what}", "cat": "CME contract", "markets": [sym],
                               "importance": 2 if "first notice" in what or "settles" in what else 1, "estimated": True})
    return ev


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp.now().normalize() - pd.Timedelta(days=7)
    end = start + pd.Timedelta(days=97)
    ev = nass_events() + rules(start, end) + contract_events(start, end)
    df = pd.DataFrame(ev)
    df = df[(df.date >= str(start.date())) & (df.date <= str(end.date()))].drop_duplicates(["date", "event"])
    hol = [{"date": h, "time": "", "event": "US exchange holiday (CME ags closed)", "cat": "Holiday", "markets": ["ALL"], "importance": 2} for h in HOLIDAYS if str(start.date()) <= h <= str(end.date())]
    df = pd.concat([df, pd.DataFrame(hol)]).sort_values(["date", "importance"], ascending=[True, False])
    df["estimated"] = df.get("estimated", False).fillna(False).astype(bool)
    rows = [{k: (None if (isinstance(v, float) and v != v) else v) for k, v in r.items()} for r in df.astype(object).to_dict("records")]
    (OUT / "calendar.json").write_text(json.dumps({"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "events": rows}, indent=0, allow_nan=False))
    print(len(rows), "events;", df.cat.value_counts().to_dict())


if __name__ == "__main__":
    main()
