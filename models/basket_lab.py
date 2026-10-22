#!/usr/bin/env python3
"""Basket lab: cross-commodity long/short portfolios, the way commodity quant funds build them.

Universe: the 27 markets of the backtest lab (models/backtest_lab.py loaders; same timing: Friday information, traded
from the next trading day's close, weekly rebalance). Each leg is risk-weighted (10% vol per market), then the whole
basket is scaled to 10% annual volatility using its own trailing 52-week volatility (known in advance), 5 bp cost per
unit of turnover.

Sleeves (literature in brackets):
- carry: long most backwardated, short most contangoed tercile [Gorton-Rouwenhorst 2004; Erb-Harvey 2006;
  Szymanowska et al. 2014; Koijen-Moskowitz-Pedersen-Vrugt 2018 "Carry"]
- cross-sectional momentum 1/2/4/13/26/52 weeks [Miffre-Rallis 2007; Asness-Moskowitz-Pedersen 2013]
- short-term reversal 1 week [Bianchi-Drew-Fan 2015 momentum + reversal in commodities]
- time-series trend at several speeds and a multi-speed blend [Moskowitz-Ooi-Pedersen 2012; Hurst-Ooi-Pedersen 2017]
- 50/200-day trend basket (strong uptrends long, downtrends short)
- carry + momentum combined rank [Asness et al. 2013; Bakshi-Gao-Rossi 2019]
- basis-momentum: 12-month return of the nearby minus the next contract [Boons-Prado 2019]
- hedging pressure: long where speculators are most net long vs open interest (hedgers most short) [Basu-Miffre 2013]
- speculator liquidity provision: short last week's biggest spec buying, long the biggest selling, 1-week hold
  [Kang-Rouwenhorst-Tang 2020: hedgers pay specs for short-term liquidity]
- skewness: long the most negatively skewed, short the most positively skewed [Fernandez-Perez et al. 2018]
- desk idea: long backwardated markets where specs just turned buyers; short contangoed markets where specs are
  crowded long or keep selling
- dairy trend basket
- a blend: equal risk of the sleeves that were positive in 2007-2018 only (selection without hindsight), judged 2019+.
Writes data/backtest/baskets.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import backtest_lab as BL   # noqa: E402

SPLIT, TARGET, COST = BL.SPLIT, 0.10, 0.0005


def panel():
    SU = BL.stocks_use()
    F = {}
    for s in BL.DESK:
        f = BL.desk_market(s)
        if f is not None and len(f) > 300:
            F[s] = BL.features(f, s, SU)
    for s in BL.EXTRA:
        f = BL.extra_market(s)
        if f is not None and len(f) > 300:
            F[s] = BL.features(f, s, SU)
    idx = pd.date_range("2006-06-02", max(f.index.max() for f in F.values()), freq="W-FRI")
    col = lambda c: pd.DataFrame({s: f[c].reindex(idx, method="nearest", tolerance=pd.Timedelta(days=3)) if c in f else np.nan for s, f in F.items()})
    P = {c: col(c) for c in ("px", "ret", "lev", "carry", "carry_adj", "mm_n", "oi", "mm_pct", "above200", "stack_up", "stack_dn", "F1", "F2", "bo_up20", "bo_dn20")}
    return F, idx, P


def xs(score, frac=1 / 3, min_n=6):
    """Long top / short bottom fraction of markets each week (+1/-1, equal count per leg)."""
    W = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    for d, row in score.iterrows():
        r = row.dropna()
        if len(r) < min_n:
            continue
        k = max(1, int(round(len(r) * frac)))
        W.loc[d, r.nlargest(k).index] = 1.0 / k
        W.loc[d, r.nsmallest(k).index] = -1.0 / k
    return W


def run(W, P, name, hold=1):
    """Raw +/- weights -> risk-weighted, vol-targeted basket returns."""
    if hold > 1:   # keep each week's book for `hold` weeks (overlapping portfolios, averaged)
        W = sum(W.shift(i).fillna(0) for i in range(hold)) / hold
    w = W * P["lev"]
    r_raw = (w * P["ret"]).sum(axis=1, min_count=1)
    vol = r_raw.rolling(52, min_periods=26).std().shift(1) * math.sqrt(52)
    k = (TARGET / vol).clip(upper=4)
    wf = w.mul(k, axis=0)
    cost = COST * wf.diff().abs().sum(axis=1)
    g = (wf * P["ret"]).sum(axis=1, min_count=1)
    r = g - cost
    keep = (r.index >= pd.Timestamp("2008-01-01")) & r.notna() & (r.index <= P["ret"].dropna(how="all").index.max())
    r = r[keep]
    r.attrs["gross"] = g[keep]
    r.attrs["cost_pa"] = float(cost[keep].mean() * 52 * 100)
    return r, wf


def stats(r, mn=52):
    r = r.dropna()
    if len(r) < mn or r.std() == 0:
        return None
    eq = r.cumsum()
    dd = float((eq - eq.cummax()).min())
    ann = float(r.mean() * 52)
    sr = ann / float(r.std() * math.sqrt(52))
    yrs = len(r) / 52
    under = (eq < eq.cummax()).astype(int)
    longest = int(max((sum(1 for _ in g) for k, g in __import__("itertools").groupby(under) if k == 1), default=0))
    return {"ann": round(ann * 100, 2), "vol": round(float(r.std() * math.sqrt(52) * 100), 1), "sharpe": round(sr, 2), "t": round(sr * math.sqrt(yrs), 2),
            "maxdd": round(dd * 100, 1), "calmar": round(ann / abs(dd), 2) if dd < 0 else None, "hit": round(float((r > 0).mean() * 100), 1),
            "worst_week": round(float(r.min() * 100), 2), "longest_dd_weeks": longest, "years": round(yrs, 1)}


def main():
    F, idx, P = panel()
    mk = list(P["ret"].columns)
    R = P["ret"]
    px = P["px"]
    S = {}
    def add(key, name, lit, W, hold=1, group="Cross-section"):
        r, wf = run(W.reindex(columns=mk).fillna(0), P, name, hold)
        full = stats(r)
        if full:
            gs = stats(r.attrs["gross"])
            S[key] = {"key": key, "name": name, "lit": lit, "group": group, "hold": hold, "r": r, "w": wf, **full, "sharpe_gross": gs["sharpe"] if gs else None, "cost_pa": round(r.attrs["cost_pa"], 2),
                      "is": stats(r[r.index < SPLIT]), "oos": stats(r[r.index >= SPLIT]),
                      **{wk: stats(r[(r.index >= a) & (r.index <= b)], 26) for wk, (a, b) in BL.WINDOWS.items()}}
    # carry
    add("xs_carry", "Carry: long most backwardated third, short most contangoed third", "Koijen et al. 2018; Gorton-Rouwenhorst; Erb-Harvey", xs(P["carry"]))
    add("xs_carry_adj", "Carry vs its own seasonal norm (cross-section)", "seasonal adjustment for crops and gas", xs(P["carry_adj"]))
    # momentum and reversal
    for h, lab in ((1, "1-week"), (2, "2-week"), (4, "4-week"), (13, "3-month"), (26, "6-month"), (52, "12-month")):
        add(f"xs_mom{h}", f"Cross-sectional momentum, {lab}: long winners, short losers", "Miffre-Rallis 2007; Asness et al. 2013", xs(px / px.shift(h) - 1), group="Momentum")
    add("xs_rev1", "Short-term reversal: long last week's losers, short winners", "Bianchi-Drew-Fan 2015", xs(-(px / px.shift(1) - 1)), group="Momentum")
    add("xs_mom12_1", "Momentum 12-1 months (skip the last month)", "Jegadeesh-Titman style; Asness et al.", xs(px.shift(4) / px.shift(52) - 1), group="Momentum")
    # time-series trend baskets
    for h, lab in ((1, "1-week"), (2, "2-week"), (4, "4-week"), (13, "3-month"), (26, "6-month"), (52, "12-month")):
        add(f"ts{h}", f"Trend, every market long if up / short if down over {lab}", "Moskowitz-Ooi-Pedersen 2012", np.sign(px / px.shift(h) - 1) / len(mk), group="Trend")
    blend = sum(np.sign(px / px.shift(h) - 1) for h in (4, 13, 26, 52)) / 4
    add("ts_blend", "Trend blend: average of 1, 3, 6 and 12-month signals", "Hurst-Ooi-Pedersen 2017 (multi-speed CTA)", blend / len(mk), group="Trend")
    add("trend_ma", "Strong uptrends long (price > 50 > 200-day), downtrends short", "classic CTA filter", (P["stack_up"].astype(float) - P["stack_dn"].astype(float)) / len(mk), group="Trend")
    add("above200", "Long markets above 200-day, short those below", "moving-average trend", np.where(P["above200"].fillna(False), 1.0, -1.0) * (px.notna()) / len(mk), group="Trend")
    # combined carry + momentum
    zr = lambda df: df.rank(axis=1, pct=True)
    add("carry_mom", "Carry + 6-month momentum combined rank", "Asness et al. 2013; Bakshi-Gao-Rossi 2019", xs((zr(P["carry"]) + zr(px / px.shift(26) - 1)) / 2))
    # basis-momentum
    bm = (np.log(P["F1"]) - np.log(P["F1"].shift(52))) - (np.log(P["F2"]) - np.log(P["F2"].shift(52)))
    add("basis_mom", "Basis-momentum: nearby's 12-month change minus next contract's", "Boons-Prado 2019", xs(bm))
    # positioning
    hp = (P["mm_n"] / P["oi"]).rolling(52, min_periods=26).mean()
    add("hedging_pressure", "Hedging pressure: long where specs are most net long (hedgers most short), 52-wk average", "Basu-Miffre 2013", xs(hp), group="Positioning")
    flow = P["mm_n"].diff() / P["oi"]
    add("spec_liquidity", "Liquidity provision: short last week's biggest spec buying, long the biggest selling", "Kang-Rouwenhorst-Tang 2020", xs(-flow), group="Positioning")
    add("spec_flow4", "Follow 4-week spec flow (cross-section)", "momentum in positioning", xs(P["mm_n"].diff(4) / P["oi"]), group="Positioning")
    # skewness
    skew = R.shift(1).rolling(52, min_periods=40).skew()
    add("skew", "Skewness: long most negatively skewed, short most positively skewed (52 weeks)", "Fernandez-Perez et al. 2018", xs(-skew), group="Cross-section")
    # desk idea: backwardation + specs just turning buyers; contango + specs crowded or selling
    d4 = P["mm_n"].diff(4)
    turn = (d4 > 0) & (d4.shift(4) <= 0)
    longs = (P["carry"] > 0) & turn
    shorts = (P["carry"] < 0) & ((P["mm_pct"] > 80) | (d4 < 0))
    W = longs.astype(float) - shorts.astype(float)
    W = W.div(W.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
    add("desk_carry_spec", "Desk idea: long backwardated + specs just turned buyers; short contango + specs crowded long or selling", "carry x positioning", W, hold=4, group="Combined")
    longs2 = (P["carry"] > 0) & P["stack_up"].fillna(False)
    shorts2 = (P["carry"] < 0) & P["stack_dn"].fillna(False)
    W2 = longs2.astype(float) - shorts2.astype(float)
    add("carry_trend", "Long backwardated uptrends, short contangoed downtrends", "carry x trend", W2.div(W2.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0), group="Combined")
    # dairy and sector baskets
    dairy = [m for m in ("DC", "GDK", "CSC", "CB", "GNF", "DY") if m in mk]
    Wd = pd.DataFrame(0.0, index=px.index, columns=mk)
    for m in dairy:
        Wd[m] = BL.turtle(F[m], 20, 20).reindex(px.index, method="nearest", tolerance=pd.Timedelta(days=3)).fillna(0) / len(dairy)
    add("dairy_trend", "Dairy trend basket: 20-day breakouts in milk, cheese, butter, powder, whey", "persistent USDA-average settlement", Wd, group="Sector")
    ags = [m for m in mk if BL.GROUP.get(m) in ("Grains", "Softs", "Livestock")]
    Wa = pd.DataFrame(0.0, index=px.index, columns=mk)
    Wa[ags] = (np.sign(px[ags] / px[ags].shift(2) - 1) * 0.5 + np.sign(px[ags] / px[ags].shift(13) - 1) * 0.5) / len(ags)
    add("ags_fast_trend", "Grains, softs, livestock: fast trend (2-week + 3-month)", "short horizons for annual crops", Wa, group="Sector")
    lo = (px.notna()).astype(float) / len(mk)
    add("long_only", "Equal-risk long-only basket (benchmark)", "Gorton-Rouwenhorst diversified index", lo, group="Benchmark")
    # blend of sleeves selected on 2008-2018 only
    cands = [k for k, v in S.items() if k not in ("long_only",) and v["is"] and v["is"]["sharpe"] > 0.3]
    if cands:
        rr = pd.DataFrame({k: S[k]["r"] for k in cands})
        rr = rr.div(rr.rolling(52, min_periods=26).std().shift(1), axis=0) * TARGET / math.sqrt(52)
        b = rr.mean(axis=1)
        b = b * TARGET / (b.rolling(52, min_periods=26).std().shift(1) * math.sqrt(52))
        b = b.dropna()
        S["blend"] = {"key": "blend", "name": f"Blend: equal risk of the {len(cands)} sleeves with Sharpe > 0.3 in 2008-2018", "lit": "diversified multi-factor (selection without hindsight)", "group": "Blend",
                      "hold": 1, "r": b, "w": None, **stats(b), "is": stats(b[b.index < SPLIT]), "oos": stats(b[b.index >= SPLIT]), "members": cands, **{wk: stats(b[(b.index >= a_) & (b.index <= b_)], 26) for wk, (a_, b_) in BL.WINDOWS.items()}}
    # recent-regime blends: sleeves picked on 2020-2023 only (Sharpe > 0.3), tested on 2024-2025; short-term and long-term books separately
    def est_hold(v):
        w = v["w"].loc[v["r"].index]
        tw = float(w.diff().abs().sum(axis=1).mean())
        return 2 * float(w.abs().sum(axis=1).mean()) / tw if tw > 0 else 99
    a0, b0 = BL.WINDOWS["r_is"]
    base = {k: v for k, v in S.items() if k not in ("long_only", "blend") and v.get("w") is not None and v.get("r_is") and v["r_is"]["sharpe"] > 0.3}
    for key, nm, keep in (("blend_recent", "Recent blend: equal risk of sleeves with Sharpe > 0.3 in 2020-2023", lambda h: True),
                          ("blend_recent_st", "Recent short-term blend: 2020-2023 winners that hold about a week", lambda h: h <= 2),
                          ("blend_recent_lt", "Recent long-term blend: 2020-2023 winners that hold several weeks", lambda h: h > 2)):
        cs = [k for k, v in base.items() if keep(est_hold(v))]
        if len(cs) < 2:
            continue
        rr = pd.DataFrame({k: S[k]["r"] for k in cs})
        rr = rr.div(rr.rolling(52, min_periods=26).std().shift(1), axis=0) * TARGET / math.sqrt(52)
        b = rr.mean(axis=1)
        b = (b * TARGET / (b.rolling(52, min_periods=26).std().shift(1) * math.sqrt(52))).dropna()
        S[key] = {"key": key, "name": nm, "lit": "selection on 2020-2023 only; 2024-2025 is the test", "group": "Blend", "hold": 1, "r": b, "w": None, **stats(b),
                  "is": stats(b[b.index < SPLIT]), "oos": stats(b[b.index >= SPLIT]), "members": cs,
                  "horizon": None if key == "blend_recent" else BL.horizon(1 if key.endswith("st") else 9),
                  **{wk: stats(b[(b.index >= a_) & (b.index <= b_)], 26) for wk, (a_, b_) in BL.WINDOWS.items()}}
    # correlations among sleeves
    keys = [k for k in S if k != "long_only"]
    C = pd.DataFrame({k: S[k]["r"] for k in keys}).corr().round(2)
    # current books
    names = {**BL.DESK, **BL.EXTRA}
    for k, v in S.items():
        if v.get("w") is not None:
            w = v["w"].iloc[-1].dropna()
            w = w[w.abs() > 1e-4].sort_values()
            v["book"] = [{"market": names[m], "sym": m, "weight": round(float(x), 3)} for m, x in w.items()]
            v["book_date"] = str(v["w"].index[-1].date())
            v["n_long"] = round(float((v["w"] > 1e-4).sum(axis=1).loc[v["r"].index].mean()), 1)
            v["n_short"] = round(float((v["w"] < -1e-4).sum(axis=1).loc[v["r"].index].mean()), 1)
            v["turnover"] = round(float(v["w"].diff().abs().sum(axis=1).loc[v["r"].index].mean() * 52), 1)
            g = float(v["w"].abs().sum(axis=1).loc[v["r"].index].mean()); tw = v["turnover"] / 52
            v["hold_wk"] = round(2 * g / tw, 1) if tw > 0 else None
            v["horizon"] = BL.horizon(v["hold_wk"])
    out_s = []
    for k, v in S.items():
        out_s.append({x: v.get(x) for x in ("key", "name", "lit", "group", "hold", "ann", "vol", "sharpe", "t", "maxdd", "calmar", "hit", "worst_week", "longest_dd_weeks", "years",
                                              "n_long", "n_short", "turnover", "book", "book_date", "members", "sharpe_gross", "cost_pa", "hold_wk", "horizon", "r_is", "r_oos", "live")} | {"is": v["is"], "oos": v["oos"],
                      "equity": [[str(d.date())[:7], round(float(x) * 100, 1)] for d, x in v["r"].cumsum().resample("ME").last().items()]})
    out_s.sort(key=lambda x: -(x["sharpe"] or -9))
    # findings
    ok = [x for x in out_s if x["key"] != "long_only" and x["is"] and x["oos"]]
    robust = [x for x in ok if x["is"]["sharpe"] > 0 and x["oos"]["sharpe"] > 0]
    by_calmar = sorted([x for x in robust if x["calmar"]], key=lambda x: -x["calmar"])
    L = []
    L.append("Best risk-adjusted sleeves that worked in both 2008-2018 and 2019+: " + "; ".join(f"{x['name']} (Sharpe {x['sharpe']}, 2019+ {x['oos']['sharpe']}, max DD {x['maxdd']}%, Calmar {x['calmar']})" for x in robust[:5]) + ".")
    L.append("Lowest drawdown per unit of return (Calmar), both periods positive: " + "; ".join(f"{x['name']} (Calmar {x['calmar']}, max DD {x['maxdd']}%, hit {x['hit']}%)" for x in by_calmar[:5]) + ".")
    bad = sorted(ok, key=lambda x: x["sharpe"])[:4]
    L.append("Did not work: " + "; ".join(f"{x['name']} (Sharpe {x['sharpe']})" for x in bad) + ".")
    if "blend" in S:
        b = S["blend"]
        L.append(f"Blend of the sleeves picked on 2008-2018 only: Sharpe {b['oos']['sharpe'] if b['oos'] else '–'} in 2019+ (vs {b['is']['sharpe']} in-sample), max DD {b['maxdd']}%, worst week {b['worst_week']}% at 10% vol.")
    # dairy deep dive: persistence of weekly returns vs other markets, liquidity, current breakout positions
    ac = {}
    for m in mk:
        x = R[m].dropna()
        x = x[x.index >= pd.Timestamp("2012-01-01")]
        if len(x) > 200:
            ac[m] = {"market": names[m], "group": BL.GROUP.get(m), "ac1": round(float(x.autocorr(1)), 2), "ac4": round(float((x.rolling(4).sum()).autocorr(4)), 2)}
    RS = json.loads((ROOT / "data/research/research.json").read_text()).get("markets", {}) if (ROOT / "data/research/research.json").exists() else {}
    LB = json.loads((ROOT / "data/backtest/lab.json").read_text()) if (ROOT / "data/backtest/lab.json").exists() else {"results": []}
    dd = []
    for m in dairy:
        rows = [x for x in LB["results"] if x["market"] == m]
        best = sorted([x for x in rows if x.get("enough") and x["key"] != "long_only"], key=lambda x: -x["sharpe"])[:3]
        pos = BL.turtle(F[m], 20, 20).iloc[-1]
        z = RS.get(m, {}).get("size", {})
        dd.append({"sym": m, "market": names[m], "ac1": ac.get(m, {}).get("ac1"), "adv": z.get("adv"), "notional": z.get("notional"),
                   "since": str(F[m].index[0].date()), "now": "long" if pos > 0 else "short" if pos < 0 else "flat",
                   "best": [{"strategy": b["strategy"], "sharpe": b["sharpe"], "oos": b["oos_sharpe"], "hit": b["hit"], "maxdd": b["maxdd"], "trades": b["trades"], "cost4": b.get("sharpe_4x_cost")} for b in best]})
    oth = [v["ac1"] for k, v in ac.items() if v["group"] != "Dairy"]
    dairy_info = {"markets": dd, "autocorr": sorted(ac.values(), key=lambda v: -v["ac1"]), "other_median_ac1": round(float(np.median(oth)), 2) if oth else None,
                  "basket": {k: S["dairy_trend"][k] for k in ("sharpe", "maxdd", "calmar", "hit", "ann") } if "dairy_trend" in S else None,
                  "basket_is": S["dairy_trend"]["is"] if "dairy_trend" in S else None, "basket_oos": S["dairy_trend"]["oos"] if "dairy_trend" in S else None}
    out = {"generated": date.today().isoformat(), "split": str(SPLIT.date()), "dairy": dairy_info, "target_vol": TARGET, "cost_bp": COST * 1e4, "markets": [names[m] for m in mk],
           "learnings": L, "strategies": out_s, "corr": {"keys": list(C.columns), "m": C.values.tolist()}}
    (ROOT / "data" / "backtest" / "baskets.json").write_text(json.dumps(out, default=lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)).replace("NaN", "null"))
    for x in out_s:
        print(f"{x['sharpe']:6.2f} IS {x['is']['sharpe'] if x['is'] else '-':>5} OOS {x['oos']['sharpe'] if x['oos'] else '-':>5} DD {x['maxdd']:6.1f} calmar {x['calmar']} hit {x['hit']}  {x['name'][:80]}")
    print("\n".join(L))


if __name__ == "__main__":
    main()
