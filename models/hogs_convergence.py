"""Lean hog convergence backtest: fundamentals vs futures in forecasting the final settlement.

Target: CME Lean Hog Index on each contract's last trading day (10th business day of the
contract month) = the futures' final cash settlement (from the desk's exact index rebuild).
Origins: every Hogs and Pigs release (first-print numbers, true release dates).
Fundamental forecast for contract T made at release t:
    log(I_T / I_T-1y) = a + b1*supply_yoy(T) + b2*log(I_t / I_t-1y) + b3*weight_yoy(t) + b4*cutout_yoy(t)
    supply_yoy: y/y change of the H&P weight group that reaches slaughter in T's month
fitted walk-forward on releases strictly before t (targets already settled).
Benchmarks: futures close of contract T on the first trading day after the release (post-report),
and the pre-report close. Scores: mean abs error to settlement; does (model - futures) predict
(settlement - futures)? Feature ablations show which data points carry information.
Writes data/livestock/derived/hogs_convergence.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "livestock" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hogs import lean_hog_index  # noqa: E402
from esmis_parse import hogs_and_pigs  # noqa: E402

CODES = "FGHJKMNQUVXZ"
HE_MONTHS = [2, 4, 5, 6, 7, 8, 10, 12]
GROUP_BY_K = {0: "ge180", 1: "120_179", 2: "50_119", 3: "lt50", 4: "lt50", 5: "lt50"}


def ltd(y, m):
    return pd.bdate_range(f"{y}-{m:02d}-01", periods=10)[-1]


def build():
    day = lean_hog_index()
    idx = day["index"].dropna()
    cw = day["head_cw"].dropna()
    hp = hogs_and_pigs()
    hp["released"] = pd.to_datetime(hp.released)
    fut = pd.read_csv(ROOT / "data" / "contracts" / "HE.csv", parse_dates=["date"])
    cut = None
    p = ROOT / "data" / "livestock" / "raw" / "pk602_pork_cutout" / "cutout_and_primal_values.csv"
    if p.exists():
        c = pd.read_csv(p)
        c["date"] = pd.to_datetime(c.report_date)
        cut = pd.to_numeric(c.pork_carcass, errors="coerce").groupby(c.date).last().dropna().sort_index()

    def at(s, d):
        s2 = s[:d]
        return s2.iloc[-1] if len(s2) else np.nan

    rows = []
    for _, r in hp.iterrows():
        t = r.released
        q = pd.Period(r.quarter, "M")
        for k in range(0, 6):
            tm = q + k
            if tm.month not in HE_MONTHS:
                continue
            T = ltd(tm.year, tm.month)
            if T <= t:
                continue
            contract = f"HE{CODES[tm.month - 1]}{tm.year}"
            f = fut[fut.contract == contract].set_index("date").close
            post = f[t + pd.Timedelta(days=1):]
            pre = f[:t]
            if post.empty or pre.empty:
                continue
            g = GROUP_BY_K[k]
            settle = idx.get(T, np.nan) if T <= idx.index.max() else np.nan
            T1 = ltd(tm.year - 1, tm.month)
            rows.append(dict(
                release=str(t.date()), contract=contract, k=k, ltd=str(T.date()),
                settle=settle, settle_ly=idx.get(T1, np.nan),
                supply_yoy=r[g] / r[g + "_prev"] - 1,
                cash_yoy=np.log(at(idx, t) / at(idx, t - pd.Timedelta(days=364))),
                weight_yoy=at(cw, t) / at(cw, t - pd.Timedelta(days=364)) - 1,
                cutout_yoy=np.nan if cut is None else np.log(at(cut, t) / at(cut, t - pd.Timedelta(days=364))),
                fut_pre=pre.iloc[-1], fut_post=post.iloc[0], cash_t=at(idx, t)))
    return pd.DataFrame(rows)


def walk_forward(d, feats, start="2012-01-01"):
    d = d.dropna(subset=["settle_ly"] + feats).copy()
    d["y"] = np.log(d.settle / d.settle_ly)
    preds = []
    for t in sorted(d.release.unique()):
        if t < start:
            continue
        train = d[(d.ltd < t) & d.y.notna()]
        test = d[d.release == t]
        if len(train) < 30:
            continue
        X = np.c_[np.ones(len(train)), train[feats].values]
        b, *_ = np.linalg.lstsq(X, train.y.values, rcond=None)
        yhat = np.c_[np.ones(len(test)), test[feats].values] @ b
        x = test.copy()
        x["model"] = x.settle_ly * np.exp(yhat)
        preds.append(x)
    return pd.concat(preds) if preds else pd.DataFrame()


def score(p):
    p = p.dropna(subset=["settle", "model"])
    if p.empty:
        return None
    gap = p.model - p.fut_post
    conv = p.settle - p.fut_post
    out = {"n": int(len(p)),
           "mae_model": round(float((p.model - p.settle).abs().mean()), 2),
           "mae_futures_post": round(float((p.fut_post - p.settle).abs().mean()), 2),
           "mae_futures_pre": round(float((p.fut_pre - p.settle).abs().mean()), 2),
           "model_beats_futures_share": round(float(((p.model - p.settle).abs() < (p.fut_post - p.settle).abs()).mean()), 2),
           "gap_vs_convergence_corr": round(float(np.corrcoef(gap, conv)[0, 1]), 3),
           "direction_hit": round(float((np.sign(gap) == np.sign(conv)).mean()), 2)}
    big = p[gap.abs() >= 3]
    if len(big):
        out["when_gap_ge_3"] = {"n": int(len(big)), "hit": round(float((np.sign(big.model - big.fut_post) == np.sign(big.settle - big.fut_post)).mean()), 2),
                                "avg_convergence_in_gap_direction": round(float((np.sign(big.model - big.fut_post) * (big.settle - big.fut_post)).mean()), 2)}
    by_k = {}
    for k, x in p.groupby("k"):
        by_k[int(k)] = {"n": int(len(x)), "mae_model": round(float((x.model - x.settle).abs().mean()), 2),
                        "mae_futures_post": round(float((x.fut_post - x.settle).abs().mean()), 2)}
    out["by_months_ahead"] = by_k
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    d = build()
    sets = {
        "seasonal_only": [],
        "supply": ["supply_yoy"],
        "supply+cash": ["supply_yoy", "cash_yoy"],
        "supply+cash+weights": ["supply_yoy", "cash_yoy", "weight_yoy"],
        "supply+cash+weights+cutout": ["supply_yoy", "cash_yoy", "weight_yoy", "cutout_yoy"],
        "cash_only": ["cash_yoy"],
    }
    res = {}
    for name, feats in sets.items():
        start = "2016-01-01" if "cutout_yoy" in feats else "2012-01-01"
        if not feats:
            x = d.dropna(subset=["settle_ly"]).copy()
            x = x[x.release >= start]
            x["model"] = x.settle_ly
            p = x
        else:
            p = walk_forward(d, feats, start)
        res[name] = score(p)
        print(name, json.dumps(res[name]))
    # current forecasts with the full-sample fit of the best set
    best = "supply+cash+weights"
    dd = d.dropna(subset=["settle_ly", "supply_yoy", "cash_yoy", "weight_yoy"]).copy()
    tr = dd.dropna(subset=["settle"])
    X = np.c_[np.ones(len(tr)), tr[sets[best]].values]
    b, *_ = np.linalg.lstsq(X, np.log(tr.settle / tr.settle_ly).values, rcond=None)
    last = dd[dd.release == dd.release.max()].copy()
    last["model"] = last.settle_ly * np.exp(np.c_[np.ones(len(last)), last[sets[best]].values] @ b)
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "tests": res,
           "coefficients": dict(zip(["const"] + sets[best], [round(float(x), 4) for x in b])),
           "current": last[["release", "contract", "ltd", "supply_yoy", "settle_ly", "model", "fut_post"]].round(3).to_dict(orient="records")}
    (OUT / "hogs_convergence.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["coefficients"]), json.dumps(out["current"], default=str))
