"""India cotton page data: balance sheets (COCPC, CAI, USDA) in 480-lb bales, state crop history, trade, Shankar-6,
cotton-district rainfall against history, and the desk crop projection.
Reads data/india/raw/*.json and data/india/cai_spot.csv; writes data/india/india.json (page) and data/india/model_eval.json
(backtest detail, kept out of the page).
"""
import csv, json, math
from datetime import date, datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "india"
RAW = D / "raw"
LAKH170_TO_M480 = 100000 * 170 / 217.7243 / 1e6       # 1 lakh 170-kg bales = 0.07808 m 480-lb bales
TODAY = date.today()
NORMAL = (1991, 2020)
# regions modelled; Telangana was part of Andhra Pradesh before 2014-15, so the two are joined
REGION = {"Punjab": "North", "Haryana": "North", "Rajasthan": "North", "Gujarat": "Gujarat", "Maharashtra": "Maharashtra",
          "Madhya Pradesh": "Madhya Pradesh", "Telangana": "Telangana + AP", "Andhra Pradesh": "Telangana + AP",
          "Karnataka": "Karnataka", "Tamil Nadu": "South other", "Odisha": "South other"}
ORDER = ["North", "Gujarat", "Maharashtra", "Madhya Pradesh", "Telangana + AP", "Karnataka", "South other"]
IRRIGATED = {"North"}
VARS = ["State and zone cotton area (Cotton Advisory Board / COCPC via CAI) and this season's sown area (Ministry of Agriculture)",
        "Each region's normal yield: the average of its previous five seasons",
        "June-July and August-September rainfall at the main cotton districts against the 1991-2020 normal (NASA POWER)",
        "Excess-rain penalty (very wet seasons cut yield and quality)"]


def jl(name, default=None):
    f = RAW / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else default


def norm_state(s):
    s = (s or "").strip().title().replace("Andhara", "Andhra").replace("Karanataka", "Karnataka").replace("Tamilnadu", "Tamil Nadu")
    return {"Orissa": "Odisha", "M.P.": "Madhya Pradesh", "Mp": "Madhya Pradesh"}.get(s, s)


def m480(lakh):
    return None if lakh is None else round(lakh * LAKH170_TO_M480, 2)


# ---------------------------------------------------------------- crop history by region
def region_history(cab):
    H = {}
    for y, blk in cab.items():
        y = int(y)
        agg = {}
        for r in blk["rows"]:
            st = norm_state(r["state"])
            if st not in REGION or not r.get("area") or not r.get("prod"):
                continue
            g = agg.setdefault(REGION[st], {"area": 0.0, "prod": 0.0})
            g["area"] += r["area"]; g["prod"] += r["prod"]
        tot = [r for r in blk["rows"] if (r.get("state") or "").strip().upper() in ("GRAND TOTAL", "ALL INDIA", "INDIA", "TOTAL INDIA")]
        nat = {"area": tot[0]["area"], "prod": tot[0]["prod"]} if tot else {"area": sum(g["area"] for g in agg.values()), "prod": sum(g["prod"] for g in agg.values())}
        for g in agg.values():
            g["yield"] = g["prod"] * 170 / g["area"] if g["area"] else None
        H[y] = {"regions": agg, "national": nat}
    return H


# ---------------------------------------------------------------- rainfall
def rain_tables(rain):
    """Monthly rain by region (mean of its districts) and kharif-window totals per year; current year from daily data."""
    by_region = {}
    for rec in rain["districts"].values():
        reg = REGION.get(rec["state"])
        if not reg:
            continue
        m = dict(rec["monthly"])
        cur = {}
        for d, v in rec.get("daily", {}).items():
            cur[d[:7]] = cur.get(d[:7], 0) + v
        for k, v in cur.items():
            if k[:4] == str(TODAY.year):
                m[k] = round(v, 1)
        by_region.setdefault(reg, []).append(m)
    out = {}
    for reg, lst in by_region.items():
        keys = set().union(*lst)
        out[reg] = {k: float(np.mean([x[k] for x in lst if k in x])) for k in keys}
    return out


def windows(monthly, year):
    g = lambda ms: sum(monthly.get(f"{year}-{m:02d}", np.nan) for m in ms)
    return {"jj": g((6, 7)), "as": g((8, 9)), "jjas": g((6, 7, 8, 9)), "oct": g((10,))}


