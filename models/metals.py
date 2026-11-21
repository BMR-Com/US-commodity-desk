"""Metals desk model: gold, silver, copper, aluminum, platinum, palladium. Reads only what the metals workflow and the shared price/COT
pipelines wrote (data/technicals, data/cot_desk, data/metals/raw, data/markets) and writes data/metals/metals.json.

Per metal: front price and curve with calendar spreads and annualised carry, the drivers that matter for that metal,
supply-and-demand reads from public sources (with each source's revisions), exchange and ETF stocks, a rule-based
factor read (+1 / 0 / -1 per factor) and a short brief. Every block carries the date of the data it used.
A part whose input is missing is left out; nothing is invented.
"""
import datetime as dt, json, math, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
RAW = D / "metals" / "raw"
OUT = D / "metals" / "metals.json"
LB_PER_T = 2204.62
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
METALS = {"gold": ("GC", "GC", "Gold", "$/oz"), "silver": ("SI", "SI", "Silver", "$/oz"),
          "copper": ("HG", "HG", "Copper", "$/lb"), "aluminum": ("ALI", "AUP", "Aluminum", "$/t"),
          "platinum": ("PL", "PL", "Platinum", "$/oz"), "palladium": ("PA", "PA", "Palladium", "$/oz")}


def J(p):
    try:
        return json.loads((D / p).read_text())
    except Exception:
        return None


def C(p, **kw):
    f = RAW / p
    return pd.read_csv(f, **kw) if f.exists() else None


def num(v):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 6)
    if isinstance(o, np.integer):
        return int(o)
    return o


def pct_rank(s, v):
    s = pd.Series(s).dropna()
    return None if v is None or len(s) < 20 else round(float((s < v).mean() * 100), 0)


def chg(s, days):
    """Change of a dated series over `days` calendar days (last value minus value on or before the cut)."""
    s = s.dropna()
    if not len(s):
        return None
    cut = s.index[-1] - pd.Timedelta(days=days)
    b = s[s.index <= cut]
    return None if not len(b) else float(s.iloc[-1] - b.iloc[-1])


def pchg(s, days):
    s = s.dropna()
    if not len(s):
        return None
    cut = s.index[-1] - pd.Timedelta(days=days)
    b = s[s.index <= cut]
    return None if not len(b) or b.iloc[-1] == 0 else float(100 * (s.iloc[-1] / b.iloc[-1] - 1))


def weekly(s, years=5):
    s = s.dropna()
    s = s[s.index >= s.index[-1] - pd.DateOffset(years=years)] if len(s) else s
    w = s.resample("W-FRI").last().dropna()
    return {"date": [d.strftime("%Y-%m-%d") for d in w.index], "v": [round(float(x), 4) for x in w.values]}


# ───────── prices from the shared technicals files ─────────
def tech(sym):
    t = J(f"technicals/{sym}.json")
    if not t:
        return None, None
    cont = next((s for s in t["series"] if s["ticker"] == "cont"), None)
    s = pd.Series({pd.Timestamp(b[0]): b[4] for b in cont["bars"] if b[4]}) if cont else pd.Series(dtype=float)
    return t, s.sort_index()


def price_block(sym):
    t, s = tech(sym)
    if not t:
        return None, None
    d = next((x for x in t["series"] if x["ticker"] == t["default"]), t["series"][0])
    a = d["analysis"]
    r = a.get("returns") or {}
    out = {"sym": sym, "contract": d.get("label"), "ticker": d["ticker"], "last": a["last"], "date": d["bars"][-1][0], "unit": t["unit"], "dp": t["dp"],
           "chg_1w": r.get("1w"), "chg_1m": r.get("1m"), "chg_3m": r.get("3m"), "chg_ytd": r.get("ytd"), "hi52": a.get("hi52"), "lo52": a.get("lo52"),
           "trend": a.get("trend"), "rsi": a.get("rsi")}
    curve = []
    for x in t["series"]:
        if x["ticker"] == "cont" or x.get("kind") == "spread" or not x.get("bars"):
            continue
        b = x["bars"][-1]
        curve.append({"ticker": x["ticker"], "label": x.get("label"), "last": b[4], "date": b[0]})
    m = {c: i for i, c in enumerate("FGHJKMNQUVXZ")}
    curve.sort(key=lambda c: (int(c["ticker"][-4:]), m[c["ticker"][-5]]))
    out["curve"] = curve
    return out, s


def ann_carry(curve, rate):
    """Calendar spreads between consecutive listed contracts, with the annualised carry they pay (later over earlier).
    For precious metals the gap to the T-bill rate is the market's implied lease rate."""
    m = {c: i for i, c in enumerate("FGHJKMNQUVXZ")}
    out = []
    for a, b in zip(curve, curve[1:]):
        if not a["last"] or not b["last"] or a["date"] != b["date"]:
            continue
        da = dt.date(int(a["ticker"][-4:]), m[a["ticker"][-5]] + 1, 1)
        db = dt.date(int(b["ticker"][-4:]), m[b["ticker"][-5]] + 1, 1)
        days = (db - da).days
        if days <= 0:
            continue
        ann = 100 * (b["last"] / a["last"] - 1) * 365 / days
        out.append({"pair": f"{a['label']} / {b['label']}", "spread": round(b["last"] - a["last"], 4), "ann_pct": round(ann, 2), "days": days,
                    "lease_pct": round(rate - ann, 2) if rate is not None else None})
    return out


def tbill():
    m = J("markets/markets.json") or {}
    x = next((i for i in m.get("items", []) if i["sym"] == "^IRX"), None)
    return x and x.get("last")


# ───────── COT read (from the shared COT desk) ─────────
def cot(sym):
    c = J(f"cot_desk/{sym}.json")
    if not c:
        return None
    mm = c["cats"]["mm"]
    return {"sym": sym, "date": c["date"], "net": mm["N"], "chg": mm["dN"], "pct3": mm["pct"].get("y3"), "pct_oi": mm.get("np_oi"), "driver": c.get("driver"),
            "sw_net": c["cats"]["sw"]["N"], "pm_net": c["cats"]["pm"]["N"]}


def fac(name, s, txt):
    return {"name": name, "s": int(s), "txt": txt}


def view(fs):
    if not fs:
        return None, "no read"
    sc = sum(f["s"] for f in fs) / len(fs)
    return round(sc, 2), ("bullish" if sc >= 0.34 else "mildly bullish" if sc >= 0.15 else "bearish" if sc <= -0.34 else "mildly bearish" if sc <= -0.15 else "neutral")


def ordn(v):
    if v is None:
        return "–"
    n = int(round(v))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def sg(v, d=1, suf=""):
    return "–" if v is None else f"{'+' if v > 0 else ''}{v:,.{d}f}{suf}"


# ───────── gold ─────────
def wgc_block():
    """World Gold Council Gold Demand Trends headline tonnages by quarter (pipelines/metals.py wgc). Year-on-year changes
    are WGC's own; the desk keeps each quarter's first published summary, so later revisions are not captured."""
    p = RAW / "wgc_gdt.json"
    if not p.exists():
        return None
    q = json.loads(p.read_text())
    keys = sorted(q)
    cur = q[keys[-1]]
    nice = {"total": "Total demand", "jewellery": "Jewellery", "technology": "Technology", "bar_coin": "Bar and coin", "etfs": "Gold ETFs (net flow)",
            "central_banks": "Central banks", "mine": "Mine production", "recycling": "Recycling", "supply": "Total supply"}
    table = [{"key": k, "line": nice.get(k, k), "now": v["t"], "yoy_pct": v.get("yoy_pct"), "hist": [((q[x].get("values") or {}).get(k) or {}).get("t") for x in keys]}
             for k, v in cur["values"].items()]
    order = list(nice)
    table.sort(key=lambda r: order.index(r["key"]) if r["key"] in order else 99)
    return {"quarter": cur["quarter"], "published": cur.get("published"), "summary": cur.get("summary"), "url": cur.get("url"), "quarters": keys, "table": table,
            "source": "World Gold Council, Gold Demand Trends (public report summary)"}


