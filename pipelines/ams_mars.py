"""USDA AMS Market News (MARS API, needs AMS_API_KEY): cash grain bids/basis, CME daily spot dairy, ethanol.

History in MARS starts mid-2020. Stored per report and year in data/ams/<slug>/<year>.csv; completed years are
fetched once, the current and previous year are refreshed each run.
"""
import os, sys, time
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ams"
B = "https://marsapi.ams.usda.gov/services/v1.2/reports/"
KEY = (os.getenv("AMS_API_KEY") or "").strip()
REPORTS = {  # slug: name
    1603: "cme_daily_dairy", 2850: "iowa_bids", 3192: "illinois_bids", 3147: "gulf_export_bids",
    3043: "ia_mn_barge_bids", 3223: "kc_wheat_bids", 3046: "minneapolis_bids", 3617: "ethanol_daily", 3148: "portland_bids"}
GRAIN_COLS = ["report_date", "commodity", "class", "grade", "protein", "trade_loc", "delivery_point", "quote_type", "sale Type",
              "basis Min", "basis Max", "basis Min Futures Month", "price Min", "price Max", "avg_price", "current",
              "delivery_start", "delivery Start Half", "trans_mode", "freight"]


def fetch(slug, start, end):
    r = requests.get(f"{B}{slug}", params={"q": f"report_begin_date={start}:{end}", "allSections": "true"}, auth=(KEY, ""), timeout=300)
    r.raise_for_status()
    j = r.json()
    if isinstance(j, list):
        det = [s for s in j if s.get("reportSection") == "Report Detail"]
        rows = det[0]["results"] if det else [x for s in j for x in s.get("results", [])]
    else:
        rows = j.get("results", [])
    return pd.DataFrame(rows)


def main():
    if not KEY:
        print("no AMS_API_KEY")
        return
    now = pd.Timestamp.now()
    for slug, name in REPORTS.items():
        d = OUT / name
        d.mkdir(parents=True, exist_ok=True)
        for y in range(2020, now.year + 1):
            p = d / f"{y}.csv"
            if p.exists() and y < now.year - 1:
                continue
            parts = []
            for q0, q1 in [("01/01", "03/31"), ("04/01", "06/30"), ("07/01", "09/30"), ("10/01", "12/31")]:
                if pd.Timestamp(f"{y}/{q0}") > now:
                    break
                try:
                    x = fetch(slug, f"{q0}/{y}", f"{q1}/{y}")
                except Exception as e:
                    print(name, y, q0, "ERR", str(e)[:120])
                    continue
                if len(x):
                    parts.append(x)
                time.sleep(0.5)
            if not parts:
                continue
            x = pd.concat(parts)
            if slug != 1603 and slug != 3617:
                x = x[[c for c in GRAIN_COLS if c in x.columns]]
            else:
                x = x.drop(columns=[c for c in x.columns if c.startswith(("office", "slug", "report_title", "market_location", "published"))], errors="ignore")
            x.drop_duplicates().to_csv(p, index=False)
            print(name, y, len(x))


if __name__ == "__main__":
    main()
