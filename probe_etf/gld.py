import requests, re, html, json
UA = "BMR-Com-research-desk/1.0 (ETF metal holdings research; GitHub Actions)"
for u in ("https://www.spdrgoldshares.com/usa/gld/", "https://www.spdrgoldshares.com/usa/historical-data/"):
    r = requests.get(u, headers={"User-Agent": UA}, timeout=60)
    t = html.unescape(r.text)
    print("==", u, r.status_code, len(t))
    for w in ("Tonnes", "tonnes", "Ounces", "ounces"):
        for m in list(re.finditer(w, t))[:6]:
            print("  ", w, "::", re.sub(r"\s+", " ", t[max(0, m.start() - 250):m.start() + 250]))
    nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if nd:
        open("probe_etf/gld_next_%s.json" % u.rstrip("/").split("/")[-1], "w").write(nd.group(1)[:3000000])
        print("  next data", len(nd.group(1)))
