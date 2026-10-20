"""Do managed-money positioning extremes predict forward futures returns?

For each contract: weekly managed-money net (CFTC disaggregated F+O), its percentile within the
trailing 3 years (past data only), and roll-adjusted forward returns of the front month over
4, 8 and 13 weeks from the report's Friday release. Compares forward returns after extreme
short (<=10th pct) and extreme long (>=90th pct) readings with all weeks.
Writes data/derived/cot_backtest.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SYMS = ["DC", "GDK", "CSC", "CB", "GNF", "DY", "HE", "LE", "GF"]


MCODE = {c: i for i, c in enumerate("FGHJKMNQUVXZ", 1)}
CASH_SETTLED = {"HE", "GF", "DC", "GDK", "CSC", "CB", "GNF", "DY"}


def roll_adjusted_index(sym):
    """Total-return index of holding the front contract, rolled before delivery/expiry, built from
    per-contract closes (data/contracts/<SYM>.csv). Physically delivered contracts roll on the 20th of the month
    before the delivery month; cash-settled ones 5 trading days before their last trading day. Falls back to the
    TradingView continuous series (cruder roll detection) when no contract history exists."""
    cp = ROOT / "data" / "contracts" / f"{sym}.csv"
    if cp.exists():
        d = pd.read_csv(cp, parse_dates=["date"]).dropna(subset=["close"])
        d = d[(d.close > 0) & (d.date >= "2006-01-01")]  # 2003-05 histories are too thin (single contracts, bad prints)
        px = d.pivot_table(index="date", columns="contract", values="close", aggfunc="last").sort_index()
        last = d.groupby("contract").date.max()
        roll = {}
        for c in px.columns:
            code = c[len(sym):]
            m, y = MCODE.get(code[0]), int(code[1:])
            if not m:
                continue
            if sym in CASH_SETTLED:
                dates = px[c].dropna().index
                roll[c] = dates[-6] if len(dates) > 6 and last[c] < px.index[-1] else pd.Timestamp(y, m, 28)
            else:
                pm, py = (m - 1, y) if m > 1 else (12, y - 1)
                roll[c] = pd.Timestamp(py, pm, 20)
        order = sorted(roll, key=lambda c: roll[c])
        ret = pd.Series(0.0, index=px.index)
        held = None
        for i, t in enumerate(px.index):
            if i == 0:
                continue
            prev = px.index[i - 1]
            # contract held over (prev, t]: the first one whose roll date is after prev and that traded on both days
            h = next((c for c in order if roll[c] > prev and not np.isnan(px.at[prev, c]) and not np.isnan(px.at[t, c])), None)
            if h is not None:
                ret.iat[i] = px.at[t, h] / px.at[prev, h] - 1
        return (1 + ret.clip(-0.25, 0.25)).cumprod()
    p = pd.read_csv(ROOT / "data" / "prices" / f"{sym}.csv", parse_dates=["date"]).set_index("date")
    c1, c2 = p.c1_close, p.c2_close
    r = c1 / c1.shift(1) - 1
    r_roll = c1 / c2.shift(1) - 1
    roll = (r_roll.abs() < r.abs()) & (r.abs() > 0.015)
    ret = r.where(~roll, r_roll).fillna(0).clip(-0.25, 0.25)
    return (1 + ret).cumprod()


def run(sym):
    d = pd.read_csv(ROOT / "data" / "cot" / f"{sym}_fo.csv", low_memory=False)
    c = pd.DataFrame({"date": pd.to_datetime(d.report_date_as_yyyy_mm_dd),
                      "net": pd.to_numeric(d.m_money_positions_long_all) - pd.to_numeric(d.m_money_positions_short_all),
                      "oi": pd.to_numeric(d.open_interest_all)}).dropna().sort_values("date").drop_duplicates("date")
    c["netpct"] = c.net / c.oi
    c["pctl"] = c.netpct.rolling(156, min_periods=104).apply(lambda x: (x[:-1] < x[-1]).mean() * 100, raw=True)
    idx = roll_adjusted_index(sym)
    c["release"] = c.date + pd.Timedelta(days=3)
    lvl = idx.reindex(idx.index.union(c.release)).ffill()
    base = lvl.reindex(c.release).values
    out = {}
    for w in (4, 8, 13):
        fwd = lvl.reindex(c.release + pd.Timedelta(weeks=w)).values
        c[f"f{w}"] = 100 * (fwd / base - 1)
    c = c.dropna(subset=["pctl", "f4"])
    for w in (4, 8, 13):
        col = f"f{w}"
        allr = c[col].dropna()
        lo, hi = c[c.pctl <= 10][col].dropna(), c[c.pctl >= 90][col].dropna()
        def stat(x):
            if len(x) < 8:
                return None
            # overlapping weekly samples: effective n ~ len/w
            se = x.std() / np.sqrt(max(len(x) / w, 1))
            return {"n": int(len(x)), "mean_pct": round(float(x.mean()), 2), "up_share": round(float((x > 0).mean()), 2),
                    "t_approx": round(float(x.mean() / se), 2) if se > 0 else None}
        out[f"w{w}"] = {"all": stat(allr), "extreme_short": stat(lo), "extreme_long": stat(hi)}
    out["first_week"] = str(c.date.min().date())
    out["current_pctl_3y"] = None if pd.isna(c.pctl.iloc[-1]) else round(float(c.pctl.iloc[-1]), 0)
    return out


if __name__ == "__main__":
    res = {s: run(s) for s in SYMS}
    (ROOT / "data" / "derived").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "derived" / "cot_backtest.json").write_text(json.dumps(res, indent=1))
    for s, v in res.items():
        for w in ("w4", "w8", "w13"):
            x = v[w]
            f = lambda k: "–" if not x[k] else f"{x[k]['mean_pct']:+.2f}% up {x[k]['up_share']:.0%} n{x[k]['n']} t{x[k]['t_approx']}"
            print(f"{s:4} {w:4} all {f('all'):34} | ext short {f('extreme_short'):34} | ext long {f('extreme_long')}")
