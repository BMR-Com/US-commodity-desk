#!/usr/bin/env python3
"""FSA crop acreage → corn, soybeans, wheat and sorghum planted, harvested and production: the cotton-crop-progress
FSA method (models/fsa_cotton.py, scripts/model.py fsa_model + abandonment_model) applied to the grains, same parameters.

Per state at the latest FSA release:
  planted   = FSA (planted + failed) x the state's median NASS-final-planted / FSA ratio at the same release month in
              past seasons (outliers outside 0.7-1.4 of the median dropped; 1.02 where a state has no NASS history);
  abandonment (1 - harvested/planted) from the FSA failed share and the season's poor/very-poor ratings, each state's
              own mean removed, weighted by planted acres, fitted on past seasons at the same release month
              (falls back to the failed-share line of fsa_model when the state has no ratings history);
  harvested = planted x (1 - abandonment);
  production = harvested x USDA's US yield in the WASDE of the same month (US level).
Cotton-only inputs that are left out: D2-D4 drought on the crop area (the desk has no cotton-area-style drought series
for grains; whole-state drought is not used) and the Texas-only abandonment/yield blend. Ratings are NASS crop
condition by state (data/grains/raw/crop_progress): corn, soybeans, sorghum from late June (ISO week 26) to the
release; wheat (winter + spring) from March to July.
Corn and sorghum harvested are for grain, so their "abandonment" includes silage/forage cut; state means absorb the
normal share. Wheat: FSA acres for grain-type intended uses only (grain, grain/graze, seed, blank): FSA reclassified
grazing wheat in 2019, which broke the NASS/FSA state ratio the method scales by (TX/OK 1.07 → 0.72); without grazing,
forage and cover the ratio is stable across the break.

USDA figures (US planted, harvested, yield, production) come from the desk's WASDE store (models/wasde_store.py →
data/wasde/json, raw values, not the rounded grains_wasde tables). State finals from NASS (data/grains/raw/annual).

Backtest: every past season with an FSA release by the same point of the season (within a week), using only the FSA
rows known then and only earlier seasons to fit, compared with USDA's final (last WASDE of the marketing year) and with
USDA's own number in the WASDE of the same month.

Writes .cache/fsa_build/grains.json (published to data/fsa/grains.json by the fsa workflow if models/fsa_check.py passes).
"""
import glob, json, math, os, sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FSA_CSV = ROOT / "data" / "fsa" / "fsa_grains_state.csv"
ANN = ROOT / "data" / "grains" / "raw" / "annual"
CP = ROOT / "data" / "grains" / "raw" / "crop_progress"
BUILD = ROOT / ".cache" / "fsa_build"
sys.path.insert(0, str(Path(__file__).resolve().parent))

CROPS = {  # FSA crop, NASS folder, NASS planted / harvested / yield / production short_desc, WASDE file
    "corn": {"fsa": "CORN", "planted": "CORN - ACRES PLANTED", "harvested": "CORN, GRAIN - ACRES HARVESTED", "wasde": "Corn", "unit": "bu"},
    "soybeans": {"fsa": "SOYBEANS", "planted": "SOYBEANS - ACRES PLANTED", "harvested": "SOYBEANS - ACRES HARVESTED", "wasde": "Oilseed,_Soybean", "unit": "bu"},
    "wheat": {"fsa": "WHEAT", "planted": "WHEAT - ACRES PLANTED", "harvested": "WHEAT - ACRES HARVESTED", "wasde": "Wheat", "unit": "bu",
              # FSA reclassified grazing wheat in 2019 (GRAIN/GRAZE dropped, GRAZING 1.8m → 5.8m+ acres; TX/OK NASS/FSA ratio
              # 1.07 → 0.72), which breaks the state ratio the method scales by; grain-type uses keep it stable (US 1.09-1.15)
              "uses": ["GRAIN", "GRAIN/GRAZE", "SEED", "BLANK", ""]},
    "sorghum": {"fsa": "SORGHUM", "planted": "SORGHUM - ACRES PLANTED", "harvested": "SORGHUM, GRAIN - ACRES HARVESTED", "wasde": "Sorghum", "unit": "bu"},
}
ST = {"ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
      "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
      "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
      "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH",
      "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH",
      "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
      "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
      "WISCONSIN": "WI", "WYOMING": "WY"}
