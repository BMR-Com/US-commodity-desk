"""Backtests for the dairy models.

A. Nowcast: after k NDPSR weeks of a month, how close is the month-to-date Class III / IV to the
   announced price? Benchmarks: front-month futures close on the day that k-th week was
   published (approx. week end + 4 days) and last month's announced price (no change).
   Note: uses the latest-revised weekly values, so it slightly flatters the nowcast (revisions are
   usually small).
B. S&D -> price: do stock and flow signals predict 1/3/6-month changes in the NDPSR monthly price
   of cheese, butter, NDM and dry whey? Features are lagged 2 months (publication lag of NASS/ERS),
   walk-forward expanding-window OLS from 2016, compared with a no-change forecast.
Writes data/dairy/derived/backtest.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dairy_class import components, regime, load_class_prices, weekly_ndpsr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "dairy" / "derived"


def nowcast_backtest():
    cp = load_class_prices()
    w = weekly_ndpsr()
    w["month"] = w.week.dt.to_period("M")
    px = {}
    for s, col in (("DC", "class3"), ("GDK", "class4")):
        p = pd.read_csv(ROOT / "data" / "prices" / f"{s}.csv", parse_dates=["date"]).set_index("date").c1_close.dropna()
        px[col] = p
    rows = []
    for m in cp.index:
        if m < pd.Period("2013-02", "M"):
            continue
        mw = w[w.month == m]
        weeks = sorted(mw.week.unique())
        prev = cp.index[cp.index.get_loc(m) - 1] if cp.index.get_loc(m) > 0 else None
        for k in range(1, len(weeks) + 1):
            sel = mw[mw.week.isin(weeks[:k])]
            sel = sel[sel.sales > 0]
            g = sel.groupby("product").apply(lambda x: (x.price * x.sales).sum() / x.sales.sum(), include_groups=False)
            if not {"cheese", "butter", "ndm", "whey"} <= set(g.index):
                continue
            c = components(g.cheese, g.butter, g.ndm, g.whey, regime(m))
            asof = pd.Timestamp(weeks[k - 1]) + pd.Timedelta(days=4)
            for col, ams in (("class3", cp.loc[m, "class_3_Price"]), ("class4", cp.loc[m, "class_4_Price"])):
                fut = px[col][:asof]
                # continuous front month rolls before the month's settlement; only compare inside the month
                if asof > m.end_time:
                    fut = fut.iloc[:0]
                rows.append(dict(month=str(m), k=k, last=k == len(weeks), cls=col, actual=ams, nowcast=c[col],
                                 futures=fut.iloc[-1] if len(fut) and (asof - fut.index[-1]).days < 7 else np.nan,
                                 prev=cp.loc[prev, "class_3_Price" if col == "class3" else "class_4_Price"] if prev is not None else np.nan))
    d = pd.DataFrame(rows)
    for f in ("nowcast", "futures", "prev"):
        d[f + "_err"] = (d[f] - d.actual).abs()
    res = {}
    for cls in ("class3", "class4"):
        x = d[(d.cls == cls)]
        for per, xx in (("2013-2026", x), ("2019-2026", x[x.month >= "2019-01"])):
            tab = xx.groupby("k")[["nowcast_err", "futures_err", "prev_err"]].mean().round(3)
            tab["n"] = xx.groupby("k").size()
            # combined: futures blended with nowcast
            tab["nowcast_beats_futures_pct"] = xx.groupby("k").apply(lambda z: round(100 * (z.nowcast_err < z.futures_err).mean(), 0), include_groups=False)
            res.setdefault(cls, {})[per] = {int(k): {c: (None if pd.isna(v) else float(v)) for c, v in r.items()} for k, r in tab.iterrows()}
    return res, d


def sd_backtest():
    sd = json.loads((OUT / "sd.json").read_text())
    prods = {"cheese": "cheese_american", "butter": "butter", "ndm": "ndm_smp", "whey": "dry_whey"}
    frames = []
    for name, key in prods.items():
        s = pd.DataFrame(sd["products"][key]["series"])
        s["month"] = pd.PeriodIndex(s.month, freq="M")
        s = s.set_index("month").sort_index()
        if "price" not in s:
            continue
        st = s.ending_stocks
        avg3 = sum(st.shift(12 * k) for k in (1, 2, 3)) / 3
        f = pd.DataFrame(index=s.index)
        f["stocks_vs_3y"] = 100 * (st / avg3 - 1)
        f["mou"] = s.months_of_use
        f["mou_vs_3y"] = s.months_of_use - sum(s.months_of_use.shift(12 * k) for k in (1, 2, 3)) / 3
        f["prod_yoy"] = 100 * (s.production.rolling(3).sum() / s.production.rolling(3).sum().shift(12) - 1)
        f["exp_yoy"] = 100 * (s.exports.rolling(3).sum() / s.exports.rolling(3).sum().shift(12) - 1)
        f = f.shift(2)  # known ~2 months later
        f["price"] = s.price
        f["mom_3"] = 100 * np.log(s.price / s.price.shift(3))
        for h in (1, 3, 6):
            f[f"y{h}"] = 100 * np.log(s.price.shift(-h) / s.price)
        f["product"] = name
        frames.append(f.dropna(subset=["price"]))
    data = pd.concat(frames)
    feats_sets = {"stocks": ["stocks_vs_3y"], "stocks+use": ["stocks_vs_3y", "mou_vs_3y"],
                  "stocks+flows": ["stocks_vs_3y", "mou_vs_3y", "prod_yoy", "exp_yoy"],
                  "stocks+flows+momentum": ["stocks_vs_3y", "mou_vs_3y", "prod_yoy", "exp_yoy", "mom_3"]}
    res = {}
    for h in (1, 3, 6):
        for fs_name, fs in feats_sets.items():
            for prod in list(prods) + ["pooled"]:
                dd = data if prod == "pooled" else data[data["product"] == prod]
                dd = dd.dropna(subset=fs + [f"y{h}"]).copy()
                dd["t"] = dd.index
                months = sorted(dd.t.unique())
                preds = []
                for m in months:
                    if m < pd.Period("2016-01", "M"):
                        continue
                    train = dd[dd.t <= m - h]  # target must be realised before m
                    test = dd[dd.t == m]
                    if len(train) < 36 or test.empty:
                        continue
                    X = np.c_[np.ones(len(train)), train[fs].values]
                    if prod == "pooled":
                        X = np.c_[X, pd.get_dummies(train["product"]).values[:, 1:]]
                    beta, *_ = np.linalg.lstsq(X, train[f"y{h}"].values, rcond=None)
                    Xt = np.c_[np.ones(len(test)), test[fs].values]
                    if prod == "pooled":
                        Xt = np.c_[Xt, pd.get_dummies(test["product"]).reindex(columns=sorted(dd["product"].unique()), fill_value=0).values[:, 1:]]
                    for yhat, y in zip(Xt @ beta, test[f"y{h}"].values):
                        preds.append((yhat, y))
                if len(preds) < 24:
                    continue
                p = np.array(preds)
                sse, sse0 = ((p[:, 1] - p[:, 0]) ** 2).sum(), (p[:, 1] ** 2).sum()
                hit = (np.sign(p[:, 0]) == np.sign(p[:, 1]))[p[:, 1] != 0].mean()
                res.setdefault(f"h{h}", {}).setdefault(fs_name, {})[prod] = {
                    "oos_r2_vs_no_change": round(1 - sse / sse0, 3), "hit_rate": round(float(hit), 3), "n": len(p),
                    "corr": round(float(np.corrcoef(p[:, 0], p[:, 1])[0, 1]), 3)}
    # simple univariate evidence: in-sample correlation of stocks_vs_3y with forward changes
    uni = {}
    for prod in prods:
        dd = data[data["product"] == prod]
        uni[prod] = {f"h{h}": round(float(dd[["stocks_vs_3y", f"y{h}"]].dropna().corr().iloc[0, 1]), 3) for h in (1, 3, 6)}
    return res, uni


if __name__ == "__main__":
    nc, detail = nowcast_backtest()
    sdres, uni = sd_backtest()
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "nowcast": nc, "sd_to_price": sdres, "stocks_corr": uni}
    (OUT / "backtest.json").write_text(json.dumps(out, indent=1))
    print("NOWCAST mean abs error $/cwt by weeks-in (2019-2026)")
    for cls in ("class3", "class4"):
        print(cls); print(pd.DataFrame(nc[cls]["2019-2026"]).T.to_string())
    print("\nS&D -> price, walk-forward out of sample (R2 vs no-change; hit rate)")
    for h, v in sdres.items():
        for fs, pr in v.items():
            print(h, fs.ljust(22), {k: (x["oos_r2_vs_no_change"], x["hit_rate"]) for k, x in pr.items()})
    print("\nstocks_vs_3y corr with forward % change:", uni)
