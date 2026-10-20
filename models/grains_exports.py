"""Export pace from FGIS inspections vs USDA WASDE export forecasts, with backtests.

Marketing years: corn & soybeans Sep-Aug, wheat Jun-May. Inspections understate Census exports
(rail to Mexico/Canada etc.), so the pace-implied figure is
    cum_inspections(week w) / avg share shipped by week w (prior 5 MYs) * avg (final WASDE exports / total inspections) (prior 5 MYs)
Backtests (MY 2010+): implied vs final WASDE exports at each week, vs USDA's forecast in force that
week; and whether (implied - USDA) calls the direction of USDA's next export revision.
Writes data/grains/derived/exports.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "grains" / "raw" / "inspections"
OUT = ROOT / "data" / "grains" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grains_wasde import tidy, load, FILES  # noqa: E402

COMS = {"corn": ("CORN", 9), "soybeans": ("SOYBEANS", 9), "wheat": ("WHEAT", 6)}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}


def weekly(grain):
    d = pd.concat([pd.read_csv(f) for f in sorted(RAW.glob("weekly_CY*.csv"))])
    d = d[d.grain == grain]
    d["week"] = pd.to_datetime(d.week)
    bu_per_mt = 39.368 if grain == "CORN" else 36.744
    return d.groupby("week").mt.sum().sort_index() * bu_per_mt / 1e6  # million bushels


def my_label(week, start_month):
    y = week.year if week.month >= start_month else week.year - 1
    return f"{y}/{str(y + 1)[-2:]}"


def wasde_exports(com):
    d = tidy(load(FILES[com]))
    d = d[(d.region == "United States") & (d.attr == "exports")].copy()
    d["release"] = [pd.Timestamp(int(r.split()[1]), MONTHS[r.split()[0]], 12) for r in d.report]
    return d


def run(com):
    grain, sm = COMS[com]
    w = weekly(grain)
    df = w.to_frame("mbu")
    df["my"] = [my_label(x, sm) for x in df.index]
    df["wk"] = df.groupby("my").cumcount() + 1
    df["cum"] = df.groupby("my").mbu.cumsum()
    tot = df.groupby("my").mbu.sum()
    wx = wasde_exports(com)
    final = wx.sort_values("wasde").groupby("my").value.last()
    mys = sorted(df.my.unique())
    complete = [m for m in mys if df[df.my == m].wk.max() >= 50]
    rows = []
    for my in mys:
        prior = [m for m in complete if m < my][-5:]
        if len(prior) < 3:
            continue
        ratio = np.mean([final[m] / tot[m] for m in prior if m in final.index])
        g = df[df.my == my]
        for _, r in g.iterrows():
            shares = []
            for m in prior:
                pm = df[(df.my == m) & (df.wk == r.wk)]
                if len(pm):
                    shares.append(pm.cum.iloc[0] / tot[m])
            if not shares:
                continue
            implied = r.cum / np.mean(shares) * ratio
            usda = wx[(wx.my == my) & (wx.release <= r.name)].sort_values("wasde")
            nxt = wx[(wx.my == my) & (wx.release > r.name)].sort_values("wasde")
            rows.append(dict(my=my, wk=int(r.wk), week=r.name, cum=r.cum, implied=implied, avg_share=np.mean(shares),
                             usda=usda.value.iloc[-1] if len(usda) else np.nan,
                             next_usda=nxt.value.iloc[0] if len(nxt) else np.nan,
                             final=final.get(my, np.nan) if my in complete else np.nan))
    r = pd.DataFrame(rows)
    test = None
    bt = r.dropna(subset=["final", "usda"])
    bt = bt[(bt.my >= "2010/11")]
    if len(bt):
        bt = bt.assign(err=(bt.implied / bt.final - 1).abs() * 100, err_usda=(bt.usda / bt.final - 1).abs() * 100)
        rv = bt.dropna(subset=["next_usda"])
        rv = rv[rv.next_usda != rv.usda]
        test_by_wk = {int(k): {"mae_pct": round(float(g.err.mean()), 2), "mae_usda_pct": round(float(g.err_usda.mean()), 2)}
                      for k, g in bt.groupby(pd.cut(bt.wk, [0, 8, 17, 26, 35, 44, 53], labels=[8, 17, 26, 35, 44, 53]), observed=True)}
        test = {"by_week": test_by_wk, "n_years": int(bt.my.nunique()),
                "revision_hit_all": round(float((np.sign(rv.implied - rv.usda) == np.sign(rv.next_usda - rv.usda)).mean()), 2) if len(rv) else None,
                "revision_n": int(len(rv))}
    cur_my = mys[-1]
    c = r[r.my == cur_my]
    prev_my = mys[-2]
    p = df[df.my == prev_my]
    if c.empty:
        return None, test
    last = c.iloc[-1]
    usda_now = wx[wx.my == cur_my].sort_values("wasde").value
    usda_now = float(usda_now.iloc[-1]) if len(usda_now) else np.nan
    wk_now = int(last.wk)
    near = None
    if test:
        k = min(test["by_week"], key=lambda x: abs(x - wk_now) if x >= wk_now else 99)
        near = test["by_week"][k]
    # weekly pace needed to hit USDA, from the average seasonal profile
    prof = [np.mean([df[(df.my == m) & (df.wk == k)].cum.iloc[0] / tot[m] for m in complete[-5:] if len(df[(df.my == m) & (df.wk == k)])]) for k in range(1, 53)]
    ratio_now = np.mean([final[m] / tot[m] for m in complete[-5:] if m in final.index])
    out = {"my": cur_my, "unit": "mil bu (inspections)", "week": wk_now, "as_of": str(last.week.date()),
           "cum": round(float(last.cum), 1), "usda": usda_now, "implied": round(float(last.implied), 0),
           "pct_of_usda": round(float(100 * last.cum * ratio_now / usda_now), 1) if usda_now == usda_now else None,
           "avg_pct": round(float(100 * last.avg_share), 1),
           "weeks": list(range(1, 53)), "cur": [round(float(x), 1) for x in c.cum] + [None] * (52 - len(c)),
           "prev": [round(float(x), 1) for x in p.cum.iloc[:52]] + [None] * max(0, 52 - len(p)),
           "needed": [round(float(usda_now / ratio_now * s), 1) for s in prof],
           "test": None if not test else {"mae_pct": near["mae_pct"], "mae_usda_pct": near["mae_usda_pct"], "n": test["n_years"],
                                          "revision_hit": test["revision_hit_all"], "by_week": test["by_week"], "revision_n": test["revision_n"]}}
    return out, test


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for com in COMS:
        out, test = run(com)
        if out:
            res[com] = out
            print(com, {k: out[k] for k in ("my", "week", "cum", "usda", "implied", "pct_of_usda", "avg_pct")}, json.dumps(test))
    res["kc"] = res.get("wheat")
    (OUT / "exports.json").write_text(json.dumps(res, separators=(",", ":"), default=str))
