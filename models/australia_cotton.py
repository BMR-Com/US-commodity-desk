"""Australian cotton desk model -> data/australia/australia.json (Cotton > Where it's grown, Australia section).

Crop history: Cotton Australia planted hectares and bales by season (1989-90 on); USDA PSD fills seasons Cotton Australia
has not posted yet. Season s = planting year (2026 = 2026-27, planted Sep-Dec 2026, picked Mar-Jun 2027).

Drivers, all measured at the same day of the season as today so every past season is judged on what was known then:
  water   total volume in the dams that supply the cotton valleys (BOM), GL
  rain    rain since 1 August at the northern cotton towns (planting moisture, dryland), % of the 1991-2020 average
  fallow  April-July rain at the northern towns (stored soil moisture), % of average
  price   ICE nearby in Australian cents/lb, July 1 to date, vs the previous three seasons (2000 on)
Area (log) and yield (bales/ha) are fitted on past seasons; the variable set is picked by leave-one-season-out error,
and the production range comes from those out-of-sample misses.
"""
import csv, gzip, json, math
from datetime import date, datetime, timedelta
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "australia"
RAW = D / "raw"
TODAY = date.today()
BALE_KG = 217.7243
NORTH = {"emerald", "dalby", "stgeorge", "goondiwindi", "moree", "narrabri", "bourke"}
SOUTH = {"warren", "hillston", "griffith"}
NORMAL = (1991, 2020)
TRAIN_FROM = 2000   # area per GL of stored water rose through the 1990s (water-use efficiency); fit on 2000 onwards
EVAL_FROM = 2005    # variable sets are compared on the same seasons (price starts 2000, needs three prior seasons)


def jl(name, default=None):
    f = RAW / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else default


def season_label(s):
    return f"{s}-{(s + 1) % 100:02d}"


def cur_season(d=TODAY):
    return d.year if d.month >= 7 else d.year - 1


def asof_in(s, d=TODAY):
    """Same day of season in season s (season starts 1 July of year s)."""
    off = (d - date(cur_season(d), 7, 1)).days
    return date(s, 7, 1) + timedelta(days=off)


# ---------------------------------------------------------------- crop history
def history():
    H = {}
    ca = jl("cotton_australia_stats", {}).get("charts", {})
    area = bales = None
    for c in ca.values():
        t = c["title"].lower()
        ser = next(iter(c["series"].values()), {}) if c["series"] else {}
        if "hectare" in t and "planted" in t and area is None:
            area = ser
        elif "bales" in t and "produced" in t and bales is None:
            bales = ser
    for y, v in (area or {}).items():
        H.setdefault(int(y) - 1, {})["area_ha"] = v
    for y, v in (bales or {}).items():
        H.setdefault(int(y) - 1, {})["bales"] = v
    for s in H:
        H[s]["src"] = "Cotton Australia"
    psd = jl("psd_australia", {}).get("years", {})
    for y, r in psd.items():
        s = int(y)
        p, a = r.get("Production"), r.get("Area Harvested")
        if p is None or a is None:
            continue
        h = H.setdefault(s, {})
        h["psd_bales"], h["psd_area_ha"] = p * 1000, a * 1000
        if "bales" not in h and s < cur_season():
            h["bales"], h["area_ha"], h["src"] = p * 1000, a * 1000, "USDA PSD (area harvested)"
    for s, h in H.items():
        if h.get("bales") and h.get("area_ha"):
            h["yield_bpha"] = h["bales"] / h["area_ha"]
    return H


# ---------------------------------------------------------------- daily series
def load_daily(name, key):
    f = RAW / name
    out = {}
    if not f.exists():
        return out
    with gzip.open(f, "rt") as g:
        for r in csv.DictReader(g):
            out.setdefault(r[key], {})[r["date"]] = float(r["mm" if "mm" in r else "ml"])
    return out