def etf_gold():
    g = C("etf_gld.csv", parse_dates=["date"])
    i = C("etf_ishares.csv", parse_dates=["date"])
    if g is None:
        return None
    gs = g.set_index("date").tonnes.astype(float).sort_index()
    try:                                                          # continued daily by the derived series (State Street shares x gold per share)
        fsr = fund_series("GLD", "gold")
        if fsr and fsr[1].get("derived"):
            gs = (fsr[0] / OZ_PER_T).sort_index()
            gs = gs[~gs.index.duplicated(keep="last")]
    except Exception:
        import traceback; traceback.print_exc()
    out = {"gld": {"asof": gs.index[-1].strftime("%Y-%m-%d"), "tonnes": float(gs.iloc[-1]), "chg_1w": chg(gs, 7), "chg_1m": chg(gs, 30), "chg_3m": chg(gs, 91),
                   "chg_ytd": float(gs.iloc[-1] - gs[gs.index < pd.Timestamp(gs.index[-1].year, 1, 1)].iloc[-1]) if (gs.index < pd.Timestamp(gs.index[-1].year, 1, 1)).any() else None,
                   "pct5y": pct_rank(gs[gs.index >= gs.index[-1] - pd.DateOffset(years=5)], float(gs.iloc[-1])), "weekly": weekly(gs, 5)}}
    if i is not None:
        iau = i[i.fund == "IAU"].set_index("date").tonnes.astype(float).sort_index()
        if len(iau):
            out["iau"] = {"asof": iau.index[-1].strftime("%Y-%m-%d"), "tonnes": float(iau.iloc[-1]), "chg_1w": chg(iau, 7), "chg_1m": chg(iau, 30), "n_days": len(iau)}
    return out


def gold(pb, s, rate):
    o = {"drivers": {}}
    ry = C("real_yields.csv", parse_dates=["date"])
    dx = C("dxy.csv", parse_dates=["date"])
    r10 = ry.set_index("date").r10.astype(float).sort_index() if ry is not None else None
    dxy = dx.set_index("date").dxy.astype(float).sort_index() if dx is not None else None
    if r10 is not None and len(r10):
        o["drivers"]["real10"] = {"asof": r10.index[-1].strftime("%Y-%m-%d"), "last": float(r10.iloc[-1]), "chg_1m": chg(r10, 30), "chg_3m": chg(r10, 91), "weekly": weekly(r10, 5)}
    if dxy is not None and len(dxy):
        o["drivers"]["dxy"] = {"asof": dxy.index[-1].strftime("%Y-%m-%d"), "last": float(dxy.iloc[-1]), "chg_1m_pct": pchg(dxy, 30), "chg_3m_pct": pchg(dxy, 91), "weekly": weekly(dxy, 5)}
    # driver fit (context only): weekly log gold on the 10-yr real yield and log dollar index, last 3 years
    if r10 is not None and dxy is not None and len(s):
        w = pd.concat([np.log(s).resample("W-FRI").last(), r10.resample("W-FRI").last(), np.log(dxy).resample("W-FRI").last()], axis=1, keys=["g", "r", "d"]).dropna()
        w = w[w.index >= w.index[-1] - pd.DateOffset(years=3)]
        if len(w) > 60:
            X = np.column_stack([np.ones(len(w)), w.r, w.d])
            b, *_ = np.linalg.lstsq(X, w.g.values, rcond=None)
            fit = X @ b
            res = w.g.values - fit
            r2 = 1 - res.var() / w.g.values.var()
            fair = float(np.exp(fit[-1]))
            o["fit"] = {"asof": w.index[-1].strftime("%Y-%m-%d"), "fair": fair, "gap_pct": 100 * (math.exp(w.g.values[-1]) / fair - 1), "r2": round(float(r2), 2),
                        "se_pct": round(float(100 * res.std()), 1), "variables": ["US 10-year real yield (TIPS, Treasury)", "US dollar index (DXY)"], "window": "weekly, last 3 years",
                        "hist": {"date": [d.strftime("%Y-%m-%d") for d in w.index], "actual": [round(float(math.exp(x)), 1) for x in w.g.values], "fit": [round(float(math.exp(x)), 1) for x in fit]}}
    o["etf"] = etf_gold()
    o["wgc"] = wgc_block()
    fs = []
    rd = o["drivers"].get("real10")
    if rd and rd.get("chg_1m") is not None:
        fs.append(fac("Real yields", 1 if rd["chg_1m"] <= -0.1 else -1 if rd["chg_1m"] >= 0.1 else 0, f"10-yr real yield {rd['last']:.2f}% ({sg(rd['chg_1m'], 2)} pts in a month)."))
    dd = o["drivers"].get("dxy")
    if dd and dd.get("chg_1m_pct") is not None:
        fs.append(fac("US dollar", 1 if dd["chg_1m_pct"] <= -1 else -1 if dd["chg_1m_pct"] >= 1 else 0, f"Dollar index {dd['last']:.2f} ({sg(dd['chg_1m_pct'], 1, '%')} in a month)."))
    e = (o.get("etf") or {}).get("gld")
    if e and e.get("chg_1m") is not None:
        fs.append(fac("ETF flows", 1 if e["chg_1m"] >= 10 else -1 if e["chg_1m"] <= -10 else 0, f"GLD holds {e['tonnes']:,.0f} t ({sg(e['chg_1m'], 0)} t in a month, {sg(e['chg_ytd'], 0)} t this year)."))
    wg = o.get("wgc")
    cb = next((r for r in (wg or {}).get("table", []) if r["key"] == "central_banks"), None)
    if cb and cb.get("yoy_pct") is not None:
        fs.append(fac("Central banks", 1 if cb["yoy_pct"] >= 10 else -1 if cb["yoy_pct"] <= -20 else 0,
                      f"Central banks bought {cb['now']:,.0f} t in {wg['quarter']} ({sg(cb['yoy_pct'], 0, '%')} y/y; World Gold Council, published {wg['published']})."))
    sp = pb.get("spreads") or []
    if sp and sp[0].get("lease_pct") is not None:
        lr = sp[0]["lease_pct"]
        fs.append(fac("Curve / lease rate", 1 if lr >= 1 else 0, f"Front spread pays {sp[0]['ann_pct']:.2f}% a year vs T-bills {rate:.2f}%: implied lease rate {lr:.2f}%{' (physical metal tight)' if lr >= 1 else ''}."))
    return o, fs


# ───────── silver ─────────
def silver(pb, s, gold_s):
    o = {}
    if gold_s is not None and len(s):
        r = (gold_s / s).dropna()
        r = r[(r > 20) & (r < 200)]
        r10 = r[r.index >= r.index[-1] - pd.DateOffset(years=10)]
        o["ratio"] = {"asof": r.index[-1].strftime("%Y-%m-%d"), "last": float(r.iloc[-1]), "pct10": pct_rank(r10, float(r.iloc[-1])), "med10": float(r10.median()),
                      "chg_1m": chg(r, 30), "weekly": weekly(r, 10)}
    i = C("etf_ishares.csv", parse_dates=["date"])
    if i is not None:
        slv = i[i.fund == "SLV"].set_index("date").sort_index()
        if len(slv):
            oz = slv.ounces.astype(float) / 1e6
            o["etf"] = {"asof": slv.index[-1].strftime("%Y-%m-%d"), "moz": float(oz.iloc[-1]), "tonnes": float(slv.tonnes.iloc[-1]), "chg_1w": chg(oz, 7), "chg_1m": chg(oz, 30),
                        "n_days": len(slv), "series": {"date": [d.strftime("%Y-%m-%d") for d in oz.index[-260:]], "v": [round(float(x), 2) for x in oz.values[-260:]]}}
    si = RAW / "silver_institute.json"
    if si.exists():
        o["survey"] = json.loads(si.read_text())
    fs = []
    if o.get("ratio"):
        p = o["ratio"]["pct10"]
        fs.append(fac("Gold/silver ratio", 1 if p is not None and p >= 75 else -1 if p is not None and p <= 25 else 0,
                      f"Gold/silver ratio {o['ratio']['last']:.1f} ({ordn(p)} percentile of 10 years, median {o['ratio']['med10']:.1f}); {'silver cheap to gold' if (p or 50) >= 75 else 'silver rich to gold' if (p or 50) <= 25 else 'mid-range'}."))
    if o.get("etf") and o["etf"]["n_days"] >= 20 and o["etf"].get("chg_1m") is not None:
        c = o["etf"]["chg_1m"]
        fs.append(fac("ETF flows", 1 if c >= 10 else -1 if c <= -10 else 0, f"SLV holds {o['etf']['moz']:,.0f} Moz ({sg(c, 1)} Moz in a month)."))
    hg = J("technicals/HG.json")
    if hg:
        a = next((x for x in hg["series"] if x["ticker"] == hg["default"]), hg["series"][0])["analysis"]
        m1 = (a.get("returns") or {}).get("1m")
        if m1 is not None:
            fs.append(fac("Industrial metals", 1 if m1 >= 3 else -1 if m1 <= -3 else 0, f"Copper {sg(m1, 1, '%')} in a month (about half of silver demand is industrial, incl. solar)."))
    return o, fs


