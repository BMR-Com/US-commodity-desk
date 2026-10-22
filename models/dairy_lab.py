#!/usr/bin/env python3
"""Dairy forecasting and trading lab: can the cash-settled dairy futures be predicted, and is there a consistent trade?

Every CME dairy contract settles on a USDA monthly average (Class III / IV, cheese, butter, nonfat dry milk, dry whey),
which is built from the weekly NDPSR survey. Prices therefore move in slow, persistent steps. This lab asks two things:

A. Persistence and fundamentals. How autocorrelated are weekly NDPSR and monthly announced prices (and how much of
   that is the mechanical effect of averaging), and do supply/demand numbers (ERS stocks, production, exports,
   domestic use) forecast the next 1-3 months of price changes out of sample?

B. Futures forecast error. On every weekly NDPSR release day since 2013 and for every open contract month up to six
   months ahead, forecast y = log(final settlement / futures price) with walk-forward models refit monthly on
   contracts already settled (no look-ahead): the futures price itself (benchmark), cash persistence, seasonal
   persistence, momentum, fundamentals and a ridge combination. Then trade it: hold one contract in the direction
   of the forecast when it clears the round-trip cost, mark to market weekly at CME settlements, charge half a
   bid-ask on every entry and exit.

Prices: per-contract settlements from TradingView with exchange trade dates (futures_io), cross-checked against CME
settlement files. Writes data/dairy/derived/dairy_lab.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from dairy_class import components, regime, load_class_prices  # noqa: E402
from dairy_arb import ndpsr, targets, cme_spot, nowcast_all  # noqa: E402
from futures_io import load_contracts  # noqa: E402

# sym: (target column, price multiplier vs USDA units, $ per 1.00 quoted unit, round-trip cost in quoted units, name, product(s))
SPEC = {"DC": ("class3", 1, 2000, 0.05, "Class III milk", ("cheese", "whey")),
        "GDK": ("class4", 1, 2000, 0.10, "Class IV milk", ("butter", "ndm")),
        "CSC": ("cheese", 1, 20000, 0.005, "Cheese", ("cheese",)),
        "CB": ("butter", 100, 200, 0.5, "Butter", ("butter",)),
        "GNF": ("ndm", 100, 440, 0.5, "Nonfat dry milk", ("ndm",)),
        "DY": ("whey", 100, 440, 0.5, "Dry whey", ("whey",))}
ERS = {"cheese": "Amer cheese, monthly", "butter": "Butter, monthly", "ndm": "Dry skim milk, monthly", "whey": "Dry whey, monthly"}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
H_MAX = 6
FEATS = ["basis", "seas", "sbasis", "mom4", "mom13", "fmom", "level", "stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy", "h"]
SPOT_FEATS = ["sbasis_spot", "nc_gap", "spot_mom", "mom4", "fmom", "seas", "h"]
START = pd.Timestamp("2013-01-01")
SPLIT = pd.Timestamp("2020-01-01")


# ------------------------------------------------------------------ inputs
def weekly_products(W):
    """Weekly NDPSR prices for cheese (Class III cheese definition), butter, ndm, whey + sales + first publication."""
    w = W.copy()
    piv = w.pivot_table(index="week", columns="product", values="price")
    sal = w.pivot_table(index="week", columns="product", values="sales")
    pub = w.groupby("week").first_pub.max().dt.normalize()
    ch = piv["block"].copy()
    old = (piv.index < "2025-06-01") & piv["barrel"].notna() & sal["barrel"].gt(0)
    ch[old] = ((piv.block * sal.block + (piv.barrel + 0.03) * sal.barrel) / (sal.block + sal.barrel))[old]
    P = pd.DataFrame({"cheese": ch, "butter": piv.butter, "ndm": piv.ndm, "whey": piv.whey})
    S = pd.DataFrame({"cheese": sal.block + sal.barrel.where(old, 0).fillna(0), "butter": sal.butter, "ndm": sal.ndm, "whey": sal.whey})
    S = S.reindex(P.index)
    S = S.fillna(S.rolling(8, min_periods=1).mean()).fillna(1.0)
    return P, S, pub


def ers_features():
    d = pd.read_csv(ROOT / "data" / "dairy" / "raw" / "ers" / "ers_product_supply_use.csv")
    d = d[d.Frequency == "Monthly"].copy()
    d["m"] = [pd.Period(f"{y}-{MONTHS[p]:02d}", "M") for y, p in zip(d.Year, d.Period)]
    out = {}
    for prod, tab in ERS.items():
        x = d[d.Table == tab].pivot_table(index="m", columns="Data_item", values="Quantity").sort_index()
        f = pd.DataFrame(index=x.index)
        stc = next(c for c in x.columns if c.startswith("Ending") and ("total" in c or "cold-storage" in c))
        prc = next(c for c in x.columns if c == "Production" or c == "Production, total")
        st = x[stc]
        use = x["Domestic disappearance"] + x["Exports"]
        mou = st / use.rolling(3, min_periods=1).mean()
        # deviation of months-of-use from the same calendar month's average of the previous 5 years
        norm = pd.Series([mou[[p for p in mou.index if p.month == m.month and m.year - 5 <= p.year < m.year]].mean() for m in mou.index], index=mou.index)
        f["stocks_dev"] = mou / norm - 1
        f["stocks_yoy"] = st / st.shift(12) - 1
        f["exports_yoy"] = x["Exports"].rolling(3).sum() / x["Exports"].rolling(3).sum().shift(12) - 1
        f["prod_yoy"] = x[prc].rolling(3).sum() / x[prc].rolling(3).sum().shift(12) - 1
        f["disapp_yoy"] = x["Domestic disappearance"].rolling(3).sum() / x["Domestic disappearance"].rolling(3).sum().shift(12) - 1
        f["avail"] = [p.end_time.normalize() + pd.Timedelta(days=55) for p in f.index]   # ERS publishes ~7 weeks after month end
        out[prod] = f
    return out


def class_from(px, m):
    c = components(px["cheese"], px["butter"], px["ndm"], px["whey"], regime(m))
    return c


# ------------------------------------------------------------------ panel
def build_panel():
    cp = load_class_prices()
    T = targets(cp)
    W = ndpsr()
    P, S, pub = weekly_products(W)
    E = ers_features()
    F = {s: load_contracts(s) for s in SPEC}
    spot = cme_spot().ffill()
    spot5 = spot.rolling(5, min_periods=3).mean()
    N = nowcast_all(W, cme_spot(), cp, cme_spot().index.min() + pd.Timedelta(days=200))
    Nx = N.set_index(["date", "m"]).sort_index()
    ncdays = Nx.index.get_level_values(0).unique()
    # announced monthly series in futures units, for seasonality and level
    ann = pd.DataFrame({s: T[SPEC[s][0]] * SPEC[s][1] for s in SPEC})
    dec_days = sorted(d for d in pub.unique() if d >= START)
    settle = {s: F[s].pivot_table(index="date", columns="m", values="close").sort_index() for s in SPEC}
    vol = {s: F[s].pivot_table(index="date", columns="m", values="volume").sort_index() for s in SPEC}
    rows = []
    for t in dec_days:
        known = P.index.intersection(pub[pub <= t].index)
        if len(known) < 20:
            continue
        P4 = P.loc[known].tail(4)
        S4 = S.loc[known].tail(4)
        cash = (P4 * S4).sum() / S4.sum()
        P4b = P.loc[known].iloc[-8:-4]; S4b = S.loc[known].iloc[-8:-4]
        cash_4ago = (P4b * S4b).sum() / S4b.sum()
        P13 = P.loc[known].iloc[-17:-13]; S13 = S.loc[known].iloc[-17:-13]
        cash_13ago = (P13 * S13).sum() / S13.sum()
        cash_avg = P.loc[known].tail(156).mean()
        efeat = {}
        for prod, f in E.items():
            av = f[f.avail <= t]
            efeat[prod] = av.iloc[-1] if len(av) else None
        sp = spot5.loc[:t]
        sp_now = sp.iloc[-1] if len(sp) and (t - sp.index[-1]).days < 7 else None
        sp4 = spot5.loc[:t - pd.Timedelta(days=28)]
        sp_4ago = sp4.iloc[-1] if len(sp4) and sp_now is not None else None
        if sp_now is not None:
            sp_cash = {"cheese": sp_now.block if (t >= pd.Timestamp("2025-06-01") or pd.isna(sp_now.barrel)) else (sp_now.block + sp_now.barrel + 0.03) / 2,
                       "butter": sp_now.butter, "ndm": sp_now.ndm, "whey": sp_now.whey}
        ncd = ncdays[ncdays <= t]
        ncd = ncd[-1] if len(ncd) and (t - ncd[-1]).days < 5 else None
        cur = t.to_period("M")
        ann_known = ann[[T.loc[m, "ann"] <= t if m in T.index else False for m in ann.index]]
        for s, (col, mult, dollar, cost, name, prods) in SPEC.items():
            st = settle[s]
            if t < st.index.min():
                continue
            rowd = st.loc[:t]
            if not len(rowd) or (t - rowd.index[-1]).days > 6:
                continue
            fut_now = rowd.iloc[-1]
            fut_4w = st.loc[:t - pd.Timedelta(days=28)].iloc[-1] if len(st.loc[:t - pd.Timedelta(days=28)]) else None
            for h in range(0, H_MAX + 1):
                m = cur + h
                if m in T.index and T.loc[m, "ann"] <= t:
                    continue
                if m not in fut_now.index or pd.isna(fut_now[m]):
                    continue
                Fv = float(fut_now[m])
                if Fv <= 0:
                    continue
                if col in ("class3", "class4"):
                    c_now = class_from(cash, m)[col]
                    c_4 = class_from(cash_4ago, m)[col]
                    c_13 = class_from(cash_13ago, m)[col]
                    c_avg = class_from(cash_avg, m)[col]
                else:
                    c_now, c_4, c_13, c_avg = cash[col] * mult, cash_4ago[col] * mult, cash_13ago[col] * mult, cash_avg[col] * mult
                # seasonal: average log change of the announced series from the current calendar month to month m, past years only
                a = ann_known[s].dropna()
                diffs = []
                for y in range(cur.year - 8, cur.year):
                    p0, p1 = pd.Period(f"{y}-{cur.month:02d}", "M"), pd.Period(f"{y}-{cur.month:02d}", "M") + h
                    if p0 in a.index and p1 in a.index and a[p0] > 0 and a[p1] > 0:
                        diffs.append(math.log(a[p1] / a[p0]))
                seas = float(np.mean(diffs)) if len(diffs) >= 3 else 0.0
                fe = {}
                for k in ("stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy"):
                    vals = [efeat[p][k] for p in prods if efeat.get(p) is not None and pd.notna(efeat[p][k])]
                    fe[k] = float(np.mean(vals)) if vals else np.nan
                sb_spot = nc_gap = spot_mom = np.nan
                if sp_now is not None:
                    sv = class_from(sp_cash, m)[col] if col in ("class3", "class4") else sp_cash[col] * mult
                    if sv and sv > 0:
                        sb_spot = math.log(sv / Fv) + seas
                    if sp_4ago is not None:
                        v_now = np.mean([sp_now[p_] if p_ != "cheese" else sp_now.block for p_ in prods])
                        v_4 = np.mean([sp_4ago[p_] if p_ != "cheese" else sp_4ago.block for p_ in prods])
                        spot_mom = math.log(v_now / v_4) if v_now > 0 and v_4 > 0 else np.nan
                if ncd is not None and (ncd, m) in Nx.index:
                    nv = Nx.loc[(ncd, m), f"mod_{col}"]
                    nv = float(nv.iloc[0]) if hasattr(nv, "iloc") else float(nv)
                    if pd.notna(nv) and nv > 0:
                        nc_gap = math.log(nv * mult / Fv)
                y = math.log(T.loc[m, col] * mult / Fv) if (m in T.index and pd.notna(T.loc[m, col])) else np.nan
                v = vol[s].loc[:t].iloc[-1].get(m, np.nan) if t >= vol[s].index.min() else np.nan
                rows.append({"t": t, "sym": s, "m": m, "h": h, "F": Fv, "y": y, "cash": c_now,
                             "basis": math.log(c_now / Fv) if c_now > 0 else np.nan, "seas": seas,
                             "sbasis": (math.log(c_now / Fv) + seas) if c_now > 0 else np.nan,
                             "mom4": math.log(c_now / c_4) if c_now > 0 and c_4 > 0 else np.nan,
                             "mom13": math.log(c_now / c_13) if c_now > 0 and c_13 > 0 else np.nan,
                             "fmom": math.log(Fv / fut_4w[m]) if fut_4w is not None and m in fut_4w.index and pd.notna(fut_4w[m]) and fut_4w[m] > 0 else 0.0,
                             "level": math.log(c_now / c_avg) if c_now > 0 and c_avg > 0 else np.nan, **fe, "vol": v,
                             "sbasis_spot": sb_spot, "nc_gap": nc_gap, "spot_mom": spot_mom})
    D = pd.DataFrame(rows)
    return D, cp, T, W, P, S, pub, E, F, settle, ann


# ------------------------------------------------------------------ models
def ridge_fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    b = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    return mu, sd, b, y.mean()


def ridge_pred(model, X):
    mu, sd, b, c = model
    return ((X - mu) / sd) @ b + c


def walk_forward(D, T):
    """Predictions for every row from models fit on rows whose contract had settled before the decision date."""
    D = D.copy()
    D["ann"] = D.m.map(T.ann)
    D = D.sort_values("t")
    for c in FEATS:
        D[c] = D[c].astype(float)
    for c in ("sbasis_spot", "nc_gap", "spot_mom"):
        D[c] = D[c].astype(float)
    D["nc_or_spot"] = D.nc_gap.fillna(D.sbasis_spot)
    preds = {k: np.full(len(D), np.nan) for k in ("beta_sbasis", "ridge_cash", "ridge_all", "ridge_fund", "ridge_spot", "beta_spot")}
    sets = {"ridge_cash": ["basis", "seas", "sbasis", "mom4", "mom13", "fmom", "level", "h"],
            "ridge_all": FEATS, "ridge_fund": ["stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy", "level", "h"],
            "ridge_spot": ["nc_or_spot", "sbasis_spot", "spot_mom", "mom4", "fmom", "seas", "h"]}
    idx = {k: i for i, k in enumerate(D.index)}
    months = D.t.dt.to_period("M").unique()
    for mo in months:
        t0 = mo.start_time
        train = D[(D.ann < t0) & D.y.notna()]
        test = D[D.t.dt.to_period("M") == mo]
        if len(train) < 300 or not len(test):
            continue
        for s in SPEC:
            tr, te = train[train.sym == s], test[test.sym == s]
            if len(tr) < 150 or not len(te):
                continue
            ii = [idx[i] for i in te.index]
            ok = tr.sbasis.notna()
            if ok.sum() > 50:
                b = np.polyfit(tr.sbasis[ok], tr.y[ok], 1)
                preds["beta_sbasis"][ii] = np.polyval(b, te.sbasis.fillna(0))
            ok2 = tr.nc_or_spot.notna()
            if ok2.sum() > 100 and te.nc_or_spot.notna().any():
                b = np.polyfit(tr.nc_or_spot[ok2], tr.y[ok2], 1)
                pv = np.polyval(b, te.nc_or_spot.values)
                preds["beta_spot"][ii] = np.where(te.nc_or_spot.notna(), pv, np.nan)
            for k, cols in sets.items():
                trk = tr.dropna(subset=cols + ["y"])
                if k == "ridge_spot" and te[["nc_or_spot", "sbasis_spot", "spot_mom"]].isna().all(axis=1).all():
                    continue
                if len(trk) < (100 if k == "ridge_spot" else 150):
                    continue
                mdl = ridge_fit(trk[cols].values, trk.y.values, alpha=len(trk) * 0.05)
                Xte = te[cols].copy()
                miss = te[cols].isna().any(axis=1).values if k == "ridge_spot" else np.zeros(len(te), bool)
                Xte = Xte.fillna(trk[cols].mean())
                preds[k][ii] = np.where(miss, np.nan, ridge_pred(mdl, Xte.values))
    for k, v in preds.items():
        D["p_" + k] = v
    D["p_futures"] = 0.0
    D["p_cash"] = D.basis
    D["p_seasonal_cash"] = D.sbasis
    D["p_momentum"] = D.mom4
    D["p_fut_momentum"] = D.fmom
    D["p_cash_fut_mom"] = D.mom4 + D.fmom
    D["p_spot_gap"] = D.nc_or_spot
    D["p_spot_mom"] = D.spot_mom
    return D


MODELS = {"futures": "Futures price (benchmark)", "cash": "Cash persistence (latest 4 NDPSR weeks)", "seasonal_cash": "Cash + seasonal change",
          "beta_sbasis": "Fitted share of (cash + seasonal) gap", "momentum": "4-week cash momentum", "ridge_cash": "Ridge: cash, seasonal, momentum",
          "ridge_fund": "Ridge: stocks, production, exports, use", "ridge_all": "Ridge: everything",
          "fut_momentum": "4-week futures momentum", "cash_fut_mom": "Cash + futures momentum", "spot_gap": "CME spot nowcast gap (spot + seasonal beyond 2 months)",
          "beta_spot": "Fitted share of the spot nowcast gap", "spot_mom": "4-week CME spot momentum", "ridge_spot": "Ridge: spot nowcast, momentum, seasonal"}


def clustered_t(x, g):
    m = pd.Series(np.asarray(x, float)).groupby(np.asarray(g)).mean()
    return float(m.mean() / m.std() * math.sqrt(len(m))) if len(m) > 3 and m.std() > 0 else None


def evaluate(D):
    out = []
    for s in SPEC:
      for per, t0 in (("2014+", "2014-01-01"), ("2020+", "2020-01-01")):
        for hb, hs in (("spot month", [0]), ("1-2 months", [1, 2]), ("3-6 months", [3, 4, 5, 6]), ("all", list(range(H_MAX + 1)))):
            g = D[(D.sym == s) & D.h.isin(hs) & D.y.notna() & (D.t >= t0)]
            if len(g) < 30:
                continue
            base = float((g.y ** 2).mean())
            for k in MODELS:
                p = g["p_" + k]
                ok = p.notna()
                if ok.sum() < 30:
                    continue
                yy, pp = g.y[ok], p[ok]
                r2 = 1 - float(((yy - pp) ** 2).mean()) / float((yy ** 2).mean()) if k != "futures" else 0.0
                hit = float((np.sign(pp) == np.sign(yy))[pp != 0].mean() * 100) if k != "futures" else None
                pnl = np.sign(pp) * yy
                out.append({"sym": s, "period": per, "horizon": hb, "model": k, "n": int(ok.sum()), "months": int(g.m[ok].nunique()),
                            "rmse_pct": round(math.sqrt(float(((yy - pp) ** 2).mean())) * 100, 2), "r2_oos": round(r2 * 100, 1),
                            "hit": round(hit, 1) if hit is not None else None, "t": round(clustered_t(pnl, g.m[ok].astype(str)), 2) if k != "futures" and clustered_t(pnl, g.m[ok].astype(str)) is not None else None})
    return out


# ------------------------------------------------------------------ trading
def backtest(D, settle, T, model, h_max=5, hurdle=1.0, size="one"):
    """Weekly book: for every open contract month h<=h_max, one contract in the sign of the model forecast when
    |forecast| > hurdle x (cost / price). Mark to market at settlements between decision days; costs half a spread per side."""
    res = {}
    for s, (col, mult, dollar, cost, name, prods) in SPEC.items():
        g = D[(D.sym == s) & (D.h <= h_max)].copy()
        g = g[g["p_" + model].notna()]
        if not len(g):
            continue
        days = sorted(g.t.unique())
        st = settle[s].ffill()
        sidx = st.index
        cpos = {m: i for i, m in enumerate(st.columns)}
        arr = st.values
        def at(m, t):
            i = sidx.searchsorted(t, side="right") - 1
            return arr[i, cpos[m]] if i >= 0 and m in cpos else np.nan
        groups = {t: gt for t, gt in g.groupby("t")}
        pos_prev = {}
        rows = []
        for i, t in enumerate(days):
            nxt = days[i + 1] if i + 1 < len(days) else None
            gt = groups[t]
            pos = {}
            for r in gt.itertuples():
                p = getattr(r, "p_" + model)
                thr = hurdle * cost / r.F
                if abs(p) > thr:
                    pos[r.m] = float(np.sign(p))
            # costs on changes
            c = 0.0
            for m in set(pos) | set(pos_prev):
                c += abs(pos.get(m, 0) - pos_prev.get(m, 0)) * cost / 2 * dollar
            # P&L to next decision day (or to final settlement)
            pnl = 0.0
            for m, w in pos.items():
                p0 = at(m, t)
                if pd.isna(p0):
                    continue
                ann_d = T.ann.get(m) if m in T.index else None
                if nxt is not None and (ann_d is None or pd.isna(ann_d) or ann_d > nxt):
                    p1 = at(m, nxt)
                    p1 = p0 if pd.isna(p1) else p1
                elif ann_d is not None and pd.notna(ann_d) and m in T.index and pd.notna(T.loc[m, col]):
                    p1 = T.loc[m, col] * mult           # settled before the next decision day
                else:
                    continue
                pnl += w * (p1 - p0) * dollar
            # positions that expired are flat at the next decision (no exit cost: cash settlement)
            pos_prev = {m: w for m, w in pos.items() if not (m in T.index and pd.notna(T.ann.get(m)) and nxt is not None and T.ann.get(m) <= nxt)}
            rows.append({"t": t, "pnl": pnl - c, "gross": pnl, "cost": c, "n": len(pos), "long": sum(1 for w in pos.values() if w > 0)})
        R = pd.DataFrame(rows).set_index("t")
        res[s] = R
    return res


def stats(R, label=None):
    x = R.pnl
    if len(x) < 20 or x.std() == 0:
        return None
    eq = x.cumsum()
    dd = float((eq - eq.cummax()).min())
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    return {"weeks": int(len(x)), "ann_usd": int(round(x.sum() / yrs)), "sharpe": round(float(x.mean() / x.std() * math.sqrt(52)), 2),
            "maxdd_usd": int(round(dd)), "hit_weeks": round(float((x[x != 0] > 0).mean() * 100), 1) if (x != 0).any() else None,
            "avg_positions": round(float(R.n.mean()), 1), "cost_ann_usd": int(round(R.cost.sum() / yrs)), "gross_ann_usd": int(round(R.gross.sum() / yrs)),
            "worst_week_usd": int(round(float(x.min())))}


# ------------------------------------------------------------------ persistence and fundamentals
def persistence(P, S, ann, settle):
    out = []
    for s, (col, mult, dollar, cost, name, prods) in SPEC.items():
        a = np.log(ann[s].dropna())
        da = a.diff().dropna()
        row = {"sym": s, "name": name, "monthly_ac1": round(float(da.autocorr(1)), 2), "monthly_ac2": round(float(da.autocorr(2)), 2),
               "months_same_direction": round(float((np.sign(da) == np.sign(da.shift(1))).iloc[1:].mean() * 100))}
        if len(prods) == 1:
            w = np.log(P[prods[0]].dropna())
            dw = w.diff().dropna()
            row.update(weekly_ac1=round(float(dw.autocorr(1)), 2), weekly_ac4=round(float(dw.rolling(4).sum().iloc[::4].autocorr(1)), 2))
        # futures: roll-adjusted 2nd-month weekly returns
        st = settle[s]
        wk = st.resample("W-FRI").last()
        rets = []
        for i in range(1, len(wk)):
            d0, d1 = wk.index[i - 1], wk.index[i]
            m = (d0 + pd.offsets.MonthBegin(1)).to_period("M") + 1
            if m in wk.columns and pd.notna(wk.iloc[i - 1][m]) and pd.notna(wk.iloc[i][m]) and wk.iloc[i - 1][m] > 0:
                rets.append((d1, math.log(wk.iloc[i][m] / wk.iloc[i - 1][m])))
        fr = pd.Series(dict(rets)).dropna()
        fr = fr[fr.index >= "2012-01-01"]
        row["futures_weekly_ac1"] = round(float(fr.autocorr(1)), 2) if len(fr) > 50 else None
        out.append(row)
    return out


def fundamentals_forecast(ann, E):
    """Walk-forward regression of the next 1 and 3 months' announced-price change on ERS fundamentals + momentum."""
    out = []
    for s, (col, mult, dollar, cost, name, prods) in SPEC.items():
        a = np.log(ann[s].dropna())
        rows = []
        for m in a.index:
            t = m.end_time.normalize() + pd.Timedelta(days=5)    # decision after month m's price is announced
            fe = {}
            for k in ("stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy"):
                vals = []
                for p in prods:
                    f = E[p]
                    av = f[f.avail <= t]
                    if len(av) and pd.notna(av.iloc[-1][k]):
                        vals.append(av.iloc[-1][k])
                fe[k] = np.mean(vals) if vals else np.nan
            r = {"m": m, **fe, "mom1": a.get(m, np.nan) - a.get(m - 1, np.nan), "mom3": a.get(m, np.nan) - a.get(m - 3, np.nan),
                 "level": a.get(m, np.nan) - a.loc[:m].tail(36).mean()}
            for hz in (1, 3):
                r[f"y{hz}"] = a.get(m + hz, np.nan) - a.get(m, np.nan)
            rows.append(r)
        X = pd.DataFrame(rows).set_index("m")
        for hz in (1, 3):
            for name_, cols in (("momentum only", ["mom1", "mom3"]), ("fundamentals only", ["stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy"]),
                                ("fundamentals + momentum + level", ["stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy", "mom1", "mom3", "level"])):
                pr, ys = [], []
                for i, m in enumerate(X.index):
                    tr = X.loc[:m - hz].dropna(subset=cols + [f"y{hz}"]).iloc[:-0 or None]
                    tr = tr[tr.index <= m - hz]
                    te = X.loc[[m]]
                    if len(tr) < 36 or te[cols].isna().any(axis=1).iloc[0] or pd.isna(te[f"y{hz}"].iloc[0]):
                        continue
                    mdl = ridge_fit(tr[cols].values, tr[f"y{hz}"].values, alpha=len(tr) * 0.05)
                    pr.append(float(ridge_pred(mdl, te[cols].values)[0])); ys.append(float(te[f"y{hz}"].iloc[0]))
                if len(pr) < 24:
                    continue
                pr, ys = np.array(pr), np.array(ys)
                out.append({"sym": s, "name": name, "horizon_m": hz, "model": name_, "n": len(pr), "r2_oos": round((1 - ((ys - pr) ** 2).sum() / (ys ** 2).sum()) * 100, 1),
                            "hit": round(float((np.sign(pr) == np.sign(ys)).mean() * 100), 1), "corr": round(float(np.corrcoef(pr, ys)[0, 1]), 2)})
        # full-sample coefficients for reading (standardized), 3-month horizon
        cols = ["stocks_dev", "stocks_yoy", "exports_yoy", "prod_yoy", "disapp_yoy", "mom1", "mom3", "level"]
        tr = X.dropna(subset=cols + ["y3"])
        if len(tr) > 36:
            mu, sd, b, c = ridge_fit(tr[cols].values, tr["y3"].values, alpha=len(tr) * 0.05)
            out.append({"sym": s, "name": name, "horizon_m": 3, "model": "coefficients (standardized, full sample)", **{k: round(float(v) * 100, 2) for k, v in zip(cols, b)}})
    return out