def rain_features(R):
    F, normals = {}, {}
    for reg, mon in R.items():
        yrs = sorted({int(k[:4]) for k in mon})
        W = {y: windows(mon, y) for y in yrs}
        nm = {w: float(np.nanmean([W[y][w] for y in yrs if NORMAL[0] <= y <= NORMAL[1]])) for w in ("jj", "as", "jjas", "oct")}
        normals[reg] = nm
        for y in yrs:
            F.setdefault(reg, {})[y] = {w: (W[y][w] / nm[w] - 1 if nm[w] and not math.isnan(W[y][w]) else np.nan) for w in nm}
            F[reg][y]["mm"] = W[y]
    return F, normals


# ---------------------------------------------------------------- yield model
def design(H, F, years):
    X, yv, meta = [], [], []
    for y in years:                       # y = season end year; kharif year = y - 1
        for reg in ORDER:
            if reg not in H.get(y, {}).get("regions", {}) or reg not in F or (y - 1) not in F[reg]:
                continue
            prev = [H[p]["regions"][reg]["yield"] for p in range(y - 5, y) if p in H and reg in H[p]["regions"] and H[p]["regions"][reg].get("yield")]
            if len(prev) < 4:
                continue
            base = float(np.mean(prev))
            f = F[reg][y - 1]
            if any(math.isnan(f[w]) for w in ("jj", "as")):
                continue
            rf = 0.0 if reg in IRRIGATED else 1.0
            X.append([rf * f["jj"], rf * f["as"], rf * max(f["jjas"], 0) ** 2, rf * min(f["jjas"], 0) ** 2, 1 - rf])
            yv.append(math.log(H[y]["regions"][reg]["yield"] / base))
            meta.append((y, reg, base, H[y]["regions"][reg]["area"]))
    return np.array(X), np.array(yv), meta


def fit(X, y, w=None, lam=0.5):
    w = np.ones(len(y)) if w is None else w
    Xa = np.column_stack([np.ones(len(y)), X])
    W = np.diag(w)
    P = lam * np.eye(Xa.shape[1]); P[0, 0] = 0
    return np.linalg.solve(Xa.T @ W @ Xa + P, Xa.T @ W @ y)


def predict(b, X):
    return np.column_stack([np.ones(len(X)), X]) @ b


def backtest(H, F, years):
    """Leave-one-season-out: national production error for the model vs the five-season-average yield (no weather)."""
    X, y, meta = design(H, F, years)
    res = []
    for s in sorted({m[0] for m in meta}):
        tr = np.array([m[0] != s for m in meta]); te = ~tr
        if te.sum() < 3:
            continue
        b = fit(X[tr], y[tr], np.array([m[3] for m in meta])[tr])
        p = predict(b, X[te])
        mm = [m for m, t in zip(meta, te) if t]
        model = sum(a * base * math.exp(pp) / 170 for (_, _, base, a), pp in zip(mm, p))
        naive = sum(a * base / 170 for (_, _, base, a) in mm)
        actual = sum(H[s]["regions"][r]["prod"] for (_, r, _, _) in mm)
        res.append({"season": s, "actual": actual, "model": model, "naive": naive})
    err = lambda k: [r[k] / r["actual"] - 1 for r in res]
    stat = lambda e: {"mae_pct": round(100 * float(np.mean(np.abs(e))), 1), "rmse_pct": round(100 * float(np.sqrt(np.mean(np.square(e)))), 1)}
    return res, {"model": stat(err("model")), "naive": stat(err("naive")), "n": len(res)}


