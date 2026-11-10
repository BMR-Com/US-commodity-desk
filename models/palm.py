"""Palm oil section: Malaysian monthly balance (MPOB), world balance (USDA PSD), prices and spreads, CME positioning.

Inputs  data/palm/raw (pipelines/palm.py). Output data/palm/palm.json (assets/palm.js). If an input is missing its
block is left out; if the MPOB tables are missing nothing is written, so the page keeps the last good build.

Malaysia   monthly production, exports, imports, closing stocks from the MPOB yearly summary tables (history before
           the tables start from the long-form mirror); domestic use is the residual of the balance.
Projection next month's closing stocks = this month's stocks + production + imports - exports - domestic use, with
           production and exports moved by their usual month-on-month change for that calendar month (median and
           10-90% range of the last 10 years). Tested walk-forward against "stocks unchanged".
Prices     Bursa FCPO in ringgit and USD, CBOT soybean oil in USD/t, the soybean oil-palm oil spread, CME palm-gasoil
           spread (POGO), and a fit of the monthly palm price on soybean oil and Malaysian stocks vs their seasonal norm.
World      USDA PSD palm oil by country, with the revision since the previous stored vintage.
"""
import io, json
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "palm" / "raw"
OUT = ROOT / "data" / "palm" / "palm.json"
MONS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LB_PER_T = 2204.62


def num(x):
    try:
        v = float(str(x).replace(",", "").strip())
        return v if np.isfinite(v) else None
    except Exception:
        return None


def mpob():
    """Monthly series from the yearly tables. Layout: first data column = December of the prior year, then Jan..Dec.
    Rows are grouped under section headers (PRODUCTION, CLOSING STOCK, EXPORT, IMPORT, PRICE)."""
    want = {("PRODUCTION", "crude palm oil"): "prod", ("CLOSING STOCK", "palm oil"): "stocks", ("EXPORT", "palm oil"): "exports",
            ("IMPORT", "palm oil (cpo+ppo)"): "imports", ("IMPORT", "crude palm oil (cpo)"): "imports_cpo", ("PRICE", "ffb (rm)"): "ffb"}
    rows, flags = {}, {}
    for p in sorted((RAW / "mpob").glob("*.html")):
        y = int(p.stem)
        try:
            tabs = pd.read_html(io.StringIO(p.read_text(errors="replace")))
        except Exception:
            continue
        for t in tabs:
            t = t.astype(str); sec = None; hdr = None
            for _, r in t.iterrows():
                c = [str(v).strip() for v in r.tolist()]
                lab = c[0].lower()
                if any(str(v).strip().lower().startswith("jan") for v in c[1:4]) and hdr is None:
                    hdr = c; continue
                up = c[0].upper()
                if len(set(c)) == 1 or up.startswith(("PRODUCTION", "CLOSING STOCK", "EXPORT", "IMPORT", "PRICE")) and num(c[1]) is None:
                    for s in ("PRODUCTION", "CLOSING STOCK", "EXPORT", "IMPORT", "PRICE"):
                        if up.startswith(s):
                            sec = s
                    continue
                k = want.get((sec, lab))
                if not k or len(c) < 14:
                    continue
                for j in range(1, 14):
                    v = num(c[j])
                    if v is None:
                        continue
                    m = pd.Period(year=y - 1, month=12, freq="M") if j == 1 else pd.Period(year=y, month=j - 1, freq="M")
                    rows[(m, k)] = v                       # later files overwrite: a year's own table carries the revised figures
                    if hdr and j < len(hdr) and "(p)" in hdr[j].lower():
                        flags[m] = "p"
                    else:
                        flags.pop(m, None)
    if not rows:
        return None, {}
    df = pd.Series(rows).unstack()
    bf = RAW / "mpob_backfill.csv"
    if bf.exists():                                         # history before the yearly tables begin
        b = pd.read_csv(bf); b["m"] = pd.PeriodIndex(pd.to_datetime(b.month), freq="M")
        mp = {"cpo_production": "prod", "total_po_stock": "stocks", "po_export": "exports", "po_import": "imports"}
        b = b[b.indicator.isin(mp)].assign(k=lambda x: x.indicator.map(mp)).pivot_table(index="m", columns="k", values="value", aggfunc="last")
        df = df.combine_first(b)
    df = df.sort_index()
    if "imports" not in df:
        df["imports"] = np.nan
    df["imports"] = df["imports"].fillna(df.get("imports_cpo"))
    return df, flags