NAME = {v: k.title() for k, v in ST.items()}
# 2014-2017 workbooks use truncated state names (cotton keeps the source's name map unchanged, see HANDOFF)
ST.update({"CALIFRNIA": "CA", "CONCTICUT": "CT", "MASACUSET": "MA", "MISISIPPI": "MS", "NEW HAMP": "NH", "NEW MEXCO": "NM",
           "NEWJERSEY": "NJ", "NO CAROLN": "NC", "NO DAKOTA": "ND", "PENSLVANA": "PA", "RHODE ISL": "RI", "S CAROLIN": "SC",
           "S DAKOTA": "SD", "WASHNGTON": "WA", "WEST VA": "WV"})
BU_PER_MT = {"corn": 39.368, "soybeans": 36.744, "wheat": 36.744, "sorghum": 39.368}


def _ols(X, y, w):
    W = np.sqrt(w)[:, None]
    beta, *_ = np.linalg.lstsq(X * W, y * W[:, 0], rcond=None)
    return beta


# ───────── inputs ─────────
def nass_finals(crop):
    """{(year, st): value} for planted and harvested, state + US ('US'), NASS final ('YEAR')."""
    c = CROPS[crop]
    fr = []
    for f in sorted(glob.glob(str(ANN / crop / "*.csv.gz"))):
        d = pd.read_csv(f, usecols=["year", "reference_period_desc", "state_alpha", "agg_level_desc", "short_desc", "Value"])
        fr.append(d[d.short_desc.isin([c["planted"], c["harvested"]]) & (d.reference_period_desc == "YEAR")])
    d = pd.concat(fr, ignore_index=True)
    d["v"] = pd.to_numeric(d.Value.astype(str).str.replace(",", ""), errors="coerce")
    d["st"] = np.where(d.agg_level_desc == "NATIONAL", "US", d.state_alpha)
    d = d.dropna(subset=["v"])
    pl = d[d.short_desc == c["planted"]].groupby(["year", "st"]).v.last()
    hv = d[d.short_desc == c["harvested"]].groupby(["year", "st"]).v.last()
    return pl, hv


def ratings(crop):
    """Season poor+very-poor by state and crop year, with week_ending so the backtest can cut it at the release."""
    fr = []
    for f in sorted(glob.glob(str(CP / crop / "*.csv.gz"))):
        d = pd.read_csv(f, usecols=["year", "week_ending", "state_alpha", "agg_level_desc", "short_desc", "Value"])
        fr.append(d[d.short_desc.str.contains("CONDITION") & (d.agg_level_desc == "STATE")])
    if not fr:
        return pd.DataFrame(columns=["state", "week_ending", "cy", "pvp"])
    d = pd.concat(fr, ignore_index=True)
    d["v"] = pd.to_numeric(d.Value.astype(str).str.replace(",", ""), errors="coerce")
    d["cat"] = d.short_desc.str.extract(r"PCT (.*)$")[0]
    d["cls"] = d.short_desc.str.split(" - ").str[0]
    p = d.pivot_table(index=["state_alpha", "week_ending", "cls"], columns="cat", values="v", aggfunc="last").reset_index()
    p = p.dropna(subset=["POOR", "VERY POOR"])
    p["pvp"] = p["POOR"] + p["VERY POOR"]
    p["week_ending"] = pd.to_datetime(p.week_ending)
    p = p.rename(columns={"state_alpha": "state"})
    if crop == "wheat":                       # winter + spring readings Mar-Jul of the harvest year
        p = p[p.week_ending.dt.month.between(3, 7)]
        p["cy"] = p.week_ending.dt.year
    else:                                     # late June (ISO week 26) on
        p = p[p.week_ending.dt.isocalendar().week.astype(int) >= 26]
        p["cy"] = p.week_ending.dt.year
    return p[["state", "week_ending", "cy", "pvp"]]


