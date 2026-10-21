"""EIA Open Data v2 series for the energy desk (energy.html), fetched server-side with the EIA_API_KEY secret.

The series list (pipelines/energy_eia_specs.json) is the energy terminal's own SPECS table (BMR-Com/natgas):
for each series it tries the known ID on each candidate route; if a route returns nothing it falls back to the
terminal's name matching (must / prefer / not patterns) over that route's series facet. The page reads
data/energy/eia/<k>.json first and only calls EIA from the browser (with a pasted key) if a file is missing.

Daily series keep the last 8 years, weekly/monthly series their full history. Writes data/energy/eia/<k>.json
and data/energy/eia/index.json (route, ID, how it was resolved, rows, last date) for the Data tab.
"""
import json, os, re, sys, time
from datetime import date, datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "energy" / "eia"
SPECS = json.loads((Path(__file__).resolve().parent / "energy_eia_specs.json").read_text())
KEY = os.environ.get("EIA_API_KEY", "")
FACETS = {}


def get(url, params, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=90)
            if r.status_code == 200:
                return r.json()
            print("  HTTP", r.status_code, url, r.text[:160])
            if r.status_code in (400, 403, 404):
                return None
        except Exception as e:
            print("  err", e)
        time.sleep(5 * (i + 1))
    return None


def data(route, facet, sid, freq):
    # EIA wants literal brackets; requests encodes them, which the v2 API accepts in query params
    q = {"api_key": KEY, "frequency": freq, "data[0]": "value", f"facets[{facet}][]": sid,
         "sort[0][column]": "period", "sort[0][direction]": "desc", "offset": 0, "length": 5000}
    j = get(f"https://api.eia.gov/v2/{route}/data/", q)
    if not j:
        return [], ""
    rows = (j.get("response") or {}).get("data") or []
    out, desc = [], ""
    for r in rows:
        try:
            v = float(r["value"])
        except (TypeError, ValueError, KeyError):
            continue
        out.append([str(r["period"])[:10], v])
        desc = desc or r.get("series-description") or r.get("seriesDescription") or ""
    out.sort()
    return out, desc


def facets(route):
    if route not in FACETS:
        f = "seriesId" if route == "steo" else "series"
        j = get(f"https://api.eia.gov/v2/{route}/facet/{f}/", {"api_key": KEY})
        FACETS[route] = [{"id": x.get("id"), "name": x.get("name") or ""} for x in ((j or {}).get("response") or {}).get("facets", [])]
    return FACETS[route]


def score(f, sp):
    s = f["name"] + " " + f["id"]
    if not all(re.search(p, s, re.I) for p in sp["must"]):
        return None
    if any(re.search(p, s, re.I) for p in sp["not"]):
        return None
    return sum(1 for p in sp["prefer"] if re.search(p, s, re.I)) - len(f["name"]) / 1000


def main():
    if not KEY:
        print("energy_eia: no EIA_API_KEY secret; the page falls back to a key pasted in the browser")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    idx = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {"series": {}}
    for sp in SPECS:
        if only and sp["k"] not in only and sp["g"] not in only:
            continue
        facet = "seriesId" if sp["routes"][0] == "steo" else "series"
        rows, desc, used, how = [], "", None, "unresolved"
        for route in sp["routes"]:
            rows, desc = data(route, "seriesId" if route == "steo" else "series", sp["id"], sp["freq"])
            if rows:
                used, how = (route, sp["id"]), "id found"
                break
        if not rows:
            best = None
            for route in sp["routes"]:
                for f in facets(route):
                    sc = score(f, sp)
                    if sc is not None and (best is None or sc > best[0]):
                        best = (sc, route, f["id"], f["name"])
            if best:
                rows, desc = data(best[1], "seriesId" if best[1] == "steo" else "series", best[2], sp["freq"])
                used, how = (best[1], best[2]), "name matched"
        if sp["freq"] == "daily" and rows:
            cut = f"{date.today().year - 8}-01-01"
            rows = [r for r in rows if r[0] >= cut]
        if rows:
            (OUT / f"{sp['k']}.json").write_text(json.dumps({"k": sp["k"], "label": sp["label"], "route": used[0], "id": used[1], "how": how,
                                                             "desc": desc, "freq": sp["freq"], "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                                             "rows": rows}, separators=(",", ":")))
        idx["series"][sp["k"]] = {"label": sp["label"], "route": used[0] if used else sp["routes"][0], "id": used[1] if used else sp["id"], "how": how,
                                  "rows": len(rows), "last": rows[-1][0] if rows else None}
        print(f"{sp['k']:10s} {how:13s} {len(rows):5d} rows  last {rows[-1][0] if rows else '-'}  {desc[:60]}", flush=True)
        time.sleep(0.4)
    idx["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (OUT / "index.json").write_text(json.dumps(idx, indent=0))


if __name__ == "__main__":
    main()
