"""Probe metals data sources from GitHub Actions: status, content type, first bytes, robots.txt."""
import json, re, time, traceback, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; +https://bmr-com.github.io/US-commodity-desk/)"}
HB = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
out = {}
def get(nm, url, hdr=H, keep=600, save=None):
    try:
        r = requests.get(url, headers=hdr, timeout=60)
        out[nm] = {"url": url, "status": r.status_code, "ct": r.headers.get("content-type", ""), "len": len(r.content), "head": r.text[:keep] if "text" in r.headers.get("content-type", "") or "json" in r.headers.get("content-type", "") or "csv" in r.headers.get("content-type","") else repr(r.content[:200])}
        if save and r.status_code == 200:
            open("probe/" + save, "wb").write(r.content)
        return r
    except Exception as e:
        out[nm] = {"url": url, "err": str(e)[:300]}
# CFTC metals codes
r = get("cftc_metals", "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$select=market_and_exchange_names,cftc_contract_market_code,commodity_subgroup_name,max(report_date_as_yyyy_mm_dd) as last,max(open_interest_all) as oi&$where=report_date_as_yyyy_mm_dd>'2025-06-01' AND (commodity_group_name='NATURAL RESOURCES')&$group=market_and_exchange_names,cftc_contract_market_code,commodity_subgroup_name&$limit=500", keep=50000)
# Yahoo
for s in ["GC=F", "SI=F", "HG=F", "ALI=F", "PL=F", "PA=F", "AUP=F", "GCG27.CMX", "SIH27.CMX", "HGH27.CMX", "ALIF27.CMX", "GLD", "SLV", "IAU", "COPX", "DX-Y.NYB", "^TNX"]:
    get("yahoo_" + s, f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=5d&interval=1d", HB, keep=300)
# Yahoo quoteSummary for ETF shares outstanding
get("yahoo_qs_GLD", "https://query1.finance.yahoo.com/v7/finance/quote?symbols=GLD,SLV,IAU", HB, keep=800)
# TradingView
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed()
    for ex, sym in [("COMEX", "GC1!"), ("COMEX", "SI1!"), ("COMEX", "HG1!"), ("COMEX", "ALI1!"), ("COMEX", "AUP1!"), ("COMEX", "ALIG2027"), ("COMEX", "GCG2027"), ("COMEX", "GCZ2020"), ("COMEX", "ALIZ2022"),
                    ("LME", "CA1!"), ("LME", "MCU1!"), ("LME", "CA3M"), ("LME", "AH1!"), ("LME", "MAL1!"), ("TVC", "GOLD"), ("TVC", "SILVER"), ("SHFE", "CU1!"), ("SHFE", "AL1!"), ("COMEX", "HGH2027"),
                    ("ECONOMICS", "USGDP"), ("NYMEX", "PL1!"), ("NYMEX", "PA1!"), ("FX_IDC", "USDCNY"), ("COMEX", "MUP1!"), ("COMEX", "EDP1!"), ("CME", "CUP1!")]:
        try:
            d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=10)
            out[f"tv_{ex}_{sym}"] = None if d is None else {"n": len(d), "last": str(d.index[-1]), "close": float(d.close.iloc[-1])}
        except Exception as e:
            out[f"tv_{ex}_{sym}"] = {"err": str(e)[:200]}
        time.sleep(1)
except Exception as e:
    out["tv"] = {"err": traceback.format_exc()[-400:]}
# CME warehouse stocks
for nm in ["Gold_Stocks.xls", "Silver_stocks.xls", "Copper_Stocks.xls", "Aluminum_Stocks.xls", "Platinum_Palladium_Stocks.xls"]:
    get("cme_" + nm, "https://www.cmegroup.com/delivery_reports/" + nm, HB, keep=200)
get("cme_robots", "https://www.cmegroup.com/robots.txt", HB, keep=3000)
# ETFs
get("spdr_gld_archive", "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv", HB, keep=800, save="gld_archive.csv")
get("spdr_robots", "https://www.spdrgoldshares.com/robots.txt", HB, keep=2000)
get("ishares_slv", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund/1467271812596.ajax?fileType=csv&fileName=SLV_holdings&dataType=fund", HB, keep=1500)
get("ishares_iau", "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund/1467271812596.ajax?fileType=csv&fileName=IAU_holdings&dataType=fund", HB, keep=1500)
get("ishares_slv_page", "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund", HB, keep=300)
get("ishares_robots", "https://www.ishares.com/robots.txt", HB, keep=3000)
# WGC
get("wgc_robots", "https://www.gold.org/robots.txt", HB, keep=4000)
get("wgc_gdt", "https://www.gold.org/goldhub/research/gold-demand-trends", HB, keep=500)
r = get("wgc_gdt_latest", "https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q3-2026", HB, keep=500)
if r is not None and r.status_code == 200:
    out["wgc_gdt_latest"]["links"] = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|pdf))"', r.text)))[:40]
    out["wgc_gdt_latest"]["tonnes"] = re.findall(r"[^.]{0,120}\d[\d,.]*\s*t(?:onnes)?\b[^.]{0,80}", r.text)[:15]
