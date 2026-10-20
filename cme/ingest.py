"""Write a CME browser-collector payload into data/cme/.

Usage: python cme/ingest.py <payload-file>

The payload is the gzip+base64 string produced in the browser by collect.js
(optionally wrapped in a tool-result JSON array, or JSON-quoted). For each
trade date it writes:
  data/cme/<YYYYMMDD>/fut_volume_oi.csv
  data/cme/<YYYYMMDD>/opt_volume_oi.csv
  data/cme/<YYYYMMDD>/fut_settlements.csv
A later run for the same date (FINAL replacing PRELIMINARY) overwrites the files.
"""
import base64, csv, gzip, io, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "data" / "cme"


def load_payload(path):
    raw = Path(path).read_text().strip()
    if raw.startswith("["):  # tool-result wrapper: [{"type":"text","text":...}]
        raw = json.loads(raw)[0]["text"]
    m = re.search(r"[A-Za-z0-9+/=]{1000,}", raw)
    if not m:
        raise SystemExit("no base64 payload found")
    return json.loads(gzip.decompress(base64.b64decode(m.group(0))))


def split_by_date(text):
    rows = list(csv.reader(io.StringIO(text)))
    header, body = rows[0], rows[1:]
    by = defaultdict(list)
    for r in body:
        by[r[0]].append(r)
    return header, by


def main(path):
    p = load_payload(path)
    written = []
    for key in ("fut_volume_oi", "opt_volume_oi", "fut_settlements"):
        header, by = split_by_date(p[key])
        for td, rows in by.items():
            out = ROOT / td / f"{key}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(header)
                w.writerows(rows)
            written.append(f"{out.relative_to(ROOT.parent.parent)} ({len(rows)} rows)")
    if p.get("errors"):
        print("collector errors:", *p["errors"], sep="\n  ")
    print("\n".join(written))


if __name__ == "__main__":
    main(sys.argv[1])
