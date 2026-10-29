"""USDA AMS Weekly Cotton Market Review (mnreports/cnwwcmr.pdf, Fridays): prices, regional crop and harvest notes, domestic
mill and export demand, spot trades. Parsed to data/cotton_review/<report date>.json and latest.json; history kept, a week
already stored is not fetched again. Usage: python pipelines/ams_cotton_review.py [local.pdf]
"""
import io, json, re, sys
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cotton_review"
URL = "https://www.ams.usda.gov/mnreports/cnwwcmr.pdf"
MARKETS = ["SE", "ND", "SD", "ETX-STX", "WTX-KS-OK", "DSW", "SJV", "7-MKT AVG"]
REGIONS = {"Southeastern": "Southeast", "South Central": "South Central (Delta)", "Southwestern": "Southwest (Texas, Oklahoma, Kansas)", "Western": "West (Arizona, California, New Mexico)"}
SUBS = ["North Delta", "South Delta", "East Texas-South Texas", "West Texas-Kansas-Oklahoma", "Desert Southwest (DSW)", "San Joaquin Valley (SJV)", "American Pima (AP)", "Textile Mill"]
COUNTRIES = ["Bangladesh", "Vietnam", "Pakistan", "Indonesia", "Thailand", "China", "Turkey", "Mexico", "Peru", "Korea", "Taiwan", "India", "Japan", "Malaysia",
             "Guatemala", "Honduras", "El Salvador", "Colombia", "Ecuador", "Egypt", "Italy", "Portugal", "Germany", "Nicaragua", "Dominican Republic", "Costa Rica",
             "Philippines", "Sri Lanka", "Cambodia", "Burma", "Myanmar", "Hong Kong", "Brazil", "Canada", "Morocco", "Tunisia", "Uzbekistan"]
ADJ = {"Peruvian": "Peru", "Mexican": "Mexico", "Vietnamese": "Vietnam", "Indonesian": "Indonesia", "Pakistani": "Pakistan", "Bangladeshi": "Bangladesh",
       "Turkish": "Turkey", "Chinese": "China", "Thai": "Thailand", "Korean": "Korea", "Taiwanese": "Taiwan", "Indian": "India", "Japanese": "Japan",
       "Egyptian": "Egypt", "Colombian": "Colombia", "Guatemalan": "Guatemala", "Italian": "Italy", "Malaysian": "Malaysia"}


def clean(t):
    t = re.sub(r"(\w)- (\w)", r"\1\2", t.replace("’", "'"))
    t = re.sub(r"\b(\w) (\w{2,})\b", lambda m: m.group(1) + m.group(2) if m.group(1).lower() in "mf" and m.group(2) in ("oderate", "or") else m.group(0), t)
    return re.sub(r"\s+", " ", t).strip()


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", clean(t)) if len(s.strip()) > 3]


def page_columns(pg):
    """Narrative columns above the centred 'Trading' heading, and the full-width text below it."""
    W, H = pg.width, pg.height
    words = pg.extract_words()
    trading_y = next((w["top"] for w in words if w["text"] == "Trading" and abs((w["x0"] + w["x1"]) / 2 - W / 2) < 60), None)
    ap_y = next((w["top"] for i, w in enumerate(words) if w["text"] == "American" and i + 1 < len(words) and words[i + 1]["text"] == "Pima"
                 and w["x0"] > 150 and w["top"] > 150), None)
    head = next((w["bottom"] for w in words if w["text"] in ("Summary",)), 40) + 18
    stops = [y for y in (trading_y, ap_y) if y]
    bot = min(stops) - 2 if stops else H - 30
    L = pg.crop((0, head, W / 2, bot)).extract_text() or ""
    R = pg.crop((W / 2, head, W, bot)).extract_text() or ""
    T = pg.crop((0, trading_y, W, H)).extract_text() if trading_y else ""
    return L, R, T or ""


def merge(*ds):
    out = {}
    for d in ds:
        for k, v in d.items():
            out[k] = (out.get(k, "") + " " + v).strip()
    return out


