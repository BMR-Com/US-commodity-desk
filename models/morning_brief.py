#!/usr/bin/env python3
"""Morning brief: one page per day, ready before 8 am ET, covering every market on the desk.

For each market: overnight price vs the prior settle, week/month change, the technical read (rating, trend, RSI,
support/resistance, trend-follower trigger levels), fund positioning, CME open-interest change, the overall view,
flags and the latest headlines. Plus today's and the next few days' scheduled reports, flash export sales since
the last brief, and cross-market numbers (board crush, ratios).

Built from the other models' outputs (trader sheet, summary, technicals, news, calendar, flash, CME files), so run
it after ohlc/technicals/trader_sheet/summary and news. Writes data/brief/latest.json, data/brief/latest.md and an
archive copy data/brief/<YYYY-MM-DD>.md.
"""
import csv, json, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
OUT = D / "brief"
ET = ZoneInfo("America/New_York")
NEWS_TAGS = {"ZC": ["corn"], "ZS": ["soybeans", "south_america"], "ZM": ["meal"], "ZL": ["oil"], "ZW": ["wheat"], "KE": ["wheat"],
             "CT": ["cotton"], "HE": ["hogs"], "LE": ["cattle"], "GF": ["cattle"], "DC": ["dairy"], "GDK": ["dairy"]}
GROUPS = [("grains", "Grains & oilseeds"), ("softs", "Cotton"), ("livestock", "Livestock"), ("dairy", "Dairy")]
CT_OFF = {"CT": -1}  # calendar times are CT; ET = CT + 1h


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def fmt(v, dp=2):
    return "–" if v is None else f"{v:,.{dp}f}"


def sentences(text, n):
    s = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text or "")
    return " ".join(s[:n]).strip()


def ct_to_et(t):
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)\s*CT", t or "")
    if not m:
        return t or ""
    h, mi, ap = int(m[1]) % 12, int(m[2]), m[3]
    h = h + (12 if ap == "PM" else 0) + 1
    return f"{(h - 1) % 12 + 1}:{mi:02d} {'PM' if h >= 12 else 'AM'} ET"


def cme_oi():
    """Total futures OI and its change per symbol from the latest CME volume/OI file."""
    dirs = sorted(p for p in (D / "cme").glob("2*") if (p / "fut_volume_oi.csv").exists())
    if not dirs:
        return None, {}
    out = {}
    with open(dirs[-1] / "fut_volume_oi.csv") as f:
        for r in csv.DictReader(f):
            o = out.setdefault(r["sym"], {"oi": 0, "oi_chg": 0, "vol": 0, "report": r["report_type"]})
            for k, c in (("oi", "oi"), ("oi_chg", "oi_change"), ("vol", "total_vol")):
                try:
                    o[k] += int(float(r[c] or 0))
                except ValueError:
                    pass
    return dirs[-1].name, out


