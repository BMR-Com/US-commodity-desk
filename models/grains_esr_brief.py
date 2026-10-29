#!/usr/bin/env python3
"""
grains_esr_brief.py — weekly export sales brief for grains and oilseeds (data/grains/derived/esr_brief.json).

Same engine as the BMR-Com cotton export sales brief: US commitments and shipments vs the latest WASDE export
forecast, pace vs past seasons at the same week, what is needed per week to reach USDA, this week's buyers,
each importer's commitments vs its USDA import forecast and usual US share, the shipment calendar, competing
exporters' supply, price in the reporting week, and a 5/10/20-season profile. Wheat is also split by class.
"""
import io, json, os
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ESRD = ROOT / "data" / "grains" / "raw" / "export_sales"
OUT = ROOT / "data" / "grains" / "derived" / "esr_brief.json"
WASDE_RAW = "https://raw.githubusercontent.com/BMR-Com/wasde-analytics/main/data"
WASDE_LOCAL = os.getenv("WASDE_DIR")
BU_PER_MT = {"corn": 39.368, "soybeans": 36.744, "wheat": 36.744, "kc": 36.744}

EU = ["European Union", "Austria", "Belgium-Luxembourg", "Denmark", "France", "Germany", "Greece", "Ireland", "Italy", "Netherlands",
      "Poland", "Portugal", "Romania", "Spain", "Cyprus", "Sweden", "Finland", "Bulgaria", "Croatia", "Malta", "Slovenia", "Lithuania", "Latvia", "Estonia"]
SEA = ["Vietnam", "Indonesia", "Philippines", "Malaysia", "Thailand", "Burma", "Cambodia", "Laos", "Singapore"]
NAF = ["Algeria", "Egypt", "Libya", "Morocco", "Tunisia"]
MIDEAST = ["Iran", "Iraq", "Israel", "Jordan", "Kuwait", "Lebanon", "Oman", "Qatar", "Saudi Arabia", "Syria", "United Arab Emirates", "Yemen", "Bahrain"]
def groups(pairs):
    out = {}
    for reg, members in pairs:
        for m in members:
            out[m] = reg
    return out
# ESR destination -> WASDE importing region (aggregates add up their member countries)
GROUPS = {
    "corn": groups([("Mexico", ["Mexico"]), ("Japan", ["Japan"]), ("South Korea", ["South Korea"]), ("Egypt", ["Egypt"]), ("China", ["China"]),
                    ("Canada", ["Canada"]), ("European Union", EU), ("Southeast Asia", SEA)]),
    "soybeans": groups([("China", ["China"]), ("Mexico", ["Mexico"]), ("Japan", ["Japan"]), ("European Union", EU), ("Southeast Asia", SEA)]),
    "wheat": groups([("Japan", ["Japan"]), ("China", ["China"]), ("Brazil", ["Brazil"]), ("Nigeria", ["Nigeria"]), ("Bangladesh", ["Bangladesh"]),
                     ("Pakistan", ["Pakistan"]), ("European Union", EU), ("Southeast Asia", SEA), ("N. Africa", NAF), ("Sel. Mideast", MIDEAST)]),
}
GROUPS["kc"] = GROUPS["wheat"]
GROUPS["cotton"] = groups([(c, [c]) for c in ("Vietnam", "Bangladesh", "China", "Pakistan", "Turkey", "Indonesia", "Mexico", "India", "Thailand")])
WHEAT_CLASSES = [("wheat_hrw", "HRW"), ("wheat_srw", "SRW"), ("wheat_hrs", "HRS"), ("wheat_white", "White"), ("wheat_durum", "Durum")]
COMMS = [
    {"key": "corn", "name": "Corn", "sym": "ZC", "dirs": [("corn", "Corn")], "wasde": "Corn.json", "start": 9, "to_world": 0.0254012, "brazil": "corn",
     "w_unit": "m bu", "w_fmt": 0, "px": "CBOT corn", "px_unit": "¢/bu", "px_fmt": 2},
    {"key": "soybeans", "name": "Soybeans", "sym": "ZS", "dirs": [("soybeans", "Soybeans")], "wasde": "Oilseed,_Soybean.json", "start": 9, "to_world": 0.0272155, "brazil": "soybeans",
     "w_unit": "m bu", "w_fmt": 0, "px": "CBOT soybeans", "px_unit": "¢/bu", "px_fmt": 2},
    {"key": "meal", "name": "Soybean meal", "sym": "ZM", "dirs": [("soybean_meal", "Meal")], "wasde": "Meal,_Soybean.json", "start": 10, "to_world": 0.000907185, "brazil": "meal",
     "w_unit": "k short tons", "w_fmt": 0, "px": "CBOT soybean meal", "px_unit": "$/st", "px_fmt": 1},
    {"key": "oil", "name": "Soybean oil", "sym": "ZL", "dirs": [("soybean_oil", "Oil")], "wasde": "Oil,_Soybean.json", "start": 10, "to_world": 0.000453592, "brazil": "oil",
     "w_unit": "m lb", "w_fmt": 0, "px": "CBOT soybean oil", "px_unit": "¢/lb", "px_fmt": 2, "disp": 1.0, "disp_unit": "MT"},
    {"key": "wheat", "name": "All wheat", "sym": "ZW", "dirs": [("wheat_all", "All wheat")], "classes": WHEAT_CLASSES, "wasde": "Wheat.json", "start": 6,
     "to_world": 0.0272155, "w_unit": "m bu", "w_fmt": 0, "px": "CBOT Chicago wheat", "px_unit": "¢/bu", "px_fmt": 2},
    {"key": "kc", "name": "HRW wheat", "sym": "KE", "dirs": [("wheat_hrw", "HRW")], "wasde": "Hard_Red_Winter.json", "world": "Wheat.json", "start": 6, "to_world": 0.0272155,
     "w_unit": "m bu", "w_fmt": 0, "px": "KC HRW wheat", "px_unit": "¢/bu", "px_fmt": 2, "class_share": True},
    # cotton (upland + Pima, running bales): the desk's own copy, so the cotton tab does not depend on the separate export-sales repo
    {"key": "cotton", "name": "Cotton", "sym": "CT", "dirs": [("cotton_upland", "Upland"), ("cotton_pima", "Pima")], "wasde": "Cotton.json", "start": 8,
     "to_world": 1.0, "w_unit": "m bales", "w_fmt": 2, "px": "ICE cotton", "px_unit": "¢/lb", "px_fmt": 2, "disp": 1e3, "disp_unit": "'000 bales",
     "sscale": 1.0, "world_unit": "m bales", "brazil": "cotton", "blend": True},
]
NOUN = {"corn": "corn", "soybeans": "soybeans", "meal": "soybean meal", "oil": "soybean oil", "wheat": "wheat", "kc": "HRW wheat", "cotton": "cotton"}
for c_ in COMMS:
    c_["noun"] = NOUN[c_["key"]]
    c_.setdefault("sscale", 3)          # world tables in MMT: changes below ~1 MMT are noise
    c_.setdefault("disp", 1e3); c_.setdefault("disp_unit", "'000 MT"); c_["esr_unit"] = "MT"
ALIAS = {"Ending stocks": "Ending Stocks", "Domestic use": "Domestic Use", "Domestic, Total": "Domestic Use", "Domestic Total": "Domestic Use",
         "Total  Domestic": "Domestic Use", "Beginning stocks": "Beginning Stocks", "Domestic, total": "Domestic Use", "Domestic Disappearance": "Domestic Use",
         "Domestic": "Domestic Use", "EU-27": "European Union", "Output": "Production"}
SUPPLY = {"corn": (["Brazil", "Argentina", "Ukraine", "South Africa", "Russia"], ["Mexico", "Japan", "South Korea", "Egypt", "China", "Southeast Asia", "European Union"]),
          "soybeans": (["Brazil", "Argentina", "Paraguay"], ["China", "European Union", "Mexico", "Japan", "Southeast Asia"]),
          "wheat": (["European Union", "Russia", "Canada", "Australia", "Argentina", "Ukraine", "Kazakhstan"], ["N. Africa", "Sel. Mideast", "Southeast Asia", "China", "Japan", "Brazil", "Nigeria", "Pakistan", "Bangladesh"])}
