"""Parse archived NASS text releases (data/esmis/) into first-print tables with release dates."""
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ESMIS = ROOT / "data" / "esmis"
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}
NUM = r"([\d,]+|\(NA\)|\(D\)|-)"


def released(text):
    m = re.search(r"Released\s+(\w+\s+\d{1,2},\s+\d{4})", text)
    return pd.to_datetime(m.group(1)) if m else None


def n(x):
    try:
        return float(x.replace(",", ""))
    except Exception:
        return None


def hogs_and_pigs():
    """One row per release: quarter reported (first print), weight groups, breeding, market; prev-year column too."""
    rows = []
    for p in sorted((ESMIS / "hogs-and-pigs").glob("*.txt")):
        t = p.read_text(errors="ignore")
        rel = released(t)
        if rel is None or "Special" in p.name:
            continue
        latest = None
        # the quarterly class/weight-group table: header "Item : yyyy : yyyy", then "<Month> 1 Inventory" blocks
        for m in re.finditer(r"Item\s*:\s*(\d{4})\s*:\s*(\d{4})\s*:", t):
            tbl = t[m.start():m.start() + 5000]
            if not re.search(r"Weight Group", t[max(0, m.start() - 600):m.start()], re.I):
                continue
            y_prev, y_cur = int(m.group(1)), int(m.group(2))
            blocks = re.split(r"\n\s*(\w+) 1 inventory[^\n]*", tbl, flags=re.I)
            for j in range(1, len(blocks), 2):
                mon, body = blocks[j].capitalize(), blocks[j + 1]
                vals = {}
                for key, pat in (("all", r"All hogs and pigs"), ("breeding", r"Kept for breeding"), ("market", r"\n\s+Market\b(?! hogs)"),
                                 ("lt50", r"Under [56]0 pounds"), ("50_119", r"[56]0-119 pounds"), ("120_179", r"120-179 pounds"),
                                 ("ge180", r"180 pounds and over")):
                    mm = re.search(pat + r"[ .]*:\s*" + NUM + r"(?:[ \t]+" + NUM + r")?", body, re.I)
                    if mm:
                        vals[key] = (n(mm.group(1)), n(mm.group(2)) if mm.group(2) else None)
                if mon == rel.strftime("%B") and all(k in vals and vals[k][1] is not None for k in ("lt50", "50_119", "120_179", "ge180")):
                    latest = (mon, vals, rel.year)
            if latest:
                break
        if latest is None:
            continue
        mon, vals, year = latest
        qm = MONTHS.get(mon)
        row = {"file": p.name, "released": rel.date(), "quarter": str(pd.Period(f"{year}-{qm:02d}", "M"))}
        for k, (a, b) in vals.items():
            row[k + "_prev"], row[k] = a, b
        rows.append(row)
    d = pd.DataFrame(rows).sort_values("released").drop_duplicates("quarter", keep="first")
    return d.reset_index(drop=True)


def milk_production():
    """First-print US milk production headline per monthly release."""
    rows = []
    for p in sorted((ESMIS / "milk-production").glob("*.txt")):
        t = re.sub(r"\s+", " ", p.read_text(errors="ignore"))
        rel = released(t)
        m = re.search(r"Milk production in the United States during (\w+) totaled ([\d.]+) billion pounds, (up|down) ([\d.]+) percent from \w+ (\d{4})", t)
        if not (rel and m):
            continue
        mon, prod, sign, pct, ly = m.groups()
        yr = int(ly) + 1
        pc = re.search(r"Production per cow in the United States averaged ([\d,]+) pounds", t)
        cw = re.search(r"number of milk cows on farms in the United States was ([\d.]+) million head, ([\d,]+) head (more|less) than", t)
        rows.append(dict(released=rel.date(), month=f"{yr}-{MONTHS[mon]:02d}", production_bn_lb=float(prod),
                         yoy_pct=float(pct) * (1 if sign == "up" else -1),
                         per_cow_lb=n(pc.group(1)) if pc else None, cows_mil=float(cw.group(1)) if cw else None,
                         cows_yoy_k=(n(cw.group(2)) / 1000 * (1 if cw.group(3) == "more" else -1)) if cw else None))
    return pd.DataFrame(rows).sort_values("month").drop_duplicates("month", keep="first").reset_index(drop=True)


if __name__ == "__main__":
    d = hogs_and_pigs()
    print(len(d), d.quarter.min(), d.quarter.max())
    print(d.tail(8).to_string())
