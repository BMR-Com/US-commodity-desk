"""Print the option settlements already stored for the last 5 trade dates as a JS array for collect_options.js HAVE,
e.g. ["ZC|10/22/2026", ...]. Products CME stopped answering for are missing and get fetched again.
`python3 cme/options_have.py fut` prints FUTHAVE instead: product-dates with futures settlements already stored by
collect.js (data/cme/<date>/fut_settlements.csv), so collect_options.js skips refetching the underlying."""
import csv, json, sys
from pathlib import Path
root = Path(__file__).resolve().parent.parent / "data" / "cme" / "options"
dates = sorted([d.name for d in root.iterdir() if d.is_dir() and d.name.isdigit()])[-5:]
if sys.argv[1:] == ["fut"]:
    base = root.parent
    fd = sorted([d.name for d in base.iterdir() if d.is_dir() and d.name.isdigit()])[-5:]
    out = set()
    for d in fd:
        f = base / d / "fut_settlements.csv"
        if f.exists():
            with f.open() as fh:
                out |= {f"{r['sym']}|{d[4:6]}/{d[6:8]}/{d[:4]}" for r in csv.DictReader(fh) if r.get("settle")}
    print(json.dumps(sorted(out)))
    sys.exit()
print(json.dumps([f"{f.name.split('.')[0]}|{d[4:6]}/{d[6:8]}/{d[:4]}" for d in dates for f in (root / d).glob("*.csv.gz")]))
