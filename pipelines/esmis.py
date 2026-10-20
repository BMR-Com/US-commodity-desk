"""Archive NASS report text files from ESMIS (first prints, as released), no key.

For each publication, crawl the listing pages and download every .txt release not yet stored to
data/esmis/<slug>/<filename>. Parsing happens in models/ (first-print values + release dates for
honest backtests).
"""
import re, sys, time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "esmis"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
BASE = "https://esmis.nal.usda.gov"
PUBS = {  # slug: oldest year to keep
    "hogs-and-pigs": 2005,
    "cattle-feed": 2005,
    "milk-production": 2010,
    "cold-storage": 2010,
    "dairy-products": 2010,
}


def get(url):
    for i in range(3):
        try:
            r = requests.get(url, headers=H, timeout=120)
            if r.status_code == 200:
                return r
        except Exception as e:
            print("  err", e)
        time.sleep(3 * (i + 1))
    return None


def year_of(name):
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", name) or re.search(r"[a-z]{4}(\d{2})(\d{2})\.txt$", name)
    if not m:
        return None
    return int(m.group(3)) if len(m.groups()) == 3 else 2000 + int(m.group(2))


def crawl(slug, oldest):
    d = OUT / slug
    d.mkdir(parents=True, exist_ok=True)
    have = {p.name for p in d.glob("*.txt")}
    new = 0
    for page in range(0, 60):
        r = get(f"{BASE}/publication/{slug}?page={page}")
        if r is None:
            break
        files = sorted(set(re.findall(r'href="([^"]+\.txt)"', r.text)))
        if not files:
            break
        older = 0
        for f in files:
            name = Path(f).name
            y = year_of(name)
            if y is not None and y < oldest:
                older += 1
                continue
            key = name
            if key in have:
                continue
            rr = get(BASE + f if f.startswith("/") else f)
            if rr is None:
                continue
            (d / key).write_bytes(rr.content)
            have.add(key)
            new += 1
            time.sleep(0.3)
    print(f"{slug}: {new} new, {len(have)} stored")


if __name__ == "__main__":
    for slug in (sys.argv[1:] or PUBS):
        crawl(slug, PUBS.get(slug, 2005))
