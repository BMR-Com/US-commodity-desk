"""COT desk per market (in the style of BMR-Com/cftc-cot-full, plus positioning risk):

1. Positioning by trader group (managed money, producer/merchant, swap dealers, other reportables, non-reportables):
   net, weekly and 4-week change, % of open interest, percentiles (1/3/5 years, full history), COT index,
   flow z-score, streak, trader counts, top-4/8 concentration; managed-money flow driver
   (new buying / short covering / long liquidation / fresh shorting); dollar exposure and flows.
2. Money under water: last-in-first-out cost layers of managed-money gross longs and gross shorts, each week's
   change priced at the report-day close of a roll-adjusted series scaled to today's front contract.
   Gives average entry, share of positions losing money, dollar P&L now and on a price grid. Estimate only.
3. CTA model: trend score = mean sign of 20/60/120/250-day returns (back-adjusted front contract). Managed-money
   net regressed on the score (last 5 years) gives lots per unit of score. Levels where each signal flips and the
   implied fund flow there; price scenarios. Breakout and moving-average trigger levels on the tradable contract.
4. Seasonality of managed-money net by year.
Writes data/cot_desk/<SYM>.json and data/cot_desk/summary.json.
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cot_desk"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cot_backtest import roll_adjusted_index  # noqa: E402

GROUPS = {"grains": ["ZC", "ZS", "ZM", "ZL", "ZW", "KE"], "livestock": ["HE", "LE", "GF"], "softs": ["CT"], "dairy": ["DC", "GDK", "CSC", "CB", "GNF", "DY"], "energy": ["NG", "CL", "HO", "RB"]}
NAMES = {"CT": "Cotton", "ZC": "Corn", "ZS": "Soybeans", "ZW": "Chicago wheat", "KE": "KC HRW wheat", "ZM": "Soybean meal", "ZL": "Soybean oil",
         "HE": "Lean hogs", "LE": "Live cattle", "GF": "Feeder cattle", "DC": "Class III milk", "GDK": "Class IV milk",
         "CSC": "Cheese", "CB": "Butter", "GNF": "Nonfat dry milk", "DY": "Dry whey",
         "NG": "Natural gas", "CL": "WTI crude", "HO": "ULSD (heating oil)", "RB": "RBOB gasoline"}
# dollars per 1.00 of the quoted price, per contract (TradingView/CME quote units)
USD = {"CT": 500, "ZC": 50, "ZS": 50, "ZW": 50, "KE": 50, "ZM": 100, "ZL": 600, "HE": 400, "LE": 400, "GF": 500,
       "DC": 2000, "GDK": 2000, "CSC": 20000, "CB": 200, "GNF": 440, "DY": 440,
       "NG": 10000, "CL": 1000, "HO": 42000, "RB": 42000}
CATS = {"mm": ("m_money_positions_long_all", "m_money_positions_short_all", "traders_m_money_long_all", "traders_m_money_short_all", "Managed money"),
        "pm": ("prod_merc_positions_long", "prod_merc_positions_short", "traders_prod_merc_long_all", "traders_prod_merc_short_all", "Producer/merchant"),
        "sw": ("swap_positions_long_all", "swap__positions_short_all", "traders_swap_long_all", "traders_swap_short_all", "Swap dealers"),
        "or": ("other_rept_positions_long", "other_rept_positions_short", "traders_other_rept_long_all", "traders_other_rept_short", "Other reportables"),
        "nr": ("nonrept_positions_long_all", "nonrept_positions_short_all", None, None, "Non-reportables")}
LOOKS = (20, 60, 120, 250)


def num(x):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def pct(hist, v):
    h = np.asarray(hist, float)
    h = h[~np.isnan(h)]
    if not len(h) or v is None or np.isnan(v):
        return None
    return round(float(((h < v).sum() + 0.5 * (h == v).sum()) / len(h) * 100), 1)


def cot_index(a, w):
    a = np.asarray(a[-w:], float)
    a = a[~np.isnan(a)]
    if not len(a):
        return None
    lo, hi = a.min(), a.max()
    return 50.0 if hi == lo else round(float((a[-1] - lo) / (hi - lo) * 100), 1)


def streak(d):
    d = d[~np.isnan(d)]
    if not len(d) or d[-1] == 0:
        return 0
    s, n = np.sign(d[-1]), 0
    for x in d[::-1]:
        if np.sign(x) != s:
            break
        n += 1
    return int(n * s)


def load_cot(sym):
    p = ROOT / "data" / "cot" / f"{sym}_fo.csv"
    if not p.exists():
        return None
    d = pd.read_csv(p, low_memory=False)
    d["date"] = pd.to_datetime(d.report_date_as_yyyy_mm_dd)
    d = d.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    out = pd.DataFrame(index=d.index)
    out["oi"] = pd.to_numeric(d.open_interest_all, errors="coerce")
    for k, (l, s, tl, ts, _) in CATS.items():
        out[f"{k}_l"] = pd.to_numeric(d[l], errors="coerce")
        out[f"{k}_s"] = pd.to_numeric(d[s], errors="coerce")
        out[f"{k}_n"] = out[f"{k}_l"] - out[f"{k}_s"]
        if tl:
            out[f"{k}_tl"] = pd.to_numeric(d[tl], errors="coerce")
            out[f"{k}_ts"] = pd.to_numeric(d[ts], errors="coerce")
    for c in ("conc_net_le_4_tdr_long_all", "conc_net_le_4_tdr_short_all", "conc_net_le_8_tdr_long_all", "conc_net_le_8_tdr_short_all"):
        if c in d:
            out[c] = pd.to_numeric(d[c], errors="coerce")
    return out


def cat_metrics(c, k):
    N, L, S, oi = c[f"{k}_n"].to_numpy(float), c[f"{k}_l"].to_numpy(float), c[f"{k}_s"].to_numpy(float), c.oi.to_numpy(float)
    dN = np.diff(N)
    sd = np.nanstd(dN[-156:]) if len(dN) > 4 else np.nan
    npo = N / oi * 100
    r = {"L": num(L[-1]), "S": num(S[-1]), "N": num(N[-1]), "dL": num(L[-1] - L[-2]), "dS": num(S[-1] - S[-2]),
         "dN": num(N[-1] - N[-2]), "dN4": num(N[-1] - N[-5]), "np_oi": num(round(npo[-1], 1)), "dnp_oi": num(round(npo[-1] - npo[-2], 1)),
         "z": num(round(dN[-1] / sd, 2)) if sd and sd > 0 else None, "streak": streak(dN),
         "pct": {"y1": pct(N[-52:], N[-1]), "y3": pct(N[-156:], N[-1]), "y5": pct(N[-260:], N[-1]), "y10": pct(N[-520:], N[-1]), "all": pct(N, N[-1])},
         "pct_L": pct(L[-156:], L[-1]), "pct_S": pct(S[-156:], S[-1]),
         "cot": {"y1": cot_index(N, 52), "y3": cot_index(N, 156), "y5": cot_index(N, 260), "y10": cot_index(N, 520), "all": cot_index(N, len(N))}, "since": None,
         "range_3y": [num(np.nanmin(N[-156:])), num(np.nanmax(N[-156:]))], "record": [num(np.nanmin(N)), num(np.nanmax(N))]}
    if f"{k}_tl" in c:
        r["TL"], r["TS"] = num(c[f"{k}_tl"].iloc[-1]), num(c[f"{k}_ts"].iloc[-1])
        r["dTL"], r["dTS"] = num(c[f"{k}_tl"].iloc[-1] - c[f"{k}_tl"].iloc[-2]), num(c[f"{k}_ts"].iloc[-1] - c[f"{k}_ts"].iloc[-2])
    return r


def driver(dL, dS):
    if dL is None or dS is None:
        return None
    if dL - dS >= 0:
        return "new buying" if dL >= -dS else "short covering"
    return "long liquidation" if -dL >= dS else "fresh shorting"


def price_series(sym):
    """Daily back-adjusted front price in today's front-contract terms, plus the front contract's OHLC."""
    idx = roll_adjusted_index(sym)
    p = ROOT / "data" / "ohlc" / f"{sym}.csv"
    t = ROOT / "data" / "technicals" / f"{sym}.json"
    if not p.exists():
        return None, None, None
    o = pd.read_csv(p, parse_dates=["date"])
    front = json.loads(t.read_text()).get("default") if t.exists() else None
    if not front or front not in set(o.series):
        live = [s for s in o.series.unique() if s != "cont"]
        front = live[0] if live else "cont"
    f = o[o.series == front].set_index("date").sort_index()
    now_px = float(f.close.iloc[-1])
    # extend the contract-based index with the front contract's own recent moves (index can lag the contract file)
    lvl = idx * (now_px / idx.loc[:f.index[-1]].iloc[-1]) if idx.index[-1] >= f.index[-1] - pd.Timedelta(days=7) else None
    if lvl is None:
        r = f.close.pct_change().loc[idx.index[-1]:].iloc[1:]
        ext = pd.concat([idx, idx.iloc[-1] * (1 + r).cumprod()])
        lvl = ext * (now_px / ext.iloc[-1])
    return lvl.sort_index(), f, front


def lifo(changes, prices, start_layer):
    """Stack of (lots, price) layers; additions push at that week's price, reductions pop the newest first."""
    stack = [list(start_layer)] if start_layer[0] > 0 else []
    for dq, px in zip(changes, prices):
        if np.isnan(dq) or np.isnan(px):
            continue
        if dq > 0:
            stack.append([dq, px])
        else:
            q = -dq
            while q > 0 and stack:
                if stack[-1][0] <= q:
                    q -= stack[-1][0]
                    stack.pop()
                else:
                    stack[-1][0] -= q
                    q = 0
    return stack