SUPPLY["kc"] = SUPPLY["wheat"]
SUPPLY["cotton"] = (["Brazil", "Australia", "India", "Afr. Fr. Zone", "Central Asia"], ["China", "Vietnam", "Bangladesh", "Pakistan", "Turkey", "Indonesia", "Mexico", "India", "Thailand"])
# Brazil's raw-cotton exports by destination (Comex Stat, NCM 5201.00.20/90), Portuguese names -> export-sales names
BR_FILE = ROOT / "data" / "south_america" / "brazil_exports_by_country.csv"   # commodity, year, month, country, t
PT = {"Vietnã": "Vietnam", "Turquia": "Turkey", "Paquistão": "Pakistan", "Indonésia": "Indonesia", "Malásia": "Malaysia", "Índia": "India", "Coreia do Sul": "South Korea",
      "Tailândia": "Thailand", "Egito": "Egypt", "Taiwan (Formosa)": "Taiwan", "Itália": "Italy", "Japão": "Japan", "México": "Mexico", "Colômbia": "Colombia",
      "Mianmar": "Burma", "Filipinas": "Philippines", "Marrocos": "Morocco", "Espanha": "Spain", "Alemanha": "Germany", "Grécia": "Greece", "Peru": "Peru",
      "Equador": "Ecuador", "Guatemala": "Guatemala", "Honduras": "Honduras", "El Salvador": "El Salvador", "Hong Kong": "Hong Kong", "Singapura": "Singapore",
      "Tunísia": "Tunisia", "Argélia": "Algeria", "Emirados Árabes Unidos": "United Arab Emirates", "Reino Unido": "United Kingdom", "Países Baixos (Holanda)": "Netherlands",
      "Irã": "Iran", "Arábia Saudita": "Saudi Arabia", "República Dominicana": "Dominican Republic", "França": "France", "Bélgica": "Belgium-Luxembourg", "Polônia": "Poland",
      "Dinamarca": "Denmark", "Irlanda": "Ireland", "Romênia": "Romania", "Bulgária": "Bulgaria", "Croácia": "Croatia", "Eslovênia": "Slovenia", "Chipre": "Cyprus",
      "Finlândia": "Finland", "Suécia": "Sweden", "Lituânia": "Lithuania", "Letônia": "Latvia", "Estônia": "Estonia", "Áustria": "Austria", "Tcheca  República": "Czech Republic",
      "Eslováquia": "Slovakia", "Noruega": "Norway", "Suíça": "Switzerland", "Rússia": "Russia", "Ucrânia": "Ukraine", "Iraque": "Iraq", "Jordânia": "Jordan", "Líbano": "Lebanon",
      "Líbia": "Libya", "Omã": "Oman", "Catar": "Qatar", "Coveite (Kuweit)": "Kuwait", "Iêmen": "Yemen", "Síria": "Syria", "Barein": "Bahrain", "Israel": "Israel",
      "Camboja": "Cambodia", "Nigéria": "Nigeria", "África do Sul": "South Africa", "Quênia": "Kenya", "Canadá": "Canada", "Chile": "Chile", "Venezuela": "Venezuela",
      "Cuba": "Cuba", "Panamá": "Panama", "Costa Rica": "Costa Rica", "Nicarágua": "Nicaragua", "Jamaica": "Jamaica", "Nova Zelândia": "New Zealand", "Austrália": "Australia",
      "Coreia do Norte": "North Korea", "Uruguai": "Uruguay", "Paraguai": "Paraguay", "Bolívia": "Bolivia", "Senegal": "Senegal", "Gana": "Ghana", "Costa do Marfim": "Ivory Coast",
      "Angola": "Angola", "Moçambique": "Mozambique", "Sudão": "Sudan", "Etiópia": "Ethiopia", "Geórgia": "Georgia", "Armênia": "Armenia", "Azerbaijão": "Azerbaijan"}
KG_PER_BALE = 217.724
INDIA_EXPORT_RATIO = 1.5
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def brazil_flows(cfg, GR):
    """Brazil's exports of this commodity by destination and month, in export-sales units (MT, or running bales for cotton),
    with destinations grouped into USDA's importing regions where the desk groups them."""
    key = cfg.get("brazil")
    if not key or not BR_FILE.exists():
        return None
    b = pd.read_csv(BR_FILE)
    b = b[b.commodity == key].copy()
    if b.empty:
        return None
    b["c"] = b.country.map(lambda x: PT.get(x, x)).map(lambda n: GR.get(n, n))
    b["kb"] = b.t * (1000 / KG_PER_BALE if cfg["key"] == "cotton" else 1.0) / cfg["disp"]
    b["d"] = pd.to_datetime(dict(year=b.year, month=b.month, day=1))
    return b


def brazil_for(B, nm, months=3):
    """Last `months` of Brazil's shipments to a destination vs the same months a year earlier."""
    if B is None or B.empty:
        return None
    last = B.d.max()
    g = B[B.c == nm]
    win = (g.d > last - pd.DateOffset(months=months)) & (g.d <= last)
    win_ly = (g.d > last - pd.DateOffset(months=12 + months)) & (g.d <= last - pd.DateOffset(months=12))
    tot3 = B[(B.d > last - pd.DateOffset(months=months)) & (B.d <= last)].kb.sum()
    r = {"last": f"{last:%b %Y}", "from": f"{last - pd.DateOffset(months=months - 1):%b}", "b3": float(g[win].kb.sum()), "b3_ly": float(g[win_ly].kb.sum()),
         "share_of_brazil": float(g[win].kb.sum() / tot3) if tot3 else None}
    r["b3_yoy"] = r["b3"] / r["b3_ly"] - 1 if r["b3_ly"] > 0.5 else None
    return r


def supply_context(cfg, w, my):
    if cfg["key"] not in SUPPLY:
        return None
    EXP, IMP = SUPPLY[cfg["key"]]; y0 = int(my[:4]); pmy = f"{y0 - 1}/{str(y0)[-2:]}"
    g = lambda r, a, m: w_latest(w, r, a, m)[0]
    ex, im = [], []
    for r in EXP:
        n = [g(r, a, my) for a in ("Beginning Stocks", "Production", "Domestic Use", "Exports")]; o = [g(r, a, pmy) for a in ("Beginning Stocks", "Production", "Domestic Use", "Exports")]
        if None in n[:3] or None in o[:3]:
            continue
        ratio = (n[0] + n[1]) / n[2] if n[2] else None; ratio_ly = (o[0] + o[1]) / o[2] if o[2] else None
        active = not (cfg["key"] == "cotton" and r == "India" and (ratio or 0) < INDIA_EXPORT_RATIO)
        ex.append({"r": r, "surplus": n[0] + n[1] - n[2], "surplus_ly": o[0] + o[1] - o[2], "prod": n[1], "prod_ly": o[1], "bs": n[0], "bs_ly": o[0], "exp": n[3], "exp_ly": o[3],
                   "ratio": ratio, "ratio_ly": ratio_ly, "active": active,
                   "active_ly": not (cfg["key"] == "cotton" and r == "India" and (ratio_ly or 0) < INDIA_EXPORT_RATIO)})
    for r in IMP:
        n = [g(r, a, my) for a in ("Beginning Stocks", "Production", "Domestic Use", "Imports")]; o = [g(r, a, pmy) for a in ("Beginning Stocks", "Production", "Domestic Use", "Imports")]
        if None in n[:3] or None in o[:3]:
            continue
        im.append({"r": r, "supply": n[0] + n[1], "supply_ly": o[0] + o[1], "use": n[2], "use_ly": o[2], "imp": n[3], "imp_ly": o[3],
                   "gap": (n[0] + n[1] - n[2]) - (o[0] + o[1] - o[2])})
    wu, wu_ly = g("World", "Domestic Use", my), g("World", "Domestic Use", pmy)
    wt, wt_ly = g("World", "Imports", my), g("World", "Imports", pmy)
    cv = cfg.get("to_world", 1.0)
    us, us_ly = (g("United States", "Exports", my) or 0) * cv, (g("United States", "Exports", pmy) or 0) * cv
    wex = g("World", "Exports", my) or wt; wex_ly = g("World", "Exports", pmy) or wt_ly
    return {"exporters": ex, "importers": im, "world_use": wu, "world_use_ly": wu_ly, "world_trade": wt, "world_trade_ly": wt_ly,
            "us_share": us / wex if us and wex else None, "us_share_ly": us_ly / wex_ly if us_ly and wex_ly else None, "my": my, "pmy": pmy}


def supply_text(S, cfg, fu):
    if not S or not S["exporters"]:
        return None
    t = ""
    act = [x for x in S["exporters"] if x["active"] or x["active_ly"]]
    d = sum((x["surplus"] if x["active"] else 0) - (x["surplus_ly"] if x["active_ly"] else 0) for x in act)
    dx = sum(((x["exp"] or 0) if x["active"] else 0) - ((x["exp_ly"] or 0) if x["active_ly"] else 0) for x in act)
    names = ", ".join(x["r"] for x in S["exporters"] if x["active"])
    tl = [f"{x['r']} {x['surplus'] - x['surplus_ly']:+.2f}" for x in sorted([x for x in act if x["active"]], key=lambda x: x["surplus"] - x["surplus_ly"]) if abs(x["surplus"] - x["surplus_ly"]) >= 0.2][:4]
    t += (f"Main competitors ({names}): exportable surplus {d:+.2f} vs {S['pmy']}" + (f" ({', '.join(tl)})" if tl else "")
          + f", and USDA has their combined exports {dx:+.2f} — " + (f"less competition for US {cfg['noun']}. " if dx < -0.2 * cfg.get("sscale", 1) else f"more competition for US {cfg['noun']}. " if dx > 0.2 * cfg.get("sscale", 1) else "little change in competition. "))
    ind = next((x for x in S["exporters"] if x["r"] == "India"), None)
    if ind and not ind["active"] and ind.get("ratio"):
        t += f"India is not competing for export business this season: supply is {ind['ratio']:.2f}× its own use (it exports in volume only when this is about 1.5× or more), so it is counted as an importer. "
    tight = [x for x in S["importers"] if x["gap"] < -0.3 * cfg.get("sscale", 1)]
    loose = [x for x in S["importers"] if x["gap"] > 0.3 * cfg.get("sscale", 1)]
    if tight:
        t += "Importers with tighter own supply vs use than last year: " + ", ".join(
            f"{x['r']} ({x['gap']:+.2f}" + (f"; imports {x['imp']:.2f} vs {x['imp_ly']:.2f}" if x["imp"] is not None and x["imp_ly"] is not None else "") + ")" for x in sorted(tight, key=lambda x: x["gap"])[:4]) + ". "
    if loose:
        t += "Better supplied: " + ", ".join(f"{x['r']} ({x['gap']:+.2f})" for x in sorted(loose, key=lambda x: -x["gap"])[:3]) + ". "
    if S["world_use"] and S["world_use_ly"]:
        t += f"World use {S['world_use']:,.2f} ({S['world_use'] / S['world_use_ly'] - 1:+.1%} y/y)"
        if S["world_trade"] and S["world_trade_ly"]:
            t += f", world trade {S['world_trade']:,.2f} ({S['world_trade'] / S['world_trade_ly'] - 1:+.1%})"
        t += ". "
    if S["us_share"] and S["us_share_ly"]:
        t += f"USDA has the US at {S['us_share'] * 100:.0f}% of world exports vs {S['us_share_ly'] * 100:.0f}% last season"
        if cfg["key"] == "wheat":
            t += "."
        elif dx < -0.2 and S["us_share"] <= S["us_share_ly"]:
            t += " — **with competitors tighter, that share looks conservative.**"
        elif dx > 0.2 and S["us_share"] > S["us_share_ly"]:
            t += " — **with competitors better supplied, that share looks ambitious.**"
        else:
            t += "."
    return t


