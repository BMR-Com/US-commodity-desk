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
        "ICE cotton futures by contract", "CFTC producer/merchant positions against USDA world exports", "historical volatility of the May contract", "February-March May, May/Jul and Jul/Dec vs USDA March US stocks/use (2007/08 on)", "cotton on-call (CFTC)", "ICE May option settlements (smile, open interest)", "May implied volatility history (2000 on)"]


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

    # Mar/May fair value: January-February average vs USDA's January US stocks/use
    hkrows = []
    for y in range(2007, oy - 1):
        my, n_ = f"{y}/{(y + 1) % 100:02d}", y + 1
        rd = pd.Timestamp(f"{n_}-01-20")
        den = lv(w, "United States", "Domestic Use", my, rd) + lv(w, "United States", EX, my, rd)
        su_j = 100 * lv(w, "United States", "Ending Stocks", my, rd) / den if den == den and den else np.nan
        H_ = d[(d.contract == f"CTH{n_}") & (d.date >= f"{n_}-01-01") & (d.date <= f"{n_}-02-28")].set_index("date").close
        K_ = d[(d.contract == f"CTK{n_}") & (d.date >= f"{n_}-01-01") & (d.date <= f"{n_}-02-28")].set_index("date").close
        hk_ = (H_ - K_).dropna()
        if len(hk_) and su_j == su_j:
            hkrows.append((my, su_j, float(hk_.mean())))
    HKF = pd.DataFrame(hkrows, columns=["my", "su", "hk"]).set_index("my")
    hkfit = {m_: fitf(df_, "hk", "inv") for m_, df_ in {"ex_2010": HKF.drop(index=["2010/11"], errors="ignore"), "ex_short": HKF.drop(index=SHORTAGE, errors="ignore"),
                                                         "since_2013": HKF[HKF.index >= "2013/14"], "all": HKF}.items()}
    for k_ in fair:
        fair[k_]["hk"] = {m_: round(val(f_, fair[k_]["su"]), 2) for m_, f_ in hkfit.items()}
    fairness["fit"]["hk"] = {m_: {k_: f_[k_] for k_ in ("r2", "sd", "n")} for m_, f_ in hkfit.items()}
    fairness["implied_su"]["hk"] = {m_: round(inv(f_, sp["HK"]), 1) for m_, f_ in hkfit.items() if sp["HK"] > f_["b"][0]}
    fairness["hk_table"] = [{"my": i, "su_jan": round(v.su, 1), "hk": round(v.hk, 2)} for i, v in HKF.iterrows()]

    # options: May smile -> market-implied distribution at option expiry, vs the desk simulation; desk fair value of May options
    opt = None
    try:
        from scipy.stats import norm
        src = [ROOT.parent / "bmr-com" / "softs--options-" / "data" / "csv" / "CT_MASTER.csv", "https://raw.githubusercontent.com/BMR-Com/softs--options-/main/data/csv/CT_MASTER.csv"]
        om = None
        for s_ in src:
            try:
                om = pd.read_csv(s_); break
            except Exception:
                continue
        exp_code = f"MAY{oy % 100}"
        om = om[om.expiry == exp_code]
        odt = om.date.max(); ox = om[om.date == odt]
        Fo, To = float(ox.futures_price.iloc[0]), float(ox.time_to_expiry_yrs.iloc[0])
        otm = ox[((ox.call_put == "C") & (ox.strike >= Fo)) | ((ox.call_put == "P") & (ox.strike < Fo))]
        otm = otm[otm.implied_vol_pct > 0].sort_values("strike")
        cc = np.polyfit(np.log(otm.strike / Fo), otm.implied_vol_pct / 100, 2)
        vfun = lambda Kq: np.clip(np.polyval(cc, np.log(Kq / Fo)), 0.08, 1.5)
        def bcall(Kq):
            sg = vfun(Kq) * np.sqrt(To); d1 = (np.log(Fo / Kq) + 0.5 * sg * sg) / sg
            return Fo * norm.cdf(d1) - Kq * norm.cdf(d1 - sg)
        grid = np.linspace(30, 260, 4601); cdf = np.clip(np.maximum.accumulate(1 + np.gradient(bcall(grid), grid[1] - grid[0])), 0, 1)
        bins = [(0, 70), (70, 80), (80, 90), (90, 100), (100, 110), (110, 120), (120, 140), (140, 999)]
        # desk distribution at option expiry: the Feb-Mar simulation diffused to expiry at historical vol
        extra = max(To - (tgt_day - today).days / 365, 0.02)
        desk_T = term2 * np.exp(rng.normal(-0.5 * vol * vol * extra, vol * np.sqrt(extra), len(term2)))
        fpc = fvf["px"]["ex_short"]                       # conservative: no shortage seasons, stocks/use held at the lowest March number they include
        cons = np.exp(fpc["b"][0] + fpc["b"][1] * np.log(np.maximum(su, su_floor)) + rng.normal(0, fpc["sd"], n)) * np.exp(rng.normal(-0.5 * vol * vol * extra, vol * np.sqrt(extra), n))
        rnp = {f"{a}-{b}": round(100 * float(np.interp(b, grid, cdf) - np.interp(a, grid, cdf)), 1) for a, b in bins}
        dkp = {f"{a}-{b}": round(100 * float(((desk_T >= a) & (desk_T < b)).mean()), 1) for a, b in bins}
        dkc = {f"{a}-{b}": round(100 * float(((cons >= a) & (cons < b)).mean()), 1) for a, b in bins}
        def delta_k(dl, cp):
            Ks = np.linspace(40, 220, 1801); sg = vfun(Ks) * np.sqrt(To); d1 = (np.log(Fo / Ks) + 0.5 * sg * sg) / sg
            de = norm.cdf(d1) if cp == "C" else norm.cdf(d1) - 1
            return float(Ks[np.argmin(abs(de - dl))])
        k25c, k25p = delta_k(0.25, "C"), delta_k(-0.25, "P")
        rows_o = []
        for _, rr in ox[ox.strike.isin([70, 75, 78, 80, 85, 90, 95, 100, 105, 110, 115, 120, 130, 150])].iterrows():
            fairv = float(np.mean(np.maximum(desk_T - rr.strike, 0) if rr.call_put == "C" else np.maximum(rr.strike - desk_T, 0)))
            fairc = float(np.mean(np.maximum(cons - rr.strike, 0) if rr.call_put == "C" else np.maximum(rr.strike - cons, 0)))
            if (rr.call_put == "C" and rr.strike >= Fo - 5) or (rr.call_put == "P" and rr.strike <= Fo + 5):
                rows_o.append({"k": rr.strike, "cp": rr.call_put, "mkt": round(float(rr.settle_price), 2), "iv": round(float(rr.implied_vol_pct), 1), "desk": round(fairv, 2), "desk_cons": round(fairc, 2),
                               "oi": int(rr.open_interest), "ratio": round(fairv / rr.settle_price, 2) if rr.settle_price > 0 else None})
        # history of May implied vol at this time of year (Bloomberg generic CTMAY1)
        ivh = None
        for s_ in [ROOT.parent / "bmr-com" / "cotton-price" / "data" / "cotton_raw.csv", "https://raw.githubusercontent.com/BMR-Com/cotton-price/main/data/cotton_raw.csv"]:
            try:
                cr = pd.read_csv(s_, na_values=["#N/A N/A"]); break
            except Exception:
                cr = None
        if cr is not None:
            cr["Dates"] = pd.to_datetime(cr.Dates, format="%m/%d/%y"); col = "CTMAY1 Comdty HIST_CALL_IMP_VOL"
            v_ = []
            for yy in range(2000, oy - 1):
                z = cr[(cr.Dates >= f"{yy}-10-20") & (cr.Dates <= f"{yy}-10-31")][col].dropna()
                if len(z):
                    v_.append((yy, float(z.mean())))
            vals = [b for _, b in v_]
            atm_now = float(vfun(Fo)) * 100
            ivh = {"years": len(vals), "median": round(float(np.median(vals)), 1), "pct": round(100 * float(np.mean(np.array(vals) < atm_now)), 0),
                   "hist": {str(a): round(b, 1) for a, b in v_}}
        opt = {"date": odt, "F": Fo, "T": round(To, 3), "expiry": exp_code, "atm": round(100 * float(vfun(Fo)), 1), "rr25": round(100 * float(vfun(k25c) - vfun(k25p)), 2),
               "k25c": round(k25c, 1), "k25p": round(k25p, 1), "iv25c": round(100 * float(vfun(k25c)), 1), "iv25p": round(100 * float(vfun(k25p)), 1),
               "rn": rnp, "desk": dkp, "desk_cons": dkc, "p_above_100_cons": round(100 * float((cons >= 100).mean()), 1), "p_below_80_cons": round(100 * float((cons < 80).mean()), 1), "p_above_100_rn": round(100 - 100 * float(np.interp(100, grid, cdf)), 1), "p_above_100_desk": round(100 * float((desk_T >= 100).mean()), 1),
               "p_below_80_rn": round(100 * float(np.interp(80, grid, cdf)), 1), "p_below_80_desk": round(100 * float((desk_T < 80).mean()), 1),
               "options": sorted(rows_o, key=lambda r: (r["cp"], r["k"])), "iv_hist": ivh,
               "top_oi": [{"k": float(r.strike), "cp": r.call_put, "oi": int(r.open_interest)} for _, r in ox.sort_values("open_interest", ascending=False).head(6).iterrows()]}
    except Exception as e:
        print("options skipped:", repr(e)[:160])

    # downside: who sells on the way down? Mills' net unfixed on-call book at end-October vs May's worst drawdown to mid-March
    downside = None
    try:
        ocsrc = [ROOT.parent / "bmr-com" / "cotton-on-call" / "data" / "cotton_oncall.csv", "https://raw.githubusercontent.com/BMR-Com/cotton-on-call/main/data/cotton_oncall.csv"]
        ocd = None
        for s_ in ocsrc:
            try:
                ocd = pd.read_csv(s_); break
            except Exception:
                continue
        ocd["d"] = pd.to_datetime(ocd["Report Date"])
        rows_d = []
        for y in range(2010, oy - 1):
            t0 = pd.Timestamp(f"{y}-{mmdd}"); n_ = y + 1
            o = ocd[(ocd.d <= t0) & (ocd.d > t0 - pd.Timedelta(days=10)) & (ocd["Old/New"] == "old")]
            o = o[o.d == o.d.max()]
            if not len(o):
                continue
            kk = d[(d.contract == f"CTK{n_}") & (d.date >= t0) & (d.date <= f"{n_}-03-15")].sort_values("date")
            if len(kk):
                rows_d.append({"my": f"{y}/{(y + 1) % 100:02d}", "net": int(o["Unfixed Call Sales"].sum() - o["Unfixed Call Purchases"].sum()),
                               "dd": round(100 * (float(kk.close.min()) / float(kk.close.iloc[0]) - 1), 1)})
        net_now = int(oncall["N_old"]) if oncall else None
        hi = [r for r in rows_d if r["net"] >= 40000]; lo = [r for r in rows_d if r["net"] < 40000]
        downside = {"net_now": net_now, "rows": rows_d, "hi_mean": round(float(np.mean([r["dd"] for r in hi])), 1) if hi else None,
                    "hi_worst": min(r["dd"] for r in hi) if hi else None, "lo_mean": round(float(np.mean([r["dd"] for r in lo])), 1) if lo else None,
                    "hi_years": [r["my"] for r in hi], "loan_rate": 55.0, "loan_note": "2026-crop upland loan rate 55.00 c/lb (One Big Beautiful Bill Act; 52.00 for 2025)",
                    "mm_net_lots": int(r.m_money_positions_long_all - r.m_money_positions_short_all)}
        if downside["hi_mean"] is not None:
            downside["typical_low"] = round(K0 * (1 + downside["hi_mean"] / 100), 1); downside["worst_low"] = round(K0 * (1 + downside["hi_worst"] / 100), 1)
    except Exception as e:
        print("downside skipped:", repr(e)[:120])

    # analog seasons: USDA too loose in October
    analog = [{"my": i, "su_oct": round(v.su_oct, 1), "su_fin": round(v.su_fin, 1), "may_chg": round(v.Kchg, 1), "pm_short_pct": round(v.pm_short_pct, 0),
               "jul_dec_june": round(v.NZe, 1)} for i, v in H.iterrows() if v.dsu <= -10 or i in SHORTAGE]
    out = {"built": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "asof": today.strftime("%Y-%m-%d"), "prices": px, "spreads": sp, "usda_su": round(usda_su, 1),
           "scenarios": scenarios, "mc": mc, "hedge": hedge, "fair": fairness, "oncall": oncall, "options": opt, "downside": downside, "analog": analog, "vars": VARS, "expiry": exp_day.strftime("%Y-%m-%d"),
           "typical": {"hk_feb": round(float(np.median(ex.HKe)), 2), "kn_apr": round(float(np.median(ex.KNe)), 2),
                       "shortage": {s: {"hk": round(float(H.loc[s, "HKe"]), 1), "kn": round(float(H.loc[s, "KNe"]), 1), "nz": round(float(H.loc[s, "NZe"]), 1)} for s in SHORTAGE if s in H.index}}}
    (ROOT / "data" / "derived" / "ct_price_outlook.json").write_text(json.dumps(out, indent=1, default=float))
    (ROOT / "data" / "derived" / "ct_price_outlook_eval.json").write_text(json.dumps({"fit": fit, "history": H.round(2).reset_index().to_dict("records")}, indent=1, default=float))
    print("May", K0, "| base", scenarios["base"], "| MC expiry", mc["may_expiry"], "high", mc["may_high"], "low", mc["may_low"])
    print("hedge", hedge["pct"], hedge["rank"], "| spreads", sp, "| MC jul/dec", mc["jul_dec"], "hk", mc["mar_may"], "kn", mc["may_jul"])


if __name__ == "__main__":
    main()