# ───────── LME ─────────
def lme(m):
    d = C(f"lme_{m}.csv", parse_dates=["date"])
    if d is None or not len(d):
        return None
    d = d.set_index("date").sort_index().astype(float)
    st = d.stock.dropna()
    cash, m3 = d.cash.dropna(), d.m3.dropna()
    spread = (cash - m3).dropna()
    st5 = st[st.index >= st.index[-1] - pd.DateOffset(years=5)]
    return {"asof": d.index[-1].strftime("%Y-%m-%d"), "cash": float(cash.iloc[-1]), "m3": float(m3.iloc[-1]), "cash_3m": float(spread.iloc[-1]) if len(spread) else None,
            "cash_3m_pct5": pct_rank(spread[spread.index >= spread.index[-1] - pd.DateOffset(years=5)], float(spread.iloc[-1])) if len(spread) else None,
            "stock": float(st.iloc[-1]), "stock_chg_1w": chg(st, 7), "stock_chg_1m": chg(st, 30), "stock_pct5": pct_rank(st5, float(st.iloc[-1])), "years": int(d.index[-1].year - d.index[0].year + 1),
            "series": {"date": [x.strftime("%Y-%m-%d") for x in d.index[-780:]], "cash": [num(x) for x in d.cash.values[-780:]], "m3": [num(x) for x in d.m3.values[-780:]],
                       "stock": [num(x) for x in d.stock.values[-780:]]}, "source": "LME official prices and stocks via westmetall.com"}


def comex_stocks(metal):
    d = C("comex_stocks.csv", parse_dates=["date"])
    if d is None:
        return None
    x = d[d.metal == metal].set_index("date").sort_index()
    if not len(x):
        return None
    t = x.total.astype(float)
    return {"asof": x.index[-1].strftime("%Y-%m-%d"), "total": float(t.iloc[-1]), "registered": num(x.registered.iloc[-1]) if "registered" in x else None,
            "chg_1w": chg(t, 7), "chg_1m": chg(t, 30), "series": {"date": [d.strftime("%Y-%m-%d") for d in t.index[-260:]], "v": [float(v) for v in t.values[-260:]]}}


# ───────── copper ─────────
def icsg_block():
    d = RAW / "icsg"
    recs = sorted(p for p in d.glob("*.json") if p.name != "index.json") if d.exists() else []
    if not recs:
        return None
    cur = json.loads(recs[-1].read_text())
    out = {"issued": cur.get("issued"), "data_month": cur.get("data_month"), "columns": cur.get("columns"), "table": cur.get("table"), "points": cur.get("points"),
           "url": cur.get("url"), "source": "International Copper Study Group, monthly press release"}
    if len(recs) > 1:
        prev = json.loads(recs[-2].read_text())
        rev = []
        for k in ("mine", "refined", "usage", "balance", "balance_bonded"):
            a, b = (cur.get("table") or {}).get(k) or {}, (prev.get("table") or {}).get(k) or {}
            for col in a:
                if col in b and a[col] is not None and b[col] is not None and a[col] != b[col]:
                    rev.append({"line": k, "period": col, "now": a[col], "before": b[col], "chg": a[col] - b[col]})
        out["revisions"] = rev
        out["prev_issued"] = prev.get("issued")
        out["prev_table"] = prev.get("table")
    return out


def usgs_block(commodities):
    fs = sorted(RAW.glob("usgs_mcs*.csv"))
    if not fs:
        return None
    d = pd.read_csv(fs[-1], dtype=str)
    yr = re.search(r"(\d{4})", fs[-1].name).group(1)
    out = {"edition": f"USGS Mineral Commodity Summaries {yr}", "items": {}}
    for c in commodities:
        x = d[(d.Commodity == c) & d.Section.str.contains("World", na=False)]
        if not len(x):
            continue
        x = x.assign(v=pd.to_numeric(x.Value.str.replace(",", ""), errors="coerce"))
        prod = x[x.Statistics_detail.str.contains("Mine production|Smelter production|Mine production, bauxite|Refinery production", case=False, na=False)
                 & ~x.Statistics_detail.str.contains("capacity|Reserves", case=False, na=False)]
        if not len(prod):
            continue
        det = prod.Statistics_detail.value_counts().index[0]
        prod = prod[prod.Statistics_detail == det]
        yrs = sorted(prod.Year.dropna().unique())
        last = yrs[-1]
        cur = prod[prod.Year == last].set_index("Country").v
        prv = prod[prod.Year == yrs[-2]].set_index("Country").v if len(yrs) > 1 else None
        wrows = x[x.Country.str.startswith("World", na=False) & x.Statistics_detail.str.lower().str.startswith(det.lower().split(":")[0].split(",")[0])]
        wy = lambda yy: (lambda r: num(r.v.iloc[0]) if len(r) else None)(wrows[wrows.Year == yy])
        world = cur.get("World total (rounded)", cur.get("World total")) if not len(wrows) else wy(last)
        rows = [{"country": k, "now": num(v), "before": num(prv.get(k)) if prv is not None else None} for k, v in cur.sort_values(ascending=False).items()
                if not str(k).lower().startswith("world") and not str(k).lower().startswith("other")][:8]
        res = x[x.Statistics_detail.str.contains("Reserves", case=False, na=False)]
        resw = res[res.Country.str.startswith("World", na=False)].v
        out["items"][c] = {"what": det, "unit": prod.Unit.iloc[0], "year": last, "prev_year": yrs[-2] if len(yrs) > 1 else None, "world": num(world),
                           "world_prev": (wy(yrs[-2]) if len(wrows) and len(yrs) > 1 else num(prv.get("World total (rounded)", prv.get("World total"))) if prv is not None else None), "top": rows,
                           "reserves_world": num(resw.iloc[0]) if len(resw) else None, "reserves_unit": res.Unit.iloc[0] if len(res) else None}
        us = d[(d.Commodity == c) & d.Section.str.contains("Salient", na=False)]
        if len(us):
            us = us.assign(v=pd.to_numeric(us.Value.str.replace(",", ""), errors="coerce"))
            lines = []
            for det2 in us.Statistics_detail.unique()[:14]:
                y = us[us.Statistics_detail == det2].sort_values("Year")
                if y.v.notna().any():
                    lines.append({"line": det2, "unit": y.Unit.iloc[-1], "years": list(y.Year), "values": [num(v) for v in y.v]})
            out["items"][c]["us"] = lines
    return out


