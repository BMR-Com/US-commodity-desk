import requests, urllib.robotparser as rp
UA = "BMR-Com-research-desk/1.0 (ETF metal holdings research; GitHub Actions)"
for host in ("https://api.spdrgoldshares.com", "https://www.spdrgoldshares.com", "https://spdrgoldshares.com"):
    r = requests.get(host + "/robots.txt", headers={"User-Agent": UA}, timeout=30)
    print("==", host, r.status_code); print(r.text[:1500])
for u in ("https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv", "https://www.spdrgoldshares.com/usa/historical-data/",
          "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"):
    try:
        r = requests.get(u, headers={"User-Agent": UA}, timeout=60)
        print("--", u, r.status_code, r.headers.get("content-type"), len(r.content)); print(r.content[:400])
        if "historical-data" in u:
            import re; print(sorted(set(re.findall(r'href="([^"]*(?:csv|xls|archive|api)[^"]*)"', r.text)))[:30])
    except Exception as e:
        print(u, e)
