"""Per-contract futures settlements from data/contracts/<SYM>.csv with exchange trade dates.

TradingView stamps evening-open sessions (CME dairy, NYMEX energy, ICE cotton on Sundays) one day early; files written
before the fix in pipelines/tvdates.py are repaired here at read time (idempotent once the nightly job rewrites them).
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from tvdates import fix_stored  # noqa: E402

CODES = "FGHJKMNQUVXZ"


def load_contracts(sym):
    f = pd.read_csv(ROOT / "data" / "contracts" / f"{sym}.csv")
    f["date"] = f.groupby("contract", group_keys=False).date.apply(lambda s: fix_stored(s.values).set_axis(s.index))
    f["date"] = pd.to_datetime(f["date"])
    f = f.drop_duplicates(["contract", "date"], keep="last").sort_values(["contract", "date"])
    n = len(sym)
    f["m"] = [pd.Period(f"{c[n + 1:]}-{CODES.index(c[n]) + 1:02d}", "M") for c in f.contract]
    return f
