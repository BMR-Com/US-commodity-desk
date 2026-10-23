"""US cotton vs man-made fibre in textile and apparel imports, monthly -> data/fiber/us_fiber.json

Monthly HS6 imports (pipelines/us_fiber.py) summed by fibre class, by net weight (kg, the closest monthly stand-in
for ERS raw-fibre pounds) and by value. Cotton share = cotton / (cotton + man-made + other + mixed); "clean" share =
cotton / (cotton + man-made). Checked against ERS annual raw-fibre-equivalent shares (data/fiber/raw/ers_annual_lbs.csv).
Lead/lag: monthly change in cotton's kg share vs the cotton/polyester price ratio (ICE cotton vs China PSF ex-VAT in
USD; Brent as the longer proxy) 0-12 months earlier, because orders are placed months before goods are imported.
"""
import csv, json, math
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "fiber" / "raw"
OUT = ROOT / "data" / "fiber" / "us_fiber.json"
SEG = {"apparel": lambda c: c[:2] in ("61", "62"), "home": lambda c: c[:2] == "63",
       "yarn_fabric": lambda c: c[:2] < "61"}


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


def monthly():
    codes = json.loads((RAW / "hs6_fiber_codes.json").read_text())
    d = pd.read_csv(RAW / "us_imports_hs6.csv", dtype={"period": str, "cmd": str})
    d = d[d.cmd.str.len() == 6]
    import importlib.util
    sp = importlib.util.spec_from_file_location("usf", ROOT / "pipelines" / "us_fiber.py")
    usf = importlib.util.module_from_spec(sp); sp.loader.exec_module(usf)
    d["fiber"] = d.cmd.map(lambda c: usf.classify(c, codes[c]["text"]) if c in codes else "mixed")   # classes from the current rules
    d["seg"] = d.cmd.map(lambda c: next(k for k, f in SEG.items() if f(c)))
    d["kg"] = pd.to_numeric(d.net_kg, errors="coerce").fillna(0)
    d["usd"] = pd.to_numeric(d.value_usd, errors="coerce").fillna(0)
    d = d[~d.cmd.str.startswith("6309")]          # worn clothing: not new fibre use
    n = d.groupby("period").cmd.nunique()
    good = n[n >= 0.6 * n.median()].index          # drop months that are not fully loaded yet
    d = d[d.period.isin(good)]
    out = {}
    for seg in ["all", "apparel", "home", "yarn_fabric"]:
        x = d if seg == "all" else d[d.seg == seg]
        p = x.pivot_table(index="period", columns="fiber", values=["kg", "usd"], aggfunc="sum").fillna(0)
        f = pd.DataFrame(index=p.index)
        for m in ["kg", "usd"]:
            tot = p[m].sum(axis=1)
            cot = p[m].get("cotton", 0)
            mmf = p[m].get("mmf", 0)
            f[f"{m}_total"] = tot
            f[f"{m}_cotton"] = cot
            f[f"{m}_mmf"] = mmf
            f[f"share_{m}"] = 100 * cot / tot
            f[f"share_{m}_clean"] = 100 * cot / (cot + mmf)
            r = p[m].rolling(12).sum()
            f[f"share_{m}_12m"] = 100 * r.get("cotton", 0) / r.sum(axis=1)
            r3 = p[m].rolling(3).sum()
            f[f"share_{m}_3m"] = 100 * r3.get("cotton", 0) / r3.sum(axis=1)
        f.index = pd.PeriodIndex([f"{s[:4]}-{s[4:]}" for s in f.index], freq="M")
        out[seg] = f.sort_index()
    return out


def ers():
    e = pd.read_csv(RAW / "ers_annual_lbs.csv")
    return e.set_index("period")


def prices():
    p = pd.read_csv(ROOT / "data" / "china" / "tv_prices.csv", parse_dates=["date"]).set_index("date")
    m = p.resample("M").mean()
    m.index = m.index.to_period("M")
    m["psf_clb"] = m.PF1 / 1.13 / m.USDCNY / 2204.62 * 100     # China PSF ex-VAT (13%) in US cents/lb
    m["ratio"] = m.CT1 / m.psf_clb
    return m


def leadlag(share, driver, maxlag=12):
    """corr( share change over 3 months , driver lagged k months ) and same in 12-month changes."""
    out = []
    ds = share.diff(3)
    for k in range(0, maxlag + 1):
        x = driver.shift(k)
        j = pd.concat([ds, x.pct_change(6) * 100], axis=1).dropna()
        if len(j) > 18:
            out.append({"lag": k, "corr": float(j.iloc[:, 0].corr(j.iloc[:, 1])), "n": len(j)})
    return out


