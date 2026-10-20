"""Cattle on feed pipeline: placements by weight -> fed cattle marketings months later.

Days on feed by placement weight (rough industry norms): <600 lb ~7 months, 600-699 ~6, 700-799 ~5,
800-899 ~4.5, >=900 ~4. Forecast marketings in month t as last year's marketings x the y/y change
in the placements that should be finishing in t (weighted by group size). Backtest vs a naive
forecast (last year's month x trailing 3-month marketings y/y).
Writes data/livestock/derived/cattle_sd.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "livestock" / "raw" / "nass" / "cattle_on_feed.csv"
OUT = ROOT / "data" / "livestock" / "derived"
MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
GROUPS = {"CATTLE, LT 600 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 7, "CATTLE, 600 TO 699 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 6,
          "CATTLE, 700 TO 799 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 5, "CATTLE, 800 TO 899 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 4,
          "CATTLE, 900 TO 999 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 4, "CATTLE, GE 1000 LBS, ON FEED - PLACEMENTS, MEASURED IN HEAD": 4}
MKT = "CATTLE, ON FEED - SALES FOR SLAUGHTER, MEASURED IN HEAD"


def series(d, sd):
    x = d[d.short_desc == sd].copy()
    x["m"] = x.reference_period_desc.str.extract(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")[0]
    x = x.dropna(subset=["m"])
    x["month"] = pd.PeriodIndex.from_fields(year=x.year, month=x.m.map(MON), freq="M")
    return pd.to_numeric(x.Value.astype(str).str.replace(",", ""), errors="coerce").groupby(x.month).last().sort_index()


if __name__ == "__main__":
    d = pd.read_csv(RAW)
    d = d[d.domaincat_desc == "CAPACITY: (1,000 OR MORE HEAD)"]
    mk_tot = series(d, MKT)
    bdays = pd.Series({m: len(pd.bdate_range(m.start_time, m.end_time)) for m in mk_tot.index})
    mk = mk_tot / bdays  # marketings per business day: removes calendar noise
    pl = {g: series(d, g) for g in GROUPS}
    rows = []
    for t in mk.index:
        if t - 12 not in mk.index:
            continue
        num = den = 0.0
        for g, lag in GROUPS.items():
            s = pl[g]
            a, b = t - lag, t - lag - 12
            if a in s.index and b in s.index and s[b] > 0:
                num += s[a]
                den += s[b]
        if den == 0:
            continue
        fc = mk[t - 12] * num / den
        tr = [m for m in (t - 4, t - 5, t - 6) if m in mk.index and m - 12 in mk.index]  # known when placements-based forecast is made
        naive = mk[t - 12] * (mk[tr].sum() / mk[[m - 12 for m in tr]].sum()) if tr else np.nan
        rows.append(dict(month=str(t), actual=mk[t], pipeline=fc, naive=naive))
    r = pd.DataFrame(rows).dropna()
    r = r[r.month >= "2012-01"]
    r["e_p"] = (r.pipeline / r.actual - 1).abs() * 100
    r["e_n"] = (r.naive / r.actual - 1).abs() * 100
    test = {"n": int(len(r)), "mape_pipeline": round(float(r.e_p.mean()), 2), "mape_naive": round(float(r.e_n.mean()), 2),
            "pipeline_beats_naive": round(float((r.e_p < r.e_n).mean()), 2)}
    # forward forecast for the next months with placements already reported
    last = mk.index.max()
    fwd = []
    for k in range(1, 7):
        t = last + k
        num = den = 0.0
        for g, lag in GROUPS.items():
            s = pl[g]
            a, b = t - lag, t - lag - 12
            if a in s.index and b in s.index:
                num += s[a]; den += s[b]
        if den and (t - 12) in mk.index:
            nb = len(pd.bdate_range(t.start_time, t.end_time))
            fwd.append({"month": str(t), "forecast_k": round(float(mk[t - 12] * num / den * nb / 1000), 0), "yoy_pct": round(float(100 * (num / den - 1)), 1)})
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "test": test, "forward": fwd,
           "history": {"month": r.month.tolist()[-48:], "actual_per_day": r.actual.round(0).tolist()[-48:], "pipeline_per_day": r.pipeline.round(0).tolist()[-48:]}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cattle_sd.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"test": test, "forward": fwd}))
