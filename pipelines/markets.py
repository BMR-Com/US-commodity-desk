"""Cross-market snapshot from Yahoo Finance (free; futures delayed ~10 min CBOT/CME, ~30 min NYMEX/COMEX/ICE US,
FX real time, US cash indices real time once open) plus the US Treasury daily par yield curve.

Covers the commodities on investing.com's futures page that Yahoo carries, major stock indices, currencies and
US yields. For each: last, time of last trade, change vs prior close (1 day), 1 week, 1 month, 3 months, YTD,
1 year, position in the 52-week range, trend vs 20/50/200-day averages, RSI(14) and the 1-day move in standard
deviations (vs 60-day daily vol). Yields change in basis points.

Writes data/markets/markets.json (snapshot) and data/markets/hist/<group>.csv (daily closes, for the brief).
"""
import json, math, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "markets"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}

# group, yahoo symbol, display name, unit, kind (price | yield)
U = [
    ("Energy", "CL=F", "WTI crude", "$/bbl"), ("Energy", "BZ=F", "Brent crude", "$/bbl"), ("Energy", "NG=F", "Natural gas", "$/MMBtu"),
    ("Energy", "HO=F", "Heating oil (ULSD)", "$/gal"), ("Energy", "RB=F", "RBOB gasoline", "$/gal"),
    ("Metals", "GC=F", "Gold", "$/oz"), ("Metals", "SI=F", "Silver", "$/oz"), ("Metals", "HG=F", "Copper", "$/lb"),
    ("Metals", "PL=F", "Platinum", "$/oz"), ("Metals", "PA=F", "Palladium", "$/oz"), ("Metals", "ALI=F", "Aluminum", "$/t"),
    ("Grains & oilseeds", "ZC=F", "Corn", "¢/bu"), ("Grains & oilseeds", "ZS=F", "Soybeans", "¢/bu"), ("Grains & oilseeds", "ZM=F", "Soybean meal", "$/st"),
    ("Grains & oilseeds", "ZL=F", "Soybean oil", "¢/lb"), ("Grains & oilseeds", "ZW=F", "Chicago wheat", "¢/bu"), ("Grains & oilseeds", "KE=F", "KC wheat", "¢/bu"),
    ("Grains & oilseeds", "ZO=F", "Oats", "¢/bu"), ("Grains & oilseeds", "ZR=F", "Rough rice", "$/cwt"),
    ("Softs", "CT=F", "Cotton", "¢/lb"), ("Softs", "SB=F", "Sugar #11", "¢/lb"), ("Softs", "KC=F", "Coffee", "¢/lb"),
    ("Softs", "CC=F", "Cocoa", "$/t"), ("Softs", "OJ=F", "Orange juice", "¢/lb"),
    ("Livestock & dairy", "LE=F", "Live cattle", "¢/lb"), ("Livestock & dairy", "GF=F", "Feeder cattle", "¢/lb"), ("Livestock & dairy", "HE=F", "Lean hogs", "¢/lb"),
    ("Livestock & dairy", "DC=F", "Class III milk", "$/cwt"), ("Livestock & dairy", "GDK=F", "Class IV milk", "$/cwt"),
    ("Livestock & dairy", "CSC=F", "Cheese", "$/lb"), ("Livestock & dairy", "CB=F", "Butter", "¢/lb"), ("Livestock & dairy", "GNF=F", "Nonfat dry milk", "¢/lb"),
    ("Livestock & dairy", "DY=F", "Dry whey", "¢/lb"),
    ("Commodity indices", "^SPGSCI", "S&P GSCI", "index"),
    ("US stocks", "^GSPC", "S&P 500", "index"), ("US stocks", "^DJI", "Dow Jones", "index"), ("US stocks", "^IXIC", "Nasdaq Composite", "index"),
    ("US stocks", "^RUT", "Russell 2000", "index"), ("US stocks", "^VIX", "VIX", "index"), ("US stocks", "ES=F", "S&P 500 futures", "index"),
    ("World stocks", "^GSPTSE", "Canada TSX", "index"), ("World stocks", "^BVSP", "Brazil Bovespa", "index"), ("World stocks", "^MXX", "Mexico IPC", "index"),
    ("World stocks", "^FTSE", "UK FTSE 100", "index"), ("World stocks", "^GDAXI", "Germany DAX", "index"), ("World stocks", "^FCHI", "France CAC 40", "index"),
    ("World stocks", "^STOXX50E", "Euro Stoxx 50", "index"), ("World stocks", "^N225", "Japan Nikkei 225", "index"), ("World stocks", "^HSI", "Hong Kong Hang Seng", "index"),
    ("World stocks", "000001.SS", "China Shanghai Comp.", "index"), ("World stocks", "^KS11", "Korea KOSPI", "index"), ("World stocks", "^AXJO", "Australia ASX 200", "index"),
    ("World stocks", "^NSEI", "India Nifty 50", "index"),
    ("Currencies", "DX-Y.NYB", "US dollar index", "index"), ("Currencies", "EURUSD=X", "EUR/USD", ""), ("Currencies", "JPY=X", "USD/JPY", ""),
    ("Currencies", "GBPUSD=X", "GBP/USD", ""), ("Currencies", "CNY=X", "USD/CNY", ""), ("Currencies", "CNH=X", "USD/CNH", ""),
    ("Currencies", "BRL=X", "USD/BRL", ""), ("Currencies", "MXN=X", "USD/MXN", ""), ("Currencies", "CAD=X", "USD/CAD", ""),
    ("Currencies", "AUDUSD=X", "AUD/USD", ""), ("Currencies", "INR=X", "USD/INR", ""), ("Currencies", "ARS=X", "USD/ARS", ""),
    ("Currencies", "ZAR=X", "USD/ZAR", ""), ("Currencies", "CHF=X", "USD/CHF", ""), ("Currencies", "BTC-USD", "Bitcoin", "$"),
    ("US rates", "^IRX", "US 13-week bill", "%", "yield"), ("US rates", "2YY=F", "US 2-year (yield futures)", "%", "yield"),
    ("US rates", "^FVX", "US 5-year", "%", "yield"), ("US rates", "^TNX", "US 10-year", "%", "yield"), ("US rates", "^TYX", "US 30-year", "%", "yield"),
    ("US rates", "ZN=F", "10-yr T-note futures", "pts"), ("US rates", "ZB=F", "30-yr T-bond futures", "pts"),
]
EXCH_DELAY = {"CBT": 10, "CME": 10, "NYM": 30, "CMX": 30, "NYB": 30, "CCY": 0, "SNP": 0, "DJI": 0, "NIM": 0, "CGI": 15, "NYS": 15}


