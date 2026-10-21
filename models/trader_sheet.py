#!/usr/bin/env python3
"""Trader sheet: one row per market pulling together price action, curve, fund positioning, CTA trigger levels,
fundamentals (export pace, WASDE read), weather, the next scheduled catalyst with its typical move, and volatility,
plus rule-based flags worth a look. Built from the other models' outputs. Writes data/summary/sheet.json.
"""
import json, math
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
MKTS = [("ZC", "corn", "grains"), ("ZS", "soybeans", "grains"), ("ZM", "meal", "grains"), ("ZL", "oil", "grains"), ("ZW", "wheat", "grains"),
        ("KE", "kc", "grains"), ("CT", "cotton", "softs"), ("HE", None, "livestock"), ("LE", None, "livestock"), ("GF", None, "livestock"),
        ("DC", None, "dairy"), ("GDK", None, "dairy")]
EVT = [("WASDE", "WASDE / Crop Production"), ("Crop Production", "WASDE / Crop Production"), ("Grain Stocks", "Grain Stocks"), ("Acreage", "Acreage"),
       ("Prospective Plantings", "Prospective Plantings"), ("Hogs and Pigs", "Hogs and Pigs"), ("Cattle on Feed", "Cattle on Feed"), ("export sales", "Export sales")]


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def main():
    summ = {m["sym"]: m for m in (J("summary/summary.json") or {}).get("markets", [])}
    cot = (J("cot_desk/summary.json") or {}).get("markets", {})
    rv = J("grains/derived/rv.json") or {}
    rr = (J("grains/derived/report_reaction.json") or {}).get("markets", {})
    esr = {b["key"]: b for b in (J("grains/derived/esr_brief.json") or {}).get("commodities", [])}
    idx = J("grains/derived/wasde_brief/index.json")
    wb = (J(f"grains/derived/wasde_brief/{idx['reports'][0]['report']}.json") or {}).get("commodities", {}) if idx else {}
    cal = (J("calendar/calendar.json") or {}).get("events", [])
    wx = (J("weather/weather.json") or {}).get("regions", [])
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    rows = []
    for sym, key, grp in MKTS:
        T = J(f"technicals/{sym}.json")
        if not T:
            continue
        s = next((x for x in T["series"] if x["ticker"] == T["default"]), T["series"][0]); a = s["analysis"]
        r = {"sym": sym, "name": T.get("name") or sym, "group": grp, "contract": s.get("label"), "unit": T.get("unit"), "last": a.get("last"), "chg": a.get("chg"),
             "r1w": (a.get("returns") or {}).get("1w"), "r1m": (a.get("returns") or {}).get("1m"), "rsi": a.get("rsi"), "rating": (a.get("rating_daily") or {}).get("overall"),
             "trend": a.get("trend"), "atr": a.get("atr"), "sup": (a.get("support") or [None])[0], "res": (a.get("resistance") or [None])[0],
             "hi52": a.get("hi52"), "lo52": a.get("lo52")}
        c = cot.get(sym) or {}
        r.update({"mm_net": c.get("N"), "mm_dn": c.get("dN"), "mm_pct3": c.get("pct3"), "mm_pct10": c.get("pct10"), "driver": c.get("driver"),
                  "cta": c.get("cta_score"), "cta_up": ((c.get("next") or {}).get("up") or {}).get("lvl"), "cta_dn": ((c.get("next") or {}).get("dn") or {}).get("lvl"),
                  "long_uw": c.get("long_uw"), "short_uw": c.get("short_uw")})
        m = (rv.get("markets") or {}).get(sym) or {}
        if m.get("spreads"):
            sp = m["spreads"][0]
            r.update({"spread": sp["pair"], "spread_v": sp["spread"], "pct_full": sp.get("pct_full"), "spread_pct": sp.get("pctile"), "spread_read": sp.get("read")})
        v = m.get("vol") or {}
        r.update({"hv20": v.get("hv20"), "hv_pct": v.get("hv20_pct10"), "day_move": v.get("day_move"), "day_move_usd": v.get("day_move_usd")})
        b = esr.get(key) if key else None
        if b:
            r.update({"esr_pace": b.get("pace"), "esr_norm": b.get("pace_norm"), "esr_implied": b.get("implied"), "esr_target": b.get("target"), "esr_unit": b.get("w_unit")})
        w = wb.get(key) if key else None
        if w:
            r["wasde"] = w.get("outlook")
        sm = summ.get(sym) or {}
        r.update({"view": sm.get("view"), "conviction": sm.get("conviction")})
        risk = [x for x in wx if sym in x.get("markets", []) and x.get("risk", 0) >= 1]
        r["weather"] = "; ".join(f"{x['region']}" for x in sorted(risk, key=lambda x: -x["risk"])[:2]) or None
        ev = [e for e in cal if e["date"] >= today and (sym in e["markets"] or "ALL" in e["markets"]) and e["importance"] >= 2 and e["cat"] != "Holiday"]
        ev = sorted(ev, key=lambda e: (e["date"], -e["importance"]))
        big = next((e for e in ev if e["importance"] >= 3), None)
        nxt = big or (ev[0] if ev else None)
        if nxt:
            r.update({"event": nxt["event"], "event_date": nxt["date"]})
            t = next((t for k, t in EVT if k.lower() in nxt["event"].lower()), None)
            x = (rr.get(sym) or {}).get("reports", {}).get(t) if t else None
            if x:
                r.update({"event_move": x["exp_move"], "event_move_usd": x["exp_move_usd"], "event_ratio": x["ratio"], "event_p90": x["p90_move"]})
        # flags
        F = []
        if r.get("mm_pct10") is not None and r["mm_pct10"] >= 90: F.append(("bear", f"Funds near a 10-yr long extreme ({r['mm_pct10']:.0f}th pct)"))
        if r.get("mm_pct10") is not None and r["mm_pct10"] <= 10: F.append(("bull", f"Funds near a 10-yr short extreme ({r['mm_pct10']:.0f}th pct)"))
        if r.get("short_uw") is not None and r["short_uw"] >= 70 and (r.get("mm_net") or 0) < 0: F.append(("bull", f"{r['short_uw']:.0f}% of fund shorts under water"))
        if r.get("long_uw") is not None and r["long_uw"] >= 70 and (r.get("mm_net") or 0) > 0: F.append(("bear", f"{r['long_uw']:.0f}% of fund longs under water"))
        if r.get("rsi") is not None and r["rsi"] < 30: F.append(("bull", f"RSI {r['rsi']:.0f}: oversold"))
        if r.get("rsi") is not None and r["rsi"] > 70: F.append(("bear", f"RSI {r['rsi']:.0f}: overbought"))
        if r.get("pct_full") is not None and r["pct_full"] >= 80: F.append(("bear", f"{r['spread']} at {r['pct_full']:.0f}% of full carry"))
        if r.get("pct_full") is not None and r["pct_full"] < 0: F.append(("bull", f"{r['spread']} inverted"))
        if r.get("esr_pace") and r.get("esr_norm"):
            g = r["esr_pace"] / r["esr_norm"] - 1
            if abs(g) >= 0.12: F.append(("bull" if g > 0 else "bear", f"Export commitments {g*100:+.0f}% vs normal pace"))
        if r.get("hv_pct") is not None and r["hv_pct"] <= 15: F.append(("neutral", f"Realized vol low ({r['hv20']:.0f}%, {r['hv_pct']:.0f}th pct): cheap to own optionality into catalysts"))
        if r.get("hv_pct") is not None and r["hv_pct"] >= 85: F.append(("neutral", f"Realized vol high ({r['hv20']:.0f}%, {r['hv_pct']:.0f}th pct)"))
        if r.get("weather"): F.append(("neutral", f"Weather watch: {r['weather']}"))
        r["flags"] = [{"tilt": t, "text": x} for t, x in F]
        rows.append(r)
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "rate": rv.get("rate"),
           "crush": (rv.get("crush") or {}).get("front"), "ratios": [{k: x[k] for k in ("name", "unit", "now", "pct10", "med10", "chg_20d")} for x in rv.get("ratios", [])],
           "rows": rows}
    (D / "summary" / "sheet.json").write_text(json.dumps(out, separators=(",", ":"), default=lambda o: None))
    for r in rows:
        print(r["sym"], r.get("last"), r.get("view"), r.get("event"), r.get("event_move"), [f["text"] for f in r["flags"]][:3])


if __name__ == "__main__":
    main()
