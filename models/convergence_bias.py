"""Systematic convergence: do futures under- or over-price their own final settlement?

For every expired contract (final close = cash settlement, or delivery-period price for live
cattle), measure (settlement - futures) / futures at 10, 20, 40, 60, 120 business days before
expiry, by contract month and overall. A persistent mean with a decent t-stat is a structural
convergence edge (risk premium / seasonal bias), independent of out-forecasting the market.
Writes data/derived/convergence_bias.json.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SYMS = ["HE", "LE", "GF", "DC", "GDK", "CSC", "CB", "GNF", "DY"]
CODES = "FGHJKMNQUVXZ"
H = [10, 20, 40, 60, 120]


def run(sym, since=2010):
    d = pd.read_csv(ROOT / "data" / "contracts" / f"{sym}.csv", parse_dates=["date"])
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=5)
    rows = []
    for c, g in d.groupby("contract"):
        g = g.sort_values("date")
        if g.date.max() >= cutoff or len(g) < 30:
            continue
        year = int(c[-4:])
        if year < since:
            continue
        settle = g.close.iloc[-1]
        for h in H:
            if len(g) > h:
                f = g.close.iloc[-1 - h]
                rows.append(dict(contract=c, month=c[-5], year=year, h=h, conv=100 * (settle / f - 1)))
    x = pd.DataFrame(rows)
    out = {"n_contracts": int(x.contract.nunique()) if len(x) else 0}
    for h, g in x.groupby("h"):
        t = g.conv.mean() / (g.conv.std() / np.sqrt(len(g))) if len(g) > 2 else np.nan
        bym = {}
        for m, gm in g.groupby("month"):
            tm = gm.conv.mean() / (gm.conv.std() / np.sqrt(len(gm))) if len(gm) > 2 else np.nan
            bym[m] = {"n": int(len(gm)), "mean_pct": round(float(gm.conv.mean()), 2), "up_share": round(float((gm.conv > 0).mean()), 2),
                      "t": None if np.isnan(tm) else round(float(tm), 2)}
        out[f"h{h}"] = {"n": int(len(g)), "mean_pct": round(float(g.conv.mean()), 2), "t": round(float(t), 2),
                        "up_share": round(float((g.conv > 0).mean()), 2), "by_month": bym}
    return out


if __name__ == "__main__":
    res = {s: run(s) for s in SYMS}
    p = ROOT / "data" / "derived"
    p.mkdir(parents=True, exist_ok=True)
    (p / "convergence_bias.json").write_text(json.dumps(res, indent=1))
    for s, v in res.items():
        line = " | ".join(f"h{h}: {v[f'h{h}']['mean_pct']:+.2f}% t{v[f'h{h}']['t']:+.1f} up{v[f'h{h}']['up_share']:.0%}" for h in H if f"h{h}" in v)
        print(f"{s:4} n{v['n_contracts']:4}  {line}")
        h = v.get("h60", {}).get("by_month", {})
        strong = {m: (r["mean_pct"], r["t"], r["n"]) for m, r in h.items() if r["t"] is not None and abs(r["t"]) >= 2}
        if strong:
            print("      h60 months with |t|>=2:", strong)
