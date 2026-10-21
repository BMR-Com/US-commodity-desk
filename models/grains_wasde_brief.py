#!/usr/bin/env python3
"""
grains_wasde_brief.py — monthly WASDE brief for corn, soybeans, soybean meal, soybean oil, wheat and HRW wheat.

Same structure as the BMR-Com cotton WASDE brief (BMR-Com/wasde-analytics/brief.py), with the grain cross-checks:
  • key changes vs the previous report: world, world ex-China, US and the main exporters / importers
  • how this month's revisions compare with the same month in past years
  • US crop vs condition ratings (desk yield model), export sales pace vs USDA's export target,
    Brazil/Argentina (CONAB survey vs USDA, Brazil export pace), fund positioning, price
  • a factor-by-factor outlook with an overall tilt; data as known at the report, then the latest data
  • full balance sheets (this and previous release, three marketing years) and revision paths

Writes data/grains/derived/wasde_brief/{index.json, <YYYY-MM>.json, revisions.json}.
"""
import json, os, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import grains_esr_brief as EB  # noqa: E402  (export sales loaders)

OUT = ROOT / "data" / "grains" / "derived" / "wasde_brief"
WASDE_RAW = "https://raw.githubusercontent.com/BMR-Com/wasde-analytics/main/data"
WASDE_LOCAL = os.getenv("WASDE_DIR")
N_RELEASES = 24
BU_PER_MT = {"corn": 39.368, "soybeans": 36.744, "wheat": 36.744, "kc": 36.744}
ALIAS = {"Beginning stocks": "Beginning Stocks", "Domestic use": "Domestic Use", "Ending stocks": "Ending Stocks", "Ending Stocks, Total": "Ending Stocks",
         "Output": "Production", "Use, total": "Total Use", "Use, Total": "Total Use", "Total Use": "Total Use", "Supply, total": "Total Supply",
         "Supply, Total": "Total Supply", "Domestic, Total": "Domestic Use", "Domestic Total": "Domestic Use", "Domestic, total": "Domestic Use",
         "Domestic Disappearance": "Domestic Use", "Domestic": "Domestic Use", "Yield per harvested acre": "Yield", "Yield per Harvested Acre": "Yield",
         "Feed and residual": "Feed and Residual", "Food, seed & industrial": "Food, Seed & Industrial", "Ethanol for fuel": "Ethanol for Fuel",
         "Ethanol & by-products": "Ethanol for Fuel", "Crushings": "Crush", "Domestic Crush": "Crush", "Avg. farm price": "Avg. Farm Price",
         "For methyl ester": "Biofuel", "For Methyl Ester": "Biofuel", "Methyl Ester": "Biofuel", "Biodiesel": "Biofuel",
         "EU-27": "European Union", "Major exporters": "Major Exporters", "Major importers": "Major Importers", "Total foreign": "Total Foreign"}
ATTRS = ["Production", "Domestic Use", "Exports", "Imports", "Ending Stocks"]
US_ROWS = ["Area Planted", "Area Harvested", "Yield", "Beginning Stocks", "Production", "Imports", "Total Supply", "Feed and Residual",
           "Food, Seed & Industrial", "Ethanol for Fuel", "Crush", "Biofuel", "Food", "Seed", "Domestic Use", "Exports", "Total Use", "Ending Stocks", "Avg. Farm Price"]
