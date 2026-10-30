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
        "Each region's normal yield: the average of its previous three seasons",
        "June-July rainfall and the August-September rainfall shortfall at the main cotton districts, against the 1991-2020 normal (NASA POWER)"]


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
            prev = [H[p]["regions"][reg]["yield"] for p in range(y - BASE_N, y) if p in H and reg in H[p]["regions"] and H[p]["regions"][reg].get("yield")]
            if len(prev) < BASE_N:
                continue
            base = float(np.mean(prev))
            f = F[reg][y - 1]
            if any(math.isnan(f[w]) for w in ("jj", "as")):
                continue
            rf = 0.0 if reg in IRRIGATED else 1.0
            X.append(feat(f, rf))
            yv.append(math.log(H[y]["regions"][reg]["yield"] / base))
            meta.append((y, reg, base, H[y]["regions"][reg]["area"]))
    return np.array(X), np.array(yv), meta


BASE_N = 3              # normal yield = average of the previous three seasons (tracks the post-2016 slide better than five)
FIT_FROM, TEST_FROM = 2008, 2011   # after Bt cotton reached most of the area


def feat(f, rf):
    """June-July rain vs normal, August-September shortfall (only a deficit counts), irrigated flag."""
    return [rf * f["jj"], rf * min(f["as"], 0), 1 - rf]


def fit(X, y, w=None, lam=0.3):
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
    for s in sorted({m[0] for m in meta if m[0] >= TEST_FROM}):
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
    short = lambda s: s if len(s) == 7 else f"{s[:4]}-{s[-2:]}"          # 2025-2026 -> 2025-26
    for s, r in (cocpc or {}).items():
        out["cocpc"][short(s)] = {"lakh": from_cocpc(r), "remark": r.get("remark")}
    by_season = {}
    for k, r in sorted((cai or {}).items()):
        if r.get("crop"):
            by_season.setdefault(short(r["season"]), []).append((k, r))
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
    """Monthly tonnes (all HS lines summed); a zero month is a month not yet reported."""
    if not tr:
        return {}
    out = {"unit": "tonnes"}
    for k in ("raw_export", "raw_import", "yarn_export"):
        rows = {}
        for m, v in sorted((tr.get(k) or {}).items()):
            t = sum(x or 0 for x in (v.get("u0") or {}).values())
            rows[m] = {"season": v["season"], "t": round(t) if t > 0 else None, "by_hs": v.get("u0")}
        out[k] = rows
        byS = {}
        for m, v in rows.items():
            if v["t"]:
                byS.setdefault(v["season"], {})[m] = v["t"]
        ss = sorted(byS)
        if len(ss) >= 2:
            cur, prev = ss[-1], ss[-2]
            n = len(byS[cur]); months = sorted(int(m[5:]) for m in byS[cur])
            ytd = sum(byS[cur].values()); same = sum(t for m, t in byS[prev].items() if int(m[5:]) in months)
            out[k + "_ytd"] = {"season": cur, "months": n, "last": max(byS[cur]), "t": ytd, "prev_same": same, "prev_season": prev,
                               "prev_total": sum(byS[prev].values()), "chg_pct": round(100 * (ytd / same - 1), 1) if same else None,
                               "m480": round(ytd * 1000 / 217.7243 / 1e6, 2) if k.startswith("raw") else None}
    return out


def season_trade(T, key, start=10):
    """Raw cotton (HS 5201) by season in lakh 170-kg bales from customs tonnes (COCPC uses the same customs series).
    Missing months of the latest season are filled at the average of its last three reported months."""
    by = {}
    for m, v in (T.get(key) or {}).items():
        t = (v.get("by_hs") or {}).get("5201") or 0
        if t > 0:
            y, mo = int(m[:4]), int(m[5:])
            sy = y if mo >= start else y - 1
            by.setdefault(f"{sy}-{(sy + 1) % 100:02d}", {})[m] = t / 17000
    out = {}
    for sn, mm in sorted(by.items()):
        n = len(mm); last3 = [mm[k] for k in sorted(mm)[-3:]]
        fill = (12 - n) * float(np.mean(last3)) if n < 12 else 0.0
        out[sn] = {"actual": round(sum(mm.values()), 1), "months": n, "through": max(mm), "projected": round(sum(mm.values()) + fill, 1),
                   "pace_month": round(float(np.mean(last3)), 2)}
    return out


