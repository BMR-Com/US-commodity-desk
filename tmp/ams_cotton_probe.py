import os, json, subprocess, requests
from pathlib import Path
OUT = Path("tmp/out2"); OUT.mkdir(parents=True, exist_ok=True)
KEY = (os.getenv("AMS_API_KEY") or "").strip(); H = {"User-Agent": "Mozilla/5.0 (research; bmr-com)"}
for n in ["cnwwcmr", "cn_fc_off"]:
    r = requests.get(f"https://www.ams.usda.gov/mnreports/{n}.pdf", headers=H, timeout=120); (OUT / f"{n}.pdf").write_bytes(r.content)
    subprocess.run(["pdftotext", str(OUT / f"{n}.pdf"), str(OUT / f"{n}_raw.txt")])
for s in (1613, 3895):
    try:
        r = requests.get(f"https://marsapi.ams.usda.gov/services/v1.2/reports/{s}", params={"allSections": "true"}, auth=(KEY, ""), timeout=120)
        (OUT / f"mars_{s}.json").write_text(r.text[:400000])
    except Exception as e:
        (OUT / f"mars_{s}.err").write_text(repr(e))
# do older weekly reviews exist (archive) for history/backfill?
for u in ["https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=&name=cnwwcmr", "https://apps.ams.usda.gov/Cotton/Historical%20Weekly%20Reports/"]:
    try:
        (OUT / ("idx_" + str(abs(hash(u)))[:6] + ".html")).write_text(requests.get(u, headers=H, timeout=60).text[:300000])
    except Exception as e:
        pass
