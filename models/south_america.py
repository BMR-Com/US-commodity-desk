"""Brazil & Argentina desk data: CONAB estimates and revision path, USDA PSD balances (BR, AR, China), Brazil monthly
exports vs prior years, Argentina campaign progress. Writes data/grains/derived/south_america.json.
"""
import json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SA = ROOT / "data" / "south_america"
OUT = ROOT / "data" / "grains" / "derived"


def rd(p):
    try:
        return pd.read_csv(SA / p)
    except Exception:
        return None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) or math.isinf(o) else round(float(o), 3)
    if isinstance(o, np.integer):
        return int(o)
    return o


def conab():
    s, h = rd("conab_surveys.csv"), rd("conab_history.csv")
    out = {}
    if s is not None and len(s):
        s["ano_agricola"] = s.ano_agricola.astype(str).str.strip()
        for p in ("soybeans", "corn", "corn_1st", "corn_2nd", "wheat"):
            x = s[s["product"] == p]
            seasons = sorted(x.ano_agricola.unique())
            if not seasons:
                continue
            cur, prev = seasons[-1], seasons[-2] if len(seasons) > 1 else None
            c = x[x.ano_agricola == cur].sort_values("survey")
            pv = x[x.ano_agricola == prev].sort_values("survey") if prev else x.iloc[0:0]
            if c.empty and pv.empty:
                continue
            last = c.iloc[-1] if len(c) else None
            fin = h[(h["product"] == p) & (h.ano_agricola.astype(str).str.strip() == prev)] if h is not None and prev else None
            prev_final = float(fin.producao_mil_t.iloc[0]) if fin is not None and len(fin) else (float(pv.producao_mil_t.iloc[-1]) if len(pv) else None)
            out[p] = {"season": cur, "survey": int(last.survey) if last is not None else None,
                      "production_kt": float(last.producao_mil_t) if last is not None else None, "area_kha": float(last.area_plantada_mil_ha) if last is not None else None,
                      "change_kt": float(c.producao_mil_t.iloc[-1] - c.producao_mil_t.iloc[-2]) if len(c) > 1 else None,
                      "prev_season": prev, "prev_final_kt": prev_final,
                      "path_cur": [[int(a), float(b)] for a, b in zip(c.survey, c.producao_mil_t)],
                      "path_prev": [[int(a), float(b)] for a, b in zip(pv.survey, pv.producao_mil_t)]}
        # first-to-final revision stats for soybeans and corn
        for p in ("soybeans", "corn"):
            x = s[s["product"] == p]
            rev = []
            for se, g in x.groupby("ano_agricola"):
                g = g.sort_values("survey")
                if se != sorted(x.ano_agricola.unique())[-1] and len(g) >= 10:
                    rev.append([se, float(g.producao_mil_t.iloc[0]), float(g.producao_mil_t.iloc[-1])])
            if p in out:
                out[p]["first_vs_final"] = rev
    if h is not None and len(h):
        hist = {}
        for p in ("soybeans", "corn", "wheat"):
            x = h[h["product"] == p].sort_values("ano_agricola").tail(15)
            hist[p] = {"season": x.ano_agricola.astype(str).str.strip().tolist(), "production_kt": x.producao_mil_t.round(0).tolist(),
                       "area_kha": x.area_plantada_mil_ha.round(0).tolist(), "yield": x.yield_t_ha.tolist()}
        out["history"] = hist
    st = rd("conab_states_latest.csv")
    if st is not None and len(st):
        top = st[st["product"] == "soybeans"].sort_values("producao_mil_t", ascending=False).head(10)
        out["soy_states"] = top[["uf", "area_plantada_mil_ha", "producao_mil_t"]].to_dict("records")
    return out


def psd():
    d = rd("psd.csv")
    if d is None or d.empty:
        return {}
    out = {}
    for (com, ctry), g in d.groupby(["commodity", "country"]):
        mys = sorted(g.my.unique())[-3:]
        tab = {}
        for my in mys:
            x = g[g.my == my]
            tab[str(my)] = {a: float(v) for a, v in zip(x.attr, x.value)}
        out.setdefault(com, {})[ctry] = tab
    return out


def exports():
    d = rd("brazil_exports.csv")
    if d is None or d.empty:
        return {}
    out = {}
    now = pd.Timestamp.now()
    for com, g in d.groupby("commodity"):
        piv = g.pivot_table(index="month", columns="year", values="kt", aggfunc="sum").reindex(range(1, 13))
        yrs = sorted(piv.columns)
        cy = yrs[-1]
        last_m = int(g[g.year == cy].month.max())
        ytd = float(piv[cy].iloc[:last_m].sum())
        ly = float(piv[cy - 1].iloc[:last_m].sum()) if cy - 1 in piv else None
        avg5 = float(np.mean([piv[y].iloc[:last_m].sum() for y in yrs[-6:-1]])) if len(yrs) > 5 else None
        out[com] = {"years": [int(y) for y in yrs[-6:]], "monthly": {str(y): [None if pd.isna(v) else float(v) for v in piv[y]] for y in yrs[-6:]},
                    "last_month": last_m, "ytd_kt": ytd, "ytd_ly_kt": ly, "ytd_avg5_kt": avg5,
                    "ytd_yoy_pct": (ytd / ly - 1) * 100 if ly else None, "last_month_kt": float(piv[cy].iloc[last_m - 1]),
                    "last_month_ly_kt": float(piv[cy - 1].iloc[last_m - 1]) if cy - 1 in piv else None}
    return out


def argentina():
    d = rd("argentina_estimates.csv")
    if d is None or d.empty:
        return {}
    out = {}
    d["camp"] = d.campania.astype(str)
    for crop, g in d.groupby("cultivo"):
        g = g.sort_values("camp")
        last = g.iloc[-1]
        prev = g.iloc[-2] if len(g) > 1 else None
        out[crop] = {"campaign": last.camp, "sown_ha": float(last.superficie_sembrada_ha), "harvested_ha": float(last.superficie_cosechada_ha),
                     "production_t": float(last.produccion_tm), "harvest_pct": float(100 * last.superficie_cosechada_ha / last.superficie_sembrada_ha) if last.superficie_sembrada_ha else None,
                     "prev_campaign": prev.camp if prev is not None else None, "prev_production_t": float(prev.produccion_tm) if prev is not None else None,
                     "history": {"campaign": g.camp.tail(12).tolist(), "production_t": g.produccion_tm.tail(12).tolist(), "sown_ha": g.superficie_sembrada_ha.tail(12).tolist()}}
    return out


def progress():
    p = SA / "raw" / "conab_progress_latest.json"
    return json.loads(p.read_text()) if p.exists() else None


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "conab": conab(), "psd": psd(), "exports": exports(),
           "argentina": argentina(), "progress_bulletin": progress()}
    (OUT / "south_america.json").write_text(json.dumps(clean(res), separators=(",", ":")))
    print({k: (list(v.keys()) if isinstance(v, dict) else v) for k, v in res.items()})
