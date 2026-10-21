#!/usr/bin/env python3
"""Assemble the geography & trade primer for each desk commodity -> data/geo/<key>.json.

- World production map: USDA PSD, latest market year; a country is shaded only if it produces >= 7% of world
  output (shade darker with share); the table lists every country >= 1%.
- Top 5 exporters and importers (PSD), with the previous year and the 5-year average.
- Trade flows: UN Comtrade bilateral exports of the top exporters (latest complete calendar year), for map arrows.
- US export destinations, top 10: FAS weekly export sales (marketing-year exports and current commitments);
  dairy (no weekly export sales) from Comtrade US exports.
- US map: NASS production/inventory by state.
- Weather: Open-Meteo crop-region readings for the countries that matter (>= 7% of production or a top-5 exporter),
  US Drought Monitor for the producing states, and a list of weather and crop-monitoring websites.
"""
import json
from datetime import date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
G = D / "geo"
RAW = G / "raw"
SHARE_MAP = 7.0

# PSD country name -> ISO 3166 numeric (world-atlas ids)
ISO = {"United States": 840, "Brazil": 76, "Argentina": 32, "China": 156, "India": 356, "Russia": 643, "Ukraine": 804, "Canada": 124,
       "Australia": 36, "Mexico": 484, "Indonesia": 360, "Pakistan": 586, "Turkey": 792, "Egypt": 818, "Japan": 392, "Korea, South": 410,
       "Vietnam": 704, "Thailand": 764, "Philippines": 608, "Bangladesh": 50, "Iran": 364, "Kazakhstan": 398, "South Africa": 710,
       "Nigeria": 566, "Ethiopia": 231, "Paraguay": 600, "Uruguay": 858, "Bolivia": 68, "Colombia": 170, "Peru": 604, "Venezuela": 862,
       "Chile": 152, "Malaysia": 458, "Taiwan": 158, "Saudi Arabia": 682, "Algeria": 12, "Morocco": 504, "Tanzania": 834, "Kenya": 404,
       "Uzbekistan": 860, "Turkmenistan": 795, "Belarus": 112, "United Kingdom": 826, "Norway": 578, "Switzerland": 756, "Serbia": 688,
       "New Zealand": 554, "Burma": 104, "Nepal": 524, "Sri Lanka": 144, "Afghanistan": 4, "Iraq": 368, "Syria": 760, "Israel": 376,
       "Jordan": 400, "Yemen": 887, "Sudan": 729, "Burkina Faso": 854, "Mali": 466, "Benin": 204, "Cote d'Ivoire": 384, "Cameroon": 120,
       "Chad": 148, "Zambia": 894, "Zimbabwe": 716, "Malawi": 454, "Mozambique": 508, "Ghana": 288, "Guatemala": 320, "Cuba": 192,
       "Dominican Republic": 214, "Ecuador": 218, "Honduras": 340, "Nicaragua": 558, "El Salvador": 222, "Costa Rica": 188, "Panama": 591,
       "Hong Kong": 344, "Singapore": 702, "United Arab Emirates": 784, "Kuwait": 414, "Oman": 512, "Qatar": 634, "Lebanon": 422, "Libya": 434,
       "Tunisia": 788, "Angola": 24, "Uganda": 800, "Senegal": 686, "Moldova": 498, "Georgia": 268, "Azerbaijan": 31, "Kyrgyzstan": 417,
       "Tajikistan": 762, "Mongolia": 496, "Korea, North": 408, "Cambodia": 116, "Laos": 418, "Burkina": 854, "Bosnia and Herzegovina": 70,
       "North Macedonia": 807, "Albania": 8, "Iceland": 352, "Armenia": 51, "Haiti": 332, "Jamaica": 388, "Madagascar": 450, "Somalia": 706}
EU = [40, 56, 100, 191, 196, 203, 208, 233, 246, 250, 276, 300, 348, 372, 380, 428, 440, 442, 470, 528, 616, 620, 642, 703, 705, 724, 752]
ISO["European Union"] = EU[0]  # handled specially: shaded as all members

