"""Probe 2: iShares fund download file, abrdn fund pages (browser network calls), GraniteShares page discovery."""
import io, json, re, time, requests, urllib.robotparser as rp
from pathlib import Path
from urllib.parse import urlparse, urljoin
OUT = Path("probe_out2"); OUT.mkdir(exist_ok=True)
UA = "BMR-Com-research-desk/1.0 (daily ETF holdings research; github actions)"
H = {"User-Agent": UA}
res = {}
_rb = {}
def allowed(url):
    u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
    if base not in _rb:
        r = rp.RobotFileParser()
        try:
            t = requests.get(base + "/robots.txt", headers=H, timeout=30)
            (OUT / ("robots_" + u.netloc + ".txt")).write_text(f"status {t.status_code}\n" + t.text[:20000])
            r.parse(t.text.splitlines() if t.status_code == 200 else [])
        except Exception: r.parse([])
        _rb[base] = r
    return _rb[base].can_fetch(UA, url)
def fetch(key, url):
    if not allowed(url):
        res[key] = {"url": url, "robots": "DISALLOWED"}; return None
    try:
        r = requests.get(url, headers=H, timeout=90)
        res[key] = {"url": url, "status": r.status_code, "ct": r.headers.get("content-type"), "cd": r.headers.get("content-disposition"), "len": len(r.content), "final": r.url, "head": r.content[:300].decode("utf-8", "replace")}
        (OUT / f"{key}.bin").write_bytes(r.content[:2_900_000])
        return r
    except Exception as e:
        res[key] = {"url": url, "err": str(e)[:200]}; return None
for f, pid in (("IAU", 239561), ("SLV", 239855)):
    for site, sub in (("us-ishares", "ISHARES"), ("one", "ONE")):
        u = f"https://www.blackrock.com/varnish-api/blk-one01-product-data/product-data/api/v1/get-fund-document?appType=PRODUCT_PAGE&appSubType={sub}&targetSite={site}&locale=en_US&portfolioId={pid}&component=fundDownload&userType=individual"
        r = fetch(f"{f}_dl_{site}", u); time.sleep(2)
        if r is not None and r.status_code == 200:
            t = r.content.decode("utf-8", "replace")
            res[f"{f}_dl_{site}"]["sheets"] = re.findall(r'ss:Name="([^"]+)"', t)[:20]
            # rows of the sheet containing 'Historical'
            m = re.search(r'ss:Name="Historical"(.*?)</ss:Worksheet>', t, re.S)
            if m:
                rows = re.findall(r"<ss:Row>(.*?)</ss:Row>", m.group(1), re.S)
                cells = [re.findall(r"<ss:Data[^>]*>([^<]*)</ss:Data>", x) for x in rows]
                res[f"{f}_dl_{site}"]["hist_rows"] = len(cells); res[f"{f}_dl_{site}"]["hist_head"] = cells[:4]; res[f"{f}_dl_{site}"]["hist_tail"] = cells[-3:]
            for w in ("Ounces", "Tonnes", "ounces", "tonnes"):
                i = t.find(w)
                if i >= 0: res[f"{f}_dl_{site}"]["ctx_" + w] = re.sub(r"<[^>]+>", "|", t[max(0, i - 400):i + 400])
(OUT / "requests.json").write_text(json.dumps(res, indent=1))

from playwright.sync_api import sync_playwright
pages = {
 "pplt": "https://www.aberdeeninvestments.com/en-us/institutional/funds/view-all-funds/abrdn-physical-platinum-shares-etf-us0032601066",
 "pall": "https://www.aberdeeninvestments.com/en-us/institutional/funds/view-all-funds/abrdn-physical-palladium-shares-etf-us0032621023",
 "pplt_inv": "https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds/abrdn-physical-platinum-shares-etf-us0032601066",
 "etfdisc": "https://www.aberdeeninvestments.com/en-us/investor/investment-solutions/etfdisclosures",
 "gs_home": "https://graniteshares.com/",
}
summary = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for k, url in pages.items():
        if not allowed(url):
            summary[k] = "robots disallowed"; continue
        ctx = b.new_context(user_agent=UA + " HeadlessChrome"); pg = ctx.new_page(); calls = []
        def on_resp(resp, calls=calls, k=k):
            rt = resp.request.resource_type
            if rt in ("xhr", "fetch", "document") or re.search(r"(\.csv|\.xls|\.json|api)", resp.url, re.I):
                if re.search(r"(google|doubleclick|demdex|onetrust|cookielaw|userway|cookiebot|adobe|linkedin|facebook|bing|hotjar|qualtrics)", resp.url): return
                rec = {"url": resp.url, "status": resp.status, "ct": resp.headers.get("content-type", ""), "rt": rt}
                try:
                    body = resp.body(); rec["len"] = len(body)
                    if len(body) < 2_500_000:
                        fn = f"{k}_{len(calls):03d}"; (OUT / fn).write_bytes(body); rec["file"] = fn
                except Exception as e: rec["err"] = str(e)[:100]
                calls.append(rec)
        pg.on("response", on_resp)
        try: pg.goto(url, timeout=60000, wait_until="load")
        except Exception as e: summary[k + "_err"] = str(e)[:200]
        pg.wait_for_timeout(12000)
        try:
            pg.mouse.wheel(0, 6000); pg.wait_for_timeout(4000)
            (OUT / f"{k}_rendered.html").write_text(pg.content()[:2_800_000])
            (OUT / f"{k}_text.txt").write_text(pg.inner_text("body"))
            hrefs = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            (OUT / f"{k}_links.txt").write_text("\n".join(sorted(set(hrefs))))
        except Exception as e: summary[k + "_err2"] = str(e)[:200]
        summary[k] = calls; ctx.close()
    b.close()
(OUT / "calls.json").write_text(json.dumps(summary, indent=1))
print(json.dumps({k: v.get("status") for k, v in res.items()}), json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}))
