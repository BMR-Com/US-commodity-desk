"""Grains analyst pack: the charts and tables of a broker-style weekly grains report, built from desk data.

Replicates (with free data) the US yield, state, balance-sheet, export-sales, price-vs-tightness, spread, positioning
and South American / world sections of a Cefetra/Ceras-style weekly. Sections that need paid or proprietary feeds
(FOB/C&F prices, Black Sea line-ups, trade polls, seeding-company yields) are listed in `missing`.

Inputs: data/esmis/crop-production (NASS Crop Production text, monthly forecasts by state), data/grains/raw/annual
(NASS final yields by state), BMR-Com/wasde-analytics (WASDE by report), data/grains/raw/export_sales (FAS ESR),
data/contracts (per-contract closes), data/cot, data/geo/raw/psd.json (PSD), data/south_america.
Writes data/grains/derived/pack.json.
"""
import gzip, json, re, sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "grains" / "derived"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from grains_wasde import tidy, load, FILES  # noqa: E402
from grains_sales import esr  # noqa: E402

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
MI = {m: i for i, m in enumerate(MONTHS, 1)}
ST = {"Alabama": "AL", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO", "Connecticut": "CT",
      "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA",
      "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
      "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
      "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
      "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA",
      "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
      "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
      "United States": "US", "US": "US", "U.S.": "US"}
ABBR = set(ST.values())
TABLE = {"corn": "Corn for Grain", "soybeans": "Soybeans for Beans"}
r1 = lambda v, d=1: None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), d)


# ---------------------------------------------------------------- NASS Crop Production: state yields by report month
def parse_cropprod(text, crop):
    m = re.search(r"Released\s+(\w+)\s+(\d+),\s+(\d{4})", text)
    if not m or m.group(1) not in MI:
        return None
    rel = date(int(m.group(3)), MI[m.group(1)], int(m.group(2)))
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if TABLE[crop] in ln and "Area Harvested, Yield, and Production" in ln and (
                "State" in ln or "by State" in ln) and "...." not in ln and \
                any(x.strip().startswith("-----") for x in lines[i + 1:i + 5]) and \
                "...." not in " ".join(lines[i + 1:i + 3]):
            start = i
            break
    if start is None:
        return None
    hdr = " ".join(lines[start:start + 2])
    if "Forecasted" not in hdr:
        return None  # annual summary (final), not a forecast
    rows, seen = {}, False
    for ln in lines[start + 2:start + 90]:
        mm = re.match(r"^\s*([A-Za-z][A-Za-z .]*?)\s*\.*\s*:\s*([\d,.\s]+?)\s*$", ln)
        if not mm:
            if seen and ln.strip().startswith("----") and "US" in rows:
                break
            continue
        name = mm.group(1).strip().rstrip(".").strip()
        code = ST.get(name, name if name in ABBR else None)
        try:
            nums = [float(x.replace(",", "")) for x in mm.group(2).split()]
        except ValueError:
            continue
        if not code or len(nums) not in (6, 7, 8):
            continue
        seen = True
        a0, a1, y0 = nums[:3]
        if rel.month == 8 or len(nums) == 6:
            yp, yc = None, nums[3]
        else:
            yp, yc = nums[3], nums[4]
        rows[code] = dict(acres_ly=a0, acres=a1, y_ly=y0, y_prev=yp, y=yc)
        if code == "US":
            break
    return (rel, rows) if "US" in rows else None


def crop_reports():
    out = {"corn": {}, "soybeans": {}}
    # "crop1026_0" is an alternate copy of "crop1026": read the suffixed copies first so the plain file wins
    fs = (ROOT / "data" / "esmis" / "crop-production").glob("*.txt.gz")
    for f in sorted(fs, key=lambda f: (re.sub(r"_\d+$", "", f.name[:-7]) == f.name[:-7], f.name)):
        try:
            text = gzip.open(f, "rt", errors="ignore").read()
        except Exception:
            continue
        for crop in out:
            r = parse_cropprod(text, crop)
            if r and r[0].month in (8, 9, 10, 11):
                out[crop][(r[0].year, r[0].month)] = r[1]
    return out


def annual_yields(crop):
    """NASS annual state + US yields (final for completed years) from data/grains/raw/annual."""
    want = {"corn": "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", "soybeans": "SOYBEANS - YIELD, MEASURED IN BU / ACRE"}[crop]
    rows = []
    for f in sorted((ROOT / "data" / "grains" / "raw" / "annual" / crop).glob("*.csv.gz")):
        d = pd.read_csv(f, dtype=str)
        d = d[(d.short_desc == want) & (d.reference_period_desc == "YEAR")]
        for r in d.itertuples():
            try:
                rows.append((int(r.year), r.state_alpha, float(str(r.Value).replace(",", ""))))
            except ValueError:
                pass
    return pd.DataFrame(rows, columns=["year", "st", "y"]).drop_duplicates(["year", "st"], keep="last")