def balance(df):
    d = df.copy()
    d["open"] = d.stocks.shift(1)
    d["dom"] = d.open + d["prod"] + d.imports.fillna(0) - d.exports - d.stocks          # domestic disappearance (residual)
    d["use"] = d.exports + d.dom
    d["su"] = d.stocks / d.use.rolling(3).mean()                                        # months of use covered
    d["dstock"] = d.stocks - d.open
    return d


def mom_stats(s, month, upto, n=10):
    """Median and 10/90% of the month-on-month % change into calendar `month`, over the n years before `upto`."""
    ch = (s / s.shift(1) - 1)
    x = ch[(ch.index.month == month) & (ch.index < upto)].dropna().tail(n)
    if len(x) < 4:
        return None
    return {"med": float(x.median()), "lo": float(x.quantile(.1)), "hi": float(x.quantile(.9)), "n": int(len(x))}


def project(d, at):
    """Closing stocks for the month after `at`, from data through `at` only."""
    nxt = at + 1; r = d.loc[at]
    ps, es = mom_stats(d["prod"], nxt.month, nxt), mom_stats(d.exports, nxt.month, nxt)
    dom = d.dom[(d.index.month == nxt.month) & (d.index <= at)].dropna().tail(3)
    if ps is None or es is None or not len(dom) or pd.isna(r.stocks):
        return None
    dm = float(dom.mean()); imp = float(d.imports[d.index <= at].dropna().tail(3).mean() or 0)
    def end(pk, ek):
        return r.stocks + r["prod"] * (1 + ps[pk]) + imp - r.exports * (1 + es[ek]) - dm
    return {"month": str(nxt), "prod": r["prod"] * (1 + ps["med"]), "exports": r.exports * (1 + es["med"]), "imports": imp, "dom": dm,
            "base": end("med", "med"), "bull": end("lo", "hi"), "bear": end("hi", "lo"), "prod_mom": ps, "exp_mom": es}


def backtest(d, years=10):
    rows = []
    idx = [m for m in d.index if m.year >= d.index[-1].year - years]
    for at in idx[:-1]:
        nxt = at + 1
        if nxt not in d.index or pd.isna(d.stocks.get(nxt)):
            continue
        p = project(d, at)
        if p is None:
            continue
        act = d.stocks[nxt]
        rows.append({"m": str(nxt), "err": p["base"] / act - 1, "naive": d.stocks[at] / act - 1, "dir": np.sign(p["base"] - d.stocks[at]) == np.sign(act - d.stocks[at]),
                     "inband": min(p["bull"], p["bear"]) <= act <= max(p["bull"], p["bear"])})
    if len(rows) < 12:
        return None
    b = pd.DataFrame(rows)
    return {"n": len(b), "mae_pct": round(100 * b.err.abs().mean(), 1), "mae_naive_pct": round(100 * b.naive.abs().mean(), 1),
            "dir_hit": round(100 * b.dir.mean()), "in_band": round(100 * b.inband.mean()), "since": b.m.iloc[0]}


def seasonal_block(s, scale=1e6, d=2):
    s = s.dropna()
    return {"month": [str(m) for m in s.index], "vals": [round(float(v) / scale, d + 1) for v in s.values]}


def prices():
    p = RAW / "prices.csv"
    if not p.exists():
        return None
    px = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    px = px[px.index.dayofweek < 5]
    fx = px.USDMYR.ffill()
    px["FCPO_USD"] = px.FCPO / fx
    px["ZL_USD"] = px.ZL / 100 * LB_PER_T
    px["SOY_PALM"] = px.ZL_USD.ffill(limit=3) - px.FCPO_USD
    return px


def pctile(s, v):
    s = s.dropna()
    return round(float((s < v).mean() * 100)) if len(s) > 30 and v is not None and np.isfinite(v) else None


