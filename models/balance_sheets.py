"""US balance sheets with desk scenarios: USDA's last three seasons and current forecast, plus base / bearish / bullish
ending stocks built from the desk's own production and export projections. Other lines (beginning stocks, imports,
domestic use) stay at USDA's current numbers.

Production:  cotton  -> cotton-crop-progress crop model (us_all central, 68% band)
             corn, soybeans -> USDA yield and the desk crop-condition yield model, weighted by the inverse of each one's squared
                               typical miss of the final (USDA's for the month of the latest report), x USDA harvested area
             wheat, HRW -> harvest complete, USDA production in every scenario
             meal, oil -> made from the soybean crush, USDA production in every scenario
Exports:     USDA and the desk export-sales projection (data/grains/derived/esr_brief.json), the projection corrected for its
             walk-forward bias at this week and the two weighted by how close each came to final exports in past seasons
Stocks:      export and production changes pass into ending stocks at the rates seen from USDA's same-month estimates to the
             final (pass_through); the rest goes to domestic use
Output:      data/derived/balance_sheets.json
"""
import json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import grains_esr_brief as G  # noqa: E402  (WASDE loader shared with the export brief)

OUT = ROOT / "data" / "derived" / "balance_sheets.json"
CROP_URL = "https://bmr-com.github.io/cotton-crop-progress/data/crop_projection.json"

