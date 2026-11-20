"""Weekly price-history backup: packs every stored price / settlement / OI / ICE-upload history file into one dated
.tar.gz with a manifest (file, rows, first and last date), for .github/workflows/price_backup.yml to attach to a
GitHub release (tag prices-YYYY-MM-DD). Releases live outside the git tree, so a bad run that overwrites a CSV cannot
touch them; the Mac collector (local/mac_collector.py) also downloads the newest one to ~/BMR-Com-backups/.

Usage: python pipelines/price_backup.py <repo-name>     -> backup/prices_<repo>_<date>.tar.gz, backup/manifest.csv
"""
import csv, io, sys, tarfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# everything that is a market price/settlement/OI/vol time series or a manual exchange upload; paths that do not
# exist in a repo are skipped
PATHS = [
    "data/contracts", "data/ohlc", "data/price_archive", "data/prices", "data/cme", "data/markets", "data/energy",
    "data/options", "data/vol", "data/basis", "data/macro", "data/delivery", "data/palm/raw/prices.csv",
    "data/coffee", "data/cocoa", "data/sugar", "data/cotton/ice", "data/ice_staging", "data/ice_raw", "data/ice_inbox",
    "coffee/data", "sugar/data", "cot/data/prices",
]


def dates_rows(p):
    """(rows, first date, last date) of a CSV with a date-like first or 'date'/'trade_date' column; blanks otherwise."""
    if p.suffix != ".csv":
        return "", "", ""
    try:
        with p.open(newline="", encoding="utf-8", errors="replace") as f:
            r = csv.reader(f)
            head = next(r, [])
            low = [h.strip().lower() for h in head]
            i = next((low.index(k) for k in ("date", "trade_date", "tradedate", "report_date") if k in low), None)
            n, lo, hi = 0, None, None
            for row in r:
                n += 1
                if i is not None and i < len(row) and row[i][:2] in ("19", "20"):
                    v = row[i].strip()
                    lo = v if lo is None or v < lo else lo
                    hi = v if hi is None or v > hi else hi
            return n, lo or "", hi or ""
    except Exception:
        return "", "", ""


def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else ROOT.name
    out = ROOT / "backup"
    out.mkdir(exist_ok=True)
    files = []
    for rel in PATHS:
        p = ROOT / rel
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += sorted(q for q in p.rglob("*") if q.is_file() and q.suffix != ".pdf")   # staged PDFs are re-parsed copies
    files = sorted(set(files))
    man = io.StringIO()
    w = csv.writer(man)
    w.writerow(["file", "bytes", "rows", "first_date", "last_date"])
    for p in files:
        w.writerow([p.relative_to(ROOT).as_posix(), p.stat().st_size, *dates_rows(p)])
    (out / "manifest.csv").write_text(man.getvalue())
    tgz = out / f"prices_{repo}_{date.today():%Y-%m-%d}.tar.gz"
    with tarfile.open(tgz, "w:gz") as t:
        for p in files:
            t.add(p, arcname=p.relative_to(ROOT).as_posix())
        t.add(out / "manifest.csv", arcname="manifest.csv")
    print(f"{len(files)} files -> {tgz.name} ({tgz.stat().st_size / 1e6:.1f} MB)")
    if not files:
        sys.exit("nothing to back up")


if __name__ == "__main__":
    main()
