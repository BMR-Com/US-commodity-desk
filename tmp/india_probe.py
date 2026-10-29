import json, os, re, requests, hashlib
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}
K="579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
U={k:"https://www.caionline.in/"+k.replace("~","/") for k in ["news_reports~cab_area_production","news_reports~cab_balancesheet","news_reports~cci_msp_procurement","news_reports~msp_kapas","raw~cotton~export","raw~cotton~import","yarn~cotton~export","details~cai~daily-arrivals","details~cai~monthly-arrivals","reports~cai~monthly","cai~press","cai~publications","news_reports~details~20","news_reports~details~19","news~4016","news~more"]}
U.update({"comtrade_x":"https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=699&cmdCode=5201&flowCode=X&period=202607","comtrade_m":"https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=699&cmdCode=5201&flowCode=M&period=202607","comtrade_a":"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=699&cmdCode=5201&flowCode=M&period=2025","psd_csv":"https://apps.fas.usda.gov/psdonline/downloads/psd_cotton_csv.zip","pib_rss":"https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"})
os.makedirs("tmp/india_probe",exist_ok=True); out={}
for k,u in U.items():
    import time; time.sleep(2)
    try:
        r=requests.get(u,headers=H,timeout=(20,60))
        out[k]={"status":r.status_code,"bytes":len(r.content),"type":r.headers.get("content-type","")[:60],"final":r.url}
        ext=".pdf" if "pdf" in out[k]["type"] else ".zip" if "zip" in out[k]["type"] else ".txt"
        if ext==".txt": open(f"tmp/india_probe/{k.replace('~','_')}.txt","w").write(r.text[:150000])
        elif r.content and len(r.content)<3e6: open(f"tmp/india_probe/{k.replace('~','_')}{ext}","wb").write(r.content)
        if k=="psd_csv" and r.ok:
            import zipfile,io,csv
            z=zipfile.ZipFile(io.BytesIO(r.content)); n=z.namelist()[0]; rows=[l for l in z.read(n).decode().splitlines() if '"India"' in l]
            open("tmp/india_probe/psd_india.csv","w").write(z.read(n).decode().splitlines()[0]+"\n"+"\n".join(rows[-400:]))
    except Exception as e:
        out[k]={"error":repr(e)[:200]}
    print(k,out[k])
json.dump(out,open("tmp/india_probe/summary.json","w"),indent=1)