# key -> WASDE file, unit, balance-sheet lines (label, WASDE attribute or None for computed), decimals
SPEC = {
    "cotton": ("Cotton.json", "m 480-lb bales", 2, [("Planted area (m ac)", "Planted"), ("Harvested area (m ac)", "Harvested"), ("Yield (lb/ac)", "Yield per Harvested Acre"),
               ("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
               ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Unaccounted", "Unaccounted"), ("Ending stocks", "Ending Stocks")]),
    "corn": ("Corn.json", "m bu", 0, [("Planted area (m ac)", "Area Planted"), ("Harvested area (m ac)", "Area Harvested"), ("Yield (bu/ac)", "Yield per Harvested Acre"),
             ("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
             ("Feed & residual", "Feed and Residual"), ("Food, seed & industrial", "Food, Seed & Industrial"), ("  of which ethanol", "Ethanol for Fuel"),
             ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
    "soybeans": ("Oilseed,_Soybean.json", "m bu", 0, [("Planted area (m ac)", "Area Planted"), ("Harvested area (m ac)", "Area Harvested"), ("Yield (bu/ac)", "Yield per Harvested Acre"),
                 ("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
                 ("Crush", "Crushings"), ("Seed & residual", None), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
    "meal": ("Meal,_Soybean.json", "k short tons", 0, [("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
             ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
    "oil": ("Oil,_Soybean.json", "m lb", 0, [("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
            ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
    "wheat": ("Wheat.json", "m bu", 0, [("Planted area (m ac)", "Area Planted"), ("Harvested area (m ac)", "Area Harvested"), ("Yield (bu/ac)", "Yield per Harvested Acre"),
              ("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
              ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
    "kc": ("Hard_Red_Winter.json", "m bu", 0, [("Beginning stocks", "Beginning Stocks"), ("Production", "Production"), ("Imports", "Imports"), ("Total supply", None),
           ("Domestic use", "Domestic Use"), ("Exports", "Exports"), ("Total use", None), ("Ending stocks", "Ending Stocks")]),
}
NAMES = {"cotton": "Cotton", "corn": "Corn", "soybeans": "Soybeans", "meal": "Soybean meal", "oil": "Soybean oil", "wheat": "All wheat", "kc": "HRW wheat"}
PRICE = {"cotton": ("Avg. Farm Price", "¢/lb"), "corn": ("Avg. Farm Price", "$/bu"), "soybeans": ("Avg. Farm Price", "$/bu"), "wheat": ("Avg. Farm Price", "$/bu"),
         "meal": ("Avg. Farm Price", "$/short ton"), "oil": ("Avg. Farm Price", "¢/lb")}
ALT = {"Ending Stocks": ["Ending Stocks, Total"], "Avg. Farm Price": ["Avg. farm price"], "Yield per Harvested Acre": ["Yield per harvested acre"], "Feed and Residual": ["Feed and residual"],
       "Food, Seed & Industrial": ["Food, seed & industrial"], "Ethanol for Fuel": ["Ethanol for fuel", "Ethanol & by-products"]}


VARS = {   # shown on the public page (variables only; rules live in the private research notes)
    "cotton": ["BMR-Com crop model (crop ratings, drought, ginnings, classing by office, FSA acreage)", "USDA crop estimate", "Texas abandonment (and its largest post-October rise on record)", "India import demand by duty status and origin (Cotton > India)",
               "weekly export sales (commitments, shipments, net sales)", "USDA export forecast", "price response of exports to crop size",
               "US share of world trade", "rival exporters' stocks (Brazil, Australia, Africa, Central Asia)", "pipeline minimum stocks", "USDA October-to-final crop revision history", "export-sales projection error at this week of the season"],
    "corn": ["desk crop-condition yield model", "USDA yield and harvested area", "weekly export sales", "USDA export forecast", "price response of exports to crop size",
             "US share of world trade", "rival exporters' stocks", "pipeline minimum stocks", "USDA October-to-final crop revision history"],
    "soybeans": ["desk crop-condition yield model", "USDA yield and harvested area", "weekly export sales", "USDA export forecast", "price response of exports to crop size",
                 "US share of world trade", "rival exporters' stocks", "pipeline minimum stocks", "USDA October-to-final crop revision history"],
    "wheat": ["USDA production (harvest complete)", "weekly export sales", "USDA export forecast", "US share of world trade", "rival exporters' stocks"],
    "kc": ["USDA production (harvest complete)", "weekly export sales (HRW)", "USDA export forecast"],
}


def latest(w, attr, my):
    for a in [attr] + ALT.get(attr, []):
        v, rd = G.w_latest(w, "United States", a, my)
        if v is not None:
            return v, rd
    return None, None


def crop_cotton():
    try:
        import requests
        return requests.get(CROP_URL, timeout=60).json()
    except Exception:
        p = ROOT.parent / "bmr-com" / "cotton-crop-progress" / "docs" / "data" / "crop_projection.json"
        return json.loads(p.read_text()) if p.exists() else None


def vintage_date(rd_cur, cur, my):
    """The date in season `my` that matches the latest report `rd_cur` of season `cur` (same report month, same point of the season)."""
    return rd_cur - pd.DateOffset(years=int(cur[:4]) - int(my[:4]))


W_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def export_test(cfg, wk, rd_cur=None, cur=None):
    """Walk-forward test of the desk export projection at this week of the season against USDA's final, past seasons.
    For each test season the projection is rebuilt from earlier seasons only, with the method the export brief uses for this
    commodity. Returns the projection's average % miss (mape_desk), its average signed % error (bias: how far it ran high or
    low), USDA's average % miss with the forecast it had at the same point of each season (same report month as the latest
    report), and the weight on USDA (w_usda, from W_GRID) that would have come closest to final exports when combined with the
    bias-corrected projection. Bias for a test season uses only the seasons before it. Near-ties (within 0.5 points of the best) go to USDA; originally: ties within 0.3 points of the best go
    to the weight nearest 0.5; fewer than 8 test seasons -> 0.5."""
    try:
        e = G.esr(cfg["dirs"]); w = G.wasde(cfg["wasde"], cfg["key"]); labels = G.my_label(e, cfg["start"])
        tot = e.groupby(["marketYear", "weekEndingDate"])[["commit", "accumulatedExports", "currentMYNetSales"]].sum().reset_index()
        tot["wk"] = tot.apply(lambda r: (r.weekEndingDate - pd.Timestamp(year=labels[r.marketYear][0], month=cfg["start"], day=1)).days // 7, axis=1)
        cy = int(tot.marketYear.max()); rows = []
        for y in sorted(tot.marketYear.unique()):
            if y >= cy:
                continue
            g = tot[tot.marketYear == y].sort_values("wk"); a = g[g.wk <= wk - 1]
            my = labels[y][1]
            wf, _ = G.w_latest(w, "United States", "Exports", my)
            if a.empty or not wf:
                continue
            uv = G.w_latest(w, "United States", "Exports", my, vintage_date(rd_cur, cur, my))[0] if rd_cur is not None and cur else None
            rows.append(dict(my=my, commit=a.commit.iloc[-1], net4=g[(g.wk > wk - 5) & (g.wk <= wk - 1)].currentMYNetSales.mean(), fin=g.accumulatedExports.iloc[-1],
                             usda=wf, usda_v=uv))
        P = pd.DataFrame(rows); P["add"] = P.fin - P.commit; P["pct"] = P.commit / P.fin; P["ratio"] = P.fin / P.usda
        T = []
        for i in range(6, len(P)):
            tr, x = P.iloc[:i], P.iloc[i]; t5 = tr.tail(5); r = t5.ratio.median()
            ad = x.commit + t5["add"].median(); ly = x.commit + tr["add"].iloc[-1]
            if cfg.get("share_only"):
                v = [x.commit / t5.pct.mean()]
            elif cfg.get("blend"):
                v = [ad, ly, x.commit + np.average(tr["add"].tail(3), weights=[1, 2, 3])]
                t10 = tr.tail(10); X = np.c_[np.ones(len(t10)), t10.net4, t10.commit]; bb = np.linalg.lstsq(X, t10["add"], rcond=None)[0]
                v.append(x.commit + bb @ [1, x.net4, x.commit])
            else:
                v = [x.commit / t5.pct.mean(), ad, ly]
            desk = float(np.median(v) / r)
            T.append({"my": x.my, "desk": desk, "fin": float(x.usda), "usda": float(x.usda_v) if pd.notna(x.usda_v) and x.usda_v else None,
                      "err": desk / x.usda - 1})
        if not T:
            return None
        for j, t in enumerate(T):            # walk-forward bias: mean signed error of the earlier test seasons (none before two)
            prior = [u["err"] for u in T[:j]]
            t["bias"] = float(np.mean(prior)) if len(prior) >= 2 else 0.0
            t["adj"] = t["desk"] / (1 + t["bias"])
        out = {"n_desk": len(T), "mape_desk": round(100 * float(np.mean([abs(t["err"]) for t in T])), 1),
               "bias": float(np.mean([t["err"] for t in T])) if len(T) >= 2 else 0.0}
        V = [t for t in T if t["usda"]]
        out["n"] = len(V)
        if V:
            ape = lambda f: 100 * float(np.mean([abs(f(t) / t["fin"] - 1) for t in V]))
            out["mape_usda"] = round(ape(lambda t: t["usda"]), 1)
            out["mape_desk_same"] = round(ape(lambda t: t["desk"]), 1)       # same seasons as USDA's
            out["mape_desk_adj"] = round(ape(lambda t: t["adj"]), 1)
            if out["mape_desk_adj"] >= out["mape_desk_same"]:            # the correction did not help in past seasons: do not use it
                for t in T:
                    t["adj"] = t["desk"]
                out["bias"] = 0.0; out["bias_used"] = False
            grid = {wu: ape(lambda t, wu=wu: wu * t["usda"] + (1 - wu) * t["adj"]) for wu in W_GRID}
            out["grid"] = {f"{k:.2f}": round(v, 2) for k, v in grid.items()}
            if len(V) >= 8:
                best = min(grid.values())
                near = [k for k, v in grid.items() if v <= best + 0.5]      # ~10 seasons: differences this small are noise
                out["w_usda"] = max(near)            # near-ties go to USDA: the projection has to earn its weight
            else:
                out["w_usda"] = 0.5; out["fallback"] = f"only {len(V)} past seasons to test"
            out["mape_blend"] = round(grid[out["w_usda"]], 1)
            out["years"] = [V[0]["my"], V[-1]["my"]]
        else:
            out.update({"w_usda": 0.5, "fallback": "no USDA forecasts from past seasons to test"})
        return out
    except Exception as ex:
        print("export test skipped:", cfg.get("key"), repr(ex)[:120])
        return None


def export_miss(cfg, wk):
    """Average % miss of the desk export projection at this week of the season vs USDA's final, past seasons (out of sample)."""
    t = export_test(cfg, wk)
    return t["mape_desk"] if t else None


def pass_through(w, cur, rd_cur):
    """How much of a change in exports and in production has ended up in US ending stocks: regression, across completed
    seasons, of (final - estimate) ending stocks on (final - estimate) exports, production and beginning stocks, no intercept;
    estimate = USDA's report in the same month as the latest one (new-crop season). The rest of a change is absorbed by
    domestic use (feed and residual for corn). Magnitudes held to 0.2-1.0 with the expected sign (exports lower stocks,
    production raises them); 1.0 (one for one) with fewer than 10 seasons."""
    import re
    us = w[w.reg == "United States"]
    def at(attr, my, upto=None):
        for a in [attr] + ALT.get(attr, []):
            x = us[(us.attr == a) & (us.my == my)]
            if upto is not None:
                x = x[x.rd <= upto]
            if len(x):
                return float(x.sort_values("rd").val.iloc[-1])
        return None
    rows, used = [], []
    mys = sorted(m for m in us.my.unique() if re.fullmatch(r"\d{4}/\d{2}", m) and m < cur)[:-1]     # last completed season may still be revised
    for my in mys:
        up = vintage_date(rd_cur, cur, my)
        if us[(us.my == my) & (us.rd <= up)].empty:
            continue
        v = [(at(a, my, up), at(a, my)) for a in ("Ending Stocks", "Exports", "Production", "Beginning Stocks")]
        if any(a is None or b is None for a, b in v):
            continue
        rows.append([b - a for a, b in v]); used.append(my)
    out = {"x": -1.0, "p": 1.0, "n": len(rows), "month": f"{rd_cur:%B}"}
    if len(rows) < 10:
        out["fallback"] = True
        return out
    R = np.array(rows)
    b = np.linalg.lstsq(R[:, 1:], R[:, 0], rcond=None)[0]
    out.update({"x_raw": float(b[0]), "p_raw": float(b[1]), "b_raw": float(b[2]),
                "x": -float(min(1.0, max(0.2, -b[0]))), "p": float(min(1.0, max(0.2, b[1]))), "first": used[0], "last": used[-1]})
    return out


ABSORB = {"corn": ["Feed & residual", "Domestic use"], "soybeans": ["Seed & residual"], "cotton": ["Unaccounted"],
          "wheat": ["Domestic use"], "kc": ["Domestic use"]}     # line that takes the part of a change that does not reach stocks


def usda_yield_error(key, rd_cur):
    """USDA's average miss (bu/ac) of the final US yield in the month of the latest report (NASS Crop Production table in
    data/grains/derived/pack.json); nearest earlier month if that month has no estimate."""
    try:
        p = json.loads((ROOT / "data" / "grains" / "derived" / "pack.json").read_text())
        t = p["yields"][key]["table"]; cy = int(p.get("crop_year") or rd_cur.year)
    except Exception:
        return None, None
    order = ["aug", "sep", "oct", "nov"]
    m = rd_cur.month
    start = {8: 0, 9: 1, 10: 2, 11: 3}.get(m, 3 if (m == 12 or m <= 4) else 0)
    for i in range(start, -1, -1):
        e = [abs(r[order[i]] - r["final"]) for r in t if r.get("year", 9999) < cy and r.get(order[i]) is not None and r.get("final") is not None]
        if len(e) >= 8:
            return float(np.mean(e)), {"aug": "August", "sep": "September", "oct": "October", "nov": "November"}[order[i]]
    return None, None


def revision_bounds(w, cur, rd_cur, area_attr=None, planted_attr=None):
    """How far USDA's US crop has moved from the same-month estimate to the final, across completed seasons:
    min/max % change in production and the largest rise in abandonment (points of planted area)."""
    import re
    us = w[w.reg == "United States"]; m_ = rd_cur.month; rows = []
    for my in sorted(m for m in us.my.unique() if re.fullmatch(r"\d{4}/\d{2}", m) and m < cur):
        when = pd.Timestamp(int(my[:4]), m_, 28)
        def at(attr, upto=None):
            x = us[(us.attr == attr) & (us.my == my)].sort_values("rd")
            if upto is not None:
                x = x[x.rd <= upto]
            return float(x.val.iloc[-1]) if len(x) else None
        po, pf = at("Production", when), at("Production")
        if po and pf:
            r = {"my": my, "dP": pf / po - 1}
            if area_attr:
                ho, hf, plo, plf = at(area_attr, when), at(area_attr), at(planted_attr, when), at(planted_attr)
                if ho and hf and plo and plf:
                    r["dAb"] = (1 - hf / plf) - (1 - ho / plo)
            rows.append(r)
    R = pd.DataFrame(rows).iloc[:-1] if len(rows) > 1 else pd.DataFrame(rows)     # last completed season may still be revised
    if R.empty:
        return None
    lo = R.loc[R.dP.idxmin()]; hi = R.loc[R.dP.idxmax()]
    out = {"n": int(len(R)), "first": R.my.iloc[0], "dP_min": float(lo.dP), "dP_min_my": lo.my, "dP_max": float(hi.dP), "dP_max_my": hi.my, "month": f"{rd_cur:%B}"}
    if "dAb" in R and R.dAb.notna().any():
        a = R.loc[R.dAb.idxmax()]; out.update({"dAb_max": float(a.dAb), "dAb_max_my": a.my})
    return out


def price_response(w, cur, start_month=10):
    """Share of a US crop change that ends up in exports once price adjusts: slope of (final - October) exports on
    (final - October) production across the last 15 completed seasons of USDA estimates; held to 0.2-0.9."""
    import numpy as np
    us = w[w.reg == "United States"]; rows = []
    for my in sorted(m for m in us.my.unique() if m < cur):
        when = pd.Timestamp(int(my[:4]), start_month, 28)
        def at(attr, upto=None):
            x = us[(us.attr == attr) & (us.my == my)].sort_values("rd")
            if upto is not None:
                x = x[x.rd <= upto]
            return float(x.val.iloc[-1]) if len(x) else None
        po, pf, eo, ef = at("Production", when), at("Production"), at("Exports", when), at("Exports")
        if None not in (po, pf, eo, ef):
            rows.append((pf - po, ef - eo))
    rows = rows[-16:-1] if len(rows) > 15 else rows[:-1]       # skip the season still being revised
    if len(rows) < 8:
        return None
    x, y = zip(*rows)
    return float(min(0.9, max(0.2, np.polyfit(x, y, 1)[0])))


def trade_cap(key, cur, b, cfg):
    """Ceiling on US exports from world trade: the highest US share of world exports in the last 5 completed seasons times
    USDA's world trade this season, less competitors' ending stocks above their own 5-season average (that inventory is
    sold before the US gains share). Competitors = the active rival exporters in the export brief (Brazil, Argentina, ...)."""
    if not cfg or key == "kc":
        return None                            # no class-level world table for HRW
    k = cfg.get("to_world", 1.0)             # US units -> world-table units (MMT, or m bales for cotton)
    ww = G.wasde(cfg.get("world") or cfg["wasde"], key)
    last = lambda reg, attr: ww[(ww.reg == reg) & (ww.attr.isin([attr, attr + ", Total"]))].sort_values("rd").groupby("my").val.last()
    wx = last("World", "Exports"); usx = last("United States", "Exports")
    if wx.empty or cur not in wx.index:
        return None
    share = (usx * k / wx).dropna()
    past = share[share.index < cur].tail(5)
    if past.empty:
        return None
    smax, smy = float(past.max()), past.idxmax()
    comps = [x["r"] for x in ((b or {}).get("supply") or {}).get("exporters", []) if x.get("active")]
    comp_rows, excess = [], 0.0
    for r in comps:
        es = last(r, "Ending Stocks")
        if cur in es.index:
            prev = es[es.index < cur].tail(5)
            if len(prev):
                ex_ = float(es[cur]) - float(prev.mean())
                comp_rows.append({"r": r, "end": float(es[cur]), "avg5": float(prev.mean()), "excess": ex_})
                excess += ex_
    s_usda = float(usx[cur] * k / wx[cur]) if cur in usx.index else smax
    displaced = max(excess, 0.0) * s_usda            # extra rival stocks take business from the US roughly in line with its share
    cap_world = smax * float(wx[cur]) - displaced
    return {"share_max": smax, "share_max_my": smy, "share_usda": float(usx[cur] * k / wx[cur]) if cur in usx.index else None,
            "world_trade": float(wx[cur]), "comp": comp_rows, "comp_excess": excess, "displaced": displaced, "cap": cap_world / k, "world_unit": cfg.get("world_unit", "MMT")}


def foreign_demand(key, ex, u):
    """Cotton only: extra US export demand from India (data/india/india.json), m 480-lb bales.
    Direct = extra US cotton India takes vs the duty-returns-in-November case; displaced = India's extra buying from Brazil, Africa and
    Australia times the US share of world exports (USDA), the part of that cotton's usual buyers that turns to the US."""
    if key != "cotton":
        return None
    f = ROOT / "data" / "india" / "india.json"
    if not f.exists():
        return None
    try:
        O = json.loads(f.read_text()).get("origins") or {}
        ee, ea = O["extra_expected"], O["extra_all_year"]
        share = (u["Exports"] / 44.71) if u.get("Exports") else 0.275
        try:
            W = json.loads((ROOT / "data" / "geo" / "raw" / "psd.json").read_text())["data"]["cotton"]["rows"]
            yr = max(r[2] for r in W if r[1] == "World" and r[3] == "Exports")
            share = u["Exports"] * 1000 / next(r[4] for r in W if r[1] == "World" and r[3] == "Exports" and r[2] == yr)
        except Exception:
            pass
        comp = ("Brazil", "Africa", "Australia")
        d_b, d_r = sum(ee.get(c, 0) for c in comp) * share, sum(ea.get(c, 0) for c in comp) * share
        notes = json.loads((ROOT / "data" / "india" / "notes.json").read_text()) if (ROOT / "data" / "india" / "notes.json").exists() else {}
        return {"base": round(ee.get("USA", 0) + d_b, 2), "bear": round(ea.get("USA", 0) + d_r, 2), "direct_base": ee.get("USA", 0), "direct_bear": ea.get("USA", 0),
                "displaced_base": round(d_b, 2), "displaced_bear": round(d_r, 2), "us_share": round(share, 3), "waiver_to": notes.get("duty_expected_until", "2026-12-31")}
    except Exception as e:
        print("foreign demand skipped:", repr(e)[:120])
        return None


PIPELINE = {"cotton": 1.5}     # m bales: working stocks the trade needs; US ending stocks have been below 2 m before


def simulate(u, prod, base_ex, theta, foreign, exp_miss_pct, bounds, tc, pipe, key, pt=None, n=20000, seed=7):
    """Monte Carlo of the crop and the export programme.
    Crop ~ normal around the base case with sd = half the bullish-bearish crop band, clipped to USDA's historical post-October revisions.
    Exports = base view + price response (theta x crop surprise) + foreign demand (cotton: India's duty path drawn 25/50/25 for duty back
    in November / waiver to December / waiver all season) + noise with sd = the typical miss of the base export view at this week.
    Ending stocks = USDA's + pass-through x (exports - USDA) + pass-through x (crop - USDA) (pt, from pass_through); the rest of the
    change goes to domestic use ("dom"). Exports are capped by the trade ceiling and rationed so stocks stay above the pipeline minimum.
    Base / bullish / bearish = median / 10th / 90th percentile of ending stocks; each case reports the average crop and exports of the
    draws around that percentile, so the columns stay internally consistent."""
    rng = np.random.default_rng(seed)
    mu, sd = prod["base"], max((prod["bear"] - prod["bull"]) / 2, 0.01 * prod["base"])
    crop = rng.normal(mu, sd, n)
    if bounds:
        up = u["Production"]
        crop = np.clip(crop, up * (1 + bounds["dP_min"]), up * (1 + bounds["dP_max"]))
    em = (exp_miss_pct or 6.0) / 100
    ex = base_ex + theta * (crop - mu) + rng.normal(0, em * base_ex, n)
    if foreign:
        k = rng.choice(3, n, p=[0.25, 0.5, 0.25])
        ex += np.select([k == 0, k == 1, k == 2], [0.0, foreign["base"], foreign["bear"]])
    if tc and tc.get("cap") is not None:
        ex = np.minimum(ex, tc["cap"])
    other_use = sum(u.get(k_) or 0 for k_ in (("Domestic use",) if key != "soybeans" else ("Crush", "Seed & residual")))
    cx, cp = (pt["x"], pt["p"]) if pt else (-1.0, 1.0)
    supply0 = (u.get("Beginning stocks") or 0) + u["Production"] + (u.get("Imports") or 0)
    end0 = supply0 - other_use - u["Exports"] - (u.get("Unaccounted") or 0)       # USDA's balance (same lines as the table)
    dP, dX = crop - u["Production"], ex - u["Exports"]
    end = end0 + cx * dX + cp * dP
    dom = (1 - cp) * dP - (1 + cx) * dX              # part of the change absorbed by domestic use (or unaccounted, cotton)
    rationed = np.zeros(n, bool)
    if pipe is not None:
        rationed = end < pipe
        ex = np.where(rationed, ex - (pipe - end), ex); end = np.maximum(end, pipe)
    use = other_use + ex + (dom if key != "cotton" else 0)
    su = 100 * end / use
    p10 = float(np.percentile(end, 10))
    out = {"n": n, "su_q": [round(float(x), 2) for x in np.percentile(su, np.arange(1, 100))], "rationed_pct": round(100 * rationed.mean(), 1), "end_pct": {p: round(float(np.percentile(end, p)), 3) for p in (5, 10, 25, 50, 75, 90, 95)},
           "p_below_usda": round(100 * float((end < u["Ending stocks"]).mean()), 1), "usda_end": u["Ending stocks"],
           "pipe": pipe, "bull_at_floor": bool(pipe is not None and abs(p10 - pipe) <= 1e-6 * max(1.0, abs(pipe))), "pass_through": {"x": cx, "p": cp}}
    for s, p in (("bull", 10), ("base", 50), ("bear", 90)):
        lo, hi = np.percentile(end, max(p - 3, 0)), np.percentile(end, min(p + 3, 100))
        m = (end >= lo) & (end <= hi)
        out[s] = {"prod": float(crop[m].mean()), "exports": float(ex[m].mean()), "end": float(end[m].mean()), "dom": float(dom[m].mean())}
    return out


def export_views(b):
    """central and the spread across the projection's own views (not the full historical min-max)."""
    pr = b.get("proj") or {}
    keys = ["add", "add3w", "ly", "flow"] if "add3w" in pr else ["share", "add", "ly"]
    v = [pr[k] for k in keys if pr.get(k) is not None]
    c = pr.get("central") or b.get("implied")
    return (c, min(v + [c]), max(v + [c])) if c else (None, None, None)


def build():
    esr = {c["key"]: c for c in json.loads((ROOT / "data/grains/derived/esr_brief.json").read_text())["commodities"]}
    cond = json.loads((ROOT / "data/grains/derived/condition.json").read_text())
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "markets": {}}
    cfgs = {c["key"]: c for c in G.COMMS}
    for key, (fname, unit, dec, lines) in SPEC.items():
        w = G.wasde(fname, key)
        hist_end = w[(w.reg == "United States") & (w.attr.isin(["Ending Stocks", "Ending Stocks, Total"]))].sort_values("rd").groupby("my").val.last()
        us = w[w.reg == "United States"]
        if us.empty:
            continue
        cur = sorted(us[us.attr.isin(["Production", "Ending Stocks"])].my.unique())[-1]
        yrs = sorted(m for m in us.my.unique() if m <= cur)[-4:]
        rd_cur = us[us.my == cur].rd.max()
        col = {my: {} for my in yrs}
        for my in yrs:
            for lab, attr in lines:
                if attr:
                    col[my][lab] = latest(w, attr, my)[0]
            c = col[my]
            c["Total supply"] = sum(c.get(k) or 0 for k in ("Beginning stocks", "Production", "Imports"))
            if key == "soybeans":
                end = c.get("Ending stocks"); tot_use = c["Total supply"] - (end or 0)
                c["Seed & residual"] = tot_use - (c.get("Crush") or 0) - (c.get("Exports") or 0)
            c["Total use"] = sum(c.get(k) or 0 for k in (("Domestic use", "Exports") if key != "soybeans" else ("Crush", "Seed & residual", "Exports")))
            if PRICE.get(key):
                c["Farm price"] = latest(w, PRICE[key][0], my)[0]
        u = col[cur]
        product = key in ("meal", "oil")      # crush output: an export miss changes the crush, not stocks
        # ---- production scenarios ----
        prod = {"base": u["Production"], "bear": u["Production"], "bull": u["Production"]}; psrc = "USDA (harvest complete)" if key in ("wheat", "kc") else "USDA (made from the soybean crush)"
        yld = {}; cot_ay = {}; bounds = None; yw = None
        if key == "cotton":
            cp = crop_cotton()
            if cp and cp.get("us_all"):
                a = cp["us_all"]; up = u["Production"]
                prod = {"base": (a["central"] + up) / 2, "bear": max(up, a["hi68"]), "bull": min(up, a["lo68"])}
                # harvested area from Texas abandonment (where the crop model's difference comes from); yield = production / area
                ab_u = (cp.get("usda") or {}).get("tx_abandonment"); ab = (cp.get("texas") or {}).get("abandonment") or {}
                txp = ((cp.get("conditional") or {}).get("tx_planted_acres"))
                if ab_u is not None and ab.get("central") is not None and txp and u.get("Harvested area (m ac)"):
                    sd = lambda side: (ab[side] - ab["central"]) / 1.96
                    abd = {"base": (ab_u + ab["central"]) / 2,
                           "bear": ab_u if prod["bear"] == up else ab["central"] + sd("lo95"),
                           "bull": ab["central"] + sd("hi95") if prod["bull"] != up else ab_u}
                    area = {k_: u["Harvested area (m ac)"] - txp * (v - ab_u) for k_, v in abd.items()}
                    rb = revision_bounds(w, cur, rd_cur, "Harvested", "Planted")
                    if rb:
                        up_ = u["Production"]; pl = u.get("Planted area (m ac)")
                        for k_ in prod:
                            prod[k_] = min(max(prod[k_], up_ * (1 + rb["dP_min"])), up_ * (1 + rb["dP_max"]))
                        if rb.get("dAb_max") is not None and pl:
                            amin = u["Harvested area (m ac)"] - rb["dAb_max"] * pl          # largest post-report abandonment rise on record
                            area = {k_: max(v, amin) for k_, v in area.items()}
                        bounds = rb
                    cot_ay = {k_: {"Harvested area (m ac)": area[k_], "Yield (lb/ac)": prod[k_] * 480 / area[k_],
                                   "tx_ab": ab_u + (u["Harvested area (m ac)"] - area[k_]) / txp} for k_ in area}
                psrc = (f"base = midway between the BMR-Com crop model ({a['central']:.2f}, {cp['asof']}) and USDA ({up:.2f}); "
                        f"bearish = the larger of USDA and the model's upper band ({a['hi68']:.2f}); bullish = the model's lower band ({a['lo68']:.2f})")
        elif key in ("corn", "soybeans"):
            m = (cond.get(key) or {}).get("model") or {}
            ha = u.get("Harvested area (m ac)")
            if m.get("estimate") and ha:
                e_ = (m.get("test") or {}).get("mae_model") or 0
                uy = u.get("Yield (bu/ac)") or m["estimate"]
                eu, eu_m = usda_yield_error(key, rd_cur)
                if e_ and eu:
                    # weight each estimate by the inverse of its squared typical miss; the combined miss is smaller than either
                    wm = (1 / e_ ** 2) / (1 / e_ ** 2 + 1 / eu ** 2); ec = (1 / (1 / e_ ** 2 + 1 / eu ** 2)) ** 0.5
                else:
                    wm, ec = 0.5, e_
                yb = uy + wm * (m["estimate"] - uy)
                yld = {"base": yb, "bear": max(uy, yb + ec), "bull": min(uy, yb - ec)}
                yw = {"w_model": wm, "mae_model": e_, "mae_usda": eu, "usda_month": eu_m, "mae_combined": ec, "model": m["estimate"], "usda": uy, "week": m.get("week")}
                prod = {k: v * ha for k, v in yld.items()}
                rb = revision_bounds(w, cur, rd_cur)
                if rb:
                    up_ = u["Production"]
                    prod = {k: min(max(v, up_ * (1 + rb["dP_min"])), up_ * (1 + rb["dP_max"])) for k, v in prod.items()}
                    yld = {k: v / ha for k, v in prod.items()}
                    bounds = rb
                psrc = ((f"yield × USDA harvested area. Base = USDA's {uy:.1f} bu/ac moved {100 * wm:.0f}% of the way to the desk crop-condition model "
                         f"({m['estimate']:.1f}, week {m['week']}) = {yb:.1f}: each is weighted by how close it has come to the final yield — USDA's {eu_m} estimate "
                         f"has missed by {eu:.2f} bu/ac on average, the model by {e_:.2f}. ") if eu else
                        f"yield × USDA harvested area. Base = midway between the desk crop-condition model ({m['estimate']:.1f} bu/ac, week {m['week']}) and USDA ({uy:.1f}). ")
                psrc += f"Bearish = the higher of USDA and the base plus the combined typical miss ({ec:.1f}); bullish = the lower of USDA and the base minus it"
        # ---- export scenarios ----
        b = esr.get(key)
        ex_c, ex_lo, ex_hi = export_views(b) if b else (None, None, None)
        ue = u["Exports"]
        # base = USDA and the bias-corrected export-sales projection, weighted by how each did at this week in past seasons
        xt = export_test(cfgs[key], b["wk"], rd_cur, cur) if b and key in cfgs and not product else None
        wu_ = (xt or {}).get("w_usda", 0.5); bias = (xt or {}).get("bias", 0.0)
        if key == "cotton" and xt:           # cotton keeps the owner's midpoint of USDA and the four-view projection; the test is reported, not applied
            xt = dict(xt, w_tested=xt.get("w_usda"), w_usda=0.5, bias=0.0, mape_blend=(xt.get("grid") or {}).get("0.50"), fallback=None); wu_, bias = 0.5, 0.0
        ex_adj = ex_c / (1 + bias) if ex_c else None
        base_ex = wu_ * ue + (1 - wu_) * (ex_adj or ue)
        exp_weight = ({"w_usda": wu_, "bias": round(bias, 4), "mape_usda": xt.get("mape_usda"), "mape_desk": xt.get("mape_desk_same", xt.get("mape_desk")),
                       "mape_desk_adj": xt.get("mape_desk_adj"), "mape_blend": xt.get("mape_blend"), "n": xt.get("n"), "years": xt.get("years"),
                       "grid": xt.get("grid"), "fallback": xt.get("fallback"), "proj": ex_c, "proj_adj": ex_adj, "usda": ue, "base": base_ex} if xt else None)
        if ex_c and xt:
            wtxt = (f"base = {100 * wu_:.0f}% USDA ({ue:,.{dec}f}) and {100 * (1 - wu_):.0f}% the export-sales projection ({ex_c:,.{dec}f}, week {b['wk']}, to {b['week']}) "
                    + (f"after allowing for how it has tended to run at this week ({'low' if bias < 0 else 'high'} by {100 * abs(bias):.1f}% on average, so it is read as {ex_adj:,.{dec}f}) " if abs(bias) > 1e-9 else "")
                    + f"= {base_ex:,.{dec}f}. "
                    + (f"Those weights would have come closest to final exports at this week of past seasons ({xt['n']} seasons, {xt['years'][0]}–{xt['years'][1]}): "
                       f"USDA's forecast at the same point missed by {xt['mape_usda']:.1f}% on average, the projection by {exp_weight['mape_desk']:.1f}% "
                       f"and the mix by {xt['mape_blend']:.1f}%. " if not xt.get("fallback") else f"Weights held at 50/50 ({xt['fallback']}). "))
        elif ex_c:
            wtxt = f"base = midway between the export-sales projection ({ex_c:,.{dec}f}, week {b['wk']}, to {b['week']}) and USDA ({ue:,.{dec}f}). "
        else:
            wtxt = "base = USDA. "
        theta = price_response(w, cur) if prod["bear"] != prod["base"] or prod["bull"] != prod["base"] else None
        if theta is not None:
            # crop-driven scenarios: a bigger crop lowers price and lifts exports; a smaller one rations them
            ex = {"base": base_ex, "bear": base_ex + theta * (prod["bear"] - prod["base"]),
                  "bull": max(ex_hi or ue, ue) + theta * (prod["bull"] - prod["base"])}
            esrc = (wtxt
                    + f"Exports respond to the crop through price: historically about {100 * theta:.0f}% of a change in the US crop has ended up in exports. "
                    + "Bearish keeps base demand (global demand is strong) and adds that share of the bigger crop; bullish starts from the strongest export view and loses that share of the smaller crop")
        else:
            ex = {"base": base_ex, "bear": min(ex_lo or ue, ue), "bull": max(ex_hi or ue, ue)}
            esrc = ("crop is fixed, so the scenarios turn on demand: " + wtxt + "Bearish = the lowest of the projection's views and USDA; bullish = the highest" if ex_c else "USDA")
        foreign = foreign_demand(key, ex, u) if theta is not None else None
        if foreign:
            ex["base"] += foreign["base"]; ex["bear"] += foreign["bear"]
            esrc += (f". India: base adds {foreign['base']:.2f} m bales (its duty waiver to {foreign['waiver_to']}: {foreign['direct_base']:.2f} direct, plus {foreign['displaced_base']:.2f} of demand it pushes to the US by buying Brazilian, African and Australian cotton); "
                     f"waiver all season adds {foreign['bear']:.2f} m (lower prices win more sales); the simulation draws the duty path (25% back in November, 50% to December, 25% all season). "
                     f"China's yarn imports already show in Vietnam and Pakistan sales, so they are not added again")
        tc = trade_cap(key, cur, b, cfgs.get(key)) if not product else None
        floor = float(hist_end[hist_end.index < cur].min()) if len(hist_end[hist_end.index < cur]) else None
        floor_my = hist_end[hist_end.index < cur].idxmin() if floor is not None else None
        sim = None
        pt = pass_through(w, cur, rd_cur) if not product else None
        if pt:
            pt["note"] = ((f"Ending stocks move by {abs(pt['x']):.2f} of a change in exports and {pt['p']:.2f} of a change in production "
                           f"(USDA's {pt['month']} estimates vs the final, {pt['n']} seasons from {pt['first']}); the rest is absorbed by "
                           + {"corn": "feed and residual use", "soybeans": "seed and residual use", "cotton": "the unaccounted line"}.get(key, "domestic use"))
                          if not pt.get("fallback") else f"Ending stocks move one for one with exports and production (only {pt['n']} seasons of USDA estimates to measure it)")
        if theta is not None and not product:
            pipe = PIPELINE.get(key, 0.6 * floor if floor else None)
            em = ((xt.get("mape_blend") or xt.get("mape_desk")) if xt else None)
            sim = simulate(u, prod, base_ex, theta, foreign, em, bounds, tc, pipe, key, pt)
            if sim:
                for s in ("base", "bear", "bull"):
                    if key == "cotton" and cot_ay:
                        # harvested area moves with the crop along the abandonment line of the original cases
                        xs = np.array([prod[k_] for k_ in cot_ay]); ys = np.array([cot_ay[k_]["Harvested area (m ac)"] for k_ in cot_ay])
                        sl, ic = np.polyfit(xs, ys, 1) if len(set(np.round(xs, 3))) > 1 else (0.0, float(ys.mean()))
                        ar = ic + sl * sim[s]["prod"]
                        cot_ay[s] = {"Harvested area (m ac)": ar, "Yield (lb/ac)": sim[s]["prod"] * 480 / ar, "tx_ab": None}
                    if yld and u.get("Harvested area (m ac)"):
                        yld[s] = sim[s]["prod"] / u["Harvested area (m ac)"]
                    prod[s] = sim[s]["prod"]; ex[s] = sim[s]["exports"]
                floor, floor_my = pipe, "pipeline minimum"
                psrc += f". Scenarios now come from {sim['n']:,} simulated crops and export programmes: base = median ending stocks, bullish = 10th percentile, bearish = 90th"
        capped = {}
        scen = {}
        for s in ("base", "bear", "bull"):
            c = dict(u)
            c["Production"] = prod[s]; c["Exports"] = ex[s]
            if tc and tc.get("cap") is not None and c["Exports"] > tc["cap"]:
                capped.setdefault(s, {})["trade"] = {"projected": c["Exports"], "allowed": tc["cap"]}
                c["Exports"] = tc["cap"]
            if s in yld:
                c["Yield (bu/ac)"] = yld[s]
            if key == "cotton":
                if s in cot_ay:
                    c["Harvested area (m ac)"] = cot_ay[s]["Harvested area (m ac)"]; c["Yield (lb/ac)"] = cot_ay[s]["Yield (lb/ac)"]
                elif prod[s] != u["Production"]:
                    c["Harvested area (m ac)"] = None; c["Yield (lb/ac)"] = None
            if not product:
                # pass-through: the part of the production / export change that does not reach stocks goes to domestic use
                if sim:
                    dom = sim[s]["dom"]
                else:
                    cx, cp = (pt["x"], pt["p"]) if pt else (-1.0, 1.0)
                    dom = (1 - cp) * (c["Production"] - u["Production"]) - (1 + cx) * (c["Exports"] - u["Exports"])
                for ln in ABSORB.get(key, []):
                    if ln == "Unaccounted" or c.get(ln) is not None:
                        c[ln] = (c.get(ln) or 0) + dom
            c["Total supply"] = sum(c.get(k) or 0 for k in ("Beginning stocks", "Production", "Imports"))
            use_keys = ("Domestic use", "Exports") if key != "soybeans" else ("Crush", "Seed & residual", "Exports")
            c["Total use"] = sum(c.get(k) or 0 for k in use_keys)
            c["Ending stocks"] = c["Total supply"] - c["Total use"] - (c.get("Unaccounted") or 0)
            if floor is not None and c["Ending stocks"] < floor and not product:
                cut = floor - c["Ending stocks"]
                capped.setdefault(s, {})["supply"] = {"projected": c["Exports"], "allowed": c["Exports"] - cut}
                c["Exports"] -= cut; c["Total use"] -= cut; c["Ending stocks"] = floor
            c["Farm price"] = None
            if product:
                c = {k_: None for k_ in c}
            scen[s] = c
        su = lambda c: (100 * c["Ending stocks"] / c["Total use"]) if c.get("Ending stocks") is not None and c.get("Total use") else None
        labels = [l for l, _ in lines]
        if key == "corn" and "Domestic use" not in u:
            labels.remove("Domestic use")
        rows = []
        for lab in labels + ["Stocks / use (%)"] + (["Farm price (" + PRICE[key][1] + ")"] if PRICE.get(key) else []):
            g = (lambda c: su(c)) if lab == "Stocks / use (%)" else (lambda c, lab=lab: c.get("Farm price") if lab.startswith("Farm price") else c.get(lab))
            rows.append({"label": lab, "usda": {my: g(col[my]) for my in yrs}, "base": g(scen["base"]), "bear": g(scen["bear"]), "bull": g(scen["bull"]),
                         "key": lab in ("Production", "Exports", "Ending stocks", "Stocks / use (%)")})
        es_u = u.get("Ending stocks")
        out["markets"][key] = {"name": NAMES[key], "unit": unit, "dec": dec, "years": yrs, "cur": cur, "report": f"{rd_cur:%B %Y}", "rows": rows,
                               "prod_src": psrc, "exp_src": esrc,
                               "summary": {s: {"prod": prod[s], "exports": scen[s]["Exports"], "exports_proj": ex[s], "end": scen[s]["Ending stocks"], "su": su(scen[s])} for s in scen},
                               "usda_end": es_u, "usda_su": su(u),
                               "exp_week": b["wk"] if b else None, "exp_miss": (xt or {}).get("mape_desk") if xt else (export_miss(cfgs[key], b["wk"]) if b and key in cfgs else None),
                               "exp_weight": exp_weight, "yield_weight": yw, "pass_through": pt,
                               "bull_at_floor": bool(sim and sim.get("bull_at_floor")), "floor_pct": sim["rationed_pct"] if sim else None,
                               "vars": VARS.get(key, []), "floor": floor, "floor_my": floor_my, "foreign": foreign if theta is not None else None, "sim": sim, "capped": capped, "product": product, "trade": tc, "theta": theta if not product else None,
                               "tx_ab": {k_: v["tx_ab"] for k_, v in cot_ay.items()} if cot_ay else None, "bounds": bounds,
                               "exp_usda": u.get("Exports"), "prod_usda": u.get("Production")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), default=lambda x: None))
    for k, m in out["markets"].items():
        s = m["summary"]
        if m["product"]:
            print(m["name"], "USDA only (processed product)"); continue
        print(f"{m['name']:13s} {m['cur']} USDA end {m['usda_end']:,.{m['dec']}f} | base {s['base']['end']:,.{m['dec']}f} bear {s['bear']['end']:,.{m['dec']}f} bull {s['bull']['end']:,.{m['dec']}f}  ({m['unit']})")


if __name__ == "__main__":
    build()