# ---------------------------------------------------------------- page sections
def balance_sheets(cocpc, cai, psd):
    rows = ["opening", "crop", "imports", "supply", "consumption", "exports", "closing"]
    def from_cocpc(r):
        cons = sum(r.get(k) or 0 for k in ("mill_consumption", "ssi_consumption", "non_texttile_consumption"))
        sup = (r.get("opening_stock") or 0) + (r.get("crop") or 0) + (r.get("import") or 0)
        return dict(zip(rows, [r.get("opening_stock"), r.get("crop"), r.get("import"), sup, cons, r.get("export"), r.get("closing")]))
    def from_cai(r):
        return dict(zip(rows, [r.get("opening_stock"), r.get("crop"), r.get("import"), r.get("total_supply"), r.get("total_consumption"), r.get("export"), r.get("closing_stock")]))
    out = {"cocpc": {}, "cai": {}, "usda": {}}
    for s, r in (cocpc or {}).items():
        out["cocpc"][s] = {"lakh": from_cocpc(r), "remark": r.get("remark")}
    by_season = {}
    for k, r in sorted((cai or {}).items()):
        if r.get("crop"):
            by_season.setdefault(r["season"], []).append((k, r))
    for s, lst in by_season.items():
        k, r = lst[-1]
        out["cai"][s] = {"lakh": from_cai(r), "as_of": k, "revisions": [{"month": kk, "crop": rr.get("crop"), "closing": rr.get("closing_stock"),
                                                                        "imports": rr.get("import"), "exports": rr.get("export"), "consumption": rr.get("total_consumption")} for kk, rr in lst]}
    for y, r in (psd or {}).items():
        s = f"{y}-{int(y) % 100 + 1:02d}"
        g = lambda k: (r.get(k) or 0) / 1000
        out["usda"][s] = {"m480": {"opening": g("Beginning Stocks"), "crop": g("Production"), "imports": g("Imports"), "supply": g("Total Supply"),
                                   "consumption": g("Domestic Use"), "exports": g("Exports"), "closing": g("Ending Stocks")},
                          "area_mha": g("Area Harvested") / 1000 * 1000 / 1000, "yield": r.get("Yield")}
    for src in ("cocpc", "cai"):
        for s, v in out[src].items():
            v["m480"] = {k: m480(x) for k, x in v["lakh"].items()}
    return out


CANDY_LB = 355.62 * 2.20462
MSP = {2022: (6080, 6380), 2023: (6620, 7020), 2024: (7121, 7521), 2025: (7710, 8110), 2026: (8267, 8667)}   # kapas MSP Rs/quintal (medium, long staple), by kharif year


def spot():
    """Shankar-6 (CAI Gujarat ICS-105 29 mm) in Rs/candy and cents/lb, its premium to ICE nearby, and the MSP-implied lint cost."""
    import pandas as pd
    f = D / "cai_spot.csv"
    if not f.exists():
        return {}
    d = pd.read_csv(f, parse_dates=["date"])
    d = d[(d.grade_standard == "ICS-105") & (d.staple.astype(str).str.startswith("29")) & (d.season == "current")]
    s = d[d.growth == "GUJ"].groupby("date").per_candy.last().combine_first(d[d.growth == "M/M(P)"].groupby("date").per_candy.last()).sort_index()
    if len(s) < 5:
        return {}
    fxf = RAW / "fx_ct.csv"
    if fxf.exists():
        m = pd.read_csv(fxf, index_col=0, parse_dates=True)
    else:
        m = pd.read_csv(ROOT / "data" / "markets" / "closes.csv", index_col=0, parse_dates=True)
    idx = m.index.union(s.index)
    fx = m["INR=X"].reindex(idx).ffill().reindex(s.index)
    ice = m["CT=F"].reindex(idx).ffill().reindex(s.index)
    clb = s / fx / CANDY_LB * 100
    w = pd.DataFrame({"rs": s, "clb": clb, "ice": ice, "inr": fx}).resample("W-FRI").last().dropna(subset=["rs"])
    L = s.index[-1]
    ago = lambda off: s[s.index <= L - off].iloc[-1] if (s.index <= L - off).any() else None
    yr = L.year if L.month >= 10 else L.year - 1
    out = {"latest": {"date": L.strftime("%Y-%m-%d"), "rs_candy": round(float(s.iloc[-1])), "clb": round(float(clb.iloc[-1]), 1),
                      "ice": None if pd.isna(ice.iloc[-1]) else round(float(ice.iloc[-1]), 2), "inr": round(float(fx.iloc[-1]), 2)},
           "weekly": {"date": [x.strftime("%Y-%m-%d") for x in w.index], "rs": [round(float(v)) for v in w.rs],
                      "clb": [None if pd.isna(v) else round(float(v), 1) for v in w.clb], "ice": [None if pd.isna(v) else round(float(v), 2) for v in w.ice]},
           "note": "CAI daily spot rate, Gujarat ICS-105 29 mm (Shankar-6), ex-gin, Rs per candy of 355.62 kg; cents/lb at the day's USD/INR"}
    out["latest"]["premium_ice"] = None if out["latest"]["ice"] is None else round(out["latest"]["clb"] - out["latest"]["ice"], 1)
    for k, off in (("chg_1m_pct", pd.DateOffset(months=1)), ("chg_1y_pct", pd.DateOffset(years=1))):
        v = ago(off)
        out["latest"][k] = None if v is None else round(100 * (float(s.iloc[-1]) / float(v) - 1), 1)
    if yr in MSP:
        med, lng = MSP[yr]
        kg = (med / 100 - 0.64 * 35) / 0.34          # 34% lint out-turn, seed credited at Rs 35/kg
        rs = round(kg * 355.62 + 1500, -2)            # + ginning about Rs 1,500/candy
        out["msp"] = {"season": f"{yr}-{(yr + 1) % 100:02d}", "kapas_medium": med, "kapas_long": lng, "lint_rs_candy": rs,
                      "lint_clb": round(rs / float(fx.iloc[-1]) / CANDY_LB * 100, 1), "assumptions": "34% lint out-turn, seed at Rs 35/kg, ginning Rs 1,500/candy"}
    return out


