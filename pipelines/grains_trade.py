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


def inspections():
    """FGIS publishes one CSV per calendar year of inspection certificates."""
    d = OUT / "inspections"
    d.mkdir(parents=True, exist_ok=True)
    cur = time.gmtime().tm_year
    for y in range(cur, 1999, -1):
        p = d / f"CY{y}.csv"
        if p.exists() and y < cur:
            continue
        r = None
        for u in (f"https://fgisonline.ams.usda.gov/ExportGrainReport/CY{y}.csv",
                  f"https://fgisonline.ams.usda.gov/exportgrainreport/CY{y}.csv"):
            r = get(u)
            if r is not None and len(r.content) > 1000:
                break
        if r is None:
            print("inspections", y, "not found")
            continue
        p.write_bytes(r.content)
        print("inspections", y, len(r.content))


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
        for my in range(cur + 1, 2009, -1):  # marketing years
            p = d / name / f"MY{my}.json"
            if p.exists() and my < cur - 1:
                continue
            r = get(f"{ESR}/exports/commodityCode/{code}/allCountries/marketYear/{my}", headers=hdr)
            if r is None:
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
            print("ESR", name, my, len(r.content))
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
