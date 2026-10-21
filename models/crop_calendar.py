"""Crop calendars by country (main producing and exporting countries), after the USDA FAS / IPAD crop calendar
charts and GEOGLAM crop calendars. Months are typical windows; the exact timing shifts a few weeks with the year.

Each stage: (stage, first month, last month, sensitivity 0-3, what matters). Months wrap over year-end
(e.g. 11 -> 2 = Nov to Feb). Sensitivity 3 = the yield-making window (corn pollination, soybean pod fill,
wheat heading/grain fill, cotton boll set); harvest-stage weather matters for pace and quality.
`regions` lists the weather regions (pipelines/geo_weather.py ids) that represent the crop in that country.
"""

P, V, C, H = "planting", "vegetative", "critical", "harvest"

CAL = {
    "corn": {
        "United States": {"regions": ["us_ia", "us_il", "us_ne"], "stages": [(P, 4, 5, 1, "planting pace; cold/wet delays"), (V, 6, 6, 2, "soil moisture build"), (C, 7, 8, 3, "pollination and grain fill: heat and dryness cut yield"), (H, 9, 11, 1, "dry weather speeds harvest")]},
        "China": {"regions": ["cn_hlj", "cn_jl", "cn_hn", "cn_sd"], "stages": [(P, 4, 6, 1, "NE spring corn Apr-May; North China Plain summer corn after wheat in June"), (V, 6, 7, 2, "summer rain"), (C, 7, 8, 3, "tasseling/silking: heat and drought in the NE and North China Plain"), (H, 9, 10, 1, "harvest; early frost risk in the NE")]},
        "Brazil": {"regions": ["br_mt", "br_go", "br_pr"], "stages": [(P, 9, 12, 1, "first crop (south) planting"), (P, 1, 3, 2, "safrinha (second crop, ~75% of output) planted after soybeans: timely soy harvest matters"), (C, 4, 5, 3, "safrinha pollination: the rainy season must last into April-May; frost risk in Paraná"), (H, 6, 9, 1, "safrinha harvest and export season")]},
        "Argentina": {"regions": ["ar_ba", "ar_cd"], "stages": [(P, 9, 12, 1, "early corn Sep-Oct, late corn Dec-Jan"), (C, 12, 2, 3, "flowering: January heat and dryness are the main risk"), (H, 3, 7, 1, "harvest")]},
        "European Union": {"regions": ["eu_fr", "eu_ro"], "stages": [(P, 4, 5, 1, "planting"), (C, 7, 8, 3, "flowering: summer heat in France, Romania, Hungary"), (H, 9, 11, 1, "harvest")]},
        "Ukraine": {"regions": ["ua_pl", "ua_dn"], "stages": [(P, 4, 5, 1, "planting"), (C, 7, 8, 3, "flowering and grain fill"), (H, 9, 11, 1, "harvest; export season from October")]},
    },
    "soybeans": {
        "United States": {"regions": ["us_ia", "us_il", "us_ne"], "stages": [(P, 5, 6, 1, "planting"), (V, 7, 7, 2, "flowering"), (C, 8, 8, 3, "pod set and fill: August rain makes the crop"), (H, 9, 11, 1, "harvest")]},
        "Brazil": {"regions": ["br_mt", "br_go", "br_pr", "br_rs", "br_ba"], "stages": [(P, 9, 12, 1, "planting starts with the rains (Mato Grosso mid-Sep, Rio Grande do Sul Nov-Dec)"), (C, 12, 2, 3, "flowering and pod fill: dry spells in the south (La Niña) or the center-west"), (H, 1, 4, 1, "harvest: Mato Grosso Jan-Feb, the south Mar-Apr; rain delays harvest and safrinha planting")]},
        "Argentina": {"regions": ["ar_ba", "ar_cd"], "stages": [(P, 10, 1, 1, "first soy Oct-Nov, second (after wheat) Dec-Jan"), (C, 2, 3, 3, "pod fill: February-March rain decides yield"), (H, 4, 6, 1, "harvest and crush season")]},
        "China": {"regions": ["cn_hlj"], "stages": [(P, 5, 5, 1, "planting in Heilongjiang"), (C, 7, 8, 3, "flowering and pod fill"), (H, 9, 10, 1, "harvest")]},
        "India": {"regions": ["in_mp", "in_mh"], "stages": [(P, 6, 7, 1, "kharif planting with the monsoon"), (C, 8, 9, 3, "flowering and pod fill: monsoon breaks"), (H, 10, 11, 1, "harvest")]},
        "Paraguay": {"regions": [], "stages": [(P, 9, 11, 1, "planting"), (C, 12, 1, 3, "pod fill"), (H, 1, 3, 1, "harvest")]},
    },
    "wheat": {
        "China": {"regions": ["cn_hn", "cn_sd"], "stages": [(P, 10, 11, 1, "winter wheat planting on the North China Plain"), (V, 12, 2, 0, "dormancy"), (C, 3, 5, 3, "jointing, heading and grain fill: spring drought and hot dry winds in May"), (H, 5, 6, 1, "harvest; rain at harvest hurts quality")]},
        "European Union": {"regions": ["eu_fr", "eu_de", "eu_ro", "eu_pl"], "stages": [(P, 9, 11, 1, "planting"), (V, 12, 2, 0, "dormancy; winterkill risk in the east"), (C, 4, 6, 3, "heading and grain fill: spring drought or heat in May-June"), (H, 7, 8, 1, "harvest; rain hurts quality")]},
        "India": {"regions": ["in_pb", "in_up", "in_mp"], "stages": [(P, 10, 12, 1, "rabi planting after the kharif harvest"), (V, 1, 1, 1, "irrigated growth"), (C, 2, 3, 3, "heading and grain fill: March heat waves cut yields"), (H, 3, 5, 1, "harvest and government procurement")]},
        "Russia": {"regions": ["ru_kr", "ru_ro", "ru_st", "ru_vo", "ru_si"], "stages": [(P, 8, 10, 1, "winter wheat planting: autumn soil moisture in the south"), (V, 11, 3, 0, "dormancy; winterkill"), (C, 4, 6, 3, "spring regrowth to heading: May-June rain in the south and Volga"), (H, 6, 8, 1, "harvest (spring wheat in Siberia Aug-Sep); export season from July")]},
        "United States": {"regions": ["us_ks", "us_nd"], "stages": [(P, 9, 11, 1, "HRW/SRW planting"), (V, 12, 2, 0, "dormancy"), (C, 4, 5, 3, "jointing to heading in the Plains"), (H, 6, 9, 1, "winter wheat harvest Jun-Jul, spring wheat Aug-Sep")]},
        "Ukraine": {"regions": ["ua_od", "ua_dn"], "stages": [(P, 9, 10, 1, "planting"), (V, 11, 3, 0, "dormancy"), (C, 4, 6, 3, "heading and grain fill"), (H, 7, 8, 1, "harvest")]},
        "Canada": {"regions": ["ca_sk", "ca_ab"], "stages": [(P, 4, 5, 1, "spring wheat planting"), (C, 7, 7, 3, "heading: July heat and dryness on the Prairies"), (H, 8, 9, 1, "harvest")]},
        "Australia": {"regions": ["au_nsw", "au_wa"], "stages": [(P, 4, 6, 1, "planting after autumn rain"), (C, 8, 10, 3, "flowering and grain fill: spring rain"), (H, 10, 12, 1, "harvest and export season")]},
        "Argentina": {"regions": ["ar_sb", "ar_cd"], "stages": [(P, 5, 7, 1, "planting"), (C, 9, 10, 3, "heading; frost and dryness"), (H, 11, 1, 1, "harvest")]},
    },
    "cotton": {
        "China": {"regions": ["cn_xj"], "stages": [(P, 4, 5, 1, "planting in Xinjiang (irrigated)"), (C, 7, 8, 3, "flowering and boll set: heat and irrigation water"), (H, 9, 11, 1, "harvest; early frost")]},
        "India": {"regions": ["in_gj", "in_mh"], "stages": [(P, 5, 7, 1, "planting with the monsoon (north irrigated from May)"), (C, 8, 10, 3, "flowering and boll development: monsoon rain, pink bollworm"), (H, 10, 3, 1, "picking and arrivals Oct-Mar")]},
        "Brazil": {"regions": ["br_mt", "br_ba"], "stages": [(P, 12, 2, 1, "second-crop cotton planted after soybeans in Mato Grosso"), (C, 3, 5, 3, "boll set: the rainy season must last into April"), (H, 6, 9, 1, "harvest; export season Aug-Jan")]},
        "United States": {"regions": ["us_tx"], "stages": [(P, 4, 6, 1, "planting; West Texas dryland needs spring rain"), (C, 7, 8, 3, "squaring, bloom and boll set: West Texas heat and drought"), (H, 9, 12, 1, "harvest; hurricanes on the Gulf coast")]},
        "Pakistan": {"regions": ["pk_ml"], "stages": [(P, 4, 6, 1, "planting"), (C, 7, 9, 3, "boll set; monsoon floods and heat"), (H, 9, 12, 1, "picking")]},
        "Australia": {"regions": ["au_nsw"], "stages": [(P, 10, 11, 1, "planting (irrigation allocations decide area)"), (C, 1, 2, 3, "boll set"), (H, 3, 6, 1, "picking")]},
    },
    "beef": {
        "United States": {"regions": ["us_ne", "us_ks"], "stages": [(P, 4, 5, 1, "spring grass green-up: pasture decides herd rebuilding and feeder placements"), (C, 6, 8, 2, "summer pasture: drought forces cow culling and early placements"), (H, 9, 11, 1, "fall calf run, placements on feed")]},
        "Brazil": {"regions": ["br_go", "br_mt"], "stages": [(C, 10, 4, 2, "rainy season: pasture growth, cattle retained, fewer slaughters"), (H, 5, 9, 1, "dry season: more cattle sent to slaughter, higher beef exports")]},
        "Australia": {"regions": ["au_qld"], "stages": [(C, 11, 4, 2, "northern wet season: pasture and herd rebuilding"), (H, 5, 10, 1, "dry season turnoff to slaughter and export")]},
        "Argentina": {"regions": ["ar_sb"], "stages": [(C, 10, 3, 2, "spring/summer pasture"), (H, 4, 9, 1, "autumn/winter slaughter")]},
    },
    "milk": {
        "United States": {"regions": ["us_wi"], "stages": [(C, 3, 6, 2, "spring flush: peak milk; heat later in summer cuts yields"), (V, 7, 9, 1, "summer heat stress"), (H, 10, 2, 0, "fall/winter: lower milk, higher component demand")]},
        "European Union": {"regions": ["eu_nl", "eu_ie", "eu_de", "eu_pl"], "stages": [(C, 4, 6, 2, "spring flush on grass: peak collections"), (V, 7, 9, 1, "summer drought reduces grass and milk"), (H, 10, 3, 0, "winter housing")]},
        "New Zealand": {"regions": ["nz_wk"], "stages": [(P, 8, 9, 1, "calving and season start"), (C, 10, 12, 3, "peak milk (Oct-Nov): pasture growth sets the season's exports"), (H, 1, 5, 1, "late season; summer dry risk")]},
        "India": {"regions": ["in_up", "in_gj"], "stages": [(C, 10, 2, 2, "winter flush"), (V, 3, 6, 1, "lean season: heat"), (V, 7, 9, 1, "monsoon fodder")]},
    },
}
CAL["meal"] = CAL["soybeans"]
CAL["oil"] = CAL["soybeans"]
CAL["cheese"] = CAL["butter"] = CAL["nfdm"] = CAL["milk"]
CAL["pork"] = {}   # pork supply follows breeding herds and feed costs, not a crop calendar; see the corn and soybean pages


