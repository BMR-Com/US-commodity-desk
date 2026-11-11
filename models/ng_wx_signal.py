"""Natural gas weather-trend and squeeze-risk signal (Energy > Weather tab, energy summary, morning brief).

The 8 Nov research note read the 15-day ensembles correctly (warm through ~22 Nov) but missed the rally because:
  1. the desk only saw 15 days; the cold risk (SSW, negative AO, -EPO) sat in days 15-35;
  2. it compared forecast LEVELS with normal, while price moves on the CHANGE in forecasts over 1-3 days, especially the
     newest days entering the back end of the window;
  3. a crowded fund short is fuel, not a trigger: it matters only once the forecast trend turns colder.

This model puts those three things together. Inputs (all already on the desk):
  data/energy/wx/runs.json      run history of GEFS / ECMWF ENS / AIFS 15-day gas-weighted HDD, plus extended weeks
  data/energy/wx/hdd_ext.json   GEFS 35-day / EC46 / CFSv2 weekly anomalies (weeks 1-5)
  data/energy/wx/vortex.json    10 hPa 60N wind (SSW), GEFS AO / NAO / PNA forecasts
  cot/data/web/series/NG.json   CFTC managed money, NYMEX Henry Hub
  data/energy/prices.json       NG front-month OHLC
Output: data/energy/wx/signal.json (latest) and data/energy/wx/signal_hist.json (kept, so the rules can be scored later).
The thresholds are rules of thumb, not fitted; signal_hist.json exists so they can be tested against the price that followed.
"""
import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WX = ROOT / "data" / "energy" / "wx"
BCF_PER_HDD = 1.6   # winter storage sensitivity used on the Weather tab and in the research note


