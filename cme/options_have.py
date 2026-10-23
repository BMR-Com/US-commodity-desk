"""Print the option settlements already stored for the last 5 trade dates as a JS array for collect_options.js HAVE,
e.g. ["ZC|10/22/2026", ...]. Products CME stopped answering for are missing and get fetched again."""
import json
from pathlib import Path
root = Path(__file__).resolve().parent.parent / "data" / "cme" / "options"
dates = sorted([d.name for d in root.iterdir() if d.is_dir() and d.name.isdigit()])[-5:]
print(json.dumps([f"{f.name.split('.')[0]}|{d[4:6]}/{d[6:8]}/{d[:4]}" for d in dates for f in (root / d).glob("*.csv.gz")]))
