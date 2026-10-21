#!/usr/bin/env python3
"""Geography and trade for the energy desk: world production, trade flows, US production by state, US exports by
destination, US LNG exports by terminal and US refining capacity. Writes data/energy/geo/raw/*.json; models/energy_geo.py
builds the page files.

Steps (python pipelines/energy_geo.py [eia] [owid] [comtrade]):
- eia (EIA_API_KEY): international crude production by country (annual, kb/d) and refined-product output; US crude
  production by state (monthly, kb/d) and natural gas marketed production by state (monthly, MMcf); US exports of crude,
  distillate, gasoline by destination (annual, kb/d); US LNG exports by destination and by point of exit (monthly MMcf);
  operable atmospheric crude distillation capacity by state (annual, b/cd).
- owid: Our World in Data energy dataset (Energy Institute Statistical Review): oil and gas production by country (TWh).
- comtrade: UN Comtrade public preview, exports of the top exporters by partner: crude 2709, LNG 271111, pipeline gas
  271121, gas oil/diesel 271019, motor gasoline 271012 (net weight, latest complete year).
"""
import io, json, os, re, sys, time
from datetime import date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "energy" / "geo" / "raw"
KEY = os.environ.get("EIA_API_KEY", "")
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}


def get(url, params=None, tries=3, timeout=120):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=H, timeout=timeout)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url[:100], r.text[:150].replace("\n", " "))
            if r.status_code in (400, 401, 403, 404):
                return None
        except Exception as e:
            print("  err", e)
        time.sleep(4 * (i + 1))
    return None


def eia(route, freq, facets, start=None, length=5000):
    """All rows of an EIA v2 route for the given facets (list values), newest first, paged."""
    rows, off = [], 0
    while True:
        p = {"api_key": KEY, "frequency": freq, "data[0]": "value", "sort[0][column]": "period", "sort[0][direction]": "desc",
             "offset": off, "length": length}
        for k, v in facets.items():
            for i, x in enumerate(v if isinstance(v, list) else [v]):
                p[f"facets[{k}][{i}]"] = x
        if start:
            p["start"] = start
        r = get(f"https://api.eia.gov/v2/{route}/data/", p)
        if r is None:
            break
        d = (r.json().get("response") or {})
        got = d.get("data") or []
        rows += got
        tot = int(d.get("total") or 0)
        off += len(got)
        if not got or off >= tot or off >= 60000:
            break
        time.sleep(0.4)
    print(f"  eia {route} {facets} -> {len(rows)} rows")
    return rows


def slim(rows, keys):
    out = []
    for r in rows:
        try:
            v = float(r.get("value"))
        except (TypeError, ValueError):
            continue
        out.append([r.get(k) for k in keys] + [v])
    return out


