"""Desk summary: for each market a written read of fundamentals, technicals and flows, an overall view, and
trade ideas from separate methods, each labelled with how well that method has tested on this desk.

Rule-based text built from the other models' outputs (no language model needed), so it updates with the data.
Writes data/summary/summary.json.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "summary"
MARKETS = [  # key, symbol, group, display, grains wasde key
    ("corn", "ZC", "grains", "Corn", "corn"), ("soybeans", "ZS", "grains", "Soybeans", "soybeans"),
    ("meal", "ZM", "grains", "Soybean meal", "meal"), ("oil", "ZL", "grains", "Soybean oil", "oil"),
    ("wheat", "ZW", "grains", "Chicago SRW wheat", "wheat"), ("kc", "KE", "grains", "KC HRW wheat", "wheat"),
    ("hogs", "HE", "livestock", "Lean hogs", None), ("cattle", "LE", "livestock", "Live cattle", None),
    ("feeders", "GF", "livestock", "Feeder cattle", None),
    ("class3", "DC", "dairy", "Class III milk", None), ("class4", "GDK", "dairy", "Class IV milk", None)]
LINK = {"grains": "#g/{key}/g-outlook", "livestock": None, "dairy": "#d-outlook"}


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def f(v, d=1):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.{d}f}"


def sg(v, d=1, suf=""):
    return "–" if v is None else f"{'+' if v > 0 else ''}{v:,.{d}f}{suf}"


def ordn(v):
    if v is None:
        return "–"
    n = int(round(v))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def word(score):
    if score is None:
        return "no clear signal"
    return ("strongly bullish" if score >= 0.6 else "bullish" if score >= 0.25 else "mildly bullish" if score >= 0.1 else
            "strongly bearish" if score <= -0.6 else "bearish" if score <= -0.25 else "mildly bearish" if score <= -0.1 else "neutral")


# ───────── technicals ─────────
def technical(sym):
    t = J(f"technicals/{sym}.json")
    if not t:
        return None, "Price data not available yet.", {}
    s = next((x for x in t["series"] if x["ticker"] == t["default"]), t["series"][0])
    a, u, dp = s["analysis"], t["unit"], t["dp"]
    rd, rw = (a.get("rating_daily") or {}).get("overall", "Neutral"), (a.get("rating_weekly") or {}).get("overall", "Neutral")
    sc = {"Strong buy": 1, "Buy": 0.5, "Neutral": 0, "Sell": -0.5, "Strong sell": -1}
    trend = {"up": 1, "down": -1}.get(a["trend"], 0)
    score = 0.4 * sc.get(rd, 0) + 0.3 * sc.get(rw, 0) + 0.3 * trend
    r = a.get("returns") or {}
    seas = (t.get("seasonal") or [None])[0]
    spreads = [x for x in (t.get("seasonal") or []) if x["kind"] == "spread"]
    txt = (f"{s['label']} trades at {a['last']:.{dp}f} {u} ({sg(r.get('1w'), 1, '%')} on the week, {sg(r.get('1m'), 1, '%')} on the month), "
           f"in a{'n' if a['trend'] == 'up' else ''} {a['trend']} trend: the daily rating is {rd.lower()} and the weekly {rw.lower()}. "
           f"RSI is {a['rsi']:.0f}{' (oversold)' if a['rsi'] < 30 else ' (overbought)' if a['rsi'] > 70 else ''} and ADX {a['adx']:.0f} "
           f"({'trending' if a['adx'] > 25 else 'weak trend' if a['adx'] > 20 else 'range-bound'}). ")
    if a.get("support") and a.get("resistance"):
        txt += f"Nearest support {a['support'][0]:.{dp}f}, resistance {a['resistance'][0]:.{dp}f}; 52-week range {a['lo52']:.{dp}f}–{a['hi52']:.{dp}f}. "
    if seas and seas.get("pct_same_time") is not None:
        p = seas["pct_same_time"]
        txt += (f"Against the same point of past seasons, {seas['label'].replace(' futures', '')} sits at the {ordn(p)} percentile "
                f"({'expensive' if p >= 80 else 'cheap' if p <= 20 else 'mid-range'} vs a {seas['n_years']}-year history). ")
    ext = [x for x in spreads if x.get("pct_same_time") is not None and (x["pct_same_time"] >= 85 or x["pct_same_time"] <= 15)]
    if ext:
        x = ext[0]
        txt += f"The {x['label']} at {x['now']:.{dp}f} is at the {ordn(x['pct_same_time'])} percentile for the time of year ({'unusually firm front' if x['pct_same_time'] >= 85 else 'unusually wide carry'})."
    return score, txt, {"t": t, "s": s, "a": a, "seas": seas, "spreads": spreads, "rd": rd, "rw": rw}


# ───────── flows ─────────
def flows(sym, group):
    c = J(f"cot_desk/{sym}.json")
    if not c:
        return None, "Positioning data not available yet.", {}
    mm = c["cats"]["mm"]
    p3 = mm["pct"]["y3"]
    cta = c.get("cta") or {}
    uw = c.get("underwater") or {}
    txt = (f"Managed money is net {'long' if mm['N'] >= 0 else 'short'} {abs(mm['N']):,.0f} lots ({ordn(p3)} percentile of 3 years, {ordn(mm['pct'].get('y10'))} of 10 years, {ordn(mm['pct'].get('all'))} of all history since {c.get('history_since', '2006')[:4]}; "
           f"{mm['np_oi']:.1f}% of open interest), {'+' if mm['dN'] >= 0 else ''}{mm['dN']:,.0f} on the week ({c.get('driver') or 'flat'}; z {mm['z']}). ")
    if (c.get("usd") or {}).get("N") is not None:
        txt += f"That is about ${abs(c['usd']['N']) / 1e9:.2f}bn of exposure. "
    if uw.get("long") and uw.get("short"):
        L, S = uw["long"], uw["short"]
        txt += (f"By our cost estimate, {L['pct_underwater']:.0f}% of fund longs (average entry {L['avg_entry']:.2f}) and {S['pct_underwater']:.0f}% of shorts "
                f"(average {S['avg_entry']:.2f}) are under water; longs are {'up' if L['pnl_usd'] >= 0 else 'down'} ${abs(L['pnl_usd']) / 1e6:,.0f}m, "
                f"shorts {'up' if S['pnl_usd'] >= 0 else 'down'} ${abs(S['pnl_usd']) / 1e6:,.0f}m. ")
    trend_ok = cta and cta.get("r2", 0) >= 0.3
    if cta:
        nx = cta.get("next") or {}
        txt += (f"The trend score is {cta['score']:+.2f} ({'all signals long' if cta['score'] >= 0.75 else 'all signals short' if cta['score'] <= -0.75 else 'mixed'}); "
                f"funds are {abs(cta['gap_lots']):,.0f} lots {'longer' if cta['gap_lots'] > 0 else 'shorter'} than the trend implies. ")
        if trend_ok and (nx.get("up") or nx.get("dn")):
            txt += ("Trend-follower triggers: " + "; ".join(
                f"{k} {v['lvl']:.2f} ({v['name']}, {v['pct']:+.1f}%)" for k, v in (("up", nx.get("up")), ("down", nx.get("dn"))) if v)
                + f", each signal flip worth roughly {abs(cta['beta_lots']) / 2:,.0f} lots of fund flow. ")
        elif not trend_ok:
            txt += "Trend explains little of fund positioning in this market, so trend-follower levels carry less weight. "
    txt += ("Positioning is a secondary input in these cash-settled/delivery markets."
            if group != "grains" else "In grains positioning has not predicted price on its own in our tests; it maps crowding and the levels where flows can accelerate.")
    # flows score: trend-following component + crowding against trend
    sc = 0.0
    if cta:
        sc += 0.6 * cta["score"]
        if p3 is not None and p3 >= 90 and cta["score"] <= 0:
            sc -= 0.3
        if p3 is not None and p3 <= 10 and cta["score"] >= 0:
            sc += 0.3
    return max(-1, min(1, sc)), txt, {"c": c, "mm": mm, "cta": cta, "uw": uw, "p3": p3}


# ───────── fundamentals ─────────
def grains_fund(key, wkey, sym):
    w = (J("grains/derived/wasde.json") or {}).get("commodities", {}).get(wkey)
    sal = (J("grains/derived/sales.json") or {}).get(key if key != "kc" else "kc")
    exp = (J("grains/derived/exports.json") or {}).get(wkey)
    cond = (J("grains/derived/condition.json") or {}).get(wkey if key != "kc" else "wheat")
    bas = (J("grains/derived/basis.json") or {}).get(key if key in ("corn", "soybeans", "wheat", "kc") else "")
    fl = (J("grains/derived/flash.json") or {}).get(key)
    parts, votes = [], []
    if w:
        us = w["us"]
        my = sorted(us)[-1]
        it = us[my]["items"]
        g = lambda k: it.get(k, {})
        es, ex = g("end_stocks"), g("exports")
        tu = g("use").get("value") or (g("domestic").get("value") or 0) + (ex.get("value") or 0)
        su = 100 * es["value"] / tu if es.get("value") and tu else None
        parts.append(f"USDA's {us[my]['report']} WASDE puts {my} ending stocks at {f(es.get('value'), 0)} {('mil bu' if wkey in ('corn', 'soybeans', 'wheat') else '')}"
                     f" ({sg(es.get('change'), 0)} on the month){f', stocks/use {su:.1f}%' if su else ''}; season-average farm price {f(g('price').get('value'), 2)}.")
        if es.get("change") and es.get("value"):
            votes.append(-np.sign(es["change"]) * 0.5 * min(1.0, abs(es["change"]) / es["value"] * 10))  # a 10% revision = full vote
        su_fit = (w.get("stocks_use_vs_price") or {}).get("fit") or {}
        if su_fit.get("r2", 0) >= 0.4:
            parts.append(f"Stocks-to-use explains price well here (R² {su_fit['r2']:.2f}), so revisions to ending stocks are the main fundamental driver.")
    if cond and cond.get("model") and key != "kc":
        m = cond["model"]
        d = m["estimate"] - m["usda"] if m.get("usda") else None
        parts.append(f"The crop-condition yield model gives {f(m['estimate'])} bu/ac vs USDA {f(m['usda'])}"
                     + (f" ({sg(d)}); it beat trend in back-tests but not USDA's own same-date forecast, so treat small gaps as noise." if d is not None else "."))
        if d is not None and abs(d) >= 1.0 and key in ("corn", "soybeans"):
            votes.append(-np.sign(d) * 0.3)
    if sal:
        gap = (sal["implied"] - sal["usda"]) / sal["usda"] * 100 if sal.get("implied") and sal.get("usda") else None
        parts.append(f"Export commitments are {f(sal['pct_of_usda'])}% of USDA's {f(sal['usda'], 0)} vs {f(sal['avg_pct'])}% usually by week {sal['week']}, "
                     f"implying {f(sal['implied'], 0)} ({sg(gap, 0, '%')} vs USDA). This gap has called the direction of USDA's next export revision "
                     f"{100 * (sal.get('test') or {}).get('revision_hit', 0):.0f}% of the time.")
        if gap is not None and abs(gap) >= 3:
            votes.append(np.sign(gap) * (0.5 if sal["week"] >= 10 else 0.25))  # early-season pace is noisy
    if fl and fl.get("since", {}).get("n"):
        parts.append(f"Daily flash sales since the last weekly report add {f(fl['since']['kt'], 0)} kt.")
    if bas:
        firm = [x for x in bas if x.get("usual") is not None]
        if firm:
            d = np.mean([x["basis"] - x["usual"] for x in firm])
            parts.append("Cash basis is " + ("weak" if d < -3 else "firm" if d > 3 else "near normal") + " against futures (" +
                         "; ".join(f"{x['label']} {sg(x['basis'], 0)} vs usual {sg(x['usual'], 0)}" for x in firm[:3]) + " ¢/bu).")
            if abs(d) > 3:
                votes.append(np.sign(d) * 0.3)
    score = float(np.clip(np.sum(votes), -1, 1)) if votes else 0.0
    return score, " ".join(parts) or "Fundamental data not available.", {"sal": sal, "w": w}


def hogs_fund():
    h, sd, cv = J("livestock/derived/hogs.json"), J("livestock/derived/hogs_sd.json"), J("livestock/derived/hogs_convergence.json")
    parts, votes = [], []
    if h:
        c = h["curve"]
        parts.append(f"The CME Lean Hog Index is ${c['index']:.2f} ({c['index_date']}); the curve trades "
                     + ", ".join(f"{m.title()} {sg(v, 2)}" for m, v in zip(c["month"][:3], c["vs_index"][:3])) + " vs the index.")
        mg = [x for x in h["cutout"]["margin"] if x is not None]
        if mg:
            parts.append(f"Packer margin proxy (cutout minus index) is {sg(mg[-1], 2)} $/cwt.")
    if sd and sd.get("current"):
        y = sd["current"]["yoy_pct"]
        parts.append(f"The {sd['current']['report']} Hogs and Pigs report shows market hogs " + ", ".join(f"{k.lower()} {sg(v, 1, '%')}" for k, v in y.items()) + " y/y.")
        votes.append(-0.3 * np.sign(np.mean(list(y.values()))))
    if cv and cv.get("current"):
        x = cv["current"][1] if len(cv["current"]) > 1 else cv["current"][0]
        parts.append(f"The supply/cash model points {x['contract']} to {x['model']:.1f} vs futures {x['fut_post']:.1f} after the report, "
                     "but in tests futures beat the model at every horizon, so it is context, not a signal.")
    return float(np.clip(np.sum(votes), -1, 1)) if votes else 0.0, " ".join(parts), {"h": h}


def cattle_fund(sym):
    c, cs = J("livestock/derived/cattle.json"), J("livestock/derived/cattle_sd.json")
    parts, votes = [], []
    if c:
        cur = c["curve_le"] if sym == "LE" else c["curve_gf"]
        if cur:
            parts.append(f"{cur['cash_label']}: ${cur['cash']:.2f}; futures " + ", ".join(f"{m.title()} {sg(v, 2)}" for m, v in zip(cur["month"][:3], cur["vs_cash"][:3])) + " vs cash.")
        cof = c["cof"]
        yo = lambda k: list(cof[k]["yoy"].items())[-1]
        parts.append(f"Cattle on feed {sg(yo('on_feed')[1], 1, '%')} y/y, placements {sg(yo('placements')[1], 1, '%')}, marketings {sg(yo('marketings')[1], 1, '%')} ({yo('on_feed')[0]}).")
        votes.append(-0.3 * np.sign(yo("on_feed")[1] or 0))
        bb = [x for x in c["boxed_beef"]["choice"] if x is not None]
        if bb:
            parts.append(f"Choice cutout ${bb[-1]:.2f}.")
    b = (J("derived/convergence_bias.json") or {}).get(sym)
    if sym == "LE" and b:
        parts.append(f"Structural edge: live cattle futures have finished {b['h20']['mean_pct']:+.1f}% above their 20-day-out price on average since 2010 "
                     f"({100 * b['h20']['up_share']:.0f}% of contracts), the one convergence premium on the desk that held in both halves of the sample.")
        votes.append(0.3)
    return float(np.clip(np.sum(votes), -1, 1)) if votes else 0.0, " ".join(parts), {"bias": b}


def dairy_fund(sym):
    spot, sd = J("dairy/derived/dairy_spot.json"), J("dairy/derived/sd.json")
    parts, votes = [], []
    tech = J(f"technicals/{sym}.json")
    fut = None
    if tech:
        s = next((x for x in tech["series"] if x["ticker"] == tech["default"]), None)
        fut = s["analysis"]["last"] if s else None
    if spot and spot.get("current"):
        cu = spot["current"]
        now = cu["class3"] if sym == "DC" else cu["class4"]
        parts.append(f"CME spot (cheese {cu['spot'].get('cheese', 0):.3f}, butter {cu['spot'].get('butter', 0):.3f}, NDM {cu['spot'].get('ndm', 0):.3f}, whey {cu['spot'].get('whey', 0):.3f} $/lb) "
                     f"plus {cu['weeks_done']} survey weeks put {cu['month']} {'Class III' if sym == 'DC' else 'Class IV'} near ${now:.2f}"
                     + (f" vs futures {fut:.2f}" if fut else "") + ". Futures beat this nowcast in tests (they trade the same spot auctions), so a gap mostly says the spot move is not yet in the survey.")
        if fut:
            votes.append(0.3 * np.sign(now - fut))
    if sd and sd.get("nass_milk"):
        m = sd["nass_milk"]
        parts.append(f"US milk output {sg(m['yoy_pct'][-1], 1, '%')} y/y in {m['month'][-1]} with the herd {sg(m['cows_yoy_k'][-1], 0)}k cows y/y.")
        votes.append(-0.3 * np.sign(m["yoy_pct"][-1]))
    return float(np.clip(np.sum(votes), -1, 1)) if votes else 0.0, " ".join(parts), {}


# ───────── trade ideas ─────────
def ideas(key, sym, group, T, F, fund_score, fund_ctx):
    out = []
    a = T.get("a")
    if not a:
        return out
    dp, u = T["t"]["dp"], T["t"]["unit"]
    px, atr = a["last"], a["atr"]
    contract = T["s"]["label"]
    cta, mm, p3 = F.get("cta") or {}, F.get("mm") or {}, F.get("p3")
    cb = J("derived/cot_backtest.json") or {}

    def idea(method, direction, why, evidence, stop_atr=2.0, tgt_atr=3.0, horizon="2–6 weeks", instrument=None, entry=None, stop=None, target=None):
        e = entry if entry is not None else px
        s = stop if stop is not None else (e - direction * stop_atr * atr)
        t = target if target is not None else (e + direction * tgt_atr * atr)
        out.append({"method": method, "side": "Long" if direction > 0 else "Short", "instrument": instrument or f"{contract} ({T['s']['ticker']})",
                    "entry": round(e, dp + 1), "stop": round(s, dp + 1), "target": round(t, dp + 1), "rr": round(abs(t - e) / abs(e - s), 1) if e != s else None,
                    "horizon": horizon, "why": why, "evidence": evidence})

    # 1. trend following (technical + CTA score agree)
    if cta and abs(cta.get("score", 0)) >= 0.5:
        d = 1 if cta["score"] > 0 else -1
        agree = (T["rd"] in ("Buy", "Strong buy")) if d > 0 else (T["rd"] in ("Sell", "Strong sell"))
        if agree:
            lvl = (a.get("resistance") or [None])[0] if d < 0 else (a.get("support") or [None])[0]
            stop = max(px + 2 * atr, lvl) if (d < 0 and lvl) else (min(px - 2 * atr, lvl) if lvl else None)
            idea("Trend (CTA-style)", d, f"Trend score {cta['score']:+.2f} and a {T['rd'].lower()} daily rating point the same way; stop beyond the nearest swing level or 2 ATR.",
                 "Rules-based; trend-following is the main driver of fund flow here (score explains R² " + f"{cta.get('r2', 0):.2f}" + " of managed-money net), but it has not been back-tested as a stand-alone trade on this desk.",
                 stop=stop)
    # 2. positioning
    if p3 is not None and cta:
        if p3 >= 90 and cta.get("score", 0) <= 0:
            idea("Positioning (crowded long, trend down)", -1, f"Funds at the {ordn(p3)} percentile of 3 years while the trend score is {cta['score']:+.2f}: longs are exposed to liquidation; {F['uw'].get('long', {}).get('pct_underwater', 0):.0f}% already under water.",
                 "Not back-tested for grains; in dairy and livestock tests fund extremes tended to persist rather than reverse, so size small and require the trend to stay down.")
        elif p3 <= 10 and cta.get("score", 0) >= 0:
            idea("Positioning (crowded short, trend up)", 1, f"Funds at the {ordn(p3)} percentile while the trend score turns {cta['score']:+.2f}: short-covering risk; {F['uw'].get('short', {}).get('pct_underwater', 0):.0f}% of shorts under water.",
                 "Not back-tested as a reversal signal; short covering in a rising trend is the documented mechanism, not a statistical edge.")
        elif sym in cb:
            w4 = cb[sym]["w4"]
            ext = "extreme_long" if p3 >= 90 else "extreme_short" if p3 <= 10 else None
            if ext and w4.get(ext, {}).get("t_approx") and abs(w4[ext]["t_approx"]) >= 2:
                d = 1 if w4[ext]["mean_pct"] > 0 else -1
                idea("Positioning persistence (tested)", d, f"Funds at the {ordn(p3)} percentile; historically {sym} moved {w4[ext]['mean_pct']:+.2f}% in the next 4 weeks after similar readings.",
                     f"Back-tested 2006–2026: n={w4[ext]['n']}, up {100 * w4[ext]['up_share']:.0f}% of the time, t≈{w4[ext]['t_approx']:.1f} (overlapping weeks overstate t).", horizon="4 weeks")
    # 3. fundamental / convergence
    if sym == "LE":
        b = fund_ctx.get("bias")
        if b:
            idea("Convergence premium (tested)", 1, "Live cattle futures have tended to finish above their 20–60-day-out price: buy the second-month contract and hold into its final 20 days.",
                 f"Since 2010: +{b['h20']['mean_pct']:.1f}% on average from 20 days out, {100 * b['h20']['up_share']:.0f}% of contracts higher, clustered t 2.3–3.2, held in 2010–17 and 2018–26. Risk: coincides with a cattle-cycle bull market.",
                 horizon="into expiry", stop_atr=3, tgt_atr=2)
    if group == "grains" and fund_ctx.get("sal"):
        s = fund_ctx["sal"]
        gap = (s["implied"] - s["usda"]) / s["usda"] * 100 if s.get("implied") and s.get("usda") else 0
        if abs(gap) >= 5 and abs(fund_score) >= 0.25 and np.sign(gap) == np.sign(fund_score):
            d = int(np.sign(gap))
            idea("Fundamental (export pace → USDA revision)", d, f"Commitments imply {gap:+.0f}% vs USDA's export forecast and the fundamental score is {word(fund_score)}: positions for USDA {'raising' if d > 0 else 'cutting'} exports at the next WASDE.",
                 f"The sales gap has called the direction of USDA's next export revision {100 * (s.get('test') or {}).get('revision_hit', 0):.0f}% of the time; it has NOT reliably predicted price, so this is a fundamental lean, not a tested price edge.",
                 horizon="to next WASDE")
    if sym in ("DC", "GDK"):
        sp = J("dairy/derived/dairy_spot.json") or {}
        cu = sp.get("current")
        if cu:
            now = cu["class3"] if sym == "DC" else cu["class4"]
            gap = now - px
            if abs(gap) >= 0.5:
                idea("Spot vs survey (front month)", int(np.sign(gap)), f"CME spot implies {cu['month']} near ${now:.2f} vs {contract} {px:.2f}: the survey (NDPSR) follows spot with a lag.",
                     "Weak: in 2021–26 tests the spot-based nowcast did not beat futures; act only on large gaps with 2+ survey weeks left.", horizon="to the class-price announcement", stop_atr=1.5, tgt_atr=2)
    # 4. seasonal / relative value
    seas = T.get("seas")
    if seas and seas.get("pct_same_time") is not None and (seas["pct_same_time"] >= 90 or seas["pct_same_time"] <= 10):
        d = -1 if seas["pct_same_time"] >= 90 else 1
        med = seas.get("median_same_time")
        idea("Seasonal / percentile", d, f"{seas['label']} is at the {ordn(seas['pct_same_time'])} percentile for this point of the season (median {f(med, dp)}).",
             "Untested as a trade: extremes can persist through regime changes (e.g. the cattle cycle). Use as context or for option structures.", horizon="season")
    for x in T.get("spreads") or []:
        p = x.get("pct_same_time")
        if p is not None and (p >= 90 or p <= 10):
            d = -1 if p >= 90 else 1
            med = x.get("median_same_time")
            out.append({"method": "Spread mean reversion", "side": ("Bear spread" if d < 0 else "Bull spread"), "instrument": x["label"], "entry": round(x["now"], dp + 1),
                        "stop": None, "target": round(med, dp + 1) if med is not None else None, "rr": None, "horizon": f"{x['wk_now']} weeks to expiry",
                        "why": f"{x['label']} at {x['now']:.{dp}f} is at the {ordn(p)} percentile for this point of the season; median {f(med, dp)}.",
                        "evidence": "Untested as a trade; spread extremes usually reflect real nearby tightness or surplus, so check the cash market first."})
            break
    return out


def catalysts(sym):
    cal = J("calendar/calendar.json")
    if not cal:
        return None
    today = pd.Timestamp.now().strftime("%Y-%m-%d")
    ev = [e for e in cal["events"] if e["date"] >= today and e["importance"] >= 3 and (sym in e["markets"] or "ALL" in e["markets"])]
    ev += [e for e in cal["events"] if e["date"] >= today and e["importance"] == 2 and sym in e["markets"] and e["cat"] in ("CME contract", "USDA")]
    ev = sorted(ev, key=lambda e: e["date"])[:3]
    return "; ".join(f"{e['event'].replace('NASS ', '')} {pd.Timestamp(e['date']).strftime('%b %-d')}" for e in ev) if ev else None


def weather_note(sym):
    wx = J("weather/weather.json")
    if not wx:
        return None
    rs = [r for r in wx["regions"] if sym in r["markets"] and r["sensitivity"] >= 1 and (r["risk"] >= 1 or r["next16_flag"] in ("dry", "wet"))]
    if not rs:
        return None
    rs = sorted(rs, key=lambda r: -r["risk"])[:3]
    def one(r):
        st = ", ".join(f"{x['crop']} {x['stage']}" for x in r["stages"])
        return f"{r['region']} ({st}): next 16 days {r['next16_mm']} mm vs {r['next16_normal']} normal ({r['next16_flag']}), last 30 days {r['past30_flag']}"
    return "Weather watch: " + "; ".join(one(r) for r in rs) + "."


def outlook(name, fs, ts, fl, ideas_, T=None, F=None, sym=None):
    w = {"f": 0.4, "t": 0.3, "c": 0.3}
    comps = [(fs, w["f"]), (ts, w["t"]), (fl, w["c"])]
    tot = sum(v * wt for v, wt in comps if v is not None) / max(sum(wt for v, wt in comps if v is not None), 1e-9)
    agree = sum(1 for v, _ in comps if v is not None and np.sign(v) == np.sign(tot) and abs(v) >= 0.1)
    conv = "high" if abs(tot) >= 0.45 and agree == 3 else "medium" if abs(tot) >= 0.25 and agree >= 2 else "low"
    txt = (f"Overall {word(tot)} with {conv} conviction: fundamentals {word(fs)}, technicals {word(ts)}, flows {word(fl)}. ")
    if agree == 3:
        txt += "All three lenses point the same way. "
    elif agree <= 1:
        txt += "The lenses disagree, which argues for smaller size and waiting for price to confirm. "
    a, nx = (T or {}).get("a") or {}, ((F or {}).get("cta") or {}).get("next") or {}
    dp = ((T or {}).get("t") or {}).get("dp", 2)
    watch = []
    if nx.get("up"):
        watch.append(f"a close above {nx['up']['lvl']:.{dp}f} ({nx['up']['name']}) would bring trend-follower buying")
    if nx.get("dn"):
        watch.append(f"below {nx['dn']['lvl']:.{dp}f} ({nx['dn']['name']}) adds selling")
    if a.get("support") and a.get("resistance"):
        watch.append(f"the {a['support'][0]:.{dp}f}–{a['resistance'][0]:.{dp}f} band is the immediate range")
    if watch:
        txt += "Levels to watch: " + "; ".join(watch) + ". "
    ct = catalysts(sym) if sym else None
    if ct:
        txt += f"Next catalysts: {ct}. "
    if ideas_:
        txt += f"{len(ideas_)} idea{'s' if len(ideas_) > 1 else ''} below, each labelled with how well its method has tested."
    return tot, conv, txt


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) or math.isinf(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    res = []
    for key, sym, group, name, wkey in MARKETS:
        try:
            ts, ttxt, T = technical(sym)
            fl, ftxt, F = flows(sym, group)
            if group == "grains":
                fs, fund_txt, ctx = grains_fund(key, wkey, sym)
            elif sym == "HE":
                fs, fund_txt, ctx = hogs_fund()
            elif sym in ("LE", "GF"):
                fs, fund_txt, ctx = cattle_fund(sym)
            else:
                fs, fund_txt, ctx = dairy_fund(sym)
            ids = ideas(key, sym, group, T, F, fs, ctx)
            wn = weather_note(sym)
            if wn:
                fund_txt = fund_txt + " " + wn
            tot, conv, otxt = outlook(name, fs, ts, fl, ids, T, F, sym)
            a = T.get("a") or {}
            mm = F.get("mm") or {}
            res.append({"key": key, "sym": sym, "group": group, "name": name, "score": tot, "view": word(tot), "conviction": conv,
                        "scores": {"fundamental": fs, "technical": ts, "flows": fl},
                        "price": a.get("last"), "unit": (T.get("t") or {}).get("unit"), "dp": (T.get("t") or {}).get("dp"), "contract": (T.get("s") or {}).get("label"),
                        "chg_1w": (a.get("returns") or {}).get("1w"), "trend": a.get("trend"), "rating": T.get("rd"),
                        "mm_pct3": F.get("p3"), "mm_pct10": (mm.get("pct") or {}).get("y10"), "mm_pct_all": (mm.get("pct") or {}).get("all"), "mm_net": mm.get("N"), "cta_score": (F.get("cta") or {}).get("score"),
                        "paras": {"fundamental": fund_txt, "technical": ttxt, "flows": ftxt, "outlook": otxt}, "ideas": ids})
            print(sym, word(tot), conv, {k: round(v, 2) if v is not None else None for k, v in {"f": fs, "t": ts, "c": fl}.items()}, len(ids), "ideas")
        except Exception:
            import traceback; traceback.print_exc()
    gen = pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")
    (OUT / "summary.json").write_text(json.dumps(clean({"generated": gen, "markets": res}), separators=(",", ":")))
