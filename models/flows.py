"""Futures, options and COT flows for the desk's contracts.

Inputs: data/cot/<sym>_fo.csv (CFTC disaggregated F+O), data/cme/<date>/*.csv (nightly CME),
data/prices/<sym>.csv. Output: data/<group>/derived/flows.json per commodity group.
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {"dairy": ["DC", "GDK", "CSC", "CB", "GNF", "DY"], "livestock": ["HE", "LE", "GF"],
          "grains": ["ZC", "ZS", "ZM", "ZL", "ZW", "KE"]}


def num(s):
    """Numbers from CME strings, incl. CBOT eighths ("1052'4" = 1052.5) and trailing A/B (ask/bid) flags."""
    x = s.astype(str).str.replace(",", "").str.replace(r"[AB]$", "", regex=True).str.strip()
    frac = x.str.extract(r"^(-?\d+)'(\d)$")
    out = pd.to_numeric(x, errors="coerce")
    m = frac[0].notna()
    out[m] = frac[0][m].astype(float) + frac[1][m].astype(float) / 8 * (frac[0][m].astype(float).apply(lambda v: -1 if v < 0 else 1))
    return out


def cot(sym):
    p = ROOT / "data" / "cot" / f"{sym}_fo.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, low_memory=False).copy()
    d["date"] = pd.to_datetime(d.report_date_as_yyyy_mm_dd).dt.date
    c = lambda n: pd.to_numeric(d[n], errors="coerce")
    out = pd.DataFrame({
        "date": d.date.astype(str), "oi": c("open_interest_all"),
        "mm_long": c("m_money_positions_long_all"), "mm_short": c("m_money_positions_short_all"),
        "mm_spread": c("m_money_positions_spread"),
        "pm_long": c("prod_merc_positions_long"), "pm_short": c("prod_merc_positions_short"),
        "sw_long": c("swap_positions_long_all"), "sw_short": c("swap__positions_short_all"),
        "or_long": c("other_rept_positions_long"), "or_short": c("other_rept_positions_short"),
        "nr_long": c("nonrept_positions_long_all"), "nr_short": c("nonrept_positions_short_all"),
        "mm_traders_long": c("traders_m_money_long_all"), "mm_traders_short": c("traders_m_money_short_all"),
    }).sort_values("date").drop_duplicates("date", keep="last")
    out["mm_net"] = out.mm_long - out.mm_short
    out["pm_net"] = out.pm_long - out.pm_short
    out["sw_net"] = out.sw_long - out.sw_short
    out["mm_net_pct_oi"] = (100 * out.mm_net / out.oi).round(1)
    last = out.iloc[-1]
    hist = out.mm_net.dropna()
    summ = {
        "date": last.date, "oi": int(last.oi), "mm_net": int(last.mm_net),
        "mm_net_wow": int(last.mm_net - out.mm_net.iloc[-2]),
        "mm_net_pct_oi": float(last.mm_net_pct_oi),
        "mm_net_percentile_all": float(round(100 * (hist < last.mm_net).mean(), 0)),
        "mm_net_percentile_3y": float(round(100 * (hist.iloc[-156:] < last.mm_net).mean(), 0)),
        "mm_long": int(last.mm_long), "mm_short": int(last.mm_short),
        "pm_net": int(last.pm_net), "sw_net": int(last.sw_net),
    }
    keep = ["date", "oi", "mm_net", "mm_long", "mm_short", "pm_net", "sw_net", "mm_net_pct_oi"]
    ser = out[keep].tail(520)
    return summ, {k: [None if pd.isna(v) else (v if isinstance(v, str) else float(v)) for v in ser[k]] for k in keep}


def cme_days():
    return sorted(p.name for p in (ROOT / "data" / "cme").glob("2*") if (p / "fut_settlements.csv").exists())


def curves(syms):
    days = cme_days()
    if not days:
        return {}
    pick = [days[-1]] + ([days[-6]] if len(days) >= 6 else days[:1] if len(days) > 1 else [])
    res = {}
    for day in dict.fromkeys(pick):
        s = pd.read_csv(ROOT / "data" / "cme" / day / "fut_settlements.csv")
        s = s[s.sym.isin(syms)].copy()
        s["settle"] = num(s.settle)
        s["oi"] = num(s.oi)
        for sym, g in s.groupby("sym"):
            res.setdefault(sym, {})[day] = {"month": g.month.tolist(), "settle": g.settle.tolist(),
                                            "oi": g.oi.fillna(0).astype(int).tolist()}
    return res


def oi_changes(syms):
    """Futures OI by month for the latest day with day-over-day change; total OI history."""
    days = cme_days()
    res = {}
    for sym in syms:
        tot = []
        for day in days:
            f = pd.read_csv(ROOT / "data" / "cme" / day / "fut_volume_oi.csv")
            f = f[f.sym == sym]
            if len(f):
                tot.append([day, int(num(f.oi).sum()), int(num(f.total_vol).sum())])
        if days:
            f = pd.read_csv(ROOT / "data" / "cme" / days[-1] / "fut_volume_oi.csv")
            f = f[f.sym == sym]
            res[sym] = {"date": days[-1], "month": f.month.tolist(), "oi": num(f.oi).fillna(0).astype(int).tolist(),
                        "oi_change": num(f.oi_change).fillna(0).astype(int).tolist(),
                        "volume": num(f.total_vol).fillna(0).astype(int).tolist(), "total_history": tot}
    return res


def option_strikes(syms, months=3):
    """Options OI by strike, calls vs puts, for the nearest listed months (latest CME day)."""
    days = cme_days()
    if not days:
        return {}
    o = pd.read_csv(ROOT / "data" / "cme" / days[-1] / "opt_volume_oi.csv")
    res = {}
    for sym in syms:
        g = o[o.sym == sym].copy()
        if g.empty:
            continue
        for c in ("strike", "oi", "oi_change", "total_vol"):
            g[c] = num(g[c])
        g["mdate"] = pd.to_datetime(g.month, format="%b %Y", errors="coerce")
        mlist = sorted(g.mdate.dropna().unique())[:months]
        res[sym] = {"date": days[-1], "months": {}}
        for m in mlist:
            x = g[g.mdate == m]
            piv = x.pivot_table(index="strike", columns="cp", values=["oi", "oi_change", "total_vol"], aggfunc="sum").fillna(0)
            piv = piv[(piv["oi"].sum(axis=1) > 0) | (piv["total_vol"].sum(axis=1) > 0)]
            get = lambda f, cp: piv[(f, cp)].astype(int).tolist() if (f, cp) in piv.columns else [0] * len(piv)
            calls, puts = sum(get("oi", "C")), sum(get("oi", "P"))
            res[sym]["months"][pd.Timestamp(m).strftime("%b %Y")] = {
                "strike": [float(s) for s in piv.index], "call_oi": get("oi", "C"), "put_oi": get("oi", "P"),
                "call_chg": get("oi_change", "C"), "put_chg": get("oi_change", "P"),
                "call_vol": get("total_vol", "C"), "put_vol": get("total_vol", "P"),
                "put_call_oi": round(puts / calls, 2) if calls else None}
    return res


def prices(sym, n=1500):
    p = ROOT / "data" / "prices" / f"{sym}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p).tail(n)
    clean = lambda s: [None if pd.isna(v) else round(float(v), 4) for v in s]
    return {"date": d.date.tolist(), "c1": clean(d.c1_close),
            "c2": clean(d.c2_close) if "c2_close" in d else None}


def relative_value():
    """Grain spreads/ratios from continuous front-month closes."""
    px = {}
    for s in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE"):
        p = ROOT / "data" / "prices" / f"{s}.csv"
        if p.exists():
            d = pd.read_csv(p, parse_dates=["date"]).set_index("date").c1_close
            px[s] = d[~d.index.duplicated()]
    if not {"ZC", "ZS"} <= set(px):
        return None
    d = pd.DataFrame(px).dropna(how="all").ffill().tail(2600)
    out = {"date": [str(x.date()) for x in d.index]}
    def put(k, sr):
        out[k] = [None if pd.isna(v) else round(float(v), 4) for v in sr]
    put("soy_corn_ratio", d.ZS / d.ZC)
    if "ZW" in d:
        put("wheat_minus_corn", d.ZW - d.ZC)
    if "KE" in d and "ZW" in d:
        put("kc_minus_chicago", d.KE - d.ZW)
    if {"ZM", "ZL"} <= set(d):
        put("board_crush", d.ZM * 0.022 + d.ZL * 0.11 - d.ZS / 100)
        put("oil_share", 100 * (d.ZL * 0.11) / (d.ZL * 0.11 + d.ZM * 0.022))
    return out


def seasonality(sym, years=15):
    p = ROOT / "data" / "prices" / f"{sym}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date").c1_close.dropna()
    d = d[~d.index.duplicated()]
    m = d.resample("ME").mean()
    m = m[m.index.year >= m.index.year.max() - years]
    dev = m.groupby(m.index.year).transform(lambda x: 100 * (x / x.mean() - 1))
    prof = dev.groupby(dev.index.month).agg(["mean", lambda x: x.quantile(.25), lambda x: x.quantile(.75)])
    prof.columns = ["mean", "q25", "q75"]
    cy = m[m.index.year == m.index.year.max()]
    ly = m[m.index.year == m.index.year.max() - 1]
    base = ly.mean() if len(ly) else cy.mean()
    return {"month": [int(i) for i in prof.index], "mean": prof["mean"].round(2).tolist(), "q25": prof.q25.round(2).tolist(),
            "q75": prof.q75.round(2).tolist(), "current_year": int(m.index.year.max()),
            "current": [round(float(100 * (v / base - 1)), 2) for v in cy], "years": years}


def clean(o):
    """Replace NaN/inf with None recursively so the output is strict JSON."""
    import math
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    return o


if __name__ == "__main__":
    for group, syms in GROUPS.items():
        out = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "cot": {}, "prices": {}}
        for s in syms:
            r = cot(s)
            if r:
                out["cot"][s] = {"summary": r[0], "series": r[1]}
            out["prices"][s] = prices(s)
        out["curves"] = curves(syms)
        out["oi"] = oi_changes(syms)
        out["options"] = option_strikes(syms)
        if group == "grains":
            out["rv"] = relative_value()
            out["seasonality"] = {s: seasonality(s) for s in syms}
        d = ROOT / "data" / group / "derived"
        d.mkdir(parents=True, exist_ok=True)
        (d / "flows.json").write_text(json.dumps(clean(json.loads(json.dumps(out, default=str))), separators=(",", ":"), allow_nan=False))
        print(group, {s: v["summary"] for s, v in out["cot"].items()})