def price_block(px, d):
    out = {}
    last = lambda c: (px[c].dropna().index[-1].strftime("%Y-%m-%d"), float(px[c].dropna().iloc[-1])) if c in px and px[c].notna().any() else (None, None)
    f = px.FCPO.dropna()
    if len(f) < 300:
        return None
    dt, v = last("FCPO")
    # calendar look-back (last close on or before the date a week / month earlier), so exchange holidays do not stretch the window
    chg = lambda off: float(f.iloc[-1] / f[:f.index[-1] - off].iloc[-1] - 1) * 100 if len(f[:f.index[-1] - off]) else None
    out["fcpo"] = {"date": dt, "last": v, "usd": float(px.FCPO_USD.dropna().iloc[-1]), "chg_1w": chg(pd.Timedelta(days=7)), "chg_1m": chg(pd.DateOffset(months=1)), "chg_ytd": float(f.iloc[-1] / f[f.index.year < f.index[-1].year].iloc[-1] - 1) * 100,
                   "ma50": float(f.tail(50).mean()), "ma200": float(f.tail(200).mean()), "hi52": float(f.tail(252).max()), "lo52": float(f.tail(252).min()),
                   "rsi": rsi(f), "pct5y": pctile(f.tail(1260), v)}
    for k, lab in (("CPO", "cme"), ("POGO", "pogo"), ("ZL_USD", "soyoil_usd"), ("SOY_PALM", "soy_palm"), ("USDMYR", "usdmyr"), ("BRENT", "brent")):
        dt, v = last(k)
        if v is not None:
            s = px[k].dropna()
            out[lab] = {"date": dt, "last": v, "pct5y": pctile(s.tail(1260), v), "med5y": float(s.tail(1260).median()), "chg_1m": float(v - s.iloc[-22]) if len(s) > 22 else None}
    w = px[["FCPO", "FCPO_USD", "ZL_USD", "SOY_PALM", "POGO"]].resample("W-FRI").last().dropna(how="all").tail(260)
    out["weekly"] = {"date": [x.strftime("%Y-%m-%d") for x in w.index], **{c.lower(): [None if pd.isna(v) else round(float(v), 1) for v in w[c]] for c in w}}
    # fit: monthly palm (USD/t) on soybean oil (USD/t) and Malaysian stocks vs their seasonal norm
    m = px[["FCPO_USD", "ZL_USD"]].groupby(px.index.to_period("M")).mean()
    st = d.stocks.copy(); norm = st.groupby(st.index.month).transform(lambda x: x.rolling(5, min_periods=3).mean().shift(1))
    dev = (st / norm - 1).shift(1)                                      # stocks known at the start of the month (prior month-end, published ~10th)
    z = pd.concat([np.log(m.FCPO_USD), np.log(m.ZL_USD), dev], axis=1, keys=["p", "s", "dev"]).dropna()
    z = z[z.index >= z.index[-1] - 143]
    if len(z) >= 60:
        X = np.c_[np.ones(len(z)), z.s, z.dev]; b, *_ = np.linalg.lstsq(X, z.p, rcond=None)
        fit = X @ b; res = z.p - fit; r2 = 1 - float(res.var() / z.p.var())
        cur_dev = float(st.iloc[-1] / norm.iloc[-1] - 1) if np.isfinite(norm.iloc[-1]) else float(dev.dropna().iloc[-1])
        zl = float(px.ZL_USD.dropna().iloc[-1]); fair = float(np.exp(b[0] + b[1] * np.log(zl) + b[2] * cur_dev))
        spot = float(px.FCPO_USD.dropna().iloc[-1]); fxl = float(px.USDMYR.dropna().iloc[-1])
        out["fit"] = {"n": len(z), "r2": round(r2, 2), "b_soy": round(float(b[1]), 2), "b_stocks": round(float(b[2]), 2), "se_pct": round(100 * float(res.std()), 1),
                      "stocks_dev_pct": round(100 * cur_dev, 1), "fair_usd": round(fair), "fair_myr": round(fair * fxl), "spot_usd": round(spot), "gap_pct": round(100 * (spot / fair - 1), 1),
                      "since": str(z.index[0]), "hist": {"month": [str(i) for i in z.index], "actual": [round(float(np.exp(v))) for v in z.p], "fit": [round(float(np.exp(v))) for v in fit]}}
    return out


def rsi(s, n=14):
    dl = s.diff().dropna(); up = dl.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-dl.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return round(float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])), 0) if dn.iloc[-1] > 0 else 100.0


