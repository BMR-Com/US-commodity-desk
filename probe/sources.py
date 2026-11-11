"""Probe 2: Australian cotton history and storage sources from GitHub Actions."""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
out = {}
def get(k, u, save=None, **kw):
    try:
        r = requests.get(u, headers=H, timeout=90, **kw)
        out[k] = {"status": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(r.content), "head": r.text[:400] if "html" in r.headers.get("content-type","") or "json" in r.headers.get("content-type","") else ""}
        if save and r.status_code == 200:
            open("probe/" + save, "wb").write(r.content)
        return r
    except Exception as e:
        out[k] = {"err": str(e)[:300]}
W = "http://data.daff.gov.au/data/warehouse/"
get("acs2017_cotton", W + "agcstd9abcc002/agcstd9abcc0022017_IugZg/ACS2017_Cotton_Tables_v1.0.0.xlsx", "au_acs2017_cotton.xlsx")
get("acs2017_water", W + "agcstd9abcc002/agcstd9abcc0022017_IugZg/ACS2017_WaterTables_v1.0.0.xlsx", "au_acs2017_water.xlsx")
get("acr2018_state", W + "aucrpd9abcc003/aucrpd9aba_20180911_Z0Srg/AustCropRrt20180911_StateCropData_v1.0.0.xlsx", "au_acr201809_state.xlsx")
get("acr2018_crop", W + "aucrpd9abcc003/aucrpd9aba_20180911_Z0Srg/AustCropRrt20180911_CropData_v1.0.0.xlsx", "au_acr201809_crop.xlsx")
# newer ABARES on data.gov.au?
for k, q in {"ckan_acs": "agricultural commodity statistics", "ckan_acr": "australian crop report", "ckan_cotton": "cotton"}.items():
    r = get(k, "https://data.gov.au/data/api/3/action/package_search", params={"q": q, "rows": 200, "sort": "metadata_modified desc"})
    if r is not None and r.status_code == 200:
        res = r.json()["result"]["results"]
        out[k]["titles"] = [(p["title"], p["name"], [x.get("url") for x in p["resources"]][:30]) for p in res if any(w in p["title"].lower() for w in ("crop report", "commodity statistics", "cotton", "commodities"))][:80]
# ABS dataflows with agriculture
r = get("abs_flows", "https://data.api.abs.gov.au/rest/dataflow/ABS", headers={**H, "Accept": "application/vnd.sdmx.structure+json"})
if r is not None and r.status_code == 200:
    try:
        fl = r.json()["data"]["dataflows"]
        out["abs_flows"]["agri"] = [(f["id"], f.get("name")) for f in fl if re.search(r"agri|crop|commodit|cotton|land|water", json.dumps(f.get("name", "")), re.I)]
    except Exception as e:
        out["abs_flows"]["parse"] = str(e)[:200]; open("probe/au_abs_flows.txt", "w").write(r.text[:300000])
# BOM KiWIS storages and timeseries
K = "http://www.bom.gov.au/waterdata/services"
st = {}
for nm in ["COPETON*", "KEEPIT*", "SPLIT ROCK*", "BURRENDONG*", "BURRINJUCK*", "BLOWERING*", "WYANGALA*", "PINDARI*", "GLENLYON*", "BEARDMORE*", "LESLIE*", "COOBY*", "FAIRBAIRN*", "CHAFFEY*", "HUME*", "DARTMOUTH*", "MENINDEE*", "COOLMUNDA*", "LAKE MENINDEE*"]:
    r = get("kiwis_" + nm, K, params={"service": "kisters", "type": "queryServices", "request": "getStationList", "datasource": 0, "format": "json", "station_name": nm})
    try: st[nm] = r.json()[1:]
    except Exception: pass
out["stations"] = st
if st.get("COPETON*"):
    sid = st["COPETON*"][0][1]
    r = get("kiwis_tslist", K, params={"service": "kisters", "type": "queryServices", "request": "getTimeseriesList", "datasource": 0, "format": "json", "station_no": sid, "returnfields": "ts_id,ts_name,parametertype_name,ts_unitname,coverage"})
    try:
        tl = r.json(); out["kiwis_tslist"]["rows"] = tl[:60]
        cand = [x for x in tl[1:] if "olume" in str(x) or "torage" in str(x)]
        out["kiwis_cand"] = cand[:20]
        for x in cand[:4]:
            rr = get("kiwis_vals_" + x[0], K, params={"service": "kisters", "type": "queryServices", "request": "getTimeseriesValues", "datasource": 0, "format": "json", "ts_id": x[0], "from": "1990-01-01", "to": "2026-11-10"})
            try:
                j = rr.json(); data = j[0]["data"]; out["kiwis_vals_" + x[0]]["n"] = len(data); out["kiwis_vals_" + x[0]]["first_last"] = [data[:2], data[-3:]]
            except Exception as e: out["kiwis_vals_" + x[0]]["perr"] = str(e)[:200]
    except Exception as e:
        out["kiwis_tslist"]["perr"] = str(e)[:200]
r = get("cotton_aus_stats", "https://cottonaustralia.com.au/statistics")
if r is not None and r.status_code == 200:
    t = re.sub(r"<[^>]+>", " ", r.text); t = re.sub(r"\s+", " ", t)
    out["cotton_aus_stats"]["text"] = t[:6000]; out["cotton_aus_stats"]["links"] = sorted(set(re.findall(r'href="([^"]+)"', r.text)))[:150]
get("nsw_awd_pdf", "https://water.dpie.nsw.gov.au/sites/default/files/2026-10/AWD-macquarie-20261013.pdf", "au_awd_macq.pdf")
get("nsw_awd_pdf2", "https://water.dpie.nsw.gov.au/sites/default/files/2026-09/awd-namoi-20260904.pdf", "au_awd_namoi.pdf")
open("probe/au_probe2.json", "w").write(json.dumps(out, indent=1, default=str))
print(json.dumps({k: (v.get("status"), v.get("len"), v.get("err")) for k, v in out.items() if isinstance(v, dict)}, indent=0))
