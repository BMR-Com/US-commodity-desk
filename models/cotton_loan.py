"""Cotton in the CCC marketing loan -> data/cotton_loan/loan.json

Inputs (pipelines/cotton_loan.py): PSL-61R monthly and weekly (state x crop year: put under loan, repaid, delivered,
outstanding), PSL-43R monthly (national: disbursement month x maturity month, Form A / Form G), weekly state snapshots
(loans with Form G, outstanding by maturity month). Year-on-year comparisons use the monthly reports (the only ones
FSA keeps for a year); weekly data are captured from now on.
Crop year = the year cotton is harvested; the marketing year starts Aug 1. Loans mature 9 months after disbursement.
"""
import glob, io, json, math, re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "cotton_loan" / "raw"
OUT = ROOT / "data" / "cotton_loan" / "loan.json"
COLS = ["com", "cy", "unit", "st", "put_f", "put_w", "put", "rep_f", "rep_w", "del_f", "del_w", "out_f", "out_w", "out"]


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return None if not math.isfinite(o) else round(o, 3)
    if hasattr(o, "item"):
        return clean(o.item())
    return o


def p61(f):
    rows = [l for l in open(f, encoding="latin-1").read().splitlines() if l.startswith("COTTON")]
    if not rows:
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(io.StringIO("\n".join(rows)), header=None, thousands=",")
    d.columns = COLS
    d = d.fillna(0)
    d["rep"] = d.rep_f + d.rep_w
    d["dlv"] = d.del_f + d.del_w
    return d


def p43(f):
    L = open(f, encoding="latin-1").read().splitlines()
    rows = [l for l in L if re.match(r"^\d{4},[A-Z][a-z]{2} \d{4}", l)]
    d = pd.read_csv(io.StringIO("\n".join(rows)), header=None, thousands=",")
    d = d.iloc[:, :15]
    d.columns = ["cy", "disb", "mat", "A_made", "A_rep", "A_forf", "A_out", "G_made", "G_rep", "G_forf", "G_out", "made", "rep", "forf", "out"]
    return d.fillna(0)


def crop_year(d):
    return d.year if d.month >= 8 else d.year - 1


