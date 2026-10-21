#!/usr/bin/env python3
"""Option vol desk for CME ag options, from the daily settlement files in data/cme/options/<date>/<SYM>.csv.gz.

Per market, as in the softs options desk:
- per expiry: underlying futures, days to expiry, ATM implied vol (smile interpolated at the futures price),
  25-delta call/put vols, risk reversal and butterfly, expected move to expiry, vol change on the day and on
  the week, realized vol of the underlying (data/vol/vol.json) and the implied-minus-realized premium,
  call/put open interest and its weekly change, call and put walls, max pain and the strike with the most gamma;
- term structure today and a week ago; smiles for the two nearest expiries today and a week ago;
- open interest, volume and gamma by strike for the nearest expiries; put/call ratios;
- implied-vol history (data/cme/options/iv_history.csv, one row per date/expiry, built up daily) with
  percentiles once a year of history exists; a short written read.
Writes data/options/<SYM>.json and data/options/index.json.
"""
import json, math
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
SRC = D / "cme" / "options"
OUT = D / "options"
NAMES = {"ZC": "Corn", "ZS": "Soybeans", "ZM": "Soybean meal", "ZL": "Soybean oil", "ZW": "Chicago wheat", "KE": "KC HRW wheat",
         "LE": "Live cattle", "GF": "Feeder cattle", "HE": "Lean hogs", "DC": "Class III milk", "GDK": "Class IV milk",
         "CSC": "Cheese", "CB": "Butter", "GNF": "Nonfat dry milk", "DY": "Dry whey",
         "NG": "Natural gas", "CL": "WTI crude", "HO": "ULSD (heating oil)", "RB": "RBOB gasoline"}


def smile(g):
    F = float(g.F.iloc[0])
    c = g[(g.cp == "C") & (g.strike >= F)]
    p = g[(g.cp == "P") & (g.strike < F)]
    s = pd.concat([p, c]).dropna(subset=["iv"])
    s = s[(s.iv > 1) & (s.iv < 200)].sort_values("strike")
    return F, s


def atm_iv(g):
    F, s = smile(g)
    if len(s) < 2 or not (s.strike.min() <= F <= s.strike.max()):
        return None
    return float(np.interp(F, s.strike, s.iv))


def delta_iv(g, side, target=0.25):
    x = g[g.cp == side].dropna(subset=["delta", "iv"]).copy()
    x["ad"] = x.delta.abs()
    x = x[(x.ad > 0.03) & (x.ad < 0.97) & (x.iv > 1)].sort_values("ad")
    if len(x) < 2 or not (x.ad.min() <= target <= x.ad.max()):
        return None
    return float(np.interp(target, x.ad, x.iv))


def max_pain(g):
    c = g[g.cp == "C"].groupby("strike").oi.sum()
    p = g[g.cp == "P"].groupby("strike").oi.sum()
    best = bk = None
    for K in sorted(g.strike.unique()):
        pay = sum(max(0, K - k) * oi for k, oi in c.items()) + sum(max(0, k - K) * oi for k, oi in p.items())
        if best is None or pay < best:
            best, bk = pay, K
    return float(bk) if bk is not None else None


def r1(v, n=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), n)


def load(sym):
    fr = []
    for p in sorted(SRC.glob(f"2*/{sym}.csv.gz"))[-12:]:
        fr.append(pd.read_csv(p))
    if not fr:
        return None
    d = pd.concat(fr)
    d["date"] = pd.to_datetime(d.date)
    return d


