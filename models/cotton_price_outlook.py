"""Cotton price and spread outlook to May expiry from the desk's US balance-sheet scenarios and its Monte Carlo, using history.

History (2010/11 on): USDA's late-October US stocks/use vs the final number, May futures from Oct 29 to late April, the Mar/May, May/Jul and
Jul/Dec spreads near expiry, and CFTC producer/merchant shorts at end-October against world exports (USDA).
Writes data/derived/ct_price_outlook.json (page) and data/derived/ct_price_outlook_eval.json (fit detail; kept off the page).
"""
import json, sys, warnings
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import grains_esr_brief as G  # noqa: E402

EX = ["Exports", "Exports, Total", "Exports, total"]
SHORTAGE = ["2010/11", "2021/22"]        # world-shortage seasons: different regime, fitted apart
BALES_PER_LOT = 50000 / 480 / 1e6
VARS = ["USDA US balance sheet (October estimate vs final, 2010/11 on)", "desk US balance-sheet scenarios and their simulation",
        "ICE cotton futures by contract", "CFTC producer/merchant positions against USDA world exports", "historical volatility of the May contract", "February-March May, May/Jul and Jul/Dec vs USDA March US stocks/use (2007/08 on)", "cotton on-call (CFTC)"]


def load():
    w = G.wasde("Cotton.json", "cotton"); w["my"] = w.my.str.replace("2010/011", "2010/11")
    d = pd.read_csv(ROOT / "data" / "contracts" / "CT.csv", parse_dates=["date"])
    c = pd.read_csv(ROOT / "data" / "cot" / "CT_fut.csv", parse_dates=["report_date_as_yyyy_mm_dd"]).rename(columns={"report_date_as_yyyy_mm_dd": "d"}).sort_values("d")
    return w, d, c


def lv(w, reg, attrs, my, rd=None):
    x = w[(w.reg == reg) & (w.attr.isin(attrs if isinstance(attrs, list) else [attrs])) & (w.my == my)]
    if rd is not None:
        x = x[x.rd <= rd]
    x = x.sort_values("rd")
    return float(x.val.iloc[-1]) if len(x) else np.nan


def history(w, d, c, mmdd):
    at = lambda k, dt: (lambda x: float(x.close.iloc[-1]) if len(x) else np.nan)(d[(d.contract == k) & (d.date <= dt)])
    rows = []
    last_my_year = int(sorted(w[w.reg == "United States"].my.unique())[-1][:4])
    for y in range(2010, last_my_year):
        my, n = f"{y}/{(y + 1) % 100:02d}", y + 1
        t0, exp = pd.Timestamp(f"{y}-{mmdd}"), pd.Timestamp(f"{n}-04-24")
        su = lambda rd: 100 * lv(w, "United States", "Ending Stocks", my, rd) / (lv(w, "United States", "Domestic Use", my, rd) + lv(w, "United States", EX, my, rd))
        k0 = at(f"CTK{n}", t0)
        seg = d[(d.contract == f"CTK{n}") & (d.date > t0) & (d.date <= exp)].sort_values("date")
        if not len(seg) or np.isnan(k0):
            continue
        r = c[c.d <= t0].iloc[-1]
        wex = lv(w, "World", EX, my, t0)
        rows.append({"my": my, "su_oct": su(t0), "su_fin": su(None), "K0": k0, "Kend": float(seg.close.iloc[-1]), "Khi": float(seg.close.max()), "Klo": float(seg.close.min()),
                     "HK0": at(f"CTH{n}", t0) - k0, "KN0": k0 - at(f"CTN{n}", t0), "NZ0": at(f"CTN{n}", t0) - at(f"CTZ{n}", t0),
                     "HKe": at(f"CTH{n}", pd.Timestamp(f"{n}-02-20")) - at(f"CTK{n}", pd.Timestamp(f"{n}-02-20")),
                     "KNe": at(f"CTK{n}", pd.Timestamp(f"{n}-04-20")) - at(f"CTN{n}", pd.Timestamp(f"{n}-04-20")),
                     "NZe": at(f"CTN{n}", pd.Timestamp(f"{n}-06-10")) - at(f"CTZ{n}", pd.Timestamp(f"{n}-06-10")),
                     "pm_short_pct": 100 * r.prod_merc_positions_short * BALES_PER_LOT / wex if wex else np.nan,
                     "vol": float(np.log(seg.close).diff().std() * np.sqrt(252))})
    H = pd.DataFrame(rows).set_index("my")
    H["dsu"] = H.su_fin - H.su_oct
    H["Kchg"] = 100 * (H.Kend / H.K0 - 1)
    return H


