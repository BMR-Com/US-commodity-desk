"""Seasonality for every desk market (grains & oilseeds, cotton, livestock, dairy, energy).

Per market:
  - roll-switch trade: buy (or sell) the next contract 5 business days before the front contract's desk roll date
    (first position / notice day for physical contracts, last trading day for cash-settled ones), hold 10 or 21 days
  - each contract's return by calendar month before expiry (heat map)
  - front-month return and first three calendar spreads by calendar month, by year
  - seasonal path of the rolled front contract through the season: marketing year for crops
    (corn/soy complex Sep-Aug, wheat Jun-May, cotton Aug-Jul), calendar year for livestock, dairy and energy
  - seasonal chart of each upcoming contract and its spread to the next one, aligned on weeks before its roll date
  - a list of seasonal rules that pass the screen, with their next dates

Input : data/contracts/<SYM>.csv (TradingView daily closes of every contract, pipelines/contracts.py)
Output: data/seasonal/<SYM>.json (market detail), data/seasonal/summary.json (rule list, market index)
"""
import json, sys, datetime as dt, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "models"))
from contract_calendar import MKT as CAL, CODES, prev_bd  # noqa: E402

OUT = ROOT / "data" / "seasonal"
MC = {c: i + 1 for i, c in enumerate(CODES)}
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NAME = {c: MON[m - 1] for c, m in MC.items()}
GROUP = {"ZC": "Grains & oilseeds", "ZS": "Grains & oilseeds", "ZM": "Grains & oilseeds", "ZL": "Grains & oilseeds", "ZW": "Grains & oilseeds",
         "KE": "Grains & oilseeds", "CT": "Cotton", "LE": "Livestock", "GF": "Livestock", "HE": "Livestock", "DC": "Dairy", "GDK": "Dairy",
         "CSC": "Dairy", "CB": "Dairy", "GNF": "Dairy", "DY": "Dairy", "CL": "Energy", "NG": "Energy", "HO": "Energy", "RB": "Energy"}
# $ per 1.00 of quoted price, unit, first month of the season (crops: marketing year; others: calendar year)
SPEC = {"ZC": (50, "¢/bu", 9), "ZS": (50, "¢/bu", 9), "ZM": (100, "$/st", 9), "ZL": (600, "¢/lb", 9), "ZW": (50, "¢/bu", 6), "KE": (50, "¢/bu", 6),
        "CT": (500, "¢/lb", 8), "LE": (400, "¢/lb", 1), "GF": (500, "¢/lb", 1), "HE": (400, "¢/lb", 1), "DC": (2000, "$/cwt", 1), "GDK": (2000, "$/cwt", 1),
        "CSC": (20000, "$/lb", 1), "CB": (200, "¢/lb", 1), "GNF": (440, "¢/lb", 1), "DY": (440, "¢/lb", 1), "CL": (1000, "$/bbl", 1),
        "NG": (10000, "$/MMBtu", 1), "HO": (42000, "$/gal", 1), "RB": (42000, "$/gal", 1)}
CYCLE_OVERRIDE = {"CT": "HKNZ"}          # desk ignores October cotton
SPLIT = 2016


def load(sym):
    d = pd.read_csv(ROOT / "data" / "contracts" / f"{sym}.csv")
    P = {}
    n = len(sym)
    for c, g in d.groupby("contract"):
        code, yr = c[n], int(c[n + 1:])
        idx = pd.to_datetime(g.date)
        idx = idx + pd.to_timedelta((idx.dt.dayofweek == 6).astype(int), unit="D") + pd.to_timedelta((idx.dt.dayofweek == 5).astype(int) * 2, unit="D")
        x = pd.Series(g.close.values.astype(float), index=idx.values).sort_index()
        x = x[~x.index.duplicated(keep="last")]
        x = x[x > 0] if sym not in ("CL",) else x
        med = x.rolling(11, center=True, min_periods=3).median()
        x = x[((x - med).abs() <= 0.2 * med.abs().clip(lower=1e-9)) | (med.abs() < 1e-9)]
        P[(code, yr)] = x
    return P


