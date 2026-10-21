#!/usr/bin/env python3
"""Relative value for the desk's futures: calendar spreads (with % of full carry for the storable grains), the board
crush and oil share, inter-market ratios and realized-volatility cones, each ranked against its own history.

Inputs: data/contracts/<SYM>.csv (per-contract daily closes since 2006, TradingView), FRED 3-month T-bill (interest).
Writes data/grains/derived/rv.json.
"""
import io, json, math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CON = ROOT / "data" / "contracts"
OUT = ROOT / "data" / "grains" / "derived" / "rv.json"
CODES = "FGHJKMNQUVXZ"
MN = dict(zip(CODES, ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]))
SYMS = {"ZC": "Corn", "ZS": "Soybeans", "ZM": "Soybean meal", "ZL": "Soybean oil", "ZW": "Chicago wheat", "KE": "KC HRW wheat", "CT": "Cotton",
        "HE": "Lean hogs", "LE": "Live cattle", "GF": "Feeder cattle"}
UNIT = {"ZC": "¢/bu", "ZS": "¢/bu", "ZW": "¢/bu", "KE": "¢/bu", "ZM": "$/st", "ZL": "¢/lb", "CT": "¢/lb", "HE": "¢/lb", "LE": "¢/lb", "GF": "¢/lb"}
USD = {"ZC": 50, "ZS": 50, "ZW": 50, "KE": 50, "ZM": 100, "ZL": 600, "CT": 500, "HE": 400, "LE": 400, "GF": 500}   # $ per 1.00 of quote
STORAGE = {"ZC": 0.165, "ZS": 0.165, "ZW": 0.165, "KE": 0.165}      # ¢/bu/day: CBOT tariff (SRW/HRW at the variable-rate floor)
CASH = {"HE", "GF"}
CROSS = {"ZC": {("N", "U"), ("N", "Z"), ("U", "Z")}, "ZS": {("Q", "U"), ("U", "X"), ("N", "X"), ("Q", "X")}, "ZW": {("K", "N")}, "KE": {("K", "N")},
         "CT": {("N", "Z"), ("K", "Z")}}   # spreads across crop years: no storage arbitrage, so no full-carry measure


def ltd(sym, code):
    """Approximate last trading day of a contract (enough to align seasons and pick the front month)."""
    L, y = code[len(sym)], int(code[len(sym) + 1:]); m = CODES.index(L) + 1
    if sym in ("ZC", "ZS", "ZM", "ZL", "ZW", "KE"):
        return pd.Timestamp(y, m, 14)
    if sym == "CT":
        return pd.Timestamp(y, m, 8)
    if sym == "HE":
        return pd.Timestamp(y, m, 14)
    return pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)


def first_delivery(sym, code):
    L, y = code[len(sym)], int(code[len(sym) + 1:])
    return pd.Timestamp(y, CODES.index(L) + 1, 1)


def load(sym):
    p = CON / f"{sym}.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, parse_dates=["date"])
    px = d.pivot_table(index="date", columns="contract", values="close").sort_index()
    return px


def label(sym, code):
    return f"{MN[code[len(sym)]]} {code[-2:]}"


def live(sym, px, today):
    cs = [c for c in px.columns if ltd(sym, c) >= today.normalize() and px[c].last_valid_index() is not None
          and px[c].last_valid_index() >= today - pd.Timedelta(days=10)]
    return sorted(cs, key=lambda c: ltd(sym, c))


def front_returns(sym, px):
    """Daily log returns of the front contract, rolling 10 days before its last trade (no roll gaps)."""
    cs = sorted(px.columns, key=lambda c: ltd(sym, c))
    lr = np.log(px).diff()
    out = pd.Series(index=px.index, dtype=float)
    for d in px.index:
        c = next((c for c in cs if ltd(sym, c) > d + pd.Timedelta(days=10) and pd.notna(lr.at[d, c])), None)
        if c is not None:
            out[d] = lr.at[d, c]
    return out.dropna()


