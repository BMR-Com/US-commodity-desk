"""Temporary probe (throwaway branch): which GLD daily sources are permitted by robots.txt, plus Yahoo options check."""
import re, json, io, urllib.robotparser as rp, requests
UA = "BMR-Com-research-desk/1.0 (ETF metal holdings research; GitHub Actions)"
H = {"User-Agent": UA}
out = []
def p(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
hosts = ["https://www.ssga.com", "https://www.spdrgoldshares.com", "https://api.spdrgoldshares.com", "https://api.nasdaq.com",
         "https://www.nasdaq.com", "https://www.nyse.com", "https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com", "https://finance.yahoo.com"]
R = {}
for h in hosts:
    try:
        r = requests.get(h + "/robots.txt", headers=H, timeout=30)
        p("==ROBOTS", h, r.status_code); p(r.text[:1500])
        x = rp.RobotFileParser(); x.parse(r.text.splitlines() if r.status_code == 200 else []); R[h] = x
    except Exception as e:
        p("==ROBOTS", h, "ERR", e)
urls = [
 "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld",
 "https://www.ssga.com/us/en/individual/etfs/spdr-gold-shares-gld",
 "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-gld.xlsx",
 "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-gld.xlsx",
 "https://www.spdrgoldshares.com/usa/",
 "https://www.spdrgoldshares.com/usa/historical-data/",
 "https://www.spdrgoldshares.com/assets/dynamic/GLD/GLD_US_archive_EN.csv",
 "https://www.spdrgoldshares.com/ajax/home/?product=gld",
 "https://api.nasdaq.com/api/quote/GLD/info?assetclass=etf",
 "https://api.nasdaq.com/api/quote/GLD/summary?assetclass=etf",
]
for u in urls:
    h = re.match(r"https://[^/]+", u).group(0)
    ok = R[h].can_fetch(UA, u) if h in R else None
    p("==URL", u, "allowed=", ok)
    if not ok: continue
    try:
        r = requests.get(u, headers={**H, "Accept": "*/*"}, timeout=60)
        p(" status", r.status_code, r.headers.get("content-type"), len(r.content))
        t = r.text if "text" in (r.headers.get("content-type") or "") or "json" in (r.headers.get("content-type") or "") else ""
        for k in ["ounces", "Ounces", "tonnes", "Tonnes", "Shares Outstanding", "shares outstanding", "sharesOutstanding", "SharesOutstanding", "Gold in Trust", "NAV"]:
            for m in list(re.finditer(k, t))[:3]:
                p("  ", k, "::", re.sub(r"\s+", " ", t[max(0, m.start()-200):m.end()+250]))
        if u.endswith(".xlsx") and r.status_code == 200:
            import pandas as pd
            for sh, df in pd.read_excel(io.BytesIO(r.content), sheet_name=None, header=None).items():
                p("  sheet", sh, df.shape); p(df.head(12).to_string()[:2500])
        if u.endswith(".csv") and r.status_code == 200: p(r.text[:800])
        if "nasdaq" in u and r.status_code == 200: p(r.text[:2500])
    except Exception as e:
        p(" ERR", e)
try:
    import yfinance as yf
    for s in ["GLD", "SLV"]:
        t = yf.Ticker(s)
        try:
            inf = t.info; p("==YF", s, {k: inf.get(k) for k in ["sharesOutstanding", "impliedSharesOutstanding", "totalAssets", "navPrice", "regularMarketPrice"]})
        except Exception as e: p("==YF info ERR", s, e)
        try:
            fi = t.fast_info; p("  fast_info shares", fi.get("shares"))
        except Exception as e: p("  fast ERR", e)
        try:
            sf = t.get_shares_full(start="2025-10-01"); p("  shares_full", None if sf is None else sf.tail(15).to_string())
        except Exception as e: p("  shares_full ERR", e)
        try:
            ex = t.options; p("  expiries", len(ex), ex[:12])
            oc = t.option_chain(ex[3]); p("  chain", ex[3], len(oc.calls), len(oc.puts)); p(oc.calls.head(3).to_string())
        except Exception as e: p("  options ERR", e)
        h = t.history(period="5d"); p(h.tail(3).to_string())
except Exception as e:
    p("YF ERR", e)
open("probe_gld/out.txt", "w").write("\n".join(out))
