#!/usr/bin/env python3
"""
prices.py — weekly price refresh from Yahoo Finance (yfinance).

Writes
  data/prices/daily.csv     daily OHLCV for every BCOM market we track (front-month
                            continuous "=F" series), merged with what's already there
                            so a failed week never loses history.
  data/prices/report.json   fetch status per market, term-structure carry from two
                            specific contracts (front vs same month next year), and
                            the equity risk regime (S&P 500 vs 200-day, VIX).

Run standalone:  python scripts/prices.py
Note: Yahoo's "=F" series is the unadjusted front contract, so long-horizon returns
include roll gaps. Good enough for trend direction; carry is measured separately.
"""
import json, math, sys, time
from datetime import datetime, timezone, date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PDIR = ROOT / "data" / "prices"
DAILY = PDIR / "daily.csv"
REPORT = PDIR / "report.json"
FRONT = PDIR / "front_contract.csv"   # ~1y daily history of the current tradable contract per market

# our ticker -> Yahoo continuous symbol, contract root, exchange suffix, listed months
YAHOO = {
    "CO":  ("BZ=F", "BZ", "NYM", "FGHJKMNQUVXZ"),
    "NG":  ("NG=F", "NG", "NYM", "FGHJKMNQUVXZ"),
    "CL":  ("CL=F", "CL", "NYM", "FGHJKMNQUVXZ"),
    "HO":  ("HO=F", "HO", "NYM", "FGHJKMNQUVXZ"),
    "XB":  ("RB=F", "RB", "NYM", "FGHJKMNQUVXZ"),
    "C":   ("ZC=F", "ZC", "CBT", "HKNUZ"),
    "S":   ("ZS=F", "ZS", "CBT", "FHKNQUX"),
    "SM":  ("ZM=F", "ZM", "CBT", "FHKNQUVZ"),
    "BO":  ("ZL=F", "ZL", "CBT", "FHKNQUVZ"),
    "W":   ("ZW=F", "ZW", "CBT", "HKNUZ"),
    "KW":  ("KE=F", "KE", "CBT", "HKNUZ"),
    "HG":  ("HG=F", "HG", "CMX", "HKNUZ"),
    "ALI": ("ALI=F", "ALI", "CMX", "FGHJKMNQUVXZ"),   # price = COMEX aluminum (MWP has no Yahoo series)
    "GC":  ("GC=F", "GC", "CMX", "GJMQVZ"),
    "SI":  ("SI=F", "SI", "CMX", "HKNUZ"),
    "SB":  ("SB=F", "SB", "NYB", "HKNV"),
    "KC":  ("KC=F", "KC", "NYB", "HKNUZ"),
    "CC":  ("CC=F", "CC", "NYB", "HKNUZ"),
    "CT":  ("CT=F", "CT", "NYB", "HKNVZ"),
    "LC":  ("LE=F", "LE", "CME", "GJMQVZ"),
    "LH":  ("HE=F", "HE", "CME", "GJKMNQVZ"),
}
PROXY_NOTE = {"ALI": "price series is COMEX aluminum; COT is the Midwest Premium contract"}
MONTHS = "FGHJKMNQUVXZ"
ENERGY = {"CO", "NG", "CL", "HO", "XB"}   # energy contract month M expires in month M-1


def _dl(symbols, **kw):
    import yfinance as yf
    for attempt in range(3):
        try:
            d = yf.download(symbols, progress=False, auto_adjust=False, group_by="ticker", threads=True, **kw)
            if d is not None and len(d):
                return d
        except Exception as e:
            print("  download error:", e)
        time.sleep(5 * (attempt + 1))
    return pd.DataFrame()


def _frame(d, sym):
    try:
        f = d[sym] if isinstance(d.columns, pd.MultiIndex) else d
    except KeyError:
        return pd.DataFrame()
    f = f.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    f.index = pd.to_datetime(f.index).tz_localize(None).normalize()
    return f


def contract_pair(tk, today):
    """Front tradable contract and the same month one year later (avoids seasonal bias)."""
    _, root, ex, listed = YAHOO[tk]
    skip = 2 if tk in ENERGY else 1
    y, m = today.year, today.month
    for k in range(skip, skip + 14):
        mm = (m - 1 + k) % 12 + 1; yy = y + (m - 1 + k) // 12
        code = MONTHS[mm - 1]
        if code in listed:
            f1 = f"{root}{code}{yy % 100:02d}.{ex}"
            f2 = f"{root}{code}{(yy + 1) % 100:02d}.{ex}"
            return f1, f2, f"{code}{yy % 100:02d}", f"{code}{(yy + 1) % 100:02d}"
    return None