def front_close(sym, px):
    cs = sorted(px.columns, key=lambda c: ltd(sym, c))
    out = pd.Series(index=px.index, dtype=float)
    for d in px.index:
        c = next((c for c in cs if ltd(sym, c) > d + pd.Timedelta(days=10) and pd.notna(px.at[d, c])), None)
        if c is not None:
            out[d] = px.at[d, c]
    return out.dropna()


def pctile(hist, v):
    h = np.array([x for x in hist if x is not None and np.isfinite(x)])
    return float((h < v).mean() * 100) if len(h) >= 5 and v is not None else None


def tbill():
    try:
        import requests
        r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO", timeout=30)
        s = pd.read_csv(io.StringIO(r.text)).iloc[:, 1]
        return float(pd.to_numeric(s, errors="coerce").dropna().iloc[-1]) / 100
    except Exception:
        return 0.04


def spreads(sym, px, today, r):
    L = live(sym, px, today)[:5]
    out = []
    pairs = list(zip(L, L[1:]))
    # the old-crop/new-crop pair for the row crops
    newcrop = None
    oc_nc = {"ZC": ("N", "Z"), "ZS": ("N", "X"), "ZW": ("N", "Z"), "KE": ("N", "Z"), "CT": ("N", "Z")}.get(sym)
    if oc_nc:
        a = next((c for c in L if c[len(sym)] == oc_nc[0]), None)
        b = next((c for c in px.columns if a and c[len(sym)] == oc_nc[1] and c[-4:] == a[-4:]), None)
        if a and b and (a, b) not in pairs:
            pairs.append((a, b)); newcrop = (a, b)
    else:
        newcrop = None
    for a, b in pairs:
        pa, pb = px[a].dropna(), px[b].dropna()
        if not len(pa) or not len(pb):
            continue
        A, B = float(pa.iloc[-1]), float(pb.iloc[-1]); spr = A - B
        days = (first_delivery(sym, b) - first_delivery(sym, a)).days
        row = {"pair": f"{label(sym, a)} / {label(sym, b)}", "a": a, "b": b, "spread": round(spr, 3), "days": days,
               "usd": round(spr * USD[sym], 0)}
        full = None
        cross = (a, b) == newcrop or (a[len(sym)], b[len(sym)]) in CROSS.get(sym, ())
        if cross:
            row["pair"] += " (old/new crop)"
        if sym in STORAGE and not cross:      # full carry does not apply across crop years
            full = STORAGE[sym] * days + A * r * days / 360
            row["full_carry"] = round(full, 2); row["pct_full"] = round(-spr / full * 100, 0)
        # same pair in past years at the same number of days before the near contract's last trade
        dte = (ltd(sym, a) - today).days
        ya = int(a[-4:]); yb = int(b[-4:])
        hist, hist_pf = [], []
        for k in range(1, 16):
            ca, cb = f"{sym}{a[len(sym)]}{ya - k}", f"{sym}{b[len(sym)]}{yb - k}"
            if ca not in px or cb not in px:
                continue
            d = ltd(sym, ca) - pd.Timedelta(days=dte)
            s = (px[ca] - px[cb]).dropna()
            s = s[s.index <= d]
            if len(s) and (d - s.index[-1]).days < 10:
                hist.append(float(s.iloc[-1]))
                if full is not None and row.get("full_carry") is not None:
                    pa_ = float(px[ca].dropna()[px[ca].dropna().index <= d].iloc[-1])
                    hist_pf.append(-s.iloc[-1] / (STORAGE[sym] * days + pa_ * r * days / 360) * 100)
        if hist:
            row.update({"hist_n": len(hist), "hist_min": round(min(hist), 2), "hist_max": round(max(hist), 2), "hist_med": round(float(np.median(hist)), 2),
                        "pctile": pctile(hist, spr), "hist_pf_med": round(float(np.median(hist_pf)), 0) if hist_pf else None})
        # recent path (60 days) for sparkline
        s = (px[a] - px[b]).dropna().tail(60)
        row["path"] = [round(float(v), 3) for v in s]
        row["chg_5d"] = round(float(s.iloc[-1] - s.iloc[-6]), 3) if len(s) > 6 else None
        out.append(row)
    return out