def main():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ET).date()
    sheet = J("summary/sheet.json") or {"rows": []}
    summ = {m["sym"]: m for m in (J("summary/summary.json") or {"markets": []})["markets"]}
    news = (J("news/news.json") or {"items": []})["items"]
    cal = (J("calendar/calendar.json") or {"events": []})["events"]
    flash = J("grains/raw/flash/announcements.json") or []
    oi_date, oi = cme_oi()

    def recent_news(tags, hours=36, n=3):
        cut = now - timedelta(hours=hours)
        out = []
        for it in news:
            try:
                t = datetime.strptime(it["time"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if t >= cut and (tags is None and not it.get("tags") or tags and set(tags) & set(it.get("tags", []))):
                out.append({"title": it["title"], "source": it.get("source"), "time": it["time"], "link": it.get("link")})
        return sorted(out, key=lambda x: x["time"], reverse=True)[:n]

    markets = []
    for r in sheet["rows"]:
        s = summ.get(r["sym"], {})
        last, chg = r.get("last"), r.get("chg")
        pct = None if last is None or chg is None or last == chg else 100 * chg / (last - chg)
        markets.append({
            "sym": r["sym"], "name": r["name"], "group": r["group"], "contract": r.get("contract"), "unit": r.get("unit"),
            "dp": s.get("dp", 2), "last": last, "chg": chg, "chg_pct": pct, "r1w": r.get("r1w"), "r1m": r.get("r1m"),
            "rating": r.get("rating"), "trend": r.get("trend"), "rsi": r.get("rsi"), "sup": r.get("sup"), "res": r.get("res"),
            "cta_up": r.get("cta_up"), "cta_dn": r.get("cta_dn"), "hi52": r.get("hi52"), "lo52": r.get("lo52"), "atr": r.get("atr"),
            "mm_net": r.get("mm_net"), "mm_chg": r.get("mm_dn"), "mm_pct3": r.get("mm_pct3"), "driver": r.get("driver"),
            "spread": r.get("spread"), "spread_v": r.get("spread_v"), "spread_read": r.get("spread_read"),
            "esr_pace": r.get("esr_pace"), "esr_norm": r.get("esr_norm"),
            "view": r.get("view"), "conviction": r.get("conviction"),
            "technical": sentences(s.get("paras", {}).get("technical"), 3),
            "levels": sentences(re.sub(r"^.*?(Levels to watch:)", r"\1", s.get("paras", {}).get("outlook", ""), count=1), 2)
            if "Levels to watch" in s.get("paras", {}).get("outlook", "") else "",
            "flags": r.get("flags", []), "event": r.get("event"), "event_date": r.get("event_date"),
            "oi": oi.get(r["sym"]), "news": recent_news(NEWS_TAGS.get(r["sym"], []))})

    d0 = today.isoformat()
    ahead = (today + timedelta(days=4)).isoformat()
    ev_today = [dict(e, time_et=ct_to_et(e.get("time"))) for e in cal if e["date"] == d0]
    ev_ahead = [dict(e, time_et=ct_to_et(e.get("time"))) for e in cal if d0 < e["date"] <= ahead and e.get("importance", 0) >= 2]
    def tkey(e):
        m = re.match(r"(\d+):(\d+)\s*(AM|PM)", e.get("time") or "")
        return (e["date"], (int(m[1]) % 12 + (12 if m[3] == "PM" else 0)) * 60 + int(m[2]) if m else 9999)
    ev_today.sort(key=tkey)
    ev_ahead.sort(key=tkey)
    for m in markets:  # drop the summary's trailing "N ideas below" pointer
        m["levels"] = re.sub(r"\s*\d+ ideas? below.*$", "", m["levels"]).strip()
    fcut = (now - timedelta(days=3)).isoformat()
    fl = [{"t": a["t"], "title": a["title"], "text": a.get("text")} for a in flash
          if a.get("t") and datetime.fromisoformat(a["t"]).astimezone(timezone.utc).isoformat() >= fcut]
    fl.sort(key=lambda a: a["t"], reverse=True)

    # headline bullets: biggest overnight movers, today's reports, fresh flash sales, strongest views
    heads = []
    mv = sorted([m for m in markets if m["chg_pct"] is not None], key=lambda m: -abs(m["chg_pct"]))[:3]
    if mv:
        heads.append("Biggest moves vs prior settle: " + "; ".join(f"{m['name']} {m['chg']:+.{m['dp']}f} ({m['chg_pct']:+.1f}%)" for m in mv) + ".")
    if ev_today:
        heads.append("Today: " + "; ".join(f"{e['event']} {e['time_et']}".strip() for e in sorted(ev_today, key=lambda e: -e.get("importance", 0))[:5]) + ".")
    if fl:
        heads.append(f"{len(fl)} flash export sale announcement(s) in the last 3 days, latest: {fl[0]['text'] or fl[0]['title']}")
    strong = [m for m in markets if m["view"] and m["view"].startswith("strongly")]
    if strong:
        heads.append("Strongest desk views: " + "; ".join(f"{m['name']} {m['view']}" for m in strong) + ".")
    tech_flips = [m for m in markets if m["last"] is not None and ((m["cta_up"] and m["last"] > m["cta_up"]) or (m["cta_dn"] and m["last"] < m["cta_dn"]))]
    if tech_flips:
        heads.append("Through a trend-follower trigger: " + "; ".join(
            f"{m['name']} {'above' if m['cta_up'] and m['last'] > m['cta_up'] else 'below'} {fmt(m['cta_up'] if m['cta_up'] and m['last'] > m['cta_up'] else m['cta_dn'], m['dp'])}" for m in tech_flips) + ".")

    B = {"generated": now.strftime("%Y-%m-%d %H:%M UTC"), "generated_et": now.astimezone(ET).strftime("%a %b %d, %Y %I:%M %p ET"),
         "date": d0, "prices_from": sheet.get("generated"), "cme_oi_date": oi_date, "headlines": heads,
         "events_today": ev_today, "events_ahead": ev_ahead, "flash": fl, "markets": markets,
         "crush": sheet.get("crush"), "ratios": sheet.get("ratios"), "general_news": recent_news(None, 24, 6)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(B, indent=1, default=str))
    md = to_md(B)
    (OUT / "latest.md").write_text(md)
    (OUT / f"{d0}.md").write_text(md)
    print("brief", d0, len(markets), "markets,", len(ev_today), "events today,", len(fl), "flash")


def to_md(B):
    L = [f"# Morning brief · {B['generated_et']}", "",
         f"Prices: front contracts, last vs prior settle (indicative before the open; data {B['prices_from']}). CME open interest from {B['cme_oi_date']}. Research only, not investment advice.", ""]
    L += ["## Key points", ""] + [f"- {h}" for h in B["headlines"]] + [""]
    L += ["## Calendar", ""]
    L += [f"- **Today** {e['time_et']} · {e['event']}" for e in B["events_today"]] or ["- Nothing scheduled today."]
    L += [f"- {e['date']} {e['time_et']} · {e['event']}" for e in B["events_ahead"]] + [""]
    L += ["## Key numbers", "", "| Market | Contract | Last | Chg | 1 wk | 1 m | Rating | RSI | Support | Resistance | Funds net (chg) | OI chg | View |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g, gl in GROUPS:
        for m in [m for m in B["markets"] if m["group"] == g]:
            dp = m["dp"]
            chg = "–" if m["chg"] is None else f"{m['chg']:+.{dp}f}" + ("" if m["chg_pct"] is None else f" ({m['chg_pct']:+.1f}%)")
            pc = lambda v: "–" if v is None else f"{v:+.1f}%"
            mm = "–" if m["mm_net"] is None else f"{m['mm_net']:,.0f} ({(m['mm_chg'] or 0):+,.0f})"
            oi = "–" if not m["oi"] else f"{m['oi']['oi_chg']:+,}"
            L.append(f"| {m['name']} | {m['contract'] or ''} | {fmt(m['last'], dp)} | {chg} | {pc(m['r1w'])} | {pc(m['r1m'])} | {m['rating'] or '–'} | "
                     f"{fmt(m['rsi'], 0)} | {fmt(m['sup'], dp)} | {fmt(m['res'], dp)} | {mm} | {oi} | {m['view'] or '–'} |")
    L.append("")
    if B.get("crush"):
        c = B["crush"]
        L.append(f"Board crush {c['crush']:.3f} $/bu (10-yr pct {c['crush_pct10']:.0f}), oil share {c['oil_share']:.1f}%. "
                 + " ".join(f"{r['name']} {r['now']:.3f}." if r['unit'] == 'ratio' else f"{r['name']} {r['now']:.2f} {r['unit']}." for r in (B.get("ratios") or [])[:4]))
        L.append("")
    if B["flash"]:
        L += ["## Flash export sales (last 3 days)", ""] + [f"- {a['t'][:10]}: {a['text'] or a['title']}" for a in B["flash"]] + [""]
    L += ["## Technical outlook by market", ""]
    for g, gl in GROUPS:
        ms = [m for m in B["markets"] if m["group"] == g]
        if not ms:
            continue
        L += [f"### {gl}", ""]
        for m in ms:
            L.append(f"**{m['name']}** ({m['contract']}, {m['view'] or 'no view'}). {m['technical']} {m['levels']}".strip())
            fl = [f["text"] for f in m["flags"]]
            if fl:
                L.append("Flags: " + "; ".join(fl) + ".")
            if m["event"] and "Next catalysts" not in m["levels"]:
                L.append(f"Next catalyst: {m['event']} {m['event_date']}.")
            for n in m["news"]:
                L.append(f"- [{n['title']}]({n['link']}) · {n.get('source') or ''}")
            L.append("")
    if B["general_news"]:
        L += ["## Other headlines", ""] + [f"- [{n['title']}]({n['link']}) · {n.get('source') or ''}" for n in B["general_news"]] + [""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
