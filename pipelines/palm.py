"""Palm oil raw data (free public sources, no login). Each step is independent and keeps what is already stored.

  mpob     MPOB monthly summary pages (production, stocks, exports, imports, prices), one HTML table per year
           -> data/palm/raw/mpob/<year>.html (+ parsed data/palm/raw/mpob_monthly.csv)
  backfill long-form CSV mirror of the MPOB monthly statistics (history from 2000) -> data/palm/raw/mpob_backfill.csv
  psd      USDA PSD palm oil / soybean oil balances by country -> data/palm/raw/psd.csv; each month's values are also
           appended to data/palm/raw/psd_vintages.csv so revisions build up over time
  cot      CFTC disaggregated COT for CME USD Malaysian Crude Palm Oil (037021) -> data/palm/raw/cot_{fo,fut}.csv
  prices   TradingView daily closes: Bursa FCPO, CME CPO, palm-gasoil spread, CBOT soybean oil, USD/MYR, gasoil, Brent
           -> data/palm/raw/prices.csv
  monthly  FRED monthly palm oil price (IMF series) -> data/palm/raw/fred_palm.csv
  daily    MPOB daily local CPO price pages -> data/palm/raw/mpob_daily/<year>.html
"""
import csv, io, re, sys, time, zipfile
from datetime import date
from pathlib import Path
import pandas as pd
import requests

RAW = Path(__file__).resolve().parent.parent / "data" / "palm" / "raw"
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def get(url, tries=3, timeout=90):
    for i in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code == 200 and len(r.content) > 200:
                return r
            print("  HTTP", r.status_code, len(r.content), url[:110])
            if r.status_code in (401, 403, 404):
                return None
        except Exception as e:
            print("  err", str(e)[:90], url[:90])
        time.sleep(4 * (i + 1))
    return None


def mpob():
    d = RAW / "mpob"; d.mkdir(parents=True, exist_ok=True)
    y1 = date.today().year
    have = {int(p.stem) for p in d.glob("*.html")}
    years = [y for y in range(2012, y1 + 1) if y not in have or y >= y1 - 1]     # history once, last two years every run
    frames = []
    for y in years:
        r = get(f"https://bepi.mpob.gov.my/stat/web_report1.php?val={y}84")
        if r is None or "<table" not in r.text.lower():
            print("mpob", y, "no table"); continue
        (d / f"{y}.html").write_bytes(r.content)
        print("mpob", y, len(r.content))
        time.sleep(1.5)
    for p in sorted(d.glob("*.html")):
        try:
            for i, t in enumerate(pd.read_html(io.StringIO(p.read_text(errors="replace")))):
                t.insert(0, "table", i); t.insert(0, "year", int(p.stem)); frames.append(t.astype(str))
        except Exception as e:
            print("mpob parse", p.name, str(e)[:80])
    if frames:
        pd.concat(frames, ignore_index=True).to_csv(RAW / "mpob_tables_raw.csv", index=False)


def backfill():
    r = get("https://palmoileconomics.com/data/mpob/csv")
    if r is not None and b"month" in r.content[:200]:
        (RAW / "mpob_backfill.csv").write_bytes(r.content); print("backfill", len(r.content))


def psd():
    r = get("https://apps.fas.usda.gov/psdonline/downloads/psd_oilseeds_csv.zip", timeout=180)
    if r is None:
        print("psd failed"); return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    df = pd.read_csv(z.open(z.namelist()[0]), dtype={"Commodity_Code": str}, encoding="latin1")
    df = df[df.Commodity_Description.str.strip().isin(["Oil, Palm", "Oil, Soybean", "Oil, Palm Kernel", "Oil, Sunflowerseed", "Oil, Rapeseed"])]
    df = df[df.Market_Year >= df.Market_Year.max() - 15]
    keep = ["Commodity_Description", "Country_Code", "Country_Name", "Market_Year", "Calendar_Year", "Month", "Attribute_Description", "Unit_Description", "Value"]
    df = df[keep]; df.to_csv(RAW / "psd.csv", index=False)
    cur = df[(df.Commodity_Description.str.strip() == "Oil, Palm") & (df.Market_Year >= df.Market_Year.max() - 1)].copy()
    cur.insert(0, "vintage", date.today().strftime("%Y-%m"))
    vp = RAW / "psd_vintages.csv"
    if vp.exists():
        old = pd.read_csv(vp, dtype=str)
        cur = pd.concat([old[old.vintage != cur.vintage.iloc[0]], cur.astype(str)], ignore_index=True)
    cur.to_csv(vp, index=False)
    print("psd", len(df), "rows; years to", int(df.Market_Year.max()))


