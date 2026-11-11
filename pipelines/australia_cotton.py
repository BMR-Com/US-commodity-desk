"""Australian cotton data for the desk crop model (runs in GitHub Actions; the Claude workspace cannot reach these sites).

Sources (all public, no keys)
  Cotton Australia statistics page   stats     planted hectares and bales by season, 1989-90 onwards (charts on the page)
  USDA FAS PSD                       psd       Australia cotton supply and demand, 1960 onwards (1000 480-lb bales, 1000 ha)
  ABS Data API AG_BROADACRE          abs       cotton area / production by state (ABS agricultural census and surveys)
  ABS Data API MERCH_EXP (SITC 263)  exports   monthly raw-cotton exports by state of origin
  BOM Water Data Online (KiWIS)      storage   daily storage volume (ML) of the dams that supply the cotton valleys, 1990 onwards
  Open-Meteo ERA5 archive + forecast rain      daily rain at the main cotton towns, 1990 onwards, plus 16-day forecast
  Yahoo                              prices    ICE cotton nearby (CT=F) and AUD/USD

ABARES files (Australian Crop Report data, Agricultural Commodity Statistics) sit behind a bot check and the old
data.daff.gov.au archive no longer answers, so ABARES and Cotton Australia forecasts are kept by hand in
data/australia/raw/forecasts_manual.json.

Everything goes to data/australia/raw/. Each step is independent: a failure is printed and the stored file is kept.
Usage: python pipelines/australia_cotton.py [stats] [psd] [abs] [exports] [storage] [rain] [prices]   (no args = all)
"""
import csv, gzip, io, json, re, sys, time, zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "australia" / "raw"
TODAY = date.today()
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
STATUS = {}

# Cotton towns: (id, label, state, valley, lat, lon)
SITES = [
    ("emerald", "Emerald", "QLD", "Central Highlands", -23.53, 148.16),
    ("dalby", "Dalby", "QLD", "Darling Downs", -27.18, 151.26),
    ("stgeorge", "St George", "QLD", "Condamine-Balonne", -28.04, 148.58),
    ("goondiwindi", "Goondiwindi", "QLD", "Border Rivers", -28.55, 150.31),
    ("moree", "Moree", "NSW", "Gwydir", -29.47, 149.85),
    ("narrabri", "Narrabri", "NSW", "Namoi", -30.32, 149.78),
    ("bourke", "Bourke", "NSW", "Barwon-Darling", -30.09, 145.94),
    ("warren", "Warren", "NSW", "Macquarie", -31.70, 147.83),
    ("hillston", "Hillston", "NSW", "Lachlan", -33.48, 145.53),
    ("griffith", "Griffith", "NSW", "Murrumbidgee", -34.29, 146.04),
]
# Dams supplying the cotton valleys: (search pattern for the BOM station name, valley, state)
DAMS = [
    ("FAIRBAIRN*", "Central Highlands (Nogoa)", "QLD"),
    ("BEARDMORE*", "Condamine-Balonne", "QLD"),
    ("E.J. BEARDMORE*", "Condamine-Balonne", "QLD"),
    ("LESLIE DAM*", "Darling Downs", "QLD"),
    ("COOLMUNDA*", "Border Rivers", "QLD"),
    ("GLENLYON*", "Border Rivers", "NSW/QLD"),
    ("PINDARI*", "Border Rivers", "NSW"),
    ("COPETON*", "Gwydir", "NSW"),
    ("KEEPIT*", "Namoi", "NSW"),
    ("SPLIT ROCK*", "Namoi", "NSW"),
    ("BURRENDONG*", "Macquarie", "NSW"),
    ("WYANGALA*", "Lachlan", "NSW"),
    ("BURRINJUCK*", "Murrumbidgee", "NSW"),
    ("BLOWERING*", "Murrumbidgee", "NSW"),
]
KIWIS = "http://www.bom.gov.au/waterdata/services"


def jload(name, default=None):
    f = RAW / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else default


def jsave(name, obj):
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = RAW / f".{name}.json.tmp"
    tmp.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(RAW / f"{name}.json")


def get(url, params=None, timeout=90, **kw):
    for i in range(3):
        try:
            r = requests.get(url, params=params, headers={**H, **kw.pop("headers", {})}, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code}")
            r.raise_for_status()
            return r
        except Exception as e:
            if i == 2:
                raise
            time.sleep(5 * (i + 1))


