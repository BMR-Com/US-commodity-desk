"""Metals desk raw data (runs in GitHub Actions; no keys). Each source is independent: a failure in one is reported and
the others still run. Old data is kept; only new data is fetched where the source allows it.

Usage: python pipelines/metals.py [step ...]      steps: etf etf_more lme wgc icsg iai usgs silver rates comex wpic jm pgm_etf   (default: all)

  etf     iShares IAU and SLV tonnes in trust (product pages, daily snapshot appended) and their full daily NAV /
          shares-outstanding history (the product page's data-download
          file, Historical sheet)                    -> raw/etf_ishares.csv, raw/etf_ishares_hist.csv
          SPDR GLD: raw/etf_gld.csv keeps the daily history to 2026-11-20; api.spdrgoldshares.com (the only host serving it)
          disallows automated access in robots.txt, so it is no longer downloaded; GLD continues quarterly from SEC filings
  etf_more other sponsors' own sites: Sprott PHYS / PSLV / SPPP ounces (fund-page holdings charts since inception plus
          the daily figure the pages load), abrdn PPLT / PALL / SGOL / SIVR shares outstanding and metal per basket
          (daily snapshot from the fund page's data service), GraniteShares PLTM / BAR daily NAV, AUM and metal per
          basket since 2020 (fund page's NAV-history feed)   -> raw/etf_sprott.csv, raw/etf_abrdn.csv, raw/etf_granite.csv
  lme     LME copper and aluminium cash, 3-month and LME stocks (westmetall.com daily tables; current year each run,
          earlier years once)                                                      -> raw/lme_cu.csv, raw/lme_al.csv
  wgc     World Gold Council Gold Demand Trends (quarterly): headline tonnages from the public report summary on gold.org
          (the Goldhub data API is disallowed by robots.txt; full tables need a login)      -> raw/wgc_gdt.json
  icsg    ICSG monthly press release (PDF): world refined copper balance table and text -> raw/icsg/<release>.json
  iai     International Aluminium Institute monthly primary aluminium production by region (public statistics page)
                                                                                   -> raw/iai_primary.csv, raw/iai/snap_<month>.json
  usgs    USGS Mineral Commodity Summaries data release (annual): world mine production, reserves, US salient statistics
          for gold, silver, copper, aluminum, bauxite                              -> raw/usgs_mcs<year>.csv
  silver  Silver Institute supply-and-demand page (World Silver Survey key numbers) -> raw/silver_institute.json
  rates   US Treasury 10-year real yield (TIPS) and the US dollar index (Yahoo)   -> raw/real_yields.csv, raw/dxy.csv
  comex   COMEX warehouse stocks: parses CME's daily stock reports (Gold_Stocks.xls etc.) that the Mac collector or a
          manual upload drops in raw/comex_stocks/ (cmegroup.com blocks GitHub's servers); NYMEX platinum and palladium
          from the combined PA-PL report                                                  -> raw/comex_stocks.csv
  wpic    World Platinum Investment Council Platinum Quarterly: the free tables workbook (Table 1, platinum balance by year
          and quarter) and the key points on the public page; each release kept, revisions vs the previous release
                                                                                   -> raw/wpic/<Qn_YYYY>.json
  jm      Johnson Matthey PGM market report (annual, May): the free supply-and-demand history workbook, platinum and
          palladium; each edition kept, revisions vs the previous edition        -> raw/jm/<edition>.json
  pgm_etf ounces held and shares outstanding at each quarter end from the trusts' SEC filings (10-Q/10-K XBRL): abrdn
          PPLT, PALL, SGOL, SIVR; iShares IAU, SLV; GraniteShares PLTM, BAR; SPDR GLD. Anchors the ounces-per-share used to turn
          daily shares outstanding into daily ounces       -> raw/etf_sec.csv (all), raw/etf_pgm.csv (PPLT, PALL)
Writes data/metals/raw/fetch_log.json (last result per step).
"""
import datetime as dt, hashlib, html, io, json, re, sys, time, traceback
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "metals" / "raw"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
TODAY = dt.date.today()
LOG = {}
ETF_UA = {"User-Agent": "BMR-Com-research-desk/1.0 (ETF metal holdings research; GitHub Actions)"}
_ROBOTS = {}


def robots_allows(url):
    """Python's standard robots.txt check for the ETF sponsor sites (cached per host; unreachable robots.txt = allowed)."""
    import urllib.robotparser
    from urllib.parse import urlparse
    u = urlparse(url)
    base = f"{u.scheme}://{u.netloc}"
    if base not in _ROBOTS:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers=ETF_UA, timeout=30)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _ROBOTS[base] = rp
    ok = _ROBOTS[base].can_fetch(ETF_UA["User-Agent"], url)
    if not ok:
        print("   robots.txt disallows", url[:120])
    return ok


def eget(url, tries=3, method="GET", **kw):
    """Request to an ETF sponsor site: honest User-Agent, robots.txt respected."""
    if not robots_allows(url):
        return None
    for i in range(tries):
        try:
            r = requests.request(method, url, headers={**ETF_UA, **kw.pop("headers", {})}, timeout=90, **kw)
            if r.status_code == 200:
                return r
            print("  ", r.status_code, url[:120])
            if r.status_code in (401, 403, 404):
                return r
        except Exception as e:
            print("  err", str(e)[:120], url[:120])
        time.sleep(4 + 4 * i)
    return None


def get(url, tries=3, **kw):
    for i in range(tries):
        try:
            r = requests.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=90, **kw)
            if r.status_code == 200:
                return r
            print("  ", r.status_code, url[:120])
            if r.status_code in (401, 403, 404):
                return r
        except Exception as e:
            print("  err", str(e)[:120], url[:120])
        time.sleep(4 + 4 * i)
    return None


def robots_ok(base, path):
    """True unless the site's robots.txt disallows `path` for all agents."""
    r = get(base.rstrip("/") + "/robots.txt", tries=1)
    if r is None or r.status_code != 200:
        return True
    agent_all, dis = False, []
    for line in r.text.splitlines():
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            agent_all = v == "*"
        elif k == "disallow" and agent_all and v:
            dis.append(v)
    return not any(path.startswith(d.replace("*", "")) for d in dis if d != "/") and "/" not in dis


def merge_csv(p, new, keys):
    old = pd.read_csv(p, dtype=str) if p.exists() else pd.DataFrame()
    new = new.astype(str)
    out = pd.concat([old, new]).drop_duplicates(keys, keep="last").sort_values(keys)
    if len(out) < len(old):
        raise RuntimeError(f"refusing to shrink {p.name}")
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    return len(out) - len(old)


