#!/usr/bin/env python3
"""Page data for Energy > Production, trade & LNG: data/energy/geo/{crude,natgas,products}.json from the raw files of
pipelines/energy_geo.py (EIA, OWID / Energy Institute, UN Comtrade)."""
import json, re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "energy" / "geo" / "raw"
OUT = ROOT / "data" / "energy" / "geo"
THRESH = 7
FIPS = {"AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17",
        "IN": "18", "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28", "MO": "29", "MT": "30",
        "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
        "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55", "WY": "56"}
NAMES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida",
         "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
         "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
         "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
         "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
         "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming"}
TERMINALS = {  # EIA point-of-exit code: (name, lat, lon)
    "YSPL": ("Sabine Pass, LA", 29.746, -93.873), "YPLAQ": ("Plaquemines, LA", 29.50, -89.70), "YCRP": ("Corpus Christi, TX", 27.89, -97.26),
    "YFPT": ("Freeport, TX", 28.94, -95.31), "YCAM": ("Cameron, LA", 30.05, -93.33), "YCCPL": ("Calcasieu Pass, LA", 29.77, -93.34),
    "YCPT": ("Cove Point, MD", 38.39, -76.41), "YELBA": ("Elba Island, GA", 32.08, -81.00), "YGPT": ("Golden Pass, TX", 29.76, -93.93),
}
SHORT = {"United States": "US", "Saudi Arabia": "Saudi", "United Arab Emirates": "UAE", "Russian Federation": "Russia"}
LINKS = {
    "crude": [("EIA Weekly Petroleum Status Report", "https://www.eia.gov/petroleum/supply/weekly/", "US stocks, runs, production, exports (Wed)"),
              ("EIA Short-Term Energy Outlook", "https://www.eia.gov/outlooks/steo/", "monthly supply-demand forecasts"),
              ("OPEC Monthly Oil Market Report", "https://www.opec.org/opec_web/en/publications/338.htm", "OPEC production and demand view"),
              ("IEA Oil Market Report", "https://www.iea.org/topics/oil-market-report", "global balances (summary free)"),
              ("Baker Hughes rig count", "https://rigcount.bakerhughes.com/", "weekly drilling activity"),
              ("NOAA National Hurricane Center", "https://www.nhc.noaa.gov/", "Gulf of Mexico storms (Jun–Nov)")],
    "natgas": [("EIA Weekly Natural Gas Storage Report", "https://ir.eia.gov/ngs/ngs.html", "working gas vs 5-year (Thu)"),
               ("EIA Natural Gas Weekly Update", "https://www.eia.gov/naturalgas/weekly/", "prices, flows, LNG, rigs"),
               ("EIA LNG exports", "https://www.eia.gov/naturalgas/data.php#imports", "monthly by terminal and destination"),
               ("NOAA CPC 6–10 / 8–14 day outlooks", "https://www.cpc.ncep.noaa.gov/products/predictions/610day/", "heating and cooling demand"),
               ("NOAA National Hurricane Center", "https://www.nhc.noaa.gov/", "Gulf production and LNG terminals"),
               ("GIE AGSI (EU gas storage)", "https://agsi.gie.eu/", "European storage, which pulls US LNG")],
    "products": [("EIA Weekly Petroleum Status Report", "https://www.eia.gov/petroleum/supply/weekly/", "gasoline and distillate stocks (Wed)"),
                 ("EIA Gasoline and Diesel Fuel Update", "https://www.eia.gov/petroleum/gasdiesel/", "retail pump prices (Mon)"),
                 ("EIA Refinery capacity", "https://www.eia.gov/petroleum/refinerycapacity/", "capacity by refinery"),
                 ("EPA RIN data (EMTS)", "https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information", "renewable fuel credits"),
                 ("NOAA National Hurricane Center", "https://www.nhc.noaa.gov/", "Gulf Coast refineries")],
}


def J(name):
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def numeric(a3):
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=a3)
        return c.numeric if c else None
    except Exception:
        return None