def window_sum(ser, a, b):
    """Sum of daily values a..b inclusive; None if more than 10% of days missing."""
    n, tot, miss = 0, 0.0, 0
    d = a
    while d <= b:
        v = ser.get(d.isoformat())
        if v is None:
            miss += 1
        else:
            tot += v
        n += 1
        d += timedelta(days=1)
    return None if n == 0 or miss > 0.1 * n else tot


def value_on(ser, d, back=10):
    for i in range(back + 1):
        v = ser.get((d - timedelta(days=i)).isoformat())
        if v is not None:
            return v
    return None


def rain_features(R, seasons, asof_today):
    """Per season: rain 1 Aug -> as-of and Apr-Jul at the northern towns, as % of the 1991-2020 average of the same window."""
    out = {}
    def mean_sites(sites, a, b):
        xs = [window_sum(R[s], a, b) for s in sites if s in R]
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if len(xs) >= max(1, len([s for s in sites if s in R]) - 1) else None
    north = [s for s in NORTH if s in R]
    for s in seasons:
        e = asof_in(s, asof_today)
        a = date(s, 8, 1)
        plant = mean_sites(north, a, e) if e >= a else 0.0
        fallow = mean_sites(north, date(s, 4, 1), date(s, 7, 31))
        out[s] = {"plant_mm": plant, "fallow_mm": fallow}
    def norm(k):
        xs = [out[s][k] for s in out if NORMAL[0] <= s <= NORMAL[1] and out[s][k] is not None]
        return sum(xs) / len(xs) if xs else None
    np_, nf = norm("plant_mm"), norm("fallow_mm")
    for s in out:
        o = out[s]
        o["plant_pct"] = None if o["plant_mm"] is None or not np_ else 100 * o["plant_mm"] / np_
        o["fallow_pct"] = None if o["fallow_mm"] is None or not nf else 100 * o["fallow_mm"] / nf
    return out, {"plant_mm": np_, "fallow_mm": nf}


def storage_features(S, seasons, asof_today):
    """Total GL in dams with a record covering every season used (so the total is comparable year to year)."""
    first = min(seasons)
    dams = [k for k, ser in S.items() if ser and min(ser) <= f"{first}-07-15"]
    out = {}
    for s in seasons:
        e = asof_in(s, asof_today)
        vals = [value_on(S[k], e) for k in dams]
        jul = [value_on(S[k], date(s, 7, 1)) for k in dams]
        out[s] = {"gl": None if any(v is None for v in vals) else sum(vals) / 1000,
                  "gl_jul1": None if any(v is None for v in jul) else sum(jul) / 1000}
    return out, dams


def price_features(seasons, asof_today):
    f = RAW / "prices.csv"
    if not f.exists():
        return {}
    rows = list(csv.DictReader(open(f)))
    px = {}
    for r in rows:
        try:
            ct, au = float(r.get("CT=F") or "nan"), float(r.get("AUDUSD=X") or "nan")
        except ValueError:
            continue
        if math.isfinite(ct) and math.isfinite(au) and au > 0:
            px[r["date"][:10]] = ct / au
    out = {}
    for s in seasons:
        e = asof_in(s, asof_today)
        xs = [v for d, v in px.items() if date(s, 7, 1).isoformat() <= d <= e.isoformat()]
        out[s] = sum(xs) / len(xs) if len(xs) >= 10 else None
    rel = {}
    for s in seasons:
        prev = [out.get(s - k) for k in (1, 2, 3)]
        if out.get(s) and all(prev):
            rel[s] = out[s] / (sum(prev) / 3)
    return {"aud_clb": out, "rel": rel}


# ---------------------------------------------------------------- fitting
def ols(X, y):
    X = np.column_stack([np.ones(len(y)), X])
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    return b


def loo(X, y):
    pred = np.empty(len(y))
    for i in range(len(y)):
        m = np.ones(len(y), bool); m[i] = False
        b = ols(X[m], y[m])
        pred[i] = b[0] + X[i] @ b[1:]
    return pred


def design(rows, vars_):
    return np.array([[r[v] for v in vars_] for r in rows], float)


