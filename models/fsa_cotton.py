#!/usr/bin/env python3
"""FSA crop acreage → cotton planted, harvested and production. Port of BMR-Com/cotton-crop-progress, unchanged:

  A. scripts/model.py  fsa_model()          FSA upland planted + failed → NASS planted (state ratio at the same release
                                            month) and failed share → harvested share;
                       abandonment_model()  final abandonment from FSA failed share, D2–D4 drought and poor/very-poor
                                            ratings, state means removed, every past season at the same release month.
  B. scripts/crop_projection/run.py, Texas  final Texas abandonment from drought + ratings, and (conditional view) from
                                            ratings + FSA failed share so far, averaged; Texas built as planted x
                                            (1 - abandonment) x USDA's in-season yield, with ranges from past seasons'
                                            joint abandonment and yield misses; the FSA failed-share note.

Only the FSA collector lives in this desk (pipelines/fsa.py → data/fsa/fsa_cotton_state.csv). The other inputs are read
from a checkout of cotton-crop-progress (CCP_DIR, default .cache/ccp; the fsa workflow sparse-clones it), so no second
collector runs: NASS weekly condition/progress (data/cotton_*.csv), NASS annual (data/ginning/annual.csv) and cotton-area
drought (data/drought/cotton_area_drought.csv). Parameters are the source's.

Not ported: the ginnings model (scripts/crop_projection/model2.py), so the source's US conditional total (Texas + the
ginnings-model rest of the US) is not rebuilt here; the US view below is method A summed over states.

Added (desk): production = harvested x USDA's in-season state yield; a walk-forward backtest at the same point of the
season (FSA releases known by then, models fitted on earlier seasons only) against NASS final and against USDA's own
estimate in the same month.

Writes the build to .cache/fsa_build/cotton.json (models/fsa_check.py checks it; the workflow publishes it to
data/fsa/cotton.json only if the checks pass). Run: python models/fsa_cotton.py
"""
import json, math, os, sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
CCP = Path(os.environ.get("CCP_DIR") or ROOT / ".cache" / "ccp")
D = str(CCP / "data")
FSA_CSV = ROOT / "data" / "fsa" / "fsa_cotton_state.csv"
BUILD = ROOT / ".cache" / "fsa_build"
MIN_YEARS = 6

# ───────── loaders: cotton-crop-progress scripts/load.py (data dir = the checkout's data/) ─────────
STATE_NAME = {"AL": "Alabama", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "FL": "Florida", "GA": "Georgia",
              "KS": "Kansas", "LA": "Louisiana", "MS": "Mississippi", "MO": "Missouri", "NM": "New Mexico",
              "NC": "North Carolina", "OK": "Oklahoma", "SC": "South Carolina", "TN": "Tennessee", "TX": "Texas",
              "VA": "Virginia", "US": "United States"}
NAME_STATE = {v.upper(): k for k, v in STATE_NAME.items()}
COND_W = {"VERY POOR": 1, "POOR": 2, "FAIR": 3, "GOOD": 4, "EXCELLENT": 5}
MAIN = ["TX", "GA", "AR", "MS", "AL", "NC", "OK", "MO", "TN", "SC", "LA", "KS", "AZ", "CA", "NM", "FL", "VA"]
DROUGHT_RAW = "https://raw.githubusercontent.com/BMR-Com/drought-monitor/main/data/state/{s}.csv"
ORDER = ["YEAR - MAR ACREAGE", "YEAR - JUN ACREAGE", "YEAR - AUG FORECAST", "YEAR - SEP FORECAST", "YEAR - OCT FORECAST",
         "YEAR - NOV FORECAST", "YEAR - DEC FORECAST", "YEAR"]


def nass_weekly():
    import glob
    fr = []
    for f in sorted(glob.glob(os.path.join(D, "cotton_*.csv"))):
        fr.append(pd.read_csv(f, usecols=["year", "state_alpha", "short_desc", "week_ending", "Value"], low_memory=False))
    d = pd.concat(fr, ignore_index=True)
    d = d[~d.short_desc.str.contains("5 YEAR|PREVIOUS YEAR", regex=True)]
    d["v"] = pd.to_numeric(d.Value.astype(str).str.replace(",", ""), errors="coerce")
    d["week_ending"] = pd.to_datetime(d.week_ending)
    d = d.dropna(subset=["v", "week_ending"])
    cond = d[d.short_desc.str.contains("CONDITION")].copy()
    cond["cat"] = cond.short_desc.str.extract(r"PCT (.*)$")[0]
    c = cond.pivot_table(index=["year", "state_alpha", "week_ending"], columns="cat", values="v", aggfunc="last").reset_index()
    c = c.dropna(subset=list(COND_W))
    c["ci"] = sum(c[k] * w for k, w in COND_W.items()) / 100.0
    c["ge"] = c["GOOD"] + c["EXCELLENT"]
    c["pvp"] = c["POOR"] + c["VERY POOR"]
    c.rename(columns={"state_alpha": "state"}, inplace=True)
    c["woy"] = c.week_ending.dt.isocalendar().week.astype(int)
    return c