class Market:
    def __init__(self, sym):
        self.sym = sym
        self.name, rule, letters, self.kind, _ = CAL[sym]
        self.cyc = CYCLE_OVERRIDE.get(sym, letters or CODES)
        self.mult, self.unit, self.y0 = SPEC[sym]
        P = load(sym)
        self.P = {k: v for k, v in P.items() if k[0] in self.cyc and len(v) > 20}
        self.cal = pd.DatetimeIndex(sorted(set().union(*[set(s.index) for s in self.P.values()])))
        self.roll = {}
        for k in list(self.P) + [(c, y) for c in self.cyc for y in range(pd.Timestamp.now().year, pd.Timestamp.now().year + 3)]:
            try:
                self.roll[k] = pd.Timestamp(rule(pd.Period(year=k[1], month=MC[k[0]], freq="M"))["out_by"])
            except Exception:
                pass
        self.first_year = max(min(k[1] for k in self.P), self.cal[0].year + 1)
        self.min_n = 12 if pd.Timestamp.now().year - self.first_year >= 15 else 9

    def nxt(self, k, j=1):
        i = self.cyc.index(k[0]) + j
        return (self.cyc[i % len(self.cyc)], k[1] + i // len(self.cyc))

    def px(self, k, t):
        s = self.P.get(k)
        if s is None:
            return np.nan
        i = s.index.searchsorted(t, side="right") - 1
        return s.iloc[i] if i >= 0 and (t - s.index[i]).days <= 5 else np.nan

    def label(self, k):
        return f"{NAME[k[0]]} {k[1]}"

    def front_for(self, t):
        c = [k for k in self.roll if self.roll[k] > t and k in self.P]
        return min(c, key=lambda k: self.roll[k]) if c else None

    def season(self, t):
        return t.year if t.month >= self.y0 else t.year - 1


def stats(v):
    v = pd.Series(v, dtype=float).dropna(); n = len(v)
    if n < 3:
        return dict(n=n)
    sd = v.std(ddof=1)
    return dict(n=n, avg=v.mean(), med=v.median(), hit=(v > 0).mean(), t=v.mean() / (sd / np.sqrt(n)) if sd > 0 else np.nan, worst=v.min(), best=v.max())


def consistency(years, vals, sgn):
    y = np.asarray(years); v = sgn * np.asarray(vals, dtype=float); ok = ~np.isnan(v); y, v = y[ok], v[ok]
    e, l = v[y < SPLIT], v[y >= SPLIT]; last10 = v[np.argsort(y)][-10:]
    return dict(early_avg=e.mean() if len(e) else np.nan, late_avg=l.mean() if len(l) else np.nan,
                hit_last10=round(100 * (last10 > 0).mean()) if len(last10) else None)


def roll_switch(m, back=5, holds=(10, 21)):
    rows = []
    for P_ in sorted(m.P, key=lambda k: (k[1], MC[k[0]])):
        C = m.nxt(P_)
        if C not in m.P or P_ not in m.roll or P_[1] < m.first_year:
            continue
        f = m.roll[P_]
        if f > m.cal[-1]:
            continue
        i = m.cal.searchsorted(f)
        if i - back < 0:
            continue
        e = m.cal[i - back]
        for h in holds:
            if i - back + h >= len(m.cal):
                continue
            x = m.cal[i - back + h]; a, b = m.px(C, e), m.px(C, x)
            if pd.isna(a) or pd.isna(b) or a <= 0:
                continue
            rows.append(dict(contract=C[0], prev=P_[0], year=C[1], hold=h, ret=b / a - 1, chg=b - a, usd=(b - a) * m.mult))
    return pd.DataFrame(rows)


def month_ends(m):
    me = pd.Series(m.cal, index=m.cal).groupby([m.cal.year, m.cal.month]).max()
    return {k: v for k, v in me.items()}


def contract_months(m, ME):
    rows = []
    for k in m.P:
        if k[1] < m.first_year + 1 or k not in m.roll:
            continue
        stop = m.roll[k]
        for back in range(1, 13):
            t = pd.Timestamp(k[1], MC[k[0]], 1) - pd.DateOffset(months=back)
            end = ME.get((t.year, t.month)); pt = t - pd.DateOffset(months=1); start = ME.get((pt.year, pt.month))
            if end is None or start is None:
                continue
            end = min(end, stop)
            if end <= start:
                continue
            a, b = m.px(k, start), m.px(k, end)
            if pd.isna(a) or pd.isna(b) or a <= 0:
                continue
            rows.append(dict(contract=k[0], year=k[1], cal_month=t.month, cal_year=t.year, back=back, ret=b / a - 1))
    return pd.DataFrame(rows)


def front_and_spreads(m, ME):
    rows = []; keys = sorted(ME)
    for i in range(1, len(keys)):
        (y, mo), (py, pm) = keys[i], keys[i - 1]
        if y < m.first_year:
            continue
        start, end = ME[(py, pm)], ME[(y, mo)]
        f = m.front_for(end)
        if f is None:
            continue
        chain = [f, m.nxt(f, 1), m.nxt(f, 2), m.nxt(f, 3)]
        p0 = [m.px(k, start) for k in chain]; p1 = [m.px(k, end) for k in chain]
        r = dict(year=y, month=mo, ret=(p1[0] / p0[0] - 1) if p0[0] and p0[0] > 0 and not (pd.isna(p0[0]) or pd.isna(p1[0])) else np.nan)
        for j in (1, 2, 3):
            r[f"s{j}"] = (p1[j - 1] - p1[j]) - (p0[j - 1] - p0[j])
            r[f"s{j}_pair"] = f"{NAME[chain[j - 1][0]]}/{NAME[chain[j][0]]}"
        rows.append(r)
    return pd.DataFrame(rows)


def front_path(m, today):
    """daily rolled front contract (roll at the desk roll date), cumulative % from the start of each season"""
    rows = []
    days = m.cal[m.cal >= pd.Timestamp(m.first_year, 1, 1)]
    prev_t, prev_k = None, None
    for t in days:
        k = m.front_for(t if prev_t is None else prev_t)   # contract held over (prev_t, t]
        if prev_t is not None and k is not None:
            a, b = m.px(k, prev_t), m.px(k, t)
            if not (pd.isna(a) or pd.isna(b)) and a > 0:
                rows.append((t, np.log(b / a)))
        prev_t = t
    s = pd.Series(dict(rows)).sort_index()
    s = s[s.abs() < 0.4]
    df = pd.DataFrame(dict(r=s)); df["season"] = [m.season(t) for t in df.index]
    start = lambda yr: pd.Timestamp(yr, m.y0, 1)
    df["wk"] = [min(51, int((t - start(y)).days // 7)) for t, y in zip(df.index, df.season)]
    by = {}
    for y, g in df.groupby("season"):
        c = (np.exp(g.r.cumsum()) - 1) * 100
        w = c.groupby(g.wk).last()
        by[int(y)] = w
    cur = m.season(today)
    hist = [y for y in by if y < cur and y >= m.first_year and by[y].index.max() >= 50 and by[y].index.min() <= 1]
    A = pd.DataFrame({y: by[y].reindex(range(52)).ffill() for y in hist}).T
    bands = {q: [[int(w), round(float(v), 2)] for w, v in A.quantile(q / 100).items() if not np.isnan(v)] for q in (10, 25, 50, 75, 90)}
    avg = A.mean(); avg5 = A.tail(5).mean()
    pts = lambda ser: [[int(w), round(float(v), 2)] for w, v in ser.items() if not np.isnan(v)]
    # average path's best and worst stretches (for the text)
    return dict(start_month=MON[m.y0 - 1], season_label=("Marketing year" if m.y0 != 1 else "Calendar year"),
                current=pts(by.get(cur, pd.Series(dtype=float))), last_year=pts(by.get(cur - 1, pd.Series(dtype=float))),
                avg=pts(avg), avg5=pts(avg5), bands=bands, n_years=len(hist), first_year=min(hist) if hist else None, season=cur,
                by_year={int(y): round(float(by[y].iloc[-1]), 1) for y in hist[-12:]})


def seas_series(m, kind, code, today):
    by_year = {}
    for k in m.P:
        if k[0] != code or k not in m.roll:
            continue
        f = m.roll[k]; other = m.nxt(k) if kind == "sp" else None
        if kind == "sp" and other not in m.P:
            continue
        vals = []
        for w in range(0, 53):
            t = f - pd.Timedelta(days=7 * w + 1)
            if t > today:
                vals.append(None); continue
            a = m.px(k, t)
            v = a - m.px(other, t) if kind == "sp" else a
            vals.append(None if pd.isna(v) else round(float(v), 4))
        by_year[k[1]] = vals
    fut = [y for y in by_year if (code, y) in m.roll and m.roll[(code, y)] > today]
    if not fut:
        return None
    cur = min(fut); hist = [y for y in sorted(by_year) if y < cur and y >= m.first_year + 1]
    if len(hist) < 5:
        return None
    A = np.array([[np.nan if v is None else v for v in by_year[y]] for y in hist], dtype=float)
    bands = {q: [[w, round(float(v), 4)] for w, v in enumerate(np.nanpercentile(A, q, axis=0)) if not np.isnan(v)] for q in (10, 25, 50, 75, 90)}
    avg5 = np.nanmean(A[-5:], axis=0)
    pts = lambda arr: [[w, v] for w, v in enumerate(arr) if v is not None and not (isinstance(v, float) and np.isnan(v))]
    k = (code, cur)
    nm = m.label(k) if kind == "px" else f"{NAME[code]}/{NAME[m.nxt(k)[0]]} {cur}"
    now_w = next((w for w, v in enumerate(by_year[cur]) if v is not None), None)
    now_v = by_year[cur][now_w] if now_w is not None else None
    same = [r[now_w] for r in A if now_w is not None and not np.isnan(r[now_w])]
    return dict(key=f"{kind}-{code}{cur}", kind=kind, code=code, label=nm, roll=str(m.roll[k].date()),
                current=pts(by_year[cur]), last_year=pts(by_year.get(cur - 1, [])),
                avg5=[[w, round(float(v), 4)] for w, v in enumerate(avg5) if not np.isnan(v)], bands=bands,
                now=now_v, wk_now=now_w, pct_same_time=(round(100 * np.mean([s < now_v for s in same])) if same and now_v is not None else None),
                n_years=len(hist), first_year=hist[0])


def next_window(m, kind, row, today):
    if kind == "roll":
        P_ = [k for k in m.roll if k[0] == row["prev"] and m.roll[k] > today + pd.Timedelta(days=7)]
        if not P_:
            return None
        P_ = min(P_, key=lambda k: m.roll[k]); f = m.roll[P_]
        e = prev_bd(f, 5); x = e + pd.offsets.BDay(int(row["hold"]))
        return e.date(), x.date(), m.label(m.nxt(P_))
    y = today.year + (1 if row["month"] < today.month or (row["month"] == today.month and today.day > 3) else 0)
    s = prev_bd(pd.Timestamp(y, row["month"], 1)); e = pd.Timestamp(y, row["month"], 1) + pd.offsets.MonthEnd(0)
    return s.date(), e.date(), None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) or np.isinf(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def build(sym, min_hit=70, min_t=2.0):
    m = Market(sym); today = m.cal[-1]; ME = month_ends(m)
    F, C, S = roll_switch(m), contract_months(m, ME), front_and_spreads(m, ME)
    order = [((m.y0 - 1 + i) % 12) + 1 for i in range(12)]
    done_m = lambda y, mo: (y < today.year) or (y == today.year and mo < today.month)
    Cd = C[[done_m(y, mo) for y, mo in zip(C.cal_year, C.cal_month)]] if len(C) else C
    hm = {}
    for code in m.cyc:
        row = {}
        for back in range(12, 0, -1):
            g = Cd[(Cd.contract == code) & (Cd.back == back)] if len(Cd) else Cd
            if len(g) < m.min_n:
                continue
            mo = int(g.cal_month.iloc[0]); st = stats(g.ret)
            row[MON[mo - 1]] = dict(avg=round(st["avg"] * 100, 2), hit=round(st["hit"] * 100), n=st["n"])
        hm[code] = row
    Sd = S[[done_m(y, mo) or (y == today.year and mo == today.month) for y, mo in zip(S.year, S.month)]]
    Sc = S[[done_m(y, mo) for y, mo in zip(S.year, S.month)]]
    # front grid by season (rows = season, columns in season order)
    grid = {}
    for r in Sd.itertuples():
        sy = r.year if r.month >= m.y0 else r.year - 1
        grid.setdefault(int(sy), {})[MON[r.month - 1]] = None if pd.isna(r.ret) else round(r.ret * 100, 1)
    favg = {MON[mo - 1]: dict(avg=round(g.ret.mean() * 100, 2), hit=round((g.ret > 0).mean() * 100), n=int(g.ret.notna().sum())) for mo, g in Sc.groupby("month")}
    sp = {f"s{j}": {MON[mo - 1]: dict(avg=round(g[f"s{j}"].mean(), 4), hit=round((g[f"s{j}"] > 0).mean() * 100), n=int(g[f"s{j}"].notna().sum()),
                                      pair=g[f"s{j}_pair"].mode().iloc[0]) for mo, g in Sc.groupby("month")} for j in (1, 2, 3)}
    fs = []
    for (code, h), g in (F.groupby(["contract", "hold"]) if len(F) else []):
        st = stats(g.ret)
        if st["n"] < m.min_n:
            continue
        fs.append(dict(contract=NAME[code], prev=NAME[g.prev.iloc[0]], hold=int(h), n=st["n"], hit=round(st["hit"] * 100), avg=round(st["avg"] * 100, 2),
                       usd=round(g.usd.mean()), worst=round(st["worst"] * 100, 1), last5=[round(x * 100, 1) for x in g.sort_values("year").ret.tail(5)]))
    trades = []
    for (code, h), g in (F.groupby(["contract", "hold"]) if len(F) else []):
        st = stats(g.ret)
        if st["n"] < m.min_n:
            continue
        side = "Long" if st["avg"] > 0 else "Short"; sgn = 1 if side == "Long" else -1; hit = st["hit"] if sgn > 0 else 1 - st["hit"]
        nw = next_window(m, "roll", dict(prev=g.prev.iloc[0], hold=h), today)
        trades.append(dict(sym=sym, market=m.name, group=GROUP[sym], family="Roll switch", side=side,
                           what=f"{side} {NAME[code]} from 5 days before the {NAME[g.prev.iloc[0]]} roll date, hold {h} days",
                           hit=round(hit * 100), avg_pct=round(sgn * st["avg"] * 100, 2), usd=round(sgn * g.usd.mean()), n=st["n"],
                           worst_pct=round(min(sgn * g.ret) * 100, 1), last5=[round(sgn * r * 100, 1) for r in g.sort_values("year").ret.tail(5)], t=st["t"] * sgn,
                           next_entry=str(nw[0]) if nw else None, next_exit=str(nw[1]) if nw else None, contract=nw[2] if nw else None,
                           **consistency(g.year.values, g.ret.values, sgn)))
    for mo, g in Sc.groupby("month"):
        for col, fam in [("ret", "Front month")] + [(f"s{j}", f"Spread {j}") for j in (1, 2, 3)]:
            v = g[col].dropna(); st = stats(v)
            if st["n"] < m.min_n or not st.get("avg"):
                continue
            sgn = 1 if st["avg"] > 0 else -1; hit = st["hit"] if sgn > 0 else 1 - st["hit"]
            side = ("Long" if sgn > 0 else "Short") if col == "ret" else ("Bull spread (buy front)" if sgn > 0 else "Bear spread (sell front)")
            pair = "" if col == "ret" else g[f"{col}_pair"].mode().iloc[0]
            nw = next_window(m, "month", dict(month=mo), today)
            trades.append(dict(sym=sym, market=m.name, group=GROUP[sym], family=fam, side=side,
                               what=(f"{side} front month in {MON[mo - 1]}" if col == "ret" else f"{side} {pair} in {MON[mo - 1]}"),
                               hit=round(hit * 100), avg_pct=round(sgn * st["avg"] * 100, 2) if col == "ret" else None,
                               avg_chg=None if col == "ret" else round(sgn * st["avg"], 4), usd=None if col == "ret" else round(sgn * v.mean() * m.mult),
                               n=st["n"], worst_pct=round(min(sgn * v) * 100, 1) if col == "ret" else None,
                               worst_chg=None if col == "ret" else round(min(sgn * v), 4),
                               last5=[round(sgn * x * (100 if col == "ret" else 1), 3) for x in g.sort_values("year")[col].dropna().tail(5)],
                               t=st["t"] * sgn, next_entry=str(nw[0]), next_exit=str(nw[1]), contract=None, month=MON[mo - 1],
                               **consistency(g.year.values, g[col].values, sgn)))
    T = pd.DataFrame(trades)
    keep = T[(T.hit >= min_hit) & (T.t >= min_t) & (T.early_avg > 0) & (T.late_avg > 0)].sort_values(["hit", "t"], ascending=False) if len(T) else T
    # seasonal charts: next contracts (all of a 4-5 month cycle, the next 6 for monthly contracts)
    upcoming = sorted([k for k in m.roll if m.roll[k] > today and k[0] in m.cyc], key=lambda k: m.roll[k])[: (6 if len(m.cyc) > 8 else len(m.cyc))]
    seas = [z for k in upcoming for kind in ("px", "sp") for z in [seas_series(m, kind, k[0], today)] if z]
    out = dict(sym=sym, name=m.name, group=GROUP[sym], unit=m.unit, mult=m.mult, as_of=str(today.date()), first_year=m.first_year,
               season_start=MON[m.y0 - 1], season_kind=("Marketing year" if m.y0 != 1 else "Calendar year"), month_order=[MON[i - 1] for i in order],
               cycle=[NAME[c] for c in m.cyc], contract_heat=hm, front_grid=grid, front_avg=favg, spread_heat=sp, roll_switch=fs,
               path=front_path(m, today), seasonal=seas,
               trades=[{k: v for k, v in r.items() if k not in ("t", "early_avg", "late_avg")} for r in keep.to_dict("records")])
    return clean(out), T


def main():
    syms = sys.argv[1:] or list(GROUP)
    OUT.mkdir(parents=True, exist_ok=True)
    summ = dict(generated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), markets=[], trades=[])
    old = OUT / "summary.json"
    prev = json.loads(old.read_text()) if old.exists() else {}
    allT = []
    for s in syms:
        try:
            o, T = build(s)
        except Exception as e:
            print(s, "FAILED", repr(e)[:200]); continue
        (OUT / f"{s}.json").write_text(json.dumps(o, separators=(",", ":")))
        summ["markets"].append(dict(sym=s, name=o["name"], group=o["group"], as_of=o["as_of"], n_rules=len(o["trades"]), season_kind=o["season_kind"]))
        summ["trades"] += o["trades"]; allT.append(T)
        print(f"{s}: {len(T)} rules tested, {len(o['trades'])} kept, {(OUT / f'{s}.json').stat().st_size / 1024:.0f} KB")
    if len(sys.argv) > 1 and prev:   # partial run: keep the other markets
        done = {m["sym"] for m in summ["markets"]}
        summ["markets"] += [m for m in prev.get("markets", []) if m["sym"] not in done]
        summ["trades"] += [t for t in prev.get("trades", []) if t["sym"] not in done]
    summ["trades"].sort(key=lambda t: (t.get("next_entry") or "9999"))
    old.write_text(json.dumps(clean(summ), separators=(",", ":")))
    if allT:
        pd.concat(allT).to_csv("/tmp/seasonal_desk_all_rules.csv", index=False)


if __name__ == "__main__":
    main()
