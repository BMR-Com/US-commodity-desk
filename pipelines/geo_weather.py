"""Crop-region weather vs history for the main producing and exporting countries (Open-Meteo, free, no key).

For each region (a representative point in the main growing area) and its crop season:
- rain over the last 30 / 60 / 90 days and season to date vs the 2011-2025 average, with the percentile among
  those years (low percentile = drier than most years);
- water balance (rain minus FAO reference evapotranspiration) over the last 60 days vs normal;
- max temperature anomaly and hot days (>= 35 C) in the last 30 days;
- soil moisture (ERA5-Land, 0-7 cm and 28-100 cm) over the last 7 days vs the same dates in past years (percentile);
- next 16 days of rain and max temperature (forecast) vs normal for those dates;
- weekly cumulative season rain and weekly root-zone soil moisture vs the historical range, for charts.

History (2011-2025) is fetched once per region and kept in data/geo/weather_hist/<id>.csv.gz (it never changes);
each run fetches only the last ~400 days and the forecast. Open-Meteo limits free use, so at most
GEO_WX_NEW (default 12) regions without history are added per run; the rest show "history pending".
Writes data/geo/weather.json. ERA5 data run about 5 days behind real time; the forecast fills the gap.
"""
import json, os, time
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "geo"
HIST = OUT / "weather_hist"
H0, H1 = "2011-01-01", "2025-12-31"
VARS = ["precipitation_sum", "temperature_2m_max", "temperature_2m_min", "et0_fao_evapotranspiration",
        "soil_moisture_0_to_7cm_mean", "soil_moisture_28_to_100cm_mean"]
SHORT = {"precipitation_sum": "rain", "temperature_2m_max": "tmax", "temperature_2m_min": "tmin", "et0_fao_evapotranspiration": "et0",
         "soil_moisture_0_to_7cm_mean": "sm7", "soil_moisture_28_to_100cm_mean": "sm100"}

