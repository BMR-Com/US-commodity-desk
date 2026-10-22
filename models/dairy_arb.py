#!/usr/bin/env python3
"""Dairy weekly-to-monthly convergence lab.

CME Class III / IV milk, cheese, butter, nonfat dry milk and dry whey futures are cash-settled to USDA's monthly
announced prices. Those are sales-weighted averages of the weekly NDPSR survey prices for the weeks ending in the
month (and, for Class III / IV, formulas of those averages). So during a contract month part of the settlement is
already known, and the rest is closely tied to the CME daily spot (cash) markets, which the survey follows with a lag.

This script asks whether futures price that correctly:
1. Lead-lag: how the weekly NDPSR price relates to the CME spot market in the same and earlier weeks.
2. Nowcast: on every trading day, estimate each contract's settlement from published NDPSR weeks plus a forecast
   of the unpublished weeks from CME spot (regressions refit monthly on past data only). Compare its error with
   the futures price and with a naive nowcast (unpublished weeks = last NDPSR print).
3. Gap trade: on each NDPSR release day, buy (sell) the contract when the nowcast is above (below) the futures by
   more than a threshold; hold to final settlement. Costs: 2 ticks round trip.
4. Release-day surprise: does the futures market under-react to a weekly NDPSR print that differs from what CME
   spot implied (drift over the next days)?
5. Formula arbitrage: Class III futures vs the Class III implied by cheese, butter and whey futures of the same
   month (and Class IV vs butter + nonfat); both legs settle on the same USDA averages, so gaps must close.
6. Live: today's nowcast vs futures for the open months.
Writes data/dairy/derived/dairy_arb.json.
"""
import glob, json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from dairy_class import components, regime, load_class_prices, RAW  # noqa: E402

CODES = "FGHJKMNQUVXZ"
# futures: settlement column, units multiplier vs USDA $/lb or $/cwt, tick, $ per 1.00 unit move, name
SPEC = {"DC": ("class3", 1, 0.01, 2000, "Class III milk ($/cwt)"),
        "GDK": ("class4", 1, 0.01, 2000, "Class IV milk ($/cwt)"),
        "CSC": ("cheese", 1, 0.001, 20000, "Cheese ($/lb)"),
        "CB": ("butter", 100, 0.025, 200, "Butter (c/lb)"),
        "GNF": ("ndm", 100, 0.025, 440, "Nonfat dry milk (c/lb)"),
        "DY": ("whey", 100, 0.025, 440, "Dry whey (c/lb)")}
PRODUCTS = ("block", "barrel", "butter", "ndm", "whey")
SPLIT = pd.Timestamp("2024-01-01")
# assumed round-trip cost (about one bid-ask spread in these thin markets), in futures price units
COST = {"DC": 0.05, "GDK": 0.10, "CSC": 0.005, "CB": 0.5, "GNF": 0.5, "DY": 0.5}


def ctstat(pnl, months):
    """t-stat with trades averaged per contract month first (trades in the same month are not independent)."""
    m = pd.Series(np.asarray(pnl, float)).groupby(np.asarray(months)).mean()
    return round(float(m.mean() / m.std() * math.sqrt(len(m))), 2) if len(m) > 3 and m.std() > 0 else None


# ------------------------------------------------------------------ data
def cme_spot():
    d = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(ROOT / "data" / "ams" / "cme_daily_dairy" / "*.csv")))])
    d["date"] = pd.to_datetime(d.report_date)
    key = np.select([d.commodity.eq("Butter"), d.commodity.eq("Nonfat Dry Milk"), d.commodity.eq("Dry Whey"),
                     d.commodity.eq("Cheese") & d.package.astype(str).str.contains("Block"),
                     d.commodity.eq("Cheese") & d.package.astype(str).str.contains("Barrel")],
                    ["butter", "ndm", "whey", "block", "barrel"], "")
    d["p"] = key
    d = d[d.p != ""]
    s = d.pivot_table(index="date", columns="p", values="close_price", aggfunc="last").sort_index()
    hp = ROOT / "data" / "ams" / "cme_daily_dairy_hist" / "history.csv"     # Nov 2018 on, from DMN weekly recaps
    if hp.exists():
        h = pd.read_csv(hp, parse_dates=["date"]).pivot_table(index="date", columns="product", values="close", aggfunc="last")
        s = pd.concat([h[h.index < s.index.min()], s]).sort_index()
    return s[list(PRODUCTS)]


