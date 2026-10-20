"""Hog supply pipeline from quarterly Hogs and Pigs, with backtests.

Forecast: market hogs by weight group on the 1st of report month M reach slaughter roughly
  >=180 lb -> M, 120-179 -> M+1, 50-119 -> M+2, <50 -> M+3/M+4.
Barrow & gilt slaughter per weekday in month M+k is forecast as last year's same-month rate
times the y/y change in the matching weight group. Backtest vs actual NASS slaughter, against a
naive forecast (last year's month x trailing 3-month y/y known at release).
Price test: report "surprise" (weight-group y/y minus the pre-report slaughter trend) vs the
roll-adjusted lean hog futures move from before release to 5 and 20 trading days after.
Writes data/livestock/derived/hogs_sd.json.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "livestock" / "raw" / "nass"
OUT = ROOT / "data" / "livestock" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cot_backtest import roll_adjusted_index  # noqa: E402

MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
GROUPS = {"GE 180 LBS": [0], "120 TO 179 LBS": [1], "50 TO 119 LBS": [2], "LT 50 LBS": [3, 4]}


def val(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def slaughter():
    d = pd.read_csv(RAW / "hogs_slaughter.csv")
    d = d[d.short_desc == "HOGS, BARROWS & GILTS, SLAUGHTER, COMMERCIAL, FI - SLAUGHTERED, MEASURED IN HEAD"].copy()
    d = d[d.reference_period_desc.isin(MON)]
    d["month"] = pd.PeriodIndex.from_fields(year=d.year, month=d.reference_period_desc.map(MON), freq="M")
    d["hd"] = val(d.Value)
    s = d.drop_duplicates("month").set_index("month")["hd"].sort_index()
    days = pd.Series({m: len(pd.bdate_range(m.start_time, m.end_time)) for m in s.index})
    return (s / days).rename("per_day"), s


def hogs_and_pigs():
    d = pd.read_csv(RAW / "hogs_inventory.csv")
    d = d[d.reference_period_desc.str.startswith("FIRST OF") & d.short_desc.str.startswith("HOGS, MARKET,")].copy()
    d["group"] = d.short_desc.str.extract(r"HOGS, MARKET, (.+?) - INVENTORY")[0]
    d = d[d.group.isin(GROUPS)]
    d["month"] = pd.PeriodIndex.from_fields(year=d.year, month=d.reference_period_desc.str[-3:].map(MON), freq="M")
    d["inv"] = val(d.Value)
    d["released"] = pd.to_datetime(d.load_time, errors="coerce")
    t = d.sort_values("released").drop_duplicates(["month", "group"], keep="first")  # first print = what the market saw
    inv = t.pivot(index="month", columns="group", values="inv").sort_index()
    rel = t.groupby("month").released.min()
    return inv, rel


def backtest():
    per_day, _ = slaughter()
    inv, rel = hogs_and_pigs()
    rows = []
    for M in inv.index:
        if M - 12 not in inv.index:
            continue
        for g, ks in GROUPS.items():
            yoy = inv.loc[M, g] / inv.loc[M - 12, g] - 1
            for k in ks:
                tgt = M + k
                if tgt not in per_day.index or tgt - 12 not in per_day.index:
                    continue
                fc = per_day[tgt - 12] * (1 + yoy)
                # naive: trailing 3 months before M, y/y, applied to year-ago target month
                tr = [m for m in (M - 1, M - 2, M - 3) if m in per_day.index and m - 12 in per_day.index]
                naive_yoy = per_day[tr].sum() / per_day[[m - 12 for m in tr]].sum() - 1 if tr else np.nan
                rows.append(dict(report=str(M), target=str(tgt), k=k, group=g, hp_yoy=yoy, naive_yoy=naive_yoy,
                                 actual_yoy=per_day[tgt] / per_day[tgt - 12] - 1,
                                 fc=fc, naive=per_day[tgt - 12] * (1 + naive_yoy), actual=per_day[tgt]))
    d = pd.DataFrame(rows)
    d["err_hp"] = (d.fc / d.actual - 1).abs() * 100
    d["err_naive"] = (d.naive / d.actual - 1).abs() * 100
    res = {}
    for per, x in (("2000-2026", d[d.report >= "2000-01"]), ("2015-2026", d[d.report >= "2015-01"])):
        g = x.groupby("k")
        res[per] = {int(k): {"mape_hp": round(v.err_hp.mean(), 2), "mape_naive": round(v.err_naive.mean(), 2),
                             "hp_beats_naive": round(float((v.err_hp < v.err_naive).mean()), 2), "n": int(len(v))}
                    for k, v in g}
    return res, d, inv, rel, per_day


def price_test(inv, rel, per_day):
    """Surprise = 120-179 & 50-119 lb group y/y minus pre-report slaughter trend (known at release)."""
    idx = roll_adjusted_index("HE")
    rows = []
    for M in inv.index:
        if M - 12 not in inv.index or M not in rel.index or pd.isna(rel[M]):
            continue
        mid = (inv.loc[M, ["120 TO 179 LBS", "50 TO 119 LBS"]].sum() / inv.loc[M - 12, ["120 TO 179 LBS", "50 TO 119 LBS"]].sum() - 1)
        tr = [m for m in (M - 1, M - 2, M - 3) if m in per_day.index and m - 12 in per_day.index]
        if not tr:
            continue
        trend = per_day[tr].sum() / per_day[[m - 12 for m in tr]].sum() - 1
        r0 = rel[M].normalize()
        before = idx[:r0 - pd.Timedelta(days=1)]
        after = idx[r0 + pd.Timedelta(days=1):]
        if len(before) == 0 or len(after) < 21:
            continue
        rows.append(dict(report=str(M), released=str(r0.date()), surprise_pct=100 * (mid - trend),
                         ret5=100 * (after.iloc[4] / before.iloc[-1] - 1), ret20=100 * (after.iloc[19] / before.iloc[-1] - 1)))
    d = pd.DataFrame(rows)
    if d.empty:
        return {}, d
    out = {}
    for h in ("ret5", "ret20"):
        c = d[["surprise_pct", h]].corr().iloc[0, 1]
        big_bear = d[d.surprise_pct >= 1.0][h]   # more hogs than trend -> bearish
        big_bull = d[d.surprise_pct <= -1.0][h]
        out[h] = {"corr": round(float(c), 3), "n": int(len(d)),
                  "after_bearish_surprise": {"n": int(len(big_bear)), "mean_pct": round(float(big_bear.mean()), 2), "down_share": round(float((big_bear < 0).mean()), 2)},
                  "after_bullish_surprise": {"n": int(len(big_bull)), "mean_pct": round(float(big_bull.mean()), 2), "up_share": round(float((big_bull > 0).mean()), 2)}}
    return out, d


def current_forecast(inv, per_day):
    M = inv.index.max()
    out = []
    for g, ks in GROUPS.items():
        yoy = inv.loc[M, g] / inv.loc[M - 12, g] - 1
        for k in ks:
            tgt = M + k
            base = per_day.get(tgt - 12)
            out.append(dict(target=str(tgt), group=g, group_yoy_pct=round(100 * yoy, 2),
                            forecast_per_day=None if base is None else round(base * (1 + yoy)),
                            actual_per_day=None if tgt not in per_day.index else round(per_day[tgt])))
    return {"report": str(M), "inventory": {g: int(inv.loc[M, g]) for g in GROUPS},
            "yoy_pct": {g: round(100 * (inv.loc[M, g] / inv.loc[M - 12, g] - 1), 2) for g in GROUPS}, "months": out}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    res, d, inv, rel, per_day = backtest()
    pt, pd_ = price_test(inv, rel, per_day)
    cur = current_forecast(inv, per_day)
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "slaughter_backtest": res,
           "price_test": pt, "current": cur,
           "slaughter_monthly": {"month": [str(m) for m in per_day.index[-120:]], "per_day": [round(v) for v in per_day.iloc[-120:]]}}
    (OUT / "hogs_sd.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"backtest": res, "price_test": pt, "current": cur}, indent=1, default=str))
