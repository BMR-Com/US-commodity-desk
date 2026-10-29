"""USDA AMS Cotton Forward Contracting Report (MARS 1613, monthly in season): share of planted Upland acres growers have
forward-contracted, by state and region, this season and the 9 before. Stored per report month in
data/cotton_review/forward_contracting.json (history kept). Needs AMS_API_KEY."""
import json, os
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cotton_review" / "forward_contracting.json"
KEY = (os.getenv("AMS_API_KEY") or "").strip()
ORDER = ["United States", "Southeastern", "Alabama", "Florida", "Georgia", "North Carolina", "South Carolina", "Virginia", "South Central", "Arkansas", "Louisiana",
         "Mississippi", "Missouri", "Tennessee", "Southwestern", "Kansas", "Oklahoma /3", "Texas", "Western", "Arizona", "California", "New Mexico"]


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main():
    if not KEY:
        print("no AMS_API_KEY"); return
    r = requests.get("https://marsapi.ams.usda.gov/services/v1.2/reports/1613", auth=(KEY, ""), timeout=180); r.raise_for_status()
    j = r.json(); rows = j[0]["results"] if isinstance(j, list) else j.get("results", [])
    if not rows:
        print("no rows"); return
    end = rows[0]["report_end_date"]; mm, dd, yy = end.split("/"); key = f"{yy}-{mm}-{dd}"
    seen, out = set(), []
    for x in rows:
        loc = x["market_location_name"]
        if loc in seen:
            continue
        seen.add(loc)
        prior = [num(x.get(f"pct_acres_planted_prior_{i}yr")) for i in range(1, 10)]
        out.append({"loc": loc.replace(" /3", ""), "region": loc in ("United States", "Southeastern", "South Central", "Southwestern", "Western"),
                    "pct": num(x.get("pct_acres_planted")), "prior": prior, "acres": x.get("nass_acres_planted_total")})
    out.sort(key=lambda r: ORDER.index(r["loc"] if r["loc"] != "Oklahoma" else "Oklahoma /3") if (r["loc"] if r["loc"] != "Oklahoma" else "Oklahoma /3") in ORDER else 99)
    hist = json.loads(OUT.read_text()) if OUT.exists() else {"reports": {}}
    hist["reports"][key] = {"as_of": key, "crop_year": int(yy), "published": rows[0].get("published_date"), "rows": out}
    hist["latest"] = max(hist["reports"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(hist, indent=1))
    us = next(r for r in out if r["loc"] == "United States")
    print("forward contracting as of", key, "US", us["pct"], "prior", us["prior"][:3])


if __name__ == "__main__":
    main()
