#!/usr/bin/env python3
"""Knowledge cards for the desk chatbot (assets/chat.js): compact text built from the desk's own data files.

The page sends the question plus the most relevant cards (alias match, current tab) to Groq, so every card is
plain text with its data date, kept short to fit the free tier's per-minute token budget.
Writes data/ai/context.json: {generated, cards: [{id, title, kind, aliases, text}]}.
"""
import json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
ALIASES = {
    "ZC": ["corn", "zc", "maize"], "ZS": ["soybeans", "soybean", "soy", "beans", "zs"], "ZM": ["meal", "soymeal", "soybean meal", "zm"],
    "ZL": ["soy oil", "soybean oil", "bean oil", "zl", "soyoil"], "ZW": ["wheat", "chicago wheat", "srw", "zw"], "KE": ["kc wheat", "hrw", "kansas", "ke"],
    "CT": ["cotton", "ct"], "LE": ["live cattle", "cattle", "le", "beef"], "GF": ["feeder cattle", "feeders", "gf", "cattle"],
    "HE": ["lean hogs", "hogs", "hog", "pork", "he"], "DC": ["class iii", "class 3", "milk", "dc", "dairy"], "GDK": ["class iv", "class 4", "gdk", "milk"],
    "CSC": ["cheese", "csc"], "CB": ["butter", "cb"], "GNF": ["nonfat", "nfdm", "ndm", "milk powder", "gnf", "skim"], "DY": ["whey", "dry whey", "dy"],
    "NG": ["natural gas", "nat gas", "natgas", "gas", "ng", "henry hub"], "CL": ["crude", "wti", "oil", "cl"], "HO": ["heating oil", "diesel", "ulsd", "ho", "distillate"],
    "RB": ["gasoline", "rbob", "rb", "gas prices"],
}
GEO = {"ZC": "corn", "ZS": "soybeans", "ZM": "meal", "ZL": "oil", "ZW": "wheat", "KE": "wheat", "CT": "cotton", "HE": "pork", "LE": "beef",
       "GF": "beef", "DC": "milk", "GDK": "milk", "CSC": "cheese", "CB": "butter", "GNF": "nfdm"}