# desk key: PSD key, display, unit label, ESR folders (US destinations), NASS state key, weather tags
PAGES = {
    "corn": ("corn", "Corn", ["corn"], "corn", "corn"),
    "soybeans": ("soybeans", "Soybeans", ["soybeans"], "soybeans", "soybeans"),
    "meal": ("meal", "Soybean meal", ["soybean_meal"], "soybeans", "soybeans"),
    "oil": ("oil", "Soybean oil", ["soybean_oil"], "soybeans", "soybeans"),
    "wheat": ("wheat", "Wheat", ["wheat_all"], "wheat", "wheat"),
    "cotton": ("cotton", "Cotton", ["cotton_upland", "cotton_pima"], "cotton", "cotton"),
    "pork": ("pork", "Pork", ["pork"], "hogs", "pork"),
    "beef": ("beef", "Beef", ["beef"], "cattle", "beef"),
    "milk": ("milk", "Milk", [], "milk", "milk"),
    "cheese": ("cheese", "Cheese", [], "cheese", "milk"),
    "butter": ("butter", "Butter", [], "milk", "milk"),
    "nfdm": ("nfdm", "Nonfat dry milk", [], "milk", "milk"),
}

LINKS_COMMON = [
    ("Open-Meteo (data source here)", "https://open-meteo.com/", "free global forecasts and ERA5 history"),
    ("College of DuPage forecast models", "https://weather.cod.edu/forecast/legacy/", "GFS/ECMWF/NAM maps: rain, temperature, anomalies"),
    ("GEOGLAM Crop Monitor", "https://www.cropmonitor.org/", "monthly crop conditions for major producers (AMIS)"),
    ("USDA FAS crop production & GAIN", "https://www.fas.usda.gov/data/world-agricultural-production", "monthly World Agricultural Production with crop maps"),
    ("USDA World Agricultural Weather Highlights / WAOB", "https://www.usda.gov/oce/weather-drought-monitor", "weekly weather and crop bulletin (global)"),
    ("NOAA CPC global precipitation & outlooks", "https://www.cpc.ncep.noaa.gov/products/Global_Monsoons/Global-Monsoon.shtml", "monsoon and global rainfall monitoring"),
    ("NASA Worldview (NDVI, soil moisture SMAP)", "https://worldview.earthdata.nasa.gov/", "satellite vegetation and soil moisture layers"),
    ("Copernicus / ECMWF charts", "https://charts.ecmwf.int/", "ECMWF forecasts and seasonal outlooks"),
    ("IRI ENSO forecast", "https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/", "El Niño / La Niña probabilities"),
]
LINKS = {
    "United States": [
        ("US Drought Monitor", "https://droughtmonitor.unl.edu/", "weekly drought map; ag in drought by crop"),
        ("USDA Agriculture in Drought", "https://www.usda.gov/sites/default/files/documents/agriculture-in-drought.pdf", "% of corn/soy/wheat/cattle area in drought"),
        ("NOAA CPC 6-10 / 8-14 day outlooks", "https://www.cpc.ncep.noaa.gov/products/predictions/814day/", "temperature and precipitation probabilities"),
        ("CPC soil moisture", "https://www.cpc.ncep.noaa.gov/products/Soilmst_Monitoring/US/Soilmst/Soilmst.shtml", "modelled soil moisture and anomaly"),
        ("NASA SPoRT soil moisture", "https://weather.msfc.nasa.gov/sport/case_studies/lis_CONUS.html", "daily LIS soil moisture percentiles"),
        ("USDA NASS VegScape / Crop-CASMA", "https://nassgeo.csiss.gmu.edu/CropCASMA/", "NDVI and SMAP soil moisture for cropland"),
        ("NASS Crop Progress", "https://www.nass.usda.gov/Publications/National_Crop_Progress/", "weekly condition and progress"),
        ("NOAA WPC QPF", "https://www.wpc.ncep.noaa.gov/qpf/qpf2.shtml", "7-day rainfall forecast"),
        ("Iowa Environmental Mesonet", "https://mesonet.agron.iastate.edu/", "station rain, GDD, soil temperature"),
    ],
    "Brazil": [("INMET", "https://portal.inmet.gov.br/", "national met service: maps and stations"), ("CONAB crop monitoring", "https://www.conab.gov.br/info-agro/safras", "crop surveys and agro-climate bulletins"),
               ("CPTEC/INPE", "https://www.cptec.inpe.br/", "forecasts and climate monitoring"), ("Rural Clima / Climatempo agro", "https://www.climatempo.com.br/", "commercial forecasts")],
    "Argentina": [("Buenos Aires Grain Exchange (BCBA) weekly", "https://www.bolsadecereales.com/estimaciones-informes", "crop progress and condition"),
                  ("Rosario Grain Exchange (BCR) GEA", "https://www.bcr.com.ar/es/mercados/gea", "crop estimates, soil moisture maps"), ("SMN Argentina", "https://www.smn.gob.ar/", "national met service")],
    "China": [("China Meteorological Administration", "https://www.cma.gov.cn/en/", "national met service"), ("CMA agrometeorology (Chinese)", "http://www.cma.gov.cn/2011xzt/2012zhuant/20120928_1_1_1_1/", "crop weather bulletins")],
    "India": [("India Meteorological Department", "https://mausam.imd.gov.in/", "monsoon progress and district rainfall"),
              ("IMD district-wise rainfall", "https://mausam.imd.gov.in/responsive/districtWiseRainfallInformation.php", "rain vs normal by district"),
              ("Ministry of Agriculture sowing data", "https://agriwelfare.gov.in/", "kharif/rabi sowing progress")],
    "Russia": [("SovEcon", "https://sovecon.com/", "Black Sea crop estimates and weather"), ("Hydrometcenter of Russia", "https://meteoinfo.ru/", "national forecasts")],
    "Ukraine": [("Ukrainian Hydrometeorological Center", "https://meteo.gov.ua/", "national forecasts"), ("APK-Inform", "https://www.apk-inform.com/en", "crop progress, Black Sea markets")],
    "European Union": [("JRC MARS Bulletin", "https://joint-research-centre.ec.europa.eu/monitoring-agricultural-resources-mars_en", "monthly EU crop yield forecasts and weather"),
                       ("European Drought Observatory", "https://edo.jrc.ec.europa.eu/", "soil moisture and drought indicators"), ("Météo-France", "https://meteofrance.com/", "France forecasts")],
    "Canada": [("AAFC Canadian Drought Monitor", "https://agriculture.canada.ca/en/agricultural-production/weather/canadian-drought-monitor", "drought map"),
               ("Saskatchewan crop report", "https://www.saskatchewan.ca/business/agriculture-natural-resources-and-industry/agribusiness-farmers-and-ranchers/market-and-trade-statistics/crops-statistics/crop-report", "weekly")],
    "Australia": [("Bureau of Meteorology", "http://www.bom.gov.au/climate/maps/", "rain deciles, soil moisture"), ("ABARES crop report", "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/australian-crop-report", "quarterly crop estimates")],
    "New Zealand": [("NIWA", "https://niwa.co.nz/climate-and-weather", "soil moisture and drought index"), ("DCANZ / Fonterra updates", "https://www.fonterra.com/", "milk collection forecasts")],
    "Pakistan": [("Pakistan Meteorological Department", "https://www.pmd.gov.pk/", "forecasts and agromet bulletins")],
}


