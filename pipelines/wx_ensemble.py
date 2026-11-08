"""Ensemble weather odds for the crop regions in pipelines/geo_weather.py (Open-Meteo ensemble API, free, no key).

For every region with a 2011-2025 history file (data/geo/weather_hist/<id>.csv.gz):
- next 15 days, from three ensembles: ECMWF ENS (51 members), ECMWF AIFS ENS (the AI ensemble, 51) and NOAA GEFS
  (31): rain total per member -> 10th/50th/90th percentile, and the share of members in the driest / wettest third of
  2011-2025 for the same dates; mean max-temperature anomaly; odds of frost (a day with min temp <= 3 C, and <= 0 C)
  and of heat (a day with max temp >= 35 C);
- weeks 3-4 (days 15-28) from GEFS 0.5 (runs to 35 days): rain and max-temperature anomaly and the dry/wet odds;
- a consensus read: dry / wet when both ECMWF ensembles put at least 60% of members in that third, split when the
  models disagree.
Global drivers: NOAA CPC weekly Nino 3.4, and the GEFS Arctic Oscillation / North Atlantic Oscillation / Pacific-North
American forecasts.
Writes data/geo/wx_ensemble.json. A rate limit (HTTP 429) stops the run and keeps the last file.
"""
import io, json, sys, time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
from geo_weather import R  # noqa: E402  (id, name, country, lat, lon, crops, season start, note)

OUT = ROOT / "data" / "geo" / "wx_ensemble.json"
HIST = ROOT / "data" / "geo" / "weather_hist"
UA = {"User-Agent": "BMR-Com research desk (github.com/BMR-Com)"}
MODELS = [("ecmwf_ens", "ECMWF ENS", "ecmwf_ifs025", 15), ("aifs_ens", "ECMWF AIFS ENS", "ecmwf_aifs025", 15), ("gefs", "GEFS", "gfs05", 35)]
BATCH = 10
LIMIT = {"hit": False}
log = []


def get(url, params, tries=3, timeout=180, pause=15):
    if LIMIT["hit"]:
        return None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
            log.append([url.split("/")[2], r.status_code, r.text[:160]])
            if r.status_code == 429:
                LIMIT["hit"] = True
                return None
            if r.status_code == 400:
                return None
        except Exception as e:
            log.append([url.split("/")[2], str(e)[:160]])
        time.sleep(pause * (i + 1))
    return None


def ens_daily(model, days, pts):
    """{region id: DataFrame(index=date, columns=MultiIndex(var, member))} for rain, tmax, tmin."""
    p = {"latitude": ",".join(str(x[3]) for x in pts), "longitude": ",".join(str(x[4]) for x in pts), "models": model,
         "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min", "forecast_days": days, "timezone": "auto"}
    # big ensemble requests can take minutes on the first try; the server keeps computing and a repeat is served from cache
    r = get("https://ensemble-api.open-meteo.com/v1/ensemble", p, tries=6, timeout=50, pause=8)
    if r is None:
        return {}
    js = r.json(); js = js if isinstance(js, list) else [js]
    out = {}
    for x, pt in zip(js, pts):
        d = x.get("daily") or {}
        if "time" not in d:
            continue
        cols = {}
        for k, v in d.items():
            if k == "time":
                continue
            var = "rain" if k.startswith("precipitation_sum") else "tmax" if k.startswith("temperature_2m_max") else "tmin" if k.startswith("temperature_2m_min") else None
            if var is None:
                continue
            mem = k.split("_member")[1] if "_member" in k else "00"
            cols[(var, mem)] = v
        if cols:
            df = pd.DataFrame(cols, index=pd.to_datetime(d["time"])).apply(pd.to_numeric, errors="coerce")
            out[pt[0]] = df
    return out


def hist(rid):
    f = HIST / f"{rid}.csv.gz"
    if not f.exists():
        return None
    h = pd.read_csv(f, index_col=0, parse_dates=True)
    return h[["rain", "tmax", "tmin"]]


def window_stats(h, dates):
    """Per-year totals of rain and mean tmax over the same calendar days in 2011-2025."""
    md = {(d.month, d.day) for d in dates}
    tots, tmx = [], []
    for y in range(2011, 2026):
        sel = [pd.Timestamp(y, m, dd) for m, dd in md if not (m == 2 and dd == 29)]
        w = h.reindex(sel).dropna()
        if len(w) >= 0.8 * len(sel):
            tots.append(w.rain.sum() * len(sel) / len(w)); tmx.append(w.tmax.mean())
    if len(tots) < 8:
        return None
    t = np.array(tots)
    return {"mean": float(t.mean()), "t33": float(np.percentile(t, 33.3)), "t67": float(np.percentile(t, 66.7)), "tmax": float(np.mean(tmx))}