def trade_section(tr):
    if not tr:
        return {}
    out = {}
    for k in ("raw_export", "raw_import", "yarn_export"):
        rows = tr.get(k) or {}
        out[k] = {m: {"season": v["season"], **{u: v.get(u) for u in ("u0", "u1", "u2")}} for m, v in sorted(rows.items())}
    out["unit_labels"] = tr.get("unit_labels")
    return out


def main():
    cab = jl("cab_area_production", {})
    rain = jl("rain", {"districts": {}})
    H = region_history(cab)
    R = rain_tables(rain)
    F, normals = rain_features(R)
    yrs = sorted(y for y in H if y >= 2006)
    res, stats = backtest(H, F, [y for y in yrs if y <= max(yrs)])
    X, yv, meta = design(H, F, yrs)
    b = fit(X, yv, np.array([m[3] for m in meta]))
    resid = yv - predict(b, X)
    sd = float(np.sqrt(np.average(resid ** 2, weights=[m[3] for m in meta])))

    # this season: kharif year TODAY.year (season ends next year)
    ky, sy = TODAY.year if TODAY.month >= 6 else TODAY.year - 1, (TODAY.year if TODAY.month >= 6 else TODAY.year - 1) + 1
    notes = json.loads((D / "notes.json").read_text()) if (D / "notes.json").exists() else {}
    last = max(H)
    area_now = notes.get("area_lakh_ha")
    last_area = sum(g["area"] for g in H[last]["regions"].values())
    scale = area_now / notes["area_last_lakh_ha"] if area_now and notes.get("area_last_lakh_ha") else 1.0   # ministry sowing change applied to CAB area
    proj = []
    for reg in ORDER:
        if reg not in H[last]["regions"] or reg not in F or ky not in F[reg]:
            continue
        prev = [H[p]["regions"][reg]["yield"] for p in range(sy - 5, sy) if p in H and reg in H[p]["regions"]]
        base = float(np.mean(prev))
        f = F[reg][ky]
        rf = 0.0 if reg in IRRIGATED else 1.0
        x = np.array([[rf * f["jj"], rf * f["as"], rf * max(f["jjas"], 0) ** 2, rf * min(f["jjas"], 0) ** 2, 1 - rf]])
        lr = float(predict(b, x)[0])
        area = H[last]["regions"][reg]["area"] * scale
        prod = area * base * math.exp(lr) / 170
        proj.append({"region": reg, "area": round(area, 2), "base_yield": round(base), "yield": round(base * math.exp(lr)), "yield_vs_normal_pct": round(100 * (math.exp(lr) - 1), 1),
                     "prod_lakh": round(prod, 1), "prod_m480": m480(prod), "last_prod_lakh": round(H[last]["regions"][reg]["prod"], 1),
                     "rain_jj_pct": round(100 * f["jj"], 0), "rain_as_pct": round(100 * f["as"], 0), "rain_jjas_pct": round(100 * f["jjas"], 0), "irrigated": reg in IRRIGATED})
    tot = sum(p["prod_lakh"] for p in proj)
    covered = sum(H[last]["regions"][p["region"]]["prod"] for p in proj)
    other = max(H[last]["national"]["prod"] - covered, 0)          # states not modelled: carry last season
    tot_all = tot + other
    band = (tot_all * math.exp(-stats["model"]["rmse_pct"] / 100), tot_all * math.exp(stats["model"]["rmse_pct"] / 100))

    bal = balance_sheets(jl("cocpc_balance", {}), jl("cai_monthly", {}), jl("psd_india", {}))
    usda_cur = bal["usda"].get(f"{ky}-{(ky + 1) % 100:02d}", {}).get("m480", {})
    page = {
        "built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "conv": {"lakh170_to_m480": round(LAKH170_TO_M480, 5), "note": "1 lakh Indian bales (170 kg) = 0.0781 m US bales (480 lb)"},
        "projection": {"season": f"{ky}-{(ky + 1) % 100:02d}", "lakh": round(tot_all, 1), "m480": m480(tot_all), "lo_m480": m480(band[0]), "hi_m480": m480(band[1]),
                       "last_season": {"season": f"{last - 1}-{last % 100:02d}", "lakh": round(H[last]["national"]["prod"], 1), "m480": m480(H[last]["national"]["prod"])},
                       "usda_m480": usda_cur.get("crop"), "area_lakh_ha": round(last_area * scale, 2), "area_change_pct": round(100 * (scale - 1), 1), "area_note": notes.get("area_note"),
                       "regions": proj, "unmodelled_lakh": round(other, 1), "variables": VARS},
        "history": {str(y): {"area": round(H[y]["national"]["area"], 2), "prod_lakh": round(H[y]["national"]["prod"], 1), "prod_m480": m480(H[y]["national"]["prod"]),
                             "yield": round(H[y]["national"]["prod"] * 170 / H[y]["national"]["area"]) if H[y]["national"]["area"] else None,
                             "regions": {r: {"area": round(g["area"], 2), "prod_lakh": round(g["prod"], 1), "yield": round(g["yield"] or 0)} for r, g in H[y]["regions"].items()}} for y in sorted(H)},
        "rain": rain_page(R, F, normals, H, ky),
        "balance": bal, "trade": trade_section(jl("trade")), "prices": spot(), "notes": notes,
    }
    (D / "india.json").write_text(json.dumps(page, separators=(",", ":"), default=float))
    (D / "model_eval.json").write_text(json.dumps({"coef": [round(float(v), 4) for v in b], "names": ["const", "jj", "as", "wet2", "dry2", "irrigated"],
                                                   "resid_sd": round(sd, 4), "backtest": stats, "seasons": res}, indent=1))
    print("projection", page["projection"]["season"], round(tot_all, 1), "lakh =", m480(tot_all), "m 480-lb; backtest", stats)


