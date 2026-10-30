"""India cotton data for Cotton > India (runs in GitHub Actions; the Indian sites are not reachable from everywhere).

Sources
  CAI (caionline.in)  cab   Cotton Advisory Board / COCPC state area, production and yield, seasons 1991-92 on
                      bs    COCPC balance sheet (official)
                      cai   CAI crop committee monthly balance sheet, every monthly estimate kept (revision history)
                      trade raw cotton exports and imports by HS 5201/5202/5203 and cotton yarn, monthly
  USDA FAS PSD        psd   India cotton supply and demand (480-lb bales)
  NASA POWER          rain  monthly rainfall at cotton districts since 1991 and daily for the current season
  Yahoo               fx    USD/INR and ICE cotton nearby
Writes data/india/raw/*.json. History is cached: a stored season is not fetched again except the last two.
Usage: python pipelines/india_cotton.py [cab] [bs] [cai] [trade] [psd] [rain]   (no args = all)
"""
import io, json, sys, time, zipfile
from datetime import date, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "india" / "raw"
B = "https://www.caionline.in/"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "X-Requested-With": "XMLHttpRequest"}
TODAY = date.today()
CUR_SEASON_END = TODAY.year + (1 if TODAY.month >= 10 else 0)       # CAI season Oct-Sep, named by its ending year

# cotton districts used for rainfall (state, district, lat, lon); state rainfall = mean of its districts
DISTRICTS = [
    ("Punjab", "Bathinda", 30.21, 74.95), ("Punjab", "Mansa", 29.99, 75.40),
    ("Haryana", "Sirsa", 29.53, 75.03), ("Haryana", "Hisar", 29.15, 75.72),
    ("Rajasthan", "Sri Ganganagar", 29.90, 73.88), ("Rajasthan", "Hanumangarh", 29.58, 74.32), ("Rajasthan", "Bhilwara", 25.35, 74.63),
    ("Gujarat", "Rajkot", 22.30, 70.80), ("Gujarat", "Amreli", 21.60, 71.22), ("Gujarat", "Surendranagar", 22.73, 71.64),
    ("Gujarat", "Bhavnagar", 21.76, 72.15), ("Gujarat", "Bharuch", 21.70, 72.98),
    ("Maharashtra", "Yavatmal", 20.39, 78.13), ("Maharashtra", "Akola", 20.70, 77.00), ("Maharashtra", "Wardha", 20.74, 78.60),
    ("Maharashtra", "Jalgaon", 21.00, 75.56), ("Maharashtra", "Chh. Sambhajinagar", 19.88, 75.34), ("Maharashtra", "Nanded", 19.15, 77.30),
    ("Maharashtra", "Beed", 18.99, 75.76),
    ("Madhya Pradesh", "Khargone", 21.82, 75.61), ("Madhya Pradesh", "Khandwa", 21.83, 76.35), ("Madhya Pradesh", "Dhar", 22.60, 75.30),
    ("Telangana", "Adilabad", 19.67, 78.53), ("Telangana", "Warangal", 17.97, 79.60), ("Telangana", "Nalgonda", 17.05, 79.27),
    ("Andhra Pradesh", "Kurnool", 15.83, 78.04), ("Andhra Pradesh", "Guntur", 16.30, 80.45),
    ("Karnataka", "Raichur", 16.20, 77.36), ("Karnataka", "Dharwad", 15.46, 75.01), ("Karnataka", "Haveri", 14.79, 75.40),
    ("Tamil Nadu", "Perambalur", 11.23, 78.88),
    ("Odisha", "Kalahandi", 19.90, 83.16), ("Odisha", "Rayagada", 19.17, 83.42),
]


def jload(name, default):
    f = RAW / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else default


def jsave(name, obj):
    RAW.mkdir(parents=True, exist_ok=True)
    f = RAW / f"{name}.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=0, separators=(",", ":")))
    tmp.replace(f)


def session():
    s = requests.Session()
    s.headers.update(H)
    try:
        s.get(B, timeout=60)
    except Exception:
        pass
    return s


