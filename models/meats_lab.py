#!/usr/bin/env python3
"""Meats strategy lab: lean hogs (cash-settled to the CME Lean Hog Index), feeder cattle (cash-settled to the CME Feeder
Cattle Index) and live cattle (physical delivery, converges to the 5-area fed steer price).

Same discipline as the dairy lab: weekly decisions on Wednesday settlements, positions marked to market at settlements
until the next decision or the contract's final settlement, half of a 2-tick bid-ask charged on every change of
position, walk-forward models only (each year's model fitted on contracts that expired before it). Daily-rule ideas
(breakouts with stops) run on daily settlements.

Ideas tested
  convergence  HE, LE: settlement estimate (cash now x a seasonal, momentum and packer-margin model) vs futures
  premium      LE, GF, HE: long the contracts in their last weeks (the live cattle convergence premium)
  trend4       4-week futures trend, every contract up to 6 months out
  seasonal     same contract, same calendar weeks, prior 5-10 years
  breakout     20-day breakout, 10-day exit, 2x ATR trailing stop
  feed margin  GF vs the cattle feeding margin (LE deferred - feeder - corn)
Writes data/livestock/derived/meats_lab.json and playbook_hogs.json / playbook_cattle.json (the Outlook trade playbooks).
Runs nightly (a few seconds).
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from futures_io import load_contracts  # noqa: E402
from hogs import lean_hog_index  # noqa: E402

RAW = ROOT / "data" / "livestock" / "raw"
OUT = ROOT / "data" / "livestock" / "derived"
SPEC = {"HE": (400, 0.05, "Lean hogs", "¢/lb"), "LE": (400, 0.05, "Live cattle", "$/cwt"), "GF": (500, 0.05, "Feeder cattle", "$/cwt")}
START = pd.Timestamp("2012-01-01")
SPLITS = (("2012_19", "2012-01-01", "2020-01-01"), ("2020_23", "2020-01-01", "2024-01-01"), ("2024_26", "2024-01-01", "2100-01-01"))


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


# ───────────────────────── futures ─────────────────────────
def expiry_rule(s, m):
    first, last = m.start_time, m.end_time.normalize()
    bd = pd.bdate_range(first, last)
    if s == "HE":
        return bd[min(9, len(bd) - 1)]
    if s == "LE":
        return bd[-1]
    th = [d for d in pd.date_range(first, last) if d.dayofweek == 3]       # GF: last Thursday
    return th[-1]


class Fut:
    def __init__(self, s, to_expiry=False):
        f = load_contracts(s)
        self.s = s
        self.today = f.date.max()
        last = f.groupby("m").date.max()
        self.exp = {m: (d if d < self.today - pd.Timedelta(days=7) else expiry_rule(s, m)) for m, d in last.items()}
        st = f.pivot_table(index="date", columns="m", values="close").sort_index()
        first = f.groupby("m").date.min()
        st = st.ffill()
        for m in st.columns:
            st.loc[(st.index > self.exp[m]) | (st.index < first[m]), m] = np.nan
        self.st = st
        self.idx = st.index
        self.col = {m: i for i, m in enumerate(st.columns)}
        self.arr = st.values
        # where a position ends: final settlement for the cash-settled contracts; for live cattle (physical delivery,
        # longs can be assigned from the first business day of the month) the last business day before the month
        self.end = {m: (e if s != "LE" or to_expiry else pd.bdate_range(m.start_time - pd.Timedelta(days=10), m.start_time - pd.Timedelta(days=1))[-1]) for m, e in self.exp.items()}
        self.fin = {m: float(self.px(m, self.end[m])) for m in last.index if self.end[m] < self.today - pd.Timedelta(days=3)}

    def px(self, m, t):
        i = self.idx.searchsorted(t, side="right") - 1
        return self.arr[i, self.col[m]] if i >= 0 and m in self.col else np.nan

    def live(self, t, lo_days=0, hi_days=200):
        return [m for m, e in self.end.items() if lo_days < (e - t).days <= hi_days and m in self.col and not np.isnan(self.px(m, t))]


# ───────────────────────── cash ─────────────────────────
def cash_hogs():
    d = lean_hog_index().dropna(subset=["index"])
    known = d.reset_index().groupby("report").agg(v=("index", "last"), cash_date=("date", "last")).sort_index()
    cal = d["index"].resample("D").last().ffill()
    c = pd.read_csv(RAW / "pk602_pork_cutout" / "cutout_and_primal_values.csv", low_memory=False)
    c["t"] = pd.to_datetime(c.report_date)
    c = c.assign(v=num(c.pork_carcass)).dropna(subset=["v"]).sort_values("t").drop_duplicates("t", keep="last").set_index("t").v
    return known, cal, c


def cash_cattle():
    d = pd.read_csv(RAW / "ct150_5area_weekly" / "detail.csv", low_memory=False)
    d = d[(d.class_description == "STEER") & (d.selling_basis_description == "LIVE FOB") & (d.grade_description == "Total all grades")].copy()
    d["t"] = pd.to_datetime(d.report_date)
    d["v"] = num(d.weighted_avg_price)
    d = d.dropna(subset=["v"]).sort_values("t").drop_duplicates("t", keep="last")
    known = d.set_index("t")[["v"]].assign(cash_date=lambda x: x.index - pd.Timedelta(days=7))
    cal = d.set_index("t").v.resample("D").last().ffill()
    b = pd.read_csv(RAW / "xb403_boxed_beef" / "current_cutout_values.csv", low_memory=False)
    b["t"] = pd.to_datetime(b.report_date)
    b = b.assign(v=num(b.choice_600_900_current)).dropna(subset=["v"]).sort_values("t").drop_duplicates("t", keep="last").set_index("t").v
    return known, cal, b


def asof(series_index, values, t):
    i = series_index.searchsorted(t, side="right") - 1
    return values[i] if i >= 0 else np.nan


def panel(Fs, s, known, cal, cut):
    """Every (Wednesday, open contract up to 26 weeks out) with cash-side features and the realized log(final / cash)."""
    rows = []
    kidx, kv = known.index, known.v.values
    cidx, cv = cut.index, cut.values
    cut_ratio = np.log(cut.reindex(cal.index).ffill() / cal).dropna()
    cr_mean = cut_ratio.rolling(365, min_periods=200).mean()
    for t in WED:
        I0 = asof(kidx, kv, t)
        if np.isnan(I0):
            continue
        cd = t - pd.Timedelta(days=1)
        cr = asof(cut_ratio.index, cut_ratio.values, cd) - asof(cr_mean.index, cr_mean.values, cd) if len(cut_ratio) else np.nan
        i14 = asof(cal.index, cal.values, cd - pd.Timedelta(days=14))
        for m in Fs.live(t, 0, 182):
            E = Fs.end[m]
            F = Fs.px(m, t)
            sea = []
            for k in range(1, 6):
                a, b = asof(cal.index, cal.values, cd - pd.DateOffset(years=k)), asof(cal.index, cal.values, E - pd.DateOffset(years=k))
                if a > 0 and b > 0:
                    sea.append(math.log(b / a))
            rows.append({"t": t, "sym": s, "m": m, "E": E, "h": (E - t).days, "F": F, "I0": I0, "basis": math.log(F / I0),
                         "seas": float(np.median(sea)) if len(sea) >= 3 else np.nan, "mom": math.log(I0 / i14) if i14 > 0 else np.nan,
                         "cut": cr, "y": math.log(Fs.fin[m] / I0) if m in Fs.fin else np.nan})
    P = pd.DataFrame(rows)
    P["cut"] = P.cut.fillna(0.0)
    return P.dropna(subset=["seas", "mom"])


def walk_forward(P, feats, alpha=1.0):
    """Ridge on standardized features, refit every January on contracts that expired before it."""
    pred = pd.Series(np.nan, index=P.index)
    for y in sorted(P.t.dt.year.unique()):
        cut = pd.Timestamp(f"{y}-01-01")
        tr = P[(P.E < cut) & P.y.notna()]
        te = P.t.dt.year == y
        if len(tr) < 200:
            continue
        X = tr[feats].values
        mu, sd = X.mean(0), X.std(0) + 1e-9
        Z = (X - mu) / sd
        A = np.c_[np.ones(len(Z)), Z]
        R = np.eye(A.shape[1]) * alpha; R[0, 0] = 0
        b = np.linalg.solve(A.T @ A + R, A.T @ tr.y.values)
        pred[te] = np.c_[np.ones(te.sum()), (P.loc[te, feats].values - mu) / sd] @ b
    return pred


# ───────────────────────── engine ─────────────────────────
def run(FS, book, start=START):
    days = [t for t in WED if t >= start]
    prev, rows, trades, open_ = {}, [], [], {}
    for i, t in enumerate(days[:-1]):
        nxt = days[i + 1]
        pos = book(t)
        cost = sum(abs(pos.get(k, 0) - prev.get(k, 0)) * SPEC[k[0]][1] / 2 * SPEC[k[0]][0] for k in set(pos) | set(prev))
        pnl = 0.0
        for (s, m), w in pos.items():
            Fs = FS[s]
            p0 = Fs.px(m, t)
            if Fs.end[m] <= nxt:
                p1 = Fs.fin.get(m, np.nan)
            else:
                p1 = Fs.px(m, nxt)
            if np.isnan(p0) or np.isnan(p1):
                continue
            d = w * (p1 - p0) * SPEC[s][0]
            pnl += d
            open_[(s, m, np.sign(w))] = open_.get((s, m, np.sign(w)), 0.0) + d
        for k in list(open_):
            s, m, sg = k
            if np.sign(pos.get((s, m), 0)) != sg or FS[s].end[m] <= nxt:
                trades.append(open_.pop(k))
        prev = {k: w for k, w in pos.items() if FS[k[0]].end[k[1]] > nxt}
        rows.append({"t": nxt, "pnl": pnl - cost, "cost": cost, "n": sum(abs(w) for w in pos.values())})
    return pd.DataFrame(rows).set_index("t"), trades


def stats(R, trades):
    x = R.pnl
    if len(x) < 52 or x.std() == 0:
        return None
    eq = x.cumsum()
    dd = float((eq - eq.cummax()).min())
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    ann = x.sum() / yrs
    out = {"weeks": int(len(x)), "ann_usd": int(round(ann)), "sharpe": round(float(x.mean() / x.std() * math.sqrt(52)), 2), "maxdd_usd": int(round(dd)),
           "calmar": round(float(ann / abs(dd)), 2) if dd < 0 else None, "worst_week_usd": int(round(float(x.min()))),
           "avg_lots": round(float(R.n.mean()), 1), "cost_ann_usd": int(round(R.cost.sum() / yrs))}
    if trades:
        tr = np.array(trades)
        w, l = tr[tr > 0], tr[tr < 0]
        out.update({"trades": int(len(tr)), "hit": round(float((tr > 0).mean() * 100), 1),
                    "avg_win_usd": int(round(float(w.mean()))) if len(w) else None, "avg_loss_usd": int(round(float(l.mean()))) if len(l) else None,
                    "payoff": round(float(w.mean() / -l.mean()), 2) if len(w) and len(l) else None})
    for lab, a, b in SPLITS:
        xs = x[(x.index >= a) & (x.index < b)]
        out[f"sharpe_{lab}"] = round(float(xs.mean() / xs.std() * math.sqrt(52)), 2) if len(xs) > 26 and xs.std() > 0 else None
    out["by_year"] = {int(y): int(round(v)) for y, v in x.groupby(x.index.year).sum().items()}
    out["equity"] = [[str(d.date()), int(v)] for d, v in eq.resample("ME").last().items()]
    sp = [out[f"sharpe_{l}"] for l, _, _ in SPLITS if out.get(f"sharpe_{l}") is not None]
    out["min_split"] = min(sp) if sp else None
    return out


# ───────────────────────── idea books ─────────────────────────
def conv_book(P, col, H, thr):
    G = {t: g for t, g in P[P.h <= 7 * H].groupby("t")}
    def book(t):
        g = G.get(t)
        if g is None:
            return {}
        gap = g.I0 * np.exp(g[col]) - g.F
        sel = g[(gap.abs() > thr) & g[col].notna()]
        return {(r.sym, r.m): float(np.sign(gp)) for r, gp in zip(sel.itertuples(), gap[sel.index])}
    return book


def premium_book(FS, s, lo, hi, side=1):
    return lambda t: {(s, m): float(side) for m in FS[s].live(t, 7 * lo, 7 * hi)}


def trend_book(FS, syms, weeks=4, hi_days=182):
    def book(t):
        out = {}
        for s in syms:
            Fs = FS[s]
            for m in Fs.live(t, 7, hi_days):
                p0, p1 = Fs.px(m, t - pd.Timedelta(weeks=weeks)), Fs.px(m, t)
                if p0 > 0 and abs(p1 - p0) > SPEC[s][1]:
                    out[(s, m)] = float(np.sign(p1 - p0))
        return out
    return book


def seasonal_book(FS, syms, weeks=4, min_years=5, agree=0.7):
    def book(t):
        out = {}
        for s in syms:
            Fs = FS[s]
            for m in Fs.live(t, 14, 182):
                r = []
                for k in range(1, 11):
                    mk = m - 12 * k
                    if mk not in Fs.col:
                        continue
                    a, b = t - pd.DateOffset(years=k), t - pd.DateOffset(years=k) + pd.Timedelta(weeks=weeks)
                    if b >= Fs.end[mk]:
                        continue
                    p0, p1 = Fs.px(mk, a), Fs.px(mk, b)
                    if p0 > 0 and p1 > 0:
                        r.append(math.log(p1 / p0))
                if len(r) >= min_years:
                    up = np.mean(np.array(r) > 0)
                    if (up >= agree or up <= 1 - agree) and abs(np.mean(r)) * Fs.px(m, t) > 2 * SPEC[s][1]:
                        out[(s, m)] = 1.0 if up >= agree else -1.0
        return out
    return book


def margin_series(FS, ZC):
    """Cattle feeding margin, $/head: 13.5 cwt x live cattle ~5 months after the feeder month - 7.5 cwt x feeders - 65 bu corn."""
    rows = []
    for t in WED:
        gf = sorted(FS["GF"].live(t, 14, 120))
        if not gf:
            continue
        m = gf[0]
        le = sorted(x for x in FS["LE"].live(t, 120, 260))
        zc = sorted(ZC.live(t, 14, 120))
        if not le or not zc:
            continue
        g, l, c = FS["GF"].px(m, t), FS["LE"].px(le[0], t), ZC.px(zc[0], t)
        rows.append({"t": t, "m": m, "margin": 13.5 * l - 7.5 * g - 0.65 * c})
    M = pd.DataFrame(rows).set_index("t")
    M["z"] = (M.margin - M.margin.rolling(156, min_periods=104).mean()) / M.margin.rolling(156, min_periods=104).std()
    return M


def margin_book(M, z=1.0):
    def book(t):
        if t not in M.index or np.isnan(M.z.get(t, np.nan)):
            return {}
        r = M.loc[t]
        return {("GF", r.m): float(np.sign(r.z))} if abs(r.z) > z else {}
    return book


def breakout(Fs, n_in=20, n_out=10, atr_mult=2.0, min_days=45):
    """Daily rule on the nearest contract at least `min_days` from expiry; exits on the n_out-day opposite breakout, the
    trailing stop, or 10 days before expiry. One lot."""
    s = Fs.s
    pos, entry, stop, m_held, edate = 0, None, None, None, None
    pnl_d, trades, cur, state = [], [], 0.0, {}
    st = Fs.st
    for t in st.index:
        if t < START - pd.Timedelta(days=60):
            continue
        cand = sorted(m for m, e in Fs.end.items() if (e - t).days >= min_days and m in Fs.col)
        if not cand:
            continue
        if m_held is None or (pos == 0 and m_held != cand[0]):
            m_held = cand[0]
        ser = st[m_held].loc[:t].dropna()
        if len(ser) < n_in + 2:
            pnl_d.append((t, 0.0)); continue
        c, pc = ser.iloc[-1], ser.iloc[-2]
        day = pos * (c - pc) * SPEC[s][0] if pos else 0.0
        cur += day
        atr = ser.diff().abs().tail(20).mean()
        hi, lo = ser.iloc[-n_in - 1:-1].max(), ser.iloc[-n_in - 1:-1].min()
        xhi, xlo = ser.iloc[-n_out - 1:-1].max(), ser.iloc[-n_out - 1:-1].min()
        expiring = (Fs.end[m_held] - t).days < 10
        cost = 0.0
        if pos:
            if (pos > 0 and (c <= stop or c < xlo)) or (pos < 0 and (c >= stop or c > xhi)) or expiring:
                cost = SPEC[s][1] / 2 * SPEC[s][0]
                trades.append(cur - cost); cur = 0.0; pos = 0
        if not pos and not expiring:
            if c > hi:
                pos, entry, stop, edate = 1, c, c - atr_mult * atr, t
            elif c < lo:
                pos, entry, stop, edate = -1, c, c + atr_mult * atr, t
            if pos:
                cost += SPEC[s][1] / 2 * SPEC[s][0]; cur -= SPEC[s][1] / 2 * SPEC[s][0]
        elif pos > 0:
            stop = max(stop, c - atr_mult * atr)
        elif pos < 0:
            stop = min(stop, c + atr_mult * atr)
        pnl_d.append((t, day - cost))
        state = {"date": str(t.date()), "month": str(m_held), "close": float(c), "pos": int(pos), "entry": float(entry) if pos else None,
                 "entry_date": str(edate.date()) if pos else None, "stop": float(stop) if pos else None,
                 "buy_above": float(ser.iloc[-n_in:].max()), "sell_below": float(ser.iloc[-n_in:].min()),
                 "exit_long_below": float(ser.iloc[-n_out:].min()), "exit_short_above": float(ser.iloc[-n_out:].max()), "atr": float(atr),
                 "open_pnl_usd": int(round(pos * (c - entry) * SPEC[s][0])) if pos else 0}
    d = pd.Series(dict(pnl_d))
    wk = d.resample("W-WED").sum()
    R = pd.DataFrame({"pnl": wk, "cost": 0.0, "n": 1.0})
    return R[R.index >= START], trades, state


# ───────────────────────── main ─────────────────────────
WED = None
MODEL_TXT = {"rw": "no change", "sea": "its median path over the same weeks of the last five years", "ridge": "a walk-forward model of seasonality, momentum and the packer margin",
             "ridge_b": "a walk-forward model that also uses the futures basis"}


def main():
    global WED
    FS = {s: Fut(s) for s in SPEC}
    ZC = Fut.__new__(Fut)
    try:
        ZC.__init__("ZC")
    except Exception:
        ZC = None
    today = max(F.today for F in FS.values())
    WED = pd.DatetimeIndex(sorted(set(pd.date_range("2007-01-03", today, freq="W-WED")) | {today}))
    res, books, notes = {}, {}, {}

    def add(key, book, **meta):
        R, tr = run(FS, book)
        res[key] = {**meta, **(stats(R, tr) or {})}
        books[key] = book

    # convergence panels
    kh, ch, cuth = cash_hogs()
    kc, cc, cutc = cash_cattle()
    PH = panel(FS["HE"], "HE", kh, ch, cuth)
    PC = panel(FS["LE"], "LE", kc, cc, cutc)
    for P in (PH, PC):
        P["rw"] = 0.0
        P["sea"] = P.seas
        P["mom_h"], P["cut_h"] = P.mom * P.h / 91, P.cut * P.h / 91      # scale with the horizon: a 2-week hold should not get a 6-month move
        P["ridge"] = walk_forward(P, ["seas", "mom_h", "cut_h"])
        P["ridge_b"] = walk_forward(P, ["seas", "mom_h", "cut_h", "basis"])
    acc = {}
    for s, P in (("HE", PH), ("LE", PC)):
        q = P[P.y.notna() & P.ridge.notna() & (P.t >= START)]
        acc[s] = {}
        for H in (2, 6, 13, 26):
            x = q[q.h <= 7 * H]
            if not len(x):
                continue
            fut_err = (np.log(x.F / x.I0) - x.y).abs().mean()
            acc[s][f"le_{H}w"] = {"n": int(len(x)), "futures_mae_pct": round(float(fut_err * 100), 2),
                                  **{f"{c}_mae_pct": round(float((x[c] - x.y).abs().mean() * 100), 2) for c in ("rw", "sea", "ridge", "ridge_b")}}
        for col in ("rw", "sea", "ridge", "ridge_b"):
            for H in (2, 6, 13):
                for thr in (0.5, 1.0, 2.0):
                    add(f"conv_{s}_{col}_{H}w_{thr}", conv_book(P, col, H, thr), group="convergence", sym=s, model=col, window=H, threshold=thr)
    # premium (long the last weeks)
    for s in SPEC:
        for lo, hi in ((0, 4), (0, 8), (0, 13), (4, 13)):
            add(f"prem_{s}_{lo}_{hi}", premium_book(FS, s, lo, hi), group="premium", sym=s, window=f"{lo}-{hi}")
    LEX = {"LE": Fut("LE", to_expiry=True)}
    for lo, hi in ((0, 4), (0, 8)):
        R, tr = run(LEX, premium_book(LEX, "LE", lo, hi))
        res[f"premx_LE_{lo}_{hi}"] = {"group": "premium (held through delivery month)", "sym": "LE", "window": f"{lo}-{hi}", **(stats(R, tr) or {})}
    for s in SPEC:
        add(f"trend_{s}", trend_book(FS, [s]), group="trend", sym=s)
        add(f"seas_{s}", seasonal_book(FS, [s]), group="seasonal", sym=s)
    if ZC is not None:
        M = margin_series(FS, ZC)
        for z in (1.0, 1.5):
            add(f"margin_GF_{z}", margin_book(M, z), group="feed margin", sym="GF", z=z)
    bstate = {}
    for s in SPEC:
        R, tr, stt = breakout(FS[s])
        res[f"breakout_{s}"] = {"group": "breakout", "sym": s, **(stats(R, tr) or {})}
        bstate[s] = stt

    # summary table (no equity) and the best of each family by the weakest period
    table = [{"key": k, **{kk: v for kk, v in r.items() if kk not in ("equity", "by_year")}} for k, r in res.items() if r.get("sharpe") is not None]
    table.sort(key=lambda r: -(r.get("min_split") if r.get("min_split") is not None else -9))
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "as_of": str(today.date()), "start": str(START.date()),
           "accuracy": acc, "table": table, "detail": {k: res[k] for k in [t["key"] for t in table[:25]]}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "meats_lab.json").write_text(json.dumps(out, default=str))

    # ── playbooks ──
    def st(key):
        r = res.get(key) or {}
        return {k: r.get(k) for k in ("sharpe", "sharpe_2012_19", "sharpe_2020_23", "sharpe_2024_26", "hit", "payoff", "ann_usd", "maxdd_usd", "calmar",
                                      "avg_win_usd", "avg_loss_usd", "trades", "avg_lots", "worst_week_usd")} if r else None

    def best(prefix):
        c = [t for t in table if t["key"].startswith(prefix)]
        return c[0]["key"] if c else None

    def pos_rows(key, extra=None):
        out_ = []
        for (s, m), w in books[key](today).items():
            Fs = FS[s]
            r = {"contract": f"{SPEC[s][2]} {m.strftime('%b %Y')}", "sym": s, "month": str(m), "side": "long" if w > 0 else "short",
                 "futures": round(float(Fs.px(m, today)), 3), "unit": SPEC[s][3], "settles": str(Fs.end[m].date()) + (" (exit before delivery month)" if s == "LE" else "")}
            if extra:
                r.update(extra(s, m))
            out_.append(r)
        return out_

    def conv_extra(P, col):
        g = P[P.t == today].set_index("m")
        def f(s, m):
            if m not in g.index:
                return {}
            r = g.loc[m]
            est = float(r.I0 * math.exp(r[col]))
            return {"estimate": round(est, 2), "edge_usd": int(round(abs(est - r.F) * SPEC[s][0])), "cost_usd": int(SPEC[s][1] * SPEC[s][0])}
        return f

    def verdict(k):
        r = res.get(k) or {}
        ms = r.get("min_split")
        if ms is None:
            return "Not enough history to judge."
        if ms >= 0.5:
            return "Worked in every period tested (2012-19, 2020-23, 2024-26)."
        if ms >= 0.3:
            return "Positive in every period tested, but weaker in at least one; trade it small."
        if ms >= 0:
            return "Close to zero in at least one period tested, so no reliable edge; shown for reference, not as a trade."
        return "Lost money in at least one period tested; shown for reference, not as a trade."

    def bk_card(s, name):
        stt = bstate[s]
        pos = []
        if stt.get("pos"):
            pos.append({"contract": f"{SPEC[s][2]} {pd.Period(stt['month'], 'M').strftime('%b %Y')}", "side": "long" if stt["pos"] > 0 else "short",
                        "entry_price": round(stt["entry"], 3), "entry_date": stt["entry_date"], "futures": round(stt["close"], 3), "stop": round(stt["stop"], 3),
                        "unit": SPEC[s][3], "open_pnl_usd": stt["open_pnl_usd"],
                        "exit_signal": (f"close on a settle below {stt['exit_long_below']:.3f} or the stop {stt['stop']:.3f}" if stt["pos"] > 0 else
                                        f"close on a settle above {stt['exit_short_above']:.3f} or the stop {stt['stop']:.3f}")})
        return {"key": f"breakout_{s}", "name": f"Breakout with trailing stop: {name}", "type": "Trend, small losses", "stats": st(f"breakout_{s}"),
                "thesis": "Wins less than half the time; stops keep losers small and the occasional long run pays for them. " + verdict(f"breakout_{s}"),
                "entry": f"Daily, on the nearest contract at least 45 days from expiry ({stt.get('month', '–')}): buy on a settle above the 20-day high (now {stt.get('buy_above', float('nan')):.3f}); sell on a settle below the 20-day low (now {stt.get('sell_below', float('nan')):.3f}).",
                "exit": "Long: a settle below the 10-day low or the trailing stop (2x the 20-day average daily move below the best close). Short: the mirror. Flat 10 days before expiry.",
                "risk": f"Average daily move {stt.get('atr', float('nan')):.3f} {SPEC[s][3]} = ${stt.get('atr', 0) * SPEC[s][0]:,.0f} per lot; the stop sits about twice that away.",
                "track": ["Daily settlement vs the 20-day high/low and the stop (this page, nightly)"],
                "levels": {k: stt.get(k) for k in ("date", "month", "close", "buy_above", "sell_below", "exit_long_below", "exit_short_above", "atr")},
                "positions": pos}

    # hogs
    hk = best("conv_HE_")
    hm = res[hk]["model"] if hk else "ridge"
    a2 = acc["HE"].get("le_2w", {})
    hog_trades = [
        {"key": hk, "name": "Cash-index convergence (lean hogs)", "type": "Cash settlement", "stats": st(hk),
         "thesis": f"Lean hog futures settle on the CME Lean Hog Index, a two-day average of what packers paid. The desk rebuilds the index from USDA's daily report a day before CME posts it and estimates where it will be at expiry (cash now x {'the seasonal path' if hm == 'sea' else 'a walk-forward model of seasonality, momentum and the packer margin' if hm.startswith('ridge') else 'no change'}). Best tested setting: within {res[hk]['window']} weeks of expiry, gap above {res[hk]['threshold']} {SPEC['HE'][3]}. " + verdict(hk) +
                   (f" Accuracy check in the last 2 weeks: futures miss the final index by {a2.get('futures_mae_pct')}% on average, the model by {a2.get(hm + '_mae_pct')}%." if a2 else ""),
         "entry": f"Wednesday after the close: for each hog contract within {res[hk]['window']} weeks of expiry, if the settlement estimate is above the futures by more than {res[hk]['threshold']} {SPEC['HE'][3]}, buy one lot; if below by more than that, sell one.",
         "exit": "Re-check each Wednesday; close when the gap falls back inside the threshold or flips, or hold to final settlement (the index on the 10th business day of the month).",
         "risk": "The index can move several dollars in two weeks around seasonal turns (spring rally, late-summer top); no stop was used in the test.",
         "track": ["USDA LM_HG201 national daily direct hog report (morning) and the desk's index rebuild", "CME Lean Hog Index (posted afternoon, one day behind)", "Pork cutout (LM_PK602) vs the index: the packer margin", "Weekly slaughter and carcass weights"],
         "positions": pos_rows(hk, conv_extra(PH, hm)) if hk else []},
    ]
    pk = best("prem_HE_")
    hog_trades.append({"key": pk, "name": "Expiry drift (lean hogs)", "type": "Risk premium", "stats": st(pk),
                       "thesis": "Checks whether being long hog contracts in their last weeks has paid, as it has for live cattle. " + verdict(pk),
                       "entry": f"Hold one lot long in each hog contract {res[pk]['window']} weeks from expiry.", "exit": "Hold to final settlement.",
                       "risk": "Unhedged long exposure to the cash index.", "track": ["Index vs futures (basis)"], "positions": pos_rows(pk)})
    for key, nm, typ, th, en, ex in (
            ("trend_HE", "4-week futures trend (lean hogs)", "Trend", "Hog prices trend through the seasonal cycle; futures partly inherit that persistence.",
             "Wednesday: one lot per contract up to 6 months out, in the direction of its 4-week change when that change exceeds the cost.", "Flip or flatten when the 4-week change reverses."),
            ("seas_HE", "Seasonal pattern (lean hogs)", "Seasonal", "The same contract has moved the same way over the same 4 calendar weeks in at least 70% of the last 5-10 years.",
             "Wednesday: one lot in the direction of the historical 4-week move, for contracts 2 weeks to 6 months out.", "Re-check weekly; flatten when the pattern no longer qualifies.")):
        hog_trades.append({"key": key, "name": nm, "type": typ, "stats": st(key), "thesis": th + " " + verdict(key), "entry": en, "exit": ex,
                           "risk": "Many positions at once; size small.", "track": ["4-week change and the seasonal table (this page, nightly)"],
                           "positions": pos_rows(key)})
    hog_trades.append(bk_card("HE", "lean hogs"))
    intro_h = ("Lean hogs settle in cash on the CME Lean Hog Index, which the desk rebuilds daily. Unlike dairy, the index is a two-day average, so there is no "
               "monthly average to lock in; the tests below ask whether the cash index, its seasonal path or the packer margin say more than the futures do. "
               "Positions are shown only for ideas that held up in every period tested.")
    for t_ in hog_trades:
        if (res.get(t_["key"]) or {}).get("min_split") is None or res[t_["key"]]["min_split"] < 0.3:
            t_["positions"] = []
            t_["type"] += " · not traded"
    (OUT / "playbook_hogs.json").write_text(json.dumps({"generated": out["generated"], "as_of": out["as_of"], "stats_since": out["start"], "stats_generated": out["generated"],
                                                        "intro": intro_h, "trades": hog_trades}, default=str))

    # cattle
    ck = best("conv_LE_")
    cm = res[ck]["model"] if ck else "ridge"
    lp, gp = best("prem_LE_"), best("prem_GF_")
    cat_trades = [
        {"key": lp, "name": "Live cattle convergence premium", "type": "Risk premium", "stats": st(lp),
         "thesis": ("Live cattle futures have tended to finish above where they traded weeks earlier: feedlots hedge by selling, and buyers are paid to take the other side. "
                    f"But most of that drift arrives in the delivery month itself. Held through the delivery month to expiry, the {res.get('premx_LE_0_8', {}).get('window', '0-8')}-week version "
                    f"has a Sharpe of {res.get('premx_LE_0_8', {}).get('sharpe')} (2012-19 {res.get('premx_LE_0_8', {}).get('sharpe_2012_19')}, 2020-23 {res.get('premx_LE_0_8', {}).get('sharpe_2020_23')}, 2024-26 {res.get('premx_LE_0_8', {}).get('sharpe_2024_26')}); "
                    "that needs an account that can be assigned delivery of live cattle. Exiting before the delivery month, as a speculative account must, leaves the numbers below. " + verdict(lp)),
         "entry": f"Hold one lot long in each live cattle contract {res[lp]['window']} weeks before its contract month begins.",
         "exit": "Close on the last Wednesday before the contract month begins (longs can be assigned delivery from the first business day of the month); the test exits there too.",
         "risk": "Coincides with a long cattle-cycle bull market; a herd-rebuilding price slump would turn it into steady losses.",
         "track": ["5-area weekly fed steer price (LM_CT150, Monday)", "Futures vs cash (basis)", "Cattle on Feed placements and marketings (monthly)", "Boxed beef cutout"],
         "positions": pos_rows(lp)},
        {"key": ck, "name": "Cash convergence (live cattle)", "type": "Delivery convergence", "stats": st(ck),
         "thesis": f"Live cattle are delivered physically, so the expiring contract converges to the 5-area cash price. Estimate: the latest weekly 5-area price moved along {MODEL_TXT.get(cm, cm)}. Best tested setting: within {res[ck]['window']} weeks, gap above {res[ck]['threshold']} $/cwt. " + verdict(ck),
         "entry": f"Wednesday: if the settlement estimate is above the futures by more than {res[ck]['threshold']} $/cwt, buy one lot; below, sell one.",
         "exit": "Re-check weekly; close when the gap closes, and in any case before the contract month begins (delivery period).",
         "risk": "Weekly cash is thin in some weeks; a single week can move $3-5.", "track": ["5-area weekly and daily cash (LM_CT150 / CT100)", "Boxed beef cutout vs cash"],
         "positions": pos_rows(ck, conv_extra(PC, cm))},
        {"key": gp, "name": "Feeder cattle expiry drift", "type": "Risk premium", "stats": st(gp),
         "thesis": "Feeder cattle settle in cash on the CME Feeder Cattle Index; tests whether being long into expiry pays as it does for live cattle. " + verdict(gp),
         "entry": f"Hold one lot long in each feeder contract {res[gp]['window']} weeks from expiry.", "exit": "Hold to final cash settlement (the index on the last Thursday of the month).",
         "risk": "Feeders swing with corn as well as cattle.", "track": ["CME Feeder Cattle Index (daily)", "Corn futures"], "positions": pos_rows(gp)},
    ]
    mk = best("margin_GF_")
    if mk:
        cat_trades.append({"key": mk, "name": "Feeders vs the cattle feeding margin", "type": "Relative value", "stats": st(mk),
                           "thesis": "When finishing cattle is unusually profitable (live cattle 5 months out minus feeders minus corn, against its 3-year range), feedlots bid up feeders; when it is unusually poor, they pull back. " + verdict(mk),
                           "entry": f"Wednesday: buy the nearest feeder contract when the margin is more than {res[mk]['z']} standard deviations above its 3-year average; sell when it is that far below.",
                           "exit": "Close when the margin returns inside the band.", "risk": "A corn shock moves the margin and the feeders together.",
                           "track": ["Feeding margin z-score (this page)", "Corn, live cattle and feeder futures"], "positions": pos_rows(mk)})
    for key, nm in (("trend_LE", "4-week futures trend (live cattle)"), ("trend_GF", "4-week futures trend (feeder cattle)"),
                    ("seas_LE", "Seasonal pattern (live cattle)"), ("seas_GF", "Seasonal pattern (feeder cattle)")):
        cat_trades.append({"key": key, "name": nm, "type": "Trend" if "trend" in key else "Seasonal", "stats": st(key),
                           "thesis": ("Cattle prices move in long cycles; futures inherit part of that persistence. " if "trend" in key else
                                      "The same contract has moved the same way over the same 4 calendar weeks in at least 70% of the last 5-10 years. ") + verdict(key),
                           "entry": "Wednesday: one lot per contract up to 6 months out in the direction of the signal, when the move exceeds the cost.",
                           "exit": "Flip or flatten at the weekly check when the signal changes.", "risk": "Many positions at once; size small.",
                           "track": ["Signals on this page (nightly)"], "positions": pos_rows(key)})
    cat_trades += [bk_card("LE", "live cattle"), bk_card("GF", "feeder cattle")]
    for t_ in cat_trades:
        if (res.get(t_["key"]) or {}).get("min_split") is None or res[t_["key"]]["min_split"] < 0.3:
            t_["positions"] = []
            t_["type"] += " · not traded"
    def grid(sym):
        keep = ("key", "group", "model", "window", "threshold", "sharpe", "sharpe_2012_19", "sharpe_2020_23", "sharpe_2024_26", "hit", "payoff", "ann_usd", "maxdd_usd", "avg_lots")
        return [{k: t_.get(k) for k in keep} for t_ in table if t_.get("sym") in sym][:20]
    intro_c = ("Feeder cattle settle in cash on the CME Feeder Cattle Index; live cattle are delivered and converge to the 5-area fed steer price. "
               "Positions are shown only for ideas that held up in every period tested (2012-19, 2020-23, 2024-26).")
    def conflicts(trs):
        seen = {}
        for t_ in trs:
            for p_ in t_["positions"]:
                seen.setdefault(p_["contract"], set()).add((p_["side"], t_["name"]))
        c = [f"{k}: {' vs '.join(f'{n} says {sd}' for sd, n in sorted(v))}" for k, v in seen.items() if len({sd for sd, _ in v}) > 1]
        return (" Signals disagree on " + "; ".join(c) + ". Running both nets to flat on that contract; the idea that held up best across periods is listed first.") if c else ""
    intro_c += conflicts(cat_trades)
    intro_h += conflicts(hog_trades)
    cat_trades.sort(key=lambda t_: -((res.get(t_["key"]) or {}).get("min_split") or -9))
    hog_trades.sort(key=lambda t_: -((res.get(t_["key"]) or {}).get("min_split") or -9))
    (OUT / "playbook_hogs.json").write_text(json.dumps({"generated": out["generated"], "as_of": out["as_of"], "stats_since": out["start"], "stats_generated": out["generated"],
                                                        "intro": intro_h, "trades": hog_trades, "grid": grid(("HE",)), "accuracy": {"HE": acc["HE"]}}, default=str))
    (OUT / "playbook_cattle.json").write_text(json.dumps({"generated": out["generated"], "as_of": out["as_of"], "stats_since": out["start"], "stats_generated": out["generated"],
                                                          "intro": intro_c, "trades": cat_trades, "grid": grid(("LE", "GF")), "accuracy": {"LE": acc["LE"]}}, default=str))
    for t_ in table[:30]:
        print(f"{t_['key']:28s} sh {t_.get('sharpe')} 12-19 {t_.get('sharpe_2012_19')} 20-23 {t_.get('sharpe_2020_23')} 24-26 {t_.get('sharpe_2024_26')} "
              f"ann {t_.get('ann_usd')} dd {t_.get('maxdd_usd')} hit {t_.get('hit')} pay {t_.get('payoff')} lots {t_.get('avg_lots')}")
    print(json.dumps(acc, indent=0)[:1500])


if __name__ == "__main__":
    main()
