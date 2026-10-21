#!/usr/bin/env python3
"""Research signals per market: the quant literature in Ma's research library, applied to the desk's futures.

Inputs: data/contracts/<SYM>.csv (daily close per contract), data/vol/vol.json (specs), data/options/<SYM>.json
and data/cme/options/<date>/<SYM>.csv.gz (CME option settlements with IV), data/cot_desk/<SYM>.json (CFTC),
data/grains/derived/wasde.json and data/energy/summary.json (inventories). Writes data/research/research.json.

What is computed, and where it comes from
- Excess-return series (Gorton-Rouwenhorst 2004): hold the nearest contract that does not expire or enter
  delivery in the holding month; daily returns are within-contract, so there are no roll gaps.
- Time-series momentum (Moskowitz-Ooi-Pedersen 2012): sign of the 12-month excess return, scaled to 40% annual
  vol with an EWMA variance (delta = 60/61, 261 days a year). Kim-Tse-Wald 2016: much of the gain is the vol
  scaling, so a vol-scaled long-only benchmark is shown next to it. 12-1 variant (Goyal-Wahal 2015).
- Trend quality: variance-ratio "signature" sigma^2(tau)/(tau sigma^2(1)) (Dao-Bouchaud 2016: trend P&L is long-
  minus short-horizon variance; ratio > 1 means trends persist) and information discreteness (Da-Gurun-Warachka
  2014: smooth trends persist longer).
- Carry / basis (Fama-French 1987, Gorton-Hayashi-Rouwenhorst 2007, Erb-Harvey 2006): annualized slope between
  the held and next contract, (F1-F2)/F1 * 365/days; for storable crops compared with the same calendar month in
  past years, since seasonal carry is structural; for livestock and dairy the curve is the market's forecast of
  the cash path, not a storage signal.
- Cross-section (GHR 2007 Tables 6-7): this market's rank on 12-month momentum and seasonal-adjusted carry among
  the desk's markets; monthly high-minus-low tercile backtest.
- Inventory state (GHR 2007): stocks/use vs prior years (WASDE) or storage vs the 5-year average (EIA).
- Options: variance risk premium IV^2 - RV^2 (Constantinides et al. 2010, Chan 2017), term-structure slope
  (Johnson 2017), risk-neutral density from settlements (Breeden-Litzenberger 1978, smoothed smile as in
  Jackwerth-Rubinstein 1996 / Gatheral 2006) with tail probabilities vs a lognormal at ATM vol.
- Positioning: CFTC managed money vs the trend sign; GHR find COT hedging pressure does not predict premia, so it
  is shown as crowding risk, not as a signal.
- Risk: momentum crash / rebound flag (Daniel-Moskowitz 2016), sizing at a vol target and inverse-vol weights
  (risk parity), a half-Kelly upper bound from a haircut Sharpe (MacLean-Thorp-Ziemba 2010), and a square-root
  impact estimate (Almgren 2008; Chan 2017).
- Backtest hygiene (Pardo 2008, Chan 2017): monthly, no look-ahead (signals use data to the prior month end),
  first-half vs second-half Sharpe, hit rate, max drawdown.
"""
import gzip, json, math
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
MON = "FGHJKMNQUVXZ"
TARGET = 0.40          # MOP per-contract annual vol target
DELTA = 60 / 61        # EWMA centre of mass 60 days
AF = 261
# months ahead the held contract must be: physical delivery in the month before (grains, cotton) or futures
# expiring the month before the contract month (NYMEX energy) -> 2; cash-settled / end-of-month expiry -> 1
AHEAD = {s: 2 for s in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE", "CT", "NG", "CL", "HO", "RB")}
STORABLE = {"ZC", "ZS", "ZM", "ZL", "ZW", "KE", "CT", "NG", "CL", "HO", "RB", "CSC", "CB", "GNF", "DY"}
WASDE = {"ZC": "corn", "ZS": "soybeans", "ZM": "meal", "ZL": "oil", "ZW": "wheat", "KE": "wheat"}
EIA = {"NG": "storL48", "CL": "crude", "HO": "dist", "RB": "gaso"}


def J(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def cmonth(code):
    """ZCZ2026 -> (2026, 12)."""
    return int(code[-4:]), MON.index(code[-5]) + 1


def held_series(df, ahead):
    """Daily excess returns of the GR roll, plus the held and next contract per date."""
    df = df.dropna(subset=["close"])
    df = df[df.close > 0]
    px = df.pivot_table(index="date", columns="contract", values="close", aggfunc="last").sort_index()
    px.index = pd.to_datetime(px.index)
    codes = sorted(px.columns, key=cmonth)
    key = {c: cmonth(c)[0] * 12 + cmonth(c)[1] for c in codes}
    rows = []
    prev_c = None
    for d, row in px.iterrows():
        m = d.year * 12 + d.month
        live = [c for c in codes if key[c] >= m + ahead and not np.isnan(row[c])]
        if not live:
            prev_c = None
            continue
        c = live[0]
        nxt = live[1] if len(live) > 1 else None
        r = np.nan
        # the return of day d on the contract held in d's month (switch on the first day of a month: previous close
        # of the new contract), so no roll gap enters
        rows.append((d, c, nxt, row[c], row[nxt] if nxt else np.nan))
        prev_c = c
    h = pd.DataFrame(rows, columns=["date", "c", "n", "F1", "F2"]).set_index("date")
    # within-contract daily return: needs yesterday's close of today's held contract
    ret = []
    idx = list(px.index)
    pos = {d: i for i, d in enumerate(idx)}
    for d, r in h.iterrows():
        i = pos[d]
        if i == 0:
            ret.append(np.nan); continue
        y = px.iloc[i - 1][r.c]
        ret.append(r.F1 / y - 1 if y and not np.isnan(y) else np.nan)
    h["r"] = ret
    h["days"] = [((cmonth(n)[0] - cmonth(c)[0]) * 12 + cmonth(n)[1] - cmonth(c)[1]) * 30.44 if isinstance(n, str) else np.nan
                 for c, n in zip(h.c, h.n)]
    h["carry"] = (h.F1 - h.F2) / h.F1 * 365 / h.days
    return h


def ewma_vol(r):
    r = r.fillna(0)
    m = r.ewm(alpha=1 - DELTA, adjust=False).mean()
    v = ((r - m.shift(1).fillna(0)) ** 2).ewm(alpha=1 - DELTA, adjust=False).mean()
    return np.sqrt(v * AF)


def stats(x):
    x = pd.Series(x).dropna()
    if len(x) < 24:
        return None
    eq = x.cumsum()
    dd = (eq - eq.cummax()).min()
    sr = x.mean() / x.std() * math.sqrt(12) if x.std() > 0 else None
    half = len(x) // 2
    s1 = x.iloc[:half]; s2 = x.iloc[half:]
    sh = lambda s: round(float(s.mean() / s.std() * math.sqrt(12)), 2) if len(s) > 12 and s.std() > 0 else None
    return {"n": int(len(x)), "ann_ret": round(float(x.mean() * 12 * 100), 1), "ann_vol": round(float(x.std() * math.sqrt(12) * 100), 1),
            "sharpe": None if sr is None else round(float(sr), 2), "hit": round(float((x > 0).mean() * 100)), "max_dd": round(float(dd * 100), 1),
            "sharpe_1st_half": sh(s1), "sharpe_2nd_half": sh(s2), "since": str(x.index[0].date())}


def variance_ratio(r, taus=(1, 5, 10, 21, 42, 63, 126, 189, 250)):
    lr = np.log1p(r.dropna())
    lr = lr[lr.index >= lr.index[-1] - pd.Timedelta(days=3653)]
    v1 = lr.var()
    out = []
    for t in taus:
        s = lr.rolling(t).sum().dropna()
        if len(s) > 3 * t:
            out.append([t, round(float(s.var() / (t * v1)), 3)])
    return out


def bs_call(F, K, T, s, df=1.0):
    from math import erf, sqrt, log
    if s <= 0 or T <= 0:
        return df * max(F - K, 0)
    d1 = (log(F / K) + 0.5 * s * s * T) / (s * sqrt(T))
    d2 = d1 - s * sqrt(T)
    N = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    return df * (F * N(d1) - K * N(d2))


def density(sym, rate):
    """Breeden-Litzenberger on a smoothed smile for the front expiry with enough strikes (>= 10 days to go)."""
    days = sorted((D / "cme" / "options").glob("2*"))
    f = next((d / f"{sym}.csv.gz" for d in reversed(days) if (d / f"{sym}.csv.gz").exists()), None)
    if f is None:
        return None
    o = pd.read_csv(f)
    o = o[(o.iv > 0.5) & (o.iv < 300) & (o.dte >= 10)]
    for con, g in sorted(o.groupby("contract"), key=lambda x: x[1].dte.iloc[0]):
        F, T, dte = float(g.F.iloc[0]), float(g["T"].iloc[0]), int(g.dte.iloc[0])
        otm = g[((g.cp == "C") & (g.strike >= F)) | ((g.cp == "P") & (g.strike <= F))]
        tick = float(g.settle[g.settle > 0].min()) if (g.settle > 0).any() else 0
        otm = otm[(otm.settle > 1.5 * tick) & (otm.delta.abs() > 0.03)]   # minimum-tick settles carry no smile information
        if len(otm) < 8 or otm.strike.min() > F * 0.97 or otm.strike.max() < F * 1.03:
            continue
        k = np.log(otm.strike.values / F)
        iv = otm.iv.values / 100
        w = np.sqrt(np.maximum(otm.oi.values, 1))
        cf = np.polyfit(k, iv, 2, w=w)   # quadratic smile in log-moneyness
        lo, hi = k.min(), k.max()
        sm = lambda x: float(np.polyval(cf, np.clip(x, lo, hi)))   # flat wings outside the quoted range
        atm = sm(0.0)
        sd = atm * math.sqrt(T)
        K = np.linspace(F * math.exp(-5 * sd), F * math.exp(5 * sd), 401)   # uniform strike grid for the second difference
        grid = np.log(K / F)
        disc = math.exp(-rate * T)
        C = np.array([bs_call(F, kk, T, max(sm(x), 0.01), disc) for kk, x in zip(K, grid)])
        q = np.zeros_like(C)
        q[1:-1] = (C[:-2] - 2 * C[1:-1] + C[2:]) / (K[1] - K[0]) ** 2 / disc
        q = np.maximum(q, 0)
        dK = np.gradient(K)
        mass = float((q * dK).sum())
        if mass <= 0.9:
            continue
        q /= mass
        if abs(float((K * q * dK).sum()) / F - 1) > 0.01:   # the density must price the future
            continue
        cdf = np.cumsum(q * dK)
        def ln_cdf(x):   # lognormal at ATM vol, prob F_T < F e^x
            from math import erf, sqrt
            z = (x + 0.5 * sd * sd) / sd
            return 0.5 * (1 + erf(z / sqrt(2)))
        tails = []
        for kk in (1, 2, 3):
            dn = float(np.interp(-kk * sd, grid, cdf)); up = float(1 - np.interp(kk * sd, grid, cdf))
            ldn = ln_cdf(-kk * sd); lup = 1 - ln_cdf(kk * sd)
            tails.append({"k": kk, "move_pct": round(100 * (math.exp(kk * sd) - 1), 1), "down": round(dn * 100, 2), "up": round(up * 100, 2),
                          "down_ratio": round(dn / ldn, 2) if ldn > 1e-6 else None, "up_ratio": round(up / lup, 2) if lup > 1e-6 else None})
        qs = {p: round(float(F * math.exp(np.interp(p / 100, cdf, grid))), 4) for p in (5, 25, 50, 75, 95)}
        step = 5
        return {"contract": con, "label": g.label.iloc[0], "date": str(g.date.iloc[0]), "F": F, "dte": dte, "atm_iv": round(atm * 100, 1),
                "mean": round(float((K * q * dK).sum()), 4), "quantiles": qs, "tails": tails, "fit_points": int(len(otm)),
                "curve": [[round(float(K[i]), 4), round(float(q[i] * F), 4), round(float(np.exp(-((grid[i] + 0.5 * sd * sd) ** 2) / (2 * sd * sd)) / (sd * math.sqrt(2 * math.pi)) / K[i] * F), 4)]
                          for i in range(0, len(K), step)]}
    return None


def nth(n):
    n = int(round(n))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def inventory(sym):
    if sym in WASDE:
        w = (J(D / "grains/derived/wasde.json") or {}).get("commodities", {}).get(WASDE[sym], {}).get("us", {})
        rows = []
        for my, v in sorted(w.items()):
            it = v.get("items", {})
            e, u = (it.get("end_stocks") or {}).get("value"), (it.get("use") or {}).get("value")
            if e and u:
                rows.append([my, round(100 * e / u, 1)])
        if len(rows) >= 2:
            cur, prev = rows[-1][1], rows[-2][1]
            state = "tight" if cur < prev * 0.9 else "ample" if cur > prev * 1.1 else "similar to last year"
            return {"measure": "US stocks/use (WASDE)", "rows": rows, "state": state,
                    "read": f"US stocks/use {cur:.1f}% for {rows[-1][0]} vs {prev:.1f}% for {rows[-2][0]} ({state})."}
    if sym in EIA:
        i = ((J(D / "energy/summary.json") or {}).get("inventories") or {}).get(EIA[sym])
        if i and i.get("vs_avg5_pct") is not None:
            p = i["vs_avg5_pct"]
            state = "tight" if p < -5 else "ample" if p > 5 else "near normal"
            return {"measure": f"{i['name']} vs 5-yr avg (EIA)", "state": state, "vs_avg5_pct": round(p, 1),
                    "read": f"{i['name']} {p:+.1f}% vs the 5-year average for the week to {i['date']} ({state})."}
    return None


def main():
    V = J(D / "vol/vol.json") or {}
    spec = V.get("markets", {})
    rate = (V.get("rate") or 4.0) / 100
    H, out = {}, {}
    for sym in spec:
        p = D / "contracts" / f"{sym}.csv"
        if not p.exists():
            continue
        h = held_series(pd.read_csv(p), AHEAD.get(sym, 1))
        h = h[h.index >= pd.Timestamp("2006-01-01")]
        if h.r.notna().sum() < 300:
            continue
        h["sig"] = ewma_vol(h.r)
        H[sym] = h
    # monthly panel
    M = {}
    for sym, h in H.items():
        r = h.r.fillna(0)
        mr = (1 + r).resample("ME").prod() - 1
        idx = (1 + r).cumprod()
        me = idx.resample("ME").last()
        M[sym] = pd.DataFrame({"r": mr, "r12": me / me.shift(12) - 1, "r12_1": me.shift(1) / me.shift(12) - 1,
                               "sig": h.sig.resample("ME").last(), "carry": h.carry.resample("ME").last()})
    # seasonal-adjusted carry: minus the median of the same calendar month in prior years (expanding, no look-ahead)
    for sym, m in M.items():
        adj = []
        for d, c in m.carry.items():
            past = m.carry[(m.index.month == d.month) & (m.index < d)]
            adj.append(c - past.median() if len(past) >= 3 and not np.isnan(c) else np.nan)
        m["carry_adj"] = adj if sym in STORABLE else m.carry   # non-storables: the raw slope is the forecast
    # cross-sectional ranks and the high-minus-low tercile backtest
    mom = pd.DataFrame({s: m.r12 for s, m in M.items()})
    car = pd.DataFrame({s: m.carry_adj for s, m in M.items()})
    ret = pd.DataFrame({s: m.r for s, m in M.items()})
    sig = pd.DataFrame({s: m.sig for s, m in M.items()})
    def xs_bt(score):
        pr = []
        for i in range(1, len(score.index)):
            d0, d1 = score.index[i - 1], score.index[i]
            s = score.loc[d0].dropna()
            if len(s) < 6:
                continue
            n = len(s) // 3
            hi, lo = s.nlargest(n).index, s.nsmallest(n).index
            w = (TARGET / sig.loc[d0]).clip(upper=5)
            pr.append((d1, float((w[hi] * ret.loc[d1, hi]).mean() - (w[lo] * ret.loc[d1, lo]).mean()) / 2))
        return pd.Series(dict(pr))
    xs = {"momentum": stats(xs_bt(mom)), "carry": stats(xs_bt(car))}
    last_m = mom.index[-1]
    rank_m = mom.loc[last_m].rank(ascending=False)
    rank_c = car.loc[last_m].rank(ascending=False)
    n_rank = int(mom.loc[last_m].notna().sum())
    # inverse-vol (diagonal risk parity) weights today
    sig_now = {s: float(h.sig.iloc[-1]) for s, h in H.items()}
    inv = {s: 1 / v for s, v in sig_now.items() if v > 0}
    tot = sum(inv.values())
    for sym, h in H.items():
        m = M[sym]
        sp = spec[sym]
        name, mult = sp["name"], sp["mult"]
        r = h.r
        sg = float(h.sig.iloc[-1])
        lev = TARGET / sg if sg > 0 else None
        idx = (1 + r.fillna(0)).cumprod()
        def back(n):
            return float(idx.iloc[-1] / idx.iloc[-1 - n] - 1) if len(idx) > n else None
        r12, r6, r3, r1 = back(252), back(126), back(63), back(21)
        last = r.dropna().iloc[-252:]
        id_ = float(np.sign(r12) * ((last < 0).mean() - (last > 0).mean())) if r12 is not None else None
        sign = 1 if (r12 or 0) > 0 else -1
        # backtests (monthly, positions from the prior month end)
        w = (TARGET / m.sig.shift(1)).clip(upper=5)
        ts = np.sign(m.r12.shift(1)) * w * m.r
        ts121 = np.sign(m.r12_1.shift(1)) * w * m.r
        lo = w * m.r
        ca = np.sign(pd.Series(m.carry_adj, index=m.index).shift(1)) * w * m.r
        bt = {"tsmom_12m": stats(ts), "tsmom_12_1": stats(ts121), "long_only_scaled": stats(lo), "carry": stats(ca)}
        c_tc = pd.concat([ts, ca], axis=1).dropna()
        bt["corr_tsmom_carry"] = round(float(c_tc.corr().iloc[0, 1]), 2) if len(c_tc) > 24 else None
        vr = variance_ratio(r)
        vrd = dict(vr)
        # vol percentile of EWMA sigma over 5y
        s5 = h.sig[h.sig.index >= h.sig.index[-1] - pd.Timedelta(days=1826)]
        sig_pct = round(float((s5 < sg).mean() * 100))
        # options
        o = J(D / "options" / f"{sym}.json")
        opt = None
        if o and o.get("expiries"):
            ex = [e for e in o["expiries"] if e.get("atm")]
            fr = next((e for e in ex if e["contract"] == o.get("front")), ex[0] if ex else None)
            if fr:
                rv = fr.get("rv20") or sg * 100
                back_e = next((e for e in ex if e["dte"] >= fr["dte"] + 50), None)
                opt = {"label": fr["label"], "dte": fr["dte"], "atm": fr["atm"], "rv20": rv, "ewma_rv": round(sg * 100, 1),
                       "var_prem": round((fr["atm"] ** 2 - rv ** 2) / 100, 1), "vol_prem": round(fr["atm"] - rv, 1), "rr25": fr.get("rr25"),
                       "iv_pct1y": o.get("iv_pct1y"), "slope": round(back_e["atm"] - fr["atm"], 1) if back_e else None,
                       "slope_pair": f"{fr['label']} -> {back_e['label']}" if back_e else None}
        dens = density(sym, rate)
        # COT positioning
        cot = J(D / "cot_desk" / f"{sym}.json")
        pos = None
        if cot and cot.get("cats", {}).get("mm"):
            mm = cot["cats"]["mm"]
            aligned = (mm["np_oi"] > 0) == (sign > 0)
            pct = mm.get("pct", {}).get("y5")
            crowd = pct is not None and ((sign > 0 and pct >= 85) or (sign < 0 and pct <= 15))
            pos = {"date": cot.get("date"), "mm_np_oi": mm["np_oi"], "mm_pct5y": pct, "aligned": bool(aligned), "crowded": bool(crowd)}
        inv_ = inventory(sym)
        # flags
        flags = []
        if sign < 0 and sig_pct >= 80 and (r12 or 0) < -0.2:
            flags.append("Rebound risk: trend is short a beaten-down market in high vol, the setting where momentum shorts crash (Daniel-Moskowitz).")
        if vrd.get(63) is not None and vrd[63] < 0.9:
            flags.append(f"Choppy: 3-month variance ratio {vrd[63]:.2f} < 1 (mean reversion), trend signals whipsaw here (Dao-Bouchaud).")
        if id_ is not None and id_ > 0:
            flags.append("Jumpy trend: most of the move came on a few days (high information discreteness), which tends to fade sooner (Da-Gurun-Warachka).")
        if pos and pos["crowded"]:
            flags.append(f"Crowded: managed money at the {nth(pos['mm_pct5y'])} 5-year percentile of its net position, {'long' if sign > 0 else 'short'} with the trend; COT is a crowding gauge, not a return signal (GHR).")
        if opt and opt.get("slope") is not None and opt["slope"] < -2:
            flags.append(f"Inverted IV curve ({opt['slope_pair']} {opt['slope']:+.1f} pts): near-dated risk priced high; for SPX an inverted slope preceded positive returns to long variance (Johnson).")
        if dens and dens["tails"][1].get("down_ratio") and dens["tails"][1]["down_ratio"] > 2:
            flags.append(f"Fat left tail: options price a {dens['tails'][1]['move_pct']:.0f}% drop {dens['tails'][1]['down_ratio']:.1f}x as likely as a lognormal at ATM vol.")
        if dens and dens["tails"][1].get("up_ratio") and dens["tails"][1]["up_ratio"] > 2:
            flags.append(f"Fat right tail: options price a {dens['tails'][1]['move_pct']:.0f}% rally {dens['tails'][1]['up_ratio']:.1f}x as likely as a lognormal at ATM vol.")
        # sizing and costs
        price = float(h.F1.iloc[-1])
        notional = price * mult
        n10 = 0.10 * 1e6 / (sg * notional) if sg > 0 else None
        vol_df = pd.read_csv(D / "contracts" / f"{sym}.csv", usecols=["date", "volume"])
        adv = float(vol_df.groupby("date").volume.sum().iloc[-20:].mean())
        cost_1pct = 0.75 * sg / math.sqrt(AF) * math.sqrt(0.01) * 1e4
        sr_ts = (bt["tsmom_12m"] or {}).get("sharpe")
        kelly = round(0.5 * (0.5 * sr_ts) / TARGET, 2) if sr_ts and sr_ts > 0 else None
        car_now = float(h.carry.dropna().iloc[-1]) if h.carry.notna().any() else None
        car_adj = m.carry_adj.dropna()
        car_adj_now = float(car_adj.iloc[-1]) if len(car_adj) else None
        cm = h.carry[h.carry.index.month == h.index[-1].month].dropna()
        cm_hist = cm[cm.index.year < h.index[-1].year]
        car_pct = round(float((cm_hist < car_now).mean() * 100)) if car_now is not None and len(cm_hist) >= 3 else None
        # reads
        read = []
        read.append(f"Trend: {r12 * 100:+.1f}% excess return over 12 months (roll-adjusted), so the time-series momentum rule is "
                    f"{'long' if sign > 0 else 'short'} at {lev:.2f}x for 40% vol (EWMA vol {sg * 100:.0f}%, {nth(sig_pct)} 5-yr percentile).")
        if car_now is not None:
            kind = "storage carry" if sym in STORABLE else "curve slope (the market's forecast of the cash path)"
            read.append(f"Carry: front {h.c.iloc[-1]} vs {h.n.iloc[-1]} {car_now * 100:+.1f}%/yr {kind}"
                        + (f", {nth(car_pct)} percentile for this calendar month" if car_pct is not None else "")
                        + (f"; seasonal-adjusted {car_adj_now * 100:+.1f}%" if car_adj_now is not None and sym in STORABLE else "") + ".")
        if n_rank:
            read.append(f"Cross-section: #{int(rank_m.get(sym, 0))} of {n_rank} on momentum, #{int(rank_c.get(sym, 0)) if not np.isnan(rank_c.get(sym, np.nan)) else '-'} on carry.")
        t = bt["tsmom_12m"]; l = bt["long_only_scaled"]
        if t and l:
            read.append(f"Backtest since {t['since'][:4]}: trend Sharpe {t['sharpe']} (halves {t['sharpe_1st_half']}/{t['sharpe_2nd_half']}) vs vol-scaled long-only {l['sharpe']}.")
        if opt:
            read.append(f"Options ({opt['label']}): IV {opt['atm']:.1f}% vs RV {opt['rv20']:.1f}%, variance premium {opt['var_prem']:+.1f}"
                        + (f"; curve slope {opt['slope']:+.1f} pts" if opt.get("slope") is not None else "") + ".")
        if inv_:
            read.append(inv_["read"])
        out[sym] = {"sym": sym, "name": name, "group": sp["group"], "unit": sp["unit"], "date": str(h.index[-1].date()),
                    "held": h.c.iloc[-1], "next": h.n.iloc[-1], "price": price,
                    "trend": {"r12": r12, "r6": r6, "r3": r3, "r1": r1, "sign": sign, "lev": round(lev, 2) if lev else None,
                              "ewma_vol": round(sg * 100, 1), "vol_pct5y": sig_pct, "id": round(id_, 2) if id_ is not None else None},
                    "vr": vr, "carry": {"now": car_now, "pct_month": car_pct, "adj": car_adj_now, "storable": sym in STORABLE,
                                         "hist": [[str(d.date()), round(float(v) * 100, 2)] for d, v in h.carry.dropna().resample("ME").last().dropna().iloc[-120:].items()]},
                    "rank": {"mom": int(rank_m[sym]) if sym in rank_m and not np.isnan(rank_m[sym]) else None,
                             "carry": int(rank_c[sym]) if sym in rank_c and not np.isnan(rank_c[sym]) else None, "n": n_rank},
                    "backtest": bt, "equity": {k: [[str(d.date())[:7], round(float(v) * 100, 1)] for d, v in s.dropna().cumsum().items()] for k, s in
                                               {"tsmom_12m": ts, "long_only_scaled": lo, "carry": ca}.items()},
                    "options": opt, "density": dens, "positioning": pos, "inventory": inv_, "flags": flags,
                    "size": {"notional": round(notional), "contracts_10pct_1m": round(n10, 1) if n10 else None,
                             "invvol_weight": round(100 * inv[sym] / tot, 1) if sym in inv else None, "half_kelly_upper": kelly,
                             "adv": round(adv), "cost_bps_1pct_adv": round(cost_1pct, 1)},
                    "read": " ".join(read)}
        print(sym, out[sym]["read"][:160])
    (D / "research").mkdir(parents=True, exist_ok=True)
    (D / "research" / "research.json").write_text(json.dumps({"generated": date.today().isoformat(), "rate": rate, "cross_section": xs,
                                                             "markets": out}, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x,
                                                            allow_nan=True).replace("NaN", "null"))
    print("cross-section", xs)


if __name__ == "__main__":
    main()
