"""US crop estimates from FSA reported acres -> data/fsa/estimates.json (cotton, corn, soybeans, wheat, sorghum).

FSA's monthly acreage files (pipelines/fsa_acres.py) count acres producers have certified, by state: planted, failed
(planted but lost, i.e. abandoned) and prevented. They are incomplete early and fill in through January, and NASS's
final planted area sits above them by a fairly stable margin. So for every crop year since 2016 we take the FSA release
at the same point of the season as the latest one and compare it with the final NASS figures (USDA's last WASDE for that
crop year):
  planted   final NASS planted / FSA planted+failed        -> scales this year's FSA count to a planted estimate
  abandon   final NASS abandonment vs FSA's failed share     -> harvested area
  yield     USDA's latest WASDE yield (FSA says nothing about yield)
Each past year is also re-estimated without itself, which gives the range and a check against USDA's own November numbers.
"""
import csv, gzip, json, math
from datetime import date, datetime
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FSA = ROOT / "data" / "fsa"
WJ = ROOT / "data" / "wasde" / "json"
WINDOW = 25   # days: a past release counts as "same point of the season" if within this many days of the same date


CROPS = {
    # key: (label, FSA crop match, FSA crops to leave out, WASDE file, attribute names, production unit, yield -> production)
    "cotton": ("Cotton", ("cotton",), (), "Cotton.json", {"Planted": "planted", "Harvested": "harvested", "Yield per Harvested Acre": "yield", "Production": "prod"},
               "m 480-lb bales", lambda h, y: h * y / 480),
    "corn": ("Corn", ("corn",), ("sweet", "pop", "ornamental"), "Corn.json", {"Area Planted": "planted", "Area Harvested": "harvested", "Yield per Harvested Acre": "yield", "Production": "prod"},
             "m bu", lambda h, y: h * y),
    "soybeans": ("Soybeans", ("soybeans",), (), "Oilseed,_Soybean.json", {"Area Planted": "planted", "Area Harvested": "harvested", "Yield per Harvested Acre": "yield", "Production": "prod"},
                 "m bu", lambda h, y: h * y),
    "wheat": ("Wheat", ("wheat",), ("buckwheat",), "Wheat.json", {"Area Planted": "planted", "Area Harvested": "harvested", "Yield per Harvested Acre": "yield", "Production": "prod"},
              "m bu", lambda h, y: h * y),
    "sorghum": ("Sorghum", ("sorghum",), ("forage", "sudan", "sweet"), "Sorghum.json", {"Area Planted": "planted", "Area Harvested": "harvested", "Yield": "yield", "Production": "prod"},
                "m bu", lambda h, y: h * y),
}


def fsa_crop(path, match, skip):
    tot = {"pf": 0.0, "planted": 0.0, "failed": 0.0, "prevented": 0.0}
    by_state, by_type = {}, {}
    with gzip.open(path, "rt") as g:
        for r in csv.DictReader(g):
            crop = (r["crop"] + " " + r["crop_type"]).lower()
            name = r["crop"].lower()
            if not any(m == name or name.startswith(m) for m in match) or any(k in crop for k in skip):
                continue
            pl, fa, pr = float(r["planted"] or 0), float(r["failed"] or 0), float(r["prevented"] or 0)
            pf = pl + fa
            tot["pf"] += pf; tot["planted"] += pl; tot["failed"] += fa; tot["prevented"] += pr
            s = by_state.setdefault(r["state"], {"pf": 0.0, "failed": 0.0, "prevented": 0.0})
            s["pf"] += pf; s["failed"] += fa; s["prevented"] += pr
            t = r["crop_type"] or r["crop"]
            by_type[t] = by_type.get(t, 0.0) + pf
    return tot, by_state, by_type


def wasde_us(fname, names):
    """{crop year: {attr: [(wasde #, report label, forecast year, forecast month, value), ...]}} for the US."""
    d = json.loads((WJ / fname).read_text())
    out = {}
    for k, rel in d["data"].items():
        reg, attr, my = k.split("||")
        if reg != "United States" or attr not in names:
            continue
        y = int(my[:4])
        out.setdefault(y, {})[names[attr]] = sorted([(r["wasdeNum"], r["reportDate"], r.get("forecastYear"), r.get("forecastMonth"), r["value"]) for r in rel if r.get("value") is not None])
    return out


def nov_value(series, year, month=11):
    """USDA's figure for crop year `year` in the WASDE of that month (or the latest one before it)."""
    xs = [x for x in series if (x[2], x[3]) <= (year, month)]
    return xs[-1][4] if xs else None


