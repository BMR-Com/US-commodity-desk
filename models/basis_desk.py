"""Cash basis (cash minus nearby futures) for the desk's ags: live cattle, lean hogs, corn, soybeans, Chicago and KC wheat.

Cash series
  live cattle  USDA 5-area weekly steers, live FOB, head-weighted (LM_CT150, 2001-)
  lean hogs    CME Lean Hog Index rebuild (models/hogs.py, LM_HG201, 2001-)
  grains       USDA AgTransport weekly bids (Grain Transportation Report data, 2007-; published about 6 days after the
               week): Gulf, Great Lakes, state elevator bids; and USDA AMS daily bids (MARS, mid-2020-): Gulf export,
               N. Illinois River barge, Iowa interior, Chicago SRW, Gulf SRW, Kansas City HRW 11% (cash = quoted basis + the
               quoted futures month)
Basis = cash minus the nearest contract not rolling within 3 days. "Vs normal" = basis minus the median of the other
seasons in the same week (+/- 1). Weekly readings on Fridays; each record row starts at the first close after the cash
number is published.
Output: data/basis/<SYM>.json, data/basis/summary.json
"""
import json, sys, datetime as dt, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import seasonal_desk as SD  # noqa: E402
import grains_basis as GB  # noqa: E402

OUT = ROOT / "data" / "basis"
H = (1, 2, 4, 8)
# market: (name, unit, cents-or-dollars label, signal horizon in weeks or None, window months or None, primary location)
MK = {
    "LE": ("Live cattle", "$/cwt", 8, None, "5-area steers, live"),
    "HE": ("Lean hogs", "$/cwt", None, None, "CME Lean Hog Index"),
    "ZC": ("Corn", "¢/bu", None, None, "Illinois elevators (weekly)"),
    "ZS": ("Soybeans", "¢/bu", None, None, "Gulf (weekly)"),
    "ZW": ("Chicago wheat", "¢/bu", 4, None, "Illinois SRW elevators (weekly)"),
    "KE": ("KC wheat", "¢/bu", None, None, "Gulf HRW, Texas (weekly)"),
}
AGT = {"Corn": "ZC", "Soybeans": "ZS", "Soft Red Winter Wheat": "ZW", "Hard Red Winter Wheat": "KE"}
AGT_NAME = {("ZC", "Illinois"): "Illinois elevators (weekly)", ("ZC", "Iowa"): "Iowa elevators (weekly)", ("ZC", "Nebraska"): "Nebraska elevators (weekly)",
            ("ZC", "Gulf - Louisiana"): "Gulf (weekly)", ("ZC", "Great Lakes - Toledo"): "Toledo (weekly)",
            ("ZS", "Illinois"): "Illinois elevators (weekly)", ("ZS", "Iowa"): "Iowa elevators (weekly)", ("ZS", "Gulf - Louisiana"): "Gulf (weekly)",
            ("ZS", "Great Lakes - Toledo"): "Toledo (weekly)", ("ZW", "Illinois"): "Illinois SRW elevators (weekly)", ("ZW", "Gulf - Louisiana"): "Gulf SRW (weekly)",
            ("KE", "Gulf - Texas"): "Gulf HRW, Texas (weekly)", ("KE", "Oklahoma"): "Oklahoma elevators (weekly)", ("KE", "Portland"): "Portland HRW (weekly)"}


def cash_series():
    out = {}
    try:
        import hogs
        day = hogs.lean_hog_index()
        s = day["index"].dropna(); s.index = pd.to_datetime(s.index)
        out[("HE", "CME Lean Hog Index")] = (s, 1)
    except Exception as e:
        print("hogs index failed", e)
    try:
        c = pd.read_csv(ROOT / "data/livestock/raw/ct150_5area_weekly/detail.csv", low_memory=False)
        c = c[(c.class_description == "STEER") & (c.selling_basis_description == "LIVE FOB")]
        c["hd"] = pd.to_numeric(c.head_count.astype(str).str.replace(",", ""), errors="coerce")
        c["p"] = pd.to_numeric(c.weighted_avg_price, errors="coerce"); c["date"] = pd.to_datetime(c.report_date)
        c = c.dropna(subset=["hd", "p"])
        out[("LE", "5-area steers, live")] = (c.groupby("date").apply(lambda g: (g.p * g.hd).sum() / g.hd.sum()), 0)
    except Exception as e:
        print("cattle failed", e)
    try:
        a = pd.read_csv(ROOT / "data/grains/raw/agtransport/grain_basis.csv.gz", parse_dates=["date"])
        for (com, mk), g in a.groupby(["commodity", "market_name"]):
            key = (AGT.get(com), mk)
            if key in AGT_NAME:
                out[(key[0], AGT_NAME[key])] = (g.set_index("date").bid.astype(float).mul(100).sort_index(), 6)
    except Exception as e:
        print("agtransport failed", e)
    cache = {}
    for com, specs in GB.SERIES.items():
        sym = GB.SYM[com]
        px, _ = GB.contract_px(sym)
        if px is None:
            continue
        for lab, rep, flt in specs:
            if rep not in cache:
                cache[rep] = GB.load(rep)
            d = cache[rep]
            if d is None:
                continue
            b = GB.series(d, flt).dropna()
            cash = {}
            for t, r in b.iterrows():
                if not isinstance(r.fm, str):
                    continue
                f = GB.front_for(sym, t, r.fm, px.columns)
                if f and t in px.index and not np.isnan(px.at[t, f]):
                    cash[t] = px.at[t, f] + r.basis
            if cash:
                out[(sym, lab + " (daily, 2020-)")] = (pd.Series(cash).sort_index(), 0)
    return out


