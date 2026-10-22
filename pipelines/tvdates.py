"""TradingView daily bars are stamped with the session's opening time (UTC on the runners). Sessions that open the
evening before (CME dairy and energy from 17:00 CT, ICE cotton on Sunday nights) come back stamped 22:00 UTC of the
previous day, so `.date` lands one trading day early: the bar dated Wednesday is Thursday's settlement. Verified
against CME settlement files (data/cme/): after this conversion 93-96% of closes equal the CME settlement exactly.
"""
import pandas as pd


def trade_dates(index):
    """Exchange trade date for each TradingView bar timestamp: an evening (>= 18:00) open belongs to the next day."""
    ts = pd.to_datetime(index)
    return (ts + pd.to_timedelta((ts.hour >= 18).astype(int), unit="D")).normalize()


def fix_stored(dates):
    """For already-stored date-only series (pre-fix): if a series has Sundays but no Fridays, every bar is one day
    early (shift all +1); otherwise move only the Sunday bars to Monday."""
    d = pd.to_datetime(pd.Series(dates))
    dow = d.dt.dayofweek
    if (dow == 6).any() and not (dow == 4).any():
        return d + pd.Timedelta(days=1)
    return d.where(dow != 6, d + pd.Timedelta(days=1))