def yields_section(reps, crop, cur_year):
    ann = annual_yields(crop)
    us = ann[ann.st == "US"].set_index("year").y
    years = sorted({y for y, _ in reps[crop]})
    rows = []
    for y in years:
        sep, octo, nov, aug = (reps[crop].get((y, m), {}).get("US", {}).get("y") for m in (9, 10, 11, 8))
        fin = us.get(y) if y < cur_year else None
        rows.append(dict(my=f"{y % 100:02d}/{(y + 1) % 100:02d}", year=y, aug=aug, sep=sep, oct=octo, nov=nov, final=fin,
                         oct_sep=r1((octo / sep - 1) * 100, 1) if sep and octo else None,
                         final_oct=r1((fin / octo - 1) * 100, 1) if fin and octo else None))
    oc = [r["oct_sep"] for r in rows if r["oct_sep"] is not None]
    fo = [r["final_oct"] for r in rows if r["final_oct"] is not None]
    stats = dict(n_oct=len(oc), avg_oct_sep=r1(np.mean(oc), 2) if oc else None,
                 pct_up_oct_sep=round(100 * np.mean([x > 0 for x in oc])) if oc else None,
                 avg_abs_oct_sep=r1(np.mean(np.abs(oc)), 2) if oc else None,
                 n_final=len(fo), avg_final_oct=r1(np.mean(fo), 2) if fo else None,
                 pct_up_final_oct=round(100 * np.mean([x > 0 for x in fo])) if fo else None,
                 avg_abs_final_oct=r1(np.mean(np.abs(fo)), 2) if fo else None)

    # state maps: every month-to-month change in the latest two seasons that has reports
    maps = []
    for y in sorted({y for y, _ in reps[crop]})[-2:]:
        for m in (9, 10, 11):
            cur, prv = reps[crop].get((y, m)), reps[crop].get((y, m - 1))
            if not cur:
                continue
            usa = cur["US"]["acres"]
            st = []
            for k, v in cur.items():
                if k == "US":
                    continue
                yp = v["y_prev"] if v["y_prev"] is not None else (prv or {}).get(k, {}).get("y")
                if yp is None:
                    continue
                st.append(dict(st=k, acres=v["acres"], y_prev=yp, y=v["y"], y_ly=v["y_ly"], chg=r1(v["y"] - yp),
                               impact=r1((v["y"] - yp) * v["acres"] / usa, 2)))
            usp = cur["US"]["y_prev"] or (prv or {}).get("US", {}).get("y")
            maps.append(dict(label=f"{MONTHS[m - 2][:3]} → {MONTHS[m - 1][:3]} {y}", year=y, month=m,
                             us_prev=usp, us=cur["US"]["y"], us_ly=cur["US"]["y_ly"],
                             states=sorted(st, key=lambda r: -r["acres"])))

    # state history with linear trend (1986 → last completed year), current forecast vs trend
    hist, vs_trend = {}, []
    latest = reps[crop].get(max(reps[crop])) if reps[crop] else {}
    top = sorted([k for k in latest if k != "US"], key=lambda k: -latest[k]["acres"])[:18] + ["US"]
    for k in top:
        s = ann[(ann.st == k) & (ann.year < cur_year)].sort_values("year")
        if len(s) < 10:
            continue
        b, a = np.polyfit(s.year, s.y, 1)
        cur = latest.get(k, {}).get("y")
        hist[k] = dict(years=s.year.tolist(), y=s.y.tolist(), trend=[r1(a + b * x) for x in s.year] + [r1(a + b * cur_year)],
                       cur=cur, cur_year=cur_year, slope=r1(b, 2))
        if cur:
            t = a + b * cur_year
            vs_trend.append(dict(st=k, cur=cur, trend=r1(t), dev=r1(cur - t), dev_pct=r1((cur / t - 1) * 100),
                                 acres=latest[k]["acres"]))
    return dict(table=rows, stats=stats, maps=maps, hist=hist, vs_trend=sorted(vs_trend, key=lambda r: -r["acres"]))


# ---------------------------------------------------------------- WASDE: balance tables and revision history
SD_ROWS = {
    "corn": ["area_planted", "area_harvested", "yield", "beg_stocks", "production", "imports", "supply", "feed_residual",
             "ethanol", "fsi", "domestic", "exports", "use", "end_stocks", "su", "price"],
    "soybeans": ["beg_stocks", "area_planted", "area_harvested", "yield", "production", "imports", "supply", "seed",
                 "residual", "crush", "exports", "use", "end_stocks", "su", "price"],
    "wheat": ["area_planted", "area_harvested", "yield", "beg_stocks", "production", "imports", "supply", "food", "seed",
              "feed_residual", "domestic", "exports", "use", "end_stocks", "su", "price"],
    "meal": ["beg_stocks", "production", "imports", "supply", "domestic", "exports", "use", "end_stocks", "su", "price"],
    "oil": ["beg_stocks", "production", "imports", "supply", "biofuel", "food_other", "domestic", "exports", "use",
            "end_stocks", "su", "price"]}


def wasde_frame(key):
    d = tidy(load(FILES[key]))
    d = d[d.region == "United States"].copy()
    d["ry"] = [int(r.split()[1]) if len(r.split()) == 2 and r.split()[0] in MI else None for r in d.report]
    d["rm"] = [MI.get(r.split()[0]) if len(r.split()) == 2 else None for r in d.report]
    d = d.dropna(subset=["ry", "value"])
    d["ord"] = d.ry * 12 + d.rm
    return d


def sd_section(key, d):
    """Columns: 3 completed MYs (latest), old crop (prev report, latest), new crop (prev report, latest)."""
    mys = sorted(d.my.unique(), key=lambda s: int(s[:4]))
    new = mys[-1]
    last = d[d.my == new].ord.max()
    prev_rep = d[(d.my == new) & (d.ord < last)].ord.max()
    lab = lambda o: f"{MONTHS[int((o - 1) % 12)][:3]} {int((o - 1) // 12)}"

    def col(my, o):
        s = d[(d.my == my) & (d.ord <= o)].sort_values("ord").groupby("attr").value.last()
        v = {a: r1(s.get(a), 3) for a in SD_ROWS[key] if a in s}
        if v.get("end_stocks") is not None and v.get("use"):
            v["su"] = r1(100 * v["end_stocks"] / v["use"], 1)
        return v

    cols = []
    for my in mys[-5:-2]:
        cols.append(dict(my=my, label="", v=col(my, last)))
    for my in mys[-2:]:
        if pd.notna(prev_rep):
            cols.append(dict(my=my, label="USDA " + lab(prev_rep), v=col(my, prev_rep)))
        cols.append(dict(my=my, label="USDA " + lab(last), v=col(my, last), latest=True))
    units = d.groupby("attr").unit.last().to_dict()
    return dict(rows=SD_ROWS[key], cols=cols, units={k: units.get(k) for k in SD_ROWS[key]}, new_crop=new)


def revisions_section(d, attr="end_stocks", m_from=9, m_to=10):
    """New-crop change from the m_from to the m_to WASDE, every year."""
    out = []
    for my in sorted(d.my.unique()):
        y0 = int(my[:4])
        s = d[(d.my == my) & (d.attr == attr)]
        a = s[(s.ry == y0) & (s.rm == m_from)].value
        b = s[(s.ry == y0) & (s.rm == m_to)].value
        if len(a) and len(b):
            out.append(dict(my=my, year=y0, before=r1(a.iloc[0], 0), after=r1(b.iloc[0], 0), chg=r1(b.iloc[0] - a.iloc[0], 0)))
    return out


# ---------------------------------------------------------------- Export sales: projections and YTD bars
ESR = {"corn": ("corn", 39.368, "corn"), "soybeans": ("soybeans", 36.744, "soybeans"), "wheat": ("wheat_all", 36.744, "wheat"),
       "HRW": ("wheat_hrw", 36.744, None), "SRW": ("wheat_srw", 36.744, None), "HRS": ("wheat_hrs", 36.744, None),
       "White": ("wheat_white", 36.744, None), "meal": ("soybean_meal", 1.10231, "meal")}


