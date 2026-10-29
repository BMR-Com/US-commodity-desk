import os, re, json, subprocess, requests
from pathlib import Path
OUT = Path("tmp/out"); OUT.mkdir(parents=True, exist_ok=True)
KEY = (os.getenv("AMS_API_KEY") or "").strip()
H = {"User-Agent": "Mozilla/5.0 (research; bmr-com)"}
def pdf(url, name):
    try:
        r = requests.get(url, headers=H, timeout=120); r.raise_for_status()
        p = OUT / f"{name}.pdf"; p.write_bytes(r.content)
        subprocess.run(["pdftotext", "-layout", str(p), str(OUT / f"{name}.txt")], check=False)
        return True
    except Exception as e:
        (OUT / f"{name}.err").write_text(repr(e)); return False
pdf("https://www.ams.usda.gov/mnreports/cnwwcmr.pdf", "cnwwcmr")
# MARS catalogue: every report with cotton in the title
try:
    r = requests.get("https://marsapi.ams.usda.gov/services/v1.2/reports", auth=(KEY, ""), timeout=120); r.raise_for_status()
    allr = r.json(); (OUT / "mars_all_count.txt").write_text(str(len(allr)))
    cot = [x for x in allr if "cotton" in json.dumps(x).lower()]
    (OUT / "mars_cotton.json").write_text(json.dumps(cot, indent=1))
except Exception as e:
    (OUT / "mars.err").write_text(repr(e))
# AMS cotton market news pages: collect report links
links = set()
for u in ["https://www.ams.usda.gov/market-news/cotton", "https://www.ams.usda.gov/market-news/cotton-market-news-reports",
          "https://www.ams.usda.gov/market-news/cotton-reports", "https://www.ams.usda.gov/market-news/cotton-and-tobacco"]:
    try:
        h = requests.get(u, headers=H, timeout=60).text
        (OUT / ("page_" + u.rstrip("/").split("/")[-1] + ".html")).write_text(h)
        for m in re.finditer(r'href="([^"]+)"[^>]*>([^<]{0,160})<', h):
            href, txt = m.group(1), m.group(2).strip()
            if re.search(r"mnreports/|mymarketnews|/report/|\.pdf|\.txt", href, re.I):
                links.add((href if href.startswith("http") else "https://www.ams.usda.gov" + href, txt))
    except Exception as e:
        (OUT / "pages.err").write_text(repr(e))
links = sorted(links)
(OUT / "links.json").write_text(json.dumps(links, indent=1))
for href, txt in links:
    m = re.search(r"mnreports/([a-z0-9_]+)\.pdf", href, re.I)
    if m and m.group(1) != "cnwwcmr":
        pdf(href, m.group(1))
