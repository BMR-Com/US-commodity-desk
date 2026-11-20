"""Headless browser: record JSON/CSV/XLS network calls each fund page makes (robots checked first)."""
import json, re, sys, time, requests, urllib.robotparser as rp
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
OUT = Path("probe_out/browser"); OUT.mkdir(parents=True, exist_ok=True)
UA = "BMR-Com-research-desk/1.0 (daily ETF holdings research; github actions) HeadlessChrome"
pages = {
 "iau": "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund",
 "pplt": "https://www.abrdn.com/en-us/us/investor/fund-details/abrdn-physical-physical-platinum-shares-etf/share/us0032601066",
 "abrdn_list": "https://www.aberdeeninvestments.com/en-us/investor/etfs",
 "sprott_silver": "https://sprott.com/investment-strategies/physical-bullion-trusts/silver/",
 "sprott_pp": "https://sprott.com/investment-strategies/physical-bullion-trusts/platinum-and-palladium/",
 "gs_pltm": "https://graniteshares.com/PLTM",
}
def allowed(url):
    u = urlparse(url); r = rp.RobotFileParser()
    try:
        t = requests.get(f"{u.scheme}://{u.netloc}/robots.txt", headers={"User-Agent": UA}, timeout=30)
        r.parse(t.text.splitlines() if t.status_code == 200 else [])
    except Exception: r.parse([])
    return r.can_fetch(UA, url)
summary = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    for k, url in pages.items():
        if not allowed(url):
            summary[k] = "robots disallowed"; continue
        ctx = b.new_context(user_agent=UA); pg = ctx.new_page(); calls = []
        def on_resp(resp, calls=calls, k=k):
            ct = resp.headers.get("content-type", "")
            if any(x in ct for x in ("json", "csv", "excel", "spreadsheet", "octet")) or re.search(r"(api|ajax|\.json|\.csv|\.xls)", resp.url, re.I):
                rec = {"url": resp.url, "status": resp.status, "ct": ct}
                try:
                    body = resp.body()
                    rec["len"] = len(body)
                    if len(body) < 3_000_000:
                        fn = f"{k}_{len(calls):03d}"
                        (OUT / fn).write_bytes(body); rec["file"] = fn
                except Exception as e: rec["err"] = str(e)[:100]
                calls.append(rec)
        pg.on("response", on_resp)
        try:
            pg.goto(url, timeout=60000, wait_until="networkidle")
        except Exception as e:
            summary[k + "_err"] = str(e)[:200]
        time.sleep(5)
        try:
            (OUT / f"{k}_rendered.html").write_text(pg.content())
            txt = pg.inner_text("body")
            (OUT / f"{k}_text.txt").write_text(txt)
        except Exception as e: pass
        summary[k] = calls
        ctx.close()
    b.close()
(OUT / "calls.json").write_text(json.dumps(summary, indent=1))
print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}))