def export_section(name, wd):
    sub, conv, wkey = ESR[name]
    g = esr(sub)
    if g is None:
        return None
    g = g.copy()
    mys = sorted(g.my.unique(), key=lambda s: int(s[:4]))
    cur = mys[-1]
    fin = g.groupby("my").accumulatedExports.last()  # ESR final shipments (MT) per completed MY
    done = [m for m in mys[:-1] if g[g.my == m].wk.max() >= 50]
    # ratio commitments(w) / final shipments, by week, completed years
    piv = g.pivot_table(index="wk", columns="my", values="commit")
    ratio = piv[done].div(fin[done]) if done else None
    c = g[g.my == cur].set_index("wk")
    proj, lo, hi = [], [], []
    sc = 1e6 if conv > 30 else 1e3  # bushels -> million bu; short tons -> thousand short tons
    for w, v in c.commit.items():
        r = ratio.loc[w].dropna() if ratio is not None and w in ratio.index else pd.Series(dtype=float)
        r = r.tail(10)
        if len(r) < 4:
            continue
        # higher ratio = more of the year already sold -> lower projection
        proj.append([int(w), r1(v / r.median() * conv / sc, 1)])
        lo.append([int(w), r1(v / r.quantile(0.9) * conv / sc, 1)])
        hi.append([int(w), r1(v / r.quantile(0.1) * conv / sc, 1)])
    usda = None
    if wkey and wd.get(wkey) is not None:
        s = wd[wkey]
        s = s[(s.my == f"{cur[:4]}/{cur[-2:]}") & (s.attr == "exports")].sort_values("ord")
        usda = r1(s.value.iloc[-1], 0) if len(s) else None
    # YTD at the same week for each MY (million MT)
    wk = int(c.index.max())
    ytd = []
    for m in mys[-10:]:
        r = g[(g.my == m) & (g.wk == wk)]
        if len(r):
            r = r.iloc[0]
            ytd.append(dict(my=m[2:], shipped=r1(r.accumulatedExports / 1e6, 2), outstanding=r1(r.outstandingSales / 1e6, 2),
                            commit=r1(r.commit / 1e6, 2)))
    # weekly net sales (current MY) vs 5-year average, '000 MT
    nets = g.pivot_table(index="wk", columns="my", values="currentMYNetSales")
    prev5 = [m for m in done[-5:]]
    weekly = dict(wk=[int(x) for x in nets.index], cur=[r1(v / 1e3, 0) if pd.notna(v) else None for v in nets[cur]],
                  avg5=[r1(v / 1e3, 0) for v in nets[prev5].mean(axis=1)] if prev5 else [])
    unit = "mil bu" if conv > 30 else "thou short tons"
    return dict(my=cur, week=wk, as_of=str(c.week.iloc[-1].date()), unit=unit, proj=proj, lo=lo, hi=hi, usda=usda,
                ytd=ytd, weekly=weekly, years_used=len(done[-10:]))


# ---------------------------------------------------------------- Prices: tightness curve, market-derived S/U, spreads
def contracts(sym):
    d = pd.read_csv(ROOT / "data" / "contracts" / f"{sym}.csv", parse_dates=["date"])
    return d


def tightness_section(key, sym, mcode, month, d_w, cdf, desk_su=None):
    """Average price of the new-crop contract during `month` of the harvest year vs WASDE S/U known at that report."""
    pts = []
    for y in range(2007, 2027):
        c = cdf[(cdf.contract == f"{sym}{mcode}{y}") & (cdf.date.dt.year == y) & (cdf.date.dt.month == month)]
        my = f"{y}/{(y + 1) % 100:02d}"
        s = d_w[(d_w.my == my) & (d_w.ry == y) & (d_w.rm <= month)]
        es = s[s.attr == "end_stocks"].sort_values("ord").value
        us = s[s.attr == "use"].sort_values("ord").value
        if not len(c) or not len(es) or not len(us):
            continue
        pts.append(dict(my=my, year=y, su=r1(100 * es.iloc[-1] / us.iloc[-1], 2), price=r1(c.close.mean() / 100, 3),
                        partial=y == date.today().year and date.today().month == month))
    fit = [p for p in pts if not p["partial"] and p["year"] >= 2007]
    # post-biofuel era: log(price) = a + b*log(su), with the residual sd
    x, yv = np.log([p["su"] for p in fit]), np.log([p["price"] for p in fit])
    b, a = np.polyfit(x, yv, 1)
    sd = float(np.std(yv - (a + b * x), ddof=2))
    r2 = 1 - np.sum((yv - (a + b * x)) ** 2) / np.sum((yv - yv.mean()) ** 2)
    curve = [[s, r1(np.exp(a + b * np.log(s)), 3), r1(np.exp(a + b * np.log(s) + sd), 3), r1(np.exp(a + b * np.log(s) - sd), 3)]
             for s in np.round(np.arange(4 if key == "corn" else 2, 25.1 if key == "corn" else 19.1, 0.25), 2)]
    # market-derived S/U for the current new crop: invert the curve at each day's new-crop price
    y0 = int(d_w.my.max()[:4])
    nc = cdf[cdf.contract == f"{sym}{mcode}{y0}"].sort_values("date")
    nc = nc[nc.date >= pd.Timestamp(y0 - 1, 9, 1)]
    mkt = [[str(r.date.date()), r1(np.exp((np.log(r.close / 100) - a) / b), 2)] for r in nc.itertuples()][::3]
    usda_steps = []
    my = f"{y0}/{(y0 + 1) % 100:02d}"
    s = d_w[d_w.my == my]
    for o in sorted(s.ord.unique()):
        es = s[(s.ord == o) & (s.attr == "end_stocks")].value
        us = s[(s.ord == o) & (s.attr == "use")].value
        if len(es) and len(us):
            usda_steps.append([f"{int((o - 1) // 12)}-{int((o - 1) % 12) + 1:02d}-12", r1(100 * es.iloc[0] / us.iloc[0], 2)])
    last_price = r1(nc.close.iloc[-1] / 100, 3) if len(nc) else None
    usda_su = usda_steps[-1][1] if usda_steps else None
    fv = lambda su: r1(np.exp(a + b * np.log(su)), 2) if su else None
    return dict(points=pts, curve=curve, a=r1(a, 4), b=r1(b, 4), sd=r1(sd, 4), r2=r1(r2, 2), n=len(fit),
                contract=f"{sym}{mcode}{y0}", month=MONTHS[month - 1], price=last_price,
                mkt_su=mkt[-1][1] if mkt else None, mkt=mkt, usda=usda_steps, usda_su=usda_su, fv_usda=fv(usda_su),
                desk_su=desk_su, fv_desk=fv(desk_su))


MC = "FGHJKMNQUVXZ"