def main():
    M = monthly()
    a = M["all"]
    ap = M["apparel"]
    E = ers()
    yr = a.groupby(a.index.year).agg({"kg_cotton": "sum", "kg_total": "sum", "usd_cotton": "sum", "usd_total": "sum", "kg_mmf": "sum"})
    nmon = a.groupby(a.index.year).size()
    yr = yr[nmon == 12]
    yr["share_kg"] = 100 * yr.kg_cotton / yr.kg_total
    yr["share_usd"] = 100 * yr.usd_cotton / yr.usd_total
    yr = yr.join(E[["cot_share_imp", "cot_share_net"]], how="left")
    cal = yr.dropna(subset=["cot_share_imp"])
    calib = {"years": [int(i) for i in cal.index], "corr_kg": float(cal.share_kg.corr(cal.cot_share_imp)) if len(cal) > 3 else None,
             "corr_usd": float(cal.share_usd.corr(cal.cot_share_imp)) if len(cal) > 3 else None,
             "gap_kg": float((cal.share_kg - cal.cot_share_imp).mean()) if len(cal) else None}
    P = prices()
    j = a.join(P[["CT1", "psf_clb", "ratio", "BRENT"]], how="left")
    ll_ratio = leadlag(j.share_kg, j.ratio)
    ll_brent = leadlag(j.share_kg, j.BRENT)
    last = a.index[-1]
    L = a.iloc[-1]
    y1 = a.loc[last - 12] if (last - 12) in a.index else None
    def pick(f, col):
        return [{"m": str(i), "v": float(v)} for i, v in f[col].dropna().items()]
    best_r = min(ll_ratio, key=lambda r: r["corr"]) if ll_ratio else None
    best_rp = max(ll_ratio, key=lambda r: r["corr"]) if ll_ratio else None
    best_b = max(ll_brent, key=lambda r: r["corr"]) if ll_brent else None
    s12 = a.share_kg_12m.dropna()
    ap12 = ap.share_kg_12m.dropna()
    txt = []
    txt.append(f"Latest month {last}: cotton {L.share_kg:.1f}% of US textile and apparel import weight "
               f"({L.share_kg_3m:.1f}% over 3 months, {L.share_kg_12m:.1f}% over 12 months"
               + (f"; {y1.share_kg_12m:.1f}% a year earlier" if y1 is not None and not pd.isna(y1.share_kg_12m) else "") + ").")
    txt.append(f"Apparel only: {ap.share_kg_3m.iloc[-1]:.1f}% cotton by weight over 3 months, {ap12.iloc[-1]:.1f}% over 12 months"
               f" (12-month low/high since {ap12.index[0]}: {ap12.min():.1f}/{ap12.max():.1f}%).")
    if calib["corr_kg"] is not None:
        txt.append(f"Check vs USDA ERS annual raw-fibre shares {cal.index.min()}-{cal.index.max()}: correlation {calib['corr_kg']:.2f} "
                   f"(weight basis), level gap {calib['gap_kg']:+.1f} pts, so read the monthly series for direction, ERS for level.")
    if best_rp:
        txt.append(f"Lead/lag: 3-month change in cotton's share vs 6-month change in the ICE cotton / China polyester price ratio "
                   f"k months earlier: strongest negative at {best_r['lag']} months (corr {best_r['corr']:.2f}), strongest positive at "
                   f"{best_rp['lag']} months ({best_rp['corr']:.2f}); Brent leads best at {best_b['lag']} months ({best_b['corr']:.2f}).")
    res = {"generated": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "last_month": str(last), "brief": txt,
           "calibration": calib, "leadlag_ratio": ll_ratio, "leadlag_brent": ll_brent,
           "annual": [{"year": int(i), **{k: float(v) if pd.notna(v) else None for k, v in r.items()}} for i, r in yr.iterrows()],
           "series": {seg: {c: pick(f, c) for c in ["share_kg", "share_kg_3m", "share_kg_12m", "share_usd_12m", "share_kg_clean", "kg_total", "kg_cotton", "kg_mmf"]}
                      for seg, f in M.items()},
           "ratio": [{"m": str(i), "ratio": float(r.ratio), "ct": float(r.CT1), "psf": float(r.psf_clb), "brent": float(r.BRENT) if pd.notna(r.BRENT) else None}
                     for i, r in P.dropna(subset=["ratio"]).iterrows()]}
    OUT.write_text(json.dumps(clean(res), separators=(",", ":")))
    print("wrote", OUT)
    for t in txt:
        print("-", t)


if __name__ == "__main__":
    main()