DUTY_FREE = [("2000-01-01", "2021-02-01"), ("2022-04-14", "2022-10-31"), ("2025-08-19", "2025-12-31"), ("2026-06-01", "2026-10-31")]   # 11% duty otherwise (notified)


def is_free(ym, extra_until=None):
    d = f"{ym}-15"
    if any(a <= d <= b for a, b in DUTY_FREE):
        return True
    return bool(extra_until) and DUTY_FREE[-1][1] < d <= extra_until


def import_scenarios(T, season, notes):
    """USDA-year (Aug-Jul) raw cotton imports, m 480-lb bales, from monthly customs behaviour around the duty:
    duty-free pace = last three duty-free months reported; duty pace = last five duty months; before each duty return importers
    pull shipments forward (Dec 2025 = 2.0x the three months before), and the first duty month still carries ~30% of that rush."""
    mon = {}
    for mm, v in (T.get("raw_import") or {}).items():
        t = (v.get("by_hs") or {}).get("5201") or 0
        if t > 0:
            mon[mm] = t / 17000 * LAKH170_TO_M480
    ks = sorted(mon)
    free_m = [mon[k] for k in ks if is_free(k)][-3:]
    duty_m = [mon[k] for k in ks if not is_free(k)][-5:]
    fp, dp = float(np.mean(free_m)), float(np.mean(duty_m))
    y0 = int(season[:4])
    months = [f"{y0 + (1 if mo < 8 else 0)}-{mo:02d}" for mo in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7)]
    def path(until, rush):
        tot, out = 0.0, []
        last_free = max([m for m in months if is_free(m, until)], default=None)
        for i, m in enumerate(months):
            if m in mon:
                v = mon[m]
            elif is_free(m, until):
                v = fp * (2.0 if rush and m == last_free else 1.0)
            else:
                prev = months[i - 1] if i else None
                v = dp + (0.3 * fp * 2.0 if rush and prev == last_free and prev not in mon else 0.0)
            out.append(round(v, 2)); tot += v
        return round(tot, 2), out
    ext = (notes or {}).get("duty_expected_until", "2026-12-31")
    sc = {"notified": {"label": f"Duty back after {DUTY_FREE[-1][1]} (as notified), no rush"},
          "expected": {"label": f"Duty-free to {ext} (expected), year-end rush, then duty"},
          "all_year": {"label": "Duty-free all season (short crop keeps the waiver going)"}}
    sc["notified"]["m480"], sc["notified"]["path"] = path(None, False)
    sc["expected"]["m480"], sc["expected"]["path"] = path(ext, True)
    sc["all_year"]["m480"], sc["all_year"]["path"] = path(f"{y0 + 1}-07-31", False)
    return {"months": months, "free_pace": round(fp, 2), "duty_pace": round(dp, 2), "reported": [m for m in months if m in mon], "scenarios": sc}