# ─────────────────────────── data ───────────────────────────
def wasde(fname, key=None):
    if WASDE_LOCAL and (Path(WASDE_LOCAL) / fname).exists():
        d = json.load(open(Path(WASDE_LOCAL) / fname))
    else:
        import requests
        r = requests.get(f"{WASDE_RAW}/{fname}", timeout=120); r.raise_for_status(); d = r.json()
    bu = BU_PER_MT.get(key)
    rows = []
    for k, vals in d["data"].items():
        reg, attr, my = k.split("||")
        attr = ALIAS.get(attr.strip(), attr.strip()); reg = ALIAS.get(reg, reg)
        for v in vals:
            if v.get("value") is None:
                continue
            val, unit = float(v["value"]), str(v.get("unit", ""))
            if reg == "United States" and "metric" in unit.lower():
                if not bu or attr not in ("Beginning Stocks", "Ending Stocks", "Exports", "Imports", "Production"):
                    continue          # world-table copy of the US: keep domestic units
                val = round(val * bu)
            rows.append((reg, attr, my, pd.Timestamp(year=v["forecastYear"], month=v["forecastMonth"], day=1), val))
    w = pd.DataFrame(rows, columns=["reg", "attr", "my", "rd", "val"])
    return w.drop_duplicates(["reg", "attr", "my", "rd"], keep="first")


def w_latest(w, reg, attr, my, upto=None):
    x = w[(w.reg == reg) & (w.attr == attr) & (w.my == my)]
    if upto is not None:
        x = x[x.rd <= upto]
    x = x.sort_values("rd")
    return (float(x.val.iloc[-1]), x.rd.iloc[-1]) if len(x) else (None, None)


def prices(sym):
    p = ROOT / "data" / "ohlc" / f"{sym}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["date"])
    d = d[d.series == "cont"].set_index("date").sort_index()[["close", "low", "high"]].dropna()
    return d


def week_px(px, we):
    """Front-month futures over the export-sales reporting week: Friday to Thursday ending `we`."""
    s = px[(px.index > we - pd.Timedelta(days=7)) & (px.index <= we)]
    return {"avg": float(s.close.mean()), "low": float(s.low.min()), "high": float(s.high.max()), "close": float(s.close.iloc[-1]), "days": len(s)} if len(s) else None


NICE = {"China, Peoples Republic Of": "China", "Korea, Republic Of": "South Korea", "South Africa, Republic Of": "South Africa",
        "Tanzania, United Republic Of": "Tanzania", "Unknown": "Unknown destinations", "European": "European Union", "Gambia, The": "Gambia",
        "Georgia, Republic Of": "Georgia"}


def esr(dirs):
    cn = {}
    try:
        for x in json.load(open(ESRD / "countries.json")):
            nm = str(x.get("countryDescription") or x.get("countryName")).strip().title().replace("'S", "'s")
            cn[int(x["countryCode"])] = NICE.get(nm, nm)
    except Exception:
        pass
    parts = []
    for i, (d, _) in enumerate(dirs):
        for f in sorted((ESRD / d).glob("MY*.csv")):
            x = pd.read_csv(f, low_memory=False)
            if x.empty:
                continue
            x["marketYear"] = int(f.stem[2:]); x["commodityCode"] = i
            parts.append(x)
    if not parts:
        return None
    e = pd.concat(parts, ignore_index=True)
    e["weekEndingDate"] = pd.to_datetime(e.weekEndingDate.astype(str).str[:10])
    for c in ["grossNewSales", "currentMYNetSales", "weeklyExports", "accumulatedExports", "outstandingSales", "nextMYNetSales", "nextMYOutstandingSales"]:
        e[c] = pd.to_numeric(e[c], errors="coerce").fillna(0)
    e["countryCode"] = pd.to_numeric(e.countryCode, errors="coerce").fillna(0).astype(int)
    e = e[e.countryCode != 0]
    e["countryName"] = [cn.get(c, f"Code {c}") for c in e.countryCode]
    e["commit"] = e.accumulatedExports + e.outstandingSales
    return remove_rollover(e)


def remove_rollover(e):
    """Week 1 of each marketing year includes old-crop sales still unshipped at the end of the previous year,
    which USDA rolls into the new year's net (and gross) sales. Take them out, country by country, so week 1
    shows only new business. Seasons where the roll-over was not booked into week 1 are left as reported."""
    e = e.copy(); e["carryIn"] = 0.0
    keys = ["commodityCode", "marketYear"]
    first = e.groupby(keys).weekEndingDate.transform("min"); last = e.groupby(keys).weekEndingDate.transform("max")
    end_out = e[e.weekEndingDate == last].groupby(["commodityCode", "marketYear", "countryCode"]).outstandingSales.sum()
    m1 = e.weekEndingDate == first
    carry = [end_out.get((cc, y - 1, ct), 0.0) for cc, y, ct in zip(e.loc[m1, "commodityCode"], e.loc[m1, "marketYear"], e.loc[m1, "countryCode"])]
    e.loc[m1, "carryIn"] = carry
    chk = e[m1].groupby(keys)[["currentMYNetSales", "carryIn"]].sum()
    booked = set(i for i, r in chk.iterrows() if r.carryIn > 0 and r.currentMYNetSales - r.carryIn >= -0.05 * r.carryIn)
    apply_ = m1 & pd.Series([(cc, y) in booked for cc, y in zip(e.commodityCode, e.marketYear)], index=e.index)
    e.loc[apply_, "currentMYNetSales"] -= e.loc[apply_, "carryIn"]
    e.loc[apply_, "grossNewSales"] = (e.loc[apply_, "grossNewSales"] - e.loc[apply_, "carryIn"]).clip(lower=0)
    e.loc[~apply_, "carryIn"] = 0.0
    return e


def price_sensitive(e, px, cfg, top=6):
    """Destinations whose weekly purchases rise most when price fell in the reporting week (last 10 seasons).
    Correlation of each buyer's weekly net sales (z-scored within season) with the week's % price change."""
    wk = e.groupby(["countryName", "marketYear", "weekEndingDate"]).currentMYNetSales.sum().reset_index()
    wk = wk[wk.marketYear >= wk.marketYear.max() - 10]
    dates = sorted(wk.weekEndingDate.unique())
    chg = {}
    for d in dates:
        a, b = week_px(px, d), week_px(px, d - pd.Timedelta(days=7))
        if a and b:
            chg[d] = a["avg"] / b["avg"] - 1
    wk["chg"] = wk.weekEndingDate.map(chg)
    out = []
    big = set(wk.groupby("countryName").currentMYNetSales.sum().sort_values(ascending=False).head(25).index)
    for nm, g in wk.dropna(subset=["chg"]).groupby("countryName"):
        if nm not in big or nm.startswith("Unknown") or (g.currentMYNetSales > 0).sum() < 60:
            continue
        z = g.groupby("marketYear").currentMYNetSales.transform(lambda x: (x - x.mean()) / (x.std() or 1))
        r = np.corrcoef(z, g.chg)[0, 1]
        n = len(g)
        if np.isfinite(r) and r * np.sqrt(n - 2) / np.sqrt(max(1e-9, 1 - r * r)) < -2:
            out.append((r, nm))
    return [nm for r, nm in sorted(out)[:top]]


def my_label(e, start_month):
    """ESR marketYear → WASDE 'YYYY/YY' using the first week of each year's data."""
    out = {}
    for y, g in e.groupby("marketYear"):
        d0 = g.weekEndingDate.min()
        sy = d0.year if d0.month >= start_month else d0.year - 1
        out[y] = (sy, f"{sy}/{str(sy + 1)[-2:]}")
    return out


# ─────────────────────────── analysis ───────────────────────────
def q(v):
    """Format a value in display units ('000 bales): no decimals above 100, one below."""
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


NOTES = ROOT / "data" / "grains" / "esr_notes.json"   # dated policy/market notes: [{"key","until","t"}], dropped after "until"


def demand_text(cfg, tot, labels, cur_y, wk, L, S, last_date, D, fu, w=None):
    """Cotton: this season vs the last two at the same week, importer demand, rival exporters, dated policy notes."""
    parts, score = [], 0
    wu_ = cfg.get("world_unit", "MMT"); thr = 0.1 if wu_ == "m bales" else 0.2
    rows = []
    for y in (cur_y - 1, cur_y - 2):
        g = tot[(tot.marketYear == y) & (tot.wk <= wk)].sort_values("wk")
        if len(g):
            fin_u = w_latest(w, "United States", "Exports", labels[y][1])[0] if w is not None else None
            rows.append((labels[y][1], float(g.commit.iloc[-1]), float(g.accumulatedExports.iloc[-1]), fin_u))
    if rows:
        above_c = all(L.commit > r[1] for r in rows); above_s = all(L.accumulatedExports > r[2] for r in rows)
        parts.append("Same week of the last two seasons: " + "; ".join(f"{m} commitments {q(c / D)}, shipped {q(sh / D)}" + (f" (final exports {fu(f)} {cfg['w_unit']})" if f else "") for m, c, sh, f in rows)
                     + f" — this season {q(L.commit / D)} committed and {q(L.accumulatedExports / D)} shipped ({cfg['disp_unit']}, export-sales basis)"
                     + (", ahead of both on sales and shipments." if above_c and above_s else ", ahead of both on sales." if above_c else ", ahead of both on shipments." if above_s else "."))
        if above_c and above_s:
            score += 1
            parts.append("Running ahead of both on sales and shipments makes a finish below last season unlikely unless buying stalls.")
    if S and S.get("importers"):
        imp = [x for x in S["importers"] if x.get("imp") is not None and x.get("imp_ly") is not None and not (cfg["key"] == "cotton" and x["r"] == "China")]
        up = sorted([x for x in imp if x["imp"] - x["imp_ly"] >= thr], key=lambda x: x["imp_ly"] - x["imp"])
        dn = [x for x in imp if x["imp"] - x["imp_ly"] <= -thr]
        dsum = sum(x["imp"] - x["imp_ly"] for x in imp)
        wu, wl = S.get("world_use"), S.get("world_use_ly")
        if wu and wl:
            parts.append(f"World {'mill use' if cfg['key'] == 'cotton' else 'consumption'} {wu:,.1f} {wu_} vs {wl:,.1f} last season ({wu - wl:+.1f}).")
        if up:
            parts.append(("Import forecasts up for spinning countries that grow little or no cotton: " if cfg["key"] == "cotton" else "Import forecasts up: ") + ", ".join(f"{x['r']} {x['imp']:.1f} ({x['imp'] - x['imp_ly']:+.1f})" for x in up) + ".")
        if dn:
            parts.append("Down: " + ", ".join(f"{x['r']} {x['imp']:.1f} ({x['imp'] - x['imp_ly']:+.1f})" for x in dn) + ".")
        if dsum - sum(x["imp"] - x["imp_ly"] for x in dn) > 5 * thr:
            score += 1
    if S and S.get("exporters"):
        ch = [(x["r"], (x["exp"] or 0) - (x["exp_ly"] or 0)) for x in S["exporters"] if x.get("active")]
        tot_ch = sum(v for _, v in ch)
        if ch:
            parts.append("Rival exporters' forecasts vs last season: " + ", ".join(f"{r} {v:+.1f}" for r, v in ch if abs(v) >= thr) + f" (net {tot_ch:+.1f} {wu_}).")
    try:
        for n_ in json.loads(NOTES.read_text()):
            if n_.get("key") == cfg["key"] and pd.Timestamp(n_["until"]) >= last_date:
                parts.append(n_["t"])
    except Exception:
        pass
    return (" ".join(parts) if parts else None), (1 if score >= 2 else 0)


