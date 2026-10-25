#!/usr/bin/env python3
"""Ingest CME option settlements collected in the browser (cme/collect_options.js) and derive implied vols.

Input: the gzip+base64 payload (plain, JSON-quoted, or a tool-result JSON array). For each product, trade date and
option expiry it parses strikes and settlements into the futures price units used on the desk, attaches the
underlying futures settlement for the same trade date, the exact option last-trade date from CME's product
calendar, and backs out Black-76 implied vol, delta and gamma (European approximation of American options; the
early-exercise premium on options on futures is small, and only out-of-the-money options feed the smile).

Writes data/cme/options/<YYYYMMDD>/<SYM>.csv.gz (one file per product per trade date; re-runs overwrite).
"""
import base64, gzip, io, json, math, re, sys
from datetime import date, datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cme" / "options"
MON = {m: i + 1 for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
EIGHTHS = {"ZC", "ZS", "ZW", "KE"}             # prices quoted in cents and eighths: 242'1 = 242.125
STRIKE_X100 = {"ZC", "ZS", "ZW", "KE"}          # strikes quoted in $/bu
SERIAL_TO_NEXT = {"ZC", "ZS", "ZM", "ZL", "ZW", "KE"}   # serial options exercise into the next listed futures
RATE = 0.04


def load(path):
    raw = Path(path).read_text().strip()
    if raw.startswith("["):
        raw = json.loads(raw)[0]["text"]
    m = re.search(r"H4sI[A-Za-z0-9+/=]+", raw)
    return json.loads(gzip.decompress(base64.b64decode(m.group(0))))


def num(s, sym):
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if s in ("", "-", "CAB", "UNCH"):
        return None
    s = re.sub(r"[A-Za-z]+$", "", s)   # trailing B/A flags on highs/lows
    if sym in EIGHTHS and "'" in s:
        a, b = s.split("'")
        neg = a.startswith("-")
        v = abs(float(a or 0)) + float(b[:1] or 0) / 8
        return -v if neg else v
    try:
        return float(s)
    except ValueError:
        return None


def N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(cp, F, K, T, v, r=RATE):
    if T <= 0 or v <= 0:
        return max(F - K, 0) if cp == "C" else max(K - F, 0)
    s = v * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * v * v * T) / s
    d2 = d1 - s
    df = math.exp(-r * T)
    return df * (F * N(d1) - K * N(d2)) if cp == "C" else df * (K * N(-d2) - F * N(-d1))


def implied(cp, F, K, T, px):
    if px is None or T <= 0 or F <= 0 or K <= 0:
        return None
    intrinsic = math.exp(-RATE * T) * (max(F - K, 0) if cp == "C" else max(K - F, 0))
    if px <= intrinsic + 1e-9:
        return None
    lo, hi = 0.005, 5.0
    if b76(cp, F, K, T, hi) < px:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if b76(cp, F, K, T, mid) > px:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def greeks(cp, F, K, T, v):
    if not v or T <= 0:
        return None, None
    s = v * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * v * v * T) / s
    df = math.exp(-RATE * T)
    delta = df * N(d1) if cp == "C" else -df * N(-d1)
    gamma = df * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (F * s)
    return delta, gamma


def main(path):
    d = load(path)
    written = []
    for sym, p in d["products"].items():
        cal = {}
        for code, cm, lt in p.get("calendar", []):
            try:
                cal[code] = datetime.strptime(lt, "%d %b %Y").date()
            except ValueError:
                pass
        fut = {}
        for td, rows in p.get("futures", {}).items():
            fm = {}
            for mo, st, oi, vol in rows:
                mm = re.match(r"([A-Z]{3}) (\d{2})", mo)
                v = num(st, sym)
                if mm and v:
                    fm[(2000 + int(mm[2]), MON[mm[1]])] = (v, num(oi, sym))
            fut[td] = fm
        for td in {e["td"] for e in p.get("exps", [])} - set(fut):   # underlying skipped (FUTHAVE): read collect.js's file
            f = ROOT / "data" / "cme" / datetime.strptime(td, "%m/%d/%Y").strftime("%Y%m%d") / "fut_settlements.csv"
            fm = {}
            if f.exists():
                for r in pd.read_csv(f, dtype=str).query("sym == @sym").itertuples():
                    mm = re.match(r"([A-Z]{3}) (\d{2})", str(r.month))
                    v = num(r.settle, sym)
                    if mm and v:
                        fm[(2000 + int(mm[2]), MON[mm[1]])] = (v, num(r.oi, sym))
            fut[td] = fm
        by_td = {}
        for e in p.get("exps", []):
            td = e["td"]
            tdd = datetime.strptime(td, "%m/%d/%Y").date()
            fm = fut.get(td, {})
            ym = (e["year"], e["month"])
            if sym in SERIAL_TO_NEXT:
                cands = sorted(k for k in fm if k >= ym)
            else:
                cands = [ym] if ym in fm else []
            if not cands:
                continue
            uy, um = cands[0]
            F = fm[(uy, um)][0]
            ex = cal.get(e["contract"])
            if ex is None:
                continue
            T = max((ex - tdd).days, 0) / 365 + 0.5 / 365
            for cp, k, st, oi, vol, chg in e["rows"]:
                K = num(k, sym)
                if K is None:
                    continue
                if sym in STRIKE_X100:
                    K = round(K * 100, 4)
                px = num(st, sym)
                iv = implied(cp, F, K, T, px) if px is not None else None
                de, ga = greeks(cp, F, K, T, iv)
                by_td.setdefault(tdd, []).append({
                    "date": tdd.isoformat(), "sym": sym, "contract": e["contract"], "label": e["label"], "expiry": ex.isoformat(),
                    "underlying": f"{['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'][um - 1]} {str(uy)[2:]}",
                    "F": F, "dte": (ex - tdd).days, "T": round(T, 5), "cp": cp, "strike": K, "settle": px,
                    "oi": int(num(oi, sym) or 0), "volume": int(num(vol, sym) or 0), "report": e.get("report"),
                    "iv": None if iv is None else round(iv * 100, 3), "delta": None if de is None else round(de, 4), "gamma": None if ga is None else round(ga, 6)})
        for tdd, rows in by_td.items():
            o = OUT / tdd.strftime("%Y%m%d")
            o.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(rows)
            df.to_csv(o / f"{sym}.csv.gz", index=False, compression="gzip")
            written.append((tdd.isoformat(), sym, len(df), int(df.iv.notna().sum())))
    for w in sorted(written):
        print(*w)
    print("errors:", len(d.get("errors", [])), (d.get("errors") or [])[:3])


if __name__ == "__main__":
    main(sys.argv[1])
