#!/usr/bin/env python3
"""Dairy strategy ideas: the convergence trade explained, variations of it, and low-drawdown / high-payoff strategies.

Uses the weekly decision panel written by models/dairy_lab.py (data/dairy/derived/dairy_panel.csv.gz: every open
contract month on each NDPSR release day since 2013 with walk-forward forecasts) and CME settlements on exchange
trade dates (futures_io). Every idea is traded the same way: positions set on the decision day at the settlement,
marked to market at settlements until the next decision day (or to final settlement), half a bid-ask spread charged
on every change of position. Daily-rule ideas (breakouts with stops) run on daily settlements of the second-month
contract. Writes data/dairy/derived/dairy_ideas.json.
"""
import json, math, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from futures_io import load_contracts  # noqa: E402
from dairy_class import load_class_prices  # noqa: E402
from dairy_arb import targets  # noqa: E402

SPEC = {"DC": ("class3", 1, 2000, 0.05, "Class III milk"), "GDK": ("class4", 1, 2000, 0.10, "Class IV milk"), "CSC": ("cheese", 1, 20000, 0.005, "Cheese"),
        "CB": ("butter", 100, 200, 0.5, "Butter"), "GNF": ("ndm", 100, 440, 0.5, "Nonfat dry milk"), "DY": ("whey", 100, 440, 0.5, "Dry whey")}
START = pd.Timestamp("2019-06-01")      # CME spot history (convergence ideas) starts late 2018


def settle_lookup(F):
    out = {}
    for s, f in F.items():
        st = f.pivot_table(index="date", columns="m", values="close").sort_index().ffill()
        out[s] = (st.index, {m: i for i, m in enumerate(st.columns)}, st.values)
    return out


def px(L, s, m, t):
    idx, cpos, arr = L[s]
    i = idx.searchsorted(t, side="right") - 1
    return arr[i, cpos[m]] if i >= 0 and m in cpos else np.nan


def run_weekly(P, L, T, book, label):
    """book(g) -> {(sym, month): weight} for one decision day's panel rows g. Returns weekly $ P&L series and trade log."""
    days = sorted(P.t.unique())
    prev = {}
    rows, trades = [], []
    open_ = {}
    for i, t in enumerate(days):
        nxt = days[i + 1] if i + 1 < len(days) else None
        pos = book(P[P.t == t])
        cost = sum(abs(pos.get(k, 0) - prev.get(k, 0)) * SPEC[k[0]][3] / 2 * SPEC[k[0]][2] for k in set(pos) | set(prev))
        pnl = 0.0
        for (s, m), w in pos.items():
            p0 = px(L, s, m, t)
            if np.isnan(p0):
                continue
            ann = T.ann.get(m) if m in T.index else None
            if nxt is not None and (ann is None or pd.isna(ann) or ann > nxt):
                p1 = px(L, s, m, nxt)
            elif ann is not None and pd.notna(ann) and pd.notna(T.loc[m, SPEC[s][0]]):
                p1 = T.loc[m, SPEC[s][0]] * SPEC[s][1]
            else:
                continue
            if not np.isnan(p1):
                d = w * (p1 - p0) * SPEC[s][2]
                pnl += d
                open_.setdefault((s, m, np.sign(w)), 0.0)
                open_[(s, m, np.sign(w))] += d
        # close trades whose position ended
        for k in list(open_):
            s, m, sg_ = k
            if np.sign(pos.get((s, m), 0)) != sg_ or (nxt is not None and m in T.index and pd.notna(T.ann.get(m)) and T.ann.get(m) <= nxt):
                trades.append(open_.pop(k))
        prev = {k: w for k, w in pos.items() if not (k[1] in T.index and pd.notna(T.ann.get(k[1])) and nxt is not None and T.ann.get(k[1]) <= nxt)}
        rows.append({"t": t, "pnl": pnl - cost, "cost": cost, "n": sum(abs(w) for w in pos.values())})
    R = pd.DataFrame(rows).set_index("t")
    return R, trades