def ndpsr():
    """Weekly NDPSR by product incl. separate blocks and barrels (moisture-adjusted), latest revision, publish date."""
    files = {"block": ("40_pound_block_cheddar_cheese_prices_and_sales.csv", "cheese_40_Price", "cheese_40_Sales"),
             "barrel": ("500_pound_barrel_cheddar_cheese_prices_sales_and_moisture_content.csv", "cheese_500_Wtd_Price", "cheese_500_Sales"),
             "butter": ("butter_prices_and_sales.csv", "Butter_Price", "Butter_Sales"),
             "ndm": ("nonfat_dry_milk_prices_and_sales.csv", "nonfat_milk_Price", "nonfat_milk_Sales"),
             "whey": ("dry_whey_prices_and_sales.csv", "whey_Price", "whey_Sales")}
    out = []
    for p, (fn, pc, sc) in files.items():
        frames = [pd.read_csv(RAW / "ndpsr" / fn)]
        fin = RAW / "ndpsr" / ("final_" + fn)
        if fin.exists():
            frames.append(pd.read_csv(fin))
        d = pd.concat(frames).rename(columns={"Week Ending Date": "week", pc: "price", sc: "sales"})
        d["published"] = pd.to_datetime(d.published_date)
        d["week"] = pd.to_datetime(d.week)
        d["sales"] = pd.to_numeric(d.sales.astype(str).str.replace(",", ""), errors="coerce")
        d = d.dropna(subset=["price"])
        first = d.groupby("week").published.min().rename("first_pub")       # when the week was first known
        d = d.sort_values("published").groupby("week").tail(1).join(first, on="week")
        d["product"] = p
        out.append(d[["week", "product", "price", "sales", "first_pub"]])
    w = pd.concat(out)
    return w[w.week >= "2012-01-01"]


def futures():
    from futures_io import load_contracts      # settlements on exchange trade dates
    return {s: load_contracts(s) for s in SPEC}


def targets(cp):
    t = pd.DataFrame({"class3": cp.class_3_Price, "class4": cp.class_4_Price, "cheese": cp.cheese_monthly_avg_Price,
                      "butter": cp.butter_monthly_avg_Price, "ndm": cp.nfdm_monthly_avg_Price, "whey": cp.whey_monthly_avg_Price})
    t["ann"] = pd.to_datetime(cp.published_date).dt.normalize()
    return t


# ------------------------------------------------------------------ lead-lag
def spot_weeks(spot):
    """Mon-Fri average of CME spot for the week ending each Saturday."""
    wk = spot.resample("W-SAT").mean()
    return wk


def leadlag(W, wk):
    rows = []
    for p in PRODUCTS:
        y = W[W["product"] == p].set_index("week").price
        x = wk[p]
        j = pd.DataFrame({"y": y}).join(pd.DataFrame({f"l{k}": x.shift(k) for k in range(0, 4)}), how="inner").dropna()
        if len(j) < 30:
            continue
        corr = {k: round(float(j.y.diff().corr(j[f"l{k}"].diff())), 2) for k in range(4)}
        X = np.c_[np.ones(len(j)), j[["l0", "l1", "l2"]].values]
        b = np.linalg.lstsq(X, j.y.values, rcond=None)[0]
        res = j.y.values - X @ b
        lvl = j.y.mean()
        rows.append({"product": p, "weeks": len(j), "corr_changes": corr, "coef": {"const": round(float(b[0]), 3), "same_week": round(float(b[1]), 2),
                     "one_week_before": round(float(b[2]), 2), "two_weeks_before": round(float(b[3]), 2)},
                     "resid_sd": round(float(res.std()), 4), "resid_sd_pct": round(float(res.std() / lvl * 100), 2),
                     "avg_gap": round(float((j.y - j.l0).mean()), 4)})
    return rows


