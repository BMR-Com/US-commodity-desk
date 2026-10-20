"""Front-month hog convergence: in the last 30 business days before expiry, do daily cash data
predict where the Lean Hog Index settles better than the expiring futures contract?

Origin t: each business day with 3..30 business days to the contract's last trading day.
Target: index on the LTD (exact final settlement).
Features known at t (index published with a 2-day lag; use values up to t-2 business days):
  momentum: index change over the last 5 business days
  margin:   CME pork cutout - lean hog index ($/cwt), deviation from its 1-year mean (packer bid capacity)
  slaughter: 5-day head count vs same days a year ago (y/y)
  weight:   carcass weight y/y
Model: log(I_T / I_t) = seasonal(t->T, past 5y) + b . features, walk-forward by contract.
Scores vs futures close at t; and does (model - futures) predict (settle - futures)?
Writes data/livestock/derived/hogs_expiry.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "livestock" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hogs import lean_hog_index  # noqa: E402

CODES = "FGHJKMNQUVXZ"
HE_MONTHS = [2, 4, 5, 6, 7, 8, 10, 12]


def expiry(f):
    """(last trading date, final settlement) from a contract's own history; (None, nan) if still trading."""
    if f.empty or f.index.max() >= pd.Timestamp.now().normalize() - pd.Timedelta(days=3):
        return None, np.nan
    return f.index.max(), float(f.iloc[-1])


def ltd(y, m):
    return pd.bdate_range(f"{y}-{m:02d}-01", periods=10)[-1]


def build():
    day = lean_hog_index()
    idx, hd, cw = day["index"].dropna(), day["hd"], day["head_cw"]
    c = pd.read_csv(ROOT / "data" / "livestock" / "raw" / "pk602_pork_cutout" / "cutout_and_primal_values.csv")
    c["date"] = pd.to_datetime(c.report_date)
    cut = pd.to_numeric(c.pork_carcass, errors="coerce").groupby(c.date).last().dropna().sort_index()
    margin = (cut - idx.reindex(cut.index)).dropna()
    margin_dev = margin - margin.rolling(250, min_periods=120).mean()
    fut = pd.read_csv(ROOT / "data" / "contracts" / "HE.csv", parse_dates=["date"])
    bd = pd.bdate_range(idx.index.min(), idx.index.max() + pd.Timedelta(days=400))

    def at(s, d):
        s2 = s[:d]
        return s2.iloc[-1] if len(s2) else np.nan

    rows = []
    for y in range(2014, pd.Timestamp.now().year + 1):
        for m in HE_MONTHS:
            contract = f"HE{CODES[m - 1]}{y}"
            f = fut[fut.contract == contract].set_index("date").close
            if f.empty:
                continue
            T, settle = expiry(f)
            if T is None:
                continue
            days = bd[(bd < T)][-30:]
            for t in days[:-2]:
                k = int((bd[(bd > t) & (bd <= T)]).size)
                info = t - pd.tseries.offsets.BDay(2)  # index known with a 2-business-day lag
                It = at(idx, info)
                if np.isnan(It) or t not in f.index:
                    continue
                seas = []
                for yy in range(1, 6):
                    a, b = at(idx, info - pd.DateOffset(years=yy)), at(idx, T - pd.DateOffset(years=yy))
                    if not np.isnan(a) and not np.isnan(b):
                        seas.append(np.log(b / a))
                h5 = hd[:info].tail(5).sum()
                h5ly = hd[:info - pd.DateOffset(years=1)].tail(5).sum()
                rows.append(dict(contract=contract, t=t, ltd=T, bdays=k, settle=settle, fut=f[t], I=It,
                                 seas=np.mean(seas) if seas else np.nan,
                                 momentum=np.log(It / at(idx, info - pd.tseries.offsets.BDay(5))),
                                 margin=at(margin_dev, info), slaughter=h5 / h5ly - 1 if h5ly else np.nan,
                                 weight=at(cw, info) / at(cw, info - pd.DateOffset(years=1)) - 1))
    return pd.DataFrame(rows)


def walk(d, feats):
    d = d.dropna(subset=["seas", "I"] + feats).copy()
    d["y"] = np.log(d.settle / d.I) - d.seas
    out = []
    for c in d.contract.unique():
        test = d[d.contract == c]
        train = d[(d.ltd < test.t.min()) & d.y.notna()]
        if len(train) < 200:
            continue
        if feats:
            X = np.c_[np.ones(len(train)), train[feats].values]
            b, *_ = np.linalg.lstsq(X, train.y.values, rcond=None)
            yhat = np.c_[np.ones(len(test)), test[feats].values] @ b
        else:
            yhat = np.full(len(test), train.y.mean())
        x = test.copy()
        x["model"] = x.I * np.exp(x.seas + yhat)
        out.append(x)
    return pd.concat(out) if out else pd.DataFrame()


def score(p):
    p = p.dropna(subset=["settle", "model"])
    gap, conv = p.model - p.fut, p.settle - p.fut
    res = {"n_days": int(len(p)), "n_contracts": int(p.contract.nunique()),
           "mae_model": round(float((p.model - p.settle).abs().mean()), 3),
           "mae_futures": round(float((p.fut - p.settle).abs().mean()), 3),
           "gap_vs_convergence_corr": round(float(np.corrcoef(gap, conv)[0, 1]), 3),
           "direction_hit": round(float((np.sign(gap) == np.sign(conv)).mean()), 3)}
    for lo, hi in ((3, 10), (11, 20), (21, 30)):
        x = p[(p.bdays >= lo) & (p.bdays <= hi)]
        g, cv = x.model - x.fut, x.settle - x.fut
        res[f"bdays_{lo}_{hi}"] = {"mae_model": round(float((x.model - x.settle).abs().mean()), 3),
                                    "mae_futures": round(float((x.fut - x.settle).abs().mean()), 3),
                                    "corr": round(float(np.corrcoef(g, cv)[0, 1]), 3),
                                    "hit_when_gap_ge_1": round(float((np.sign(g[g.abs() >= 1]) == np.sign(cv[g.abs() >= 1])).mean()), 3),
                                    "n_gap_ge_1": int((g.abs() >= 1).sum())}
    return res


if __name__ == "__main__":
    d = build()
    sets = {"cash+seasonal": [], "+momentum": ["momentum"], "+margin": ["margin"], "+slaughter": ["slaughter"],
            "+weight": ["weight"], "all": ["momentum", "margin", "slaughter", "weight"]}
    res = {}
    for name, feats in sets.items():
        res[name] = score(walk(d, feats))
        print(name, json.dumps(res[name]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "hogs_expiry.json").write_text(json.dumps({"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "tests": res}, indent=1))