def J(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def esr_destinations(folders):
    """Top-10 US destinations: last complete marketing year exports and the current MY commitments to date."""
    cmap = {}
    try:
        for x in json.load(open(D / "grains/raw/export_sales/countries.json")):
            cmap[x["countryCode"]] = (x["countryDescription"].strip().title(), x.get("gencCode"))
    except Exception:
        pass
    frames = []
    for f in folders:
        for p in sorted((D / "grains/raw/export_sales" / f).glob("MY*.csv")):
            d = pd.read_csv(p)
            d["my"] = int(p.stem[2:])
            frames.append(d)
    if not frames:
        return None
    d = pd.concat(frames)
    d["weekEndingDate"] = pd.to_datetime(d.weekEndingDate)
    out = {}
    mys = sorted(d.my.unique())
    for label, my in (("last_my", mys[-2] if len(mys) > 1 else None), ("current_my", mys[-1])):
        if my is None:
            continue
        x = d[d.my == my]
        wk = x.weekEndingDate.max()
        x = x[x.weekEndingDate == wk].groupby("countryCode")[["accumulatedExports", "currentMYTotalCommitment"]].sum()
        col = "accumulatedExports" if label == "last_my" else "currentMYTotalCommitment"
        tot = float(x[col].sum())
        top = x[col].sort_values(ascending=False)
        rows = []
        for cc, v in top.items():
            nm, g3 = cmap.get(cc, (str(cc), None))
            if v <= 0 or "Unknown" in nm or nm.upper().startswith("UNKNOWN"):
                continue
            rows.append({"country": nm, "iso3": g3, "value": float(v), "share": round(100 * v / tot, 1) if tot else None})
        unk = float(x[col][[c for c in x.index if "UNKNOWN" in cmap.get(c, ("",))[0].upper()]].sum()) if len(x) else 0
        out[label] = {"my": int(my), "week": wk.date().isoformat(), "measure": "exports in the marketing year" if label == "last_my" else "commitments (exports + outstanding sales) to date",
                      "total": tot, "unknown": unk, "top": rows[:10]}
    return out


def iso3_to_num(a3):
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=a3)
        return int(c.numeric) if c else None
    except Exception:
        return None