def wasde_us(crop):
    """US planted/harvested (million acres), yield, production (million bu) by marketing year and report (raw values)."""
    from wasde_store import local_dir
    j = json.loads(Path(local_dir(), CROPS[crop]["wasde"] + ".json").read_text())
    want = {"area planted": "planted", "area harvested": "harvested", "yield per harvested acre": "yield", "yield": "yield", "production": "prod"}
    rows = []
    for key, hist in j["data"].items():
        region, attr, my = key.split("||")
        a = want.get(attr.strip().lower())
        if region != "United States" or not a:
            continue
        for h in hist:
            if h.get("value") is None:
                continue
            v, metric = float(h["value"]), "metric" in str(h.get("unit", "")).lower()
            if metric and a != "prod":
                continue
            if metric:                        # some years' US production is stored only in MMT (world-table collision)
                v = round(v * BU_PER_MT[crop])
            rows.append({"my": my, "attr": a, "wasde": h["wasdeNum"], "rep": pd.Timestamp(int(h["forecastYear"]), int(h["forecastMonth"]), 1),
                         "report": h["reportDate"], "value": v, "metric": metric})
    d = pd.DataFrame(rows).sort_values("metric").drop_duplicates(["my", "attr", "wasde"])
    d["cy"] = d.my.str[:4].astype(int)
    return d


def usda_same_month(w, cy, rel):
    """USDA's US numbers in the WASDE published in the FSA release's month (else the latest before it)."""
    rel = pd.Timestamp(rel)
    x = w[(w.cy == cy) & (w.rep <= pd.Timestamp(rel.year, rel.month, 1))]
    if not len(x):
        return None
    last = x.wasde.max()
    y = x[x.wasde == last]
    o = {r.attr: r.value for r in y.itertuples()}
    o.update({"wasde": int(last), "report": y.report.iloc[0]})
    return o


def usda_final(w, cy):
    x = w[w.cy == cy]
    if not len(x):
        return None
    return x.sort_values("wasde").groupby("attr").value.last().to_dict()


def fsa_crop(crop):
    f = pd.read_csv(FSA_CSV, keep_default_na=False, na_values=[""])
    f = f[f.crop == CROPS[crop]["fsa"]].copy()
    if CROPS[crop].get("uses"):
        f = f[f.intended_use.fillna("").astype(str).isin(CROPS[crop]["uses"])]
    f["st"] = f.state.astype(str).str.upper().str.strip().map(ST)
    f = f.dropna(subset=["st"])
    return f.groupby(["crop_year", "release", "st"])[["planted", "failed"]].sum().reset_index()


def season_day(rel, cy, crop):
    start = pd.Timestamp(int(cy), 8, 1)       # FSA releases run August → January for every crop
    return (pd.Timestamp(rel) - start).days


