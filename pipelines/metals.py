"""Metals desk raw data (runs in GitHub Actions; no keys). Each source is independent: a failure in one is reported and
the others still run. Old data is kept; only new data is fetched where the source allows it.

Usage: python pipelines/metals.py [step ...]      steps: etf lme wgc icsg iai usgs silver rates comex   (default: all)

  etf     SPDR GLD daily history (spdrgoldshares.com archive), iShares IAU and SLV tonnes in trust (product pages, daily
          snapshot appended)                                                       -> raw/etf_gld.csv, raw/etf_ishares.csv
  lme     LME copper and aluminium cash, 3-month and LME stocks (westmetall.com daily tables; current year each run,
          earlier years once)                                                      -> raw/lme_cu.csv, raw/lme_al.csv
  wgc     World Gold Council quarterly supply and demand (the public Goldhub chart data; a snapshot is kept whenever it
          changes, so revisions can be read)                                      -> raw/wgc/sd_<date>.json
  icsg    ICSG monthly press release (PDF): world refined copper balance table and text -> raw/icsg/<release>.json
  iai     International Aluminium Institute monthly primary aluminium production by region (public statistics page)
                                                                                   -> raw/iai_primary.csv, raw/iai/snap_<month>.json
  usgs    USGS Mineral Commodity Summaries data release (annual): world mine production, reserves, US salient statistics
          for gold, silver, copper, aluminum, bauxite                              -> raw/usgs_mcs<year>.csv
  silver  Silver Institute supply-and-demand page (World Silver Survey key numbers) -> raw/silver_institute.json
  rates   US Treasury 10-year real yield (TIPS) and the US dollar index (Yahoo)   -> raw/real_yields.csv, raw/dxy.csv
  comex   COMEX warehouse stocks: parses CME's daily stock reports (Gold_Stocks.xls etc.) that the Mac collector or a
          manual upload drops in raw/comex_stocks/ (cmegroup.com blocks GitHub's servers)  -> raw/comex_stocks.csv
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
    r = get("https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en")
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
        print("GLD archive not available")
    rows = []
    for fund, url in [("IAU", "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund"),
                      ("SLV", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund")]:
        r = get(url)
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
        time.sleep(2)
    if rows:
        n += merge_csv(RAW / "etf_ishares.csv", pd.DataFrame(rows), ["fund", "date"])
    if not rows and not (RAW / "etf_gld.csv").exists():
        raise RuntimeError("no ETF data")
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


# ───────── World Gold Council quarterly supply and demand ─────────
def wgc():
    if not robots_ok("https://fsv3.gold.org", "/api/"):
        raise RuntimeError("fsv3.gold.org robots.txt disallows /api/")
    r = get("https://fsv3.gold.org/api/v11/charts/supply-and-demand/44", headers={"Referer": "https://www.gold.org/goldhub/data/gold-demand-by-country", "Accept": "application/json"})
    if r is None or r.status_code != 200:
        raise RuntimeError("WGC supply-demand data not available")
    cd = r.json()["chartData"]
    keep = {k: v for k, v in cd.items() if k in ("Supply_Quarterly", "Demand_Quarterly", "Supply_Annually", "Demand_Annually")}
    body = json.dumps(keep, sort_keys=True)
    d = RAW / "wgc"
    d.mkdir(parents=True, exist_ok=True)
    snaps = sorted(d.glob("sd_*.json"))
    if snaps and json.dumps(json.loads(snaps[-1].read_text())["data"], sort_keys=True) == body:
        print("WGC unchanged, latest quarter", keep["Demand_Quarterly"]["categories"][-1]); return 0
    (d / f"sd_{TODAY}.json").write_text(json.dumps({"fetched": str(TODAY), "source": "World Gold Council, Goldhub supply and demand (world)", "data": keep}))
    print("WGC new snapshot, latest quarter", keep["Demand_Quarterly"]["categories"][-1])
    return 1


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
COMEX_FILES = {"Gold_Stocks": "gold", "Silver_stocks": "silver", "Copper_Stocks": "copper", "Aluminum_Stocks": "aluminum"}


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


STEPS = {"etf": etf, "lme": lme, "wgc": wgc, "icsg": icsg, "iai": iai, "usgs": usgs, "silver": silver, "rates": rates, "comex": comex}


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
