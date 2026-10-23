"""Collect China cotton data from GitHub Actions (no Claude session needed), when the sites answer GitHub's runners.

  python pipelines/china_collect.py gacc   China customs English monthly bulletin (plain HTML)
  python pipelines/china_collect.py cca    China Cotton Association: renders the site's own pages in headless Chromium
                                           and runs china/collect_cca.js there (same collector as the Mac browser task)
Only data newer than what is stored is read (china/ingest.py known). Each step records its outcome in
data/china/raw/collect_status.json; a failure leaves the stored data untouched.
"""
import json, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / "data" / "china" / "raw" / "collect_status.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
KEEP = re.compile(r"cotton|yarn|grain|cereal|soya|wheat|maize|barley|sorghum|rice|rape|edible|meat|beans|sugar|textile|wool|dairy|milk|powdered|bovine|swine|poultry|agricultur|fertil|palm|oil", re.I)
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def known():
    return json.loads(subprocess.check_output([sys.executable, str(ROOT / "china" / "ingest.py"), "known"], text=True))


def status(step, ok, note):
    s = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    s[step] = {"ok": ok, "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "note": str(note)[:300]}
    STATUS.write_text(json.dumps(s, indent=1))


def ingest(kind, obj):
    import base64, gzip
    b = base64.b64encode(gzip.compress(json.dumps(obj, ensure_ascii=False).encode())).decode()
    with tempfile.NamedTemporaryFile("w", suffix=".b64", delete=False) as f:
        f.write(b)
    print(subprocess.check_output([sys.executable, str(ROOT / "china" / "ingest.py"), kind, f.name], text=True))


def gacc():
    from bs4 import BeautifulSoup
    have = set(known()["gacc"]["have"])
    base = "http://english.customs.gov.cn"
    rows, log = [], []
    y0 = datetime.now(timezone.utc).year
    for y in (y0 - 1, y0):
        r = requests.get(f"{base}/statics/report/monthly{y}.html", headers=UA, timeout=60)
        if r.status_code != 200 and y == y0:
            r = requests.get(f"{base}/statics/report/monthly.html", headers=UA, timeout=60)
        r.raise_for_status()
        d = BeautifulSoup(r.text, "html.parser")
        for tag, flow in (("Major Import Commodities", "M"), ("Major Export Commodities", "X")):
            row = next((tr for tr in d.find_all("tr") if tag in tr.get_text()), None)
            if not row:
                log.append(f"{y} no {tag}")
                continue
            for a in row.find_all("a"):
                m = a.get_text(strip=True).replace(".", "")
                if f"{flow}|{y}|{m}" in have or m not in MON:
                    continue
                href = re.sub(r"^https?://[^/]+", "", a.get("href", ""))
                t = BeautifulSoup(requests.get(base + href, headers=UA, timeout=60).text, "html.parser")
                n = 0
                for tr in t.find_all("tr"):
                    c = [re.sub(r"\s+", " ", td.get_text(strip=True)) for td in tr.find_all(["td", "th"])]
                    if len(c) >= 7 and KEEP.search(c[0]):
                        rows.append([flow, y, m] + c[:7])
                        n += 1
                log.append(f"{flow} {y} {m} {n}")
                time.sleep(1)
    ingest("gacc", {"collected_at": datetime.now(timezone.utc).isoformat(), "rows": rows, "log": log})
    status("gacc", True, f"{len(rows)} rows; {log[-3:]}")


def cca():
    from playwright.sync_api import sync_playwright
    K = known()["cca"]
    src = (ROOT / "china" / "collect_cca.js").read_text().strip().rstrip(";")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(user_agent=UA["User-Agent"], viewport={"width": 1400, "height": 1000})
        pg.goto("https://www.china-cotton.org/", timeout=90000, wait_until="domcontentloaded")
        pg.wait_for_timeout(5000)
        b64 = pg.evaluate(f"async (K) => await ({src})(K)", K)
        b.close()
    with tempfile.NamedTemporaryFile("w", suffix=".b64", delete=False) as f:
        f.write(b64)
    out = subprocess.check_output([sys.executable, str(ROOT / "china" / "ingest.py"), "cca", f.name], text=True)
    print(out)
    status("cca", True, out.strip())


if __name__ == "__main__":
    for step in sys.argv[1:] or ["gacc", "cca"]:
        try:
            {"gacc": gacc, "cca": cca}[step]()
        except Exception as e:
            print(step, "failed:", e)
            status(step, False, e)
