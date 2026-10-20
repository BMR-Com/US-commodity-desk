"""Dairy convergence backtest: fundamental estimate of the announced class price vs futures.

Target: announced Class III / IV for month T (the futures' cash settlement).
Origins: each weekly NDPSR release (week end + 4 days), 2013 on.
Forecasts for months T = current .. current+6:
  - current month: sales-weighted completed weeks + latest week carried for the remaining weeks
  - later months: latest-week product prices through the formula (persistence), and a variant
    adding the average seasonal change in the class price from origin month to T (past years only)
Benchmark: contract T's futures close on the origin day (per-contract history).
Writes data/dairy/derived/dairy_convergence.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "dairy" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dairy_class import components, regime, load_class_prices, weekly_ndpsr  # noqa: E402

CODES = "FGHJKMNQUVXZ"


def run():
    cp = load_class_prices()
    w = weekly_ndpsr()
    w = w[w.sales > 0]
    piv = w.pivot_table(index="week", columns="product", values="price").sort_index()
    sales = w.pivot_table(index="week", columns="product", values="sales").sort_index()
    futs = {s: pd.read_csv(ROOT / "data" / "contracts" / f"{s}.csv", parse_dates=["date"]) for s in ("DC", "GDK")}
    # seasonal: average log change of class price from month a to month b, using years before origin
    cls = {"class3": cp.class_3_Price, "class4": cp.class_4_Price}
    rows = []
    for week in piv.index:
        if week < pd.Timestamp("2013-01-01"):
            continue
        t = week + pd.Timedelta(days=4)
        latest = piv.loc[week]
        if latest[["cheese", "butter", "ndm", "whey"]].isna().any():
            continue
        M = week.to_period("M")
        for h in range(0, 7):
            T = M + h
            if T not in cp.index:
                continue
            if h == 0:
                wk = piv[(piv.index.to_period("M") == M) & (piv.index <= week)]
                sl = sales.loc[wk.index]
                n_weeks_total = len([d for d in pd.date_range(M.start_time, M.end_time, freq="W-SAT")])
                remain = max(n_weeks_total - len(wk), 0)
                px = {}
                for p in ("cheese", "butter", "ndm", "whey"):
                    s_done = (wk[p] * sl[p]).sum()
                    v_done = sl[p].sum()
                    avg_v = v_done / max(len(wk), 1)
                    px[p] = (s_done + latest[p] * avg_v * remain) / (v_done + avg_v * remain)
            else:
                px = {p: latest[p] for p in ("cheese", "butter", "ndm", "whey")}
            c = components(px["cheese"], px["butter"], px["ndm"], px["whey"], regime(T))
            for col, sym in (("class3", "DC"), ("class4", "GDK")):
                hist = cls[col]
                past = [y for y in range(T.year - 6, T.year) if pd.Period(f"{y}-{M.month:02d}", "M") in hist.index
                        and pd.Period(f"{y + (T.month < M.month)}-{T.month:02d}", "M") in hist.index
                        and pd.Period(f"{y + (T.month < M.month)}-{T.month:02d}", "M") < M]
                seas = np.mean([np.log(hist[pd.Period(f"{y + (T.month < M.month)}-{T.month:02d}", "M")] / hist[pd.Period(f"{y}-{M.month:02d}", "M")]) for y in past]) if (h and past) else 0.0
                f = futs[sym]
                fc = f[f.contract == f"{sym}{CODES[T.month - 1]}{T.year}"].set_index("date").close[:t]
                if fc.empty or (t - fc.index[-1]).days > 6:
                    continue
                rows.append(dict(origin=str(t.date()), target=str(T), h=h, cls=col, actual=hist[T],
                                 persist=c[col], seasonal=c[col] * np.exp(seas), futures=fc.iloc[-1]))
    return pd.DataFrame(rows)


def score(d):
    out = {}
    for cls in ("class3", "class4"):
        x = d[d.cls == cls]
        for h, g in x.groupby("h"):
            r = {"n": int(len(g))}
            for m in ("persist", "seasonal", "futures"):
                r["mae_" + m] = round(float((g[m] - g.actual).abs().mean()), 3)
            gap, conv = g.seasonal - g.futures, g.actual - g.futures
            r["gap_vs_convergence_corr"] = round(float(np.corrcoef(gap, conv)[0, 1]), 3)
            r["direction_hit"] = round(float((np.sign(gap) == np.sign(conv)).mean()), 2)
            big = g[gap.abs() >= 1.0]
            if len(big) >= 10:
                r["when_gap_ge_1"] = {"n": int(len(big)), "hit": round(float((np.sign(big.seasonal - big.futures) == np.sign(big.actual - big.futures)).mean()), 2)}
            out.setdefault(cls, {})[int(h)] = r
    return out


if __name__ == "__main__":
    d = run()
    res = {"2013-2026": score(d), "2019-2026": score(d[d.origin >= "2019-01-01"])}
    (OUT / "dairy_convergence.json").write_text(json.dumps({"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "tests": res}, indent=1))
    for per, v in res.items():
        print(per)
        for cls, hs in v.items():
            print(" ", cls)
            for h, r in hs.items():
                print("   h", h, r)
