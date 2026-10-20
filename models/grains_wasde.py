"""WASDE grains balance: US and key-country balances with monthly revisions, stocks/use vs price.

Reads BMR-Com/wasde-analytics processed JSONs (local clone via WASDE_DIR, else GitHub raw).
Writes data/grains/derived/wasde.json.
"""
import json, os, re
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grains" / "derived"
RAW = "https://raw.githubusercontent.com/BMR-Com/wasde-analytics/main/data/{}.json"
FILES = {"corn": "Corn", "soybeans": "Oilseed,_Soybean", "meal": "Meal,_Soybean", "oil": "Oil,_Soybean", "wheat": "Wheat"}
CANON = {  # lower-cased WASDE attribute -> canonical
    "area planted": "area_planted", "area harvested": "area_harvested", "yield per harvested acre": "yield",
    "beginning stocks": "beg_stocks", "production": "production", "imports": "imports", "supply, total": "supply",
    "total supply": "supply", "feed and residual": "feed_residual", "food, seed & industrial": "fsi",
    "ethanol & by-products": "ethanol", "ethanol for fuel": "ethanol", "domestic, total": "domestic", "domestic total": "domestic",
    "domestic": "domestic", "domestic disappearance": "domestic", "crushings": "crush", "domestic crush": "crush",
    "exports": "exports", "use, total": "use", "total use": "use", "ending stocks": "end_stocks",
    "avg. farm price": "price", "food": "food", "seed": "seed", "residual": "residual",
    "biofuel": "biofuel", "biodiesel": "biofuel", "for methyl ester": "biofuel", "methyl ester": "biofuel",
    "food, feed & other industrial": "food_other", "domestic feed": "dom_feed", "trade": "trade",
}
COUNTRIES = {"corn": ["Brazil", "Argentina", "Ukraine", "China", "World"],
             "soybeans": ["Brazil", "Argentina", "China", "World"],
             "wheat": ["Russia", "EU-27", "European Union", "Australia", "Canada", "Argentina", "Ukraine", "China", "World"]}


def load(name):
    local = os.getenv("WASDE_DIR")
    if local and Path(local, f"{name}.json").exists():
        return json.loads(Path(local, f"{name}.json").read_text())
    return requests.get(RAW.format(name), timeout=120).json()


def tidy(j):
    rows = []
    for key, hist in j["data"].items():
        region, attr, my = key.split("||")
        c = CANON.get(attr.strip().lower())
        if not c:
            continue
        for h in hist:
            rows.append(dict(region=region, attr=c, my=my, wasde=h["wasdeNum"], report=h["reportDate"], value=h["value"], unit=h["unit"]))
    d = pd.DataFrame(rows)
    if len(d):  # the US also appears in the world tables in metric tons; keep domestic units for the US
        d = d[~((d.region == "United States") & d.unit.str.contains("Metric", case=False, na=False))]
    # attribute renames over the years create duplicates for the same report: keep the first non-null
    return d.dropna(subset=["value"]).drop_duplicates(["region", "attr", "my", "wasde"]) if len(d) else d


def balance(d, region="United States", years=3):
    x = d[d.region == region]
    mys = sorted(x.my.unique())[-years:]
    out = {}
    for my in mys:
        y = x[x.my == my]
        last = y.wasde.max()
        prev = y[y.wasde < last].wasde.max() if (y.wasde < last).any() else None
        row = {}
        for a, g in y.groupby("attr"):
            g = g.sort_values("wasde")
            cur = g[g.wasde == last].value
            pv = g[g.wasde == prev].value if prev is not None else pd.Series(dtype=float)
            row[a] = {"value": float(cur.iloc[0]) if len(cur) else None,
                      "change": round(float(cur.iloc[0] - pv.iloc[0]), 3) if len(cur) and len(pv) else None,
                      "first": float(g.value.iloc[0]), "unit": g.unit.iloc[-1],
                      "history": [[r.report, float(r.value)] for r in g.itertuples()][-18:]}
        out[my] = {"report": y[y.wasde == last].report.iloc[0], "items": row}
    return out


def final_values(d, region="United States"):
    """Last estimate for each completed marketing year (the 'final' WASDE number)."""
    x = d[d.region == region].sort_values("wasde").groupby(["my", "attr"]).value.last().unstack()
    return x


def stocks_use_vs_price(fv):
    if not {"end_stocks", "use", "price"} <= set(fv.columns):
        return None
    f = fv.dropna(subset=["end_stocks", "use", "price"]).copy()
    f["su"] = 100 * f.end_stocks / f.use
    f = f.iloc[:-1]  # drop the current projection year
    lx, ly = np.log(f.su), np.log(f.price)
    b, a = np.polyfit(lx, ly, 1)
    return {"my": f.index.tolist(), "stocks_use_pct": f.su.round(2).tolist(), "price": f.price.round(3).tolist(),
            "fit": {"elasticity": round(float(b), 3), "intercept": round(float(a), 3),
                    "r2": round(float(np.corrcoef(lx, ly)[0, 1] ** 2), 3)}}


def revision_stats(d, attr, region="United States"):
    """How much does USDA revise attr from its first estimate to its final, by marketing year."""
    x = d[(d.region == region) & (d.attr == attr)].sort_values("wasde")
    rows = []
    for my, g in x.groupby("my"):
        if len(g) < 12:
            continue
        rows.append(dict(my=my, first=float(g.value.iloc[0]), final=float(g.value.iloc[-1])))
    r = pd.DataFrame(rows)
    if r.empty:
        return None
    r["pct"] = 100 * (r.final / r["first"] - 1)
    return {"my": r.my.tolist(), "first": r["first"].tolist(), "final": r.final.tolist(), "pct": r.pct.round(2).tolist(),
            "mean_abs_pct": round(float(r.pct.abs().mean()), 2)}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "commodities": {}}
    for k, f in FILES.items():
        d = tidy(load(f))
        fv = final_values(d)
        entry = {"us": balance(d), "stocks_use_vs_price": stocks_use_vs_price(fv),
                 "revisions": {a: revision_stats(d, a) for a in ("yield", "production", "exports", "end_stocks", "crush", "feed_residual", "ethanol")
                               if a in d.attr.unique()}}
        if k in COUNTRIES:
            entry["world"] = {c: balance(d, c, years=2) for c in COUNTRIES[k] if c in d.region.unique()}
        out["commodities"][k] = entry
        us = entry["us"]
        my = sorted(us)[-1]
        it = us[my]["items"]
        print(k, my, us[my]["report"], {a: (it[a]["value"], it[a]["change"]) for a in ("production", "exports", "end_stocks", "price") if a in it},
              "S/U fit", entry["stocks_use_vs_price"]["fit"] if entry["stocks_use_vs_price"] else None)
    (OUT / "wasde.json").write_text(json.dumps(out, separators=(",", ":"), default=str))