def post(s, path, data, tries=3):
    for i in range(tries):
        try:
            r = s.post(B + path, files={k: (None, str(v)) for k, v in data.items()}, headers={"Referer": B + path.rsplit("/", 1)[0]}, timeout=(20, 90))
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def cab(s):
    """State area (lakh ha), production (lakh 170-kg bales, pressed + loose), yield (kg/ha). Keyed by season end year."""
    d = jload("cab_area_production", {})
    for y in range(1992, CUR_SEASON_END + 1):
        if str(y) in d and y < CUR_SEASON_END - 1:
            continue
        try:
            j = post(s, "news_reports/cab_area_production/filter", {"year": y, "weight_type": "kg"})
        except Exception as e:
            print("cab", y, "failed", repr(e)[:120]); continue
        if j.get("status") != 1 or not j.get("rec"):
            continue
        rows = []
        for zone, lst in j["rec"].items():
            for r in lst if isinstance(lst, list) else []:
                rows.append({"zone": zone, "state": r.get("state"), "area": num(r.get("area")), "pressed": num(r.get("pressed_bales")),
                             "loose": num(r.get("loose_cotton")), "prod": num(r.get("total")), "yield": num(r.get("yield"))})
        if rows:
            d[str(y)] = {"season": f"{y-1}-{str(y)[2:]}", "rows": rows, "fetched": TODAY.isoformat()}
        time.sleep(1)
    jsave("cab_area_production", d)
    print("cab seasons", len(d), "latest", max(d) if d else None)


def bs(s):
    """COCPC balance sheet; each response holds the chosen season and the one before."""
    d = jload("cocpc_balance", {})
    for y in range(2012, CUR_SEASON_END + 1):
        if str(y) in d and y < CUR_SEASON_END - 1:
            continue
        try:
            j = post(s, "news_reports/cab_balancesheet/filter", {"year": y, "weight_type": "kg"})
        except Exception as e:
            print("bs", y, "failed", repr(e)[:120]); continue
        if j.get("status") != 1:
            continue
        for season in j.get("season", []):
            rec = {r["title"]: num(r.get(season)) for r in j.get("rec", []) if r.get(season) is not None}
            if rec:
                d[season] = {**rec, "remark": " ".join(j.get("remarks", {}).get(season, [])).strip()}
        time.sleep(1)
    jsave("cocpc_balance", d)
    print("cocpc seasons", sorted(d)[-3:])


CAI_FIELDS = ["opening_stock", "crop", "import", "total_supply", "mill_consumption", "ssi_consumption", "non_mill_consumption",
              "total_consumption", "export", "total_demand", "closing_stock"]


def cai(s):
    """CAI crop committee monthly estimates. year ids: 2026 -> 81 (id = year - 1945)."""
    d = jload("cai_monthly", {})
    for yr in range(2016, TODAY.year + 1):
        for m in range(1, 13):
            k = f"{yr}-{m:02d}"
            if date(yr, m, 1) > TODAY or (k in d and date(yr, m, 1) < TODAY - timedelta(days=120)):
                continue
            try:
                j = post(s, "details/cai/monthly", {"year": yr - 1945, "year_name": yr, "month": m, "unit": 0})
            except Exception as e:
                print("cai", k, "failed", repr(e)[:120]); continue
            for blk in ("current", "previous", "last_season_data"):
                for r in j.get(blk) or []:
                    kk = f"{r['year_name']}-{int(r['month_id']):02d}"
                    d[kk] = {"season": r.get("season_name"), "file": r.get("file_path"), "remark": r.get("remark") or "",
                             "posted": (r.get("c_date") or "")[:10], **{f: num(r.get(f)) for f in CAI_FIELDS}}
            time.sleep(0.8)
    jsave("cai_monthly", d)
    print("cai monthly estimates", len(d), "latest", max(d) if d else None)


def trade(s):
    """Raw cotton (HS 5201-5203) and cotton yarn exports/imports by month; one call returns every season shown on the site."""
    out = {}
    for name, path, var in (("raw_export", "raw/cotton/export/data", 5201), ("raw_import", "raw/cotton/import/data", 5201),
                            ("yarn_export", "yarn/cotton/export/data", 5205)):
        rows = {}
        for unit in (0, 1, 2):
            try:
                j = post(s, path, {"season": 37 + (CUR_SEASON_END - 2027), "unit": unit, "variety": var})
            except Exception as e:
                print(name, unit, "failed", repr(e)[:120]); continue
            for lst in (j.get("data") or {}).values():
                for r in lst:
                    k = f"{r['year_name']}-{int(r['month_id']):02d}"
                    rows.setdefault(k, {"season": r["season_name"]})[f"u{unit}"] = {kk[8:]: num(v) for kk, v in r.items() if kk.startswith("variety_")}
            out.setdefault("unit_labels", j.get("unit_list") or j.get("units"))
            time.sleep(1)
        out[name] = rows
    jsave("trade", out)
    print("trade", {k: (len(v), max(v) if v else None) for k, v in out.items() if isinstance(v, dict) and k != "unit_labels"})