def step_eia():
    if not KEY:
        print("eia: no EIA_API_KEY")
        return
    y0 = str(date.today().year - 8)
    res = {"generated": date.today().isoformat()}
    # world crude production (kb/d) and refined products output, annual by country
    res["intl_crude"] = slim(eia("international", "annual", {"productId": "57", "activityId": "1", "countryRegionTypeId": "c", "unit": "TBPD"}, start=y0),
                             ["period", "countryRegionId", "countryRegionName"])
    res["intl_products"] = slim(eia("international", "annual", {"productId": "54", "activityId": "1", "countryRegionTypeId": "c", "unit": "TBPD"}, start=y0),
                                ["period", "countryRegionId", "countryRegionName"])
    res["intl_consumption"] = slim(eia("international", "annual", {"productId": "5", "activityId": "2", "countryRegionTypeId": "c", "unit": "TBPD"}, start=y0),
                                   ["period", "countryRegionId", "countryRegionName"])
    res["us_imports_by_source"] = slim(eia("international", "annual", {"productId": "787", "activityId": "3"}, start=y0),
                                       ["period", "countryRegionId", "countryRegionName", "unit"])
    ym = f"{date.today().year - 3}-01"
    # US crude production by state (kb/d), natural gas marketed production by state (MMcf)
    res["us_crude_states"] = slim(eia("petroleum/crd/crpdn", "monthly", {"process": "FPF", "product": "EPC0"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    res["us_gas_states"] = slim(eia("natural-gas/prod/sum", "monthly", {"process": "VGM"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    # US exports by destination (annual), crude / distillate / gasoline
    for k, prod in [("us_exp_crude", "EPC0"), ("us_exp_distillate", "EPD0"), ("us_exp_gasoline", "EPM0F")]:
        res[k] = slim(eia("petroleum/move/expc", "annual", {"product": prod}, start=y0), ["period", "duoarea", "area-name", "series-description", "units"])
    # LNG exports by destination and by terminal (monthly MMcf)
    res["us_lng_dest"] = slim(eia("natural-gas/move/expc", "monthly", {"process": "ENG"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    if not res["us_lng_dest"]:
        res["us_lng_dest"] = slim(eia("natural-gas/move/expc", "monthly", {"process": "EVE"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    res["us_lng_poe"] = slim(eia("natural-gas/move/poe2", "monthly", {"process": "ENG"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    res["us_pipe_poe"] = slim(eia("natural-gas/move/poe2", "monthly", {"process": "ENP"}, start=ym), ["period", "duoarea", "area-name", "series-description", "units"])
    # refining: operable atmospheric crude distillation capacity by state, as of Jan 1 (barrels per calendar day)
    res["us_refining"] = slim(eia("petroleum/pnp/cap1", "annual", {"process": "8D0"}, start=str(date.today().year - 3)),
                              ["period", "duoarea", "area-name", "series-description", "units"])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "eia.json").write_text(json.dumps(res, separators=(",", ":")))
    print("eia:", {k: len(v) for k, v in res.items() if isinstance(v, list)})


def step_owid():
    r = get("https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv", timeout=240)
    if r is None:
        print("owid: download failed")
        return
    import pandas as pd
    df = pd.read_csv(io.StringIO(r.text), usecols=lambda c: c in ("country", "year", "iso_code", "oil_production", "gas_production", "oil_consumption", "gas_consumption"))
    df = df[df.iso_code.notna() & ~df.iso_code.astype(str).str.startswith("OWID") & (df.year >= date.today().year - 12)]
    out = {}
    for col in ("oil_production", "gas_production", "gas_consumption", "oil_consumption"):
        d = df[df[col].notna() & (df[col] > 0)]
        out[col] = [[int(y), iso, c, round(float(v), 2)] for y, iso, c, v in zip(d.year, d.iso_code, d.country, d[col])]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "owid.json").write_text(json.dumps({"generated": date.today().isoformat(), "unit": "TWh",
                                               "source": "Our World in Data energy dataset (Energy Institute Statistical Review of World Energy)", "data": out}, separators=(",", ":")))
    print("owid:", {k: len(v) for k, v in out.items()})


# Comtrade reporter codes of the main exporters
REP = {"Saudi Arabia": 682, "Russia": 643, "Iraq": 368, "United Arab Emirates": 784, "Canada": 124, "United States": 842, "Kuwait": 414,
       "Norway": 579, "Qatar": 634, "Australia": 36, "Nigeria": 566, "Kazakhstan": 398, "Malaysia": 458, "India": 699, "Singapore": 702,
       "Netherlands": 528, "Korea": 410, "Brazil": 76, "Mexico": 484, "Algeria": 12, "Angola": 24, "Oman": 512, "Indonesia": 360}
TRADE = {  # key: (HS code, exporters to query)
    "crude": ("2709", ["Saudi Arabia", "Russia", "United States", "Canada", "United Arab Emirates", "Iraq", "Norway", "Kazakhstan", "Brazil"]),
    "lng": ("271111", ["United States", "Qatar", "Australia", "Russia", "Malaysia", "Nigeria", "Algeria", "Oman"]),
    "pipeline_gas": ("271121", ["Norway", "Russia", "United States", "Canada", "Algeria", "Qatar"]),
    "diesel": ("271019", ["United States", "Russia", "India", "Netherlands", "Korea", "Saudi Arabia", "Singapore"]),
    "gasoline": ("271012", ["United States", "Netherlands", "India", "Korea", "Singapore", "Russia"]),
}


def step_comtrade():
    ref = get("https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json")
    names = {x["PartnerCode"]: x["PartnerDesc"] for x in ref.json()["results"]} if ref is not None else {}
    iso3 = {x["PartnerCode"]: x.get("PartnerCodeIsoAlpha3") for x in ref.json()["results"]} if ref is not None else {}
    p = OUT / "comtrade.json"
    old = json.loads(p.read_text()) if p.exists() else {"data": {}}
    out = old.get("data", {})
    yr = date.today().year - 1
    for k, (hs, exps) in TRADE.items():
        res = out.get(k, {"exporters": {}})
        for cname in exps:
            rc = REP[cname]
            if any(x.startswith(cname + "|") and int(x.split("|")[1]) >= yr - 1 for x in res.get("done", [])):
                continue
            for y in (yr, yr - 1, yr - 2):
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
                    t = tot.setdefault(x["partnerCode"], [0.0, 0.0])
                    t[0] += w / 1000.0
                    t[1] += x.get("primaryValue") or 0
                parts = sorted(([pc, names.get(pc, str(pc)), iso3.get(pc), round(v[0]), round(v[1])] for pc, v in tot.items()), key=lambda z: -z[3])
                res["exporters"][cname] = {"reporter": rc, "year": y, "total_t": round(sum(z[3] for z in parts)), "partners": parts[:15]}
                res.setdefault("done", []).append(f"{cname}|{y}")
                print("comtrade", k, cname, y, len(parts), "partners")
                break
        res["hs"] = hs
        out[k] = res
    OUT.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"generated": date.today().isoformat(), "source": "UN Comtrade (public preview API), annual, net weight", "data": out}))


if __name__ == "__main__":
    steps = sys.argv[1:] or ["eia", "owid", "comtrade"]
    for s in steps:
        print("==", s, flush=True)
        try:
            {"eia": step_eia, "owid": step_owid, "comtrade": step_comtrade}[s]()
        except Exception as e:
            print(s, "failed:", e)