def copper(pb, rate):
    o = {"lme": lme("cu"), "icsg": icsg_block(), "comex_stocks": comex_stocks("copper")}
    L = o["lme"]
    _, s = tech("HG")
    if L and s is not None and len(s):
        d = C("lme_cu.csv", parse_dates=["date"]).set_index("date").sort_index()
        hg_t = (s * LB_PER_T).rename("comex")
        a = pd.concat([hg_t, d.m3.astype(float)], axis=1, keys=["comex", "lme"]).dropna()
        if len(a):
            arb = a.comex - a.lme
            o["arb"] = {"asof": a.index[-1].strftime("%Y-%m-%d"), "usd_t": float(arb.iloc[-1]), "pct": float(100 * arb.iloc[-1] / a.lme.iloc[-1]),
                        "chg_1m": chg(arb, 30), "series": {"date": [x.strftime("%Y-%m-%d") for x in arb.index[-520:]], "v": [round(float(x), 1) for x in arb.values[-520:]]},
                        "note": "COMEX front-month copper converted to $/t minus LME 3-month (both delayed closes; COMEX front and LME 3-month are not the same date of delivery)."}
    fs = []
    if L:
        if L.get("stock_chg_1m") is not None:
            pc = 100 * L["stock_chg_1m"] / max(1.0, L["stock"] - L["stock_chg_1m"])
            fs.append(fac("LME stocks", 1 if pc <= -10 else -1 if pc >= 10 else 0, f"LME copper stocks {L['stock']:,.0f} t ({sg(L['stock_chg_1m'], 0)} t in a month; {ordn(L['stock_pct5'])} percentile of 5 years)."))
        if L.get("cash_3m") is not None:
            fs.append(fac("LME spread", 1 if L["cash_3m"] >= 20 else -1 if L["cash_3m"] <= -60 else 0, f"LME cash–3M {sg(L['cash_3m'], 0)} $/t ({'backwardation: nearby metal tight' if L['cash_3m'] > 0 else 'contango'})."))
    ic = o.get("icsg")
    if ic and ic.get("table", {}).get("balance"):
        cols = ic["columns"]
        ytd = next((c for c in cols if c.startswith(cols[5].split()[0]) and "-" in c), cols[5] if len(cols) > 5 else None)
        bal = ic["table"]["balance"].get(ytd)
        if bal is not None:
            prev_bal = ((ic.get("prev_table") or {}).get("balance") or {}).get(ytd)
            fs.append(fac("ICSG balance", 1 if bal < 0 else -1 if bal > 100 else 0,
                          f"ICSG refined balance {ytd}: {'surplus' if bal > 0 else 'deficit'} {abs(bal):,.0f} kt"
                          + (f" (previous release {prev_bal:+,.0f} kt)" if prev_bal is not None else "") + f"; data to {ic['data_month']}, issued {ic['issued']}."))
    if o.get("arb"):
        p = o["arb"]["pct"]
        fs.append(fac("COMEX–LME arbitrage", 1 if p >= 3 else -1 if p <= -2 else 0, f"COMEX trades {sg(p, 1, '%')} vs LME 3-month ({sg(o['arb']['usd_t'], 0)} $/t){': US pulling metal in (tariff risk premium)' if p >= 3 else ''}."))
    return o, fs


# ───────── aluminum ─────────
def iai_block():
    d = C("iai_primary.csv")
    if d is None or not len(d):
        return None
    d = d.set_index("month")
    w = d["World"].astype(float)
    china = next((c for c in d.columns if c.lower().startswith("china")), None)
    ch = d[china].astype(float) if china else None
    last = w.index[-1]
    y, m = int(last[:4]), int(last[5:7])
    ya = f"{y - 1}-{m:02d}"
    ytd = [i for i in w.index if i.startswith(str(y))]
    ytd_p = [f"{y - 1}{i[4:]}" for i in ytd]
    days = lambda mm: pd.Period(mm).days_in_month
    out = {"month": last, "world": float(w.iloc[-1]), "world_daily": float(w.iloc[-1]) / days(last), "world_yoy_pct": 100 * (w.iloc[-1] / w.get(ya) - 1) if ya in w else None,
           "ytd_yoy_pct": 100 * (w[ytd].sum() / w[ytd_p].sum() - 1) if all(i in w for i in ytd_p) else None,
           "china": float(ch.iloc[-1]) if ch is not None else None, "china_yoy_pct": 100 * (ch.iloc[-1] / ch.get(ya) - 1) if ch is not None and ya in ch else None,
           "exchina_yoy_pct": 100 * ((w.iloc[-1] - ch.iloc[-1]) / (w.get(ya) - ch.get(ya)) - 1) if ch is not None and ya in w else None,
           "series": {"month": list(w.index[-61:]), "world": [num(x) for x in w.values[-61:]], "china": [num(x) for x in ch.values[-61:]] if ch is not None else None},
           "regions": {c: num(d[c].iloc[-1]) for c in d.columns if c not in ("World", "Daily average") and num(d[c].iloc[-1])}, "source": "International Aluminium Institute"}
    snaps = sorted((RAW / "iai").glob("snap_*.json")) if (RAW / "iai").exists() else []
    if len(snaps) > 1:
        a = {r["month"]: r for r in json.loads(snaps[-1].read_text())}
        b = {r["month"]: r for r in json.loads(snaps[-2].read_text())}
        out["revisions"] = [{"month": k, "now": a[k]["World"], "before": b[k]["World"], "chg": a[k]["World"] - b[k]["World"]} for k in a if k in b and a[k].get("World") != b[k].get("World")]
        out["prev_release_month"] = snaps[-2].stem[5:]
    return out


def aluminum(pb):
    o = {"lme": lme("al"), "iai": iai_block(), "comex_stocks": comex_stocks("aluminum")}
    aup, s = price_block("AUP")
    if aup is not None and s is not None and len(s):
        o["midwest"] = {**{k: aup[k] for k in ("contract", "last", "date", "chg_1m", "chg_3m", "chg_ytd")}, "usd_t": aup["last"] * LB_PER_T,
                        "weekly": weekly(s, 5), "pct5": pct_rank(s[s.index >= s.index[-1] - pd.DateOffset(years=5)], float(s.iloc[-1]))}
    fs = []
    L = o["lme"]
    if L:
        if L.get("stock_chg_1m") is not None:
            pc = 100 * L["stock_chg_1m"] / max(1.0, L["stock"] - L["stock_chg_1m"])
            fs.append(fac("LME stocks", 1 if pc <= -10 else -1 if pc >= 10 else 0, f"LME aluminium stocks {L['stock']:,.0f} t ({sg(L['stock_chg_1m'], 0)} t in a month)."))
        if L.get("cash_3m") is not None:
            fs.append(fac("LME spread", 1 if L["cash_3m"] >= 10 else -1 if L["cash_3m"] <= -40 else 0, f"LME cash–3M {sg(L['cash_3m'], 0)} $/t."))
    I = o["iai"]
    if I and I.get("world_yoy_pct") is not None:
        fs.append(fac("World output (IAI)", -1 if I["world_yoy_pct"] >= 3 else 1 if I["world_yoy_pct"] <= 0 else 0,
                      f"Primary output {I['month']}: {I['world']:,.0f} kt ({sg(I['world_yoy_pct'], 1, '%')} y/y; China {sg(I.get('china_yoy_pct'), 1, '%')}, outside China {sg(I.get('exchina_yoy_pct'), 1, '%')})."))
    mw = o.get("midwest")
    if mw and mw.get("chg_1m") is not None:
        fs.append(fac("US Midwest premium", 1 if mw["chg_1m"] >= 5 else -1 if mw["chg_1m"] <= -5 else 0, f"Midwest premium {mw['last']:.4f} $/lb (≈ ${mw['usd_t']:,.0f}/t; {sg(mw['chg_1m'], 1, '%')} in a month)."))
    return o, fs


# ───────── platinum and palladium ─────────
def ratio_block(a, b, lo, hi, years=10):
    """a / b on common dates (continuous front months), with its 10-year percentile and median."""
    if a is None or b is None or not len(a) or not len(b):
        return None
    r = (a / b).dropna()
    r = r[(r > lo) & (r < hi)]
    if not len(r):
        return None
    rw = r[r.index >= r.index[-1] - pd.DateOffset(years=years)]
    return {"asof": r.index[-1].strftime("%Y-%m-%d"), "last": float(r.iloc[-1]), "pct10": pct_rank(rw, float(r.iloc[-1])), "med10": float(rw.median()),
            "chg_1m": chg(r, 30), "chg_1y": chg(r, 365), "weekly": weekly(r, years)}


def revisions(cur, prev, cols):
    out = []
    for k, v in cur.items():
        b = prev.get(k) or {}
        for c in cols:
            pc = c if c in b else (c.rstrip("f") if c.rstrip("f") in b else c + "f" if c + "f" in b else None)
            if pc and v.get(c) is not None and b.get(pc) is not None and abs(v[c] - b[pc]) >= 0.5:
                out.append({"line": k, "period": c, "now": v[c], "before": b[pc], "chg": round(v[c] - b[pc], 1)})
    return out


WPIC_LINES = ["Total Mining Supply", "Refined Production: South Africa", "Refined Production: Russia", "Refined Production: Zimbabwe", "Refined Production: North America",
              "Recycling", "Total Supply", "Automotive", "Jewellery", "Industrial", "Industrial: Chemical", "Industrial: Glass", "Industrial: Hydrogen Stationary and Other",
              "Investment", "Investment: Change in Bars, Coins", "Investment: Change in ETF Holdings", "Investment: Change in Stocks Held by Exchanges", "Total Demand", "Balance", "Above Ground Stocks"]