def main():
    PDIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    report = {"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
              "source": "Yahoo Finance via yfinance (front-month continuous)", "markets": {}, "carry": {}, "regime": {}}

    old = pd.read_csv(DAILY, parse_dates=["date"]) if DAILY.exists() else pd.DataFrame()
    start = "2006-01-01" if old.empty else (old["date"].max() - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    syms = [v[0] for v in YAHOO.values()] + ["^GSPC", "^VIX"]
    print(f"Downloading daily prices since {start} for {len(syms)} symbols ...")
    d = _dl(syms, start=start, interval="1d")

    rows = []
    for tk, (sym, *_r) in YAHOO.items():
        f = _frame(d, sym)
        report["markets"][tk] = {"yahoo": sym, "rows_fetched": int(len(f)),
                                 "last": f.index.max().strftime("%Y-%m-%d") if len(f) else None,
                                 "status": "ok" if len(f) else "no data"}
        if tk in PROXY_NOTE:
            report["markets"][tk]["note"] = PROXY_NOTE[tk]
        if len(f):
            f = f.reset_index().rename(columns={"index": "date", "Date": "date"})
            f.columns = ["date"] + list(f.columns[1:])
            f["ticker"] = tk
            rows.append(f)
    for sym, tk in [("^GSPC", "SPX"), ("^VIX", "VIX")]:
        f = _frame(d, sym)
        if len(f):
            f = f.reset_index(); f.columns = ["date"] + list(f.columns[1:]); f["ticker"] = tk; rows.append(f)

    new = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if not new.empty:
        allp = pd.concat([old, new], ignore_index=True) if not old.empty else new
        allp = allp.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"])
        for c in ["open", "high", "low", "close"]:
            allp[c] = allp[c].astype(float).round(5)
        allp["volume"] = allp["volume"].fillna(0).astype("int64")
        allp[["date", "ticker", "open", "high", "low", "close", "volume"]].to_csv(DAILY, index=False, date_format="%Y-%m-%d")
        print(f"Saved {DAILY.name}: {len(allp):,} rows")
    else:
        allp = old
        print("WARNING: no new prices downloaded; keeping existing file")

    # ── regime: S&P 500 vs 200-day, VIX ──
    try:
        spx = allp[allp.ticker == "SPX"].set_index("date")["close"]
        vix = allp[allp.ticker == "VIX"].set_index("date")["close"]
        s200 = spx.rolling(200).mean()
        report["regime"] = {"spx": round(float(spx.iloc[-1]), 2), "spx_200d": round(float(s200.iloc[-1]), 2),
                            "spx_above_200d": bool(spx.iloc[-1] > s200.iloc[-1]), "vix": round(float(vix.iloc[-1]), 2),
                            "date": spx.index[-1].strftime("%Y-%m-%d")}
        report["regime"]["risk_off"] = (not report["regime"]["spx_above_200d"]) and report["regime"]["vix"] > 25
    except Exception as e:
        report["regime"] = {"error": str(e)}

    # ── carry: front vs same month next year (+ front contract's own history) ──
    pairs = {tk: contract_pair(tk, today) for tk in YAHOO}
    csyms = sorted({s for p in pairs.values() if p for s in p[:2]})
    cd = _dl(csyms, period="1y", interval="1d")
    fr = []
    for tk, p in pairs.items():
        if not p:
            continue
        f = _frame(cd, p[0])
        if len(f):
            f = f.reset_index(); f.columns = ["date"] + list(f.columns[1:]); f["ticker"] = tk; f["contract"] = YAHOO[tk][1] + p[2]; fr.append(f)
    if fr:
        fc = pd.concat(fr, ignore_index=True)
        for c in ["open", "high", "low", "close"]:
            fc[c] = fc[c].astype(float).round(5)
        fc["volume"] = fc["volume"].fillna(0).astype("int64")
        fc[["date", "ticker", "contract", "open", "high", "low", "close", "volume"]].to_csv(FRONT, index=False, date_format="%Y-%m-%d")
        print(f"Saved {FRONT.name}: {len(fc):,} rows for {fc.ticker.nunique()} contracts")
    for tk, p in pairs.items():
        if not p:
            continue
        f1, f2 = _frame(cd, p[0]), _frame(cd, p[1])
        if len(f1) and len(f2):
            p1, p2 = float(f1["close"].iloc[-1]), float(f2["close"].iloc[-1])
            c = math.log(p1 / p2) if p1 > 0 and p2 > 0 else None
            report["carry"][tk] = {"front": p[2], "deferred": p[3], "p_front": round(p1, 4), "p_deferred": round(p2, 4),
                                   "carry_ann": round(c, 4) if c is not None else None,
                                   "date": f1.index[-1].strftime("%Y-%m-%d")}
        else:
            report["carry"][tk] = {"front": p[2], "deferred": p[3], "carry_ann": None,
                                   "status": "contract data unavailable on Yahoo"}

    ok = sum(1 for m in report["markets"].values() if m["status"] == "ok")
    report["summary"] = {"markets_ok": ok, "markets_total": len(YAHOO),
                         "carry_ok": sum(1 for c in report["carry"].values() if c.get("carry_ann") is not None)}
    REPORT.write_text(json.dumps(report, indent=1))
    print(json.dumps(report["summary"]), json.dumps(report["regime"]))


if __name__ == "__main__":
    main()