def rain_page(R, F, normals, H, ky):
    out = {"normal": f"{NORMAL[0]}-{NORMAL[1]}", "regions": {}, "kharif_year": ky}
    w = {r: g["area"] for r, g in H[max(H)]["regions"].items()}
    idx = {}
    for reg, mon in R.items():
        yrs = sorted(F[reg])
        jjas = {y: F[reg][y]["mm"]["jjas"] for y in yrs if not math.isnan(F[reg][y]["mm"]["jjas"])}
        cur = jjas.get(ky)
        rank = sorted(jjas.values()).index(cur) + 1 if cur is not None else None
        monthly = {f"{m:02d}": {"cur": mon.get(f"{ky}-{m:02d}"), "normal": float(np.mean([mon[f"{y}-{m:02d}"] for y in range(*NORMAL) if f"{y}-{m:02d}" in mon])),
                                "last": mon.get(f"{ky - 1}-{m:02d}")} for m in range(5, 12)}
        out["regions"][reg] = {"jjas_mm": round(cur, 0) if cur else None, "jjas_pct": round(100 * F[reg][ky]["jjas"]) if ky in F[reg] else None,
                               "jj_pct": round(100 * F[reg][ky]["jj"]) if ky in F[reg] else None, "as_pct": round(100 * F[reg][ky]["as"]) if ky in F[reg] else None,
                               "oct_pct": round(100 * F[reg][ky]["oct"]) if ky in F[reg] and not math.isnan(F[reg][ky]["oct"]) else None,
                               "rank_driest": rank, "years": len(jjas), "monthly": monthly,
                               "history": {str(y): round(v) for y, v in jjas.items()}, "area_share": round(w.get(reg, 0) / sum(w.values()), 3) if w else None}
        for y, v in jjas.items():
            idx.setdefault(y, []).append((F[reg][y]["jjas"], w.get(reg, 0)))
    out["cotton_area_index"] = {str(y): round(100 * sum(a * b for a, b in v) / sum(b for _, b in v)) for y, v in sorted(idx.items()) if sum(b for _, b in v)}
    return out


if __name__ == "__main__":
    main()
