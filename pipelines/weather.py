"""Weather watch for the key growing regions (Open-Meteo, free, no key; runs in GitHub Actions).

For each region: last 30 days and next 16 days of rain and max temperature vs the 1996–2025 normal for the same
calendar window, plus the crop stage that matters this month. Flags dry/wet/heat where it matters for that stage.
Writes data/weather/weather.json.
"""
import json, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "weather"
# name, country, lat, lon, crops, markets
REGIONS = [
    ("Central Iowa", "US", 42.03, -93.62, ["corn", "soy"], ["ZC", "ZS"]),
    ("Central Illinois", "US", 40.12, -88.24, ["corn", "soy"], ["ZC", "ZS"]),
    ("South-central Nebraska", "US", 40.92, -98.34, ["corn", "soy"], ["ZC", "ZS"]),
    ("SW Kansas (HRW)", "US", 37.75, -100.02, ["hrw"], ["KE"]),
    ("Ohio Valley (SRW)", "US", 38.5, -87.5, ["srw"], ["ZW"]),
    ("Red River Valley ND (spring wheat)", "US", 46.88, -96.79, ["hrs"], ["KE", "ZW"]),
    ("Texas Panhandle (feedlots/pasture)", "US", 35.2, -101.8, ["cattle"], ["LE", "GF"]),
    ("Sorriso, Mato Grosso", "Brazil", -12.55, -55.72, ["br_soy_mt", "br_safrinha"], ["ZS", "ZC"]),
    ("Rio Verde, Goiás", "Brazil", -17.79, -50.92, ["br_soy_mt", "br_safrinha"], ["ZS", "ZC"]),
    ("Cascavel, Paraná", "Brazil", -24.96, -53.46, ["br_soy_south", "br_safrinha"], ["ZS", "ZC"]),
    ("Passo Fundo, Rio Grande do Sul", "Brazil", -28.26, -52.41, ["br_soy_south"], ["ZS"]),
    ("LEM, western Bahia", "Brazil", -12.09, -45.80, ["br_soy_mt"], ["ZS"]),
    ("Pergamino, N Buenos Aires", "Argentina", -33.89, -60.57, ["ar_soy", "ar_corn", "ar_wheat"], ["ZS", "ZM", "ZL", "ZC"]),
    ("Marcos Juárez, Córdoba", "Argentina", -32.70, -62.10, ["ar_soy", "ar_corn", "ar_wheat"], ["ZS", "ZM", "ZL", "ZC"]),
    ("Rafaela, Santa Fe", "Argentina", -31.25, -61.49, ["ar_soy", "ar_corn"], ["ZS", "ZM", "ZL", "ZC"]),
    ("Bahía Blanca, S Buenos Aires", "Argentina", -38.72, -62.27, ["ar_wheat"], ["ZW", "KE"]),
]
# crop: {month: (stage, sensitivity 0-3, what matters)}
STAGES = {
    "corn": {4: ("planting", 1, "dry fields help planting; cold/wet delays"), 5: ("planting/emergence", 1, "planting pace"), 6: ("vegetative", 2, "soil moisture build ahead of pollination"),
             7: ("pollination", 3, "heat and dryness cut yield most now"), 8: ("grain fill", 2, "rain supports kernel weight"), 9: ("maturity/harvest", 1, "dry weather speeds harvest"),
             10: ("harvest", 1, "dry weather speeds harvest; rain delays"), 11: ("harvest", 0, "harvest wrap-up")},
    "soy": {5: ("planting", 1, "planting pace"), 6: ("planting/emergence", 1, "stand establishment"), 7: ("flowering", 2, "moisture into pod set"),
            8: ("pod fill", 3, "August rain decides yield"), 9: ("maturity/harvest", 1, "dry weather speeds harvest"), 10: ("harvest", 1, "dry weather speeds harvest; rain delays"), 11: ("harvest", 0, "wrap-up")},
    "hrw": {9: ("planting", 2, "moisture for emergence"), 10: ("planting/emergence", 2, "moisture for stand"), 11: ("establishment", 1, "fall moisture"), 12: ("dormancy", 0, "winterkill risk if no snow"),
            1: ("dormancy", 0, "winterkill risk"), 2: ("dormancy", 1, "green-up moisture"), 3: ("green-up", 2, "spring rain"), 4: ("jointing", 3, "drought and freeze risk"), 5: ("heading/fill", 3, "rain and heat decide yield"),
            6: ("harvest", 1, "dry harvest weather"), 7: ("harvest", 0, "harvest wrap-up")},
    "srw": {10: ("planting", 1, "planting conditions"), 11: ("establishment", 1, "fall stands"), 4: ("jointing", 2, "spring rain"), 5: ("heading", 3, "wet weather raises disease/vomitoxin risk"), 6: ("harvest", 1, "dry harvest weather")},
    "hrs": {4: ("planting", 1, "planting pace"), 5: ("planting", 2, "planting pace"), 6: ("tillering", 2, "moisture"), 7: ("heading/fill", 3, "heat and dryness cut yield"), 8: ("harvest", 1, "dry harvest weather"), 9: ("harvest", 0, "wrap-up")},
    "cattle": {m: ("pasture/feedlot", 1, "heat stress in feedlots (summer), pasture and hay (drought), blizzards (winter)") for m in range(1, 13)},
    "br_soy_mt": {9: ("planting starts", 2, "regular rains needed to plant"), 10: ("planting", 3, "planting pace sets the safrinha window"), 11: ("planting/emergence", 2, "rain regularity"),
                  12: ("flowering/pod set", 2, "rain regularity"), 1: ("fill/early harvest", 2, "too much rain delays harvest"), 2: ("harvest", 1, "harvest pace vs safrinha planting"), 3: ("harvest", 0, "wrap-up")},
    "br_safrinha": {1: ("safrinha planting", 2, "planting window after soy"), 2: ("safrinha planting", 3, "late planting raises frost/dry risk"), 3: ("vegetative", 2, "rain"),
                    4: ("pollination", 3, "when the rains stop decides yield"), 5: ("grain fill", 3, "dry season onset and frost (south)"), 6: ("maturity/harvest", 1, "frost risk Paraná/MS"), 7: ("harvest", 0, "harvest pace")},
    "br_soy_south": {10: ("planting", 1, "planting pace"), 11: ("planting", 2, "moisture"), 12: ("emergence/vegetative", 2, "La Niña dryness risk in RS"), 1: ("flowering", 3, "dryness cuts yield"),
                     2: ("pod fill", 3, "dryness/heat cut yield"), 3: ("maturity/harvest", 1, "harvest pace"), 4: ("harvest", 1, "harvest"), 5: ("harvest", 0, "wrap-up")},
    "ar_soy": {11: ("planting", 2, "soil moisture for planting"), 12: ("planting", 2, "moisture"), 1: ("vegetative/flowering", 2, "heat waves"), 2: ("pod set/fill", 3, "dryness and heat cut yield"),
               3: ("fill", 3, "rain decides yield"), 4: ("harvest", 1, "harvest pace"), 5: ("harvest", 1, "harvest"), 6: ("harvest", 0, "wrap-up")},
    "ar_corn": {9: ("early planting", 2, "moisture"), 10: ("early planting", 2, "moisture"), 11: ("planting", 1, "moisture"), 12: ("late planting/early pollination", 2, "heat"),
                1: ("pollination", 3, "heat and dryness"), 2: ("grain fill", 3, "rain"), 3: ("harvest starts", 1, "harvest"), 4: ("harvest", 1, "harvest"), 5: ("harvest", 0, "harvest")},
    "ar_wheat": {5: ("planting", 1, "moisture"), 6: ("planting", 2, "moisture"), 7: ("tillering", 1, "moisture"), 8: ("tillering", 2, "moisture"), 9: ("heading", 3, "dryness and frost"),
                 10: ("grain fill", 3, "rain decides yield; frost risk"), 11: ("harvest", 1, "harvest pace"), 12: ("harvest", 0, "harvest")},
}
CROPNAME = {"corn": "corn", "soy": "soybeans", "hrw": "HRW wheat", "srw": "SRW wheat", "hrs": "spring wheat", "cattle": "cattle",
            "br_soy_mt": "soybeans", "br_safrinha": "safrinha corn", "br_soy_south": "soybeans", "ar_soy": "soybeans", "ar_corn": "corn", "ar_wheat": "wheat"}


