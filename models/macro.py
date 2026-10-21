#!/usr/bin/env python3
"""Macro read for commodities and ags: rates, the dollar and farm-exporter currencies, risk appetite, energy,
China/industrial demand and commodity breadth, each with its usual channel into ag prices, plus this week's
high-impact US and China releases.

Rule-based text from data/markets/markets.json and data/macro/econ_calendar.json. The channels are the standard
ones (a stronger dollar or weaker BRL weighs on US export prices; crude feeds soybean oil and corn via biofuels;
risk-off and higher real rates pull fund money out of commodities); they have not been back-tested on this desk,
so the score is context, not a trading signal. Writes data/macro/macro.json.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
ET = ZoneInfo("America/New_York")


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def sgn(v, a, b=None):
    """+1 if v > a, -1 if v < -a (or < b), else 0."""
    if v is None:
        return 0
    return 1 if v > a else -1 if v < (-a if b is None else b) else 0


def f(v, d=1, plus=True):
    return "n/a" if v is None else (f"{v:+.{d}f}" if plus else f"{v:.{d}f}")


def main():
    M = J("markets/markets.json")
    if not M:
        print("macro: no markets.json")
        return
    I = {x["sym"]: x for x in M["items"]}
    g = lambda s, k="m1": (I.get(s) or {}).get(k)
    T = M.get("treasury") or {}
    tc = {c["tenor"]: c for c in T.get("curve", [])}
    y10, y2 = (tc.get("10 Yr") or {}).get("now"), (tc.get("2 Yr") or {}).get("now")
    y10m = None if not tc.get("10 Yr") or tc["10 Yr"]["m1"] is None else 100 * (tc["10 Yr"]["now"] - tc["10 Yr"]["m1"])
    y2m = None if not tc.get("2 Yr") or tc["2 Yr"]["m1"] is None else 100 * (tc["2 Yr"]["now"] - tc["2 Yr"]["m1"])
    sec, score = [], {}

    # rates
    s = -sgn(y10m, 15)
    score["rates"] = s
    sec.append(("Rates", s, f"US 10-year {f(y10, 2, False)}% ({f(y10m, 0)} bp in a month), 2-year {f(y2, 2, False)}% ({f(y2m, 0)} bp); "
                f"2s10s curve {f(T.get('s2s10_bp'), 0)} bp ({f(T.get('s2s10_chg_1m_bp'), 0)} bp in a month). "
                + ("Rising long yields raise carry and funding costs and pull money out of commodities. " if s < 0 else
                   "Falling yields ease funding costs and support commodity investment flows. " if s > 0 else "Yields are little changed on the month. ")
                + ("A steepening curve led by the long end often reflects inflation or term-premium worries; " if (T.get("s2s10_chg_1m_bp") or 0) > 10 else "")
                + f"T-bill yield {f(g('^IRX', 'last'), 2, False)}% sets the cost of carrying inventory."))
    # dollar and exporter currencies
    dxy, brl, cny, mxn = g("DX-Y.NYB"), g("BRL=X"), g("CNY=X"), g("MXN=X")
    s = -sgn(dxy, 1.0)
    s_brl = sgn(brl, 2.0)  # USD/BRL up = weaker real = Brazil farmers sell more = bearish soy/corn/sugar/coffee/cotton
    score["dollar"] = s
    score["brl"] = -s_brl
    sec.append(("Dollar & farm currencies", s - s_brl,
                f"Dollar index {f(g('DX-Y.NYB', 'last'), 2, False)} ({f(dxy)}% in a month, {f(g('DX-Y.NYB', 'ytd'))}% YTD). "
                + ("A stronger dollar makes US grain, oilseeds, cotton and meat dearer abroad. " if s < 0 else "A softer dollar helps US export competitiveness. " if s > 0 else "")
                + f"USD/BRL {f(g('BRL=X', 'last'), 3, False)} ({f(brl)}% in a month): "
                + ("a weaker real encourages Brazilian farmer selling of soybeans, corn, sugar, coffee and cotton, pressuring world prices. " if s_brl > 0 else
                   "a firmer real slows Brazilian farmer selling and supports world prices. " if s_brl < 0 else "little changed. ")
                + f"USD/CNY {f(g('CNY=X', 'last'), 3, False)} ({f(cny)}%); USD/MXN {f(g('MXN=X', 'last'), 2, False)} ({f(mxn)}%)"
                + ("; a sharply weaker peso cuts Mexico's buying power for US corn, pork, dairy and wheat (Mexico is the top buyer of all four)." if (mxn or 0) > 3 else
                   "; a firmer peso supports Mexican buying of US corn, pork, dairy and wheat." if (mxn or 0) < -3 else ".")))
    if (mxn or 0) > 3:
        score["mxn"] = -1
    # risk appetite
    spx, vix = g("^GSPC"), g("^VIX", "last")
    s = sgn(spx, 3.0) - (1 if (vix or 0) > 25 else 0) + (1 if vix is not None and vix < 15 else 0)
    s = max(-1, min(1, s))
    score["risk"] = s
    sec.append(("Risk appetite", s, f"S&P 500 {f(spx)}% in a month ({f(g('^GSPC', 'ytd'))}% YTD); VIX {f(vix, 1, False)}. "
                + ("Risk-off: funds tend to cut commodity length along with equities. " if s < 0 else
                   "Risk-on backdrop: supportive for index and trend-following flows into commodities. " if s > 0 else "Neutral risk backdrop. ")))
    # energy
    wti, ng = g("CL=F"), g("NG=F")
    s = sgn(wti, 5.0)
    score["energy"] = s
    sec.append(("Energy", s, f"WTI {f(g('CL=F', 'last'), 2, False)} $/bbl ({f(wti)}% in a month), Brent {f(g('BZ=F', 'last'), 2, False)}, "
                f"ULSD {f(g('HO=F', 'last'), 3, False)} $/gal ({f(g('HO=F'))}%), natural gas {f(g('NG=F', 'last'), 2, False)} ({f(ng)}%). "
                + ("Higher crude lifts biofuel margins (soybean oil, corn for ethanol) and synthetic-fibre costs (supports cotton), but raises diesel, drying and freight costs. " if s > 0 else
                   "Lower crude weighs on soybean oil and corn through biofuel margins and on cotton via cheaper polyester. " if s < 0 else "Crude little changed on the month. ")
                + ("Natural gas drives nitrogen fertilizer costs for next year's corn. " if abs(ng or 0) > 10 else "")))
    # china / industrial
    cu, sh, hsi = g("HG=F"), g("000001.SS"), g("^HSI")
    s = sgn((cu or 0) + (sh or 0), 4.0)
    score["china"] = s
    sec.append(("China & industrial demand", s, f"Copper {f(cu)}% in a month, Shanghai Composite {f(sh)}%, Hang Seng {f(hsi)}%, yuan {f(-(cny or 0))}% vs USD. "
                + ("Firm China/industrial signals support demand for soybeans, cotton and meat imports. " if s > 0 else
                   "Soft China/industrial signals point to weaker import demand. " if s < 0 else "Mixed China signals. ")))
    # commodity breadth
    comm = [x for x in M["items"] if x["group"] in ("Energy", "Metals", "Grains & oilseeds", "Softs", "Livestock & dairy")]
    above = [x for x in comm if x.get("ma50") and x["last"] > x["ma50"]]
    br = 100 * len(above) / len(comm) if comm else None
    s = sgn((br or 50) - 50, 15)
    score["breadth"] = s
    gold = g("GC=F")
    sec.append(("Commodity breadth", s, f"{len(above)} of {len(comm)} commodities trade above their 50-day average ({f(br, 0, False)}%); S&P GSCI {f(g('^SPGSCI'))}% in a month; "
                f"gold {f(gold)}%" + (" — a strong gold bid alongside high yields points to inflation/debasement hedging. " if (gold or 0) > 5 else ". ")))

    total = sum(score.values())
    view = "tailwind" if total >= 2 else "headwind" if total <= -2 else "mixed"
    ags = [x for x in comm if x["group"] in ("Grains & oilseeds", "Softs", "Livestock & dairy")]
    best = sorted([x for x in ags if x.get("m1") is not None], key=lambda x: -x["m1"])
    # this week's high-impact US/China events still to come
    cal = (J("macro/econ_calendar.json") or {}).get("events", [])
    today = datetime.now(ET).date()
    wk = [e for e in cal if today.isoformat() <= e["date"] <= (today + timedelta(days=7)).isoformat() and e["impact"] in ("High",) and e["country"] in ("US", "China")]
    summary = (f"Macro backdrop for ags: {view} (score {total:+d} across rates, dollar, Brazil real, risk, energy, China, breadth). "
               + "; ".join(f"{k} {'+' if v > 0 else '−' if v < 0 else '0'}" for k, v in score.items()) + ". "
               + (f"Strongest ag/soft over the month: {best[0]['name']} {best[0]['m1']:+.1f}%; weakest: {best[-1]['name']} {best[-1]['m1']:+.1f}%. " if best else "")
               + (f"Key releases ahead: " + "; ".join(f"{e['country']} {e['title']} ({e['date'][5:]} {e['time']})" for e in wk[:6]) + "." if wk else ""))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "view": view, "score": total, "components": score,
           "summary": summary, "sections": [{"title": t, "score": s, "text": x} for t, s, x in sec],
           "caveat": "Directional channels from macro to ag prices are standard relationships, not signals tested on this desk; use as context.",
           "events_ahead": wk}
    (D / "macro").mkdir(parents=True, exist_ok=True)
    (D / "macro" / "macro.json").write_text(json.dumps(out, indent=1))
    print(summary)


if __name__ == "__main__":
    main()