# ───────── the cotton method (fsa_model + abandonment_model), ratings-only abandonment ─────────
def model(g, pl, hv, rt, cur):
    """g: FSA rows (crop_year, release, st, planted, failed) known at this point. Returns state rows or None."""
    g = g.copy()
    g["rm"] = pd.to_datetime(g.release).dt.month
    g["tot"] = g.planted + g.failed
    g["fs"] = np.where(g.tot > 0, g.failed / g.tot.where(g.tot > 0), np.nan)
    g["npl"] = [pl.get((y, s)) if y < cur else None for y, s in zip(g.crop_year, g.st)]
    g["nhv"] = [hv.get((y, s)) if y < cur else None for y, s in zip(g.crop_year, g.st)]
    g["npl"], g["nhv"] = pd.to_numeric(g.npl), pd.to_numeric(g.nhv)
    g["ratio"] = g.npl / g.tot
    g["ab"] = 1 - g.nhv / g.npl
    hist = g.dropna(subset=["npl", "nhv", "fs"])
    hist = hist[hist.tot > 0]
    if hist.crop_year.nunique() < 3:
        return None
    med = hist.groupby("st").ratio.median()
    hist = hist[(hist.ratio / hist.st.map(med)).between(0.7, 1.4)]
    now = g[g.crop_year == cur]
    if not len(now):
        return None
    rel = now.release.max()
    rm = int(pd.to_datetime(rel).month)
    now = now[(now.release == rel) & (now.tot > 0)]
    # fsa_model: failed share → abandonment line + 0.8 x state residual
    hx = hist[hist.rm == rm] if (hist.rm == rm).sum() >= 30 else hist
    b = np.polyfit(hx.fs, hx.ab, 1, w=np.sqrt(hx.npl))
    resid = (hx.ab - np.polyval(b, hx.fs)).groupby(hx.st).mean()
    rmed = hist[hist.rm == rm].groupby("st").ratio.median() if (hist.rm == rm).any() else med
    # abandonment_model with ratings instead of ratings + drought: same release month, state means removed, weighted
    relT = pd.Timestamp(rel)
    md_cut = lambda y: pd.Timestamp(relT.year - (cur - y), relT.month, min(relT.day, 28))
    pv = {}
    for y in sorted(set(g.crop_year)):
        r = rt[(rt.cy == y) & (rt.week_ending < md_cut(y))]
        if len(r):
            pv.update(r.groupby("state").pvp.mean().rename(lambda s, y=y: (y, s)).to_dict())
    feats = ["fs", "pvp"]
    a = hist[hist.rm == rm].copy()
    a["pvp"] = [pv.get((y, s)) for y, s in zip(a.crop_year, a.st)]
    a = a.dropna(subset=feats + ["ab", "npl"])
    a = a[a.npl > 20000]
    am = None
    if a.crop_year.nunique() >= 6:
        m = a.groupby("st")[feats + ["ab"]].mean()
        X = np.c_[np.ones(len(a)), a[feats].values - m.loc[a.st, feats].values]
        ba = _ols(X, a.ab.values - m.loc[a.st, "ab"].values, a.npl.values)
        am = (ba, m)
    out = {}
    for _, r in now.iterrows():
        k = rmed.get(r.st, med.get(r.st, 1.02))
        ab_f = float(np.clip(np.polyval(b, r.fs) + 0.8 * resid.get(r.st, 0), 0, 0.95))
        ab, src = ab_f, "fsa failed share"
        p = pv.get((cur, r.st))
        if am is not None and r.st in am[1].index:
            ba, m = am
            pvp = p if p is not None else float(a[a.st == r.st].pvp.mean())
            x = np.r_[1, np.array([r.fs, pvp]) - m.loc[r.st, feats].values.astype(float)]
            ab, src = float(np.clip(m.loc[r.st, "ab"] + x @ ba, 0, 0.95)), "fsa failed share + ratings"
        out[r.st] = {"fsa_planted": float(r.planted), "fsa_failed": float(r.failed), "fsa_total": float(r.tot), "fail_share": float(r.fs),
                     "scale": float(k), "planted": float(r.tot * k), "abandonment": ab, "ab_source": src, "ab_fsa_only": ab_f,
                     "pvp": p, "harvested": float(r.tot * k * (1 - ab)),
                     "nass_planted_prev": pl.get((cur - 1, r.st))}
    return {"release": rel, "states": out, "abandonment_fit_years": int(a.crop_year.nunique()) if len(a) else 0}


def us_totals(st, usda):
    t = lambda k: float(sum(v[k] for v in st.values()))
    us = {"fsa_planted": t("fsa_planted"), "fsa_failed": t("fsa_failed"), "fsa_total": t("fsa_total"), "planted": t("planted"), "harvested": t("harvested")}
    us["abandonment"] = 1 - us["harvested"] / us["planted"] if us["planted"] else None
    y = (usda or {}).get("yield")
    us["yield"] = y
    us["prod"] = us["harvested"] * y / 1e6 if y else None          # million bu
    return us