def main():
    vol = json.loads((D / "vol/vol.json").read_text()).get("markets", {}) if (D / "vol/vol.json").exists() else {}
    hp = SRC / "iv_history.csv"
    hist = pd.read_csv(hp, parse_dates=["date"]) if hp.exists() else pd.DataFrame()
    new_hist, index = [], {}
    for sym, name in NAMES.items():
        d = load(sym)
        if d is None:
            continue
        dates = sorted(d.date.unique())
        last = dates[-1]
        prev = dates[-2] if len(dates) > 1 else None
        wk = [x for x in dates if x <= last - pd.Timedelta(days=6)]
        wk = wk[-1] if wk else (dates[0] if dates[0] != last else None)
        day = d[d.date == last]
        rvmap = {c["label"].upper(): c for c in vol.get(sym, {}).get("contracts", [])}
        rows = []
        for con, g in sorted(day.groupby("contract"), key=lambda x: x[1].dte.iloc[0]):
            dte = int(g.dte.iloc[0])
            if dte < 2:
                continue
            F, T = float(g.F.iloc[0]), float(g["T"].iloc[0])
            a = atm_iv(g)
            c25, p25 = delta_iv(g, "C"), delta_iv(g, "P")
            def at(dt):
                if dt is None:
                    return None, None
                gg = d[(d.date == dt) & (d.contract == con)]
                return (atm_iv(gg), gg) if len(gg) else (None, None)
            a_d, g_d = at(prev)
            a_w, g_w = at(wk)
            rr = c25 - p25 if c25 is not None and p25 is not None else None
            rr_w = None
            if g_w is not None:
                cw, pw = delta_iv(g_w, "C"), delta_iv(g_w, "P")
                rr_w = cw - pw if cw is not None and pw is not None else None
            und = g.underlying.iloc[0]
            rv = (rvmap.get(und.upper()) or {}).get("hv20")
            cOI, pOI = int(g[g.cp == "C"].oi.sum()), int(g[g.cp == "P"].oi.sum())
            ww = None if g_w is None else (int(g_w[g_w.cp == "C"].oi.sum()), int(g_w[g_w.cp == "P"].oi.sum()))
            above, below = g[(g.cp == "C") & (g.strike >= F)], g[(g.cp == "P") & (g.strike <= F)]
            gam = g.assign(gx=g.gamma.fillna(0) * g.oi).groupby("strike").gx.sum()
            row = {"contract": con, "label": g.label.iloc[0], "underlying": und, "expiry": g.expiry.iloc[0], "dte": dte, "F": F,
                   "atm": r1(a), "d_atm_1d": r1(a - a_d) if a is not None and a_d is not None else None,
                   "d_atm_1w": r1(a - a_w) if a is not None and a_w is not None else None,
                   "c25": r1(c25), "p25": r1(p25), "rr25": r1(rr), "d_rr_1w": r1(rr - rr_w) if rr is not None and rr_w is not None else None,
                   "bf25": r1((c25 + p25) / 2 - a) if None not in (c25, p25, a) else None,
                   "move": r1(F * a / 100 * math.sqrt(T), 3) if a else None, "move_pct": r1(a * math.sqrt(T), 2) if a else None,
                   "rv20": rv, "vrp": r1(a - rv) if a is not None and rv is not None else None,
                   "cOI": cOI, "pOI": pOI, "d_cOI_1w": (cOI - ww[0]) if ww else None, "d_pOI_1w": (pOI - ww[1]) if ww else None,
                   "cVol": int(g[g.cp == "C"].volume.sum()), "pVol": int(g[g.cp == "P"].volume.sum()),
                   "pc_oi": r1(pOI / cOI) if cOI else None,
                   "call_wall": float(above.loc[above.oi.idxmax(), "strike"]) if len(above) and above.oi.max() > 0 else None,
                   "put_wall": float(below.loc[below.oi.idxmax(), "strike"]) if len(below) and below.oi.max() > 0 else None,
                   "smile": [[float(k), round(float(v), 2)] for k, v in zip(*(lambda s_: (s_.strike, s_.iv))(smile(g)[1][lambda x: (x.strike > F * 0.6) & (x.strike < F * 1.5)]))],
                   "max_pain": max_pain(g) if cOI + pOI > 0 else None, "gamma_peak": float(gam.idxmax()) if len(gam) and gam.max() > 0 else None}
            rows.append(row)
            new_hist.append({"date": last.date().isoformat(), "sym": sym, "contract": con, "underlying": und, "dte": dte, "F": F, "atm": row["atm"],
                             "rr25": row["rr25"], "bf25": row["bf25"], "cOI": cOI, "pOI": pOI})
            for dt in dates[:-1]:   # backfill history rows for earlier dates in the window
                gg = d[(d.date == dt) & (d.contract == con)]
                if len(gg):
                    c_, p_ = delta_iv(gg, "C"), delta_iv(gg, "P")
                    new_hist.append({"date": dt.date().isoformat(), "sym": sym, "contract": con, "underlying": und, "dte": int(gg.dte.iloc[0]),
                                     "F": float(gg.F.iloc[0]), "atm": r1(atm_iv(gg)), "rr25": r1(c_ - p_) if c_ is not None and p_ is not None else None,
                                     "bf25": None, "cOI": int(gg[gg.cp == "C"].oi.sum()), "pOI": int(gg[gg.cp == "P"].oi.sum())})
        # dairy options settle on a monthly average that is mostly known in the last weeks, so look past them
        min_dte = 25 if sym in ("DC", "GDK", "CSC", "CB", "GNF", "DY") else 7
        liquid = [r for r in rows if r["cOI"] + r["pOI"] >= 200 and r["atm"] is not None and r["dte"] >= min_dte] or [r for r in rows if r["atm"] is not None]
        if not liquid:
            continue
        front = liquid[0]

        def smile_pts(dt, con):
            gg = d[(d.date == dt) & (d.contract == con)]
            if gg.empty:
                return []
            F_, s = smile(gg)
            s = s[(s.strike > F_ * 0.75) & (s.strike < F_ * 1.3)]
            return [[float(k), round(float(v), 2)] for k, v in zip(s.strike, s.iv)]
        def term(dt):
            out = []
            for con, gg in d[d.date == dt].groupby("contract"):
                if int(gg.dte.iloc[0]) < 5:
                    continue
                a = atm_iv(gg)
                if a is not None:
                    out.append({"contract": con, "label": gg.label.iloc[0], "dte": int(gg.dte.iloc[0]), "atm": round(a, 2)})
            return sorted(out, key=lambda x: x["dte"])
        def strike_map(con):
            g = day[day.contract == con]
            F = float(g.F.iloc[0])
            out = []
            for K, kk in g.groupby("strike"):
                if not (F * 0.75 < K < F * 1.3):
                    continue
                c, p = kk[kk.cp == "C"], kk[kk.cp == "P"]
                out.append({"K": float(K), "cOI": int(c.oi.sum()), "pOI": int(p.oi.sum()), "cVol": int(c.volume.sum()), "pVol": int(p.volume.sum()),
                            "gam": round(float((kk.gamma.fillna(0) * kk.oi).sum()), 2)})
            return {"contract": con, "label": g.label.iloc[0], "F": F, "rows": out}
        # read
        r = front
        txt = [f"{name} {r['label']} options (on {r['underlying']} futures {r['F']:g}, {r['dte']} days): at-the-money implied vol {r['atm']:.1f}%"
               + (f", {r['d_atm_1w']:+.1f} pts on the week" if r["d_atm_1w"] is not None else "") + "."]
        if r["rv20"]:
            txt.append(f"20-day realized vol is {r['rv20']:.1f}%, so options price a {'premium' if r['vrp'] > 0 else 'discount'} of {abs(r['vrp']):.1f} pts to recent movement"
                       + (" (rich: sellers' market unless a report is due)." if r["vrp"] > 4 else " (cheap: buyers' market)." if r["vrp"] < -2 else "."))
        if r["move"]:
            txt.append(f"Expected move to expiry ±{r['move']:g} ({r['move_pct']:.1f}%), range {r['F'] - r['move']:g}–{r['F'] + r['move']:g}.")
        if r["rr25"] is not None:
            txt.append(f"25-delta risk reversal {r['rr25']:+.1f} pts: {'calls bid over puts (upside fear)' if r['rr25'] > 0.5 else 'puts bid over calls (downside protection)' if r['rr25'] < -0.5 else 'balanced skew'}"
                       + (f", {r['d_rr_1w']:+.1f} on the week." if r["d_rr_1w"] is not None else "."))
        txt.append(f"Open interest: calls {r['cOI']:,}, puts {r['pOI']:,} (put/call {r['pc_oi'] if r['pc_oi'] is not None else '–'}); call wall {r['call_wall']}, put wall {r['put_wall']}, max pain {r['max_pain']}, most gamma at {r['gamma_peak']}.")
        tlist = term(last)
        if len(tlist) >= 2:
            sl = tlist[-1]["atm"] - tlist[0]["atm"]
            txt.append(f"Term structure {'upward sloping' if sl > 1 else 'inverted (front month richer: event or delivery risk)' if sl < -1 else 'flat'}: {tlist[0]['label']} {tlist[0]['atm']:.1f}% to {tlist[-1]['label']} {tlist[-1]['atm']:.1f}%.")
        out = {"sym": sym, "name": name, "date": last.date().isoformat(), "prev": prev.date().isoformat() if prev is not None else None,
               "week_ago": wk.date().isoformat() if wk is not None else None, "expiries": rows, "front": front["contract"],
               "term": tlist, "term_week_ago": term(wk) if wk is not None else [],
               "smiles": [{"contract": c["contract"], "label": c["label"], "F": c["F"], "now": smile_pts(last, c["contract"]),
                           "week_ago": smile_pts(wk, c["contract"]) if wk is not None else []} for c in liquid[:2]],
               "strike_maps": [strike_map(c["contract"]) for c in liquid[:2]], "read": " ".join(txt),
               "pc_oi_all": r1(day[day.cp == "P"].oi.sum() / max(day[day.cp == "C"].oi.sum(), 1)),
               "pc_vol_all": r1(day[day.cp == "P"].volume.sum() / max(day[day.cp == "C"].volume.sum(), 1)),
               "note": "Implied vols backed out of CME settlement prices with Black-76 (European approximation); ATM vol is the out-of-the-money smile interpolated at the futures price."}
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{sym}.json").write_text(json.dumps(out, default=lambda o: None))
        index[sym] = {"name": name, "date": out["date"], "front": front["label"], "atm": front["atm"], "rv20": front["rv20"], "vrp": front["vrp"], "rr25": front["rr25"]}
        print(sym, out["date"], front["label"], "ATM", front["atm"], "RV", front["rv20"], "RR", front["rr25"], "| expiries", len(rows))
    if new_hist:
        h = pd.concat([hist, pd.DataFrame(new_hist).assign(date=lambda x: pd.to_datetime(x.date))]) if len(hist) else pd.DataFrame(new_hist).assign(date=lambda x: pd.to_datetime(x.date))
        h = h.drop_duplicates(["date", "sym", "contract"], keep="last").sort_values(["sym", "date", "dte"])
        h.to_csv(hp, index=False, date_format="%Y-%m-%d")
        # IV history per market: front liquid expiry each day, with percentiles once enough history exists
        for sym in index:
            hs = h[(h.sym == sym) & h.atm.notna() & (h.dte >= 5)]
            front = hs.sort_values("dte").groupby("date").first()
            js = json.loads((OUT / f"{sym}.json").read_text())
            js["iv_hist"] = [[dt.strftime("%Y-%m-%d"), float(v), r] for dt, v, r in zip(front.index, front.atm, front.contract)]
            a = js["expiries"][0]["atm"] if js["expiries"] else None
            s1 = front.atm[front.index > front.index.max() - pd.Timedelta(days=365)]
            js["iv_pct1y"] = round(float((s1 < a).mean() * 100)) if a is not None and len(s1) >= 120 else None
            js["iv_hist_days"] = int(len(front))
            (OUT / f"{sym}.json").write_text(json.dumps(js, default=lambda o: None))
    (OUT / "index.json").write_text(json.dumps({"generated": date.today().isoformat(), "markets": index}))


if __name__ == "__main__":
    main()