def wpic_block():
    """WPIC Platinum Quarterly (Metals Focus research): platinum balance by year and quarter, with revisions vs the previous release."""
    d = RAW / "wpic"
    recs = sorted((p for p in d.glob("Q*_*.json")), key=lambda p: (p.stem[3:], p.stem[1])) if d.exists() else []
    if not recs:
        return None
    cur = json.loads(recs[-1].read_text())
    cols = cur["columns"][-4:]
    qs = cur["quarters"][-4:]
    tab = cur["table"]
    out = {"release": cur["release"], "fetched": cur.get("fetched"), "url": cur.get("url"), "report": cur.get("report"), "points": cur.get("points"), "heads": cur.get("heads"),
           "columns": cols, "quarters": qs, "rows": [{"line": k, **{c: (tab.get(k) or {}).get(c) for c in cols + qs}} for k in WPIC_LINES if k in tab],
           "source": "World Platinum Investment Council, Platinum Quarterly (research by Metals Focus); free tables workbook"}
    meta = RAW / "wpic" / "meta.json"
    if meta.exists():
        out["next_release"] = json.loads(meta.read_text()).get("next_release")
    if len(recs) > 1:
        prev = json.loads(recs[-2].read_text())
        out["prev_release"] = prev["release"]
        out["revisions"] = [r for r in revisions({k: tab[k] for k in WPIC_LINES if k in tab}, prev["table"], cols[-3:]) if r["period"] in cols]
    return out


JM_KEEP = {"platinum": ["Total primary supply", "Primary supply: South Africa", "Primary supply: Russia", "Primary supply: Zimbabwe", "Primary supply: North America",
                        "Total secondary supply", "Total combined supply", "Demand by application: Auto", "Demand by application: Jewellery", "Demand by application: Chemical",
                        "Demand by application: Glass", "Demand by application: Investment", "Total Demand", "Movements in stocks"],
           "palladium": ["Total Supply", "Supply: South Africa", "Russia: Primary", "Supply: North America", "Supply: Zimbabwe", "Total secondary supply",
                         "Secondary supply: Automotive", "Total combined supply", "Demand by Application: Auto", "Demand by Application: Electrical & Electronics",
                         "Demand by Application: Chemical", "Demand by Application: Investment", "Total Demand", "Movements in stocks"]}


def jm_block(metal):
    """Johnson Matthey PGM market report (annual, May): supply, recycling, demand and the balance (movements in stocks),
    with revisions vs the previous edition."""
    d = RAW / "jm"
    recs = sorted(d.glob("*.json")) if d.exists() else []
    recs = [p for p in recs if metal in json.loads(p.read_text())]
    if not recs:
        return None
    cur = json.loads(recs[-1].read_text())
    m = cur[metal]
    yrs = m["years"][-4:]
    tab = m["table"]
    keep = [k for k in JM_KEEP[metal] if k in tab]
    out = {"edition": cur["edition"], "url": cur.get("url"), "report": cur.get("report"), "years": yrs,
           "rows": [{"line": k.split(": ", 1)[-1] if not k.startswith("Russia") else "Russia (primary)", "key": k, **{y: tab[k].get(y) for y in yrs}} for k in keep],
           "source": "Johnson Matthey, PGM market report; free supply-and-demand history workbook"}
    if len(recs) > 1:
        prev = json.loads(recs[-2].read_text())
        out["prev_edition"] = prev["edition"]
        out["revisions"] = revisions({k: tab[k] for k in keep}, prev[metal]["table"], yrs[-3:-1])
    return out


def pgm_etf_block(fund):
    d = C("etf_pgm.csv", parse_dates=["date"])
    if d is None:
        return None
    x = d[d.fund == fund].set_index("date").sort_index()
    if not len(x):
        return None
    oz = x.ounces.astype(float)
    prev = oz.iloc[-2] if len(oz) > 1 else None
    ya = oz[oz.index <= oz.index[-1] - pd.Timedelta(days=360)]
    return {"fund": fund, "asof": oz.index[-1].strftime("%Y-%m-%d"), "koz": float(oz.iloc[-1]) / 1000, "chg_q_pct": 100 * (oz.iloc[-1] / prev - 1) if prev else None,
            "chg_y_pct": 100 * (oz.iloc[-1] / ya.iloc[-1] - 1) if len(ya) else None, "filed": x.filed.iloc[-1],
            "series": {"date": [i.strftime("%Y-%m-%d") for i in oz.index[-24:]], "v": [round(float(v) / 1000, 1) for v in oz.values[-24:]]},
            "source": f"abrdn {'Platinum' if fund == 'PPLT' else 'Palladium'} ETF Trust ({fund}), quarterly SEC filings (10-Q/10-K)"}


# ───────── daily ETF metal holdings, per fund, from the sponsors' own sites ─────────
OZ_PER_T = 32150.7466
# sponsor fee a year: only used to carry metal-per-share between and beyond the published anchors (the fee is paid in metal)
FEES = {"GLD": [("2100-01-01", 0.0040)], "IAU": [("2010-07-01", 0.0040), ("2100-01-01", 0.0025)], "SLV": [("2100-01-01", 0.0050)], "PLTM": [("2100-01-01", 0.0050)],
        "BAR": [("2100-01-01", 0.0020)], "PPLT": [("2100-01-01", 0.0060)], "PALL": [("2100-01-01", 0.0060)], "SGOL": [("2100-01-01", 0.0017)],
        "SIVR": [("2100-01-01", 0.0030)]}
ETF_FUNDS = {"gold": [("GLD", "SPDR Gold Shares"), ("IAU", "iShares Gold Trust"), ("PHYS", "Sprott Physical Gold Trust"), ("SGOL", "abrdn Physical Gold Shares"), ("BAR", "GraniteShares Gold Trust")],
             "silver": [("SLV", "iShares Silver Trust"), ("PSLV", "Sprott Physical Silver Trust"), ("SIVR", "abrdn Physical Silver Shares")],
             "platinum": [("PPLT", "abrdn Physical Platinum Shares"), ("SPPP", "Sprott Physical Platinum and Palladium Trust"), ("PLTM", "GraniteShares Platinum Trust")],
             "palladium": [("PALL", "abrdn Physical Palladium Shares"), ("SPPP", "Sprott Physical Platinum and Palladium Trust")]}
ETF_UNIT = {"gold": ("t", OZ_PER_T, 1), "silver": ("Moz", 1e6, 1), "platinum": ("koz", 1e3, 1), "palladium": ("koz", 1e3, 1)}


def _fee(fund, d):
    for until, f in FEES.get(fund, [("2100-01-01", 0.0)]):
        if str(d)[:10] < until:
            return f
    return 0.0


def ops_at(fund, dates, anchors):
    """Metal per share on `dates`: log-linear between anchor dates, carried by the sponsor fee before the first / after the last."""
    a = anchors.dropna().sort_index()
    a = a[~a.index.duplicated(keep="last")]
    if not len(a):
        return pd.Series(np.nan, index=dates)
    t = np.array([d.toordinal() for d in a.index], dtype=float)
    la = np.log(a.values.astype(float))
    out = []
    for d in dates:
        x = d.toordinal()
        if x <= t[0]:
            out.append(la[0] + _fee(fund, d) * (t[0] - x) / 365.25)
        elif x >= t[-1]:
            out.append(la[-1] - _fee(fund, d) * (x - t[-1]) / 365.25)
        else:
            out.append(np.interp(x, t, la))
    return pd.Series(np.exp(out), index=dates)


def _sec(fund):
    d = C("etf_sec.csv", parse_dates=["date"])
    if d is None:
        return None
    x = d[d.fund == fund].set_index("date").sort_index()
    return x if len(x) else None


def _at_or_before(s, d, days=6):
    b = s[(s.index <= d) & (s.index >= d - pd.Timedelta(days=days))]
    return float(b.iloc[-1]) if len(b) else None


def from_shares(fund, shares, snap_oz=None):
    """Daily ounces = shares outstanding x metal per share, anchored on the sponsor's own ounce figures (page snapshot)
    and the trust's quarter-end ounces in its SEC filings."""
    anc = {}
    sec = _sec(fund)
    if sec is not None:
        for d, r in sec.iterrows():
            sh = _at_or_before(shares, d) or num(r.get("shares"))
            if sh:
                anc[d] = float(r.ounces) / sh
    if snap_oz is not None:
        for d, oz in snap_oz.items():
            sh = _at_or_before(shares, d, 0)
            if sh:
                anc[d] = float(oz) / sh
    if not anc:
        return None, 0
    ops = ops_at(fund, shares.index, pd.Series(anc))
    return (shares * ops).dropna(), len(anc)