def panel(m, cash, lag):
    cal = m.cal
    cash = cash[~cash.index.duplicated()].sort_index()
    rows = []
    for t in pd.date_range(max(cash.index.min(), cal[0]) + pd.Timedelta(days=30), cal[-1], freq="W-FRI"):
        c = cash[cash.index <= t]
        if not len(c) or (t - c.index[-1]).days > 8:
            continue
        near = m.front_for(t + pd.Timedelta(days=3))
        if near is None:
            continue
        fut = m.px(near, t)
        if np.isnan(fut):
            continue
        i0 = cal.searchsorted(max(t, c.index[-1] + pd.Timedelta(days=lag)), side="right")
        r = dict(date=t, season=m.season(t), woy=int(t.isocalendar().week), cash=float(c.iloc[-1]), fut=float(fut),
                 basis=float(c.iloc[-1] - fut), near=m.label(near))
        for h in H:
            i1 = i0 + 5 * h
            if i1 >= len(cal):
                continue
            t0, t1 = cal[i0], cal[i1]
            fr = m.front_for(t1 + pd.Timedelta(days=2)); nx = m.nxt(fr) if fr else None
            if fr is None:
                continue
            a0, a1, b0, b1 = m.px(fr, t0), m.px(fr, t1), m.px(nx, t0), m.px(nx, t1)
            r[f"px{h}"] = float(np.log(a1 / a0) * 100) if a0 > 0 and a1 > 0 else np.nan
            r[f"sp{h}"] = float(((a1 - b1) - (a0 - b0)) * m.mult) if not np.isnan([a0, a1, b0, b1]).any() else np.nan
        rows.append(r)
    D = pd.DataFrame(rows)
    g = D.groupby(["season", "woy"]).basis.median().reset_index()
    D["norm"] = [g[(g.season != r.season) & ((g.woy - r.woy).abs() <= 1)].basis.median() for r in D.itertuples()]
    D["anom"] = D.basis - D.norm
    return D