def build(cfg):
    e = esr(cfg["dirs"])
    if e is None or e.empty:
        return None
    w = wasde(cfg["wasde"], cfg["key"])
    ww = wasde(cfg["world"], cfg["key"]) if cfg.get("world") else w      # world tables (import forecasts, competitors)
    labels = my_label(e, cfg["start"])
    tot = e.groupby(["marketYear", "weekEndingDate"])[["commit", "accumulatedExports", "outstandingSales", "currentMYNetSales", "weeklyExports",
                                                       "grossNewSales", "nextMYOutstandingSales", "nextMYNetSales"]].sum().reset_index()
    tot["wk"] = tot.apply(lambda r: (r.weekEndingDate - pd.Timestamp(year=labels[r.marketYear][0], month=cfg["start"], day=1)).days // 7, axis=1)
    cur_y = int(tot.marketYear.max()); sy, my = labels[cur_y]
    c = tot[tot.marketYear == cur_y].sort_values("weekEndingDate")
    if c.empty:
        return None
    L = c.iloc[-1]; wk = int(L.wk); last_date = L.weekEndingDate
    target, rd = w_latest(w, "United States", "Exports", my)
    if target is None:
        return None
    prev_t, _ = w_latest(w, "United States", "Exports", my, rd - pd.Timedelta(days=20))

    # ratio ESR final shipments / WASDE final exports (per completed season), and same-week pace history
    hist = []
    for y in sorted(tot.marketYear.unique()):
        if y >= cur_y or y < cur_y - 10:
            continue
        g = tot[tot.marketYear == y].sort_values("wk")
        if g.empty:
            continue
        fin_esr = float(g.accumulatedExports.iloc[-1]); wfin, _ = w_latest(w, "United States", "Exports", labels[y][1])
        if not wfin and cfg.get("cov") and fin_esr:
            wfin = fin_esr / cfg["cov"]          # class tables only go back a few seasons: use all-wheat export-sales coverage
        at = g[g.wk <= wk]
        if not len(at) or not wfin or not fin_esr:
            continue
        a = at.iloc[-1]
        hist.append({"y": y, "my": labels[y][1], "ratio": fin_esr / wfin, "fin_esr": fin_esr, "wfin": wfin,
                     "commit_pct": a.commit / fin_esr, "ship_pct": a.accumulatedExports / fin_esr, "commit": a.commit,
                     "net4": float(g[(g.wk > wk - 4) & (g.wk <= wk)].currentMYNetSales.mean())})
    H = pd.DataFrame(hist)
    if H.empty:
        return None
    H5 = H.tail(5)
    ratio = float(H5.ratio.median()); t_esr = target * ratio
    pace = L.commit / t_esr; pace_n = float(H5.commit_pct.mean()); ship = L.accumulatedExports / t_esr; ship_n = float(H5.ship_pct.mean())
    implied = L.commit / pace_n / ratio if pace_n > 0 else None
    weeks_left = max(1, 52 - (wk + 1))
    need_ship = (t_esr - L.accumulatedExports) / weeks_left
    CARRY = 0      # replaced below by the typical end-of-season carry-over of the last 5 seasons
    sales_left = t_esr + CARRY - L.commit; ship_left = t_esr - L.accumulatedExports
    need_sales = sales_left / weeks_left
    rec = c.tail(4); net4 = float(rec.currentMYNetSales.mean()); ship4 = float(rec.weeklyExports.mean())
    ly = H[H.y == cur_y - 1]; ly_commit = float(ly.commit.iloc[0]) if len(ly) else None
    net4_5y = float(H5.net4.mean())
    D = cfg["disp"]

    # ── projections and feasibility from what past seasons did over the REST of the season (not just % of USDA) ──
    rest = []
    for y in H.y:
        g = tot[tot.marketYear == y].sort_values("wk")
        at = g[g.wk <= wk]
        if not len(at):
            continue
        after = g[g.wk > wk]
        rest.append({"y": y, "my": labels[y][1], "commit_wk": float(at.commit.iloc[-1]), "fin": float(g.accumulatedExports.iloc[-1]),
                     "carry": float(g.outstandingSales.iloc[-1]), "rem_sales": float(after.currentMYNetSales.sum()), "rem_ship": float(after.weeklyExports.sum()),
                     "n_rem": int(len(after))})
    R = pd.DataFrame(rest)
    R["add"] = R.fin - R.commit_wk
    R5 = R.tail(5)
    carry = float(R5.carry.median()) if len(R5) else 0.0
    CARRY = carry
    proj = {"share": L.commit / pace_n if pace_n > 0 else None,
            "add": L.commit + float(R5["add"].median()) if len(R5) else None,
            "add_lo": L.commit + float(R5["add"].min()) if len(R5) else None, "add_hi": L.commit + float(R5["add"].max()) if len(R5) else None,
            "ly": L.commit + float(R["add"].iloc[-1]) if len(R) else None}
    vals = [v for v in (proj["share"], proj["add"], proj["ly"]) if v is not None]
    proj["central"] = float(np.median(vals)) if vals else None
    if cfg.get("blend"):
        # Cotton: buying has moved later in the season (no Chinese front-loading, mills booking nearer shipment), so the
        # share-of-final method runs low. Central = median of four sales-flow views: 5-season median additions,
        # recency-weighted additions (last 3 seasons, 1:2:3), last season's additions, and additions explained by the
        # current net-sales rate and commitment level (fit on the last 10 seasons). Share-of-final is shown, not used.
        R3 = R.tail(3)
        proj["add3w"] = L.commit + float(np.average(R3["add"], weights=list(range(1, len(R3) + 1)))) if len(R3) else None
        RF = R.merge(H[["y", "net4"]], on="y").tail(10)
        if len(RF) >= 6:
            X = np.c_[np.ones(len(RF)), RF.net4, RF.commit_wk]; b_ = np.linalg.lstsq(X, RF["add"], rcond=None)[0]
            proj["flow"] = L.commit + float(b_ @ [1.0, net4, L.commit])
        vals = [v for v in (proj["add"], proj.get("add3w"), proj["ly"], proj.get("flow")) if v is not None]
        proj["central"] = float(np.median(vals)) if vals else None
        proj["blend_lo"], proj["blend_hi"] = (float(min(vals)), float(max(vals))) if vals else (None, None)
    projw = {k: (v / ratio if v is not None else None) for k, v in proj.items()}           # USDA (census) units
    if projw["central"]:
        implied = projw["central"]
    sales_need_tot = t_esr + carry - L.commit
    ship_need_tot = t_esr - L.accumulatedExports
    feas = {"sales_need": sales_need_tot, "ship_need": ship_need_tot, "carry": carry,
            "sales_ok5": int((R5.rem_sales >= sales_need_tot).sum()), "sales_ok10": int((R.rem_sales >= sales_need_tot).sum()),
            "ship_ok5": int((R5.rem_ship >= ship_need_tot).sum()), "ship_ok10": int((R.rem_ship >= ship_need_tot).sum()), "n5": int(len(R5)), "n10": int(len(R)),
            "rem_sales_wk5": float((R5.rem_sales / R5.n_rem.clip(lower=1)).mean()) if len(R5) else None,
            "rem_sales_wk_lo": float((R5.rem_sales / R5.n_rem.clip(lower=1)).min()) if len(R5) else None,
            "rem_sales_wk_hi": float((R5.rem_sales / R5.n_rem.clip(lower=1)).max()) if len(R5) else None,
            "rem_sales_wk_ly": float(R.rem_sales.iloc[-1] / max(R.n_rem.iloc[-1], 1)) if len(R) else None,
            "rem_ship_wk5": float((R5.rem_ship / R5.n_rem.clip(lower=1)).mean()) if len(R5) else None,
            "rem_ship_wk_hi": float((R5.rem_ship / R5.n_rem.clip(lower=1)).max()) if len(R5) else None,
            "fin_ly": float(R.fin.iloc[-1]) if len(R) else None, "fin_max5": float(R5.fin.max()) if len(R5) else None}
    sales_left = sales_need_tot
    need_sales = sales_left / weeks_left

    # this week's buyers
    tw = e[(e.marketYear == cur_y) & (e.weekEndingDate == last_date)]
    by = tw.groupby("countryName")[["currentMYNetSales", "weeklyExports", "nextMYNetSales"]].sum()
    buyers = by.currentMYNetSales.sort_values(ascending=False)
    top_buy = [{"c": k, "v": round(v / D, 3)} for k, v in buyers.head(5).items() if v > 0]
    cancels = [{"c": k, "v": round(v / D, 3)} for k, v in buyers.tail(3).items() if v / D <= -0.0005]
    top_ship = [{"c": k, "v": round(v / D, 3)} for k, v in by.weeklyExports.sort_values(ascending=False).head(5).items() if v > 0]

    # destinations
    cy = e[e.marketYear == cur_y]
    GR = GROUPS.get(cfg["key"], {})
    eg = e.assign(countryName=e.countryName.map(lambda n: GR.get(n, n)))      # member countries summed into USDA's importing regions
    cyg = eg[eg.marketYear == cur_y]
    cn = cyg[cyg.weekEndingDate == last_date].groupby("countryName").commit.sum()
    dest = []
    names = [n for n in cn.sort_values(ascending=False).head(12).index if n != "Unknown destinations"]
    for reg in sorted(set(GR.values())):
        imp, _ = w_latest(ww, reg, "Imports", my)
        if imp and imp > 0.3 and reg in set(cyg.countryName) and reg not in names:
            names.append(reg)
    for nm in names:
        row = {"c": nm, "commit": round(float(cn.get(nm, 0)) / D, 3), "share_now": float(cn.get(nm, 0)) / L.commit if L.commit else None}
        hh = []
        for _, h in H.iterrows():
            g = eg[(eg.marketYear == h.y) & (eg.countryName == nm)]
            if g.empty:
                hh.append({"y": h.y, "my": h.my, "same": 0.0, "fin": 0.0}); continue
            gw = g.groupby("weekEndingDate")[["commit", "accumulatedExports"]].sum().reset_index()
            gw["wk"] = (gw.weekEndingDate - pd.Timestamp(year=labels[h.y][0], month=cfg["start"], day=1)).dt.days // 7
            at = gw[gw.wk <= wk]
            hh.append({"y": h.y, "my": h.my, "same": float(at.commit.iloc[-1]) if len(at) else 0.0, "fin": float(gw.sort_values("wk").accumulatedExports.iloc[-1]),
                       "ratio": h.ratio})
        hh = pd.DataFrame(hh)
        last5 = hh.tail(5)
        row["ly"] = round(float(hh.same.iloc[-1]) / D, 3) if len(hh) else None
        row["avg5"] = round(float(last5.same.mean()) / D, 3) if len(last5) else None
        fin5 = last5.fin.sum()
        row["norm_pct"] = float(last5.same.sum() / fin5) if fin5 > 0 else None   # share of final usually committed by now
        reg = nm if nm in set(GR.values()) else None
        if reg:
            imp, _ = w_latest(ww, reg, "Imports", my)
            sh = []
            for _, x in hh.iterrows():
                ii, _ = w_latest(ww, reg, "Imports", x.my)
                if ii and ii > 0 and x.get("ratio"):
                    sh.append(x.fin / x.ratio * cfg.get("to_world", 1.0) / ii)
            if imp and sh:
                s5, s10 = float(np.mean(sh[-5:])), float(np.mean(sh))
                exp_us = imp * s5                             # usual US-origin volume (WASDE units)
                row.update({"imports": imp, "us_share5": s5, "us_share10": s10, "exp_us": round(exp_us, 3)})
                if row["norm_pct"] and row["norm_pct"] >= 0.25:
                    impl = float(cn.get(nm, 0)) / row["norm_pct"] / ratio * cfg.get("to_world", 1.0)
                    row["implied_us"] = round(impl, 3); row["implied_share"] = impl / imp
                    row["vs_usual"] = impl / exp_us - 1 if exp_us else None
        if reg:
            pmy_ = f"{int(my[:4]) - 1}/{my[2:4]}"
            row["imports_ly"] = w_latest(ww, reg, "Imports", pmy_)[0]
        dest.append(row)
    for row in dest:      # far below normal this season AND last season at this point: a lost market, not room to catch up
        row["structural_low"] = bool(row.get("avg5") and row["commit"] < 0.5 * row["avg5"] and (row.get("ly") or 0) < 0.5 * row["avg5"])
    BRZ = brazil_flows(cfg, GR)
    if BRZ is not None:
        for row in dest:
            row["brazil"] = brazil_for(BRZ, row["c"])

    # shipment seasonality by destination: share of the season's shipments by calendar month (last 5 seasons)
    seas = []
    ye = e[e.marketYear.isin(H5.y)].copy(); ye["m"] = ye.weekEndingDate.dt.month
    top = ye.groupby("countryName").weeklyExports.sum().sort_values(ascending=False)
    for nm in [n for n in top.index if n not in ("Unknown", "Code 9990", "Unknown destinations")][:10]:
        g = ye[ye.countryName == nm].groupby("m").weeklyExports.sum()
        if g.sum() <= 0:
            continue
        sh = (g / g.sum()).reindex(range(1, 13), fill_value=0)
        order = [((cfg["start"] - 1 + i) % 12) + 1 for i in range(12)]
        cum = np.cumsum([sh[m] for m in order])
        mi = order.index(last_date.month)
        cy_c = cy[(cy.countryName == nm) & (cy.weekEndingDate == last_date)]
        acc = float(cy_c.accumulatedExports.sum()); com = float(cy_c.commit.sum())
        seas.append({"c": nm, "share": [round(float(sh[m]), 3) for m in order], "peak": [MONTHS[m - 1] for m in sh.sort_values(ascending=False).index[:3]],
                     "norm_shipped": round(float(cum[mi]), 3), "shipped_of_commit": round(acc / com, 3) if com else None,
                     "next3": round(float(sum(sh[order[(mi + k) % 12]] for k in range(1, 4))), 3), "outstanding": round((com - acc) / D, 3)})
    months_order = [MONTHS[((cfg["start"] - 1 + i) % 12)] for i in range(12)]
    S = supply_context(cfg, ww, my)

    # narrative
    fu = lambda v: f"{v:,.{cfg['w_fmt']}f}"
    T = []
    head = (f"Week ending {last_date:%b %d}: {cfg['noun']} commitments {q(L.commit / D)} {cfg['disp_unit']} for {my} "
            f"({q(L.accumulatedExports / D)} shipped, {q(L.outstandingSales / D)} outstanding) = **{pace*100:.0f}% of USDA's {fu(target)} {cfg['w_unit']}** "
            f"export forecast, vs a 5-yr norm of {pace_n*100:.0f}% by week {wk + 1}. "
            + f"(Export sales usually capture {ratio / (cfg['to_world'] * 1e6):.0%} of USDA's census-basis exports — median of the last 5 seasons — so USDA's {fu(target)} {cfg['w_unit']} is taken as {q(t_esr / D)} {cfg['disp_unit']} on the export-sales basis.) ")
    if ly_commit:
        head += f"Commitments are {L.commit / ly_commit - 1:+.0%} vs a year ago. "
    if projw.get("central"):
        gap = projw["central"] / target - 1
        pp = lambda k: fu(projw[k]) if projw.get(k) else "n/a"
        if cfg.get("blend"):
            head += (f"Projection (USDA units): **{fu(projw['central'])} {cfg['w_unit']}** ({gap:+.0%} vs USDA), the middle of four sales-flow views — "
                     f"what the rest of the season added in the last 5 seasons ({pp('add')}), the same weighted toward the last 3 ({pp('add3w')}), "
                     f"last season's finish ({pp('ly')}) and what the current net-sales rate implies ({pp('flow')}); range {pp('blend_lo')}–{pp('blend_hi')}. "
                     f"Simply scaling by the usual share sold by now gives {pp('share')}, but that method has run low in each of the last three seasons because "
                     f"buyers now book later in the season than when China front-loaded purchases, so it is shown for reference only. ")
        else:
          head += (f"Three ways to project the season from here (USDA units): if this week's {pace*100:.0f}% is the usual share of the final, about {pp('share')}; "
                 f"if the rest of the season adds what it added in the last 5 seasons, about **{pp('add')}** (range {pp('add_lo')}–{pp('add_hi')}); "
                 f"if it repeats last season's finish, {pp('ly')}. Middle estimate **{fu(projw['central'])} {cfg['w_unit']}** ({gap:+.0%} vs USDA)"
                 + ((" — early-season sales are a weak guide to the final number for this crop, so treat this as a direction, not a forecast." if cfg["key"] in ("corn", "sorghum") and abs(gap) > 0.04 else "")
                    or (" — below USDA; a cut is possible unless sales pick up." if gap < -0.04 else " — above USDA; room for a raise." if gap > 0.04 else " — in line with USDA."))
                 + (" The %-of-USDA comparison understates the pace when USDA's target is larger than in past seasons; the second method does not depend on the target." if pace < pace_n and ly_commit and L.commit > ly_commit else ""))
    T.append({"h": "Pace vs USDA", "t": head})
    dem_sig = 0
    if True:
        dem_t, dem_sig = demand_text(cfg, tot, labels, cur_y, wk, L, S, last_date, D, fu, w)
        if dem_t:
            T.append({"h": "Demand & competition", "t": dem_t})
    F_ = feas
    def ease(ok, n, ok10=0):
        return ("comfortably achievable" if ok >= max(n - 1, 1) and n else "achievable" if ok >= (n + 1) // 2 else "a stretch" if ok >= 1
                else "a stretch (last done more than 5 seasons ago)" if ok10 > 0 else "not achieved in any recent season")
    verdict = ease(F_['sales_ok5'], F_['n5'], F_['sales_ok10'])
    if net4 >= need_sales and (F_.get('rem_sales_wk_ly') or 0) >= need_sales:
        verdict = "achievable at the current pace and last season's rest-of-season pace (both above what is needed)"
    t = (f"To reach USDA's {fu(target)} {cfg['w_unit']}, the US needs {q(F_['sales_need'] / D)} {cfg['disp_unit']} more net sales "
         f"(including the usual {q(F_['carry'] / D)} carried into next season) — {q(need_sales / D)}/week for {weeks_left} weeks. "
         f"Over the same weeks the last 5 seasons sold {q(F_['rem_sales_wk5'] / D)}/week on average (range {q(F_['rem_sales_wk_lo'] / D)}–{q(F_['rem_sales_wk_hi'] / D)}; last season {q(F_['rem_sales_wk_ly'] / D)}); "
         f"that total was reached in {F_['sales_ok5']} of the last {F_['n5']} seasons and {F_['sales_ok10']} of {F_['n10']} — **sales look {verdict}**. "
         f"Recent pace: {q(net4 / D)}/week over the last 4 weeks (5-yr avg for these weeks {q(net4_5y / D)}). "
         f"Shipments need {q(need_ship / D)}/week vs {q(F_['rem_ship_wk5'] / D)}/week shipped over the rest of the season on average (best of 5: {q(F_['rem_ship_wk_hi'] / D)}); "
         f"reached in {F_['ship_ok5']} of {F_['n5']} seasons — shipping capacity looks {ease(F_['ship_ok5'], F_['n5'], F_['ship_ok10'])}. "
         f"Shipped so far {ship*100:.0f}% of target (norm {ship_n*100:.0f}%).")
    T.append({"h": "What USDA's number requires", "t": t})
    if prev_t is not None and abs(target - prev_t) > 1e-9:
        T.append({"h": "Latest WASDE", "t": f"USDA {'raised' if target > prev_t else 'cut'} the {my} export forecast to {fu(target)} {cfg['w_unit']} ({target - prev_t:+,.{cfg['w_fmt']}f}) in the {rd:%B} report."})
    wkline = f"Net sales {q(L.currentMYNetSales / D)} {cfg['disp_unit']} (4-wk avg {q(net4 / D)}); shipments {q(L.weeklyExports / D)}."
    if top_buy:
        wkline += " Main buyers: " + ", ".join(f"{b['c']} {q(b['v'])}" for b in top_buy[:4]) + "."
    if cancels:
        wkline += " Net reductions: " + ", ".join(f"{b['c']} {q(b['v'])}" for b in cancels) + "."
    if L.nextMYOutstandingSales > 0 and wk > 30:
        wkline += f" Next-season sales on the books {q(L.nextMYOutstandingSales / D)}."
    T.append({"h": "This week", "t": wkline})
    xs = 0.0
    dd = [d for d in dest if d.get("vs_usual") is not None and d.get("imports") and np.isfinite(d["vs_usual"])]
    if dd:
        ahead = sorted([d for d in dd if d["vs_usual"] > 0.15], key=lambda d: -d["vs_usual"])[:3]
        behind = sorted([d for d in dd if d["vs_usual"] < -0.15], key=lambda d: d["vs_usual"])[:3]
        t = ""
        if ahead:
            t += "Buying more US than usual: " + "; ".join(f"{d['c']} (pace implies {d['implied_share']*100:.0f}% US share of its {d['imports']:,.2f} {cfg.get('world_unit', 'MMT')} import forecast vs {d['us_share5']*100:.0f}% usual)" for d in ahead) + ". "
        if behind:
            t += "Buying less US than usual: " + "; ".join(f"{d['c']} ({d['implied_share']*100:.0f}% vs {d['us_share5']*100:.0f}% usual)" for d in behind) + "."
        xs = sum((d["implied_us"] - d["exp_us"]) for d in dd if not d.get("structural_low")) / cfg.get("to_world", 1.0)
        lost = [d["c"] for d in dd if d.get("structural_low")]
        t += (f" Across these destinations, the sales pace adds up to {fu(xs) if abs(xs) >= 10 else f'{xs:+.2f}'} {cfg['w_unit']} vs their usual US-origin volumes"
              + (" — supports a higher US export forecast." if xs > 0.03 * target else " — argues against raising USDA's number." if xs < -0.03 * target else ".")
              + (f" Left out of that sum: {', '.join(lost)}, running far below normal for a second season (treated as a lost market, not room to catch up)." if lost else ""))
        if t:
            T.append({"h": "Destinations vs import forecasts", "t": t})
    room, crowded, brup = [], [], []
    cand = [d for d in dest if (d.get("avg5") or 0) > 0 or d.get("imports")]
    if cand:
        lines = []
        wu = cfg.get("world_unit", "MMT")
        for d in sorted(cand, key=lambda d: -max((d.get("exp_us") or 0) / cfg.get("to_world", 1.0) * ratio / D, d.get("avg5") or 0, d["commit"]))[:8]:
            b = d.get("brazil") or {}
            yy = d["commit"] / d["ly"] - 1 if d.get("ly") else None
            v5 = d["commit"] / d["avg5"] - 1 if d.get("avg5") else None
            iy = d["imports"] / d["imports_ly"] - 1 if d.get("imports") and d.get("imports_ly") else None
            by = b.get("b3_yoy")
            if d.get("implied_share") is not None and d.get("vs_usual") is not None:
                rel = d["vs_usual"]; basis = f"pace points to {d['implied_share']*100:.0f}% of its {d['imports']:,.2f} {wu} imports vs {d['us_share5']*100:.0f}% usual"
            else:
                rel = v5; basis = (f"usual US share {d['us_share5']*100:.0f}% of its {d['imports']:,.2f} {wu} imports" if d.get("us_share5") and np.isfinite(d["us_share5"]) else "no USDA import forecast")
            ahead = rel is not None and rel > 0.15
            behind = rel is not None and rel < -0.15
            br_up = by is not None and by > 0.15
            if d.get("structural_low"):
                tag = "far below normal for a second season — treat as lost demand, not room"
            elif ahead and br_up:
                tag = "already well bought and Brazil is shipping more — little extra room"; crowded.append(d["c"])
            elif ahead:
                tag = "ahead of normal — limited extra upside"; crowded.append(d["c"])
            elif behind and br_up:
                tag = "Brazil is taking share — the gap may not close"; brup.append(d["c"])
            elif behind and iy is not None and iy > -0.05:
                tag = "behind normal with steady or rising import needs — room for more US sales"; room.append(d)
            elif behind and iy is None:
                tag = "behind normal (no USDA import forecast to judge the room)"
            elif behind:
                tag = "behind normal, but its imports are falling too"
            else:
                tag = "close to normal"
            lines.append(f"**{d['c']}**: US commitments {q(d['commit'])} ({'' if yy is None else f'{yy:+.0%} y/y, '}{'' if v5 is None else f'{v5:+.0%} vs 5-yr avg'}); {basis}"
                         + (f", USDA imports {iy:+.0%} y/y" if iy is not None else "")
                         + (f"; Brazil shipped {q(b['b3'])} in {b['from']}–{b['last']} ({by:+.0%} y/y)" if b and by is not None else f"; Brazil shipped {q(b['b3'])} in {b['from']}–{b['last']}" if b else "")
                         + f" — {tag}.")
        if lines:
            gap_room = sum((d["exp_us"] - d["implied_us"]) for d in room if d.get("implied_us") is not None and d.get("exp_us") is not None) / cfg.get("to_world", 1.0)
            summ = ((f"Room for more US sales in {', '.join(d['c'] for d in room)}" + (f" (about {fu(gap_room)} {cfg['w_unit']} below their usual US volumes)" if gap_room > 0 else "") + ". " if room else "")
                    + (f"Already well bought: {', '.join(crowded)}. " if crowded else "") + (f"Brazil gaining: {', '.join(brup)}. " if brup else ""))
            bline = ""
            if BRZ is not None:
                bt = BRZ[BRZ.d > BRZ.d.max() - pd.DateOffset(months=3)].kb.sum(); bt_ly = BRZ[(BRZ.d > BRZ.d.max() - pd.DateOffset(months=15)) & (BRZ.d <= BRZ.d.max() - pd.DateOffset(months=12))].kb.sum()
                bline = f"Brazil's total {cfg['noun']} shipments {q(bt)} {cfg['disp_unit']} in the last 3 months ({bt / bt_ly - 1:+.0%} y/y). " if bt_ly else ""
            T.append({"h": "By destination: room vs competition", "t": summ + bline + " ".join(lines)})
    st = supply_text(S, cfg, fu)
    if st:
        T.append({"h": "Competition and import need", "t": st})
    if seas:
        nxt = sorted(seas, key=lambda x: -x["next3"])[:3]
        lag = [x for x in seas if x["shipped_of_commit"] is not None and x["outstanding"] > 0 and x["norm_shipped"] > 0.25 and x["shipped_of_commit"] < 0.5 * x["norm_shipped"]]
        t = ("Shipments usually concentrate in the next three months for " + ", ".join(f"{x['c']} ({x['next3']*100:.0f}% of its season)" for x in nxt) + ".")
        if lag:
            t += " Slow to ship vs sales: " + ", ".join(f"{x['c']} ({q(x['outstanding'])} outstanding)" for x in lag[:3]) + " — watch for cancellations or roll-overs."
        T.append({"h": "Shipment calendar", "t": t})
    # ── week-to-week and year-to-date scorecard ──
    FLOW = [("grossNewSales", "Gross new sales"), ("currentMYNetSales", "Net sales"), ("weeklyExports", "Shipments"), ("nextMYNetSales", "Next-season net sales")]
    STOCK = [("accumulatedExports", "Shipped to date"), ("outstandingSales", "Outstanding sales"), ("commit", "Total commitments"), ("nextMYOutstandingSales", "Next-season outstanding")]
    yrs5 = list(H5.y)
    def make_score(tt):
        cc = tt[tt.marketYear == cur_y].sort_values("weekEndingDate")
        cc = cc[cc.weekEndingDate <= last_date]
        if cc.empty:
            return []
        LL = cc.iloc[-1]; pv = cc.iloc[-2] if len(cc) > 1 else None
        def same_week(y, col):
            g = tt[(tt.marketYear == y) & (tt.wk <= wk)].sort_values("wk")
            return float(g[col].iloc[-1]) if len(g) else None
        def ytd(y, col):
            g = tt[(tt.marketYear == y) & (tt.wk <= wk)]
            return float(g[col].sum()) if len(g) else None
        out_ = []
        for col, lab in FLOW:
            lyv = same_week(cur_y - 1, col); a5 = [v for v in (same_week(y, col) for y in yrs5) if v is not None]
            yt = float(cc[col].sum()); yl = ytd(cur_y - 1, col); y5 = [v for v in (ytd(y, col) for y in yrs5) if v is not None]
            out_.append({"k": col, "label": lab, "type": "flow", "tw": float(LL[col]) / D, "lw": float(pv[col]) / D if pv is not None else None,
                         "avg4": float(cc[col].tail(4).mean()) / D, "ly": lyv / D if lyv is not None else None, "avg5": float(np.mean(a5)) / D if a5 else None,
                         "ytd": yt / D, "ytd_ly": yl / D if yl is not None else None, "ytd_avg5": float(np.mean(y5)) / D if y5 else None})
        for col, lab in STOCK:
            lyv = same_week(cur_y - 1, col); a5 = [v for v in (same_week(y, col) for y in yrs5) if v is not None]
            out_.append({"k": col, "label": lab, "type": "stock", "tw": float(LL[col]) / D, "lw": float(pv[col]) / D if pv is not None else None,
                         "ly": lyv / D if lyv is not None else None, "avg5": float(np.mean(a5)) / D if a5 else None})
        return out_
    prev = c.iloc[-2] if len(c) > 1 else None
    score = make_score(tot)
    score_by = {"All": score}
    for d_, lab_c in cfg.get("classes", []):
        sub = esr([(d_, lab_c)])
        if sub is not None and len(sub):
            sub = sub[sub.marketYear <= cur_y]
            ts = sub.groupby(["marketYear", "weekEndingDate"])[["commit", "accumulatedExports", "outstandingSales", "currentMYNetSales", "weeklyExports",
                                                                 "grossNewSales", "nextMYOutstandingSales", "nextMYNetSales"]].sum().reset_index()
            ts = ts[ts.marketYear.isin(labels.keys())]
            ts["wk"] = [(d - pd.Timestamp(year=labels[y][0], month=cfg["start"], day=1)).days // 7 for y, d in zip(ts.marketYear, ts.weekEndingDate)]
            score_by[lab_c] = make_score(ts)
    # weekly series (this season + last 5) for interactive charts
    series = {}
    yrs20 = [y for y in sorted(tot.marketYear.unique()) if y < cur_y][-20:]
    for y in [cur_y] + yrs20[::-1]:
        g = tot[tot.marketYear == y].sort_values("wk")
        series[labels[y][1]] = {k: [[int(w_) + 1, round(float(v) / D, 4)] for w_, v in zip(g.wk, g[k])] for k, _ in FLOW + STOCK}
    # countries this week
    cw = e[(e.marketYear == cur_y)]
    tw_ = cw[cw.weekEndingDate == last_date].groupby("countryName")[["currentMYNetSales", "weeklyExports", "accumulatedExports", "outstandingSales", "commit", "nextMYOutstandingSales"]].sum()
    lw_ = cw[cw.weekEndingDate == (prev.weekEndingDate if prev is not None else last_date)].groupby("countryName")[["currentMYNetSales", "weeklyExports"]].sum()
    lyc = {}
    gly = e[e.marketYear == cur_y - 1].copy()
    if len(gly):
        gly["wk"] = (gly.weekEndingDate - pd.Timestamp(year=labels[cur_y - 1][0], month=cfg["start"], day=1)).dt.days // 7
        lastw = gly[gly.wk <= wk].weekEndingDate.max()
        lyc = gly[gly.weekEndingDate == lastw].groupby("countryName")[["commit", "accumulatedExports"]].sum().to_dict("index")
    COLS = ["currentMYNetSales", "weeklyExports", "accumulatedExports", "outstandingSales", "commit", "nextMYOutstandingSales"]
    lyw = {}
    if len(gly):
        lyw = gly[gly.weekEndingDate == lastw].groupby("countryName")[COLS].sum()
    dmap = {d["c"]: d for d in dest}
    def ship_norm(nm):
        """Share of a destination's season shipments usually made by this week (last 5 seasons)."""
        a_, f_ = 0.0, 0.0
        for y in yrs5:
            g = e[(e.marketYear == y) & (e.countryName == nm)]
            if g.empty:
                continue
            gw = g.groupby("weekEndingDate").accumulatedExports.sum().reset_index()
            gw["wk"] = (gw.weekEndingDate - pd.Timestamp(year=labels[y][0], month=cfg["start"], day=1)).dt.days // 7
            at = gw[gw.wk <= wk]
            a_ += float(at.accumulatedExports.iloc[-1]) if len(at) else 0.0; f_ += float(gw.accumulatedExports.max())
        return a_ / f_ if f_ > 0 else None
    def rowfor(nm, cur_, lw0, ly0):
        g = lambda df, k: float(df.get(k, 0)) / D if df is not None else None
        r = {"c": nm, "net": g(cur_, "currentMYNetSales"), "net_lw": g(lw0, "currentMYNetSales"), "net_ly": g(ly0, "currentMYNetSales"),
             "ship": g(cur_, "weeklyExports"), "ship_lw": g(lw0, "weeklyExports"), "ship_ly": g(ly0, "weeklyExports"),
             "accum": g(cur_, "accumulatedExports"), "accum_ly": g(ly0, "accumulatedExports"),
             "outst": g(cur_, "outstandingSales"), "outst_ly": g(ly0, "outstandingSales"),
             "commit": g(cur_, "commit"), "commit_ly": g(ly0, "commit"), "next": g(cur_, "nextMYOutstandingSales")}
        d = dmap.get(nm)
        if d and d.get("imports") and d.get("us_share5"):
            exp_season = d["imports"] * d["us_share5"] / cfg.get("to_world", 1.0) * ratio / D   # usual US volume, export-sales basis
            sn = ship_norm(nm)
            r.update({"imports": d["imports"], "us_share5": d["us_share5"], "exp_season": exp_season, "ship_norm": sn,
                      "exp_mytd": exp_season * sn if sn is not None else None})
        return r
    TW = tw_.reindex(columns=COLS).fillna(0)
    LW = cw[cw.weekEndingDate == (prev.weekEndingDate if prev is not None else last_date)].groupby("countryName")[COLS].sum()
    order_ = [n for n in TW.sort_values("commit", ascending=False).index if n != "Unknown destinations"]
    top12 = order_[:12]
    ctab = [rowfor(nm, TW.loc[nm], LW.loc[nm] if nm in LW.index else None, lyw.loc[nm] if len(lyw) and nm in lyw.index else None) for nm in top12]
    rest = [n for n in TW.index if n not in top12]
    ly_rest = lyw[~lyw.index.isin(top12)].sum() if len(lyw) else None
    oth = rowfor(f"Others ({len(rest)})", TW.loc[rest].sum(), LW[LW.index.isin(rest)].sum(), ly_rest)
    oth["others"] = True
    ctab.append(oth)
    sc = {x["k"]: x for x in score}
    def ch(a, b):
        return (lambda r: "0%" if abs(r) < 0.005 else f"{r:+.0%}")(a / b - 1) if a is not None and b not in (None, 0) else "n/a"
    ns, sh_ = sc["currentMYNetSales"], sc["weeklyExports"]
    T.insert(2, {"h": "Week on week", "t": (
        f"Net sales {q(ns['tw'])} vs {q(ns['lw'] or 0)} the week before ({ch(ns['tw'], ns['lw'])}), {ch(ns['tw'], ns['ly'])} vs the same week last year and "
        f"{ch(ns['tw'], ns['avg5'])} vs the 5-yr average. Shipments {q(sh_['tw'])} vs {q(sh_['lw'] or 0)} ({ch(sh_['tw'], sh_['lw'])}), "
        f"{ch(sh_['tw'], sh_['ly'])} vs last year, {ch(sh_['tw'], sh_['avg5'])} vs the 5-yr average.")})
    T.insert(3, {"h": "Season to date", "t": (
        f"Net sales {q(ns['ytd'])} ({ch(ns['ytd'], ns['ytd_ly'])} y/y, {ch(ns['ytd'], ns['ytd_avg5'])} vs 5-yr avg); shipments {q(sc['accumulatedExports']['tw'])} "
        f"({ch(sc['accumulatedExports']['tw'], sc['accumulatedExports']['ly'])} y/y); outstanding sales {q(sc['outstandingSales']['tw'])} "
        f"({ch(sc['outstandingSales']['tw'], sc['outstandingSales']['ly'])} y/y); next-season sales on the books {q(sc['nextMYOutstandingSales']['tw'])}.")})

    # ── price in the reporting week ──
    px = prices(cfg["sym"])
    PS = price_sensitive(e, px, cfg) if px is not None else []
    price = None
    if px is not None:
        lyd = gly[gly.wk <= wk].weekEndingDate.max() if len(gly) else None
        tw_p, lw_p = week_px(px, last_date), week_px(px, last_date - pd.Timedelta(days=7))
        ly_p = week_px(px, lyd) if lyd is not None and pd.notna(lyd) else None
        p4 = px[(px.index > last_date - pd.Timedelta(days=35)) & (px.index <= last_date - pd.Timedelta(days=7))]
        if tw_p and lw_p:
            wk_series = []
            for r in c.itertuples():
                wp = week_px(px, r.weekEndingDate)
                wk_series.append([int(r.wk) + 1, round(wp["avg"], 2) if wp else None])
            price = {"tw": tw_p, "lw": lw_p, "ly": ly_p, "avg4": float(p4.close.mean()) if len(p4) else None,
                     "chg": tw_p["avg"] / lw_p["avg"] - 1, "low_vs_lw": tw_p["low"] / lw_p["avg"] - 1,
                     "yoy": tw_p["avg"] / ly_p["avg"] - 1 if ly_p else None, "weekly": wk_series}
            cc_ = c[c.wk >= 2]                      # skip the first weeks of the season (carry-in from the old crop)
            trend = float(cc_.currentMYNetSales.iloc[-9:-1].mean()) if len(cc_) > 3 else None
            ns_now = float(L.currentMYNetSales)
            rel_ = ns_now / trend - 1 if trend else None
            pf, pu = cfg["px_fmt"], cfg["px_unit"]
            t = (f"{cfg['px']} averaged {tw_p['avg']:.{pf}f} {pu} in the reporting week (Fri–Thu; low {tw_p['low']:.{pf}f}, high {tw_p['high']:.{pf}f}), "
                 f"{price['chg']:+.1%} vs the week before ({lw_p['avg']:.{pf}f})"
                 + (f" and {price['yoy']:+.1%} vs the same week last year ({ly_p['avg']:.{pf}f})" if ly_p else "") + ". "
                 f"The week's low was {price['low_vs_lw']:+.1%} vs last week's average. ")
            a5_ = [x for x in score if x["k"] == "currentMYNetSales"][0]["avg5"] if score else None
            rel5 = (ns_now / D) / a5_ - 1 if a5_ else None
            if rel_ is not None:
                t += (f"Net sales were {rel_:+.0%} vs their recent trend" + (f" and {rel5:+.0%} vs the 5-yr average for this week" if rel5 is not None else "") + ". ")
                rel_ = (rel_ + rel5) / 2 if rel5 is not None else rel_
                if price["chg"] <= -0.015:
                    t += ("**Buyers stepped in on the price dip — a sign of underlying demand.** " if rel_ > 0.2 else
                          "Some buying came in on the dip, though not strongly. " if rel_ > 0.05 else
                          "**Lower prices failed to pull in buying — demand looks soft.** " if rel_ < -0.1 else "Buying held steady on the dip. ")
                elif price["chg"] >= 0.015:
                    t += ("**Sales held up despite higher prices — firm demand.** " if rel_ > -0.05 else
                          "Buyers stepped back as prices rose, as they usually do. ")
                else:
                    t += "Prices were little changed, so the week's sales mostly reflect underlying demand. "
            sens = [b for b in top_buy if b["c"] in PS]
            if sens:
                t += "Buyers that historically buy more on price dips were active this week: " + ", ".join(f"{b['c']} {q(b['v'])}" for b in sens) + "."
            elif PS:
                t += "Buyers that historically buy more on price dips: " + ", ".join(PS[:5]) + " (none among this week's top buyers)."
            T.insert(4, {"h": "Price and buying", "t": t})
            for r_ in ctab:
                r_["price_sensitive"] = r_["c"] in PS

    # ── historical profile at the same week: 5 / 10 / 20 seasons ──
    PROF = [("accumulatedExports", "Shipped to date"), ("outstandingSales", "Outstanding sales"), ("commit", "Total commitments"), ("nextMYOutstandingSales", "Next-season sales")]
    past = [y for y in sorted(tot.marketYear.unique()) if y < cur_y][-20:]
    def at_week(df_y, y):
        g = df_y.copy(); g["wk"] = (g.weekEndingDate - pd.Timestamp(year=labels[y][0], month=cfg["start"], day=1)).dt.days // 7
        g = g[g.wk <= wk]
        return g[g.weekEndingDate == g.weekEndingDate.max()] if len(g) else g.iloc[0:0]
    snap = {y: at_week(e[e.marketYear == y], y) for y in past}
    cur_snap = e[(e.marketYear == cur_y) & (e.weekEndingDate == last_date)]
    profile = {}
    for col, lab_ in PROF:
        rows_ = []
        for nm in ["Total"] + top12:
            def val(df):
                d_ = df if nm == "Total" else df[df.countryName == nm]
                return float(d_[col].sum()) / D
            hist_ = [val(snap[y]) for y in past]
            now_ = val(cur_snap)
            rec = {"c": nm, "now": now_}
            for n_ in (5, 10, 20):
                h_ = hist_[-n_:]
                if h_:
                    rec[f"min{n_}"], rec[f"max{n_}"], rec[f"avg{n_}"] = min(h_), max(h_), float(np.mean(h_))
            rec["rank"] = int(sum(v > now_ for v in hist_) + 1); rec["of"] = len(hist_) + 1
            rows_.append(rec)
        profile[col] = {"label": lab_, "rows": rows_}

    # bottom line: weigh sales pace, destinations and competitor supply
    sig = []
    if implied:
        g_ = implied / target - 1; sig.append(("sales pace", -1 if g_ < -0.04 else 1 if g_ > 0.04 else 0))
    if dd:
        sig.append(("destination buying", -1 if xs < -0.03 * target else 1 if xs > 0.03 * target else 0))
    if S and S.get("exporters"):
        dxc = sum(((x["exp"] or 0) if x["active"] else 0) - ((x["exp_ly"] or 0) if x["active_ly"] else 0) for x in S["exporters"])
        dxc /= cfg.get("to_world", 1.0)          # world tables are in MMT
        sig.append(("competitor exports", 1 if dxc < -0.03 * target else -1 if dxc > 0.03 * target else 0))
    if dem_sig:
        sig.append(("sales and shipments vs recent seasons, importer demand", dem_sig))
    neg = [a for a, v in sig if v < 0]; pos = [a for a, v in sig if v > 0]; net = sum(v for _, v in sig)
    bl = ("Export outlook vs USDA: **" + ("below" if net < 0 else "above" if net > 0 else "balanced around") + f" USDA's {fu(target)} {cfg['w_unit']}**. ")
    if neg:
        bl += "Pointing lower: " + ", ".join(neg) + ". "
    if pos:
        bl += "Pointing higher: " + ", ".join(pos) + ". "
    if projw.get("central"):
        bl += f"Middle projection {fu(projw['central'])} {cfg['w_unit']} ({projw['central'] / target - 1:+.0%}); "
        bl += f"the sales USDA's number needs were reached in {feas['sales_ok5']} of the last {feas['n5']} seasons ({feas['sales_ok10']} of {feas['n10']}). "
    room_ = [d["c"] for d in room]; crowd_ = crowded
    if room_ or crowd_ or brup:
        if True:
            bl += (("Where extra US sales can come from: " + ", ".join(room_) + ". " if room_ else "") + ("Already well bought: " + ", ".join(crowd_) + ". " if crowd_ else "")
                   + ("Brazil gaining in: " + ", ".join(brup) + ". " if brup else ""))
    if neg and pos:
        bl += ("Less competition usually shows up later in the season, once rival origins run short — "
               "watch whether US sales accelerate into the new year before reading the slow start as lost demand.")
    T.append({"h": "Bottom line", "t": bl})
    # headline follows the bottom line (sales projections, destinations, competitors), not the pace projection alone
    tilt = "weak" if net < 0 else "strong" if net > 0 else "on track"
    return {"name": cfg["name"], "w_fmt": cfg["w_fmt"], "my": my, "week": f"{last_date:%Y-%m-%d}", "wk": wk + 1, "unit": cfg["disp_unit"], "w_unit": cfg["w_unit"],
            "report": f"{rd:%B %Y}", "world_unit": cfg.get("world_unit", "MMT"), "ratio": None, "coverage": ratio / (cfg["to_world"] * 1e6), "key": cfg["key"], "sym": cfg["sym"],
            "px_label": cfg["px"], "px_unit": cfg["px_unit"], "px_fmt": cfg["px_fmt"], "start_month": MONTHS[cfg["start"] - 1], "classes_label": "All classes" if cfg.get("classes") else None, "target": target, "target_prev": prev_t, "target_esr": round(t_esr / D, 3),
            "commit": round(L.commit / D, 3), "shipped": round(L.accumulatedExports / D, 3), "outstanding": round(L.outstandingSales / D, 3),
            "pace": pace, "pace_norm": pace_n, "ship_pct": ship, "ship_norm": ship_n, "implied": implied, "proj": {k: round(float(v), 4) for k, v in projw.items() if v is not None}, "ly_commit": round(ly_commit / D, 3) if ly_commit else None,
            "net": round(L.currentMYNetSales / D, 3), "net4": round(net4 / D, 3), "net4_5y": round(net4_5y / D, 3), "ship_wk": round(L.weeklyExports / D, 3), "ship4": round(ship4 / D, 3),
            "need_ship": round(need_ship / D, 3), "need_sales": round(max(need_sales, 0) / D, 3), "weeks_left": weeks_left, "tilt": tilt,
            "score": score, "score_by": score_by, "sales_left": sales_left / D, "ship_left": ship_left / D, "carry": CARRY / D,
            "target_ly": w_latest(w, "United States", "Exports", f"{int(my[:4]) - 1}/{my[2:4]}")[0], "series": series, "countries": ctab, "price": price, "profile": profile, "profile_years": len(past), "buyers": top_buy, "cancels": cancels, "shippers": top_ship, "dest": dest, "brief": T, "seas": seas, "months": months_order, "supply": S,
            "curve": {"cur": [[int(r.wk) + 1, round(r.commit / t_esr, 4)] for r in c.itertuples()],
                      "hist": {labels[y][1]: [[int(r.wk) + 1, round(r.commit / float(tot[tot.marketYear == y].accumulatedExports.max()), 4)]
                                              for r in tot[tot.marketYear == y].sort_values("wk").itertuples()]
                               for y in yrs20[::-1] if tot[tot.marketYear == y].accumulatedExports.max() > 0}}}


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else round(float(o), 5)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    return o


def main():
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "commodities": []}
    cov = {}
    for cfg in [c for c in COMMS if c.get("enabled", True)]:
        if cfg["key"] == "kc" and "wheat" in cov:
            cfg["cov"] = cov["wheat"] * cfg["to_world"] * 1e6
        try:
            b = build(cfg)
            if b:
                cov[cfg["key"]] = b["coverage"]
        except Exception as ex:
            print(cfg["name"], "failed:", repr(ex)); b = None
        if b:
            out["commodities"].append(b)
            print(f"\n== {b['name']} {b['my']} wk{b['wk']} ({b['week']})")
            for x in b["brief"]:
                print(f"[{x['h']}] {x['t']}")
    OUT.write_text(json.dumps(clean(out), separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