def gld_ops_anchor(oz, sh, at, n=10):
    """Gold per share at date `at` from the last n days where the sponsor's ounces and State Street's shares both exist
    (median, each carried to `at` by the fee), so one mismatched day cannot shift the level."""
    both = pd.concat([oz.rename("oz"), sh.rename("sh")], axis=1).dropna()
    both = both[both.index <= at].tail(n)
    if not len(both):
        return None
    f = _fee("GLD", at)
    v = (both.oz / both.sh) * np.exp(-f * np.array([(at - d).days for d in both.index]) / 365.25)
    return float(np.median(v))


def gld_derived(oz):
    """GLD ounces after the sponsor's stored daily history: daily shares outstanding (State Street NAV-history file) x gold
    per share. Gold per share is anchored on the sponsor's last daily figures and on any later SEC quarter-end ounces;
    between anchors log-interpolated, after the last one carried down by the 0.40% fee. Returns (series, n SEC anchors)."""
    g = C("etf_gld_ssga.csv", parse_dates=["date"])
    if g is None or not len(oz):
        return None
    sh = g.set_index("date").sort_index().shares.astype(float)
    sh = sh[sh > 0]
    last = oz.index[-1]
    a0 = gld_ops_anchor(oz, sh, last)
    if a0 is None:
        return None
    anc = {last: a0}
    sec = _sec("GLD")
    na = 0
    if sec is not None:
        for d, r in sec[sec.index > last].iterrows():
            s_ = _at_or_before(sh, d) or num(r.get("shares"))
            if s_:
                anc[d] = float(r.ounces) / s_; na += 1
    after = sh[sh.index > last]
    if not len(after):
        return after, na
    return (after * ops_at("GLD", after.index, pd.Series(anc))).dropna(), na


def gld_check():
    """Back-test of the derivation where the sponsor's ounces and State Street's shares overlap: anchor on a day, carry gold
    per share by the fee, compare with the sponsor's figure 1 week / 1 month / 3 months / 1 year later. Written to
    raw/gld_derivation_check.json (repo only, not shown on the page)."""
    g, h = C("etf_gld.csv", parse_dates=["date"]), C("etf_gld_ssga.csv", parse_dates=["date"])
    if g is None or h is None:
        return None
    oz = g.set_index("date").sort_index().ounces.astype(float)
    sh = h.set_index("date").sort_index().shares.astype(float)
    b = pd.concat([oz.rename("oz"), sh.rename("sh")], axis=1).dropna()
    b = b[(b.oz > 0) & (b.sh > 0)]
    if len(b) < 300:
        return None
    ops = b.oz / b.sh
    out = {"overlap": [b.index[0].strftime("%Y-%m-%d"), b.index[-1].strftime("%Y-%m-%d"), len(b)]}
    same = pd.Series(np.log(ops.values), index=ops.index)
    # same-day consistency: daily change of gold per share should be the fee only (big jumps = timing mismatch between files)
    dj = same.diff().dropna()
    out["daily_ops_jump_gt_0.1pct_share"] = round(float((dj.abs() > 0.001).mean()), 4)
    for lag, lab in ((5, "1w"), (21, "1m"), (63, "3m"), (252, "1y")):
        errs, chg_err = [], []
        idx = b.index
        for i in range(10, len(idx) - lag, 5):
            a, t = idx[i], idx[i + lag]
            o0 = gld_ops_anchor(b.oz, b.sh, a)
            est = b.sh.iloc[i + lag] * o0 * np.exp(-0.004 * (t - a).days / 365.25)
            errs.append(est / b.oz.iloc[i + lag] - 1)
            chg_err.append((est - b.oz.iloc[i]) - (b.oz.iloc[i + lag] - b.oz.iloc[i]))
        e = np.abs(np.array(errs)) * 100
        ce = np.abs(np.array(chg_err)) / OZ_PER_T
        rec = {"median_abs_pct": round(float(np.median(e)), 3), "p95_abs_pct": round(float(np.percentile(e, 95)), 3), "max_abs_pct": round(float(e.max()), 3),
               "flow_err_t_median": round(float(np.median(ce)), 2), "flow_err_t_p95": round(float(np.percentile(ce, 95)), 2), "n": len(e)}
        rs = [x for x, d in zip(np.abs(errs), idx[10:len(idx) - lag:5]) if d >= pd.Timestamp("2021-01-01")]
        rec["median_abs_pct_since_2021"] = round(float(np.median(rs) * 100), 3) if rs else None
        out[lab] = rec
    (RAW / "gld_derivation_check.json").write_text(json.dumps(out, indent=1))
    print("GLD derivation check:", json.dumps(out))
    return out


def fund_series(fund, metal):
    """(dated ounces series, meta) for one fund; None when the desk has no data for it."""
    if fund == "GLD":
        g = C("etf_gld.csv", parse_dates=["date"])
        if g is None:
            return None
        s = g.set_index("date").sort_index()
        oz = s.ounces.astype(float).where(s.ounces.astype(float) > 0, s.tonnes.astype(float) * OZ_PER_T)
        der = gld_derived(oz)
        if der is not None and len(der[0]):
            d, na = der
            return pd.concat([oz, d]).sort_index(), {
                "how": f"ounces in the trust: the sponsor's daily figures to {oz.index[-1]:%d %b %Y}; after that, derived each day as State Street's daily shares outstanding x gold per share "
                       f"(gold per share from the sponsor's last figures, falling by the 0.40% a year fee, recalibrated on {na} later quarter-end SEC filing{'s' if na != 1 else ''})",
                "daily": True, "ffill": 5, "derived": True, "url": "https://www.ssga.com/us/en/intermediary/etfs/spdr-gold-shares-gld"}
        sec = _sec("GLD")                                       # no State Street file: quarter ends from SEC filings
        if sec is not None:
            q = sec[sec.index > oz.index[-1]].ounces.astype(float)
            oz = pd.concat([oz, q]).sort_index()
        return oz, {"how": f"ounces in the trust, daily to {oz.index[-1]:%d %b %Y} (sponsor's history file); the sponsor's data host closes automated access in robots.txt",
                    "daily": True, "ffill": 5, "url": "https://www.spdrgoldshares.com/usa/historical-data/"}
    if fund in ("IAU", "SLV"):
        h = C("etf_ishares_hist.csv", parse_dates=["date"])
        sn = C("etf_ishares.csv", parse_dates=["date"])
        if h is None or not len(h[h.fund == fund]):
            if sn is None:
                return None
            x = sn[sn.fund == fund].set_index("date").sort_index()
            return x.ounces.astype(float), {"how": "ounces in trust, daily snapshot of the product page", "daily": True, "ffill": 5,
                                            "url": "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund" if fund == "IAU" else "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"}
        sh = h[h.fund == fund].set_index("date").sort_index().shares.astype(float)
        snap = sn[sn.fund == fund].set_index("date").ounces.astype(float) if sn is not None else None
        oz, na = from_shares(fund, sh, snap)
        if oz is None:
            return None
        if snap is not None:                                    # the sponsor's own figure wins on the days it was read
            for d, v in snap.items():
                if d in oz.index:
                    oz.loc[d] = v
        return oz, {"how": f"daily shares outstanding (product-page download) x metal per share; metal per share from the sponsor's ounces-in-trust figure and {na} quarter-end SEC anchors",
                    "daily": True, "ffill": 5, "derived": True,
                    "url": "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund" if fund == "IAU" else "https://www.ishares.com/us/products/239855/ishares-silver-trust-fund"}
    if fund in ("PHYS", "PSLV", "SPPP"):
        d = C("etf_sprott.csv", parse_dates=["date"])
        if d is None:
            return None
        x = d[(d.fund == fund) & (d.metal == metal)].set_index("date").sort_index()
        if not len(x):
            return None
        page = {"PHYS": "gold", "PSLV": "silver", "SPPP": "platinum-and-palladium"}[fund]
        return x.ounces.astype(float), {"how": "ounces held after each change, since inception (fund page's holdings chart) plus the page's daily figure",
                                        "daily": True, "ffill": None, "url": f"https://sprott.com/investment-strategies/exchange-listed-products/physical-bullion-funds/{page}/"}
    if fund in ("PLTM", "BAR"):
        d = C("etf_granite.csv", parse_dates=["date"])
        if d is None:
            return None
        x = d[d.fund == fund].set_index("date").sort_index()
        if not len(x):
            return None
        oz, na = from_shares(fund, x.shares.astype(float))
        if oz is None:
            return None
        return oz, {"how": f"daily shares outstanding (fund page's NAV/AUM history) x metal per share from {na} quarter-end SEC anchors",
                    "daily": True, "ffill": 5, "derived": True, "url": f"https://graniteshares.com/etfs/{fund.lower()}/"}
    if fund in ("PPLT", "PALL", "SGOL", "SIVR"):
        sec = _sec(fund)
        ab = C("etf_abrdn.csv", parse_dates=["date"])
        ab = ab[ab.fund == fund].set_index("date").sort_index() if ab is not None else None
        pts = {}
        if sec is not None:
            for d, r in sec.iterrows():
                pts[d] = float(r.ounces)
        if ab is not None and len(ab) and sec is not None:
            anc = {d: float(r.ounces) / num(r.shares) for d, r in sec.iterrows() if num(r.get("shares"))}
            if anc:
                ops = ops_at(fund, ab.index, pd.Series(anc))
                for d, r in ab.iterrows():
                    # creation basket size in shares, from the metal per basket and the filed metal per share (rounded to 2,500 shares)
                    bsh = round(float(r.basket_oz) / ops.loc[d] / 2500) * 2500 if num(r.basket_oz) else None
                    pts[d] = float(r.shares) * (float(r.basket_oz) / bsh if bsh else ops.loc[d])
        if not pts:
            return None
        s = pd.Series(pts).sort_index()
        return s, {"how": "quarter ends from the trust's SEC filings; from Nov 2026 daily: shares outstanding x metal per creation basket (fund page's data service, one reading a day)",
                   "daily": ab is not None and len(ab) > 0, "ffill": 5, "quarterly_before": ab.index[0].strftime("%Y-%m-%d") if ab is not None and len(ab) else None,
                   "url": "https://www.aberdeeninvestments.com/en-us/institutional/funds/view-all-funds/" + {"PPLT": "abrdn-physical-platinum-shares-etf-us0032601066",
                          "PALL": "abrdn-physical-palladium-shares-etf-us0032621023", "SGOL": "abrdn-physical-gold-shares-etf-us00326a1043", "SIVR": "abrdn-physical-silver-shares-etf-us0032641088"}[fund]}
    return None


