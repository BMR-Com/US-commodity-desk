#!/usr/bin/env python3
"""Energy supply & demand and inventory-based fair values (Energy > Supply, demand & fair value).

Inputs: data/energy/eia/<k>.json (EIA weekly/monthly series, pipelines/energy_eia.py), data/contracts/<SYM>.csv.
Per market:
- balance table (weekly for crude/distillate/gasoline, monthly for natural gas) with 4-week / 12-month averages vs a
  year ago;
- inventories against the same week of the last 5 years (level, deviation, days of supply), and a seasonal chart;
- a fair-value regression of price (or the inventory-sensitive spread / crack) on the inventory deviation, fitted on
  the last 5 years of weekly data, with a walk-forward check (does today's gap to fair value predict the next 4 weeks?).
  natural gas: log(front futures) ~ storage vs 5-yr average (%) + season;  crude: WTI 1st-2nd month spread ~ Cushing
  and US crude stocks vs 5-yr (outright crude is priced on global balances, so only the spread is modelled);
  ULSD / gasoline: Gulf Coast crack vs WTI ~ days of supply vs 5-yr + season.
Writes data/energy/sd.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
E = ROOT / "data" / "energy" / "eia"
sys.path.insert(0, str(ROOT / "models"))


def S(k):
    p = E / f"{k}.json"
    if not p.exists():
        return pd.Series(dtype=float)
    r = json.loads(p.read_text()).get("rows") or []
    s = pd.Series({pd.Timestamp(d): v for d, v in r}).sort_index()
    return s[~s.index.duplicated()]


def wk(s, how="mean"):
    """Weekly on Friday (EIA weeks end Friday)."""
    if s.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    return getattr(s.resample("W-FRI"), how)().dropna()


def vs5(s):
    """Each week's value vs the average of the same ISO week in the previous 5 years."""
    df = pd.DataFrame({"v": s})
    df["y"], df["w"] = df.index.isocalendar().year.values, np.minimum(df.index.isocalendar().week.values, 52)
    piv = df.pivot_table(index="w", columns="y", values="v", aggfunc="last")
    avg, lo, hi = [], [], []
    for d, r in df.iterrows():
        prev = [piv.at[r.w, y] for y in range(int(r.y) - 5, int(r.y)) if y in piv.columns and not pd.isna(piv.at[r.w, y])]
        avg.append(np.mean(prev) if len(prev) >= 3 else np.nan)
    df["avg5"] = avg
    df["dev"] = df.v - df.avg5
    df["dev_pct"] = 100 * df.dev / df.avg5
    return df


def seasonal_chart(s):
    df = pd.DataFrame({"v": s})
    df["y"], df["w"] = df.index.isocalendar().year.values, np.minimum(df.index.isocalendar().week.values, 52)
    piv = df.pivot_table(index="w", columns="y", values="v", aggfunc="last").reindex(range(1, 53))
    cy = int(df.y.iloc[-1])
    prev = [y for y in piv.columns if cy - 5 <= y < cy]
    r = lambda a: [None if pd.isna(x) else round(float(x), 1) for x in a]
    return {"weeks": list(range(1, 53)), "cy": cy, "this": r(piv.get(cy, pd.Series(index=piv.index))), "last": r(piv.get(cy - 1, pd.Series(index=piv.index))),
            "min5": r(piv[prev].min(axis=1)), "max5": r(piv[prev].max(axis=1)), "avg5": r(piv[prev].mean(axis=1))}


def ols(y, X):
    A = np.column_stack([np.ones(len(X)), X])
    b, *_ = np.linalg.lstsq(A, y, rcond=None)
    fit = A @ b
    ss = ((y - y.mean()) ** 2).sum()
    return b, fit, (1 - ((y - fit) ** 2).sum() / ss) if ss > 0 else None


def season(idx):
    w = 2 * math.pi * idx.dayofyear.values / 365.25
    return np.column_stack([np.sin(w), np.cos(w)])


