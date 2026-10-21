"""US economic snapshot from free official sources (no API keys needed):

- BLS public API v2 (no key: 25 requests/day, 10 series each): CPI (headline, core, food at home, energy),
  PPI (final demand, core, farm products), nonfarm payrolls, unemployment rate, average hourly earnings,
  participation rate.
- BEA data mirrored by DBnomics (api.db.nomics.world, free): real GDP growth (q/q annualized), real consumer
  spending, PCE and core PCE price indexes, personal saving rate. ISM PMIs and University of Michigan sentiment
  also come from DBnomics when available.
- New York Fed markets API: effective fed funds rate, target range, SOFR.
- US Treasury: real yield curve (TIPS) -> 10-year real yield and breakeven inflation with the nominal curve.
(FRED is the usual one-stop source but its API needs a free key and fred.stlouisfed.org times out from
GitHub runners; everything here is the primary source or a mirror of it.)

Writes data/macro/us_econ.json.
"""
import json, time
from datetime import date, datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "macro"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
BLS = {
    "CUSR0000SA0": ("cpi", "CPI, all items (SA index)"), "CUSR0000SA0L1E": ("cpi_core", "Core CPI (SA index)"),
    "CUUR0000SA0": ("cpi_nsa", "CPI NSA"), "CUUR0000SA0L1E": ("cpi_core_nsa", "Core CPI NSA"),
    "CUSR0000SAF11": ("cpi_food_home", "CPI food at home"), "CUSR0000SA0E": ("cpi_energy", "CPI energy"),
    "WPSFD4": ("ppi", "PPI final demand (SA)"), "WPSFD49104": ("ppi_core", "PPI final demand less food and energy (SA)"),
    "WPU01": ("ppi_farm", "PPI farm products (NSA)"), "CES0000000001": ("payrolls", "Nonfarm payrolls (thousands, SA)"),
    "LNS14000000": ("unemp", "Unemployment rate (%)"), "CES0500000003": ("ahe", "Average hourly earnings ($, SA)"),
    "LNS11300000": ("lfpr", "Labor force participation (%)"),
}
DBN = {
    "gdp": ("BEA/NIPA-T10101/A191RL-Q", "Real GDP growth (% q/q annualized)"),
    "pce_real_q": ("BEA/NIPA-T10101/DPCERL-Q", "Real consumer spending growth (% q/q annualized)"),
    "pce_px": ("BEA/NIPA-T20804/DPCERG-M", "PCE price index"), "pce_core_px": ("BEA/NIPA-T20804/DPCCRG-M", "Core PCE price index"),
    "saving": ("BEA/NIPA-T20600/A072RC-M", "Personal saving rate (%)"),
}


def get(url, method="get", tries=3, **kw):
    for i in range(tries):
        try:
            r = getattr(requests, method)(url, headers={**H, **kw.pop("headers", {})}, timeout=60, **kw)
            if r.status_code == 200:
                return r
            print("  HTTP", r.status_code, url[:100])
        except Exception as e:
            print("  err", e, url[:100])
        time.sleep(4 * (i + 1))
    return None


def bls():
    out = {}
    ids = list(BLS)
    y = date.today().year
    for k in range(0, len(ids), 10):
        r = get("https://api.bls.gov/publicAPI/v2/timeseries/data/", method="post", headers={"Content-type": "application/json"},
                json={"seriesid": ids[k:k + 10], "startyear": str(y - 3), "endyear": str(y)})
        if r is None:
            continue
        j = r.json()
        for s in j.get("Results", {}).get("series", []):
            pts = []
            for d in s["data"]:
                if not d["period"].startswith("M") or d["period"] == "M13":
                    continue
                try:
                    pts.append([f"{d['year']}-{d['period'][1:]}", float(d["value"])])
                except ValueError:
                    pass
            out[BLS[s["seriesID"]][0]] = sorted(pts)
        print("bls", len(out), "series", j.get("message"))
        time.sleep(2)
    return out


def dbn(code):
    r = get(f"https://api.db.nomics.world/v22/series/{code}?observations=1")
    if r is None:
        return None
    try:
        d = r.json()["series"]["docs"][0]
        return [[p, v] for p, v in zip(d["period"], d["value"]) if v not in (None, "NA")]
    except Exception as e:
        print("dbn parse", code, e)
        return None


