#!/usr/bin/env python3
"""Energy summary for the morning brief and the Summary page: EIA inventories vs history, prices, cracks, vol.

Reads data/energy/eia/*.json (pipelines/energy_eia.py), data/energy/prices.json (energy_prices.py), and, when
present, data/options/<SYM>.json (CME implied vols) and data/vol/vol.json (realized vols).
Writes data/energy/summary.json.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
E = D / "energy"


def J(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def series(k):
    j = J(E / "eia" / f"{k}.json")
    return [(datetime.strptime(r[0][:10], "%Y-%m-%d").date(), r[1]) for r in j["rows"]] if j and j.get("rows") else []


def weekly_stats(rows, years=5):
    """Latest weekly level, change, vs a year ago and vs the same week's 5-year average."""
    if len(rows) < 60:
        return None
    d, v = rows[-1]
    prev = rows[-2][1]
    def near(target):
        c = min(rows, key=lambda r: abs((r[0] - target).days))
        return c[1] if abs((c[0] - target).days) <= 4 else None
    yago = near(d - timedelta(days=364))
    hist = [near(d - timedelta(days=364 * k)) for k in range(1, years + 1)]
    hist = [h for h in hist if h is not None]
    avg5 = sum(hist) / len(hist) if hist else None
    chg_hist = []
    for k in range(1, years + 1):
        a, b = near(d - timedelta(days=364 * k)), near(d - timedelta(days=364 * k + 7))
        if a is not None and b is not None:
            chg_hist.append(a - b)
    return {"date": d.isoformat(), "value": v, "chg": v - prev, "yago": yago, "avg5": avg5,
            "vs_avg5": None if avg5 is None else v - avg5, "vs_avg5_pct": None if not avg5 else 100 * (v / avg5 - 1),
            "vs_yago": None if yago is None else v - yago, "chg_avg5": sum(chg_hist) / len(chg_hist) if chg_hist else None}


def main():
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    inv = {}
    for k, name, unit in [("storL48", "Natural gas storage, Lower 48", "Bcf"), ("crude", "Crude stocks ex-SPR", "mb"), ("cushing", "Cushing crude", "mb"),
                          ("gaso", "Gasoline stocks", "mb"), ("dist", "Distillate stocks", "mb")]:
        s = weekly_stats(series(k))
        if s:
            s.update({"name": name, "unit": unit})
            if unit == "mb":   # EIA reports thousand barrels
                for f in ("value", "chg", "yago", "avg5", "vs_avg5", "vs_yago", "chg_avg5"):
                    if s.get(f) is not None:
                        s[f] = s[f] / 1000
            inv[k] = s
    out["inventories"] = inv
    util = series("util")
    if util:
        out["refinery_util"] = {"date": util[-1][0].isoformat(), "value": util[-1][1], "chg": util[-1][1] - util[-2][1] if len(util) > 1 else None}
    prod = series("prod")
    if prod:
        out["crude_prod"] = {"date": prod[-1][0].isoformat(), "value": prod[-1][1] / 1000, "unit": "mb/d"}
    hh = series("hhSpot")
    if hh:
        out["henry_hub_spot"] = {"date": hh[-1][0].isoformat(), "value": hh[-1][1]}
    P = (J(E / "prices.json") or {}).get("prices", {})
    px = {}
    for k in ("NG", "CL", "HO", "RB", "BZ"):
        b = P.get(k) or []
        if len(b) > 6:
            c = [x["c"] for x in b]
            px[k] = {"date": b[-1]["d"], "last": c[-1], "d1": 100 * (c[-1] / c[-2] - 1), "w1": 100 * (c[-1] / c[-6] - 1),
                     "m1": 100 * (c[-1] / c[-22] - 1) if len(c) > 22 else None}
    out["prices"] = px
    if all(k in px for k in ("CL", "HO", "RB")):
        cl, ho, rb = px["CL"]["last"], px["HO"]["last"] * 42, px["RB"]["last"] * 42
        out["cracks"] = {"321": (2 * rb + ho - 3 * cl) / 3, "ho": ho - cl, "rb": rb - cl}
    vol = (J(D / "vol" / "vol.json") or {}).get("markets", {})
    iv = {}
    for k in ("NG", "CL", "HO", "RB"):
        o = J(D / "options" / f"{k}.json")
        fr = None
        if o and o.get("expiries"):
            fr = next((e for e in o["expiries"] if e["contract"] == o.get("front")), o["expiries"][0])
        iv[k] = {"atm": fr.get("atm") if fr else None, "label": fr.get("label") if fr else None, "rr25": fr.get("rr25") if fr else None,
                 "rv20": (vol.get(k) or {}).get("hv20_front")}
    out["vol"] = iv
    # read
    t = []
    g = inv.get("storL48")
    if g:
        t.append(f"Gas storage {g['value']:,.0f} Bcf (week to {g['date']}), {g['chg']:+.0f} Bcf vs a 5-year average {g['chg_avg5']:+.0f} for the week; "
                 f"{g['vs_avg5']:+,.0f} Bcf ({g['vs_avg5_pct']:+.1f}%) vs the 5-year average, {g['vs_yago']:+,.0f} vs last year.")
    c = inv.get("crude")
    if c:
        t.append(f"Crude stocks {c['value']:.1f} mb ({c['chg']:+.1f} mb on the week, {c['vs_avg5_pct']:+.1f}% vs 5-yr avg)"
                 + (f"; gasoline {inv['gaso']['chg']:+.1f} mb, distillate {inv['dist']['chg']:+.1f} mb" if "gaso" in inv and "dist" in inv else "")
                 + (f"; refinery utilization {out['refinery_util']['value']:.1f}%" if out.get("refinery_util") else "") + ".")
    if out.get("cracks"):
        t.append(f"3-2-1 crack ${out['cracks']['321']:.2f}/bbl (ULSD ${out['cracks']['ho']:.2f}, gasoline ${out['cracks']['rb']:.2f}).")
    ivs = [f"{k} IV {v['atm']:.0f}% vs RV {v['rv20']:.0f}%" for k, v in iv.items() if v.get("atm") and v.get("rv20")]
    if ivs:
        t.append("Options: " + "; ".join(ivs) + ".")
    t.append("For ags: diesel and natural gas set farm fuel, drying and nitrogen fertilizer costs; crude and gasoline drive ethanol and biodiesel margins (corn, soybean oil).")
    out["read"] = " ".join(t)
    (E).mkdir(parents=True, exist_ok=True)
    (E / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    print(out["read"])


if __name__ == "__main__":
    main()