def drought(states):
    import io
    import requests
    ap = os.path.join(D, "drought", "cotton_area_drought.csv")
    a = pd.read_csv(ap) if os.path.exists(ap) else pd.DataFrame(columns=["location"])
    have = set(a.location)
    out = []
    for s in states:                      # whole-state USDM only for states the cotton-area file lacks (as the source)
        if s == "US" or s in have:
            continue
        try:
            t = pd.read_csv(io.StringIO(requests.get(DROUGHT_RAW.format(s=s), timeout=60).text))
            t["state"] = s
            out.append(t)
        except Exception as e:
            print("drought missing", s, e)
    d = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["state", "Week", "D1-D4", "D2-D4", "D3-D4"])
    a = a[a.location.isin(states) & (a.location != "US")]
    if len(a):
        a = a.rename(columns={"location": "state", "week": "Week", "d1": "D1-D4", "d2": "D2-D4", "d3": "D3-D4"})
        a = a[["state", "Week", "D1-D4", "D2-D4", "D3-D4"]]
        d = pd.concat([d[~d.state.isin(set(a.state))], a], ignore_index=True) if out else a.copy()
    for c in ("D1-D4", "D2-D4", "D3-D4"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["week"] = pd.to_datetime(d.Week)
    d["year"] = d.week.dt.year
    d["woy"] = d.week.dt.isocalendar().week.astype(int)
    return d.rename(columns={"D2-D4": "d2", "D1-D4": "d1", "D3-D4": "d3"})[["state", "week", "year", "woy", "d1", "d2", "d3"]]


def annual():
    a = pd.read_csv(os.path.join(D, "ginning", "annual.csv"))
    if "period" not in a.columns:
        a["period"] = "YEAR"
    return a


def pick(a, item, year=None, final_only=False):
    x = a[a.item == item].copy()
    if year is not None:
        x = x[x.year == year]
    if final_only:
        x = x[x.period == "YEAR"]
    x["rank"] = x.period.map({p: i for i, p in enumerate(ORDER)}).fillna(-1)
    x = x.sort_values("rank").groupby(["year", "state"]).tail(1)
    return x.set_index(["year", "state"]).value


_FSA = None                                   # backtest swaps in the FSA rows known at that point of the season


def fsa_frame():
    return (_FSA if _FSA is not None else pd.read_csv(FSA_CSV)).copy()


# ───────── scripts/model.py (unchanged apart from reading FSA through fsa_frame()) ─────────
def _ols(X, y, w):
    W = np.sqrt(w)[:, None]
    beta, *_ = np.linalg.lstsq(X * W, y * W[:, 0], rcond=None)
    return beta


def _week_features(cond, dr, years, wk):
    c = cond[(cond.woy >= 26) & (cond.woy <= wk) & cond.year.isin(years)]
    f = c.groupby(["year", "state"]).agg(ci=("ci", "mean"), pvp=("pvp", "mean"), n=("ci", "size"))
    last = cond[(cond.woy <= wk) & (cond.woy >= wk - 2) & cond.year.isin(years)].sort_values("woy").groupby(["year", "state"]).ci.last()
    f["ci_now"] = last
    d = dr[(dr.woy >= 22) & (dr.woy <= min(wk, 44)) & dr.year.isin(years)].groupby(["year", "state"]).d2.mean()
    f["d2"] = d
    return f[f.n >= 3]


def fsa_model(ann, cur):
    f = fsa_frame()
    f = f[f.type.astype(str).str.upper().str.contains("UPLAND")].copy()
    f["st"] = f.state.astype(str).str.upper().map(NAME_STATE)
    f["rm"] = pd.to_datetime(f.release).dt.month
    g = f.groupby(["crop_year", "release", "rm", "st"])[["planted", "failed"]].sum().reset_index()
    irr = f[f.irr == "N"].groupby(["crop_year", "release", "st"])[["planted", "failed"]].sum()
    g["tot"] = g.planted + g.failed
    g["fs"] = g.failed / g.tot
    pl = pick(ann, "upland_planted", final_only=True)
    hv = pick(ann, "upland_harvested", final_only=True)
    g["npl"] = [pl.get((y, s)) if y < cur else None for y, s in zip(g.crop_year, g.st)]
    g["nhv"] = [hv.get((y, s)) if y < cur else None for y, s in zip(g.crop_year, g.st)]
    g["ratio"] = g.npl / g.tot
    g["ab"] = 1 - g.nhv / g.npl
    hist = g.dropna(subset=["npl", "nhv"])
    med = hist.groupby("st").ratio.median()
    hist = hist[(hist.ratio / hist.st.map(med)).between(0.7, 1.4)]
    now = g[g.crop_year == cur]
    if not len(now):
        return None
    rel = now.release.max()
    rm = int(pd.to_datetime(rel).month)
    now = now[now.release == rel]
    hx = hist[hist.rm == rm] if (hist.rm == rm).sum() >= 30 else hist
    b = np.polyfit(hx.fs, hx.ab, 1, w=np.sqrt(hx.npl))
    resid = (hx.ab - np.polyval(b, hx.fs)).groupby(hx.st).mean()
    e = []
    for y in sorted(hx.crop_year.unique()):
        tr, te = hx[hx.crop_year != y], hx[hx.crop_year == y]
        bb = np.polyfit(tr.fs, tr.ab, 1, w=np.sqrt(tr.npl))
        rr = (tr.ab - np.polyval(bb, tr.fs)).groupby(tr.st).mean()
        e += [((np.polyval(bb, r.fs) + 0.8 * rr.get(r.st, 0)) - r.ab, r.npl) for _, r in te.iterrows()]
    e = np.array(e)
    sd = float(np.sqrt(np.average(e[:, 0] ** 2, weights=e[:, 1]))) if len(e) else 0.12
    rmed = hist[hist.rm == rm].groupby("st").ratio.median() if (hist.rm == rm).any() else med
    out = {}
    for _, r in now.iterrows():
        k = rmed.get(r.st, med.get(r.st, 1.02))
        ab = float(np.clip(np.polyval(b, r.fs) + 0.8 * resid.get(r.st, 0), 0, 0.95))
        dry = irr.loc[(cur, rel, r.st)] if (cur, rel, r.st) in irr.index else None
        out[r.st] = {"fsa_planted": r.planted, "fsa_failed": r.failed, "fsa_total": r.tot, "fail_share": r.fs,
                     "planted_adj": r.tot * k, "scale": k, "hr_fsa": 1 - ab,
                     "dry_fail_share": float(dry.failed / (dry.planted + dry.failed)) if dry is not None and (dry.planted + dry.failed) > 0 else None}
    return {"states": out, "release": rel, "sd_hr": sd}


def abandonment_model(cond, dr, ann, fm, cur, wk):
    if fm is None:
        return None
    f = fsa_frame()
    f = f[f.type.astype(str).str.upper().str.contains("UPLAND")].copy()
    f["st"] = f.state.astype(str).str.upper().map(NAME_STATE)
    f["rm"] = pd.to_datetime(f.release).dt.month
    rm = int(pd.to_datetime(fm["release"]).month)
    g = f[f.rm == rm].groupby(["crop_year", "st"])[["planted", "failed"]].sum().reset_index()
    g["fs"] = g.failed / (g.planted + g.failed)
    F = _week_features(cond, dr, sorted(set(cond.year)), min(wk, 44)).reset_index().rename(columns={"year": "crop_year", "state": "st"})
    g = g.merge(F[["crop_year", "st", "pvp", "d2"]], on=["crop_year", "st"], how="left")
    g["d2"] = g.d2.fillna(0)
    pl = pick(ann, "upland_planted", final_only=True)
    hv = pick(ann, "upland_harvested", final_only=True)
    g["npl"] = [pl.get((y, s)) if y < cur else None for y, s in zip(g.crop_year, g.st)]
    g["ab"] = [1 - hv.get((y, s)) / pl.get((y, s)) if y < cur and hv.get((y, s)) and pl.get((y, s)) else None for y, s in zip(g.crop_year, g.st)]
    feats = ["fs", "d2", "pvp"]
    hist = g[(g.crop_year < cur)].dropna(subset=feats + ["ab", "npl"])
    hist = hist[hist.npl > 20000]
    if hist.crop_year.nunique() < 6:
        return None

    def fit(tr):
        m = tr.groupby("st")[feats + ["ab"]].mean()
        X = np.c_[np.ones(len(tr)), tr[feats].values - m.loc[tr.st, feats].values]
        b = _ols(X, (tr.ab.values - m.loc[tr.st, "ab"].values), tr.npl.values)
        return b, m

    def pred(row, b, m, tr):
        base = m.loc[row.st] if row.st in m.index else tr[feats + ["ab"]].mean()
        x = np.r_[1, np.array([row[c] for c in feats], float) - base[feats].values.astype(float)]
        return float(np.clip(base.ab + x @ b, 0, 0.95))

    err, loo = [], {}
    for y in sorted(hist.crop_year.unique()):
        tr, te = hist[hist.crop_year != y], hist[hist.crop_year == y]
        b, m = fit(tr)
        for _, r in te.iterrows():
            pa = pred(r, b, m, tr)
            loo[(int(y), r.st)] = pa
            err.append((pa - r.ab, r.npl))
    e = np.array(err)
    sd = float(np.sqrt(np.average(e[:, 0] ** 2, weights=e[:, 1])))
    b, m = fit(hist)
    out = {}
    for _, r in g[g.crop_year == cur].dropna(subset=["fs"]).iterrows():
        rr = r.copy()
        rr["pvp"] = rr.pvp if not pd.isna(rr.pvp) else hist[hist.st == r.st].pvp.mean()
        out[r.st] = {"ab_final": pred(rr, b, m, hist), "fs_now": r.fs, "ab_avg": float(m.loc[r.st, "ab"]) if r.st in m.index else None}
    tx = hist[hist.st == "TX"].sort_values("crop_year")
    hist_tx = [{"year": int(r.crop_year), "fs": r.fs, "d2": r.d2, "pvp": r.pvp, "ab": r.ab} for _, r in tx.iterrows()]
    return {"states": out, "sd": sd, "release_month": rm, "tx_history": hist_tx, "loo_ab": loo}


# ───────── scripts/crop_projection/run.py, Texas section (unchanged; ginnings-model parts left out) ─────────
def tmult(p, n):
    return stats.t.ppf(0.5 + p / 2, n - 1) * math.sqrt(1 + 1 / n)


def asof_monday(cur, today):
    """run.py's as-of date: the latest Monday on the weekly grid (first Monday on/after 1 Sep, then weekly) up to today+1."""
    d0 = pd.Timestamp(cur, 9, 1)
    d0 = d0 + pd.Timedelta(days=(7 - d0.weekday()) % 7)
    grid = [d0 + pd.Timedelta(days=7 * k) for k in range(20)]
    ok = [x for x in grid if x <= today + pd.Timedelta(days=1)]
    return ok[-1] if ok else grid[0]


def texas(cond, dr, ann, cur, asof_D):
    pl = pick(ann, "upland_planted", final_only=True)
    hv = pick(ann, "upland_harvested", final_only=True)
    prod = pick(ann, "upland_prod", final_only=True)
    fsa_tx = fsa_frame()
    fsa_tx = fsa_tx[fsa_tx.type.str.contains("UPLAND") & ~fsa_tx.type.str.contains("SEED") & (fsa_tx.state.str.upper() == "TEXAS")].copy()
    fsa_tx["rel"] = pd.to_datetime(fsa_tx.release)

    def fsa_share(y, t):
        f = fsa_tx[(fsa_tx.crop_year == y) & (fsa_tx.rel <= t)]
        if not len(f):
            return np.nan
        l = f[f.rel == f.rel.max()]
        return float(l.failed.sum() / (l.planted.sum() + l.failed.sum()))

    def tx_feats(y, t):
        d = dr[(dr.location == "TX") & (dr.week >= pd.Timestamp(y, 5, 1)) & (dr.week <= min(t, pd.Timestamp(y, 10, 31)))]
        c = cond[(cond.year == y) & (cond.state == "TX") & (cond.week_ending <= t)].sort_values("week_ending")
        return {"d2": d.d2.mean(), "pvp_now": c.pvp.iloc[-1] if len(c) else np.nan, "fsa": fsa_share(y, t)}

    def usda_latest(y, item, st, before=None):
        x = ann[(ann.year == y) & (ann.state == st) & (ann.item == item) & ann.period.str.contains("FORECAST|ACREAGE")].copy()
        if before is not None and "load_time" in x:
            x = x[pd.to_datetime(x.load_time) <= before]
        if not len(x):
            return np.nan
        return float(x.sort_values("load_time").value.iloc[-1]) if "load_time" in x else float(x.value.iloc[-1])

    md = (asof_D.month, asof_D.day)
    T = []
    for y in range(2001, cur + 1):
        t = pd.Timestamp(y, *md) - pd.Timedelta(days=1)
        f = tx_feats(y, t)
        planted = pl.get((y, "TX")) if y < cur else usda_latest(y, "upland_planted", "TX")
        T.append({"year": y, **f, "planted": planted,
                  "ab": 1 - hv.get((y, "TX"), np.nan) / pl.get((y, "TX")) if y < cur and (y, "TX") in pl.index else np.nan,
                  "P": prod.get((y, "TX"), np.nan) if y < cur else np.nan,
                  "uy": usda_latest(y, "upland_yield", "TX", before=pd.Timestamp(y, *md))})
    T = pd.DataFrame(T).set_index("year")
    h = T[T.index < cur].dropna(subset=["ab", "d2", "pvp_now"])
    X = lambda D_: np.c_[np.ones(len(D_)), D_.d2, D_.pvp_now]
    ab_loo = pd.Series({y: float((X(h.loc[[y]]) @ np.linalg.lstsq(X(h.drop(y)), h.drop(y).ab, rcond=None)[0])[0]) for y in h.index})
    bA = np.linalg.lstsq(X(h), h.ab, rcond=None)[0]
    res = h.ab - X(h) @ bA
    s2 = float(res @ res / (len(h) - 3))
    x0 = np.r_[1, T.loc[cur, ["d2", "pvp_now"]].values.astype(float)]
    ab_now = float(np.clip(x0 @ bA, 0.02, 0.9))
    se_ab = math.sqrt(s2 * (1 + x0 @ np.linalg.inv(X(h).T @ X(h)) @ x0))
    ab_lo = max(0.0, ab_now - tmult(0.95, len(h)) / math.sqrt(1 + 1 / len(h)) * se_ab)
    ab_hi = min(0.95, ab_now + tmult(0.95, len(h)) / math.sqrt(1 + 1 / len(h)) * se_ab)

    cond_view = None
    hf = h.dropna(subset=["fsa"])
    if len(hf) >= 8 and np.isfinite(T.loc[cur, "fsa"]):
        XF = lambda D_: np.c_[np.ones(len(D_)), D_.pvp_now, D_.fsa]
        f_loo = pd.Series({y: float((XF(hf.loc[[y]]) @ np.linalg.lstsq(XF(hf.drop(y)), hf.drop(y).ab, rcond=None)[0])[0]) for y in hf.index})
        f_now = float(np.clip(np.r_[1, T.loc[cur, ["pvp_now", "fsa"]].values.astype(float)] @ np.linalg.lstsq(XF(hf), hf.ab, rcond=None)[0], 0.02, 0.9))
        comb = (ab_loo.loc[hf.index] + f_loo) / 2
        sd_c = float(np.sqrt(np.mean((hf.ab - comb) ** 2)))
        abc = (ab_now + f_now) / 2
        wc = tmult(0.95, len(hf)) * sd_c
        cond_view = {"ab": abc, "lo": max(0.0, abc - wc), "hi": min(0.95, abc + wc), "sd_pts": sd_c, "n": len(hf),
                     "ab_drought_ratings": ab_now, "ab_ratings_fsa": f_now}
    an = h[h.pvp_now >= T.loc[cur, "pvp_now"] - 7]
    analog = {"min": float(an.ab.min()), "max": float(an.ab.max()), "mean": float(an.ab.mean()), "n": int(len(an)),
              "pvp_from": float(T.loc[cur, "pvp_now"] - 7)} if len(an) >= 3 else None

    conditional = None
    if cond_view and np.isfinite(T.loc[cur, "uy"]):
        hy = T.loc[T.index < cur].dropna(subset=["ab", "uy"])
        hy = hy[hy.index.isin(ab_loo.index)]
        yfin = pick(ann, "upland_yield", final_only=True)
        ey = np.log(np.array([yfin.get((y, "TX"), np.nan) for y in hy.index]) / hy.uy.values)
        ea = (hy.ab - ab_loo.loc[hy.index]).values
        ok = np.isfinite(ey) & np.isfinite(ea)
        ey, ea = ey[ok], ea[ok]
        rng = np.random.default_rng(7)
        nd = 40000
        idx = rng.integers(len(ea), size=nd)
        a_d = np.clip(cond_view["ab"] + ea[idx] + rng.normal(0, ea.std() * 0.3, nd), 0.02, 0.95)
        y_d = T.loc[cur, "uy"] * np.exp(ey[idx] - ey.mean() + rng.normal(0, ey.std() * 0.3, nd))
        tx_d = T.loc[cur, "planted"] * (1 - a_d) * y_d / 480
        tx_c = float(T.loc[cur, "planted"] * (1 - cond_view["ab"]) * T.loc[cur, "uy"] / 480)
        q = lambda x: {"central": None, "lo68": float(np.percentile(x, 16)), "hi68": float(np.percentile(x, 84)),
                       "lo95": float(np.percentile(x, 2.5)), "hi95": float(np.percentile(x, 97.5)),
                       "lo99": float(np.percentile(x, 0.5)), "hi99": float(np.percentile(x, 99.5))}

        def mb(c, x):
            o = q(x); o["central"] = c
            return {k: round(v / 1e6, 3) for k, v in o.items()}
        conditional = {"tx_abandonment": {"central": round(cond_view["ab"], 3), "lo95": round(float(np.percentile(a_d, 2.5)), 3), "hi95": round(float(np.percentile(a_d, 97.5)), 3)},
                       "tx_harvested_acres": {"central": round(T.loc[cur, "planted"] * (1 - cond_view["ab"]) / 1e6, 3),
                                              "lo95": round(T.loc[cur, "planted"] * (1 - float(np.percentile(a_d, 97.5))) / 1e6, 3),
                                              "hi95": round(T.loc[cur, "planted"] * (1 - float(np.percentile(a_d, 2.5))) / 1e6, 3)},
                       "tx_planted_acres": round(T.loc[cur, "planted"] / 1e6, 3),
                       "tx_yield": {"central": round(float(T.loc[cur, "uy"])), "lo95": round(float(np.percentile(y_d, 2.5))), "hi95": round(float(np.percentile(y_d, 97.5)))},
                       "texas": mb(tx_c, tx_d), "analog": analog, "n_seasons": int(len(ea))}

    fsa_note = None
    f = fsa_tx[fsa_tx.crop_year == cur]
    if len(f):
        lr = f[f.release == f.release.max()]
        fs = lr.failed.sum() / (lr.planted.sum() + lr.failed.sum())
        fsa_note = {"release": str(lr.release.iloc[0]), "fail_share": float(fs),
                    "text": (f"Texas FSA failed acres ({pd.Timestamp(lr.release.iloc[0]):%B} release) are {fs * 100:.1f}% of planted. Failed acres are reported to FSA "
                             f"with a lag and the December–January releases settle them, so the abandonment projection uses this season's drought and "
                             f"ratings readings against what similar readings meant for final abandonment in past seasons.")}
    tx_hist = [{"year": int(y), "fsa_fail_share": None if pd.isna(r.fsa) else round(float(r.fsa), 4), "pvp": None if pd.isna(r.pvp_now) else float(r.pvp_now),
                "d2": None if pd.isna(r.d2) else round(float(r.d2), 1), "final_ab": None if pd.isna(r.ab) else round(float(r.ab), 4)}
               for y, r in T.iterrows() if y >= 2014]
    return {"asof_monday": str(asof_D.date()), "abandonment_drought_ratings": {"central": round(ab_now, 3), "lo95": round(ab_lo, 3), "hi95": round(ab_hi, 3)},
            "conditional_view": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in cond_view.items()} if cond_view else None,
            "conditional": conditional, "fsa_note": fsa_note, "history": tx_hist}