# ------------------------------------------------------------------ main
def main():
    D, cp, T, W, P, S, pub, E, F, settle, ann = build_panel()
    print("panel", len(D), D.t.min().date(), D.t.max().date())
    D = walk_forward(D, T)
    # weekly decision panel with every forecast, for the strategy-ideas module (models/dairy_ideas.py)
    keep = ["t", "sym", "m", "h", "F", "y", "cash", "basis", "seas", "mom4", "fmom", "sbasis_spot", "nc_gap", "spot_mom", "nc_or_spot"] + [c for c in D.columns if c.startswith("p_")]
    D[keep].assign(m=D.m.astype(str)).to_csv(ROOT / "data" / "dairy" / "derived" / "dairy_panel.csv.gz", index=False, float_format="%.6g")
    out = {"generated": date.today().isoformat(), "models": MODELS, "specs": {s: {"name": v[4], "usd_per_unit": v[2], "cost": v[3]} for s, v in SPEC.items()}}
    out["persistence"] = persistence(P, S, ann, settle)
    out["fundamentals"] = fundamentals_forecast(ann, E)
    ev = evaluate(D)
    out["evaluation"] = ev
    # strategies
    strat = []
    books = {}
    for model in ("cash", "seasonal_cash", "beta_sbasis", "momentum", "ridge_cash", "ridge_fund", "ridge_all", "fut_momentum", "cash_fut_mom", "spot_gap", "beta_spot", "spot_mom", "ridge_spot"):
        for hmax in (2, 5):
            for hurdle in (1.0, 2.0):
                res = backtest(D[D.y.notna() | (D.t >= D.t.max() - pd.Timedelta(days=1))], settle, T, model, h_max=hmax, hurdle=hurdle)
                for s, R in res.items():
                    R = R[R.index >= "2014-01-01"]
                    st_all, st_a, st_b = stats(R), stats(R[R.index < SPLIT]), stats(R[R.index >= SPLIT])
                    st_c, st_d = stats(R[(R.index >= SPLIT) & (R.index < "2024-01-01")]), stats(R[R.index >= "2024-01-01"])
                    if not st_all:
                        continue
                    strat.append({"sym": s, "name": SPEC[s][4], "model": model, "h_max": hmax, "hurdle": hurdle, **st_all,
                                  "sharpe_2014_19": st_a["sharpe"] if st_a else None, "sharpe_2020_26": st_b["sharpe"] if st_b else None,
                                  "ann_2014_19": st_a["ann_usd"] if st_a else None, "ann_2020_26": st_b["ann_usd"] if st_b else None,
                                  "sharpe_2020_23": st_c["sharpe"] if st_c else None, "sharpe_2024_26": st_d["sharpe"] if st_d else None,
                                  "ann_2024_26": st_d["ann_usd"] if st_d else None, "maxdd_2020_26": st_b["maxdd_usd"] if st_b else None,
                                  "by_year": {int(y): int(round(v)) for y, v in R.pnl.groupby(R.index.year).sum().items()}})
                    books[(s, model, hmax, hurdle)] = R
    out["strategies"] = strat
    Sdf = pd.DataFrame(strat)
    # pre-specified "desk strategy": per contract, the model/settings with the best 2014-19 Sharpe (chosen on the first half only), judged on 2020-26
    pick = []
    for s in SPEC:
        x = Sdf[(Sdf.sym == s) & Sdf.sharpe_2014_19.notna()].sort_values("sharpe_2014_19", ascending=False)
        if len(x):
            r = x.iloc[0]
            pick.append({k: (r[k] if not isinstance(r[k], (np.floating, np.integer)) else r[k].item()) for k in ("sym", "name", "model", "h_max", "hurdle", "sharpe", "sharpe_2014_19", "sharpe_2020_26", "ann_usd", "ann_2014_19", "ann_2020_26", "maxdd_usd", "avg_positions")})
    out["selected_on_2014_19"] = pick
    pick2 = []
    for s in SPEC:
        x = Sdf[(Sdf.sym == s) & Sdf.sharpe_2020_23.notna()].sort_values("sharpe_2020_23", ascending=False)
        if len(x):
            r = x.iloc[0]
            pick2.append({k: (r[k] if not isinstance(r[k], (np.floating, np.integer)) else r[k].item()) for k in ("sym", "name", "model", "h_max", "hurdle", "sharpe", "sharpe_2020_23", "sharpe_2024_26", "ann_usd", "ann_2024_26", "maxdd_2020_26", "avg_positions")})
    out["selected_on_2020_23"] = pick2
    # portfolio of the ridge_cash model across all six (equal $ risk by trailing 52-week vol)
    port = {}
    for model in ("ridge_cash", "seasonal_cash", "ridge_all"):
        series = {s: books[(s, model, 5, 1.0)].pnl for s in SPEC if (s, model, 5, 1.0) in books}
        Pn = pd.DataFrame(series).fillna(0)
        Pn = Pn[Pn.index >= "2014-01-01"]
        sc = Pn.rolling(52, min_periods=26).std().shift(1)
        Wt = (1 / sc).div((1 / sc).sum(axis=1), axis=0).fillna(0)
        tgt = (Pn * Wt).sum(axis=1)
        x = tgt[tgt != 0]
        if len(x) > 50:
            eq = x.cumsum()
            port[model] = {"sharpe": round(float(x.mean() / x.std() * math.sqrt(52)), 2),
                           "sharpe_2014_19": round(float(x[x.index < SPLIT].mean() / x[x.index < SPLIT].std() * math.sqrt(52)), 2),
                           "sharpe_2020_26": round(float(x[x.index >= SPLIT].mean() / x[x.index >= SPLIT].std() * math.sqrt(52)), 2),
                           "equity": [[str(d.date()), round(float(v), 3)] for d, v in (eq / x.std()).resample("ME").last().items()],
                           "sum_usd_equity": [[str(d.date()), int(v)] for d, v in Pn.sum(axis=1).cumsum().resample("ME").last().items()]}
    out["portfolio"] = port
    # ---- desk book: two pre-specified sleeves on all six contracts, no per-contract selection
    #  convergence sleeve: CME-spot nowcast vs futures, contracts up to 2 months out
    #  trend sleeve: 4-week futures momentum, contracts up to 5 months out
    sleeves = {"convergence": ("spot_gap", 2, 1.0), "trend": ("fut_momentum", 5, 1.0), "cash_trend": ("cash_fut_mom", 2, 1.0)}
    cols = {}
    for nm_, (mdl, hm, hu) in sleeves.items():
        for s in SPEC:
            if (s, mdl, hm, hu) in books:
                cols[(nm_, s)] = books[(s, mdl, hm, hu)].pnl
    B = pd.DataFrame(cols).fillna(0)
    B = B[B.index >= "2019-06-01"]
    desk = {}
    for label, keys in (("Convergence (spot gap) + trend, all six", [k for k in B.columns if k[0] in ("convergence", "trend")]),
                        ("Convergence only", [k for k in B.columns if k[0] == "convergence"]), ("Trend only", [k for k in B.columns if k[0] == "trend"]),
                        ("Convergence + trend + cash momentum", list(B.columns))):
        X = B[keys]
        sc = X.rolling(52, min_periods=26).std().shift(1)
        Wt = (1 / sc.replace(0, np.nan))
        Wt = Wt.div(Wt.sum(axis=1), axis=0).fillna(0)
        rp = (X * Wt).sum(axis=1)
        rp = rp[rp.index >= "2020-01-01"]
        one = X.sum(axis=1)
        one = one[one.index >= "2020-01-01"]
        def sh(x):
            return round(float(x.mean() / x.std() * math.sqrt(52)), 2) if len(x) > 20 and x.std() > 0 else None
        eq1 = one.cumsum()
        desk[label] = {"sleeves": [f"{k[0]}:{k[1]}" for k in keys], "sharpe_risk_weighted": sh(rp), "sharpe_one_lot": sh(one),
                       "sharpe_2020_23": sh(one[one.index < "2024-01-01"]), "sharpe_2024_26": sh(one[one.index >= "2024-01-01"]),
                       "ann_usd_one_lot": int(round(one.sum() / ((one.index[-1] - one.index[0]).days / 365.25))), "maxdd_usd_one_lot": int(round(float((eq1 - eq1.cummax()).min()))),
                       "hit_weeks": round(float((one[one != 0] > 0).mean() * 100), 1), "by_year": {int(y): int(round(v)) for y, v in one.groupby(one.index.year).sum().items()},
                       "equity": [[str(d.date()), int(v)] for d, v in eq1.resample("ME").last().items()],
                       "corr_conv_trend": round(float(B[[k for k in B.columns if k[0] == "convergence"]].sum(axis=1).corr(B[[k for k in B.columns if k[0] == "trend"]].sum(axis=1))), 2)}
    out["desk_book"] = desk
    # equity curves for the best per contract (selected) and the ridge_cash h<=5 book
    out["equity"] = {f"{s}|{m}|{h}|{u}": [[str(d.date()), int(v)] for d, v in books[(s, m, h, u)].pnl.cumsum().resample("ME").last().items()]
                     for (s, m, h, u) in books if (m in ("ridge_cash", "seasonal_cash", "cash", "ridge_all") and h == 5 and u == 1.0)}
    # live signals: latest decision day
    last = D.t.max()
    L = D[(D.t == last)].sort_values(["sym", "h"])
    out["live"] = [{"sym": r.sym, "name": SPEC[r.sym][4], "month": str(r.m), "h": int(r.h), "futures": round(r.F, 4), "cash": round(r.cash, 4),
                    "basis_pct": round(r.basis * 100, 2), "seasonal_pct": round(r.seas * 100, 2),
                    **{f"f_{k}": (round(float(getattr(r, "p_" + k)) * 100, 2) if pd.notna(getattr(r, "p_" + k)) else None) for k in ("seasonal_cash", "ridge_cash", "ridge_all", "ridge_fund")},
                    "cost_pct": round(SPEC[r.sym][3] / r.F * 100, 2),
                    "spot_gap_pct": round(float(r.p_spot_gap) * 100, 2) if pd.notna(r.p_spot_gap) else None, "fmom_pct": round(float(r.fmom) * 100, 2) if pd.notna(r.fmom) else None,
                    "sig_convergence": (int(np.sign(r.p_spot_gap)) if r.h <= 2 and pd.notna(r.p_spot_gap) and abs(r.p_spot_gap) > SPEC[r.sym][3] / r.F else 0),
                    "sig_trend": (int(np.sign(r.fmom)) if r.h <= 5 and pd.notna(r.fmom) and abs(r.fmom) > SPEC[r.sym][3] / r.F else 0),
                    "usd_per_unit": SPEC[r.sym][2]} for r in L.itertuples()]
    out["live_date"] = str(last.date())
    # ---- learnings
    Ldf = pd.DataFrame(ev)
    Lr = []
    pers = {r["sym"]: r for r in out["persistence"]}
    Lr.append("Persistence is real but mostly in the cash prices, not in futures: monthly announced price changes have autocorrelation " +
              ", ".join(f"{pers[s]['name']} {pers[s]['monthly_ac1']}" for s in SPEC) + " (an average of a random walk alone gives about 0.25); "
              "weekly futures returns have " + ", ".join(f"{pers[s]['name']} {pers[s]['futures_weekly_ac1']}" for s in SPEC) + ". Futures already price most of the cash persistence.")
    for s in SPEC:
        x = Ldf[(Ldf.sym == s) & (Ldf.horizon == "all") & (Ldf.period == "2020+")].set_index("model")
        if len(x):
            best = x.drop(index="futures", errors="ignore").sort_values("r2_oos", ascending=False).iloc[0]
            Lr.append(f"{SPEC[s][4]}: best forecast of the futures error is '{MODELS[best.name]}' (out-of-sample R² {best.r2_oos:+.1f}% vs the futures price, right on direction {best.hit}% of the time, month-clustered t {best.t}).")
    fd = pd.DataFrame([r for r in out["fundamentals"] if "r2_oos" in r])
    if len(fd):
        g = fd[fd.model == "fundamentals only"]
        Lr.append("Supply and demand (ERS stocks vs normal, production, exports, domestic use) forecast the next 3 months of announced prices with out-of-sample R² " +
                  ", ".join(f"{r.name} {r.r2_oos:+.0f}%" for r in g[g.horizon_m == 3].itertuples()) + "; momentum alone: " +
                  ", ".join(f"{r.name} {r.r2_oos:+.0f}%" for r in fd[(fd.model == 'momentum only') & (fd.horizon_m == 3)].itertuples()) + ".")
    for r in pick:
        Lr.append(f"Strategy chosen on 2014-19 only for {r['name']}: {MODELS[r['model']]}, months up to {r['h_max']} ahead, hurdle {r['hurdle']}x cost: Sharpe {r['sharpe_2014_19']} in 2014-19, then {r['sharpe_2020_26']} in 2020-26 (${r['ann_2020_26']:,} a year per one-lot book).")
    for k, v in port.items():
        Lr.append(f"Six-contract portfolio, {MODELS[k]}: Sharpe {v['sharpe']} (2014-19 {v['sharpe_2014_19']}, 2020-26 {v['sharpe_2020_26']}).")
    for r in pick2:
        Lr.append(f"Chosen on 2020-23 only for {r['name']}: {MODELS[r['model']]}, up to {r['h_max']} months out, hurdle {r['hurdle']}x cost: Sharpe {r['sharpe_2020_23']} in 2020-23, then {r['sharpe_2024_26']} in 2024-26 (${r['ann_2024_26']:,} a year).")
    for k, v in desk.items():
        Lr.append(f"Desk book '{k}' (2020-26, one lot per signal): Sharpe {v['sharpe_one_lot']} (2020-23 {v['sharpe_2020_23']}, 2024-26 {v['sharpe_2024_26']}), about ${v['ann_usd_one_lot']:,} a year, worst drawdown ${v['maxdd_usd_one_lot']:,}; risk-weighted Sharpe {v['sharpe_risk_weighted']}.")
    out["learnings"] = Lr
    (ROOT / "data" / "dairy" / "derived" / "dairy_lab.json").write_text(json.dumps(out, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else str(o)).replace("NaN", "null"))
    print("\n".join(Lr))
    print(Sdf.sort_values("sharpe", ascending=False).head(25)[["name", "model", "h_max", "hurdle", "sharpe", "sharpe_2014_19", "sharpe_2020_26", "ann_usd", "maxdd_usd", "avg_positions"]].to_string())


if __name__ == "__main__":
    main()
