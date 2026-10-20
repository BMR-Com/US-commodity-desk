"""Export sales (FAS ESR) pace vs USDA WASDE export forecasts, with backtests.

Commitments = accumulated exports + outstanding sales for the current marketing year.
Commitment-implied exports at week w = commitments(w) / avg[commitments_m(w) / final WASDE exports_m] over the
prior 5 completed marketing years (units cancel, so the ratio also absorbs ESR vs Census coverage).
Backtests (MY 2011+): implied vs final at each week vs USDA's forecast in force that week; does
(implied - USDA) call the direction of USDA's next export revision; does weekly net sales vs the pace
needed move the front month on release day (release = week ending + 7 days, Thursday).
Writes data/grains/derived/sales.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "grains" / "raw" / "export_sales"
OUT = ROOT / "data" / "grains" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grains_wasde import tidy, load, FILES  # noqa: E402

# key: (ESR dir, WASDE key, MT -> WASDE unit, unit label, futures symbol)
COMS = {"corn": ("corn", "corn", 39.368 / 1e6, "mil bu", "ZC"),
        "soybeans": ("soybeans", "soybeans", 36.744 / 1e6, "mil bu", "ZS"),
        "meal": ("soybean_meal", "meal", 1.10231 / 1e3, "thou short tons", "ZM"),
        "oil": ("soybean_oil", "oil", 2204.62 / 1e6, "mil lb", "ZL"),
        "wheat": ("wheat_all", "wheat", 36.744 / 1e6, "mil bu", "ZW")}
CLASSES = {"HRW": "wheat_hrw", "SRW": "wheat_srw", "HRS": "wheat_hrs", "White": "wheat_white", "Durum": "wheat_durum"}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}
COLS = ["weeklyExports", "accumulatedExports", "outstandingSales", "grossNewSales", "currentMYNetSales",
        "currentMYTotalCommitment", "nextMYOutstandingSales", "nextMYNetSales"]


def countries():
    p = RAW / "countries.json"
    if not p.exists():
        return {}
    return {c["countryCode"]: c["countryDescription"].strip().title() for c in json.loads(p.read_text())}


def esr(sub, by_country=False):
    """Weekly totals (MT) per marketing year. FAS 'marketYear' N = WASDE 'N-1/N'."""
    fs = sorted((RAW / sub).glob("MY*.csv"))
    out = []
    for f in fs:
        my = int(f.stem[2:])
        d = pd.read_csv(f)
        if d.empty:
            continue
        d["week"] = pd.to_datetime(d.weekEndingDate)
        d["my"] = f"{my - 1}/{str(my)[-2:]}"
        out.append(d)
    if not out:
        return None
    d = pd.concat(out)
    if by_country:
        return d
    g = d.groupby(["my", "week"])[COLS].sum().reset_index().sort_values(["my", "week"])
    g["wk"] = g.groupby("my").cumcount() + 1
    g["commit"] = g.accumulatedExports + g.outstandingSales
    return g


def wasde_exports(key):
    d = tidy(load(FILES[key]))
    d = d[(d.region == "United States") & (d.attr == "exports")].copy()
    d["release"] = [pd.Timestamp(int(r.split()[1]), MONTHS[r.split()[0]], 12) for r in d.report]
    return d


def front_returns(sym):
    p = ROOT / "data" / "prices" / f"{sym}.csv"
    if not p.exists():
        return None
    from cot_backtest import roll_adjusted_index
    return roll_adjusted_index(sym)


def run(com):
    sub, key, conv, unit, sym = COMS[com]
    g = esr(sub)
    if g is None:
        return None
    wx = wasde_exports(key)
    final = wx.sort_values("wasde").groupby("my").value.last()
    mys = sorted(g.my.unique())
    nweeks = g.groupby("my").wk.max()
    complete = [m for m in mys if nweeks[m] >= 50 and m in final.index]
    rows = []
    for my in mys:
        prior = [m for m in complete if m < my][-5:]
        if len(prior) < 3:
            continue
        for _, r in g[g.my == my].iterrows():
            sh = [g[(g.my == m) & (g.wk == r.wk)].commit.iloc[0] / final[m] for m in prior if len(g[(g.my == m) & (g.wk == r.wk)])]
            if not sh:
                continue
            usda = wx[(wx.my == my) & (wx.release <= r.week)].sort_values("wasde")
            nxt = wx[(wx.my == my) & (wx.release > r.week)].sort_values("wasde")
            rows.append(dict(my=my, wk=int(r.wk), week=r.week, commit=r.commit, net=r.currentMYNetSales, shipped=r.weeklyExports,
                             implied=r.commit / np.mean(sh), share=np.mean(sh),
                             usda=usda.value.iloc[-1] if len(usda) else np.nan, next_usda=nxt.value.iloc[0] if len(nxt) else np.nan,
                             final=final[my] if my in complete else np.nan))
    r = pd.DataFrame(rows)
    if r.empty:
        return None
    r.to_csv(OUT / f"sales_detail_{com}.csv", index=False)
    # ---- backtests
    bt = r.dropna(subset=["final", "usda"])
    test = None
    if len(bt):
        bt = bt.assign(err=(bt.implied / bt.final - 1).abs() * 100, err_usda=(bt.usda / bt.final - 1).abs() * 100)
        rv = bt.dropna(subset=["next_usda"])
        rv = rv[rv.next_usda != rv.usda]
        buckets = pd.cut(bt.wk, [0, 8, 17, 26, 35, 44, 53], labels=[8, 17, 26, 35, 44, 53])
        by = {int(k): {"mae_pct": round(float(x.err.mean()), 2), "mae_usda_pct": round(float(x.err_usda.mean()), 2), "n": int(x.my.nunique())}
              for k, x in bt.groupby(buckets, observed=True)}
        hit = (np.sign(rv.implied - rv.usda) == np.sign(rv.next_usda - rv.usda))
        big = rv[(rv.implied / rv.usda - 1).abs() > 0.03]
        test = {"by_week": by, "n_years": int(bt.my.nunique()),
                "revision_hit": round(float(hit.mean()), 2) if len(rv) else None, "revision_n": int(rv.my.nunique()),
                "revision_hit_gap3": round(float((np.sign(big.implied - big.usda) == np.sign(big.next_usda - big.usda)).mean()), 2) if len(big) else None,
                "revision_n_gap3": int(len(big))}
    # ---- release-day price reaction: net sales vs pace needed for USDA
    price = None
    idx = front_returns(sym)
    if idx is not None:
        x = r.dropna(subset=["usda"]).copy()
        x = x[x.my >= "2011/12"]
        wk_left = (52 - x.wk).clip(lower=4)
        x["need"] = (x.usda / conv * 1.0 - x.commit) / wk_left  # MT per week still needed (rough: ignores carry-over sales)
        x["avg4"] = x.groupby("my").net.transform(lambda s: s.rolling(4, min_periods=2).mean().shift(1))
        x["surprise"] = (x.net - x.avg4) / x.avg4.abs().clip(lower=1)
        rel = x.week + pd.Timedelta(days=7)
        rets = []
        for t in rel:
            a, b = idx[:t], idx[:t - pd.Timedelta(days=1)]
            rets.append(100 * (a.iloc[-1] / b.iloc[-1] - 1) if len(a) and len(b) and a.index[-1] == t else np.nan)
        x["ret"] = rets
        x = x.replace([np.inf, -np.inf], np.nan).dropna(subset=["ret", "surprise"])
        x = x[x.wk >= 3]
        if len(x) > 50:
            hi = x[x.surprise > 0.5]
            lo = x[x.surprise < -0.5]
            price = {"n": int(len(x)), "corr": round(float(x.surprise.clip(-3, 3).corr(x.ret)), 3),
                     "big_up_n": int(len(hi)), "big_up_ret": round(float(hi.ret.mean()), 2) if len(hi) else None,
                     "big_up_hit": round(float((hi.ret > 0).mean()), 2) if len(hi) else None,
                     "big_dn_n": int(len(lo)), "big_dn_ret": round(float(lo.ret.mean()), 2) if len(lo) else None,
                     "big_dn_hit": round(float((lo.ret < 0).mean()), 2) if len(lo) else None,
                     "note": "release day = week ending + 7 days (Thursday); holiday weeks are slightly misdated"}
    # ---- current
    cur = mys[-1]
    if g[g.my == cur].wk.max() < 2 and len(mys) > 1:  # new MY only just started; keep it but also report
        pass
    c = g[g.my == cur]
    p = g[g.my == mys[-2]] if len(mys) > 1 else g.iloc[0:0]
    last = c.iloc[-1]
    wk = int(last.wk)
    usda_now = wx[wx.my == cur].sort_values("wasde").value
    usda_now = float(usda_now.iloc[-1]) if len(usda_now) else np.nan
    prior = complete[-5:]
    prof = [np.mean([g[(g.my == m) & (g.wk == k)].commit.iloc[0] / final[m] for m in prior if len(g[(g.my == m) & (g.wk == k)])] or [np.nan])
            for k in range(1, 53)]
    rc = r[r.my == cur]
    implied = float(rc.implied.iloc[-1]) if len(rc) else np.nan
    prev_same = p[p.wk == wk].commit
    net4 = float(c.currentMYNetSales.tail(4).mean())
    need = (usda_now / conv - last.commit) / max(52 - wk, 1)
    near = None
    if test:
        k = min(test["by_week"], key=lambda z: abs(z - wk) if z >= wk else 99)
        near = test["by_week"][k]
    out = {"my": cur, "unit": unit, "as_of": str(last.week.date()), "week": wk,
           "commit": round(float(last.commit * conv), 1), "shipped": round(float(last.accumulatedExports * conv), 1),
           "outstanding": round(float(last.outstandingSales * conv), 1),
           "commit_prev": round(float(prev_same.iloc[0] * conv), 1) if len(prev_same) else None,
           "usda": usda_now, "pct_of_usda": round(float(100 * last.commit * conv / usda_now), 1) if usda_now == usda_now else None,
           "avg_pct": round(float(100 * prof[wk - 1] * conv), 1) if wk <= 52 and prof[wk - 1] == prof[wk - 1] else None,
           "implied": round(implied, 0) if implied == implied else None,
           "net_last": round(float(last.currentMYNetSales * conv), 2), "net_4wk": round(net4 * conv, 2),
           "need_weekly": round(float(need * conv), 2), "next_my_outstanding": round(float(last.nextMYOutstandingSales * conv), 1),
           "weeks": list(range(1, 53)),
           "cur": [round(float(v * conv), 1) for v in c.commit] + [None] * (52 - len(c)),
           "prev": [round(float(v * conv), 1) for v in p.commit.iloc[:52]] + [None] * max(0, 52 - len(p)),
           "avg_path": [None if v != v else round(float(v * usda_now * conv), 1) for v in prof],  # avg commitments path that ends at USDA,
           "net_weeks": [str(d.date()) for d in c.week.tail(20)], "net_series": [round(float(v * conv), 2) for v in c.currentMYNetSales.tail(20)],
           "test": None if not test else {**test, "near": near}, "price": price}
    return out


def destinations(sub, conv, n=8):
    d = esr(sub, by_country=True)
    if d is None:
        return None
    names = countries()
    d["commit"] = d.accumulatedExports + d.outstandingSales
    mys = sorted(d.my.unique())
    cur, prev = mys[-1], mys[-2]
    last = d[d.my == cur].week.max()
    wk = d[(d.my == cur)].week.drop_duplicates().sort_values().tolist().index(last)
    pw = d[d.my == prev].week.drop_duplicates().sort_values().tolist()
    pweek = pw[min(wk, len(pw) - 1)]
    a = d[(d.my == cur) & (d.week == last)].groupby("countryCode").commit.sum()
    b = d[(d.my == prev) & (d.week == pweek)].groupby("countryCode").commit.sum()
    t = pd.DataFrame({"cur": a, "prev": b}).fillna(0)
    t = t[t.index != 1999] if 1999 in t.index else t  # keep 'unknown' (code varies) — dropped only if a known aggregate code
    t = t.sort_values("cur", ascending=False)
    tot_c, tot_p = t.cur.sum(), t.prev.sum()
    rows = [{"name": names.get(k, str(k)), "cur": round(float(v.cur * conv), 1), "prev": round(float(v.prev * conv), 1),
             "share": round(float(100 * v.cur / tot_c), 1) if tot_c else None} for k, v in t.head(n).iterrows()]
    return {"as_of": str(last.date()), "prev_week": str(pweek.date()), "rows": rows,
            "total_cur": round(float(tot_c * conv), 1), "total_prev": round(float(tot_p * conv), 1)}


def wheat_classes():
    conv = 36.744 / 1e6
    out = []
    for name, sub in CLASSES.items():
        g = esr(sub)
        if g is None:
            continue
        mys = sorted(g.my.unique())
        c, p = g[g.my == mys[-1]], g[g.my == mys[-2]]
        wk = int(c.wk.max())
        ps = p[p.wk == wk].commit
        pf = p.commit.iloc[-1] if len(p) else np.nan
        out.append({"cls": name, "commit": round(float(c.commit.iloc[-1] * conv), 1),
                    "prev": round(float(ps.iloc[0] * conv), 1) if len(ps) else None,
                    "yoy_pct": round(float(100 * (c.commit.iloc[-1] / ps.iloc[0] - 1)), 1) if len(ps) and ps.iloc[0] else None,
                    "prev_share_by_now": round(float(100 * ps.iloc[0] / pf), 1) if len(ps) and pf else None,
                    "net_4wk": round(float(c.currentMYNetSales.tail(4).mean() * conv), 2)})
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for com, (sub, key, conv, unit, sym) in COMS.items():
        o = run(com)
        if not o:
            print(com, "no data")
            continue
        o["destinations"] = destinations(sub, conv)
        res[com] = o
        print(com, {k: o[k] for k in ("my", "week", "commit", "commit_prev", "usda", "pct_of_usda", "avg_pct", "implied", "net_4wk", "need_weekly")})
        print("   test", json.dumps({k: v for k, v in (o["test"] or {}).items() if k != "by_week"}), "price", json.dumps(o["price"]))
    if "wheat" in res:
        res["wheat"]["classes"] = wheat_classes()
        res["kc"] = res["wheat"]
    (OUT / "sales.json").write_text(json.dumps(res, separators=(",", ":"), default=str).replace("NaN", "null"))