def crop_estimate(key, rels, cur, release_for):
    label, match, skip, wfile, names, unit, to_prod = CROPS[key]
    W = wasde_us(wfile, names)
    cy = cur["year"]
    rows = []
    for y in sorted({r["year"] for r in rels}):
        r = release_for(y)
        w = W.get(y, {})
        if not r or not w.get("planted"):
            continue
        tot, st, ty = fsa_crop(FSA / "raw" / r["file"], match, skip)
        if tot["pf"] <= 0:
            continue
        last = w["planted"][-1]
        final_done = y < cy and last[2] and (last[2], last[3] or 0) >= (y + 1, 5)   # a WASDE from May of the next year on
        row = {"year": y, "fsa_asof": r["asof"], "fsa_pf": tot["pf"], "fsa_failed": tot["failed"], "fsa_prevented": tot["prevented"],
               "fsa_failed_share": tot["failed"] / tot["pf"], "fsa_tx_pf": st.get("Texas", {}).get("pf"), "fsa_tx_failed": st.get("Texas", {}).get("failed"),
               "usda_same": {k: nov_value(w.get(k, []), y, int(r["asof"][5:7]) if int(r["asof"][:4]) == y else 12) for k in ("planted", "harvested", "yield", "prod")}}
        if final_done:
            row["final"] = {k: w[k][-1][4] for k in ("planted", "harvested", "yield", "prod") if w.get(k)}
            row["final_from"] = last[1]
            f = row["final"]
            row["r_plant"] = f["planted"] * 1e6 / tot["pf"]
            row["abandon"] = 1 - f["harvested"] / f["planted"]
        rows.append(row)
    past = [r for r in rows if r.get("r_plant")]
    now = next((r for r in rows if r["year"] == cy), None)
    if now is None or len(past) < 4:
        return {"label": label, "error": f"not enough comparable years ({len(past)} past, current {'ok' if now else 'missing'})"}

    def estimate(train, x):
        rp = float(np.median([t["r_plant"] for t in train]))
        fs = np.array([t["fsa_failed_share"] for t in train]); ab = np.array([t["abandon"] for t in train])
        if len(train) >= 5 and np.std(fs) > 1e-6:
            b, a = np.polyfit(fs, ab, 1)
        else:
            b, a = 0.0, float(np.mean(ab))
        planted = x["fsa_pf"] * rp / 1e6
        aband = min(max(a + b * x["fsa_failed_share"], 0.0), 0.7)
        return {"planted": planted, "abandon": aband, "harvested": planted * (1 - aband), "r_plant": rp, "ab_a": float(a), "ab_b": float(b)}

    bt = []
    for t in past:
        e = estimate([p for p in past if p is not t], t)
        yl = t["usda_same"]["yield"]; f = t["final"]; u = t["usda_same"]
        prod = to_prod(e["harvested"], yl) if yl else None
        pct = lambda a, b: 100 * (a / b - 1) if a is not None and b else None
        bt.append({"year": t["year"], "fsa_asof": t["fsa_asof"], "est_planted": e["planted"], "est_harvested": e["harvested"], "est_prod": prod,
                   "usda_planted": u["planted"], "usda_harvested": u["harvested"], "usda_prod": u["prod"],
                   "final_planted": f.get("planted"), "final_harvested": f.get("harvested"), "final_prod": f.get("prod"),
                   "err_plant_pct": pct(e["planted"], f.get("planted")), "usda_err_plant_pct": pct(u["planted"], f.get("planted")),
                   "err_harv_pct": pct(e["harvested"], f.get("harvested")), "usda_err_harv_pct": pct(u["harvested"], f.get("harvested")),
                   "err_prod_pct": pct(prod, f.get("prod")), "usda_err_prod_pct": pct(u["prod"], f.get("prod"))})
    e = estimate(past, now)
    yl = now["usda_same"]["yield"]
    prod = to_prod(e["harvested"], yl) if yl else None
    errs = sorted(b["err_harv_pct"] for b in bt if b["err_harv_pct"] is not None)
    lo, hi = (errs[0], errs[-1]) if errs else (None, None)
    mae = lambda k: float(np.mean([abs(b[k]) for b in bt if b.get(k) is not None])) if any(b.get(k) is not None for b in bt) else None
    st_now = fsa_crop(FSA / "raw" / cur["file"], match, skip)[1]
    prev_rel = release_for(cy - 1)
    st_prev = fsa_crop(FSA / "raw" / prev_rel["file"], match, skip)[1] if prev_rel else {}
    prev = next((r for r in rows if r["year"] == cy - 1), None)
    u = now["usda_same"]
    out = {
        "label": label, "unit": unit,
        "fsa": {"pf_m": now["fsa_pf"] / 1e6, "failed_m": now["fsa_failed"] / 1e6, "prevented_m": now["fsa_prevented"] / 1e6, "failed_share": now["fsa_failed_share"],
                "prev_year_same_date": {"asof": prev_rel["asof"], "pf_m": prev["fsa_pf"] / 1e6, "failed_share": prev["fsa_failed_share"]} if prev and prev_rel else None},
        "estimate": {"planted_m": e["planted"], "harvested_m": e["harvested"], "abandon_pct": 100 * e["abandon"], "yield": yl, "prod": prod,
                     "harv_lo_m": e["harvested"] * (1 + lo / 100) if lo is not None else None, "harv_hi_m": e["harvested"] * (1 + hi / 100) if hi is not None else None,
                     "prod_lo": prod * (1 + lo / 100) if prod and lo is not None else None, "prod_hi": prod * (1 + hi / 100) if prod and hi is not None else None,
                     "r_plant": e["r_plant"], "abandon_fit": {"a": e["ab_a"], "b": e["ab_b"]}},
        "usda": {"planted_m": u["planted"], "harvested_m": u["harvested"], "yield": yl, "prod": u["prod"], "abandon_pct": 100 * (1 - u["harvested"] / u["planted"]) if u["planted"] and u["harvested"] else None},
        "backtest": {"years": len(bt), "mae_plant_pct": mae("err_plant_pct"), "usda_mae_plant_pct": mae("usda_err_plant_pct"), "mae_harv_pct": mae("err_harv_pct"),
                     "usda_mae_harv_pct": mae("usda_err_harv_pct"), "mae_prod_pct": mae("err_prod_pct"), "usda_mae_prod_pct": mae("usda_err_prod_pct"), "rows": bt},
        "states": [{"state": s_, "pf_k": v["pf"] / 1e3, "failed_k": v["failed"] / 1e3, "failed_pct": 100 * v["failed"] / v["pf"] if v["pf"] else None,
                    "prev_pf_k": (st_prev.get(s_, {}).get("pf", 0) / 1e3) or None} for s_, v in sorted(st_now.items(), key=lambda kv: -kv[1]["pf"])[:12]],
    }
    return out