# id, region, country, lat, lon, commodities, season start (MM-DD), note
R = [
    # United States (for comparison; Drought Monitor and NOAA cover the US in detail)
    ("us_ia", "Central Iowa", "United States", 42.03, -93.62, ["corn", "soybeans"], "04-15", "Corn Belt"),
    ("us_il", "Central Illinois", "United States", 40.12, -88.24, ["corn", "soybeans"], "04-15", "Corn Belt"),
    ("us_ne", "South-central Nebraska", "United States", 40.92, -98.34, ["corn", "soybeans", "beef"], "04-15", "Corn Belt west, feedlots"),
    ("us_ks", "Southwest Kansas", "United States", 37.75, -100.02, ["wheat", "beef"], "09-15", "HRW wheat, feedlots"),
    ("us_nd", "Red River Valley, ND", "United States", 46.88, -96.79, ["wheat"], "04-15", "spring wheat"),
    ("us_tx", "Lubbock, West Texas", "United States", 33.58, -101.85, ["cotton"], "05-01", "dryland/irrigated cotton"),
    ("us_wi", "Wisconsin dairy belt", "United States", 44.5, -89.5, ["milk", "cheese"], "04-01", "pasture/forage"),
    # Brazil
    ("br_mt", "Sorriso, Mato Grosso", "Brazil", -12.55, -55.72, ["soybeans", "corn", "cotton"], "09-15", "soy, safrinha corn, cotton"),
    ("br_go", "Rio Verde, Goiás", "Brazil", -17.79, -50.92, ["soybeans", "corn", "beef"], "09-15", "soy, corn, pasture"),
    ("br_pr", "Cascavel, Paraná", "Brazil", -24.96, -53.46, ["soybeans", "corn", "pork"], "09-01", "soy, corn, hogs/poultry"),
    ("br_rs", "Passo Fundo, Rio Grande do Sul", "Brazil", -28.26, -52.41, ["soybeans", "wheat"], "10-15", "soy (late), wheat"),
    ("br_ba", "LEM, western Bahia", "Brazil", -12.09, -45.80, ["soybeans", "cotton"], "10-15", "soy, cotton"),
    # Argentina
    ("ar_ba", "Pergamino, N Buenos Aires", "Argentina", -33.89, -60.57, ["soybeans", "corn", "meal", "oil"], "10-01", "core zone"),
    ("ar_cd", "Marcos Juárez, Córdoba", "Argentina", -32.70, -62.10, ["soybeans", "corn", "wheat", "meal", "oil"], "10-01", "core zone"),
    ("ar_sb", "Bahía Blanca, S Buenos Aires", "Argentina", -38.72, -62.27, ["wheat", "beef"], "05-15", "wheat, cattle"),
    # China
    ("cn_hlj", "Harbin, Heilongjiang", "China", 45.75, 126.65, ["corn", "soybeans"], "04-25", "NE corn/soy"),
    ("cn_jl", "Changchun, Jilin", "China", 43.88, 125.32, ["corn"], "04-25", "NE corn belt"),
    ("cn_hn", "Zhengzhou, Henan", "China", 34.75, 113.62, ["wheat", "corn", "pork"], "10-01", "winter wheat / summer corn"),
    ("cn_sd", "Jinan, Shandong", "China", 36.65, 117.0, ["wheat", "corn", "pork"], "10-01", "winter wheat / summer corn"),
    ("cn_xj", "Aksu, Xinjiang", "China", 41.17, 80.26, ["cotton"], "04-01", "irrigated cotton: heat and water supply matter, rain little"),
    # India
    ("in_pb", "Ludhiana, Punjab", "India", 30.90, 75.85, ["wheat"], "11-01", "rabi wheat (irrigated)"),
    ("in_up", "Kanpur, Uttar Pradesh", "India", 26.45, 80.33, ["wheat", "milk"], "11-01", "rabi wheat"),
    ("in_mp", "Indore, Madhya Pradesh", "India", 22.72, 75.86, ["wheat", "soybeans"], "06-15", "kharif soy / rabi wheat"),
    ("in_gj", "Rajkot, Gujarat", "India", 22.30, 70.80, ["cotton", "milk"], "06-01", "kharif cotton (monsoon)"),
    ("in_mh", "Akola, Maharashtra", "India", 20.70, 77.00, ["cotton", "soybeans"], "06-01", "kharif cotton/soy (monsoon)"),
    # Pakistan, Australia
    ("pk_ml", "Multan, Punjab (Pakistan)", "Pakistan", 30.20, 71.47, ["cotton"], "04-15", "cotton"),
    ("au_nsw", "Moree, New South Wales", "Australia", -29.47, 149.85, ["wheat", "cotton"], "05-01", "wheat, irrigated cotton"),
    ("au_wa", "Merredin, Western Australia", "Australia", -31.48, 118.28, ["wheat"], "05-01", "export wheat belt"),
    ("au_qld", "Roma, Queensland", "Australia", -26.57, 148.79, ["beef"], "10-01", "cattle pasture"),
    # Europe
    ("eu_fr", "Beauce, France", "European Union", 48.45, 1.50, ["wheat", "corn"], "10-01", "soft wheat"),
    ("eu_de", "Saxony-Anhalt, Germany", "European Union", 52.0, 11.6, ["wheat", "pork", "milk"], "10-01", "wheat, hogs, dairy"),
    ("eu_ro", "Constanța, Romania", "European Union", 44.17, 28.63, ["wheat", "corn"], "10-01", "Black Sea EU exporter"),
    ("eu_pl", "Central Poland", "European Union", 52.2, 19.0, ["wheat", "milk"], "10-01", "wheat, dairy"),
    ("eu_nl", "Friesland, Netherlands", "European Union", 53.1, 5.8, ["milk", "cheese", "butter"], "03-01", "dairy pasture"),
    ("eu_ie", "Cork, Ireland", "European Union", 51.9, -8.5, ["milk", "butter", "beef"], "03-01", "grass-based dairy"),
    # Black Sea
    ("ru_kr", "Krasnodar, Russia", "Russia", 45.04, 38.98, ["wheat", "corn"], "09-01", "winter wheat, south"),
    ("ru_ro", "Rostov, Russia", "Russia", 47.23, 39.72, ["wheat"], "09-01", "winter wheat, south"),
    ("ru_st", "Stavropol, Russia", "Russia", 45.04, 41.97, ["wheat"], "09-01", "winter wheat"),
    ("ru_vo", "Saratov, Volga", "Russia", 51.53, 46.03, ["wheat"], "09-01", "Volga winter/spring wheat"),
    ("ru_si", "Barnaul, Altai (Siberia)", "Russia", 53.35, 83.77, ["wheat"], "05-01", "spring wheat"),
    ("ua_od", "Odesa, Ukraine", "Ukraine", 46.48, 30.73, ["wheat", "corn"], "09-01", "south: wheat"),
    ("ua_dn", "Dnipro, Ukraine", "Ukraine", 48.46, 35.04, ["wheat", "corn"], "09-01", "central: wheat, corn"),
    ("ua_pl", "Poltava, Ukraine", "Ukraine", 49.59, 34.55, ["corn", "wheat"], "04-15", "corn belt"),
    # Canada, New Zealand
    ("ca_sk", "Regina, Saskatchewan", "Canada", 50.45, -104.61, ["wheat"], "04-20", "spring wheat, canola"),
    ("ca_ab", "Lethbridge, Alberta", "Canada", 49.69, -112.84, ["wheat", "beef"], "04-20", "wheat, feedlots"),
    ("nz_wk", "Waikato, New Zealand", "New Zealand", -37.79, 175.28, ["milk", "butter", "nfdm", "cheese"], "07-01", "pasture dairy (top dairy exporter)"),
]


