"""US cotton crop estimate from FSA reported acres -> data/fsa/cotton_estimate.json.

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
WJ = ROOT / "data" / "wasde" / "json" / "Cotton.json"
WINDOW = 25   # days: a past release counts as "same point of the season" if within this many days of the same date


def fsa_cotton(path):
    tot = {"pf": 0.0, "planted": 0.0, "failed": 0.0, "prevented": 0.0}
    by_state, by_type = {}, {}
    with gzip.open(path, "rt") as g:
        for r in csv.DictReader(g):
            crop = (r["crop"] + " " + r["crop_type"]).lower()
            if "cotton" not in crop:
                continue
            pl, fa, pr = float(r["planted"] or 0), float(r["failed"] or 0), float(r["prevented"] or 0)
            pf = pl + fa
            tot["pf"] += pf; tot["planted"] += pl; tot["failed"] += fa; tot["prevented"] += pr
            s = by_state.setdefault(r["state"], {"pf": 0.0, "failed": 0.0, "prevented": 0.0})
            s["pf"] += pf; s["failed"] += fa; s["prevented"] += pr
            t = "Pima (ELS)" if ("els" in crop or "pima" in crop or "extra" in crop) else "Upland"
            by_type[t] = by_type.get(t, 0.0) + pf
    return tot, by_state, by_type


def wasde_us():
    """{crop year: {attr: [(wasde #, report label, forecast month, value), ...]}} for US cotton."""
    d = json.loads(WJ.read_text())
    out = {}
    names = {"Planted": "planted", "Harvested": "harvested", "Yield per Harvested Acre": "yield", "Production": "prod"}
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


def main():
    idx = json.loads((FSA / "index.json").read_text())
    rels = [r for r in idx["releases"] if r.get("rows") and r.get("file")]
    if not rels:
        raise SystemExit("no FSA releases stored")
    W = wasde_us()
    cur = max(rels, key=lambda r: r["asof"])
    cy = cur["year"]
    ca = date.fromisoformat(cur["asof"])
    off = (ca - date(cy, 1, 1)).days

    def release_for(y):
        best = None
        for r in rels:
            if r["year"] != y:
                continue
            d = abs((date.fromisoformat(r["asof"]) - date(y, 1, 1)).days - off)
            if d <= WINDOW and (best is None or d < best[0]):
                best = (d, r)
        return best[1] if best else None

    rows = []
    for y in sorted({r["year"] for r in rels}):
        r = release_for(y)
        w = W.get(y, {})
        if not r or not w.get("planted"):
            continue
        tot, st, ty = fsa_cotton(FSA / "raw" / r["file"])
        final_done = y < cy and w["planted"][-1][2] and (w["planted"][-1][2], w["planted"][-1][3] or 0) >= (y + 1, 5)  # a WASDE from May of the next year on
        row = {"year": y, "fsa_asof": r["asof"], "fsa_pf": tot["pf"], "fsa_failed": tot["failed"], "fsa_prevented": tot["prevented"],
               "fsa_failed_share": tot["failed"] / tot["pf"] if tot["pf"] else None,
               "fsa_tx_pf": st.get("Texas", {}).get("pf"), "fsa_tx_failed": st.get("Texas", {}).get("failed"),
               "usda_nov": {k: nov_value(w.get(k, []), y) for k in ("planted", "harvested", "yield", "prod")}}
        if final_done:
            row["final"] = {k: w[k][-1][4] for k in ("planted", "harvested", "yield", "prod") if w.get(k)}
            row["final_from"] = w["planted"][-1][1]
            f = row["final"]
            row["r_plant"] = f["planted"] * 1e6 / tot["pf"]
            row["abandon"] = 1 - f["harvested"] / f["planted"]
        rows.append(row)

    past = [r for r in rows if r.get("r_plant")]
    now = next((r for r in rows if r["year"] == cy), None)
    if now is None or len(past) < 4:
        raise SystemExit(f"not enough comparable years: {len(past)} past, current {'ok' if now else 'missing'}")

    def estimate(train, x):
        rp = float(np.median([t["r_plant"] for t in train]))
        fs = np.array([t["fsa_failed_share"] for t in train]); ab = np.array([t["abandon"] for t in train])
        if len(train) >= 5 and np.std(fs) > 0:
            b, a = np.polyfit(fs, ab, 1)
        else:
            b, a = 0.0, float(np.mean(ab))
        planted = x["fsa_pf"] * rp / 1e6
        aband = min(max(a + b * x["fsa_failed_share"], 0.0), 0.6)
        harv = planted * (1 - aband)
        return {"planted": planted, "abandon": aband, "harvested": harv, "r_plant": rp, "ab_a": a, "ab_b": b}

    # leave-one-year-out: FSA-based estimate (with USDA's November yield) vs final, and USDA November vs final
    bt = []
    for t in past:
        e = estimate([p for p in past if p is not t], t)
        yl = t["usda_nov"]["yield"]
        prod = e["harvested"] * yl / 480 if yl else None
        f = t["final"]
        bt.append({"year": t["year"], "fsa_asof": t["fsa_asof"], "est_planted": e["planted"], "est_harvested": e["harvested"], "est_prod": prod,
                   "usda_nov_planted": t["usda_nov"]["planted"], "usda_nov_harvested": t["usda_nov"]["harvested"], "usda_nov_prod": t["usda_nov"]["prod"],
                   "final_planted": f.get("planted"), "final_harvested": f.get("harvested"), "final_prod": f.get("prod"),
                   "err_harv_pct": 100 * (e["harvested"] / f["harvested"] - 1), "usda_err_harv_pct": 100 * (t["usda_nov"]["harvested"] / f["harvested"] - 1) if t["usda_nov"]["harvested"] else None,
                   "err_prod_pct": 100 * (prod / f["prod"] - 1) if prod else None, "usda_err_prod_pct": 100 * (t["usda_nov"]["prod"] / f["prod"] - 1) if t["usda_nov"]["prod"] else None})
    e = estimate(past, now)
    yl = now["usda_nov"]["yield"]
    prod = e["harvested"] * yl / 480 if yl else None
    errs = [b["err_harv_pct"] for b in bt]
    lo, hi = (min(errs), max(errs)) if errs else (None, None)
    mae = lambda k: float(np.mean([abs(b[k]) for b in bt if b.get(k) is not None])) if bt else None
    prev = next((r for r in rows if r["year"] == cy - 1), None)
    st_now = fsa_cotton(FSA / "raw" / cur["file"])[1]
    prev_rel = release_for(cy - 1)
    st_prev = fsa_cotton(FSA / "raw" / prev_rel["file"])[1] if prev_rel else {}
    states = sorted(st_now.items(), key=lambda kv: -kv[1]["pf"])[:12]
    out = {
        "built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "crop_year": cy, "fsa_asof": cur["asof"], "fsa_label": cur["label"], "fsa_url": cur["url"],
        "fsa": {"pf_m": now["fsa_pf"] / 1e6, "failed_m": now["fsa_failed"] / 1e6, "prevented_m": now["fsa_prevented"] / 1e6, "failed_share": now["fsa_failed_share"],
                "tx_pf_m": (now["fsa_tx_pf"] or 0) / 1e6, "tx_failed_m": (now["fsa_tx_failed"] or 0) / 1e6,
                "by_type_m": {k: v / 1e6 for k, v in fsa_cotton(FSA / "raw" / cur["file"])[2].items()},
                "prev_year_same_date": {"asof": prev_rel["asof"], "pf_m": prev["fsa_pf"] / 1e6, "failed_share": prev["fsa_failed_share"]} if prev and prev_rel else None},
        "estimate": {"planted_m": e["planted"], "harvested_m": e["harvested"], "abandon_pct": 100 * e["abandon"], "yield_lb": yl, "prod_m480": prod,
                     "harv_lo_m": e["harvested"] * (1 + lo / 100) if lo is not None else None, "harv_hi_m": e["harvested"] * (1 + hi / 100) if hi is not None else None,
                     "prod_lo_m480": prod * (1 + lo / 100) if prod and lo is not None else None, "prod_hi_m480": prod * (1 + hi / 100) if prod and hi is not None else None,
                     "r_plant": e["r_plant"], "abandon_fit": {"a": e["ab_a"], "b": e["ab_b"]}},
        "usda_latest": now["usda_nov"], "usda_report": W[cy]["planted"][-1][1],
        "backtest": {"years": len(bt), "mae_harv_pct": mae("err_harv_pct"), "usda_mae_harv_pct": mae("usda_err_harv_pct"), "mae_prod_pct": mae("err_prod_pct"),
                     "usda_mae_prod_pct": mae("usda_err_prod_pct"), "rows": bt},
        "history": [{k: v for k, v in r.items()} for r in rows],
        "states": [{"state": s, "pf_k": v["pf"] / 1e3, "failed_k": v["failed"] / 1e3, "failed_pct": 100 * v["failed"] / v["pf"] if v["pf"] else None,
                    "prev_pf_k": st_prev.get(s, {}).get("pf", 0) / 1e3 or None} for s, v in states],
        "window_days": WINDOW,
    }
    tmp = FSA / ".cotton_estimate.json.tmp"
    tmp.write_text(json.dumps(out, indent=1, default=lambda x: None))
    tmp.replace(FSA / "cotton_estimate.json")
    E = out["estimate"]
    print(f"{cy}: FSA {now['fsa_pf']/1e6:.2f} m acres P+F as of {cur['asof']} -> planted {E['planted_m']:.2f}, abandon {E['abandon_pct']:.1f}%, harvested {E['harvested_m']:.2f}, "
          f"prod {E['prod_m480'] or 0:.2f} m bales at {yl} lb; USDA {now['usda_nov']}; backtest {len(bt)} yrs harv MAE {out['backtest']['mae_harv_pct']:.1f}% vs USDA {out['backtest']['usda_mae_harv_pct']}")


if __name__ == "__main__":
    main()
