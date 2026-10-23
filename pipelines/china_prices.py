"""Zhengzhou cotton (CF) and cotton yarn (CY) front months, USD/CNY and ICE cotton front month, daily, from TradingView
(tvdatafeed, no login). Appends to data/china/tv_prices.csv (date, CF1, CY1, USDCNY, CT1).
ZCE night-session bars are stamped the previous evening (UTC); they are moved to the next trading day, and a bar
dated after today (the session still forming) is dropped.
"""
import time
from datetime import date
from pathlib import Path
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

OUT = Path(__file__).resolve().parent.parent / "data" / "china" / "tv_prices.csv"
SYMS = {"CF1": ("ZCE", "CF1!"), "CY1": ("ZCE", "CY1!"), "USDCNY": ("FX_IDC", "USDCNY"), "CT1": ("ICEUS", "CT1!"),
        "PF1": ("ZCE", "PF1!"),      # polyester staple fibre, yuan/t (listed Oct 2020)
        "TA1": ("ZCE", "TA1!"),      # PTA, the main polyester feedstock, yuan/t
        "BRENT": ("ICEEUR", "BRN1!")}


def zce_date(ix):
    d = (pd.DatetimeIndex(ix) + pd.Timedelta(hours=12)).normalize()     # 21:00 Beijing night session -> next day
    return d + pd.to_timedelta([2 if x.weekday() == 5 else 1 if x.weekday() == 6 else 0 for x in d], unit="D")


if __name__ == "__main__":
    old = pd.read_csv(OUT, parse_dates=["date"]).set_index("date") if OUT.exists() else pd.DataFrame()
    tv = TvDatafeed()
    new = {}
    for k, (ex, sym) in SYMS.items():
        for i in range(3):
            try:
                n = 120 if (len(old) and k in old and old[k].notna().sum() > 200) else 3000   # backfill a new column once
                d = tv.get_hist(symbol=sym, exchange=ex, interval=Interval.in_daily, n_bars=n)
                if d is not None and len(d):
                    s = d["close"]
                    s.index = zce_date(s.index) if ex == "ZCE" else pd.DatetimeIndex(s.index).normalize()
                    new[k] = s[~s.index.duplicated(keep="last")]
                    break
            except Exception as e:
                print(k, "err", str(e)[:80])
            time.sleep(3)
    df = pd.DataFrame(new)
    df = df[df.index <= pd.Timestamp(date.today())]
    out = df.combine_first(old) if len(old) else df
    out.index.name = "date"
    out.sort_index().to_csv(OUT, float_format="%.4f")
    print({k: (str(v.index[-1].date()), float(v.iloc[-1])) for k, v in new.items()})
