"""Per-contract daily futures history (including expired contracts) from TradingView.

Needed for convergence backtests: where did each contract trade before expiry vs the cash
number it settled to. Writes data/contracts/<SYM>.csv (contract, date, close, volume), merging
with what is already stored; expired contracts already stored are not re-fetched.
"""
import sys, time
from pathlib import Path
import pandas as pd
from tvDatafeed import TvDatafeed, Interval
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tvdates import trade_dates, fix_stored  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "contracts"
CODES = "FGHJKMNQUVXZ"
SPEC = {  # sym: (exchange, TV root, months, first year)
    "HE": ("CME", "HE", "GJKMNQVZ", 2006),
    "LE": ("CME", "LE", "GJMQVZ", 2006),
    "GF": ("CME", "GF", "FHJKQUVX", 2006),
    "DC": ("CME", "DC", CODES, 2006),
    "GDK": ("CME", "GDK", CODES, 2012),
    "CSC": ("CME", "CSC", CODES, 2012),
    "CB": ("CME", "CB", CODES, 2012),
    "GNF": ("CME", "GNF", CODES, 2012),
    "DY": ("CME", "DY", CODES, 2012),
    "ZC": ("CBOT", "ZC", "HKNUZ", 2006),
    "ZS": ("CBOT", "ZS", "FHKNQUX", 2006),
    "ZM": ("CBOT", "ZM", "FHKNQUVZ", 2008),
    "ZL": ("CBOT", "ZL", "FHKNQUVZ", 2008),
    "ZW": ("CBOT", "ZW", "HKNUZ", 2006),
    "KE": ("CBOT", "KE", "HKNUZ", 2008),
    "CT": ("ICEUS", "CT", "HKNZ", 2006),   # ICE cotton No. 2: Mar, May, Jul, Dec (October ignored)
    # energy desk (NYMEX, every month)
    "NG": ("NYMEX", "NG", CODES, 2015), "CL": ("NYMEX", "CL", CODES, 2015),
    "HO": ("NYMEX", "HO", CODES, 2015), "RB": ("NYMEX", "RB", CODES, 2015),
}


def run(sym):
    ex, root, months, y0 = SPEC[sym]
    p = OUT / f"{sym}.csv"
    have = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["contract", "date", "close", "volume"])
    if len(have):   # one-time repair of rows stored before the trade-date fix (idempotent on corrected data)
        have["date"] = have.groupby("contract", group_keys=False).date.apply(lambda s: fix_stored(s.values).dt.strftime("%Y-%m-%d").set_axis(s.index))
    done = set(have.contract.unique())
    today = pd.Timestamp.now()
    tv = TvDatafeed()
    frames = [have]
    for y in range(y0, today.year + 3):
        for m in months:
            c = f"{root}{m}{y}"
            mi = CODES.index(m) + 1
            expired_long_ago = pd.Timestamp(y, mi, 1) < today - pd.Timedelta(days=75)
            if c in done and expired_long_ago:
                continue
            if pd.Timestamp(y, mi, 1) > today + pd.Timedelta(days=760):
                continue
            d = None
            for attempt in range(2):
                try:
                    d = tv.get_hist(symbol=c, exchange=ex, interval=Interval.in_daily, n_bars=800)
                    break
                except Exception as e:
                    print(c, "err", str(e)[:80])
                    time.sleep(5)
            time.sleep(1.2)
            if d is None or not len(d):
                continue
            f = pd.DataFrame({"contract": c, "date": trade_dates(d.index).date.astype(str),
                              "close": d.close.round(4).values, "volume": d.volume.values})
            frames.append(f)
            done.add(c)
    out = pd.concat(frames).drop_duplicates(["contract", "date"], keep="last").sort_values(["contract", "date"])
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    print(sym, out.contract.nunique(), "contracts", len(out), "rows")


if __name__ == "__main__":
    for s in (sys.argv[1:] or SPEC):
        try:
            run(s)
        except Exception as e:
            print(s, "FAILED", e)
