"""Probe 2: save raw responses for parsing work."""
import json, re, time, os, requests
HB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
os.makedirs("probe/m", exist_ok=True)
out = {}
def save(nm, url, fn, hdr=HB, **kw):
    try:
        r = requests.get(url, headers=hdr, timeout=90, **kw)
        out[nm] = {"url": url, "status": r.status_code, "ct": r.headers.get("content-type"), "len": len(r.content), "final": r.url}
        if r.status_code == 200:
            open("probe/m/" + fn, "wb").write(r.content)
        return r
    except Exception as e:
        out[nm] = {"url": url, "err": str(e)[:300]}
save("cftc", "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$select=market_and_exchange_names,cftc_contract_market_code,max(report_date_as_yyyy_mm_dd) as last,max(open_interest_all) as oi&$where=report_date_as_yyyy_mm_dd>'2026-01-01' AND (commodity_subgroup_name='PRECIOUS METALS' OR commodity_subgroup_name='BASE METALS')&$group=market_and_exchange_names,cftc_contract_market_code&$limit=500", "cftc.json")
save("cftc_al_hist", "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$select=market_and_exchange_names,cftc_contract_market_code,min(report_date_as_yyyy_mm_dd) as first,max(report_date_as_yyyy_mm_dd) as last,count(*) as n&$where=upper(market_and_exchange_names) like '%25ALUMIN%25'&$group=market_and_exchange_names,cftc_contract_market_code&$limit=500", "cftc_al.json")
save("wgc_robots", "https://www.gold.org/robots.txt", "wgc_robots.txt")
save("wgc_gdt_xlsx", "https://www.gold.org/download/file/21333/GDT%20Tables_Q326_EN.xlsx", "gdt_q326.xlsx")
r = save("wgc_gdt_index", "https://www.gold.org/goldhub/research/gold-demand-trends", "gdt_index.html")
save("wgc_cb_page", "https://www.gold.org/goldhub/data/gold-reserves-by-country", "wgc_cb.html")
save("wgc_monthly_cb", "https://www.gold.org/goldhub/data/monthly-central-bank-statistics", "wgc_cbm.html")
save("wgc_etf_page", "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows", "wgc_etf.html")
save("iai_page", "https://international-aluminium.org/statistics/primary-aluminium-production/", "iai.html")
for p in ["", "/statistics", "/statistics/1", "/v1/statistics", "/datasets"]:
    save("alvis" + p, "https://alvis.international-aluminium.org/api" + p, "alvis" + p.replace("/", "_") + ".txt")
save("icsg_press", "https://icsg.org/press-releases/", "icsg_press.html")
save("icsg_sitemap", "https://icsg.org/sitemap.xml", "icsg_sitemap.xml")
time.sleep(20)
save("icsg_wp_pages", "https://icsg.org/wp-json/wp/v2/pages?per_page=20&orderby=modified&_fields=id,date,modified,link,title", "icsg_pages.json")
save("silver_sd", "https://silverinstitute.org/silver-supply-demand/", "silver_sd.html")
save("usgs_sb_item", "https://www.sciencebase.gov/catalog/item/696a75d5d4be0228872d3bf8?format=json", "usgs_sb_item.json")
save("usgs_sb_q", "https://www.sciencebase.gov/catalog/items?q=Mineral%20Commodity%20Summaries%202026&format=json&max=10&fields=title,link,files", "usgs_sb_q.json")
save("usgs_mcs_cu", "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-copper.pdf", "mcs2026_cu.pdf")
save("wm_cu", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash", "wm_cu.html")
save("wm_list", "https://www.westmetall.com/en/markdaten.php", "wm_list.html")
save("wm_cu_stock", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_stock", "wm_cu_stock.html")
save("gld_page", "https://www.spdrgoldshares.com/usa/", "gld.html")
save("gld_hist", "https://www.spdrgoldshares.com/usa/historical-data/", "gld_hist.html")
save("gld_xlsx", "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.xlsx", "gld_archive.xlsx")
save("slv_page", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund", "slv.html")
save("iau_page", "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund", "iau.html")
save("slv_json", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund/1467271812596.ajax?tab=all&fileType=json", "slv_ajax.json")
save("cme_fedwatch", "https://www.cmegroup.com/ftp/", "x")
json.dump(out, open("probe/m/out.json", "w"), indent=1)
print(json.dumps(out, indent=0))
