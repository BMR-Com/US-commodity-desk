"""Daily futures price history (continuous front and second month) from TradingView.

Writes data/prices/<sym>.csv. Per-contract settlements going forward come from the nightly
CME collector (data/cme/); this file gives the long continuous history for charts.
"""
import time
from pathlib import Path
import pandas as pd
import sys
from tvDatafeed import TvDatafeed, Interval
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tvdates import trade_dates  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "prices"
SYMS = {  # desk symbol: (exchange, TradingView root candidates)
    "DC": ("CME", ["DC"]), "GDK": ("CME", ["GDK", "DK"]), "CSC": ("CME", ["CSC"]), "CB": ("CME", ["CB"]),
    "GNF": ("CME", ["GNF"]), "DY": ("CME", ["DY"]),
    "HE": ("CME", ["HE"]), "LE": ("CME", ["LE"]), "GF": ("CME", ["GF"]),
    "ZC": ("CBOT", ["ZC"]), "ZS": ("CBOT", ["ZS"]), "ZM": ("CBOT", ["ZM"]), "ZL": ("CBOT", ["ZL"]),
    "ZW": ("CBOT", ["ZW"]), "KE": ("CBOT", ["KE"]),
}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    tv = TvDatafeed()
    for sym, (ex, roots) in SYMS.items():
        frames = {}
        for n in (1, 2):
            for root in roots:
                d = None
                try:
                    d = tv.get_hist(symbol=f"{root}{n}!", exchange=ex, interval=Interval.in_daily, n_bars=6000)
                except Exception as e:
                    print(sym, root, n, "err", str(e)[:80])
                time.sleep(1.5)
                if d is not None and len(d):
                    d.index = trade_dates(d.index)          # evening-session bars belong to the next trade date
                    d = d[~d.index.duplicated(keep="last")]
                    frames[n] = d
                    break
        if not frames:
            print(sym, "no data")
            continue
        out = pd.DataFrame(index=sorted(set().union(*[f.index for f in frames.values()])))
        for n, d in frames.items():
            for c in ("open", "high", "low", "close", "volume"):
                out[f"c{n}_{c}"] = d[c]
        out.index = pd.to_datetime(out.index).date
        out.index.name = "date"
        out.to_csv(OUT / f"{sym}.csv")
        print(sym, len(out), out.index[0], out.index[-1])