def etf_factor(metal, E):
    """Month's net flow across the funds with a current daily reading (thresholds: gold 10 t, silver 10 Moz, PGMs 2% of holdings)."""
    if not E:
        return None
    a = pd.Timestamp(E["asof"])
    fr = [f for f in E["funds"] if f.get("chg_1m") is not None and pd.Timestamp(f["asof"]) >= a - pd.Timedelta(days=5)]
    if not fr:
        return None
    c, v, u = sum(f["chg_1m"] for f in fr), sum(f["v"] for f in fr), E["unit"]
    lim = {"gold": 10, "silver": 10}.get(metal, 0.02 * v)
    dp = 0 if u == "koz" else 1
    return fac("ETF flows", 1 if c >= lim else -1 if c <= -lim else 0,
               f"{', '.join(f['fund'] for f in fr)} hold{'s' if len(fr) == 1 else ''} {v:,.{dp}f} {u} ({sg(c, dp)} {u} in a month; daily, from the sponsors' sites, as of {E['asof']}).")


def _daily(s, meta, idx):
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if meta.get("ffill") is None:                                 # event series: holdings unchanged between listed dates
        return s.reindex(s.index.union(idx)).ffill().reindex(idx).where(idx >= s.index[0])
    q = meta.get("quarterly_before")
    d = s.reindex(s.index.union(idx)).ffill(limit=meta["ffill"]).reindex(idx)
    if q:                                                         # quarter-end points stay points before daily readings start
        d[idx < pd.Timestamp(q)] = s.reindex(idx)[idx < pd.Timestamp(q)]
    return d.where(idx <= s.index[-1] + pd.Timedelta(days=4))


def etf_daily(metal):
    unit, div, dp = ETF_UNIT[metal]
    funds, cols = [], {}
    for fund, name in ETF_FUNDS[metal]:
        try:
            r = fund_series(fund, metal)
        except Exception:
            import traceback; traceback.print_exc(); r = None
        if r is None or not len(r[0].dropna()):
            continue
        s, meta = r
        s = s.dropna().sort_index()
        cols[fund] = (s, meta)
    if not cols:
        return None
    last = max(s.index[-1] for s, _ in cols.values())
    idx = pd.bdate_range(min(s.index[0] for s, _ in cols.values()), last)
    D_ = {f: _daily(s, m, idx) / div for f, (s, m) in cols.items()}
    ys = pd.Timestamp(last.year, 1, 1) - pd.Timedelta(days=1)

    def change(d, cut, tol=6):
        d = d.dropna()
        if not len(d):
            return None
        b = d[(d.index <= cut) & (d.index >= cut - pd.Timedelta(days=tol))]
        return None if not len(b) else float(d.iloc[-1] - b.iloc[-1])
    for fund, name in ETF_FUNDS[metal]:
        if fund not in cols:
            continue
        s, meta = cols[fund]
        d = D_[fund].dropna()
        if not len(d):
            continue
        a = d.index[-1]
        daily_since = meta.get("quarterly_before") or s.index[0].strftime("%Y-%m-%d")
        funds.append({"fund": fund, "name": name, "asof": a.strftime("%Y-%m-%d"), "v": round(float(d.iloc[-1]), dp + 1),
                      "chg_1w": change(d, a - pd.Timedelta(days=7)), "chg_1m": change(d, a - pd.Timedelta(days=30)), "chg_ytd": change(d, ys, 10),
                      "since": s.index[0].strftime("%Y-%m-%d"), "daily_since": daily_since if meta.get("daily") else None,
                      "how": meta["how"], "derived": bool(meta.get("derived")), "url": meta["url"]})
    tot = {"v": sum(f["v"] for f in funds)}
    for k in ("chg_1w", "chg_1m", "chg_ytd"):
        tot[k] = None if any(f[k] is None for f in funds) else sum(f[k] for f in funds)
    d3 = idx[idx >= last - pd.DateOffset(years=3)]
    wk = pd.date_range(idx[0], last, freq="W-FRI")
    rnd = lambda v: None if v is None or v != v else round(float(v), dp + 1)
    weekly_ = {f: D_[f].reindex(D_[f].index.union(wk)).ffill(limit=5 if cols[f][1].get("ffill") else None).reindex(wk) for f in D_}
    for f in D_:                                                  # quarterly-only stretches: show the quarter-end point in its week, nothing in between
        q = cols[f][1].get("quarterly_before")
        if q:
            pts = cols[f][0] / div
            w = pd.Series(np.nan, index=wk)
            for d, v in pts[pts.index < pd.Timestamp(q)].items():
                k = wk[wk >= d]
                if len(k):
                    w.loc[k[0]] = v
            weekly_[f] = weekly_[f].where(wk >= pd.Timestamp(q), w)
    return {"unit": unit, "asof": last.strftime("%Y-%m-%d"), "funds": funds, "total": tot,
            "daily": {"date": [d.strftime("%Y-%m-%d") for d in d3], **{f: [rnd(v) for v in D_[f].reindex(d3).values] for f in D_}},
            "weekly": {"date": [d.strftime("%Y-%m-%d") for d in wk], **{f: [rnd(v) for v in weekly_[f].values] for f in D_}}}


def jm_line(J, key, yr):
    r = next((x for x in (J or {}).get("rows", []) if x["key"] == key), None)
    return r and r.get(yr)


