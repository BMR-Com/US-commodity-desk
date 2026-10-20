"""Cash grain basis from USDA AMS daily bids (MARS, 2020-): Gulf export, Illinois River barge, Iowa interior,
Chicago SRW, Kansas City HRW. Cash convergence test for grains.

Basis = cash bid minus the referenced futures month (cents/bu, mid of the reported range, spot/'current' bids).
Test: when spot basis is strong relative to its usual level for the time of year (other years' same-week mean),
does the nearby future gain on the next contract over the following 20 trading days (cash pulls the delivery
month up as it converges), and does the nearby future itself rise?
Writes data/grains/derived/basis.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AMS = ROOT / "data" / "ams"
OUT = ROOT / "data" / "grains" / "derived"
MCODE = {c: i for i, c in enumerate("FGHJKMNQUVXZ", 1)}
SERIES = {  # key: [(label, report dir, filter)]
    "corn": [("Gulf export", "gulf_export_bids", dict(commodity="Corn")),
             ("N. Illinois River barge", "illinois_bids", dict(commodity="Corn", trade_loc="North Illinois River")),
             ("Iowa interior", "iowa_bids", dict(commodity="Corn", delivery_point="Country Elevators"))],
    "soybeans": [("Gulf export", "gulf_export_bids", dict(commodity="Soybeans")),
                 ("N. Illinois River barge", "illinois_bids", dict(commodity="Soybeans", trade_loc="North Illinois River")),
                 ("Iowa interior", "iowa_bids", dict(commodity="Soybeans", delivery_point="Country Elevators"))],
    "wheat": [("Chicago SRW", "illinois_bids", dict(commodity="Wheat", trade_loc="Chicago")),
              ("Gulf SRW", "gulf_export_bids", dict(commodity="Wheat"))],
    "kc": [("Kansas City HRW 11%", "kc_wheat_bids", dict(commodity="Wheat", protein="11.0%"))],
}
SYM = {"corn": "ZC", "soybeans": "ZS", "wheat": "ZW", "kc": "KE"}


def load(rep):
    fs = sorted((AMS / rep).glob("*.csv"))
    if not fs:
        return None
    d = pd.concat([pd.read_csv(f, low_memory=False) for f in fs])
    d["date"] = pd.to_datetime(d.report_date)
    return d


def series(d, flt):
    x = d.copy()
    for k, v in flt.items():
        x = x[x[k].astype(str) == v]
    x = x[(x.quote_type == "Basis") & (x.get("current", "Yes").astype(str) == "Yes")]
    x["basis"] = (pd.to_numeric(x["basis Min"], errors="coerce") + pd.to_numeric(x["basis Max"], errors="coerce")) / 2
    x["fm"] = x["basis Min Futures Month"].astype(str).str.extract(r"\((\w)\)")[0]
    x = x.dropna(subset=["basis"])
    g = x.groupby("date").agg(basis=("basis", "mean"), fm=("fm", "first")).sort_index()
    return g[~g.index.duplicated()]


def contract_px(sym):
    p = ROOT / "data" / "contracts" / f"{sym}.csv"
    if not p.exists():
        return None, None
    d = pd.read_csv(p, parse_dates=["date"])
    px = d.pivot_table(index="date", columns="contract", values="close", aggfunc="last").sort_index()
    return px, d.groupby("contract").date.max()


def front_for(sym, date, letter, cols):
    """Contract with the given month letter that is next to deliver after `date`."""
    for y in (date.year, date.year + 1):
        c = f"{sym}{letter}{y}"
        if c in cols:
            m = MCODE[letter]
            if pd.Timestamp(y, m, 1) > date:
                return c
    return None


def nxt(sym, c, cols):
    m, y = MCODE[c[len(sym)]], int(c[len(sym) + 1:])
    cands = []
    for cc in cols:
        mm, yy = MCODE.get(cc[len(sym)]), int(cc[len(sym) + 1:])
        if mm and (yy, mm) > (y, m):
            cands.append(((yy, mm), cc))
    return min(cands)[1] if cands else None


def test(s, sym, horizon=20):
    px, last = contract_px(sym)
    if px is None or len(s) < 200:
        return None
    s = s.copy()
    s["woy"] = s.index.isocalendar().week.values
    s["yr"] = s.index.year
    norm = s.groupby(["yr", "woy"]).basis.mean().rename("m").reset_index()
    def loyo(r):
        o = norm[(norm.woy == r.woy) & (norm.yr != r.yr)]
        return o.m.mean() if len(o) >= 2 else np.nan
    s["norm"] = [loyo(r) for r in s.itertuples()]
    s["dev"] = s.basis - s.norm
    rows = []
    idx = px.index
    for t, r in s.dropna(subset=["dev", "fm"]).iterrows():
        f = front_for(sym, t, r.fm, px.columns)
        if not f:
            continue
        n = nxt(sym, f, px.columns)
        i = idx.searchsorted(t)
        if not n or i + horizon >= len(idx):
            continue
        t1 = idx[i + horizon]
        # stay clear of delivery: front month must start after the horizon ends
        if pd.Timestamp(int(f[len(sym) + 1:]), MCODE[f[len(sym)]], 1) - pd.Timedelta(days=5) <= t1:
            continue
        a0, b0, a1, b1 = px.at[idx[i], f], px.at[idx[i], n], px.at[t1, f], px.at[t1, n]
        if np.isnan([a0, b0, a1, b1]).any():
            continue
        rows.append(dict(date=t, dev=r.dev, spread_chg=(a1 - b1) - (a0 - b0), ret=100 * (a1 / a0 - 1)))
    x = pd.DataFrame(rows)
    if len(x) < 100:
        return None
    nn = x.iloc[::horizon]
    hi, lo = x[x.dev >= x.dev.quantile(0.8)], x[x.dev <= x.dev.quantile(0.2)]
    yrs = x.groupby(x.date.dt.year)[["dev", "spread_chg"]].apply(lambda g: np.corrcoef(g.dev, g.spread_chg)[0, 1] if len(g) > 20 else np.nan).dropna()
    return {"n": int(len(x)), "n_nonoverlap": int(len(nn)), "since": str(x.date.min().date()),
            "corr_spread": round(float(np.corrcoef(x.dev, x.spread_chg)[0, 1]), 2), "corr_spread_nonoverlap": round(float(np.corrcoef(nn.dev, nn.spread_chg)[0, 1]), 2),
            "corr_ret": round(float(np.corrcoef(x.dev, x.ret)[0, 1]), 2), "corr_ret_nonoverlap": round(float(np.corrcoef(nn.dev, nn.ret)[0, 1]), 2),
            "strong_spread_chg": round(float(hi.spread_chg.mean()), 2), "weak_spread_chg": round(float(lo.spread_chg.mean()), 2),
            "strong_ret": round(float(hi.ret.mean()), 2), "weak_ret": round(float(lo.ret.mean()), 2),
            "years_pos": int((yrs > 0).sum()), "years": int(len(yrs))}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cache, res = {}, {}
    for com, specs in SERIES.items():
        out = []
        for lab, rep, flt in specs:
            if rep not in cache:
                cache[rep] = load(rep)
            d = cache[rep]
            if d is None:
                continue
            s = series(d, flt)
            if s.empty:
                continue
            doy = {}
            for y, g in s.groupby(s.index.year):
                doy[str(y)] = [[int(t.dayofyear), round(float(v), 1)] for t, v in zip(g.index, g.basis)][::2]
            cur = s.iloc[-1]
            same = s[(s.index.dayofyear - s.index[-1].dayofyear).__abs__() <= 7]
            same = same[same.index.year < s.index[-1].year]
            out.append({"label": lab, "as_of": str(s.index[-1].date()), "basis": round(float(cur.basis), 1), "fm": cur.fm,
                        "chg_5d": round(float(cur.basis - s.basis.iloc[-6]), 1) if len(s) > 6 else None,
                        "usual": round(float(same.basis.mean()), 1) if len(same) else None,
                        "by_year": doy, "test": test(s, SYM[com])})
        if out:
            res[com] = out
            for o in out:
                print(com, o["label"], o["as_of"], o["basis"], o["fm"], "usual", o["usual"], json.dumps(o["test"]))
    (OUT / "basis.json").write_text(json.dumps(res, separators=(",", ":"), default=str).replace("NaN", "null"))