def chart(sym):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d&includePrePost=false", headers=H, timeout=30)
            if r.status_code == 200:
                return r.json()["chart"]["result"][0]
            print("  HTTP", r.status_code, sym, host)
        except Exception as e:
            print("  err", sym, e)
        time.sleep(2)
    return None


def pct(a, b):
    return None if a is None or b is None or b == 0 or (isinstance(b, float) and math.isnan(b)) else 100 * (a / b - 1)


def rsi(c, n=14):
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def treasury_curve():
    """US Treasury daily par yield curve (all tenors, published ~3:30-6 pm ET)."""
    y = datetime.now(timezone.utc).year
    rows = []
    for yr in (y - 1, y):
        u = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all"
             f"?type=daily_treasury_yield_curve&field_tdr_date_value={yr}&page&_format=csv")
        try:
            r = requests.get(u, headers=H, timeout=60)
            if r.status_code == 200 and r.text.startswith("Date"):
                rows.append(pd.read_csv(pd.io.common.StringIO(r.text)))
        except Exception as e:
            print("treasury", yr, e)
    if not rows:
        return None
    df = pd.concat(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").drop_duplicates("Date").set_index("Date")
    last = df.iloc[-1]
    def ago(days):
        s = df[df.index <= df.index[-1] - pd.Timedelta(days=days)]
        return s.iloc[-1] if len(s) else None
    tenors = [c for c in ["1 Mo", "3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"] if c in df]
    w, m, yb = ago(7), ago(30), ago(365)
    curve = [{"tenor": t, "now": float(last[t]), "w1": None if w is None else float(w[t]), "m1": None if m is None else float(m[t]),
              "y1": None if yb is None else float(yb[t])} for t in tenors]
    s = df.get("10 Yr") - df.get("2 Yr")
    return {"date": str(df.index[-1].date()), "curve": curve, "s2s10_bp": round(100 * float(s.iloc[-1]), 1),
            "s2s10_chg_1m_bp": round(100 * float(s.iloc[-1] - s[s.index <= s.index[-1] - pd.Timedelta(days=30)].iloc[-1]), 1),
            "s3m10_bp": round(100 * float(last["10 Yr"] - last["3 Mo"]), 1),
            "hist_2y10y": [[str(d.date()), round(100 * float(v), 1)] for d, v in s.dropna().iloc[-260:].items()]}


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    return o


def main():
    now = time.time()
    items, closes = [], {}
    for row in U:
        g, sym, name, unit = row[:4]
        kind = row[4] if len(row) > 4 else "price"
        j = chart(sym)
        time.sleep(0.4)
        if not j or not j.get("timestamp"):
            print("missing", sym)
            continue
        m = j["meta"]
        q = j["indicators"]["quote"][0]
        c = pd.Series(q["close"], index=pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("America/New_York").date, dtype=float).dropna()
        c = c[~c.index.duplicated(keep="last")]
        if len(c) < 30:
            continue
        last = float(m.get("regularMarketPrice") or c.iloc[-1])
        prev = float(c.iloc[-2])
        def back(days):
            s = c[c.index <= c.index[-1] - pd.Timedelta(days=days)]
            return float(s.iloc[-1]) if len(s) else None
        ytd = c[[d.year < c.index[-1].year for d in c.index]]
        r = c.pct_change()
        vol = float(r.iloc[-61:-1].std()) if len(r) > 61 else None
        y1 = c.iloc[-252:]
        hi, lo = float(y1.max()), float(y1.min())
        ma = {n: float(c.iloc[-n:].mean()) for n in (20, 50, 200) if len(c) >= n}
        chg = (lambda b: None if b is None else (100 * (last - b) if kind == "yield" else pct(last, b)))  # yields: bp
        it = {"group": g, "sym": sym, "name": name, "unit": unit, "kind": kind, "last": last, "prev": prev,
              "time": datetime.fromtimestamp(m.get("regularMarketTime", now), timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
              "age_min": round((now - m.get("regularMarketTime", now)) / 60), "exch": m.get("exchangeName"), "delay_min": EXCH_DELAY.get(m.get("exchangeName")),
              "d1": chg(prev), "w1": chg(back(7)), "m1": chg(back(30)), "m3": chg(back(91)), "ytd": chg(float(ytd.iloc[-1]) if len(ytd) else None), "y1": chg(back(365)),
              "pos52": None if hi == lo else round(100 * (last - lo) / (hi - lo)), "hi52": hi, "lo52": lo,
              "ma20": ma.get(20), "ma50": ma.get(50), "ma200": ma.get(200),
              "trend": sum((1 if last > v else -1) for v in ma.values()), "rsi": round(float(rsi(c).iloc[-1]), 1),
              "z1": None if not vol or kind == "yield" else round((last / prev - 1) / vol, 2),
              "spark": [round(float(v), 6) for v in c.iloc[-66:]]}
        items.append(it)
        closes[sym] = c
        print(f"{sym:10s} {last:>12.4f} d1 {it['d1'] if it['d1'] is None else round(it['d1'], 2)}")
    ust = treasury_curve()
    OUT.mkdir(parents=True, exist_ok=True)
    snap = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "source": "Yahoo Finance (delayed: CBOT/CME ~10 min, NYMEX/COMEX/ICE US ~30 min; FX and cash indices real time) and US Treasury",
            "items": items, "treasury": ust}
    (OUT / "markets.json").write_text(json.dumps(clean(snap), default=str))
    if closes:
        pd.DataFrame(closes).sort_index().iloc[-520:].to_csv(OUT / "closes.csv")
    print("markets", len(items), "of", len(U), "treasury", ust and ust["date"])


if __name__ == "__main__":
    main()