def model(df, ycol, xcols, log=False, seasonal=True, window=260, horizon=4, label="", unit="", driver_label=""):
    """Rolling-window OLS fair value with a walk-forward test of the gap."""
    d = df[[ycol] + xcols].dropna()
    if len(d) < 160:
        return None
    y = np.log(d[ycol].values) if log else d[ycol].values
    X = d[xcols].values
    if seasonal:
        X = np.column_stack([X, season(d.index)])
    n = len(d)
    w0 = max(0, n - window)
    b, fit, r2 = ols(y[w0:], X[w0:])
    fv = np.exp(fit) if log else fit
    act = d[ycol].values[w0:]
    resid_now = float(act[-1] - fv[-1])
    sd = float(np.std(act - fv))
    # walk-forward: at each week of the last 3 years fit on the previous `window` weeks only
    gaps, fwd = [], []
    for t in range(max(window // 2, n - 156), n - horizon):
        a = max(0, t - window)
        bb, _, _ = ols(y[a:t], X[a:t])
        pred = np.r_[1, X[t]] @ bb
        g = (d[ycol].values[t] - (math.exp(pred) if log else pred))
        gaps.append(g); fwd.append(d[ycol].values[t + horizon] - d[ycol].values[t])
    gaps, fwd = np.array(gaps), np.array(fwd)
    wf = None
    if len(gaps) > 30:
        c = float(np.corrcoef(gaps, fwd)[0, 1])
        hit = float(np.mean(np.sign(-gaps[np.abs(gaps) > 0]) == np.sign(fwd[np.abs(gaps) > 0])))
        wf = {"n": int(len(gaps)), "corr_gap_next": round(c, 2), "hit": round(100 * hit), "horizon_weeks": horizon,
              "reads": "the gap has tended to close" if c < -0.15 and hit > 0.55 else "the gap has not reliably closed (treat as context, not a signal)"}
    coef = {xcols[i]: round(float(b[i + 1]), 4) for i in range(len(xcols))}
    return {"label": label, "unit": unit, "driver": driver_label, "log": log, "seasonal": seasonal, "r2": None if r2 is None else round(float(r2), 2), "coef": coef,
            "window_weeks": int(len(act)), "since": str(d.index[w0].date()), "date": str(d.index[-1].date()),
            "actual": round(float(act[-1]), 3), "fair": round(float(fv[-1]), 3), "gap": round(resid_now, 3), "gap_z": round(resid_now / sd, 2) if sd else None,
            "walk_forward": wf, "x_now": {k: round(float(d[k].iloc[-1]), 2) for k in xcols},
            "series": [[str(i.date()), round(float(a), 3), round(float(f), 3)] for i, a, f in zip(d.index[w0:], act, fv)][-260:],
            "scatter": [[round(float(x), 2), round(float(v), 3)] for x, v in zip(d[xcols[0]].values[w0:], act)]}


def front_contract(sym, ahead=1):
    from research import held_series
    p = ROOT / "data" / "contracts" / f"{sym}.csv"
    if not p.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    h = held_series(pd.read_csv(p), ahead)
    return h.F1.dropna(), (h.F1 - h.F2).dropna()


def balance(rows, months=False):
    """rows: {label: series in common units} -> table of latest periods with averages and year-ago comparison."""
    rows = {k: v for k, v in rows.items() if v is not None and len(v)}
    df = pd.DataFrame(rows).sort_index().dropna(how="all")
    df = df[df.index >= df.index.max() - pd.Timedelta(days=800)]
    if df.empty:
        return None
    n_avg = 12 if months else 4
    last = df.tail(8 if not months else 13)
    tbl = {"periods": [str(i.date()) for i in last.index], "rows": []}
    for c in df.columns:
        s = df[c].dropna()
        if s.empty:
            continue
        avg = s.tail(n_avg).mean()
        ya = s[(s.index <= s.index[-1] - pd.Timedelta(days=364))].tail(n_avg).mean() if len(s) > (n_avg + 12 if months else 60) else np.nan
        tbl["rows"].append({"name": c, "values": [None if pd.isna(last.at[i, c]) else round(float(last.at[i, c]), 1) for i in last.index],
                            "avg": round(float(avg), 1), "avg_ya": None if pd.isna(ya) else round(float(ya), 1),
                            "chg_ya_pct": None if pd.isna(ya) or ya <= 0 or avg <= 0 else round(100 * (avg / ya - 1), 1)})
    tbl["avg_label"] = "12-month average" if months else "4-week average"
    return tbl


def main():
    out = {"generated": date.today().isoformat(), "markets": {}}
    # ---------- natural gas ----------
    st = wk(S("storL48"), "last")
    if not st.empty:
        g = vs5(st)
        ng, _ = front_contract("NG", 1)
        g["price"] = wk(ng).reindex(g.index, method="nearest", tolerance=pd.Timedelta(days=3))
        g["dev_pct_x"] = g.dev_pct
        m = model(g, "price", ["dev_pct_x"], log=True, label="Henry Hub front-month futures", unit="$/MMBtu",
                  driver_label="Lower 48 storage vs 5-year average (%)")
        # end-of-season projection at the 5-year average pace from here
        last = g.iloc[-1]
        df = pd.DataFrame({"v": st}); df["y"] = df.index.isocalendar().year.values; df["w"] = np.minimum(df.index.isocalendar().week.values, 52)
        piv = df.pivot_table(index="w", columns="y", values="v", aggfunc="last")
        wnow, cy = int(last.w), int(last.y)
        prev = [y for y in piv.columns if cy - 5 <= y < cy]
        def proj(target_w, year_shift=0):
            chg = []
            for y in prev:
                try:
                    a = piv.at[wnow, y]
                    b = piv.at[target_w, y + year_shift] if (y + year_shift) in piv.columns else np.nan
                    if not pd.isna(a) and not pd.isna(b):
                        chg.append(b - a)
                except KeyError:
                    pass
            return float(last.v + np.mean(chg)) if chg else None, float(np.mean([piv.at[target_w, y + year_shift] for y in prev if (y + year_shift) in piv.columns and not pd.isna(piv.at[target_w, y + year_shift])])) if prev else None
        eo_w = 44 if wnow <= 44 else None
        proj_rows = []
        if eo_w:
            p, a = proj(eo_w)
            proj_rows.append({"what": "end of October (injection season end)", "projected": round(p) if p else None, "avg5": round(a) if a else None})
        p, a = proj(13, 1 if wnow > 13 else 0)
        proj_rows.append({"what": "end of March (withdrawal season end)", "projected": round(p) if p else None, "avg5": round(a) if a else None})
        # monthly balance (Bcf/d)
        dpm = lambda s: (s / s.index.days_in_month / 1000) if not s.empty else s
        bal = balance({"Dry production": dpm(S("prodDry")), "Imports": dpm(S("impTot")), "Residential": dpm(S("consRes")), "Commercial": dpm(S("consCom")),
                       "Industrial": dpm(S("consInd")), "Power": dpm(S("consPow")), "Total consumption": dpm(S("consTot")), "LNG exports": dpm(S("expLng")),
                       "Total exports": dpm(S("expTot"))}, months=True)
        out["markets"]["NG"] = {"name": "Natural gas", "unit_stock": "Bcf",
                                "stocks": {"name": "Lower 48 working gas", "date": str(g.index[-1].date()), "value": round(float(last.v)), "avg5": round(float(last.avg5)),
                                           "dev": round(float(last.dev)), "dev_pct": round(float(last.dev_pct), 1), "wow": round(float(g.v.diff().iloc[-1])),
                                           "yago": round(float(g.v.iloc[-53])) if len(g) > 53 else None},
                                "seasonal": seasonal_chart(st), "projection": proj_rows, "balance": bal, "balance_unit": "Bcf/d (EIA monthly)",
                                "fair": m, "storage_regions": {k: round(float(wk(S(k), "last").iloc[-1])) for k in ("storEast", "storMw", "storSc", "storMtn", "storPac") if not S(k).empty}}
    # ---------- crude ----------
    cr = wk(S("crude"), "last") / 1000
    if not cr.empty:
        c = vs5(cr)
        cu = vs5(wk(S("cushing"), "last") / 1000) if not S("cushing").empty else None
        runs = wk(S("runs"))
        c["days"] = c.v * 1000 / runs.reindex(c.index, method="nearest", tolerance=pd.Timedelta(days=3))
        dd = vs5(c["days"].dropna())
        c["days_dev"] = dd.dev
        _, spread = front_contract("CL", 2)
        c["spread"] = wk(spread).reindex(c.index, method="nearest", tolerance=pd.Timedelta(days=3))
        if cu is not None:
            c["cush_dev"] = cu.dev.reindex(c.index)
        c["crude_dev"] = c.dev
        m = model(c, "spread", ["cush_dev", "crude_dev"] if cu is not None else ["crude_dev"], label="WTI 1st minus 2nd held contract", unit="$/bbl",
                  driver_label="Cushing stocks vs 5-year average (mb), with US crude stocks vs 5-year")
        wti = wk(S("wti"))
        c["wti"] = wti.reindex(c.index, method="nearest", tolerance=pd.Timedelta(days=3))
        m2 = model(c, "wti", ["days_dev"], log=True, seasonal=False, label="WTI spot (outright)", unit="$/bbl", driver_label="crude days of supply vs 5-year average")
        if m2:
            m2 = {k: m2[k] for k in ("label", "r2", "window_weeks", "since")}   # kept only to show how little US stocks explain the outright price
        kbd = lambda s: wk(s)
        dstock = cr.diff() * 1000 / 7
        bal = balance({"Production": kbd(S("prod")), "Imports": kbd(S("imp")), "Exports": kbd(S("exp")), "Refinery crude input": kbd(S("runs")),
                       "Change in commercial stocks": dstock, "Adjustment (balancing item)": dstock - (kbd(S("prod")) + kbd(S("imp")) - kbd(S("exp")) - kbd(S("runs")))})
        last = c.iloc[-1]
        out["markets"]["CL"] = {"name": "WTI crude", "unit_stock": "million bbl",
                                "stocks": {"name": "US commercial crude stocks (ex-SPR)", "date": str(c.index[-1].date()), "value": round(float(last.v), 1), "avg5": round(float(last.avg5), 1),
                                           "dev": round(float(last.dev), 1), "dev_pct": round(float(last.dev_pct), 1), "wow": round(float(c.v.diff().iloc[-1]), 1),
                                           "days": round(float(last.days), 1) if not pd.isna(last.days) else None,
                                           "cushing": round(float(cu.v.iloc[-1]), 1) if cu is not None else None, "cushing_avg5": round(float(cu.avg5.iloc[-1]), 1) if cu is not None else None,
                                           "spr": round(float(wk(S("spr"), "last").iloc[-1]) / 1000, 1) if not S("spr").empty else None},
                                "seasonal": seasonal_chart(cr), "balance": bal, "balance_unit": "thousand b/d (EIA weekly)", "fair": m, "fair_outright": m2}
    # ---------- products ----------
    for sym, nm, stk, dem, prod, imp, exp, spot in (("HO", "ULSD / distillate", "dist", "demDist", "distProd", "distImp", "distExp", "spotDist"),
                                                    ("RB", "RBOB / gasoline", "gaso", "demGaso", "gasoProd", "gasoImp", "gasoExp", "spotGaso")):
        s = wk(S(stk), "last") / 1000
        if s.empty:
            continue
        p = vs5(s)
        demand = wk(S(dem)).rolling(4, min_periods=2).mean()
        p["days"] = p.v * 1000 / demand.reindex(p.index, method="nearest", tolerance=pd.Timedelta(days=3))
        p["days_dev"] = vs5(p["days"].dropna()).dev
        crack = (wk(S(spot)) * 42 - wk(S("wti"))).dropna()
        p["crack"] = crack.reindex(p.index, method="nearest", tolerance=pd.Timedelta(days=3))
        m = model(p, "crack", ["days_dev"], label=f"Gulf Coast {nm.split(' / ')[1]} crack vs WTI", unit="$/bbl", driver_label="days of supply vs 5-year average")
        dstock = s.diff() * 1000 / 7
        bal = balance({"Refinery production": wk(S(prod)), "Imports": wk(S(imp)), "Exports": wk(S(exp)), "Product supplied (demand)": wk(S(dem)), "Change in stocks": dstock})
        last = p.iloc[-1]
        out["markets"][sym] = {"name": nm, "unit_stock": "million bbl",
                               "stocks": {"name": f"US {nm.split(' / ')[1]} stocks", "date": str(p.index[-1].date()), "value": round(float(last.v), 1), "avg5": round(float(last.avg5), 1),
                                          "dev": round(float(last.dev), 1), "dev_pct": round(float(last.dev_pct), 1), "wow": round(float(p.v.diff().iloc[-1]), 1),
                                          "days": round(float(last.days), 1) if not pd.isna(last.days) else None,
                                          "days_avg5": round(float(last.days - last.days_dev), 1) if not pd.isna(last.days_dev) else None},
                               "seasonal": seasonal_chart(s), "balance": bal, "balance_unit": "thousand b/d (EIA weekly)", "fair": m}
    # model quality label and the latest futures price
    for sym, M in out["markets"].items():
        f = M.get("fair")
        if f:
            r2, wf = f.get("r2") or 0, (f.get("walk_forward") or {})
            f["quality"] = ("usable: inventories explain much of the price and gaps have closed" if r2 >= 0.5 and wf.get("corr_gap_next", 0) < -0.15 else
                            "partial: inventories explain part of the price" if r2 >= 0.25 else
                            "weak: inventories explain little of this price right now (global and refinery factors dominate); shown for context")
        fr, _ = front_contract(sym if sym != "RB" else "RB", 1 if sym == "NG" else 2)
        if len(fr):
            M["price_now"] = {"value": round(float(fr.iloc[-1]), 4), "date": str(fr.index[-1].date())}
    # reads
    for sym, M in out["markets"].items():
        st_, f = M["stocks"], M.get("fair")
        t = [f"{st_['name']} {st_['value']:,} {M['unit_stock']} (week to {st_['date']}), {st_['dev']:+,} ({st_['dev_pct']:+.1f}%) vs the 5-year average, {st_['wow']:+,} on the week"
             + (f"; {st_['days']} days of supply" if st_.get("days") else "") + "."]
        if f:
            t.append(f"Inventory fair value for the {f['label']}: {f['fair']:.2f} {f['unit']} vs {f['actual']:.2f} actual (gap {f['gap']:+.2f}, z {f['gap_z']:+.1f}; R² {f['r2']} over {f['window_weeks']} weeks; model {f['quality'].split(':')[0]})"
                     + (f"; walk-forward: {f['walk_forward']['reads']} (corr {f['walk_forward']['corr_gap_next']}, hit {f['walk_forward']['hit']}% over {f['walk_forward']['horizon_weeks']} weeks)." if f.get("walk_forward") else "."))
        if M.get("projection"):
            t.append("At the 5-year average pace from here: " + "; ".join(f"{x['what']} {x['projected']:,} Bcf (5-yr avg {x['avg5']:,})" for x in M["projection"] if x["projected"]) + ".")
        M["read"] = " ".join(t)
        print(sym, M["read"][:300])
    (ROOT / "data" / "energy" / "sd.json").write_text(json.dumps(out, default=lambda x: None))


if __name__ == "__main__":
    main()