def read(sp):
    """One-line trader read of a carry spread."""
    pf = sp.get("pct_full")
    if pf is None:
        p = sp.get("pctile")
        return None if p is None else ("tight (inverted vs history)" if p > 85 else "wide vs history" if p < 15 else "normal")
    if pf >= 80:
        return "near full carry: market paying to store — ample stocks, bearish nearby"
    if pf >= 50:
        return "moderate carry"
    if pf >= 0:
        return "weak carry: commercials want grain now"
    return "inverted: nearby scarcity, bullish nearby"


def crush(today):
    S, M, O = load("ZS"), load("ZM"), load("ZL")
    if S is None or M is None or O is None:
        return None
    MAP = {"F": "F", "H": "H", "K": "K", "N": "N", "Q": "Q", "U": "U", "X": "Z"}
    rows = []
    for s in live("ZS", S, today)[:6]:
        L, y = s[2], s[-4:]; mm = "ZM" + MAP[L] + y; oo = "ZL" + MAP[L] + y
        if mm not in M or oo not in O:
            continue
        sv, mv, ov = S[s].dropna(), M[mm].dropna(), O[oo].dropna()
        if not (len(sv) and len(mv) and len(ov)):
            continue
        oil_v, meal_v = ov.iloc[-1] * 0.11, mv.iloc[-1] * 0.022
        c = oil_v + meal_v - sv.iloc[-1] / 100
        rows.append({"label": f"{label('ZS', s)} beans / {label('ZM', mm)} products", "crush": round(float(c), 3), "oil_share": round(float(oil_v / (oil_v + meal_v) * 100), 1)})
    # front-month history
    fs, fm, fo = front_close("ZS", S), front_close("ZM", M), front_close("ZL", O)
    h = pd.concat([fs, fm, fo], axis=1, keys=["s", "m", "o"]).dropna()
    h["crush"] = h.o * 0.11 + h.m * 0.022 - h.s / 100
    h["share"] = h.o * 0.11 / (h.o * 0.11 + h.m * 0.022) * 100
    last = h.iloc[-1]; h10 = h[h.index >= h.index[-1] - pd.DateOffset(years=10)]
    mo = h10.groupby(h10.index.month).crush.median()
    wk = h.resample("W-FRI").last().tail(260)
    return {"curve": rows, "front": {"crush": round(float(last.crush), 3), "oil_share": round(float(last.share), 1),
                                     "crush_pct10": pctile(h10.crush, last.crush), "share_pct10": pctile(h10.share, last.share),
                                     "crush_med10": round(float(h10.crush.median()), 3), "share_med10": round(float(h10.share.median()), 1),
                                     "seasonal": [round(float(mo.get(m, np.nan)), 3) for m in range(1, 13)]},
            "hist": {"date": [d.strftime("%Y-%m-%d") for d in wk.index], "crush": [round(float(v), 3) for v in wk.crush], "share": [round(float(v), 1) for v in wk.share]}}


def ratios(fc):
    out = []
    def add(name, s, unit, note):
        s = s.dropna()
        if len(s) < 300:
            return
        h10 = s[s.index >= s.index[-1] - pd.DateOffset(years=10)]
        same = h10[(h10.index.month == s.index[-1].month)]
        wk = s.resample("W-FRI").last().tail(260)
        out.append({"name": name, "unit": unit, "now": round(float(s.iloc[-1]), 3), "pct10": pctile(h10, s.iloc[-1]),
                    "med10": round(float(h10.median()), 3), "same_month_med": round(float(same.median()), 3), "chg_20d": round(float(s.iloc[-1] - s.iloc[-21]), 3),
                    "note": note, "hist": {"date": [d.strftime("%Y-%m-%d") for d in wk.index], "v": [round(float(v), 3) for v in wk]}})
    if "ZS" in fc and "ZC" in fc:
        add("Soybean / corn price ratio", fc["ZS"] / fc["ZC"], "ratio", "Above ~2.4 favours soybean acres next spring, below ~2.2 favours corn (front months; new-crop Nov/Dec ratio matters most Jan–Mar).")
    if "ZW" in fc and "ZC" in fc:
        add("Chicago wheat − corn", fc["ZW"] - fc["ZC"], "¢/bu", "Narrow spread puts wheat into feed rations, capping wheat's premium.")
    if "KE" in fc and "ZW" in fc:
        add("KC HRW − Chicago SRW", fc["KE"] - fc["ZW"], "¢/bu", "Protein premium of bread wheat over soft wheat; widens on Plains drought or tight HRW stocks.")
    if "ZL" in fc and "ZM" in fc:
        add("Soybean oil / meal value", fc["ZL"] * 0.11 / (fc["ZM"] * 0.022), "ratio", "Oil's value per bushel vs meal's; biofuel demand has pushed this up since 2021.")
    if "LE" in fc and "GF" in fc:
        add("Feeder − live cattle", fc["GF"] - fc["LE"], "¢/lb", "Feeder premium over fed cattle; driven by corn cost and calf scarcity.")
    if "LE" in fc and "HE" in fc:
        add("Live cattle − lean hogs", fc["LE"] - fc["HE"], "¢/lb", "Beef vs pork relative price.")
    return out


