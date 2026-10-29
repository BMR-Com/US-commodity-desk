"""More USDA AMS cotton reports for Cotton › AMS market review (needs AMS_API_KEY for MARS):
  monthly   MARS 3895 Monthly Cotton Price Statistics: spot averages and bales traded by market, AMS commentary, CCC loans
  classing  MARS 1652 / 1625 Daily Cotton Quality Summary by state and by classing office (latest report: daily and weekly rows)
  schedule  mnreports/cnaasrd.pdf: this year's release dates for cotton reports (USDA-wide)
Outputs in data/cotton_review/: monthly_prices.json, classing_daily.json, schedule.json. History is kept; a period already
stored is not rewritten except the current month/season.
Usage: python pipelines/ams_cotton_extra.py [monthly] [classing] [schedule]   (no args = all)
"""
import io, json, os, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "cotton_review"
B = "https://marsapi.ams.usda.gov/services/v1.2/reports/"
KEY = (os.getenv("AMS_API_KEY") or "").strip()
H = {"User-Agent": "Mozilla/5.0 (research; bmr-com)"}


def mars(slug, q=None, all_sections=True):
    p = {"allSections": "true"} if all_sections else {}
    if q:
        p["q"] = q
    r = requests.get(B + str(slug), params=p, auth=(KEY, ""), timeout=(30, 300)); r.raise_for_status()
    j = r.json()
    return {s.get("reportSection") or "Report": s.get("results") or [] for s in (j if isinstance(j, list) else [j])}


def g(r, *ks):       # case-insensitive field lookup (MARS mixes report_begin_date / report_Begin_Date)
    low = {k.lower(): v for k, v in r.items()}
    for k in ks:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def md(s):          # mm/dd/yyyy -> yyyy-mm-dd
    try:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        return s


def monthly():
    f = OUT / "monthly_prices.json"
    hist = json.loads(f.read_text()) if f.exists() else {"months": {}}
    start = (date.today().replace(day=1) - timedelta(days=500)).strftime("%m/%d/%Y")
    S = mars(3895, f"report_begin_date={start}:{date.today():%m/%d/%Y}")
    print("monthly sections", {k: len(v) for k, v in S.items()})
    if not any(S.values()):
        S = mars(3895)                                   # latest report only
    for h in S.get("Report Header", []):
        m = md(g(h, "report_begin_date"))[:7]
        txt = re.sub(r"<[^>]+>", " ", g(h, "report_narrative", "narrative") or "").strip()
        bas = re.search(r"basis for the base quality at the end of [A-Za-z]+ was ([\d,]+) points (off|on) the ICE ([A-Za-z]+ \d{4})", txt)
        bal = re.search(r"totaled ([\d,]+) running bales", txt)
        hist["months"].setdefault(m, {}).update({"narrative": re.sub(r"\s+", " ", txt), "published": g(h, "published_date"),
                                                 "basis_pts": (-1 if bas.group(2) == "off" else 1) * num(bas.group(1)) if bas else None,
                                                 "basis_vs": bas.group(3) if bas else None, "bales": num(bal.group(1)) if bal else None})
    for r in S.get("Monthly Summary", []):
        m = md(g(r, "report_begin_date"))[:7]
        mk = hist["months"].setdefault(m, {}).setdefault("markets", {})
        mk[g(r, "market")] = {"bales_month": num(g(r, "bales_Reported_Current_Month")), "bales_my": num(g(r, "bales_Reported_Market_Year")),
                           "avg_41": num(g(r, "monthly_Average_41_4_34")), "avg_31": num(g(r, "monthly_Average_31_3_36")),
                           "hi_41": num(g(r, "monthly_High_41_4_34")), "lo_41": num(g(r, "monthly_Low_41_4_34")), "ccc_loan_value": num(g(r, "cCC_Loan_Average_Value"))}
    loans = S.get("CCC Loan Activity", [])
    if loans:
        last = max(md(g(r, "report_begin_date")) for r in loans)
        hist["ccc_loans"] = {"as_of": last[:7], "rows": [{"crop": g(r, "crop_Year"), "disbursed": md(g(r, "month_Disbursed"))[:7], "matures": md(g(r, "month_Matures"))[:7],
                                                         "made": num(g(r, "total_Loans_Made")), "repaid": num(g(r, "total_Repaid")), "forfeit": num(g(r, "forfeitures")),
                                                         "outstanding": num(g(r, "outstanding"))} for r in loans if md(g(r, "report_begin_date")) == last]}
    hist["latest"] = max(hist["months"]) if hist["months"] else None
    f.write_text(json.dumps(hist, indent=1))
    print("monthly prices through", hist["latest"])


