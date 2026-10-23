"""China cotton desk: crop progress and estimates, imports of cotton and cotton yarn, domestic prices vs the world
and vs the Xinjiang target price. Writes data/china/cotton.json for the Cotton > China tab.

Inputs (data/china/raw/ unless noted):
- cca_production_articles.json  China Cotton Association (china-cotton.org) production-monitoring surveys
                                 (sowing, growth, output estimates, picking and selling progress), read from the site's pages
- cca_tables.json               CCA data-centre tables (price indices, NBS output, balance sheet, cotton imports by year)
- gacc_major_commodities.csv    China customs monthly bulletin, table "Major import commodities" (english.customs.gov.cn)
- comtrade_china_monthly.csv    UN Comtrade, China imports by HS code and origin (history to the latest year posted)
- data/china/tv_prices.csv      Zhengzhou cotton (CF) and cotton yarn (CY) front month, USD/CNY, ICE cotton front month
- data/geo/raw/psd.json         USDA PSD (China cotton balance)
"""
import json, re, sys
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "china" / "raw"
OUT = ROOT / "data" / "china" / "cotton.json"
LB_PER_T = 2204.62
TARGET_PRICE = 18600            # Xinjiang cotton target price, yuan/t (NDRC/MoF, 2026-2028 round; same level since 2017)
VAT = 0.09                      # domestic lint prices (CCIndex, Zhengzhou) include 9% VAT
YARN_TO_LINT = 1.1              # ~1.1 t lint per t of yarn (spinning waste); blended yarn overstates the cotton content
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def c_lb(yuan_t, cny):
    return yuan_t / cny / LB_PER_T * 100


def ordinal(n):
    n = int(round(n))
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def rnd(x, d=1):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)


# ── CCA survey articles ───────────────────────────────────────────────────────
REG = r"(全国|全疆|新疆|南疆|北疆|内地|长江流域|黄河流域|西北内陆|甘肃)"
REG_KEY = {"全国": "national", "全疆": "xinjiang", "新疆": "xinjiang", "内地": "inland", "长江流域": "yangtze", "黄河流域": "yellow",
           "西北内陆": "northwest", "南疆": "south_xj", "北疆": "north_xj", "甘肃": "gansu"}


def _adate(body):
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", body)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _season(obs):
    """Cotton season (crop year) of an observation date: picking runs Sep-Jan, selling into Mar."""
    return obs.year if obs.month >= 7 else obs.year - 1


def parse_articles():
    p = RAW / "cca_production_articles.json"
    if not p.exists():
        return [], [], []
    d = json.loads(p.read_text())
    prog, est, price = [], [], []
    for title, _, url in d["list"]:
        a = d["art"].get(url)
        if not a:
            continue
        body = a["body"]
        pub = _adate(body)
        if not pub:
            continue
        text = body[body.find("\n"):]
        # national output estimate (surveys titled 全国…), from the body or the title
        if "全国" in title and re.search(r"产量|生长|总产|生产|采摘交售", title):
            m = re.search(r"总产(?:量)?(?:为|预计为|预计|约|达到|达)?\s*(\d{3}(?:\.\d+)?)\s*万吨", text) or \
                re.search(r"(?:全国)?(?:棉花)?(?:总)?产量(?:为|预计为|预计|约|达到|达)?\s*(\d{3}(?:\.\d+)?)\s*万吨", text) or \
                re.search(r"(?:产量|总产预计|总产)(\d{3}(?:\.\d+)?)万吨", title)
            if m:
                ar = re.search(r"(?:植棉)?面积(?:为|约)?\s*(\d{4}(?:\.\d+)?)\s*万亩", text)
                yl = re.search(r"单产(?:为|约|预计为|预计)?\s*(\d{2,3}(?:\.\d+)?)\s*公斤", text)
                sm = re.search(r"（(\d{4})年(\d{1,2})月", title)
                survey = date(int(sm[1]), int(sm[2]), 1) if sm else date(pub.year, pub.month, 1)
                est.append({"pub": pub.isoformat(), "survey": survey.isoformat()[:7], "season": survey.year if survey.month >= 4 else survey.year - 1,
                            "prod_kt": float(m[1]) * 10, "area_kmu": float(ar[1]) * 10 if ar else None,
                            "yield_kg_mu": float(yl[1]) if yl else None, "title": title, "url": url})
        # seed-cotton selling price
        for m in ([] if not re.search(r"全国|新疆", title) else re.finditer(r"(?:平均)?交售(?:平均|均)?价(?:格)?(?:为|是)?\s*(\d{1,2}\.\d{1,2})\s*元/公斤[，,]?\s*(?:同比(上涨|下跌|下降|增长|提高)(\d+(?:\.\d+)?)%)?", text)):
            v = float(m[1])
            yoy = float(m[3]) * (1 if m[2] in ("上涨", "增长", "提高") else -1) if m[2] else None
            price.append({"pub": pub.isoformat(), "season": _season(pub) if pub.month >= 8 or pub.month <= 3 else None, "yuan_kg": v, "yoy_pct": yoy, "title": title})
            break
        # picking / selling progress at "截至M月D日"
        for para in re.split(r"\n+", text):
            for anc in re.finditer(r"截[至止](?:到)?(\d{1,2})月(\d{1,2})日", para):
                mo, dy = int(anc[1]), int(anc[2])
                yr = pub.year if mo <= pub.month else pub.year - 1
                try:
                    obs = date(yr, mo, dy)
                except ValueError:
                    continue
                if obs.month in (4, 5, 6, 7):
                    continue                     # sowing season: different metric
                seg = re.split(r"截[至止]", para[anc.end():anc.end() + 300])[0]
                before = re.findall(REG, para[:anc.start()])
                region = before[-1] if before else None
                for cl in re.split(r"[；;。]", seg):
                    r = re.findall(REG, cl)
                    if r:
                        region = r[0]
                    if not region:
                        continue
                    for kind, kw in (("pick", "采摘"), ("sell", "交售")):
                        for x in re.finditer(kw + r"(?:进度|率)?(?:为|达到|达|已达|已超过|超过|约)?\s*(\d{1,3}(?:\.\d+)?)\s*%", cl):
                            v = float(x[1])
                            if v <= 100:
                                prog.append({"obs": obs.isoformat(), "season": _season(obs), "region": REG_KEY[region], "kind": kind, "pct": v,
                                             "pub": pub.isoformat(), "title": title})
    pr = pd.DataFrame(prog)
    if len(pr):   # one value per (obs, region, kind): keep the latest publication
        pr = pr.sort_values("pub").drop_duplicates(["obs", "region", "kind"], keep="last")
    return pr, pd.DataFrame(est), pd.DataFrame(price)


def doy(obs, season):
    """Days since 1 September of the season."""
    return (pd.Timestamp(obs) - pd.Timestamp(season, 9, 1)).days


def progress_block(pr):
    if pr is None or not len(pr):
        return None
    out = {"series": {}, "latest": {}}
    for reg in ("national", "xinjiang", "inland"):
        for kind in ("pick", "sell"):
            s = pr[(pr.region == reg) & (pr.kind == kind)].copy()
            if not len(s):
                continue
            s["d"] = [doy(o, se) for o, se in zip(s.obs, s.season)]
            s = s[(s.d >= -10) & (s.d <= 200)].sort_values("d")
            ser = {int(se): [[int(r.d), r.pct, r.obs] for r in g.itertuples()] for se, g in s.groupby("season")}
            out["series"][f"{reg}_{kind}"] = ser
    # latest reading vs prior seasons at the same date (linear interpolation; 0 before the first reading in Sep)
    for key, ser in out["series"].items():
        cur = max(ser)
        if not ser[cur]:
            continue
        d, v, obs = ser[cur][-1]
        comp = {}
        for se, pts in ser.items():
            if se == cur or len(pts) < 2:
                continue
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            # only interpolate between real readings (or from zero when that season's first reading is early and small)
            if xs[0] > d and not (xs[0] - d <= 20 and ys[0] <= 10):
                continue
            if xs[0] > d:
                xs, ys = [0] + xs, [0] + ys
            if d <= xs[-1] and min(abs(x - d) for x in xs) <= 20:
                comp[se] = rnd(np.interp(d, xs, ys))
        prev = [comp[s] for s in sorted(comp) if s >= cur - 5]
        out["latest"][key] = {"season": cur, "obs": obs, "pct": v, "last_year": comp.get(cur - 1),
                              "avg5": rnd(np.mean(prev)) if prev else None, "n_avg": len(prev), "by_season": comp}
    return out