def split_subs(text):
    """Split column text on sub-market headings (North Delta, Textile Mill, ...)."""
    out, cur, buf = {}, None, []
    for line in text.splitlines():
        s = line.strip()
        if re.search(r"Regional Summary|@usda\.gov|◦|^(et|ets|t|rket|arket|Market)s? Regional", s) or re.fullmatch(r"[a-z]{0,6}", s):
            continue
        hit = next((h for h in SUBS if s == h or s.startswith(h) and len(s) < len(h) + 3), None)
        if hit:
            if buf:
                out[cur] = out.get(cur, "") + " " + " ".join(buf)
            cur, buf = hit, []
        else:
            buf.append(s)
    if buf:
        out[cur] = out.get(cur, "") + " " + " ".join(buf)
    return {k: clean(v) for k, v in out.items() if v.strip()}


AREAS = r"East Texas/South Texas|West Texas, Kansas, Oklahoma|North Delta|South Delta|Desert Southwest|San Joaquin Valley|American Pima"


def trades(T):
    T = re.sub(r"^\s*Trading\s*", "", T)
    items, cur_area = [], None
    T = re.sub(r"(%s)" % AREAS, r"•\1•", T)
    for chunk in re.split(r"\n(?=\s*•)|•", T):
        c = clean(chunk)
        if not c:
            continue
        m = re.match(r"^(%s)\s*(.*)$" % AREAS, c)
        if m:
            cur_area, c = m.group(1), m.group(2)
            if not c:
                continue
        if "No trading activity" in c:
            items.append({"area": cur_area, "text": "No trading reported."}); continue
        px = re.findall(r"(\d{2,3}\.\d{2})(?:\s*(?:to|-)\s*(\d{2,3}\.\d{2}))?\s*cents", c)
        q = re.search(r"colou?r ([\d ,and&-]+?)(?:,| and better)", c)
        vol = re.search(r"\b(light|moderate|heavy)\b volume", c)
        items.append({"area": cur_area, "text": c, "lo": float(px[0][0]) if px else None, "hi": float(px[0][1] or px[0][0]) if px else None,
                      "color": q.group(1).strip() if q else None, "volume": vol.group(1) if vol else None})
    return items


def countries(s):
    hit = [c for c in COUNTRIES if re.search(r"\b" + c + r"\b", s)] + [v for k, v in ADJ.items() if re.search(r"\b" + k + r"\b", s)]
    return sorted(set(hit), key=lambda c: s.find(c) if c in s else 999)


CROP = re.compile(r"harvest|defoliat|desiccat|boll|gin|module|weather|rain|precip|shower|temperature|freeze|frost|drought|moisture|"
                  r"field|crop|yield|quality|insurance|abandon|hail|storm|flood|regrowth|percent|NASS", re.I)
DEMAND = re.compile(r"mill|inquir|demand|export|buyer|forward contract|yarn|finished product|shipment|delivery|offering", re.I)
WEATHER_ONLY = re.compile(r"^(Daytime|Nighttime|Overnight)|temperatures? (were|ranged|peaked)|high temperatures|lows (were|ranged|dipped|cooled)", re.I)


def classify(text):
    crop, demand, market = [], [], []
    for s in sentences(text):
        if re.search(r"Spot cotton trading|Supplies (and|of)|Average local|CCC-loan|prices were|Trading of", s) and not re.search(r"mill", s, re.I):
            market.append(s)
        elif DEMAND.search(s) and not re.search(r"harvest|ginning|module", s, re.I):
            demand.append(s)
        elif CROP.search(s):
            crop.append(s)
    return crop, demand, market


def key_crop(crop):
    """The crop sentences worth keeping: NASS progress numbers and anything that moves the crop size or quality."""
    keep = []
    for s in crop:
        if WEATHER_ONLY.search(s) and not re.search(r"freeze|frost|hail|flood|tornado|damage", s, re.I):
            continue
        score = (3 if re.search(r"\d+ percent", s) else 0) + (3 if re.search(r"declin|damage|concern|abandon|insurance|adjuster|regrowth|quality|not to open|loss|poor|delay|interrupt", s, re.I) else 0) \
            + (2 if re.search(r"freeze|frost|hail|flood|tornado|historic", s, re.I) else 0) + (1 if re.search(r"ahead|behind|average|complet", s, re.I) else 0)
        keep.append((score, s))
    top = sorted(keep, key=lambda x: -x[0])[:3]
    return [nass(s) for sc, s in keep if sc > 0 and (sc, s) in top]