# ───────── desk additions: production, US totals, walk-forward backtest ─────────
SEASON = {"AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12, "JAN": 13}


def usda_same_month(ann, item, y, st, mon):
    """USDA's estimate as published in calendar month `mon` of the season (8..12, 13 = January): the latest
    in-season period whose month is not after it (March/June acreage count as before August)."""
    x = ann[(ann.year == y) & (ann.state == st) & (ann.item == item) & ann.period.str.contains("FORECAST|ACREAGE")]
    if not len(x):
        return None
    m = x.period.str.extract(r"- (\w{3}) ")[0].map({"MAR": 3, "JUN": 6, **SEASON})
    x = x.assign(m=m.values).dropna(subset=["m"])
    x = x[x.m <= mon]
    if not len(x):
        return None
    return float(x.sort_values("m").value.iloc[-1])


def season_month(rel):
    t = pd.Timestamp(rel)
    return t.month if t.month >= 8 else t.month + 12


def season_day(rel, crop_year):
    return (pd.Timestamp(rel) - pd.Timestamp(int(crop_year), 8, 1)).days


def build_states(fm, am, ann, cur, mon):
    rows = []
    for s, fs in fm["states"].items():
        if not isinstance(s, str):
            continue
        a = (am or {}).get("states", {}).get(s)
        ab = a["ab_final"] if a else 1 - fs["hr_fsa"]
        uy = usda_same_month(ann, "upland_yield", cur, s, mon)
        harv = fs["planted_adj"] * (1 - ab)
        rows.append({"st": s, "name": STATE_NAME.get(s, s), "fsa_planted": fs["fsa_planted"], "fsa_failed": fs["fsa_failed"],
                     "fsa_total": fs["fsa_total"], "fail_share": fs["fail_share"], "scale": fs["scale"],
                     "planted": fs["planted_adj"], "abandonment": ab, "ab_source": "fsa+drought+ratings" if a else "fsa failed share",
                     "hr_fsa": fs["hr_fsa"], "ab_avg": a["ab_avg"] if a else None, "harvested": harv,
                     "usda_yield": uy, "prod": harv * uy / 480 if uy else None,
                     "usda_planted": usda_same_month(ann, "upland_planted", cur, s, mon),
                     "usda_harvested": usda_same_month(ann, "upland_harvested", cur, s, mon),
                     "usda_prod": usda_same_month(ann, "upland_prod", cur, s, mon)})
    rows.sort(key=lambda r: -(r["planted"] or 0))
    return rows


def totals(rows):
    t = lambda k: float(sum(r[k] or 0 for r in rows if r[k] is not None))
    us = {k: t(k) for k in ("fsa_planted", "fsa_failed", "fsa_total", "planted", "harvested", "prod")}
    us["abandonment"] = 1 - us["harvested"] / us["planted"] if us["planted"] else None
    us["yield"] = us["prod"] * 480 / us["harvested"] if us["harvested"] else None
    return us


def backtest(cond, dr, ann, cur, rel_now, wk):
    """Each past season with an FSA release by the same point of the season: rebuild planted/harvested/production
    from the FSA rows known then, fitting on earlier seasons only, and compare with NASS final and USDA's same-month."""
    global _FSA
    full = pd.read_csv(FSA_CSV)
    sd_now = season_day(rel_now, cur)
    pl = pick(ann, "upland_planted", final_only=True)
    hv = pick(ann, "upland_harvested", final_only=True)
    pr = pick(ann, "upland_prod", final_only=True)
    out = []
    try:
        for y in sorted(full.crop_year.unique()):
            if y >= cur or (y, "US") not in pr.index:
                continue
            sub = full[full.crop_year < y].copy()
            fy = full[full.crop_year == y]
            fy = fy[[season_day(r, y) <= sd_now + 7 for r in fy.release]]
            if not len(fy):
                continue
            if sub.crop_year.nunique() < 3:          # too few earlier seasons to fit the FSA relations
                continue
            _FSA = pd.concat([sub, fy], ignore_index=True)
            fm = fsa_model(ann, y)
            if fm is None:
                continue
            am = abandonment_model(cond, dr, ann, fm, y, wk)
            mon = season_month(fm["release"])
            rows = build_states(fm, am, ann, y, mon)
            us = totals(rows)
            fin = {"planted": pl.get((y, "US")), "harvested": hv.get((y, "US")), "prod": pr.get((y, "US"))}
            usda = {"planted": usda_same_month(ann, "upland_planted", y, "US", mon), "harvested": usda_same_month(ann, "upland_harvested", y, "US", mon),
                    "prod": usda_same_month(ann, "upland_prod", y, "US", mon)}
            out.append({"year": int(y), "release": str(fm["release"]), "fsa_model_years": int(sub.crop_year.nunique()),
                        "abandonment_model": am is not None,
                        **{f"fsa_{k}": us[k] for k in ("planted", "harvested", "prod")},
                        **{f"usda_{k}": usda[k] for k in usda}, **{f"final_{k}": fin[k] for k in fin}})
    finally:
        _FSA = None
    return summarize(out)


def summarize(out):
    """Percent misses vs final, per season and on average (mean absolute), FSA-based vs USDA same-month."""
    for r in out:
        for k in ("planted", "harvested", "prod"):
            f = r.get(f"final_{k}")
            for src in ("fsa", "usda"):
                v = r.get(f"{src}_{k}")
                r[f"{src}_{k}_err_pct"] = round(100 * (v / f - 1), 2) if v and f else None
    summ = {}
    for k in ("planted", "harvested", "prod"):
        both = [r for r in out if r[f"fsa_{k}_err_pct"] is not None and r[f"usda_{k}_err_pct"] is not None]
        if both:
            fa = [abs(r[f"fsa_{k}_err_pct"]) for r in both]
            ua = [abs(r[f"usda_{k}_err_pct"]) for r in both]
            summ[k] = {"n": len(both), "fsa_mae_pct": round(float(np.mean(fa)), 2), "usda_mae_pct": round(float(np.mean(ua)), 2),
                       "fsa_closer": int(sum(a < b for a, b in zip(fa, ua))),
                       "fsa_bias_pct": round(float(np.mean([r[f"fsa_{k}_err_pct"] for r in both])), 2),
                       "usda_bias_pct": round(float(np.mean([r[f"usda_{k}_err_pct"] for r in both])), 2)}
    return {"seasons": out, "summary": summ}


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else round(float(o), 4 if abs(float(o)) >= 1 else 6)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (pd.Timestamp, date)):
        return str(o)[:10]
    return o