def fit_models(W, wk, cutoff):
    """NDPSR_week ~ CME spot same week, 1 and 2 weeks earlier; only weeks published before cutoff."""
    M = {}
    for p in PRODUCTS:
        y = W[(W["product"] == p) & (W.first_pub < cutoff)].set_index("week").price
        j = pd.DataFrame({"y": y}).join(pd.DataFrame({f"l{k}": wk[p].shift(k) for k in range(3)}), how="inner").dropna().tail(156)
        if len(j) < 26:
            M[p] = None
            continue
        X = np.c_[np.ones(len(j)), j[["l0", "l1", "l2"]].values]
        M[p] = np.linalg.lstsq(X, j.y.values, rcond=None)[0]
    return M


# ------------------------------------------------------------------ nowcast
def month_saturdays(m):
    return [d for d in pd.date_range(m.start_time, m.end_time, freq="W-SAT")]


def nowcast_all(W, spot, cp, start):
    """For each trading day d (spot data) and months d.month-1 .. d.month+2 not yet announced on d:
    product monthly averages and class prices, model (spot-based) and naive (last print)."""
    T = targets(cp)
    wk_full = spot_weeks(spot)
    piv = W.pivot_table(index="week", columns="product", values="price")
    sal = W.pivot_table(index="week", columns="product", values="sales")
    pub = W.groupby("week").first_pub.max()
    days = spot.index[spot.index >= start]
    out = []
    models, mkey = None, None
    for d in days:
        if mkey != (d.year, d.month):
            models, mkey = fit_models(W, wk_full, d.normalize().replace(day=1)), (d.year, d.month)
        sp = spot.loc[:d].ffill()
        last = sp.iloc[-1]
        # weekly spot averages known through d; future days filled with the latest spot
        known_pub = pub[pub.dt.normalize() <= d].index           # weeks published by d
        lastweek = known_pub.max()
        avg_sales = sal.reindex(known_pub).dropna(how="all").tail(8).mean()
        sp_ext = pd.concat([sp, pd.DataFrame([last.values] * 70, columns=sp.columns, index=pd.bdate_range(d + pd.Timedelta(days=1), periods=70))])
        wk = sp_ext.resample("W-SAT").mean()
        cur = d.to_period("M")
        for m in (cur - 1, cur, cur + 1, cur + 2):
            if m in T.index and T.loc[m, "ann"] <= d:
                continue
            sats = month_saturdays(m)
            px_model, px_naive, nknown = {}, {}, 0
            for p in PRODUCTS:
                vals_m, vals_n, wts = [], [], []
                for s in sats:
                    w_ = sal.at[s, p] if (s in known_pub and s in sal.index and pd.notna(sal.at[s, p])) else avg_sales.get(p, np.nan)
                    if s in known_pub and s in piv.index and pd.notna(piv.at[s, p]):
                        vals_m.append(piv.at[s, p]); vals_n.append(piv.at[s, p])
                        if p == "block":
                            nknown += 1
                    else:
                        b = models.get(p)
                        l = [wk[p].get(s - pd.Timedelta(weeks=k), np.nan) for k in range(3)]
                        vals_m.append(b[0] + b[1] * l[0] + b[2] * l[1] + b[3] * l[2] if b is not None and not np.isnan(l).any() else np.nan)
                        vals_n.append(piv.at[lastweek, p] if lastweek in piv.index else np.nan)
                    wts.append(w_ if pd.notna(w_) else 1.0)
                wts = np.array(wts, float)
                px_model[p] = float(np.dot(vals_m, wts) / wts.sum()) if not np.isnan(vals_m).any() else np.nan
                px_naive[p] = float(np.dot(vals_n, wts) / wts.sum()) if not np.isnan(vals_n).any() else np.nan
                if p == "barrel":
                    px_model["barrel_w"] = px_naive["barrel_w"] = float(wts.sum())
                if p == "block":
                    px_model["block_w"] = px_naive["block_w"] = float(wts.sum())
            r = regime(m)
            row = {"date": d, "m": m, "known": nknown, "weeks": len(sats)}
            for tag, px in (("mod", px_model), ("nai", px_naive)):
                if r["cheese"] == "blend" and pd.notna(px.get("barrel")):
                    ch = (px["block"] * px["block_w"] + (px["barrel"] + 0.03) * px["barrel_w"]) / (px["block_w"] + px["barrel_w"])
                else:
                    ch = px["block"]
                c = components(ch, px["butter"], px["ndm"], px["whey"], r)
                row.update({f"{tag}_cheese": ch, f"{tag}_butter": px["butter"], f"{tag}_ndm": px["ndm"], f"{tag}_whey": px["whey"],
                            f"{tag}_class3": c["class3"], f"{tag}_class4": c["class4"]})
            out.append(row)
    return pd.DataFrame(out)