def nass(s):
    return re.sub(r"According to (?:the )?(?:National Agricultural Statistics Service's \(NASS\)|NASS)(?: Crop Progress report)?(?: released)?(?: on)? ([A-Z][a-z]+ \d{1,2}),?\s*",
                  lambda m: f"NASS ({m.group(1)[:3]} {m.group(1).split()[1]}): ", s)


def level(text, what):
    m = re.search(what + r"\s+(?:was|were)\s+([a-z]+(?: to [a-z]+)?)\b", text, re.I)
    return m.group(1).strip() if m else None


def parse(pdf_bytes):
    pdf = pdfplumber.open(io.BytesIO(pdf_bytes))
    p0 = pdf.pages[0].extract_text() or ""
    out = {"source": URL}
    m = re.search(r"Vol\.\s*(\d+)\s*No\.\s*(\d+)\s*•\s*([A-Z][a-z]+ \d{1,2}, \d{4})", p0)
    from datetime import datetime
    out["date"] = datetime.strptime(m.group(3), "%B %d, %Y").strftime("%Y-%m-%d") if m else None
    out["volume"] = f"Vol. {m.group(1)} No. {m.group(2)}" if m else None
    g = lambda pat, t=p0, f=float: (lambda m: f(m.group(1)) if m else None)(re.search(pat, t))
    out["prices"] = {"spot_7mkt_avg": g(r"([\d.]+)\s*cents/pound"), "chg_week_pts": (lambda m: (-1 if m.group(1) == "down" else 1) * float(m.group(2)) if m else None)(re.search(r"Change vs\. Last Week:\s*(up|down)\s*([\d.]+)\s*points", p0)),
                     "year_ago": g(r"up from ([\d.]+)¢|down from ([\d.]+)¢"), "range": re.findall(r"Weekly Range:\s*([\d.]+)¢\s*–\s*([\d.]+)¢", p0)[0] if re.search(r"Weekly Range", p0) else None,
                     "dec_settle": g(r"Price:\s*([\d.]+)¢"), "dec_settle_prev": g(r"up from ([\d.]+)¢ last week|down from ([\d.]+)¢ last week")}
    def grid(label):
        sec = p0.split(label, 1)[1] if label in p0 else ""
        rows = []
        for line in sec.splitlines():
            mm = re.match(r"\s*([A-Z][a-z]{2} \d{1,2})\s+([\d.\s]+)$", line)
            if mm:
                v = [float(x) for x in mm.group(2).split()]
                if len(v) == 8:
                    rows.append({"date": mm.group(1), **dict(zip(MARKETS, v))})
            elif rows:
                break
        return rows
    out["spot_41_4_34"], out["spot_31_3_36"] = grid("41-4-34 Prices"), grid("31-3-36 Prices")
    p1 = pdf.pages[1].extract_text() or ""
    fut = []
    for line in p1.splitlines():
        mm = re.match(r"\s*([A-Z][a-z]{2} \d{1,2})\s+([\d.\s]+)$", line)
        if mm:
            v = [float(x) for x in mm.group(2).split()]
            if len(v) >= 8:
                fut.append({"date": mm.group(1), "futures": v[:6], "spot_7mkt": v[6], "a_index": v[7]})
    hdr = re.search(r"((?:[A-Z][a-z]{2}-\d{2}\s+){5,6})", p1)
    out["futures_months"] = hdr.group(1).split() if hdr else None
    out["futures"] = fut
    out["awp"] = g(r"Adjusted World price\s*1?/?\s*([\d.]+)", p1)
    out["awp_window"] = (re.search(r"Prices are in effect from ([^\n]+)", p1) or [None, None])[1]
    out["ldp"] = g(r"Loan Deficiency Payment\s*([\d.]+)", p1)
    # regions
    regions, cur = [], None
    for pg in pdf.pages[3:9]:
        top = (pg.extract_text() or "").strip().splitlines()[:1]
        title = top[0] if top else ""
        rk = next((k for k in REGIONS if title.startswith(k)), None) if "Regional Summary" in title else None
        if not rk:
            continue
        L, R, T = page_columns(pg)
        if cur and cur["key"] == rk:
            cur["trades"] += trades(T); continue
        if rk == "Western":
            ws = pg.extract_words()
            ap_top = next((w["top"] for i, w in enumerate(ws) if w["text"] == "American" and i + 1 < len(ws) and ws[i + 1]["text"] == "Pima" and w["x0"] > 150 and w["top"] > 150), pg.height)
            full = pg.crop((0, ap_top, pg.width, pg.height)).extract_text() or ""
            ap, _, tr = full.partition("Trading")
            subs = merge(split_subs(L), split_subs(R))
            subs["American Pima (AP)"] = clean(re.sub(r"^American Pima \(AP\)", "", ap.strip()))
            T = "Trading" + tr
        else:
            subs = merge(split_subs(L), split_subs(R))
        cur = {"key": rk, "region": REGIONS[rk], "subs": {}, "trades": trades(T)}
        for name, txt in subs.items():
            crop, demand, market = classify(txt)
            cur["subs"][name or REGIONS[rk]] = {"text": txt, "crop": crop, "crop_key": key_crop(crop), "demand": demand, "market": market,
                                                "trading": level(txt, "Spot cotton trading") or level(txt, "Trading of spot cotton(?: and CCC-loan equities)?"), "demand_level": level(txt, r"(?<!Finished product )Demand"),
                                                "supplies": level(txt, r"Supplies(?: and producer offerings| of available cotton)?"),
                                                "foreign_inquiries": level(txt, "Foreign mill inquiries")}
        regions.append(cur)
    out["regions"] = regions
    # demand summary
    dom, exp = [], []
    for r in regions:
        for sub, d in r["subs"].items():
            for s in d["demand"] + [x for x in d["market"] if "inquir" in x]:
                if re.search(r"Domestic mill|Finished product|yarn", s, re.I):
                    dom.append(s)
                elif re.search(r"export|mills in|mill buyers inquired|Inquiries were best|Interest was best|Representatives for mills|Agents for mills|Foreign mill", s, re.I):
                    c = countries(s)
                    q = re.search(r"colou?r ([^;]+?)(?: for| shipment|\.)", s)
                    sh = re.search(r"for ([A-Z][a-z]+(?:/[A-Z][a-z]+)?(?: \d{4})?(?: through [A-Z][a-z]+ \d{4})?) (?:shipment|delivery)", s)
                    exp.append({"region": r["region"], "sub": sub, "text": s, "countries": c, "quality": q.group(1).strip() if q else None, "when": sh.group(1) if sh else None})
    out["domestic_mill"] = list(dict.fromkeys(x for x in dom if len(x) > 25 and not x.endswith(" y.")))
    exp = [e for e in exp if e["countries"]]
    out["export_inquiries"] = exp
    ex_lvl = next((level(" ".join(r["subs"][s]["text"] for s in r["subs"]), "Demand through export channels") for r in regions if r["key"] == "Southeastern"), None)
    out["export_demand_level"] = ex_lvl
    return out


