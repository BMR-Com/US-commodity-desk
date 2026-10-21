#!/usr/bin/env python3
"""Report-day reaction study: how far each market has moved on USDA report days since 2006, versus an ordinary day,
and for WASDE days how the move lines up with USDA's revision to US ending stocks.

Release dates come from the report text as released (ESMIS first prints: "Released <Month D, YYYY>"); weekly
export sales from the FAS week-ending dates (+7 days). Reports released after the livestock close (Hogs and Pigs,
Cattle on Feed) are measured on the next trading day. Returns are the front contract's, rolled 10 days before
last trade, so contract rolls never show up as moves.
Writes data/grains/derived/report_reaction.json.
"""
import json, math, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
import grains_rv as RV  # noqa: E402

ES = ROOT / "data" / "esmis"
OUT = ROOT / "data" / "grains" / "derived" / "report_reaction.json"
REPORTS = {  # type: (esmis slug, after the close?)
    "WASDE / Crop Production": ("crop-production", False),
    "Grain Stocks": ("grain-stocks", False),
    "Acreage": ("acreage", False),
    "Prospective Plantings": ("prospective-plantings", False),
    "Hogs and Pigs": ("hogs-and-pigs", True),
    "Cattle on Feed": ("cattle-feed", True),
}
BY_SYM = {"ZC": ["WASDE / Crop Production", "Grain Stocks", "Acreage", "Prospective Plantings", "Export sales"],
          "ZS": ["WASDE / Crop Production", "Grain Stocks", "Acreage", "Prospective Plantings", "Export sales"],
          "ZM": ["WASDE / Crop Production", "Grain Stocks", "Export sales"], "ZL": ["WASDE / Crop Production", "Grain Stocks", "Export sales"],
          "ZW": ["WASDE / Crop Production", "Grain Stocks", "Acreage", "Export sales"], "KE": ["WASDE / Crop Production", "Grain Stocks", "Acreage", "Export sales"],
          "CT": ["WASDE / Crop Production", "Acreage", "Prospective Plantings", "Export sales"],
          "HE": ["Hogs and Pigs", "WASDE / Crop Production"], "LE": ["Cattle on Feed", "WASDE / Crop Production"], "GF": ["Cattle on Feed", "WASDE / Crop Production"]}
WASDE_KEY = {"ZC": ("Corn.json", "corn"), "ZS": ("Oilseed,_Soybean.json", "soybeans"), "ZW": ("Wheat.json", "wheat"), "KE": ("Wheat.json", "wheat"),
             "CT": ("Cotton.json", "cotton")}
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}


def release_dates(slug):
    out = set()
    for f in (ES / slug).glob("*.txt"):
        try:
            t = f.read_text(errors="ignore")[:6000]
        except Exception:
            continue
        m = re.search(r"Released\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})", t)
        if m and m.group(1) in MONTHS:
            out.add(pd.Timestamp(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))))
    return sorted(out)


def esr_dates():
    p = ROOT / "data" / "grains" / "raw" / "export_sales" / "corn"
    ds = set()
    for f in p.glob("MY*.csv"):
        ds |= set(pd.to_datetime(pd.read_csv(f, usecols=["weekEndingDate"]).weekEndingDate.astype(str).str[:10]))
    return sorted(d + pd.Timedelta(days=7) for d in ds)


def react_day(idx, d, after_close):
    """Trading day whose close-to-close return captures the release."""
    pos = idx.searchsorted(d)
    if pos >= len(idx):
        return None
    if after_close:
        pos += 1 if idx[pos] == d else 0
    return idx[pos] if pos < len(idx) else None


def wasde_revisions(fname, key):
    import grains_wasde_brief as WB
    try:
        df = WB.load_wasde(fname, key)
    except Exception as e:
        print("wasde", e); return {}
    us = df[df.reg == "United States"]
    rels = sorted(us.rd.unique()); out = {}
    for i, rd in enumerate(rels[1:], 1):
        my = WB.focus_my(df, rd); prev = rels[i - 1]
        es, esp = WB.get(df, "United States", "Ending Stocks", my, rd), WB.get(df, "United States", "Ending Stocks", my, prev)
        du, ex = WB.get(df, "United States", "Domestic Use", my, rd), WB.get(df, "United States", "Exports", my, rd)
        use = du + ex if du is not None and ex is not None else WB.get(df, "United States", "Total Use", my, rd)
        if None not in (es, esp, use) and use > 0:
            out[(rd.year, rd.month)] = (es - esp) / use * 100      # revision, % of total use
    return out