def spreads_section(sym, pairs, cdf, today=None):
    """Calendar spreads: current vs the same pair at this time of year and near expiry of the first leg, all years."""
    today = today or cdf.date.max()
    px = cdf.pivot_table(index="date", columns="contract", values="close")
    out = []
    for m1, dy1, m2, dy2 in pairs:
        c1, c2 = f"{sym}{m1}{today.year + dy1}", f"{sym}{m2}{today.year + dy2}"
        if c1 not in px or c2 not in px:
            continue
        s = (px[c1] - px[c2]).dropna()
        if not len(s):
            continue
        cur = s.iloc[-1]
        same, near = [], []
        for k in range(1, 20):
            a, b = f"{sym}{m1}{today.year + dy1 - k}", f"{sym}{m2}{today.year + dy2 - k}"
            if a not in px or b not in px:
                continue
            h = (px[a] - px[b]).dropna()
            if len(h) < 50:
                continue
            ref = today - pd.DateOffset(years=k)
            hs = h[(h.index >= ref - pd.Timedelta(days=5)) & (h.index <= ref + pd.Timedelta(days=5))]
            if len(hs):
                same.append(hs.mean())
            near.append(h.iloc[-10:].mean())
        q = lambda v, p: r1(np.percentile(v, p), 1) if len(v) >= 5 else None
        out.append(dict(pair=f"{m1}{(today.year + dy1) % 100}/{m2}{(today.year + dy2) % 100}", c1=c1, c2=c2,
                        current=r1(cur, 2), n=len(same), now_med=q(same, 50), now_p10=q(same, 10), now_p90=q(same, 90),
                        pct_rank=round(100 * np.mean(np.array(same) <= cur)) if same else None,
                        exp_med=q(near, 50), exp_p10=q(near, 10), exp_p90=q(near, 90)))
    return out


