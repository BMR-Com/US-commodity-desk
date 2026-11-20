"""Discovery probe: sponsor ETF metal-holdings sources (robots.txt respected, honest UA)."""
import json, re, sys, time, requests, urllib.robotparser as rp
from pathlib import Path
OUT = Path("probe_out"); OUT.mkdir(exist_ok=True)
UA = "BMR-Com-research-desk/1.0 (daily ETF holdings research; github actions)"
H = {"User-Agent": UA}
res = {}
robots = {}
def allowed(url):
    from urllib.parse import urlparse
    u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
    if base not in robots:
        r = rp.RobotFileParser()
        try:
            t = requests.get(base + "/robots.txt", headers=H, timeout=30)
            (OUT / ("robots_" + u.netloc + ".txt")).write_text(f"status {t.status_code}\n" + t.text[:20000])
            r.parse(t.text.splitlines() if t.status_code == 200 else [])
        except Exception as e:
            r.parse([])
        robots[base] = r
    return robots[base].can_fetch(UA, url)
def fetch(key, url, save=True):
    ok = allowed(url)
    if not ok:
        res[key] = {"url": url, "robots": "DISALLOWED"}; return None
    try:
        r = requests.get(url, headers=H, timeout=60)
        res[key] = {"url": url, "status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "final": r.url}
        if save:
            ext = "bin"
            ct = (r.headers.get("content-type") or "")
            if "html" in ct: ext = "html"
            elif "json" in ct: ext = "json"
            elif "csv" in ct: ext = "csv"
            (OUT / f"{key}.{ext}").write_bytes(r.content[:8_000_000])
        return r
    except Exception as e:
        res[key] = {"url": url, "err": str(e)[:200]}; return None
def links(key, r, pat=r"(xls|csv|ajax|historical|history|ounce|bar.?list|holding|download|\.json|api/)"):
    if r is None: return
    t = r.text.replace("\\/", "/").replace("&amp;", "&")
    found = sorted(set(m for m in re.findall(r'["\'(]((?:https?:)?/[^"\'\s<>()]{3,300})["\')]', t) if re.search(pat, m, re.I)))
    res[key]["links"] = found[:300]

pages = {
 "iau": "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund",
 "slv": "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund",
 "iau_br": "https://www.blackrock.com/us/individual/products/239561/ishares-gold-trust-fund",
 "slv_br": "https://www.blackrock.com/us/individual/products/239855/ishares-silver-trust-fund",
 "pplt_abrdn": "https://www.abrdn.com/en-us/us/investor/fund-details/abrdn-physical-physical-platinum-shares-etf/share/us0032601066",
 "abrdn_etf_list": "https://www.aberdeeninvestments.com/en-us/investor/etfs",
 "sprott_silver": "https://sprott.com/investment-strategies/physical-bullion-trusts/silver/",
 "sprott_gold": "https://sprott.com/investment-strategies/physical-bullion-trusts/gold/",
 "sprott_pp": "https://sprott.com/investment-strategies/physical-bullion-trusts/platinum-and-palladium/",
 "gs_pltm": "https://graniteshares.com/PLTM",
 "gs_bar": "https://graniteshares.com/BAR",
}
for k, u in pages.items():
    r = fetch(k, u); links(k, r); time.sleep(2)
# iShares xls downloads found on page
for k in ("iau", "slv"):
    for l in (res.get(k, {}).get("links") or []):
        if "fileType=" in l or ".ajax" in l:
            u = ("https://www.ishares.com" + l) if l.startswith("/") else l
            kk = k + "_dl_" + re.sub(r"\W+", "_", l)[-60:]
            fetch(kk, u); time.sleep(2)
(OUT / "requests.json").write_text(json.dumps(res, indent=1))
print(json.dumps({k: {x: v.get(x) for x in ("status", "len", "robots", "err")} for k, v in res.items()}, indent=0))