def dbn_find(provider_dataset, words):
    """First series in a DBnomics dataset whose name contains all words (ISM, UMich codes are not fixed here)."""
    r = get(f"https://api.db.nomics.world/v22/series/{provider_dataset}?limit=200&observations=1")
    if r is None:
        return None, None
    for s in r.json().get("series", {}).get("docs", []):
        nm = (s.get("series_name") or "").lower()
        if all(w in nm for w in words):
            return s.get("series_name"), [[p, v] for p, v in zip(s["period"], s["value"]) if v not in (None, "NA")]
    return None, None


def pct(a, b):
    return None if a is None or b in (None, 0) else 100 * (a / b - 1)


def series_stats(pts, kind):
    """kind: 'index' (m/m %, y/y %), 'level' (change), 'k' (monthly change in thousands)."""
    if not pts:
        return None
    last, prev = pts[-1], pts[-2] if len(pts) > 1 else None
    o = {"period": last[0], "value": last[1], "prev_period": prev[0] if prev else None, "prev": prev[1] if prev else None}
    if kind == "index":
        o["mom"] = pct(last[1], prev[1]) if prev else None
        o["mom_prev"] = pct(prev[1], pts[-3][1]) if len(pts) > 2 else None
        yago = [p for p in pts if p[0] == f"{int(last[0][:4]) - 1}{last[0][4:]}"]
        o["yoy"] = pct(last[1], yago[0][1]) if yago else None
        py = [p for p in pts if p[0] == f"{int(prev[0][:4]) - 1}{prev[0][4:]}"] if prev else []
        o["yoy_prev"] = pct(prev[1], py[0][1]) if py and prev else None
        # 3-month annualized
        o["ann3"] = (((last[1] / pts[-4][1]) ** 4) - 1) * 100 if len(pts) > 3 else None
        o["spark"] = [[p[0], round(pct(p[1], q[1]), 2)] for p in pts[-24:] for q in [x for x in pts if x[0] == f"{int(p[0][:4]) - 1}{p[0][4:]}"]]
    elif kind == "k":
        o["chg"] = last[1] - prev[1] if prev else None
        o["chg_prev"] = prev[1] - pts[-3][1] if len(pts) > 2 else None
        ch = [pts[i][1] - pts[i - 1][1] for i in range(1, len(pts))]
        o["avg3"] = sum(ch[-3:]) / 3 if len(ch) >= 3 else None
        o["spark"] = [[pts[i][0], round(pts[i][1] - pts[i - 1][1], 1)] for i in range(max(1, len(pts) - 24), len(pts))]
    else:
        o["chg"] = last[1] - prev[1] if prev else None
        o["spark"] = [[p[0], p[1]] for p in pts[-24:]]
    return o