COMS = {
    "corn": {"name": "Corn", "file": "Corn.json", "sym": "ZC", "esr": "corn", "cond": "corn", "unit": "m bu", "wunit": "MMT",
             "regions": ["World", "World Less China", "United States", "Brazil", "Argentina", "Ukraine", "Russia", "South Africa", "China", "European Union",
                         "Mexico", "Japan", "South Korea", "Southeast Asia", "Egypt"],
             "hist": [("United States", "Yield"), ("United States", "Production"), ("United States", "Feed and Residual"), ("United States", "Exports"),
                      ("United States", "Ending Stocks"), ("World", "Production"), ("World", "Ending Stocks"), ("World Less China", "Ending Stocks"),
                      ("Brazil", "Production"), ("Argentina", "Production"), ("Ukraine", "Production"), ("China", "Imports")],
             "sa": {"conab": "corn", "comex": "corn"}},
    "soybeans": {"name": "Soybeans", "file": "Oilseed,_Soybean.json", "sym": "ZS", "esr": "soybeans", "cond": "soybeans", "unit": "m bu", "wunit": "MMT",
                 "regions": ["World", "World Less China", "United States", "Brazil", "Argentina", "Paraguay", "China", "European Union", "Mexico", "Japan", "Southeast Asia"],
                 "hist": [("United States", "Yield"), ("United States", "Production"), ("United States", "Crush"), ("United States", "Exports"),
                          ("United States", "Ending Stocks"), ("World", "Production"), ("World", "Ending Stocks"), ("Brazil", "Production"),
                          ("Argentina", "Production"), ("China", "Imports"), ("Brazil", "Exports")],
                 "sa": {"conab": "soybeans", "comex": "soybeans"}},
    "meal": {"name": "Soybean meal", "file": "Meal,_Soybean.json", "sym": "ZM", "esr": "meal", "unit": "k short tons",
             "regions": ["United States"], "hist": [("United States", "Production"), ("United States", "Domestic Use"), ("United States", "Exports"), ("United States", "Ending Stocks")],
             "sa": {"comex": "meal"}},
    "oil": {"name": "Soybean oil", "file": "Oil,_Soybean.json", "sym": "ZL", "esr": "oil", "unit": "m lb",
            "regions": ["United States"], "hist": [("United States", "Production"), ("United States", "Biofuel"), ("United States", "Domestic Use"),
                                                   ("United States", "Exports"), ("United States", "Ending Stocks")],
            "sa": {"comex": "oil"}},
    "wheat": {"name": "Wheat", "file": "Wheat.json", "sym": "ZW", "esr": "wheat", "cond": "wheat", "unit": "m bu", "wunit": "MMT",
              "regions": ["World", "World Less China", "United States", "Russia", "European Union", "Canada", "Australia", "Argentina", "Ukraine", "Kazakhstan",
                          "China", "India", "N. Africa", "Sel. Mideast", "Southeast Asia"],
              "hist": [("United States", "Production"), ("United States", "Exports"), ("United States", "Ending Stocks"), ("World", "Production"),
                       ("World", "Ending Stocks"), ("World Less China", "Ending Stocks"), ("Russia", "Production"), ("European Union", "Production"),
                       ("Australia", "Production"), ("Argentina", "Production"), ("Canada", "Production"), ("China", "Imports")]},
    "kc": {"name": "HRW wheat", "file": "Hard_Red_Winter.json", "world": "Wheat.json", "sym": "KE", "esr": "kc", "cond": "wheat", "unit": "m bu", "wunit": "MMT",
           "regions": ["World", "World Less China", "United States", "Russia", "European Union", "Canada", "Australia", "Argentina", "Ukraine"],
           "hist": [("United States", "Production"), ("United States", "Exports"), ("United States", "Ending Stocks"), ("World", "Production"),
                    ("World", "Ending Stocks"), ("Russia", "Production")]},
}


# ─────────────────────────── loaders ───────────────────────────
def raw(fname):
    if WASDE_LOCAL and (Path(WASDE_LOCAL) / fname).exists():
        return json.load(open(Path(WASDE_LOCAL) / fname))
    import requests
    r = requests.get(f"{WASDE_RAW}/{fname}", timeout=180); r.raise_for_status(); return r.json()


def load_wasde(fname, key, us_only=False, drop_us=False):
    d = raw(fname); bu = BU_PER_MT.get(key); rows = []
    for k, vals in d["data"].items():
        reg, attr, my = k.split("||")
        attr = ALIAS.get(attr.strip(), attr.strip()); reg = ALIAS.get(reg, reg)
        if (us_only and reg != "United States") or (drop_us and reg == "United States"):
            continue
        for v in vals:
            if v.get("value") is None:
                continue
            val, unit = float(v["value"]), str(v.get("unit", ""))
            if reg == "United States" and "metric" in unit.lower():
                if not bu or attr not in ("Beginning Stocks", "Ending Stocks", "Exports", "Imports", "Production"):
                    continue
                val, unit = round(val * bu), "Million Bushels"
            rows.append((reg, attr, my, pd.Timestamp(year=v["forecastYear"], month=v["forecastMonth"], day=1), val, unit))
    df = pd.DataFrame(rows, columns=["reg", "attr", "my", "rd", "val", "unit"])
    return df.drop_duplicates(["reg", "attr", "my", "rd"], keep="first")


def frame(cfg, key):
    if cfg.get("world"):        # HRW: US class balance + world wheat tables
        return pd.concat([load_wasde(cfg["file"], key, us_only=True), load_wasde(cfg["world"], key, drop_us=True)], ignore_index=True)
    return load_wasde(cfg["file"], key)


def cond_data():
    p = ROOT / "data" / "grains" / "derived" / "condition.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cot(sym):
    p = ROOT / "data" / "cot_desk" / f"{sym}.json"
    if not p.exists():
        return None
    s = json.loads(p.read_text())["series"]
    df = pd.DataFrame({"mm_n": s["mm_n"], "oi": s["oi"]}, index=pd.to_datetime(s["date"])).astype(float)
    lo, hi = df.mm_n.rolling(156, min_periods=52).min(), df.mm_n.rolling(156, min_periods=52).max()
    df["idx"] = (df.mm_n - lo) / (hi - lo) * 100
    return df


def south_america():
    sa = ROOT / "data" / "south_america"
    out = {}
    try:
        out["conab"] = pd.read_csv(sa / "conab_surveys.csv")
    except Exception:
        pass
    try:
        out["comex"] = pd.read_csv(sa / "brazil_exports.csv")
    except Exception:
        pass
    return out


