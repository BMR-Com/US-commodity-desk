"""Fetch USDA livestock data (open datamart, no key) into data/livestock/raw/.

Selected sections of mandatory price reports, full history:
- Hogs: LM_HG201 prior-day slaughtered swine (CME Lean Hog Index inputs), LM_HG214 weekly
  national direct swine, LM_PK602 pork cutout.
- Cattle: LM_CT100 5-area daily negotiated, LM_CT150 5-area weekly, LSWFEDCC weekly fed cattle
  comprehensive, LM_XB403 boxed beef cutout.
Plus NASS QuickStats (needs NASS_API_KEY) and ERS meat supply/disappearance.
"""
import io, os, sys, time, urllib.parse, zipfile
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usda_dairy import DM, H, get, slug, write_rows  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "livestock" / "raw"
REPORTS = {
    2511: ("hg201_slaughtered_swine", ["Barrows/Gilts", "Carcass Measurements"]),
    2524: ("hg214_weekly_swine", ["Weekly Volume and Weighted Average Price of Barrows/Gilts by Purchase Type"]),
    2498: ("pk602_pork_cutout", ["Cutout and Primal Values", "Current Volume"]),
    2466: ("ct100_5area_daily", ["Detail"]),
    2477: ("ct150_5area_weekly", ["Detail"]),
    2700: ("fedcc_weekly", ["Weighted Average", "Weekly Fed Cattle Comprehensive"]),
    2453: ("xb403_boxed_beef", ["Current Cutout Values", "Current Volume"]),
}
NASS = {  # name: QuickStats filter
    "hogs_inventory": {"commodity_desc": "HOGS", "statisticcat_desc": "INVENTORY", "agg_level_desc": "NATIONAL", "freq_desc": "POINT IN TIME"},
    "hogs_pig_crop": {"commodity_desc": "HOGS", "statisticcat_desc": "PIG CROP", "agg_level_desc": "NATIONAL"},
    "hogs_litter_rate": {"commodity_desc": "HOGS", "short_desc": "HOGS - LITTER RATE, MEASURED IN PIGS / LITTER", "agg_level_desc": "NATIONAL"},
    "hogs_slaughter": {"commodity_desc": "HOGS", "statisticcat_desc": "SLAUGHTERED", "agg_level_desc": "NATIONAL", "freq_desc": "MONTHLY"},
    "cattle_on_feed": {"commodity_desc": "CATTLE", "short_desc__LIKE": "ON FEED", "agg_level_desc": "NATIONAL"},
    "cattle_inventory": {"commodity_desc": "CATTLE", "statisticcat_desc": "INVENTORY", "agg_level_desc": "NATIONAL", "freq_desc": "POINT IN TIME"},
    "cattle_slaughter": {"commodity_desc": "CATTLE", "statisticcat_desc": "SLAUGHTERED", "agg_level_desc": "NATIONAL", "freq_desc": "MONTHLY"},
    "cold_storage_pork": {"commodity_desc": "PORK", "statisticcat_desc": "STOCKS", "agg_level_desc": "NATIONAL"},
    "cold_storage_beef": {"commodity_desc": "BEEF", "statisticcat_desc": "STOCKS", "agg_level_desc": "NATIONAL"},
}
ERS = {
    "ers_meat_supply_disappearance": "https://www.ers.usda.gov/media/5531/meat-supply-and-disappearance-tables.xlsx",
    "ers_livestock_machine_readable": "https://www.ers.usda.gov/media/5539/livestock-domestic-data-machine-readable-files.zip",
}


def datamart():
    """Full history per section, fetched in yearly report_date chunks (API caps a call at ~100k rows)."""
    this_year = time.gmtime().tm_year
    for rid, (name, sections) in REPORTS.items():
        for sec in sections:
            rows = []
            for y in range(2001, this_year + 1):
                q = urllib.parse.quote(f"report_date=01/01/{y}:12/31/{y}", safe="=/:")
                r = get(f"{DM}/{rid}/{urllib.parse.quote(sec, safe='/')}?q={q}")
                if r is None:
                    continue
                j = r.json()
                part = j.get("results", []) if isinstance(j, dict) else []
                if isinstance(j, dict) and j.get("stats", {}).get("totalRows:", 0) > len(part):
                    print(f"  WARNING {rid} {sec} {y}: {len(part)} of {j['stats']['totalRows:']} rows")
                rows += part
            n = write_rows(OUT / name / f"{slug(sec)}.csv", rows)
            print(f"{rid} {name} / {sec}: {n} rows")


def nass():
    key = os.getenv("NASS_API_KEY")
    if not key:
        print("no NASS_API_KEY")
        return
    import csv
    for name, q in NASS.items():
        rows = []
        for y0, y1 in ((1990, 2009), (2010, 2030)):
            params = {"key": key, "year__GE": y0, "year__LE": y1, "format": "CSV", **q}
            try:
                r = requests.get("https://quickstats.nass.usda.gov/api/api_GET/", params=params, headers=H, timeout=300)
            except Exception as e:
                print(name, e)
                continue
            if r.status_code != 200:
                print(name, y0, r.status_code, r.text[:120])
                continue
            rows += list(csv.DictReader(io.StringIO(r.text)))
            time.sleep(1)
        if rows:
            keep = ["year", "reference_period_desc", "week_ending", "begin_code", "end_code", "freq_desc", "short_desc",
                    "domaincat_desc", "class_desc", "statisticcat_desc", "unit_desc", "Value", "load_time"]
            p = OUT / "nass" / f"{name}.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keep, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            print("NASS", name, len(rows))


def ers():
    for name, url in ERS.items():
        r = get(url)
        if r is None:
            continue
        d = OUT / "ers"
        d.mkdir(parents=True, exist_ok=True)
        if url.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(r.content))
            for n in z.namelist():
                if n.lower().endswith(".csv"):
                    (d / Path(n).name).write_bytes(z.read(n))
                    print("ERS", n)
        else:
            (d / Path(url).name).write_bytes(r.content)
            print("ERS", name, len(r.content))


if __name__ == "__main__":
    import builtins, traceback
    OUT.mkdir(parents=True, exist_ok=True)
    log = open(OUT / "_run.log", "w")
    _print = builtins.print
    def print(*a, **k):  # noqa: A001 - tee to the committed run log
        _print(*a, **k); _print(*a, file=log, flush=True)
    builtins.print = print
    what = sys.argv[1:] or ["datamart", "nass", "ers"]
    for step, fn in (("datamart", datamart), ("nass", nass), ("ers", ers)):
        if step in what:
            try:
                fn()
            except Exception:
                print(step, "FAILED", traceback.format_exc())