def world():
    p = RAW / "psd.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p); df["c"] = df.Commodity_Description.str.strip(); df["n"] = df.Country_Name.str.strip()
    A = {"Production": "prod", "Imports": "imports", "Exports": "exports", "Domestic Consumption": "use", "Industrial Dom. Cons.": "industrial", "Food Use Dom. Cons.": "food", "Ending Stocks": "end"}
    po = df[(df.c == "Oil, Palm") & df.Attribute_Description.isin(A)].copy(); po["a"] = po.Attribute_Description.map(A)
    y1 = int(po.Market_Year.max()); yrs = list(range(y1 - 5, y1 + 1))
    lab = lambda y: f"{y}/{str(y + 1)[2:]}"          # PSD Market_Year is the year the oilseed marketing year begins
    t = po.pivot_table(index=["n", "Market_Year"], columns="a", values="Value", aggfunc="sum")
    W = t.groupby("Market_Year").sum()
    regs = ["Indonesia", "Malaysia", "Thailand", "India", "China", "European Union", "Pakistan", "Bangladesh"]
    def rows(g):
        o = []
        for y in yrs:
            if y in g.index:
                r = g.loc[y]; use = r.get("use", np.nan)
                o.append({"my": lab(y), **{k: (round(float(r[k]) / 1000, 2) if k in r and pd.notna(r[k]) else None) for k in A.values()},
                          "su": round(float(r["end"] / use * 100), 1) if use else None})
        return o
    out = {"my": lab(y1), "unit": "million t", "regions": [{"name": "World", "rows": rows(W)}] + [{"name": n, "rows": rows(t.loc[n])} for n in regs if n in t.index.get_level_values(0)]}
    # all vegetable oils for context: world ending stocks / use of the five oils in the file
    vo = df[df.Attribute_Description.isin(["Ending Stocks", "Domestic Consumption"])].pivot_table(index="Market_Year", columns="Attribute_Description", values="Value", aggfunc="sum")
    out["vegoil_su"] = [{"my": lab(int(y)), "su": round(float(r["Ending Stocks"] / r["Domestic Consumption"] * 100), 1)} for y, r in vo.loc[yrs[0]:].iterrows()]
    vp = RAW / "psd_vintages.csv"
    if vp.exists():                                          # change vs the previous stored month, current marketing year
        v = pd.read_csv(vp); v["n"] = v.Country_Name.str.strip(); v = v[(v.Market_Year == y1) & v.Attribute_Description.isin(A)]
        vs = sorted(v.vintage.unique())
        if len(vs) >= 2:
            a_, b_ = v[v.vintage == vs[-1]], v[v.vintage == vs[-2]]
            pa = a_.pivot_table(index="n", columns="Attribute_Description", values="Value", aggfunc="sum"); pb = b_.pivot_table(index="n", columns="Attribute_Description", values="Value", aggfunc="sum")
            dlt = (pa - pb).round(0); ch = []
            for n in dlt.index:
                for at in dlt.columns:
                    x = dlt.loc[n, at]
                    if pd.notna(x) and abs(x) >= 50:
                        ch.append({"country": n, "attr": A[at], "chg": round(float(x) / 1000, 2)})
            out["revisions"] = {"from": vs[-2], "to": vs[-1], "rows": sorted(ch, key=lambda r: -abs(r["chg"]))[:14]}
    return out


def cot():
    p = RAW / "cot_fo.csv"
    if not p.exists():
        return None
    c = pd.read_csv(p); c["d"] = pd.to_datetime(c.report_date_as_yyyy_mm_dd.str[:10]); c = c.sort_values("d")
    g = lambda a: pd.to_numeric(c[a], errors="coerce")
    o = pd.DataFrame({"d": c.d, "oi": g("open_interest_all"), "mm": g("m_money_positions_long_all") - g("m_money_positions_short_all"),
                      "pm": g("prod_merc_positions_long") - g("prod_merc_positions_short"), "sw": g("swap_positions_long_all") - g("swap__positions_short_all"),
                      "oth": g("other_rept_positions_long") - g("other_rept_positions_short")}).set_index("d")
    o = o[o.oi > 0]; L = o.iloc[-1]
    return {"date": o.index[-1].strftime("%Y-%m-%d"), "oi": int(L.oi), "mm": int(L.mm), "pm": int(L.pm), "sw": int(L.sw), "oth": int(L.oth),
            "mm_pct": pctile(o.mm.tail(156), L.mm), "oi_pct": pctile(o.oi.tail(156), L.oi), "mm_pct_oi": round(100 * float(L.mm / L.oi), 1),
            "hist": {"date": [x.strftime("%Y-%m-%d") for x in o.index], "oi": [int(v) for v in o.oi.fillna(0)], "mm": [int(v) for v in o.mm.fillna(0)], "pm": [int(v) for v in o.pm.fillna(0)]}}