def main():
    if not (CCP / "data" / "ginning" / "annual.csv").exists():
        print(f"cotton-crop-progress inputs not found in {CCP} (set CCP_DIR)")
        return 1
    if not FSA_CSV.exists():
        print("no FSA cotton data yet")
        return 1
    cond = nass_weekly()
    cur = int(cond.year.max())
    states = ["US"] + [s for s in MAIN if s in set(cond.state)]
    dr_states = drought([s for s in states if s != "US"])
    ann = annual()
    wk = int(cond[cond.year == cur].woy.max())
    fm = fsa_model(ann, cur)
    if fm is None:
        print("no FSA release for", cur)
        return 1
    am = abandonment_model(cond, dr_states, ann, fm, cur, wk)
    mon = season_month(fm["release"])
    rows = build_states(fm, am, ann, cur, mon)
    us = totals(rows)
    us.update({"usda_planted": usda_same_month(ann, "upland_planted", cur, "US", mon),
               "usda_harvested": usda_same_month(ann, "upland_harvested", cur, "US", mon),
               "usda_prod": usda_same_month(ann, "upland_prod", cur, "US", mon),
               "usda_yield": usda_same_month(ann, "upland_yield", cur, "US", mon)})
    # run.py reads the cotton-area drought file directly for Texas
    drx = pd.read_csv(os.path.join(D, "drought", "cotton_area_drought.csv"))
    drx["week"] = pd.to_datetime(drx.week)
    today = pd.Timestamp(os.environ.get("FSA_ASOF") or date.today())
    tx = texas(cond, drx, ann, cur, asof_monday(cur, today))
    bt = backtest(cond, dr_states, ann, cur, fm["release"], wk)
    out = {"crop": "cotton", "crop_year": cur, "built": str(date.today()), "fsa_release": fm["release"],
           "inputs_through": {"fsa": fm["release"], "crop_condition": f"{cond.week_ending.max():%Y-%m-%d}",
                              "drought": f"{drx.week.max():%Y-%m-%d}", "usda_month": mon if mon <= 12 else 1},
           "unit": {"acres": "acres", "prod": "480-lb bales", "yield": "lb/acre"},
           "us": us, "states": rows, "texas": tx,
           "abandonment_model": {"sd": am["sd"], "release_month": am["release_month"]} if am else None,
           "fsa_model": {"sd_hr": fm["sd_hr"]},
           "backtest": bt,
           "method": ["FSA planted + failed acres by state, scaled to NASS planted with each state's median NASS/FSA ratio at the same release month",
                      "Final abandonment from FSA failed share, D2-D4 drought (cotton area) and poor/very-poor ratings, state means removed (past seasons, same release month)",
                      "Harvested = planted x (1 - abandonment); production = harvested x USDA's same-month state yield",
                      "Texas: abandonment from drought + ratings and from ratings + FSA failed share so far, averaged; x USDA's in-season Texas yield"],
           "source": "Port of BMR-Com/cotton-crop-progress (scripts/model.py fsa_model/abandonment_model, scripts/crop_projection/run.py Texas)"}
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "cotton.json").write_text(json.dumps(clean(out), indent=1, allow_nan=False))
    c = (tx.get("conditional") or {}).get("tx_abandonment")
    print(f"cotton FSA {fm['release']}: US planted {us['planted'] / 1e6:.2f}m, harvested {us['harvested'] / 1e6:.2f}m, "
          f"prod {us['prod'] / 1e6:.2f}m bales; Texas conditional abandonment {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
