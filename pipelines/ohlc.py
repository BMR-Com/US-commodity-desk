"""Daily OHLCV for charts and technicals: the continuous front month (~10 years) and the next listed contracts
that have not expired. Writes data/ohlc/<SYM>.csv (series, date, open, high, low, close, volume);
series = 'cont' or the contract code (e.g. ZCZ2026).

Source: Yahoo Finance first (free; CBOT/CME ~10 min delayed, ICE US ~30 min), e.g. ZC=F for the front month and
ZCZ26.CBT for a contract; TradingView (tvdatafeed, no login, also free and ~10 min delayed) only as a fallback
for a series Yahoo does not return. Yahoo's last bar during the session is the latest trade, not a settlement.
"""
import sys, time
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contracts import SPEC, CODES  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "ohlc"
N_ACTIVE = {"DC": 6, "GDK": 6, "CSC": 6, "CB": 6, "GNF": 6, "DY": 6, "HE": 5, "LE": 5, "GF": 5,
            "ZC": 5, "ZS": 6, "ZM": 6, "ZL": 6, "ZW": 5, "KE": 5, "CT": 5}


def last_trade_guess(sym, y, m):
    """Rough last trading day, only used to decide which contracts are still live."""
    if sym in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE"):
        return pd.Timestamp(y, m, 14)
    if sym == "CT":
        return pd.Timestamp(y, m, 8)        # ~17 business days before month end
    if sym == "HE":
        return pd.Timestamp(y, m, 14)
    if sym in ("DC", "GDK", "CSC", "CB", "GNF", "DY"):
        return pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0) + pd.Timedelta(days=3)
    return pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)


def active(sym, today):
    ex, root, months, _ = SPEC[sym]
    out = []
    for y in range(today.year, today.year + 3):
        for m in months:
            mi = CODES.index(m) + 1
            if last_trade_guess(sym, y, mi) >= today.normalize():
                out.append(f"{root}{m}{y}")
    return out[:N_ACTIVE.get(sym, 5)]


YH = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
Y_SUFFIX = {"CME": ".CME", "CBOT": ".CBT", "ICEUS": ".NYB"}


def yahoo_symbol(series, root, ex):
    """'cont' -> ZC=F; 'ZCZ2026' -> ZCZ26.CBT."""
    if series == "cont":
        return f"{root}=F"
    return f"{series[:-4]}{series[-2:]}{Y_SUFFIX[ex]}"


def yahoo(ysym, rng):
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{ysym}?range={rng}&interval=1d", headers=YH, timeout=40)
            if r.status_code != 200:
                continue
            j = r.json()["chart"]["result"][0]
            if not j.get("timestamp"):
                return None
            q = j["indicators"]["quote"][0]
            tz = j["meta"].get("exchangeTimezoneName", "America/New_York")
            # a session that opens the evening before is dated by its trade date (as exchanges and TradingView do)
            dates = (pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert(tz) + pd.Timedelta(hours=8)).date
            d = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]}, index=dates)
            d = d.dropna(subset=["close"])
            return d[~d.index.duplicated(keep="last")]
        except Exception as e:
            print(ysym, "yahoo err", str(e)[:80])
        time.sleep(2)
    return None


def get(tv, symbol, ex, n):
    for attempt in range(3):
        try:
            d = tv.get_hist(symbol=symbol, exchange=ex, interval=Interval.in_daily, n_bars=n)
            if d is not None and len(d):
                return d
        except Exception as e:
            print(symbol, "err", str(e)[:80])
        time.sleep(4)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tv = None
    today = pd.Timestamp.now()
    src = {"yahoo": 0, "tradingview": 0}
    for sym in (sys.argv[1:] or SPEC):
        ex, root, months, _ = SPEC[sym]
        frames = []
        for series, symbol, n in [("cont", f"{root}1!", 2700)] + [(c, c, 800) for c in active(sym, today)]:
            # range=max makes Yahoo return weekly bars for some contracts; 2y (contracts) / 10y (front) stay daily
            d = yahoo(yahoo_symbol(series, root, ex), "10y" if series == "cont" else "2y")
            time.sleep(0.4)
            daily = d is not None and len(d) >= 20 and pd.Series(pd.to_datetime(d.index)).diff().dt.days.tail(60).median() <= 3
            if daily:
                src["yahoo"] += 1
            else:
                if tv is None:
                    from tvDatafeed import TvDatafeed, Interval  # noqa: F401  (fallback only)
                    globals()["Interval"] = Interval
                    tv = TvDatafeed()
                d = get(tv, symbol, ex, n)
                time.sleep(1.2)
                if d is None:
                    continue
                src["tradingview"] += 1
                print("  fallback to TradingView:", symbol)
            f = pd.DataFrame({"series": series, "date": pd.to_datetime(d.index).date.astype(str),
                              "open": d.open.values, "high": d.high.values, "low": d.low.values, "close": d.close.values, "volume": d.volume.values})
            frames.append(f)
        if not frames:
            print(sym, "no data")
            continue
        out = pd.concat(frames)
        for c in ("open", "high", "low", "close"):
            out[c] = out[c].round(4)
        out.to_csv(OUT / f"{sym}.csv", index=False)
        print(sym, out.series.nunique(), "series", len(out), "rows")
    print("sources", src)


if __name__ == "__main__":
    main()