def ols(y, X):
    Xa = np.column_stack([np.ones(len(y)), X]); b = np.linalg.lstsq(Xa, y, rcond=None)[0]; e = y - Xa @ b
    s = float(np.sqrt(e @ e / (len(y) - Xa.shape[1]))); t = b / np.sqrt(np.diag(s * s * np.linalg.inv(Xa.T @ Xa)))
    return {"b": [round(float(v), 4) for v in b], "t": [round(float(v), 2) for v in t], "r2": round(float(1 - (e @ e) / ((y - y.mean()) @ (y - y.mean()))), 2), "sd": round(s, 2), "n": int(len(y))}


def main():
    w, d, c = load()
    today = d.date.max()
    mmdd = today.strftime("%m-%d") if today.month in (9, 10, 11, 12) else "10-29"
    H = history(w, d, c, mmdd)
    ex = H.drop(index=[s for s in SHORTAGE if s in H.index])
    fit = {"kchg_dsu": ols(ex.Kchg.values, ex[["dsu"]].values),
           "kchg_dsu_hedge": ols(ex.Kchg.values, ex[["dsu", "pm_short_pct"]].values),
           "nz_su": ols(ex.NZe.values, ex[["su_fin"]].values),
           "nz_su_all": ols(H.NZe.values, H[["su_fin"]].values)}
    hk_ch, kn_ch = (ex.HKe - ex.HK0).values, (ex.KNe - ex.KN0).values

    # current market
    x = d[d.date == today].set_index("contract").close
    oy = today.year + 1 if today.month >= 8 else today.year
    px = {k: (float(x[f"CT{k}{oy}"]) if f"CT{k}{oy}" in x else None) for k in ("H", "K", "N")}
    px["Z_old"] = float(x[f"CTZ{oy - 1}"]) if f"CTZ{oy - 1}" in x else None
    px["Z_new"] = float(x[f"CTZ{oy}"]) if f"CTZ{oy}" in x else None
    sp = {"HK": round(px["H"] - px["K"], 2), "KN": round(px["K"] - px["N"], 2), "NZ": round(px["N"] - px["Z_new"], 2), "ZH": round(px["Z_old"] - px["H"], 2) if px["Z_old"] else None}
    K0 = px["K"]
    r = c.iloc[-1]; my_cur = f"{oy - 1}/{oy % 100:02d}"
    wex = lv(w, "World", EX, my_cur)
    hedge = {"date": r.d.strftime("%Y-%m-%d"), "pm_short_m": round(r.prod_merc_positions_short * BALES_PER_LOT, 2), "pm_long_m": round(r.prod_merc_positions_long * BALES_PER_LOT, 2),
             "mm_net_m": round((r.m_money_positions_long_all - r.m_money_positions_short_all) * BALES_PER_LOT, 2), "oi_m": round(r.open_interest_all * BALES_PER_LOT, 2),
             "world_exports": wex, "pct": round(100 * r.prod_merc_positions_short * BALES_PER_LOT / wex, 1)}
    hist_pct = H.pm_short_pct.dropna()
    hedge.update({"median_pct": round(float(hist_pct.median()), 1), "rank": f"{int((hist_pct < hedge['pct']).sum()) + 1} of {len(hist_pct) + 1}",
                  "high_years": [{"my": i, "pct": round(v.pm_short_pct, 0), "may_chg": round(v.Kchg, 1)} for i, v in H[H.pm_short_pct >= 38].iterrows()],
                  "high_mean": round(float(H[H.pm_short_pct >= 38].Kchg.mean()), 1), "low_mean": round(float(H[H.pm_short_pct < 30].Kchg.mean()), 1)})

    # balance-sheet scenarios
    B = json.loads((ROOT / "data" / "derived" / "balance_sheets.json").read_text())["markets"]["cotton"]
    usda_su = B["usda_su"]; S = B["summary"]; sim = B.get("sim") or {}
    b1, b2, bn = fit["kchg_dsu"]["b"], fit["kchg_dsu_hedge"]["b"], fit["nz_su"]["b"]
    def scen(su):
        dsu = su - usda_su
        m1 = b1[0] + b1[1] * dsu; m2 = b2[0] + b2[1] * dsu + b2[2] * hedge["pct"]
        return {"su": round(su, 1), "dsu": round(dsu, 1), "may_pct": round(m1, 1), "may": round(K0 * (1 + m1 / 100), 1), "may_hedge_pct": round(m2, 1), "may_hedge": round(K0 * (1 + m2 / 100), 1),
                "may_lo": round(K0 * (1 + (m1 - fit["kchg_dsu"]["sd"]) / 100), 1), "may_hi": round(K0 * (1 + (m1 + fit["kchg_dsu"]["sd"]) / 100), 1),
                "jul_dec": round(bn[0] + bn[1] * su, 1)}
    scenarios = {k: scen(S[k]["su"]) for k in ("bull", "base", "bear")}
    scenarios["usda"] = scen(usda_su)

    # Monte Carlo: stocks/use from the balance-sheet simulation, price residuals from history, daily paths to expiry
    rng = np.random.default_rng(11)
    n = 20000
    q = np.array(sim.get("su_q") or [S["base"]["su"]] * 99)
    su = np.interp(rng.uniform(0, 98, n), np.arange(99), q)
    dsu = su - usda_su
    m = b1[0] + b1[1] * dsu                                 # stocks surprise only (the merchant-hedge term is not significant once it is in)
    term = K0 * np.exp(np.log1p((m + rng.normal(0, fit["kchg_dsu"]["sd"], n)) / 100))
    exp_day = pd.Timestamp(f"{oy}-04-24")
    days = max(int(np.busday_count(today.date(), exp_day.date())), 5)
    vol = float(np.median(H.vol))
    steps = rng.normal(0, vol / np.sqrt(252), (2000, days)).cumsum(axis=1)
    tt = np.arange(1, days + 1) / days
    bridge = steps - tt * steps[:, -1:]                      # Brownian bridge from today's price to each simulated expiry price
    paths = K0 * np.exp(np.log(term[:2000, None] / K0) * tt + bridge)
    pmax, pmin = paths.max(axis=1), paths.min(axis=1)
    pct = lambda a: {p: round(float(np.percentile(a, p)), 1) for p in (10, 25, 50, 75, 90)}
    nz = bn[0] + bn[1] * su + rng.normal(0, fit["nz_su"]["sd"], n)
    hk = sp["HK"] + rng.choice(hk_ch, n) ; kn = sp["KN"] + rng.choice(kn_ch, n)
    mc = {"n": n, "paths": 2000, "days": days, "vol_pct": round(100 * vol, 1), "may_expiry": pct(term), "may_high": pct(pmax), "may_low": pct(pmin),
          "p_above": {lvl: round(100 * float((pmax >= lvl).mean()), 0) for lvl in (90, 95, 100, 110)},
          "p_below": {lvl: round(100 * float((pmin <= lvl).mean()), 0) for lvl in (80, 78, 75)},
          "mar_may": pct(hk), "may_jul": pct(kn), "jul_dec": pct(nz), "p_hk_inverse": round(100 * float((hk > 0).mean()), 0), "p_kn_inverse": round(100 * float((kn > 0).mean()), 0)}

    # fair value: the market prices USDA's numbers once crop and exports are clear (Feb-Mar), so fit Feb-Mar averages
    # of May, May/Jul and Jul/Dec to USDA's March US stocks/use (the desk scenario stands in for where USDA's March number lands)
    fvrows = []
    for y in range(2007, oy - 1):
        my, n_ = f"{y}/{(y + 1) % 100:02d}", y + 1
        rd = pd.Timestamp(f"{n_}-03-15")
        den = lv(w, "United States", "Domestic Use", my, rd) + lv(w, "United States", EX, my, rd)
        su_m = 100 * lv(w, "United States", "Ending Stocks", my, rd) / den if den == den and den else np.nan
        win = lambda k: d[(d.contract == k) & (d.date >= f"{n_}-02-01") & (d.date <= f"{n_}-03-31")].set_index("date").close
        K_, N_, Z_ = win(f"CTK{n_}"), win(f"CTN{n_}"), win(f"CTZ{n_}")
        if len(K_) and su_m == su_m:
            fvrows.append((my, su_m, float(K_.mean()), float((K_ - N_).dropna().mean()), float((N_ - Z_).dropna().mean())))
    FV = pd.DataFrame(fvrows, columns=["my", "su", "px", "kn", "nz"]).set_index("my")
    def fitf(df, ycol, kind):
        x = np.log(df.su) if kind == "log" else 1 / df.su
        yv = np.log(df[ycol].values) if kind == "log" else df[ycol].values
        X = np.column_stack([np.ones(len(df)), x]); b = np.linalg.lstsq(X, yv, rcond=None)[0]; e = yv - X @ b
        return {"b": [round(float(v), 4) for v in b], "sd": round(float(np.sqrt(e @ e / (len(yv) - 2))), 3), "n": len(yv),
                "r2": round(float(1 - (e @ e) / ((yv - yv.mean()) @ (yv - yv.mean()))), 2), "kind": kind}
    samples = {"ex_2010": FV.drop(index=["2010/11"], errors="ignore"), "ex_short": FV.drop(index=SHORTAGE, errors="ignore"), "since_2013": FV[FV.index >= "2013/14"], "all": FV}
    fvf = {y_: {m_: fitf(df, y_, "log" if y_ == "px" else "inv") for m_, df in samples.items()} for y_ in ("px", "kn", "nz")}
    def val(f_, su_):
        return float(np.exp(f_["b"][0] + f_["b"][1] * np.log(su_))) if f_["kind"] == "log" else float(f_["b"][0] + f_["b"][1] / su_)
    def inv(f_, v):
        return float(np.exp((np.log(v) - f_["b"][0]) / f_["b"][1])) if f_["kind"] == "log" else float(f_["b"][1] / (v - f_["b"][0]))
    fair = {k: {"su": round(v, 1), **{y_: {m_: round(val(f_, v), 2) for m_, f_ in fvf[y_].items()} for y_ in fvf}}
            for k, v in (("usda", usda_su), ("bear", S["bear"]["su"]), ("base", S["base"]["su"]), ("bull", S["bull"]["su"]))}
    implied = {"px": {m_: round(inv(f_, K0), 1) for m_, f_ in fvf["px"].items()},
               "kn": {m_: round(inv(f_, sp["KN"]), 1) for m_, f_ in fvf["kn"].items() if sp["KN"] > f_["b"][0]},
               "nz": {m_: round(inv(f_, sp["NZ"]), 1) for m_, f_ in fvf["nz"].items() if sp["NZ"] > f_["b"][0]}}
    sus = np.maximum(su, 5)
    fsim = {y_: pct(np.array([val(fvf[y_]["ex_2010"], v) for v in sus[:5000]])) for y_ in fvf}
    fairness = {"fit": {y_: {m_: {k_: f_[k_] for k_ in ("r2", "sd", "n")} for m_, f_ in fvf[y_].items()} for y_ in fvf}, "scen": fair, "implied_su": implied, "sim": fsim,
                "window": "February-March average; USDA March US stocks/use", "min_su_hist": round(float(FV.su.min()), 1), "min_su_my": FV.su.idxmin(),
                "table": [{"my": i, "su": round(v.su, 1), "px": round(v.px, 1), "kn": round(v.kn, 2), "nz": round(v.nz, 2)} for i, v in FV.iterrows()]}
    (ROOT / "data" / "derived" / "ct_fair_eval.json").write_text(json.dumps(fvf, indent=1))
    # simulation on the fair-value model: USDA's March stocks/use drawn from the desk balance-sheet simulation
    # every combination: the balance-sheet draw (crop x exports x India's duty path, already in su) x which history the market follows
    # (fit drawn equally from the four samples) x that fit's residual; no cap on stocks/use (the balance sheet's pipeline minimum is the only limit)
    su_floor = float(samples["ex_short"].su.min())
    sus = np.maximum(su, 1.0)
    fk_ = list(fvf["px"]); pick = rng.integers(0, len(fk_), n)
    def draw(kind):
        b0 = np.array([fvf[kind][fk_[i]]["b"][0] for i in pick]); b1 = np.array([fvf[kind][fk_[i]]["b"][1] for i in pick]); sd_ = np.array([fvf[kind][fk_[i]]["sd"] for i in pick])
        e = rng.normal(0, 1, n) * sd_
        return np.exp(b0 + b1 * np.log(sus) + e) if kind == "px" else b0 + b1 / sus + e
    tgt_day = pd.Timestamp(f"{oy}-03-15")
    term2 = draw("px")
    days2 = max(int(np.busday_count(today.date(), tgt_day.date())), 5)
    st = rng.normal(0, vol / np.sqrt(252), (2000, days2)).cumsum(axis=1); tt2 = np.arange(1, days2 + 1) / days2
    paths2 = K0 * np.exp(np.log(term2[:2000, None] / K0) * tt2 + (st - tt2 * st[:, -1:]))
    knd = draw("kn"); nzd = draw("nz")
    mc.update({"target": tgt_day.strftime("%Y-%m-%d"), "may_feb_mar": pct(term2), "may_high": pct(paths2.max(axis=1)), "may_low": pct(paths2.min(axis=1)),
               "p_above": {lvl: round(100 * float((paths2.max(axis=1) >= lvl).mean()), 0) for lvl in (90, 100, 110, 120, 140)},
               "p_below": {lvl: round(100 * float((paths2.min(axis=1) <= lvl).mean()), 0) for lvl in (80, 78, 75)},
               "may_jul": pct(knd), "jul_dec": pct(nzd), "p_kn_inverse": round(100 * float((knd > 0).mean()), 0),
               "p_nz_above_now": round(100 * float((nzd > sp["NZ"]).mean()), 0), "su_floor": round(su_floor, 1), "p_su_below_floor": round(100 * float((su < su_floor).mean()), 0), "fits": fk_,
               "su_pct": pct(su), "p_su_below_10": round(100 * float((su < 10).mean()), 0),
               "by_fit": {fk_[i]: round(float(np.median(term2[pick == i])), 1) for i in range(len(fk_))}, "p_may_above_now": round(100 * float((term2 > K0).mean()), 0), "days": days2})
    # merchants' NET short vs world exports, and the on-call book
    net_now = 100 * (r.prod_merc_positions_short - r.prod_merc_positions_long) * BALES_PER_LOT / wex
    nets = {}
    for y in range(2010, oy - 1):
        my, t0 = f"{y}/{(y + 1) % 100:02d}", pd.Timestamp(f"{y}-{mmdd}")
        rr = c[c.d <= t0].iloc[-1]; we = lv(w, "World", EX, my, t0)
        if we:
            nets[my] = round(100 * (rr.prod_merc_positions_short - rr.prod_merc_positions_long) * BALES_PER_LOT / we, 1)
    hedge["net_pct"] = round(net_now, 1)
    hedge["net_rank"] = f"{sum(v < net_now for v in nets.values()) + 1} of {len(nets) + 1}"
    hedge["net_hist"] = nets
    bull_eps = [m_ for m_ in nets if m_ in H.index and H.loc[m_, "Kchg"] >= 12]
    hedge["net_bull_avg"] = round(float(np.mean([nets[m_] for m_ in bull_eps])), 1) if bull_eps else None
    hedge["bull_eps"] = [{"my": m_, "net_pct": nets[m_], "may_chg": round(float(H.loc[m_, "Kchg"]), 1)} for m_ in bull_eps]
    oc = None
    for src in ("https://bmr-com.github.io/cotton-on-call/data/intel/brief.json", str(ROOT.parent / "bmr-com" / "cotton-on-call" / "data" / "intel" / "brief.json")):
        try:
            if src.startswith("http"):
                import requests
                oc = requests.get(src, timeout=30).json()
            else:
                oc = json.loads(Path(src).read_text())
            break
        except Exception:
            continue
    oncall = None
    if oc and oc.get("latest"):
        L = oc["latest"]
        oncall = {k: L.get(k) for k in ("oncall_date", "S_old", "P_old", "N_old", "S_old_seas_pct", "P_old_seas_pct", "ls_old", "ls_old_pct", "pmu_net_old", "front", "S_front", "S_2nd", "Sold_pct_trade")}

    # analog seasons: USDA too loose in October
    analog = [{"my": i, "su_oct": round(v.su_oct, 1), "su_fin": round(v.su_fin, 1), "may_chg": round(v.Kchg, 1), "pm_short_pct": round(v.pm_short_pct, 0),
               "jul_dec_june": round(v.NZe, 1)} for i, v in H.iterrows() if v.dsu <= -10 or i in SHORTAGE]
    out = {"built": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "asof": today.strftime("%Y-%m-%d"), "prices": px, "spreads": sp, "usda_su": round(usda_su, 1),
           "scenarios": scenarios, "mc": mc, "hedge": hedge, "fair": fairness, "oncall": oncall, "analog": analog, "vars": VARS, "expiry": exp_day.strftime("%Y-%m-%d"),
           "typical": {"hk_feb": round(float(np.median(ex.HKe)), 2), "kn_apr": round(float(np.median(ex.KNe)), 2),
                       "shortage": {s: {"hk": round(float(H.loc[s, "HKe"]), 1), "kn": round(float(H.loc[s, "KNe"]), 1), "nz": round(float(H.loc[s, "NZe"]), 1)} for s in SHORTAGE if s in H.index}}}
    (ROOT / "data" / "derived" / "ct_price_outlook.json").write_text(json.dumps(out, indent=1, default=float))
    (ROOT / "data" / "derived" / "ct_price_outlook_eval.json").write_text(json.dumps({"fit": fit, "history": H.round(2).reset_index().to_dict("records")}, indent=1, default=float))
    print("May", K0, "| base", scenarios["base"], "| MC expiry", mc["may_expiry"], "high", mc["may_high"], "low", mc["may_low"])
    print("hedge", hedge["pct"], hedge["rank"], "| spreads", sp, "| MC jul/dec", mc["jul_dec"], "hk", mc["mar_may"], "kn", mc["may_jul"])


if __name__ == "__main__":
    main()