def pgm(key, pb, s, gold_s, other_s):
    o = {}
    if key == "platinum":
        o["ratio_pd"] = ratio_block(s, other_s, 0.1, 10)
        o["ratio_gold"] = ratio_block(s, gold_s, 0.05, 2)
        o["wpic"] = wpic_block()
    else:
        o["ratio_pd"] = ratio_block(other_s, s, 0.1, 10)          # always platinum / palladium
        o["ratio_gold"] = ratio_block(s, gold_s, 0.05, 3)
    o["jm"] = jm_block(key)
    o["etf"] = pgm_etf_block("PPLT" if key == "platinum" else "PALL")
    o["comex_stocks"] = comex_stocks(key)
    fs = []
    W = o.get("wpic")
    if W:
        bal = next((r for r in W["rows"] if r["line"] == "Balance"), None)
        if bal:
            fy = W["columns"][-1]
            cy = W["columns"][-2]
            v = bal.get(fy)
            rv = next((r for r in W.get("revisions", []) if r["line"] == "Balance" and r["period"] == cy), None)
            if v is not None:
                fs.append(fac("WPIC balance", 1 if v < 0 else -1 if v > 250 else 0,
                              f"WPIC sees {fy.rstrip('f')} in {'deficit' if v < 0 else 'surplus'} {abs(v):,.0f} koz; {cy.rstrip('f')} {'deficit' if (bal.get(cy) or 0) < 0 else 'surplus'} {abs(bal.get(cy) or 0):,.0f} koz"
                              + (f" (revised {sg(rv['chg'], 0)} koz vs the {W['prev_release']} release)" if rv else "") + f"; Platinum Quarterly {W['release']}."))
    J = o.get("jm")
    if J:
        y = J["years"][-1]
        b = jm_line(J, "Movements in stocks", y)
        if b is not None:
            fs.append(fac("JM balance", 1 if b < 0 else -1 if b > 150 else 0, f"Johnson Matthey ({J['edition']}) puts {y} in {'deficit' if b < 0 else 'surplus'} {abs(b):,.0f} koz."))
        if key == "palladium":
            a1, a0 = jm_line(J, "Demand by Application: Auto", y), jm_line(J, "Demand by Application: Auto", J["years"][-2])
            if a1 and a0:
                pc = 100 * (a1 / a0 - 1)
                fs.append(fac("Autocatalyst demand", 1 if pc >= 2 else -1 if pc <= -2 else 0, f"JM autocatalyst demand {y} {a1:,.0f} koz ({sg(pc, 1, '%')} y/y; electrified and battery vehicles erode gasoline-car loadings)."))
    sp = pb.get("spreads") or []
    if sp and sp[0].get("lease_pct") is not None:
        lr = sp[0]["lease_pct"]
        fs.append(fac("Curve / lease rate", 1 if lr >= 1 else -1 if sp[0]["ann_pct"] > 0 and lr <= -1 else 0,
                      f"Front spread pays {sp[0]['ann_pct']:.2f}% a year: implied lease rate {lr:.2f}%{' (metal tight to borrow)' if lr >= 1 else ''}."))
    E = o.get("etf")
    if E and E.get("chg_q_pct") is not None:
        fs.append(fac("ETF holdings", 1 if E["chg_q_pct"] >= 3 else -1 if E["chg_q_pct"] <= -3 else 0,
                      f"{E['fund']} held {E['koz']:,.0f} koz on {E['asof']} ({sg(E['chg_q_pct'], 1, '%')} on the quarter{', ' + sg(E['chg_y_pct'], 1, '%') + ' on the year' if E.get('chg_y_pct') is not None else ''})."))
    R = o.get("ratio_gold")
    if R and R.get("pct10") is not None and key == "platinum":
        fs.append(fac("Platinum vs gold", 1 if R["pct10"] <= 20 else -1 if R["pct10"] >= 80 else 0,
                      f"Platinum/gold ratio {R['last']:.2f} ({ordn(R['pct10'])} percentile of 10 years); {'platinum cheap to gold' if R['pct10'] <= 20 else 'platinum rich to gold' if R['pct10'] >= 80 else 'mid-range'}."))
    P = o.get("ratio_pd")
    if P and P.get("pct10") is not None and key == "palladium":
        fs.append(fac("Palladium vs platinum", -1 if P["pct10"] <= 20 else 1 if P["pct10"] >= 80 else 0,
                      f"Platinum/palladium ratio {P['last']:.2f} ({ordn(P['pct10'])} percentile of 10 years); {'palladium rich to platinum (substitution risk)' if P['pct10'] <= 20 else 'palladium cheap to platinum' if P['pct10'] >= 80 else 'mid-range'}."))
    cx = o.get("comex_stocks")
    if cx and cx.get("chg_1m") is not None and cx["total"]:
        pc = 100 * cx["chg_1m"] / max(1.0, cx["total"] - cx["chg_1m"])
        fs.append(fac("NYMEX stocks", 1 if pc <= -10 else -1 if pc >= 10 else 0, f"NYMEX {key} stocks {cx['total']:,.0f} oz ({sg(cx['chg_1m'], 0)} oz in a month)."))
    return o, fs


def brief(name, pb, fs, extra):
    b = []
    if pb:
        b.append({"h": "Price", "t": f"{pb['contract']} {pb['last']:,.{pb['dp']}f} {pb['unit']} on {pb['date']}: {sg(pb['chg_1w'], 1, '%')} on the week, {sg(pb['chg_1m'], 1, '%')} on the month, "
                                     f"{sg(pb['chg_ytd'], 1, '%')} this year; 52-week range {pb['lo52']:,.{pb['dp']}f}–{pb['hi52']:,.{pb['dp']}f}."})
    for f in fs:
        b.append({"h": f["name"], "t": f["txt"]})
    b += extra
    return b


def main():
    rate = tbill()
    out = {"generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "rate": rate, "metals": {}}
    gold_s = None
    _, pl_s = tech("PL")
    _, pa_s = tech("PA")
    for key, (sym, csym, name, unit) in METALS.items():
        try:
            pb, s = price_block(sym)
            if pb:
                pb["spreads"] = ann_carry(pb["curve"], rate)
                pb["weekly"] = weekly(s, 10)
            o, fs = {}, []
            if key == "gold":
                o, fs = gold(pb or {}, s if s is not None else pd.Series(dtype=float), rate)
                gold_s = s
            elif key == "silver":
                o, fs = silver(pb or {}, s if s is not None else pd.Series(dtype=float), gold_s)
            elif key == "copper":
                o, fs = copper(pb or {}, rate)
            elif key == "aluminum":
                o, fs = aluminum(pb or {})
            elif key in ("platinum", "palladium"):
                o, fs = pgm(key, pb or {}, s if s is not None else pd.Series(dtype=float), gold_s, pa_s if key == "platinum" else pl_s)
            if key == "gold":
                try:
                    gld_check()
                except Exception:
                    import traceback; traceback.print_exc()
            if key in ETF_FUNDS:
                try:
                    o["etf_daily"] = etf_daily(key)
                    nf = etf_factor(key, o["etf_daily"])
                    if nf:
                        fs = [f for f in fs if f["name"] != "ETF flows"] + [nf]      # PGMs keep the quarterly "ETF holdings" read too
                except Exception:
                    import traceback; traceback.print_exc()
            o["usgs"] = (usgs_block({"gold": ["Gold"], "silver": ["Silver"], "copper": ["Copper"], "aluminum": ["Aluminum", "Bauxite"], "platinum": ["Platinum"], "palladium": ["Palladium"]}[key]) or None)
            c = cot(csym)
            score, v = view(fs)
            extra = []
            if c:
                extra.append({"h": "Positioning", "t": f"Managed money {'long' if c['net'] >= 0 else 'short'} {abs(c['net']):,.0f} lots in {csym} ({sg(c['chg'], 0)} on the week, "
                                                       f"{ordn(c['pct3'])} percentile of 3 years; CFTC, positions of {c['date']})."})
            out["metals"][key] = {"key": key, "sym": sym, "cot_sym": csym, "name": name, "unit": unit, "price": pb, "cot": c, "factors": fs, "score": score, "view": v,
                                  "brief": brief(name, pb, fs, extra), **o}
            print(key, v, score, [(f["name"], f["s"]) for f in fs])
        except Exception:
            import traceback; traceback.print_exc()
            out["metals"][key] = {"key": key, "sym": sym, "name": name, "error": True}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean(out), separators=(",", ":"), allow_nan=False))
    tmp.replace(OUT)
    if all(m.get("error") for m in out["metals"].values()):
        raise SystemExit("metals model: every metal failed")


if __name__ == "__main__":
    main()