def world(rows, unit, source):
    """rows: [year, iso3, name, value] -> production table (latest year with broad coverage)."""
    by = defaultdict(dict)
    for y, a3, nm, v in rows:
        by[int(y)][a3] = (nm, v)
    years = sorted(y for y in by if len(by[y]) > 40)
    if not years:
        return None
    y = years[-1]
    tot = sum(v for _, v in by[y].values())
    out = []
    for a3, (nm, v) in sorted(by[y].items(), key=lambda x: -x[1][1]):
        sh = round(100 * v / tot, 1) if tot else 0
        if sh < 1:
            break
        prev = by.get(y - 1, {}).get(a3, (None, None))[1]
        hist = [by.get(y - k, {}).get(a3, (None, None))[1] for k in range(1, 6)]
        hist = [h for h in hist if h is not None]
        out.append({"country": nm, "short": SHORT.get(nm, nm), "iso": numeric(a3), "value": round(v, 1), "share": sh, "prev": prev,
                    "avg5": sum(hist) / len(hist) if hist else None, "mapped": sh >= THRESH})
    return {"year": y, "world": round(tot, 1), "unit": unit, "prod_source": source, "production": out}


def states(rows, unit_filter, scale, unit, what, source, months=1):
    """US states from EIA state rows [period, duoarea, area, desc, units, value]."""
    rows = [r for r in rows if r[4] == unit_filter]
    if not rows:
        return None
    periods = sorted({r[0] for r in rows})
    last = periods[-months:]
    prevp = periods[-12 - months:-12] if len(periods) >= 12 + months else []
    def agg(ps):
        d = defaultdict(float)
        for r in rows:
            if r[0] in ps:
                d[r[1]] += r[5]
        return {k: v * scale / len(ps) for k, v in d.items()} if ps else {}
    now, prev = agg(last), agg(prevp)
    tot = now.get("NUS")
    st = []
    for k, v in now.items():
        if k.startswith("S") and len(k) == 3 and k[1:] in FIPS and v > 0:
            st.append({"state": NAMES[k[1:]], "abbr": k[1:], "fips": FIPS[k[1:]], "value": round(v, 1), "prev": round(prev[k], 1) if k in prev else None})
    tot = tot or sum(s["value"] for s in st)
    for s in st:
        s["share"] = round(100 * s["value"] / tot, 1)
    st.sort(key=lambda s: -s["value"])
    off = now.get("R3FM")
    return {"what": what, "unit": unit, "source": source, "period": last[-1] if months == 1 else f"{last[0]} to {last[-1]}", "total": round(tot, 1),
            "offshore": round(off, 1) if off else None, "states": st}


def flows(ct, key, label):
    d = (ct or {}).get("data", {}).get(key, {})
    fl, ex = [], []
    for nm, x in d.get("exporters", {}).items():
        a3 = {"Korea": "KOR", "United States": "USA", "United Arab Emirates": "ARE", "Saudi Arabia": "SAU"}.get(nm)
        ex.append({"country": nm, "value": round(x["total_t"] / 1e6, 1), "unit": "Mt", "year": x["year"]})
        import pycountry
        try:
            src = pycountry.countries.lookup(a3 or nm)
            fiso = src.numeric
        except Exception:
            fiso = None
        for pc, pn, p3, t, usd in x["partners"][:6]:
            to = numeric(p3) if p3 else None
            fl.append({"from": nm, "from_iso": fiso, "to": pn, "to_iso": to, "t": round(t / 1000), "usd": usd, "year": x["year"]})
    ex.sort(key=lambda e: -e["value"])
    return fl, ex