def stats(R, trades=None):
    x = R.pnl
    if len(x) < 30 or x.std() == 0:
        return None
    eq = x.cumsum()
    dd = float((eq - eq.cummax()).min())
    yrs = (x.index[-1] - x.index[0]).days / 365.25
    ann = x.sum() / yrs
    out = {"weeks": int(len(x)), "ann_usd": int(round(ann)), "sharpe": round(float(x.mean() / x.std() * math.sqrt(52)), 2), "maxdd_usd": int(round(dd)),
           "calmar": round(float(ann / abs(dd)), 2) if dd < 0 else None, "worst_week_usd": int(round(float(x.min()))), "best_week_usd": int(round(float(x.max()))),
           "skew": round(float(x.skew()), 2), "avg_lots": round(float(R.n.mean()), 1), "cost_ann_usd": int(round(R.cost.sum() / yrs))}
    if trades:
        tr = np.array(trades)
        w, l = tr[tr > 0], tr[tr < 0]
        out.update({"trades": int(len(tr)), "hit": round(float((tr > 0).mean() * 100), 1),
                    "avg_win_usd": int(round(float(w.mean()))) if len(w) else None, "avg_loss_usd": int(round(float(l.mean()))) if len(l) else None,
                    "payoff": round(float(w.mean() / -l.mean()), 2) if len(w) and len(l) else None})
    for lab, a, b in (("2020_23", "2020-01-01", "2024-01-01"), ("2024_26", "2024-01-01", "2100-01-01")):
        xs = x[(x.index >= a) & (x.index < b)]
        out[f"sharpe_{lab}"] = round(float(xs.mean() / xs.std() * math.sqrt(52)), 2) if len(xs) > 20 and xs.std() > 0 else None
        out[f"ann_{lab}"] = int(round(xs.sum() / max((xs.index[-1] - xs.index[0]).days / 365.25, 0.25))) if len(xs) > 20 else None
    out["by_year"] = {int(y): int(round(v)) for y, v in x.groupby(x.index.year).sum().items()}
    out["equity"] = [[str(d.date()), int(v)] for d, v in eq.resample("ME").last().items()]
    return out


def daily_breakout(F, T, s, n_in=20, n_out=10, atr_mult=2.0, h_target=2):
    """Daily rule on the contract ~h_target months out (rolled monthly): enter on an n_in-day closing breakout, exit on an
    n_out-day opposite breakout or a stop atr_mult x 20-day ATR (close-to-close) from entry. One contract."""
    f = F[s]
    dates = sorted(f.date.unique())
    st = f.pivot_table(index="date", columns="m", values="close").sort_index()
    pos, entry, stop, m_held = 0, None, None, None
    pnl_d, trades, cur = [], [], 0.0
    for t in st.index:
        if t < pd.Timestamp("2013-01-01"):
            continue
        mt = t.to_period("M") + h_target
        if m_held is None or (m_held != mt and pos == 0):
            m_held = mt
        if m_held not in st.columns:
            pnl_d.append((t, 0.0)); continue
        ser = st[m_held].loc[:t].dropna()
        if len(ser) < n_in + 2:
            pnl_d.append((t, 0.0)); continue
        c = ser.iloc[-1]; prev_c = ser.iloc[-2]
        day = pos * (c - prev_c) * SPEC[s][2] if pos else 0.0
        cur += day
        atr = ser.diff().abs().tail(20).mean()
        hi, lo = ser.iloc[-n_in - 1:-1].max(), ser.iloc[-n_in - 1:-1].min()
        xhi, xlo = ser.iloc[-n_out - 1:-1].max(), ser.iloc[-n_out - 1:-1].min()
        ann = T.ann.get(m_held) if m_held in T.index else None
        expiring = ann is not None and pd.notna(ann) and (ann - t).days < 10
        cost = 0.0
        if pos:
            hit_stop = (pos > 0 and c <= stop) or (pos < 0 and c >= stop)
            exit_ = hit_stop or (pos > 0 and c < xlo) or (pos < 0 and c > xhi) or expiring
            if exit_:
                cost = SPEC[s][3] / 2 * SPEC[s][2]
                trades.append(cur - cost); cur = 0.0; pos = 0
        if not pos and not expiring:
            if c > hi:
                pos, entry, stop = 1, c, c - atr_mult * atr
            elif c < lo:
                pos, entry, stop = -1, c, c + atr_mult * atr
            if pos:
                cost += SPEC[s][3] / 2 * SPEC[s][2]; cur -= SPEC[s][3] / 2 * SPEC[s][2]
        elif pos > 0:
            stop = max(stop, c - atr_mult * atr)           # trailing stop
        elif pos < 0:
            stop = min(stop, c + atr_mult * atr)
        pnl_d.append((t, day - cost))
    d = pd.Series(dict(pnl_d))
    wk = d.resample("W-WED").sum()
    R = pd.DataFrame({"pnl": wk, "cost": 0.0, "n": 1.0})
    return R[R.index >= START], trades


