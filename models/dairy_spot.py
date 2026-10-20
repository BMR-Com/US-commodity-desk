"""CME daily spot dairy (AMS MARS report 1603) -> current-month Class III/IV nowcast, tested against futures.

The announced class price uses monthly averages of the weekly NDPSR survey, which follows CME spot with a lag.
Spot-informed nowcast for month M at origin t (each weekly NDPSR release, Wednesday):
  completed NDPSR weeks (sales-weighted) + remaining weeks at [CME spot average over the 5 sessions to t
  + trailing 8-week mean of (NDPSR week price - CME spot average for that week)].
Compared with the NDPSR-only nowcast (remaining weeks at the latest NDPSR week) and with the futures close on t.
Writes data/dairy/derived/dairy_spot.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "ams" / "cme_daily_dairy"
OUT = ROOT / "data" / "dairy" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dairy_class import components, regime, load_class_prices, weekly_ndpsr  # noqa: E402

CODES = "FGHJKMNQUVXZ"


def spot():
    fs = sorted(RAW.glob("*.csv"))
    if not fs:
        return None
    d = pd.concat([pd.read_csv(f) for f in fs])
    d["date"] = pd.to_datetime(d.report_date)
    d["px"] = pd.to_numeric(d.close_price, errors="coerce")
    c, g = d.commodity.astype(str).str.lower(), d.get("grade", pd.Series("", index=d.index)).astype(str).str.lower()
    key = np.select([c.str.contains("cheese") & (g.str.contains("block") | d.get("package", pd.Series("", index=d.index)).astype(str).str.lower().str.contains("block")),
                     c.str.contains("cheese") & (g.str.contains("barrel") | d.get("package", pd.Series("", index=d.index)).astype(str).str.lower().str.contains("barrel")),
                     c.str.contains("butter"), c.str.contains("nonfat"), c.str.contains("whey")],
                    ["cheese", "barrels", "butter", "ndm", "whey"], default="")
    d["product"] = key
    d = d[d["product"] != ""].dropna(subset=["px"])
    return d.pivot_table(index="date", columns="product", values="px", aggfunc="last").sort_index()


def run(sp):
    cp = load_class_prices()
    w = weekly_ndpsr()
    w = w[w.sales > 0]
    piv = w.pivot_table(index="week", columns="product", values="price").sort_index()
    sales = w.pivot_table(index="week", columns="product", values="sales").sort_index()
    futs = {s: pd.read_csv(ROOT / "data" / "contracts" / f"{s}.csv", parse_dates=["date"]) for s in ("DC", "GDK")}
    # weekly CME spot average (Mon-Fri, week ending Saturday like NDPSR) and NDPSR - spot spread
    spw = sp.resample("W-SAT").mean()
    prods = ["cheese", "butter", "ndm", "whey"]
    spread = (piv[prods] - spw.reindex(piv.index)[prods])
    rows = []
    for week in piv.index:
        t = week + pd.Timedelta(days=4)
        if t < sp.index.min() + pd.Timedelta(days=70):
            continue
        latest = piv.loc[week]
        M = week.to_period("M")
        if M not in cp.index or latest[prods].isna().any():
            continue
        wk = piv[(piv.index.to_period("M") == M) & (piv.index <= week)]
        sl = sales.loc[wk.index]
        n_total = len(pd.date_range(M.start_time, M.end_time, freq="W-SAT"))
        remain = max(n_total - len(wk), 0)
        s5 = sp[(sp.index <= t)].tail(5)[prods].mean()
        sprd = spread[spread.index < week].tail(8).mean()
        est = {}
        for name, rem in (("ndpsr", latest[prods]), ("spot", s5 + sprd)):
            px = {}
            for p in prods:
                s_done, v_done = (wk[p] * sl[p]).sum(), sl[p].sum()
                avg_v = v_done / max(len(wk), 1)
                px[p] = (s_done + rem[p] * avg_v * remain) / (v_done + avg_v * remain) if (v_done + avg_v * remain) else rem[p]
            est[name] = components(px["cheese"], px["butter"], px["ndm"], px["whey"], regime(M))
        for col, sym, cpcol in (("class3", "DC", "class_3_Price"), ("class4", "GDK", "class_4_Price")):
            f = futs[sym]
            fc = f[f.contract == f"{sym}{CODES[M.month - 1]}{M.year}"].set_index("date").close[:t]
            if fc.empty or (t - fc.index[-1]).days > 6:
                continue
            rows.append(dict(origin=str(t.date()), month=str(M), weeks_done=len(wk), remain=remain, cls=col, actual=cp[cpcol][M],
                             ndpsr=est["ndpsr"][col], spot=est["spot"][col], futures=fc.iloc[-1]))
    return pd.DataFrame(rows)


def score(d):
    out = {}
    for cls, g0 in d.groupby("cls"):
        res = {}
        for lab, g in [("all", g0), ("2+ weeks left", g0[g0.remain >= 2]), ("1 week left", g0[g0.remain == 1]), ("final week", g0[g0.remain == 0])]:
            if len(g) < 8:
                continue
            gap, conv = g.spot - g.futures, g.actual - g.futures
            big = g[gap.abs() >= 0.25]
            res[lab] = {"n": int(len(g)), "mae_ndpsr": round(float((g.ndpsr - g.actual).abs().mean()), 3),
                        "mae_spot": round(float((g.spot - g.actual).abs().mean()), 3), "mae_futures": round(float((g.futures - g.actual).abs().mean()), 3),
                        "gap_corr": round(float(np.corrcoef(gap, conv)[0, 1]), 2), "direction_hit": round(float((np.sign(gap) == np.sign(conv)).mean()), 2),
                        "big_gap_n": int(len(big)), "big_gap_hit": round(float((np.sign(big.spot - big.futures) == np.sign(big.actual - big.futures)).mean()), 2) if len(big) else None}
        out[cls] = res
    return out


def current(sp):
    """Today's spot-informed nowcast for the current month (uses the latest NDPSR weeks)."""
    cp = load_class_prices()
    w = weekly_ndpsr()
    w = w[w.sales > 0]
    piv = w.pivot_table(index="week", columns="product", values="price").sort_index()
    sales = w.pivot_table(index="week", columns="product", values="sales").sort_index()
    prods = ["cheese", "butter", "ndm", "whey"]
    spw = sp.resample("W-SAT").mean()
    sprd = (piv[prods] - spw.reindex(piv.index)[prods]).dropna().tail(8).mean()
    today = sp.index.max()
    M = today.to_period("M")
    if M in cp.index:
        return None
    wk = piv[piv.index.to_period("M") == M]
    sl = sales.loc[wk.index]
    n_total = len(pd.date_range(M.start_time, M.end_time, freq="W-SAT"))
    remain = max(n_total - len(wk), 0)
    s5 = sp.tail(5)[prods].mean()
    px = {}
    for p in prods:
        s_done, v_done = (wk[p] * sl[p]).sum(), sl[p].sum()
        avg_v = v_done / max(len(wk), 1) if len(wk) else 1.0
        rem = s5[p] + sprd[p]
        px[p] = (s_done + rem * avg_v * remain) / (v_done + avg_v * remain)
    c = components(px["cheese"], px["butter"], px["ndm"], px["whey"], regime(M))
    return {"month": str(M), "spot_date": str(today.date()), "weeks_done": int(len(wk)), "weeks_left": int(remain),
            "spot": {p: round(float(sp[p].dropna().iloc[-1]), 4) for p in sp.columns}, "spread": {p: round(float(v), 4) for p, v in sprd.items()},
            "class3": round(float(c["class3"]), 2), "class4": round(float(c["class4"]), 2)}


if __name__ == "__main__":
    sp = spot()
    if sp is None or sp.empty:
        sys.exit("no CME spot dairy data yet")
    d = run(sp)
    res = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "since": str(sp.index.min().date()),
           "tests": score(d) if len(d) else None, "current": current(sp),
           "spot_series": {"date": [str(x.date()) for x in sp.index[-260:]], **{p: [None if pd.isna(v) else round(float(v), 4) for v in sp[p].iloc[-260:]] for p in sp.columns}}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "dairy_spot.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("since", "tests", "current")}, indent=1))
