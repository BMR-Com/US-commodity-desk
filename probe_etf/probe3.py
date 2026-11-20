"""Probe 3: abrdn tabs + API request bodies, abrdn SGOL/SIVR pages, GraniteShares PLTM/BAR pages, SEC ounce/share facts."""
import json, re, time, requests, urllib.robotparser as rp
from pathlib import Path
from urllib.parse import urlparse
OUT = Path("probe_out3"); OUT.mkdir(exist_ok=True)
UA = "BMR-Com-research-desk/1.0 (daily ETF holdings research; github actions)"
H = {"User-Agent": UA}
_rb = {}
def allowed(url):
    u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
    if base not in _rb:
        r = rp.RobotFileParser()
        try:
            t = requests.get(base + "/robots.txt", headers=H, timeout=30); r.parse(t.text.splitlines() if t.status_code == 200 else [])
        except Exception: r.parse([])
        _rb[base] = r
    return _rb[base].can_fetch(UA, url)
res = {}
# SEC
SH = {"User-Agent": "BMR-Com research desk research@bmr-com.example"}
try:
    tick = requests.get("https://www.sec.gov/files/company_tickers.json", headers=SH, timeout=60).json()
    want = {"IAU", "SLV", "SGOL", "SIVR", "PPLT", "PALL", "PLTM", "BAR", "GLDM", "GLTR"}
    ciks = {v["ticker"]: v["cik_str"] for v in tick.values() if v["ticker"] in want}
    res["ciks"] = ciks
    for t, cik in ciks.items():
        r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json", headers=SH, timeout=60)
        time.sleep(0.5)
        if r.status_code != 200: res[t] = r.status_code; continue
        f = r.json().get("facts", {}); keep = {}
        for ns, cs in f.items():
            for c, d in cs.items():
                for unit, vals in d.get("units", {}).items():
                    if re.search(r"oz|ounce|shares", unit, re.I) or re.search(r"Shares|Ounce", c):
                        keep[f"{ns}:{c}:{unit}"] = [(v["end"], v["val"], v.get("form")) for v in vals][-200:]
        res[t] = keep
except Exception as e:
    res["sec_err"] = str(e)
(OUT / "sec.json").write_text(json.dumps(res))
# abrdn sitemap -> physical ETF urls
try:
    sm = requests.get("https://www.aberdeeninvestments.com/institutional/sitemap.xml", headers=H, timeout=60).text
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    subs = [l for l in locs if l.endswith(".xml")]
    found = [l for l in locs if "physical" in l]
    for s in subs[:30]:
        if found: break
        t = requests.get(s, headers=H, timeout=60).text
        found += [l for l in re.findall(r"<loc>([^<]+)</loc>", t) if "physical" in l]
    (OUT / "abrdn_physical_urls.txt").write_text("\n".join(found) + "\n\nSUBS\n" + "\n".join(subs[:50]))
except Exception as e:
    (OUT / "abrdn_physical_urls.txt").write_text("err " + str(e))
from playwright.sync_api import sync_playwright
pages = {
 "pplt": "https://www.aberdeeninvestments.com/en-us/institutional/funds/view-all-funds/abrdn-physical-platinum-shares-etf-us0032601066",
 "gs_pltm": "https://graniteshares.com/etfs/pltm/",
 "gs_bar": "https://graniteshares.com/etfs/bar/",
}
summary = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for k, url in pages.items():
        if not allowed(url): summary[k] = "robots disallowed"; continue
        ctx = b.new_context(user_agent=UA + " HeadlessChrome"); pg = ctx.new_page(); calls = []
        def on_resp(resp, calls=calls, k=k):
            rt = resp.request.resource_type
            if rt not in ("xhr", "fetch"): return
            if re.search(r"(google|doubleclick|demdex|onetrust|cookielaw|userway|cookiebot|adobe|linkedin|facebook|bing|hotjar|clarity|hubspot|hs-sites|hubapi|livechat|adsrvr|reddit|_next/static|hscollected)", resp.url): return
            rec = {"url": resp.url, "status": resp.status, "method": resp.request.method, "post": (resp.request.post_data or "")[:2000], "ct": resp.headers.get("content-type", "")}
            try:
                body = resp.body(); rec["len"] = len(body)
                if len(body) < 2_500_000:
                    fn = f"{k}_{len(calls):03d}"; (OUT / fn).write_bytes(body); rec["file"] = fn
            except Exception as e: rec["err"] = str(e)[:100]
            calls.append(rec)
        pg.on("response", on_resp)
        try: pg.goto(url, timeout=60000, wait_until="load")
        except Exception as e: summary[k + "_err"] = str(e)[:200]
        pg.wait_for_timeout(10000)
        for tab in ("Performance", "Premium/Discount", "Literature", "Holdings", "Prices", "Fund Data", "Documents"):
            try:
                loc = pg.get_by_text(tab, exact=True)
                if loc.count():
                    loc.first.click(timeout=5000); pg.wait_for_timeout(5000)
                    (OUT / f"{k}_tab_{re.sub(r'\W','',tab)}.txt").write_text(pg.inner_text("body"))
            except Exception as e: summary[f"{k}_{tab}_err"] = str(e)[:150]
        try:
            (OUT / f"{k}_text.txt").write_text(pg.inner_text("body"))
            hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            (OUT / f"{k}_links.txt").write_text("\n".join(sorted(set(hrefs))))
        except Exception as e: summary[k + "_err2"] = str(e)[:200]
        summary[k] = calls; ctx.close()
    b.close()
(OUT / "calls.json").write_text(json.dumps(summary, indent=1))
print("done")