def underwater(c, nominal, sym, start_weeks=104):
    """Cost layers priced on the nominal front-month close (how traders quote levels), last two years."""
    lvl = nominal
    px = lvl.reindex(lvl.index.union(c.index)).ffill().reindex(c.index)
    w = c.iloc[-start_weeks:]
    p = px.iloc[-start_weeks:].to_numpy(float)
    base_px = float(px.iloc[-start_weeks - 13:-start_weeks].mean()) if len(px) > start_weeks + 13 else float(p[0])
    now = float(lvl.iloc[-1])
    out = {"window_weeks": start_weeks, "price_now": now}
    for side, col, sgn in (("long", "mm_l", 1), ("short", "mm_s", -1)):
        q = w[col].to_numpy(float)
        st = lifo(np.diff(q), p[1:], (q[0], base_px))
        lots = sum(x[0] for x in st)
        if not lots:
            continue
        avg = sum(x[0] * x[1] for x in st) / lots
        def at(P):
            pnl = sum(sgn * (P - x[1]) * x[0] for x in st) * USD[sym]
            uw = sum(x[0] for x in st if sgn * (P - x[1]) < 0)
            return pnl, uw / lots * 100
        pnl, uw = at(now)
        out[side] = {"lots": lots, "avg_entry": avg, "pnl_usd": pnl, "pct_underwater": uw,
                     "layers": [[round(x[1], 4), round(x[0])] for x in st if x[0] >= 0.005 * lots]}
    grid = []
    for k in np.arange(-15, 15.1, 2.5):
        P = now * (1 + k / 100)
        row = {"move_pct": float(k), "price": P}
        for side, sgn in (("long", 1), ("short", -1)):
            if side in out:
                st = out[side]["layers"]
                lots = sum(x[1] for x in st) or 1
                row[f"{side}_pnl_usd"] = sum(sgn * (P - x[0]) * x[1] for x in st) * USD[sym]
                row[f"{side}_pct_underwater"] = sum(x[1] for x in st if sgn * (P - x[0]) < 0) / lots * 100
        grid.append(row)
    out["grid"] = grid
    # price levels where half of the longs (shorts) would be under water
    for side, sgn in (("long", 1), ("short", -1)):
        if side not in out:
            continue
        st = sorted(out[side]["layers"], key=lambda x: -sgn * x[0])  # longs: highest cost first
        tot, acc = sum(x[1] for x in st), 0
        for pr, lots in st:
            acc += lots
            if acc >= tot / 2:
                out[side]["half_underwater_at"] = pr
                break
    return out