def J(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def ts(s):
    return dt.datetime.fromisoformat(s[:16])


def matched_change(cur, prev):
    ds = [d for d in cur if d in prev]
    return (sum(cur[d] - prev[d] for d in ds), len(ds)) if ds else (None, 0)


def trend(runs, hours):
    """Average change (HDD, matched dates) across the 15-day ensembles vs the newest run at least `hours` older."""
    if not runs:
        return None
    last = runs[-1]; t0 = ts(last["generated"]); out = {}
    for name, m in last["models"].items():
        for r in reversed(runs[:-1]):
            if (t0 - ts(r["generated"])).total_seconds() / 3600 >= hours and name in r["models"]:
                chg, n = matched_change(m["daily"], r["models"][name]["daily"])
                if chg is not None:
                    out[name] = {"hdd": round(chg, 1), "days": n, "vs_run": r["generated"]}
                break
    if not out:
        return None
    avg = sum(v["hdd"] for v in out.values()) / len(out)
    return {"avg_hdd": round(avg, 1), "bcf": round(avg * BCF_PER_HDD), "by_model": out}


def back_end(runs, k=5):
    """HDD vs normal per day over the last k days of each 15-day window: where new cold (or warmth) is entering."""
    if not runs:
        return None
    out = {}
    for name, m in runs[-1]["models"].items():
        ds = sorted(m["daily"])[-k:]
        if ds:
            out[name] = round(sum(m["daily"][d] - m["normal"].get(d, m["daily"][d]) for d in ds) / len(ds), 2)
    return {"avg_per_day": round(sum(out.values()) / len(out), 2), "by_model": out} if out else None


def extended(ext, runs):
    """Weeks 3-5 from the extended models, and the change against the extended run ~24h earlier (same week dates)."""
    res = {}
    prev_ext = None
    if runs and runs[-1].get("ext_generated"):
        t0 = ts(runs[-1]["ext_generated"])
        for r in reversed(runs[:-1]):
            if r.get("ext_generated") and (t0 - ts(r["ext_generated"])).total_seconds() / 3600 >= 20 and r.get("extended"):
                prev_ext = r["extended"]; break
    for name, v in (ext or {}).get("models", {}).items():
        wk = {w["week"]: w for w in v["weeks"]}
        row = {}
        for n in (3, 4, 5):
            if n in wk:
                w = wk[n]; chg = None
                if prev_ext and name in prev_ext:
                    p = next((x for x in prev_ext[name]["weeks"] if x["from"] == w["from"]), None)
                    chg = round(w["mean"] - p["mean"], 1) if p else None
                row[f"wk{n}"] = {"from": w["from"], "to": w["to"], "mean": w["mean"], "p10": w["p10"], "p90": w["p90"],
                                 "share_cold": w["share_cold"], "chg_24h": chg}
        if row:
            res[name] = row
    if not res:
        return None
    w34 = [r[k]["mean"] for r in res.values() for k in ("wk3", "wk4") if k in r]
    return {"wk34_avg": round(sum(w34) / len(w34), 1) if w34 else None, "by_model": res}


def tele(vort):
    if not vort:
        return None
    today = dt.date.today()
    out = {}
    for idx in ("ao", "nao", "pna"):
        days = ((vort.get("teleconnections", {}).get(idx) or {}).get("gefs") or {}).get("days", {})
        wk2 = [v["mean"] for d, v in days.items() if 7 <= (dt.date.fromisoformat(d) - today).days <= 14]
        allv = [v["mean"] for v in days.values()]
        if allv:
            out[idx] = {"now": allv[0], "wk2_mean": round(sum(wk2) / len(wk2), 2) if wk2 else None, "min": min(allv)}
    u = [x for s in vort.get("u10_60N_ms", {}).values() for d, x in s.items()
         if abs((dt.date.fromisoformat(d) - today).days) <= 10]
    out["u10_min"] = min(u) if u else None
    out["ssw"] = bool(u) and min(u) < 0
    return out


def positioning(cot):
    try:
        mm = cot["ct"]["all"]["managed_money"]; dates = cot["dates"]
    except Exception:
        return None
    net = [l - s for l, s in zip(mm["l"], mm["s"])]
    def pct(win):
        w = net[-win:]; return round(100 * sum(x <= net[-1] for x in w) / len(w), 1)
    return {"date": dates[-1], "net": net[-1], "chg_1w": net[-1] - net[-2], "chg_4w": net[-1] - net[-5],
            "pct_3y": pct(156), "pct_all": pct(len(net))}


def price(px):
    rows = (px or {}).get("prices", {}).get("NG") or []
    c = [r["c"] for r in rows if r.get("c") is not None]
    if len(c) < 20:
        return None
    g = [max(0, b - a) for a, b in zip(c[-15:-1], c[-14:])]; l = [max(0, a - b) for a, b in zip(c[-15:-1], c[-14:])]
    rsi = 100 - 100 / (1 + (sum(g) / 14) / (sum(l) / 14 or 1e-9))
    return {"date": rows[-1]["d"], "last": c[-1], "chg_5d_pct": round(100 * (c[-1] / c[-6] - 1), 1), "rsi14": round(rsi, 1)}


def ordinal(x):
    n = max(1, int(round(x)))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def main():
    runs = J(WX / "runs.json", [])
    ext = J(WX / "hdd_ext.json", {})
    vort = J(WX / "vortex.json", {})
    cot = J(ROOT / "cot" / "data" / "web" / "series" / "NG.json", {})
    px = J(ROOT / "data" / "energy" / "prices.json", {})

    t24, t72 = trend(runs, 20), trend(runs, 48)   # "72h" = newest run at least 2 days older
    be, ex, tl, pos, pr = back_end(runs), extended(ext, runs), tele(vort), positioning(cot), price(px)

    # cold-risk checklist: each item is something the market trades before the 15-day mean turns cold
    checks = []
    def add(key, ok, txt):
        checks.append({"key": key, "on": bool(ok), "text": txt})
    add("trend72", t72 and t72["avg_hdd"] >= 8, f"15-day ensembles colder over 2-3 days: {t72['avg_hdd']:+.1f} HDD on matched dates (≈{-t72['bcf']:+d} Bcf)" if t72 else "3-day trend: not enough run history")
    add("trend24", t24 and t24["avg_hdd"] >= 4, f"…and over ~24h: {t24['avg_hdd']:+.1f} HDD" if t24 else "24h trend: not enough run history")
    add("back_end", be and be["avg_per_day"] >= 0, f"back end of the 15-day window (last 5 days) {be['avg_per_day']:+.1f} HDD/day vs normal" if be else "back end: n/a")
    add("wk34", ex and ex["wk34_avg"] is not None and ex["wk34_avg"] >= 10, f"weeks 3-4 extended models {ex['wk34_avg']:+.0f} HDD/week vs normal" if ex and ex["wk34_avg"] is not None else "weeks 3-4: extended models not yet available")
    add("ao", tl and tl.get("ao", {}).get("wk2_mean") is not None and tl["ao"]["wk2_mean"] <= -1, f"GEFS AO week 2 {tl['ao']['wk2_mean']:+.2f} (now {tl['ao']['now']:+.2f})" if tl and tl.get("ao", {}).get("wk2_mean") is not None else "AO: n/a")
    add("pna", tl and tl.get("pna", {}).get("wk2_mean") is not None and tl["pna"]["wk2_mean"] >= 0.5, f"GEFS PNA week 2 {tl['pna']['wk2_mean']:+.2f} (western ridge / eastern trough)" if tl and tl.get("pna", {}).get("wk2_mean") is not None else "PNA: n/a")
    add("ssw", tl and tl.get("ssw"), f"stratospheric wind at 60N {tl['u10_min']:+.1f} m/s (below 0 = SSW; surface effect lags 2-8 weeks)" if tl and tl.get("u10_min") is not None else "SSW: n/a")
    n_on = sum(c["on"] for c in checks)

    # Weather is the trigger; positioning is only the fuel. A crowded short on its own has tended to keep winning,
    # so it never raises the regime by itself.
    on = {c["key"]: c["on"] for c in checks}
    weather_trigger = on["trend72"] or on["wk34"] or (on["trend24"] and on["back_end"])
    pattern_flags = sum(on[k] for k in ("ao", "pna", "ssw"))
    crowded = bool(pos and pos["pct_3y"] <= 10)
    if weather_trigger and crowded:
        regime, action = "HIGH", "Squeeze risk high: forecasts are turning colder into a crowded fund short. Do not sell rallies or add outright shorts; short ideas wait until the forecast trend stalls."
    elif weather_trigger or (crowded and pattern_flags >= 2):
        regime, action = "ELEVATED", ("Forecasts turning colder; positioning is not crowded, so the move needs the weather to verify." if weather_trigger and not crowded
                                      else "Cold-pattern signals are present but the models have not turned colder yet. Keep shorts small and in options; switch to HIGH if the 2-3 day trend or weeks 3-4 turn cold.")
    elif pos and pos["pct_3y"] >= 90 and not weather_trigger and n_on == 0:
        regime, action = "LONG-SQUEEZE", "Funds are crowded long while the weather trend is warm: downside air-pocket risk."
    else:
        regime, action = "LOW", "No colder forecast trend; trade the fundamentals and the curve."
    for c in checks:
        c["role"] = "trigger" if c["key"] in ("trend72", "trend24", "back_end", "wk34") else "pattern"
    exit_rules = ["Two consecutive model cycles not colder on matched dates (24h trend ≤ 0) AND weeks 3-4 no longer colder than normal",
                  "Managed money covers back above its 25th percentile (3-year)",
                  "Price fails at the 50-day average while the trend is flat"]

    out = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M"), "regime": regime, "action": action,
           "cold_checks_on": n_on, "cold_checks": checks, "trend_24h": t24, "trend_72h": t72, "back_end": be,
           "extended": ex, "teleconnections": tl, "positioning": pos, "price": pr, "exit_when": exit_rules,
           "bcf_per_hdd": BCF_PER_HDD,
           "note": "Rules of thumb, not fitted. signal_hist.json keeps every reading so the rules can be scored against what price did next."}
    pos_txt = f"managed money net {pos['net']:,} ({ordinal(pos['pct_3y'])} pct of 3 yrs, {pos['chg_4w']:+,} in 4 wks)" if pos else "COT n/a"
    out["read"] = (f"NG weather/positioning: squeeze risk {regime} ({n_on} of {len(checks)} cold-risk checks on; {pos_txt}). "
                   + "; ".join(c["text"] for c in checks if c["on"]) + ". " + action)
    (WX / "signal.json").write_text(json.dumps(out, indent=1))
    hist = J(WX / "signal_hist.json", [])
    hist.append({k: out[k] for k in ("generated", "regime", "cold_checks_on")} | {
        "trend24": t24 and t24["avg_hdd"], "trend72": t72 and t72["avg_hdd"], "back_end": be and be["avg_per_day"],
        "wk34": ex and ex["wk34_avg"], "mm_pct3y": pos and pos["pct_3y"], "px": pr and pr["last"]})
    (WX / "signal_hist.json").write_text(json.dumps(hist[-2000:], separators=(",", ":")))
    print(out["read"])


if __name__ == "__main__":
    main()
