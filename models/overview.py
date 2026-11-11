"""Overview tab: one tile per commodity with an overall colour (bearish red → neutral yellow → bullish green) and short
reads of fundamentals, fair value, recent events, technicals and key levels, implied/realized vol, seasonality and COT.

Built only from what the desk's other models already wrote (summary, technicals, COT desk, options/vol, seasonal,
WASDE fits, cotton price outlook, energy S&D, palm, sugar/coffee data, news), plus data/overview/notes.json, which the
daily research-reading task writes (own-words recent events and a fundamental read for markets without a model).
Any part that is missing is shown as missing; a failure in one market does not stop the others.

Usage: python models/overview.py            (desk detected from the repo: softs desk if data/sugar exists)
Writes data/overview/overview.json.
"""
import csv, json, math, re, sys, traceback
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from summary import technical, flows  # same rule-based reads the Summary tab uses
except Exception:  # keep the overview alive even if summary.py cannot be imported
    technical = flows = None

SOFTS = (D / "sugar").exists() and (ROOT / "sugar.html").exists()
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

if SOFTS:
    GROUPS = [("Softs", [("cotton", "CT", "Cotton"), ("sugar", "SB", "Sugar No. 11"), ("coffee", "KC", "Coffee C"), ("cocoa", "CC", "Cocoa")])]
else:
    GROUPS = [("Grains & oilseeds", [("corn", "ZC", "Corn"), ("soybeans", "ZS", "Soybeans"), ("meal", "ZM", "Soybean meal"), ("oil", "ZL", "Soybean oil"),
                                     ("wheat", "ZW", "Chicago SRW wheat"), ("kc", "KE", "KC HRW wheat")]),
              ("Cotton", [("cotton", "CT", "Cotton")]),
              ("Livestock", [("hogs", "HE", "Lean hogs"), ("cattle", "LE", "Live cattle"), ("feeders", "GF", "Feeder cattle")]),
              ("Dairy", [("class3", "DC", "Class III milk"), ("class4", "GDK", "Class IV milk")]),
              ("Vegetable oils", [("palm", "FCPO", "Palm oil (Bursa)")]),
              ("Energy", [("natgas", "NG", "Natural gas"), ("crude", "CL", "WTI crude"), ("ulsd", "HO", "ULSD (heating oil)"), ("rbob", "RB", "RBOB gasoline")])]
NEWS_TAG = {"corn": "corn", "soybeans": "soybeans", "meal": "meal", "oil": "oil", "wheat": "wheat", "kc": "wheat", "cotton": "cotton", "hogs": "hogs",
            "cattle": "cattle", "feeders": "cattle", "class3": "dairy", "class4": "dairy", "palm": "oil", "natgas": "natgas", "crude": "crude",
            "ulsd": "products", "rbob": "products", "sugar": "sugar", "coffee": "coffee", "cocoa": "cocoa"}
NEWS_RX = {"palm": r"palm", "cocoa": r"cocoa|cacao", "ulsd": r"diesel|heating oil|distillate", "rbob": r"gasoline|RBOB", "kc": r"wheat"}
W = {"fundamental": 0.4, "technical": 0.3, "cot": 0.2, "seasonal": 0.1}


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def num(v, d=2):
    return "–" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:,.{d}f}"


def sgn(v, d=1, suf=""):
    return "–" if v is None else f"{'+' if v > 0 else ''}{v:,.{d}f}{suf}"


