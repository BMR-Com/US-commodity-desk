#!/usr/bin/env python3
"""Light publish gate, run just before a workflow's commit step (data.yml, brief.yml).

Checks the key published JSONs: data/brief/latest.json, data/summary/summary.json, data/derived/balance_sheets.json,
data/grains/derived/esr_brief.json and data/technicals/*.json (each optional: a missing file is skipped, never a failure).
- valid JSON with no NaN / Infinity;
- each market's front price present and positive, and within ±25% of the previously committed value
  (`git show HEAD:<path>`, same market and contract; skipped when there is no committed copy or the contract rolled);
- balance-sheet ending stocks non-negative;
- dates not in the future (one day of slack for evening sessions stamped with the next trade date).
A file that fails is restored to its committed copy (`git checkout HEAD -- <file>`) so a bad upstream value does not
reach the site, with a ::error:: annotation. Exit 1 if anything was restored (the workflow records that and still
commits), else 0.
"""
import glob, json, math, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_MOVE = 0.25
TODAY = datetime.now(timezone.utc).date()
LATEST_OK = (TODAY + timedelta(days=1)).isoformat()


def strict_loads(txt):
    def bad(c):
        raise ValueError(f"non-finite number {c}")
    return json.loads(txt, parse_constant=bad)


def committed(rel):
    try:
        out = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        return strict_loads(out.stdout) if out.returncode == 0 else None
    except Exception:
        return None


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def check_date(errs, label, v):
    if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit() and v[:10] > LATEST_OK:
        errs.append(f"{label} {v} is in the future")


def check_price(errs, label, now, prev):
    if not num(now) or now <= 0:
        errs.append(f"{label}: front price missing or not positive ({now!r})")
    elif num(prev) and prev > 0 and abs(now / prev - 1) > MAX_MOVE:
        errs.append(f"{label}: {now:g} is {100 * (now / prev - 1):+.0f}% vs the committed {prev:g} (limit ±{MAX_MOVE:.0%})")


def v_brief(d, old):
    errs = []
    check_date(errs, "date", d.get("date")); check_date(errs, "generated", d.get("generated"))
    prev = {(m.get("sym"), m.get("contract")): m.get("last") for m in (old or {}).get("markets", [])}
    for m in d.get("markets", []):
        check_price(errs, f"{m.get('sym')} {m.get('contract')}", m.get("last"), prev.get((m.get("sym"), m.get("contract"))))
    return errs


def v_summary(d, old):
    errs = []
    check_date(errs, "generated", d.get("generated"))
    prev = {(m.get("sym"), m.get("contract")): m.get("price") for m in (old or {}).get("markets", [])}
    for m in d.get("markets", []):
        check_price(errs, f"{m.get('sym')} {m.get('contract')}", m.get("price"), prev.get((m.get("sym"), m.get("contract"))))
    return errs


def v_balance(d, old):
    errs = []
    check_date(errs, "generated", d.get("generated"))
    for k, m in (d.get("markets") or {}).items():
        for r in m.get("rows", []):
            if r.get("label", "").strip().lower() != "ending stocks":
                continue
            vals = list((r.get("usda") or {}).values()) + [r.get(s) for s in ("base", "bear", "bull")]
            neg = [v for v in vals if num(v) and v < 0]
            if neg:
                errs.append(f"{k}: negative ending stocks {neg}")
        for s, x in (m.get("summary") or {}).items():
            if num((x or {}).get("end")) and x["end"] < 0:
                errs.append(f"{k} {s}: negative ending stocks {x['end']}")
    return errs


def v_esr(d, old):
    errs = []
    check_date(errs, "generated", d.get("generated"))
    for c in d.get("commodities", []):
        check_date(errs, f"{c.get('key')} week", c.get("week"))
    return errs


def v_tech(d, old):
    errs = []
    check_date(errs, "generated", d.get("generated"))
    prev = {s.get("ticker"): (s.get("bars") or [[None] * 5])[-1] for s in (old or {}).get("series", [])}
    for s in d.get("series", []):
        bars = s.get("bars") or []
        if not bars:
            continue
        last = bars[-1]
        check_date(errs, f"{s.get('ticker')} last bar", last[0])
        if s.get("ticker") != d.get("default"):   # price checks on the front (default) series only; spreads can be negative
            continue
        p = prev.get(s.get("ticker"))
        check_price(errs, f"{s.get('ticker')} close", last[4] if len(last) > 4 else None, p[4] if p and len(p) > 4 else None)
    return errs


FILES = [("data/brief/latest.json", v_brief), ("data/summary/summary.json", v_summary),
         ("data/derived/balance_sheets.json", v_balance), ("data/grains/derived/esr_brief.json", v_esr)]


def main():
    files = FILES + [(str(Path(p).relative_to(ROOT)), v_tech) for p in sorted(glob.glob(str(ROOT / "data/technicals/*.json")))]
    restored, checked = [], 0
    for rel, fn in files:
        p = ROOT / rel
        if not p.exists():
            continue
        checked += 1
        try:
            d = strict_loads(p.read_text())
            errs = fn(d, committed(rel))
        except Exception as e:
            errs = [f"not valid JSON: {e}"]
        if not errs:
            continue
        msg = "; ".join(errs[:6]) + (f" (+{len(errs) - 6} more)" if len(errs) > 6 else "")
        r = subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=ROOT, capture_output=True, text=True)
        what = "restored the committed copy" if r.returncode == 0 else "no committed copy to restore"
        print(f"::error file={rel}::publish check failed, {what}: {msg}")
        restored.append(rel)
    print(f"validate: {checked} files checked, {len(restored)} failed" + (": " + ", ".join(restored) if restored else ""))
    return 1 if restored else 0


if __name__ == "__main__":
    sys.exit(main())
