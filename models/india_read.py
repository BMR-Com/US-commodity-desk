"""Shared India read for US cotton: one paragraph used by the export-sales brief, the cotton outlook brief and the Summary tab.
Reads data/india/india.json (models/india_cotton.py), data/derived/balance_sheets.json and data/contracts/CT.csv (spreads)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MON = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def _j(p):
    try:
        return json.loads((ROOT / p).read_text())
    except Exception:
        return None


def spreads():
    """Old-crop spreads (Mar/May, May/Jul) and old/new (Jul/Dec) for the current season, from the last settlement."""
    try:
        import pandas as pd
        d = pd.read_csv(ROOT / "data" / "contracts" / "CT.csv", parse_dates=["date"])
        last = d.date.max(); x = d[d.date == last].set_index("contract").close
        y = last.year + (1 if last.month >= 10 else 0)          # old-crop year for Mar/May/Jul
        g = lambda m, yy: x.get(f"CT{m}{yy}")
        out = {"date": last.strftime("%Y-%m-%d"), "H": g("H", y), "K": g("K", y), "N": g("N", y), "Z_new": g("Z", y), "y": y}
        if None not in (out["H"], out["K"], out["N"], out["Z_new"]):
            out.update({"hk": round(out["H"] - out["K"], 2), "kn": round(out["K"] - out["N"], 2), "nz": round(out["N"] - out["Z_new"], 2)})
        return out
    except Exception:
        return {}


def india_for_us():
    """Returns (text, score) or (None, 0). Score +1: India adds to US export demand."""
    I = _j("data/india/india.json")
    B = (_j("data/derived/balance_sheets.json") or {}).get("markets", {}).get("cotton", {})
    if not I or not I.get("origins", {}).get("split"):
        return None, 0
    P, O, DB = I["projection"], I["origins"], I.get("desk_balance", {})
    S = (DB.get("import_scenarios") or {}).get("scenarios", {})
    fo, uc = B.get("foreign") or {}, O.get("us_commit") or {}
    sm = B.get("summary", {})
    t = (f"India's crop looks like {P['m480']:.1f} m bales on the desk model (USDA {P['usda_m480']:.1f}) after the driest June–September in its main cotton districts since at least 1991. "
         f"With the import duty waived to {fo.get('waiver_to', 'December')} India imports about {S.get('expected', {}).get('m480', 0):.1f} m bales "
         f"({S.get('all_year', {}).get('m480', 0):.1f} m if the waiver runs all season) vs USDA's {(I['desk_balance'].get('cases', {}).get('usda', {}) or {}).get('usda_imports', 0):.1f} m. ")
    if uc:
        t += (f"US cotton to India: {O['split']['expected']['USA']:.1f}–{O['split']['all_year']['USA']:.1f} m bales against {uc['commit_m']:.2f} m committed, so {uc['to_book']['expected']:.1f}–{uc['to_book']['all_year']:.1f} m of new US sales are still to come. ")
    if fo:
        t += (f"Counting the Brazilian, African and Australian cotton India takes from other buyers, US exports gain about {fo['base']:.1f} m bales in the desk base and {fo['bear']:.1f} m in the bearish (big-crop, lower-price) case")
        if sm:
            t += (f"; base exports {sm['base']['exports']:.1f} m and bearish {sm['bear']['exports']:.1f} m vs USDA {B['rows'][[r['label'] for r in B['rows']].index('Exports')]['usda'][B['cur']]:.1f}, "
                  f"and every case runs into the {B.get('floor', 0):.2f} m stock floor ({B.get('floor_my')}), so price has to ration exports. ")
        else:
            t += ". "
    sp = spreads()
    if sp.get("hk") is not None:
        t += (f"At today's prices more sales are likely, which pressures old-crop spreads: Mar/May {sp['hk']:+.2f}, May/Jul {sp['kn']:+.2f} (carry that should narrow toward inversion as US stocks tighten) "
              f"and Jul/Dec {sp['nz']:+.2f} (old crop already over new; in 2021/22, the last season of tight US stocks and strong demand, it widened to +16–23¢).")
    return t.strip(), 1
