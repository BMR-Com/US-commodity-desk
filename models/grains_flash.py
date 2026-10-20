"""Daily export sales announcements ("flash sales") : running tally, sales since the last weekly report, price tests.

Inputs: data/grains/raw/flash/flash.csv (pipelines/flash.py), data/grains/derived/sales.json (week of the last ESR).
Tests: front-month close-to-close return on announcement days vs all other days (announcements come out
~8 am CT, before the open, so the close-to-close move contains the reaction), by size and buyer, and the
5-day drift after. Writes data/grains/derived/flash.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "grains" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cot_backtest import roll_adjusted_index  # noqa: E402

COMS = {"corn": ("ZC", ["corn"], 39.368), "soybeans": ("ZS", ["soybeans"], 36.744), "meal": ("ZM", ["meal"], None),
        "oil": ("ZL", ["oil"], None), "wheat": ("ZW", ["wheat", "wheat_hrw", "wheat_srw", "wheat_hrs", "wheat_white", "wheat_durum"], 36.744)}
MY_START = {"corn": 9, "soybeans": 9, "meal": 10, "oil": 10, "wheat": 6}


def tstat(x):
    x = pd.Series(x).dropna()
    return round(float(x.mean() / x.std() * np.sqrt(len(x))), 2) if len(x) > 5 and x.std() > 0 else None


def event_test(dates, idx):
    r = idx.pct_change() * 100
    fwd5 = (idx.shift(-5) / idx - 1) * 100
    days = pd.DatetimeIndex(sorted(set(pd.to_datetime(dates)))).intersection(r.index)
    other = r.index.difference(days)
    other = other[other >= days.min()] if len(days) else other
    a, b = r.reindex(days).dropna(), r.reindex(other).dropna()
    f_a, f_b = fwd5.reindex(days).dropna(), fwd5.reindex(other).dropna()
    se = np.sqrt(a.var() / len(a) + b.var() / len(b)) if len(a) > 5 else np.nan
    return {"excess_day": round(float(a.mean() - b.mean()), 3) if len(a) else None, "excess_t": round(float((a.mean() - b.mean()) / se), 2) if se == se and se > 0 else None,
            "excess_fwd5": round(float(f_a.mean() - f_b.mean()), 2) if len(f_a) else None,
            "n": int(len(a)), "mean_day": round(float(a.mean()), 3) if len(a) else None, "up_share": round(float((a > 0).mean()), 2) if len(a) else None,
            "t_vs_zero": tstat(a), "other_mean": round(float(b.mean()), 3), "other_up": round(float((b > 0).mean()), 2),
            "fwd5": round(float(fwd5.reindex(days).dropna().mean()), 2) if len(a) else None, "fwd5_t": tstat(fwd5.reindex(days))}


def run(com, f, sales):
    sym, keys, bu = COMS[com]
    x = f[f.commodity.isin(keys)].copy()
    if x.empty:
        return None
    x["date"] = pd.to_datetime(x.date)
    out = {"recent": x.sort_values("date").tail(15).iloc[::-1].assign(date=lambda z: z.date.dt.strftime("%Y-%m-%d"))[
        ["date", "commodity", "qty_mt", "destination", "my"]].to_dict("records")}
    # MY-to-date tally vs prior years at the same day of the MY
    sm = MY_START[com]
    x["myy"] = np.where(x.date.dt.month >= sm, x.date.dt.year, x.date.dt.year - 1)
    today = pd.Timestamp.now().normalize()
    cy = today.year if today.month >= sm else today.year - 1
    doy = (today - pd.Timestamp(cy, sm, 1)).days
    tally = []
    for y in range(cy - 6, cy + 1):
        s = x[(x.myy == y) & ((x.date - pd.Timestamp(y, sm, 1)).dt.days <= doy)]
        tally.append({"my": f"{y}/{str(y + 1)[-2:]}", "kt": round(float(s.qty_mt.sum() / 1000), 0), "n": int(len(s)),
                      "china_kt": round(float(s[s.destination == "China"].qty_mt.sum() / 1000), 0)})
    out["tally"] = tally
    # since the last weekly export sales report's week ending
    s = sales.get(com)
    if s:
        since = x[x.date > pd.Timestamp(s["as_of"])]
        out["since"] = {"week_ending": s["as_of"], "kt": round(float(since.qty_mt.sum() / 1000), 0), "n": int(len(since)),
                        "in_unit": round(float(since.qty_mt.sum() * bu / 1e6), 1) if bu else None}
    # price tests
    try:
        idx = roll_adjusted_index(sym)
    except Exception:
        idx = None
    if idx is not None:
        day = x.groupby("date").qty_mt.sum()
        china = x[x.destination == "China"].groupby("date").qty_mt.sum()
        big = day[day >= day.quantile(0.75)]
        out["test"] = {"all": event_test(day.index, idx), "big": event_test(big.index, idx), "big_cut_kt": round(float(day.quantile(0.75) / 1000), 0),
                       "china": event_test(china.index, idx), "recent": event_test(day.index[day.index >= "2022-01-01"], idx),
                       "since": str(day.index.min().date())}
    return out


if __name__ == "__main__":
    p = ROOT / "data" / "grains" / "raw" / "flash" / "flash.csv"
    if not p.exists():
        sys.exit("no flash data")
    f = pd.read_csv(p)
    sales = json.loads((D / "sales.json").read_text()) if (D / "sales.json").exists() else {}
    res = {}
    for com in COMS:
        o = run(com, f, sales)
        if o:
            res[com] = o
            print(com, o.get("since"), o["tally"][-1], json.dumps(o.get("test", {}).get("all")), json.dumps(o.get("test", {}).get("big")))
    if "wheat" in res:
        res["kc"] = res["wheat"]
    (D / "flash.json").write_text(json.dumps(res, separators=(",", ":"), default=str).replace("NaN", "null"))