def cot():
    for tag, ds in {"fo": "kh3c-gbw2", "fut": "72hh-3qpy"}.items():
        r = get(f"https://publicreporting.cftc.gov/resource/{ds}.csv?cftc_contract_market_code=037021&$order=report_date_as_yyyy_mm_dd&$limit=50000", timeout=120)
        if r is not None and r.text.count("\n") > 5:
            (RAW / f"cot_{tag}.csv").write_text(r.text); print("cot", tag, r.text.count("\n") - 1)
        else:
            print("cot", tag, "no rows")


def prices():
    from tvDatafeed import TvDatafeed, Interval
    S = {"FCPO": ("MYX", "FCPO1!"), "FCPO3": ("MYX", "FCPO3!"), "CPO": ("CME", "CPO1!"), "POGO": ("CME", "POG1!"), "ZL": ("CBOT", "ZL1!"),
         "USDMYR": ("FX_IDC", "USDMYR"), "GASOIL": ("ICEEUR", "G1!"), "BRENT": ("ICEEUR", "BRN1!"), "DCE_P": ("DCE", "P1!"), "USDIDR": ("FX_IDC", "USDIDR")}
    out = RAW / "prices.csv"
    old = pd.read_csv(out, parse_dates=["date"]).set_index("date") if out.exists() else pd.DataFrame()
    tv = TvDatafeed(); new = {}
    for k, (ex, sym) in S.items():
        for i in range(3):
            try:
                n = 150 if (len(old) and k in old and old[k].notna().sum() > 300) else 5000
                d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n)
                if d is not None and len(d):
                    s = d["close"]; s.index = (pd.DatetimeIndex(s.index) + pd.Timedelta(hours=10)).normalize()   # Asian sessions stamp the prior UTC evening
                    new[k] = s[~s.index.duplicated(keep="last")]
                    if k in ("FCPO", "CPO"):
                        v = d["volume"]; v.index = s.index if len(v) == len(s) else v.index
                    break
            except Exception as e:
                print(k, "err", str(e)[:80])
            time.sleep(3)
    if not new:
        print("prices: nothing"); return
    df = pd.DataFrame(new); df = df[df.index <= pd.Timestamp(date.today()) + pd.Timedelta(days=1)]
    df = df.combine_first(old) if len(old) else df
    df.index.name = "date"; df.sort_index().to_csv(out, float_format="%.4f")
    print({k: (str(v.index[-1].date()), float(v.iloc[-1]), len(v)) for k, v in new.items()})


def monthly():
    r = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=PPOILUSDM,PSOILUSDM")
    if r is not None and "PPOILUSDM" in r.text[:200]:
        (RAW / "fred_palm.csv").write_text(r.text); print("fred", r.text.count("\n"))


def daily():
    d = RAW / "mpob_daily"; d.mkdir(parents=True, exist_ok=True)
    y1 = date.today().year
    for y in [y for y in range(2016, y1 + 1) if y == y1 or not (d / f"{y}.html").exists()]:
        r = get(f"https://bepi.mpob.gov.my/admin2/price_local_daily_view_cpo_msia.php?more=Y&jenis=1Y&tahun={y}")
        if r is not None and "<table" in r.text.lower():
            (d / f"{y}.html").write_bytes(r.content); print("daily", y, len(r.content))
        time.sleep(1.5)


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    steps = sys.argv[1:] or ["mpob", "backfill", "psd", "cot", "prices", "monthly", "daily"]
    for s in steps:
        try:
            print("==", s); globals()[s]()
        except Exception as e:
            print(s, "FAILED", str(e)[:200])
