"""Probe 3: network capture of JS-driven data pages + downloads."""
import json, re, time, os, io, requests
HB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
os.makedirs("probe/m3", exist_ok=True)
out = {}
def save(nm, url, fn, **kw):
    try:
        r = requests.get(url, headers=HB, timeout=90, **kw)
        out[nm] = {"url": url, "status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "final": r.url, "cd": r.headers.get("content-disposition")}
        if r.status_code == 200:
            open("probe/m3/" + fn, "wb").write(r.content)
        return r
    except Exception as e:
        out[nm] = {"url": url, "err": str(e)[:300]}
save("gld_api", "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en", "gld_api.bin")
save("wm_cu_2025", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash&year=2025", "wm_cu_2025.html")
save("wm_al", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_cash", "wm_al.html")
save("wgc_gdt_q3", "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2026", "gdt_q3.html")
r = save("icsg_press", "https://icsg.org/press-releases/", "icsg.html")
time.sleep(21)
if r is not None and r.status_code == 200:
    u = re.search(r'data-downloadurl="(https://icsg.org/download/[^"]*monthly-press-release[^"]*)"', r.text)
    if u:
        save("icsg_monthly_pdf", u.group(1).replace("&#038;", "&"), "icsg_monthly.pdf")
        try:
            from pypdf import PdfReader
            t = "\n".join(p.extract_text() or "" for p in PdfReader("probe/m3/icsg_monthly.pdf").pages)
            open("probe/m3/icsg_monthly.txt", "w").write(t)
        except Exception as e:
            out["icsg_pdf_text_err"] = str(e)
save("usgs_data", "https://www.sciencebase.gov/catalog/file/get/696a75d5d4be0228872d3bf8?f=__disk__eb%2F4d%2Fd1%2Feb4dd129d4f08cfba010a8b11", "mcs2026_data.csv")
# headless browser network capture
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        for nm, url in [("iai", "https://international-aluminium.org/statistics/primary-aluminium-production/"),
                        ("wgc_cb", "https://www.gold.org/goldhub/data/gold-reserves-by-country"),
                        ("wgc_etf", "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows")]:
            pg = b.new_page(user_agent=HB["User-Agent"])
            reqs = []
            def onresp(resp, reqs=reqs, nm=nm):
                u = resp.url
                if any(k in u for k in ("alvis", "api", "json", "ajax", "data", "csv", "xls")) and not u.endswith((".js", ".css", ".woff2", ".png", ".svg")):
                    try:
                        body = resp.body()
                    except Exception:
                        body = b""
                    reqs.append({"url": u, "status": resp.status, "method": resp.request.method, "post": (resp.request.post_data or "")[:500], "ct": resp.headers.get("content-type"), "len": len(body)})
                    if len(body) < 3_000_000 and len(reqs) < 40:
                        open(f"probe/m3/{nm}_{len(reqs)}.bin", "wb").write(body)
            pg.on("response", onresp)
            try:
                pg.goto(url, wait_until="networkidle", timeout=90000)
                pg.wait_for_timeout(6000)
            except Exception as e:
                reqs.append({"err": str(e)[:200]})
            out["net_" + nm] = reqs
            pg.close()
        b.close()
except Exception as e:
    out["playwright_err"] = str(e)[:500]
json.dump(out, open("probe/m3/out.json", "w"), indent=1)
print(json.dumps(out, indent=0)[:20000])