def main():
    idx = json.loads((FSA / "index.json").read_text())
    rels = [r for r in idx["releases"] if r.get("rows") and r.get("file") and (FSA / "raw" / r["file"]).exists()]
    if not rels:
        raise SystemExit("no FSA releases stored")
    cur = max(rels, key=lambda r: r["asof"])
    cy = cur["year"]
    off = (date.fromisoformat(cur["asof"]) - date(cy, 1, 1)).days

    def release_for(y):
        best = None
        for r in rels:
            if r["year"] != y:
                continue
            d = abs((date.fromisoformat(r["asof"]) - date(y, 1, 1)).days - off)
            if d <= WINDOW and (best is None or d < best[0]):
                best = (d, r)
        return best[1] if best else None

    crops = {}
    for k in CROPS:
        try:
            crops[k] = crop_estimate(k, rels, cur, release_for)
        except Exception as e:
            crops[k] = {"label": CROPS[k][0], "error": repr(e)[:200]}
        c = crops[k]
        if c.get("estimate"):
            E, U, B = c["estimate"], c["usda"], c["backtest"]
            print(f"{k}: FSA {c['fsa']['pf_m']:.2f} m ac -> planted {E['planted_m']:.2f} (USDA {U['planted_m']}), harvested {E['harvested_m']:.2f} (USDA {U['harvested_m']}), "
                  f"prod {E['prod'] or 0:.1f} vs USDA {U['prod']} {c['unit']}; backtest {B['years']} yrs harv MAE {B['mae_harv_pct'] or 0:.1f}% vs USDA {B['usda_mae_harv_pct'] or 0:.1f}%")
        else:
            print(k, c.get("error"))
    used = sorted({release_for(y)["asof"] for y in {r["year"] for r in rels} if release_for(y)})
    out = {"built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "crop_year": cy, "fsa_asof": cur["asof"], "fsa_label": cur["label"], "fsa_url": cur["url"],
           "releases_compared": used, "window_days": WINDOW, "crops": crops,
           "method": "Planted = FSA planted+failed acres x the median ratio of USDA's final planted area to FSA acres at the same point of past seasons; "
                     "abandonment from FSA's failed share (fitted on past seasons); yield = USDA's latest. Backtest: each past season re-estimated without itself."}
    if not any(c.get("estimate") for c in crops.values()):
        raise SystemExit("no crop estimated")
    tmp = FSA / ".estimates.json.tmp"
    tmp.write_text(json.dumps(out, indent=1, default=lambda x: None))
    tmp.replace(FSA / "estimates.json")


if __name__ == "__main__":
    main()