def desk_balance(page):
    """Desk balance sheet for the new season (lakh 170-kg bales), built twice: on the official COCPC sheet and on CAI's.
    Last season's closing stock is corrected for actual customs imports and exports; the new season takes the desk crop,
    imports and exports at the current customs pace, and consumption held at last season's level of each sheet."""
    B, T, P = page["balance"], page["trade"], page["projection"]
    imp, exp = season_trade(T, "raw_import"), season_trade(T, "raw_export")
    new = P["season"]; prev = f"{int(new[:4]) - 1}-{new[2:4]}"
    out = {"season": new, "prev": prev, "imports_customs": imp, "exports_customs": exp, "cases": {}}
    for src in ("cocpc", "cai"):
        b = (B[src].get(prev) or {}).get("lakh")
        if not b or prev not in imp:
            continue
        di = imp[prev]["projected"] - (b["imports"] or 0)
        de = exp.get(prev, {}).get("projected", b["exports"] or 0) - (b["exports"] or 0)
        open_adj = b["closing"] + di - de
        # new season trade: its own months so far plus the recent pace, or last season's total until data arrive
        im_new = imp[new]["projected"] if new in imp else imp[prev]["projected"]
        ex_new = exp[new]["projected"] if new in exp else exp.get(prev, {}).get("projected", b["exports"])
        cons = b["consumption"]
        close = open_adj + P["lakh"] + im_new - cons - ex_new
        su_prev = open_adj / (cons + exp.get(prev, {}).get("projected", b["exports"]))
        need = su_prev * (cons + ex_new) - (open_adj + P["lakh"] - cons - ex_new)
        lakh = {"opening": round(open_adj, 1), "crop": P["lakh"], "imports": round(im_new, 1), "supply": round(open_adj + P["lakh"] + im_new, 1),
                "consumption": round(cons, 1), "exports": round(ex_new, 1), "closing": round(close, 1)}
        out["cases"][src] = {"lakh": lakh, "m480": {k: m480(v) for k, v in lakh.items()}, "stocks_use": round(100 * close / (cons + ex_new), 1),
                             "prev_closing_sheet": b["closing"], "prev_closing_adj": round(open_adj, 1), "prev_imports_sheet": b["imports"], "prev_exports_sheet": b["exports"],
                             "imports_to_hold_stocks_use": round(need, 1), "imports_to_hold_m480": m480(need), "prev_stocks_use": round(100 * su_prev, 1)}
    # USDA year (August-July): USDA's last season as published, the new season from the desk crop and customs trade
    U = B["usda"]; uprev = U.get(prev, {}).get("m480"); ucur = U.get(new, {}).get("m480")
    if uprev and ucur:
        ui, ue = season_trade(T, "raw_import", 8), season_trade(T, "raw_export", 8)
        IS = import_scenarios(T, new, page.get("notes"))
        out["import_scenarios"] = IS
        im = IS["scenarios"]["expected"]["m480"] / LAKH170_TO_M480
        ex = (ue[new]["projected"] if new in ue else ue.get(prev, {}).get("projected")) or 0
        lk = lambda v: v / LAKH170_TO_M480
        m = {"opening": uprev["closing"], "crop": P["m480"], "imports": m480(im), "consumption": ucur["consumption"], "exports": m480(ex)}
        m["supply"] = round(m["opening"] + m["crop"] + m["imports"], 2)
        m["closing"] = round(m["supply"] - m["consumption"] - m["exports"], 2)
        for k, v in IS["scenarios"].items():
            v["closing_m480"] = round(m["opening"] + m["crop"] + v["m480"] - m["consumption"] - m["exports"], 2)
            v["stocks_use"] = round(100 * v["closing_m480"] / (m["consumption"] + m["exports"]), 1)
        out["cases"]["usda"] = {"m480": m, "lakh": {k: round(lk(v), 1) for k, v in m.items()}, "stocks_use": round(100 * m["closing"] / (m["consumption"] + m["exports"]), 1),
                                "usda_closing": ucur["closing"], "usda_imports": ucur["imports"], "usda_exports": ucur["exports"],
                                "imports_months": ui.get(new, {}).get("months", 0), "prev_customs_imports_m480": m480(ui.get(prev, {}).get("actual")),
                                "prev_usda_imports": uprev["imports"]}
    return out


