"""Probe Australian cotton data sources from GitHub Actions (no keys, no credentials)."""
import json, re, requests
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
U = {
 "abares_crop_pdf": "https://daff.ent.sirsidynix.net.au/client/en_AU/search/asset/1038523/0/__AustCropRrt20260901_v1.0.0.pdf",
 "abares_crop_xlsx": "https://daff.ent.sirsidynix.net.au/client/en_AU/search/asset/1038523/2/__AustCropRrt20260901_v1.0.0.xlsx",
 "abares_state_xlsx": "https://daff.ent.sirsidynix.net.au/client/en_AU/search/asset/1038523/3/__AustCropRrt20260901_v1.0.0.xlsx",
 "abares_crop_page": "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/australian-crop-report/september-2026",
 "abares_data_page": "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/data",
 "abares_acr_index": "https://www.agriculture.gov.au/abares/research-topics/agricultural-outlook/australian-crop-report",
 "datagovau_ckan": "https://data.gov.au/data/api/3/action/package_search?q=abares%20crop%20report&rows=20",
 "datagovau_ckan2": "https://data.gov.au/data/api/3/action/package_search?q=agricultural%20commodity%20statistics&rows=20",
 "bom_kiwis": "http://www.bom.gov.au/waterdata/services?service=kisters&type=queryServices&request=getStationList&datasource=0&format=json&station_name=Copeton*",
 "bom_waterstorage": "http://www.bom.gov.au/waterdata/",
 "bom_storage_json": "https://water.bom.gov.au/waterstorage/resources/data/storages.json",
 "waternsw_rt": "https://realtimedata.waternsw.com.au/cgi/webservice.pl?%7B%22function%22:%22get_ts_traces%22,%22version%22:%222%22,%22params%22:%7B%22site_list%22:%22418026%22,%22datasource%22:%22CP%22,%22varfrom%22:%22130.00%22,%22varto%22:%22130.00%22,%22start_time%22:%2220261001000000%22,%22end_time%22:%2220261110000000%22,%22data_type%22:%22mean%22,%22interval%22:%22day%22,%22multiplier%22:%221%22%7D%7D",
 "waternsw_page": "https://www.waternsw.com.au/nsw-dams/dam-levels",
 "nsw_awd": "https://water.dpie.nsw.gov.au/our-work/allocations-availability/allocations/available-water-determinations",
 "nsw_awd2": "https://www.dcceew.nsw.gov.au/water/allocations-availability/allocations/available-water-determinations",
 "sunwater": "https://www.sunwater.com.au/dam-levels/",
 "qld_water_monitor": "https://water-monitoring.information.qld.gov.au/",
 "mdba_storage": "https://www.mdba.gov.au/water-management/storages",
 "open_meteo": "https://archive-api.open-meteo.com/v1/archive?latitude=-29.47&longitude=149.85&start_date=2026-10-01&end_date=2026-10-31&daily=precipitation_sum",
 "nasa_power": "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=AG&longitude=149.85&latitude=-29.47&start=2020&end=2025&format=JSON",
 "cotton_aus": "https://cottonaustralia.com.au/statistics",
 "cotton_aus2": "https://cottonaustralia.com.au/",
 "abs_api": "https://data.api.abs.gov.au/rest/dataflow/ABS",
}
LINKS = {"abares_data_page", "abares_acr_index", "abares_crop_page", "nsw_awd", "nsw_awd2", "waternsw_page", "cotton_aus", "sunwater", "mdba_storage"}
out = {}
for k, u in U.items():
    try:
        r = requests.get(u, headers=H, timeout=60)
        ct = r.headers.get("content-type", "")
        out[k] = {"status": r.status_code, "ct": ct, "len": len(r.content),
                  "head": r.text[:300] if ("text" in ct or "json" in ct) else ""}
        if r.status_code == 200 and k in LINKS:
            out[k]["links"] = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|pdf|docx)[^"]*)"', r.text)))[:120]
        if r.status_code == 200 and ("json" in ct or k.startswith("datagovau")):
            open(f"probe/au_{k}.json", "wb").write(r.content[:2000000])
        if r.status_code == 200 and k.endswith("xlsx"):
            open(f"probe/au_{k}.xlsx", "wb").write(r.content)
    except Exception as e:
        out[k] = {"err": str(e)[:300]}
open("probe/au_probe.json", "w").write(json.dumps(out, indent=1))
print(json.dumps({k: (v.get("status"), v.get("len"), v.get("err")) for k, v in out.items()}, indent=0))