get("wgc_cb", "https://www.gold.org/goldhub/data/gold-reserves-by-country", HB, keep=500)
get("wgc_cb_monthly", "https://www.gold.org/goldhub/gold-focus", HB, keep=300)
# Silver Institute
get("silver_robots", "https://www.silverinstitute.org/robots.txt", HB, keep=2000)
r = get("silver_sd", "https://silverinstitute.org/silver-supply-demand/", HB, keep=300)
if r is not None and r.status_code == 200:
    open("probe/silver_sd.html", "w").write(r.text)
# ICSG
get("icsg_robots", "https://icsg.org/robots.txt", HB, keep=2000)
r = get("icsg_press", "https://icsg.org/press-releases/", HB, keep=300)
if r is not None and r.status_code == 200:
    out["icsg_press"]["links"] = sorted(set(re.findall(r'href="(https?://icsg\.org/[^"]+)"', r.text)))[:80]
    open("probe/icsg_press.html", "w").write(r.text)
get("icsg_wp", "https://icsg.org/wp-json/wp/v2/posts?per_page=10&_fields=id,date,link,title", HB, keep=4000)
# IAI
get("iai_robots", "https://international-aluminium.org/robots.txt", HB, keep=2000)
r = get("iai_primary", "https://international-aluminium.org/statistics/primary-aluminium-production/", HB, keep=300)
if r is not None and r.status_code == 200:
    open("probe/iai_primary.html", "w").write(r.text)
    out["iai_primary"]["api"] = sorted(set(re.findall(r'(https?://[^"\']*(?:api|json|csv|xlsx|download)[^"\']*)', r.text)))[:40]
# USGS
get("usgs_mcs", "https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-copper.pdf", HB, keep=100)
get("usgs_mcs25", "https://pubs.usgs.gov/periodicals/mcs2025/mcs2025-copper.pdf", HB, keep=100)
r = get("usgs_sb", "https://www.sciencebase.gov/catalog/items?q=Mineral%20Commodity%20Summaries%202026&format=json&max=10&fields=title,link", HB, keep=4000)
r = get("usgs_sb25", "https://www.sciencebase.gov/catalog/items?q=Mineral%20Commodity%20Summaries%202025%20data%20release&format=json&max=10&fields=title,link", HB, keep=4000)
get("usgs_robots", "https://pubs.usgs.gov/robots.txt", HB, keep=1000)
# LME and free LME prices / stocks
get("lme_robots", "https://www.lme.com/robots.txt", HB, keep=2000)
get("lme_copper", "https://www.lme.com/en/metals/non-ferrous/lme-copper", HB, keep=300)
get("westmetall_robots", "https://www.westmetall.com/robots.txt", HB, keep=2000)
r = get("westmetall_cu", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash", HB, keep=300)
if r is not None and r.status_code == 200: open("probe/westmetall_cu.html", "w").write(r.text)
get("westmetall_al_stock", "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Al_stock", HB, keep=300)
# SHFE weekly stocks
get("shfe_robots", "https://www.shfe.com.cn/robots.txt", HB, keep=1000)
get("shfe_week", "https://www.shfe.com.cn/data/tradedata/future/weeklydata/20261114weeklystock.dat", HB, keep=500)
# Midwest premium / Fastmarkets / Harbor: no free; CME AUP via TV above
# News RSS
get("gnews_metals", "https://news.google.com/rss/search?q=gold+prices+site:reuters.com&hl=en-US&gl=US&ceid=US:en", HB, keep=500)
json.dump(out, open("probe/metals_out.json", "w"), indent=1)
print(json.dumps({k: {kk: vv for kk, vv in (v or {}).items() if kk in ("status", "len", "err", "n", "last", "close")} if isinstance(v, dict) else v for k, v in out.items()}, indent=0))
