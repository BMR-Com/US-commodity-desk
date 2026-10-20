"""NASS weekly crop progress and condition + annual acreage/yield/production for grains and oilseeds.

Batched to stay under QuickStats' 50,000-row cap: one request per (commodity, year, level);
a batch that is too large is split by state. Completed years are stored once
(data/grains/raw/crop_progress/<commodity>/<year>.csv); the current year is refreshed each run.
Needs NASS_API_KEY.
"""
import csv, os, sys, time
from pathlib import Path
import requests

KEY = os.environ.get("NASS_API_KEY", "")
B = "https://quickstats.nass.usda.gov/api/"
OUT = Path(__file__).resolve().parent.parent / "data" / "grains" / "raw"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
COMMODITIES = ["CORN", "SOYBEANS", "WHEAT", "SORGHUM", "OATS", "BARLEY", "RICE", "SUNFLOWER", "CANOLA", "PEANUTS"]
FIRST_YEAR = int(os.environ.get("CP_FIRST_YEAR", "1986"))
KEEP = ["year", "week_ending", "reference_period_desc", "state_alpha", "agg_level_desc", "commodity_desc", "class_desc",
        "util_practice_desc", "short_desc", "statisticcat_desc", "unit_desc", "Value"]
ANNUAL_STATS = ["AREA PLANTED", "AREA HARVESTED", "YIELD", "PRODUCTION"]


def get(path, **params):
    for attempt in range(4):
        try:
            r = requests.get(B + path, params={"key": KEY, **params}, headers=H, timeout=180)
            if r.status_code == 200:
                return r.json()
            t = r.text.lower()
            if r.status_code == 413 or "exceeds" in t or "50,000" in t:
                return {"too_big": True}
            if r.status_code == 400 and ("no data" in t or "bad request" in t):
                return {"data": []}
            print("  HTTP", r.status_code, r.text[:120])
        except Exception as e:
            print("  retry:", e)
        time.sleep(4 * (attempt + 1))
    return {"data": []}


def batch(q):
    d = get("api_GET/", format="JSON", **q)
    if d.get("too_big"):
        states = get("get_param_values/", param="state_alpha", **q).get("state_alpha", [])
        rows = []
        for s in states:
            rows += batch({**q, "state_alpha": s})
        return rows
    time.sleep(0.4)
    return d.get("data", [])


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KEEP, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def weekly(commodity, year, cur_year):
    p = OUT / "crop_progress" / commodity.lower() / f"{year}.csv"
    if p.exists() and year < cur_year:
        return None
    rows = []
    for level in ("NATIONAL", "STATE"):
        for stat in ("PROGRESS", "CONDITION"):
            rows += batch(dict(commodity_desc=commodity, year=year, agg_level_desc=level, statisticcat_desc=stat,
                               source_desc="SURVEY", freq_desc="WEEKLY"))
    if rows:
        write(p, rows)
    return len(rows)


def annual(commodity, year, cur_year):
    p = OUT / "annual" / commodity.lower() / f"{year}.csv"
    if p.exists() and year < cur_year - 1:  # final estimates arrive the following January
        return None
    rows = []
    for level in ("NATIONAL", "STATE"):
        for stat in ANNUAL_STATS:
            rows += batch(dict(commodity_desc=commodity, year=year, agg_level_desc=level, statisticcat_desc=stat,
                               source_desc="SURVEY", freq_desc="ANNUAL", reference_period_desc="YEAR"))
    if rows:
        write(p, rows)
    return len(rows)


if __name__ == "__main__":
    if not KEY:
        sys.exit("NASS_API_KEY missing")
    cur = time.gmtime().tm_year
    comms = [a.upper() for a in sys.argv[1:]] or COMMODITIES
    budget = int(os.environ.get("CP_MAX_BATCHES", "400"))  # cap per run; later runs continue where this stopped
    done = 0
    for c in comms:
        for y in range(cur, FIRST_YEAR - 1, -1):  # newest first so the current season is always fresh
            if done >= budget:
                print("batch budget reached; next run continues")
                sys.exit(0)
            n = weekly(c, y, cur)
            m = annual(c, y, cur)
            if n is not None or m is not None:
                done += 1
                print(c, y, "weekly", n, "annual", m)