# ─────────────────────────── helpers (as in the cotton brief) ───────────────────────────
_IDX = {}


def get(df, reg, attr, my, rd):
    k = id(df)
    if k not in _IDX:
        _IDX[k] = {(a, b, c, d): v for a, b, c, d, v in zip(df.reg, df.attr, df.my, df.rd, df.val)}
    v = _IDX[k].get((reg, attr, my, rd))
    return None if v is None else float(v)


_FM = {}


def focus_my(df, rd):
    k = (id(df), rd)
    if k not in _FM:
        _FM[k] = _focus_my(df, rd)
    return _FM[k]


def _focus_my(df, rd):
    mys = sorted(df[(df.rd == rd) & (df.reg == "United States")].my.unique()) or sorted(df[df.rd == rd].my.unique())
    return mys[-1] if mys else None


def su(df, reg, my, rd):
    es = get(df, reg, "Ending Stocks", my, rd)
    tu = get(df, reg, "Total Use", my, rd)
    du = get(df, reg, "Domestic Use", my, rd); ex = get(df, reg, "Exports", my, rd)
    if es is None:
        return None
    if tu:
        use = tu
    elif du is None:
        return None
    else:
        use = du if reg in ("World", "World Less China") else du + (ex or 0)
    return es / use if use else None


def changes_table(df, rd, prev, my, regions):
    rows = []
    for reg in regions:
        u = df[(df.reg == reg) & (df.attr == "Production") & (df.rd == rd)].unit
        r = {"region": reg, "unit": u.iloc[0] if len(u) else ""}
        any_ = False
        for a in ATTRS:
            now = get(df, reg, a, my, rd); was = get(df, reg, a, my, prev) if prev is not None else None
            r[a] = {"now": now, "prev": was, "chg": (round(now - was, 3) if now is not None and was is not None else None)}
            any_ = any_ or now is not None
        s_now = su(df, reg, my, rd); s_prev = su(df, reg, my, prev) if prev is not None else None
        r["S/U"] = {"now": s_now, "prev": s_prev, "chg": (s_now - s_prev if s_now is not None and s_prev is not None else None)}
        if any_:
            rows.append(r)
    return rows


_RELS = {}


def month_history(df, reg, attr, rd):
    k = (id(df), reg)
    if k not in _RELS:
        _RELS[k] = sorted(df[df.reg == reg].rd.unique())
    rels = _RELS[k]; hist = []
    if rd not in rels:
        return None
    for t in rels:
        if t.month != rd.month or t >= rd:
            continue
        i = rels.index(t)
        if i == 0:
            continue
        my = focus_my(df, t); a, b = get(df, reg, attr, my, t), get(df, reg, attr, my, rels[i - 1])
        if a is not None and b is not None:
            hist.append((t.year, a - b))
    i = rels.index(rd); my = focus_my(df, rd)
    a, b = get(df, reg, attr, my, rd), (get(df, reg, attr, my, rels[i - 1]) if i > 0 else None)
    if a is None or b is None or len(hist) < 4:
        return None
    ch = a - b; h = np.array([x[1] for x in hist])
    M = rd.strftime('%B'); n = len(h); pct = float((np.abs(h) < abs(ch)).mean() * 100)
    if abs(ch) < 1e-9:
        k_ = int((np.abs(h) < 1e-9).sum())
        note = f"unchanged ({k_} of {n} past {M} reports also left it unchanged)" if k_ else f"unchanged, unusually — every past {M} report since {hist[0][0]} revised it"
    elif pct < 40:
        note = f"small by {M} standards"
    else:
        same = [y for y, v in hist if (v >= ch if ch > 0 else v <= ch)]
        word = "increase" if ch > 0 else "cut"
        if not same:
            note = f"largest {M} {word} in {n + 1} years"
        elif pct >= 60 and max(same) < rd.year - 2:
            note = f"largest {M} {word} since {max(same)}"
        else:
            note = f"{len(same)} of {n} past {M} reports {'raised' if ch > 0 else 'cut'} it by as much"
    return {"region": reg, "attr": attr, "chg": round(ch, 3), "now": a, "avg_abs": round(float(np.mean(np.abs(h))), 3),
            "up_share": round(float((h > 0).mean()), 2), "pct_abs": round(pct, 0), "n": n, "since": min(x[0] for x in hist), "note": note}


def nd(v):
    return 0 if v is not None and abs(v) >= 100 else 2 if v is not None and abs(v) < 10 else 1