def main():
    events = {k: release_dates(s) for k, (s, _) in REPORTS.items()}
    events["Export sales"] = esr_dates()
    print({k: len(v) for k, v in events.items()})
    res = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "markets": {}, "events_n": {k: len(v) for k, v in events.items()}}
    for sym, types in BY_SYM.items():
        px = RV.load(sym)
        if px is None:
            continue
        r = RV.front_returns(sym, px) * 100          # % log return
        fc = RV.front_close(sym, px)
        if len(r) < 500:
            continue
        idx = r.index; normal = float(r.abs().median()); normal_mean = float(r.abs().mean())
        price = float(fc.iloc[-1]); m = {"name": RV.SYMS[sym], "unit": RV.UNIT[sym], "price": price, "normal_abs_med": round(normal, 2),
                                         "normal_abs_mean": round(normal_mean, 2), "reports": {}}
        for t in types:
            after = REPORTS.get(t, (None, False))[1]
            rows = []
            for d in events.get(t, []):
                rd = react_day(idx, d, after)
                if rd is not None and (rd - d).days <= 4:
                    rows.append((d, rd, float(r[rd])))
            if len(rows) < 8:
                continue
            v = np.array([x[2] for x in rows]); a = np.abs(v)
            med = float(np.median(a))
            m["reports"][t] = {"n": len(rows), "since": rows[0][0].year, "abs_med": round(med, 2), "abs_mean": round(float(a.mean()), 2),
                               "p90": round(float(np.quantile(a, .9)), 2), "ratio": round(med / normal, 2), "up_share": round(float((v > 0).mean()), 2),
                               "exp_move": round(price * med / 100, 2), "exp_move_usd": round(price * med / 100 * RV.USD[sym]),
                               "p90_move": round(price * float(np.quantile(a, .9)) / 100, 2),
                               "last": [{"date": d.strftime("%Y-%m-%d"), "ret": round(x, 2)} for d, _, x in rows[-8:]][::-1],
                               "biggest": [{"date": d.strftime("%Y-%m-%d"), "ret": round(x, 2)} for d, _, x in sorted(rows, key=lambda z: -abs(z[2]))[:5]]}
        if sym in WASDE_KEY and "WASDE / Crop Production" in m["reports"]:
            rev = wasde_revisions(*WASDE_KEY[sym])
            pts = []
            for d in events["WASDE / Crop Production"]:
                rd = react_day(idx, d, False)
                if rd is not None and (d.year, d.month) in rev and (rd - d).days <= 4:
                    pts.append((rev[(d.year, d.month)], float(r[rd]), d))
            if len(pts) >= 20:
                X = np.array([p[0] for p in pts]); Y = np.array([p[1] for p in pts])
                b = float(np.polyfit(X, Y, 1)[0]); c = float(np.corrcoef(X, Y)[0, 1])
                big = [p for p in pts if abs(p[0]) >= np.quantile(np.abs(X), .75)]
                agree = float(np.mean([np.sign(p[0]) != np.sign(p[1]) for p in big])) if big else None
                m["wasde_sensitivity"] = {"n": len(pts), "beta": round(b, 2), "corr": round(c, 2), "big_n": len(big), "big_hit": round(agree, 2) if agree is not None else None,
                                          "note": f"{b:+.2f}% price move per 1% of total use added to US ending stocks; on the quarter of reports with the largest revisions, price moved opposite to the stocks change {agree*100:.0f}% of the time." if agree is not None else ""}
        res["markets"][sym] = m
        print(sym, {k: (v["n"], v["abs_med"], v["ratio"]) for k, v in m["reports"].items()}, m.get("wasde_sensitivity", {}).get("corr"))
    OUT.write_text(json.dumps(RV.clean(res), separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