def get(url, params, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                return r.json()
            print("  HTTP", r.status_code, r.text[:150])
            if r.status_code == 429:
                time.sleep(30)
        except Exception as e:
            print("  err", e)
        time.sleep(5 * (i + 1))
    return None


def to_df(j, keys=VARS):
    if not j or "daily" not in j:
        return None
    d = pd.DataFrame({SHORT.get(k, k): j["daily"].get(k) for k in keys if k in j["daily"]}, index=pd.to_datetime(j["daily"]["time"]))
    return d


def season_start(d, mmdd):
    m, dd = map(int, mmdd.split("-"))
    s = date(d.year, m, dd)
    return s if s <= d else date(d.year - 1, m, dd)


def pctile(v, arr):
    arr = [a for a in arr if a is not None and not np.isnan(a)]
    if v is None or np.isnan(v) or len(arr) < 5:
        return None
    return round(100 * (np.sum(np.array(arr) < v) + 0.5 * np.sum(np.array(arr) == v)) / len(arr))


def window(df, end, days, col, how="sum"):
    s = df.loc[pd.Timestamp(end - timedelta(days=days - 1)):pd.Timestamp(end), col]
    if len(s) < days * 0.8:
        return None
    return float(s.sum() if how == "sum" else s.mean())


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) or np.isinf(o) else round(float(o), 3)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main():
    HIST.mkdir(parents=True, exist_ok=True)
    budget = int(os.environ.get("GEO_WX_NEW", "12"))
    today = date.today()
    out = []
    for rid, name, country, lat, lon, comms, sstart, note in R:
        hp = HIST / f"{rid}.csv.gz"
        hist = None
        if hp.exists():
            hist = pd.read_csv(hp, index_col=0, parse_dates=True)
        elif budget > 0:
            j = get("https://archive-api.open-meteo.com/v1/archive", {"latitude": lat, "longitude": lon, "start_date": H0, "end_date": H1,
                                                                     "daily": ",".join(VARS), "timezone": "auto"})
            hist = to_df(j)
            if hist is not None:
                hist.round(3).to_csv(hp, compression="gzip")
                budget -= 1
                print("history", rid, len(hist))
            time.sleep(8)
        rec = to_df(get("https://archive-api.open-meteo.com/v1/archive", {"latitude": lat, "longitude": lon, "start_date": (today - timedelta(days=420)).isoformat(),
                                                                           "end_date": (today - timedelta(days=1)).isoformat(), "daily": ",".join(VARS), "timezone": "auto"}))
        fc = to_df(get("https://api.open-meteo.com/v1/forecast", {"latitude": lat, "longitude": lon, "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration",
                                                                  "forecast_days": 16, "past_days": 7, "timezone": "auto"}),
                   ["precipitation_sum", "temperature_2m_max", "temperature_2m_min", "et0_fao_evapotranspiration"])
        time.sleep(1.5)
        if rec is None:
            print("no recent data", rid)
            continue
        # observed series: ERA5 recent, gap to yesterday filled by the forecast model's past days
        obs = rec.dropna(subset=["rain"])
        last_obs = obs.index.max().date()
        if fc is not None:
            gap = fc[(fc.index.date > last_obs) & (fc.index.date < today)]
            obs = pd.concat([obs, gap])
        end = obs.index.max().date()
        fut = fc[fc.index.date >= today] if fc is not None else None
        o = {"id": rid, "name": name, "country": country, "lat": lat, "lon": lon, "commodities": comms, "note": note, "season_start": sstart,
             "data_through": end.isoformat(), "era5_through": last_obs.isoformat(), "history": hist is not None}
        ss = season_start(end, sstart)
        o["season_from"] = ss.isoformat()
        for k, days in (("r30", 30), ("r60", 60), ("r90", 90)):
            o[k] = window(obs, end, days, "rain")
        o["rstd"] = float(obs.loc[pd.Timestamp(ss):pd.Timestamp(end), "rain"].sum())
        o["wb60"] = None if o["r60"] is None else o["r60"] - (window(obs, end, 60, "et0") or 0)
        o["tmax30"] = window(obs, end, 30, "tmax", "mean")
        o["hot30"] = int((obs.loc[pd.Timestamp(end - timedelta(days=29)):, "tmax"] >= 35).sum())
        sm_end = last_obs
        o["sm7"] = window(rec, sm_end, 7, "sm7", "mean")
        o["sm100"] = window(rec, sm_end, 7, "sm100", "mean")
        if fut is not None and len(fut):
            o["f16_rain"] = float(fut.rain.sum())
            o["f16_tmax"] = float(fut.tmax.mean())
            o["f16_days"] = len(fut)
            o["f16_from"] = fut.index.min().date().isoformat()
        if hist is not None:
            yrs = sorted(set(hist.index.year))
            def hy(fn):
                vals = []
                for y in yrs:
                    try:
                        e = date(y, end.month, min(end.day, 28 if end.month == 2 else end.day))
                    except ValueError:
                        continue
                    if pd.Timestamp(e) > hist.index.max():
                        continue
                    v = fn(e)
                    if v is not None:
                        vals.append(v)
                return vals
            for k, days in (("r30", 30), ("r60", 60), ("r90", 90)):
                arr = hy(lambda e: window(hist, e, days, "rain"))
                o[k + "_n"] = float(np.mean(arr)) if arr else None
                o[k + "_p"] = pctile(o[k], arr)
            arr = hy(lambda e: float(hist.loc[pd.Timestamp(season_start(e, sstart)):pd.Timestamp(e), "rain"].sum()) if pd.Timestamp(season_start(e, sstart)) >= hist.index.min() else None)
            o["rstd_n"], o["rstd_p"] = (float(np.mean(arr)) if arr else None), pctile(o["rstd"], arr)
            arr = hy(lambda e: (window(hist, e, 60, "rain") or 0) - (window(hist, e, 60, "et0") or 0))
            o["wb60_n"], o["wb60_p"] = (float(np.mean(arr)) if arr else None), pctile(o["wb60"], arr)
            arr = hy(lambda e: window(hist, e, 30, "tmax", "mean"))
            o["tmax30_n"] = float(np.mean(arr)) if arr else None
            arr = hy(lambda e: int((hist.loc[pd.Timestamp(e - timedelta(days=29)):pd.Timestamp(e), "tmax"] >= 35).sum()))
            o["hot30_n"] = float(np.mean(arr)) if arr else None
            for k in ("sm7", "sm100"):
                arr = []
                for y in yrs:
                    try:
                        e = date(y, sm_end.month, min(sm_end.day, 28))
                    except ValueError:
                        continue
                    v = window(hist, e, 7, k, "mean")
                    if v is not None:
                        arr.append(v)
                o[k + "_n"] = float(np.mean(arr)) if arr else None
                o[k + "_p"] = pctile(o[k], arr)
            if fut is not None and len(fut):
                arr = []
                for y in yrs:
                    s = pd.Timestamp(date(y, fut.index.min().month, min(fut.index.min().day, 28)))
                    seg = hist.loc[s:s + pd.Timedelta(days=len(fut) - 1)]
                    if len(seg) == len(fut):
                        arr.append(float(seg.rain.sum()))
                o["f16_rain_n"] = float(np.mean(arr)) if arr else None
                o["f16_rain_p"] = pctile(o["f16_rain"], arr)
            # weekly charts: cumulative season rain (this season vs history min/mean/max) and root-zone soil moisture
            weeks = list(range(0, ((end - ss).days // 7) + 1))
            cur = [float(obs.loc[pd.Timestamp(ss):pd.Timestamp(ss + timedelta(days=7 * w + 6)), "rain"].sum()) for w in weeks]
            band = []
            for y in yrs:
                s0 = season_start(date(y, end.month, min(end.day, 28)), sstart)
                if pd.Timestamp(s0) < hist.index.min() or pd.Timestamp(s0 + timedelta(days=7 * len(weeks))) > hist.index.max() + pd.Timedelta(days=1):
                    continue
                band.append([float(hist.loc[pd.Timestamp(s0):pd.Timestamp(s0 + timedelta(days=7 * w + 6)), "rain"].sum()) for w in weeks])
            if band:
                b = np.array(band)
                o["chart_rain"] = {"weeks": weeks, "cur": [round(v) for v in cur], "mean": [round(v) for v in b.mean(0)],
                                   "p10": [round(v) for v in np.percentile(b, 10, 0)], "p90": [round(v) for v in np.percentile(b, 90, 0)],
                                   "min": [round(v) for v in b.min(0)], "max": [round(v) for v in b.max(0)]}
            # soil moisture: last 52 weeks vs same weeks in history
            sm = rec["sm100"].dropna()
            wk = sm.resample("W").mean().iloc[-52:]
            hs = hist["sm100"].dropna()
            hw = hs.groupby(hs.index.isocalendar().week).agg(["mean", lambda x: x.quantile(.1), lambda x: x.quantile(.9)])
            hw.columns = ["mean", "p10", "p90"]
            iw = [int(d.isocalendar()[1]) for d in wk.index]
            o["chart_sm"] = {"dates": [d.date().isoformat() for d in wk.index], "cur": [round(float(v), 3) for v in wk.values],
                             "mean": [round(float(hw["mean"].get(w, np.nan)), 3) for w in iw], "p10": [round(float(hw["p10"].get(w, np.nan)), 3) for w in iw],
                             "p90": [round(float(hw["p90"].get(w, np.nan)), 3) for w in iw]}
        # one-line read
        flags = []
        if o.get("r60_p") is not None:
            if o["r60_p"] <= 20:
                flags.append(f"dry: 60-day rain in the driest {max(o['r60_p'], 5)}% of 2011-25")
            elif o["r60_p"] >= 80:
                flags.append("wet: 60-day rain among the wettest 20% of years")
        if o.get("sm100_p") is not None and o["sm100_p"] <= 20:
            flags.append("root-zone soil moisture low for the date")
        if o.get("hot30_n") is not None and o["hot30"] >= o["hot30_n"] + 5:
            flags.append(f"{o['hot30']} days >= 35 C in 30 days (normal {o['hot30_n']:.0f})")
        if o.get("f16_rain_p") is not None:
            flags.append("next 16 days " + ("dry" if o["f16_rain_p"] <= 25 else "wet" if o["f16_rain_p"] >= 75 else "near normal"))
        o["flags"] = flags
        out.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in o.items()})
        print(rid, o.get("r60"), o.get("r60_p"), o.get("sm100_p"), flags)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "weather.json").write_text(json.dumps({"generated": date.today().isoformat(), "history": f"{H0[:4]}-{H1[:4]}",
                                                   "source": "Open-Meteo (ERA5 / ERA5-Land reanalysis for history and recent days; best-match forecast model for 16 days)",
                                                   "regions": clean(out)}))


if __name__ == "__main__":
    main()
