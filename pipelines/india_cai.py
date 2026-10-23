"""Cotton Association of India daily spot rates (caionline.in, the page's own date lookup), new dates only.
Writes data/india/cai_spot.csv: date, growth, grade_standard, staple, micronaire, strength_gpt, season, per_candy, per_quintal.
A candy is 355.62 kg of lint; rates are ex-gin, excluding tax. Kept separate from the China data.
"""
import csv, io, sys, time
from datetime import date, timedelta
from pathlib import Path
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "india" / "cai_spot.csv"
URL = "https://www.caionline.in/details/cai/spot-rates/by/date"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
     "Referer": "https://www.caionline.in/details/cai/spot-rates", "X-Requested-With": "XMLHttpRequest"}
COLS = ["date", "growth", "grade_standard", "staple", "micronaire", "strength_gpt", "season", "per_candy", "per_quintal"]
START = date(2025, 10, 1)


def day(d):
    r = requests.post(URL, data={"date": d.strftime("%d-%m-%Y")}, headers=H, timeout=40)
    r.raise_for_status()
    j = r.json()
    rows = []
    for x in (j.get("list") or []) + (j.get("master") or []):
        for season, candy, qtl in (("current", x.get("per_candy"), x.get("per_quintal")), ("previous", x.get("p_per_candy"), x.get("p_per_quintal"))):
            try:
                c = float(candy or 0)
            except ValueError:
                c = 0
            if c > 0:
                rows.append([d.isoformat(), x.get("growth"), x.get("grade_standard"), x.get("staple"), x.get("micronaire"), x.get("strength_gpt"), season, c, qtl])
    return rows


def save(old, new):
    keep = {(r[0], r[1], r[2], r[3], r[6]): r for r in old}
    for r in new:
        keep[(r[0], r[1], r[2], r[3], r[6])] = [str(v) for v in r]
    if len(keep) < len(old):
        sys.exit("refusing to shrink the stored history")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLS)
    for k in sorted(keep):
        w.writerow(keep[k])
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(buf.getvalue())
    tmp.replace(OUT)
    return list(keep.values())


MAX_DATES = 80          # per run, so a first backfill finishes over a few runs and every run saves what it got


if __name__ == "__main__":
    old = []
    if OUT.exists():
        with OUT.open() as f:
            old = list(csv.reader(f))[1:]
    have = {r[0] for r in old}
    last = max((date.fromisoformat(d) for d in have), default=START - timedelta(days=1))
    d, new, n, t0 = max(START, last - timedelta(days=3)), [], 0, time.time()
    while d <= date.today() and n < MAX_DATES and time.time() - t0 < 420:
        if d.weekday() != 6:
            try:
                new += day(d)
                n += 1
            except Exception as e:
                print(d, "error", str(e)[:120])
            time.sleep(0.5)
        d += timedelta(days=1)
    rows = save(old, new) if new else old
    print(f"cai: {n} dates read up to {d - timedelta(days=1)}, {len(new)} rows, {len(rows)} stored")
