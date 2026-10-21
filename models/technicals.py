"""Price & technicals for every desk contract, in the format of the cotton desk's technicals page.

Bars: data/ohlc/<SYM>.csv (pipelines/ohlc.py, TradingView): continuous front month + live contracts.
Per series: trend, momentum, volatility, levels (pivots, 52-week Fibonacci, swing highs/lows) and a
TradingView-style rating from moving averages and oscillators, daily and weekly; calendar spreads between
consecutive live contracts. Seasonality/percentiles from per-contract closes (data/contracts), each contract
aligned on weeks before its last trading day. Indicator and rating code shared with the cotton desk.
Writes data/technicals/<SYM>.json.
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "technicals"
CODES = "FGHJKMNQUVXZ"
MNAME = dict(zip(CODES, ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]))
UNITS = {"CT": ("¢/lb", 2), "ZC": ("¢/bu", 2), "ZS": ("¢/bu", 2), "ZW": ("¢/bu", 2), "KE": ("¢/bu", 2), "ZM": ("$/st", 1), "ZL": ("¢/lb", 2),
         "HE": ("¢/lb", 3), "LE": ("¢/lb", 3), "GF": ("¢/lb", 3), "DC": ("$/cwt", 2), "GDK": ("$/cwt", 2),
         "CSC": ("$/lb", 3), "CB": ("¢/lb", 3), "GNF": ("¢/lb", 3), "DY": ("¢/lb", 3)}
NAMES = {"CT": "Cotton", "ZC": "Corn", "ZS": "Soybeans", "ZW": "Chicago wheat", "KE": "KC HRW wheat", "ZM": "Soybean meal", "ZL": "Soybean oil",
         "HE": "Lean hogs", "LE": "Live cattle", "GF": "Feeder cattle", "DC": "Class III milk", "GDK": "Class IV milk",
         "CSC": "Cheese", "CB": "Butter", "GNF": "Nonfat dry milk", "DY": "Dry whey"}


def ordinal(v):
    n = int(round(v))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ───────── indicators ─────────
def sma(s, n): return s.rolling(n).mean()
def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def rma(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()


def rsi(c, n=14):
    d = c.diff()
    up, dn = rma(d.clip(lower=0), n), rma(-d.clip(upper=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(h, n=14):
    tr = pd.concat([h.High - h.Low, (h.High - h.Close.shift()).abs(), (h.Low - h.Close.shift()).abs()], axis=1).max(axis=1)
    return rma(tr, n)


def adx(h, n=14):
    up, dn = h.High.diff(), -h.Low.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(h, n)
    pdi = 100 * rma(pd.Series(pdm, h.index), n) / a
    mdi = 100 * rma(pd.Series(mdm, h.index), n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return rma(dx, n), pdi, mdi


def stoch(h, n=14, k=3, d=3):
    ll, hh = h.Low.rolling(n).min(), h.High.rolling(n).max()
    kk = sma(100 * (h.Close - ll) / (hh - ll), k)
    return kk, sma(kk, d)


def cci(h, n=20):
    tp = (h.High + h.Low + h.Close) / 3
    md = tp.rolling(n).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - sma(tp, n)) / (0.015 * md)


def ichimoku(h):
    conv = (h.High.rolling(9).max() + h.Low.rolling(9).min()) / 2
    base = (h.High.rolling(26).max() + h.Low.rolling(26).min()) / 2
    a = (conv + base) / 2
    b = (h.High.rolling(52).max() + h.Low.rolling(52).min()) / 2
    return conv, base, a, b


def psar(h, step=0.02, mx=0.2):
    hi, lo = h.High.values, h.Low.values
    out = np.full(len(h), np.nan)
    if len(h) < 3:
        return pd.Series(out, h.index)
    bull, af, ep, sar = True, step, hi[0], lo[0]
    for i in range(1, len(h)):
        sar = sar + af * (ep - sar)
        if bull:
            sar = min(sar, lo[i - 1], lo[i - 2] if i > 1 else lo[i - 1])
            if lo[i] < sar:
                bull, sar, ep, af = False, ep, lo[i], step
            elif hi[i] > ep:
                ep, af = hi[i], min(af + step, mx)
        else:
            sar = max(sar, hi[i - 1], hi[i - 2] if i > 1 else hi[i - 1])
            if hi[i] > sar:
                bull, sar, ep, af = True, ep, hi[i], step
            elif lo[i] < ep:
                ep, af = lo[i], min(af + step, mx)
        out[i] = sar
    return pd.Series(out, h.index)


def hma(s, n=9):
    return sma(2 * s.rolling(n // 2).apply(_wma, raw=True) - s.rolling(n).apply(_wma, raw=True), 1).rolling(int(math.sqrt(n))).apply(_wma, raw=True)


def _wma(x):
    w = np.arange(1, len(x) + 1)
    return (x * w).sum() / w.sum()


def weekly(h):
    w = h.resample("W-FRI").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna(subset=["Close"])
    return w


def rating(h):
    """TradingView-style summary: each MA and oscillator votes buy / sell / neutral."""
    c = h.Close
    last = c.iloc[-1]
    ma_votes = {}
    for n in (10, 20, 30, 50, 100, 200):
        for kind, f in (("SMA", sma), ("EMA", ema)):
            v = f(c, n).iloc[-1]
            if not np.isnan(v):
                ma_votes[f"{kind} {n}"] = 1 if last > v else -1 if last < v else 0
    conv, base, a, b = ichimoku(h)
    if not np.isnan(base.iloc[-1]):
        ma_votes["Ichimoku base line"] = 1 if last > base.iloc[-1] else -1
    hm = hma(c, 9)
    if len(hm.dropna()):
        ma_votes["Hull MA 9"] = 1 if last > hm.iloc[-1] else -1
    osc = {}
    r = rsi(c)
    osc["RSI (14)"] = (r.iloc[-1], 1 if r.iloc[-1] < 30 and r.iloc[-1] > r.iloc[-2] else -1 if r.iloc[-1] > 70 and r.iloc[-1] < r.iloc[-2] else 0)
    k, d = stoch(h)
    osc["Stochastic %K (14,3,3)"] = (k.iloc[-1], 1 if k.iloc[-1] < 20 and k.iloc[-1] > d.iloc[-1] else -1 if k.iloc[-1] > 80 and k.iloc[-1] < d.iloc[-1] else 0)
    cc = cci(h)
    osc["CCI (20)"] = (cc.iloc[-1], 1 if cc.iloc[-1] < -100 and cc.iloc[-1] > cc.iloc[-2] else -1 if cc.iloc[-1] > 100 and cc.iloc[-1] < cc.iloc[-2] else 0)
    ad, pdi, mdi = adx(h)
    osc["ADX (14)"] = (ad.iloc[-1], (1 if pdi.iloc[-1] > mdi.iloc[-1] else -1) if ad.iloc[-1] > 20 and ad.iloc[-1] > ad.iloc[-2] else 0)
    ao = sma((h.High + h.Low) / 2, 5) - sma((h.High + h.Low) / 2, 34)
    osc["Awesome oscillator"] = (ao.iloc[-1], 1 if ao.iloc[-1] > 0 and ao.iloc[-1] > ao.iloc[-2] else -1 if ao.iloc[-1] < 0 and ao.iloc[-1] < ao.iloc[-2] else 0)
    mom = c - c.shift(10)
    osc["Momentum (10)"] = (mom.iloc[-1], 1 if mom.iloc[-1] > mom.iloc[-2] else -1)
    m = ema(c, 12) - ema(c, 26); sg = ema(m, 9)
    osc["MACD (12,26)"] = (m.iloc[-1], 1 if m.iloc[-1] > sg.iloc[-1] else -1)
    lo, hi = c.rolling(14).min(), c.rolling(14).max()
    sr = rsi(c); srsi = 100 * (sr - sr.rolling(14).min()) / (sr.rolling(14).max() - sr.rolling(14).min())
    sk = sma(srsi, 3); sd = sma(sk, 3)
    osc["Stochastic RSI fast"] = (sk.iloc[-1], 1 if sk.iloc[-1] < 20 and sk.iloc[-1] > sd.iloc[-1] else -1 if sk.iloc[-1] > 80 and sk.iloc[-1] < sd.iloc[-1] else 0)
    wr = -100 * (h.High.rolling(14).max() - c) / (h.High.rolling(14).max() - h.Low.rolling(14).min())
    osc["Williams %R (14)"] = (wr.iloc[-1], 1 if wr.iloc[-1] < -80 and wr.iloc[-1] > wr.iloc[-2] else -1 if wr.iloc[-1] > -20 and wr.iloc[-1] < wr.iloc[-2] else 0)
    e13 = ema(c, 13)
    bbp = (h.High - e13) + (h.Low - e13)
    osc["Bull bear power"] = (bbp.iloc[-1], 1 if bbp.iloc[-1] > 0 and bbp.iloc[-1] > bbp.iloc[-2] else -1 if bbp.iloc[-1] < 0 and bbp.iloc[-1] < bbp.iloc[-2] else 0)
    bp = c - pd.concat([h.Low, c.shift()], axis=1).min(axis=1)
    tr = pd.concat([h.High, c.shift()], axis=1).max(axis=1) - pd.concat([h.Low, c.shift()], axis=1).min(axis=1)
    uo = 100 * (4 * bp.rolling(7).sum() / tr.rolling(7).sum() + 2 * bp.rolling(14).sum() / tr.rolling(14).sum() + bp.rolling(28).sum() / tr.rolling(28).sum()) / 7
    osc["Ultimate oscillator"] = (uo.iloc[-1], 1 if uo.iloc[-1] > 70 else -1 if uo.iloc[-1] < 30 else 0)

    def word(score):
        return "Strong buy" if score > 0.5 else "Buy" if score > 0.1 else "Strong sell" if score < -0.5 else "Sell" if score < -0.1 else "Neutral"
    mv = list(ma_votes.values()); ov = [v for _, v in osc.values()]
    ms, os_ = np.mean(mv) if mv else 0, np.mean(ov) if ov else 0
    return {"overall": word((ms + os_) / 2), "ma": word(ms), "osc": word(os_),
            "ma_counts": [sum(v > 0 for v in mv), sum(v == 0 for v in mv), sum(v < 0 for v in mv)],
            "osc_counts": [sum(v > 0 for v in ov), sum(v == 0 for v in ov), sum(v < 0 for v in ov)],
            "ma_detail": [[k, round(float(ma_value(h, k)), 4), v] for k, v in ma_votes.items()],
            "osc_detail": [[k, None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 2), s] for k, (v, s) in osc.items()]}


def ma_value(h, label):
    c = h.Close
    if label.startswith("SMA"):
        return sma(c, int(label.split()[1])).iloc[-1]
    if label.startswith("EMA"):
        return ema(c, int(label.split()[1])).iloc[-1]
    if label.startswith("Ichimoku"):
        return ichimoku(h)[1].iloc[-1]
    return hma(c, 9).iloc[-1]


def pivots(h):
    """Classic and Fibonacci pivots from the last completed week and month."""
    out = {}
    for lab, rule in (("weekly", "W-FRI"), ("monthly", "ME")):
        g = h.resample(rule).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
        if len(g) < 2:
            continue
        p = g.iloc[-2]
        P = (p.High + p.Low + p.Close) / 3
        rg = p.High - p.Low
        out[lab] = {"P": P, "R1": 2 * P - p.Low, "S1": 2 * P - p.High, "R2": P + rg, "S2": P - rg, "R3": p.High + 2 * (P - p.Low), "S3": p.Low - 2 * (p.High - P),
                    "fibR1": P + 0.382 * rg, "fibS1": P - 0.382 * rg, "fibR2": P + 0.618 * rg, "fibS2": P - 0.618 * rg}
    return {k: {kk: round(float(vv), 4) for kk, vv in v.items()} for k, v in out.items()}


def swings(h, look=5, n=6):
    """Recent swing highs/lows (local extremes over ±look bars) as support/resistance candidates."""
    hi, lo = h.High.values, h.Low.values
    sh, sl = [], []
    for i in range(look, len(h) - look):
        if hi[i] == hi[i - look:i + look + 1].max():
            sh.append((h.index[i], hi[i]))
        if lo[i] == lo[i - look:i + look + 1].min():
            sl.append((h.index[i], lo[i]))
    last = h.Close.iloc[-1]
    res = sorted({round(float(v), 4) for _, v in sh[-40:] if v > last})[:n]
    sup = sorted({round(float(v), 4) for _, v in sl[-40:] if v < last}, reverse=True)[:n]
    return res, sup


def analyse(h, label, spread=False, u="¢", dp=2):
    c = h.Close
    last, prev = float(c.iloc[-1]), float(c.iloc[-2])
    s20, s50, s100, s200 = (sma(c, n).iloc[-1] for n in (20, 50, 100, 200))
    r = float(rsi(c).iloc[-1])
    m = ema(c, 12) - ema(c, 26); sg = ema(m, 9); hist = m - sg
    a = float(atr(h).iloc[-1])
    ad, pdi, mdi = adx(h)
    mid, sd = sma(c, 20), c.rolling(20).std()
    bw = (4 * sd / mid).dropna()
    bw_pct = float((bw.iloc[-252:] < bw.iloc[-1]).mean() * 100) if len(bw) > 30 else None
    hi52, lo52 = float(h.High.iloc[-252:].max()), float(h.Low.iloc[-252:].min())
    # Fibonacci retracement of the last 52-week range, direction from where the extreme came last
    up = h.High.iloc[-252:].idxmax() > h.Low.iloc[-252:].idxmin()
    rng = hi52 - lo52
    fib = {f"{p:.1%}": round(hi52 - p * rng if up else lo52 + p * rng, 4) for p in (0.236, 0.382, 0.5, 0.618, 0.786)}
    res, sup = swings(h)
    s50s, s200s = sma(c, 50), sma(c, 200)
    cross = None
    for i in range(1, min(60, len(c) - 200)):
        a1, b1, a0, b0 = s50s.iloc[-i], s200s.iloc[-i], s50s.iloc[-i - 1], s200s.iloc[-i - 1]
        if a1 > b1 and a0 <= b0:
            cross = f"golden cross (50-day above 200-day) {i} sessions ago"; break
        if a1 < b1 and a0 >= b0:
            cross = f"death cross (50-day below 200-day) {i} sessions ago"; break
    w = weekly(h)
    rt_d, rt_w = rating(h), (rating(w) if len(w) > 60 else None)
    ret = {k: (float(c.iloc[-1] / c.iloc[-n - 1] - 1) * 100 if len(c) > n else None) for k, n in (("1w", 5), ("1m", 21), ("3m", 63))}
    ytd = c[c.index.year == c.index[-1].year]
    ret["ytd"] = float(c.iloc[-1] / ytd.iloc[0] - 1) * 100 if len(ytd) > 1 else None
    if spread:                                   # spreads: changes in cents, not percent
        ret = {k: (float(c.iloc[-1] - c.iloc[-n - 1]) if len(c) > n else None) for k, n in (("1w", 5), ("1m", 21), ("3m", 63))}
        ret["ytd"] = float(c.iloc[-1] - ytd.iloc[0]) if len(ytd) > 1 else None

    trend = ("up" if last > s50 > s200 else "down" if last < s50 < s200 else "mixed") if not np.isnan(s200) else ("up" if last > s50 else "down")
    t = []
    if spread:
        ch = lambda n: last - float(c.iloc[-n - 1]) if len(c) > n else float("nan")
        t.append(f"{label} at {last:+.{dp}f} {u} ({last - prev:+.{dp}f} on the day, {ch(5):+.{dp}f} on the week, {ch(21):+.{dp}f} on the month); "
                 f"52-week range {lo52:+.{dp}f} to {hi52:+.{dp}f} {u}. Negative = front under the next contract (carry); positive = inverted.")
    else:
        t.append(f"{label} at {last:.{dp}f} {u} ({last - prev:+.{dp}f} on the day), {ret['1w']:+.1f}% on the week and {ret['1m']:+.1f}% on the month; "
                 f"52-week range {lo52:.{dp}f}–{hi52:.{dp}f} {u}.")
    ma_txt = ", ".join(f"{n}-day {v:.{dp}f}" for n, v in ((20, s20), (50, s50), (100, s100), (200, s200)) if not np.isnan(v))
    t.append(f"Trend: {trend}. Price is {'above' if last > s50 else 'below'} the 50-day and {'above' if not np.isnan(s200) and last > s200 else 'below'} the 200-day ({ma_txt})"
             + (f"; {cross}." if cross else "."))
    t.append(f"Momentum: RSI {r:.0f} ({'overbought' if r > 70 else 'oversold' if r < 30 else 'neutral'}); MACD {'above' if m.iloc[-1] > sg.iloc[-1] else 'below'} its signal "
             f"with the histogram {'rising' if hist.iloc[-1] > hist.iloc[-2] else 'falling'}; ADX {ad.iloc[-1]:.0f} "
             f"({'trending' if ad.iloc[-1] > 25 else 'weak trend' if ad.iloc[-1] > 20 else 'range-bound'}, {'+DI' if pdi.iloc[-1] > mdi.iloc[-1] else '−DI'} leading).")
    t.append(f"Volatility: ATR {a:.{dp}f} {u}" + ("" if spread else f" ({a / last * 100:.1f}% of price)") + (f"; Bollinger width at the {ordinal(bw_pct)} percentile of the past year"
             + (" — a squeeze, often ahead of a range break." if bw_pct < 20 else ".") if bw_pct is not None else "."))
    if res or sup:
        t.append("Levels: resistance " + (", ".join(f"{v:.{dp}f}" for v in res[:3]) or "—") + "; support " + (", ".join(f"{v:.{dp}f}" for v in sup[:3]) or "—")
                 + f". 52-week Fibonacci 38.2% {fib['38.2%']:.{dp}f}, 50% {fib['50.0%']:.{dp}f}, 61.8% {fib['61.8%']:.{dp}f}.")
    t.append(f"Rating: daily {rt_d['overall'].lower()} (moving averages {rt_d['ma'].lower()}, oscillators {rt_d['osc'].lower()})"
             + (f"; weekly {rt_w['overall'].lower()}." if rt_w else "."))
    return {"last": last, "chg": last - prev, "returns": ret, "spread": spread, "trend": trend, "rsi": r, "atr": a, "adx": float(ad.iloc[-1]),
            "hi52": hi52, "lo52": lo52, "fib": fib, "resistance": res, "support": sup, "pivots": pivots(h),
            "rating_daily": rt_d, "rating_weekly": rt_w, "text": t, "date": h.index[-1].strftime("%Y-%m-%d")}


# ───────── seasonality & percentiles from per-contract closes ─────────
def code_parts(sym, c):
    s = c[len(sym):]
    return s[0], int(s[1:])


def season_rows(sym, live, last_dates, closes):
    """Rows: the first 4 live contracts (price) and spreads between consecutive live contracts.
    History: same contract month in earlier years, aligned on weeks before that contract's last trade."""
    out = []
    est_last = {}
    for c in live:
        L, y = code_parts(sym, c)
        m = CODES.index(L) + 1
        est_last[c] = last_dates.get(c) or (pd.Timestamp(y, m, 8) if sym == "CT" else pd.Timestamp(y, m, 14) if sym in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE", "HE")
                                            else pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0))
    def wk_series(c, last):
        s = closes.get(c)
        if s is None or not len(s):
            return None
        w = ((last - s.index).days // 7)
        x = pd.Series(s.values, index=w)
        x = x[(x.index >= 0) & (x.index <= 52)]
        return x.groupby(level=0).last()
    defs = [(c, None) for c in live[:4]] + list(zip(live[:3], live[1:4]))
    for a, b in defs:
        La, ya = code_parts(sym, a)
        lab = f"{MNAME[La]} {ya % 100:02d}" + (f"/{MNAME[code_parts(sym, b)[0]]} {code_parts(sym, b)[1] % 100:02d} spread" if b else " futures")
        cur = wk_series(a, est_last[a]) if not b else None
        if b:
            sa, sb = closes.get(a), closes.get(b)
            if sa is None or sb is None:
                continue
            j = (sa - sb).dropna()
            w = (est_last[a] - j.index).days // 7
            cur = pd.Series(j.values, index=w)
            cur = cur[(cur.index >= 0) & (cur.index <= 52)].groupby(level=0).last()
        if cur is None or cur.empty:
            continue
        hist = {}
        for yy in range(ya - 25, ya):
            pa = f"{sym}{La}{yy}"
            if pa not in last_dates:
                continue
            if not b:
                hs = wk_series(pa, last_dates[pa])
            else:
                Lb, yb = code_parts(sym, b)
                pb = f"{sym}{Lb}{yy + (yb - ya)}"
                if pb not in closes:
                    continue
                j = (closes[pa] - closes[pb]).dropna()
                w = (last_dates[pa] - j.index).days // 7
                hs = pd.Series(j.values, index=w)
                hs = hs[(hs.index >= 0) & (hs.index <= 52)].groupby(level=0).last()
            if hs is not None and len(hs) > 20:
                hist[yy] = hs
        if len(hist) < 4:
            continue
        H = pd.DataFrame(hist)
        now_w, now_v = int(cur.index.min()), float(cur.loc[cur.index.min()])
        same = H.loc[[w for w in range(now_w - 1, now_w + 2) if w in H.index]].mean()
        allv = H.stack().values
        pct = lambda arr: float((np.asarray(arr) < now_v).mean() * 100) if len(arr) else None
        yrs = sorted(H.columns)
        last5 = yrs[-5:]
        out.append({"label": lab, "kind": "spread" if b else "price", "contract": a + (f"-{b}" if b else ""), "now": now_v, "wk_now": now_w,
                    "expiry": str(est_last[a].date()),
                    "pct_same_time": pct(same.dropna()), "pct_same_time_10y": pct(same[[y for y in same.index if y >= ya - 10]].dropna()),
                    "pct_all": pct(allv), "pct_all_10y": pct(H[[y for y in yrs if y >= ya - 10]].stack().values),
                    "median_same_time": float(same.median()), "avg5_same_time": float(same[last5].mean()),
                    "ly_same_time": float(same.get(ya - 1)) if (ya - 1) in same.index and not pd.isna(same.get(ya - 1)) else None,
                    "min_same_time": float(same.min()), "max_same_time": float(same.max()), "years": [int(yrs[0]), int(yrs[-1])], "n_years": int(same.notna().sum()),
                    "bands": {q: [[int(w), round(float(v), 4)] for w, v in H.quantile(q / 100, axis=1).dropna().items()] for q in (10, 25, 50, 75, 90)},
                    "avg5": [[int(w), round(float(v), 4)] for w, v in H[last5].mean(axis=1).dropna().items()],
                    "last_year": [[int(w), round(float(v), 4)] for w, v in H[ya - 1].dropna().items()] if (ya - 1) in H else [],
                    "current": [[int(w), round(float(v), 4)] for w, v in cur.items()]})
    return out


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if (math.isnan(o) or math.isinf(o)) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def build(sym):
    p = ROOT / "data" / "ohlc" / f"{sym}.csv"
    if not p.exists():
        return None
    u, dp = UNITS[sym]
    d = pd.read_csv(p, parse_dates=["date"])
    out = {"sym": sym, "name": NAMES[sym], "unit": u, "dp": dp, "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "series": [],
           "note": "Daily bars from TradingView (CME Group). The continuous series rolls between contracts, so gaps at rolls are price jumps, not moves."}
    frames = {}
    order = ["cont"] + sorted([s for s in d.series.unique() if s != "cont"], key=lambda c: (code_parts(sym, c)[1], CODES.index(code_parts(sym, c)[0])))
    for s in order:
        h = d[d.series == s].set_index("date").sort_index().rename(columns=str.title)[["Open", "High", "Low", "Close", "Volume"]]
        h = h[(h.Close > 0)].copy()
        for c in ("Open", "High", "Low"):
            h[c] = h[c].where(h[c] > 0)
        h["Open"] = h.Open.fillna(h.Close.shift()).fillna(h.Close)
        h["High"] = h[["High", "Open", "Close"]].max(axis=1)
        h["Low"] = h[["Low", "Open", "Close"]].min(axis=1)
        if s != "cont" and h.index[-1] < d.date.max() - pd.Timedelta(days=5):
            continue  # expired or not trading
        if len(h) < 60:
            continue
        L, y = (None, None) if s == "cont" else code_parts(sym, s)
        label = "Continuous front" if s == "cont" else f"{MNAME[L]} {y % 100:02d}"
        frames[s] = h
        out["series"].append({"label": label, "ticker": s, "expiry": None if s == "cont" else s,
                              "bars": [[i.strftime("%Y-%m-%d"), r.Open, r.High, r.Low, r.Close, int(r.Volume or 0)] for i, r in h.iterrows()],
                              "analysis": analyse(h, "Continuous front month" if s == "cont" else label, u=u, dp=dp)})
    live = [s for s in order if s != "cont" and s in frames]
    # make the first live contract with real volume the default view
    vol = {s: frames[s].Volume.tail(10).mean() for s in live}
    out["default"] = next((s for s in live if vol[s] >= 0.25 * max(vol.values())), live[0] if live else "cont") if live else "cont"
    for a, b in zip(live, live[1:4]):
        j = frames[a].join(frames[b], how="inner", lsuffix="_a", rsuffix="_b")
        if len(j) < 60:
            continue
        c = (j.Close_a - j.Close_b).round(4)
        o = c.shift().fillna(c)
        sp = pd.DataFrame({"Open": o, "High": pd.concat([o, c], axis=1).max(axis=1), "Low": pd.concat([o, c], axis=1).min(axis=1), "Close": c, "Volume": j.Volume_b.fillna(0)})
        lab = f"{MNAME[code_parts(sym, a)[0]]} {code_parts(sym, a)[1] % 100:02d}/{MNAME[code_parts(sym, b)[0]]} {code_parts(sym, b)[1] % 100:02d} spread"
        out["series"].append({"label": lab, "ticker": f"{a}-{b}", "expiry": a, "kind": "spread",
                              "bars": [[i.strftime("%Y-%m-%d"), r.Open, r.High, r.Low, r.Close, int(r.Volume)] for i, r in sp.iterrows()],
                              "analysis": analyse(sp, lab, spread=True, u=u, dp=dp)})
    # seasonality from per-contract closes, extended with the live contracts' latest bars
    cp = ROOT / "data" / "contracts" / f"{sym}.csv"
    if cp.exists():
        k = pd.read_csv(cp, parse_dates=["date"]).dropna(subset=["close"])
        k = k[k.close > 0]
        closes = {c: g.set_index("date").close.sort_index() for c, g in k.groupby("contract")}
        for s in live:
            closes[s] = pd.concat([closes.get(s, pd.Series(dtype=float)), frames[s].Close]).groupby(level=0).last().sort_index()
        today = d.date.max()
        last_dates = {c: s.index.max() for c, s in closes.items() if s.index.max() < today - pd.Timedelta(days=10)}
        try:
            out["seasonal"] = season_rows(sym, live, last_dates, closes)
        except Exception as e:
            import traceback; traceback.print_exc()
    return clean(out)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    syms = sys.argv[1:] or list(UNITS)
    for s in syms:
        try:
            o = build(s)
        except Exception as e:
            import traceback; traceback.print_exc(); o = None
        if not o:
            print(s, "no ohlc")
            continue
        (OUT / f"{s}.json").write_text(json.dumps(o, separators=(",", ":"), ensure_ascii=False))
        a = next((x for x in o["series"] if x["ticker"] == o["default"]), o["series"][0])["analysis"]
        print(s, len(o["series"]), "series, default", o["default"], a["last"], a["trend"], a["rating_daily"]["overall"], "seasonal rows", len(o.get("seasonal") or []))
