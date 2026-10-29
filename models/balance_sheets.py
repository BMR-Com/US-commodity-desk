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
        yld = {}
        if key == "cotton":
            cp = crop_cotton()
            if cp and cp.get("us_all"):
                a = cp["us_all"]; prod = {"base": a["central"], "bear": a["hi68"], "bull": a["lo68"]}
                psrc = f"BMR-Com crop model, {cp['asof']} (inputs to {max(cp['inputs_through'].values())}); bearish/bullish = 68% range"
        elif key in ("corn", "soybeans"):
            m = (cond.get(key) or {}).get("model") or {}
            ha = u.get("Harvested area (m ac)")
            if m.get("estimate") and ha:
                e_ = (m.get("test") or {}).get("mae_model") or 0
                yld = {"base": m["estimate"], "bear": m["estimate"] + e_, "bull": m["estimate"] - e_}
                prod = {k: v * ha for k, v in yld.items()}
                psrc = f"desk crop-condition yield model {m['estimate']:.1f} bu/ac (week {m['week']}) × USDA harvested area; bearish/bullish = ± its average miss ({e_:.1f} bu/ac)"
        # ---- export scenarios ----
        b = esr.get(key)
        ex_c, ex_lo, ex_hi = export_views(b) if b else (None, None, None)
        ex = {"base": ex_c or u["Exports"], "bear": ex_lo or u["Exports"], "bull": ex_hi or u["Exports"]}
        esrc = (f"export-sales projection, week {b['wk']} (to {b['week']}); bearish/bullish = low/high of its projection views" if ex_c else "USDA")
        floor = float(hist_end[hist_end.index < cur].min()) if len(hist_end[hist_end.index < cur]) else None
        floor_my = hist_end[hist_end.index < cur].idxmin() if floor is not None else None
        capped = {}
        scen = {}
        for s in ("base", "bear", "bull"):
            c = dict(u)
            c["Production"] = prod[s]; c["Exports"] = ex[s]
            if s in yld:
                c["Yield (bu/ac)"] = yld[s]
            if key == "cotton" and u.get("Harvested area (m ac)") and prod[s] != u["Production"]:
                c["Yield (lb/ac)"] = None; c["Harvested area (m ac)"] = None      # crop model projects bales, not area x yield
            c["Total supply"] = sum(c.get(k) or 0 for k in ("Beginning stocks", "Production", "Imports"))
            use_keys = ("Domestic use", "Exports") if key != "soybeans" else ("Crush", "Seed & residual", "Exports")
            c["Total use"] = sum(c.get(k) or 0 for k in use_keys)
            c["Ending stocks"] = c["Total supply"] - c["Total use"] - (c.get("Unaccounted") or 0)
            if floor is not None and c["Ending stocks"] < floor and not product:
                cut = floor - c["Ending stocks"]
                capped[s] = {"projected": c["Exports"], "allowed": c["Exports"] - cut}
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
                               "floor": floor, "floor_my": floor_my, "capped": capped, "product": product,
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