def main():
    P = pd.read_csv(ROOT / "data" / "dairy" / "derived" / "dairy_panel.csv.gz", parse_dates=["t"])
    P["m"] = P.m.map(lambda x: pd.Period(x, "M"))
    P = P[P.t >= START]
    T = targets(load_class_prices())
    F = {s: load_contracts(s) for s in SPEC}
    L = settle_lookup(F)
    cost_rel = lambda r: SPEC[r.sym][3] / r.F
    ideas = []

    def add(key, name, how, why, R_tr, risk_note=""):
        R, tr = R_tr
        st = stats(R[R.index >= START], tr)
        if st:
            ideas.append({"key": key, "name": name, "how": how, "why": why, "risk": risk_note, **st})
            print(f"{name[:60]:60s} sharpe {st['sharpe']:5} calmar {st['calmar']} hit {st.get('hit')} payoff {st.get('payoff')} dd {st['maxdd_usd']} ann {st['ann_usd']} 20-23 {st['sharpe_2020_23']} 24-26 {st['sharpe_2024_26']}")

    # 1. the high-Sharpe convergence trade, every contract, up to 2 months out
    def conv(g, hmax=2, mult=1.0, only=None, need_trend=False, late=False):
        pos = {}
        for r in g.itertuples():
            if only and r.sym not in only:
                continue
            if r.h > hmax or pd.isna(r.nc_or_spot):
                continue
            if late and not (r.h == 0 and r.t.day >= 8):
                continue
            if abs(r.nc_or_spot) > mult * cost_rel(r):
                sgn = float(np.sign(r.nc_or_spot))
                if need_trend and np.sign(r.fmom) != sgn:
                    continue
                pos[(r.sym, r.m)] = sgn
        return pos
    add("conv_all", "Convergence: spot nowcast vs futures (all six, up to 2 months out)",
        "Every Wednesday after the USDA weekly report: estimate each contract's settlement from published weeks plus CME spot for the rest; buy one lot if the estimate is above futures by more than the round-trip cost, sell if below; hold until next Wednesday.",
        "The settlement is an average of survey prices that follow CME spot with a 1-2 week lag, so spot already tells you much of the answer; futures in the thinner contracts do not fully price it.",
        run_weekly(P, L, T, conv, "conv"))
    add("conv_butter_whey", "Convergence in butter and dry whey only",
        "Same rule, only the two contracts where it has worked in every period.", "These contracts are thin and the futures curve often anchors on old levels instead of where spot is.",
        run_weekly(P, L, T, lambda g: conv(g, only=("CB", "DY")), "cbdy"))
    add("conv_2x", "Convergence, gap above 2x cost (fewer, stronger trades)", "Same rule, but only when the gap is more than twice the round-trip cost.",
        "Bigger gaps are less likely to be noise.", run_weekly(P, L, T, lambda g: conv(g, mult=2.0), "conv2"))
    add("conv_trend", "Convergence confirmed by the 4-week futures trend", "Take the convergence signal only when the futures have moved the same way over the last 4 weeks.",
        "Agreement between the cash signal and the market's own trend filters out gaps that close the other way.", run_weekly(P, L, T, lambda g: conv(g, need_trend=True), "convt"))
    add("conv_late", "Spot month after the first week is published (lowest risk)",
        "Only the current-month contract, from the 8th of the month on, when at least one weekly print is known; gap above cost.",
        "Once part of the average is locked in, the remaining uncertainty and the daily risk collapse; this is closest to a cash arbitrage.",
        run_weekly(P, L, T, lambda g: conv(g, hmax=0, late=True), "late"), "Small edges per trade; size is limited by liquidity in the expiring month.")

    # 2. calendar spread version: long the cheaper-vs-nowcast month, short the dearer one
    def cal(g):
        pos = {}
        for s in SPEC:
            x = g[(g.sym == s) & g.nc_or_spot.notna()].set_index("h")
            for h in (0, 1):
                if h in x.index and h + 1 in x.index:
                    a, b = x.loc[h], x.loc[h + 1]
                    d = a.nc_or_spot - b.nc_or_spot
                    if abs(d) > 2 * SPEC[s][3] / a.F:
                        pos[(s, a.m)] = pos.get((s, a.m), 0) + float(np.sign(d))
                        pos[(s, b.m)] = pos.get((s, b.m), 0) - float(np.sign(d))
        return {k: v for k, v in pos.items() if v}
    add("calendar", "Calendar spread on the nowcast gap", "Within each product, buy the month whose futures sit furthest below its spot nowcast and sell the next month, when the difference beats twice the cost.",
        "A spread removes most of the outright price risk, so drawdowns are smaller; it bets only on the curve being mispriced relative to spot.",
        run_weekly(P, L, T, cal, "cal"), "Two legs, so costs double; thin back months.")

    # 3. trend (persistence) with a trailing stop: low hit rate, large winners
    for s in ("GDK", "CB", "GNF", "DC", "CSC", "DY"):
        R, tr = daily_breakout(F, T, s)
        add(f"breakout_{s}", f"Breakout with trailing stop: {SPEC[s][4]}",
            "Daily: buy when the contract ~2 months out closes at a 20-day high (sell at a 20-day low); exit on a 10-day opposite break or a trailing stop 2x the 20-day average daily move.",
            "Dairy prices trend because the settlement averages slow-moving survey prices; stops keep losers small so a minority of long trends pays for many small losses.", (R, tr),
            "Low hit rate by design; expect strings of small losses.")

    # 4. futures trend (4-week momentum), as in the desk book, for comparison
    def trend(g, hmax=5):
        return {(r.sym, r.m): float(np.sign(r.fmom)) for r in g.itertuples() if r.h <= hmax and pd.notna(r.fmom) and abs(r.fmom) > cost_rel(r)}
    add("trend4", "4-week futures trend (all six, up to 5 months out)", "Hold one lot per contract month in the direction of its 4-week price change.",
        "Persistence in the settlement average carries into the futures.", run_weekly(P, L, T, trend, "trend"))

    ideas.sort(key=lambda x: -(min(x.get("sharpe_2020_23") or -9, x.get("sharpe_2024_26") or -9)))
    # formula arbitrage from dairy_arb (already a backtest of its own)
    arb = json.loads((ROOT / "data" / "dairy" / "derived" / "dairy_arb.json").read_text()).get("formula_arb", {})
    # current signals
    last = P.t.max()
    g = P[P.t == last]
    now = {"date": str(last.date()), "convergence": [{"sym": k[0], "name": SPEC[k[0]][4], "month": str(k[1]), "side": "long" if v > 0 else "short"} for k, v in conv(g).items()],
           "late": [{"sym": k[0], "name": SPEC[k[0]][4], "month": str(k[1]), "side": "long" if v > 0 else "short"} for k, v in conv(g, hmax=0, late=True).items()],
           "calendar": [{"sym": k[0], "name": SPEC[k[0]][4], "month": str(k[1]), "side": "long" if v > 0 else "short"} for k, v in cal(g).items()]}
    # worked examples of the convergence trade: recent butter and whey signals held to final settlement
    ex = []
    for r in P[(P.sym.isin(["CB", "DY"])) & (P.h <= 2) & P.nc_or_spot.notna() & P.y.notna()].sort_values("t").itertuples():
        if abs(r.nc_or_spot) <= cost_rel(r):
            continue
        sgn = np.sign(r.nc_or_spot)
        fin = r.F * math.exp(r.y)
        ex.append({"date": str(r.t.date()), "name": SPEC[r.sym][4], "month": str(r.m), "futures": round(r.F, 3), "nowcast": round(r.F * math.exp(r.nc_or_spot), 3),
                   "side": "long" if sgn > 0 else "short", "settled": round(fin, 3), "usd_to_settlement": int(round(sgn * (fin - r.F) * SPEC[r.sym][2] - SPEC[r.sym][3] * SPEC[r.sym][2]))})
    seen, first = set(), []
    for e in ex:                    # the first signal on each contract month (the natural entry), held to settlement
        k = (e["name"], e["month"])
        if k not in seen:
            seen.add(k); first.append(e)
    examples = first[-12:][::-1]
    fx = pd.DataFrame(first)
    out_ex = {"n": int(len(fx)), "hit": round(float((fx.usd_to_settlement > 0).mean() * 100), 1) if len(fx) else None,
              "avg_usd": int(fx.usd_to_settlement.mean()) if len(fx) else None}
    out = {"generated": date.today().isoformat(), "start": str(START.date()), "ideas": ideas, "formula_arb": arb, "now": now, "examples": examples, "examples_summary": out_ex}
    (ROOT / "data" / "dairy" / "derived" / "dairy_ideas.json").write_text(json.dumps(out, default=lambda o: None if (isinstance(o, float) and math.isnan(o)) else str(o)))


if __name__ == "__main__":
    main()