# ───────── ETF holdings ─────────
def etf():
    n = 0
    # SPDR GLD: the sponsor's history file and daily figures are served from api.spdrgoldshares.com, whose robots.txt
    # disallows all automated access (checked 2026-11-20), so the desk no longer downloads them. The history already
    # stored (Nov 2004 - Nov 2026) is kept; GLD continues from its quarterly SEC filings (pgm_etf step).
    if robots_allows("https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"):
        r = eget("https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en")
        if r is not None and r.status_code == 200 and r.content[:2] == b"PK":
            d = pd.read_excel(io.BytesIO(r.content), sheet_name="US GLD Historical Archive")
            d.columns = [str(c).strip() for c in d.columns]
            d["date"] = pd.to_datetime(d["Date"], format="%d-%b-%Y", errors="coerce")
            d["tonnes"] = pd.to_numeric(d["Tonnes of Gold"], errors="coerce")
            d["ounces"] = pd.to_numeric(d["Total Ounces of Gold in the Trust"], errors="coerce")
            d = d.dropna(subset=["date", "tonnes"])
            d = d[d.tonnes > 0]
            out = pd.DataFrame({"date": d.date.dt.strftime("%Y-%m-%d"), "tonnes": d.tonnes.round(2), "ounces": d.ounces.round(0)})
            n += merge_csv(RAW / "etf_gld.csv", out, ["date"])
            print("GLD", len(out), "days, last", out.date.iloc[-1], out.tonnes.iloc[-1])
    else:
        print("GLD: sponsor data host closed to automated access by robots.txt; stored history kept, quarterly SEC figures continue it")
    rows, hist = [], []
    for fund, pid, url in [("IAU", 239561, "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund"),
                           ("SLV", 239855, "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund")]:
        r = eget(url)
        if r is None or r.status_code != 200:
            print(fund, "page not available"); continue
        t = html.unescape(r.text)
        def fv(name):
            m = re.search(r'"name":"%s"' % name, t)
            seg = t[max(0, m.start() - 600):m.start() + 50] if m else ""
            vs = re.findall(r'"formattedValue":"([\d,\.]+)"', seg)
            ds = re.findall(r'"formattedAsOfDate":"([A-Za-z]{3} \d{1,2}, \d{4})"', seg)
            return (float(vs[-1].replace(",", "")) if vs else None), (ds[-1] if ds else None)
        tonnes, asof = fv("tonnes")
        ounces, _ = fv("ounces")
        if tonnes and asof:
            rows.append({"fund": fund, "date": pd.to_datetime(asof).strftime("%Y-%m-%d"), "tonnes": tonnes, "ounces": ounces})
            print(fund, asof, tonnes, "t")
        # the page's "Download" button: SpreadsheetML workbook whose Historical sheet has daily NAV and shares outstanding
        m = re.search(r'href="([^"]*get-fund-document\?[^"]*portfolioId=%d[^"]*component=fundDownload[^"]*)"' % pid, r.text)
        dl = html.unescape(m.group(1)) if m else ("https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE"
                                                   f"&appSubType=ISHARES&targetSite=us-ishares&locale=en_US&portfolioId={pid}&component=fundDownload&userType=individual")
        time.sleep(2)
        x = eget(dl)
        if x is not None and x.status_code == 200 and b"Historical" in x.content[:400000]:
            xt = x.content.decode("utf-8", "replace")
            sh = re.search(r'ss:Name="Historical"(.*?)</ss:Worksheet>', xt, re.S)
            cells = [re.findall(r"<ss:Data[^>]*>([^<]*)</ss:Data>", row) for row in re.findall(r"<ss:Row>(.*?)</ss:Row>", sh.group(1) if sh else "", re.S)]
            if cells and cells[0][:1] == ["As Of"]:
                hd = cells[0]
                iN, iS = hd.index("NAV per Share"), hd.index("Shares Outstanding")
                n0 = len(hist)
                for c in cells[1:]:
                    try:
                        hist.append({"fund": fund, "date": pd.to_datetime(c[0], format="%b %d, %Y").strftime("%Y-%m-%d"), "nav": float(c[iN]), "shares": float(c[iS])})
                    except Exception:
                        pass
                print(fund, "history", len(hist) - n0, "days")
            else:
                print(fund, "download has no Historical sheet")
        else:
            print(fund, "download not available")
        time.sleep(2)
    if rows:
        n += merge_csv(RAW / "etf_ishares.csv", pd.DataFrame(rows), ["fund", "date"])
    if hist:
        n += merge_csv(RAW / "etf_ishares_hist.csv", pd.DataFrame(hist), ["fund", "date"])
    if not rows and not hist:
        raise RuntimeError("no iShares data")
    return n


# ───────── LME prices and stocks (westmetall.com) ─────────
WM = {"cu": "LME_Cu_cash", "al": "LME_Al_cash"}


