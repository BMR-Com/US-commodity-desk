"""Gold and silver ETFs (GLD, SLV): daily prices with volume and the Yahoo option chains, archived every run.
Runs in GitHub Actions only (metals.yml, after the US close and again before the next open); no keys, no Claude.

Writes (data/metals/etf/):
  <T>_px.csv            daily open/high/low/close/volume (Yahoo via yfinance; whole history, merged each run)
  options_daily.csv     one row per fund and day: ATM implied vol at 30/60/90 days, 25-delta skew, put/call ratios,
                        realized vol and the IV - realized gap (appended; history builds from the first run)
  options_expiry.csv    one row per fund, day and expiry: ATM IV, 25-delta put/call IV, skew, open interest, volume
  options_strikes.csv   biggest open-interest strikes (calls and puts) per expiry and day
  etf.json              what the Metals tab shows (Gold and Silver desks, "ETFs & options" tab)

Ma's rule: options expiring in under 15 days are left out of every implied-vol reading (they still count in the
open-interest and volume totals and in the strike tables, marked). IVs are solved here from the bid/ask mid of
out-of-the-money options (Black-76 on the forward; Yahoo's own IV field is not used).
Usage: python pipelines/metals_etf.py [--force]   (--force reads the chains during US market hours too)
"""
import json, math, sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "metals" / "etf"
OUT.mkdir(parents=True, exist_ok=True)
FUNDS = {"GLD": ("gold", 0.0040, "SPDR Gold Shares"), "SLV": ("silver", 0.0050, "iShares Silver Trust")}   # sponsor fee acts as a carry on the forward
MIN_DTE = 15
ET = ZoneInfo("America/New_York")
NOW = datetime.now(ET)


def merge(p, new, keys):
    if p.exists():
        old = pd.read_csv(p, dtype={k: str for k in keys})
        new = pd.concat([old, new.astype({k: str for k in keys})]).drop_duplicates(keys, keep="last")
    new.sort_values(keys).to_csv(p, index=False)
    return new


def N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def b76(F, K, T, v, call):
    if v <= 0 or T <= 0:
        return max(0.0, (F - K) if call else (K - F))
    s = v * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    d2 = d1 - s
    return F * N(d1) - K * N(d2) if call else K * N(-d2) - F * N(-d1)


def iv_solve(px, F, K, T, call):
    """Undiscounted price -> vol by bisection (robust; ~40 steps)."""
    intr = max(0.0, (F - K) if call else (K - F))
    if px <= intr + 1e-6:
        return None
    lo, hi = 0.005, 5.0
    if b76(F, K, T, hi, call) < px:
        return None
    for _ in range(60):
        m = 0.5 * (lo + hi)
        if b76(F, K, T, m, call) > px:
            hi = m
        else:
            lo = m
    return 0.5 * (lo + hi)


def fdelta(F, K, T, v, call):
    s = v * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    return N(d1) if call else N(d1) - 1


def prices(yf, t):
    h = yf.Ticker(t).history(period="max", auto_adjust=False)
    if h is None or not len(h):
        raise RuntimeError(f"{t}: no Yahoo price history")
    h.index = pd.to_datetime(h.index).tz_localize(None)
    d = pd.DataFrame({"date": h.index.strftime("%Y-%m-%d"), "open": h.Open.round(4), "high": h.High.round(4), "low": h.Low.round(4),
                      "close": h.Close.round(4), "volume": h.Volume.astype("int64")})
    d = d[d.close > 0]
    return merge(OUT / f"{t}_px.csv", d, ["date"])


def tbill(yf):
    try:
        h = yf.Ticker("^IRX").history(period="1mo")
        return float(h.Close.dropna().iloc[-1]) / 100
    except Exception:
        return 0.04


