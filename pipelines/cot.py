"""CFTC Commitments of Traders for the desk's contracts (no key), full history.

Writes data/cot/<sym>.csv from the Disaggregated futures-and-options combined report
(Socrata dataset kh3c-gbw2), plus the futures-only version (72hh-3qpy).
"""
import csv, io, time
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "cot"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
CODES = {  # CFTC contract market codes
    "DC": "052641", "GDK": "052644", "GNF": "052642", "DY": "052645", "CB": "050642", "CSC": "063642",
    "HE": "054642", "LE": "057642", "GF": "061641",
    "ZC": "002602", "ZS": "005602", "ZM": "026603", "ZL": "007601", "ZW": "001602", "KE": "001612",
}
SETS = {"fo": "kh3c-gbw2", "fut": "72hh-3qpy"}


def fetch(ds, code):
    rows, off = [], 0
    while True:
        u = (f"https://publicreporting.cftc.gov/resource/{ds}.csv?cftc_contract_market_code={code}"
             f"&$order=report_date_as_yyyy_mm_dd&$limit=50000&$offset={off}")
        for i in range(3):
            try:
                r = requests.get(u, headers=H, timeout=120)
                if r.status_code == 200:
                    break
            except Exception as e:
                print("err", e)
            time.sleep(5)
        else:
            return rows
        part = list(csv.DictReader(io.StringIO(r.text)))
        rows += part
        if len(part) < 50000:
            return rows
        off += 50000


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for sym, code in CODES.items():
        for tag, ds in SETS.items():
            rows = fetch(ds, code)
            if not rows:
                print(sym, tag, "no rows")
                continue
            with (OUT / f"{sym}_{tag}.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
            print(sym, tag, len(rows), rows[-1].get("report_date_as_yyyy_mm_dd", "")[:10])