def estimates_block(est, nbs, balance, psd_prod, cca_final=None):
    if est is None or not len(est):
        return None
    est = est.sort_values("pub").drop_duplicates(["season", "survey"], keep="last")
    paths = {int(s): [[r.survey, r.prod_kt, r.area_kmu, r.yield_kg_mu, r.url] for r in g.itertuples()] for s, g in est.groupby("season")}
    cur = max(paths)
    last = paths[cur][-1]
    # how the CCA estimate moved from the same survey month to the season's last survey (Nov-Jan), past seasons
    mth = int(last[0][5:7])
    # "final": the association's balance-sheet / final production figure where published, else its last survey of the season
    finals = {int(b["season"]): b["prod"] * 10 for b in (balance or []) if int(b["season"]) < cur}
    for r in (cca_final or []):
        if r.get("region") == "全国":
            finals[int(r["year"])] = r["prod_kt"]
    moves = []
    for s, p in paths.items():
        if s == cur:
            continue
        same = [x for x in p if int(x[0][5:7]) == mth and int(x[0][:4]) == s]
        fin = [x for x in p if (int(x[0][:4]) == s and int(x[0][5:7]) >= 11) or int(x[0][:4]) == s + 1]
        fv, src = (finals[s], "CCA final") if s in finals else ((fin[-1][1], "last survey") if fin else (None, None))
        if same and fv:
            moves.append({"season": s, "at": same[0][1], "final": fv, "final_src": src, "chg_pct": rnd((fv / same[0][1] - 1) * 100, 2)})
    proj = None
    if moves:
        ch = [m["chg_pct"] for m in moves]
        proj = {"median_chg_pct": rnd(np.median(ch), 2), "min_chg_pct": min(ch), "max_chg_pct": max(ch), "n": len(ch),
                "kt": rnd(last[1] * (1 + np.median(ch) / 100), 0), "lo_kt": rnd(last[1] * (1 + min(ch) / 100), 0),
                "hi_kt": rnd(last[1] * (1 + max(ch) / 100), 0)}
    prev = paths.get(cur - 1, [])
    prev_same = [x for x in prev if int(x[0][5:7]) == mth]
    return {"season": cur, "latest": {"survey": last[0], "prod_kt": last[1], "area_kmu": last[2], "yield_kg_mu": last[3], "url": last[4],
                                      "prev_survey_kt": paths[cur][-2][1] if len(paths[cur]) > 1 else None},
            "last_year_same_survey_kt": prev_same[0][1] if prev_same else None,
            "last_year_final_kt": finals.get(cur - 1) or (prev[-1][1] if prev else None),
            "last_year_final_src": "CCA final" if (cur - 1) in finals else "last survey",
            "finals": {int(k): v for k, v in finals.items()},
            "table": [{"season": s, "sep": next((x[1] for x in paths.get(s, []) if x[0][5:7] == "09" and int(x[0][:4]) == s), None),
                       "last_survey": paths[s][-1][1] if s in paths else None, "cca_final": finals.get(s),
                       "nbs": next((n["prod_kt"] for n in (nbs or []) if n["year"] == s), None),
                       "usda": (psd_prod or {}).get(s, {}).get("Production")} for s in range(cur - 8, cur + 1)],
            "paths": paths, "moves": moves, "projection": proj, "nbs": nbs, "balance": balance, "usda": psd_prod}


# ── customs: cotton and cotton yarn imports ─────────────────────────────────
def gacc_monthly():
    p = RAW / "gacc_major_commodities.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d = d[d.flow == "M"].copy()
    d["c"] = d.commodity.replace({"Wheat and wheat flour": "Wheat", "Maize and maize flour": "Maize", "Rice and rice flour": "Rice"})
    num = lambda s: pd.to_numeric(s.astype(str).str.replace(",", ""), errors="coerce")
    d["m"] = d.mon.map({m: i + 1 for i, m in enumerate(MON)})
    d["ytd_q"] = num(d.ytd_qty)
    d["ytd_v"] = num(d.ytd_val)
    d["mq"] = num(d.m_qty)
    d["mv"] = num(d.m_val)
    d["mult"] = d.unit.map({"10000T": 10.0, "T": 0.001}).fillna(np.nan)     # -> thousand t
    rows = []
    for (c, y), g in d.groupby(["c", "year"]):
        g = g.sort_values("m").drop_duplicates("m", keep="last").set_index("m")
        mult = g.mult.dropna().iloc[0] if g.mult.notna().any() else np.nan
        ytd = g.ytd_q * mult
        ytv = g.ytd_v / 1000.0                       # USD million
        # months the bulletin skipped (e.g. Sep-Oct 2024) between two published months: interpolate the year-to-date
        known_m = sorted(m for m in ytd.index if pd.notna(ytd.get(m)))
        if known_m:
            full = pd.Series(ytd.reindex(range(known_m[0], known_m[-1] + 1)).values, index=range(known_m[0], known_m[-1] + 1)).interpolate()
            fullv = pd.Series(ytv.reindex(range(known_m[0], known_m[-1] + 1)).values, index=range(known_m[0], known_m[-1] + 1)).interpolate()
            est = [m for m in full.index if m not in g.index and m > 2]   # Jan missing = released with Feb, not interpolated
            for m in est:
                g.loc[m] = np.nan
            ytd = pd.concat([ytd, full[est]]).sort_index()
            ytv = pd.concat([ytv, fullv[est]]).sort_index()
            g = g.sort_index()
        prev_q, prev_v = 0.0, 0.0
        for m in range(1, 13):
            if m not in g.index:
                continue
            q, v = ytd.get(m), ytv.get(m)
            # monthly = YTD difference; a missing previous month (e.g. Jan-Feb released together) leaves a 2-month figure
            mq = q - prev_q if m - 1 in g.index or m == 1 else (g.mq.get(m) * mult if pd.notna(g.mq.get(m)) else q - prev_q)
            mv = v - prev_v if m - 1 in g.index or m == 1 else (g.mv.get(m) / 1000 if pd.notna(g.mv.get(m)) else v - prev_v)
            rows.append({"c": c, "year": int(y), "m": m, "ytd_kt": q, "ytd_musd": v, "m_kt": mq, "m_musd": mv})
            prev_q, prev_v = q, v
    return pd.DataFrame(rows)


def cca_import_reports():
    """Monthly cotton and cotton-yarn imports from the CCA's monthly import reports (they quote customs before the
    English bulletin is out): {(year, month): {"cotton": kt, "yarn": kt, "url": ...}}."""
    p = RAW / "cca_production_articles.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out = {}
    for u, a in d["art"].items():
        m = re.search(r"进口月度报告（(\d{4})年(\d{1,2})月）", a.get("t", ""))
        if not m:
            continue
        y, mo = int(m[1]), int(m[2])
        b = a["body"]
        r = {}
        c = re.search(rf"{mo}月(?:我国)?(?:进口棉花|棉花进口量?)(?:为|仅)?\s*([\d.]+)\s*万吨", b) or re.search(r"当月棉花进口[^。]{0,30}?([\d.]+)万吨", b)
        if c:
            r["cotton"] = float(c[1]) * 10
        yv = re.search(r"棉纱线?进口(?:量)?(?:为)?\s*([\d.]+)\s*万吨", b)
        if yv:
            r["yarn"] = float(yv[1]) * 10
        if r:
            r["url"] = u
            out[(y, mo)] = r
    return out


def fill_from_reports(g, rep):
    """Add months the customs English bulletin has not published yet, from the CCA import reports (flagged)."""
    if not len(g) or not rep:
        return g, []
    add, used = [], []
    for (y, mo), r in sorted(rep.items()):
        for key, c in (("cotton", "Cotton"), ("yarn", "Cotton yarn")):
            if key not in r:
                continue
            s = g[(g.c == c) & (g.year == y)]
            if len(s[s.m == mo]) or not len(s[s.m == mo - 1]):
                continue
            prev = s[s.m == mo - 1].iloc[0]
            add.append({"c": c, "year": y, "m": mo, "ytd_kt": prev.ytd_kt + r[key], "ytd_musd": np.nan, "m_kt": r[key], "m_musd": np.nan, "src": "CCA report"})
            used.append(f"{c} {y}-{mo:02d} {r[key]:.0f} kt")
    if add:
        g = pd.concat([g, pd.DataFrame(add)], ignore_index=True)
    return g, used


def add_fibre(g):
    """Cotton + yarn as lint (yarn x YARN_TO_LINT), by year and month where both are known."""
    a = g[g.c == "Cotton"].set_index(["year", "m"])
    b = g[g.c == "Cotton yarn"].set_index(["year", "m"])
    ix = a.index.intersection(b.index)
    if not len(ix):
        return g
    f = pd.DataFrame({"ytd_kt": a.loc[ix, "ytd_kt"] + b.loc[ix, "ytd_kt"] * YARN_TO_LINT,
                      "m_kt": a.loc[ix, "m_kt"] + b.loc[ix, "m_kt"] * YARN_TO_LINT,
                      "ytd_musd": a.loc[ix, "ytd_musd"] + b.loc[ix, "ytd_musd"], "m_musd": a.loc[ix, "m_musd"] + b.loc[ix, "m_musd"]}).reset_index()
    f["c"] = "Cotton+yarn"
    return pd.concat([g, f], ignore_index=True)


