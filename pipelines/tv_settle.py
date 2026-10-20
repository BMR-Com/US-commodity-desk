"""Fallback futures settlements from TradingView when the CME download (Mac browser) is missing.

CME blocks GitHub's IP ranges, so data/cme/<date>/ normally comes from the nightly collector on Ma's Mac.
For any trade date in data/ohlc newer than the latest CME folder, write data/cme/<date>/fut_settlements.csv
from TradingView daily closes (CME settlement prices) in the CME file's format, with a SOURCE marker.
Open interest and options are not available from TradingView; those panels keep the last CME day.
A later real CME download for the same date overwrites these files.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CME = ROOT / "data" / "cme"
CODES = "FGHJKMNQUVXZ"
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
EXCH = {s: "CBOT" for s in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE")}


def main():
    real = sorted(p.name for p in CME.glob("2*") if (p / "fut_settlements.csv").exists() and not (p / "SOURCE").exists())
    last_real = real[-1] if real else "00000000"
    frames = []
    for f in sorted((ROOT / "data" / "ohlc").glob("*.csv")):
        sym = f.stem
        d = pd.read_csv(f)
        d = d[d.series != "cont"]
        d["trade_date"] = d.date.str.replace("-", "")
        d = d[d.trade_date > last_real]
        dt = pd.to_datetime(d.date)
        now_ct = pd.Timestamp.now(tz="America/Chicago")
        d = d[(dt.dt.dayofweek < 5) & ((dt.dt.date < now_ct.date()) | (now_ct.hour >= 15))]  # weekdays, settled bars only
        if d.empty:
            continue
        code = d.series.str[len(sym):]
        d["month"] = [f"{MON[CODES.index(c[0])]} {c[-2:]}" for c in code]
        d["sort"] = [int(c[1:]) * 100 + CODES.index(c[0]) for c in code]
        frames.append(pd.DataFrame({"trade_date": d.trade_date, "sym": sym, "exch": EXCH.get(sym, "CME"), "month": d.month,
                                    "open": d.open, "high": d.high, "low": d.low, "last": d.close, "change": "", "settle": d.close,
                                    "volume": d.volume, "oi": "", "sort": d["sort"]}))
    if not frames:
        print("CME data current; no fallback needed")
        return
    a = pd.concat(frames)
    for day, g in a.groupby("trade_date"):
        p = CME / day
        if (p / "fut_settlements.csv").exists() and not (p / "SOURCE").exists():
            continue
        p.mkdir(parents=True, exist_ok=True)
        g.sort_values(["sym", "sort"]).drop(columns="sort").to_csv(p / "fut_settlements.csv", index=False)
        (p / "SOURCE").write_text("tradingview fallback (CME download missing)\n")
        print("fallback settlements", day, len(g))


if __name__ == "__main__":
    main()