def vol(sym, px, fc):
    r = front_returns(sym, px)
    if len(r) < 300:
        return None
    hv = lambda n: r.rolling(n).std() * math.sqrt(252) * 100
    h20, h60 = hv(20), hv(60)
    h10 = h20[h20.index >= h20.index[-1] - pd.DateOffset(years=10)].dropna()
    mo = h10.groupby(h10.index.month).median()
    now20, now60 = float(h20.iloc[-1]), float(h60.iloc[-1])
    price = float(fc[sym].iloc[-1]) if sym in fc else None
    d1 = price * now20 / 100 / math.sqrt(252) if price else None
    cone = {}
    for n in (10, 20, 60, 120):
        s = hv(n)[hv(n).index >= h20.index[-1] - pd.DateOffset(years=10)].dropna()
        cone[n] = {"now": round(float(hv(n).iloc[-1]), 1), "p10": round(float(s.quantile(.1)), 1), "p50": round(float(s.median()), 1), "p90": round(float(s.quantile(.9)), 1)}
    nxt = (h20.index[-1].month % 12) + 1
    return {"hv20": round(now20, 1), "hv60": round(now60, 1), "hv20_pct10": pctile(h10, now20), "seasonal": [round(float(mo.get(m, np.nan)), 1) for m in range(1, 13)],
            "next_month_med": round(float(mo.get(nxt, np.nan)), 1), "cone": cone, "day_move": round(d1, 2) if d1 else None,
            "day_move_usd": round(d1 * USD[sym]) if d1 else None, "week_move": round(d1 * math.sqrt(5), 2) if d1 else None,
            "hist": {"date": [d.strftime("%Y-%m-%d") for d in h20.resample("W-FRI").last().tail(260).index],
                     "hv20": [None if not np.isfinite(v) else round(float(v), 1) for v in h20.resample("W-FRI").last().tail(260)]}}


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    today = pd.Timestamp.now().normalize()
    r = tbill()
    res = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "rate": round(r * 100, 2), "storage": STORAGE, "markets": {}}
    fc = {}
    pxs = {}
    for sym in SYMS:
        px = load(sym)
        if px is None:
            continue
        pxs[sym] = px; fc[sym] = front_close(sym, px)
    for sym, px in pxs.items():
        sp = spreads(sym, px, today, r)
        for s in sp:
            s["read"] = read(s)
        res["markets"][sym] = {"name": SYMS[sym], "unit": UNIT[sym], "spreads": sp, "vol": vol(sym, px, fc)}
        print(sym, [(s["pair"], s["spread"], s.get("pct_full"), s.get("pctile")) for s in sp][:3], (res["markets"][sym]["vol"] or {}).get("hv20"))
    res["crush"] = crush(today)
    res["ratios"] = ratios(fc)
    OUT.write_text(json.dumps(clean(res), separators=(",", ":"), allow_nan=False))
    print("crush", (res["crush"] or {}).get("front"), [(x["name"], x["now"], x["pct10"]) for x in res["ratios"]])


if __name__ == "__main__":
    main()