def cta(c, lvl, f, sym):
    d = lvl.dropna()
    if len(d) < 300:
        return None
    sig = {n: np.sign(d / d.shift(n) - 1) for n in LOOKS}
    score = sum(sig.values()) / len(LOOKS)
    sc_w = score.reindex(score.index.union(c.index)).ffill().reindex(c.index)
    x = pd.DataFrame({"score": sc_w, "mm": c.mm_n}).dropna().iloc[-260:]
    if len(x) < 100:
        return None
    b_lvl, a = np.polyfit(x.score, x.mm, 1)
    r2 = float(np.corrcoef(x.score, x.mm)[0, 1] ** 2)
    # flow sensitivity: 2-week change in managed-money net vs 2-week change in the score (non-overlapping)
    x2 = pd.DataFrame({"ds": sc_w.diff(2), "dm": c.mm_n.diff(2)}).dropna().iloc[-260::2]
    b = float(np.polyfit(x2.ds, x2.dm, 1)[0]) if len(x2) > 40 else b_lvl
    r_flow = float(np.corrcoef(x2.ds, x2.dm)[0, 1]) if len(x2) > 40 else None
    now = float(d.iloc[-1])
    cur = float(score.iloc[-1])
    hi, lo, cl = f.high.fillna(f.close), f.low.fillna(f.close), f.close
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    flips = []
    for n in LOOKS:
        s = float(sig[n].iloc[-1])
        ref = float(d.iloc[-n])           # tomorrow the window starts one day later
        lvl_flip = ref
        flips.append({"lookback": n, "state": s, "flip_price": lvl_flip, "dist_pct": (lvl_flip / now - 1) * 100,
                      "dist_atr": (lvl_flip - now) / atr if atr else None,
                      "flow_lots_if_flipped": -s * 2 / len(LOOKS) * b, "flow_usd_if_flipped": -s * 2 / len(LOOKS) * b * lvl_flip * USD[sym],
                      "ref_window": [str(d.index[-n].date()), str(d.index[-n + min(5, n - 1)].date())],
                      "flip_next_5d": [float(d.iloc[-n + k]) for k in range(0, min(5, n))]})
    scen = []
    for k in (-10, -7.5, -5, -2.5, 0, 2.5, 5, 7.5, 10):
        P = now * (1 + k / 100)
        s2 = sum(np.sign(P / float(d.iloc[-n]) - 1) for n in LOOKS) / len(LOOKS)
        scen.append({"move_pct": k, "price": P, "score": s2, "implied_mm": a + b_lvl * s2, "flow_lots": b * (s2 - cur), "flow_usd": b * (s2 - cur) * P * USD[sym]})
    # breakout / moving-average triggers on the tradable contract
    lv = []
    for n in (20, 55, 100):
        H, L = hi.rolling(n).max().shift(), lo.rolling(n).min().shift()
        stt = pd.Series(np.where(cl > H, 1, np.where(cl < L, -1, np.nan)), index=cl.index).ffill()
        lv.append({"k": f"d{n}", "name": f"{n}-day breakout", "state": int(stt.iloc[-1]) if not np.isnan(stt.iloc[-1]) else 0,
                   "up": float(hi.iloc[-n:].max()), "dn": float(lo.iloc[-n:].min())})
    lastc = float(cl.iloc[-1])
    for n in (50, 100, 200):
        if len(cl) >= n:
            m = float(cl.rolling(n).mean().iloc[-1])
            lv.append({"k": f"s{n}", "name": f"{n}-day average", "state": 1 if lastc > m else -1, "lvl": m})
    ups, dns = [], []
    for x in lv:
        if "lvl" in x:
            (ups if x["lvl"] > lastc else dns).append((x["lvl"], x["name"]))
        else:
            if x["state"] != 1:
                ups.append((x["up"], x["name"] + " high"))
            if x["state"] != -1:
                dns.append((x["dn"], x["name"] + " low"))
    for x in flips:
        (ups if x["flip_price"] > now else dns).append((x["flip_price"] * lastc / now, f"{x['lookback']}-day momentum flip"))
    nxt = {}
    if ups:
        u = min(ups); nxt["up"] = {"lvl": u[0], "name": u[1], "pct": (u[0] / lastc - 1) * 100, "atr": (u[0] - lastc) / atr if atr else None}
    if dns:
        dd = max(dns); nxt["dn"] = {"lvl": dd[0], "name": dd[1], "pct": (dd[0] / lastc - 1) * 100, "atr": (dd[0] - lastc) / atr if atr else None}
    hist = pd.DataFrame({"score": sc_w, "mm": c.mm_n}).dropna().iloc[-156:]
    return {"score": cur, "beta_lots": b, "alpha_lots": a, "r2": r2, "beta_level": b_lvl, "r_flow": r_flow, "implied_mm": a + b_lvl * cur, "mm_now": float(c.mm_n.iloc[-1]),
            "gap_lots": float(c.mm_n.iloc[-1] - (a + b_lvl * cur)), "atr": atr, "price_now": now, "front_close": lastc,
            "signals": flips, "scenarios": scen, "triggers": lv, "next": nxt,
            "history": {"date": [str(i.date()) for i in hist.index], "score": hist.score.round(2).tolist(), "mm": hist.mm.tolist(),
                        "implied": (a + b_lvl * hist.score).round(0).tolist()}}