def dec_dec(sym, m, cdf):
    """Same-month spread (e.g. Dec/Dec) path by year, aligned on days to the first leg's expiry."""
    px = cdf.pivot_table(index="date", columns="contract", values="close")
    yrs = {}
    last_y = cdf.date.max().year
    for y in range(2008, last_y + 1):
        a, b = f"{sym}{m}{y}", f"{sym}{m}{y + 1}"
        if a not in px or b not in px:
            continue
        s = (px[a] - px[b]).dropna()
        s = s[s.index >= s.index.max() - pd.Timedelta(days=540)]
        if len(s) < 60:
            continue
        exp = px[a].dropna().index.max()
        if y == last_y or (y == last_y - 1 and exp >= cdf.date.max() - pd.Timedelta(days=3)):
            exp = pd.Timestamp(y, MC.index(m) + 1, 14)  # live contract: align on its approx. expiry
        d = (s.index - exp).days
        yrs[str(y)] = [[int(k), r1(v, 2)] for k, v in zip(d[::3], s.values[::3])]
    allp = pd.DataFrame([(k, v) for ys in list(yrs.values())[:-2] for k, v in ys], columns=["d", "v"])
    allp["b"] = (allp.d // 7) * 7
    med = allp.groupby("b").v.median()
    return dict(years=yrs, median=[[int(k), r1(v, 2)] for k, v in med.items()], month=m)


def cot_mmt(sym, bu_mt):
    d = pd.read_csv(ROOT / "data" / "cot" / f"{sym}_fo.csv")
    d["date"] = pd.to_datetime(d.report_date_as_yyyy_mm_dd).dt.date.astype(str)
    d = d.sort_values("date")
    net = d.m_money_positions_long_all - d.m_money_positions_short_all
    mmt = net * 5000 / bu_mt / 1e6
    return dict(date=d.date.tolist()[::1], mmt=[r1(v, 2) for v in mmt], pct=round(100 * np.mean(mmt <= mmt.iloc[-1])),
                last=r1(mmt.iloc[-1], 2), wow=r1(mmt.iloc[-1] - mmt.iloc[-2], 2))


# ---------------------------------------------------------------- World / South America
PSD_EXP = {"corn": [("AR", "Argentina"), ("BR", "Brazil"), ("UP", "Ukraine"), ("E4", "EU"), ("RS", "Russia"),
                    ("RB", "Serbia"), ("PA", "Paraguay"), ("IN", "India"), ("CA", "Canada"), ("SF", "South Africa"),
                    ("US", "United States")],
           "wheat": [("AR", "Argentina"), ("AS", "Australia"), ("CA", "Canada"), ("KZ", "Kazakhstan"), ("RS", "Russia"),
                     ("UP", "Ukraine"), ("E4", "EU"), ("US", "United States")]}


def psd_frame(com):
    p = json.loads((ROOT / "data" / "geo" / "raw" / "psd.json").read_text())["data"][com]
    d = pd.DataFrame(p["rows"], columns=["cc", "country", "my", "attr", "v"])
    return d


def world_corn():
    d = psd_frame("corn")
    e = d[d.attr == "Exports"].pivot_table(index="cc", columns="my", values="v", aggfunc="sum")
    mys = [m for m in sorted(e.columns) if m >= max(e.columns) - 11]
    rows = []
    for cc, nm in PSD_EXP["corn"]:
        if cc in e.index:
            rows.append(dict(cc=cc, name=nm, v=[r1(e.loc[cc, m] / 1000, 1) for m in mys]))
    world = d[(d.attr == "Exports")].groupby("my").v.sum()
    tot = [r1(world.get(m) / 1000, 1) for m in mys]
    imp = d[d.attr == "Imports"]
    ex_eu_cn = imp[~imp.cc.isin(["E4", "CH"])].groupby("my").v.sum()
    yoy = [r1(100 * (ex_eu_cn.get(m) / ex_eu_cn.get(m - 1) - 1), 1) if ex_eu_cn.get(m - 1) else None for m in mys]
    return dict(mys=[f"{m % 100:02d}/{(m + 1) % 100:02d}" for m in mys], rows=rows, world=tot, yoy_imports=yoy,
                note="USDA PSD local marketing years (not a common Sep/Aug year)")


def world_wheat():
    d = psd_frame("wheat")
    attrs = ["Area Harvested", "Yield", "Beginning Stocks", "Production", "Imports", "Total Supply",
             "Feed Dom. Consumption", "Domestic Consumption", "Exports", "Ending Stocks"]
    mys = sorted(d.my.unique())[-3:]
    out = {}
    for my in mys:
        s = d[d.my == my]
        cols = []
        for cc, nm in PSD_EXP["wheat"] + [("WD", "World")]:
            t = s[s.cc == cc] if cc != "WD" else s
            if cc != "WD" and t.empty:
                continue
            v = t.groupby("attr").v.sum()
            if cc == "WD":
                v = s[s.attr.isin(attrs)].groupby("attr").v.sum()
            row = {a: r1(v.get(a) / (1 if a in ("Yield",) else 1000), 2) for a in attrs if a in v}
            if cc == "WD" and "Area Harvested" in v and "Production" in v:
                row["Yield"] = r1(v["Production"] / v["Area Harvested"], 2)
            use = v.get("Domestic Consumption", 0) + v.get("Exports", 0)
            row["su"] = r1(100 * v.get("Ending Stocks", 0) / use, 1) if use else None
            cols.append(dict(cc=cc, name=nm, v=row))
        out[f"{my}/{(my + 1) % 100:02d}"] = cols
    return dict(rows=attrs + ["su"], years=out)


def brazil_corn():
    d = pd.read_csv(ROOT / "data" / "south_america" / "brazil_exports.csv")
    out = {}
    for com, m0 in (("corn", 9), ("soybeans", 1)):
        c = d[d.commodity == com].copy()
        c["my"] = np.where(c.month >= m0, c.year, c.year - 1) if m0 > 1 else c.year
        c["i"] = (c.month - m0) % 12
        piv = c.pivot_table(index="i", columns="my", values="kt").sort_index()
        mys = [m for m in sorted(piv.columns)][-5:]
        out[com] = dict(start=m0, mys=[f"{m % 100:02d}/{(m + 1) % 100:02d}" if m0 > 1 else str(m) for m in mys],
                        monthly={str(m): [r1(v / 1000, 2) if pd.notna(v) else None for v in piv[m]] for m in mys},
                        totals={str(m): r1(piv[m].sum() / 1000, 1) for m in mys})
    return out


# ---------------------------------------------------------------- Brazil & Argentina soybean complex
SA_ROWS = {
    "soybeans": ["Beginning Stocks", "Area Harvested", "Yield", "Production", "Imports", "Total Supply", "Crush",
                 "Other domestic", "Domestic Consumption", "Exports", "Total use", "Ending Stocks", "su"],
    "meal": ["Beginning Stocks", "Crush", "Production", "Imports", "Total Supply", "Domestic Consumption", "Exports",
             "Total use", "Ending Stocks", "su"],
    "oil": ["Beginning Stocks", "Crush", "Production", "Imports", "Total Supply", "Industrial Dom. Cons.",
            "Food Use Dom. Cons.", "Domestic Consumption", "Exports", "Total use", "Ending Stocks", "su"]}


def sa_balance(cc, com, n=7):
    d = psd_frame(com)
    d = d[d.cc == cc]
    mys = sorted(d.my.unique())[-n:]
    cols = []
    for my in mys:
        v = d[d.my == my].groupby("attr").v.sum()
        row = {}
        for a in SA_ROWS[com]:
            if a in v:
                row[a] = r1(v[a] / (1 if a == "Yield" else 1000), 2)
        dom, ex = v.get("Domestic Consumption"), v.get("Exports")
        if dom is not None and ex is not None:
            row["Total use"] = r1((dom + ex) / 1000, 2)
            if v.get("Ending Stocks") is not None and dom + ex:
                row["su"] = r1(100 * v["Ending Stocks"] / (dom + ex), 1)
        if com == "soybeans" and dom is not None and v.get("Crush") is not None:
            row["Other domestic"] = r1((dom - v["Crush"]) / 1000, 2)
        if com in ("meal", "oil") and v.get("Crush") is not None and v.get("Production"):
            row["Crush"] = r1(v["Crush"] / 1000, 2)
        cols.append(dict(my=f"{my}/{(my + 1) % 100:02d}", v=row))
    return dict(rows=SA_ROWS[com], cols=cols)


CONAB_ROWS = {"soybeans": {"1.1": "Beginning Stocks", "1.2": "Production", "1.3": "Imports", "1.4": "Seed & other",
                            "1.6": "Crush", "1.5": "Exports", "1.7": "Ending Stocks"},
              "meal": {"2.1": "Beginning Stocks", "2.2": "Production", "2.3": "Imports", "2.5": "Domestic sales",
                       "2.4": "Exports", "2.6": "Ending Stocks"},
              "oil": {"3.1": "Beginning Stocks", "3.2": "Production", "3.3": "Imports", "3.5": "Domestic sales",
                      "3.4": "Exports", "3.6": "Ending Stocks"}}


def conab_balance():
    """CONAB 'Suprimento - Soja' sheet (soybeans, meal, oil; '000 t) from the latest Boletim da Safra de Grãos."""
    sa = ROOT / "data" / "south_america"
    if not (sa / "conab_supply_raw.csv").exists() or not (sa / "conab_balanco_soja.csv").exists():
        return None
    raw = pd.read_csv(sa / "conab_supply_raw.csv")
    raw = raw[raw.sheet == "Suprimento - Soja"]
    safras = pd.read_csv(sa / "conab_balanco_soja.csv").safra.tolist()
    meta = json.loads((sa / "conab_supply_meta.json").read_text()) if (sa / "conab_supply_meta.json").exists() else {}
    out = {}
    for com, mp in CONAB_ROWS.items():
        cols = []
        for j, sf in enumerate(safras, 1):
            v = {}
            for code, name in mp.items():
                x = raw[raw.label.str.startswith(code + ".") & (raw.col == j)].value
                if len(x):
                    v[name] = r1(float(x.iloc[0]) / 1000, 2)
            sup = sum(v.get(k) or 0 for k in ("Beginning Stocks", "Production", "Imports"))
            use = sum(v.get(k) or 0 for k in ("Seed & other", "Crush", "Domestic sales", "Exports"))
            v["Total Supply"], v["Total use"] = r1(sup, 2), r1(use, 2)
            if use and v.get("Ending Stocks") is not None:
                v["su"] = r1(100 * v["Ending Stocks"] / use, 1)
            cols.append(dict(my=f"{sf} (cal. {int(sf[:4]) + 1})", v=v))
        rows = list(mp.values())
        rows = rows[:3] + ["Total Supply"] + rows[3:-1] + ["Total use", rows[-1], "su"]
        out[com] = dict(rows=rows, cols=cols)
    out["survey"] = f"{meta.get('levantamento', '?')}º levantamento {meta.get('safra', '')}, published {meta.get('data_publicacao', '')}"
    return out


def monthly_table(df, col, start, n=4, scale=1e3):
    """{season: [12 monthly values in start-month order]}, values in thousand t -> million t."""
    d = df[["year", "month", col]].dropna().copy()
    d["s"] = (d.year - (d.month < start)).astype(int)
    d["i"] = (d.month - start) % 12
    piv = d.pivot_table(index="i", columns="s", values=col, aggfunc="sum").reindex(range(12))
    seasons = sorted(piv.columns)
    lab = (lambda s: str(s)) if start == 1 else (lambda s: f"{s % 100:02d}/{(s + 1) % 100:02d}")
    hist = piv[[s for s in seasons[:-1]][-10:]]
    return dict(seasons=[lab(s) for s in seasons[-n:]],
                values={lab(s): [r1(v / scale, 2) if pd.notna(v) else None for v in piv[s]] for s in seasons[-n:]},
                min10=[r1(v / scale, 2) for v in hist.min(axis=1)], max10=[r1(v / scale, 2) for v in hist.max(axis=1)],
                avg10=[r1(v / scale, 2) for v in hist.mean(axis=1)])


def south_america_soy():
    out = {"brazil": {}, "argentina": {}}
    for cc, k in (("BR", "brazil"), ("AR", "argentina")):
        out[k]["balance"] = {c: sa_balance(cc, c) for c in ("soybeans", "meal", "oil")}
    try:
        out["brazil"]["conab"] = conab_balance()
    except Exception as e:
        print("conab balance", e)
    # Brazil monthly exports (Comex Stat), calendar year, million t
    bx = pd.read_csv(ROOT / "data" / "south_america" / "brazil_exports.csv")
    mon = {}
    for c in ("soybeans", "meal", "oil"):
        x = bx[bx.commodity == c].rename(columns={"kt": "v"})
        mon[c] = monthly_table(x, "v", 1)
    out["brazil"]["monthly"] = {"exports": mon, "start": 1, "source": "Comex Stat (via the desk pipeline)"}
    # Argentina monthly crush / output (MAGyP) and stocks; Apr/Mar season, million t
    p1, p2 = ROOT / "data" / "south_america" / "ar_crush_monthly.csv", ROOT / "data" / "south_america" / "ar_stocks_monthly.csv"
    if p1.exists():
        cr = pd.read_csv(p1)
        cr["meal"] = cr.pellets.fillna(0) + cr.expellers.fillna(0)
        m = {"crush": monthly_table(cr, "crush", 4, scale=1e6), "oil_prod": monthly_table(cr, "oil", 4, scale=1e6),
             "meal_prod": monthly_table(cr, "meal", 4, scale=1e6)}
        last = cr.iloc[-1]
        yld = cr.tail(12)
        out["argentina"]["crush_asof"] = f"{int(last.year)}-{int(last.month):02d}"
        out["argentina"]["yields"] = dict(meal=r1(100 * yld.meal.sum() / yld.crush.sum(), 1), oil=r1(100 * yld.oil.sum() / yld.crush.sum(), 1))
        if p2.exists():
            st = pd.read_csv(p2)
            st["meal"] = st.pellets.fillna(0) + st.expellers.fillna(0)
            # MAGyP stocks are surveyed at the start of the month: stocks dated M = end of month M-1
            t = pd.to_datetime(dict(year=st.year, month=st.month, day=1)) - pd.DateOffset(months=1)
            st["year"], st["month"] = t.dt.year, t.dt.month
            for c, nm in (("meal", "meal_stocks"), ("oil", "oil_stocks"), ("beans", "bean_stocks")):
                m[nm] = monthly_table(st, c, 4, scale=1e6)
            # implied meal disappearance (exports + domestic use) = production + opening - closing stocks
            j = cr[["year", "month", "meal"]].merge(st[["year", "month", "meal"]].rename(columns={"meal": "stk"}), on=["year", "month"])
            j = j.sort_values(["year", "month"])
            j["disp"] = j.meal + j.stk.shift(1) - j.stk
            m["meal_disp"] = monthly_table(j.dropna(), "disp", 4, scale=1e6)
            out["argentina"]["stocks_asof"] = f"{int(st.year.iloc[-1])}-{int(st.month.iloc[-1]):02d}"
        out["argentina"]["monthly"] = m
        out["argentina"]["source"] = "MAGyP (Subsecretaría de Mercados Agropecuarios): molienda de oleaginosas, existencias por provincia"
    return out


def us_fats_oils():
    """NASS Fats & Oils monthly soybean crush, oil and meal production/stocks (after oilseeds_monthly.py nass)."""
    d = {}
    for f in (ROOT / "data" / "grains" / "raw" / "fats_oils").glob("*.csv.gz"):
        d[f.stem.split(".")[0]] = pd.read_csv(f)
    if not d:
        return None
    a = pd.concat(d.values())
    want = {"crush": "SOYBEANS - CRUSHED, MEASURED IN TONS",
            "meal_prod": "CAKE & MEAL, SOYBEAN - PRODUCTION, MEASURED IN TONS",
            "meal_stocks": "CAKE & MEAL, SOYBEAN - STOCKS, MEASURED IN TONS",
            "oil_crude_prod": "OIL, SOYBEAN, CRUDE - PRODUCTION, MEASURED IN LB",
            "oil_stocks_crude": "OIL, SOYBEAN, ONSITE & OFFSITE, CRUDE - STOCKS, MEASURED IN LB",
            "oil_stocks_refined": "OIL, SOYBEAN, ONSITE & OFFSITE, ONCE REFINED - STOCKS, MEASURED IN LB"}
    series, chosen = {}, {}
    for k, sd in want.items():
        x = a[a.short_desc == sd].drop_duplicates(["year", "month"], keep="last")
        if x.empty:
            continue
        chosen[k] = dict(desc=sd, unit=x.unit.iloc[0])
        series[k] = x[["year", "month", "value"]].rename(columns={"value": k})
    if "crush" not in series:
        return dict(found=sorted(a.short_desc.unique())[:200])
    m = None
    for k, v in series.items():
        m = v if m is None else m.merge(v, on=["year", "month"], how="outer")
    m = m.sort_values(["year", "month"])
    if "oil_stocks_crude" in m and "oil_stocks_refined" in m:
        m["oil_stocks"] = m.oil_stocks_crude + m.oil_stocks_refined
        series["oil_stocks"] = m[["year", "month", "oil_stocks"]]
        chosen["oil_stocks"] = dict(desc="crude + once-refined stocks (onsite & offsite)", unit="LB")
        for k in ("oil_stocks_crude", "oil_stocks_refined"):
            series.pop(k); chosen.pop(k)
    out = {"chosen": chosen, "asof": f"{int(m.year.iloc[-1])}-{int(m.month.iloc[-1]):02d}", "monthly": {}}
    # Sep/Aug season; crush in million bu if tons -> convert (60 lb/bu), meal thousand short tons, oil million lb
    conv = {}
    for k, c in chosen.items():
        u = c["unit"].upper()
        conv[k] = (2000 / 60 / 1e6 if "TON" in u else 1 / 60 / 1e6) if k == "crush" else (1 / 1e3 if "TON" in u else 1 / 1e6)
    for k in series:
        out["monthly"][k] = monthly_table(m.assign(**{k: m[k] * conv[k]}), k, 9, n=4, scale=1)
    out["units"] = {k: ("million bu" if k == "crush" else "thousand short tons" if "TON" in chosen[k]["unit"].upper() else "million lb") for k in chosen}
    if "meal_prod" in m and "crush" in m:
        t = m.dropna(subset=["meal_prod", "crush"]).tail(12)
        cb = t.crush.sum() * conv["crush"] * 1e6
        out["meal_yield_lb_bu"] = r1(t.meal_prod.sum() * (2000 if "TON" in chosen["meal_prod"]["unit"].upper() else 1) / cb, 2) if cb else None
    if "oil_crude_prod" in m and "crush" in m:
        t = m.dropna(subset=["oil_crude_prod", "crush"]).tail(12)
        cb = t.crush.sum() * conv["crush"] * 1e6
        out["oil_yield_lb_bu"] = r1(t.oil_crude_prod.sum() / cb, 2) if cb else None
    return out


def basis_band(key, label="Iowa interior"):
    b = json.loads((OUT / "basis.json").read_text()).get(key, [])
    b = next((x for x in b if x["label"] == label), None)
    if not b:
        return None
    by = b["by_year"]
    yrs = sorted(by)
    rows = [(int(y), d, v) for y in yrs[:-1] for d, v in by[y]]
    df = pd.DataFrame(rows, columns=["y", "d", "v"])
    df["w"] = df.d // 7
    q = df.groupby("w").v.quantile([0.1, 0.3, 0.5, 0.7, 0.9]).unstack()
    return dict(label=label, fm=b.get("fm"), as_of=b.get("as_of"), basis=b.get("basis"),
                band=[[int(w) * 7] + [r1(v, 1) for v in r] for w, r in q.iterrows()], cur=by[yrs[-1]], cur_year=yrs[-1])


def nth(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def fnum(v, d=0):
    return "–" if v is None else f"{v:,.{d}f}"


def outlook(p):
    """Rule-based readout of the pack: what the public numbers say, per market. Not a recommendation."""
    out = []
    for c, nm, unit in (("corn", "Corn", "bu/ac"), ("soybeans", "Soybeans", "bu/ac")):
        L = []
        t = p["yields"][c]["table"][-1]
        st = p["yields"][c]["stats"]
        if t.get("oct") and t.get("sep"):
            L.append(f"USDA October yield {t['oct']} {unit} vs {t['sep']} in September ({t['oct_sep']:+.1f}%). Since 2006 the "
                     f"final yield has come in above the October number in {st['pct_up_final_oct']}% of years, average "
                     f"{st['avg_final_oct']:+.2f}%, typical miss ±{st['avg_abs_final_oct']}%.")
        m = p["yields"][c]["maps"][-1] if p["yields"][c]["maps"] else None
        if m:
            top = sorted(m["states"], key=lambda r: -abs(r["impact"] or 0))[:3]
            L.append(f"{m['label']}: national {m['us_prev']} → {m['us']}; biggest state contributions "
                     + ", ".join(f"{r['st']} {r['impact']:+.2f}" for r in top) + " bu/ac.")
        tr = next((r for r in p["yields"][c]["vs_trend"] if r["st"] == "US"), None)
        if tr:
            L.append(f"Current forecast is {tr['dev']:+.1f} bu/ac ({tr['dev_pct']:+.1f}%) vs the 1986+ linear trend ({tr['trend']}).")
        sd = p["sd"].get(c)
        if sd:
            a, b = sd["cols"][-2], sd["cols"][-1]
            L.append(f"{sd['new_crop']} ending stocks {fnum(b['v'].get('end_stocks'))} m bu ({b['label']}) vs "
                     f"{fnum(a['v'].get('end_stocks'))} ({a['label']}); stocks/use {b['v'].get('su')}%.")
        tt = p["tightness"].get(c)
        if tt and tt["price"]:
            rich = "above" if tt["price"] > (tt["fv_usda"] or 0) else "below"
            L.append(f"Price vs tightness ({tt['month']} avg of the new-crop contract, R² {tt['r2']}): USDA S/U {tt['usda_su']}% "
                     f"maps to ${tt['fv_usda']:.2f}; {tt['contract']} at ${tt['price']:.2f} is {rich} it and prices "
                     f"S/U of {tt['mkt_su']}% (market {'tighter' if tt['mkt_su'] < tt['usda_su'] else 'looser'} than USDA).")
        e = p["exports"].get(c)
        if e and e["proj"]:
            pv, lo, hi = e["proj"][-1][1], e["lo"][-1][1], e["hi"][-1][1]
            vs = "above" if pv > (e["usda"] or 0) else "below"
            L.append(f"Export sales week {e['week']}: commitments-based projection {fnum(pv)} m bu (range {fnum(lo)}–{fnum(hi)}) "
                     f"vs USDA {fnum(e['usda'])}, {vs} USDA. YTD commitments {e['ytd'][-1]['commit']} MMT vs "
                     f"{e['ytd'][-2]['commit']} a year ago.")
        k = p["cot"].get(c)
        if k:
            L.append(f"Managed money net {k['last']:+.1f} MMT ({k['wow']:+.1f} w/w), {nth(k['pct'])} percentile since 2006"
                     + (" — crowded long." if k["pct"] >= 85 else " — crowded short." if k["pct"] <= 15 else "."))
        sp = (p["spreads"].get(c) or [None])[0]
        if sp:
            L.append(f"{sp['pair']} spread {sp['current']:+g}c vs a {sp['now_med']:+g}c median at this time of year "
                     f"({nth(sp['pct_rank'])} percentile).")
        out.append(dict(key=c, name=nm, lines=L))
    e = p["exports"].get("wheat")
    if e and e["proj"]:
        L = [f"Export sales week {e['week']}: projection {fnum(e['proj'][-1][1])} m bu vs USDA {fnum(e['usda'])}; "
             + ", ".join(f"{k} {fnum(p['exports'][k]['proj'][-1][1])}" for k in ("HRW", "SRW", "HRS", "White") if p["exports"].get(k) and p["exports"][k]["proj"]) + " m bu by class."]
        sd = p["sd"].get("wheat")
        if sd:
            b = sd["cols"][-1]
            L.append(f"{sd['new_crop']} ending stocks {fnum(b['v'].get('end_stocks'))} m bu, S/U {b['v'].get('su')}% ({b['label']}).")
        k = p["cot"].get("wheat")
        if k:
            L.append(f"Managed money net {k['last']:+.1f} MMT, {nth(k['pct'])} percentile.")
        out.append(dict(key="wheat", name="Wheat", lines=L))
    w = p["world"]["corn"]
    if w["rows"]:
        i = len(w["mys"]) - 1
        big = {r["name"]: r["v"] for r in w["rows"]}
        L = [f"PSD {w['mys'][i]} corn exports: " + ", ".join(f"{n} {big[n][i]}" for n in ("United States", "Brazil", "Argentina", "Ukraine") if n in big)
             + f" MMT; world {w['world'][i]} MMT. Imports ex EU/China {w['yoy_imports'][i]:+.1f}% y/y."]
        b = p["brazil"]["corn"]
        L.append("Brazil corn exports (Sep/Aug, Comex Stat) by season: " + ", ".join(f"{m} {b['totals'][k]}" for m, k in zip(b["mys"], b["totals"])) + " MMT (latest season in progress).")
        out.append(dict(key="world", name="World & South America", lines=L))
    L = []
    sa = p.get("sa_soy") or {}
    am = (sa.get("argentina") or {}).get("monthly")
    if am:
        c = am["crush"]; s1, s0 = c["seasons"][-1], c["seasons"][-2]
        n = sum(v is not None for v in c["values"][s1])
        a1, a0 = sum(v or 0 for v in c["values"][s1][:n]), sum(v or 0 for v in c["values"][s0][:n])
        ms = am["meal_stocks"]; v = [x for x in ms["values"][ms["seasons"][-1]] if x is not None]
        L.append(f"Argentina soybean crush {s1} through month {n} of the Apr/Mar season: {a1:.1f} Mt vs {a0:.1f} a year earlier "
                 f"({100 * (a1 / a0 - 1):+.0f}%, MAGyP)." + (f" Meal stocks {v[-1]:.2f} Mt at the latest month-end." if v else ""))
    bm = (sa.get("brazil") or {}).get("monthly")
    if bm:
        e = bm["exports"]["soybeans"]; s1, s0 = e["seasons"][-1], e["seasons"][-2]
        n = sum(x is not None for x in e["values"][s1])
        a1, a0 = sum(x or 0 for x in e["values"][s1][:n]), sum(x or 0 for x in e["values"][s0][:n])
        L.append(f"Brazil soybean exports Jan–{MONTHS[n - 1][:3]} {s1}: {a1:.1f} Mt vs {a0:.1f} in {s0} ({100 * (a1 / a0 - 1):+.0f}%, Comex Stat).")
    us = p.get("us_fo") or {}
    if us.get("monthly"):
        c = us["monthly"]["crush"]; s1, s0 = c["seasons"][-1], c["seasons"][-2]
        n = sum(x is not None for x in c["values"][s1])
        a1, a0 = sum(x or 0 for x in c["values"][s1][:n]), sum(x or 0 for x in c["values"][s0][:n])
        L.append(f"US soybean crush {s1} season-to-date ({n} month{'s' if n > 1 else ''}, NASS to {us['asof']}): {a1:.0f} m bu vs {a0:.0f} a year earlier "
                 f"({100 * (a1 / a0 - 1):+.1f}%); meal yield {us.get('meal_yield_lb_bu')} lb/bu, oil {us.get('oil_yield_lb_bu')} lb/bu (trailing 12 months).")
    if L:
        out.append(dict(key="soycx", name="Soybean complex: Brazil, Argentina, US crush", lines=L))
    return out


def main():
    import os
    reps = crop_reports()
    cur_year = max(y for y, _ in reps["corn"]) if reps["corn"] else date.today().year
    pack = dict(generated=date.today().isoformat(), crop_year=cur_year)
    pack["yields"] = {c: yields_section(reps, c, cur_year) for c in ("corn", "soybeans")}
    wd = {}
    for k in ("corn", "soybeans", "wheat", "meal", "oil"):
        try:
            wd[k] = wasde_frame(k)
        except Exception as e:
            print("wasde", k, e)
    pack["sd"] = {k: sd_section(k, wd[k]) for k in wd}
    pack["revisions"] = {k: revisions_section(wd[k]) for k in ("corn", "soybeans") if k in wd}
    pack["exports"] = {}
    for n in ESR:
        try:
            pack["exports"][n] = export_section(n, wd)
        except Exception as e:
            print("export", n, e)
    cond = json.loads((OUT / "condition.json").read_text())
    pack["condition"] = {c: cond[c]["model"] for c in ("corn", "soybeans") if c in cond}
    zc, zs = contracts("ZC"), contracts("ZS")
    pack["tightness"] = {"corn": tightness_section("corn", "ZC", "Z", 11, wd["corn"], zc),
                         "soybeans": tightness_section("soybeans", "ZS", "X", 10, wd["soybeans"], zs)}
    pack["spreads"] = {"corn": spreads_section("ZC", [("Z", 0, "Z", 1), ("H", 1, "Z", 1), ("K", 1, "Z", 1), ("N", 1, "Z", 1), ("Z", 1, "Z", 2)], zc),
                       "soybeans": spreads_section("ZS", [("X", 0, "X", 1), ("F", 1, "X", 1), ("H", 1, "X", 1), ("K", 1, "X", 1), ("N", 1, "X", 1), ("X", 1, "X", 2)], zs)}
    pack["decdec"] = {"corn": dec_dec("ZC", "Z", zc), "soybeans": dec_dec("ZS", "X", zs)}
    pack["cot"] = {"corn": cot_mmt("ZC", 39.368), "soybeans": cot_mmt("ZS", 36.744), "wheat": cot_mmt("ZW", 36.744)}
    pack["world"] = {"corn": world_corn(), "wheat": world_wheat()}
    pack["brazil"] = brazil_corn()
    pack["basis"] = {k: basis_band(k) for k in ("corn", "soybeans")}
    try:
        pack["sa_soy"] = south_america_soy()
    except Exception as e:
        print("sa_soy", e)
    try:
        pack["us_fo"] = us_fats_oils()
    except Exception as e:
        print("us_fo", e)
    pack["outlook"] = outlook(pack)
    pack["missing"] = [
        "Trade-poll surprise (no free analyst poll): shown instead as USDA's own Sep→Oct revision",
        "Seeding-company and other private yield estimates, and the report owner's own balance columns (add a desk column later)",
        "FOB and C&F prices, Matif premiums, Asia feed-wheat vs corn matrix (paid price feeds)",
        "Black Sea / Azov port line-ups, war-strike counts, Polymarket odds (not grains-desk data)",
        "Russian/Ukrainian/EU monthly wheat exports and French FranceAgriMer balance (not collected yet)",
        "Argentine monthly meal exports (shown as implied disappearance) and truck deliveries to ports",
        "Brazil monthly crush and stocks and the ABIOVE balance (members-only); US crush utilization (NOPA capacity is members-only)"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pack.json").write_text(json.dumps(pack, separators=(",", ":"), default=lambda o: None if o is None else str(o)))
    print("pack.json", round((OUT / "pack.json").stat().st_size / 1e3), "KB")


if __name__ == "__main__":
    main()