def origin_demand(I, ct, esr):
    """China's extra yarn imports this year, split by supplying country, as extra lint those countries must spin,
    compared with each country's cotton imports and the US share of them (from the export-sales brief)."""
    y = (I or {}).get("yarn")
    if not y:
        return None
    cy, lm = y["year"], y["last_month"]
    cur, prev = y["ytd_kt"].get(cy), y["ytd_kt"].get(cy - 1)
    if not cur or not prev:
        return None
    # shares: the latest month published in the trade press if recent, else the latest full year in Comtrade (HS 5205)
    shares, src = {}, ""
    p = RAW / "yarn_origin_shares.csv"
    if p.exists():
        sh = pd.read_csv(p)
        lastp = sh.period.max()
        if lastp >= f"{cy}-01":
            shares = dict(zip(sh[sh.period == lastp].country, sh[sh.period == lastp].share_pct))
            src = f"{sh[sh.period == lastp].source.iloc[0]}, {lastp}"
    org = (I.get("origins") or {}).get("yarn")
    if not shares and org:
        k = org["years"].index(org["last_year"])
        shares = {c: v[k] for c, v in org["share"].items()}
        src = f"UN Comtrade {org['last_year']}"
    base_sh = {}
    if org:
        k = org["years"].index(org["last_year"])
        base_sh = {c: v[k] for c, v in org["share"].items()}
    dest = {d["c"]: d for d in ((esr or {}).get("dest") or [])}
    alias = {"Vietnam": "Vietnam", "Pakistan": "Pakistan", "India": "India", "Bangladesh": "Bangladesh", "Indonesia": "Indonesia",
             "Malaysia": "Malaysia", "Uzbekistan": "Uzbekistan", "Taiwan": "Taiwan", "Cambodia": "Cambodia"}
    own_crop = {"India", "Uzbekistan"}     # spin mostly home-grown cotton
    rows = []
    for c, sh in sorted(shares.items(), key=lambda x: -x[1]):
        if c == "Other" or sh < 1:
            continue
        sh_prev = base_sh.get(c, sh)
        d_yarn = cur * sh / 100 - prev * sh_prev / 100
        d_lint = d_yarn * YARN_TO_LINT
        r = {"country": c, "share_pct": sh, "share_prev_pct": sh_prev, "yarn_ytd_kt": rnd(cur * sh / 100, 0), "yarn_prev_kt": rnd(prev * sh_prev / 100, 0),
             "extra_yarn_kt": rnd(d_yarn, 0), "extra_lint_kt": rnd(d_lint, 0), "extra_lint_mbales": rnd(d_lint / 217.725, 2)}
        e = dest.get(alias.get(c, c))
        if e and e.get("commit") is not None:
            r["us_commit_kbales"] = rnd(e["commit"], 0)
            r["us_commit_ly_kbales"] = rnd(e.get("ly"), 0)
        if e and e.get("imports") and c not in own_crop:
            r["usda_imports_mbales"] = e["imports"]
            r["extra_pct_of_imports"] = rnd(d_lint / 217.725 / e["imports"] * 100, 1)
            us = e.get("us_share5")
            if us is not None:
                r["us_share5_pct"] = rnd(us * 100, 0)
                r["implied_us_mbales"] = rnd(d_lint / 217.725 * us, 2)
        r["note"] = "spins mostly its own cotton" if c in ("India", "Uzbekistan") else ("spins home-grown and imported cotton" if c == "Pakistan" else "spins imported cotton")
        rows.append(r)
    return {"year": cy, "through_month": lm, "yarn_ytd_kt": cur, "yarn_prev_kt": prev, "share_source": src,
            "share_base": f"UN Comtrade {org['last_year']}" if org else None, "rows": rows}


def esr_note(O, I):
    """Plain-text note for the cotton export-sales page (no charts depend on it)."""
    if not O or not O.get("rows"):
        return None
    m = MON[O["through_month"] - 1]
    parts = []
    for r in O["rows"][:6]:
        t = f"{r['country']}: ~{r['yarn_ytd_kt']:,.0f} kt of yarn to China Jan–{m} ({r['extra_yarn_kt']:+,.0f} kt y/y) ≈ {r['extra_lint_kt']:+,.0f} kt of extra lint ({r['extra_lint_mbales']:+.2f} m bales)"
        if r.get("extra_pct_of_imports") is not None:
            t += f", {r['extra_pct_of_imports']:+.0f}% of its {r['usda_imports_mbales']:.1f} m-bale USDA import forecast"
        if r.get("implied_us_mbales") is not None:
            t += f"; at the US's usual {r['us_share5_pct']:.0f}% share that is {r['implied_us_mbales']:+.2f} m bales of US cotton"
        t += f" ({r['note']})"
        parts.append(t)
    head = (f"China's cotton-yarn imports are {O['yarn_ytd_kt']:,.0f} kt Jan–{m} {O['year']} vs {O['yarn_prev_kt']:,.0f} kt a year earlier. "
            "Each tonne is spun abroad from about 1.1 t of lint, so the extra yarn is extra cotton demand in the supplying countries:")
    tail = (" These are estimates: this year's country split uses " + O["share_source"] + " for the whole year to date" + (f", last year's uses {O['share_base']} (the latest year China has reported to the UN)" if O.get("share_base") else "") +
            "; customs 'cotton yarn' includes blends, so the lint figures are upper bounds. Read it as a tailwind for US and Brazilian sales to " +
            (", ".join(r["country"] for r in O["rows"] if (r.get("implied_us_mbales") or 0) >= 0.03) or "the yarn-exporting importers") + ", not as a revision to the projections.")
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": f"{O['year']}-{O['through_month']:02d}", "text": head, "items": parts, "caveat": tail}


