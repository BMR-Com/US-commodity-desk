import os, json, subprocess, requests
from pathlib import Path
OUT = Path("tmp/out3"); OUT.mkdir(parents=True, exist_ok=True)
KEY = (os.getenv("AMS_API_KEY") or "").strip(); H = {"User-Agent": "Mozilla/5.0 (research; bmr-com)"}
B = "https://marsapi.ams.usda.gov/services/v1.2/reports/"
def sample(slug, params=None):
    try:
        r = requests.get(B + str(slug), params=params or {"allSections": "true"}, auth=(KEY, ""), timeout=(30, 300)); j = r.json()
        secs = j if isinstance(j, list) else [j]
        out = [{"section": s.get("reportSection"), "stats": s.get("stats"), "first": (s.get("results") or [])[:4]} for s in secs]
        (OUT / f"mars_{slug}.json").write_text(json.dumps(out, indent=1))
    except Exception as e:
        (OUT / f"mars_{slug}.err").write_text(repr(e))
sample(3895, {"allSections": "true", "q": "report_begin_date=01/01/2025:10/31/2026"})
sample(1625); sample(1652); sample(3024); sample(3024, {"q": "report_begin_date=01/01/2026:10/31/2026"})
r = requests.get("https://www.ams.usda.gov/mnreports/cnaasrd.pdf", headers=H, timeout=120); (OUT / "cnaasrd.pdf").write_bytes(r.content)
subprocess.run(["pdftotext", "-layout", str(OUT / "cnaasrd.pdf"), str(OUT / "cnaasrd.txt")])
for u in ["https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=3024", "https://mymarketnews.ams.usda.gov/viewReport/3024"]:
    try:
        h = requests.get(u, headers=H, timeout=(30, 200)).text; (OUT / ("p_" + u.split("/")[-1].replace("?", "_")[:40] + ".html")).write_text(h[:300000])
    except Exception as e:
        (OUT / "p.err").write_text(repr(e))
