"""Geography & trade for each desk commodity: who produces, who exports, where it goes.

Steps (each can be run alone: python pipelines/geo.py psd comtrade nass usdm):
- psd: USDA FAS PSD bulk file (apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip, free) -> production,
  exports, imports, consumption, ending stocks by country, last 12 market years, for the commodities below.
- comtrade: UN Comtrade public preview API (free, no key, rate-limited) -> bilateral exports of the top
  exporters by HS code (net weight), latest complete year. Used for the trade-flow arrows.
- nass: USDA NASS QuickStats (NASS_API_KEY) -> US production/inventory by state for the US map
  (corn/soybeans/wheat also come from data/grains/raw/annual when present).
- usdm: US Drought Monitor statistics by state (percent area D0-D4 and DSCI) for the producing states.
Writes data/geo/raw/{psd.json, comtrade.json, nass_states.json, usdm.json}; models/geo.py assembles the page data.
"""
import io, json, os, sys, time, zipfile
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo" / "raw"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
NASS_KEY = os.environ.get("NASS_API_KEY", "")

# key: PSD commodity description, HS codes, Comtrade label
COMMS = {
    "corn": ("Corn", "1005"), "soybeans": ("Soybeans", "1201"), "meal": ("Meal, Soybean", "2304"), "oil": ("Oil, Soybean", "1507"),
    "wheat": ("Wheat", "1001"), "cotton": ("Cotton", "5201"), "pork": ("Meat, Swine", "0203"), "beef": ("Meat, Beef and Veal", "0201,0202"),
    "cheese": ("Dairy, Cheese", "0406"), "butter": ("Dairy, Butter", "0405"), "nfdm": ("Dairy, Milk, Nonfat Dry", "040210"),
    "milk": ("Dairy, Milk, Fluid", None), "sorghum": ("Sorghum", "1007"),
}
ATTRS = ["Production", "Exports", "Imports", "Domestic Consumption", "Ending Stocks", "TY Exports", "TY Imports", "Area Harvested", "Yield",
         "Total Supply", "Feed Dom. Consumption", "Crush", "Cow Milk Production", "Fluid Use Dom. Consum."]


def get(url, tries=3, **kw):
    for i in range(tries):
        try:
            r = requests.get(url, headers={**H, **kw.pop("headers", {})}, timeout=180, **kw)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url[:120], r.text[:100].replace("\n", " "))
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:
            print("  err", e, url[:120])
        time.sleep(4 * (i + 1))
    return None


def psd():
    r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip")
    if r is None:
        print("psd: download failed")
        return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    df = pd.read_csv(z.open(z.namelist()[0]), dtype={"Commodity_Code": str}, encoding="latin1")
    want = {v[0]: k for k, v in COMMS.items()}
    df = df[df.Commodity_Description.isin(want) & df.Attribute_Description.isin(ATTRS)]
    y1 = int(df.Market_Year.max())
    df = df[df.Market_Year >= y1 - 12]
    out = {}
    for desc, g in df.groupby("Commodity_Description"):
        k = want[desc]
        unit = g.Unit_Description.mode().iloc[0] if len(g) else ""
        rows = []
        for (cc, cn, my, at), v in g.groupby(["Country_Code", "Country_Name", "Market_Year", "Attribute_Description"]).Value.sum().items():
            rows.append([cc, cn.strip(), int(my), at, round(float(v), 2)])
        units = g.groupby("Attribute_Description").Unit_Description.first().to_dict()
        out[k] = {"psd_name": desc, "unit": unit, "units": units, "rows": rows,
                  "release_month": int(g[g.Market_Year == g.Market_Year.max()].Month.max()) if "Month" in g else None}
        print("psd", k, len(rows), "rows; years", g.Market_Year.min(), "-", g.Market_Year.max(), unit)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "psd.json").write_text(json.dumps({"generated": date.today().isoformat(), "source": "USDA FAS PSD Online (psd_alldata_csv.zip)", "data": out}))


