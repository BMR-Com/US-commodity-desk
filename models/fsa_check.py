#!/usr/bin/env python3
"""Build checks for the FSA acreage outputs (run between the build and the publish step of .github/workflows/fsa.yml).

Checks .cache/fsa_build/cotton.json and grains.json:
  - strict JSON (no NaN / Infinity), release dates not in the future;
  - every state: planted > 0, 0 <= abandonment <= 0.95; US FSA-based planted within 25% of USDA's same-month planted;
  - cotton reproduces cotton-crop-progress (CCP_DIR checkout) when both run on the same FSA rows for the release:
      Texas conditional block of docs/data/crop_projection.json (abandonment, harvested and planted acres, yield,
      production with ranges), drought+ratings abandonment, the FSA failed-share note, and per-state FSA planted /
      failed share / harvested share / final abandonment of docs/data/crop.json (relative tolerance 1e-4).
    If this desk's FSA rows for the release differ from cotton-crop-progress's (this desk reads every county_data
    sheet), that is recorded as a note and the reproduction check is skipped, not failed.
A crop with no FSA history yet ("error" in grains.json) is listed as pending, not failed.
Writes data/fsa/check.json (committed either way). Exit 1 if anything failed, so the publish step does not run.
"""
import json, math, os, sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".cache" / "fsa_build"
CCP = Path(os.environ.get("CCP_DIR") or ROOT / ".cache" / "ccp")
LATEST_OK = (date.today() + timedelta(days=1)).isoformat()


def strict(p):
    def bad(c):
        raise ValueError(f"non-finite number {c}")
    return json.loads(p.read_text(), parse_constant=bad)


def close(a, b, tol=1e-4):
    if isinstance(a, dict) and isinstance(b, dict):
        return all(close(a.get(k), v, tol) for k, v in b.items())
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol * max(1.0, abs(b))
    return a == b


def check_states(rows, fails, tag):
    for r in rows:
        if not (r.get("planted") or 0) > 0:
            fails.append(f"{tag} {r.get('st')}: planted not positive")
        ab = r.get("abandonment")
        if ab is None or not (0 <= ab <= 0.95):
            fails.append(f"{tag} {r.get('st')}: abandonment {ab} outside 0-0.95")


def same_fsa_rows(rel, cy):
    a = pd.read_csv(ROOT / "data" / "fsa" / "fsa_cotton_state.csv")
    p = CCP / "data" / "fsa" / "fsa_cotton_state.csv"
    if not p.exists():
        return None
    b = pd.read_csv(p)
    k = ["state", "type", "irr"]
    a = a[(a.crop_year == cy) & (a.release == rel)].set_index(k)[["planted", "failed"]].sort_index()
    b = b[(b.crop_year == cy) & (b.release == rel)].set_index(k)[["planted", "failed"]].sort_index()
    if not len(b):
        return None
    return a.index.equals(b.index) and ((a - b).abs() <= 0.01).all().all()


def cotton(fails, notes):
    p = BUILD / "cotton.json"
    if not p.exists():
        fails.append("cotton.json not built")
        return
    c = strict(p)
    if c["fsa_release"] > LATEST_OK:
        fails.append(f"cotton release {c['fsa_release']} in the future")
    check_states(c["states"], fails, "cotton")
    us = c["us"]
    if us.get("usda_planted") and not (0.75 <= us["planted"] / us["usda_planted"] <= 1.25):
        fails.append(f"cotton US planted {us['planted']:.0f} vs USDA {us['usda_planted']:.0f}")
    same = same_fsa_rows(c["fsa_release"], c["crop_year"])
    if same is None:
        notes.append(f"cotton: cotton-crop-progress has no FSA rows for {c['fsa_release']}; reproduction not checked")
        return
    if not same:
        notes.append(f"cotton: FSA rows for {c['fsa_release']} differ from cotton-crop-progress (all county_data sheets read here); reproduction not checked")
        return
    proj = CCP / "docs" / "data" / "crop_projection.json"
    if proj.exists():
        b = json.loads(proj.read_text())
        tx = c["texas"]
        if tx.get("asof_monday") and b.get("asof") and abs((pd.Timestamp(b["asof"]) - pd.Timestamp(tx["asof_monday"])).days) > 7:
            notes.append(f"cotton: crop_projection.json is from {b['asof']}, this build's as-of Monday {tx['asof_monday']}; Texas not compared")
        else:
            for k in ("tx_abandonment", "tx_harvested_acres", "tx_planted_acres", "tx_yield", "texas", "n_seasons"):
                if not close((tx.get("conditional") or {}).get(k), (b.get("conditional") or {}).get(k), 1e-6):
                    fails.append(f"cotton Texas {k}: {(tx.get('conditional') or {}).get(k)} vs crop_projection.json {(b.get('conditional') or {}).get(k)}")
            if not close(tx["abandonment_drought_ratings"], b["texas"]["abandonment"], 1e-6):
                fails.append(f"cotton Texas abandonment {tx['abandonment_drought_ratings']} vs {b['texas']['abandonment']}")
            if (tx.get("fsa_note") or {}).get("text") not in (b.get("notes") or []):
                fails.append("cotton FSA note differs from crop_projection.json")
            notes.append(f"cotton: Texas conditional block matches crop_projection.json ({b['asof']})")
    cj = CCP / "docs" / "data" / "crop.json"
    if cj.exists():
        e = json.loads(cj.read_text()).get("estimate") or {}
        if e.get("fsa_release") == c["fsa_release"]:
            st = {s["st"]: s for s in e.get("states", [])}
            n = 0
            for r in c["states"]:
                s = st.get(r["st"])
                if not s or "fsa_total" not in s:
                    continue
                for k1, k2 in (("planted", "planted"), ("fsa_total", "fsa_total"), ("fail_share", "fail_share"), ("hr_fsa", "hr_fsa"), ("abandonment", "ab_final")):
                    if k2 in s and not close(r[k1], s[k2], 1e-3 if k1 in ("fail_share", "abandonment", "hr_fsa") else 1e-4):
                        fails.append(f"cotton {r['st']} {k1}: {r[k1]} vs crop.json {s[k2]}")
                n += 1
            notes.append(f"cotton: {n} states compared with crop.json estimate")


def grains(fails, notes, pending):
    p = BUILD / "grains.json"
    if not p.exists():
        notes.append("grains.json not built")
        return
    g = strict(p)
    for crop, c in g.get("crops", {}).items():
        if c.get("error"):
            pending.append(f"{crop}: {c['error']}")
            continue
        if c["fsa_release"] > LATEST_OK:
            fails.append(f"{crop} release {c['fsa_release']} in the future")
        check_states(c["states"], fails, crop)
        u, usda = c["us"], c.get("usda") or {}
        if usda.get("planted") and not (0.75 <= u["planted_m"] / usda["planted"] <= 1.25):
            fails.append(f"{crop} US planted {u['planted_m']:.2f}m vs USDA {usda['planted']}m")


def main():
    fails, notes, pending = [], [], []
    for fn in (cotton, grains):
        try:
            fn(fails, notes, pending) if fn is grains else fn(fails, notes)
        except Exception as e:
            fails.append(f"{fn.__name__}: {e!r}"[:300])
    out = {"checked": str(date.today()), "ok": not fails, "failures": fails, "notes": notes, "pending": pending}
    (ROOT / "data" / "fsa").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "fsa" / "check.json").write_text(json.dumps(out, indent=1))
    for f in fails:
        print("::error::" + f)
    for n in notes + pending:
        print(n)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