# ---------------------------------------------------------------- Cotton Australia statistics page
def stats(_s=None):
    r = get("https://cottonaustralia.com.au/statistics")
    t = r.text
    out = {}
    # each chart: a title paragraph, then a google.visualization DataTable with addColumn(...) and addRows([[new Date(Y,0), v, ...], ...])
    for m in re.finditer(r"function ChartID(\d+)\(\)\s*\{(.*?)chartNames\.push", t, re.S):
        body = m.group(2)
        before = re.sub(r"<[^>]+>", " ", t[max(0, m.start() - 600):m.start()])
        title = re.sub(r"\s+", " ", before).strip()
        title = re.split(r"(?:graph for further data\.|chartNames\.push\(ChartID\d+\);)", title)[-1].strip()[-200:]
        cols = re.findall(r"addColumn\('(\w+)',\s*'([^']*)'\)", body)
        rows = re.findall(r"\[new Date\((\d{4}),\s*\d+\),([^\]]*)\]", body)
        names = [c[1] for c in cols[1:]]
        ser = {n: {} for n in names}
        for y, rest in rows:
            vals = [v.strip() for v in rest.split(",")]
            for n, v in zip(names, vals):
                if v and v != "null":
                    try:
                        ser[n][int(y)] = float(v)
                    except ValueError:
                        pass
        out[f"chart{m.group(1)}"] = {"title": title, "series": ser}
    if not out:
        raise RuntimeError("no charts found on the Cotton Australia statistics page")
    jsave("cotton_australia_stats", {"fetched": TODAY.isoformat(), "note": "year = calendar year the season finished (2024 = 2023-24)", "charts": out})
    print("Cotton Australia charts:", {k: (v["title"][:60], {n: (min(s), max(s)) for n, s in v["series"].items() if s}) for k, v in out.items()})


# ---------------------------------------------------------------- USDA PSD
def psd(_s=None):
    r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_cotton_csv.zip", timeout=180)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    rows = csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode()))
    d = {}
    for x in rows:
        if x["Country_Name"] != "Australia":
            continue
        try:
            d.setdefault(x["Market_Year"], {})[x["Attribute_Description"]] = float(x["Value"])
        except ValueError:
            pass
        d[x["Market_Year"]]["_month"] = x.get("Calendar_Year", "") + "-" + x.get("Month", "")
    jsave("psd_australia", {"fetched": TODAY.isoformat(), "unit": "1000 ha / 1000 480-lb bales / kg/ha",
                            "note": "Market_Year = year planting starts (2026 = 2026-27 crop, harvested 2027)", "years": d})
    print("PSD Australia years", min(d), "-", max(d))