def f0(v):
    return f"{v:,.0f}"


def mt(v, d=2):
    return f"{v / 1e6:.{d}f}"


def main():
    df, flags = mpob()
    if df is None or df.stocks.dropna().empty:
        print("palm: no MPOB tables; nothing written"); return
    d = balance(df)
    d = d[d.stocks.notna()]
    at = d[d["prod"].notna() & d.exports.notna()].index[-1]; L = d.loc[at]; P = d.loc[at - 1]; Y = d.loc[at - 12] if at - 12 in d.index else None
    mon = MONS[at.month - 1]
    same = d[(d.index.month == at.month) & (d.index < at)]
    avg5 = lambda c: float(same[c].dropna().tail(5).mean())
    rec = d.stocks[d.index < at].max(); rec_m = d.stocks[d.index < at].idxmax()
    proj = project(d, at); bt = backtest(d)
    px = prices(); PB = price_block(px, d) if px is not None else None
    W = world(); C = cot()

    # ── score and brief ──
    sc = []
    sdev = L.stocks / avg5("stocks") - 1
    sc.append(("Malaysian stocks vs 5-yr norm", -1 if sdev > .10 else 1 if sdev < -.10 else 0, f"{sdev:+.0%}"))
    if proj:
        dn = proj["base"] / L.stocks - 1
        sc.append(("Projected stock change next month", -1 if dn > .02 else 1 if dn < -.02 else 0, f"{dn:+.1%}"))
    if PB:
        sp = PB.get("soy_palm"); pg = PB.get("pogo"); f = PB["fcpo"]
        if sp:
            sc.append(("Palm discount to soybean oil", 1 if sp["pct5y"] is not None and sp["pct5y"] >= 70 else -1 if sp["pct5y"] is not None and sp["pct5y"] <= 30 else 0, f"${sp['last']:,.0f}/t, {sp['pct5y']}th pct of 5 yrs"))
        if pg:
            sc.append(("Palm vs gasoil (biodiesel pull)", 1 if pg["last"] < -50 else -1 if pg["last"] > 100 else 0, f"${pg['last']:,.0f}/t"))
        sc.append(("Trend", 1 if f["last"] > f["ma50"] > f["ma200"] else -1 if f["last"] < f["ma50"] and f["last"] < f["ma200"] else 0, f"{f['last']:,.0f} vs 50-day {f['ma50']:,.0f}, 200-day {f['ma200']:,.0f}"))
        if PB.get("fit"):
            g = PB["fit"]["gap_pct"]; se = PB["fit"]["se_pct"]
            sc.append(("Price vs soybean-oil-and-stocks fit", 1 if g < -se else -1 if g > se else 0, f"{g:+.0f}% vs fit (typical miss ±{se:.0f}%)"))
    score = sum(s for _, s, _ in sc)
    view = "bullish" if score >= 3 else "mildly bullish" if score >= 1 else "bearish" if score <= -3 else "mildly bearish" if score <= -1 else "neutral"

    B = []
    t = (f"MPOB {mon} {at.year}{' (preliminary)' if flags.get(at) == 'p' else ''}: closing stocks **{mt(L.stocks)} million t** ({L.stocks / P.stocks - 1:+.1%} m/m"
         + (f", {L.stocks / Y.stocks - 1:+.0%} y/y" if Y is not None else "") + f"), {sdev:+.0%} vs the 5-year average for {mon}. "
         f"CPO production {mt(L['prod'])} ({L['prod'] / P['prod'] - 1:+.1%} m/m), exports {mt(L.exports)} ({L.exports / P.exports - 1:+.1%}), imports {f0(L.imports)} t, "
         f"domestic use (residual) {mt(L.dom)}.")
    if L.stocks > rec:
        t += f" Stocks are the highest in the data (previous high {mt(rec)} in {MONS[rec_m.month - 1]} {rec_m.year})."
    B.append({"h": "Malaysia", "t": t})
    if proj:
        nm = MONS[(at + 1).month - 1]
        t = (f"{nm} closing stocks about **{mt(proj['base'])} million t** ({proj['base'] / L.stocks - 1:+.1%}), range {mt(min(proj['bull'], proj['bear']))}–{mt(max(proj['bull'], proj['bear']))}. "
             f"Production usually moves {proj['prod_mom']['med']:+.0%} into {nm} (10–90%: {proj['prod_mom']['lo']:+.0%} to {proj['prod_mom']['hi']:+.0%}) and exports {proj['exp_mom']['med']:+.0%} "
             f"({proj['exp_mom']['lo']:+.0%} to {proj['exp_mom']['hi']:+.0%}).")
        if bt:
            t += (f" Tested since {bt['since'][:4]}: it called the direction of the stock change {bt['dir_hit']}% of the time, but on the level it missed by {bt['mae_pct']}% on average, "
                  f"no better than assuming stocks unchanged ({bt['mae_naive_pct']}%). Treat it as a direction guide. It uses seasonal norms only; cargo-surveyor export counts during the month are the better guide to exports.")
        B.append({"h": "Next month", "t": t})
    if PB:
        f = PB["fcpo"]; t = (f"Bursa FCPO front month RM{f['last']:,.0f} (US${f['usd']:,.0f}/t) on {f['date']}: {f['chg_1w']:+.1f}% on the week, {f['chg_1m']:+.1f}% on the month, {f['chg_ytd']:+.1f}% year to date; "
                             f"RSI {f['rsi']:.0f}; 52-week range {f['lo52']:,.0f}–{f['hi52']:,.0f}.")
        if PB.get("soy_palm"):
            s = PB["soy_palm"]; t += f" Palm trades US${s['last']:,.0f}/t below CBOT soybean oil (5-year median {s['med5y']:,.0f}; {s['pct5y']}th percentile) — a wide discount pulls price-sensitive buyers such as India toward palm."
        if PB.get("pogo"):
            g = PB["pogo"]; t += f" Palm minus gasoil (CME POGO) US${g['last']:,.0f}/t: {'palm is cheaper than gasoil, so discretionary biodiesel blending pays' if g['last'] < 0 else 'palm is dearer than gasoil, so blending needs a subsidy'}."
        B.append({"h": "Price", "t": t})
        if PB.get("fit"):
            x = PB["fit"]
            B.append({"h": "Price vs fundamentals", "t": f"A fit of the monthly palm price on soybean oil and Malaysian stocks vs their seasonal norm ({x['since']} on, R² {x['r2']}) puts palm at about "
                      f"**US${x['fair_usd']:,}/t (RM{x['fair_myr']:,})** with stocks {x['stocks_dev_pct']:+.0f}% vs norm; the market is {x['gap_pct']:+.0f}% from that (typical miss ±{x['se_pct']:.0f}%). "
                      f"A 10% rise in stocks vs norm has gone with a {abs(x['b_stocks']) * 10:.1f}% {'lower' if x['b_stocks'] < 0 else 'higher'} price at a given soybean oil price. Context, not a tested trading signal."})
    if W:
        w = W["regions"][0]["rows"]
        if len(w) >= 2:
            a_, b_ = w[-1], w[-2]
            t = (f"USDA {a_['my']}: world production {a_['prod']:.1f} million t ({a_['prod'] - b_['prod']:+.1f} y/y), use {a_['use']:.1f} ({a_['use'] - b_['use']:+.1f}), "
                 f"ending stocks {a_['end']:.1f} ({a_['end'] - b_['end']:+.1f}); stocks/use {a_['su']:.1f}% vs {b_['su']:.1f}%.")
            for n in ("Indonesia", "India"):
                r = next((x["rows"] for x in W["regions"] if x["name"] == n), None)
                if r and len(r) >= 2:
                    t += (f" Indonesia: production {r[-1]['prod']:.1f} ({r[-1]['prod'] - r[-2]['prod']:+.1f}), exports {r[-1]['exports']:.1f} ({r[-1]['exports'] - r[-2]['exports']:+.1f}), industrial use (mostly biodiesel) {r[-1]['industrial']:.1f} ({r[-1]['industrial'] - r[-2]['industrial']:+.1f})."
                          if n == "Indonesia" else f" India imports {r[-1]['imports']:.1f} ({r[-1]['imports'] - r[-2]['imports']:+.1f}).")
            if W.get("revisions") and W["revisions"]["rows"]:
                t += " Revisions since the previous month's data: " + "; ".join(f"{x['country']} {x['attr']} {x['chg']:+.2f}" for x in W["revisions"]["rows"][:5]) + "."
            B.append({"h": "World balance", "t": t})
    if C:
        B.append({"h": "CME positioning", "t": f"CME USD Malaysian Crude Palm Oil, {C['date']}: open interest {C['oi']:,}; producers/merchants net {C['pm']:+,}, swap dealers {C['sw']:+,}, managed money {C['mm']:+,} "
                  f"({C['mm_pct_oi']:+.1f}% of open interest). The contract is dominated by commercial hedgers, so fund positioning here says little; the liquid market is Bursa FCPO."})
    B.append({"h": "Outlook", "t": f"**{view.capitalize()}** (score {score:+d} of ±{len(sc)}). " + "; ".join(f"{n}: {txt} ({'supportive' if s > 0 else 'weighing' if s < 0 else 'neutral'})" for n, s, txt in sc) + ". Rule-based read; research use only."})

    tail = d.tail(14)
    table = [{"m": str(m), "flag": flags.get(m), **{k: (None if pd.isna(r[k]) else round(float(r[k]))) for k in ("open", "prod", "imports", "exports", "dom", "stocks")},
              "su": None if pd.isna(r.su) else round(float(r.su), 2)} for m, r in tail.iterrows()]
    hist = d[d.index >= pd.Period(year=at.year - 11, month=1, freq="M")]
    rel = at + 2; nx = date(rel.year, rel.month, 10)          # data for month m come out around the 10th of m+1
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": str(at), "asof_label": f"{mon} {at.year}", "prelim": flags.get(at) == "p",
           "view": view, "score": score, "factors": [{"name": n, "s": s, "txt": txt} for n, s, txt in sc], "brief": B,
           "kpi": {"stocks": float(L.stocks), "stocks_mom": float(L.stocks / P.stocks - 1) * 100, "stocks_vs5": sdev * 100, "prod": float(L["prod"]), "prod_mom": float(L["prod"] / P["prod"] - 1) * 100,
                   "exports": float(L.exports), "exports_mom": float(L.exports / P.exports - 1) * 100, "su": None if pd.isna(L.su) else float(L.su),
                   "su_pct": pctile(d.su.tail(120), L.su)},
           "table": table, "projection": proj, "backtest": bt,
           "series": {"stocks": seasonal_block(hist.stocks), "prod": seasonal_block(hist["prod"]), "exports": seasonal_block(hist.exports), "dom": seasonal_block(hist.dom),
                      "su": seasonal_block(hist.su, 1, 2)},
           "prices": PB, "world": W, "cot": C,
           "calendar": {"next_mpob": nx.isoformat(), "note": "MPOB publishes the prior month's supply and demand around the 10th (midday Kuala Lumpur). Cargo surveyors (ITS, AmSpec) publish Malaysian export counts for days 1–10, 1–15, 1–20, 1–25 and the full month."},
           "sources": {"mpob": "https://bepi.mpob.gov.my/", "psd": "https://apps.fas.usda.gov/psdonline/", "cftc": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"}}
    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [clean(v) for v in o]
        if isinstance(o, (np.floating, float)):
            return None if not np.isfinite(o) else round(float(o), 4)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        return o
    OUT.write_text(json.dumps(clean(out), separators=(",", ":"), allow_nan=False))
    print("palm:", out["asof_label"], "stocks", mt(L.stocks), "view", view, score, "| projection", proj and mt(proj["base"]), "| backtest", bt)
    for b in B:
        print(f"[{b['h']}] {b['t']}")


if __name__ == "__main__":
    main()