def main():
    B = bls()
    ind = []
    def add(cat, key, name, pts, kind, unit, src, note=""):
        s = series_stats(pts, kind)
        if s:
            ind.append({"cat": cat, "key": key, "name": name, "kind": kind, "unit": unit, "source": src, "note": note, **s})
    # inflation
    add("Inflation", "cpi", "CPI (headline)", B.get("cpi_nsa") and B.get("cpi"), "index", "%", "BLS")
    if B.get("cpi_nsa") and ind and ind[-1]["key"] == "cpi":    # y/y from NSA (as published), m/m from SA
        y = series_stats(B["cpi_nsa"], "index")
        ind[-1].update({"yoy": y["yoy"], "yoy_prev": y["yoy_prev"], "spark": y["spark"]})
    add("Inflation", "cpi_core", "Core CPI (ex food & energy)", B.get("cpi_core"), "index", "%", "BLS")
    if B.get("cpi_core_nsa") and ind and ind[-1]["key"] == "cpi_core":
        y = series_stats(B["cpi_core_nsa"], "index")
        ind[-1].update({"yoy": y["yoy"], "yoy_prev": y["yoy_prev"], "spark": y["spark"]})
    add("Inflation", "cpi_food_home", "CPI food at home", B.get("cpi_food_home"), "index", "%", "BLS", "grocery prices: demand for meat, dairy, grain-based food")
    add("Inflation", "cpi_energy", "CPI energy", B.get("cpi_energy"), "index", "%", "BLS")
    add("Inflation", "ppi", "PPI final demand", B.get("ppi"), "index", "%", "BLS")
    add("Inflation", "ppi_core", "Core PPI", B.get("ppi_core"), "index", "%", "BLS")
    add("Inflation", "ppi_farm", "PPI farm products", B.get("ppi_farm"), "index", "%", "BLS", "prices received at the farm gate (NSA)")
    for key, (code, name) in [("pce_px", DBN["pce_px"]), ("pce_core_px", DBN["pce_core_px"])]:
        add("Inflation", key, "PCE inflation" if key == "pce_px" else "Core PCE inflation (Fed's target gauge)", dbn(code), "index", "%", "BEA via DBnomics")
    # jobs
    add("Jobs", "payrolls", "Nonfarm payrolls (monthly change, k)", B.get("payrolls"), "k", "k", "BLS")
    add("Jobs", "unemp", "Unemployment rate", B.get("unemp"), "level", "%", "BLS")
    add("Jobs", "ahe", "Average hourly earnings", B.get("ahe"), "index", "%", "BLS", "wage growth")
    add("Jobs", "lfpr", "Participation rate", B.get("lfpr"), "level", "%", "BLS")
    # growth
    for key in ("gdp", "pce_real_q"):
        code, name = DBN[key]
        add("Growth", key, name.replace(" (% q/q annualized)", ""), dbn(code), "level", "% q/q ann.", "BEA via DBnomics")
    add("Growth", "saving", "Personal saving rate", dbn(DBN["saving"][0]), "level", "%", "BEA via DBnomics")
    # ISM PMIs are licensed; the free mirror is stale, so they are left to the calendar (forecast/previous)
    try:
        name, pts = dbn_find("SCSMICH/MICS", ["sentiment"])
        if pts:
            add("Sentiment", "umich", "UMich consumer sentiment", pts, "level", "index", "University of Michigan via DBnomics")
    except Exception as e:
        print("umich", e)
    # drop anything stale (a mirror that stopped updating): monthly older than 6 months, quarterly older than 8
    def fresh(i):
        p = i["period"]
        try:
            if "Q" in p:
                y, q = p.split("-Q")
                d = date(int(y), int(q) * 3, 1)
                lim = 245
            else:
                d = date(int(p[:4]), int(p[5:7]), 1)
                lim = 190
            return (date.today() - d).days <= lim
        except Exception:
            return True
    stale = [i["name"] for i in ind if not fresh(i)]
    if stale:
        print("stale, dropped:", stale)
    ind[:] = [i for i in ind if fresh(i)]
    # rates
    rates = {}
    r = get("https://markets.newyorkfed.org/api/rates/unsecured/effr/last/260.json")
    if r is not None:
        rr = sorted(r.json()["refRates"], key=lambda x: x["effectiveDate"])
        last = rr[-1]
        rates.update({"effr": last["percentRate"], "target_lo": last.get("targetRateFrom"), "target_hi": last.get("targetRateTo"), "effr_date": last["effectiveDate"],
                      "effr_hist": [[x["effectiveDate"], x["percentRate"]] for x in rr]})
        tgt = [(x["effectiveDate"], x.get("targetRateTo")) for x in rr]
        changes = [(tgt[i][0], tgt[i][1] - tgt[i - 1][1]) for i in range(1, len(tgt)) if tgt[i][1] != tgt[i - 1][1]]
        rates["last_moves"] = changes[-4:]
    r = get("https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json")
    if r is not None:
        x = r.json()["refRates"][0]
        rates.update({"sofr": x["percentRate"], "sofr_date": x["effectiveDate"]})
    y = date.today().year
    r = get(f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve&field_tdr_date_value={y}&page&_format=csv")
    if r is not None and r.text.startswith("Date"):
        lines = [l.split(",") for l in r.text.strip().splitlines()]
        hdr = [h.strip('"') for h in lines[0]]
        row = dict(zip(hdr, lines[1]))
        rates["real10"] = float(row["10 YR"])
        rates["real5"] = float(row["5 YR"])
        rates["real_date"] = datetime.strptime(row["Date"], "%m/%d/%Y").date().isoformat()
    mk = json.loads((OUT.parent / "markets" / "markets.json").read_text()) if (OUT.parent / "markets" / "markets.json").exists() else {}
    tc = {c["tenor"]: c["now"] for c in (mk.get("treasury") or {}).get("curve", [])}
    if tc:
        rates.update({"y2": tc.get("2 Yr"), "y10": tc.get("10 Yr"), "y3m": tc.get("3 Mo"), "y30": tc.get("30 Yr"), "curve_date": mk["treasury"]["date"]})
        if rates.get("real10") is not None and tc.get("10 Yr") is not None:
            rates["breakeven10"] = round(tc["10 Yr"] - rates["real10"], 2)
        if rates.get("real5") is not None and tc.get("5 Yr") is not None:
            rates["breakeven5"] = round(tc["5 Yr"] - rates["real5"], 2)
        if rates.get("effr") is not None and tc.get("2 Yr") is not None:
            rates["y2_minus_ff"] = round(tc["2 Yr"] - rates["effr"], 2)
    # next release dates from the calendar
    cal = json.loads((OUT / "econ_calendar.json").read_text()).get("events", []) if (OUT / "econ_calendar.json").exists() else []
    today = date.today().isoformat()
    MATCH = {"cpi": "CPI m/m", "cpi_core": "Core CPI", "ppi": "PPI m/m", "ppi_core": "Core PPI", "payrolls": "Non-Farm", "unemp": "Unemployment Rate",
             "ahe": "Average Hourly", "gdp": "GDP", "pce_core_px": "Core PCE", "umich": "UoM Consumer Sentiment"}
    for i in ind:
        m = MATCH.get(i["key"])
        nxt = [e for e in cal if e["country"] == "US" and m and m.lower() in e["title"].lower() and e["date"] >= today]
        if nxt:
            i["next"] = {"date": nxt[0]["date"], "time": nxt[0]["time"], "forecast": nxt[0]["forecast"], "previous": nxt[0]["previous"]}
    # read
    g = {i["key"]: i for i in ind}
    txt = []
    if "cpi" in g and g["cpi"].get("yoy") is not None:
        c, cc = g["cpi"], g.get("cpi_core", {})
        txt.append(f"Inflation: CPI {c['yoy']:.1f}% y/y ({c['period']}), core {cc.get('yoy', 0):.1f}%; core 3-month annualized {cc.get('ann3', 0):.1f}%"
                   + (f"; core PCE {g['pce_core_px']['yoy']:.1f}%" if g.get("pce_core_px", {}).get("yoy") is not None else "") + ".")
    if "payrolls" in g:
        p, u = g["payrolls"], g.get("unemp", {})
        txt.append(f"Jobs: payrolls {p['chg']:+.0f}k in {p['period']} (3-month average {p['avg3']:+.0f}k), unemployment {u.get('value', 0):.1f}%"
                   + (f" ({u['chg']:+.1f})" if u.get("chg") is not None else "") + (f", wages {g['ahe']['yoy']:.1f}% y/y" if g.get("ahe", {}).get("yoy") is not None else "") + ".")
    if "gdp" in g:
        txt.append(f"Growth: real GDP {g['gdp']['value']:.1f}% annualized in {g['gdp']['period']}" + (f", consumer spending {g['pce_real_q']['value']:.1f}%" if "pce_real_q" in g else "") + ".")
    if rates.get("effr") is not None:
        txt.append(f"Policy: fed funds target {rates.get('target_lo')}-{rates.get('target_hi')}% (effective {rates['effr']:.2f}%); 2-year Treasury {rates.get('y2', 0):.2f}%"
                   + (f" ({rates['y2_minus_ff']:+.2f} vs fed funds: market {'pricing cuts' if rates['y2_minus_ff'] < -0.15 else 'pricing hikes' if rates['y2_minus_ff'] > 0.15 else 'expecting little change'})" if rates.get("y2_minus_ff") is not None else "")
                   + (f"; 10-year breakeven inflation {rates['breakeven10']:.2f}%, real 10-year {rates['real10']:.2f}%" if rates.get("breakeven10") is not None else "") + ".")
    if "ppi_farm" in g and g["ppi_farm"].get("yoy") is not None:
        txt.append(f"Farm prices (PPI farm products) {g['ppi_farm']['yoy']:+.1f}% y/y; food-at-home CPI {g.get('cpi_food_home', {}).get('yoy', 0):+.1f}% y/y.")
    txt.append("For ags: high real yields and a firm dollar weigh on fund demand for commodities; sticky inflation keeps rates high (carry and storage costs up); "
               "a weak job market or falling real incomes hits meat and dairy demand first.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "us_econ.json").write_text(json.dumps({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                                   "sources": "BLS public API, BEA (via DBnomics), New York Fed, US Treasury (all free, no keys)",
                                                   "indicators": ind, "rates": rates, "read": " ".join(txt)}, default=lambda o: None))
    print("us_econ", len(ind), "indicators;", " ".join(txt)[:400])


if __name__ == "__main__":
    main()