def psd(_s=None):
    r = requests.get("https://apps.fas.usda.gov/psdonline/downloads/psd_cotton_csv.zip", timeout=180)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    import csv
    rows = csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode()))
    d = {}
    for x in rows:
        if x["Country_Name"] != "India" or int(x["Market_Year"]) < 2000:
            continue
        d.setdefault(x["Market_Year"], {})[x["Attribute_Description"]] = num(x["Value"])
    jsave("psd_india", d)
    print("psd India years", min(d), "-", max(d))


def rain(_s=None):
    """NASA POWER: monthly corrected precipitation (mm/day averaged -> mm/month) 1991 to last full year; daily for this year."""
    d = jload("rain", {"districts": {}})
    P = "https://power.larc.nasa.gov/api/temporal/"
    for st, dist, lat, lon in DISTRICTS:
        k = f"{st}|{dist}"
        rec = d["districts"].setdefault(k, {"state": st, "district": dist, "lat": lat, "lon": lon, "monthly": {}, "daily": {}})
        last_full = TODAY.year - 1
        if not any(m.startswith(str(last_full)) for m in rec["monthly"]):
            try:
                r = requests.get(P + "monthly/point", params={"parameters": "PRECTOTCORR", "community": "AG", "latitude": lat, "longitude": lon,
                                                            "start": 1991, "end": last_full, "format": "JSON"}, timeout=(20, 180))
                r.raise_for_status()
                v = r.json()["properties"]["parameter"]["PRECTOTCORR"]
                for ym, mmday in v.items():
                    if ym[4:] == "13" or mmday is None or mmday < 0:
                        continue
                    y, m = int(ym[:4]), int(ym[4:])
                    days = (date(y + (m == 12), m % 12 + 1, 1) - date(y, m, 1)).days
                    rec["monthly"][f"{y}-{m:02d}"] = round(mmday * days, 1)
            except Exception as e:
                print("rain monthly", k, "failed", repr(e)[:120])
            time.sleep(1)
        try:
            r = requests.get(P + "daily/point", params={"parameters": "PRECTOTCORR", "community": "AG", "latitude": lat, "longitude": lon,
                                                      "start": f"{TODAY.year}0501", "end": TODAY.strftime("%Y%m%d"), "format": "JSON"}, timeout=(20, 180))
            r.raise_for_status()
            v = r.json()["properties"]["parameter"]["PRECTOTCORR"]
            rec["daily"] = {f"{k8[:4]}-{k8[4:6]}-{k8[6:]}": x for k8, x in v.items() if x is not None and x >= 0}
        except Exception as e:
            print("rain daily", k, "failed", repr(e)[:120])
        time.sleep(1)
    d["updated"] = TODAY.isoformat()
    jsave("rain", d)
    n = sum(1 for r in d["districts"].values() if r["monthly"])
    print("rain districts with history", n, "of", len(DISTRICTS), "daily through", max((max(r["daily"]) for r in d["districts"].values() if r["daily"]), default=None))


def fx(_s=None):
    """USD/INR and ICE cotton nearby (Yahoo), daily since 2016, for Shankar-6 in cents/lb and its premium to ICE."""
    import yfinance as yf
    df = yf.download(["INR=X", "CT=F"], start="2016-01-01", progress=False, auto_adjust=False)["Close"]
    df = df.dropna(how="all")
    RAW.mkdir(parents=True, exist_ok=True)
    df.round(4).to_csv(RAW / "fx_ct.csv", index_label="date")
    print("fx/ICE rows", len(df), "through", df.index[-1].date())


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def main():
    jobs = sys.argv[1:] or ["cab", "bs", "cai", "trade", "psd", "rain", "fx"]
    s = session() if set(jobs) & {"cab", "bs", "cai", "trade"} else None
    for j in jobs:
        try:
            globals()[j](s)
        except Exception as e:
            import traceback
            print(j, "failed:", repr(e)[:200]); traceback.print_exc()


if __name__ == "__main__":
    main()
