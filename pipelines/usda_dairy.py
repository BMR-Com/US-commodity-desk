"""Fetch USDA dairy data (no API keys) into data/dairy/raw/.

Sources
- AMS mandatory price reporting datamart (mpr.datamart.ams.usda.gov): every section of each
  configured report, full history, one CSV per section.
- ERS Dairy Data: monthly/annual supply and utilization files (CSV).
Runs on GitHub Actions (USDA hosts are reachable there).
"""
import csv, io, json, re, sys, time, urllib.parse
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "dairy" / "raw"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
DM = "https://mpr.datamart.ams.usda.gov/services/v1.1/reports"

REPORTS = {
    2993: "ndpsr",            # National Dairy Products Sales Report (weekly)
    2991: "class_prices",     # Announcement of Class and Component Prices (monthly)
    2989: "advanced_prices",  # Announcement of Advanced Prices and Pricing Factors (monthly)
    3345: "fmmo_class1_prices",
    3346: "fmmo_class1_util", 3347: "fmmo_class2_util", 3348: "fmmo_class3_util", 3349: "fmmo_class4_util",
    3351: "fmmo_uniform", 3352: "fmmo_price_pool", 3357: "fmmo_mailbox", 3358: "fluid_sales",
    3461: "fmmo_producer_receipts", 3462: "fmmo_components",
}
ERS = {
    "ers_milk_supply_use": "https://www.ers.usda.gov/media/5507/supply-and-utilization-of-milk-in-all-products-monthly-and-annual.csv",
    "ers_product_supply_use": "https://www.ers.usda.gov/media/5505/supply-and-utilization-of-dairy-product-categories-monthly-and-annual.csv",
    "ers_dairy_at_a_glance": "https://www.ers.usda.gov/media/5501/us-dairy-situation-at-a-glance-monthly-and-annual.csv",
    "ers_milk_production": "https://www.ers.usda.gov/media/5503/us-milk-production-and-related-data-quarterly-and-annual.csv",
}


def get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=180)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url)
        except Exception as e:
            print("  err", e, url)
        time.sleep(5 * (i + 1))
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def write_rows(path, rows):
    if not rows:
        return 0
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    drop = {"office_name", "office_code", "office_city", "office_state", "market_location_name",
            "market_location_city", "market_location_state", "market_type", "market_type_category",
            "report_title", "slug_name", "slug_id", "narrative"}
    cols = [c for c in cols if c not in drop]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def datamart():
    for rid, name in REPORTS.items():
        r = get(f"{DM}/{rid}")
        if r is None:
            continue
        root = r.json()
        sections = root.get("reportSections") or ["Summary"]
        for sec in sections:
            if sec == "Summary":
                rows = root.get("results", [])
            else:
                rr = get(f"{DM}/{rid}/{urllib.parse.quote(sec, safe='')}")
                if rr is None:
                    continue
                j = rr.json()
                rows = j.get("results", []) if isinstance(j, dict) else []
            n = write_rows(OUT / name / f"{slug(sec)}.csv", rows)
            print(f"{rid} {name} / {sec}: {n} rows")


def ers():
    for name, url in ERS.items():
        r = get(url)
        if r is None:
            continue
        p = OUT / "ers" / f"{name}.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        print(f"ERS {name}: {len(r.content)} bytes")


if __name__ == "__main__":
    what = sys.argv[1:] or ["datamart", "ers"]
    if "datamart" in what:
        datamart()
    if "ers" in what:
        ers()
