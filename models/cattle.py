"""Live and feeder cattle: cash, beef cutout, cattle on feed, curves vs cash, convergence evidence.

Writes data/livestock/derived/cattle.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "livestock" / "raw"
OUT = ROOT / "data" / "livestock" / "derived"
MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def five_area():
    d = pd.read_csv(RAW / "ct150_5area_weekly" / "detail.csv", low_memory=False)
    d = d[(d.class_description == "STEER") & (d.grade_description.str.strip() == "Total all grades")].copy()
    d["date"] = pd.to_datetime(d.report_date)
    d["px"] = num(d.weighted_avg_price)
    d["hd"] = num(d.head_count)
    p = d.pivot_table(index="date", columns="selling_basis_description", values="px", aggfunc="last").sort_index()
    h = d.pivot_table(index="date", columns="selling_basis_description", values="hd", aggfunc="last").sort_index()
    return p, h


def boxed_beef():
    x = pd.read_csv(RAW / "xb403_boxed_beef" / "current_cutout_values.csv")
    x["date"] = pd.to_datetime(x.report_date)
    x = x.sort_values(["date", "published_date"]).drop_duplicates("date", keep="last").set_index("date")
    return pd.DataFrame({"choice": num(x.choice_600_900_current), "select": num(x.select_600_900_current)})


def cattle_on_feed():
    d = pd.read_csv(RAW / "nass" / "cattle_on_feed.csv")
    d = d[d.domaincat_desc == "CAPACITY: (1,000 OR MORE HEAD)"]
    items = {"on_feed": "CATTLE, ON FEED - INVENTORY", "placements": "CATTLE, ON FEED - PLACEMENTS, MEASURED IN HEAD",
             "marketings": "CATTLE, ON FEED - SALES FOR SLAUGHTER, MEASURED IN HEAD"}
    out = {}
    for k, sd in items.items():
        x = d[d.short_desc == sd].copy()
        x["m"] = x.reference_period_desc.str.extract(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")[0]
        x = x.dropna(subset=["m"])
        if k == "on_feed":
            x = x[x.reference_period_desc.str.startswith("FIRST OF")] if x.reference_period_desc.str.startswith("FIRST OF").any() else x
        x["month"] = [f"{y}-{MON[m]:02d}" for y, m in zip(x.year, x.m)]
        s = (num(x.Value).groupby(x.month).last().sort_index() / 1000).round(0)
        out[k] = s[s.index >= "2012-01"]
    return out


def yoy(s):
    idx = pd.PeriodIndex(s.index, freq="M")
    v = pd.Series(s.values, index=idx)
    return {str(i): (None if (i - 12) not in v.index else round(float(100 * (v[i] / v[i - 12] - 1)), 1)) for i in v.index[-24:]}


def curve(sym, cash, label):
    days = sorted(p.name for p in (ROOT / "data" / "cme").glob("2*") if (p / "fut_settlements.csv").exists())
    if not days or cash is None:
        return None
    s = pd.read_csv(ROOT / "data" / "cme" / days[-1] / "fut_settlements.csv")
    s = s[s.sym == sym].copy()
    s["settle"] = pd.to_numeric(s.settle.astype(str).str.replace(r"[AB]$", "", regex=True), errors="coerce")
    return {"trade_date": days[-1], "cash_label": label, "cash": round(float(cash), 2), "month": s.month.tolist(),
            "settle": [None if pd.isna(v) else float(v) for v in s.settle],
            "vs_cash": [None if pd.isna(v) else round(float(v - cash), 2) for v in s.settle]}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    p, h = five_area()
    bb = boxed_beef()
    cof = cattle_on_feed()
    live = p.get("LIVE FOB").dropna()
    dressed = p.get("DRESSED DELIVERED").dropna()
    w = bb.resample("W-FRI").mean()
    spread = (w.choice - dressed.resample("W-FRI").last()).dropna()
    idx = pd.read_csv(ROOT / "data" / "cme" / "indexes.csv") if (ROOT / "data" / "cme" / "indexes.csv").exists() else None
    fci = None
    if idx is not None:
        f = idx[idx["index"] == "cattle"].sort_values("date")
        fci = (f.date.iloc[-1], float(f.price.iloc[-1])) if len(f) else None
    n = 260
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"),
           "five_area": {"date": [str(x.date()) for x in live.index[-n:]], "live_fob": live.iloc[-n:].round(2).tolist(),
                         "dressed": dressed.reindex(live.index[-n:]).round(2).tolist()},
           "boxed_beef": {"date": [str(x.date()) for x in bb.index[-750:]], "choice": bb.choice.iloc[-750:].round(2).tolist(),
                          "select": bb.select.iloc[-750:].round(2).tolist()},
           "cutout_minus_dressed": {"date": [str(x.date()) for x in spread.index[-n:]], "spread": spread.iloc[-n:].round(2).tolist()},
           "cof": {k: {"month": v.index.tolist()[-60:], "k_head": v.tolist()[-60:], "yoy": yoy(v)} for k, v in cof.items()},
           "curve_le": curve("LE", live.iloc[-1], f"5-area live steer, week of {live.index[-1].date()}"),
           "curve_gf": curve("GF", fci[1], f"CME Feeder Cattle Index {fci[0]}") if fci else None}
    (OUT / "cattle.json").write_text(json.dumps(out, separators=(",", ":"), default=str).replace("NaN", "null"))
    print({k: (v[-1] if isinstance(v, list) else None) for k, v in out["five_area"].items()}, out["curve_le"]["vs_cash"][:4] if out["curve_le"] else None,
          {k: list(v["yoy"].items())[-1] for k, v in out["cof"].items()}, out["curve_gf"]["vs_cash"][:3] if out["curve_gf"] else None)
