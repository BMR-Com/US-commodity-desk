"""USDA AgTransport weekly grain basis (Grain Transportation Report data, Socrata dataset v85y-3hep), 2007-.

Weekly cash bid, futures and basis by market (Gulf, Great Lakes, Atlantic, Portland, state elevator bids) for corn,
soybeans and wheat by class. Full refresh each run (about 30k rows); written to
data/grains/raw/agtransport/grain_basis.csv.gz
"""
from pathlib import Path
import io
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grains" / "raw" / "agtransport"
URL = "https://agtransport.usda.gov/resource/v85y-3hep.csv"


def main():
    r = requests.get(URL, params={"$limit": 2000000}, headers={"User-Agent": "Mozilla/5.0"}, timeout=300)
    r.raise_for_status()
    d = pd.read_csv(io.StringIO(r.text))
    if len(d) < 10000:
        raise SystemExit(f"too few rows ({len(d)}), keeping the previous file")
    d["date"] = pd.to_datetime(d.date).dt.date
    d = d[["date", "market_name", "market_type", "commodity", "bid", "contract_month", "futures_price", "basis"]].sort_values(["date", "commodity", "market_name"])
    OUT.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT / "grain_basis.csv.gz", index=False)
    print("agtransport basis", len(d), d.date.min(), d.date.max())


if __name__ == "__main__":
    main()
