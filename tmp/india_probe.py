import json, os, requests, time
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36","X-Requested-With":"XMLHttpRequest"}
B="https://www.caionline.in/"
os.makedirs("tmp/india_probe3",exist_ok=True); out={}
S=requests.Session(); S.headers.update(H); S.get(B,timeout=60)
P=[("exp_37","raw/cotton/export/data",{"season":"37","unit":"0","variety":"5201"}),
   ("exp_36","raw/cotton/export/data",{"season":"36","unit":"0","variety":"5201"}),
   ("imp_37","raw/cotton/import/data",{"season":"37","unit":"0","variety":"5201"}),
   ("imp_36","raw/cotton/import/data",{"season":"36","unit":"0","variety":"5201"}),
   ("yexp_36","yarn/cotton/export/data",{"season":"36","unit":"0","variety":"5205"}),
   ("mon_2026_9","details/cai/monthly",{"year":"81","year_name":"2026","month":"9","unit":"0"}),
   ("mon_2026_10","details/cai/monthly",{"year":"81","year_name":"2026","month":"10","unit":"0"}),
   ("mon_2026_all","details/cai/monthly",{"year":"81","year_name":"2026","month":"","unit":"0"}),
   ("bs_2026","news_reports/cab_balancesheet/filter",{"year":"2026","weight_type":"kg"}),
   ("bs_2027","news_reports/cab_balancesheet/filter",{"year":"2027","weight_type":"kg"}),
   ("ap_2026","news_reports/cab_area_production/filter",{"year":"2026","weight_type":"kg"}),
   ("ap_2025","news_reports/cab_area_production/filter",{"year":"2025","weight_type":"kg"}),
   ("arr_d1","details/cai/monthly-arrivals/by/date",{"date":"30-09-2026"}),
   ("arr_d2","details/cai/monthly-arrivals/by/date",{"date":"09-2026"}),
   ("darr","details/cai/daily-arrivals/by/date",{"date":"28-10-2026"}),
   ("msp_proc","news_reports/cci_msp_procurement/filter",{"year":"2026","weight_type":"kg"}),
]
for k,u,d in P:
    time.sleep(1.5)
    try:
        r=S.post(B+u,files={x:(None,v) for x,v in d.items()},headers={"Referer":B+u.rsplit('/',1)[0]},timeout=(20,90))
        out[k]={"status":r.status_code,"bytes":len(r.content)}
        open(f"tmp/india_probe3/{k}.txt","w").write(r.text[:200000])
    except Exception as e: out[k]={"error":repr(e)[:200]}
    print(k,out[k])
for m in ["Aug-2026","Sep-2026","Oct-2026","Jul-2026"]:
    u=B+f"uploads/press/doc/CAI_Monthly_Report_{m}.pdf"
    try:
        r=S.get(u,timeout=60); out[m]={"status":r.status_code,"bytes":len(r.content),"type":r.headers.get("content-type")}
        if r.ok and r.content[:4]==b"%PDF": open(f"tmp/india_probe3/cai_{m}.pdf","wb").write(r.content)
    except Exception as e: out[m]={"error":repr(e)[:200]}
    print(m,out[m])
r=requests.get("https://apps.fas.usda.gov/psdonline/downloads/psd_cotton_csv.zip",timeout=120)
import zipfile,io; z=zipfile.ZipFile(io.BytesIO(r.content)); t=z.read(z.namelist()[0]).decode().splitlines()
open("tmp/india_probe3/psd_india.csv","w").write("\n".join([t[0]]+[l for l in t if '"India"' in l or ',India,' in l]))
json.dump(out,open("tmp/india_probe3/summary.json","w"),indent=1)