def main():
    P = (J(RAW / "psd.json") or {}).get("data", {})
    C = (J(RAW / "comtrade.json") or {}).get("data", {})
    N = (J(RAW / "nass_states.json") or {}).get("data", {})
    U = J(RAW / "usdm.json") or {}
    W = J(G / "weather.json") or {"regions": []}
    idx = {}
    for key, (pk, name, esr, nk, wtag) in PAGES.items():
        if pk not in P:
            print("geo", key, "no PSD")
            continue
        df = pd.DataFrame(P[pk]["rows"], columns=["code", "country", "my", "attr", "value"])
        unit = (P[pk].get("units") or {}).get("Production") or P[pk]["unit"]
        prod = df[df.attr.isin(["Production"])]
        if prod.empty and pk == "milk":
            prod = df[df.attr == "Cow Milk Production"]
        yrs = sorted(prod.my.unique())
        latest = max(y for y in yrs if prod[prod.my == y].value.sum() > 0)
        def table(attr, y):
            t = df[(df.attr == attr) & (df.my == y)].groupby("country").value.sum()
            return t[t > 0].sort_values(ascending=False)
        pt = prod[prod.my == latest].groupby("country").value.sum().sort_values(ascending=False)
        pt = pt[pt > 0]
        world = float(pt.sum())
        hist = prod.pivot_table(index="country", columns="my", values="value", aggfunc="sum").fillna(0)
        production = []
        for c, v in pt.items():
            sh = 100 * v / world
            if sh < 1:
                continue
            prev = float(hist.loc[c, latest - 1]) if latest - 1 in hist.columns else None
            avg5 = float(hist.loc[c, [y for y in range(latest - 5, latest) if y in hist.columns]].mean()) if c in hist.index else None
            production.append({"country": c, "iso": EU if c == "European Union" else ISO.get(c), "value": round(float(v), 1), "share": round(sh, 1),
                               "prev": prev, "avg5": None if avg5 is None else round(avg5, 1), "mapped": sh >= SHARE_MAP,
                               "hist": [round(float(hist.loc[c, y]), 1) if y in hist.columns else None for y in yrs[-10:]]})
        def topn(attr, n=5):
            t = table(attr, latest)
            tp = table(attr, latest - 1)
            tw = float(t.sum())
            return [{"country": c, "iso": EU if c == "European Union" else ISO.get(c), "value": round(float(v), 1), "share": round(100 * v / tw, 1) if tw else None,
                     "prev": round(float(tp.get(c, 0)), 1)} for c, v in t.head(n).items()], tw
        ex, ex_tot = topn("Exports")
        im, im_tot = topn("Imports", 8)
        # flows from Comtrade
        flows = []
        for exp, e in (C.get(pk, {}).get("exporters") or {}).items():
            for p in e["partners"][:8]:
                code, pname, a3, t, usd = p
                if code in (0, 97) or t <= 0:
                    continue
                flows.append({"from": exp, "from_iso": EU if exp == "European Union" else ISO.get(exp), "to": pname, "to_iso": iso3_to_num(a3) if a3 else None,
                              "t": t, "usd": usd, "year": e["year"]})
        # US destinations
        us = esr_destinations(esr) if esr else None
        if not us and C.get(pk, {}).get("exporters", {}).get("United States"):
            e = C[pk]["exporters"]["United States"]
            tot = e["total_t"]
            us = {"comtrade": {"year": e["year"], "measure": "exports (UN Comtrade, tonnes)", "total": tot,
                               "top": [{"country": p[1], "iso3": p[2], "value": p[3], "share": round(100 * p[3] / tot, 1) if tot else None} for p in e["partners"][:10]]}}
        # US states
        st = None
        if nk not in N and "milk" in N and pk in ("cheese", "butter", "nfdm"):
            nk = "milk"
        if nk in N and N[nk]["rows"]:
            sd = pd.DataFrame(N[nk]["rows"], columns=["year", "fips", "abbr", "state", "value", "unit"])
            sd = sd[~sd.fips.isin(["98", "99", "00"])]
            if len(sd):
                y = int(sd.year.max())
                s = sd[sd.year == y].groupby(["fips", "abbr", "state"]).value.sum().sort_values(ascending=False)
                tot = float(s.sum())
                st = {"year": y, "unit": sd.unit.iloc[0], "what": N[nk]["query"].get("short_desc") or nk, "total": tot,
                      "states": [{"fips": f, "abbr": a, "state": n, "value": float(v), "share": round(100 * v / tot, 1)} for (f, a, n), v in s.items()]}
        # weather regions that matter: country >= 7% of production or top-5 exporter
        keyc = {p["country"] for p in production if p["share"] >= SHARE_MAP} | {e["country"] for e in ex}
        regs = [r["id"] for r in W["regions"] if wtag in r["commodities"] and r["country"] in keyc]
        usdm = None
        if st and U.get("data"):
            top_states = [s["abbr"] for s in st["states"][:8] if s["abbr"] in U["data"]]
            usdm = {"cols": U.get("cols"), "latest": {s: U["data"][s][0] for s in top_states}, "month_ago": {s: U["data"][s][min(4, len(U["data"][s]) - 1)] for s in top_states},
                    "conus": (U["data"].get("CONUS") or [None])[0]}
        links = [{"country": c, "links": [{"name": a, "url": b, "what": w} for a, b, w in LINKS[c]]} for c in
                 ["United States"] + sorted(keyc - {"United States"}) if c in LINKS]
        out = {"key": key, "name": name, "unit": unit, "units": P[pk].get("units"), "my": int(latest), "years": [int(y) for y in yrs[-10:]],
               "world": round(world, 1), "threshold": SHARE_MAP, "production": production, "exporters": ex, "exports_world": round(ex_tot, 1),
               "importers": im, "imports_world": round(im_tot, 1), "flows": flows, "flows_year": max([f["year"] for f in flows], default=None),
               "us_dest": us, "us_states": st, "weather_regions": regs, "usdm": usdm, "links": links, "links_common": [{"name": a, "url": b, "what": w} for a, b, w in LINKS_COMMON],
               "sources": "USDA FAS PSD (production/trade by country, marketing years), UN Comtrade (bilateral flows, calendar year), USDA FAS Export Sales (US destinations), "
                          "USDA NASS (US states), U.S. Drought Monitor, Open-Meteo (weather)", "generated": date.today().isoformat()}
        (G / f"{key}.json").write_text(json.dumps(out, default=lambda o: None))
        idx[key] = {"name": name, "my": int(latest), "mapped": [p["country"] for p in production if p["mapped"]]}
        print("geo", key, latest, "world", round(world), unit, "| >=7%:", idx[key]["mapped"], "| flows", len(flows), "| us_dest", bool(us), "| states", bool(st), "| wx", len(regs))
    (G / "index.json").write_text(json.dumps({"generated": date.today().isoformat(), "pages": idx}))


if __name__ == "__main__":
    main()