def chain(yf, t, asof, spot, r, fee):
    tk = yf.Ticker(t)
    exps, rows, strikes = [], [], []
    tot = {"call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0}
    for e in tk.options:
        ed = pd.Timestamp(e)
        dte = (ed - pd.Timestamp(asof)).days
        if dte <= 0:
            continue
        try:
            oc = tk.option_chain(e)
        except Exception as x:
            print(t, e, "chain failed:", x); continue
        T = dte / 365.0
        F = spot * math.exp((r - fee) * T)
        df = math.exp(-r * T)
        rec = {"expiry": e, "dte": dte, "fwd": round(F, 4)}
        for side, d in (("call", oc.calls), ("put", oc.puts)):
            d = d.copy()
            d["openInterest"] = pd.to_numeric(d.openInterest, errors="coerce").fillna(0)
            d["volume"] = pd.to_numeric(d.volume, errors="coerce").fillna(0)
            rec[f"{side}_oi"], rec[f"{side}_vol"] = int(d.openInterest.sum()), int(d.volume.sum())
            tot[f"{side}_oi"] += rec[f"{side}_oi"]; tot[f"{side}_vol"] += rec[f"{side}_vol"]
            for i, (_, x) in enumerate(d.sort_values("openInterest", ascending=False).head(3).iterrows()):
                if x.openInterest > 0:
                    strikes.append({"expiry": e, "dte": dte, "type": side, "rank": i + 1, "strike": float(x.strike), "oi": int(x.openInterest), "volume": int(x.volume)})
        smile = []                                           # out-of-the-money options only: (strike, iv, forward delta)
        if dte >= MIN_DTE:
            for side, d in (("call", oc.calls), ("put", oc.puts)):
                call = side == "call"
                for _, x in d.iterrows():
                    K = float(x.strike)
                    if (call and K < F) or (not call and K >= F):
                        continue
                    b, a = float(x.bid or 0), float(x.ask or 0)
                    if not (b > 0 and a >= b):
                        continue
                    mid = 0.5 * (a + b)
                    if (a - b) / mid > 0.6 or mid < 0.02:
                        continue
                    v = iv_solve(mid / df, F, K, T, call)
                    if v and 0.03 < v < 3:
                        smile.append((K, v, fdelta(F, K, T, v, call), call))
        smile.sort()
        if len(smile) >= 4:
            ks = np.array([s[0] for s in smile]); vs = np.array([s[1] for s in smile])
            lk = np.log(ks / F)
            if lk.min() < 0 < lk.max():
                rec["atm_iv"] = round(float(np.interp(0.0, lk, vs)), 5)
            P = sorted([(s[2], s[1]) for s in smile if not s[3]])      # put deltas rise from about -0 (far OTM) toward -0.5
            Cs = sorted([(s[2], s[1]) for s in smile if s[3]])         # call deltas from about 0 up to 0.5
            if P and P[0][0] <= -0.25 <= P[-1][0]:
                rec["iv25p"] = round(float(np.interp(-0.25, [p[0] for p in P], [p[1] for p in P])), 5)
            if Cs and Cs[0][0] <= 0.25 <= Cs[-1][0]:
                rec["iv25c"] = round(float(np.interp(0.25, [c[0] for c in Cs], [c[1] for c in Cs])), 5)
            if rec.get("iv25p") and rec.get("iv25c"):
                rec["skew25"] = round(rec["iv25p"] - rec["iv25c"], 5)
            rec["n_iv"] = len(smile)
        exps.append(rec)
    return exps, strikes, tot


def cm(exps, days, key="atm_iv"):
    """Constant-maturity reading from expiries >= MIN_DTE days: ATM IV by total variance, skew linearly; flat beyond the ends."""
    pts = sorted((e["dte"], e[key]) for e in exps if e["dte"] >= MIN_DTE and e.get(key) is not None)
    if not pts:
        return None
    if days <= pts[0][0]:
        return pts[0][1]
    if days >= pts[-1][0]:
        return pts[-1][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= days <= d1:
            w = (days - d0) / (d1 - d0)
            if key == "atm_iv":
                tv = (1 - w) * v0 * v0 * d0 + w * v1 * v1 * d1
                return math.sqrt(tv / days)
            return v0 + w * (v1 - v0)


def rv(px, n):
    c = px.close.astype(float).values
    r = np.diff(np.log(c))[-n:]
    return float(np.std(r, ddof=1) * math.sqrt(252)) if len(r) >= n * 0.8 else None


def rv_series(px, n):
    r = np.log(px.close.astype(float)).diff()
    return (r.rolling(n).std() * math.sqrt(252))


def main():
    import yfinance as yf
    force = "--force" in sys.argv
    open_hours = NOW.weekday() < 5 and (NOW.hour, NOW.minute) >= (9, 30) and (NOW.hour, NOW.minute) < (16, 15)
    r = tbill(yf)
    failed = []
    P = {}
    for t in FUNDS:
        try:
            P[t] = prices(yf, t)
            print(t, "prices", len(P[t]), "days, last", P[t].date.iloc[-1], P[t].close.iloc[-1])
        except Exception as e:
            failed.append(f"{t} prices: {e}"); print(failed[-1])
    if open_hours and not force:
        print("US market open: option chains are read after the close (and before the next open); stored archive kept")
    else:
        D, E, S = [], [], []
        for t, (metal, fee, _) in FUNDS.items():
            if t not in P:
                continue
            px = P[t]
            asof, spot = px.date.iloc[-1], float(px.close.iloc[-1])
            try:
                exps, strikes, tot = chain(yf, t, asof, spot, r, fee)
            except Exception as e:
                failed.append(f"{t} options: {e}"); print(failed[-1]); continue
            if not exps:
                failed.append(f"{t} options: no expiries"); continue
            r21, r63 = rv(px, 21), rv(px, 63)
            iv30 = cm(exps, 30)
            row = {"date": asof, "fund": t, "spot": spot, "r": round(r, 5), "iv30": iv30, "iv60": cm(exps, 60), "iv90": cm(exps, 90),
                   "skew25_30": cm(exps, 30, "skew25"), "skew25_90": cm(exps, 90, "skew25"), "rv21": r21, "rv63": r63,
                   "gap30": (iv30 - r21) if iv30 is not None and r21 is not None else None,
                   **tot, "pc_oi": round(tot["put_oi"] / tot["call_oi"], 4) if tot["call_oi"] else None,
                   "pc_vol": round(tot["put_vol"] / tot["call_vol"], 4) if tot["call_vol"] else None, "n_exp": len(exps),
                   "fetched": NOW.strftime("%Y-%m-%d %H:%M ET")}
            D.append({k: (round(v, 5) if isinstance(v, float) else v) for k, v in row.items()})
            E += [{"date": asof, "fund": t, **e} for e in exps]
            S += [{"date": asof, "fund": t, **s} for s in strikes]
            print(t, asof, f"spot {spot}", f"IV30 {iv30 and round(iv30 * 100, 1)}", f"RV21 {r21 and round(r21 * 100, 1)}", f"P/C OI {row['pc_oi']}", f"{len(exps)} expiries")
        if D:
            merge(OUT / "options_daily.csv", pd.DataFrame(D), ["date", "fund"])
            merge(OUT / "options_expiry.csv", pd.DataFrame(E), ["date", "fund", "expiry"])
            # the strike table is replaced per fund and day (so a re-read before the open refreshes the open interest)
            sp = OUT / "options_strikes.csv"
            old = pd.read_csv(sp, dtype={"date": str}) if sp.exists() else pd.DataFrame()
            keys = {(d["date"], d["fund"]) for d in D}
            if len(old):
                old = old[[(a, b) not in keys for a, b in zip(old.date, old.fund)]]
            pd.concat([old, pd.DataFrame(S)]).sort_values(["date", "fund", "expiry", "type", "rank"]).to_csv(sp, index=False)
    build_json(P)
    if failed:
        print("::error::" + "; ".join(failed)); sys.exit(1)


def build_json(P):
    od = pd.read_csv(OUT / "options_daily.csv", dtype={"date": str}) if (OUT / "options_daily.csv").exists() else pd.DataFrame()
    oe = pd.read_csv(OUT / "options_expiry.csv", dtype={"date": str}) if (OUT / "options_expiry.csv").exists() else pd.DataFrame()
    os_ = pd.read_csv(OUT / "options_strikes.csv", dtype={"date": str}) if (OUT / "options_strikes.csv").exists() else pd.DataFrame()
    nz = lambda v: None if v is None or (isinstance(v, float) and v != v) else v
    out = {"generated": NOW.strftime("%Y-%m-%d %H:%M ET"), "min_dte": MIN_DTE, "funds": {}}
    for t, (metal, fee, name) in FUNDS.items():
        px = P.get(t)
        if px is None and (OUT / f"{t}_px.csv").exists():
            px = pd.read_csv(OUT / f"{t}_px.csv", dtype={"date": str})
        if px is None:
            continue
        px = px.sort_values("date")
        c = px.close.astype(float)
        last = px.iloc[-1]
        ch = lambda n: round((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100, 2) if len(c) > n else None
        y = px[px.date >= str(pd.Timestamp(last.date) - pd.DateOffset(years=2))[:10]]
        rv21 = rv_series(px, 21).round(4)
        f = {"name": name, "metal": metal, "asof": last.date, "close": float(last.close), "volume": int(last.volume),
             "vol_avg20": int(px.volume.tail(20).mean()), "chg_1d": ch(1), "chg_1w": ch(5), "chg_1m": ch(21), "chg_1y": ch(252),
             "hi52": float(c.tail(252).max()), "lo52": float(c.tail(252).min()),
             "px": {"date": y.date.tolist(), "close": y.close.round(3).tolist(), "volume": y.volume.astype(int).tolist(),
                    "rv21": [nz(v) for v in rv21.loc[y.index].tolist()]}}
        if len(od) and (od.fund == t).any():
            h = od[od.fund == t].sort_values("date")
            L = h.iloc[-1]
            f["opt"] = {k: nz(L[k].item() if hasattr(L[k], "item") else L[k]) for k in ["date", "spot", "iv30", "iv60", "iv90", "skew25_30", "skew25_90", "rv21", "rv63", "gap30",
                                                                                          "pc_oi", "pc_vol", "call_oi", "put_oi", "call_vol", "put_vol", "fetched"]}
            f["opt_hist"] = {k: [nz(v) for v in h[k].tolist()] for k in ["date", "iv30", "rv21", "gap30", "skew25_30", "pc_oi", "pc_vol"]}
            e = oe[(oe.fund == t) & (oe.date == L.date)].sort_values("dte")
            f["term"] = [{k: nz(x[k]) for k in ["expiry", "dte", "atm_iv", "iv25p", "iv25c", "skew25", "call_oi", "put_oi", "call_vol", "put_vol"] if k in x} for _, x in e.iterrows()]
            s = os_[(os_.fund == t) & (os_.date == L.date)] if len(os_) else os_
            f["strikes"] = []
            short, longer = e[e.dte < MIN_DTE].expiry.tolist(), e[e.dte >= MIN_DTE].expiry.tolist()
            for ex in short[:2] + longer[:8]:                    # the two nearest expiries, then eight from 15 days out
                ss = s[s.expiry == ex]
                f["strikes"].append({"expiry": ex, "dte": int(e[e.expiry == ex].dte.iloc[0]),
                                     "calls": [{"k": float(x.strike), "oi": int(x.oi)} for _, x in ss[ss.type == "call"].sort_values("rank").iterrows()],
                                     "puts": [{"k": float(x.strike), "oi": int(x.oi)} for _, x in ss[ss.type == "put"].sort_values("rank").iterrows()]})
        out["funds"][t] = f
    (OUT / "etf.json").write_text(json.dumps(out, separators=(",", ":"), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print("etf.json written")


if __name__ == "__main__":
    main()