def brief(page, F):
    P, R, X, B, T = page["projection"], page["rain"], page["prices"].get("latest", {}), page["balance"], page["trade"]
    regs = sorted(P["regions"], key=lambda r: r["prod_m480"] - r["last_prod_lakh"] * LAKH170_TO_M480)
    worst = [r for r in regs if not r["irrigated"] and r["yield_vs_normal_pct"] <= -5][:4]
    out = []
    chg = 100 * (P["m480"] / P["last_season"]["m480"] - 1)
    out.append({"h": "Crop", "t": f"Desk projection **{P['m480']:.1f} m 480-lb bales** ({P['lakh']:.0f} lakh Indian bales) for {P['season']}, range {P['lo_m480']:.1f}–{P['hi_m480']:.1f}, "
                f"vs USDA {P['usda_m480']:.1f} and {P['last_season']['m480']:.1f} last season ({chg:+.0f}%). Area is about flat ({P['area_change_pct']:+.1f}%), so the cut is yield: "
                + ", ".join(f"{r['region']} {r['yield_vs_normal_pct']:+.0f}% (Aug–Sep rain {r['rain_as_pct']:+.0f}%)" for r in worst) + "."})
    ix = R.get("cotton_area_index", {}); ky = str(R.get("kharif_year"))
    if ky in ix:
        order = sorted(ix, key=lambda y: ix[y]); rk = order.index(ky) + 1
        drier = sorted(order[:rk - 1])
        mh = R["regions"].get("Maharashtra", {})
        out.append({"h": "Monsoon", "t": f"June–September rain across the cotton areas was {ix[ky]:+d}% vs the {R['normal']} normal, the {rk}{'th' if rk > 3 else ['st','nd','rd'][rk-1]} driest of {len(ix)} years"
                    + (f" (drier only in {', '.join(drier)})" if drier else "") + f". Maharashtra, a third of India's cotton area, had {mh.get('jjas_pct', 0):+d}%, "
                    + (f"the driest since at least {min(map(int, mh['history']))}" if mh.get("rank_driest") == 1 else f"rank {mh.get('rank_driest')} of {mh.get('years')}") +
                    f", with August–September {mh.get('as_pct', 0):+d}% when bolls fill. October has been dry as well, which helps picking but not yield."})
    cc, ca = B["cocpc"].get(max(B["cocpc"])) if B["cocpc"] else None, B["cai"].get(max(B["cai"])) if B["cai"] else None
    if cc and ca:
        out.append({"h": "Stocks", "t": f"For {max(B['cai'])} the official COCPC sheet ends with {cc['m480']['closing']:.1f} m bales of stock and the trade's CAI sheet ({ca['as_of']}) with "
                    f"{ca['m480']['closing']:.1f} m; they differ mainly on the crop ({cc['m480']['crop']:.1f} vs {ca['m480']['crop']:.1f} m). A crop near the desk number would pull 2026-27 stocks down from either level."})
    im, ex = T.get("raw_import_ytd"), T.get("raw_export_ytd")
    if im:
        out.append({"h": "Trade", "t": f"Raw cotton imports {im['season']} through {im['last']}: {im['t']/1e6:.2f} mt ({im['m480']:.1f} m bales), {im['chg_pct']:+.0f}% on the same months of {im['prev_season']}"
                    + (f"; exports {ex['t']/1e3:.0f} kt ({ex['chg_pct']:+.0f}%)" if ex else "") + ". India has turned into a steady importer."})
    if X:
        M = page["prices"].get("msp") or {}
        out.append({"h": "Price", "t": f"Shankar-6 ₹{X['rs_candy']:,}/candy = {X['clb']:.1f}¢/lb ({X['date']}), {X['premium_ice']:+.1f}¢ over ICE nearby and {X['chg_1y_pct']:+.0f}% on a year ago"
                    + (f"; the MSP floor works out to about {M['lint_clb']:.0f}¢/lb lint, so CCI support sits just under the market" if M else "") + ". Indian cotton is dear against the world."})
    DB = page.get("desk_balance", {})
    c = DB.get("cases", {}).get("cocpc")
    if c:
        pi = DB["imports_customs"][DB["prev"]]
        out.append({"h": "Balance sheet", "t": f"Customs data show {DB['prev']} imports of {pi['actual']:.1f} lakh bales through {pi['through']} (about {pi['projected']:.0f} for the season at the recent pace) "
                    f"vs {c['prev_imports_sheet']:.0f} in the official COCPC sheet, so last season's closing stock is nearer {c['prev_closing_adj']:.0f} lakh than {c['prev_closing_sheet']:.0f}. "
                    f"With the desk crop, imports and exports at the customs pace and use held at last season's level, {DB['season']} ends with **{c['m480']['closing']:.1f} m 480-lb bales** "
                    f"({c['lakh']['closing']:.0f} lakh; stocks/use {c['stocks_use']:.0f}% vs {c['prev_stocks_use']:.0f}%). Holding last season's stocks/use would take about {c['imports_to_hold_m480']:.1f} m bales of imports "
                    f"({c['imports_to_hold_stocks_use']:.0f} lakh), against USDA's {page['balance']['usda'].get(DB['season'], {}).get('m480', {}).get('imports', 0):.1f} m."})
    u = DB.get("cases", {}).get("usda")
    if u:
        S = DB["import_scenarios"]["scenarios"]
        out.append({"h": "Imports and the duty", "t": f"Customs data show imports run at about {DB['import_scenarios']['free_pace']:.2f} m bales a month duty-free and {DB['import_scenarios']['duty_pace']:.2f} m with the 11% duty, "
                    f"with a rush before each deadline (December 2025 was double the months before, then imports fell to 0.08 m in February). Keeping USDA's {DB['prev']} and its {DB['season']} use ({u['m480']['consumption']:.1f} m), "
                    f"with the desk crop ({u['m480']['crop']:.1f} m): if the duty returns in November as notified, imports are **{S['notified']['m480']:.1f} m** (about USDA's {u['usda_imports']:.1f} m, so that is the floor) and ending stocks {S['notified']['closing_m480']:.1f} m; "
                    f"duty-free to December as expected, **{S['expected']['m480']:.1f} m** and {S['expected']['closing_m480']:.1f} m; duty-free all season, **{S['all_year']['m480']:.1f} m** and {S['all_year']['closing_m480']:.1f} m (USDA {u['usda_closing']:.1f} m). "
                    f"So imports rise a lot only if the waiver runs well past December; each extra duty-free month adds roughly {DB['import_scenarios']['free_pace'] - DB['import_scenarios']['duty_pace']:.2f} m."})
    cci = (page.get("notes") or {}).get("cci")
    if cci:
        left = cci["procured"] - cci["sold"]
        out.append({"h": "Government stocks (CCI)", "t": f"The Cotton Corporation of India bought {cci['procured']:.0f} lakh bales of the {cci['season']} crop at MSP and had sold {cci['sold']:.0f} lakh by {cci['as_of']}, "
                    f"leaving about {left:.0f} lakh ({m480(left):.1f} m bales); at its recent pace of about {cci['weekly']:.1f} lakh a week the reserve is close to empty, so carry-in stocks sit with mills and traders, not the government. "
                    f"New-crop buying at the {page['prices'].get('msp', {}).get('kapas_medium', 0):,} rupee MSP started in October; with Shankar-6 above the MSP-implied lint cost, CCI should buy less than last season unless prices fall."})
    out.append({"h": "For US cotton", "t": "A smaller Indian crop, duty-free imports (waiver expected through December) and Indian prices well above ICE all point to more Indian import demand in 2026-27 than USDA's number, with US and Brazilian cotton the main suppliers."})
    return out


def main():
    cab = jl("cab_area_production", {})
    rain = jl("rain", {"districts": {}})
    H = region_history(cab)
    R = rain_tables(rain)
    F, normals = rain_features(R)
    yrs = sorted(y for y in H if y >= FIT_FROM)
    res, stats = backtest(H, F, yrs)
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
        prev = [H[p]["regions"][reg]["yield"] for p in range(sy - BASE_N, sy) if p in H and reg in H[p]["regions"]]
        base = float(np.mean(prev))
        f = F[reg][ky]
        rf = 0.0 if reg in IRRIGATED else 1.0
        x = np.array([feat(f, rf)])
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
    page["desk_balance"] = desk_balance(page)
    page["brief"] = brief(page, F)
    (D / "india.json").write_text(json.dumps(page, separators=(",", ":"), default=float))
    (D / "model_eval.json").write_text(json.dumps({"coef": [round(float(v), 4) for v in b], "names": ["const", "jj", "as_shortfall", "irrigated"], "base_n": BASE_N, "fit_from": FIT_FROM,
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