def fmt(v, d=None, sign=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    d = nd(v) if d is None else d
    if sign and abs(v) < 1e-9:
        return "unch"
    return f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"


def balance(df, rd, prev, regions, rows):
    """{region: [{attr, unit, vals: {my: [now, prev]}}]} for the three latest marketing years of this report."""
    mys = sorted(df[(df.rd == rd)].my.unique())[-3:]
    out = {}
    for reg in regions:
        lst = []
        for a in rows:
            vals = {my: [get(df, reg, a, my, rd), get(df, reg, a, my, prev) if prev is not None else None] for my in mys}
            if any(v[0] is not None for v in vals.values()):
                u = df[(df.reg == reg) & (df.attr == a) & (df.rd == rd)].unit
                lst.append({"attr": a, "unit": u.iloc[0] if len(u) else "", "vals": vals})
        if lst:
            s = {my: [su(df, reg, my, rd), su(df, reg, my, prev) if prev is not None else None] for my in mys}
            lst.append({"attr": "Stocks/use", "unit": "%", "vals": {k: [None if x is None else round(x * 100, 1) for x in v] for k, v in s.items()}})
            out[reg] = lst
    return {"mys": mys, "regions": out}


# ─────────────────────────── cross-checks ───────────────────────────
def esr_frame(key):
    cfg = next(c for c in EB.COMMS if c["key"] == key)
    e = EB.esr(cfg["dirs"])
    if e is None or e.empty:
        return None, cfg
    labels = EB.my_label(e, cfg["start"])
    tot = e.groupby(["marketYear", "weekEndingDate"])[["commit", "accumulatedExports"]].sum().reset_index()
    tot["my"] = tot.marketYear.map(lambda y: labels[y][1])
    tot["wk"] = [(d - pd.Timestamp(year=labels[y][0], month=cfg["start"], day=1)).days // 7 for y, d in zip(tot.marketYear, tot.weekEndingDate)]
    return tot, cfg


def checks(key, cfg, df, rd, prev, my, ctx, cut, pcut=None):
    out = {"asof": cut.strftime("%Y-%m-%d")}
    y0 = int(my[:4])
    # crop ratings and the desk's condition -> yield model (current season)
    cd = ctx.get("cond", {}).get(cfg.get("cond") or "", None)
    usd_y = get(df, "United States", "Yield", my, rd)
    if cd and usd_y:
        ge = cd.get("ge", {}).get(str(y0))
        wk_cut = cut.isocalendar()[1]
        if ge and cut.year == y0:
            s = [g for w, g in ge if w <= wk_cut]
            if s:
                ly = [g for w, g in cd["ge"].get(str(y0 - 1), []) if w <= wk_cut]
                sp = [g for w, g in ge if pcut is not None and w <= pcut.isocalendar()[1]]
                out["conditions"] = {"GE": s[-1], "GE_last_year": ly[-1] if ly else None, "GE_prev": sp[-1] if sp else None, "week": int(min(wk_cut, ge[-1][0]))}
        m = cd.get("model", {})
        if m.get("year") == y0 and m.get("estimate") and cut >= pd.Timestamp(year=y0, month=8, day=1):
            out["implied"] = {"yield": m["estimate"], "trend": m.get("trend"), "usda": usd_y, "mae": (m.get("test") or {}).get("mae_model"),
                              "gap": round(usd_y - m["estimate"], 1)}
    # export sales pace vs USDA at the cut
    tot, ecfg = ctx.get("esr", {}).get(key, (None, None))
    target = get(df, "United States", "Exports", my, rd)
    if tot is not None and target:
        cur = tot[(tot.my == my) & (tot.weekEndingDate <= cut)]
        if len(cur):
            L = cur.sort_values("weekEndingDate").iloc[-1]; wk = int(L.wk)
            hist = []
            for m_, g in tot[tot.my < my].groupby("my"):
                fin = float(g.accumulatedExports.max()); at = g[g.wk <= wk]
                wf = df[(df.reg == "United States") & (df.attr == "Exports") & (df.my == m_)].sort_values("rd").val
                if fin > 0 and len(at) and len(wf):
                    hist.append((m_, float(at.commit.iloc[-1]) / fin, fin / float(wf.iloc[-1])))
            hist = hist[-5:]
            if hist:
                ratio = float(np.median([h[2] for h in hist])); norm = float(np.mean([h[1] for h in hist]))
                pace = float(L.commit) / (target * ratio)
                out["export_sales"] = {"week": L.weekEndingDate.strftime("%Y-%m-%d"), "wk": wk + 1, "commit_kt": round(float(L.commit) / 1e3, 1),
                                       "pace": round(pace, 3), "pace_5y": round(norm, 3), "usda": target,
                                       "usda_prev": get(df, "United States", "Exports", my, prev) if prev is not None else None,
                                       "implied": round(target * pace / norm) if norm > 0 else None}
    # Brazil / Argentina
    sa = ctx.get("sa", {}); sac = cfg.get("sa", {})
    if sac.get("conab") and "conab" in sa:
        c = sa["conab"]; c = c[c["product"] == sac["conab"]].copy()
        if len(c):
            c["season"] = c.ano_agricola.astype(str).str.strip()
            by0 = y0; br_my = my                                   # USDA Brazil 2025/26 = CONAB 2025/26 for the crop harvested early in y0+1
            cs = c[c.season == br_my].sort_values("survey")
            if cs.empty:                                 # new season not surveyed yet: compare the crop just harvested
                by0 = y0 - 1; br_my = f"{by0}/{str(by0 + 1)[-2:]}"
                cs = c[c.season == br_my].sort_values("survey")
            # CONAB releases survey k of a season around the 12th of month (Oct + k - 1) of its first year
            if len(cs):
                cs = cs.assign(date=[pd.Timestamp(year=by0, month=10, day=12) + pd.DateOffset(months=int(k) - 1) for k in cs.survey])
                cs = cs[cs.date <= cut]
            usda_br = get(df, "Brazil", "Production", br_my, rd)
            if len(cs) and usda_br:
                last = cs.iloc[-1]
                out["conab"] = {"season": br_my, "survey": int(last.survey), "conab_mmt": round(float(last.producao_mil_t) / 1e3, 1), "usda_mmt": usda_br,
                                "gap": round(float(last.producao_mil_t) / 1e3 - usda_br, 1),
                                "first_mmt": round(float(cs.producao_mil_t.iloc[0]) / 1e3, 1)}
    if sac.get("comex") and "comex" in sa:
        x = sa["comex"]; x = x[x.commodity == sac["comex"]]
        x = x.assign(date=pd.to_datetime(dict(year=x.year, month=x.month, day=1)))
        x = x[x.date < (cut - pd.offsets.MonthBegin(1))]
        if len(x):
            lastd = x.date.max(); yr, mo = lastd.year, lastd.month
            ytd = float(x[(x.year == yr) & (x.month <= mo)].kt.sum()); ly = float(x[(x.year == yr - 1) & (x.month <= mo)].kt.sum())
            out["brazil_exports"] = {"through": lastd.strftime("%b %Y"), "ytd_mmt": round(ytd / 1e3, 2), "ly_mmt": round(ly / 1e3, 2),
                                     "yoy": round(ytd / ly - 1, 3) if ly else None,
                                     "usda_br_exp": get(df, "Brazil", "Exports", my, rd), "usda_br_exp_prev": get(df, "Brazil", "Exports", my, prev) if prev is not None else None}
    # positioning and price
    c = ctx.get("cot")
    if c is not None:
        s = c[c.index <= cut].dropna(subset=["mm_n"])
        if len(s):
            r = s.iloc[-1]
            out["cot"] = {"date": s.index[-1].strftime("%Y-%m-%d"), "mm_net": float(r.mm_n), "idx": None if pd.isna(r.idx) else round(float(r.idx), 0),
                          "pct_oi": round(float(r.mm_n / r.oi * 100), 1) if r.oi else None}
    px = ctx.get("px")
    if px is not None:
        s = px[px.index <= cut]
        if len(s) > 22:
            out["price"] = {"date": s.index[-1].strftime("%Y-%m-%d"), "close": float(s.iloc[-1]), "chg_1m": float(s.iloc[-1] / s.iloc[-22] - 1)}
    return out


# ─────────────────────────── outlook and text ───────────────────────────
def outlook(cfg, ch, rep, now):
    F = []
    def add(name, tilt, text):
        F.append({"factor": name, "tilt": tilt, "text": text})
    U = cfg["unit"]
    us = next((r for r in ch if r["region"] == "United States"), None)
    wxc = next((r for r in ch if r["region"] == "World Less China"), None)
    if us and us["Ending Stocks"]["chg"] is not None and us["Ending Stocks"]["now"]:
        c = us["Ending Stocks"]["chg"]; rel = c / us["Ending Stocks"]["now"]
        add("US balance sheet", "bearish" if rel > 0.02 else "bullish" if rel < -0.02 else "neutral",
            f"US ending stocks {fmt(us['Ending Stocks']['now'])} {U} ({fmt(c, sign=True)}), stocks/use {fmt((us['S/U']['now'] or 0) * 100, 1)}%"
            + (f" vs {fmt(us['S/U']['prev'] * 100, 1)}% last month." if us['S/U']['prev'] else "."))
    if wxc and wxc["Ending Stocks"]["chg"] is not None:
        c = wxc["Ending Stocks"]["chg"]
        add("World ex-China stocks", "bearish" if c > 1 else "bullish" if c < -1 else "neutral",
            f"World ex-China ending stocks {fmt(wxc['Ending Stocks']['now'])} MMT ({fmt(c, sign=True)}); stocks/use {fmt((wxc['S/U']['now'] or 0) * 100, 1)}%.")
    im = now.get("implied")
    if im and im.get("mae"):
        g = im["gap"]; tilt = "bullish" if g > 0.5 * im["mae"] else "bearish" if g < -0.5 * im["mae"] else "neutral"
        add("US yield vs ratings", tilt, f"Crop ratings point to a {im['yield']:.1f} bu/acre yield (model error ±{im['mae']:.1f}) vs USDA {im['usda']:.1f} — "
            + ("USDA looks generous; downside risk to its crop." if tilt == "bullish" else "USDA looks conservative; upside risk to its crop." if tilt == "bearish" else "USDA is in line with ratings."))
    ex = now.get("export_sales")
    if ex and ex.get("pace_5y"):
        d = ex["pace"] / ex["pace_5y"] - 1
        add("US export sales", "bullish" if d > 0.08 else "bearish" if d < -0.08 else "neutral",
            f"Week ending {ex['week']}: commitments " + (f"{ex['commit_kt'] / 1e3:,.1f} MMT" if ex['commit_kt'] >= 1000 else f"{ex['commit_kt'] * 1e3:,.0f} MT") + f" = {ex['pace']*100:.0f}% of USDA's {fmt(ex['usda'])} {U} target vs a 5-yr norm of "
            f"{ex['pace_5y']*100:.0f}% at this point — " + ("ahead of pace, supports a raise." if d > 0.08 else "behind pace, risk of a cut." if d < -0.08 else "on pace.")
            + (f" Pace implies about {fmt(ex['implied'])} {U}." if ex.get("implied") else ""))
    cb = now.get("conab")
    if cb:
        g = cb["gap"]; tilt = "bearish" if g > 2 else "bullish" if g < -2 else "neutral"
        add("Brazil crop (CONAB vs USDA)", tilt, f"CONAB survey {cb['survey']} puts Brazil's {cb['season']} crop at {cb['conab_mmt']:.1f} MMT vs USDA {cb['usda_mmt']:.1f} — "
            + ("CONAB above USDA, room for USDA to raise Brazil." if tilt == "bearish" else "CONAB below USDA, room for USDA to cut Brazil." if tilt == "bullish" else "the two agree."))
    bx = now.get("brazil_exports")
    if bx and bx.get("yoy") is not None:
        add("Brazil exports", "bearish" if bx["yoy"] > 0.08 else "bullish" if bx["yoy"] < -0.08 else "neutral",
            f"Brazil shipped {bx['ytd_mmt']:.1f} MMT Jan–{bx['through']} ({bx['yoy']*100:+.0f}% y/y) — "
            + ("strong competition for US exports." if bx["yoy"] > 0.08 else "less competition for US exports." if bx["yoy"] < -0.08 else "steady."))
    c = now.get("cot")
    if c and c.get("idx") is not None:
        i_ = c["idx"]
        add("Fund positioning", "bearish" if i_ > 80 else "bullish" if i_ < 20 else "neutral",
            f"COT {c['date']}: managed money net {c['mm_net']/1000:+.0f}k ({c['pct_oi']:+.1f}% of OI, 3-yr index {i_:.0f}) — "
            + ("crowded long, liquidation risk." if i_ > 80 else "crowded short, short-covering fuel." if i_ < 20 else "not at an extreme."))
    score = sum(1 if f["tilt"] == "bullish" else -1 if f["tilt"] == "bearish" else 0 for f in F)
    label = "bullish" if score >= 2 else "modestly bullish" if score == 1 else "bearish" if score <= -2 else "modestly bearish" if score == -1 else "neutral"
    return F, score, label


def text(cfg, df, rd, prev, my, ch, hist, rep, now, F, label, is_latest):
    U = cfg["unit"]; T = []
    g = lambda r, a, k: ((r or {}).get(a) or {}).get(k)
    us = next((r for r in ch if r["region"] == "United States"), None); wl = next((r for r in ch if r["region"] == "World"), None)
    wxc = next((r for r in ch if r["region"] == "World Less China"), None)
    yld, yp = get(df, "United States", "Yield", my, rd), get(df, "United States", "Yield", my, prev) if prev is not None else None
    head = (f"The {rd:%B %Y} WASDE puts {my} US production at {fmt(g(us,'Production','now'))} {U} ({fmt(g(us,'Production','chg'), sign=True)})"
            + (f" on a {yld:.1f} bu/acre yield ({yld - yp:+.1f})" if yld and yp else "")
            + f", exports {fmt(g(us,'Exports','now'))} ({fmt(g(us,'Exports','chg'), sign=True)}) and ending stocks {fmt(g(us,'Ending Stocks','now'))} "
            f"({fmt(g(us,'Ending Stocks','chg'), sign=True)}); stocks/use {fmt((g(us,'S/U','now') or 0) * 100, 1)}%.")
    if wl:
        head += (f" World ending stocks {fmt(g(wl,'Ending Stocks','now'))} MMT ({fmt(g(wl,'Ending Stocks','chg'), sign=True)})"
                 + (f", world ex-China {fmt(g(wxc,'Ending Stocks','now'))} ({fmt(g(wxc,'Ending Stocks','chg'), sign=True)})" if wxc else "") + ".")
    T.append({"h": "Headline", "t": head})
    # US demand lines
    lines = []
    for a in ("Feed and Residual", "Food, Seed & Industrial", "Ethanol for Fuel", "Crush", "Biofuel", "Food", "Domestic Use"):
        n_, p_ = get(df, "United States", a, my, rd), get(df, "United States", a, my, prev) if prev is not None else None
        if n_ is not None and p_ is not None and abs(n_ - p_) > 1e-9:
            lines.append(f"{a.lower()} {fmt(n_)} ({fmt(n_ - p_, sign=True)})")
    pr, pp = get(df, "United States", "Avg. Farm Price", my, rd), get(df, "United States", "Avg. Farm Price", my, prev) if prev is not None else None
    if pr is not None:
        lines.append(f"season-average farm price ${pr:,.2f}" + (f" ({pr - pp:+.2f})" if pp is not None else ""))
    if lines:
        T.append({"h": "US use and price", "t": "Revisions: " + "; ".join(lines) + "."})
    movers = sorted([r for r in ch if r["region"] not in ("World", "World Less China", "United States")],
                    key=lambda r: -max(abs((r[a] or {}).get("chg") or 0) for a in ATTRS))[:5]
    mv = []
    for r in movers:
        parts = [f"{a.lower()} {fmt(r[a]['chg'], sign=True)}" for a in ATTRS if r[a]["chg"] not in (None, 0)]
        if parts:
            mv.append(f"{r['region']} ({', '.join(parts)})")
    if mv:
        T.append({"h": "Biggest country changes", "t": "; ".join(mv) + " (MMT)."})
    hs = [h for h in hist if h and abs(h["chg"]) > 1e-9]
    if hs:
        T.append({"h": f"vs past {rd:%B} reports", "t": " ".join(
            f"{h['region']} {h['attr'].lower()} {fmt(h['chg'], sign=True)} — {h['note']} (avg {rd:%B} move ±{fmt(h['avg_abs'])} since {h['since']})." for h in hs[:6])})
    c = rep.get("conditions"); im = rep.get("implied")
    if c or im:
        t = ""
        if c:
            t += (f"US {'winter wheat' if cfg.get('cond') == 'wheat' else 'crop'} rated {c['GE']:.0f}% good/excellent (week {c['week']})" + (f", vs {c['GE_last_year']:.0f}% a year ago" if c.get("GE_last_year") is not None else "") + ". ")
        if im:
            t += (f"The desk's ratings model points to {im['yield']:.1f} bu/acre (trend {fmt(im.get('trend'), 1)}; average miss ±{fmt(im.get('mae'), 1)}) vs USDA's {im['usda']:.1f}. ")
            if yld and yp and abs(yld - yp) >= 0.1:
                agree = (yld - yp > 0) == (im["yield"] > yp)
                t += (f"USDA's {'increase' if yld > yp else 'cut'} is in the direction ratings point." if agree else
                      f"**USDA {'raised' if yld > yp else 'cut'} yield although ratings point the other way — we disagree with the direction.**")
        T.append({"h": "Crop vs conditions", "t": t})
    ex = rep.get("export_sales")
    if ex and ex.get("pace_5y") and ex.get("usda_prev") is not None:
        d = ex["pace"] / ex["pace_5y"] - 1; dx = ex["usda"] - ex["usda_prev"]
        t = (f"At the report, commitments were {ex['pace']*100:.0f}% of the export target vs a 5-yr norm of {ex['pace_5y']*100:.0f}% (week {ex['wk']}); USDA "
             + (f"{'raised' if dx > 0 else 'cut'} exports {abs(dx):,.0f} to {ex['usda']:,.0f} {U}." if abs(dx) > 1e-9 else f"left exports at {ex['usda']:,.0f} {U}."))
        if (d < -0.08 and dx > 0) or (d > 0.08 and dx < 0):
            t += f" **Sales pace argued for a {'cut' if d < 0 else 'raise'} — we disagree with USDA here.**"
        T.append({"h": "Export target vs sales pace", "t": t})
    sa_t = [f["text"] for f in F if f["factor"] in ("Brazil crop (CONAB vs USDA)", "Brazil exports")]
    if sa_t:
        T.append({"h": "South America", "t": " ".join(sa_t)})
    S = []
    cn = now.get("conditions")
    if cn and c and cn["week"] != c["week"]:
        S.append(f"Ratings now {cn['GE']:.0f}% G/E (week {cn['week']}; {cn['GE'] - c['GE']:+.0f} pts since the report).")
    for f in F:
        if f["factor"] in ("US export sales", "US yield vs ratings"):
            S.append(f["text"])
    if S:
        T.append({"h": "Latest data (drives the outlook)" if is_latest else "Data up to the next report (drives the outlook)", "t": " ".join(S)})
    pos = [f["text"] for f in F if f["factor"] == "Fund positioning"]
    if pos:
        T.append({"h": "Positioning", "t": " ".join(pos)})
    bull = [f["factor"] for f in F if f["tilt"] == "bullish"]; bear = [f["factor"] for f in F if f["tilt"] == "bearish"]
    px = now.get("price")
    T.append({"h": "Price outlook", "t": f"**{label.capitalize()}.** " + (f"Supportive: {', '.join(bull)}. " if bull else "") + (f"Weighing: {', '.join(bear)}. " if bear else "")
              + (f"Front month {px['close']:,.2f} on {px['date']} ({px['chg_1m']*100:+.1f}% over the past month). " if px else "")
              + f"Uses crop ratings, export sales, CONAB, Brazil trade and COT data available through {now['asof']}."})
    return T


def revisions(df, cfg):
    """Value of key estimates at each release, for the current and previous 5 marketing years."""
    out = {}
    keys = [("United States", a) for a in ("Production", "Yield", "Exports", "Ending Stocks", "Crush", "Feed and Residual", "Biofuel", "Domestic Use")] + cfg["hist"]
    seen = set()
    for reg, a in keys:
        if (reg, a) in seen:
            continue
        seen.add((reg, a))
        x = df[(df.reg == reg) & (df.attr == a)]
        if x.empty:
            continue
        mys = sorted(x.my.unique())[-6:]
        ser = {my: [[t.strftime("%Y-%m"), v] for t, v in x[x.my == my].sort_values("rd")[["rd", "val"]].itertuples(index=False)] for my in mys}
        out[f"{reg}|{a}"] = {"region": reg, "attr": a, "unit": x.unit.iloc[-1], "mys": ser}
    return out


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctx0 = {"cond": cond_data(), "sa": south_america(), "esr": {}}
    for k in COMS:
        try:
            ctx0["esr"][k] = esr_frame(COMS[k]["esr"])
        except Exception as e:
            print("esr", k, e)
    frames = {k: frame(c, k) for k, c in COMS.items()}
    base = frames["corn"]
    rels = sorted(base[base.reg == "United States"].rd.unique())[-N_RELEASES:]
    reports = {}
    revs = {}
    for k, cfg in COMS.items():
        df = frames[k]; ctx = dict(ctx0); ctx["cot"] = cot(cfg["sym"]); pxd = EB.prices(cfg["sym"]); ctx["px"] = pxd.close if pxd is not None else None
        ctx["esr"] = ctx0["esr"]
        all_rels = sorted(df[df.reg == "United States"].rd.unique())
        revs[k] = revisions(df, cfg)
        for rd in rels:
            if rd not in all_rels:
                continue
            i = all_rels.index(rd); prev = all_rels[i - 1] if i > 0 else None
            my = focus_my(df, rd)
            ch = changes_table(df, rd, prev, my, cfg["regions"])
            hist = [h for h in (month_history(df, r, a, rd) for r, a in cfg["hist"]) if h]
            nxt = all_rels[i + 1] if i + 1 < len(all_rels) else None
            rcut = rd + pd.Timedelta(days=10)
            ncut = (nxt + pd.Timedelta(days=9)) if nxt is not None else pd.Timestamp.now().normalize()
            rep = checks(k, cfg, df, rd, prev, my, ctx, rcut)
            now = checks(k, cfg, df, rd, prev, my, ctx, ncut, pcut=rcut)
            F, score, label = outlook(cfg, ch, rep, now)
            bs = balance(df, rd, prev, cfg["regions"], US_ROWS)
            reports.setdefault(rd, {})[k] = {"name": cfg["name"], "my": my, "unit": cfg["unit"], "wunit": cfg.get("wunit"), "changes": ch, "history": hist,
                                            "checks": rep, "latest": now, "factors": F, "score": score, "outlook": label, "balance": bs,
                                            "brief": text(cfg, df, rd, prev, my, ch, hist, rep, now, F, label, nxt is None)}
    index = []
    for rd in sorted(reports):
        key = rd.strftime("%Y-%m")
        (OUT / f"{key}.json").write_text(json.dumps(clean({"report": key, "label": rd.strftime("%B %Y"), "commodities": reports[rd]}), separators=(",", ":"), allow_nan=False))
        index.append({"report": key, "label": rd.strftime("%B %Y"), "outlooks": {k: v["outlook"] for k, v in reports[rd].items()}})
    (OUT / "revisions.json").write_text(json.dumps(clean(revs), separators=(",", ":"), allow_nan=False))
    (OUT / "index.json").write_text(json.dumps({"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "reports": index[::-1]}))
    last = reports[max(reports)]
    print("reports:", len(index), "| latest:", max(reports).strftime("%B %Y"))
    for k, v in last.items():
        print(f"\n===== {v['name']} {v['my']}: {v['outlook']}")
        for b in v["brief"]:
            print(f"[{b['h']}] {b['t']}")


if __name__ == "__main__":
    main()