# ---------------------------------------------------------------- ABS
def abs_(_s=None):
    """AG_BROADACRE, all dimensions as CSV with labels; keep only rows that mention cotton."""
    keep, hdr = [], None
    r = get("https://data.api.abs.gov.au/rest/data/ABS,AG_BROADACRE/all", params={"format": "csvfilewithlabels"}, timeout=240,
            headers={"Accept": "application/vnd.sdmx.data+csv;labels=both"})
    rd = csv.reader(io.StringIO(r.text))
    for row in rd:
        if hdr is None:
            hdr = row; continue
        if any("otton" in c for c in row):
            keep.append(row)
    if not keep:
        raise RuntimeError(f"ABS AG_BROADACRE has no cotton rows ({len(r.text)} bytes)")
    RAW.mkdir(parents=True, exist_ok=True)
    with open(RAW / "abs_broadacre_cotton.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(hdr); w.writerows(keep)
    print("ABS broadacre cotton rows", len(keep), "columns", hdr)


def exports(_s=None):
    """Monthly exports of SITC 263 (raw cotton), total of all destinations, by state of origin."""
    r = get("https://data.api.abs.gov.au/rest/data/ABS,MERCH_EXP/263..", params={"format": "csvfilewithlabels", "startPeriod": "2010-01"},
            timeout=240, headers={"Accept": "application/vnd.sdmx.data+csv;labels=both"})
    rows = list(csv.reader(io.StringIO(r.text)))
    if len(rows) < 2:
        raise RuntimeError("no export rows")
    hdr = rows[0]
    ci = {h: i for i, h in enumerate(hdr)}
    # keep all-countries total only if present, else all rows (summed later)
    with open(RAW / "abs_exports_263.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)
    print("ABS exports SITC 263 rows", len(rows) - 1, "columns", hdr)


# ---------------------------------------------------------------- BOM storages
def _kiwis(params):
    p = {"service": "kisters", "type": "queryServices", "datasource": 0, "format": "json", **params}
    return get(KIWIS, params=p, timeout=180).json()


def storage(_s=None):
    meta = jload("storage_meta", {})
    f = RAW / "storage_daily.csv.gz"
    have = {}
    if f.exists():
        with gzip.open(f, "rt") as g:
            for row in csv.DictReader(g):
                have.setdefault(row["dam"], {})[row["date"]] = float(row["ml"])
    for pat, valley, state in DAMS:
        try:
            st = _kiwis({"request": "getStationList", "station_name": pat})[1:]
            st = [s for s in st if -36.5 < float(s[3] or 0) < -22 and 140 < float(s[4] or 0) < 154]
            if not st:
                print("storage: no station for", pat); continue
            name, no = st[0][0], st[0][1]
            if name in meta and meta[name].get("ts_id"):
                ts = meta[name]["ts_id"]
            else:
                tl = _kiwis({"request": "getTimeseriesList", "station_no": no, "returnfields": "ts_id,ts_name,parametertype_name,ts_unitname,coverage"})
                hd = tl[0]; tl = [dict(zip(hd, x)) for x in tl[1:]]
                cand = [x for x in tl if x["parametertype_name"] == "Storage Volume" and x["ts_name"].endswith("DailyMean.24HR") and x.get("from")]
                cand.sort(key=lambda x: (not x["ts_name"].startswith("DMQaQc"), x.get("from") or "9999"))
                if not cand:
                    print("storage: no daily volume series for", name); continue
                ts = cand[0]["ts_id"]
            start = "1990-01-01"
            if have.get(name):
                start = (max(date.fromisoformat(d) for d in have[name]) - timedelta(days=45)).isoformat()
            j = _kiwis({"request": "getTimeseriesValues", "ts_id": ts, "from": start, "to": TODAY.isoformat()})
            n = 0
            for t, v in j[0]["data"]:
                if v is None:
                    continue
                have.setdefault(name, {})[t[:10]] = round(float(v), 1); n += 1
            meta[name] = {"station_no": no, "ts_id": ts, "valley": valley, "state": state, "lat": float(st[0][3]), "lon": float(st[0][4])}
            print(f"storage {name}: {n} values from {start}")
        except Exception as e:
            print("storage", pat, "failed", repr(e)[:160])
        time.sleep(1)
    if not have:
        raise RuntimeError("no storage data")
    RAW.mkdir(parents=True, exist_ok=True)
    tmp = RAW / ".storage_daily.csv.gz.tmp"
    with gzip.open(tmp, "wt", newline="") as g:
        w = csv.writer(g); w.writerow(["dam", "date", "ml"])
        for dam in sorted(have):
            for d in sorted(have[dam]):
                w.writerow([dam, d, have[dam][d]])
    tmp.replace(f)
    jsave("storage_meta", meta)


# ---------------------------------------------------------------- rain (Open-Meteo)
def rain(_s=None):
    f = RAW / "rain_daily.csv.gz"
    have = {}
    if f.exists():
        with gzip.open(f, "rt") as g:
            for row in csv.DictReader(g):
                have.setdefault(row["site"], {})[row["date"]] = float(row["mm"])
    fc = {}
    for sid, lbl, st, valley, lat, lon in SITES:
        try:
            start = "1990-01-01"
            if have.get(sid):
                start = (max(date.fromisoformat(d) for d in have[sid]) - timedelta(days=20)).isoformat()
            end = (TODAY - timedelta(days=2)).isoformat()
            j = get("https://archive-api.open-meteo.com/v1/archive", params={"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
                                                                             "daily": "precipitation_sum", "timezone": "Australia/Sydney"}, timeout=180).json()
            for d, v in zip(j["daily"]["time"], j["daily"]["precipitation_sum"]):
                if v is not None:
                    have.setdefault(sid, {})[d] = round(v, 1)
            k = get("https://api.open-meteo.com/v1/forecast", params={"latitude": lat, "longitude": lon, "daily": "precipitation_sum",
                                                                      "past_days": 7, "forecast_days": 16, "timezone": "Australia/Sydney"}).json()
            fc[sid] = dict(zip(k["daily"]["time"], k["daily"]["precipitation_sum"]))
            print(f"rain {sid}: archive from {start}, forecast {len(fc[sid])} days")
        except Exception as e:
            print("rain", sid, "failed", repr(e)[:160])
        time.sleep(1.5)
    if not have:
        raise RuntimeError("no rain data")
    tmp = RAW / ".rain_daily.csv.gz.tmp"
    with gzip.open(tmp, "wt", newline="") as g:
        w = csv.writer(g); w.writerow(["site", "date", "mm"])
        for s in sorted(have):
            for d in sorted(have[s]):
                w.writerow([s, d, have[s][d]])
    tmp.replace(f)
    jsave("rain_forecast", {"fetched": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "sites": fc})
    jsave("sites", [dict(zip(["id", "label", "state", "valley", "lat", "lon"], s)) for s in SITES])


# ---------------------------------------------------------------- prices
def prices(_s=None):
    import yfinance as yf
    df = yf.download(["CT=F", "AUDUSD=X"], start="2000-01-01", progress=False, auto_adjust=False)["Close"].dropna(how="all")
    RAW.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(RAW / "prices.csv", index_label="date")
    print("prices rows", len(df), "through", df.index[-1].date())


STEPS = {"stats": stats, "psd": psd, "abs": abs_, "exports": exports, "storage": storage, "rain": rain, "prices": prices}

if __name__ == "__main__":
    want = [a for a in sys.argv[1:] if a in STEPS] or list(STEPS)
    for k in want:
        t0 = time.time()
        try:
            STEPS[k]()
            STATUS[k] = {"ok": True}
        except Exception as e:
            print(f"::warning::{k} failed: {repr(e)[:300]}")
            STATUS[k] = {"ok": False, "err": repr(e)[:300]}
        STATUS[k]["at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"); STATUS[k]["secs"] = round(time.time() - t0)
    old = jload("collect_status", {})
    old.update(STATUS)
    jsave("collect_status", old)