STATES = ["Alabama", "Georgia", "Virginia", "the Carolinas", "North Carolina", "South Carolina", "Florida", "Arkansas", "Missouri", "Tennessee", "Louisiana",
          "Mississippi", "Texas", "Oklahoma", "Kansas", "Arizona", "California", "New Mexico"]


def harvest_pct(d):
    """State harvest percentages quoted from NASS in the regional notes."""
    out = {}
    for r in d["regions"]:
        for s in r["subs"].values():
            for x in s["crop"]:
                if not re.search(r"harvest", x, re.I):
                    continue
                for num, st in re.findall(r"(\d{1,3})(?: percent)?(?: complete(?:d)?)? in (" + "|".join(STATES) + r")\b", x):
                    out[st.replace("the ", "")] = int(num)
    return out


def headline(d, prev=None):
    h = []
    hp = harvest_pct(d)
    if hp:
        h.append("Harvest (NASS, as quoted): " + ", ".join(f"{k} {v}%" for k, v in hp.items()) + ".")
    risk = []
    for r in d["regions"]:
        for sub, s in r["subs"].items():
            hits = [x for x in s["crop"] if re.search(r"declin|damage|concern|regrowth|abandon|insurance|not to open|loss|delay", x, re.I)]
            if hits:
                tags = []
                for pat, lab in ((r"production estimates continued to decline|declin", "production estimates falling"), (r"quality", "fiber quality concerns"),
                                 (r"regrowth", "regrowth"), (r"insurance|adjuster", "insurance adjusters in fields"), (r"damage", "storm damage being assessed"),
                                 (r"not to open|decided not", "some gins not opening"), (r"delay|interrupt", "harvest delays")):
                    if any(re.search(pat, x, re.I) for x in hits) and lab not in tags:
                        tags.append(lab)
                risk.append(f"{sub} ({', '.join(tags)})")
    if risk:
        h.append("Watch: " + "; ".join(risk) + ".")
    p = d.get("prices") or {}
    if p.get("spot_7mkt_avg"):
        bas = round((p["spot_7mkt_avg"] - p["dec_settle"]) * 100) if p.get("dec_settle") else None
        a = (d.get("futures") or [{}])[-1].get("a_index")
        h.append(f"Spot 41-4-34 7-market average {p['spot_7mkt_avg']:.2f}¢ ({'+' if (p.get('chg_week_pts') or 0) >= 0 else ''}{p.get('chg_week_pts', 0):.0f} pts on the week; {p.get('year_ago')}¢ a year ago)"
                 + (f", {bas:+d} pts vs Dec futures" if bas is not None else "") + (f"; A Index {a:.2f}¢" if a else "") + (f"; AWP {d['awp']:.2f}¢" if d.get("awp") else "") + ".")
    lv = [f"export {d['export_demand_level']}" if d.get("export_demand_level") else None]
    dm = next((x for x in (d.get("domestic_mill") or []) if "Finished product demand" in x), None)
    if dm:
        lv.append("finished-product (yarn/fabric) demand " + re.sub(r".*was ", "", dm).rstrip("."))
    cs = []
    for e in d.get("export_inquiries") or []:
        cs += [c for c in e["countries"] if c not in cs]
    if cs:
        lv.append("export inquiries from " + ", ".join(cs))
    if any(lv):
        h.append("Demand: " + "; ".join(x for x in lv if x) + ".")
    if prev:
        pp = prev.get("prices") or {}
        if pp.get("spot_7mkt_avg") and p.get("spot_7mkt_avg"):
            h.append(f"Versus the previous report ({prev['date']}): spot {p['spot_7mkt_avg'] - pp['spot_7mkt_avg']:+.2f}¢"
                     + (f"; export demand was {prev['export_demand_level']}" if prev.get("export_demand_level") and prev.get("export_demand_level") != d.get("export_demand_level") else "") + ".")
    return h


