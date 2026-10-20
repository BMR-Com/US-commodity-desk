"""Grains backtests summary -> data/grains/derived/tests.json (per commodity HTML-ready rows).

1. WASDE revision momentum: after USDA revises an item for a marketing year, how often is the
   next revision of that item (same year) in the same direction? Uses every monthly WASDE.
2. Condition yield model test (from condition.json) and export pace test (from exports.json)
   when available.
3. Price reaction to WASDE: front-month continuous futures return on WASDE day vs the direction
   of the ending-stocks revision (when price data available).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "grains" / "derived"
ITEMS = {"corn": ["yield", "production", "exports", "feed_residual", "ethanol", "end_stocks"],
         "soybeans": ["yield", "production", "exports", "crush", "end_stocks"],
         "wheat": ["production", "exports", "feed_residual", "end_stocks"],
         "meal": ["production", "exports", "domestic", "end_stocks"], "oil": ["production", "biofuel", "exports", "end_stocks"]}
SYM = {"corn": "ZC", "soybeans": "ZS", "wheat": "ZW", "meal": "ZM", "oil": "ZL"}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December"], 1)}


def momentum(com, wasde):
    out = {}
    us = wasde["commodities"][com]["us"]
    # need full histories: rebuild from the tidy WASDE source
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grains_wasde import tidy, load, FILES
    d = tidy(load(FILES[com]))
    d = d[d.region == "United States"]
    for item in ITEMS[com]:
        x = d[d.attr == item].sort_values("wasde")
        pairs = []
        for my, g in x.groupby("my"):
            r = g.value.diff().dropna()
            r = r[r != 0]
            s = np.sign(r.values)
            pairs += list(zip(s[:-1], s[1:]))
        if len(pairs) < 15:
            continue
        same = np.mean([a == b for a, b in pairs])
        out[item] = {"n": len(pairs), "same_direction": round(float(same), 2)}
    return out


def wasde_price_reaction(com):
    p = ROOT / "data" / "prices" / f"{SYM[com]}.csv"
    if not p.exists():
        return None
    px = pd.read_csv(p, parse_dates=["date"]).set_index("date").c1_close.dropna()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from grains_wasde import tidy, load, FILES
    d = tidy(load(FILES[com]))
    d = d[(d.region == "United States") & (d.attr == "end_stocks")]
    rows = []
    for (wn, rep), g in d.groupby(["wasde", "report"]):
        try:
            mon, yr = rep.split()
            mi = MONTHS[mon]
        except Exception:
            continue
        # WASDE is released around the 9th-12th; find the day with the largest abs return in that window as a proxy is biased,
        # so use the 12th-or-next trading day close vs the prior close.
        day = pd.Timestamp(int(yr), mi, 1)
        win = px[day + pd.Timedelta(days=7): day + pd.Timedelta(days=13)]
        if len(win) < 2:
            continue
        # revision to the newest marketing year reported in this WASDE
        my = sorted(g.my)[-1]
        prev = d[(d.my == my) & (d.wasde < wn)].sort_values("wasde")
        if prev.empty:
            continue
        rev = g[g.my == my].value.iloc[0] - prev.value.iloc[-1]
        if rev == 0:
            continue
        rows.append(dict(report=rep, my=my, rev_pct=100 * rev / prev.value.iloc[-1], ret_window=100 * (win.iloc[-1] / win.iloc[0] - 1)))
    r = pd.DataFrame(rows)
    if len(r) < 20:
        return None
    hit = (np.sign(-r.rev_pct) == np.sign(r.ret_window)).mean()
    return {"n": int(len(r)), "corr": round(float(np.corrcoef(r.rev_pct, r.ret_window)[0, 1]), 3), "hit": round(float(hit), 2),
            "note": "approximate: window return over WASDE week (exact release dates not used)"}


def bias(com):
    p = ROOT / "data" / "derived" / "convergence_bias.json"
    if not p.exists():
        return None
    b = json.loads(p.read_text()).get(SYM.get(com, ""), {})
    return b if b.get("n_contracts") else None


def html(com, mom, cond, exp, react):
    parts = []
    b = bias(com)
    if b:
        cells = "".join(f"<td>{b[h]['mean_pct']:+.2f}% · {100 * b[h]['up_share']:.0f}% up · t {b[h]['t']:+.1f}</td>" for h in ("h20", "h60", "h120") if h in b)
        parts.append(f"<h3>Convergence: futures vs their own final price</h3><div class='tbl'><table><tr><th>Expired contracts since 2010</th><th>From 20 bdays</th><th>From 60</th><th>From 120</th></tr><tr><td>{b['n_contracts']} contracts</td>{cells}</tr></table></div><p class='note'>Positive = futures finished above where they traded. t-stats overstate significance (neighbouring contracts share shocks).</p>")
    if mom:
        parts.append("<h3>WASDE revision momentum</h3><div class='tbl'><table><tr><th>Item</th><th>Next revision same direction</th><th>n</th></tr>" +
                     "".join(f"<tr><td>{k.replace('_', ' ')}</td><td>{100 * v['same_direction']:.0f}%</td><td>{v['n']}</td></tr>" for k, v in mom.items()) +
                     "</table></div><p class='note'>After USDA revises an item for a marketing year, how often its next revision of that item goes the same way. Well above 50% means revisions trend: USDA moves toward the final number in steps.</p>")
    if cond:
        m = cond.get("model")
        if m:
            t = m['test']
            usda = f" On the {t['n_usda']} years where USDA had a yield forecast out by that date: model {t['mae_model_same_years']} vs USDA {t['mae_usda_same_date']} bu/ac." if t.get('mae_usda_same_date') is not None else ""
            parts.append(f"<h3>Condition yield model</h3><p>Leave-one-year-out over {t['n']} years, condition at week {m['week']}: mean abs error {t['mae_model']} bu/ac vs {t['mae_trend']} for trend alone; direction vs trend right {100 * t['hit_direction']:.0f}% of years.{usda}</p>")
    if exp and exp.get("test"):
        t = exp["test"]
        parts.append(f"<h3>Export pace</h3><p>Pace-implied exports at this point of the season: mean abs error {t['mae_pct']}% of final vs {t['mae_usda_pct']}% for USDA's same-month forecast; called the direction of USDA's next export revision {100 * t['revision_hit']:.0f}% of the time (n={t['n']}).</p>")
    if react:
        parts.append(f"<h3>Price reaction to WASDE</h3><p>Ending-stocks revision vs front-month move over WASDE week: correlation {react['corr']}, price moved opposite to the stocks revision {100 * react['hit']:.0f}% of the time (n={react['n']}; {react['note']}).</p>")
    return "".join(parts) or "<p class='note'>No tests yet.</p>"


if __name__ == "__main__":
    wasde = json.loads((D / "wasde.json").read_text())
    cond = json.loads((D / "condition.json").read_text()) if (D / "condition.json").exists() else {}
    exp = json.loads((D / "exports.json").read_text()) if (D / "exports.json").exists() else {}
    out = {}
    for com in ITEMS:
        mom = momentum(com, wasde)
        react = wasde_price_reaction(com)
        out[com] = {"momentum": mom, "price_reaction": react, "html": html(com, mom, cond.get(com), exp.get(com), react)}
        print(com, mom, react)
    out["kc"] = out["wheat"]
    (D / "tests.json").write_text(json.dumps(out, indent=1))