def comtrade():
    """Bilateral exports of each commodity's top exporters (by PSD exports), net weight in tonnes."""
    P = json.loads((OUT / "psd.json").read_text())["data"] if (OUT / "psd.json").exists() else {}
    ref = get("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json")
    names = {x["PartnerCode"]: x["PartnerDesc"] for x in ref.json()["results"]} if ref is not None else {}
    iso3 = {x["PartnerCode"]: x.get("PartnerCodeIsoAlpha3") for x in ref.json()["results"]} if ref is not None else {}
    # PSD country name -> Comtrade reporter code (EU as a bloc = 97, extra-EU trade)
    REP = {"United States": 842, "Brazil": 76, "Argentina": 32, "Ukraine": 804, "Russia": 643, "Canada": 124, "Australia": 36,
           "European Union": 97, "Paraguay": 600, "India": 699, "China": 156, "Kazakhstan": 398, "Uruguay": 858, "Mexico": 484,
           "New Zealand": 554, "Belarus": 112, "Turkey": 792, "Pakistan": 586, "Benin": 204, "Burkina": 854, "Mali": 466,
           "Greece": 300, "Uzbekistan": 860, "Cote d'Ivoire": 384, "Chile": 152, "Malaysia": 458, "Indonesia": 360,
           "United Kingdom": 826, "Vietnam": 704, "Thailand": 764, "Bolivia": 68, "South Africa": 710, "Japan": 392, "Korea, South": 410}
    old = json.loads((OUT / "comtrade.json").read_text()) if (OUT / "comtrade.json").exists() else {"data": {}}
    out = old.get("data", {})
    yr = date.today().year - 1
    for k, (desc, hs) in COMMS.items():
        if not hs or k not in P:
            continue
        rows = P[k]["rows"]
        last = max(r[2] for r in rows if r[3] == "Exports")
        ex = sorted([(r[1], r[4]) for r in rows if r[3] == "Exports" and r[2] == last - 1 and r[1] in REP], key=lambda x: -x[1])[:6]
        res = out.get(k, {"exporters": {}})
        for cname, _ in ex:
            rc = REP[cname]
            got = None
            for y in (yr, yr - 1):
                key = f"{cname}|{y}"
                if key in res.get("done", []):
                    got = True
                    break
                r = get(f"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode={rc}&period={y}&cmdCode={hs}&flowCode=X", tries=4)
                time.sleep(3.2)
                if r is None:
                    continue
                d = [x for x in r.json().get("data", []) if x["partnerCode"] not in (0,) and x.get("partner2Code", 0) == 0
                     and x.get("customsCode") in ("C00", None) and x.get("motCode", 0) == 0]
                if not d:
                    continue
                tot = {}
                for x in d:
                    w = x.get("netWgt") or x.get("qty") or 0
                    p = x["partnerCode"]
                    t = tot.setdefault(p, [0.0, 0.0])
                    t[0] += w / 1000.0
                    t[1] += x.get("primaryValue") or 0
                parts = sorted(([p, names.get(p, str(p)), iso3.get(p), round(v[0]), round(v[1])] for p, v in tot.items()), key=lambda z: -z[3])
                res["exporters"][cname] = {"reporter": rc, "year": y, "total_t": round(sum(z[3] for z in parts)), "partners": parts[:15]}
                res.setdefault("done", []).append(key)
                print("comtrade", k, cname, y, len(parts), "partners, total", round(sum(z[3] for z in parts)), "t")
                got = True
                break
            if not got:
                print("comtrade", k, cname, "no data")
        res["hs"] = hs
        out[k] = res
    (OUT / "comtrade.json").write_text(json.dumps({"generated": date.today().isoformat(), "source": "UN Comtrade (public preview API), annual, net weight", "data": out}))


NASS_Q = {  # key: list of query dicts; first that returns data wins
    "cotton": [dict(commodity_desc="COTTON", statisticcat_desc="PRODUCTION", unit_desc="480 LB BALES", class_desc="ALL CLASSES", agg_level_desc="STATE")],
    "hogs": [dict(commodity_desc="HOGS", statisticcat_desc="INVENTORY", short_desc="HOGS - INVENTORY", reference_period_desc="FIRST OF DEC", agg_level_desc="STATE")],
    "cattle": [dict(commodity_desc="CATTLE", statisticcat_desc="INVENTORY", short_desc="CATTLE, INCL CALVES - INVENTORY", reference_period_desc="FIRST OF JAN", agg_level_desc="STATE")],
    "cattle_on_feed": [dict(commodity_desc="CATTLE", short_desc="CATTLE, ON FEED - INVENTORY", reference_period_desc="FIRST OF JAN", agg_level_desc="STATE")],
    "milk": [dict(commodity_desc="MILK", short_desc="MILK - PRODUCTION, MEASURED IN LB", reference_period_desc="YEAR", agg_level_desc="STATE")],
    "cheese": [dict(commodity_desc="CHEESE", short_desc="CHEESE, TOTAL - PRODUCTION, MEASURED IN LB", reference_period_desc="YEAR", agg_level_desc="STATE")],
    "corn": [dict(commodity_desc="CORN", short_desc="CORN, GRAIN - PRODUCTION, MEASURED IN BU", reference_period_desc="YEAR", agg_level_desc="STATE")],
    "soybeans": [dict(commodity_desc="SOYBEANS", short_desc="SOYBEANS - PRODUCTION, MEASURED IN BU", reference_period_desc="YEAR", agg_level_desc="STATE")],
    "wheat": [dict(commodity_desc="WHEAT", short_desc="WHEAT - PRODUCTION, MEASURED IN BU", reference_period_desc="YEAR", agg_level_desc="STATE")],
    "sorghum": [dict(commodity_desc="SORGHUM", short_desc="SORGHUM, GRAIN - PRODUCTION, MEASURED IN BU", reference_period_desc="YEAR", agg_level_desc="STATE")],
}


