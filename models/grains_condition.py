"""Crop condition -> yield model for corn, soybeans, winter and spring wheat.

Condition index (national, weekly): good/excellent share, and a weighted index
(VP=1, P=2, F=3, G=4, E=5, scaled 0-100). Yield model: final national yield as a deviation from
a linear trend fitted on prior years, regressed on the condition index at a given week of the
season. Backtest: leave-one-year-out, compared with trend alone (and USDA's August forecast when
first-print Crop Production data are available).
Writes data/grains/derived/condition.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "grains" / "raw"
OUT = ROOT / "data" / "grains" / "derived"
CROPS = {  # key: (commodity dir, condition short_desc prefix, yield short_desc, model week candidates)
    "corn": ("corn", "CORN - CONDITION", "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", range(28, 37)),
    "soybeans": ("soybeans", "SOYBEANS - CONDITION", "SOYBEANS - YIELD, MEASURED IN BU / ACRE", range(30, 38)),
    "wheat": ("wheat", "WHEAT, WINTER - CONDITION", "WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", range(16, 23)),
    "spring_wheat": ("wheat", "WHEAT, SPRING, (EXCL DURUM) - CONDITION", "WHEAT, SPRING, (EXCL DURUM) - YIELD, MEASURED IN BU / ACRE", range(26, 32)),
}
W = {"VERY POOR": 1, "POOR": 2, "FAIR": 3, "GOOD": 4, "EXCELLENT": 5}


def val(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def read_dir(sub):
    fs = sorted((RAW / sub).glob("*.csv"))
    return pd.concat([pd.read_csv(f, low_memory=False) for f in fs]) if fs else pd.DataFrame()


def condition(commodity_dir, prefix):
    d = read_dir(f"crop_progress/{commodity_dir}")
    if d.empty:
        return None
    d = d[(d.agg_level_desc == "NATIONAL") & d.short_desc.str.startswith(prefix)].copy()
    d["cat"] = d.short_desc.str.extract(r"PCT (.+)$")[0]
    d = d[d.cat.isin(W)]
    d["v"] = val(d.Value)
    d["week_ending"] = pd.to_datetime(d.week_ending)
    p = d.pivot_table(index="week_ending", columns="cat", values="v", aggfunc="last").sort_index()
    p = p.dropna(subset=["GOOD", "EXCELLENT"])
    out = pd.DataFrame(index=p.index)
    out["ge"] = p.GOOD + p.EXCELLENT
    pf = p.reindex(columns=list(W)).fillna(0)
    tot = pf.sum(axis=1)
    out["idx"] = (sum(pf[c] * w for c, w in W.items()) / tot * 20).where(tot >= 95)  # 20..100; incomplete rows dropped
    out["year"] = out.index.year
    out["week"] = out.index.isocalendar().week.values.astype(int)
    if "WINTER" in prefix:  # fall ratings belong to next year's crop: week 44 -> year+1, week -8
        fall = out.week >= 35
        out.loc[fall, "year"] += 1
        out.loc[fall, "week"] -= 52
    return out


def yields(commodity_dir, ydesc):
    d = read_dir(f"annual/{commodity_dir}")
    if d.empty:
        return None
    d = d[(d.agg_level_desc == "NATIONAL") & (d.short_desc == ydesc) & (d.reference_period_desc == "YEAR")]
    return val(d.Value).groupby(d.year).last().sort_index()


def trend(y, upto, start=1990):
    x = y[(y.index >= start) & (y.index < upto)]
    if len(x) < 8:
        return np.nan
    b, a = np.polyfit(x.index, x.values, 1)
    return a + b * upto


def usda_yield_history(key):
    """USDA yield forecast by marketing year and WASDE release date (corn, soybeans)."""
    if key not in ("corn", "soybeans"):
        return None
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grains_wasde import tidy, load, FILES
    months = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                           "September", "October", "November", "December"], 1)}
    d = tidy(load(FILES[key]))
    d = d[(d.region == "United States") & (d.attr == "yield")].copy()
    d["release"] = [pd.Timestamp(int(r.split()[1]), months[r.split()[0]], 12) for r in d.report]
    d["year"] = d.my.str[:4].astype(int)
    return d[["year", "release", "value"]]


def model(cond, y, weeks, uh=None):
    """Pick the week with the best leave-one-year-out fit among candidates; report that test."""
    best = None
    years = sorted(set(cond.year) & set(y.index))
    for wk in weeks:
        rows = []
        for yr in years:
            c = cond[(cond.year == yr) & (cond.week <= wk)].dropna(subset=["idx"])
            if c.empty or c.week.max() < wk - 1:
                continue
            t = trend(y, yr)
            if np.isnan(t):
                continue
            usda = np.nan
            if uh is not None:
                u = uh[(uh.year == yr) & (uh.release <= c.index[-1])].sort_values("release")
                usda = u.value.iloc[-1] if len(u) else np.nan
            rows.append(dict(year=yr, idx=c.idx.iloc[-1], ge=c["ge"].iloc[-1], dev=y[yr] - t, trend=t, actual=y[yr], usda=usda))
        r = pd.DataFrame(rows)
        if len(r) < 12:
            continue
        preds = []
        for i, row in r.iterrows():
            tr = r.drop(i)
            b, a = np.polyfit(tr.idx, tr.dev, 1)
            preds.append(row.trend + a + b * row.idx)
        r["pred"] = preds
        mae, mae_t = (r.pred - r.actual).abs().mean(), (r.trend - r.actual).abs().mean()
        if best is None or mae < best["mae_model"]:
            b, a = np.polyfit(r.idx, r.dev, 1)
            ru = r.dropna(subset=["usda"])
            best = {"week": int(wk), "n": int(len(r)), "mae_model": round(float(mae), 2), "mae_trend": round(float(mae_t), 2),
                    "mae_usda_same_date": round(float((ru.usda - ru.actual).abs().mean()), 2) if len(ru) else None,
                    "mae_model_same_years": round(float((ru.pred - ru.actual).abs().mean()), 2) if len(ru) else None,
                    "n_usda": int(len(ru)),
                    "slope_per_index_pt": round(float(b), 3), "intercept": round(float(a), 3),
                    "hit_direction": round(float((np.sign(r.pred - r.trend) == np.sign(r.actual - r.trend)).mean()), 2),
                    "years": r.year.tolist(), "pred": r.pred.round(1).tolist(), "actual": r.actual.round(1).tolist()}
    return best


def wasde_yield(key):
    p = OUT / "wasde.json"
    if key not in ("corn", "soybeans") or not p.exists():
        return None
    b = json.loads(p.read_text())["commodities"][key]["us"]
    my = sorted(b)[-1]
    y = b[my]["items"].get("yield")
    return None if not y else y["value"]


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    for key, (cdir, prefix, ydesc, weeks) in CROPS.items():
        cond = condition(cdir, prefix)
        y = yields(cdir, ydesc)
        if cond is None or cond.empty:
            print(key, "no condition data yet")
            continue
        entry = {"ge": {str(yr): [[int(w), float(v)] for w, v in zip(g.week, g["ge"])] for yr, g in cond.groupby("year") if yr >= 2010}}
        if y is not None and len(y) > 10:
            m = model(cond, y, weeks, usda_yield_history(key))
            if m:
                cy = int(cond.year.max())
                c = cond[cond.year == cy]
                c = c[c.week <= m["week"]].dropna(subset=["idx"])
                t = trend(y, cy)
                est = t + m["intercept"] + m["slope_per_index_pt"] * c.idx.iloc[-1] if len(c) else None
                entry["model"] = {"year": cy, "week": m["week"], "estimate": None if est is None else round(float(est), 1),
                                  "trend": round(float(t), 1), "usda": float(y[cy]) if cy in y.index else wasde_yield(key),
                                  "test": {k: m[k] for k in ("n", "mae_model", "mae_trend", "hit_direction", "slope_per_index_pt",
                                                             "mae_usda_same_date", "mae_model_same_years", "n_usda")},
                                  "history": {k: m[k] for k in ("years", "pred", "actual")}}
                print(key, json.dumps({k: v for k, v in entry["model"].items() if k != "history"}))
        out[key] = entry
    (OUT / "condition.json").write_text(json.dumps(out, separators=(",", ":")))