QF = {"bales": "numberofBales", "color": "predominateColor", "color_pct": "predominateColorPct", "leaf": "avgLeaf", "mike": "avgMike", "staple": "avgStaple",
      "length": "avgLength", "strength": "avgStrength", "uniformity": "avgUniformity", "loan_pts": "avgLoanPD", "bark_pct": "pctBark", "tenderable_pct": "pctTenderable", "gins": "numberofGins"}


def classing():
    f = OUT / "classing_daily.json"
    hist = json.loads(f.read_text()) if f.exists() else {"days": {}}
    since = (date.today() - timedelta(days=6)).strftime("%m/%d/%Y")
    for slug, key, fld in ((1652, "state", "classing_State"), (1625, "office", "classing_Office")):
        rows = mars(slug, f"report_begin_date={since}:{date.today():%m/%d/%Y}", all_sections=False).get("Report", [])
        rows = [r for r in rows if r.get("commodity") == "Upland"]
        if not rows:
            continue
        latest = max(md(r["report_begin_date"]) for r in rows)
        for r in rows:
            if md(r["report_begin_date"]) != latest:
                continue
            per = r.get("period"); d0, d1 = md(r.get("startDate")), md(r.get("endDate"))
            rec = {k: (num(r.get(v)) if k != "color" else r.get(v)) for k, v in QF.items()}
            if per == "Daily":
                hist["days"].setdefault(d0, {}).setdefault(key, {})[r[fld]] = rec
            else:
                hist.setdefault("periods", {}).setdefault(key, {}).setdefault(per, {})[r[fld]] = {**rec, "from": d0, "to": d1}
        hist["as_of"] = latest
    keep = sorted(hist["days"])[-60:]                      # about two months of daily rows
    hist["days"] = {d: hist["days"][d] for d in keep}
    f.write_text(json.dumps(hist, indent=1))
    print("classing as of", hist.get("as_of"), "days", len(hist["days"]))


def schedule():
    import pdfplumber
    r = requests.get("https://www.ams.usda.gov/mnreports/cnaasrd.pdf", headers=H, timeout=120); r.raise_for_status()
    pdf = pdfplumber.open(io.BytesIO(r.content))
    txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
    yr = int((re.search(r"(\d{4}) Schedule of Release Dates", txt) or [None, date.today().year])[1])
    out = []
    for line in txt.splitlines():
        m = re.match(r"\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(.+?)\s+(NASS|WAOB|ERS|AMS|FAS|FSA)\s*$", line)
        if m:
            d = datetime.strptime(f"{m.group(1)} {m.group(2)} {yr}", "%B %d %Y").strftime("%Y-%m-%d")
            out.append({"date": d, "report": re.sub(r"\s+", " ", m.group(3)).strip(), "source": m.group(4)})
    (OUT / "schedule.json").write_text(json.dumps({"year": yr, "releases": out}, indent=1))
    print("schedule", yr, len(out), "releases")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = sys.argv[1:] or ["monthly", "classing", "schedule"]
    for j in jobs:
        if j in ("monthly", "classing") and not KEY:
            print("no AMS_API_KEY for", j); continue
        try:
            globals()[j]()
        except Exception as e:
            import traceback; print(j, "failed:", repr(e)[:300]); traceback.print_exc()


if __name__ == "__main__":
    main()