def nass():
    if not NASS_KEY:
        print("nass: no NASS_API_KEY")
        return
    p = OUT / "nass_states.json"
    out = json.loads(p.read_text())["data"] if p.exists() else {}
    y = date.today().year
    for k, qs in NASS_Q.items():
        for q in qs:
            got = None
            for yr in (y, y - 1, y - 2):
                r = get("https://quickstats.nass.usda.gov/api/api_GET/", params={"key": NASS_KEY, "format": "JSON", "year__GE": yr - 4, "source_desc": "SURVEY", **q}, tries=2)
                time.sleep(1)
                if r is None:
                    continue
                d = r.json().get("data", [])
                if d:
                    got = d
                    break
            if not got:
                print("nass", k, "no data")
                continue
            rows = []
            for x in got:
                v = str(x.get("Value", "")).replace(",", "").strip()
                if not v.replace(".", "").isdigit():
                    continue
                rows.append([int(x["year"]), x["state_fips_code"], x["state_alpha"], x["state_name"].title(), float(v), x["unit_desc"]])
            out[k] = {"query": q, "rows": rows}
            print("nass", k, len(rows), "rows, years", sorted({r[0] for r in rows})[-3:])
            break
    p.write_text(json.dumps({"generated": date.today().isoformat(), "source": "USDA NASS QuickStats", "data": out}))


USDM_STATES = {"IA": 19, "IL": 17, "NE": 31, "MN": 27, "IN": 18, "OH": 39, "SD": 46, "ND": 38, "KS": 20, "MO": 29, "WI": 55, "MI": 26,
               "TX": 48, "OK": 40, "MT": 30, "WA": 53, "CO": 8, "GA": 13, "MS": 28, "AR": 5, "NC": 37, "CA": 6, "ID": 16, "NY": 36}


def usdm():
    end = date.today()
    start = end - timedelta(days=400)
    fmt = lambda d: f"{d.month}/{d.day}/{d.year}"
    out = {}
    for st, fips in USDM_STATES.items():
        r = get(f"https://usdmdataservices.unl.edu/api/StateStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi={fips:02d}&startdate={fmt(start)}&enddate={fmt(end)}&statisticsType=1",
                headers={"Accept": "application/json"}, tries=2)
        if r is None:
            continue
        rows = r.json()
        out[st] = [[x["mapDate"][:10], x["none"], x["d0"], x["d1"], x["d2"], x["d3"], x["d4"]] for x in rows]
        time.sleep(0.4)
    r = get(f"https://usdmdataservices.unl.edu/api/USStatistics/GetDroughtSeverityStatisticsByAreaPercent?aoi=conus&startdate={fmt(start)}&enddate={fmt(end)}&statisticsType=1",
            headers={"Accept": "application/json"}, tries=2)
    if r is not None:
        out["CONUS"] = [[x["mapDate"][:10], x["none"], x["d0"], x["d1"], x["d2"], x["d3"], x["d4"]] for x in r.json()]
    print("usdm", len(out), "areas")
    (OUT / "usdm.json").write_text(json.dumps({"generated": date.today().isoformat(), "source": "U.S. Drought Monitor (UNL/USDA/NOAA), % of area in each category (cumulative D0+..D4)",
                                               "cols": ["date", "none", "d0", "d1", "d2", "d3", "d4"], "data": out}))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for step in sys.argv[1:] or ["psd", "comtrade", "nass", "usdm"]:
        try:
            globals()[step]()
        except Exception as e:
            import traceback
            print(step, "FAILED", traceback.format_exc())