def brief(d, prev=None):
    """Two short lists: crop progress by region and mill demand."""
    crop, mill = [], []
    for r in d["regions"]:
        for sub, s in r["subs"].items():
            if sub == "Textile Mill":
                continue
            lines = s["crop_key"]
            if lines:
                crop.append({"area": sub if sub not in REGIONS.values() else r["region"], "t": " ".join(lines)})
    dom = d.get("domestic_mill") or []
    if dom:
        mill.append({"area": "US mills", "t": " ".join(dom[:3])})
    by_c = {}
    for e in d.get("export_inquiries") or []:
        for c in e["countries"]:
            by_c.setdefault(c, []).append(e)
    if d.get("export_demand_level"):
        mill.append({"area": "Export demand", "t": f"Demand through export channels was {d['export_demand_level']}."})
    if by_c:
        mill.append({"area": "Export inquiries", "t": "; ".join(
            f"{c}" + (f" ({', '.join(sorted({x['quality'] for x in v if x['quality']}))[:60]}" + (f", {v[0]['when']}" if v[0]['when'] else "") + ")" if any(x['quality'] for x in v) else "")
            for c, v in sorted(by_c.items(), key=lambda kv: -len(kv[1]))) + "."})
    act = []
    for r in d["regions"]:
        for sub, s in r["subs"].items():
            if s.get("trading") or s.get("demand_level"):
                act.append(f"{sub if sub not in REGIONS.values() else r['region'].split(' (')[0]}: trading {s.get('trading') or '–'}, demand {s.get('demand_level') or '–'}")
    if act:
        mill.append({"area": "Spot market", "t": "; ".join(act) + "."})
    if prev:
        p, n = (prev.get("prices") or {}), (d.get("prices") or {})
        if p.get("spot_7mkt_avg") and n.get("spot_7mkt_avg"):
            pass
    return {"headline": headline(d, prev), "crop": crop, "mill": mill}


