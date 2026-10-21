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
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "data_date": B.get("date"), "cards": cards}
    (D / "ai").mkdir(parents=True, exist_ok=True)
    (D / "ai" / "context.json").write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(len(cards), "cards,", sum(len(c["text"]) for c in cards), "chars;", max(len(c["text"]) for c in cards), "max")


if __name__ == "__main__":
    main()
