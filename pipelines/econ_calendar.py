"""US economic calendar.

Source: Forex Factory's public weekly calendar export (nfs.faireconomy.media), which lists each release with
time, impact (High/Medium/Low), consensus forecast and previous value. The export has no actual values, so the
calendar shows forecast vs previous; actuals come from the release itself. Fetched for this week (and next
week once it is published, usually from Thursday) and merged into a rolling file so past weeks stay visible.

Writes data/macro/econ_calendar.json: [{date (ET), time (ET), country, title, impact, forecast, previous, why}].
"""
import json, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "macro"
ET = ZoneInfo("America/New_York")
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
KEEP = {"USD": "US"}   # US only (Ma, 2026-10-21: other countries' entries were thin)
# why a release matters for commodities / ags (matched on the title, first hit wins)
WHY = [
    (r"FOMC|Federal Funds|Fed Chair|Powell|Fed .*Speaks|Beige Book", "Fed policy path: rates, dollar and fund flows into commodities"),
    (r"Non-Farm|Unemployment|Jobless|ADP|JOLTS|Employment Cost|Average Hourly", "Labor market sets the Fed path, dollar and demand"),
    (r"CPI|PCE|PPI|Inflation|Price Index", "Inflation sets rates and real yields; commodities as an inflation hedge"),
    (r"GDP|Retail Sales|Industrial Production|Durable|Factory Orders|Consumer Spending|Personal", "Growth and demand"),
    (r"PMI|ISM|Empire|Philly|Richmond|Chicago|Business|Caixin|NBS", "Manufacturing/services cycle: industrial and energy demand"),
    (r"Trade Balance|Exports|Imports|Current Account", "Trade flows; China imports drive soybeans, corn, cotton, meat"),
    (r"Crude|Natural Gas|Oil|OPEC|EIA|API Weekly", "Energy prices: biofuel margins, freight and farm input costs"),
    (r"Housing|Home|Building Permits|Pending", "Housing cycle: lumber, copper"),
    (r"Treasury|Bond Auction|Note Auction", "Treasury demand and yields"),
    (r"Loan Prime|LPR|RRR|Reserve Requirement|PBOC|Yuan|New Loans|M2|Aggregate Financing|Credit", "China credit and policy easing: commodity demand"),
    (r"Consumer Sentiment|Consumer Confidence|UoM|Michigan", "Consumer outlook and inflation expectations"),
]


def why(title):
    for p, w in WHY:
        if re.search(p, title, re.I):
            return w
    return ""


def fetch(name):
    u = f"https://nfs.faireconomy.media/ff_calendar_{name}.json"
    for i in range(3):
        try:
            r = requests.get(u, headers=H, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return []
            print("HTTP", r.status_code, u)
        except Exception as e:
            print("err", e)
        time.sleep(5 * (i + 1))
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "econ_calendar.json"
    old = json.loads(p.read_text())["events"] if p.exists() else []
    ev = {(e["date"], e["country"], e["title"]): e for e in old}
    got = 0
    for wk in ("thisweek", "nextweek"):
        rows = fetch(wk)
        for x in rows or []:
            if x.get("country") not in KEEP:
                continue
            try:
                t = datetime.fromisoformat(x["date"]).astimezone(ET)
            except Exception:
                continue
            allday = t.hour == 0 and t.minute == 0
            e = {"date": t.date().isoformat(), "time": "" if allday else t.strftime("%-I:%M %p ET"), "country": KEEP[x["country"]],
                 "title": x.get("title", ""), "impact": x.get("impact", ""), "forecast": x.get("forecast") or "", "previous": x.get("previous") or "",
                 "why": why(x.get("title", ""))}
            ev[(e["date"], e["country"], e["title"])] = e
            got += 1
    cut = (datetime.now(ET).date() - timedelta(days=45)).isoformat()
    out = sorted((e for e in ev.values() if e["date"] >= cut and e["country"] in KEEP.values()), key=lambda e: (e["date"], datetime.strptime(e["time"], "%I:%M %p ET").time() if e["time"] else datetime.min.time()))
    p.write_text(json.dumps({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                             "source": "Forex Factory weekly calendar export (forecast = consensus; no actuals in the export)", "events": out}, indent=0))
    print("econ calendar", got, "fetched,", len(out), "kept")


if __name__ == "__main__":
    main()