def ordn(v):
    n = int(round(v))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def clip(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def sentences(t, n=2):
    s = re.split(r"(?<=[.!?])\s+(?=[A-Z])", (t or "").strip())
    return " ".join(s[:n])


def word(s):
    if s is None:
        return "no read"
    return ("strongly bullish" if s >= 0.45 else "bullish" if s >= 0.2 else "mildly bullish" if s >= 0.07 else
            "strongly bearish" if s <= -0.45 else "bearish" if s <= -0.2 else "mildly bearish" if s <= -0.07 else "neutral")


def shade(s):
    if s is None:
        return "na"
    return ("bull3" if s >= 0.45 else "bull2" if s >= 0.2 else "bull1" if s >= 0.07 else
            "bear3" if s <= -0.45 else "bear2" if s <= -0.2 else "bear1" if s <= -0.07 else "neutral")


SUMMARY = {m["key"]: m for m in (J("summary/summary.json") or {}).get("markets", [])}
NOTES = (J("overview/notes.json") or {}).get("markets", {})
NEWS = (J("news/news.json") or {}).get("items", [])


# ───────── technicals + key levels ─────────
def tech(sym):
    if not technical:
        return None
    try:
        sc, _txt, ctx = technical(sym)
    except Exception:
        return None
    if not ctx:
        return None
    a, t, s = ctx["a"], ctx["t"], ctx["s"]
    dp, u = t.get("dp", 2), t.get("unit", "")
    r = a.get("returns") or {}
    sup, res = (a.get("support") or [])[:2], (a.get("resistance") or [])[:2]
    txt = (f"{a['trend'].capitalize()} trend; daily rating {ctx['rd'].lower()}, weekly {ctx['rw'].lower()}. RSI {a['rsi']:.0f}"
           f"{' (oversold)' if a['rsi'] < 30 else ' (overbought)' if a['rsi'] > 70 else ''}, ADX {a['adx']:.0f}"
           f"{' (trending)' if a['adx'] > 25 else ' (range-bound)' if a['adx'] < 20 else ''}.")
    return {"score": round(sc, 2), "text": txt, "contract": s["label"], "last": a["last"], "unit": u, "dp": dp,
            "chg_1w": r.get("1w"), "chg_1m": r.get("1m"),
            "levels": {"support": [round(x, dp) for x in sup], "resistance": [round(x, dp) for x in res],
                       "lo52": round(a["lo52"], dp) if a.get("lo52") else None, "hi52": round(a["hi52"], dp) if a.get("hi52") else None}}


# ───────── COT ─────────
def cot(sym, group):
    if not flows:
        return None
    try:
        sc, _txt, ctx = flows(sym, "grains" if group.startswith("Grains") else group.lower())
    except Exception:
        return None
    if not ctx:
        return None
    mm, cta, p3 = ctx["mm"], ctx.get("cta") or {}, ctx.get("p3")
    crowd = " — crowded long" if p3 is not None and p3 >= 90 else " — crowded short" if p3 is not None and p3 <= 10 else ""
    txt = (f"Managed money net {'long' if mm['N'] >= 0 else 'short'} {abs(mm['N']):,.0f} lots ({ordn(p3)} pct of 3 yrs{crowd}), "
           f"{sgn(mm['dN'], 0)} on the week.")
    if cta:
        txt += f" Trend-follower score {cta['score']:+.2f}."
        nx = cta.get("next") or {}
        trig = [f"buy above {v['lvl']:.2f}" if k == "up" else f"sell below {v['lvl']:.2f}" for k, v in (("up", nx.get("up")), ("down", nx.get("dn"))) if v]
        if trig and cta.get("r2", 0) >= 0.3:
            txt += " Fund triggers: " + ", ".join(trig) + "."
    return {"score": round(sc, 2), "text": txt, "date": ctx["c"].get("date"), "triggers": cta.get("next")}


# ───────── vol ─────────
def vol(sym):
    o = J(f"options/{sym}.json")
    if o and o.get("expiries"):
        e = o["expiries"][0]
        pct = None
        hist = [x[1] if isinstance(x, list) else x for x in (o.get("iv_hist") or []) if x is not None]
        hist = [h for h in hist if isinstance(h, (int, float))]
        if len(hist) >= 40 and e.get("atm") is not None:
            pct = 100 * sum(h <= e["atm"] for h in hist) / len(hist)
        skew = e.get("rr25")
        txt = (f"{e['label']} ATM implied {num(e.get('atm'), 1)}% vs 20-day realized {num(e.get('rv20'), 1)}%"
               + (f" ({ordn(pct)} pct of its history)" if pct is not None else "") + "; "
               + (f"25-delta risk reversal {sgn(skew, 2)} ({'calls' if skew > 0 else 'puts'} bid). " if skew is not None else "")
               + (f"Expected move to expiry ±{num(e.get('move_pct'), 1)}%. " if e.get("move_pct") else "")
               + f"Options data as of {o.get('date')}.")
        return {"kind": "implied", "atm": e.get("atm"), "rv20": e.get("rv20"), "pct": pct, "rr25": skew, "text": txt}
    en = (J("energy/summary.json") or {}).get("vol", {}).get(sym)
    if en:
        return {"kind": "implied", "atm": en.get("atm"), "rv20": en.get("rv20"), "rr25": en.get("rr25"),
                "text": f"{en.get('label')} ATM implied {num(en.get('atm'), 1)}% vs 20-day realized {num(en.get('rv20'), 1)}%; 25-delta risk reversal {sgn(en.get('rr25'), 2)}."}
    v = (J("vol/vol.json") or {}).get("markets", {}).get(sym)
    if v:
        cone = next((c for c in v.get("cone", []) if c["n"] == 20), None)
        return {"kind": "realized", "rv20": v.get("hv20_front"), "pct": v.get("hv20_pct1y"),
                "text": f"20-day realized vol {num(v.get('hv20_front'), 1)}% ({ordn(v['hv20_pct1y'])} pct of 1 yr, {ordn(v['hv20_pct5y'])} of 5 yrs)"
                        + (f"; 5-yr median {num(cone['p50'], 1)}%" if cone else "") + ". Free implied vol is not available for ICE softs."}
    return None


# ───────── seasonality ─────────
def seasonal(sym):
    s = J(f"seasonal/{sym}.json")
    if not s:
        return None
    today = date.today()
    m0, m1 = MON[today.month - 1], MON[today.month % 12]
    fa = s.get("front_avg") or {}
    cur, nxt = fa.get(m0), fa.get(m1)
    if not cur:
        return None
    # remaining part of this month weighs less than next month
    frac = 1 - today.day / 31
    avg = (cur["avg"] * frac + (nxt or cur)["avg"]) / (1 + frac)
    hit = (cur["hit"] * frac + (nxt or cur)["hit"]) / (1 + frac)
    sc = clip((hit - 50) / 25) * min(1, abs(avg) / 2) if (hit - 50) * avg > 0 else 0.0
    txt = (f"Front month has averaged {sgn(cur['avg'], 1, '%')} in {m0} (up {cur['hit']}% of {cur['n']} yrs)"
           + (f" and {sgn(nxt['avg'], 1, '%')} in {m1} (up {nxt['hit']}%)" if nxt else "") + ".")
    upcoming = sorted([t for t in s.get("trades", []) if t.get("next_entry") and t["next_entry"] <= f"{today.year + (today.month >= 11)}-{(today.month + 1) % 12 + 1:02d}-31"],
                      key=lambda t: t["next_entry"])[:1]
    for t in upcoming:
        txt += f" Next seasonal rule: {t['what']} (hit {t['hit']}% of {t['n']} yrs, from {t['next_entry']})."
    return {"score": round(sc, 2), "text": txt}


# ───────── news / recent events ─────────
def events(key, n=3):
    tag = NEWS_TAG.get(key)
    rx = NEWS_RX.get(key)
    pri = {"ADMIS": 0, "Rabobank": 0, "Czapp": 0}
    its = [i for i in NEWS if (rx and re.search(rx, i["title"] + " " + (i.get("teaser") or ""), re.I)) or (not rx and tag in (i.get("tags") or []))]
    its.sort(key=lambda i: (i.get("time") or "")[:10], reverse=True)
    recent = [i for i in its if (i.get("time") or "") >= (datetime.now(timezone.utc).date().isoformat()[:8] + "01")] or its
    research = [i for i in recent if i["source"] in pri][:2]
    rest = [i for i in recent if i["source"] not in pri and i not in research]
    out = (research + rest)[:n]
    return [{"title": i["title"], "link": i["link"], "source": i["source"], "date": (i.get("time") or "")[:10]} for i in out]


# ───────── fundamentals and fair value ─────────
def grains_fair(key, wkey, T):
    w = (J("grains/derived/wasde.json") or {}).get("commodities", {}).get(wkey)
    if not w or not T:
        return None
    fit = (w.get("stocks_use_vs_price") or {}).get("fit") or {}
    us = w.get("us") or {}
    if not fit.get("r2") or fit["r2"] < 0.4 or not us:
        return None
    my = sorted(us)[-1]
    it = us[my]["items"]
    es, ex = it.get("end_stocks", {}).get("value"), it.get("exports", {}).get("value")
    tu = it.get("use", {}).get("value") or ((it.get("domestic", {}).get("value") or 0) + (ex or 0))
    safp = it.get("price", {}).get("value")
    if not es or not tu or not safp:
        return None
    su = 100 * es / tu
    model = math.exp(fit["intercept"] + fit["elasticity"] * math.log(su))
    fut = T["last"] / (100 if T["unit"].startswith("¢") else 1)
    fair_fut = fut * model / safp
    gap = 100 * (fair_fut / fut - 1)
    fv = fair_fut * (100 if T["unit"].startswith("¢") else 1)
    return {"value": round(fv, T["dp"]), "unit": T["unit"], "gap_pct": round(gap, 1),
            "text": f"USDA stocks/use {su:.1f}% maps to a season-average farm price of ${model:.2f} on the {len(w['stocks_use_vs_price']['my'])}-season fit "
                    f"(R² {fit['r2']:.2f}) vs USDA's ${safp:.2f}; scaled to futures ≈ {fv:,.{T['dp']}f} ({sgn(gap, 0, '%')} vs {T['last']:,.{T['dp']}f}). Rough guide: farm-price fit, not a futures model.",
            "score": clip(gap / 15)}


def cotton_fair(T):
    o = J("derived/ct_price_outlook.json")
    if not o:
        return None
    b = (o.get("scenarios") or {}).get("base")
    may = (o.get("prices") or {}).get("K")
    if not b or not may:
        return None
    gap = 100 * (b["may"] / may - 1)
    return {"value": b["may"], "unit": "¢/lb", "gap_pct": round(gap, 1),
            "text": f"Desk base-case fair May {b['may']:.1f} (range {b['may_lo']:.1f}–{b['may_hi']:.1f}) at stocks/use {b['su']:.0f}% vs USDA {o.get('usda_su')}%; May trades {may:.2f} ({sgn(gap, 0, '%')}).",
            "score": clip(gap / 15)}


def energy_fund(key):
    E = J("energy/summary.json") or {}
    inv = E.get("inventories") or {}
    if key == "natgas":
        f = ((J("energy/sd.json") or {}).get("markets") or {}).get("NG", {}).get("fair") or {}
        st = inv.get("storL48") or {}
        fair = None
        px = ((E.get("prices") or {}).get("NG") or {}).get("last") or f.get("actual")
        if f.get("fair") and px:
            g = f["fair"] / px - 1
            fair = {"value": f["fair"], "unit": "$/MMBtu", "gap_pct": round(100 * g, 1),
                    "text": f"Storage-vs-5-yr fit (R² {f.get('r2')}, storage week {f.get('date')}) puts Henry Hub front-month fair at ${f['fair']:.2f} vs ${px:.2f} now "
                            f"({sgn(100 * g, 0, '%')}); in walk-forward tests {f.get('walk_forward', {}).get('reads', 'the gap is a weak guide')} "
                            f"({f.get('walk_forward', {}).get('hit', '–')}% hit over {f.get('walk_forward', {}).get('horizon_weeks', 4)} weeks).",
                    "score": clip(g / 0.25)}
        txt = (f"Lower-48 storage {num(st.get('value'), 0)} Bcf ({sgn(st.get('vs_avg5_pct'), 1, '%')} vs 5-yr avg, {sgn(st.get('vs_yago'), 0)} vs a year ago), "
               f"last injection {sgn(st.get('chg'), 0)} vs 5-yr {sgn(st.get('chg_avg5'), 0)}.")
        sc = clip(-(st.get("vs_avg5_pct") or 0) / 8) if st else None
        return sc, txt, fair
    m = {"crude": ("crude", "Crude stocks ex-SPR"), "ulsd": ("dist", "Distillate stocks"), "rbob": ("gaso", "Gasoline stocks")}[key]
    x = inv.get(m[0]) or {}
    if not x:
        return None, None, None
    txt = (f"{m[1]} {num(x.get('value'), 1)} mb ({sgn(x.get('vs_avg5_pct'), 1, '%')} vs 5-yr avg, {sgn(x.get('chg'), 1)} on the week vs 5-yr {sgn(x.get('chg_avg5'), 1)}).")
    if key == "crude":
        cu = inv.get("cushing") or {}
        txt += f" Cushing {num(cu.get('value'), 1)} mb ({sgn(cu.get('vs_avg5_pct'), 0, '%')} vs 5-yr). Refinery runs {num((E.get('refinery_util') or {}).get('value'), 1)}%."
    if key in ("ulsd", "rbob"):
        cr = (E.get("cracks") or {}).get("ho" if key == "ulsd" else "rb")
        if cr is not None:
            txt += f" Crack vs WTI ${cr:.1f}/bbl."
    sym = {"crude": "CL", "ulsd": "HO", "rbob": "RB"}[key]
    f = ((J("energy/sd.json") or {}).get("markets") or {}).get(sym, {}).get("fair") or {}
    fair = None
    if f.get("fair") is not None:
        fair = {"value": None, "unit": None, "gap_pct": None, "score": None,
                "text": f"No outright fair-value model. The inventory fit for the {f.get('label', 'spread')} gives {f['fair']:.2f} vs {f['actual']:.2f} "
                        f"({f.get('date')}; R² {f.get('r2')}{', weak — context only' if (f.get('r2') or 0) < 0.3 else ''})."}
    return clip(-(x.get("vs_avg5_pct") or 0) / 10), txt, fair


def palm_fund():
    p = J("palm/palm.json")
    if not p:
        return None, None, None
    fs = p.get("factors") or []
    sc = clip(sum(f.get("s", 0) for f in fs) / max(1, len(fs)) * 1.5) if fs else None
    txt = " ".join(re.sub(r"\*\*", "", b["t"]).split(". ")[0] + "." for b in (p.get("brief") or [])[:2])
    fit = None
    t = json.dumps(p)
    m = re.search(r'"fair_usd": ([\d.]+), "fair_myr": ([\d.]+), "spot_usd": ([\d.]+), "gap_pct": (-?[\d.]+)', t)
    if m:
        fu, fm, su, gp = map(float, m.groups())
        fit = {"value": fm, "unit": "MYR/t", "gap_pct": round(-gp, 1),
               "text": f"Stocks + soybean-oil fit puts fair value at ${fu:,.0f}/t (≈ MYR {fm:,.0f}) vs spot ${su:,.0f} ({sgn(-gp, 1, '%')} to fair).", "score": clip(-gp / 15)}
    return sc, txt, fit


def sugar_fund():
    s = J("sugar/signals.json") or {}
    n = s.get("now") or {}
    z = J("sugar/czapp_digest.json") or {}
    bits, sc = [], 0.0
    if n.get("parity_premium") is not None:
        p = n["parity_premium"]
        bits.append(f"Raw sugar is {abs(p):.2f}¢/lb {'above' if p > 0 else 'below'} hydrous-ethanol parity in Brazil, so mills {'favour sugar in the mix (more supply)' if p > 0 else 'lean to ethanol (less sugar)'}.")
        sc += clip(-p / 4) * 0.6
    if n.get("brl_t") is not None:
        bits.append(f"Sugar in BRL at R${n['brl_t']:,.0f}/t ({ordn(n['brl_t_pctile_5y'])} pct of 5 yrs).")
    th = z.get("themes") or []
    if th:
        bits.append(th[0])
    return (clip(sc) if bits else None), " ".join(bits) or None, None


def coffee_fund():
    bits, sc = [], 0.0
    try:
        rows = list(csv.DictReader(open(D / "coffee/ice_certs.csv")))
        cert = {}
        for r in rows:
            if r["section"] == "certified":
                cert[r["date"]] = cert.get(r["date"], 0) + float(r["bags"] or 0)
        ds = sorted(cert)
        if len(ds) > 25:
            now, m1 = cert[ds[-1]], cert[ds[-22]]
            ch = 100 * (now / m1 - 1) if m1 else None
            bits.append(f"ICE certified arabica {now / 1000:,.0f}k bags ({sgn(ch, 0, '%')} over ~1 month)" + (", building" if ch and ch > 3 else ", drawing" if ch and ch < -3 else "") + ".")
            if ch is not None:
                sc += clip(-ch / 20) * 0.5
    except Exception:
        pass
    c = J("coffee/cecafe.json") or {}
    if c.get("mtd"):
        bits.append(f"Brazil export registrations {c['month']} month-to-date {c['mtd']['total'] / 1e6:.2f}m bags (Cecafé, to {c.get('asof')}; prior month {c.get('prev_month_total', {}).get('total', 0) / 1e6:.2f}m).")
    return (clip(sc) if bits else None), " ".join(bits) or None, None


def fundamental(key, sym, T):
    n = NOTES.get(key) or {}
    sm = SUMMARY.get(key)
    score, txt, fair = None, None, None
    if key in ("natgas", "crude", "ulsd", "rbob"):
        score, txt, fair = energy_fund(key)
    elif key == "palm":
        score, txt, fair = palm_fund()
    elif key == "sugar":
        score, txt, fair = sugar_fund()
    elif key == "coffee":
        score, txt, fair = coffee_fund()
    elif sm:
        score = (sm.get("scores") or {}).get("fundamental")
        txt = sentences(sm["paras"].get("fundamental"), 3)
    if key == "cotton":
        fair = cotton_fair(T)
        ob = ((J("derived/outlook_brief.json") or {}).get("markets") or {}).get("cotton")
        if ob:
            txt = " ".join(i["t"] for i in ob["items"] if i["h"] in ("Crop", "Exports", "Balance sheet"))
    elif key in ("corn", "soybeans", "meal", "oil", "wheat", "kc") and T:
        fair = grains_fair(key, {"kc": "wheat"}.get(key, key), T)
    # the daily research reading adds an own-words read; for markets without a model it is the fundamental read
    if n.get("fundamental"):
        txt = (txt + " " if txt else "") + "Research read: " + n["fundamental"]
        if score is None and n.get("fund_score") is not None:
            score = clip(float(n["fund_score"]))
        elif n.get("fund_score") is not None:
            score = clip(0.7 * score + 0.3 * float(n["fund_score"]))
    if fair and score is not None and fair.get("score") is not None:
        score = clip(0.7 * score + 0.3 * fair["score"])
    elif fair and score is None:
        score = fair.get("score")
    return {"score": None if score is None else round(score, 2), "text": txt or "No fundamental model for this market yet."}, fair


def build(key, sym, name, group):
    T = tech(sym)
    F, fair = fundamental(key, sym, T)
    C = cot(sym, group)
    S = seasonal(sym)
    V = vol(sym)
    parts = {"fundamental": F.get("score"), "technical": (T or {}).get("score"), "cot": (C or {}).get("score"), "seasonal": (S or {}).get("score")}
    have = {k: v for k, v in parts.items() if v is not None}
    total = sum(W[k] * v for k, v in have.items()) / sum(W[k] for k in have) if have else None
    agree = None
    if have:
        sg = [math.copysign(1, v) for v in have.values() if abs(v) >= 0.1]
        agree = bool(sg) and (all(x > 0 for x in sg) or all(x < 0 for x in sg))
    n = NOTES.get(key) or {}
    ev = [{"text": e} for e in (n.get("events") or [])][:3]
    return {"key": key, "sym": sym, "name": name, "group": group,
            "score": None if total is None else round(total, 2), "view": word(total), "shade": shade(total),
            "conviction": None if total is None else ("high" if abs(total) >= 0.4 and agree else "medium" if abs(total) >= 0.2 else "low"),
            "parts": parts, "price": T and {k: T[k] for k in ("contract", "last", "unit", "dp", "chg_1w", "chg_1m")},
            "fundamental": F, "fair": fair, "events": ev, "headlines": events(key), "notes_date": n.get("date"),
            "technical": T and {"text": T["text"], "score": T["score"]}, "levels": T and T["levels"],
            "vol": V, "seasonal": S, "cot": C}


def main():
    out = []
    for g, ms in GROUPS:
        for key, sym, name in ms:
            try:
                out.append(build(key, sym, name, g))
            except Exception:
                traceback.print_exc()
                out.append({"key": key, "sym": sym, "name": name, "group": g, "score": None, "view": "no read", "shade": "na", "error": True})
            o = out[-1]
            print(f"{sym:5} {o['view']:17} {o.get('score')} {o.get('parts')}")
    (D / "overview").mkdir(parents=True, exist_ok=True)
    (D / "overview" / "overview.json").write_text(json.dumps({
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "desk": "softs" if SOFTS else "us",
        "weights": W, "groups": [g for g, _ in GROUPS], "markets": out}, ensure_ascii=False, separators=(",", ":"), default=lambda x: None))


if __name__ == "__main__":
    main()