def my_cumulative(g, c):
    """Cumulative imports by calendar year and by Aug-Jul marketing year (thousand t)."""
    s = g[g.c == c]
    ytd = {(int(r.year), int(r.m)): r.ytd_kt for r in s.itertuples()}
    years = sorted({y for y, _ in ytd})
    cal = {y: [rnd(ytd.get((y, m)), 0) for m in range(1, 13)] for y in years}
    my = {}
    for y in years:
        base = ytd.get((y, 7))
        if base is None:
            continue
        row = []
        for k, (yy, m) in enumerate([(y, m) for m in range(8, 13)] + [(y + 1, m) for m in range(1, 8)]):
            if yy == y:
                v = ytd.get((y, m))
                row.append(rnd(v - base, 0) if v is not None else None)
            else:
                dec = ytd.get((y, 12))
                v = ytd.get((yy, m))
                row.append(rnd(dec - base + v, 0) if v is not None and dec is not None else None)
        if any(v is not None for v in row):
            my[f"{y}/{str(y + 1)[2:]}"] = row
    return {"calendar": cal, "my": my, "my_months": ["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]}


def usda_check(I, cum, psd):
    """Compare China's marketing-year (Aug-Jul) imports so far with USDA's forecast, and USDA's mill use with the CCA's."""
    if not cum or not psd:
        return None
    out = {}
    my = cum["cotton"]["my"]
    keys = sorted(my)
    cur = keys[-1]
    row = my[cur]
    k = max(i for i, v in enumerate(row) if v is not None)
    y0 = int(cur[:4])
    usda = lambda y, a: (psd.get(y) or {}).get(a)
    f = usda(y0, "Imports")
    shares = []
    for key in keys[:-1]:
        r = my[key]
        if r[11] is not None and r[k] is not None and r[11] > 0:
            shares.append({"my": key, "share_pct": rnd(r[k] / r[11] * 100), "full_kt": r[11], "usda_kt": usda(int(key[:4]), "Imports")})
    med = np.median([x["share_pct"] for x in shares]) if shares else None
    out["imports"] = {"my": cur, "through": cum["cotton"]["my_months"][k], "to_date_kt": row[k], "usda_kt": f,
                      "usda_pct_done": rnd(row[k] / f * 100) if f else None, "hist": shares,
                      "median_share_pct": rnd(med) if med else None, "pace_implied_kt": rnd(row[k] / med * 100, 0) if med else None}
    last = keys[-2] if len(keys) > 1 else None
    if last and my[last][11] is not None:
        out["imports"]["last_my"] = {"my": last, "actual_kt": my[last][11], "usda_kt": usda(int(last[:4]), "Imports")}
    yarn_my = cum.get("yarn", {}).get("my", {})
    out["use"] = {"my": cur, "usda_kt": usda(y0, "Domestic Use"), "usda_prev_kt": usda(y0 - 1, "Domestic Use"),
                  "usda_prod_kt": usda(y0, "Production"), "usda_end_kt": usda(y0, "Ending Stocks"),
                  "yarn_last_my_kt": yarn_my.get(last, [None] * 12)[11] if last else None,
                  "yarn_to_date_kt": (yarn_my.get(cur) or [None] * 12)[k], "yarn_to_date_prev_kt": (yarn_my.get(last) or [None] * 12)[k] if last else None}
    return out


def comtrade():
    p = RAW / "comtrade_china_monthly.csv"
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


PARTNER = {704: "Vietnam", 699: "India", 586: "Pakistan", 860: "Uzbekistan", 458: "Malaysia", 360: "Indonesia", 50: "Bangladesh",
           490: "Taiwan", 116: "Cambodia", 156: "China (re-imports)", 76: "Brazil", 842: "USA", 36: "Australia", 398: "Kazakhstan",
           792: "Türkiye", 818: "Egypt", 854: "Burkina Faso", 120: "Cameroon", 466: "Mali", 204: "Benin", 32: "Argentina", 4: "Afghanistan", 834: "Tanzania"}


def unit_values(s, years, cy):
    """USD/t year to date, at the last month with customs values (CCA-filled months carry no value)."""
    v = s[s.ytd_musd.notna()]
    lm = int(v[v.year == cy].m.max()) if len(v[v.year == cy]) else None
    out = {}
    for y in years:
        r = v[(v.year == y) & (v.m == lm)]
        if lm and len(r) and r.ytd_kt.iloc[0]:
            out[int(y)] = rnd(r.ytd_musd.iloc[0] / r.ytd_kt.iloc[0] * 1000, 0)
    return out


def imports_block(g, ct, cca_yearly):
    if not len(g):
        return None
    out = {}
    for key, name in (("Cotton yarn", "yarn"), ("Cotton", "cotton"), ("Cotton+yarn", "fibre")):
        s = g[g.c == key]
        if not len(s):
            continue
        years = sorted(s.year.unique())
        cy = years[-1]
        last_m = int(s[s.year == cy].m.max())
        ytd = {int(y): rnd(s[(s.year == y) & (s.m == last_m)].ytd_kt.max(), 0) for y in years}
        ytdv = {int(y): rnd(s[(s.year == y) & (s.m == last_m)].ytd_musd.max(), 0) for y in years}
        full = {int(y): rnd(s[(s.year == y) & (s.m == 12)].ytd_kt.max(), 0) for y in years if y < cy}
        monthly = {int(y): [rnd(s[(s.year == y) & (s.m == m)].m_kt.max(), 0) if len(s[(s.year == y) & (s.m == m)]) else None for m in range(1, 13)] for y in years}
        prev = [ytd[y] for y in years if cy - 5 <= y < cy and ytd.get(y)]
        out[name] = {"year": int(cy), "last_month": last_m, "ytd_kt": ytd, "ytd_musd": ytdv, "full_kt": full, "monthly_kt": monthly,
                     "ytd_yoy_pct": rnd((ytd[cy] / ytd[cy - 1] - 1) * 100) if ytd.get(cy - 1) else None,
                     "ytd_vs_avg5_pct": rnd((ytd[cy] / np.mean(prev) - 1) * 100) if prev else None,
                     "avg5_kt": rnd(np.mean(prev), 0) if prev else None,
                     "unit_usd_t": unit_values(s, years, cy),
                     "src_last_month": "CCA import report (customs data quoted before the English bulletin)" if "src" in s and s[(s.year == cy) & (s.m == last_m)].src.notna().any() else "China customs",
                     "rank": int(sorted([ytd[y] for y in years], reverse=True).index(ytd[cy]) + 1), "n_years": len(years)}
    if "yarn" in out and "cotton" in out:
        y, c = out["yarn"], out["cotton"]
        cy = y["year"]
        lm = min(y["last_month"], c["last_month"])
        comb = {}
        for yr in y["ytd_kt"]:
            a = g[(g.c == "Cotton yarn") & (g.year == yr) & (g.m == lm)].ytd_kt.max()
            b = g[(g.c == "Cotton") & (g.year == yr) & (g.m == lm)].ytd_kt.max()
            if pd.notna(a) and pd.notna(b):
                comb[int(yr)] = {"cotton": rnd(b, 0), "yarn_lint_eq": rnd(a * YARN_TO_LINT, 0), "total": rnd(b + a * YARN_TO_LINT, 0),
                                 "yarn_share_pct": rnd(a * YARN_TO_LINT / (b + a * YARN_TO_LINT) * 100)}
        out["combined"] = {"through_month": lm, "by_year": comb, "factor": YARN_TO_LINT}
    # origins (Comtrade, HS 5205 yarn and 5201 cotton)
    if len(ct):
        org = {}
        for hs, name in ((5205, "yarn"), (5201, "cotton")):
            s = ct[(ct.hs == hs) & (ct.partner_code != 0)].copy()
            if not len(s):
                continue
            s["y"] = s.period // 100
            s["p"] = s.partner_code.map(PARTNER).fillna("Other")
            t = s.groupby(["p", "y"]).net_kg.sum().unstack(1).fillna(0) / 1e6
            share = (t / t.sum() * 100).round(1)
            last = int(t.columns.max())
            top = t[last].sort_values(ascending=False).index[:8].tolist()
            org[name] = {"years": [int(c) for c in t.columns], "kt": {p: [rnd(v, 1) for v in t.loc[p]] for p in top},
                         "share": {p: [rnd(v, 1) for v in share.loc[p]] for p in top}, "last_year": last}
        out["origins"] = org
        # HS 5205 / 5206 split by month, years Comtrade has
        w = ct[(ct.partner_code == 0) & ct.hs.isin([5205, 5206])].copy()
        w["y"], w["m"] = w.period // 100, w.period % 100
        out["hs_split"] = {int(y): {str(h): rnd(gg[gg.hs == h].net_kg.sum() / 1e6, 1) for h in (5205, 5206)} for y, gg in w.groupby("y")}
    if cca_yearly:
        out["cotton_cca_yearly"] = cca_yearly
    return out


def grains_block(g):
    if not len(g):
        return None
    keys = [("Soya beans", "Soybeans"), ("Maize", "Corn"), ("Wheat", "Wheat"), ("Barley", "Barley"), ("Grain sorghum", "Sorghum"), ("Cotton", "Cotton"), ("Cotton yarn", "Cotton yarn")]
    cy = int(g.year.max())
    lm = int(g[(g.year == cy) & (g.c == "Soya beans")].m.max())
    rows = []
    for k, lab in keys:
        s = g[(g.c == k) & (g.m == lm)]
        if not len(s):
            continue
        v = {int(r.year): rnd(r.ytd_kt, 0) for r in s.itertuples()}
        prev = [v[y] for y in v if cy - 5 <= y < cy]
        rows.append({"name": lab, "ytd": v, "yoy_pct": rnd((v[cy] / v[cy - 1] - 1) * 100) if v.get(cy) and v.get(cy - 1) else None,
                     "vs_avg5_pct": rnd((v[cy] / np.mean(prev) - 1) * 100) if v.get(cy) and prev else None})
    return {"year": cy, "through_month": lm, "rows": rows}


# ── prices ───────────────────────────────────────────────────────────────────
def load_tv():
    p = ROOT / "data" / "china" / "tv_prices.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    return d


def cca_prices():
    p = RAW / "cca_tables.json"
    if not p.exists():
        return pd.DataFrame(), pd.DataFrame(), {}
    t = json.loads(p.read_text())
    cc = pd.DataFrame()
    rows = t.get("ccindex") or []
    if rows:
        cc = pd.DataFrame([[r[0], r[5]] for r in rows if len(r) > 5], columns=["date", "cc3128"])
        cc["date"] = pd.to_datetime(cc.date, errors="coerce")
        cc["cc3128"] = pd.to_numeric(cc.cc3128, errors="coerce")
        cc = cc.dropna().drop_duplicates("date").set_index("date").sort_index()
    cl = pd.DataFrame()
    rows = t.get("cotlook") or []
    if rows:
        cl = pd.DataFrame([r[:5] for r in rows], columns=["date", "a", "chg", "l1", "ls"])
        cl["date"] = pd.to_datetime(cl.date, errors="coerce")
        for k in ("a", "l1", "ls"):
            cl[k] = pd.to_numeric(cl[k], errors="coerce")
        cl = cl.dropna(subset=["date"]).drop_duplicates("date").set_index("date").sort_index()[["a", "l1", "ls"]]
    return cc, cl, t


def prices_block(tv, cc, cl, latest_quotes):
    out = {"target_yuan_t": TARGET_PRICE}
    if not len(tv):
        return out
    fx = tv.USDCNY.ffill()
    df = pd.DataFrame(index=tv.index.union(cc.index) if len(cc) else tv.index)
    df["fx"] = fx.reindex(df.index).ffill()
    df["cf"] = tv.CF1.reindex(df.index)
    df["cy"] = tv.CY1.reindex(df.index)
    df["ct"] = tv.CT1.reindex(df.index).ffill(limit=3)
    if len(cc):
        df["cc"] = cc.cc3128.reindex(df.index)
    if len(cl):
        df = df.reindex(df.index.union(cl.index))
        df["fx"] = df.fx.ffill()
        for k in ("a", "l1", "ls"):
            df[k] = cl[k].reindex(df.index)
        df["imp_margin_1pct"] = df.cc - df.l1
        df["imp_margin_sliding"] = df.cc - df.ls
    df = df[df.index <= pd.Timestamp(date.today())]
    for k in ("cf", "cy", "cc"):
        if k in df:
            df[k + "_clb"] = c_lb(df[k], df.fx)
            df[k + "_clb_xvat"] = df[k + "_clb"] / (1 + VAT)
    df["target_clb"] = c_lb(TARGET_PRICE, df.fx)
    if "cc" in df:
        df["cc_vs_target"] = df.cc - TARGET_PRICE
    wk = df.resample("W-FRI").last().dropna(subset=["fx"])
    wk = wk[wk.index >= "2017-01-01"]
    out["weekly"] = {"date": [d.strftime("%Y-%m-%d") for d in wk.index]}
    for k in ("cf_clb", "cy_clb", "cc_clb", "cc_clb_xvat", "cf_clb_xvat", "ct", "target_clb", "cc", "cf", "cy", "fx", "a", "l1", "ls", "imp_margin_1pct", "imp_margin_sliding", "cc_vs_target"):
        if k in wk:
            out["weekly"][k] = [rnd(v, 2) for v in wk[k]]
    last = df.dropna(subset=["cf"]).iloc[-1]
    L = {"date": df.dropna(subset=["cf"]).index[-1].strftime("%Y-%m-%d"), "fx": rnd(last.fx, 4), "cf": rnd(last.cf, 0), "cf_clb": rnd(last.cf_clb, 2),
         "cy": rnd(last.cy, 0), "cy_clb": rnd(last.cy_clb, 2), "ct": rnd(df.ct.dropna().iloc[-1], 2), "target_clb": rnd(c_lb(TARGET_PRICE, last.fx), 2)}
    if "cc" in df and df.cc.notna().any():
        lc = df.dropna(subset=["cc"]).iloc[-1]
        L.update({"cc_date": df.dropna(subset=["cc"]).index[-1].strftime("%Y-%m-%d"), "cc": rnd(lc.cc, 0), "cc_clb": rnd(c_lb(lc.cc, lc.fx), 2),
                  "cc_clb_xvat": rnd(c_lb(lc.cc, lc.fx) / (1 + VAT), 2), "cc_vs_target": rnd(lc.cc - TARGET_PRICE, 0),
                  "cc_vs_target_pct": rnd((lc.cc / TARGET_PRICE - 1) * 100, 1)})
        # Sep-Nov average so far (the target-price subsidy is paid on the gap between 18,600 and the harvest-season market price)
        s0 = pd.Timestamp(date.today().year if date.today().month >= 9 else date.today().year - 1, 9, 1)
        win = df.cc[(df.index >= s0) & (df.index < s0 + pd.DateOffset(months=3))].dropna()
        if len(win):
            L["harvest_avg_cc"] = rnd(win.mean(), 0)
            L["implied_subsidy_yuan_t"] = rnd(max(0.0, TARGET_PRICE - win.mean()), 0)
        # percentile of the domestic price vs the same week of past years
    if "a" in df and df.a.notna().any():
        la = df.dropna(subset=["a"]).iloc[-1]
        L.update({"a_date": df.dropna(subset=["a"]).index[-1].strftime("%Y-%m-%d"), "cotlook_a": rnd(la.a, 2), "a_1pct_yuan": rnd(la.l1, 0), "a_sliding_yuan": rnd(la.ls, 0)})
        m = df.dropna(subset=["imp_margin_1pct"])
        if len(m):
            L["imp_margin_1pct"] = rnd(m.imp_margin_1pct.iloc[-1], 0)
            L["imp_margin_sliding"] = rnd(m.imp_margin_sliding.iloc[-1], 0)
    for k, v in (latest_quotes or {}).items():
        L["q_" + k] = v
    # spreads
    if L.get("cc_clb_xvat") and L.get("cotlook_a"):
        L["cc_xvat_vs_a"] = rnd(L["cc_clb_xvat"] - L["cotlook_a"], 2)
    L["cf_vs_ct"] = rnd(L["cf_clb"] - L["ct"], 2) if L.get("cf_clb") and L.get("ct") else None
    L["cf_xvat_vs_ct"] = rnd(L["cf_clb"] / (1 + VAT) - L["ct"], 2) if L.get("cf_clb") and L.get("ct") else None
    L["cy_minus_cf"] = rnd(L["cy"] - L["cf"], 0) if L.get("cy") and L.get("cf") else None
    # history of the CF-CT spread: where today's sits (weekly, since 2017)
    sp = (wk.cf_clb / (1 + VAT) - wk.ct).dropna()
    if len(sp):
        out["spread_cf_ct_xvat_pctile"] = rnd((sp < sp.iloc[-1]).mean() * 100, 0)
        out["spread_cf_ct_xvat_avg"] = rnd(sp.mean(), 2)
    ym = (wk.cy - wk.cf).dropna()
    if len(ym):
        out["yarn_margin_pctile"] = rnd((ym < ym.iloc[-1]).mean() * 100, 0)
        out["yarn_margin_avg"] = rnd(ym[ym.index >= ym.index[-1] - pd.DateOffset(years=5)].mean(), 0)
    out["latest"] = L
    return out


def polyester_block(tv):
    """Cotton vs polyester in China: Zhengzhou cotton (CF) against polyester staple fibre (PF) and PTA (TA), and Brent."""
    need = {"CF1", "PF1"}
    if not len(tv) or not need.issubset(tv.columns) or tv.PF1.notna().sum() < 100:
        return None
    w = tv.resample("W-FRI").last()
    w = w[w.index >= "2020-10-01"]
    w["ratio"] = w.CF1 / w.PF1
    w["pf_clb"] = c_lb(w.PF1, w.USDCNY.ffill())
    w["pf_clb_xvat"] = w.pf_clb / (1 + VAT)
    w["ct_pf"] = w.CT1 / w.pf_clb_xvat
    w = w.dropna(subset=["ratio"])
    last = w.iloc[-1]
    ago = lambda col, weeks: w[col].dropna().iloc[-weeks - 1] if w[col].notna().sum() > weeks else None
    chg = lambda col, weeks: rnd((w[col].dropna().iloc[-1] / ago(col, weeks) - 1) * 100) if ago(col, weeks) else None
    r = w.ratio.dropna()
    out = {"date": w.index[-1].strftime("%Y-%m-%d"), "cf": rnd(last.CF1, 0), "pf": rnd(last.PF1, 0), "ta": rnd(last.get("TA1"), 0), "brent": rnd(last.get("BRENT"), 2),
           "ratio": rnd(last.ratio, 2), "ratio_pctile": rnd((r < r.iloc[-1]).mean() * 100, 0), "ratio_avg": rnd(r.mean(), 2), "ratio_min": rnd(r.min(), 2), "ratio_max": rnd(r.max(), 2),
           "ratio_26w_ago": rnd(r.iloc[-27], 2) if len(r) > 27 else None, "pf_clb": rnd(last.pf_clb, 1), "pf_clb_xvat": rnd(last.pf_clb_xvat, 1),
           "ct_pf": rnd(last.ct_pf, 2), "ct_pf_avg": rnd(w.ct_pf.mean(), 2),
           "chg_26w": {k: chg(c, 26) for k, c in (("brent", "BRENT"), ("pta", "TA1"), ("psf", "PF1"), ("cotton", "CF1"), ("ice", "CT1"))},
           "chg_52w": {k: chg(c, 52) for k, c in (("brent", "BRENT"), ("pta", "TA1"), ("psf", "PF1"), ("cotton", "CF1"), ("ice", "CT1"))}}
    if "BRENT" in w:
        x = w[["PF1", "BRENT"]].dropna().pct_change().dropna()
        x = x[x.index >= x.index[-1] - pd.DateOffset(years=3)]
        out["corr_psf_brent_3y"] = rnd(x.PF1.corr(x.BRENT), 2)
    out["weekly"] = {"date": [d.strftime("%Y-%m-%d") for d in w.index], "cf": [rnd(v, 0) for v in w.CF1], "pf": [rnd(v, 0) for v in w.PF1],
                     "ta": [rnd(v, 0) for v in w.get("TA1", pd.Series(index=w.index, dtype=float))], "brent": [rnd(v, 2) for v in w.get("BRENT", pd.Series(index=w.index, dtype=float))],
                     "ratio": [rnd(v, 3) for v in w.ratio]}
    return out


MSP = {2026: {"medium": 8267, "long": 8667}}     # India kapas MSP, Rs/quintal (2026-27 kharif)
CANDY_LB = 355.62 * 2.20462


def india_block():
    """Indian spot cotton (CAI daily spot, Gujarat ICS-105 29 mm = the Shankar-6 benchmark) in c/lb, vs the MSP."""
    p = ROOT / "data" / "india" / "cai_spot.csv"
    m = ROOT / "data" / "markets" / "closes.csv"
    if not p.exists() or not m.exists():
        return None
    d = pd.read_csv(p, parse_dates=["date"])
    d = d[(d.grade_standard == "ICS-105") & (d.staple == "29 mm") & (d.season == "current")]
    b = d[d.growth == "GUJ"].set_index("date").per_candy
    alt = d[d.growth == "M/M(P)"].set_index("date").per_candy
    s = b.combine_first(alt).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    if len(s) < 5:
        return None
    fx = pd.read_csv(m, index_col=0, parse_dates=True)["INR=X"].dropna()
    fx = fx.reindex(fx.index.union(s.index)).ffill().reindex(s.index)
    clb = s / fx / CANDY_LB * 100
    yr = s.index[-1].year if s.index[-1].month >= 9 else s.index[-1].year - 1
    msp = MSP.get(yr)
    out = {"date": s.index[-1].strftime("%Y-%m-%d"), "rs_candy": rnd(s.iloc[-1], 0), "clb": rnd(clb.iloc[-1], 1), "inr": rnd(fx.iloc[-1], 2),
           "chg_1y_pct": rnd((s.iloc[-1] / s[s.index <= s.index[-1] - pd.DateOffset(years=1)].iloc[-1] - 1) * 100, 1) if (s.index <= s.index[-1] - pd.DateOffset(years=1)).any() else None,
           "chg_3m_pct": rnd((s.iloc[-1] / s[s.index <= s.index[-1] - pd.DateOffset(months=3)].iloc[-1] - 1) * 100, 1) if (s.index <= s.index[-1] - pd.DateOffset(months=3)).any() else None,
           "weekly": {"date": [x.strftime("%Y-%m-%d") for x in s.resample("W-FRI").last().dropna().index],
                      "clb": [rnd(v, 1) for v in clb.resample("W-FRI").last().dropna()], "rs": [rnd(v, 0) for v in s.resample("W-FRI").last().dropna()]}}
    if msp:
        # lint cost implied by buying kapas at MSP: 34% lint out-turn, cottonseed credited at Rs 35/kg, ginning ~Rs 1,500/candy
        kg = (msp["medium"] / 100 - 0.64 * 35) / 0.34
        out["msp"] = {"season": f"{yr}/{str(yr + 1)[2:]}", "kapas_medium": msp["medium"], "kapas_long": msp["long"],
                      "lint_equiv_rs_candy": rnd(kg * 355.62 + 1500, -2), "assumptions": "34% lint out-turn, seed credited at Rs 35/kg, ginning Rs 1,500/candy"}
        out["msp"]["lint_equiv_clb"] = rnd(out["msp"]["lint_equiv_rs_candy"] / fx.iloc[-1] / CANDY_LB * 100, 1)
    return out


def psd_china():
    """USDA PSD China cotton by marketing year (Aug-Jul), thousand t."""
    o = {}
    p = ROOT / "data" / "geo" / "raw" / "psd.json"
    if p.exists():
        for cc, _, y, attr, v in json.loads(p.read_text())["data"]["cotton"]["rows"]:
            if cc == "CH":
                o.setdefault(int(y), {})[attr] = v
    snap = RAW / "usda_psd_china.json"
    if snap.exists():
        for y, a in json.loads(snap.read_text())["rows"].items():
            for k, v in a.items():
                o.setdefault(int(y), {}).setdefault(k, v)
    return {y: {k: rnd(v * 0.217725, 0) if k not in ("Yield", "Area Harvested") else v for k, v in a.items()} for y, a in sorted(o.items()) if y >= 2015}


# ── the brief ────────────────────────────────────────────────────────────────
def brief(E, P, I, X, SP, G):  # noqa: C901
    S = []

    def f0(v):
        return "–" if v is None else f"{v:,.0f}"

    def pct(v, d=1):
        return "–" if v is None else f"{v:+.{d}f}%"
    # crop
    if E:
        L = E["latest"]
        ly = E.get("last_year_final_kt")
        pj = E.get("projection")
        u = (E.get("usda") or {}).get(E["season"], {}).get("Production")
        txt = (f"The China Cotton Association's latest survey ({L['survey']}) puts the {E['season']} crop at **{L['prod_kt']/1000:.2f} mt**"
               + (f" ({pct((L['prod_kt']/ly-1)*100)} vs last season's {E['last_year_final_src']} of {ly/1000:.2f} mt)" if ly else "")
               + (f", {'+' if L['prod_kt'] >= L['prev_survey_kt'] else ''}{(L['prod_kt']-L['prev_survey_kt']):,.0f} kt vs the previous survey" if L.get("prev_survey_kt") else "")
               + (f"; area {L['area_kmu']/1000:.2f} m mu ({L['area_kmu']/15000:.2f} m ha), yield {L['yield_kg_mu']:.1f} kg/mu ({L['yield_kg_mu']*15:,.0f} kg/ha)" if L.get("area_kmu") and L.get("yield_kg_mu") else "") + ".")
        if pj:
            txt += (f" From the same survey month to the association's final number, past seasons moved {pj['min_chg_pct']:+.1f}% to {pj['max_chg_pct']:+.1f}% (median {pj['median_chg_pct']:+.1f}%, {pj['n']} seasons): "
                    f"that points to a final of **{pj['kt']/1000:.2f} mt** (range {pj['lo_kt']/1000:.2f}–{pj['hi_kt']/1000:.2f}).")
        up = [m for m in E.get("moves", []) if m["final_src"] == "CCA final"]
        if up and all(m["chg_pct"] > 0 for m in up):
            ups = ", ".join("{} {:+.1f}%".format(m["season"], m["chg_pct"]) for m in up)
            txt += f" In the {len(up)} seasons with a published final figure it came in above the September survey ({ups}), so the risk skews up."
        if u:
            txt += f" USDA has {u/1000:.2f} mt ({u/0.217725/1000:.1f} m bales); compare the agencies' revisions rather than their levels."
        S.append({"h": "Crop size", "t": txt})
    # progress
    if P and P.get("latest"):
        parts = []
        for key, lab in (("xinjiang_pick", "Xinjiang picking"), ("national_pick", "National picking"), ("national_sell", "National seed-cotton selling"), ("xinjiang_sell", "Xinjiang selling")):
            z = P["latest"].get(key)
            if not z:
                continue
            p2 = f"{lab} {z['pct']:.1f}% at {z['obs'][5:]}"
            cmp = []
            if z.get("last_year") is not None:
                cmp.append(f"{z['pct']-z['last_year']:+.1f} pts vs last year")
            if z.get("avg5") is not None:
                cmp.append(f"{z['pct']-z['avg5']:+.1f} vs the {z['n_avg']}-season average")
            parts.append(p2 + (f" ({', '.join(cmp)})" if cmp else ""))
        if parts:
            pace = P["latest"].get("xinjiang_pick") or P["latest"].get("national_pick")
            fast = pace and pace.get("last_year") is not None and pace["pct"] > pace["last_year"] + 3
            slow = pace and pace.get("last_year") is not None and pace["pct"] < pace["last_year"] - 3
            S.append({"h": "Harvest pace", "t": "; ".join(parts) + "." + (" A fast harvest brings new-crop lint to market early: ginning and hedge selling on Zhengzhou come forward, which usually weighs on nearby prices in Oct–Dec." if fast else
                      " A slow harvest delays new-crop supply and keeps old-crop stocks and reserve sales in focus." if slow else "")})
    if SP is not None and len(SP):
        z = SP.sort_values("pub").iloc[-1]
        if S and S[-1]["h"] == "Harvest pace":
            S[-1]["t"] += f" Farmers' seed-cotton price {z.yuan_kg:.1f} yuan/kg" + (f" ({z.yoy_pct:+.1f}% y/y)" if pd.notna(z.yoy_pct) else "") + f" in the {z.pub} survey."
    # imports
    if I and "yarn" in I and "cotton" in I:
        y, c, cb = I["yarn"], I["cotton"], I.get("combined", {})
        cy, lm = y["year"], y["last_month"]
        t = (f"Jan–{MON[lm-1]} {cy} cotton yarn imports **{y['ytd_kt'][cy]:,.0f} kt** ({pct(y['ytd_yoy_pct'])} y/y, {pct(y['ytd_vs_avg5_pct'])} vs the 5-year average; #{y['rank']} of {y['n_years']} years) "
             f"and raw cotton **{c['ytd_kt'][c['year']]:,.0f} kt** ({pct(c['ytd_yoy_pct'])} y/y, {pct(c['ytd_vs_avg5_pct'])} vs average).")
        bc = cb.get("by_year", {})
        if bc.get(cy) and bc.get(cy - 1):
            t += (f" Counting yarn as lint (×{cb['factor']}), China has taken {bc[cy]['total']:,.0f} kt of foreign fibre through {MON[cb['through_month']-1]} vs {bc[cy-1]['total']:,.0f} kt a year ago; "
                  f"yarn is {bc[cy]['yarn_share_pct']:.0f}% of it.")
        uv = y["unit_usd_t"]
        if uv.get(cy) and uv.get(cy - 1):
            t += f" Imported yarn averages ${uv[cy]:,.0f}/t ({pct((uv[cy]/uv[cy-1]-1)*100)} y/y)."
        S.append({"h": "Imports", "t": t})
        # what it means
        m = []
        if y.get("ytd_yoy_pct") and y["ytd_yoy_pct"] > 15:
            m.append("Yarn is coming in much faster than raw cotton: mills and weavers are buying foreign yarn (mainly Vietnam, India, Pakistan, Uzbekistan) instead of spinning domestic lint. "
                     "Downstream fabric demand is there, but the import-quota and price structure favour yarn; this is demand for cotton outside China's quota system and it caps Chinese spinners' margins")
        if c.get("ytd_yoy_pct") is not None and c["ytd_yoy_pct"] > 30:
            m.append("raw cotton imports have recovered from last year's low base as the domestic premium over world prices widened and extra sliding-scale quota was issued")
        elif c.get("ytd_yoy_pct") is not None and c["ytd_yoy_pct"] < -20:
            m.append("raw cotton imports are well below last year: domestic supply and quota limits are holding them back")
        if X and X.get("latest", {}).get("imp_margin_1pct") is not None:
            L = X["latest"]
            v = L["imp_margin_1pct"]
            m.append(f"imported lint is {abs(v):,.0f} yuan/t {'below' if v > 0 else 'above'} the domestic price at 1% duty, so mills with quota {'have every reason to import' if v > 1000 else 'gain a little by importing' if v > 0 else 'have no reason to import'}; "
                     "the binding limit is quota, which is why foreign yarn (no quota) fills the gap")
        if m:
            S.append({"h": "What it means for demand", "t": ("; ".join(m) + ".")[0].upper() + ("; ".join(m) + ".")[1:]})
    O = (I or {}).get("origin_demand")
    if O and O.get("rows"):
        top = [r for r in O["rows"] if r["extra_lint_kt"] and r["extra_lint_kt"] > 20][:4]
        if top:
            t = ("China's extra yarn is cotton spun elsewhere: " + "; ".join(
                f"{r['country']} {r['extra_yarn_kt']:+,.0f} kt of yarn ≈ {r['extra_lint_mbales']:+.2f} m bales of lint" +
                (f" ({r['extra_pct_of_imports']:+.0f}% of its USDA imports; ≈{r['implied_us_mbales']:+.2f} m bales of US cotton at the usual {r['us_share5_pct']:.0f}% US share)" if r.get("implied_us_mbales") is not None else f" ({r['note']})")
                for r in top) + ". That supports US and Brazilian sales to Vietnam and the South Asian importers even while China's own lint imports are slow; "
                 "India and Uzbekistan mainly turn their own crops into yarn, which tightens their exportable cotton instead. Country split is an estimate (" + O["share_source"] + ").")
            S.append({"h": "Demand pulled into supplying countries", "t": t})
    # USDA check: marketing-year (Aug-Jul) imports so far vs the WASDE number, and mill use
    U = (I or {}).get("usda_check")
    if U and U.get("imports", {}).get("usda_kt"):
        a = U["imports"]
        hs = a["hist"]
        lo = min(x["share_pct"] for x in hs) if hs else None
        hi = max(x["share_pct"] for x in hs) if hs else None
        t = (f"USDA has China importing {a['usda_kt']/1000:.2f} mt ({a['usda_kt']/217.725:.1f} m bales) in {a['my']} (Aug–Jul). Aug–{a['through']} arrivals were {a['to_date_kt']:,.0f} kt, "
             f"{a['usda_pct_done']:.0f}% of that; in the last {len(hs)} seasons {lo:.0f}–{hi:.0f}% (median {a['median_share_pct']:.0f}%) had arrived by the end of {a['through']}, "
             f"so the pace points to about {a['pace_implied_kt']/1000:.2f} mt.")
        if a.get("last_my"):
            l = a["last_my"]
            t += f" For {l['my']} customs shows {l['actual_kt']/1000:.2f} mt against USDA's {l['usda_kt']/1000:.2f} mt, so USDA tracks customs closely once the year is done."
        gap = a["pace_implied_kt"] - a["usda_kt"]
        if gap < -150:
            t += (f" Read: on pace alone USDA looks about {abs(gap)/217.725:.1f} m bales high (two months is a weak guide: the share by now has ranged {lo:.0f}–{hi:.0f}%), and it holds only if buying picks up when the {int(a['my'][:4])+1} quota is issued in January; "
                  "early arrivals are slow because this year's quota is used up, the domestic crop is early and large, and mills are importing yarn instead.")
        elif gap > 150:
            t += f" Read: the pace runs ahead of USDA by about {gap/217.725:.1f} m bales; an upward revision is likely if it holds."
        else:
            t += " Read: the pace is in line with USDA."
        # policy: extra sliding-scale quota and state-reserve restocking can lift imports beyond the pace
        try:
            P = json.loads((RAW / "policy_history.json").read_text())
            q = [x for x in P["sliding_quota"] if x["year"] >= 2018]
            given = [x for x in q if x["kt"]]
            sales = [x for x in P["reserve"] if x["type"] == "sale"]
            last_sale = sales[-1]
            imp_sold = last_sale.get("imported_kt") or last_sale["kt"]
            restock = a["pace_implied_kt"] + imp_sold
            t += (f" Policy can change this. Extra sliding-scale quota was issued in {len(given)} of the last {len(q)} years ("
                  + ", ".join(f"{x['year']} {x['kt']} kt" for x in q if x['kt']) + "); the one skip, 2024, came when reserve restocking had already lifted imports. "
                  f"The state reserve sold {last_sale['kt']:,.0f} kt from {last_sale['from'][5:7]}/{last_sale['from'][:4]} to {last_sale['to'][5:7]}/{last_sale['to'][:4]}, {imp_sold:,.0f} kt of it imported cotton. "
                  "After the 2023 sale (880 kt) the reserve restocked mostly with imports in 2023/24, about 3 m bales above the prior year. "
                  f"Pace plus replacing the imported cotton it just sold gives about {restock/1000:.2f} mt ({restock/217.725:.1f} m bales); an early 2027 sliding-scale quota would add more (the pace already reflects a typical year's quota, so count only an unusually large one). "
                  "So USDA's number needs restocking or extra quota, and history says at least one usually comes; watch the reserve's purchase announcements and the 2027 quota.")
        except Exception:
            pass
        u = U.get("use") or {}
        if u.get("usda_kt"):
            bal = (E or {}).get("balance") or []
            cca_use = sorted(bal, key=lambda r: r["season"])[-1]["use"] * 10 if bal else None
            t += (f" USDA's mill use is {u['usda_kt']/1000:.2f} mt ({u['usda_kt']/217.725:.1f} m bales, {(u['usda_kt']/u['usda_prev_kt']-1)*100:+.1f}%)"
                  + (f" vs the CCA's {cca_use/1000:.2f} mt" if cca_use else "") + ".")
            if u.get("yarn_to_date_kt") and u.get("yarn_to_date_prev_kt"):
                t += (f" Yarn imports Aug–{a['through']} are {u['yarn_to_date_kt']:,.0f} kt vs {u['yarn_to_date_prev_kt']:,.0f} kt a year earlier "
                      f"({(u['yarn_to_date_kt']/u['yarn_to_date_prev_kt']-1)*100:+.0f}%): every tonne of imported yarn is about {YARN_TO_LINT} t of lint that Chinese mills do not spin, "
                      "so a mill-use increase looks optimistic while yarn imports run this high; China's fibre demand is real but it is being met offshore, which helps exporters that sell to Vietnam, Pakistan and India more than those selling lint to China.")
        S.append({"h": "USDA check", "t": t})
    # the association's balance sheet: demand and stocks
    bal = (E or {}).get("balance") or []
    if bal:
        b = sorted(bal, key=lambda r: r["season"])
        c, p_ = b[-1], (b[-2] if len(b) > 1 else None)
        su = c["end"] / c["use"] * 100
        t = (f"CCA balance sheet {c['season']}/{str(c['season']+1)[2:]}: production {c['prod']/100:.2f} mt, imports {c['imp']/100:.2f}, mill use {c['use']/100:.2f}, ending stocks {c['end']/100:.2f} mt "
             f"(stocks/use {su:.0f}%)")
        if p_:
            t += f"; mill use {(c['use']/p_['use']-1)*100:+.1f}% vs {p_['season']}/{str(p_['season']+1)[2:]} and stocks {c['end']-p_['end']:+.0f} 10kt"
        t += (f". Mill use exceeds the crop by {(c['use']-c['prod'])/100:.2f} mt, covered by lint imports ({c['imp']/100:.2f} mt) and stocks. "
              "Imported yarn comes on top of this: it is weavers' demand that bypasses Chinese spinners")
        yl = ((I or {}).get("yarn") or {}).get("full_kt") or {}
        if yl:
            ly = max(yl)
            t += f" (calendar {ly}: {yl[ly]:,.0f} kt of yarn, ≈{yl[ly]*YARN_TO_LINT/1000:.2f} mt of lint), so China's total cotton use is larger than the mill-use line suggests"
        t += "."
        S.append({"h": "Balance", "t": t.replace(" 10kt", "0 kt")})
    # prices and support
    if X and X.get("latest"):
        L = X["latest"]
        t = []
        if L.get("cc"):
            t.append(f"CCIndex 3128B {L['cc']:,.0f} yuan/t on {L['cc_date']} = **{L['cc_clb']:.1f}¢/lb** ({L['cc_clb_xvat']:.1f}¢ ex-VAT) at USD/CNY {L['fx']:.3f}")
            t.append(f"that is {abs(L['cc_vs_target']):,.0f} yuan/t ({L['cc_vs_target_pct']:+.1f}%) {'below' if L['cc_vs_target'] < 0 else 'above'} the 18,600 yuan/t Xinjiang target price ({L['target_clb']:.1f}¢/lb)")
            if L.get("implied_subsidy_yuan_t") is not None:
                t.append(f"at the harvest-season average so far ({L['harvest_avg_cc']:,.0f}) the target-price payment would be about {L['implied_subsidy_yuan_t']:,.0f} yuan/t, paid to Xinjiang growers, so it supports planting rather than the lint price")
        t.append(f"Zhengzhou cotton (CF front) {L['cf']:,.0f} yuan/t = {L['cf_clb']:.1f}¢/lb vs ICE {L['ct']:.2f}¢ ({L['cf_xvat_vs_ct']:+.1f}¢ ex-VAT"
                 + (f"; {ordinal(X['spread_cf_ct_xvat_pctile'])} percentile since 2017" if X.get("spread_cf_ct_xvat_pctile") is not None else "") + ")")
        if L.get("cotlook_a"):
            t.append(f"Cotlook A {L['cotlook_a']:.2f}¢ ({L['a_date']}) lands at {L['a_1pct_yuan']:,.0f} yuan/t inside the 1% quota and {L['a_sliding_yuan']:,.0f} under sliding-scale quota, "
                     f"so imported cotton is {abs(L['imp_margin_1pct']):,.0f} / {abs(L['imp_margin_sliding']):,.0f} yuan/t {'cheaper' if L['imp_margin_1pct'] > 0 else 'dearer'} than domestic 3128B")
        if L.get("cy_minus_cf") is not None:
            t.append(f"Zhengzhou yarn minus cotton {L['cy_minus_cf']:,.0f} yuan/t" + (f" vs a 5-year average of {X['yarn_margin_avg']:,.0f}" if X.get("yarn_margin_avg") else "") + " (a rough spinning margin)")
        S.append({"h": "Prices and support", "t": "; ".join(t) + "."})
    # bottom line first
    bl = []
    if E:
        L = E["latest"]; ly = E.get("last_year_final_kt")
        if ly:
            ch = (L["prod_kt"] / ly - 1) * 100
            bl.append(f"a {'smaller' if ch < -1 else 'larger' if ch > 1 else 'similar'} crop ({L['prod_kt']/1000:.2f} mt, {ch:+.1f}%)")
    if P and P.get("latest", {}).get("xinjiang_pick"):
        z = P["latest"]["xinjiang_pick"]
        if z.get("last_year") is not None:
            bl.append("an early harvest" if z["pct"] > z["last_year"] + 3 else "a late harvest" if z["pct"] < z["last_year"] - 3 else "a normal harvest pace")
    if I and I.get("yarn", {}).get("ytd_yoy_pct") is not None:
        bl.append(f"yarn imports {I['yarn']['ytd_yoy_pct']:+.0f}% and cotton imports {I['cotton']['ytd_yoy_pct']:+.0f}% y/y")
    if X and X.get("latest", {}).get("cc"):
        Lx = X["latest"]
        bl.append(f"domestic lint {abs(Lx['cc_vs_target']):,.0f} yuan/t {'under' if Lx['cc_vs_target'] < 0 else 'over'} the target price" + (f" and {Lx['imp_margin_1pct']:,.0f} yuan/t over landed imports" if Lx.get("imp_margin_1pct") else ""))
    if bl:
        read = ("Supply is not the constraint and imported fibre is cheap, so Chinese prices should hold a premium to the world but struggle to rally while new-crop sales are heavy; "
                "strong yarn imports are the main channel through which China adds to world cotton demand this year.") if (X and (X.get("latest", {}).get("imp_margin_1pct") or 0) > 1000) else \
               "Domestic and world prices are close, so import demand depends on quota and mill margins rather than price."
        S.insert(0, {"h": "Bottom line", "t": "China has " + ", ".join(bl) + ". " + read})
    IN = (X or {}).get("india")
    if IN:
        L = (X or {}).get("latest", {})
        t = (f"Shankar-6 (CAI spot, Gujarat 29 mm) {IN['rs_candy']:,.0f} Rs/candy on {IN['date']} = **{IN['clb']:.1f}¢/lb** at {IN['inr']:.1f} Rs/$"
             + (f" ({IN['chg_1y_pct']:+.0f}% y/y in rupees)" if IN.get("chg_1y_pct") is not None else "") + "; "
             + (f"Cotlook A {L['cotlook_a']:.1f}¢, " if L.get("cotlook_a") else "") + f"ICE {L.get('ct', 0):.1f}¢, China 3128B {L.get('cc_clb_xvat', 0):.1f}¢ ex-VAT.")
        if IN.get("msp"):
            mm = IN["msp"]
            t += (f" The {mm['season']} MSP (kapas {mm['kapas_medium']:,}/{mm['kapas_long']:,} Rs/quintal medium/long) implies lint at roughly {mm['lint_equiv_rs_candy']:,.0f} Rs/candy "
                  f"({mm['lint_equiv_clb']:.0f}¢/lb; {mm['assumptions']}), so Indian lint is {'at or below' if IN['rs_candy'] <= mm['lint_equiv_rs_candy'] * 1.02 else 'above'} the support level: "
                  + ("CCI buying at MSP sets the floor and keeps Indian cotton out of export competition unless world prices rise." if IN['rs_candy'] <= mm['lint_equiv_rs_candy'] * 1.05 else "the market, not CCI, is setting the price."))
        S.append({"h": "India", "t": t})
    PY = (X or {}).get("polyester")
    if PY:
        c6 = PY["chg_26w"]
        t = (f"Brent {PY['brent']:.0f}$ ({c6['brent']:+.0f}% in 6 months) has pushed PTA {c6['pta']:+.0f}% and polyester staple fibre {c6['psf']:+.0f}% "
             f"to {PY['pf']:,.0f} yuan/t ({PY['pf_clb']:.0f}¢/lb, {PY['pf_clb_xvat']:.0f}¢ ex-VAT), while Zhengzhou cotton moved {c6['cotton']:+.0f}%. "
             f"Cotton now costs {PY['ratio']:.2f}× polyester in China, {ordinal(PY['ratio_pctile'])} percentile since PSF futures listed (range {PY['ratio_min']:.2f}–{PY['ratio_max']:.2f}, average {PY['ratio_avg']:.2f}"
             + (f"; {PY['ratio_26w_ago']:.2f} six months ago" if PY.get("ratio_26w_ago") else "") + "). "
             f"ICE cotton is {PY['ct_pf']:.2f}× Chinese PSF ex-VAT (average {PY['ct_pf_avg']:.2f}). ")
        if PY["ratio"] < PY["ratio_avg"] * 0.9:
            t += ("Cotton is unusually cheap against polyester: spinners shift blends toward cotton when the ratio is this low, which adds to cotton use with a lag of a few months, "
                  "provided crude stays high; polyester capacity is ample, so the PSF rally depends on oil rather than tight fibre supply.")
        elif PY["ratio"] > PY["ratio_avg"] * 1.1:
            t += "Cotton is expensive against polyester, so blends lean toward synthetics."
        else:
            t += "The ratio is near its average, so substitution is not a strong force either way."
        if PY.get("corr_psf_brent_3y") is not None:
            t += f" Weekly PSF and Brent changes correlate {PY['corr_psf_brent_3y']:.2f} over three years."
        S.append({"h": "Cotton vs polyester", "t": t})
    if G:
        r = {x["name"]: x for x in G["rows"]}
        t = ", ".join(f"{k.lower()} {r[k]['ytd'][G['year']]/1000:.1f} mt ({pct(r[k]['yoy_pct'],0)})" for k in ("Soybeans", "Corn", "Wheat", "Barley", "Sorghum") if k in r and r[k]["ytd"].get(G["year"]))
        S.append({"h": "Grains (context)", "t": f"Jan–{MON[G['through_month']-1]} {G['year']} imports, customs: {t}."})
    return S


def clean(o):
    """JSON-safe: numpy scalars -> python, NaN -> None, dict keys -> str."""
    if isinstance(o, dict):
        return {str(int(k)) if isinstance(k, (np.integer,)) else str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp, date)):
        return o.isoformat()[:10]
    return o


def valid(out):
    """Refuse to publish a build that lost a block the page needs."""
    probs = []
    if len(out.get("brief") or []) < 4:
        probs.append("brief too short")
    for k in ("estimates", "progress", "imports", "prices"):
        if not out.get(k):
            probs.append(f"missing {k}")
    if out.get("imports") and not (out["imports"].get("yarn") and out["imports"].get("cotton")):
        probs.append("imports without cotton/yarn")
    return probs


def save(out, note):
    """Publish only a valid build; keep a dated copy of every published build (the page falls back to the latest one)."""
    out = clean(out)
    probs = valid(out)
    HIST = OUT.parent / "history"
    HIST.mkdir(parents=True, exist_ok=True)
    if probs:
        print("NOT PUBLISHED (previous cotton.json kept):", "; ".join(probs))
        sys.exit(1)
    txt = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(txt)
    json.loads(tmp.read_text())
    tmp.replace(OUT)
    day = out["generated"][:10]
    (HIST / f"cotton_{day}.json").write_text(txt)
    files = sorted(HIST.glob("cotton_*.json"))
    for f in files[:-90]:          # keep about four months of daily builds
        f.unlink()
    (HIST / "index.json").write_text(json.dumps({"latest": files[-1].name if files else None, "files": [f.name for f in files[-90:]]}))
    if note:
        n = OUT.parent / "esr_note.json"
        n.with_suffix(".tmp").write_text(json.dumps(clean(note), ensure_ascii=False))
        n.with_suffix(".tmp").replace(n)
    print("wrote", OUT, len(out["brief"]), "brief items; history", day)


def main():
    pr, est, sp = parse_articles()
    cc, cl, T = cca_prices()
    tv = load_tv()
    psd = psd_china()
    nbs = T.get("nbs")
    bal = T.get("balance")
    quotes = T.get("quotes") or {}
    E = estimates_block(est, nbs, bal, psd, T.get("cca_final"))
    P = progress_block(pr)
    G = gacc_monthly()
    G, filled = fill_from_reports(G, cca_import_reports())
    G = add_fibre(G)
    ct = comtrade()
    I = imports_block(G, ct, T.get("cotton_imports_yearly"))
    if I is not None:
        I["filled_from_cca"] = filled
        I["cumulative"] = {"cotton": my_cumulative(G, "Cotton"), "yarn": my_cumulative(G, "Cotton yarn"), "fibre": my_cumulative(G, "Cotton+yarn")}
        try:
            esr = next((c for c in json.loads((ROOT / "data" / "grains" / "derived" / "esr_brief.json").read_text())["commodities"] if c["key"] == "cotton"), None)
        except Exception:
            esr = None
        I["origin_demand"] = origin_demand(I, ct, esr)
        I["usda_check"] = usda_check(I, I["cumulative"], psd)
    X = prices_block(tv, cc, cl, quotes)
    if X is not None:
        X["polyester"] = polyester_block(tv)
        try:
            X["india"] = india_block()
        except Exception as e:
            print("india block skipped:", e)
    GR = grains_block(G[G.get("src", pd.Series(index=G.index, dtype=object)).isna()] if "src" in G else G)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "brief": brief(E, P, I, X, sp, GR),
           "estimates": E, "progress": P, "seed_price": sp.to_dict("records") if len(sp) else [], "imports": I, "prices": X, "grains": GR,
           "sources": {"cca": "https://www.china-cotton.org/", "gacc": "http://english.customs.gov.cn/statics/report/monthly.html",
                       "comtrade": "https://comtradeplus.un.org/", "target_price": "NDRC/MoF 2026-2028 cotton target price: 18,600 yuan/t (Xinjiang)"}}
    save(out, esr_note((I or {}).get("origin_demand"), I))
    for b in out["brief"]:
        print("-", b["h"], ":", b["t"][:600])


if __name__ == "__main__":
    main()
