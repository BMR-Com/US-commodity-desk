"""EU grain, oilseed/vegetable-oil and sugar trade from the European Commission agri-food data portal (DG TAXUD customs surveillance, open API).

https://api.tech.ec.europa.eu/agrifood/api/taxud/weeklyData/{export|import}
For each marketing year (July/June) and week (grouped into calendar months by the week's Thursday), sums kg by member state and partner for:
  see JOBS: wheat and maize (Cereals), soybeans/soymeal/rapeseed and palm/soy/rapeseed/sunflower oil (Oilseeds),
  raw cane and white sugar (Sugar, Oct/Sep year)
-> data/europe/taxud_<direction>_<slug>.csv.gz (my, month, ms, partner, partner_name, t)
Completed marketing years are fetched once; the current and previous ones are refreshed each run.
The API wants one sector + one product per call and is slow (~5-20 s per call), so calls go nine weeks at a time.
"""
import gzip, io, sys, time
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "europe"
API = "https://api.tech.ec.europa.eu/agrifood/api/taxud/weeklyData/"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)", "Accept": "application/json"}
# (direction, sector, product, file slug, group, first month of the marketing year)
# exchange-traded grains, oilseeds/vegetable oils and sugar only (Ma, 2026-11-05)
JOBS = [("export", "Cereals", "Common wheat", "wheat", "wheat", 7), ("export", "Cereals", "Maize", "maize", "maize", 7),
        ("import", "Cereals", "Maize", "maize", "maize", 7),
        ("import", "Oilseeds", "Soya beans", "soybeans", "oilseeds", 7), ("import", "Oilseeds", "Soya meal", "soymeal", "oilseeds", 7),
        ("import", "Oilseeds", "Palm oil", "palmoil", "oils", 7), ("import", "Oilseeds", "Rapeseed", "rapeseed", "oilseeds", 7),
        ("import", "Oilseeds", "Sunflowerseed oil", "sunoil", "oils", 7), ("import", "Oilseeds", "Soya oil", "soyoil", "oils", 7),
        ("import", "Oilseeds", "Rapeseed oil", "rapeoil", "oils", 7), ("export", "Oilseeds", "Rapeseed oil", "rapeoil", "oils", 7),
        ("export", "Oilseeds", "Soya oil", "soyoil", "oils", 7),
        ("import", "Sugar", "Raw cane sugar", "rawcane", "sugar", 10), ("import", "Sugar", "White sugar", "whitesugar", "sugar", 10),
        ("export", "Sugar", "White sugar", "whitesugar", "sugar", 10)]
FIRST = int(__import__("os").environ.get("TAXUD_FIRST", "2016"))


def call(direction, sector, product, my, weeks):
    # one sector + one product per call; the API rejects month filters combined with marketing years
    p = {"sectors": sector, "products": product, "marketingYears": my, "weeks": ",".join(map(str, weeks))}
    for i in range(4):
        try:
            r = requests.get(API + direction, params=p, headers=H, timeout=240)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:        # "No results found" (weeks not reached yet)
                return []
            print("  HTTP", r.status_code, r.text[:160], flush=True)
        except Exception as e:
            print("  retry", str(e)[:100], flush=True)
        time.sleep(10 * (i + 1))
    return None


def week_month(my, w, m0=7):
    """Marketing-year week w (week 1 = the Monday-to-Sunday week containing the 1st of the first month) -> month of its Thursday."""
    y = int(my[:4])
    jul1 = date(y, m0, 1)
    start = jul1 - timedelta(days=jul1.weekday()) + timedelta(weeks=w - 1)
    return (start + timedelta(days=3)).month


def fetch(direction, sector, product, my, m0=7):
    from concurrent.futures import ThreadPoolExecutor
    chunks = [list(range(k + 1, min(k + 10, 54))) for k in range(0, 54, 9)]
    with ThreadPoolExecutor(3) as ex:     # the API takes 20-60 s per call; three at a time keeps it polite but quicker
        res = list(ex.map(lambda wk: call(direction, sector, product, my, wk), chunks))
    if any(r is None for r in res):
        print(f"  {direction} {product} {my}: a chunk failed", flush=True)
        return None
    rows = [(my, int(x["week"]), x.get("memberStateCode"), x.get("partnerCode"), x.get("partner"),
             (x.get("kgEquivalent") or x.get("kg") or 0) / 1000) for j in res for x in j]
    d = pd.DataFrame(rows, columns=["my", "week", "ms", "partner", "partner_name", "t"])
    d = d.groupby(["my", "week", "ms", "partner", "partner_name"], as_index=False).t.sum()
    d["month"] = [week_month(m, w, m0) for m, w in zip(d.my, d.week)]
    return d


def discover():
    """List what the TAXUD API knows: OpenAPI parameter docs and, per sector name, products with volumes in one week."""
    import json
    out = {}
    try:
        doc = requests.get("https://api.tech.ec.europa.eu/agrifood/v3/api-docs/taxud_weekly", headers=H, timeout=60).json()
        for path, v in doc.get("paths", {}).items():
            out[path] = [{k: prm.get(k) for k in ("name", "description", "schema")} for prm in list(v.values())[0].get("parameters", [])]
    except Exception as e:
        out["doc_error"] = str(e)
    for sec in ["Oilseeds", "Oilseeds and protein crops", "Oils and fats", "Vegetable oils", "Olive oil", "Sugar", "Cereals"]:
        for direction in ("import", "export"):
            r = requests.get(API + direction, params={"sectors": sec, "marketingYears": "2025/2026", "weeks": "10"}, headers=H, timeout=240)
            key = f"{direction}|{sec}"
            if r.status_code != 200:
                out[key] = f"HTTP {r.status_code} {r.text[:200]}"
                continue
            agg = {}
            for x in r.json():
                k = f"{x.get('sector')}|{x.get('product')}|{x.get('marketingYear')}"
                agg[k] = round(agg.get(k, 0) + (x.get("kgEquivalent") or x.get("kg") or 0) / 1e6, 2)
            out[key] = agg
            print(key, agg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "taxud_discover.json").write_text(json.dumps(out, indent=1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = date.today()
    only = [o.lower() for o in sys.argv[1:]]
    for direction, sector, product, slug, group, m0 in JOBS:
        if only and slug not in only and group not in only:
            continue
        cur = today.year if today.month >= m0 else today.year - 1
        mys = [f"{y}/{y + 1}" for y in range(FIRST, cur + 1)]
        p = OUT / f"taxud_{direction}_{slug}.csv.gz"
        old = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["my", "week", "ms", "partner", "partner_name", "t", "month"])
        have = set(old.my.unique())
        parts = [old]
        for my in mys:
            if my in have and my not in mys[-2:]:
                continue
            t0 = time.time()
            d = fetch(direction, sector, product, my, m0)
            if d is None:
                continue
            parts = [x[x.my != my] for x in parts] + [d]
            print(f"{direction} {product} {my}: {d.t.sum() / 1e6:.2f} Mt, {len(d)} rows, weeks to {d.week.max() if len(d) else 0}, {time.time() - t0:.0f}s", flush=True)
            pd.concat(parts).to_csv(p, index=False, compression="gzip")   # save as we go (long backfill)


if __name__ == "__main__":
    discover() if sys.argv[1:2] == ["discover"] else main()