def main():
    H = history()
    R = load_daily("rain_daily.csv.gz", "site")
    S = load_daily("storage_daily.csv.gz", "dam")
    cs = cur_season()
    # drivers as of the last day the rain archive covers at every town (ERA5 runs ~5 days behind)
    asof = min([TODAY] + [date.fromisoformat(max(v)) for v in R.values() if v])
    # leave out dams whose record stopped more than 10 days before that date
    S = {k: v for k, v in S.items() if v and date.fromisoformat(max(v)) >= asof - timedelta(days=10)}
    seasons_all = sorted(s for s in H if 1990 <= s < cs and H[s].get("bales") and H[s].get("area_ha"))
    if len(seasons_all) < 15 or not R or not S or not H:
        raise SystemExit(f"not enough data yet: {len(seasons_all)} seasons, rain sites {len(R)}, dams {len(S)}")
    seasons = seasons_all + [cs]
    rf, rnorm = rain_features(R, seasons, asof)
    sf, dams = storage_features(S, seasons, asof)
    pf = price_features(seasons, asof)

    rows = []
    for s in seasons:
        r = {"s": s, "gl": sf[s]["gl"], "plant": rf[s]["plant_pct"], "fallow": rf[s]["fallow_pct"],
             "price": (pf.get("rel") or {}).get(s), "trend": s - 2000}
        if r["gl"]:
            r["lgl"] = math.log(r["gl"])
        if s < cs:
            r["la"] = math.log(H[s]["area_ha"]); r["y"] = H[s]["yield_bpha"]
        rows.append(r)
    cur = next(r for r in rows if r["s"] == cs)

    AREA_SETS = [["lgl"], ["lgl", "plant"], ["lgl", "plant", "fallow"], ["lgl", "trend"], ["lgl", "plant", "trend"], ["lgl", "price"], ["lgl", "plant", "price"]]
    YIELD_SETS = [["trend"], ["trend", "lgl"], ["trend", "lgl", "plant"], ["trend", "plant"]]

    def pick(sets, target):
        res = []
        for vs in sets:
            tr = [r for r in rows if TRAIN_FROM <= r["s"] < cs and all(r.get(v) is not None for v in vs) and r.get(target) is not None]
            if len(tr) < 12 or any(cur.get(v) is None for v in vs):
                continue
            X, y = design(tr, vs), np.array([r[target] for r in tr])
            p = loo(X, y)
            ix = [i for i, r in enumerate(tr) if r["s"] >= EVAL_FROM]   # same seasons for every variable set
            rmse = float(np.sqrt(np.mean((p[ix] - y[ix]) ** 2)))
            res.append({"vars": vs, "n": len(tr), "n_eval": len(ix), "rmse": rmse, "years": [r["s"] for r in tr], "pred": p.tolist(), "obs": y.tolist(), "b": ols(X, y).tolist()})
        # compare on the common sample is fairer, but sets using price have fewer years; pick lowest rmse, ties -> fewer vars
        res.sort(key=lambda x: (round(x["rmse"], 4), len(x["vars"])))
        return res

    A = pick(AREA_SETS, "la")
    Y = pick(YIELD_SETS, "y")
    if not A or not Y:
        raise SystemExit("model could not be fitted")
    a, yv = A[0], Y[0]
    area_hat = math.exp(a["b"][0] + sum(b * cur[v] for b, v in zip(a["b"][1:], a["vars"])))
    yld_hat = yv["b"][0] + sum(b * cur[v] for b, v in zip(yv["b"][1:], yv["vars"]))
    prod_hat = area_hat * yld_hat

    # out-of-sample production misses (seasons in both samples)
    pa = dict(zip(a["years"], a["pred"])); py = dict(zip(yv["years"], yv["pred"]))
    bt = []
    for s in sorted(set(pa) & set(py)):
        est = math.exp(pa[s]) * py[s]
        bt.append({"season": season_label(s), "est_m": est / 1e6, "act_m": H[s]["bales"] / 1e6, "err_pct": 100 * (est / H[s]["bales"] - 1),
                   "area_est_kha": math.exp(pa[s]) / 1000, "area_act_kha": H[s]["area_ha"] / 1000})
    lerr = np.array([math.log(1 + x["err_pct"] / 100) for x in bt])
    lo, hi = (float(np.quantile(lerr, 0.1)), float(np.quantile(lerr, 0.9))) if len(lerr) >= 10 else (-0.3, 0.3)
    mape = float(np.mean(np.abs([x["err_pct"] for x in bt]))) if bt else None
    naive = [abs(H[s]["bales"] / H[s - 1]["bales"] - 1) * 100 for s in sorted(set(pa) & set(py)) if H.get(s - 1, {}).get("bales")]

    last = H.get(cs - 1, {})
    man = jl("forecasts_manual", {}).get("rows", [])
    def to_m(r):
        if r.get("bales_m"):
            return r["bales_m"]
        if r.get("lint_kt"):
            return r["lint_kt"] * 1e6 / BALE_KG / 1e6
    others = [{**r, "m480": round(to_m(r), 2) if to_m(r) else None} for r in man if r.get("season") == season_label(cs)]
    psd_cur = H.get(cs, {})
    if psd_cur.get("psd_bales"):
        others.append({"source": "USDA", "report": "PSD / WASDE", "date": jl("psd_australia", {}).get("fetched"), "season": season_label(cs), "region": "Australia",
                       "area_kha": psd_cur["psd_area_ha"] / 1000, "m480": round(psd_cur["psd_bales"] / 1e6, 2), "remark": "area harvested"})

    # storage detail by dam
    meta = jl("storage_meta", {})
    dtab = []
    for k, ser in sorted(S.items(), key=lambda kv: (meta.get(kv[0], {}).get("state", ""), meta.get(kv[0], {}).get("valley", ""))):
        now_d = max(ser)
        v = ser[now_d]
        same = [value_on(ser, date(y, *map(int, now_d[5:].split("-")))) for y in range(int(now_d[:4]) - 10, int(now_d[:4]))]
        same = [x for x in same if x is not None]
        ly = value_on(ser, date(int(now_d[:4]) - 1, *map(int, now_d[5:].split("-"))))
        allv = sorted(ser.values())
        hi_mark = allv[int(0.98 * (len(allv) - 1))]
        dtab.append({"dam": k.title(), "valley": meta.get(k, {}).get("valley"), "state": meta.get(k, {}).get("state"), "date": now_d,
                     "gl": v / 1000, "pct_high": 100 * v / hi_mark if hi_mark else None, "ly_gl": ly / 1000 if ly else None,
                     "avg10_gl": sum(same) / len(same) / 1000 if same else None, "in_model": k in dams})
    # rain detail by site
    fc = jl("rain_forecast", {}).get("sites", {})
    sites = {x["id"]: x for x in jl("sites", [])}
    rtab = []
    for sid, ser in R.items():
        last_d = date.fromisoformat(max(ser))
        tot = window_sum(ser, date(cs, 8, 1), last_d)
        norm = [window_sum(ser, date(y, 8, 1), asof_in(y, last_d)) for y in range(NORMAL[0], NORMAL[1] + 1)]
        norm = [x for x in norm if x is not None]
        l30 = window_sum(ser, last_d - timedelta(days=29), last_d)
        n30 = [window_sum(ser, asof_in(y, last_d) - timedelta(days=29), asof_in(y, last_d)) for y in range(NORMAL[0], NORMAL[1] + 1)]
        n30 = [x for x in n30 if x is not None]
        f16 = sum(v for d, v in (fc.get(sid) or {}).items() if v is not None and d > TODAY.isoformat())
        fd = [d for d, v in (fc.get(sid) or {}).items() if d > TODAY.isoformat()]
        nf = [window_sum(ser, asof_in(y, TODAY) + timedelta(days=1), asof_in(y, TODAY) + timedelta(days=len(fd))) for y in range(NORMAL[0], NORMAL[1] + 1)] if fd else []
        nf = [x for x in nf if x is not None]
        rk = sorted([x for x in [window_sum(ser, date(y, 8, 1), asof_in(y, last_d)) for y in range(1990, cs)] if x is not None] + [tot or 0])
        rtab.append({"site": sid, "label": sites.get(sid, {}).get("label", sid), "state": sites.get(sid, {}).get("state"), "valley": sites.get(sid, {}).get("valley"),
                     "through": last_d.isoformat(), "since_aug_mm": tot, "since_aug_pct": 100 * tot / (sum(norm) / len(norm)) if tot is not None and norm else None,
                     "rank": rk.index(tot or 0) + 1 if tot is not None else None, "years": len(rk),
                     "last30_mm": l30, "last30_pct": 100 * l30 / (sum(n30) / len(n30)) if l30 is not None and n30 else None,
                     "fc16_mm": round(f16, 1) if fd else None, "fc16_pct": 100 * f16 / (sum(nf) / len(nf)) if fd and nf and sum(nf) else None,
                     "north": sid in NORTH})
    rtab.sort(key=lambda x: (x["state"] != "QLD", x["label"]))

    hist_tab = [{"season": season_label(s), "area_kha": H[s]["area_ha"] / 1000, "m480": H[s]["bales"] / 1e6, "yield_bpha": H[s]["yield_bpha"],
                 "src": H[s].get("src"), "gl": sf.get(s, {}).get("gl"), "plant_pct": rf.get(s, {}).get("plant_pct"), "fallow_pct": rf.get(s, {}).get("fallow_pct"),
                 "psd_m480": H[s].get("psd_bales", 0) / 1e6 or None} for s in seasons_all]

    P = {"season": season_label(cs), "asof": asof.isoformat(), "m480": prod_hat / 1e6, "lo_m480": prod_hat * math.exp(lo) / 1e6, "hi_m480": prod_hat * math.exp(hi) / 1e6,
         "lint_kt": prod_hat * BALE_KG / 1e6, "area_kha": area_hat / 1000, "yield_bpha": yld_hat, "yield_kg_ha": yld_hat * BALE_KG,
         "last_m480": last.get("bales", 0) / 1e6 or None, "last_area_kha": last.get("area_ha", 0) / 1000 or None, "last_src": last.get("src"),
         "drivers": {"gl": cur["gl"], "plant_pct": cur["plant"], "fallow_pct": cur["fallow"], "price_rel": cur.get("price"),
                     "gl_last": sf.get(cs - 1, {}).get("gl"), "gl_avg10": np.mean([sf[s]["gl"] for s in seasons_all[-10:] if sf.get(s, {}).get("gl")]).item() if seasons_all else None},
         "area_model": {"vars": a["vars"], "n": a["n"], "loo_rmse_log": a["rmse"], "coef": a["b"], "alternatives": [{"vars": x["vars"], "n": x["n"], "loo_rmse_log": x["rmse"]} for x in A]},
         "yield_model": {"vars": yv["vars"], "n": yv["n"], "loo_rmse": yv["rmse"], "coef": yv["b"], "alternatives": [{"vars": x["vars"], "n": x["n"], "loo_rmse": x["rmse"]} for x in Y]},
         "backtest": {"mape_pct": mape, "naive_mape_pct": float(np.mean(naive)) if naive else None, "q10_pct": 100 * (math.exp(lo) - 1), "q90_pct": 100 * (math.exp(hi) - 1), "rows": bt},
         "dams_in_model": [d.title() for d in dams]}
    # ABARES-anchored update: ABARES' latest national figure for this season, moved by the change in water and rain since
    # its release, using the area and yield sensitivities fitted above (fixed variable set so the update always has both).
    anch = None
    abr = sorted([r for r in man if r.get("source") == "ABARES" and r.get("region") == "Australia" and r.get("season") == season_label(cs) and r.get("area_kha") and r.get("lint_kt")], key=lambda r: r["date"])
    if abr:
        ab = abr[-1]; ad = date.fromisoformat(ab["date"])
        tr = [r for r in rows if TRAIN_FROM <= r["s"] < cs and r.get("lgl") is not None and r.get("plant") is not None]
        ba = ols(design(tr, ["lgl", "plant"]), np.array([r["la"] for r in tr]))
        by = ols(design(tr, ["trend", "plant"]), np.array([r["y"] for r in tr]))
        gl_ab = sum(value_on(S[k], ad) or 0 for k in dams) / 1000
        pl_ab = rain_features(R, [cs], ad)[0][cs]["plant_pct"]
        # normal for the September window comes from the same 1991-2020 seasons
        rfa, _ = rain_features(R, list(range(NORMAL[0], NORMAL[1] + 1)) + [cs], ad)
        pl_ab = rfa[cs]["plant_pct"]
        d_la = ba[1] * (math.log(cur["gl"]) - math.log(gl_ab)) + ba[2] * (cur["plant"] - pl_ab)
        y_ab = ab["lint_kt"] * 1e6 / BALE_KG / (ab["area_kha"] * 1000)
        d_y = by[2] * (cur["plant"] - pl_ab)
        area_a = ab["area_kha"] * math.exp(d_la)
        yld_a = y_ab + d_y
        anch = {"from": f"ABARES {ab['date']}", "abares_area_kha": ab["area_kha"], "abares_m480": ab["lint_kt"] / BALE_KG, "abares_yield_bpha": y_ab,
                "gl_then": gl_ab, "gl_now": cur["gl"], "plant_then_pct": pl_ab, "plant_now_pct": cur["plant"],
                "area_change_pct": 100 * (math.exp(d_la) - 1), "yield_change_bpha": d_y, "area_kha": area_a, "yield_bpha": yld_a, "m480": area_a * yld_a / 1000,
                "lint_kt": area_a * yld_a * BALE_KG / 1000, "coef": {"area_per_log_gl": ba[1], "area_per_rain_pt": ba[2], "yield_per_rain_pt": by[2]}}
    P["statistical"] = {k: P[k] for k in ("m480", "lo_m480", "hi_m480", "lint_kt", "area_kha", "yield_bpha", "yield_kg_ha")}
    P["anchored"] = anch
    if anch:   # desk call = anchored update; the statistical model's 80% band (scaled) gives the range
        P.update({"m480": anch["m480"], "lint_kt": anch["lint_kt"], "area_kha": anch["area_kha"], "yield_bpha": anch["yield_bpha"], "yield_kg_ha": anch["yield_bpha"] * BALE_KG,
                  "lo_m480": anch["m480"] * math.exp(lo), "hi_m480": anch["m480"] * math.exp(hi), "method": "anchored"})
    else:
        P["method"] = "statistical"
    names = {"lgl": "water in storage", "plant": "rain since 1 August", "fallow": "April-July rain", "price": "ICE price in A$ vs last 3 seasons", "trend": "yield trend"}

    # brief
    def f2(x): return f"{x:.2f}"
    ab = next((o for o in others if o["source"] == "ABARES" and o["region"] == "Australia"), None)
    ca = next((o for o in others if o["source"] == "Cotton Australia"), None)
    us = next((o for o in others if o["source"] == "USDA"), None)
    cmp_ = "; ".join(f"{o['source']} {f2(o['m480'])} m ({o['date']})" for o in (ab, ca, us) if o and o.get("m480"))
    dr = P["drivers"]
    north = [x for x in rtab if x["north"] and x["since_aug_pct"] is not None]
    wet = sorted(north, key=lambda x: -x["since_aug_pct"])
    brief = [
        {"h": "Bottom line", "t": f"Desk estimate for {P['season']}: **{f2(P['m480'])} m bales** ({P['lint_kt']:.0f} kt lint) from about {P['area_kha']:.0f} kha at {P['yield_bpha']:.1f} bales/ha; "
              f"range {f2(P['lo_m480'])}–{f2(P['hi_m480'])}. Last season {f2(P['last_m480']) if P['last_m480'] else '–'} m. Others: {cmp_ or 'none recorded'}."},
        ({"h": "Since ABARES", "t": f"Starting from {anch['from']} ({anch['abares_area_kha']:.0f} kha, {f2(anch['abares_m480'])} m bales): water in the model's dams went from {anch['gl_then']:.0f} to {anch['gl_now']:.0f} GL and rain since 1 August "
              f"from {anch['plant_then_pct']:.0f}% to {anch['plant_now_pct']:.0f}% of average. On past seasons' sensitivities that is {anch['area_change_pct']:+.0f}% area and {anch['yield_change_bpha']:+.2f} bales/ha "
              f"(wetter starts bring in lower-yielding dryland), so **{anch['area_kha']:.0f} kha, {f2(anch['m480'])} m bales**. The statistical model alone, which does not see allocations or planting intentions, says "
              f"{f2(P['statistical']['m480'])} m ({f2(P['statistical']['lo_m480'])}–{f2(P['statistical']['hi_m480'])})."} if anch else None),
        {"h": "Water", "t": f"The {len(dams)} dams in the model hold **{dr['gl']:.0f} GL** today vs {dr['gl_last']:.0f} GL a year ago and a {dr['gl_avg10']:.0f} GL ten-season average for this date. "
              "Irrigated area follows water in storage more than anything else: the area model's first variable."} if dr["gl"] and dr["gl_last"] and dr["gl_avg10"] else {"h": "Water", "t": "Storage data incomplete."},
        {"h": "Rain", "t": (f"Since 1 August the northern cotton towns have had **{dr['plant_pct']:.0f}%** of the 1991–2020 average for this date (April–July: {dr['fallow_pct']:.0f}%). "
              + (f"Wettest: {', '.join(f'{x['label']} {x['since_aug_pct']:.0f}%' for x in wet[:3])}; driest: {', '.join(f'{x['label']} {x['since_aug_pct']:.0f}%' for x in wet[-2:])}. " if len(wet) >= 4 else "")
              + "Rain at planting mostly adds dryland area and fills on-farm storages from runoff; it changes valley allocations only if it reaches the dams.") if dr["plant_pct"] is not None and dr["fallow_pct"] is not None else "Rain data incomplete."},
        {"h": "Model", "t": f"Area uses {', '.join(names[v] for v in a['vars'])}; yield uses {', '.join(names[v] for v in yv['vars'])}. Judged on what was known at this date each season, "
              f"the estimate missed the final crop by {mape:.0f}% on average over {len(bt)} seasons (80% of misses between {P['backtest']['q10_pct']:+.0f}% and {P['backtest']['q90_pct']:+.0f}%), "
              f"vs {P['backtest']['naive_mape_pct']:.0f}% for 'same as last season'."} if mape is not None and P["backtest"]["naive_mape_pct"] else {"h": "Model", "t": "Backtest unavailable."},
    ]
    brief = [b for b in brief if b]
    out = {"built": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "brief": brief, "projection": P, "others": others, "history": hist_tab,
           "storage": dtab, "rain": rtab, "rain_normal": {"period": f"{NORMAL[0]}–{NORMAL[1]}", **rnorm},
           "names": names, "status": jl("collect_status", {}),
           "sources": ["Cotton Australia statistics (area, bales by season)", "USDA FAS PSD", "BOM Water Data Online (dam storage)", "Open-Meteo ERA5 archive and forecast (rain)",
                       "Yahoo (ICE cotton, AUD/USD)", "ABARES Australian Crop Report and Cotton Australia statements (entered by hand)"]}
    for k in ("brief", "projection", "history", "storage", "rain"):
        if not out[k]:
            raise SystemExit(f"check failed: {k} empty")
    tmp = D / ".australia.json.tmp"
    tmp.write_text(json.dumps(out, separators=(",", ":"), default=lambda x: None if isinstance(x, float) and not math.isfinite(x) else x))
    tmp.replace(D / "australia.json")
    print(json.dumps({k: P[k] for k in ("season", "m480", "lo_m480", "hi_m480", "area_kha", "yield_bpha")}, default=str), a["vars"], yv["vars"], f"MAPE {mape}")


if __name__ == "__main__":
    main()