def J(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def f(v, d=2):
    try:
        return f"{float(v):,.{d}f}"
    except Exception:
        return "-"


def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def more_cards(cards):
    """Cards for the rest of the site: history, macro and markets, US economy, energy fundamentals and geography,
    commodity geography and weather, dairy and livestock cash markets, calendar and news."""
    def add(id_, title, kind, aliases, lines, cap=4200):
        txt = "\n".join(x for x in lines if x)
        if txt.strip():
            cards.append({"id": id_, "title": title, "kind": kind, "aliases": aliases, "text": txt[:cap]})
    # price and positioning history per market (weekly, about 6 months) for "how has X moved" questions
    for fp in sorted((D / "technicals").glob("*.json")):
        t = J(fp)
        sym = t["sym"]
        cont = next((x for x in t["series"] if x["ticker"] == "cont"), None)
        L = [f"{t['name']} ({sym}) weekly history (Friday closes, continuous front, {t['unit']}):"]
        if cont and cont.get("bars"):
            wk = {}
            for b in cont["bars"][-140:]:
                d = datetime.strptime(b[0], "%Y-%m-%d")
                wk[d.strftime("%G-W%V")] = (b[0], b[4])
            L.append(", ".join(f"{d}: {f(c)}" for d, c in list(wk.values())[-26:]))
            hi = max(cont["bars"][-252:], key=lambda b: b[2]); lo = min(cont["bars"][-252:], key=lambda b: b[3])
            L.append(f"52-week high {f(hi[2])} on {hi[0]}, low {f(lo[3])} on {lo[0]}.")
        sea = t.get("seasonal") or []
        if sea:
            x = sea[0]
            L.append(f"Seasonal: {x.get('label')} at the {x.get('pct_same_time')}th percentile of past years at this point of the contract.")
        c = J(D / "cot_desk" / f"{sym}.json")
        if c and c.get("series", {}).get("date"):
            ser = c["series"]
            L.append("Managed money net (contracts), last 13 weeks: " + ", ".join(f"{d}: {int(n):,}" for d, n in list(zip(ser["date"], ser["mm_n"]))[-13:] if n is not None))
            if ser.get("pm_n"):
                L.append("Producer/merchant net, last 8 weeks: " + ", ".join(f"{d}: {int(n):,}" for d, n in list(zip(ser["date"], ser["pm_n"]))[-8:] if n is not None))
        add(f"hist_{sym}", f"{t['name']} history", "history", ALIASES.get(sym, [sym.lower()]) + ["history", "weekly", "last weeks", "since", "chart", "trend", "high", "low", "52-week"], L)
    # cross-market heat map (Yahoo, delayed)
    M = J(D / "markets/markets.json")
    if M:
        L = [f"Markets snapshot {M.get('generated')} (last price; % change 1 day / 1 week / 1 month / YTD / 1 year; yields: bp):"]
        for x in M["items"]:
            sc = (lambda v: "-" if v is None else (f"{v:+.0f}bp" if x.get("kind") == "yield" else f"{v:+.1f}%"))
            L.append(f"{x['group']} | {x['name']} {x.get('contract') or ''}: {f(x.get('last'))} {x.get('unit') or ''}; {sc(x.get('d1'))} / {sc(x.get('w1'))} / {sc(x.get('m1'))} / {sc(x.get('ytd'))} / {sc(x.get('y1'))}")
        tr = M.get("treasury") or {}
        if tr:
            L.append("US Treasury curve: " + clip(json.dumps(tr), 400))
        add("markets", "Markets & macro heat map (commodities, indices, currencies, yields)", "macro",
            ["s&p", "stocks", "equities", "dollar", "dxy", "currency", "currencies", "yield", "yields", "treasury", "bond", "vix", "gold", "copper", "brl", "real", "peso", "yuan", "heat map", "index", "indices"], L, 6000)
    MC = J(D / "macro/macro.json")
    if MC:
        L = [f"Macro read for ags ({MC.get('generated')}): {MC.get('view')} (score {MC.get('score')}). {clip(MC.get('summary'), 500)}"]
        L += [f"{x.get('title')}: {clip(x.get('text'), 500)}" for x in MC.get("sections", [])]
        if MC.get("caveat"):
            L.append("Caveat: " + clip(MC["caveat"], 300))
        add("macro", "Macro outlook and impact on ags", "macro", ["macro", "rates", "fed", "dollar", "risk", "china", "breadth", "outlook", "recession", "inflation"], L)
    U = J(D / "macro/us_econ.json")
    if U:
        L = [f"US economy snapshot ({U.get('generated')}). {clip(U.get('read'), 600)}"]
        for x in U.get("indicators", []):
            parts = [f"{x['name']} {x.get('period')}: {f(x.get('value'))}{'' if x.get('kind') == 'index' else ' ' + (x.get('unit') or '')}"]
            for k, lab in (("yoy", "y/y"), ("mom", "m/m"), ("chg", "chg"), ("ann3", "3m ann.")):
                if x.get(k) is not None:
                    parts.append(f"{lab} {x[k]:+.2f}")
            L.append("; ".join(parts) + f" ({x.get('source')})")
        if U.get("rates"):
            L.append("Rates: " + clip(json.dumps(U["rates"]), 600))
        add("us_econ", "US economy (inflation, jobs, GDP, rates)", "macro",
            ["cpi", "ppi", "inflation", "jobs", "payrolls", "unemployment", "gdp", "pce", "fed funds", "sofr", "economy", "wages", "breakeven", "real yield"], L, 5000)
    # energy fundamentals and geography
    ES = J(D / "energy/summary.json")
    if ES:
        L = [f"Energy fundamentals ({ES.get('generated')}): {clip(ES.get('read'), 900)}"]
        for k, v in (ES.get("inventories") or {}).items():
            L.append(f"{v['name']} {f(v['value'], 1)} {v['unit']} (week to {v['date']}), w/w {f(v['chg'], 1)}, vs 5-yr avg {f(v.get('vs_avg5'), 1)} ({f(v.get('vs_avg5_pct'), 1)}%), vs year ago {f(v.get('vs_yago'), 1)}")
        for k, v in (("refinery utilization %", ES.get("refinery_util")), ("US crude production mb/d", ES.get("crude_prod")), ("Henry Hub spot $/MMBtu", ES.get("henry_hub_spot"))):
            if v:
                L.append(f"{k}: {v['value']} ({v['date']})")
        if ES.get("cracks"):
            L.append("Cracks $/bbl: 3-2-1 {:.2f}, ULSD-crude {:.2f}, gasoline-crude {:.2f}".format(ES["cracks"]["321"], ES["cracks"]["ho"], ES["cracks"]["rb"]))
        add("energy_fund", "Energy fundamentals (EIA storage, stocks, refining, cracks)", "fundamental",
            ["storage", "inventories", "stocks", "eia", "refinery", "crack", "cushing", "distillate", "henry hub", "natural gas", "crude", "gasoline", "diesel", "energy"], L)
    for k, title, al in (("crude", "Crude oil production and trade", ["crude", "oil", "opec", "saudi", "russia", "permian", "texas", "exports", "producers"]),
                         ("natgas", "Natural gas production, LNG terminals and trade", ["natural gas", "lng", "terminal", "sabine", "plaquemines", "corpus christi", "freeport", "pipeline", "mexico", "exports", "producers"]),
                         ("products", "Oil products: consumption, refining capacity, diesel and gasoline trade", ["diesel", "gasoline", "refining", "refinery", "capacity", "products", "consumption"])):
        G = J(D / "energy/geo" / f"{k}.json")
        if not G:
            continue
        L = [f"{G.get('prod_title') or 'Production'} ({G.get('prod_source')}, {G.get('year')}, {G.get('unit')}): " + ", ".join(f"{p['country']} {f(p['value'], 0)} ({p['share']}%)" for p in (G.get("production") or [])[:10])]
        us = G.get("us_states") or G.get("refining")
        if us:
            L.append(f"US {us.get('what', 'refining capacity')} ({us.get('period')}, {us.get('unit')}): total {f(us.get('total'), 1)}; " + ", ".join(f"{x['state']} {f(x['value'], 1)} ({x['share']}%)" for x in us["states"][:8]))
        tm = G.get("terminals")
        if tm:
            L.append(f"US LNG exports by terminal, 12 months to {tm['through']} (Bcf): total {f(tm['total'], 0)}; " + "; ".join(f"{t['name']} {f(t['value'], 0)} ({t['share']}%, latest month {f(t['last'], 0)}; buyers {', '.join(t['top'][:3])})" for t in tm["rows"]))
        if G.get("pipeline"):
            L.append("Pipeline exports by crossing (12 months, Bcf): " + ", ".join(f"{p['name']} {f(p['value'], 0)} to {p['to']}" for p in G["pipeline"][:8]))
        for d in G.get("us_dest") or []:
            L.append(f"{d['title']} ({d['period']}, {d['unit']}): " + ", ".join(f"{x['country']} {f(x['value'], 0)} ({x['share']}%)" for x in d["top"]))
        if G.get("exporters"):
            L.append("Main exporters (UN Comtrade, Mt): " + ", ".join(f"{e['country']} {e['value']} ({e['year']})" for e in G["exporters"]))
        add(f"egeo_{k}", title, "geography", al, L)
    # commodity geography, crop calendar and weather
    WX = J(D / "geo/weather.json") or {}
    wxr = {r["id"]: r for r in WX.get("regions", [])}
    for f_ in sorted((D / "geo").glob("*.json")):
        if f_.stem in ("weather", "index"):
            continue
        G = J(f_)
        if not G or not G.get("production"):
            continue
        nm = G["name"]
        L = [f"{nm}: world production {G.get('my')} ({G.get('unit')}), world {f(G.get('world'), 1)}: " + ", ".join(f"{p['country']} {f(p['value'], 1)} ({p['share']}%)" for p in G["production"][:8])]
        if G.get("exporters"):
            L.append("Top exporters: " + ", ".join(f"{e['country']} {f(e['value'], 1)} ({e['share']}%)" for e in G["exporters"]))
        if G.get("importers"):
            L.append("Top importers: " + ", ".join(f"{e['country']} {f(e['value'], 1)} ({e['share']}%)" for e in G["importers"]))
        ud = G.get("us_dest") or {}
        for k in ("last_my", "current_my", "comtrade"):
            d = ud.get(k)
            if d:
                L.append(f"US export destinations ({d.get('measure')}, {k}): " + ", ".join(f"{x['country']} {f(x['value'], 0)} ({x.get('share')}%)" for x in d["top"][:10]))
        if G.get("us_states"):
            S_ = G["us_states"]
            L.append(f"US by state ({S_.get('year')}, {S_.get('what')}): " + ", ".join(f"{x['state']} {x['share']}%" for x in S_["states"][:8]))
        for c in G.get("calendar") or []:
            L.append(f"{c['country']} ({c.get('share')}%): stage now {c['now'][0] if c.get('now') else 'between seasons'}; weather read: {c.get('read')}")
        regs = [wxr[i] for i in G.get("weather_regions", []) if i in wxr]
        for r in regs[:10]:
            L.append(f"Weather {r['name']} ({r['country']}): rain 60d {f(r.get('r60'), 0)} mm ({r.get('r60_p')}th pct), season {f(r.get('rstd'), 0)} mm vs avg {f(r.get('rstd_n'), 0)}, soil moisture {r.get('sm100_p')}th pct, next 16d rain {f(r.get('f16_rain'), 0)} mm; {'; '.join(r.get('flags') or [])}")
        add(f"geo_{f_.stem}", f"{nm}: where it's grown, trade, crop calendar and weather", "geography",
            [f_.stem, nm.lower(), "weather", "rain", "drought", "crop calendar", "producers", "production", "exporters", "importers", "brazil", "argentina", "india", "china", "where", "harvest", "planting"], L, 5000)
    # dairy cash and class prices
    sp = (J(D / "dairy/derived/dairy_spot.json") or {}).get("current")
    cs = (J(D / "dairy/derived/class_summary.json") or {})
    if sp or cs:
        L = []
        if sp:
            L.append(f"CME spot dairy {sp.get('spot_date')}: " + ", ".join(f"{k} ${v}" for k, v in sp["spot"].items()) + f". Month {sp['month']} Class III implied by spot+NDPSR {sp.get('class3')}, Class IV {sp.get('class4')} ({sp.get('weeks_done')} weeks of NDPSR in, {sp.get('weeks_left')} left).")
        for n in cs.get("nowcast", [])[:2]:
            L.append(f"NDPSR nowcast {n['month']} (through {n['through']}): cheese {n['cheese']}, butter {n['butter']}, NDM {n['ndm']}, whey {n['whey']} $/lb; Class III {n['class3']}, Class IV {n['class4']} $/cwt.")
        L.append(f"Last announced class prices: {cs.get('last_announced')}. The desk rebuild matches announced Class III/IV to the cent.")
        add("dairy_cash", "Dairy cash markets, NDPSR and Class III/IV nowcast", "fundamental", ["class iii", "class iv", "ndpsr", "spot", "cheese", "butter", "nonfat", "whey", "barrels", "blocks", "milk", "dairy", "nowcast"], L)
    H = J(D / "livestock/derived/hogs.json")
    Cc = J(D / "livestock/derived/cattle.json")
    L = []
    if H:
        ix = H["index"]
        L.append("CME Lean Hog Index (desk rebuild), last 10 days: " + ", ".join(f"{d}: {v}" for d, v in list(zip(ix["date"], ix.get("index") or ix.get("value") or []))[-10:]))
        cu = H.get("cutout") or {}
        vals = cu.get("cutout") or cu.get("value") or []
        if vals:
            L.append("Pork cutout, last 5: " + ", ".join(f"{d}: {v}" for d, v in list(zip(cu["date"], vals))[-5:]))
    if Cc:
        fa = Cc.get("five_area") or {}
        for k, v in fa.items():
            if k != "date" and isinstance(v, list):
                L.append(f"5-area {k}, last 6 weeks: " + ", ".join(f"{d}: {x}" for d, x in list(zip(fa["date"], v))[-6:]))
                break
        bb = Cc.get("boxed_beef") or {}
        for k, v in bb.items():
            if k != "date" and isinstance(v, list):
                L.append(f"Boxed beef {k}, last 5: " + ", ".join(f"{d}: {x}" for d, x in list(zip(bb["date"], v))[-5:]))
                break
        for k in ("curve_le", "curve_gf"):
            cv = Cc.get(k) or {}
            if cv.get("cash") is not None:
                L.append(f"{cv.get('cash_label')}: {cv['cash']}")
    CSD = J(D / "livestock/derived/cattle_sd.json")
    if CSD:
        L.append("Fed cattle slaughter forecast: " + ", ".join(f"{x['month']} {x['forecast_k']}k ({x['yoy_pct']:+.1f}% y/y)" for x in CSD.get("forward", [])[:6]))
    add("livestock_cash", "Livestock cash markets (hog index, cutout, 5-area cattle, boxed beef, feeder index)", "fundamental",
        ["hog index", "lean hog index", "cutout", "pork", "5-area", "cash cattle", "boxed beef", "feeder index", "slaughter", "packer", "hogs", "cattle"], L)
    # calendar and news
    CAL = J(D / "calendar/calendar.json")
    if CAL:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ev = [e for e in CAL["events"] if e["date"] >= today][:70]
        add("calendar", "Calendar of reports and contract dates (next weeks)", "calendar",
            ["calendar", "when", "next", "report", "release", "schedule", "expiry", "last trading", "first notice", "wasde", "eia", "cot", "this week", "tomorrow"],
            [f"Events from {today} (US Central time):"] + [f"{e['date']} {e.get('time') or ''} {e['event']} [{', '.join(e.get('markets') or [])}]{' (estimated)' if e.get('estimated') else ''}" for e in ev], 5000)
    NW = J(D / "news/news.json")
    if NW:
        it = NW["items"][:60]
        add("news", "Latest headlines (last days)", "news", ["news", "headline", "headlines", "latest", "today", "reuters", "bloomberg", "story", "why did"],
            [f"Headlines, newest first ({NW.get('generated')}):"] + [f"{x['time'][:10]} [{', '.join(x.get('tags') or [])}] {x['title']} ({x.get('source')})" for x in it], 6000)


def main():
    cards = []
    B = J(D / "brief/latest.json") or {}
    S = {m["sym"]: m for m in (J(D / "summary/summary.json") or {}).get("markets", [])}
    R = J(D / "research/research.json") or {}
    RM = R.get("markets", {})
    BM = {m["sym"]: m for m in B.get("markets", [])}
    V = (J(D / "vol/vol.json") or {}).get("markets", {})
    # overview
    ov = [f"Morning brief {B.get('generated_et', '')}."]
    ov += [f"- {h}" for h in B.get("headlines", [])[:10]]
    mac = B.get("macro") or {}
    if mac.get("view"):
        ov.append(f"Macro view for ags: {mac['view']} (score {mac.get('score')}). {clip(mac.get('summary'), 600)}")
    if B.get("us_econ"):
        ov.append("US economy: " + clip(B["us_econ"], 700))
    en = (B.get("energy") or {}).get("read")
    if en:
        ov.append("Energy: " + clip(en, 600))
    if B.get("crush"):
        ov.append("Crush/ratios: " + clip(json.dumps(B.get("crush")) + " " + json.dumps(B.get("ratios")), 400))
    ev = B.get("events_ahead") or []
    if ev:
        ov.append("Events ahead: " + "; ".join(f"{e.get('date', '')} {e.get('title') or e.get('name') or ''}" for e in ev[:12]))
    cards.append({"id": "overview", "title": "Desk overview (morning brief, macro, energy)", "kind": "overview", "aliases": ["today", "overview", "macro", "brief", "summary"], "text": "\n".join(ov)})
    # one-line table of every market
    rows = []
    for sym in list(dict.fromkeys(list(BM) + list(RM))):
        b, r = BM.get(sym, {}), RM.get(sym, {})
        name = b.get("name") or r.get("name") or sym
        t = r.get("trend") or {}
        rows.append(f"{name} ({sym}): {b.get('contract', r.get('held', ''))} {f(b.get('last', r.get('price')))} {b.get('unit', r.get('unit', ''))}, "
                    f"1w {f(b.get('r1w'), 1)}%, 1m {f(b.get('r1m'), 1)}%, view {b.get('view', '-')}, rating {b.get('rating', '-')}, "
                    f"12m roll-adj {f((t.get('r12') or 0) * 100, 1)}%, EWMA vol {t.get('ewma_vol', '-')}%, funds {b.get('driver', '-')}")
    cards.append({"id": "table", "title": "All markets at a glance", "kind": "table", "aliases": ["all markets", "compare", "which", "strongest", "weakest", "best", "worst", "rank"],
                  "text": f"Data as of {B.get('date', '')}.\n" + "\n".join(rows)})
    # per market
    for sym in list(dict.fromkeys(list(S) + list(BM) + list(RM))):
        b, s, r = BM.get(sym, {}), S.get(sym, {}), RM.get(sym, {})
        name = b.get("name") or s.get("name") or r.get("name") or sym
        L = [f"{name} ({sym}) — data as of {B.get('date', '')}."]
        if b:
            L.append(f"Price {b.get('contract')} {f(b.get('last'))} {b.get('unit')} (chg {f(b.get('chg'))}, 1w {f(b.get('r1w'), 1)}%, 1m {f(b.get('r1m'), 1)}%), "
                     f"52w {f(b.get('lo52'))}-{f(b.get('hi52'))}, RSI {f(b.get('rsi'), 0)}, support {f(b.get('sup'))}, resistance {f(b.get('res'))}, ATR {f(b.get('atr'))}. "
                     f"Rating {b.get('rating')}, trend {b.get('trend')}, desk view {b.get('view')} ({b.get('conviction')} conviction).")
            L.append(f"Managed money net {f(b.get('mm_net'), 0)} (w/w {f(b.get('mm_chg'), 0)}), 3y pct {b.get('mm_pct3')}, driver {b.get('driver')}. "
                     f"Spread {b.get('spread')} {b.get('spread_v')} ({b.get('spread_read')}). Next event {b.get('event')} {b.get('event_date')}.")
            if b.get("technical"):
                L.append("Technical: " + clip(b["technical"], 500))
            if b.get("levels"):
                L.append(clip(b["levels"], 350))
            if b.get("flags"):
                L.append("Flags: " + "; ".join(x["text"] for x in b["flags"])[:400])
        if s.get("paras"):
            for k, v in s["paras"].items():
                L.append(f"{k.capitalize()}: " + clip(v, 550))
        if s.get("ideas"):
            L.append("Ideas: " + clip("; ".join(f"{i.get('method')}: {i.get('side')} {i.get('instrument', '')} {i.get('rationale', '')}" for i in s["ideas"]), 450))
        if r:
            L.append("Research signals: " + clip(r.get("read"), 700) + (" Flags: " + " ".join(r["flags"]) if r.get("flags") else ""))
            bt = (r.get("backtest") or {}).get("tsmom_12m") or {}
            if bt:
                L.append(f"Trend backtest Sharpe {bt.get('sharpe')} since {bt.get('since')}; carry backtest Sharpe {((r.get('backtest') or {}).get('carry') or {}).get('sharpe')}. "
                         f"Sizing: {r['size'].get('contracts_10pct_1m')} contracts for 10% vol on $1M; notional ${r['size'].get('notional')}.")
        o = J(D / "options" / f"{sym}.json")
        if o and o.get("read"):
            L.append("Options: " + clip(o["read"], 500))
        elif sym in V:
            L.append(f"Realized vol 20d {V[sym].get('hv20_front')}% ({V[sym].get('hv20_pct5y')}th 5y pct).")
        g = J(D / "geo" / f"{GEO.get(sym, '_')}.json")
        if g and g.get("calendar"):
            reads = [f"{c['country']}: {c.get('read', '')}" for c in g["calendar"][:4] if c.get("read")]
            if reads:
                L.append("Crop calendar/weather: " + clip(" | ".join(reads), 600))
        if g and g.get("production"):
            top = g["production"][:5] if isinstance(g["production"], list) else []
            if top and isinstance(top[0], dict):
                L.append("Top producers: " + ", ".join(f"{x.get('country')} {x.get('share', '')}%" for x in top))
        cards.append({"id": sym, "title": name, "kind": "market", "aliases": ALIASES.get(sym, [sym.lower()]) + [name.lower()], "text": "\n".join(L)[:4200]})
    # export sales / WASDE
    E = (J(D / "grains/derived/esr_brief.json") or {}).get("commodities", {})
    for v in (E if isinstance(E, list) else []):
        k = v.get("key") or v.get("name", "").lower()
        L = [f"US export sales (USDA ESR) {v.get('name')} {v.get('my')}, week ending {v.get('week')} (unit {v.get('unit')}):"]
        L += [re.sub(r"\*\*", "", f"{x.get('h')}: {x.get('t')}") for x in (v.get("brief") or [])[:6]]
        L.append(f"Commitments {f(v.get('commit'), 0)} = {f((v.get('pace') or 0) * 100, 0)}% of USDA target {f(v.get('target'), 0)} (5y normal {f((v.get('pace_norm') or 0) * 100, 0)}%); "
                 f"net sales this week {f(v.get('net'), 0)}, 4-wk avg {f(v.get('net4'), 0)} vs 5y {f(v.get('net4_5y'), 0)}; needed per week {f(v.get('need_sales'), 0)}; tilt {v.get('tilt')}.")
        if v.get("buyers"):
            L.append("Top buyers this week: " + ", ".join(f"{b['c']} {f(b['v'], 0)}" for b in v["buyers"][:6]))
        cards.append({"id": f"esr_{k}", "title": f"Export sales {v.get('name')}", "kind": "fundamental",
                      "aliases": [k, (v.get("name") or "").lower(), "export sales", "exports", "esr", "sales", "buyers", "china", "mexico"], "text": clip("\n".join(L), 2600)})
    W = J(D / "grains/derived/wasde.json") or {}
    for c, v in (W.get("commodities") or {}).items():
        us = v.get("us", {})
        L = []
        for my, x in sorted(us.items())[-2:]:
            it = x.get("items", {})
            L.append(f"{my} ({x.get('report')}): " + ", ".join(f"{k} {it[k]['value']} {it[k].get('unit', '')}".strip() + (f" (chg {it[k]['change']})" if it[k].get('change') else "")
                                                             for k in ("area_planted", "yield", "production", "exports", "use", "end_stocks", "price") if k in it))
        cards.append({"id": f"wasde_{c}", "title": f"WASDE US {c}", "kind": "fundamental", "aliases": [c, "wasde", "usda", "balance", "stocks", "ending stocks", "supply"], "text": f"USDA WASDE US balance, {c}:\n" + "\n".join(L)})
    # COT full desk (BCOM markets)
    C = J(ROOT / "cot/data/latest_summary.json")
    if C:
        L = [f"CFTC disaggregated COT, report {C.get('report_date')} (managed money net, w/w change, percentile of net over 3y / 10y / full history; producer/merchant net pct full):"]
        for c in C.get("commodities", []):
            v = next((x for x in c.get("variants", []) if x.get("crop_type") == "all"), None)
            if not v:
                continue
            mm = v["categories"].get("managed_money", {}); pm = v["categories"].get("prod_merc", {})
            p = mm.get("pctiles", {})
            L.append(f"{c['name']} ({c['ticker']}): MM net {mm.get('net'):,} ({mm.get('net_pct_oi')}% OI), w/w {mm.get('wk_chg_net'):+,}, pct 3y {p.get('net_3yr')} / 10y {p.get('net_10yr')} / full {p.get('net_full')}; "
                     f"producers pct {(pm.get('pctiles') or {}).get('net_full')}")
        cards.append({"id": "cot_full", "title": "COT positioning (21 BCOM markets)", "kind": "positioning",
                      "aliases": ["cot", "cftc", "positioning", "funds", "managed money", "speculators", "commercials", "crowded", "gold", "silver", "copper", "sugar", "coffee", "cocoa", "brent"],
                      "text": "\n".join(L)})
    # research cross-section and method notes
    xs = R.get("cross_section") or {}
    if xs:
        cards.append({"id": "research", "title": "Research signals method and cross-section", "kind": "method", "aliases": ["signals", "research", "momentum", "carry", "backtest", "tsmom", "sharpe", "kelly", "density"],
                      "text": "Signals tab: time-series momentum (12-month roll-adjusted excess return, 40% EWMA vol target, Moskowitz-Ooi-Pedersen), carry (F1-F2 annualized vs same calendar month; Fama-French, Gorton-Hayashi-Rouwenhorst, Erb-Harvey), "
                              "variance ratio trend quality, options IV-RV and Breeden-Litzenberger density, COT crowding, sizing (vol target, inverse vol, half Kelly), sqrt impact. "
                              f"Cross-section tercile backtests: momentum {json.dumps(xs.get('momentum'))}; carry {json.dumps(xs.get('carry'))}."})
    more_cards(cards)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "data_date": B.get("date"), "cards": cards}
    (D / "ai").mkdir(parents=True, exist_ok=True)
    (D / "ai" / "context.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(len(cards), "cards,", sum(len(c["text"]) for c in cards), "chars;", max(len(c["text"]) for c in cards), "max")


if __name__ == "__main__":
    main()
