#!/usr/bin/env python3
"""Contract calendar: for every desk futures market, the next listed contracts with first position day, first notice
day, last trading day and the date to be out of (or rolled from) each contract, from the exchange rules.

Rules are coded from the CME / ICE contract specifications and checked against the last trade date of every expired
contract in data/contracts (printed at the end of a run). Exchange holidays: US exchange calendar (New Year, MLK,
Presidents, Good Friday, Memorial, Juneteenth, Independence, Labor, Thanksgiving, Christmas). Special early closes
and one-off exchange changes are not modelled: always confirm on the exchange calendar before a delivery-sensitive date.
Writes data/specs/calendar.json.
"""
import json, sys
from datetime import date
from pathlib import Path
import pandas as pd
from pandas.tseries.holiday import (AbstractHolidayCalendar, Holiday, USMartinLutherKingJr, USPresidentsDay, GoodFriday,
                                    USMemorialDay, USLaborDay, USThanksgivingDay, nearest_workday)
from pandas.tseries.offsets import CustomBusinessDay

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))


class Exch(AbstractHolidayCalendar):
    rules = [Holiday("NewYear", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay, GoodFriday, USMemorialDay,
             Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
             Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
             Holiday("Christmas", month=12, day=25, observance=nearest_workday)]


HOL = set(Exch().holidays("2000-01-01", "2035-12-31"))
BD = CustomBusinessDay(holidays=sorted(HOL))
CODES = "FGHJKMNQUVXZ"


def isbd(d):
    return d.dayofweek < 5 and d not in HOL


def bdays(a, b):
    return pd.date_range(a, b, freq=BD)


def prev_bd(d, n=1):
    return d - n * BD


def next_bd(d, n=1):
    return d + n * BD


def first_bd(m):
    return bdays(m.start_time, m.end_time.normalize())[0]


def last_bd(m):
    return bdays(m.start_time, m.end_time.normalize())[-1]


# ───────── rules: each returns dict of dates for contract month m (pandas Period) ─────────
def cbot_grain(m):
    """CBOT grains: LTD = business day before the 15th; FND = last business day of the prior month; FPD = the business day
    before FND (two business days before the delivery month). Longs must be out before FPD to avoid delivery."""
    fifteenth = pd.Timestamp(m.year, m.month, 15)
    ltd = prev_bd(fifteenth)
    fnd = last_bd(m - 1)
    fpd = prev_bd(fnd)
    return {"fpd": fpd, "fnd": fnd, "ltd": ltd, "out_by": prev_bd(fpd)}


def ice_cotton(m):
    """ICE cotton No. 2: FND = five business days before the first business day of the delivery month; LTD = seventeen
    business days from the end of the delivery month."""
    fnd = prev_bd(first_bd(m), 5)
    ltd = bdays(m.start_time, m.end_time.normalize())[-17]
    return {"fnd": fnd, "ltd": ltd, "out_by": prev_bd(fnd)}


def cme_le(m):
    """Live cattle: physical delivery; LTD = last business day of the contract month (noon CT). Deliveries can be
    tendered from the first business day of the contract month, so speculative longs exit before it."""
    fnd = first_bd(m)
    return {"fnd": fnd, "ltd": last_bd(m), "out_by": prev_bd(fnd)}


def cme_he(m):
    """Lean hogs: cash-settled to the CME Lean Hog Index; LTD = 10th business day of the contract month (noon CT)."""
    ltd = bdays(m.start_time, m.end_time.normalize())[9]
    return {"ltd": ltd, "out_by": ltd}


def cme_gf(m):
    """Feeder cattle: cash-settled to the CME Feeder Cattle Index; LTD = last Thursday of the contract month, except
    November (the Thursday before Thanksgiving); if that Thursday or any of the four weekdays before it is a holiday, the
    Thursday before."""
    th = [d for d in pd.date_range(m.start_time, m.end_time.normalize()) if d.dayofweek == 3]
    if m.month == 11:
        tg = [d for d in th if d in HOL][0]
        ltd = tg - pd.Timedelta(days=7)
    else:
        ltd = th[-1]
    while any(d in HOL for d in pd.date_range(ltd - pd.Timedelta(days=6), ltd) if d.dayofweek < 5):
        ltd = ltd - pd.Timedelta(days=7)
    return {"ltd": ltd, "out_by": ltd}


def usda_dairy_announcement(m):
    """USDA announces the monthly class and product prices on the last Wednesday on or before the 5th of the next month;
    moved to Thursday when a holiday falls earlier that week."""
    fifth = pd.Timestamp((m + 1).year, (m + 1).month, 5)
    wed = fifth - pd.Timedelta(days=(fifth.dayofweek - 2) % 7)
    if any(d in HOL for d in pd.date_range(wed - pd.Timedelta(days=2), wed)):
        wed = wed + pd.Timedelta(days=1)
    return wed


def cme_dairy(m):
    """Class III / IV milk, cheese, butter, NDM, dry whey: cash-settled; LTD = business day before the USDA announcement."""
    ann = usda_dairy_announcement(m)
    return {"ltd": prev_bd(ann), "settles": ann, "out_by": prev_bd(ann)}


def nymex_cl(m):
    """WTI: LTD = 3 business days before the 25th of the month before delivery (or before the business day preceding
    the 25th when it is not a business day). Physical: positions open after LTD go to delivery at Cushing."""
    d25 = pd.Timestamp((m - 1).year, (m - 1).month, 25)
    ref = d25 if isbd(d25) else prev_bd(d25)
    ltd = prev_bd(ref, 3)
    return {"ltd": ltd, "out_by": prev_bd(ltd, 2)}


def nymex_ng(m):
    """Henry Hub: LTD = 3 business days before the first calendar day of the delivery month. Physical delivery."""
    ltd = prev_bd(m.start_time, 3)
    return {"ltd": ltd, "out_by": prev_bd(ltd, 2)}


def nymex_products(m):
    """ULSD (HO) and RBOB (RB): LTD = last business day of the month before delivery. Physical delivery in NY Harbor."""
    ltd = last_bd(m - 1)
    return {"ltd": ltd, "out_by": prev_bd(ltd, 2)}


MKT = {
    # sym: (name, rule, listed month letters or None for every month, settle type, roll guidance)
    "ZC": ("Corn", cbot_grain, "HKNUZ", "physical", "Roll or exit before first position day; most volume rolls 5-15 days before it (index funds roll on the 5th-9th business day of the month before)."),
    "ZS": ("Soybeans", cbot_grain, "FHKNQUX", "physical", "As corn."),
    "ZM": ("Soybean meal", cbot_grain, "FHKNQUVZ", "physical", "As corn."),
    "ZL": ("Soybean oil", cbot_grain, "FHKNQUVZ", "physical", "As corn."),
    "ZW": ("Chicago wheat", cbot_grain, "HKNUZ", "physical", "As corn."),
    "KE": ("KC wheat", cbot_grain, "HKNUZ", "physical", "As corn."),
    "CT": ("Cotton No. 2", ice_cotton, "HKNVZ", "physical", "Exit or roll before first notice day; open interest and liquidity move to the next month 1-3 weeks earlier."),
    "LE": ("Live cattle", cme_le, "GJMQVZ", "physical", "Speculators exit before the contract month: from its first business day, longs can be assigned live cattle."),
    "GF": ("Feeder cattle", cme_gf, "FHJKQUVX", "cash", "No delivery: can be held to final cash settlement on the CME Feeder Cattle Index; liquidity thins in the last week."),
    "HE": ("Lean hogs", cme_he, "GJKMNQVZ", "cash", "No delivery: can be held to final cash settlement on the CME Lean Hog Index (10th business day); liquidity thins in the last days."),
    "DC": ("Class III milk", cme_dairy, None, "cash", "No delivery: held contracts settle to the USDA announced price; the spot month is thin, so the desk's convergence trades usually hold to settlement."),
    "GDK": ("Class IV milk", cme_dairy, None, "cash", "As Class III."),
    "CSC": ("Cheese", cme_dairy, None, "cash", "As Class III."),
    "CB": ("Butter", cme_dairy, None, "cash", "As Class III."),
    "GNF": ("Nonfat dry milk", cme_dairy, None, "cash", "As Class III."),
    "DY": ("Dry whey", cme_dairy, None, "cash", "As Class III."),
    "CL": ("WTI crude oil", nymex_cl, None, "physical", "Roll at least 2 business days before the last trading day; most volume moves to the next month about a week before it. Micro and E-mini crude are cash-settled and stop trading a few days earlier."),
    "NG": ("Henry Hub natural gas", nymex_ng, None, "physical", "Roll at least 2 business days before the last trading day (3 business days before the delivery month)."),
    "HO": ("NY Harbor ULSD", nymex_products, None, "physical", "Roll before the last business day of the month before delivery."),
    "RB": ("RBOB gasoline", nymex_products, None, "physical", "As ULSD."),
}
EXPLAIN = {
    "fpd": "First position day: the first day a short can declare intent to deliver (CBOT). Longs still holding can be assigned delivery after it.",
    "fnd": "First notice day: the first day delivery notices can be issued to long holders.",
    "ltd": "Last trading day: trading in the contract ends; cash-settled contracts settle to the index or USDA price, physical ones go to delivery.",
    "out_by": "Desk rule: the last day to roll or exit a speculative position (business day before the first position / notice day for physical contracts, the last trading day for cash-settled ones; two business days before the last trading day for energy).",
}


def contracts_for(sym, start, n):
    name, rule, letters, kind, roll = MKT[sym]
    out, m = [], start.to_period("M") - 1
    while len(out) < n:
        m += 1
        if letters and CODES[m.month - 1] not in letters:
            continue
        d = rule(m)
        out.append({"contract": f"{sym}{CODES[m.month - 1]}{m.year}", "month": str(m), **{k: str(v.date()) for k, v in d.items()}})
    return out


def check():
    """Rule vs the last date each expired contract traded in data/contracts (TradingView daily bars)."""
    from futures_io import load_contracts
    res = {}
    for sym, (_, rule, letters, *_r) in MKT.items():
        try:
            f = load_contracts(sym)
        except Exception:
            continue
        last = f.groupby("m").date.max()
        last = last[(last < pd.Timestamp.today() - pd.Timedelta(days=10)) & (last.index.year >= 2015)]
        off = {}
        for m, d in last.items():
            if letters and CODES[m.month - 1] not in letters:
                continue
            ltd = rule(m)["ltd"]
            k = (len(bdays(ltd, d)) - 1) if d >= ltd else -(len(bdays(d, ltd)) - 1)
            off[k] = off.get(k, 0) + 1
        res[sym] = {"checked": sum(off.values()), "exact": off.get(0, 0),
                    "offsets_business_days": {str(k): v for k, v in sorted(off.items())}}
    return res


def main():
    today = pd.Timestamp(date.today())
    out = {"generated": today.strftime("%Y-%m-%d"), "explain": EXPLAIN, "markets": {}}
    for sym, (name, rule, letters, kind, roll) in MKT.items():
        rows = [r for r in contracts_for(sym, today - pd.Timedelta(days=45), 10 if letters else 14) if r["ltd"] >= str(today.date())][:7]
        for r in rows:
            r["days_to_out"] = int(len(bdays(today, pd.Timestamp(r["out_by"]))) - 1) if r["out_by"] >= str(today.date()) else 0
        out["markets"][sym] = {"name": name, "settle": kind, "roll": roll, "rule": " ".join(rule.__doc__.split()), "contracts": rows}
    if "--check" in sys.argv or date.today().weekday() == 0:
        out["check"] = check()
    else:
        try:
            out["check"] = json.loads((ROOT / "data" / "specs" / "calendar.json").read_text()).get("check")
        except Exception:
            pass
    if out.get("check"):
        for k, v in out["check"].items():
            print(k, v)
    out["check_note"] = ("Rule vs the last daily bar of every expired contract since 2015 (offset in business days). Data bars of +1 or +2 days "
                         "after the rule date are the final-settlement price posted on the settlement day (dairy, hogs, feeders), not trading days.")
    (ROOT / "data" / "specs" / "calendar.json").write_text(json.dumps(out, indent=0))
    for s, v in out["markets"].items():
        c = v["contracts"][0]
        print(s, c["contract"], c.get("fnd", "-"), c["ltd"], c["out_by"])


if __name__ == "__main__":
    main()
