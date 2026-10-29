import json, os, re, requests, hashlib
H={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36","Accept-Language":"en-US,en;q=0.9"}
K="579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
U={
 "cai_home":"https://www.caionline.in/",
 "cai_crop":"https://www.caionline.in/details/cai/crop-statistics",
 "cai_news":"https://www.caionline.in/details/cai/press-release",
 "cai_cotai":"https://www.cotai.org.in/",
 "texmin_bs":"https://texmin.nic.in/sites/default/files/Cotton%20Balance%20Sheet.pdf",
 "texmin_stats":"https://texmin.nic.in/textile-data",
 "cci_home":"https://cotcorp.org.in/",
 "cci_stats":"https://cotcorp.org.in/statistics.aspx",
 "cci_sales":"https://cotcorp.org.in/CottonSales.aspx",
 "agri_home":"https://agriwelfare.gov.in/",
 "agri_major":"https://agriwelfare.gov.in/en/Major",
 "pib_rss":"https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
 "pib_search":"https://pib.gov.in/allRel.aspx",
 "upag":"https://upag.gov.in/",
 "upag_api":"https://upag.gov.in/api/dash/getcropDetails",
 "desagri":"https://desagri.gov.in/",
 "tradestat":"https://tradestat.commerce.gov.in/meidb/",
 "tradestat_new":"https://tradestat.commerce.gov.in/eidb/",
 "datagov_agmark":f"https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?api-key={K}&format=json&filters[commodity]=Cotton&limit=5",
 "datagov_cat":f"https://api.data.gov.in/lists?format=json&filters[title]=cotton&limit=50&api-key={K}",
 "comtrade_x":"https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=699&cmdCode=5201&flowCode=X&period=202607,202608",
 "comtrade_m":"https://comtradeapi.un.org/public/v1/preview/C/M/HS?reporterCode=699&cmdCode=5201&flowCode=M&period=202607,202608",
 "psd_csv":"https://apps.fas.usda.gov/psdonline/downloads/psd_cotton_csv.zip",
 "mcx":"https://www.mcxindia.com/market-data/spot-market-price",
 "cicr":"https://cicr.icar.gov.in/datasets-tables",
 "texprocil":"https://www.texprocil.org/",
 "agmarknet":"https://agmarknet.gov.in/",
 "ncdex":"https://www.ncdex.com/markets/spotprices",
}
os.makedirs("tmp/india_probe",exist_ok=True); out={}
for k,u in U.items():
    try:
        r=requests.get(u,headers=H,timeout=(20,60))
        out[k]={"status":r.status_code,"bytes":len(r.content),"type":r.headers.get("content-type","")[:60],"final":r.url}
        ext=".pdf" if "pdf" in out[k]["type"] else ".zip" if "zip" in out[k]["type"] else ".txt"
        if ext==".txt": open(f"tmp/india_probe/{k}.txt","w").write(r.text[:150000])
        elif r.content and len(r.content)<3e6: open(f"tmp/india_probe/{k}{ext}","wb").write(r.content)
        if k=="psd_csv" and r.ok:
            import zipfile,io,csv
            z=zipfile.ZipFile(io.BytesIO(r.content)); n=z.namelist()[0]; rows=[l for l in z.read(n).decode().splitlines() if '"India"' in l]
            open("tmp/india_probe/psd_india.csv","w").write(z.read(n).decode().splitlines()[0]+"\n"+"\n".join(rows[-400:]))
    except Exception as e:
        out[k]={"error":repr(e)[:200]}
    print(k,out[k])
json.dump(out,open("tmp/india_probe/summary.json","w"),indent=1)
