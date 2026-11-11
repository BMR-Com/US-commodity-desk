"""Probe 3: ABS agriculture dataflows; ABARES archive over https; USDA PSD zip."""
import json, re, requests, io, zipfile, csv
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
out = {}
try:
    r = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers={**H, "Accept": "application/vnd.sdmx.structure+json"}, timeout=90)
    out["abs_status"] = r.status_code
    fl = r.json()["data"]["dataflows"]
    out["abs_agri"] = [(f["id"], f.get("version"), f.get("name")) for f in fl if re.search(r"agri|crop|commodit|cotton|water acc|land man", json.dumps(f.get("name", "")), re.I)]
except Exception as e:
    out["abs_err"] = str(e)[:300]
for fid, ver, nm in out.get("abs_agri", [])[:12]:
    try:
        r = requests.get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{fid}/{ver}?references=codelist", headers={**H, "Accept": "application/vnd.sdmx.structure+json"}, timeout=90)
        j = r.json()["data"]
        cl = {c["id"]: [(x["id"], x.get("name")) for x in c.get("codes", []) if re.search(r"otton", json.dumps(x.get("name", "")), re.I)] for c in j.get("codelists", [])}
        dims = [d["id"] for d in j["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"]]
        out["abs_dsd_" + fid] = {"dims": dims, "cotton_codes": {k: v for k, v in cl.items() if v}, "codelists": list(cl)}
    except Exception as e:
        out["abs_dsd_" + fid] = {"err": str(e)[:200]}
for k, u in {"daff_https": "https://data.daff.gov.au/data/warehouse/agcstd9abcc002/agcstd9abcc0022017_IugZg/ACS2017_Cotton_Tables_v1.0.0.xlsx",
             "agri_acs": "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/data"}.items():
    try:
        r = requests.get(u, headers=H, timeout=150); out[k] = [r.status_code, len(r.content), r.headers.get("content-type")]
        if r.status_code == 200 and k == "agri_acs":
            out[k].append(sorted(set(re.findall(r'href="([^"]+)"', r.text)))[:400])
        if r.status_code == 200 and k == "daff_https": open("probe/au_acs2017_cotton.xlsx", "wb").write(r.content)
    except Exception as e:
        out[k] = str(e)[:200]
open("probe/au_probe3.json", "w").write(json.dumps(out, indent=1, default=str))
print(json.dumps(out, default=str)[:3000])