def in_window(m, a, b):
    return a <= m <= b if a <= b else (m >= a or m <= b)


def stage_now(stages, month):
    cur = [s for s in stages if in_window(month, s[1], s[2])]
    if not cur:
        nxt = min(stages, key=lambda s: (s[1] - month) % 12)
        return None, nxt
    return max(cur, key=lambda s: s[3]), None


def read(stage, regs):
    """Weather impact for the stage from the region readings (geo_weather output)."""
    if not regs or stage is None:
        return "between seasons" if stage is None else "no weather reading", 0
    have = [r for r in regs if r.get("history")]
    if not have:
        return "weather history still loading", 0
    p60 = [r["r60_p"] for r in have if r.get("r60_p") is not None]
    sm = [r["sm100_p"] for r in have if r.get("sm100_p") is not None]
    hot = [r["hot30"] - (r.get("hot30_n") or 0) for r in have if r.get("hot30") is not None]
    f16 = [r["f16_rain_p"] for r in have if r.get("f16_rain_p") is not None]
    avg = lambda x: sum(x) / len(x) if x else None
    a60, asm, ahot, af = avg(p60), avg(sm), avg(hot), avg(f16)
    name, sens = stage[0], stage[3]
    dry = (a60 is not None and a60 <= 25) or (asm is not None and asm <= 25)
    wet = a60 is not None and a60 >= 75
    heat = ahot is not None and ahot >= 4
    out, score = [], 0
    if name == H:
        if wet or (af is not None and af >= 75):
            out.append("wet: harvest delays and quality risk"); score = -1
        else:
            out.append("harvest weather workable"); score = 0
    elif name == P:
        if dry:
            out.append("dry soils: planting may wait for rain, poor emergence"); score = -1 if sens >= 1 else 0
        elif wet:
            out.append("wet: planting delays possible, good soil moisture"); score = 0
        else:
            out.append("planting conditions normal")
    else:
        if dry and heat:
            out.append("dry and hot in a yield-sensitive stage: yield risk"); score = -sens
        elif dry:
            out.append("dry: yield risk if it persists" if sens >= 2 else "dry"); score = -max(sens - 1, 0)
        elif heat:
            out.append("heat stress"); score = -1 if sens >= 2 else 0
        elif wet:
            out.append("well watered: favorable for yields" if sens >= 2 else "wet"); score = 1 if sens >= 2 else 0
        else:
            out.append("near-normal weather")
    if af is not None and name != H:
        out.append("next 16 days " + ("dry" if af <= 25 else "wet" if af >= 75 else "near normal"))
    return "; ".join(out), score
