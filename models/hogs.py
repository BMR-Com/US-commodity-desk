"""Lean hog model.

1. CME Lean Hog Index rebuild from USDA LM_HG201 (prior-day slaughtered swine): producer-sold
   barrows & gilts, negotiated + swine/pork market formula + negotiated formula, weight =
   head x avg carcass weight, two consecutive reporting days pooled. Checked against CME's
   published index values (data/cme/indexes.csv) and against expiring futures.
2. Cash / futures: index vs each listed contract (from nightly CME settlements).
3. Packer margin proxy: CME pork cutout (LM_PK602) vs hog index.
Writes data/livestock/derived/hogs.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "livestock" / "raw"
OUT = ROOT / "data" / "livestock" / "derived"
TYPES = ["Prod. Sold Negotiated", "Prod. Sold Swine or Pork Market Formula", "Prod. Sold Negotiated Formula"]


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")


def lean_hog_index():
    d = pd.read_csv(RAW / "hg201_slaughtered_swine" / "barrows_gilts.csv", low_memory=False)
    d = d[d.purchase_type.isin(TYPES)].copy()
    d["date"] = pd.to_datetime(d.for_date_begin)
    d["report"] = pd.to_datetime(d.report_date)
    for c in ("head_count", "avg_net_price", "avg_carcass_weight"):
        d[c] = num(d[c])
    d = d.dropna(subset=["avg_net_price", "avg_carcass_weight", "head_count"])
    d = d.sort_values("published_date").drop_duplicates(["date", "purchase_type"], keep="last")
    d["w"] = d.head_count * d.avg_carcass_weight
    d["v"] = d.w * d.avg_net_price
    day = d.groupby("date").agg(w=("w", "sum"), v=("v", "sum"), hd=("head_count", "sum"),
                                report=("report", "max")).sort_index()
    day["daily"] = day.v / day.w
    day["index"] = (day.v + day.v.shift(1)) / (day.w + day.w.shift(1))
    day["head_cw"] = day.w / day.hd
    return day


def check_vs_cme(day):
    p = ROOT / "data" / "cme" / "indexes.csv"
    if not p.exists():
        return None
    c = pd.read_csv(p)
    c = c[c["index"] == "hogs"].copy()
    c["date"] = pd.to_datetime(c.date)
    j = c.set_index("date").price.to_frame("cme").join(day["index"], how="left")
    j["diff"] = (j["index"] - j.cme).round(3)
    return [{"date": str(i.date()), "cme": r.cme, "rebuild": None if pd.isna(r["index"]) else round(r["index"], 2),
             "diff": None if pd.isna(r["diff"]) else r["diff"]} for i, r in j.iterrows()]


def expiry_check(day):
    """Index on each HE last trading day (10th business day of the contract month) vs the
    front-month close that day (continuous series; contaminated if TradingView already rolled)."""
    px = pd.read_csv(ROOT / "data" / "prices" / "HE.csv", parse_dates=["date"]).set_index("date").c1_close
    months = [2, 4, 5, 6, 7, 8, 10, 12]
    res = []
    for y in range(2006, pd.Timestamp.now().year + 1):
        for m in months:
            bd = pd.bdate_range(f"{y}-{m:02d}-01", f"{y}-{m:02d}-28")
            if len(bd) < 10:
                continue
            ltd = bd[9]
            if ltd not in day.index or ltd not in px.index:
                continue
            res.append({"month": f"{y}-{m:02d}", "ltd": str(ltd.date()), "index": round(day.loc[ltd, "index"], 2),
                        "futures_close": round(float(px[ltd]), 3)})
    df = pd.DataFrame(res)
    if len(df):
        df["diff"] = (df.futures_close - df["index"]).round(3)
    return df


def cutout():
    p = RAW / "pk602_pork_cutout" / "cutout_and_primal_values.csv"
    d = pd.read_csv(p, low_memory=False)
    d["date"] = pd.to_datetime(d.report_date)
    col = next(c for c in d.columns if "carcass" in c.lower() and "value" in c.lower()) if any(
        "carcass" in c.lower() and "value" in c.lower() for c in d.columns) else None
    cols = {c: num(d[c]) for c in d.columns if c.endswith("_value") or c.endswith("Value")}
    out = pd.DataFrame({"date": d.date, **cols}).sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    return out, col


def curve_vs_index(day):
    days = sorted(p.name for p in (ROOT / "data" / "cme").glob("2*") if (p / "fut_settlements.csv").exists())
    if not days:
        return None
    s = pd.read_csv(ROOT / "data" / "cme" / days[-1] / "fut_settlements.csv")
    s = s[s.sym == "HE"].copy()
    s["settle"] = pd.to_numeric(s.settle.astype(str).str.replace(r"[AB]$", "", regex=True), errors="coerce")
    last = day["index"].dropna()
    return {"trade_date": days[-1], "index_date": str(last.index[-1].date()), "index": round(float(last.iloc[-1]), 2),
            "month": s.month.tolist(), "settle": s.settle.tolist(),
            "vs_index": [round(float(x - last.iloc[-1]), 2) for x in s.settle]}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    day = lean_hog_index()
    chk = check_vs_cme(day)
    exp = expiry_check(day)
    print("vs CME published:", chk)
    if len(exp):
        print("expiry check: n", len(exp), "median |diff|", exp["diff"].abs().median(), "share within 0.10:",
              round((exp["diff"].abs() <= 0.10).mean(), 2))
        print(exp.tail(12).to_string())
    co, cocol = cutout()
    print("cutout columns:", list(co.columns)[:12], "carcass col:", cocol)
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"),
           "index": {"date": [str(i.date()) for i in day.index[-1500:]],
                     "index": [None if pd.isna(v) else round(v, 2) for v in day["index"].iloc[-1500:]],
                     "head": [int(v) for v in day["hd"].iloc[-1500:]],
                     "carcass_wt": [round(v, 1) for v in day["head_cw"].iloc[-1500:]]},
           "check_vs_cme": chk,
           "expiry_check": exp.to_dict(orient="list") if len(exp) else None,
           "curve": curve_vs_index(day)}
    (OUT / "hogs.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
