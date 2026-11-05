"""EU cereal trade from the European Commission agri-food data portal (DG TAXUD customs surveillance, open API).

https://api.tech.ec.europa.eu/agrifood/api/taxud/weeklyData/{export|import}
For each marketing year (July/June) and calendar month, sums kg by member state and partner for:
  exports: Common wheat, Maize, Barley;  imports: Maize, Common wheat
-> data/europe/taxud_<direction>_<product>.csv.gz (my, month, ms, partner, partner_name, t)
Completed marketing years are fetched once; the current and previous ones are refreshed each run.
The API wants one sector + one product per call and is slow (~5-20 s per call), so calls go month by month.
"""
import gzip, io, sys, time
from datetime import date
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "europe"
API = "https://api.tech.ec.europa.eu/agrifood/api/taxud/weeklyData/"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)", "Accept": "application/json"}
JOBS = [("export", "Common wheat"), ("export", "Maize"), ("export", "Barley"), ("import", "Maize"), ("import", "Common wheat")]
FIRST = int(__import__("os").environ.get("TAXUD_FIRST", "2020"))


def call(direction, product, my, month):
    p = {"sectors": "Cereals", "products": product, "marketingYears": my, "months": month}
    for i in range(4):
        try:
            r = requests.get(API + direction, params=p, headers=H, timeout=180)
            if r.status_code == 200:
                return r.json()
            print("  HTTP", r.status_code, r.text[:160])
        except Exception as e:
            print("  retry", str(e)[:100])
        time.sleep(10 * (i + 1))
    return None


def fetch(direction, product, my):
    rows = []
    for m in (7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6):
        j = call(direction, product, my, m)
        if j is None:
            print(f"  {direction} {product} {my} month {m}: failed")
            return None
        for x in j:
            rows.append((my, m, x.get("memberStateCode"), x.get("partnerCode"), x.get("partner"), (x.get("kgEquivalent") or x.get("kg") or 0) / 1000))
        time.sleep(1)
    d = pd.DataFrame(rows, columns=["my", "month", "ms", "partner", "partner_name", "t"])
    return d.groupby(["my", "month", "ms", "partner", "partner_name"], as_index=False).t.sum()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today()
    cur = today.year if today.month >= 7 else today.year - 1
    mys = [f"{y}/{y + 1}" for y in range(FIRST, cur + 1)]
    only = sys.argv[1:]
    for direction, product in JOBS:
        if only and product.split()[-1].lower() not in [o.lower() for o in only]:
            continue
        p = OUT / f"taxud_{direction}_{product.split()[-1].lower()}.csv.gz"
        old = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["my", "month", "ms", "partner", "partner_name", "t"])
        have = set(old.my.unique())
        parts = [old]
        for my in mys:
            if my in have and my not in mys[-2:]:
                continue
            t0 = time.time()
            d = fetch(direction, product, my)
            if d is None:
                continue
            parts = [x[x.my != my] for x in parts] + [d]
            print(f"{direction} {product} {my}: {d.t.sum() / 1e6:.2f} Mt, {len(d)} rows, {time.time() - t0:.0f}s")
            pd.concat(parts).to_csv(p, index=False, compression="gzip")   # save as we go (long backfill)


if __name__ == "__main__":
    main()
