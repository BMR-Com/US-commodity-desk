"""Daily OHLCV for charts and technicals, from TradingView: the continuous front month (<ROOT>1!, ~10 years)
and the next listed contracts that have not expired. Writes data/ohlc/<SYM>.csv
(series, date, open, high, low, close, volume); series = 'cont' or the contract code (e.g. ZCZ2026).
"""
import sys, time
from pathlib import Path
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contracts import SPEC, CODES  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "ohlc"
N_ACTIVE = {"DC": 6, "GDK": 6, "CSC": 6, "CB": 6, "GNF": 6, "DY": 6, "HE": 5, "LE": 5, "GF": 5,
            "ZC": 5, "ZS": 6, "ZM": 6, "ZL": 6, "ZW": 5, "KE": 5}


def last_trade_guess(sym, y, m):
    """Rough last trading day, only used to decide which contracts are still live."""
    if sym in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE"):
        return pd.Timestamp(y, m, 14)
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
    tv = TvDatafeed()
    today = pd.Timestamp.now()
    for sym in (sys.argv[1:] or SPEC):
        ex, root, months, _ = SPEC[sym]
        frames = []
        for series, symbol, n in [("cont", f"{root}1!", 2700)] + [(c, c, 800) for c in active(sym, today)]:
            d = get(tv, symbol, ex, n)
            time.sleep(1.2)
            if d is None:
                continue
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


if __name__ == "__main__":
    main()