def run_crop(crop):
    full = fsa_crop(crop)
    if not len(full):
        return None
    pl, hv = nass_finals(crop)
    rt = ratings(crop)
    w = wasde_us(crop)
    cur = int(full.crop_year.max())
    res = model(full, pl, hv, rt, cur)
    if res is None:
        return {"crop": crop, "crop_year": cur, "error": "not enough FSA history yet"}
    usda = usda_same_month(w, cur, res["release"])
    us = us_totals(res["states"], usda)
    rows = sorted(({"st": s, "name": NAME.get(s, s), **v} for s, v in res["states"].items()), key=lambda r: -r["planted"])
    # backtest
    sd_now = season_day(res["release"], cur, crop)
    seasons = []
    for y in sorted(full.crop_year.unique()):
        if y >= cur:
            continue
        fy = full[full.crop_year == y]
        fy = fy[[season_day(r, y, crop) <= sd_now + 7 for r in fy.release]]
        if not len(fy):
            continue
        r = model(pd.concat([full[full.crop_year < y], fy]), pl, hv, rt, y)
        fin = usda_final(w, y)
        if r is None or not fin:
            continue
        u = usda_same_month(w, y, r["release"])
        t = us_totals(r["states"], u)
        row = {"year": int(y), "release": str(r["release"]), "usda_report": (u or {}).get("report"),
               "fsa_planted": t["planted"] / 1e6, "fsa_harvested": t["harvested"] / 1e6, "fsa_prod": t["prod"],
               "usda_planted": (u or {}).get("planted"), "usda_harvested": (u or {}).get("harvested"), "usda_prod": (u or {}).get("prod"),
               "final_planted": fin.get("planted"), "final_harvested": fin.get("harvested"), "final_prod": fin.get("prod")}
        seasons.append(row)
    from fsa_cotton import summarize
    bt = summarize(seasons)
    return {"crop": crop, "crop_year": cur, "fsa_release": res["release"], "usda": usda,
            "us": {**us, "planted_m": us["planted"] / 1e6, "harvested_m": us["harvested"] / 1e6,
                   "fsa_total_m": us["fsa_total"] / 1e6, "fsa_failed_m": us["fsa_failed"] / 1e6},
            "states": rows[:15], "n_states": len(rows), "abandonment_fit_years": res["abandonment_fit_years"],
            "fsa_history_years": sorted(int(x) for x in full.crop_year.unique()),
            "backtest": bt, "unit": {"acres": "acres (states), million acres (us *_m, usda)", "prod": "million bu", "yield": "bu/acre"}}


def main():
    from fsa_cotton import clean
    out = {"built": str(date.today()), "crops": {},
           "method": ["Same as the cotton FSA method: FSA planted + failed by state x the state's NASS/FSA ratio at the same release month",
                      "Abandonment from FSA failed share and poor/very-poor ratings (state means removed), past seasons at the same release month; drought left out",
                      "Production = harvested x USDA's same-month US yield (WASDE)"]}
    for crop in CROPS:
        if not FSA_CSV.exists():
            out["crops"][crop] = {"crop": crop, "error": "FSA grain acreage backfill in progress"}
            continue
        try:
            r = run_crop(crop)
            if r:
                out["crops"][crop] = r
                u = r.get("us") or {}
                if u:
                    print(f"{crop} {r['fsa_release']}: planted {u['planted_m']:.2f}m, harvested {u['harvested_m']:.2f}m, prod {u.get('prod') or 0:.0f}m bu"
                          f" | USDA {(r['usda'] or {}).get('planted')}/{(r['usda'] or {}).get('harvested')}/{(r['usda'] or {}).get('prod')}")
        except Exception as e:
            import traceback; traceback.print_exc()
            out["crops"][crop] = {"crop": crop, "error": repr(e)[:300]}
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "grains.json").write_text(json.dumps(clean(out), indent=1, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
