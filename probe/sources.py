import time
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed()
out = []
for s, e in [("DCX2026", "CME"), ("CBZ2026", "CME"), ("ZCZ2026", "CBOT"), ("CTZ2026", "ICEUS"), ("HEZ2026", "CME"), ("CLZ2026", "NYMEX"), ("LEZ2026", "CME"), ("ZSF2027", "CBOT"), ("KCZ2026", "ICEUS"), ("DC1!", "CME"), ("ZC1!", "CBOT"), ("CL1!", "NYMEX"), ("CT1!", "ICEUS")]:
    try:
        d = tv.get_hist(symbol=s, exchange=e, interval=Interval.in_daily, n_bars=6)
        out.append(f"{s} {e} tz={getattr(d.index, 'tz', None)}\n" + d[["close", "volume"]].to_string())
    except Exception as ex:
        out.append(f"{s} ERR {ex}")
    time.sleep(1)
open("probe/out_tv.txt", "w").write("\n\n".join(out))
print("\n\n".join(out))