# ------------------------------------------------------------------ evaluation helpers
def phase(row, ann):
    d, m = row.date, row.m
    if d.to_period("M") < m:
        return "1. Month before" if (m.start_time - d).days > 14 else "2. Last 2 weeks before"
    if d.to_period("M") == m:
        return f"3. In month, {row.known} week{'s' if row.known != 1 else ''} published" if row.known < 3 else "3. In month, 3+ weeks published"
    return "4. After month end (last week pending)"


def tstat(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(len(x))) if len(x) > 2 and x.std() > 0 else None


def main():
    cp = load_class_prices()
    T = targets(cp)
    W = ndpsr()
    spot = cme_spot()
    F = futures()
    wk = spot_weeks(spot)
    print("spot", spot.index.min().date(), spot.index.max().date(), "ndpsr", W.week.max().date())

    out = {"generated": date.today().isoformat(), "spot_from": str(spot.index.min().date())}
    out["leadlag"] = leadlag(W, wk)

    start = spot.index.min() + pd.Timedelta(days=200)     # 26+ weeks of spot history for the first regression
    N = nowcast_all(W, spot, cp, start)
    print("nowcast rows", len(N))

    # attach futures and targets
    rows = []
    for s, (col, mult, tick, dollar, name) in SPEC.items():
        f = F[s]
        last_date = f.groupby("m").date.max()
        f = f[f.volume > 0]                           # traded days only: the price history repeats the last trade on days without volume
        fx = f.set_index(["date", "m"]).close
        j = N[["date", "m", "known", "weeks", f"mod_{col}", f"nai_{col}"]].copy()
        j["F"] = [fx.get((d, m), np.nan) for d, m in zip(j.date, j.m)]
        j = j.dropna(subset=["F"])
        j = j[j.date < j.m.map(last_date)]            # the last row holds the final settlement, not a traded price
        j["T"] = j.m.map(T[col]) * mult
        j["mod"] = j[f"mod_{col}"] * mult
        j["nai"] = j[f"nai_{col}"] * mult
        j["sym"] = s
        rows.append(j[["sym", "date", "m", "known", "weeks", "F", "mod", "nai", "T"]])
    D = pd.concat(rows)
    D["phase"] = [phase(r, None) for r in D.itertuples()]
    live = D[D["T"].isna()].copy()
    D = D.dropna(subset=["T", "mod"])
    print("evaluation rows", len(D), D.date.min().date(), D.date.max().date())

    # ---- 2. accuracy by phase
    acc = []
    for s in SPEC:
        x = D[D.sym == s]
        for ph, g in x.groupby("phase"):
            e_f, e_m, e_n = (g.F - g["T"]).abs(), (g["mod"] - g["T"]).abs(), (g.nai - g["T"]).abs()
            # does the nowcast add information beyond futures? slope of (T-F) on (mod-F)
            gap = g["mod"] - g.F
            b = float(np.polyfit(gap, g["T"] - g.F, 1)[0]) if gap.std() > 0 and len(g) > 20 else None
            acc.append({"sym": s, "phase": ph, "obs": len(g), "months": g.m.nunique(), "mae_futures": round(float(e_f.mean()), 4), "mae_nowcast": round(float(e_m.mean()), 4),
                        "mae_naive": round(float(e_n.mean()), 4), "mae_blend": round(float(((g.F + g["mod"]) / 2 - g["T"]).abs().mean()), 4),
                        "nowcast_better_pct": round(float((e_m < e_f).mean() * 100)), "slope": round(b, 2) if b is not None else None,
                        "ticks_futures": round(float(e_f.mean() / SPEC[s][2]), 1)})
    out["accuracy"] = acc

    # ---- 3. gap trade on NDPSR release days, hold to settlement
    pubdays = set(W.first_pub.dt.normalize().unique())
    G = D[D.date.isin(pubdays)].copy()
    G["gap"] = G["mod"] - G.F
    G["gap_n"] = G.nai - G.F
    trades = []
    for s, (col, mult, tick, dollar, name) in SPEC.items():
        g = G[G.sym == s]
        c = COST[s]
        for k in (0.5, 1, 2, 4):
            thr = k * c                      # threshold in multiples of the round-trip cost
            for src in ("gap", "gap_n"):
                for win, sub in (("All", g), ("Within 2 weeks of / inside the month", g[(g.m.dt.start_time - g.date).dt.days <= 14])):
                    x = sub[sub[src].abs() > thr]
                    if len(x) < 8:
                        continue
                    pnl = np.sign(x[src]) * (x["T"] - x.F) - c
                    ins, oos = pnl[x.date < SPLIT], pnl[x.date >= SPLIT]
                    lo, sh = pnl[x[src] > 0], pnl[x[src] < 0]
                    trades.append({"sym": s, "name": name, "signal": "Spot-based nowcast" if src == "gap" else "Naive (last NDPSR print)", "window": win,
                                   "threshold_x_cost": k, "threshold": round(thr, 4),
                                   "trades": len(x), "months": x.m.nunique(), "hit": round(float((pnl > 0).mean() * 100)), "avg": round(float(pnl.mean()), 4),
                                   "avg_usd": round(float(pnl.mean() * dollar)), "t": ctstat(pnl, x.m.astype(str)),
                                   "long_usd": round(float(lo.mean() * dollar)) if len(lo) else None, "short_usd": round(float(sh.mean() * dollar)) if len(sh) else None,
                                   "hit_2021_23": round(float((ins > 0).mean() * 100)) if len(ins) else None, "avg_usd_2021_23": round(float(ins.mean() * dollar)) if len(ins) else None,
                                   "hit_2024_26": round(float((oos > 0).mean() * 100)) if len(oos) else None, "avg_usd_2024_26": round(float(oos.mean() * dollar)) if len(oos) else None,
                                   "n_2024_26": int(len(oos)), "worst_usd": round(float(pnl.min() * dollar)), "cost_usd": round(c * dollar)})
    out["gap_trades"] = trades
    # by phase (threshold 1x cost, spot-based)
    bp = []
    for s, (col, mult, tick, dollar, name) in SPEC.items():
        g = G[(G.sym == s) & (G.gap.abs() > COST[s])]
        for ph, x in g.groupby("phase"):
            if len(x) < 6:
                continue
            pnl = np.sign(x.gap) * (x["T"] - x.F) - COST[s]
            bp.append({"sym": s, "phase": ph, "trades": len(x), "hit": round(float((pnl > 0).mean() * 100)),
                       "avg_usd": round(float(pnl.mean() * dollar)), "t": ctstat(pnl, x.m.astype(str))})
    out["gap_by_phase"] = bp

    # ---- 4. release-day surprise and drift (current-month contract)
    sur = []
    Ns = N.set_index(["date", "m"])
    for s, (col, mult, tick, dollar, name) in SPEC.items():
        ff = F[s]
        lastd = ff.groupby("m").date.transform("max")
        f = ff[(ff.volume > 0) | (ff.date == lastd)].set_index(["m", "date"]).close.sort_index()
        recs = []
        for d in sorted(pubdays):
            if d < start + pd.Timedelta(days=10):
                continue
            for m in (d.to_period("M") - 1, d.to_period("M")):
                if m not in f.index.get_level_values(0):
                    continue
                fm = f.loc[m]
                if d not in fm.index:
                    continue
                prev = fm.index[fm.index < d]
                if len(prev) == 0 or (d - prev[-1]).days > 7:
                    continue
                p0 = prev[-1]
                if (p0, m) not in Ns.index or (d, m) not in Ns.index:
                    continue
                exp_move = (Ns.at[(d, m), f"mod_{col}"] - Ns.at[(p0, m), f"mod_{col}"]) * mult   # change in nowcast from the print (and spot since the last trade)
                i = fm.index.get_loc(d)
                if i + 1 >= len(fm) - 1:
                    continue
                r0 = fm.iloc[i] - fm.loc[p0]
                drift = {k: fm.iloc[min(i + k, len(fm) - 2)] - fm.iloc[i] for k in (1, 3, 5)}
                recs.append({"d": d, "m": m, "exp": exp_move, "r0": r0, **{f"d{k}": v for k, v in drift.items()}})
        R = pd.DataFrame(recs).dropna()
        if len(R) < 20:
            continue
        big = R[R.exp.abs() > COST[s]]
        beta0 = float(np.polyfit(R.exp, R.r0, 1)[0]) if R.exp.std() > 0 else None
        row = {"sym": s, "name": name, "events": len(R), "big": len(big), "reaction_slope": round(beta0, 2) if beta0 is not None else None,
               "same_day_hit": round(float((np.sign(R.exp) == np.sign(R.r0))[R.exp != 0].mean() * 100))}
        for k in (1, 3, 5):
            pnl = np.sign(big.exp) * big[f"d{k}"] - COST[s]
            row[f"drift{k}_ticks"] = round(float((np.sign(big.exp) * big[f"d{k}"]).mean() / tick), 1) if len(big) else None
            row[f"drift{k}_usd_net"] = round(float(pnl.mean() * dollar)) if len(big) else None
            row[f"drift{k}_hit"] = round(float((pnl > 0).mean() * 100)) if len(big) else None
            row[f"drift{k}_t"] = round(tstat(pnl), 2) if len(big) > 2 and tstat(pnl) is not None else None
        sur.append(row)
    out["surprise"] = sur

    # ---- 5. formula arbitrage: Class III / IV futures vs component futures, same month (2012 on)
    px = {}
    for s in SPEC:
        f = F[s]
        last_date = f.groupby("m").date.max()
        f = f[(f.date < f.m.map(last_date)) & (f.volume > 0)]   # only days the contract actually traded
        px[s] = f.set_index(["date", "m"]).close
    J = pd.DataFrame(px).dropna(subset=["DC", "CSC", "CB", "DY"], how="any")
    J = J[J.index.get_level_values(0) >= "2012-01-01"]
    imp3, imp4 = [], []
    for (d, m), x in J.iterrows():
        r = regime(m)
        c = components(x.CSC, x.CB / 100, (x.GNF / 100) if pd.notna(x.GNF) else 1.0, x.DY / 100, r)
        imp3.append(c["class3"]); imp4.append(c["class4"] if pd.notna(x.GNF) else np.nan)
    J["imp3"], J["imp4"] = imp3, imp4
    J["gap3"], J["gap4"] = J.DC - J.imp3, J.GDK - J.imp4
    J = J.reset_index().rename(columns={"level_0": "date", "level_1": "m"})
    J["T3"], J["T4"] = J.m.map(T.class3), J.m.map(T.class4)
    J["days_left"] = (J.m.map(T.ann) - J.date).dt.days
    arb = {}
    for k, cls, legs in (("class3", "gap3", "cheese, butter, dry whey"), ("class4", "gap4", "butter, nonfat dry milk")):
        x = J.dropna(subset=[cls])
        a = x[cls].abs()
        yr = x.groupby(x.date.dt.year)[cls].agg(lambda s: round(float(s.abs().mean()), 3)).to_dict()
        # convergence: gap 20-40 days before announcement vs at the last observed day
        near = x[(x.days_left >= 20) & (x.days_left <= 40)].groupby("m")[cls].mean()
        end = x.sort_values("date").groupby("m")[cls].last()
        cv = pd.DataFrame({"early": near, "end": end}).dropna()
        trades_ = []
        for thr in (0.05, 0.10, 0.20, 0.30):
            e = x[x[cls].abs() > thr].sort_values("date").groupby("m").head(1)        # first breach per month
            e = e.join(end.rename("end_gap"), on="m")
            pnl = (e[cls].abs() - np.sign(e[cls]) * e.end_gap)                          # gap closes to its final value
            pnl = pnl - (0.12 if k == "class3" else 0.18)                               # costs: one bid-ask on every leg, in $/cwt of Class milk
            if len(pnl):
                trades_.append({"threshold": thr, "months": int(len(e)), "hit": round(float((pnl > 0).mean() * 100)), "avg_cwt": round(float(pnl.mean()), 3),
                                "avg_usd": round(float(pnl.mean() * 2000)), "avg_days_to_close": round(float(e.days_left.mean()))})
        recent = x[x.date >= x.date.max() - pd.Timedelta(days=10)].sort_values("date").groupby("m").tail(1)
        arb[k] = {"legs": legs, "obs": int(len(x)), "months": int(x.m.nunique()), "mean_abs_gap": round(float(a.mean()), 3), "share_gt_10c": round(float((a > 0.10).mean() * 100), 1),
                  "share_gt_25c": round(float((a > 0.25).mean() * 100), 1), "max_abs": round(float(a.max()), 2), "by_year": yr,
                  "end_gap_mean_abs": round(float(end.abs().mean()), 3), "early_vs_end_corr": round(float(cv.early.corr(cv.end)), 2) if len(cv) > 5 else None,
                  "trades": trades_, "now": [{"month": str(r.m), "futures": r.DC if k == "class3" else r.GDK, "implied": round(float(r.imp3 if k == "class3" else r.imp4), 2),
                                              "gap": round(float(getattr(r, cls)), 2)} for r in recent.itertuples() if pd.notna(getattr(r, cls))][-8:]}
    # hedge ratios: component contracts per 10 Class contracts (current formula), from the formula's sensitivities
    r = regime(pd.Period(date.today(), "M"))
    base = dict(cheese=1.6, butter=1.5, ndm=1.5, whey=0.6)
    def dv(prod, cls, h=0.01):
        up = dict(base); up[prod] += h
        return (components(up["cheese"], up["butter"], up["ndm"], up["whey"], r)[cls] - components(base["cheese"], base["butter"], base["ndm"], base["whey"], r)[cls]) / h
    lots = {"CSC": 20000, "CB": 20000, "GNF": 44000, "DY": 44000}
    hr = {}
    for cls, prods in (("class3", (("cheese", "CSC"), ("butter", "CB"), ("whey", "DY"))), ("class4", (("butter", "CB"), ("ndm", "GNF")))):
        hr[cls] = {sym: round(float(dv(p_, cls) * 2000 / lots[sym] * 10), 1) for p_, sym in prods}   # $/cwt per $/lb x 2,000 cwt / lot size
    arb["hedge_per_10"] = hr
    arb["cost_cwt"] = {"class3": 0.12, "class4": 0.18}
    out["formula_arb"] = arb

    # ---- risk collapse through the month: daily futures change sd by phase
    vol = []
    for s, (col, mult, tick, dollar, name) in SPEC.items():
        x = D[D.sym == s].sort_values(["m", "date"]).copy()
        x["chg"] = x.groupby("m").F.diff()
        v = x.dropna(subset=["chg"]).groupby("phase").chg.std()
        vol.append({"sym": s, **{k: round(float(val / tick), 1) for k, val in v.items()}})
    out["daily_sd_ticks"] = vol

    # ---- live
    lv = []
    dmax = N.date.max()
    for r in N[N.date == dmax].itertuples():
        if r.m in T.index and pd.notna(T.loc[r.m, "class3"]):
            continue
        for sym, (col, mult, tick, dollar, name) in SPEC.items():
            f = F[sym][F[sym].m == r.m].sort_values("date")
            if not len(f):
                continue
            fl = f.iloc[-1]
            tr = f[f.volume > 0]
            mod, nai = getattr(r, f"mod_{col}") * mult, getattr(r, f"nai_{col}") * mult
            if pd.isna(mod):
                continue
            lv.append({"sym": sym, "name": name, "month": str(r.m), "date": str(dmax.date()), "known_weeks": int(r.known), "weeks": int(r.weeks),
                       "futures": round(float(fl.close), 4), "futures_date": str(fl.date.date()), "last_trade": str(tr.date.iloc[-1].date()) if len(tr) else None,
                       "nowcast": round(float(mod), 4), "naive": round(float(nai), 4), "gap_ticks": round(float((mod - fl.close) / tick), 1),
                       "gap_usd": round(float((mod - fl.close) * dollar)), "cost_usd": round(COST[sym] * dollar)})
    out["live"] = lv
    out["specs"] = {s: {"name": v[4], "tick": v[2], "usd_per_unit": v[3]} for s, v in SPEC.items()}
    out["volume"] = {s: int(F[s][F[s].date >= pd.Timestamp.today() - pd.Timedelta(days=365)].groupby("date").volume.sum().mean()) for s in SPEC}

    # ---- learnings
    L = []
    ll = {r["product"]: r for r in out["leadlag"]}
    if ll:
        L.append("Weekly NDPSR prices follow the CME spot market with a lag: " + "; ".join(
            f"{p} (weight on same week {r['coef']['same_week']}, week before {r['coef']['one_week_before']}, two weeks before {r['coef']['two_weeks_before']}; typical miss {r['resid_sd_pct']}%)"
            for p, r in ll.items()) + ". So by the time a week is published, most of it can be predicted from spot prices already seen.")
    A = pd.DataFrame(acc)
    for s in ("DC", "CSC", "CB", "GDK", "GNF", "DY"):
        a = A[A.sym == s].sort_values("phase")
        if len(a):
            L.append(f"{SPEC[s][4]}: futures error vs final settlement {' → '.join(f'{x.mae_futures:g}' for x in a.itertuples())} through the phases; spot-based nowcast "
                     f"{' → '.join(f'{x.mae_nowcast:g}' for x in a.itertuples())}; nowcast closer than futures {round(float(a.nowcast_better_pct.mean()))}% of the time on average.")
    Tdf = pd.DataFrame(trades)
    if len(Tdf):
        x = Tdf[(Tdf.signal == "Spot-based nowcast") & (Tdf.threshold_x_cost == 1) & (Tdf.window == "All")].sort_values("t", ascending=False)
        for r in x.itertuples():
            L.append(f"Gap trade, {r.name} (buy when the spot-based nowcast is above futures by more than the ${r.cost_usd} round-trip cost, sell when below; hold to settlement): {r.trades} weekly entries in {r.months} months, hit {r.hit}%, "
                     f"${r.avg_usd:+,} per contract after costs (longs ${r.long_usd:+,}, shorts ${r.short_usd:+,}), month-clustered t {r.t}; 2021-23 ${r.avg_usd_2021_23:+,}, 2024-26 ${r.avg_usd_2024_26:+,}.")
    for r in sur:
        L.append(f"{r['name']}: on NDPSR release days futures move {r['reaction_slope']} x the change the print implies for the monthly average (1 = full reaction); after a big surprise the next 3 days drift {r['drift3_ticks']:+} ticks in its direction (${r['drift3_usd_net']:+,} net per contract, hit {r['drift3_hit']}%).")
    for k, a in arb.items():
        if not k.startswith("class"):
            continue
        L.append(f"Formula arbitrage {k.replace('class', 'Class ')} vs {a['legs']} futures: average gap ${a['mean_abs_gap']}/cwt, above 10 cents {a['share_gt_10c']}% of days, above 25 cents {a['share_gt_25c']}%; "
                 f"it closes to ${a['end_gap_mean_abs']} by expiry. " + ("Best: " + "; ".join(f"gap > ${t['threshold']:.2f}: {t['months']} months, hit {t['hit']}%, ${t['avg_usd']:+,} per Class contract after costs" for t in a["trades"][:3]) if a["trades"] else ""))
    out["learnings"] = L
    (ROOT / "data" / "dairy" / "derived" / "dairy_arb.json").write_text(json.dumps(out, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else str(o)).replace("NaN", "null"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
