#!/usr/bin/env python3
"""Volatility stats and option-pricer inputs for every futures market on the desk.

From data/ohlc/<SYM>.csv (Yahoo daily bars per contract, continuous front for long history):
- per live contract: last price and date, close-to-close realized vol over 10/20/30/60/90 trading days and a
  Parkinson (high-low) 20-day estimate, annualized with 252 days; estimated option expiry and days left;
- per market (continuous front): 20-day vol percentile over 1/5 years, a vol cone (10..120-day windows: now vs
  10th/50th/90th percentile over 5 years) and the median 20-day vol by calendar month (seasonality);
- contract specs for the pricer: multiplier ($ per 1 price unit), unit, strike step;
- the risk-free rate (13-week T-bill, Yahoo ^IRX) for Black-76.
Implied vol is not in free data for CME ags options; realized vol is the default input (editable in the page).
Option expiries follow the exchange rules approximately (holidays ignored). Writes data/vol/vol.json.
"""
import json, math
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data"
MON = "FGHJKMNQUVXZ"
MNAME = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# sym: name, group, unit, $ per 1 unit of price, strike step, decimals, expiry rule
SPEC = {
    "ZC": ("Corn", "Grains & oilseeds", "¢/bu", 50, 5, 2, "grain"), "ZS": ("Soybeans", "Grains & oilseeds", "¢/bu", 50, 10, 2, "grain"),
    "ZM": ("Soybean meal", "Grains & oilseeds", "$/short ton", 100, 5, 1, "grain"), "ZL": ("Soybean oil", "Grains & oilseeds", "¢/lb", 600, 0.5, 2, "grain"),
    "ZW": ("Chicago wheat", "Grains & oilseeds", "¢/bu", 50, 5, 2, "grain"), "KE": ("KC HRW wheat", "Grains & oilseeds", "¢/bu", 50, 5, 2, "grain"),
    "CT": ("Cotton", "Softs", "¢/lb", 500, 1, 2, "cotton"),
    "LE": ("Live cattle", "Livestock", "¢/lb", 400, 1, 3, "le"), "GF": ("Feeder cattle", "Livestock", "¢/lb", 500, 1, 3, "gf"),
    "HE": ("Lean hogs", "Livestock", "¢/lb", 400, 1, 3, "he"),
    "DC": ("Class III milk", "Dairy", "$/cwt", 2000, 0.25, 2, "dairy"), "GDK": ("Class IV milk", "Dairy", "$/cwt", 2000, 0.25, 2, "dairy"),
    "CSC": ("Cheese (cash-settled)", "Dairy", "$/lb", 20000, 0.01, 3, "dairy"), "CB": ("Butter (cash-settled)", "Dairy", "¢/lb", 200, 1, 2, "dairy"),
    "GNF": ("Nonfat dry milk", "Dairy", "¢/lb", 440, 1, 2, "dairy"), "DY": ("Dry whey", "Dairy", "¢/lb", 440, 1, 2, "dairy"),
}
RULE_TEXT = {"grain": "last Friday at least 2 business days before the last business day of the month before the contract month",
             "cotton": "last Friday at least 5 business days before the last business day of the month before the contract month",
             "le": "first Friday of the contract month", "gf": "last Thursday of the contract month (same as futures)",
             "he": "10th business day of the contract month (same as futures)",
             "dairy": "business day before the USDA class/product price announcement (about the first Wednesday after the contract month)"}


def bdays_back(d, n):
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def last_bday(y, m):
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expiry(rule, y, m):
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    if rule in ("grain", "cotton"):
        lim = bdays_back(last_bday(py, pm), 2 if rule == "grain" else 5)
        d = lim
        while d.weekday() != 4:
            d -= timedelta(days=1)
        return d
    if rule == "le":
        d = date(y, m, 1)
        while d.weekday() != 4:
            d += timedelta(days=1)
        return d
    if rule == "gf":
        d = last_bday(y, m)
        while d.weekday() != 3:
            d -= timedelta(days=1)
        return d
    if rule == "he":
        d, n = date(y, m, 1), 0
        while True:
            if d.weekday() < 5:
                n += 1
                if n == 10:
                    return d
            d += timedelta(days=1)
    if rule == "dairy":
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        d = date(ny, nm, 1)
        while d.weekday() != 2:
            d += timedelta(days=1)
        return bdays_back(d, 1)
    return last_bday(y, m)


def hv(c, n, clean=False):
    """Annualized close-to-close vol (%). clean=True drops roll gaps in a continuous series: returns beyond
    4 trailing 60-day standard deviations (this also drops a few genuine limit moves, a small downward bias)."""
    r = np.log(c).diff()
    if clean:
        sd = r.rolling(60, min_periods=20).std().shift(1)
        r = r.where(~(r.abs() > 4 * sd))
    return r.rolling(n, min_periods=int(n * 0.8)).std() * math.sqrt(252) * 100