def us_dest(rows, title, unit_filter, unit, source, scale=1.0, months=None):
    rows = [r for r in rows if r[4] == unit_filter]
    if not rows:
        return None
    periods = sorted({r[0] for r in rows})
    ps = periods[-months:] if months else periods[-1:]
    d = defaultdict(float)
    for r in rows:
        if r[0] in ps and r[1].startswith("NUS-N"):
            nm = r[3].split(" to ", 1)[1].split(" of ")[0].split(" (")[0].strip() if " to " in r[3] else r[2]
            d[nm] += r[5] * scale / (1 if months else 1)
    tot = sum(d.values())
    top = sorted(d.items(), key=lambda x: -x[1])[:10]
    return {"title": title, "source": source, "unit": unit, "period": ps[-1] if not months else f"{ps[0]} to {ps[-1]}",
            "top": [{"country": c, "value": round(v, 1), "share": round(100 * v / tot, 1) if tot else None} for c, v in top]}


def main():
    E, O, C = J("eia.json") or {}, J("owid.json") or {}, J("comtrade.json")
    OUT.mkdir(parents=True, exist_ok=True)
    gen = date.today().isoformat()
    # crude
    g = world([r for r in E.get("intl_crude", []) if r[3] is not None], "kb/d", "EIA International") or {}
    fl, ex = flows(C, "crude", "")
    crude = {"key": "crude", "name": "Crude oil", "threshold": THRESH, **g,
             "us_states": states(E.get("us_crude_states", []), "MBBL/D", 1, "kb/d", "crude oil production by state", "EIA"),
             "flows": fl, "flows_label": "crude oil exports of the main exporters by destination, UN Comtrade (HS 2709), thousand tonnes",
             "exporters": ex, "exporters_label": "UN Comtrade, million tonnes (Russia does not report)",
             "us_dest": [x for x in [us_dest(E.get("us_exp_crude", []), "US crude exports: top 10 destinations", "MBBL/D", "kb/d", "EIA")] if x],
             "links": [{"name": a, "url": b, "what": c} for a, b, c in LINKS["crude"]], "sources": "EIA (international, state production, exports), UN Comtrade.", "generated": gen}
    (OUT / "crude.json").write_text(json.dumps(crude))
    # natural gas
    og = [[y, a3, nm, v] for y, a3, nm, v in O.get("data", {}).get("gas_production", [])]
    g = world(og, "TWh", "Energy Institute Statistical Review via Our World in Data") or {}
    poe = E.get("us_lng_poe", [])
    per = sorted({r[0] for r in poe})
    last12 = per[-12:]
    term = defaultdict(float); lastm = defaultdict(float); buyers = defaultdict(lambda: defaultdict(float))
    for p, da, an, desc, u, v in poe:
        if p not in last12 or da.startswith("NUS"):
            continue
        code, dest = da.split("-", 1)
        if dest == "Z00":
            term[code] += v / 1000
            if p == per[-1]:
                lastm[code] += v / 1000
        else:
            buyers[code][re.sub(r"\s+(Liquefied|LNG).*$", "", desc.split(" to ", 1)[1].split(" (")[0]).strip().title() if " to " in desc else an] += v / 1000
    tot = sum(term.values())
    rows = []
    for code, v in sorted(term.items(), key=lambda x: -x[1]):
        if code not in TERMINALS or v < 0.005 * tot:
            continue
        nm, lat, lon = TERMINALS[code]
        top = [k for k, _ in sorted(buyers[code].items(), key=lambda x: -x[1])[:4]]
        rows.append({"name": nm, "short": nm.split(",")[0], "lat": lat, "lon": lon, "value": round(v, 1), "last": round(lastm[code], 1), "share": round(100 * v / tot, 1),
                     "unit": "Bcf (12 m)", "top": top})
    pipe = defaultdict(float); pto = {}
    for p, da, an, desc, u, v in E.get("us_pipe_poe", []):
        if p in last12 and not da.startswith("NUS"):
            nm = desc.split(" Natural Gas")[0].strip()
            pipe[nm] += v / 1000; pto[nm] = an
    lng_dest = defaultdict(float)
    for p, da, an, desc, u, v in poe:
        if p in last12 and da.startswith("NUS-N") and not da.endswith("Z00"):
            lng_dest[desc.split(" to ", 1)[1].split(" (")[0] if " to " in desc else an] += v / 1000
    ld_tot = sum(lng_dest.values())
    fl1, ex1 = flows(C, "lng", "")
    fl2, ex2 = flows(C, "pipeline_gas", "")
    natgas = {"key": "natgas", "name": "Natural gas", "threshold": THRESH, **g,
              "us_states": states(E.get("us_gas_states", []), "MMCF", 1 / 1000 / 30.4, "Bcf/d", "natural gas marketed production by state (12-month average)", "EIA", months=12),
              "terminals": {"through": per[-1] if per else None, "total": round(tot, 1), "rows": rows,
                            "note": "Terminals with under 0.5% of exports (small container exports from Florida and border points) are left out."} if rows else None,
              "pipeline": [{"name": k, "to": pto[k], "value": round(v, 1)} for k, v in sorted(pipe.items(), key=lambda x: -x[1])],
              "flows": fl1 + fl2, "flows_label": "LNG (HS 271111) and pipeline gas (HS 271121) exports of the main exporters, UN Comtrade, thousand tonnes",
              "exporters": [dict(e, country=e["country"] + " (LNG)") for e in ex1] + [dict(e, country=e["country"] + " (pipeline)") for e in ex2], "exporters_label": "UN Comtrade, million tonnes",
              "us_dest": [{"title": "US LNG exports: top 10 destinations", "source": "EIA", "unit": "Bcf", "period": f"{last12[0]} to {last12[-1]}" if last12 else "",
                           "top": [{"country": c, "value": round(v, 1), "share": round(100 * v / ld_tot, 1)} for c, v in sorted(lng_dest.items(), key=lambda x: -x[1])[:10]]}] if ld_tot else [],
              "links": [{"name": a, "url": b, "what": c} for a, b, c in LINKS["natgas"]], "sources": "EIA (state production, LNG and pipeline exports by point of exit), Energy Institute via OWID, UN Comtrade.", "generated": gen}
    (OUT / "natgas.json").write_text(json.dumps(natgas))
    # products
    g = world([r for r in E.get("intl_consumption", []) if r[3] is not None], "kb/d", "EIA International (petroleum consumption)") or {}
    fl3, ex3 = flows(C, "diesel", "")
    fl4, ex4 = flows(C, "gasoline", "")
    ref = states(E.get("us_refining", []), "B/CD", 1 / 1000, "kb/d", "refining capacity", "EIA")
    products = {"key": "products", "name": "Oil products (diesel & gasoline)", "threshold": THRESH, **g, "prod_title": "Where oil is consumed",
                "refining": ref,
                "flows": fl3 + fl4, "flows_label": "diesel/gas oil (HS 271019) and motor gasoline (HS 271012) exports of the main exporters, UN Comtrade, thousand tonnes",
                "exporters": [dict(e, country=e["country"] + " (diesel)") for e in ex3] + [dict(e, country=e["country"] + " (gasoline)") for e in ex4], "exporters_label": "UN Comtrade, million tonnes",
                "us_dest": [x for x in [us_dest(E.get("us_exp_distillate", []), "US distillate exports: top 10 destinations", "MBBL/D", "kb/d", "EIA"),
                                         us_dest(E.get("us_exp_gasoline", []), "US gasoline exports: top 10 destinations", "MBBL/D", "kb/d", "EIA")] if x],
                "links": [{"name": a, "url": b, "what": c} for a, b, c in LINKS["products"]], "sources": "EIA (consumption by country, refining capacity, exports), UN Comtrade.", "generated": gen}
    if products.get("production"):
        products["name"] = "Oil products (diesel & gasoline)"
    (OUT / "products.json").write_text(json.dumps(products))
    for k, v in (("crude", crude), ("natgas", natgas), ("products", products)):
        print(k, v.get("year"), len(v.get("production") or []), "producers;", len(v.get("flows") or []), "flows;", "states", len((v.get("us_states") or v.get("refining") or {}).get("states", [])))


if __name__ == "__main__":
    main()
