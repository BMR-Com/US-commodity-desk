#!/usr/bin/env python3
"""Technical pattern lab: classic chart and indicator setups tested on every desk market (daily, roll-adjusted).

Rules (long and short mirrors, with and without a 200-day trend filter):
- mean reversion: RSI(14) back above 30 / below 70; RSI(2) < 10 / > 90 (Connors); close 3/5/7/10% below / above the
  9-day MA; close back inside the Bollinger band (20, 2); 3/4/5 down / up days in a row; stochastic(14) cross of 20 / 80
- pullbacks in a trend: price above 50 > 200-day (uptrend) and the close dips to the 9, 20 or 50-day MA (mirror for
  downtrends); uptrend + RSI(2) < 10
- crossovers and breakouts: MACD (12, 26, 9) crossing its signal (any / below zero / with trend), 9x20 and 20x50 EMA
  crosses, 50x200 SMA (golden / death cross), close crossing the 20-day MA, 20 and 55-day closing breakouts
- divergence: price makes a lower 20-day low while RSI(14) makes a higher low (bullish), and the mirror (bearish);
  the same with the MACD histogram
Execution: signal at a day's close, entry at the NEXT day's close, exit after 5, 10 or 20 trading days; trades do not
overlap. Per rule, market and holding period: trades, win rate, average and median return, profit factor, average
worst drawdown inside the trade (max adverse excursion), t-stat, and the Sharpe / max drawdown of trading the rule at
10% volatility (5 bp per side), split 2007-2018 vs 2019+. Base rate = average return of any day held the same length
in the same direction, so a rule's edge is the gap to the base rate.
Also: how often and how fast markets recover to the 9-day MA after closing 3-10% below it (and drawdown before), and
what happens after the first pullback to the 9/20/50-day MA in an uptrend.
Writes data/backtest/tech.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from research import held_series, AHEAD   # noqa: E402
import backtest_lab as BL   # noqa: E402

SPLIT = pd.Timestamp("2019-01-01")
HOLDS = (5, 10, 20)
COST = 0.0005


def load(sym):
    p = ROOT / "data" / "contracts" / f"{sym}.csv"
    if not p.exists():
        return None
    h = held_series(pd.read_csv(p), AHEAD.get(sym, 1))
    h = h[h.index >= pd.Timestamp("2006-01-01")]
    h = h[h.index.dayofweek < 5]
    r = h.r.fillna(0)
    c = (1 + r).cumprod()
    return pd.DataFrame({"c": c, "r": r})


def rsi(c, n):
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def ind(f):
    c = f.c
    for n in (9, 20, 50, 100, 200):
        f[f"ma{n}"] = c.rolling(n).mean()
    for n in (9, 20, 50):
        f[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    f["rsi14"], f["rsi2"] = rsi(c, 14), rsi(c, 2)
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    f["macd"], f["sig"] = m, m.ewm(span=9, adjust=False).mean()
    f["mh"] = f.macd - f.sig
    sd = c.rolling(20).std()
    f["bbl"], f["bbu"] = f.ma20 - 2 * sd, f.ma20 + 2 * sd
    lo, hi = c.rolling(14).min(), c.rolling(14).max()
    f["sto"] = 100 * (c - lo) / (hi - lo)
    f["up"] = (c > f.ma50) & (f.ma50 > f.ma200)
    f["dn"] = (c < f.ma50) & (f.ma50 < f.ma200)
    # trend for pullback tests: 50-day above 200-day and rising (does not require price above the 50-day, so a dip to it can count)
    f["upt"] = (f.ma50 > f.ma200) & (f.ma50 > f.ma50.shift(10))
    f["dnt"] = (f.ma50 < f.ma200) & (f.ma50 < f.ma50.shift(10))
    f["dev9"] = c / f.ma9 - 1
    dd = (c.diff() < 0).astype(int); ud = (c.diff() > 0).astype(int)
    f["downs"] = dd.groupby((dd == 0).cumsum()).cumsum()
    f["ups"] = ud.groupby((ud == 0).cumsum()).cumsum()
    f["vol"] = f.r.ewm(span=40).std().shift(1) * math.sqrt(252)
    # divergence: new 20-day closing low below the low of days 21-60, while RSI / MACD histogram is above its value then
    low20 = c.rolling(20).min(); prev_low = c.shift(20).rolling(40).min()
    idx_prev = c.shift(20).rolling(40).apply(np.argmin, raw=True)
    f["newlow"] = (c <= low20) & (c < prev_low)
    f["newhigh"] = (c >= c.rolling(20).max()) & (c > c.shift(20).rolling(40).max())
    rs, hs = f.rsi14.values, f.mh.values
    pos = np.arange(len(f))
    def at_prev(arr, kind):
        k = c.shift(20).rolling(40).apply(np.argmin if kind == "min" else np.argmax, raw=True).values
        out = np.full(len(f), np.nan)
        for i in range(len(f)):
            if not np.isnan(k[i]):
                j = int(i - 20 - 39 + k[i])
                if 0 <= j < len(f):
                    out[i] = arr[j]
        return out
    f["rsi_at_low"], f["rsi_at_high"] = at_prev(rs, "min"), at_prev(rs, "max")
    f["hist_at_low"], f["hist_at_high"] = at_prev(hs, "min"), at_prev(hs, "max")
    return f


X = lambda a, b: (a > b) & (a.shift(1) <= b.shift(1))   # a crosses above b


def rules(f):
    c = f.c
    R = {}
    def add(name, fam, long_ev, short_ev=None):
        R[name] = (fam, long_ev.fillna(False), None if short_ev is None else short_ev.fillna(False))
    t, d = f.up.fillna(False), f.dn.fillna(False)
    a200 = c > f.ma200
    # mean reversion
    add("RSI(14) back above 30 / below 70", "Mean reversion", X(f.rsi14, 30 + 0 * c), X(70 + 0 * c, f.rsi14))
    add("RSI(14) back above 30 in uptrend / below 70 in downtrend", "Mean reversion + trend", X(f.rsi14, 30 + 0 * c) & a200, X(70 + 0 * c, f.rsi14) & ~a200)
    add("RSI(2) < 10 / > 90", "Mean reversion", f.rsi2 < 10, f.rsi2 > 90)
    add("RSI(2) < 10 above 200-day / > 90 below (Connors)", "Mean reversion + trend", (f.rsi2 < 10) & a200, (f.rsi2 > 90) & ~a200)
    for x in (3, 5, 7, 10):
        add(f"Close {x}% below / above the 9-day MA", "Mean reversion", (f.dev9 < -x / 100) & (f.dev9.shift(1) >= -x / 100), (f.dev9 > x / 100) & (f.dev9.shift(1) <= x / 100))
    add("Close 5% below 9-day MA, above 200-day / mirror", "Mean reversion + trend", (f.dev9 < -0.05) & (f.dev9.shift(1) >= -0.05) & a200, (f.dev9 > 0.05) & (f.dev9.shift(1) <= 0.05) & ~a200)
    add("Close back inside lower / upper Bollinger band", "Mean reversion", X(c, f.bbl), X(f.bbu, c))
    for k in (3, 4, 5):
        add(f"{k} down days in a row / {k} up days", "Mean reversion", f.downs == k, f.ups == k)
    add("Stochastic(14) crosses up through 20 / down through 80", "Mean reversion", X(f.sto, 20 + 0 * c), X(80 + 0 * c, f.sto))
    # pullbacks in trend
    for n in (9, 20, 50):
        ma = f[f"ma{n}"]
        add(f"Uptrend pullback to the {n}-day MA / downtrend rally to it", "Pullback in trend", f.upt.fillna(False) & (c <= ma) & (c.shift(1) > ma.shift(1)), f.dnt.fillna(False) & (c >= ma) & (c.shift(1) < ma.shift(1)))
    add("Uptrend + RSI(2) < 10 / downtrend + RSI(2) > 90", "Pullback in trend", t & (f.rsi2 < 10), d & (f.rsi2 > 90))
    add("Uptrend + close back above 9-day MA after a dip / mirror", "Pullback in trend", t & X(c, f.ma9) & (f.dev9.shift(3).rolling(3).min() < 0), d & X(f.ma9, c) & (f.dev9.shift(3).rolling(3).max() > 0))
    # crossovers and breakouts
    add("MACD crosses above / below its signal", "Crossover", X(f.macd, f.sig), X(f.sig, f.macd))
    add("MACD bullish cross below zero / bearish cross above zero", "Crossover", X(f.macd, f.sig) & (f.macd < 0), X(f.sig, f.macd) & (f.macd > 0))
    add("MACD cross with the 200-day trend", "Crossover + trend", X(f.macd, f.sig) & a200, X(f.sig, f.macd) & ~a200)
    add("9-day EMA crosses 20-day EMA", "Crossover", X(f.ema9, f.ema20), X(f.ema20, f.ema9))
    add("20-day EMA crosses 50-day EMA", "Crossover", X(f.ema20, f.ema50), X(f.ema50, f.ema20))
    add("Golden / death cross (50 x 200-day)", "Crossover", X(f.ma50, f.ma200), X(f.ma200, f.ma50))
    add("Close crosses above / below the 20-day MA", "Crossover", X(c, f.ma20), X(f.ma20, c))
    add("20-day closing breakout (high / low)", "Breakout", c > c.shift(1).rolling(20).max(), c < c.shift(1).rolling(20).min())
    add("55-day closing breakout (high / low)", "Breakout", c > c.shift(1).rolling(55).max(), c < c.shift(1).rolling(55).min())
    # divergence
    add("Bullish / bearish RSI divergence", "Divergence", f.newlow & (f.rsi14 > f.rsi_at_low), f.newhigh & (f.rsi14 < f.rsi_at_high))
    add("Bullish / bearish MACD-histogram divergence", "Divergence", f.newlow & (f.mh > f.hist_at_low), f.newhigh & (f.mh < f.hist_at_high))
    add("RSI divergence with the 200-day trend", "Divergence + trend", f.newlow & (f.rsi14 > f.rsi_at_low) & a200, f.newhigh & (f.rsi14 < f.rsi_at_high) & ~a200)
    return R


def trades(f, ev, side, h):
    """Non-overlapping trades: signal close t, enter close t+1, exit close t+1+h."""
    c = f.c.values; vol = f.vol.values; e = ev.values; n = len(c)
    out = []; i = 0
    while i < n - h - 2:
        if e[i]:
            a, b = i + 1, i + 1 + h
            path = c[a:b + 1] / c[a] - 1
            ret = side * path[-1] - 2 * COST
            mae = float(np.min(side * path))
            out.append((f.index[i], ret, mae, vol[a] if not np.isnan(vol[a]) else np.nan))
            i = b
        else:
            i += 1
    return out


def pstats(tr, h):
    if len(tr) < 8:
        return None
    r = np.array([t[1] for t in tr]); mae = np.array([t[2] for t in tr])
    v = np.array([t[3] for t in tr]); v = np.where(np.isnan(v) | (v <= 0), np.nanmedian(v), v)
    ru = r / (v * math.sqrt(h / 252))                      # return in units of the trade's expected volatility
    yrs = max((tr[-1][0] - tr[0][0]).days / 365.25, 1)
    per_year = len(tr) / yrs
    sr = float(ru.mean() / ru.std() * math.sqrt(per_year * 1)) if ru.std() > 0 else 0.0
    # equity at 10% vol per trade-period scaled to risk units: cumulative of ru * 10% * sqrt(h/252)
    eq = np.cumsum(ru * 0.10 * math.sqrt(h / 252))
    dd = float((eq - np.maximum.accumulate(eq)).min())
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"n": int(len(r)), "win": round(float((r > 0).mean() * 100), 1), "avg": round(float(r.mean() * 100), 2), "med": round(float(np.median(r) * 100), 2),
            "pf": round(float(gains / losses), 2) if losses > 0 else None, "mae": round(float(mae.mean() * 100), 2), "mae_worst": round(float(mae.min() * 100), 1),
            "t": round(float(ru.mean() / ru.std() * math.sqrt(len(ru))), 2) if ru.std() > 0 else None, "sharpe": round(sr, 2), "maxdd": round(dd * 100, 1),
            "per_year": round(per_year, 1)}


def base_rate(f, side, h):
    fw = f.c.shift(-h - 1) / f.c.shift(-1) - 1
    return float(side * fw.mean() * 100)


def recovery(f, xs=(3, 5, 7, 10), N=20):
    out = {}
    c, ma9 = f.c.values, f.ma9.values
    dev = f.dev9.values
    for x in xs:
        ev = np.where((dev < -x / 100) & (np.r_[0, dev[:-1]] >= -x / 100))[0]
        rec, days, mae, r5, r10, r20, orig = [], [], [], [], [], [], []
        for i in ev:
            if i + N + 1 >= len(c):
                continue
            seg = c[i + 1:i + 1 + N] >= ma9[i + 1:i + 1 + N]
            k = int(np.argmax(seg)) if seg.any() else None
            rec.append(k is not None)
            orig.append(bool((c[i + 1:i + 1 + N] >= ma9[i]).any()))
            if k is not None:
                days.append(k + 1)
            end = i + 1 + (k if k is not None else N)
            mae.append(float(np.min(c[i:end + 1] / c[i] - 1)))
            r5.append(c[i + 5] / c[i] - 1); r10.append(c[i + 10] / c[i] - 1); r20.append(c[i + 20] / c[i] - 1)
        if len(rec) >= 5:
            out[x] = {"events": len(rec), "recovered_pct": round(100 * float(np.mean(rec)), 0), "orig_pct": round(100 * float(np.mean(orig)), 0), "days_median": float(np.median(days)) if days else None,
                      "mae_avg": round(100 * float(np.mean(mae)), 2), "mae_worst": round(100 * float(np.min(mae)), 1),
                      "r5": round(100 * float(np.mean(r5)), 2), "r10": round(100 * float(np.mean(r10)), 2), "r20": round(100 * float(np.mean(r20)), 2),
                      "win10": round(100 * float(np.mean(np.array(r10) > 0)))}
    return out


def pullbacks(f, N=20):
    out = {}
    c = f.c
    for n in (9, 20, 50):
        ma = f[f"ma{n}"]
        ev = (f.upt.fillna(False) & (c <= ma) & (c.shift(1) > ma.shift(1))).values
        idx = np.where(ev)[0]
        resume, mae, r10, r20, below50 = [], [], [], [], []
        cv = c.values; hi20 = c.rolling(20).max().values; m50 = f.ma50.values
        for i in idx:
            if i + N + 1 >= len(cv):
                continue
            fut = cv[i + 1:i + 1 + N]
            resume.append(bool((fut > hi20[i]).any()))
            mae.append(float(fut.min() / cv[i] - 1))
            r10.append(cv[i + 10] / cv[i] - 1); r20.append(cv[i + 20] / cv[i] - 1)
            below50.append(bool((fut < m50[i + 1:i + 1 + N]).any()))
        if len(resume) >= 5:
            out[n] = {"events": len(resume), "new_high_pct": round(100 * float(np.mean(resume))), "mae_avg": round(100 * float(np.mean(mae)), 2),
                      "r10": round(100 * float(np.mean(r10)), 2), "r20": round(100 * float(np.mean(r20)), 2), "win20": round(100 * float(np.mean(np.array(r20) > 0))),
                      "broke50_pct": round(100 * float(np.mean(below50)))}
    return out


def main():
    rows, rec, pb, names = [], {}, {}, {}
    for sym, nm in BL.DESK.items():
        f = load(sym)
        if f is None or len(f) < 1500:
            continue
        f = ind(f)
        names[sym] = nm
        for rule, (fam, le, se) in rules(f).items():
            for side, ev in ((1, le), (-1, se)):
                if ev is None:
                    continue
                for h in HOLDS:
                    tr = [t for t in trades(f, ev, side, h) if t[0] >= pd.Timestamp("2007-01-01")]
                    s = pstats(tr, h)
                    if not s:
                        continue
                    s_is, s_oos = pstats([t for t in tr if t[0] < SPLIT], h), pstats([t for t in tr if t[0] >= SPLIT], h)
                    rows.append({"market": sym, "name_m": nm, "group": BL.GROUP.get(sym), "rule": rule, "family": fam, "side": "long" if side > 0 else "short", "hold": h, **s,
                                 "base": round(base_rate(f[f.index >= pd.Timestamp("2007-01-01")], side, h), 2),
                                 "is_sharpe": s_is["sharpe"] if s_is else None, "oos_sharpe": s_oos["sharpe"] if s_oos else None,
                                 "oos_win": s_oos["win"] if s_oos else None, "oos_n": s_oos["n"] if s_oos else 0})
        rec[sym] = recovery(f); pb[sym] = pullbacks(f)
        print(sym, len(rows), flush=True)
    df = pd.DataFrame(rows)
    df["edge"] = df.avg - df.base
    df["robust"] = (df.is_sharpe > 0) & (df.oos_sharpe > 0) & (df.n >= 20) & (df.oos_n >= 5)
    n_tests = len(df)
    noise_t = round(math.sqrt(2 * math.log(n_tests)), 2)
    # pooled across markets per rule / side / hold
    pool = df.groupby(["rule", "family", "side", "hold"]).agg(markets=("market", "count"), trades=("n", "sum"), win=("win", "median"), avg=("avg", "median"), edge=("edge", "median"),
                                                              pf=("pf", "median"), mae=("mae", "median"), sharpe=("sharpe", "median"), pos_share=("sharpe", lambda s: round(100 * (s > 0).mean())),
                                                              robust=("robust", lambda s: round(100 * s.mean())), oos=("oos_sharpe", "median")).reset_index()
    pool["score"] = pool.sharpe * np.sqrt(pool.markets / 20)
    pool = pool.sort_values("sharpe", ascending=False)
    fam = df.groupby(["family", "side"]).agg(tests=("market", "count"), sharpe=("sharpe", "median"), win=("win", "median"), edge=("edge", "median"),
                                             pos=("sharpe", lambda s: round(100 * (s > 0).mean())), robust=("robust", lambda s: round(100 * s.mean()))).reset_index().sort_values("sharpe", ascending=False)
    elig = df[(df.n >= 20)]
    top = elig[elig.robust].sort_values("sharpe", ascending=False).head(20)
    worst = elig.sort_values("sharpe").head(10)
    best_win = elig[(elig.n >= 30) & elig.robust].sort_values(["win", "sharpe"], ascending=False).head(10)
    low_dd = elig[elig.robust & (elig.sharpe > 0.3)].sort_values("maxdd", ascending=False).head(10)
    per = {}
    for sym, g in df.groupby("market"):
        g2 = g[(g.n >= 20) & g.robust].sort_values("sharpe", ascending=False)
        per[sym] = {"name": names[sym], "best": g2.head(8).round(2).to_dict("records"), "worst": g[g.n >= 20].sort_values("sharpe").head(5).round(2).to_dict("records")}
    # pooled recovery / pullback tables
    def pooled(d, keys):
        out = []
        for k in keys:
            xs = [v[k] for v in d.values() if k in v]
            if not xs:
                continue
            tot = sum(x["events"] for x in xs)
            wavg = lambda f_: round(sum(x[f_] * x["events"] for x in xs if x.get(f_) is not None) / tot, 2)
            row = {"k": k, "events": tot, "markets": len(xs)}
            for f_ in xs[0]:
                if f_ != "events" and all(x.get(f_) is not None for x in xs):
                    row[f_] = wavg(f_)
            out.append(row)
        return out
    L = []
    pl = pool[(pool.markets >= 12)]
    for r in pl.head(8).itertuples():
        L.append(f"{r.rule} ({r.side}, hold {r.hold} days): median Sharpe {r.sharpe:.2f} across {r.markets} markets, win rate {r.win:.0f}%, median edge {r.edge:+.2f}% per trade vs holding any day, positive in {r.pos_share}% of markets, robust out of sample in {r.robust}%.")
    w = pl.sort_values("sharpe").head(5)
    L.append("Weakest: " + "; ".join(f"{r.rule} ({r.side}, {r.hold}d, median Sharpe {r.sharpe:.2f}, win {r.win:.0f}%)" for r in w.itertuples()) + ".")
    for fam_, side in (("Mean reversion", "long"), ("Pullback in trend", "long"), ("Crossover", "long"), ("Divergence", "long"), ("Breakout", "long")):
        x = fam[(fam.family == fam_) & (fam.side == side)]
        if len(x):
            x = x.iloc[0]
            L.append(f"{fam_} ({side}): median Sharpe {x.sharpe:.2f}, win rate {x.win:.0f}%, edge {x.edge:+.2f}% per trade, {x.pos}% of tests positive, {x.robust}% robust.")
    rp = pooled(rec, [3, 5, 7, 10])
    for r in rp:
        L.append(f"After a close {r['k']}% below the 9-day MA ({r['events']} cases): touches the (falling) 9-day MA within 20 days in {r['recovered_pct']:.0f}% of cases (median {r.get('days_median', 0):.0f} days) but gets back to the 9-day MA level of the signal day only {r['orig_pct']:.0f}% of the time; "
                 f"average drawdown before that {r['mae_avg']:.1f}% (worst {r['mae_worst']:.0f}%), return after 10 days {r['r10']:+.2f}% (up {r['win10']:.0f}% of the time).")
    pp = pooled(pb, [9, 20, 50])
    for r in pp:
        L.append(f"First dip to the {r['k']}-day MA in an uptrend ({r['events']} cases): new 20-day high within 20 days {r['new_high_pct']:.0f}%, closed below the 50-day {r['broke50_pct']:.0f}%, "
                 f"average dip {r['mae_avg']:.1f}%, return after 20 days {r['r20']:+.2f}% (up {r['win20']:.0f}%).")
    L.append(f"{n_tests} rule x market x holding-period tests: a t-stat around {noise_t} is what the luckiest test would show by chance, so prefer rules that work across many markets and in both 2007-18 and 2019+.")
    out = {"generated": date.today().isoformat(), "split": str(SPLIT.date()), "holds": HOLDS, "n_tests": n_tests, "noise_t": noise_t, "learnings": L,
           "families": fam.round(2).to_dict("records"), "pooled": pool.round(2).to_dict("records"), "top": top.round(2).to_dict("records"), "worst": worst.round(2).to_dict("records"),
           "best_win": best_win.round(2).to_dict("records"), "low_dd": low_dd.round(2).to_dict("records"), "per_market": per,
           "recovery": {"pooled": rp, "by_market": {names[k]: v for k, v in rec.items()}}, "pullback": {"pooled": pp, "by_market": {names[k]: v for k, v in pb.items()}}}
    (ROOT / "data" / "backtest" / "tech.json").write_text(json.dumps(out, default=lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else (bool(x) if isinstance(x, np.bool_) else float(x))).replace("NaN", "null"))
    print("\n".join(L))
    print(top[["name_m", "rule", "side", "hold", "n", "win", "avg", "sharpe", "oos_sharpe", "maxdd"]].to_string())


if __name__ == "__main__":
    main()
