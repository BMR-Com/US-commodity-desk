"""Probe 4: FSA crop acreage data page and files."""
import json, re, requests, io, zipfile
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
out = {}
pages = ["https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data",
         "https://www.fsa.usda.gov/news-room/efoia/electronic-reading-room/frequently-requested-information/crop-acreage-data/index"]
links = []
for u in pages:
    try:
        r = requests.get(u, headers=H, timeout=90, allow_redirects=True)
        out[u] = {"status": r.status_code, "final": r.url, "len": len(r.text)}
        if r.status_code == 200:
            ls = re.findall(r'href="([^"]+)"[^>]*>([^<]{0,160})<', r.text)
            ls = [(h, t.strip()) for h, t in ls if re.search(r"xlsx|xls|zip|acre", h + t, re.I)]
            out[u]["links"] = ls[:200]; links += ls
            t = re.sub(r"<[^>]+>", " ", r.text); out[u]["text"] = re.sub(r"\s+", " ", t)[:5000]
    except Exception as e:
        out[u] = {"err": str(e)[:200]}
# try downloading the newest-looking 2026 file and one 2025 file
def absu(h): return h if h.startswith("http") else "https://www.fsa.usda.gov" + h
got = 0
for h, t in links:
    if re.search(r"\.(xlsx|zip)", h, re.I) and ("2026" in h + t or "2025" in h + t) and got < 4:
        try:
            r = requests.get(absu(h), headers=H, timeout=180)
            nm = "probe/fsa_" + re.sub(r"[^A-Za-z0-9._-]", "_", h.split("/")[-1])[:80]
            out.setdefault("dl", []).append([h, r.status_code, len(r.content), r.headers.get("content-type")])
            if r.status_code == 200 and len(r.content) < 40_000_000:
                open(nm, "wb").write(r.content); got += 1
        except Exception as e:
            out.setdefault("dl", []).append([h, str(e)[:150]])
open("probe/fsa_probe.json", "w").write(json.dumps(out, indent=1))
print(json.dumps({k: (v.get("status"), len(v.get("links", []))) if isinstance(v, dict) else v for k, v in out.items()}, indent=0)[:3000])
