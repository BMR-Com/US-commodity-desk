"""Grain trade data: FGIS export inspections (open), FAS weekly export sales (FAS_API_KEY), daily flash sales.

Writes data/grains/raw/{inspections,export_sales,flash}/ and a run log data/grains/raw/_trade_run.log.
"""
import builtins, io, json, os, re, sys, time, traceback
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "grains" / "raw"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
FAS_KEY = os.environ.get("FAS_API_KEY", "")
ESR = "https://api.fas.usda.gov/api/esr"
ESR_COMMODITIES = {"corn": 401, "soybeans": 801, "soybean_meal": 901, "soybean_oil": 902, "wheat_all": 107,
                   "wheat_hrw": 101, "wheat_srw": 102, "wheat_hrs": 103, "wheat_white": 104, "wheat_durum": 105, "sorghum": 701}


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers={**H, **kw.pop("headers", {})}, timeout=180, **kw)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url, r.text[:120].replace("\n", " "))
            if r.status_code in (401, 403, 404):
                return None
        except Exception as e:
            print("  err", e, url)
        time.sleep(4 * (i + 1))
    return None


def aggregate_inspections(raw_bytes):
    import pandas as pd
    d = pd.read_csv(io.BytesIO(raw_bytes), low_memory=False, encoding="latin-1", dtype=str)
    d.columns = [c.strip() for c in d.columns]
    d["week"] = pd.to_datetime(d["Thursday"], format="%Y%m%d", errors="coerce")
    for c in ("1000 Bushels", "Metric Ton"):
        d[c] = pd.to_numeric(d[c].str.replace(",", ""), errors="coerce")
    d["Class"] = d["Class"].fillna("").str.strip()
    g = d.groupby(["week", "Grain", "Class", "Destination", "AMS Reg"], dropna=False)[["1000 Bushels", "Metric Ton"]].sum().reset_index()
    return g.rename(columns={"Grain": "grain", "Class": "cls", "Destination": "destination", "AMS Reg": "region",
                             "1000 Bushels": "kbu", "Metric Ton": "mt"})


def inspections():
    """FGIS publishes one CSV per calendar year of inspection certificates; keep weekly aggregates only."""
    import pandas as pd
    d = OUT / "inspections"
    d.mkdir(parents=True, exist_ok=True)
    cur = time.gmtime().tm_year
    for y in range(cur, 1999, -1):
        p = d / f"weekly_CY{y}.csv"
        if p.exists() and y < cur:
            continue
        r = get(f"https://fgisonline.ams.usda.gov/ExportGrainReport/CY{y}.csv")
        if r is None or len(r.content) < 1000:
            print("inspections", y, "not found")
            continue
        g = aggregate_inspections(r.content)
        g.to_csv(p, index=False)
        print("inspections", y, len(g), "weekly rows")
    for old in d.glob("CY*.csv"):
        old.unlink()


def export_sales():
    if not FAS_KEY:
        print("export sales: no FAS_API_KEY secret")
        return
    d = OUT / "export_sales"
    d.mkdir(parents=True, exist_ok=True)
    hdr = {"X-Api-Key": FAS_KEY}
    r = get(f"{ESR}/countries", headers=hdr)
    if r is not None:
        (d / "countries.json").write_bytes(r.content)
    r = get(f"{ESR}/commodities", headers=hdr)
    if r is not None:
        (d / "commodities.json").write_bytes(r.content)
    cur = time.gmtime().tm_year
    for name, code in ESR_COMMODITIES.items():
        for my in range(cur + 1, 2009, -1):  # marketing years; stored as compact CSV (raw JSON is ~0.7 MB/year)
            p = d / name / f"MY{my}.csv"
            if p.exists() and my < cur - 1:
                continue
            r = get(f"{ESR}/exports/commodityCode/{code}/allCountries/marketYear/{my}", headers=hdr)
            if r is None:
                continue
            try:
                rows = r.json()
            except ValueError:
                continue
            if not rows:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).drop(columns=["commodityCode"], errors="ignore").to_csv(p, index=False)
            print("ESR", name, my, len(rows))
            time.sleep(0.5)


def flash():
    """FAS daily export sales announcements (large sales reported the next day)."""
    d = OUT / "flash"
    d.mkdir(parents=True, exist_ok=True)
    for u in ("https://apps.fas.usda.gov/export-sales/dailyrep.htm", "https://www.fas.usda.gov/programs/export-sales-reporting-program/daily-export-sales",
              "https://apps.fas.usda.gov/export-sales/DailyReports.aspx"):
        r = get(u)
        if r is not None:
            name = re.sub(r"[^a-z0-9]+", "_", u.split("//")[1].lower())[:80]
            (d / f"{name}.html").write_bytes(r.content)
            links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
            print("flash page", u, len(r.content), [l for l in links if re.search(r"daily|\\.txt|\\.pdf|\\.htm", l, re.I)][:25])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    log = open(OUT / "_trade_run.log", "w")
    _p = builtins.print
    builtins.print = lambda *a, **k: (_p(*a, **k), _p(*a, file=log, flush=True))
    for step in (sys.argv[1:] or ["inspections", "export_sales", "flash"]):
        try:
            globals()[step]()
        except Exception:
            print(step, "FAILED", traceback.format_exc())