def seasonality(c):
    s = c.mm_n.dropna()
    df = pd.DataFrame({"y": s.index.year, "w": s.index.isocalendar().week.values, "v": s.values})
    df = df.groupby(["y", "w"]).v.last().reset_index()
    cy = int(df.y.max())
    out = {"years": {}, "band": {}}
    for y in range(cy - 5, cy + 1):
        g = df[df.y == y]
        out["years"][str(y)] = [[int(w), float(v)] for w, v in zip(g.w, g.v)]
    prev = df[(df.y >= cy - 5) & (df.y < cy)].groupby("w").v
    out["band"] = {"w": [int(w) for w in prev.min().index], "min": prev.min().tolist(), "max": prev.max().tolist(), "avg": prev.mean().round(0).tolist()}
    return out


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if math.isnan(o) or math.isinf(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


def build(sym):
    c = load_cot(sym)
    if c is None or len(c) < 60:
        return None
    cats = {k: cat_metrics(c, k) for k in CATS}
    mm = cats["mm"]
    out = {"sym": sym, "name": NAMES[sym], "date": str(c.index[-1].date()), "history_since": str(c.index[0].date()), "oi": num(c.oi.iloc[-1]), "doi": num(c.oi.iloc[-1] - c.oi.iloc[-2]),
           "cats": cats, "cat_names": {k: v[4] for k, v in CATS.items()}, "driver": driver(mm["dL"], mm["dS"]),
           "conc": {k: num(c[k].iloc[-1]) for k in c.columns if k.startswith("conc_")}}
    lvl, f, front = price_series(sym)
    hist = c.iloc[-520:]
    if lvl is not None:
        pxw = lvl.reindex(lvl.index.union(c.index)).ffill().reindex(hist.index)
        now = float(f.close.iloc[-1])
        m = USD[sym]
        out["front"] = front
        out["usd"] = {"price": now, "L": mm["L"] * now * m, "S": mm["S"] * now * m, "N": mm["N"] * now * m,
                      "dN": mm["dN"] * now * m, "dN4": mm["dN4"] * now * m}
        try:
            o = pd.read_csv(ROOT / "data" / "ohlc" / f"{sym}.csv", parse_dates=["date"])
            nominal = o[o.series == "cont"].set_index("date").close.sort_index()
            nominal = pd.concat([nominal, f.close.loc[nominal.index[-1]:].iloc[1:]])  # bridge to today's front
            out["underwater"] = underwater(c, nominal, sym)
        except Exception as e:
            print(sym, "underwater failed", e)
        try:
            out["cta"] = cta(c, lvl, f, sym)
        except Exception as e:
            import traceback; traceback.print_exc()
    else:
        pxw = pd.Series(np.nan, index=hist.index)
    out["series"] = {"date": [str(i.date()) for i in hist.index], "price": [num(v) for v in pxw],
                     **{f"{k}_{s}": [num(v) for v in hist[f"{k}_{s}"]] for k in CATS for s in ("l", "s", "n")},
                     "oi": [num(v) for v in hist.oi], "mm_tl": [num(v) for v in hist.mm_tl], "mm_ts": [num(v) for v in hist.mm_ts]}
    out["seasonal"] = seasonality(c)
    return clean(out)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    errs = {}
    syms = sys.argv[1:] or [s for g in GROUPS.values() for s in g]
    for s in syms:
        try:
            o = build(s)
        except Exception as e:
            import traceback; traceback.print_exc(); o = None
            errs[s] = traceback.format_exc()[-1500:]
        if not o:
            print(s, "no data")
            continue
        (OUT / f"{s}.json").write_text(json.dumps(o, separators=(",", ":")))
        mm = o["cats"]["mm"]
        uw, ct = o.get("underwater") or {}, o.get("cta") or {}
        summary[s] = {"name": o["name"], "date": o["date"], "N": mm["N"], "dN": mm["dN"], "dN4": mm["dN4"], "z": mm["z"], "pct3": mm["pct"]["y3"], "pct10": mm["pct"]["y10"], "pct_all": mm["pct"]["all"],
                      "cot3": mm["cot"]["y3"], "np_oi": mm["np_oi"], "driver": o["driver"], "streak": mm["streak"],
                      "pm_pct3": o["cats"]["pm"]["pct"]["y3"], "usdN": (o.get("usd") or {}).get("N"), "usd_dN": (o.get("usd") or {}).get("dN"),
                      "long_uw": (uw.get("long") or {}).get("pct_underwater"), "short_uw": (uw.get("short") or {}).get("pct_underwater"),
                      "long_pnl": (uw.get("long") or {}).get("pnl_usd"), "short_pnl": (uw.get("short") or {}).get("pnl_usd"),
                      "cta_score": ct.get("score"), "cta_gap": ct.get("gap_lots"), "next": ct.get("next"), "front": o.get("front")}
        print(s, o["date"], "MM", mm["N"], mm["dN"], o["driver"], "pct3", mm["pct"]["y3"], "| longs uw", summary[s]["long_uw"], "shorts uw", summary[s]["short_uw"],
              "| cta", ct.get("score"), "beta", round(ct.get("beta_lots") or 0), "r2", round(ct.get("r2") or 0, 2))
    if not sys.argv[1:]:
        (OUT / "errors.json").write_text(json.dumps(errs, indent=1))
        (OUT / "summary.json").write_text(json.dumps(clean({"groups": GROUPS, "markets": summary}), separators=(",", ":")))