def wm_table(field, year=None):
    u = f"https://www.westmetall.com/en/markdaten.php?action=table&field={field}" + (f"&year={year}" if year else "")
    r = get(u)
    if r is None or r.status_code != 200:
        return None
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        c = [html.unescape(re.sub("<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
        if len(c) >= 4 and re.match(r"\d{1,2}\. \w+ \d{4}", c[0]):
            num = lambda s: float(s.replace(",", "")) if re.match(r"^[\d,\.]+$", s) else None
            rows.append({"date": pd.to_datetime(c[0].replace(".", ""), format="%d %B %Y").strftime("%Y-%m-%d"), "cash": num(c[1]), "m3": num(c[2]), "stock": num(c[3])})
    return pd.DataFrame(rows)


def lme():
    if not robots_ok("https://www.westmetall.com", "/en/markdaten.php"):
        raise RuntimeError("westmetall robots.txt disallows the market-data pages")
    n = 0
    for m, field in WM.items():
        p = RAW / f"lme_{m}.csv"
        have = set(pd.read_csv(p).date.str[:4]) if p.exists() else set()
        years = [None] + [y for y in range(2012, TODAY.year) if str(y) not in have][:6]   # backfill a few years per run
        for y in years:
            d = wm_table(field, y)
            time.sleep(2)
            if d is None or not len(d):
                print("LME", m, y, "no rows"); continue
            if y is not None and not d.date.str.startswith(str(y)).any():
                print("LME", m, y, "year table not offered"); break
            n += merge_csv(p, d, ["date"])
            print("LME", m, y or "current", len(d), "rows, last", d.date.max())
    return n


# ───────── World Gold Council Gold Demand Trends (quarterly) ─────────
# The Goldhub data API (fsv3.gold.org) is disallowed by its robots.txt and the full tables need a login, so the desk reads
# the public summary of each Gold Demand Trends report on www.gold.org (allowed) and parses the headline tonnages.
GDT_LINES = [("total", r"(total )?gold demand"), ("central_banks", r"central banks?"), ("etfs", r"\bETFs?\b"), ("bar_coin", r"bar and coin"),
             ("jewellery", r"jewel(le)?ry"), ("technology", r"technology"), ("mine", r"mine production"), ("recycling", r"recycl"), ("supply", r"total supply")]


def gdt_parse(desc):
    out = {}
    for clause in re.split(r"(?<=[.;])\s+|,\s+(?:while|and|lifting)\s+|\s+By contrast,\s+", desc):
        for key, rx in GDT_LINES:
            if key in out or not re.search(rx, clause, re.I):
                continue
            t = re.search(r"([\d,]+(?:\.\d+)?)\s?t\b", clause)
            if not t:
                continue
            v = float(t.group(1).replace(",", ""))
            pc = re.search(r"(up|down|rose|fell|lower|higher|increased|declined|grew|dropped|gained|increase|decrease)\D{0,20}?(\d+(?:\.\d+)?)%|(\d+(?:\.\d+)?)%\s+(lower|higher|up|down)", clause, re.I)
            yoy = None
            if pc:
                word = (pc.group(1) or pc.group(4) or "").lower()
                yoy = float(pc.group(2) or pc.group(3)) * (-1 if word in ("down", "fell", "lower", "declined", "dropped", "decrease") else 1)
            elif re.search(r"unchanged|flat", clause, re.I):
                yoy = 0.0
            if key == "etfs" and re.search(r"outflow", clause, re.I):
                v = -v
            out[key] = {"t": v, "yoy_pct": yoy}
            break
    return out


def wgc():
    if not robots_ok("https://www.gold.org", "/goldhub/research/gold-demand-trends"):
        raise RuntimeError("gold.org robots.txt disallows the Gold Demand Trends pages")
    r = get("https://www.gold.org/goldhub/research/gold-demand-trends")
    if r is None or r.status_code != 200:
        raise RuntimeError("WGC Gold Demand Trends page not available")
    slugs = sorted(set(re.findall(r'href="/goldhub/research/gold-demand-trends/(gold-demand-trends-q([1-4])-(\d{4}))"', r.text)), key=lambda x: (x[2], x[1]))
    p = RAW / "wgc_gdt.json"
    have = json.loads(p.read_text()) if p.exists() else {}
    n = 0
    for k, v in have.items():          # re-read stored summaries with the current parser (no refetch)
        if v.get("summary"):
            v["values"] = gdt_parse(v["summary"])
    for slug, q, y in slugs[-6:]:
        key = f"{y}-Q{q}"
        if key in have and have[key].get("values"):
            continue
        time.sleep(3)
        pg = get(f"https://www.gold.org/goldhub/research/gold-demand-trends/{slug}")
        if pg is None or pg.status_code != 200:
            continue
        m = re.findall(r'"description":"([^"]{80,})"', pg.text)
        desc = html.unescape(m[0].replace("\\/", "/")) if m else None
        if not desc:
            print("WGC", key, "no summary found"); continue
        vals = gdt_parse(desc)
        pub = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', pg.text)
        have[key] = {"quarter": key, "published": pub.group(1) if pub else str(TODAY), "summary": desc, "values": vals,
                     "url": f"https://www.gold.org/goldhub/research/gold-demand-trends/{slug}", "fetched": str(TODAY)}
        n += 1
        print("WGC", key, {k: v["t"] for k, v in vals.items()})
    if not have:
        raise RuntimeError("no WGC quarter parsed")
    p.write_text(json.dumps(dict(sorted(have.items())), indent=1))
    return n


# ───────── ICSG monthly press release ─────────
ICSG_ROWS = [("mine", r"World Copper Mine Production"), ("mine_util", r"Mine Capacity Utilization"),
             ("refined_primary", r"Primary Refined Copper Production"), ("refined_secondary", r"Secondary Refined Copper Production"),
             ("refined", r"\(Primary & Secondary\)"), ("refinery_util", r"Refinery Capacity Utilization"), ("usage", r"World Refined Copper Usage"),
             ("stocks", r"^End of Period"), ("stock_change", r"Period Stock Change"), ("balance", r"^Refined Copper Balance"),
             ("balance_sa", r"Seasonally Adjusted Refined Balance"), ("balance_bonded", r"stock change 4/")]


def icsg_parse(text):
    out = {"issued": None, "data_month": None, "table": {}, "points": []}
    m = re.search(r"Date Issued:\s*(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)\s+(\d{4})", text)
    if m:
        out["issued"] = pd.to_datetime(f"{m.group(1)} {m.group(2)} {m.group(3)}").strftime("%Y-%m-%d")
    m = re.search(r"Preliminary Data for (\w+ \d{4})", text)
    if m:
        out["data_month"] = pd.to_datetime(m.group(1)).strftime("%Y-%m")
    lines = [l.strip() for l in text.splitlines()]
    hdr_i = next((i for i, l in enumerate(lines) if re.match(r"^(\d{4}\s+){5,}\d{4}$", l)), None)
    if hdr_i is not None:
        years = lines[hdr_i].split()
        sub = lines[hdr_i + 1].split() if hdr_i + 1 < len(lines) else []
        cols = years[:4] + [f"{years[4]} {sub[0]}" if sub else years[4], f"{years[5]} {sub[0]}" if sub else years[5]] + [f"{y} {s}" for y, s in zip(years[6:], sub[1:])]
        out["columns"] = cols
        prev = ""
        for l in lines[hdr_i + 2:]:
            nums = re.findall(r"-?[\d,]+\.?\d*", l)
            lab = re.sub(r"\s*-?[\d,]+\.?\d*(\s+-?[\d,]+\.?\d*)*\s*$", "", l).strip()
            for key, rx in ICSG_ROWS:
                if re.search(rx, l) or (len(nums) >= 6 and not re.search(r"\d", prev) and re.search(rx, prev + " " + l)):
                    vals = [float(x.replace(",", "")) for x in nums if not re.fullmatch(r"[1-4]/?", x)]
                    vals = [v for v in vals][-len(cols):] if len(vals) >= 6 else vals
                    if key not in out["table"] and len(vals) >= 4:
                        off = len(cols) - len(vals)
                        out["table"][key] = {c: v for c, v in zip(cols[off:], vals)}
            prev = l
    for s in re.split(r"(?<=\.)\s+(?=[A-Z])", re.sub(r"\s+", " ", text)):
        if re.search(r"world (copper mine production|refined copper production|apparent refined copper usage|refined copper balance)|bonded stocks|exchanges \(LME", s, re.I) and len(s) < 400:
            out["points"].append(s.strip().lstrip("• "))
    out["points"] = out["points"][:8]
    return out


def icsg():
    if not robots_ok("https://icsg.org", "/press-releases/"):
        raise RuntimeError("icsg.org robots.txt disallows press releases")
    r = get("https://icsg.org/press-releases/")
    if r is None or r.status_code != 200:
        raise RuntimeError("ICSG press page not available")
    links = [u.replace("&#038;", "&") for u in re.findall(r'data-downloadurl="(https://icsg.org/download/[^"]*monthly-press-release[^"]*)"', r.text)]
    d = RAW / "icsg"
    d.mkdir(parents=True, exist_ok=True)
    idx_p = d / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {}
    n = 0
    from pypdf import PdfReader
    for u in links[:3]:
        slug = re.search(r"/download/([^/]+)/", u).group(1)
        if slug in idx:
            continue
        time.sleep(21)                                   # robots.txt crawl-delay 20
        p = get(u)
        if p is None or p.status_code != 200 or p.content[:4] != b"%PDF":
            print("ICSG", slug, "download failed"); continue
        text = "\n".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(p.content)).pages)
        rec = icsg_parse(text)
        rec.update(slug=slug, url=u.split("?")[0], text=text[:12000])
        key = rec["issued"] or slug
        (d / f"{key}.json").write_text(json.dumps(rec, indent=0))
        idx[slug] = key
        n += 1
        print("ICSG", key, rec["data_month"], "rows", list(rec["table"]))
    idx_p.write_text(json.dumps(idx, indent=0))
    return n


# ───────── IAI primary aluminium production ─────────
IAI_PAGE = "https://international-aluminium.org/statistics/primary-aluminium-production/"
IAI_API = "https://alvis.international-aluminium.org/api/publication/?publication=primary-aluminium-production"


def iai_json():
    """The statistics page loads its data from the IAI's own public API with a token embedded in the page; read it the
    same way the page does (token taken from the page each run), falling back to a headless browser."""
    page = get(IAI_PAGE)
    tok = re.search(r'ALVIS_API_TOKEN\s*=\s*"([^"]+)"', page.text).group(1) if page is not None and page.status_code == 200 and "ALVIS_API_TOKEN" in page.text else None
    hdrs = [{}]
    if tok:
        hdrs = [{"Authorization": f"Bearer {tok}"}, {"X-Api-Token": tok}, {"Api-Token": tok}, {"token": tok}, {}]
    for h in hdrs:
        r = get(IAI_API, tries=1, headers={**h, "Accept": "application/json", "Origin": "https://international-aluminium.org", "Referer": IAI_PAGE})
        if r is not None and r.status_code == 200 and r.text.startswith("{"):
            return r.json()
    try:
        from playwright.sync_api import sync_playwright
        got = {}
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(user_agent=UA["User-Agent"])
            pg.on("response", lambda resp: got.setdefault("j", resp) if "alvis.international-aluminium.org/api/publication" in resp.url and resp.status == 200 else None)
            pg.goto(IAI_PAGE, wait_until="networkidle", timeout=120000)
            pg.wait_for_timeout(4000)
            j = got["j"].json() if "j" in got else None
            b.close()
        return j
    except Exception as e:
        print("IAI browser fallback failed:", str(e)[:200])
        return None


def iai():
    if not robots_ok("https://international-aluminium.org", "/statistics/"):
        raise RuntimeError("IAI robots.txt disallows statistics")
    j = iai_json()
    if not j:
        raise RuntimeError("IAI data not available")
    c = j["data"]["publication"]["charts"]
    names = {str(x["id"]): x["name"] for x in c["columns"]}
    names.update({"11": "World", "12": "Daily average"})
    rows = []
    for rec in c["data"]:
        m = rec["period"]["from"][:7]
        vals = (rec.get("data") or {}).get(str(c["rows"][0]["id"])) or {}
        rows.append({"month": m, **{names.get(k, k): (v or {}).get("value") for k, v in vals.items()}})
    df = pd.DataFrame(rows).sort_values("month")
    p = RAW / "iai_primary.csv"
    old = pd.read_csv(p) if p.exists() else None
    last = df.month.iloc[-1]
    snap = RAW / "iai" / f"snap_{last}.json"
    snap.parent.mkdir(parents=True, exist_ok=True)
    new_month = old is None or last > old.month.iloc[-1]
    if new_month or not snap.exists():   # keep what the release said about the last 13 months, for revisions
        snap.write_text(df.tail(13).to_json(orient="records"))
    df.to_csv(p, index=False)
    print("IAI", len(df), "months, last", last, "world", df.World.iloc[-1], "kt")
    return int(new_month)


# ───────── USGS Mineral Commodity Summaries (annual) ─────────
def usgs():
    n = 0
    for y in (TODAY.year, TODAY.year - 1):
        p = RAW / f"usgs_mcs{y}.csv"
        if p.exists():
            continue
        r = get(f"https://www.sciencebase.gov/catalog/items?q=%22Mineral%20Commodity%20Summaries%20{y}%20Data%20Release%22&format=json&max=5&fields=title,files")
        if r is None or r.status_code != 200:
            continue
        item = next((i for i in r.json().get("items", []) if i.get("title", "").strip().lower() == f"mineral commodity summaries {y} data release"), None)
        if not item:
            print("USGS", y, "data release not found"); continue
        it = get(f"https://www.sciencebase.gov/catalog/item/{item['id']}?format=json").json()
        f = next((f for f in it.get("files", []) if re.search(r"Commodities_Data\.csv$", f["name"])), None)
        if not f:
            print("USGS", y, "no commodities CSV"); continue
        c = get(f["url"])
        d = pd.read_csv(io.BytesIO(c.content), encoding="latin1", dtype=str)
        d = d[d.Commodity.isin(["Gold", "Silver", "Copper", "Aluminum", "Bauxite", "Alumina", "Platinum", "Palladium"])]
        d["Section"] = d.Section.str.replace("�", " ", regex=False).str.replace("\x97", " ", regex=False)
        d[["Section", "Commodity", "Country", "Statistics", "Statistics_detail", "Unit", "Year", "Value"]].to_csv(p, index=False)
        print("USGS", y, len(d), "rows")
        n += 1
    return n


# ───────── Silver Institute (World Silver Survey key numbers) ─────────
def silver():
    if not robots_ok("https://silverinstitute.org", "/silver-supply-demand/"):
        raise RuntimeError("silverinstitute.org robots.txt disallows the page")
    r = get("https://silverinstitute.org/silver-supply-demand/")
    if r is None or r.status_code != 200:
        raise RuntimeError("Silver Institute page not available")
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", r.text, flags=re.S)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
    survey = re.findall(r"World Silver Survey (\d{4})", txt)
    pts = []
    for s in re.split(r"(?<=[.])\s+(?=[A-Z])", txt):
        if re.search(r"\d", s) and re.search(r"\b(Moz|Boz|billion ounces|million ounces|percent|%)", s) and 40 < len(s) < 420:
            pts.append(s.strip())
    rec = {"fetched": str(TODAY), "survey": f"World Silver Survey {max(survey)}" if survey else None, "points": list(dict.fromkeys(pts))[:14],
           "url": "https://silverinstitute.org/silver-supply-demand/"}
    p = RAW / "silver_institute.json"
    old = json.loads(p.read_text()) if p.exists() else {}
    if old.get("points") == rec["points"]:
        print("Silver Institute unchanged", rec["survey"]); return 0
    hist = old.get("history", [])
    if old.get("points"):
        hist = (hist + [{k: old[k] for k in ("fetched", "survey", "points")}])[-6:]
    rec["history"] = hist
    p.write_text(json.dumps(rec, indent=0))
    print("Silver Institute", rec["survey"], len(rec["points"]), "points")
    return 1


# ───────── real yields and the dollar ─────────
def rates():
    p = RAW / "real_yields.csv"
    have = set(pd.read_csv(p).date.str[:4]) if p.exists() else set()
    n = 0
    for y in [y for y in range(2015, TODAY.year) if str(y) not in have] + [TODAY.year]:
        r = get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        if r is None or r.status_code != 200 or "Date" not in r.text[:50]:
            continue
        d = pd.read_csv(io.StringIO(r.text))
        d["date"] = pd.to_datetime(d.Date).dt.strftime("%Y-%m-%d")
        out = d[["date"] + [c for c in ("5 YR", "10 YR", "30 YR") if c in d]].rename(columns={"5 YR": "r5", "10 YR": "r10", "30 YR": "r30"})
        n += merge_csv(p, out, ["date"])
        time.sleep(1)
    r = get("https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=10y&interval=1d")
    if r is not None and r.status_code == 200:
        j = r.json()["chart"]["result"][0]
        d = pd.DataFrame({"date": pd.to_datetime(j["timestamp"], unit="s").strftime("%Y-%m-%d"), "dxy": j["indicators"]["quote"][0]["close"]}).dropna()
        n += merge_csv(RAW / "dxy.csv", d.assign(dxy=d.dxy.round(3)), ["date"])
    print("rates/dxy rows added", n)
    return n


# ───────── COMEX warehouse stocks (files dropped by the Mac collector or uploaded) ─────────
COMEX_FILES = {"Gold_Stocks": "gold", "Silver_stocks": "silver", "Copper_Stocks": "copper", "Aluminum_Stocks": "aluminum", "PA-PL_Stck_Rprt": "pgm"}


def pgm_stock_parse(path):
    """NYMEX platinum and palladium share one CME report: split it at each metal's heading and read its totals."""
    x = pd.read_excel(path, header=None, engine="xlrd" if path.suffix == ".xls" else None)
    cells = x.astype(str).values
    flat = " ".join(" ".join(r) for r in cells)
    m = re.search(r"Activity Date:?\s*(\d{1,2}/\d{1,2}/\d{4})", flat) or re.search(r"Report Date:?\s*(\d{1,2}/\d{1,2}/\d{4})", flat)
    date = pd.to_datetime(m.group(1)).strftime("%Y-%m-%d") if m else None
    out, cur = {}, None
    for r in cells:
        lab = " ".join(v for v in r if v != "nan").upper()
        if re.fullmatch(r"\s*(PLATINUM|PALLADIUM)\b.*", lab) and not re.search(r"\d", lab):
            cur = "platinum" if "PLATINUM" in lab else "palladium"
            out.setdefault(cur, {"date": date, "metal": cur})
            continue
        if not cur:
            continue
        nums = [float(v.replace(",", "")) for v in r if re.fullmatch(r"-?[\d,]+\.?\d*", v.replace("nan", "x"))]
        for key, rx in (("registered", r"TOTAL REGISTERED"), ("eligible", r"TOTAL ELIGIBLE"), ("total", r"COMBINED TOTAL|GRAND TOTAL")):
            if re.search(rx, lab) and nums and key not in out[cur]:
                out[cur][key] = nums[-1]
    return [v for v in out.values() if date and "total" in v]


def comex_parse(path, metal):
    x = pd.read_excel(path, header=None, engine="xlrd" if path.suffix == ".xls" else None)
    cells = x.astype(str).values
    flat = " ".join(" ".join(r) for r in cells)
    m = re.search(r"Activity Date:?\s*(\d{1,2}/\d{1,2}/\d{4})", flat) or re.search(r"Report Date:?\s*(\d{1,2}/\d{1,2}/\d{4})", flat)
    date = pd.to_datetime(m.group(1)).strftime("%Y-%m-%d") if m else None
    out = {"date": date, "metal": metal}
    for r in cells:
        lab = " ".join(r).upper()
        nums = [float(v.replace(",", "")) for v in r if re.fullmatch(r"-?[\d,]+\.?\d*", v.replace("nan", "x"))]
        for key, rx in (("registered", r"TOTAL REGISTERED"), ("eligible", r"TOTAL ELIGIBLE"), ("total", r"COMBINED TOTAL|GRAND TOTAL")):
            if re.search(rx, lab) and nums and key not in out:
                out[key] = nums[-1]          # last column = stocks at the end of the day ("TOTAL TODAY")
    return out if date and "total" in out else None


def comex():
    d = RAW / "comex_stocks"
    files = sorted(d.glob("*.xls*")) if d.exists() else []
    rows = []
    for f in files:
        metal = next((v for k, v in COMEX_FILES.items() if f.name.lower().startswith(k.lower())), None)
        if not metal:
            continue
        try:
            if metal == "pgm":
                got = pgm_stock_parse(f)
                rows += got
                if not got:
                    print("COMEX", f.name, "not parsed")
                continue
            r = comex_parse(f, metal)
            if r:
                rows.append(r)
            else:
                print("COMEX", f.name, "not parsed")
        except Exception as e:
            print("COMEX", f.name, "failed:", str(e)[:120])
    if not rows:
        print("COMEX stocks: no files yet (collected by the Mac collector; cmegroup.com blocks GitHub)")
        return 0
    n = merge_csv(RAW / "comex_stocks.csv", pd.DataFrame(rows), ["date", "metal"])
    for f in files:   # the parsed CSV keeps the history; raw files older than two weeks are removed to keep the repo small
        if (time.time() - f.stat().st_mtime) > 14 * 86400 or re.search(r"_(\d{8})\.xls", f.name) and f.name[-12:-4] < (TODAY - dt.timedelta(days=14)).strftime("%Y%m%d"):
            f.unlink()
    print("COMEX stocks rows added", n)
    return n


# ───────── World Platinum Investment Council: Platinum Quarterly (free tables workbook + public key points) ─────────
WPIC = "https://platinuminvestment.com"
WPIC_PAGE = WPIC + "/supply-and-demand/platinum-quarterly"


def wpic_table1(content, q, y):
    """Table 1 of a Platinum Quarterly tables workbook: platinum balance (koz) by year and by quarter. Lines are keyed
    'Parent' or 'Parent: child' (e.g. 'Recycling: Autocatalyst', 'Investment: Change in ETF Holdings')."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    want = f"Q{q}'{str(y)[2:]}"
    names = [n for n in wb.sheetnames if re.fullmatch(r"Table 1\s*\(" + re.escape(want) + r"\)", n.strip())]
    if not names:
        raise RuntimeError(f"WPIC workbook has no Table 1 for {want}")
    rows = [list(r) for r in wb[names[0]].iter_rows(values_only=True)]
    hdr_i = next(i for i, r in enumerate(rows) if any(isinstance(c, str) and "Supply-demand Balance" in c for c in r))
    hdr = rows[hdr_i]
    lab_col = next(j for j, c in enumerate(hdr) if isinstance(c, str) and "Supply-demand Balance" in c)
    cols = {}
    for j, c in enumerate(hdr):
        s = str(c).strip() if c is not None else ""
        if re.fullmatch(r"\d{4}f?", s) or re.fullmatch(r"Q[1-4] \d{4}", s):
            cols[j] = s
    table, parent = {}, None
    for r in rows[hdr_i + 1:]:
        labs = [(j, str(c).strip()) for j, c in enumerate(r[:lab_col + 2]) if isinstance(c, str) and c.strip()]
        if not labs:
            continue
        j, lab = labs[0]
        if lab.startswith("Source") or lab.startswith("Notes") or re.match(r"^\d\.", lab):
            break
        if lab in ("SUPPLY", "DEMAND"):
            parent = None
            continue
        vals = {cols[k]: (float(v) if isinstance(v, (int, float)) else float(v.replace(",", "").rstrip("*")) if isinstance(v, str) and re.fullmatch(r"[\d,\.]+\*?", v) else None)
                for k, v in enumerate(r) if k in cols}
        if not any(v is not None for v in vals.values()):
            continue
        if j == lab_col:
            parent, key = lab, lab
        else:
            key = f"{parent}: {lab}" if parent else lab
        table[key] = {k: (round(v, 1) if v is not None else None) for k, v in vals.items()}
    annual = [c for c in cols.values() if re.fullmatch(r"\d{4}f?", c)]
    quarters = [c for c in cols.values() if c.startswith("Q")]
    keep = annual + quarters[-8:]
    return {"columns": annual, "quarters": quarters[-8:], "table": {k: {c: v.get(c) for c in keep} for k, v in table.items()}}


def wpic_points(page):
    """Key points WPIC lists on the public Platinum Quarterly page (the 'overview of key data' bullets)."""
    i = page.find("Overview of key data")
    seg = page[i:i + 20000] if i >= 0 else ""
    seg = seg[:seg.find("Disclaimer")] if "Disclaimer" in seg else seg
    pts = [html.unescape(re.sub(r"<[^>]+>", " ", x)) for x in re.findall(r"<li[^>]*>(.*?)</li>", seg, re.S)]
    pts = [re.sub(r"\s+", " ", x).strip() for x in pts if len(x.strip()) > 20]
    heads = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<(?:h\d|strong|b)[^>]*>(.*?)</(?:h\d|strong|b)>", seg, re.S)]
    return pts[:14], [h for h in heads if re.search(r"\d{4}", h)][:4]


def wpic():
    if not robots_ok(WPIC, "/supply-and-demand/platinum-quarterly") or not robots_ok(WPIC, "/files/"):
        raise RuntimeError("platinuminvestment.com robots.txt disallows the Platinum Quarterly pages")
    r = get(WPIC_PAGE)
    if r is None or r.status_code != 200:
        raise RuntimeError("WPIC Platinum Quarterly page not available")
    m = re.search(r'href="(/files/\d+/WPIC_PQ_tables_Q([1-4])_(\d{4})\.xlsx)"', r.text)
    if not m:
        raise RuntimeError("WPIC tables workbook link not found on the Platinum Quarterly page")
    link, q, y = m.group(1), int(m.group(2)), int(m.group(3))
    d = RAW / "wpic"
    d.mkdir(parents=True, exist_ok=True)
    key = f"Q{q}_{y}"
    pts, heads = wpic_points(r.text)
    nxt = re.search(r"next Platinum Quarterly will be published on (\d{1,2} \w+ \d{4})", re.sub(r"<[^>]+>", " ", r.text))
    meta_p = d / "meta.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    meta.update({"checked": str(TODAY), "latest": key, "next_release": pd.to_datetime(nxt.group(1)).strftime("%Y-%m-%d") if nxt else meta.get("next_release")})
    n = 0
    if not (d / f"{key}.json").exists():
        time.sleep(3)
        x = get(WPIC + link)
        if x is None or x.status_code != 200 or x.content[:2] != b"PK":
            raise RuntimeError("WPIC tables workbook download failed")
        rec = wpic_table1(x.content, q, y)
        pdf = re.search(r'href="(/files/\d+/WPIC_Platinum_Quarterly_Q%d_%d\.pdf)"' % (q, y), r.text)
        rec.update(release=f"Q{q} {y}", key=key, fetched=str(TODAY), points=pts, heads=heads, url=WPIC + link, report=WPIC + pdf.group(1) if pdf else WPIC_PAGE)
        (d / f"{key}.json").write_text(json.dumps(rec, indent=0))
        n += 1
        print("WPIC", key, len(rec["table"]), "lines", rec["columns"][-4:])
    else:                                    # refresh the key points if WPIC edits the page text
        rec = json.loads((d / f"{key}.json").read_text())
        if pts and pts != rec.get("points"):
            rec["points"], rec["heads"] = pts, heads
            (d / f"{key}.json").write_text(json.dumps(rec, indent=0))
    pq, py = (q - 1, y) if q > 1 else (4, y - 1)          # seed the previous release once, so revisions show from the start
    pkey = f"Q{pq}_{py}"
    if not (d / f"{pkey}.json").exists() and not meta.get(f"seed_failed_{pkey}"):
        a = get(WPIC_PAGE + "/archive")
        pm = re.search(r'/files/(\d+)/WPIC_Platinum_Quarterly_Q%d_%d\.pdf' % (pq, py), a.text) if a is not None and a.status_code == 200 else None
        ok = False
        if pm:
            time.sleep(3)
            x = get(f"{WPIC}/files/{pm.group(1)}/WPIC_PQ_tables_Q{pq}_{py}.xlsx", tries=1)
            if x is not None and x.status_code == 200 and x.content[:2] == b"PK":
                try:
                    prev = wpic_table1(x.content, pq, py)
                    prev.update(release=f"Q{pq} {py}", key=pkey, fetched=str(TODAY), points=[], url=f"{WPIC}/files/{pm.group(1)}/WPIC_PQ_tables_Q{pq}_{py}.xlsx", seeded=True)
                    (d / f"{pkey}.json").write_text(json.dumps(prev, indent=0))
                    ok = True
                    print("WPIC seeded previous release", pkey)
                except Exception as e:
                    print("WPIC previous release not parsed:", str(e)[:120])
        if not ok:
            meta[f"seed_failed_{pkey}"] = str(TODAY)
            print("WPIC previous release", pkey, "not available as a workbook; revisions start with the next release")
    meta_p.write_text(json.dumps(meta, indent=0))
    return n


# ───────── Johnson Matthey PGM market report (annual, May): free supply-and-demand history workbook ─────────
JM = "https://matthey.com"
JM_PAGE = JM + "/products-and-markets/pgms-and-circularity/pgm-market-data"


def jm_sheet(ws):
    """First block of a JM metal sheet (supply, recycling, demand by application, movements in stocks), '000 oz by year."""
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr_i = next(i for i, r in enumerate(rows) if r and isinstance(r[0], str) and r[0].strip().startswith("'000 oz"))
    years = {j: int(c) for j, c in enumerate(rows[hdr_i]) if isinstance(c, (int, float)) and 1970 < c < 2100}
    keep = sorted(years.items(), key=lambda x: x[1])[-10:]
    out, sec, parent = {}, None, None
    body = rows[hdr_i + 1:]
    for i, r in enumerate(body):
        if not r or not isinstance(r[0], str) or not r[0].strip():
            continue
        raw = r[0]
        lab = re.sub(r"\s*\(\d+\)|\*", "", raw).strip()
        vals = {str(y): (float(r[j]) if j < len(r) and isinstance(r[j], (int, float)) else None) for j, y in keep}
        if not any(v is not None for v in vals.values()):
            if out and lab.lower().startswith(("notes", "(1)")):
                break
            if raw.startswith(" "):          # an empty sub-line (e.g. Russian state stock sales, no longer reported)
                continue
            nxt = next((x[0] for x in body[i + 1:] if x and isinstance(x[0], str) and x[0].strip()), "")
            if nxt.startswith(" "):          # a parent line with no figures of its own (e.g. Russia: Primary only)
                parent = lab
            else:
                sec = lab
            continue
        if raw.startswith(" ") and parent:
            key = f"{parent}: {lab}"
        else:
            parent = lab
            key = lab if (sec is None or lab.lower().startswith(("total", "demand", "movements", "western"))) else f"{sec}: {lab}"
        if key not in out:
            out[key] = vals
        if lab.lower().startswith("movements in stocks"):
            break
    return {"years": [str(y) for _, y in keep], "table": out}


def jm_parse(content, edition):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    rec = {"edition": edition, "fetched": str(TODAY)}
    for metal in ("Platinum", "Palladium"):
        if metal in wb.sheetnames:
            rec[metal.lower()] = jm_sheet(wb[metal])
    return rec


def jm():
    if not robots_ok(JM, "/products-and-markets/pgms-and-circularity/pgm-market-data") or not robots_ok(JM, "/documents/"):
        raise RuntimeError("matthey.com robots.txt disallows the PGM market data pages")
    r = get(JM_PAGE)
    if r is None or r.status_code != 200:
        raise RuntimeError("Johnson Matthey PGM market data page not available")
    links = re.findall(r'href="([^"]*pgm-supply-demand-history-([a-z]+)-(\d{4})-final[^"]*)"', r.text, re.I) \
        or re.findall(r'href="([^"]*PGM\+supply\+demand\+history\+([A-Za-z]+)\+(\d{4})\+final\.xlsx[^"]*)"', r.text)
    if not links:
        raise RuntimeError("JM supply-and-demand workbook link not found")
    u, mon, y = links[0]
    u = u if u.startswith("http") else JM + u
    edition = f"{mon.capitalize()} {y}"
    d = RAW / "jm"
    d.mkdir(parents=True, exist_ok=True)
    slug = f"{y}-{mon.lower()[:3]}"
    n = 0
    if not (d / f"{slug}.json").exists():
        time.sleep(3)
        x = get(u)
        if x is None or x.status_code != 200 or x.content[:2] != b"PK":
            raise RuntimeError("JM workbook download failed")
        rec = jm_parse(x.content, edition)
        rp = re.search(r'href="([^"]*pgm-market-report-%s\.pdf[^"]*)"' % str(y)[2:], get(JM + "/products-and-markets/pgms-and-circularity/pgm-markets/pgm-market-reports").text or "")
        rec.update(url=u.split("?")[0], page=JM_PAGE, report=(rp.group(1) if rp else None))
        (d / f"{slug}.json").write_text(json.dumps(rec, indent=0))
        n += 1
        print("JM", edition, {k: len(v["table"]) for k, v in rec.items() if isinstance(v, dict) and "table" in v})
    py = int(y) - 1                                       # the previous edition, once, for revisions
    if not list(d.glob(f"{py}-*.json")):
        time.sleep(3)
        x = get(f"{JM}/documents/d/guest/pgm-supply-demand-history-{mon.lower()}-{py}-final", tries=1)
        if x is not None and x.status_code == 200 and x.content[:2] == b"PK":
            rec = jm_parse(x.content, f"{mon.capitalize()} {py}")
            rec.update(url=f"{JM}/documents/d/guest/pgm-supply-demand-history-{mon.lower()}-{py}-final", seeded=True)
            (d / f"{py}-{mon.lower()[:3]}.json").write_text(json.dumps(rec, indent=0))
            print("JM seeded previous edition", py)
        else:
            print("JM previous edition", py, "not available")
    return n


# ───────── other ETF sponsors (Sprott, abrdn, GraniteShares), from their own fund pages ─────────
SPROTT = {"PHYS": ("gold", "https://sprott.com/investment-strategies/exchange-listed-products/physical-bullion-funds/gold/"),
          "PSLV": ("silver", "https://sprott.com/investment-strategies/exchange-listed-products/physical-bullion-funds/silver/"),
          "SPPP": ("platinum,palladium", "https://sprott.com/investment-strategies/exchange-listed-products/physical-bullion-funds/platinum-and-palladium/")}
ABRDN = {"PPLT": ("platinum", "abrdn-physical-platinum-shares-etf-us0032601066"), "PALL": ("palladium", "abrdn-physical-palladium-shares-etf-us0032621023"),
         "SGOL": ("gold", "abrdn-physical-gold-shares-etf-us00326a1043"), "SIVR": ("silver", "abrdn-physical-silver-shares-etf-us0032641088")}
GRANITE = {"PLTM": ("platinum", 60, "pltm"), "BAR": ("gold", 59, "bar")}
GRANITE_NAV = ("https://knockoutv2.azurewebsites.net/api/ProductNavHistory/triggers/When_a_HTTP_request_is_received/invoke/{pid}?api-version=2022-05-01"
               "&sp=%2Ftriggers%2FWhen_a_HTTP_request_is_received%2Frun&sv=1.0&sig=bH7VS-AEVsHFaoHEdwodgWM-T_MUr8kOaZi9St7whis")


def sprott_charts(page):
    """{metal: [(date, ounces)]} from the 'Cumulative Oz. of <metal> Acquired by Trust' charts (holdings after each change)."""
    out = {}
    for m in re.finditer(r"<h3>\s*Cumulative Oz\. of (\w+) Acquired by Trust\s*</h3>", page):
        seg = page[m.end():m.end() + 600000]
        nxt = re.search(r"<h3>", seg)
        seg = seg[:nxt.start()] if nxt else seg
        c0 = seg.find("categories:")
        d0 = seg.find("data:", c0)
        if c0 < 0 or d0 < 0:
            continue
        dates = [dt.date(int(y), int(mo) + 1, int(d)) for y, mo, d in re.findall(r"Date\.UTC\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2})\)", seg[c0:d0])]
        vals = re.match(r"data:\s*\[([^\]]*)\]", seg[d0:])
        vals = [float(v) for v in vals.group(1).split(",") if v.strip()] if vals else []
        if dates and len(dates) == len(vals):
            out[m.group(1).lower()] = list(zip(dates, vals))
        else:
            print("   Sprott chart", m.group(1), "dates/values do not line up", len(dates), len(vals))
    return out


def sprott():
    rows = []
    api = eget("https://sprott.com/api/FinancialData/v1/BullionCalculatorData")
    snap = api.json() if api is not None and api.status_code == 200 else []
    snap = [x for x in snap if isinstance(x, dict) and "totalOunces1" in x]
    for i, (fund, (metals, url)) in enumerate(SPROTT.items()):
        r = eget(url)
        ch = sprott_charts(r.text) if r is not None and r.status_code == 200 else {}
        for k, metal in enumerate(metals.split(",")):
            pts = ch.get(metal, [])
            rows += [{"fund": fund, "metal": metal, "date": d.isoformat(), "ounces": v, "src": "fund page holdings chart"} for d, v in pts]
            # the page's live figure: PHYS, PSLV, SPPP are the first three rows of the calculator feed (checked against the chart)
            x = snap[i] if i < len(snap) else None
            if x is not None:
                oz = float(x["totalOunces1" if k == 0 else "totalOunces2"] or 0)
                if oz > 0 and (not pts or abs(oz / pts[-1][1] - 1) < 0.05):
                    rows.append({"fund": fund, "metal": metal, "date": x["dateTimeStamp"][:10], "ounces": oz, "src": "fund page daily figure"})
                elif oz > 0:
                    print("   Sprott feed row", i, "does not match", fund, metal, oz, pts[-1][1])
            print(fund, metal, len(pts), "chart points", (pts[-1] if pts else ""))
        time.sleep(2)
    if not rows:
        raise RuntimeError("no Sprott data")
    df = pd.DataFrame(rows).sort_values(["fund", "metal", "date", "src"]).drop_duplicates(["fund", "metal", "date"], keep="first")
    return merge_csv(RAW / "etf_sprott.csv", df, ["fund", "metal", "date"])


def abrdn():
    rows = []
    base = "https://www.aberdeeninvestments.com"
    for fund, (metal, slug) in ABRDN.items():
        r = eget(f"{base}/en-us/institutional/funds/view-all-funds/{slug}")
        if r is None or r.status_code != 200:
            print(fund, "page not available"); continue
        t = r.text
        isin = slug[-12:].upper()
        sc = re.search(r'"id":"([0-9a-f\-]{36})","name":"[^"]*","isin":"%s"' % isin, t)
        fid = re.search(r'data-fund_id="([0-9a-f\-]{36})"', t)
        cr = re.search(r'"correlationFundRangeID":"([0-9a-f\-]{36})"', t)
        nm = re.search(r'"pageTitle":"([^"|]+?) \|', t)
        if not (sc and fid and cr):
            print(fund, "fund ids not found on the page"); continue
        name = nm.group(1).strip() if nm else ""
        body = {"countryCode": "USA", "language": "en-US", "shareClass": sc.group(1), "assetClassId": "Alternatives", "fund": fid.group(1),
                "correlationFundRangeId": cr.group(1), "fundRangeName": "Exchange Traded Fund", "fundName": name, "fundNameId": name, "shareClassNameId": "Share",
                "literatureAuthorizations": ["2"], "sfdrClassificationId": "N/A", "countryInvestors": {"countryCode": "USA", "investorType": "4,2", "jurisdiction": "Live"},
                "site": "Institutional"}
        time.sleep(2)
        x = eget(f"{base}/api/gateway/funds/fundDetailsKeyInformation", method="POST", json=body, headers={"Referer": r.url})
        if x is None or x.status_code != 200:
            print(fund, "data service not available"); continue
        c = (x.json() or {}).get("content") or {}
        ent = (c.get("metalEntitlement") or {})
        bk = next((v for k, v in ent.items() if k.lower().startswith("basketsize")), None)
        so = num(c.get("shareClass", {}).get("sharesOutstanding"))
        fs = (c.get("fund") or {}).get("fundSizeWithDate") or {}
        if not (bk and so):
            print(fund, "no shares/basket in the data service", list(ent)); continue
        d = (bk.get("date") or fs.get("date") or "")[:10]
        rows.append({"fund": fund, "metal": metal, "date": d, "shares": so, "basket_oz": num(bk.get("value")), "aum": num(fs.get("value"))})
        print(fund, d, so, "shares,", bk.get("value"), "oz per basket")
        time.sleep(2)
    if not rows:
        raise RuntimeError("no abrdn data")
    return merge_csv(RAW / "etf_abrdn.csv", pd.DataFrame(rows), ["fund", "date"])


def granite():
    rows = []
    for fund, (metal, pid, slug) in GRANITE.items():
        url = GRANITE_NAV.format(pid=pid)
        pg = eget(f"https://graniteshares.com/etfs/{slug}/")                         # the fund page that loads the feed
        if pg is not None and pg.status_code == 200:
            m = re.search(r"https://knockoutv2\.azurewebsites\.net/api/ProductNavHistory/[^\"'\s]+", pg.text)
            if m:
                url = html.unescape(m.group(0)).replace("{0}", str(pid))
        r = eget(url)
        if r is None or r.status_code != 200:
            print(fund, "NAV history not available"); continue
        d = pd.DataFrame(r.json())
        d = d[(d.ProductId == pid) & d.AUM.notna() & d.Price.notna()]
        for _, x in d.iterrows():
            rows.append({"fund": fund, "metal": metal, "date": str(x.PriceDate)[:10], "nav": float(x.Price), "aum": float(x.AUM),
                         "shares": round(float(x.AUM) / float(x.Price), -2), "basket_oz": num(x.Ounces)})
        print(fund, len(d), "days from", d.PriceDate.min(), "to", d.PriceDate.max())
        time.sleep(2)
    if not rows:
        raise RuntimeError("no GraniteShares data")
    return merge_csv(RAW / "etf_granite.csv", pd.DataFrame(rows), ["fund", "date"])


def num(v):
    try:
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def etf_more():
    n, bad = 0, []
    for nm, f in (("Sprott", sprott), ("abrdn", abrdn), ("GraniteShares", granite)):
        print("-", nm)
        try:
            n += f()
        except Exception as e:
            traceback.print_exc()
            bad.append(nm)
    if bad:
        raise RuntimeError("ETF sources failed: " + ", ".join(bad))
    return n


# ───────── ETF trusts: ounces held and shares outstanding at quarter ends (SEC filings) ─────────
SEC_ETF = {"GLD": ("0001222333", "gold"), "PPLT": ("0001460235", "platinum"), "PALL": ("0001459862", "palladium"), "SGOL": ("0001450923", "gold"), "SIVR": ("0001450922", "silver"),
           "IAU": ("0001278680", "gold"), "SLV": ("0001330568", "silver"), "PLTM": ("0001690842", "platinum"), "BAR": ("0001690437", "gold")}
SHARE_FACTS = ("SharesOutstanding", "CommonStockSharesOutstanding", "TemporaryEquitySharesOutstanding")


def pgm_etf():
    rows = []
    for fund, (cik, metal) in SEC_ETF.items():
        r = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", headers={"User-Agent": "research-desk admin@example.com"})
        if r is None or r.status_code != 200:
            print(fund, "SEC data not available"); continue
        g = (r.json().get("facts") or {}).get("us-gaap", {})
        sh = {}
        for f in SHARE_FACTS:
            for v in (g.get(f, {}).get("units", {}).get("shares") or []):
                sh.setdefault(v["end"], v["val"])
        for unit, vals in g.get("InvestmentOwnedBalanceOtherMeasure", {}).get("units", {}).items():
            if unit.lower() not in ("oz", "ounce", "ounces", "troyounce"):
                continue
            for v in vals:
                rows.append({"fund": fund, "metal": metal, "date": v["end"], "ounces": round(float(v["val"]), 1), "form": v.get("form"), "filed": v.get("filed"),
                             "shares": sh.get(v["end"])})
        time.sleep(1)
    if not rows:
        raise RuntimeError("no ETF ounces in SEC data")
    df = pd.DataFrame(rows).sort_values(["fund", "date", "filed"]).drop_duplicates(["fund", "date"], keep="last")
    n = merge_csv(RAW / "etf_sec.csv", df, ["fund", "date"])
    pg = df[df.fund.isin(["PPLT", "PALL"])][["fund", "metal", "date", "ounces", "form", "filed"]]
    n += merge_csv(RAW / "etf_pgm.csv", pg, ["fund", "date"])
    for f, g in df.groupby("fund"):
        print(f, len(g), "quarters, last", g.date.iloc[-1], g.ounces.iloc[-1], "oz")
    return n


STEPS = {"etf": etf, "etf_more": etf_more, "lme": lme, "wgc": wgc, "icsg": icsg, "iai": iai, "usgs": usgs, "silver": silver, "rates": rates, "comex": comex, "wpic": wpic, "jm": jm, "pgm_etf": pgm_etf}


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    lp = RAW / "fetch_log.json"
    log = json.loads(lp.read_text()) if lp.exists() else {}
    failed = []
    for s in (sys.argv[1:] or STEPS):
        t0 = time.time()
        print(f"── {s}")
        try:
            n = STEPS[s]()
            log[s] = {"ok": True, "at": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "new": n, "secs": round(time.time() - t0)}
            if n:
                log[s]["last_new"] = log[s]["at"]
            else:
                log[s]["last_new"] = (log.get(s) or {}).get("last_new")
        except Exception as e:
            traceback.print_exc()
            failed.append(s)
            log[s] = {**(log.get(s) or {}), "ok": False, "at": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "error": str(e)[:300]}
    lp.write_text(json.dumps(log, indent=1))
    if failed:
        print("::error::metals sources failed: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
