"""US balance sheets with desk scenarios: USDA's last three seasons and current forecast, plus base / bearish / bullish
ending stocks built from the desk's own production and export projections. Other lines (beginning stocks, imports,
domestic use) stay at USDA's current numbers.

Production:  cotton  -> cotton-crop-progress crop model (us_all central, 68% band)
             corn, soybeans -> desk crop-condition yield model (estimate +/- its back-tested mean miss) x USDA harvested area
             wheat, HRW -> harvest complete, USDA production in every scenario
             meal, oil -> made from the soybean crush, USDA production in every scenario
Exports:     desk export-sales projection (data/grains/derived/esr_brief.json): central, and the spread across its views
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


def export_miss(cfg, wk):
    """Average % miss of the desk export projection at this week of the season vs USDA's final, past seasons (out of sample)."""
    import numpy as np
    try:
        e = G.esr(cfg["dirs"]); w = G.wasde(cfg["wasde"], cfg["key"]); labels = G.my_label(e, cfg["start"])
        tot = e.groupby(["marketYear", "weekEndingDate"])[["commit", "accumulatedExports", "currentMYNetSales"]].sum().reset_index()
        tot["wk"] = tot.apply(lambda r: (r.weekEndingDate - pd.Timestamp(year=labels[r.marketYear][0], month=cfg["start"], day=1)).days // 7, axis=1)
        cy = int(tot.marketYear.max()); rows = []
        for y in sorted(tot.marketYear.unique()):
            if y >= cy:
                continue
            g = tot[tot.marketYear == y].sort_values("wk"); a = g[g.wk <= wk - 1]
            wf, _ = G.w_latest(w, "United States", "Exports", labels[y][1])
            if a.empty or not wf:
                continue
            rows.append(dict(commit=a.commit.iloc[-1], net4=g[(g.wk > wk - 5) & (g.wk <= wk - 1)].currentMYNetSales.mean(), fin=g.accumulatedExports.iloc[-1], usda=wf))
        P = pd.DataFrame(rows); P["add"] = P.fin - P.commit; P["pct"] = P.commit / P.fin; P["ratio"] = P.fin / P.usda
        errs = []
        for i in range(6, len(P)):
            tr, x = P.iloc[:i], P.iloc[i]; t5 = tr.tail(5); r = t5.ratio.median()
            ad = x.commit + t5["add"].median(); ly = x.commit + tr["add"].iloc[-1]
            if cfg.get("blend"):
                v = [ad, ly, x.commit + np.average(tr["add"].tail(3), weights=[1, 2, 3])]
                t10 = tr.tail(10); X = np.c_[np.ones(len(t10)), t10.net4, t10.commit]; bb = np.linalg.lstsq(X, t10["add"], rcond=None)[0]
                v.append(x.commit + bb @ [1, x.net4, x.commit])
            else:
                v = [x.commit / t5.pct.mean(), ad, ly]
            errs.append(abs(np.median(v) / r - x.usda) / x.usda)
        return round(100 * float(np.mean(errs)), 1) if errs else None
    except Exception:
        return None


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


def simulate(u, prod, base_ex, theta, foreign, exp_miss_pct, bounds, tc, pipe, key, n=20000, seed=7):
    """Monte Carlo of the crop and the export programme.
    Crop ~ normal around the base case with sd = half the bullish-bearish crop band, clipped to USDA's historical post-October revisions.
    Exports = base view + price response (theta x crop surprise) + foreign demand (cotton: India's duty path drawn 25/50/25 for duty back
    in November / waiver to December / waiver all season) + noise with sd = the export-sales projection's typical miss at this week.
    Exports are capped by the trade ceiling and rationed so stocks stay above the pipeline minimum.
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
    supply = (u.get("Beginning stocks") or 0) + crop + (u.get("Imports") or 0)
    end = supply - other_use - ex - (u.get("Unaccounted") or 0)
    rationed = np.zeros(n, bool)
    if pipe is not None:
        rationed = end < pipe
        ex = np.where(rationed, ex - (pipe - end), ex); end = np.maximum(end, pipe)
    use = other_use + ex
    su = 100 * end / use
    out = {"n": n, "su_q": [round(float(x), 2) for x in np.percentile(su, np.arange(1, 100))], "rationed_pct": round(100 * rationed.mean(), 1), "end_pct": {p: round(float(np.percentile(end, p)), 3) for p in (5, 10, 25, 50, 75, 90, 95)},
           "p_below_usda": round(100 * float((end < u["Ending stocks"]).mean()), 1), "usda_end": u["Ending stocks"]}
    for s, p in (("bull", 10), ("base", 50), ("bear", 90)):
        lo, hi = np.percentile(end, max(p - 3, 0)), np.percentile(end, min(p + 3, 100))
        m = (end >= lo) & (end <= hi)
        out[s] = {"prod": float(crop[m].mean()), "exports": float(ex[m].mean()), "end": float(end[m].mean())}
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
        yld = {}; cot_ay = {}; bounds = None
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
                yld = {"base": (m["estimate"] + uy) / 2, "bear": max(uy, m["estimate"] + e_), "bull": min(uy, m["estimate"] - e_)}
                prod = {k: v * ha for k, v in yld.items()}
                rb = revision_bounds(w, cur, rd_cur)
                if rb:
                    up_ = u["Production"]
                    prod = {k: min(max(v, up_ * (1 + rb["dP_min"])), up_ * (1 + rb["dP_max"])) for k, v in prod.items()}
                    yld = {k: v / ha for k, v in prod.items()}
                    bounds = rb
                psrc = (f"yield × USDA harvested area. Base = midway between the desk crop-condition model ({m['estimate']:.1f} bu/ac, week {m['week']}) and USDA ({uy:.1f}); "
                        f"bearish = the higher of USDA and the model plus its average miss ({e_:.1f}); bullish = the lower of USDA and the model minus it")
        # ---- export scenarios ----
        b = esr.get(key)
        ex_c, ex_lo, ex_hi = export_views(b) if b else (None, None, None)
        ue = u["Exports"]
        base_ex = ((ex_c or ue) + ue) / 2
        theta = price_response(w, cur) if prod["bear"] != prod["base"] or prod["bull"] != prod["base"] else None
        if theta is not None:
            # crop-driven scenarios: a bigger crop lowers price and lifts exports; a smaller one rations them
            ex = {"base": base_ex, "bear": base_ex + theta * (prod["bear"] - prod["base"]),
                  "bull": max(ex_hi or ue, ue) + theta * (prod["bull"] - prod["base"])}
            esrc = ((f"base = midway between the export-sales projection ({ex_c:,.{dec}f}, week {b['wk']}, to {b['week']}) and USDA ({ue:,.{dec}f}). " if ex_c else "base = USDA. ")
                    + f"Exports respond to the crop through price: historically about {100 * theta:.0f}% of a change in the US crop has ended up in exports. "
                    + "Bearish keeps base demand (global demand is strong) and adds that share of the bigger crop; bullish starts from the strongest export view and loses that share of the smaller crop")
        else:
            ex = {"base": base_ex, "bear": min(ex_lo or ue, ue), "bull": max(ex_hi or ue, ue)}
            esrc = (f"crop is fixed, so the scenarios turn on demand: base = midway between the export-sales projection ({ex_c:,.{dec}f}, week {b['wk']}) and USDA ({ue:,.{dec}f}); "
                    f"bearish = the lowest of its views and USDA; bullish = the highest" if ex_c else "USDA")
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
        if theta is not None and not product:
            pipe = PIPELINE.get(key, 0.6 * floor if floor else None)
            em = export_miss(cfgs[key], b["wk"]) if b and key in cfgs else None
            sim = simulate(u, prod, base_ex, theta, foreign, em, bounds, tc, pipe, key)
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
                               "exp_week": b["wk"] if b else None, "exp_miss": export_miss(cfgs[key], b["wk"]) if b and key in cfgs else None,
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
