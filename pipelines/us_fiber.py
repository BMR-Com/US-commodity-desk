"""US textile and apparel imports by fibre, monthly (cotton vs man-made fibre share).

Source: UN Comtrade public preview API (free, no key) - US monthly imports (reporter 842, partner World) at HS 6-digit
for chapters 50-63, the same Census data OTEXA publishes. Each HS6 code is classed cotton / man-made / other / mixed
from its description (chapters 52 = cotton, 54-55 = man-made; elsewhere "of cotton", "of synthetic/artificial/man-made
fibres" in the heading text). Value is reported; net weight (kg) is Comtrade's estimate where the US reports units.

Stored: data/fiber/raw/us_imports_hs6.csv (period, cmd, value_usd, net_kg, qty, qty_unit). Only months not stored
yet are requested (plus the latest stored month again, for revisions); the file is never shrunk.
"""
import csv, io, json, re, sys, time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "fiber" / "raw"
OUT = RAW / "us_imports_hs6.csv"
CODES = RAW / "hs6_fiber_codes.json"
COLS = ["period", "cmd", "value_usd", "net_kg", "qty", "qty_unit"]
START = (2015, 1)
H = {"User-Agent": "Mozilla/5.0 (research desk; contact via GitHub BMR-Com)"}
BASE = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
BUDGET = 1200   # seconds per run; a first backfill finishes over a few runs

MMF = re.compile(r"man-made|manmade|synthetic|artificial|polyester|nylon|polyamide|polyethylene|polypropylene|acrylic|viscose|aramid|elastomeric|filament", re.I)
COT = re.compile(r"\bcotton\b", re.I)
NOT_COT = re.compile(r"other than cotton|excluding cotton|\(excl\.? cotton", re.I)


def classify(code, text):
    ch = int(code[:2])
    if ch == 52:
        return "cotton"
    if ch in (54, 55):
        return "mmf"
    if ch in (50, 51, 53):
        return "other"
    t = text.split(" - ", 1)[-1]
    if COT.search(t) and not NOT_COT.search(t) and not MMF.search(t):
        return "cotton"
    if MMF.search(t) and not COT.search(t):
        return "mmf"
    if re.search(r"\bwool|fine animal hair|silk|flax|jute|sisal|abaca|vegetable textile|bast", t, re.I) and not COT.search(t) and not MMF.search(t):
        return "other"
    return "mixed"   # "of other textile materials", "knitted" without fibre, cotton/man-made mixes, 6309 worn clothing


def get(url, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, headers=H, timeout=90)
            if r.status_code == 200:
                return r.json()
            print("http", r.status_code, url[:120])
        except Exception as e:
            print("error", str(e)[:120])
        time.sleep(6 * (i + 1))
    return None


def codes():
    if CODES.exists():
        return json.loads(CODES.read_text())
    j = get("https://comtradeapi.un.org/files/v1/app/reference/HS.json")
    res = j.get("results", j)
    out = {x["id"]: {"text": x["text"], "fiber": classify(x["id"], x["text"]), "unit": x.get("standardUnitAbbr")}
           for x in res if re.fullmatch(r"(5\d|6[0-3])\d{4}", x["id"])}
    RAW.mkdir(parents=True, exist_ok=True)
    CODES.write_text(json.dumps(out, indent=0, sort_keys=True))
    from collections import Counter
    print("hs6 classes:", Counter(v["fiber"] for v in out.values()))
    for k, v in sorted(out.items()):
        if v["fiber"] == "mixed" and k[:2] in ("61", "62"):
            print("  mixed", k, v["text"][:110])
    return out


def load():
    if not OUT.exists():
        return {}
    with OUT.open() as f:
        return {(r["period"], r["cmd"]): r for r in csv.DictReader(f)}


def save(rows, n_old):
    if len(rows) < n_old:
        sys.exit("refusing to shrink the stored history")
    buf = io.StringIO()
    w = csv.DictWriter(buf, COLS)
    w.writeheader()
    for k in sorted(rows):
        w.writerow({c: rows[k].get(c, "") for c in COLS})
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(buf.getvalue())
    tmp.replace(OUT)


def months():
    y, m = START
    t = date.today()
    while (y, m) <= (t.year, t.month):
        yield f"{y}{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main():
    C = sorted(codes())
    rows = load()
    n_old = len(rows)
    have = sorted({p for p, _ in rows})
    # months already stored are skipped, except the latest two (revisions); empty months (not yet published) retried
    todo = [p for p in months() if p not in have or p in have[-2:]]
    todo.reverse()                      # newest first, then backfill
    groups = [C[i:i + 110] for i in range(0, len(C), 110)]
    t0, calls, got = time.time(), 0, 0
    for i in range(0, len(todo), 4):
        per = todo[i:i + 4]
        for g in groups:
            if time.time() - t0 > BUDGET:
                break
            j = get(f"{BASE}?reporterCode=842&period={','.join(per)}&flowCode=M&partnerCode=0&cmdCode={','.join(g)}")
            calls += 1
            time.sleep(1.2)
            if not j:
                continue
            d = j.get("data") or []
            if len(d) >= 500:
                print("warning: 500-row cap hit", per, g[0])
            for x in d:
                if x.get("partner2Code", 0) != 0 or str(x.get("customsCode")) != "C00" or str(x.get("motCode")) != "0":
                    continue
                k = (str(x["period"]), x["cmdCode"])
                rows[k] = {"period": k[0], "cmd": k[1], "value_usd": x.get("primaryValue") or 0, "net_kg": x.get("netWgt") or 0,
                           "qty": x.get("qty") or 0, "qty_unit": x.get("qtyUnitCode")}
                got += 1
        if time.time() - t0 > BUDGET:
            break
        save(rows, n_old)
    save(rows, n_old)
    have = sorted({p for p, _ in rows})
    print(f"us_fiber: {calls} calls, {got} rows read, {len(rows)} stored, months {have[0] if have else '-'}..{have[-1] if have else '-'}")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    main()