def is_daily(s):
    return pd.Series(s.index).diff().dt.days.tail(60).median() <= 3


def pct_rank(v, s):
    s = s.dropna()
    return None if v is None or len(s) < 20 or np.isnan(v) else round(float((s < v).mean() * 100))


def main():
    mk = json.loads((D / "markets/markets.json").read_text()) if (D / "markets/markets.json").exists() else {"items": []}
    irx = next((x["last"] for x in mk["items"] if x["sym"] == "^IRX"), None)
    today = date.today()
    out = {}
    for sym, (name, group, unit, mult, step, dp, rule) in SPEC.items():
        p = D / "ohlc" / f"{sym}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["date"] = pd.to_datetime(df.date)
        cont = df[df.series == "cont"].set_index("date").sort_index()
        c = cont.close.dropna()
        c = c[c > 0]
        h20 = hv(c, 20, True)
        last5 = h20[h20.index >= h20.index[-1] - pd.Timedelta(days=5 * 365)]
        last1 = h20[h20.index >= h20.index[-1] - pd.Timedelta(days=365)]
        cone = []
        for n in (10, 20, 30, 60, 90, 120):
            s = hv(c, n, True)
            s5 = s[s.index >= s.index[-1] - pd.Timedelta(days=5 * 365)].dropna()
            if len(s5) > 50:
                cone.append({"n": n, "now": round(float(s.iloc[-1]), 1), "p10": round(float(s5.quantile(.1)), 1), "p50": round(float(s5.median()), 1),
                             "p90": round(float(s5.quantile(.9)), 1), "min": round(float(s5.min()), 1), "max": round(float(s5.max()), 1)})
        seas = last5.groupby(last5.index.month).median() if len(last5) else pd.Series(dtype=float)
        contracts = []
        for code in [s for s in df.series.unique() if s != "cont"]:
            g = df[df.series == code].set_index("date").sort_index()
            cc = g.close.dropna()
            cc = cc[cc > 0]
            if len(cc) < 5 or not is_daily(cc):
                continue
            m, y = MON.index(code[-5]) + 1, int(code[-4:])
            ex = expiry(rule, y, m)
            if ex < today:
                continue
            row = {"code": code, "label": f"{MNAME[m - 1]} {str(y)[2:]}", "last": round(float(cc.iloc[-1]), 4), "date": cc.index[-1].date().isoformat(),
                   "chg": round(float(cc.iloc[-1] - cc.iloc[-2]), 4) if len(cc) > 1 else None, "expiry": ex.isoformat(), "dte": (ex - today).days}
            for n in (10, 20, 30, 60, 90):
                v = hv(cc, n).iloc[-1] if len(cc) > n + 1 else np.nan
                row[f"hv{n}"] = None if np.isnan(v) else round(float(v), 1)
            hl = np.log(g.high / g.low).dropna()
            hl = hl[hl > 0]
            row["park20"] = round(float(math.sqrt((hl.iloc[-20:] ** 2).mean() / (4 * math.log(2))) * math.sqrt(252) * 100), 1) if len(hl) >= 20 else None
            row["vol"] = row["hv20"] or row["hv30"] or (cone[1]["now"] if len(cone) > 1 else None)
            contracts.append(row)
        contracts.sort(key=lambda r: r["expiry"])
        now20 = float(h20.iloc[-1]) if len(h20) else None
        out[sym] = {"name": name, "group": group, "unit": unit, "mult": mult, "step": step, "dp": dp, "expiry_rule": RULE_TEXT[rule],
                    "hv20_front": None if now20 is None else round(now20, 1), "hv20_pct1y": pct_rank(now20, last1), "hv20_pct5y": pct_rank(now20, last5),
                    "cone": cone, "seasonal": [None if (m not in seas or np.isnan(seas[m])) else round(float(seas[m]), 1) for m in range(1, 13)],
                    "hv20_hist": [[d.date().isoformat(), round(float(v), 1)] for d, v in h20.dropna().iloc[-260:].items()], "contracts": contracts}
        print(sym, name, "hv20", out[sym]["hv20_front"], "pct5y", out[sym]["hv20_pct5y"], "|", [(r["label"], r["vol"], r["expiry"]) for r in contracts[:3]])
    (D / "vol").mkdir(parents=True, exist_ok=True)
    (D / "vol" / "vol.json").write_text(json.dumps({"generated": date.today().isoformat(), "rate": irx, "rate_src": "US 13-week T-bill (Yahoo ^IRX)",
                                                   "note": "Realized volatility from daily closes (Yahoo); implied volatility for CME ag options is not available from free data.",
                                                   "markets": out}))


if __name__ == "__main__":
    main()