def get(url, params):
    for i in range(4):
        try:
            r = requests.get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        time.sleep(5 * (i + 1))
    return None


def window_normal(arch, start, end):
    """Mean precip total and Tmax over the same calendar window in each year 1996-2025."""
    d = arch.copy()
    tot, tmx = [], []
    for y in range(1996, 2026):
        try:
            s = pd.Timestamp(y, start.month, start.day)
            e = s + (end - start)
        except ValueError:
            continue
        w = d[(d.index >= s) & (d.index <= e)]
        if len(w) > 0.9 * ((end - start).days + 1):
            tot.append(w.precip.sum())
            tmx.append(w.tmax.mean())
    return (float(np.mean(tot)), float(np.percentile(tot, 20)), float(np.percentile(tot, 80)), float(np.mean(tmx))) if tot else (None, None, None, None)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "normals_cache.json"
    norms = json.loads(cache.read_text()) if cache.exists() else {}
    today = pd.Timestamp.now().normalize()
    res = []
    for name, country, lat, lon, crops, mk in REGIONS:
        f = get("https://api.open-meteo.com/v1/forecast", {"latitude": lat, "longitude": lon, "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
                                                            "past_days": 30, "forecast_days": 16, "timezone": "auto"})
        if not f:
            print(name, "forecast failed"); continue
        d = pd.DataFrame({"date": pd.to_datetime(f["daily"]["time"]), "precip": f["daily"]["precipitation_sum"], "tmax": f["daily"]["temperature_2m_max"],
                          "tmin": f["daily"]["temperature_2m_min"]}).set_index("date")
        past, fut = d[d.index < today].tail(30), d[d.index >= today].head(16)
        key = f"{lat},{lon}"
        if key not in norms:
            a = get("https://archive-api.open-meteo.com/v1/archive", {"latitude": lat, "longitude": lon, "start_date": "1996-01-01", "end_date": "2025-12-31",
                                                                       "daily": "precipitation_sum,temperature_2m_max", "timezone": "auto"})
            if not a:
                print(name, "archive failed"); continue
            norms[key] = {"date": a["daily"]["time"], "precip": a["daily"]["precipitation_sum"], "tmax": a["daily"]["temperature_2m_max"]}
            time.sleep(2)
        arch = pd.DataFrame({"precip": norms[key]["precip"], "tmax": norms[key]["tmax"]}, index=pd.to_datetime(norms[key]["date"])).fillna(0)
        pn, plo, phi, tn = window_normal(arch, past.index[0], past.index[-1])
        fn, flo, fhi, ftn = window_normal(arch, fut.index[0], fut.index[-1])
        p_obs, f_obs = float(past.precip.sum()), float(fut.precip.sum())
        stages = []
        m = today.month
        for c in crops:
            st = STAGES[c].get(m)
            if st:
                stages.append({"crop": CROPNAME[c], "stage": st[0], "sensitivity": st[1], "matters": st[2]})
        sens = max([s["sensitivity"] for s in stages] or [0])
        def flag(obs, nrm, lo, hi):
            if nrm is None:
                return None
            return "dry" if obs < lo else "wet" if obs > hi else "normal"
        fflag, pflag = flag(f_obs, fn, flo, fhi), flag(p_obs, pn, plo, phi)
        heat = (float(fut.tmax.mean()) - ftn) if ftn is not None else None
        risk = 0
        if sens >= 2 and fflag == "dry":
            risk += sens
        if sens >= 2 and pflag == "dry":
            risk += 1
        if heat is not None and heat >= 3 and sens >= 2:
            risk += 1
        harvest = any("harvest" in s["stage"] for s in stages)
        if harvest and fflag == "wet":
            risk += 1
        res.append({"region": name, "country": country, "lat": lat, "lon": lon, "markets": mk, "stages": stages, "sensitivity": sens,
                    "past30_mm": round(p_obs), "past30_normal": round(pn) if pn else None, "past30_flag": pflag,
                    "next16_mm": round(f_obs), "next16_normal": round(fn) if fn else None, "next16_range": [round(flo), round(fhi)] if flo is not None else None, "next16_flag": fflag,
                    "tmax_next16": round(float(fut.tmax.mean()), 1), "tmax_anom": round(heat, 1) if heat is not None else None, "tmin_next16_min": round(float(fut.tmin.min()), 1),
                    "risk": risk, "daily": {"date": [str(x.date()) for x in d.index], "precip": [None if pd.isna(v) else round(v, 1) for v in d.precip],
                                             "tmax": [None if pd.isna(v) else round(v, 1) for v in d.tmax]}, "today": str(today.date())})
        print(name, pflag, fflag, f_obs, fn, "risk", risk)
        time.sleep(1)
    cache.write_text(json.dumps(norms))
    (OUT / "weather.json").write_text(json.dumps({"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC"), "regions": res}, separators=(",", ":")))


if __name__ == "__main__":
    main()