def main():
    res = {"generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "notes": []}
    # ── monthly series (PSL-61R) ──
    M = {}
    for f in sorted(glob.glob(str(RAW / "psl61r_monthly" / "*.csv"))):
        M[date.fromisoformat(Path(f).stem)] = p61(f)
    W = {}
    for f in sorted(glob.glob(str(RAW / "psl61r_weekly" / "*.csv"))):
        W[date.fromisoformat(Path(f).stem)] = p61(f)
    series = []
    for d, df in sorted({**M, **W}.items()):
        cy = crop_year(d)
        for com in ("COTTON-UP", "COTTON-ELS"):
            x = df[df.com == com].groupby("cy")[["put", "rep", "dlv", "out"]].sum()
            cur = x.loc[cy] if cy in x.index else pd.Series({"put": 0, "rep": 0, "dlv": 0, "out": 0})
            old = x.loc[cy - 1] if (cy - 1) in x.index else pd.Series({"put": 0, "rep": 0, "dlv": 0, "out": 0})
            series.append({"date": d.isoformat(), "kind": "weekly" if d in W and d not in M else "monthly", "com": com, "crop_year": cy,
                           "put": float(cur.put), "repaid": float(cur.rep), "delivered": float(cur.dlv), "out": float(cur.out),
                           "prior_crop_out": float(old.out), "prior_crop_put": float(old.put)})
    res["series"] = series
    # year-on-year at the latest monthly report
    up = [s for s in series if s["com"] == "COTTON-UP" and s["kind"] == "monthly"]
    yoy = None
    if up:
        last = up[-1]
        ld = date.fromisoformat(last["date"])
        prev = [s for s in up if abs((date.fromisoformat(s["date"]) - ld).days - (-365)) <= 5]
        if prev:
            yoy = {"now": last, "year_ago": prev[0]}
    res["yoy"] = yoy
    # ── state table: latest weekly (or monthly) vs the same month last year ──
    latest_d = max(list(M) + list(W))
    L = (W.get(latest_d) if latest_d in W else M[latest_d])
    cy = crop_year(latest_d)
    lm = max(M)
    lmy = [d for d in M if abs((d - lm).days + 365) <= 5]
    st = []
    cur = L[(L.com == "COTTON-UP") & (L.cy == cy)].set_index("st")
    m_now = M[lm][(M[lm].com == "COTTON-UP") & (M[lm].cy == crop_year(lm))].set_index("st")
    m_ly = M[lmy[0]][(M[lmy[0]].com == "COTTON-UP") & (M[lmy[0]].cy == crop_year(lmy[0]))].set_index("st") if lmy else None
    oldc = L[(L.com == "COTTON-UP") & (L.cy == cy - 1)].set_index("st")
    for s in sorted(set(cur.index) | set(oldc.index) | set(m_now.index) | (set(m_ly.index) if m_ly is not None else set())):
        g = lambda df, c: float(df.loc[s, c]) if df is not None and s in df.index else 0.0
        st.append({"st": s, "put": g(cur, "put"), "repaid": g(cur, "rep"), "out": g(cur, "out"),
                   "m_put": g(m_now, "put"), "m_put_ly": g(m_ly, "put") if m_ly is not None else None,
                   "old_out": g(oldc, "out"), "old_put": g(oldc, "put"), "old_repaid": g(oldc, "rep"), "old_dlv": g(oldc, "dlv")})
    st.sort(key=lambda r: -(r["put"] + r["old_out"]))
    res["state"] = {"as_of": latest_d.isoformat(), "crop_year": cy, "monthly_as_of": lm.isoformat(), "monthly_year_ago": lmy[0].isoformat() if lmy else None, "rows": st}
    # ── maturity (PSL-43R) now vs a year ago ──
    P = {date.fromisoformat(Path(f).stem): p43(f) for f in sorted(glob.glob(str(RAW / "psl43r" / "*.csv")))}
    mat = None
    if P:
        pl = max(P)
        pa = [d for d in P if abs((d - pl).days + 365) <= 5]

        def mtab(df, ref):
            o = df[df.out > 0].copy()
            return [{"crop_year": int(r.cy), "disbursed": r.disb, "matures": r.mat, "out": float(r.out), "form_a": float(r.A_out), "form_g": float(r.G_out)} for _, r in o.iterrows()]

        def summ(df, ref):
            cyr = crop_year(ref)
            t = {}
            for c in (cyr, cyr - 1):
                x = df[df.cy == c]
                t[str(c)] = {k: float(x[k].sum()) for k in ["made", "rep", "forf", "out", "A_made", "G_made", "A_out", "G_out"]}
            return t
        mat = {"as_of": pl.isoformat(), "rows": mtab(P[pl], pl), "summary": summ(P[pl], pl)}
        if pa:
            mat["year_ago"] = {"as_of": pa[0].isoformat(), "rows": mtab(P[pa[0]], pa[0]), "summary": summ(P[pa[0]], pa[0])}
    res["maturity"] = mat
    # ── weekly state snapshot: outstanding by maturity month and state ──
    snaps = sorted(glob.glob(str(RAW / "state" / "*")))
    if snaps:
        f = Path(snaps[-1]) / "upland_maturity.csv"
        if f.exists():
            rows = [l for l in open(f, encoding="latin-1").read().splitlines() if re.match(r"^[A-Z]{2},COTTON", l)]
            d = pd.read_csv(io.StringIO("\n".join(rows)), header=None, thousands=",")
            d = d.iloc[:, :8]
            d.columns = ["st", "com", "unit", "cy", "matures", "count", "qty", "usd"]
            res["maturity_state"] = {"week": Path(snaps[-1]).name, "taken": (Path(snaps[-1]) / "taken.txt").read_text().strip(),
                                     "rows": d[["st", "cy", "matures", "qty", "usd"]].to_dict("records")}
    # ── brief ──
    B = []
    w_up = [s for s in series if s["com"] == "COTTON-UP"]
    if w_up:
        n = w_up[-1]
        B.append({"h": "In the loan now", "t": f"As of {n['date']}, {n['put']/1e3:,.0f}k bales of {n['crop_year']} upland have gone into the loan, {n['repaid']/1e3:,.0f}k already repaid, "
                                                 f"{n['out']/1e3:,.0f}k outstanding; {n['prior_crop_out']/1e3:,.0f}k bales of the {n['crop_year']-1} crop are still in the loan (of {n['prior_crop_put']/1e6:.2f}m that entered)."})
        wk = [s for s in w_up if s["kind"] == "weekly"]
        if len(wk) >= 2:
            a, b = wk[-2], wk[-1]
            B.append({"h": "Last week", "t": f"{a['date']} to {b['date']}: {(b['put']-a['put'])/1e3:+,.0f}k bales entered, {(b['repaid']-a['repaid'])/1e3:+,.0f}k repaid; "
                                              f"old-crop outstanding {(b['prior_crop_out']-a['prior_crop_out'])/1e3:+,.0f}k."})
    if yoy:
        a, b = yoy["year_ago"], yoy["now"]
        pct = (b["put"] / a["put"] - 1) * 100 if a["put"] else None
        B.append({"h": "Year on year (monthly report)", "t": f"At {b['date']}, {b['crop_year']} crop loans total {b['put']/1e3:,.0f}k bales vs {a['put']/1e3:,.0f}k of the {a['crop_year']} crop at {a['date']}"
                  + (f" ({pct:+.0f}%)" if pct is not None else "") + f"; old crop still in the loan {b['prior_crop_out']/1e3:,.0f}k vs {a['prior_crop_out']/1e3:,.0f}k a year ago."})
    if mat:
        s = mat["summary"]
        oc = s.get(str(crop_year(date.fromisoformat(mat["as_of"])) - 1), {})
        by_m = {}
        for r in mat["rows"]:
            if r["crop_year"] == crop_year(date.fromisoformat(mat["as_of"])) - 1:
                by_m[r["matures"]] = by_m.get(r["matures"], 0) + r["out"]
        if by_m:
            B.append({"h": "Old crop maturing", "t": f"PSL-43R {mat['as_of']} (upland and ELS): {oc.get('out', 0)/1e3:,.0f}k bales of old-crop loans outstanding, maturing "
                      + ", ".join(f"{k} {v/1e3:,.1f}k" for k, v in by_m.items()) + ". Loans mature 9 months after disbursement; with the AWP above the loan rate they are repaid, not forfeited, so maturing loans are cotton that must be sold or re-financed."})
        if oc.get("made"):
            B.append({"h": "Form A vs Form G", "t": f"Of the {oc['made']/1e6:.2f}m bales of old-crop loans, {oc['G_made']/oc['made']*100:.0f}% were Form G (made through loan servicing agents, mostly merchants and cooperatives) and {oc['A_made']/oc['made']*100:.0f}% Form A (made at county offices); forfeited {oc.get('forf', 0):,.0f}."})
    res["brief"] = B
    OUT.write_text(json.dumps(clean(res), separators=(",", ":")))
    print("wrote", OUT)
    for b in B:
        print("-", b["h"], ":", b["t"])


if __name__ == "__main__":
    main()