def summarize(df, h, d0, d1):
    w = df[(df.index >= d0) & (df.index <= d1)]
    if w.empty or "rain" not in w.columns.get_level_values(0):
        return None
    rain = w["rain"].sum(min_count=1).dropna()
    if rain.empty:
        return None
    st = window_stats(h, list(w.index)) if h is not None else None
    o = {"from": str(w.index[0].date()), "to": str(w.index[-1].date()), "days": len(w), "members": int(rain.size),
         "rain_p10": round(float(rain.quantile(.1)), 1), "rain_p50": round(float(rain.median()), 1), "rain_p90": round(float(rain.quantile(.9)), 1)}
    tmax = w["tmax"].mean() if "tmax" in w.columns.get_level_values(0) else None
    tmin = w["tmin"] if "tmin" in w.columns.get_level_values(0) else None
    if st:
        o.update({"rain_normal": round(st["mean"], 1), "p_dry": round(float((rain < st["t33"]).mean()), 2), "p_wet": round(float((rain > st["t67"]).mean()), 2),
                  "rain_anom_pct": round(float(rain.median() / st["mean"] * 100 - 100), 0) if st["mean"] > 1 else None})
        if tmax is not None:
            o["tmax_anom"] = round(float(tmax.mean() - st["tmax"]), 1)
    if tmin is not None:
        mn = tmin.min()
        o["p_frost3"] = round(float((mn <= 3).mean()), 2); o["p_frost0"] = round(float((mn <= 0).mean()), 2)
        o["tmin_p10"] = round(float(mn.quantile(.1)), 1)
    if "tmax" in w.columns.get_level_values(0):
        mx = w["tmax"].max(); o["p_heat35"] = round(float((mx >= 35).mean()), 2)
    return o


def drivers():
    d = {}
    r = get("https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for", None, tries=2, timeout=60)
    if r is not None:
        import re
        vals = []
        for l in r.text.splitlines():
            m = re.match(r"\s*(\d{2}[A-Z]{3}\d{4})", l)
            pr = re.findall(r"(\d+\.\d)\s*(-?\d+\.\d)", l[10:])
            if m and len(pr) == 4:
                vals.append({"week": m.group(1), "nino34_anom": float(pr[2][1]), "nino12_anom": float(pr[0][1])})
        d["nino34"] = vals[-12:]
    for idx in ("ao", "nao", "pna"):
        z = "1000" if idx == "ao" else "500"
        r = get(f"https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.{idx}.gefs.z{z}.120days.csv", None, tries=2, timeout=60)
        if r is None:
            continue
        try:
            t = pd.read_csv(io.StringIO(r.text))
            vk = [c for c in t.columns if c.endswith("_index")][0]
            t = t[t.time == t.time.max()]
            g = t.groupby("valid_time")[vk].agg(["mean", "min", "max"]).round(2)
            d[idx] = {"init": str(t.time.max()), "days": {k: v for k, v in g.to_dict("index").items()}}
        except Exception as e:
            log.append([idx, str(e)[:120]])
        ob = get(f"https://ftp.cpc.ncep.noaa.gov/cwlinks/norm.daily.{idx}.cdas.z{z}.19500101_current.csv", None, tries=2, timeout=60)
        if ob is not None:
            try:
                t = pd.read_csv(io.StringIO(ob.text)).tail(30)
                d.setdefault(idx, {})["obs_last30"] = t.iloc[:, -1].round(2).tolist()
                d[idx]["obs_last_date"] = "-".join(str(int(x)).zfill(2) for x in t.iloc[-1, :3])
            except Exception as e:
                log.append([idx + " obs", str(e)[:120]])
    return d


def main():
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    today = pd.Timestamp(date.today())
    regs, seen = [], set()
    for r in R:
        if r[0] in seen:
            continue
        seen.add(r[0]); regs.append(r)
    H = {r[0]: hist(r[0]) for r in regs}
    res = {r[0]: {"name": r[1], "country": r[2], "crops": r[5]} for r in regs}
    for key, label, model, days in MODELS:
        for i in range(0, len(regs), BATCH):
            pts = regs[i:i + BATCH]
            got = ens_daily(model, days, pts)
            for rid, df in got.items():
                h = H.get(rid)
                a = summarize(df, h, today, today + pd.Timedelta(days=14))
                if a:
                    res[rid].setdefault("next15", {})[key] = a
                if key == "gefs":
                    b = summarize(df, h, today + pd.Timedelta(days=14), today + pd.Timedelta(days=27))
                    if b:
                        res[rid]["wk34"] = b
            print(label, i, len(got), flush=True)
            time.sleep(4)
            if LIMIT["hit"]:
                break
        if LIMIT["hit"]:
            break
    n_ok = sum(1 for v in res.values() if v.get("next15"))
    if n_ok == 0 and old:
        print("no ensemble data this run; keeping last file", log[-3:]); return
    for rid, v in res.items():
        n = v.get("next15", {})
        e, a = n.get("ecmwf_ens"), n.get("aifs_ens")
        if e and a and "p_dry" in e and "p_dry" in a:
            if e["p_dry"] >= .6 and a["p_dry"] >= .6:
                c = "dry"
            elif e["p_wet"] >= .6 and a["p_wet"] >= .6:
                c = "wet"
            elif (e["p_dry"] >= .5 and a["p_wet"] >= .5) or (e["p_wet"] >= .5 and a["p_dry"] >= .5):
                c = "split"
            else:
                c = "near normal"
            v["consensus"] = c
        fr = [m.get("p_frost3") for m in n.values() if m.get("p_frost3") is not None]
        if fr:
            v["p_frost3_max"] = max(fr)
    out = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "models": {k: l for k, l, _, _ in MODELS},
           "normals": "2011-2025, same calendar days (ERA5 via Open-Meteo)", "regions": res, "drivers": drivers(), "log": log[-20:]}
    OUT.write_text(json.dumps(out, separators=(",", ":"), default=float))
    print("wx ensemble: regions with data", n_ok, "of", len(res), "| consensus", pd.Series([v.get("consensus") for v in res.values()]).value_counts().to_dict())


if __name__ == "__main__":
    main()
