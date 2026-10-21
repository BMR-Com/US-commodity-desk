#!/usr/bin/env python3
"""Keep the repo and the published site small. Safe to run any time (idempotent); runs weekly from data.yml.

1. Dated daily folders older than KEEP_DAYS (default 183, about 6 months) are deleted, after their lasting
   content is kept elsewhere:
   - data/cme/<YYYYMMDD>/ (nightly CME futures): per-symbol total open interest and volume go to
     data/cme/oi_history.csv first (models/flows.py reads it for the OI history chart);
   - data/cme/options/<YYYYMMDD>/ (CME option settlements): the implied-vol statistics already live in
     data/cme/options/iv_history.csv (models/options_desk.py needs only the latest ~12 days of files);
   - data/brief/<YYYY-MM-DD>.md (morning brief archive).
2. Archives that are read only by the Python models are stored gzipped (5-20x smaller):
   - data/esmis/<slug>/*.txt -> *.txt.gz (NASS report text, read by models/esmis_parse.py);
   - data/grains/raw/crop_progress|annual/<commodity>/<year>.csv -> .csv.gz (NASS QuickStats, read by
     models/grains_condition.py).
Deleting a file shrinks the working tree (and so the GitHub Pages site); git history keeps old versions.
"""
import csv, gzip, os, re, shutil, sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
KEEP_DAYS = int(os.environ.get("KEEP_DAYS", "183"))
CUT = date.today() - timedelta(days=KEEP_DAYS)
DRY = "--dry-run" in sys.argv
freed = 0


def size(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


def remove(p):
    global freed
    freed += size(p)
    print("  delete", p.relative_to(ROOT))
    if not DRY:
        shutil.rmtree(p) if p.is_dir() else p.unlink()


def day_of(name):
    m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})(\.md)?", name)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def num(x):
    try:
        return float(str(x).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def cme_futures():
    hist = D / "cme" / "oi_history.csv"
    have = set()
    if hist.exists():
        with hist.open() as f:
            have = {(r["date"], r["sym"]) for r in csv.DictReader(f)}
    old = sorted(p for p in (D / "cme").glob("2*") if p.is_dir() and day_of(p.name) and day_of(p.name) < CUT)
    rows = []
    for p in old:
        f = p / "fut_volume_oi.csv"
        if f.exists():
            tot = {}
            with f.open() as fh:
                for r in csv.DictReader(fh):
                    t = tot.setdefault(r["sym"], [0, 0])
                    t[0] += num(r.get("oi"))
                    t[1] += num(r.get("total_vol"))
            rows += [[p.name, s, int(v[0]), int(v[1])] for s, v in sorted(tot.items()) if (p.name, s) not in have]
    if rows and not DRY:
        new = not hist.exists()
        with hist.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "sym", "oi", "volume"])
            w.writerows(rows)
    print(f"cme futures: {len(old)} folders older than {CUT}, {len(rows)} OI rows kept in oi_history.csv")
    for p in old:
        remove(p)


def cme_options():
    old = [p for p in (D / "cme" / "options").glob("2*") if p.is_dir() and day_of(p.name) and day_of(p.name) < CUT]
    print(f"cme options: {len(old)} folders older than {CUT} (stats are in iv_history.csv)")
    for p in sorted(old):
        remove(p)


def brief():
    old = [p for p in (D / "brief").glob("2*.md") if day_of(p.name) and day_of(p.name) < CUT]
    print(f"brief archive: {len(old)} older than {CUT}")
    for p in sorted(old):
        remove(p)


def gz(p):
    global freed
    out = p.with_name(p.name + ".gz")
    b = p.read_bytes()
    z = gzip.compress(b, 9, mtime=0)
    freed += len(b) - len(z)
    if not DRY:
        out.write_bytes(z)
        p.unlink()


def compress():
    n = 0
    for p in (D / "esmis").glob("*/*.txt"):
        gz(p); n += 1
    for sub in ("crop_progress", "annual"):
        for p in (D / "grains" / "raw" / sub).glob("*/*.csv"):
            gz(p); n += 1
    print(f"compressed {n} files")


if __name__ == "__main__":
    print(f"retention: keep {KEEP_DAYS} days (delete before {CUT}){' [dry run]' if DRY else ''}")
    cme_futures()
    cme_options()
    brief()
    compress()
    print(f"freed {freed / 1e6:.1f} MB from the working tree")