def seasonal(m, D):
    """basis by week of the season (marketing year for crops, calendar year otherwise)"""
    start = lambda y: pd.Timestamp(y, m.y0, 1)
    D = D.copy(); D["sw"] = [min(52, int((t - start(s)).days // 7)) for t, s in zip(D.date, D.season)]
    cur = D.season.max(); hist = D[D.season < cur]
    piv = hist.pivot_table(index="season", columns="sw", values="basis", aggfunc="last")
    bands = {q: [[int(w), round(float(v), 2)] for w, v in piv.quantile(q / 100).items() if not np.isnan(v)] for q in (10, 25, 50, 75, 90)}
    avg5 = piv.tail(5).mean()
    pts = lambda s: [[int(w), round(float(v), 2)] for w, v in s.items() if not np.isnan(v)]
    by = lambda s: D[D.season == s].set_index("sw").basis
    return dict(bands=bands, avg5=pts(avg5), current=pts(by(cur)), last_year=pts(by(cur - 1)), season=int(cur),
                n_years=int(piv.shape[0]), first=int(piv.index.min()) if len(piv) else None, start_month=SD.MON[m.y0 - 1],
                season_kind=("Marketing year" if m.y0 != 1 else "Calendar year"))


def record(D, months=None):
    X = D.dropna(subset=["anom"])
    if months:
        X = X[X.date.dt.month.isin(months)]
    if len(X) < 60:
        return None, None
    cut = list(X.anom.quantile([1 / 3, 2 / 3]))
    X = X.assign(state=np.where(X.anom <= cut[0], "Weak", np.where(X.anom >= cut[1], "Firm", "Normal")))
    rows = []
    for st in ("Weak", "Normal", "Firm"):
        g = X[X.state == st]; r = dict(state=st, n=int(len(g)))
        for h in H:
            v, s = g.get(f"px{h}", pd.Series(dtype=float)).dropna(), g.get(f"sp{h}", pd.Series(dtype=float)).dropna()
            r[f"px{h}"] = round(float(v.mean()), 2) if len(v) else None; r[f"up{h}"] = round(float((v > 0).mean() * 100)) if len(v) else None
            r[f"sp{h}"] = round(float(s.mean())) if len(s) else None; r[f"spup{h}"] = round(float((s > 0).mean() * 100)) if len(s) else None
        rows.append(r)
    return rows, [round(float(c), 2) for c in cut]


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) or np.isinf(o) else round(float(o), 3)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    C = cash_series()
    summ = dict(generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), markets=[])
    for sym, (name, unit, hz, months, primary) in MK.items():
        m = SD.Market(sym)
        locs = []
        for (s, lab), (cash, lag) in C.items():
            if s != sym:
                continue
            try:
                D = panel(m, cash, lag)
            except Exception as e:
                print(sym, lab, "failed", e); continue
            if len(D) < 50:
                continue
            last = D.iloc[-1]
            same = D[(D.season < last.season) & ((D.woy - last.woy).abs() <= 1)].basis
            rec, cut = record(D, months)
            pct = round(float((D.dropna(subset=["anom"]).anom < last.anom).mean() * 100)) if not np.isnan(last.anom) else None
            stale = (m.cal[-1] - pd.Timestamp(cash.index.max())).days > 14 + lag
            state = None if cut is None or np.isnan(last.anom) or stale else ("Weak" if last.anom <= cut[0] else "Firm" if last.anom >= cut[1] else "Normal")
            locs.append(dict(location=lab, primary=lab == primary, since=str(D.date.min().date()), seasons=int(D.season.nunique()),
                             cash_as_of=str(pd.Timestamp(cash.index.max()).date()), stale=bool(stale),
                             now=dict(date=str(last.date.date()), cash=last.cash, fut=last.fut, near=last.near, basis=last.basis, norm=last.norm, anom=last.anom,
                                      chg4=float(last.basis - D.basis.iloc[-5]) if len(D) > 5 else None, state=state, pct=pct,
                                      same_week=[float(same.quantile(.1)), float(same.quantile(.9))] if len(same) >= 4 else None),
                             seasonal=seasonal(m, D), record=rec, window=("Oct–May" if months else "all year"),
                             weekly=[[str(t.date()), round(float(b), 2)] for t, b in zip(D.date, D.basis)]))
        if not locs:
            continue
        locs.sort(key=lambda x: (not x["primary"], "daily" in x["location"], x["location"]))
        p = locs[0]; st = p["now"]["state"]
        idea = None
        r = next((x for x in (p["record"] or []) if x["state"] == st), None) if hz and st in ("Weak", "Firm") else None
        ok = r is not None and r[f"px{hz}"] is not None and ((st == "Weak" and r[f"px{hz}"] <= -0.3) or (st == "Firm" and r[f"px{hz}"] >= 0.3))
        if ok:
            idea = dict(horizon=hz, side=("Bearish lean" if st == "Weak" else "Bullish lean"), location=p["location"],
                        avg=r[f"px{hz}"], hit=(100 - r[f"up{hz}"]) if st == "Weak" else r[f"up{hz}"], n=r["n"],
                        in_window=(months is None or dt.date.today().month in months))
        o = dict(sym=sym, name=name, unit=unit, as_of=p["now"]["date"], signal_horizon=hz, window=("Oct–May" if months else "all year"),
                 tested=bool(hz), idea=idea, locations=locs)
        (OUT / f"{sym}.json").write_text(json.dumps(clean(o), separators=(",", ":")))
        summ["markets"].append(clean(dict(sym=sym, name=name, unit=unit, as_of=o["as_of"], location=p["location"], basis=p["now"]["basis"],
                                          anom=p["now"]["anom"], state=st, pct=p["now"]["pct"], idea=idea, seasons=p["seasons"], since=p["since"])))
        print(sym, p["location"], p["now"]["basis"], p["now"]["anom"], st, idea)
    (OUT / "summary.json").write_text(json.dumps(clean(summ), separators=(",", ":")))


if __name__ == "__main__":
    main()
