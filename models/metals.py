"""Metals desk model: gold, silver, copper, aluminum. Reads only what the metals workflow and the shared price/COT
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
          "copper": ("HG", "HG", "Copper", "$/lb"), "aluminum": ("ALI", "AUP", "Aluminum", "$/t")}


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


def sg(v, d=1, suf=""):
    return "–" if v is None else f"{'+' if v > 0 else ''}{v:,.{d}f}{suf}"


# ───────── gold ─────────
def wgc_block():
    snaps = sorted((RAW / "wgc").glob("sd_*.json")) if (RAW / "wgc").exists() else []
    if not snaps:
        return None
    cur = json.loads(snaps[-1].read_text())
    q = cur["data"]["Demand_Quarterly"]
    sq = cur["data"]["Supply_Quarterly"]
    cats = q["categories"]
    ser = {s["name"]: s["data"] for s in q["series"]}
    sup = {s["name"]: s["data"] for s in sq["series"]}
    rows = [("Jewellery consumption", ser), ("Technology", ser), ("Total bc", ser), ("Etfs", ser), ("Central banks", ser), ("Mine production", sup), ("Recycled gold", sup)]
    nice = {"Total bc": "Bar and coin", "Etfs": "Gold ETFs", "Jewellery consumption": "Jewellery", "Recycled gold": "Recycling"}
    i = len(cats) - 1
    table = []
    for name, src in rows:
        v = src.get(name)
        if not v:
            continue
        table.append({"line": nice.get(name, name), "now": v[i], "yago": v[i - 4] if i >= 4 else None, "yoy": (v[i] - v[i - 4]) if i >= 4 and v[i - 4] is not None else None,
                      "avg4": float(np.mean([x for x in v[i - 3:i + 1] if x is not None])), "hist": v[-12:]})
    lbma = ser.get("LBMA") or sup.get("LBMA")
    rev = []
    if len(snaps) > 1:
        prev = json.loads(snaps[-2].read_text())
        pq = prev["data"]["Demand_Quarterly"]
        pser = {s["name"]: s["data"] for s in pq["series"]}
        pc = pq["categories"]
        for name in ("Jewellery consumption", "Technology", "Total bc", "Etfs", "Central banks"):
            for k, c in enumerate(cats):
                if c in pc and name in pser and name in ser:
                    a, b = ser[name][k], pser[name][pc.index(c)]
                    if a is not None and b is not None and abs(a - b) >= 1:
                        rev.append({"line": nice.get(name, name), "quarter": c, "now": a, "before": b, "chg": a - b})
        rev = sorted(rev, key=lambda r: -abs(r["chg"]))[:10]
    return {"asof": cur["fetched"], "quarter": cats[i], "quarters": cats[-12:], "table": table, "lbma": lbma[-12:] if lbma else None,
            "revisions": rev, "prev_snapshot": snaps[-2].stem[3:] if len(snaps) > 1 else None, "source": "World Gold Council, Gold Demand Trends (Goldhub data)"}


def etf_gold():
    g = C("etf_gld.csv", parse_dates=["date"])
    i = C("etf_ishares.csv", parse_dates=["date"])
    if g is None:
        return None
    gs = g.set_index("date").tonnes.astype(float).sort_index()
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
    cb = next((r for r in (wg or {}).get("table", []) if r["line"] == "Central banks"), None)
    if cb:
        fs.append(fac("Central banks", 1 if cb["now"] >= 1.1 * cb["avg4"] else -1 if cb["now"] <= 0.8 * cb["avg4"] else 0,
                      f"Central banks bought {cb['now']:,.0f} t in {wg['quarter']} (4-quarter average {cb['avg4']:,.0f} t; {sg(cb['yoy'], 0)} t y/y)."))
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
                      f"Gold/silver ratio {o['ratio']['last']:.1f} ({int(p) if p is not None else '–'}th percentile of 10 years, median {o['ratio']['med10']:.1f}); {'silver cheap to gold' if (p or 50) >= 75 else 'silver rich to gold' if (p or 50) <= 25 else 'mid-range'}."))
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
        world = cur.get("World total (rounded)", cur.get("World total"))
        rows = [{"country": k, "now": num(v), "before": num(prv.get(k)) if prv is not None else None} for k, v in cur.sort_values(ascending=False).items()
                if not str(k).lower().startswith("world") and not str(k).lower().startswith("other")][:8]
        res = x[x.Statistics_detail.str.contains("Reserves", case=False, na=False)]
        resw = res[res.Country.str.startswith("World", na=False)].v
        out["items"][c] = {"what": det, "unit": prod.Unit.iloc[0], "year": last, "prev_year": yrs[-2] if len(yrs) > 1 else None, "world": num(world),
                           "world_prev": num(prv.get("World total (rounded)", prv.get("World total"))) if prv is not None else None, "top": rows,
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
            fs.append(fac("LME stocks", 1 if pc <= -10 else -1 if pc >= 10 else 0, f"LME copper stocks {L['stock']:,.0f} t ({sg(L['stock_chg_1m'], 0)} t in a month; {int(L['stock_pct5'] or 0)}th percentile of 5 years)."))
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
            o["usgs"] = (usgs_block({"gold": ["Gold"], "silver": ["Silver"], "copper": ["Copper"], "aluminum": ["Aluminum", "Bauxite"]}[key]) or None)
            c = cot(csym)
            score, v = view(fs)
            extra = []
            if c:
                extra.append({"h": "Positioning", "t": f"Managed money {'long' if c['net'] >= 0 else 'short'} {abs(c['net']):,.0f} lots in {csym} ({sg(c['chg'], 0)} on the week, "
                                                       f"{int(c['pct3']) if c['pct3'] is not None else '–'}th percentile of 3 years; CFTC, positions of {c['date']})."})
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