ARCHIVE = "https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=3024&page={}"


def backfill(pages=1):
    """Past issues from the AMS file repository (50 per page, newest first); issues that fail to parse are skipped."""
    import requests
    H = {"User-Agent": "Mozilla/5.0 (research; bmr-com)"}
    done = {p.stem for p in OUT.glob("20*.json")}
    for pg in range(pages):
        h = None
        for attempt in range(4):
            try:
                h = requests.get(ARCHIVE.format(pg), headers=H, timeout=(30, 300)).text; break
            except Exception as e:
                print("archive page retry", pg, attempt, repr(e)[:100]); __import__("time").sleep(20)
        if h is None:
            continue
        print("archive page", pg, "links", len(re.findall(r'href="([^"]+\.pdf)"', h)))
        for link in re.findall(r'href="([^"]+\.pdf)"', h):
            m = re.search(r"/(\d{4}-\d{2}-\d{2})/", link)
            if not m or m.group(1) in done:
                continue
            try:
                raw = requests.get("https://mymarketnews.ams.usda.gov/" + link.lstrip("/"), headers=H, timeout=(30, 180)).content
                d = parse(raw)
                if not d.get("date") or not d.get("regions"):
                    print("skip (layout)", m.group(1)); continue
                (OUT / f"{d['date']}.json").write_text(json.dumps(d, indent=1)); done.add(d["date"]); print("backfilled", d["date"])
            except Exception as e:
                print("skip", m.group(1), repr(e)[:80])
    # briefs need the previous issue, so build them in date order
    files = sorted(OUT.glob("20*.json"))
    for i, f in enumerate(files):
        try:
            d = json.loads(f.read_text())
            d["brief"] = brief(d, json.loads(files[i - 1].read_text()) if i else None)
            f.write_text(json.dumps(d, indent=1))
        except Exception as e:
            print("brief failed", f.stem, repr(e)[:120])
    write_latest()


def write_latest():
    files = sorted(OUT.glob("20*.json"))
    if not files:
        return
    d = json.loads(files[-1].read_text())
    series = []
    for f in files:
        x = json.loads(f.read_text()); p = x.get("prices") or {}; fu = (x.get("futures") or [{}])[-1]
        series.append({"date": x["date"], "spot": p.get("spot_7mkt_avg"), "dec": p.get("dec_settle"), "a_index": fu.get("a_index"), "awp": x.get("awp"),
                       "export_demand": x.get("export_demand_level"), "countries": sorted({c for e in x.get("export_inquiries") or [] for c in e["countries"]})})
    (OUT / "latest.json").write_text(json.dumps({**d, "history": [f.stem for f in files], "series": series}))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--backfill":
        backfill(int(sys.argv[2]) if len(sys.argv) > 2 else 1); return
    if len(sys.argv) > 1:
        raw = Path(sys.argv[1]).read_bytes()
    else:
        import requests
        r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0 (research; bmr-com)"}, timeout=120); r.raise_for_status(); raw = r.content
    d = parse(raw)
    if not d.get("date"):
        print("could not read the report date"); return
    f = OUT / f"{d['date']}.json"
    if f.exists() and len(sys.argv) == 1:
        print("already stored", d["date"]); return
    prev = sorted(p for p in OUT.glob("20*.json") if p.stem < d["date"])
    d["brief"] = brief(d, json.loads(prev[-1].read_text()) if prev else None)
    f.write_text(json.dumps(d, indent=1))
    write_latest()
    print("stored", d["date"])


if __name__ == "__main__":
    main()
