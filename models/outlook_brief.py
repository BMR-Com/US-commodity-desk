"""Outlook in brief, per market: crop, exports, ending stocks (desk base case), positioning, technicals, options flow and a
bottom line. Shown at the top of each market's Outlook tab and on the Summary tab.
Reads: data/derived/balance_sheets.json, data/grains/derived/esr_brief.json, data/grains/derived/condition.json,
cotton-crop-progress crop_projection.json, data/cot_desk/<SYM>.json, data/technicals/<SYM>.json,
data/cme/<date>/opt_volume_oi.csv (CME options), softs--options- CT_desk.json (ICE cotton options), data/summary/summary.json.
Output: data/derived/outlook_brief.json
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "derived" / "outlook_brief.json"
CROP_URL = "https://bmr-com.github.io/cotton-crop-progress/data/crop_projection.json"
CT_OPT_URL = "https://bmr-com.github.io/softs--options-/data/web/CT_desk.json"
MARKETS = [("cotton", "CT", "Cotton"), ("corn", "ZC", "Corn"), ("soybeans", "ZS", "Soybeans"), ("meal", "ZM", "Soybean meal"), ("oil", "ZL", "Soybean oil"),
           ("wheat", "ZW", "Chicago wheat"), ("kc", "KE", "KC HRW wheat"), ("hogs", "HE", "Lean hogs"), ("cattle", "LE", "Live cattle"),
           ("feeders", "GF", "Feeder cattle"), ("dairy", "DC", "Class III milk")]


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def web(url, local=None):
    try:
        import requests
        return requests.get(url, timeout=60).json()
    except Exception:
        try:
            return json.loads(Path(local).read_text()) if local else None
        except Exception:
            return None


def n(v, d=0):
    return "–" if v is None else f"{v:,.{d}f}"


def ord_(v):
    if v is None:
        return "–"
    v = int(round(v)); return f"{v}{'th' if 10 <= v % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(v % 10, 'th')}"


# ───────── pieces ─────────
def crop_line(key, B, cond, cp):
    m = B.get(key) if B else None
    if key == "cotton" and cp and cp.get("us_all"):
        a, u = cp["us_all"], cp.get("usda") or {}
        ab, abu = ((cp.get("texas") or {}).get("abandonment") or {}).get("central"), u.get("tx_abandonment")
        b = (m or {}).get("bounds") or {}
        cut = a["central"] / u["us_all"] - 1 if u.get("us_all") else None
        t = (f"Crop model {a['central']:.2f}m bales vs USDA {u.get('us_all', 0):.2f}m ({cut:+.0%})"
             + (f", driven by Texas abandonment of {ab:.0%} vs USDA's {abu:.0%} on drought and poor ratings" if ab is not None and abu is not None else "") + ". ")
        if b.get("dP_min") is not None and cut is not None and cut <= 0.8 * b["dP_min"]:
            t += f"A cut that size after the {b['month']} report has happened once since {b['first']} ({b['dP_min_my']}, {b['dP_min']:+.0%}), so the model sits near the edge of history. "
        return t, (-1 if cut is not None and cut > 0.03 else 1 if cut is not None and cut < -0.03 else 0)
    if key in ("corn", "soybeans"):
        md = (cond.get(key) or {}).get("model") or {}
        if md.get("estimate"):
            gap = md["estimate"] - md["usda"]
            return (f"Condition yield model {md['estimate']:.1f} bu/ac vs USDA {md['usda']:.1f} ({gap:+.1f}; the model's average miss is ±{(md.get('test') or {}).get('mae_model', 0):.1f}). "
                    + ("Harvest is well advanced, so the crop number is mostly settled. " if (md.get("week") or 0) >= 34 else "")), (-1 if gap > 1 else 1 if gap < -1 else 0)
    if key in ("wheat", "kc"):
        return "Harvest is complete; USDA's production number stands. ", 0
    if key in ("meal", "oil"):
        return "Supply follows the soybean crush (see soybeans). ", 0
    return None, 0


def export_line(key, E, B=None):
    b = (E or {}).get(key)
    if not b:
        return None, 0
    pr, tgt, u = b.get("implied"), b.get("target"), b.get("w_unit", "")
    dec = b.get("w_fmt", 0)
    bl = next((x["t"] for x in b.get("brief", []) if x["h"] == "Bottom line"), "")
    tilt = b.get("tilt")
    t = (f"Export sales (week {b['wk']}) project {pr:,.{dec}f} {u} vs USDA {tgt:,.{dec}f} ({pr / tgt - 1:+.0%}); commitments {b['commit'] / b['ly_commit'] - 1:+.0%} vs a year ago. " if pr and tgt and b.get("ly_commit") else "")
    mb = (B or {}).get(key) or {}
    if mb.get("exp_miss") is not None and mb["exp_miss"] >= 10:
        t += f"Early read: at week {b['wk']} the projection has missed by about {mb['exp_miss']:.0f}% on average. "
    if "**" in bl:
        t += "Outlook " + bl.split("**")[1].replace("USDA's", "USDA's") + ". "
    return t, {"strong": 1, "weak": -1}.get(tilt, 0)


def balance_line(key, B):
    m = (B or {}).get(key)
    if not m or m.get("product"):
        return None, 0
    S, d = m["summary"], m["dec"]
    b = S["base"]
    t = (f"Desk base case {m['cur']} ending stocks {b['end']:,.{d}f} vs USDA {m['usda_end']:,.{d}f} (stocks/use {b['su']:.1f}% vs {m['usda_su']:.1f}%); "
         f"bearish {S['bear']['end']:,.{d}f}, bullish {S['bull']['end']:,.{d}f}. ")
    r = b["su"] / m["usda_su"] - 1 if m.get("usda_su") else 0
    return t, (1 if r < -0.1 else -1 if r > 0.1 else 0)


def cot_line(sym):
    c = J(f"cot_desk/{sym}.json")
    if not c:
        return None, 0
    mm, cta = c["cats"]["mm"], c.get("cta") or {}
    p3 = (mm.get("pct") or {}).get("y3")
    t = (f"Managed money net {'long' if mm['N'] >= 0 else 'short'} {abs(mm['N']):,.0f} lots ({ord_(p3)} percentile of 3 years), "
         f"{'+' if mm['dN'] >= 0 else ''}{mm['dN']:,.0f} on the week (as of {c.get('date')}). ")
    nx = cta.get("next") or {}
    if cta and cta.get("r2", 0) >= 0.3:
        t += f"Trend signals {'long' if cta['score'] > 0.25 else 'short' if cta['score'] < -0.25 else 'mixed'}" + (f"; trend-follower selling below {nx['dn']['lvl']:.2f}" if nx.get("dn") else "") + (f", buying above {nx['up']['lvl']:.2f}" if nx.get("up") else "") + ". "
    sc = 0
    if p3 is not None and p3 >= 85:
        t += "Funds are crowded long — a source of selling if the trend turns. "; sc = -1 if (cta.get("score") or 0) <= 0 else 0
    elif p3 is not None and p3 <= 15:
        t += "Funds are crowded short — short-covering fuel if prices turn up. "; sc = 1 if (cta.get("score") or 0) >= 0 else 0
    return t, sc


def tech_line(sym):
    t = J(f"technicals/{sym}.json")
    if not t:
        return None, 0
    s = next((x for x in t["series"] if x["ticker"] == t["default"]), t["series"][0]); a = s["analysis"]; dp = t.get("dp", 2)
    rd, rw = (a.get("rating_daily") or {}).get("overall", "Neutral"), (a.get("rating_weekly") or {}).get("overall", "Neutral")
    r = a.get("returns") or {}
    x = (f"{s['label']} {a['last']:.{dp}f} ({'+' if (r.get('1w') or 0) >= 0 else ''}{(r.get('1w') or 0):.1f}% on the week), {a['trend']} trend; daily {rd.lower()}, weekly {rw.lower()}; RSI {a['rsi']:.0f}"
         + (f"; support {a['support'][0]:.{dp}f}, resistance {a['resistance'][0]:.{dp}f}" if a.get("support") and a.get("resistance") else "") + ". ")
    sc = {"Strong buy": 1, "Buy": 0.5, "Neutral": 0, "Sell": -0.5, "Strong sell": -1}
    v = 0.5 * sc.get(rd, 0) + 0.5 * sc.get(rw, 0) + (0.5 if a["trend"] == "up" else -0.5 if a["trend"] == "down" else 0)
    return x, (1 if v >= 0.5 else -1 if v <= -0.5 else 0)


def cme_options(sym):
    days = sorted(p.name for p in (D / "cme").iterdir() if p.is_dir() and p.name.isdigit() and (p / "opt_volume_oi.csv").exists())[-25:]
    if len(days) < 6:
        return None, 0
    rows = []
    for dname in days:
        try:
            x = pd.read_csv(D / "cme" / dname / "opt_volume_oi.csv")
        except Exception:
            continue
        x = x[x.sym == sym]
        if len(x):
            g = x.groupby("cp")[["total_vol", "oi", "oi_change"]].sum()
            rows.append({"d": dname, "cv": g.total_vol.get("C", 0), "pv": g.total_vol.get("P", 0), "coi": g.oi.get("C", 0), "poi": g.oi.get("P", 0),
                         "cch": g.oi_change.get("C", 0), "pch": g.oi_change.get("P", 0), "x": x})
    if len(rows) < 6:
        return None, 0
    R = pd.DataFrame([{k: v for k, v in r.items() if k != "x"} for r in rows])
    l5, prev = R.tail(5), R.iloc[:-5]
    pc5 = l5.pv.sum() / max(l5.cv.sum(), 1); pcp = prev.pv.sum() / max(prev.cv.sum(), 1) if len(prev) else None
    last = rows[-1]; x = last["x"]
    top = x.sort_values("oi_change", ascending=False).head(1)
    t = (f"CME options, last 5 sessions: put/call volume {pc5:.2f}" + (f" vs {pcp:.2f} over the previous {len(prev)} sessions" if pcp else "")
         + (" — more put buying" if pcp and pc5 > 1.25 * pcp else " — more call buying" if pcp and pc5 < 0.8 * pcp else "") + ". ")
    if len(top) and top.oi_change.iloc[0] > 0:
        r0 = top.iloc[0]; t += f"Biggest build: {r0.month.title()} {r0.strike:g} {'calls' if r0.cp == 'C' else 'puts'} (+{r0.oi_change:,.0f}). "
    sc = 0
    if pcp:
        sc = 1 if pc5 < 0.8 * pcp else -1 if pc5 > 1.25 * pcp else 0
    return t, sc


def ct_options():
    o = web(CT_OPT_URL, ROOT.parent / "bmr-com/softs--options-/data/web/CT_desk.json")
    if not o:
        return None, 0
    mp = (o.get("maps") or [{}])[0]
    t = (f"ICE options ({o['front_label']}, {o['date']}): ATM implied vol {o['atm']:.1f}% ({ord_(o.get('pct1y'))} percentile of the past year), "
         f"25-delta risk reversal {o['rr25']:+.1f} ({'puts bid over calls' if o['rr25'] < 0 else 'calls bid over puts'}), put/call open interest {o['pc_oi']:.2f}"
         + (f"; put wall {mp['put_wall']:g}, call wall {mp['call_wall']:g}" if mp.get("put_wall") else "") + f". Options lean: {o.get('lean', 'neutral')}. ")
    return t, (-1 if "bear" in (o.get("lean") or "") else 1 if "bull" in (o.get("lean") or "") else 0)


def ams_lines():
    """Cotton field and mill reports from the USDA AMS Weekly Cotton Market Review and Forward Contracting Report."""
    d, fc = J("cotton_review/latest.json"), J("cotton_review/forward_contracting.json")
    out = []
    if d and d.get("brief"):
        hl = d["brief"].get("headline") or []
        watch = next((x for x in hl if x.startswith("Watch:")), None)
        harv = next((x for x in hl if x.startswith("Harvest")), None)
        t = " ".join(x for x in (watch, harv) if x)
        if t:
            out.append({"h": f"Field reports (AMS, {d['date']})", "t": t})
        dem = next((x for x in hl if x.startswith("Demand:")), None)
        dom = next((x for x in (d.get("domestic_mill") or []) if x.startswith("Domestic mill")), None)
        if dem or dom:
            out.append({"h": "Mill demand (AMS)", "t": " ".join(x for x in (dem, dom) if x)})
    if fc and fc.get("latest"):
        r = fc["reports"][fc["latest"]]; us = next((x for x in r["rows"] if x["loc"] == "United States"), None); tx = next((x for x in r["rows"] if x["loc"] == "Texas"), None)
        if us and us.get("pct") is not None:
            p5 = [v for v in us["prior"][:5] if v is not None and v <= 100]
            out.append({"h": "Grower forward contracting (AMS)", "t": f"{us['pct']:.0f}% of US acres contracted as of {r['as_of']} vs {us['prior'][0]:.0f}% a year ago"
                        + (f" and a {sum(p5) / len(p5):.0f}% five-season average" if p5 else "") + (f"; Texas {tx['pct']:.0f}%" if tx and tx.get("pct") is not None else "")
                        + ". More of the crop is priced early, leaving less grower selling for later."})
    return out


def bottom(name, parts):
    fund = sum(parts.get(k, 0) for k in ("crop", "exports", "balance"))
    tech, cot, opt = parts.get("tech", 0), parts.get("cot", 0), parts.get("options", 0)
    fw = "bullish" if fund >= 1 else "bearish" if fund <= -1 else "neutral"
    mw = "bullish" if tech + opt >= 1 else "bearish" if tech + opt <= -1 else "mixed"
    if fw != "neutral" and mw != "mixed" and fw != mw:
        tail = f"The two disagree: the {fw} fundamental case needs price to confirm before leaning on it."
    elif fw != "neutral" and fw == mw:
        tail = f"Both point the same way — the {fw} case has confirmation."
    elif fw != "neutral":
        tail = f"Price has not yet picked a side; the {fw} fundamental case is the guide."
    else:
        tail = "No strong fundamental edge; trade the technical levels."
    crowd = " Fund positioning is crowded, which raises the risk of sharp moves." if cot != 0 else ""
    return f"{name}: fundamentals {fw}, technicals and options {mw}. {tail}{crowd}"


def build():
    B = (J("derived/balance_sheets.json") or {}).get("markets") or {}
    E = {c["key"]: c for c in (J("grains/derived/esr_brief.json") or {}).get("commodities", [])}
    cond = J("grains/derived/condition.json") or {}
    cp = web(CROP_URL, ROOT.parent / "bmr-com/cotton-crop-progress/docs/data/crop_projection.json")
    SM = {m["sym"]: m for m in (J("summary/summary.json") or {}).get("markets", [])}
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "markets": {}}
    for key, sym, name in MARKETS:
        items, parts = [], {}
        for lab, (txt, sc) in (("Crop", crop_line(key, B, cond, cp)), ("Exports", export_line(key, E, B)), ("Balance sheet", balance_line(key, B))):
            if txt:
                items.append({"h": lab, "t": txt.strip()}); parts[{"Crop": "crop", "Exports": "exports", "Balance sheet": "balance"}[lab]] = sc
        if key == "cotton":
            ins = ams_lines()
            pos = next((i for i, x in enumerate(items) if x["h"] == "Exports"), len(items))
            items[pos:pos] = ins
            try:
                po = J("derived/ct_price_outlook.json")
                if po:
                    M, Sb, Hd = po["mc"], po["scenarios"]["base"], po["hedge"]
                    items.insert(next((i for i, x in enumerate(items) if x["h"] == "Balance sheet"), len(items) - 1) + 1,
                                 {"h": "Price and spreads", "t": f"On the desk base case history points May (now {po['prices']['K']:.2f}) to about {Sb['may']:.0f} by expiry; the simulation gives "
                                  f"{M['may_expiry']['10']:.0f}–{M['may_expiry']['90']:.0f} (10th–90th percentile), a {M['p_above']['90']:.0f}% chance May trades 90 or higher and {M['p_below']['78']:.0f}% that it trades 78 or lower along the way. "
                                  f"Merchants' shorts are {Hd['pct']:.0f}% of world exports, the most at this time of year since 2010/11; in heavily hedged seasons May rose {Hd['high_mean']:.0f}% on average. "
                                  + (f"On the level of US stocks/use, May already implies {po['fair']['implied_su']['ex_2010']:.0f}–{po['fair']['implied_su']['all']:.0f}% (USDA {po['usda_su']:.1f}%): close to the desk base, whose fair value is {po['fair']['scen']['base']['ex_2010']:.0f}–{po['fair']['scen']['base']['all']:.0f}; the bullish tail ({po['fair']['scen']['bull']['su']:.0f}%) is worth {po['fair']['scen']['bull']['ex_2010']:.0f}–{po['fair']['scen']['bull']['all']:.0f} and is not priced. " if po.get("fair") else "")
                                  + f"Spreads: Mar/May {po['spreads']['HK']:+.2f} should stay a carry (median {M['mar_may']['50']:+.1f} near expiry), May/Jul {po['spreads']['KN']:+.2f} has a {M['p_kn_inverse']:.0f}% chance of inverting, "
                                  f"and Jul/Dec {po['spreads']['NZ']:+.2f} is already above what US stocks alone justify (median {M['jul_dec']['50']:+.1f} by June) unless world supply turns short."})
            except Exception as e:
                print("price line skipped:", repr(e)[:120])
            try:
                from india_read import india_for_us
                it, isc = india_for_us()
                if it:
                    pos = next((i for i, x in enumerate(items) if x["h"] == "Exports"), len(items) - 1) + 1
                    items.insert(pos, {"h": "India", "t": it})
                    parts["exports"] = max(parts.get("exports", 0), isc)
            except Exception as e:
                print("india line skipped:", repr(e)[:120])
        if not items and SM.get(sym):                   # livestock and dairy: the desk's fundamental read
            f = (SM[sym].get("paras") or {}).get("fundamental", "")
            if f:
                import re
                f = re.sub(r"<[^>]+>", "", f); sents = [x.strip() for x in re.split(r"(?<=\.)\s+", f) if x.strip()]
                items.append({"h": "Fundamentals", "t": " ".join(sents[:3])})
                parts["crop"] = 1 if SM[sym]["scores"].get("fundamental", 0) >= 0.25 else -1 if SM[sym]["scores"].get("fundamental", 0) <= -0.25 else 0
        for lab, k_, fn in (("Positioning (COT)", "cot", lambda: cot_line(sym)), ("Technicals", "tech", lambda: tech_line(sym)),
                            ("Options flow", "options", (lambda: ct_options()) if sym == "CT" else (lambda: cme_options(sym)))):
            try:
                txt, sc = fn()
            except Exception:
                txt, sc = None, 0
            if txt:
                items.append({"h": lab, "t": txt.strip()}); parts[k_] = sc
        items.append({"h": "Bottom line", "t": bottom(name, parts)})
        out["markets"][key] = {"sym": sym, "name": name, "items": items, "parts": parts}
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    for k, m in out["markets"].items():
        print(f"\n== {m['name']}")
        for i in m["items"]:
            print(f"  [{i['h']}] {i['t']}")


if __name__ == "__main__":
    build()
