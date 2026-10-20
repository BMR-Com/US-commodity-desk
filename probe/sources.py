"""Probe which public data sources are reachable from GitHub Actions (no keys)."""
import json, os, re, time, requests, traceback
out = {}
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
def get(url, **kw):
    try:
        r = requests.get(url, headers=H, timeout=60, **kw)
        return r.status_code, r.headers.get("content-type", ""), r.text
    except Exception as e:
        return None, "", str(e)

# 1. USDA LMR / Dairy mandatory reporting datamart (no key)
st, ct, tx = get("https://mpr.datamart.ams.usda.gov/services/v1.1/reports")
out["datamart_list"] = {"status": st, "n": len(tx)}
if st == 200:
    try:
        rep = json.loads(tx)
        open("probe/datamart_reports.json", "w").write(json.dumps(rep, indent=1))
        out["datamart_list"]["count"] = len(rep)
    except Exception as e:
        out["datamart_list"]["err"] = str(e); open("probe/datamart_reports.txt", "w").write(tx[:200000])

# 2. MARS API without key
st, ct, tx = get("https://marsapi.ams.usda.gov/services/v1.2/reports")
out["mars_nokey"] = {"status": st, "head": tx[:300]}
k = os.getenv("AMS_API_KEY")
if k:
    st, ct, tx = get("https://marsapi.ams.usda.gov/services/v1.2/reports", auth=(k, ""))
    out["mars_key"] = {"status": st, "n": len(tx)}
    if st == 200: open("probe/mars_reports.json", "w").write(tx)
# 3. NASS QuickStats
st, ct, tx = get("https://quickstats.nass.usda.gov/api/get_counts/?commodity_desc=MILK&year=2025")
out["nass_nokey"] = {"status": st, "head": tx[:200]}
nk = os.getenv("NASS_API_KEY") or os.getenv("USDA_API_KEY")
if nk:
    st, ct, tx = get(f"https://quickstats.nass.usda.gov/api/get_counts/?key={nk}&commodity_desc=MILK&year=2025")
    out["nass_key"] = {"status": st, "head": tx[:200]}
# 4. ERS data product pages
for nm, u in {"ers_livestock_meat": "https://www.ers.usda.gov/data-products/livestock-and-meat-domestic-data/",
              "ers_dairy": "https://www.ers.usda.gov/data-products/dairy-data/",
              "ers_ldp": "https://www.ers.usda.gov/publications/pub-details?pubid=0"}.items():
    st, ct, tx = get(u)
    links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip))"', tx)))
    out[nm] = {"status": st, "links": links[:60]}
# 5. CME endpoints
for nm, u in {"cme_settle_json": "https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/22/FUT?tradeDate=10/16/2026&strategy=DEFAULT&pageSize=50",
              "cme_bulletin_dir": "https://www.cmegroup.com/ftp/bulletin/",
              "cme_dairy_page": "https://www.cmegroup.com/markets/agriculture/dairy.html",
              "cme_lc_quotes": "https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/22/G"}.items():
    st, ct, tx = get(u)
    out[nm] = {"status": st, "ct": ct, "head": tx[:300]}
# 6. CFTC: dairy + livestock contract codes
st, ct, tx = get("https://publicreporting.cftc.gov/resource/kh3c-gbw2.json?$select=market_and_exchange_names,cftc_contract_market_code,max(report_date_as_yyyy_mm_dd)&$group=market_and_exchange_names,cftc_contract_market_code&$where=commodity_subgroup_name in('DAIRY PRODUCTS','LIVESTOCK/MEAT PRODUCTS')&$limit=200")
out["cftc_codes"] = {"status": st, "rows": json.loads(tx) if st == 200 else tx[:300]}
# 7. TradingView continuous symbols
try:
    from tvDatafeed import TvDatafeed, Interval
    tv = TvDatafeed(); res = {}
    for s in ["LE1!", "HE1!", "GF1!", "DC1!", "DK1!", "CSC1!", "CB1!", "GNF1!", "DY1!", "ZC1!", "ZS1!", "ZM1!", "ZL1!", "ZW1!", "KE1!", "LEZ2026", "HEZ2026", "DCX2026"]:
        ex = "CME" if s[:2] in ("LE", "HE", "GF", "DC", "DK", "CS", "CB", "GN", "DY") else "CBOT"
        try:
            d = tv.get_hist(symbol=s, exchange=ex, interval=Interval.in_daily, n_bars=5000)
            res[f"{ex}:{s}"] = None if d is None else [len(d), str(d.index[0].date()), str(d.index[-1].date()), float(d.close.iloc[-1])]
        except Exception as e:
            res[f"{ex}:{s}"] = str(e)[:100]
        time.sleep(1)
    out["tradingview"] = res
except Exception as e:
    out["tradingview"] = traceback.format_exc()[-300:]
json.dump(out, open("probe/out.json", "w"), indent=1)
