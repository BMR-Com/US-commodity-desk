"""US cotton in the CCC marketing loan (FSA State Office Reporting System, public reports, no key).

Monthly (history kept, compared year on year):
  PSL-43R  Warehouse Cotton Maturity: loans made / repaid / forfeited / outstanding by crop year, month disbursed and month
           the loan matures (9 months later), Form A (producer) and Form G (cooperative), national. CSV + PDF per month.
  PSL-61R  Price Support Loan Activity, monthly: by commodity, crop year and STATE: put under loan (farm/warehouse),
           repaid, delivered to CCC, outstanding. Cotton rows kept.
Weekly:
  PSL-61R  weekly (as of each Monday): same layout as the monthly, state level.
  Current state snapshots taken once a week (the site only shows "now"): loans made/outstanding by state with Form G,
  outstanding by state and maturity month. Upland (6100) and ELS (6000).
Only snapshots not stored yet are fetched; raw files are never overwritten. Writes data/cotton_loan/raw/...
"""
import csv, io, re, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "cotton_loan" / "raw"
BASE = "https://fcp-apps-fsa.fpac.usda.gov/sorspub/reports"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
S = requests.Session()
S.headers.update(H)


def snapshots(report):
    """{snapshot id: date} from the report page's 'As Of' list."""
    h = S.get(f"{BASE}/web/public/{report}", timeout=60).text
    sel = re.search(r'name="snapshot".*?</select>', h, re.S)
    out = {}
    for v, t in re.findall(r'<option[^>]*value="(\d+)"[^>]*>\s*([A-Za-z]{3} \d{1,2}, \d{4})', sel.group(0) if sel else ""):
        out[v] = datetime.strptime(t, "%b %d, %Y").date().isoformat()
    return out


def post(report, fmt, **params):
    data = {"reportType": fmt, "reportCatalogName": "public", "reportName": report, **params}
    r = S.post(f"{BASE}/{fmt}/public/{report}", data=data, timeout=120)
    r.raise_for_status()
    return r.content


def write_once(path, content):
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(path)
    return True


def cotton_rows(text):
    """Keep the header lines and the cotton rows of a PSL-61R CSV."""
    lines = text.splitlines()
    head = [l for l in lines[:8] if l.strip() and not l.startswith("BARLEY")]
    return "\n".join(head + [l for l in lines if l.startswith("COTTON")]) + "\n"


def monthly():
    n = 0
    for sid, d in snapshots("official-psl43r-cotton").items():
        p = RAW / "psl43r" / f"{d}.csv"
        if not p.exists():
            write_once(p, post("official-psl43r-cotton", "csv", snapshot=sid))
            try:
                write_once(RAW / "psl43r" / f"{d}.pdf", post("official-psl43r-cotton", "pdf", snapshot=sid))
            except Exception as e:
                print("pdf", d, e)
            n += 1
            time.sleep(1)
    for sid, d in snapshots("official-psl61r-monthly").items():
        p = RAW / "psl61r_monthly" / f"{d}.csv"
        if not p.exists():
            write_once(p, cotton_rows(post("official-psl61r-monthly", "csv", snapshot=sid).decode("latin-1")).encode())
            n += 1
            time.sleep(1)
    print("monthly snapshots added:", n)


def weekly():
    n = 0
    for sid, d in snapshots("official-psl61r-weekly").items():
        p = RAW / "psl61r_weekly" / f"{d}.csv"
        if not p.exists():
            write_once(p, cotton_rows(post("official-psl61r-weekly", "csv", snapshot=sid).decode("latin-1")).encode())
            n += 1
            time.sleep(1)
    # current state views, once per ISO week (the site has no history for these)
    today = date.today()
    wk = f"{today.isocalendar()[0]}-W{today.isocalendar()[1]:02d}"
    d = RAW / "state" / wk
    if not d.exists():
        common = {"state": "00", "activityTypes": "formG", "_activityTypes": "on"}
        files = {}
        for code, name in (("6100", "upland"), ("6000", "els")):
            for cy in (str(today.year), str(today.year - 1)):
                files[f"{name}_loans_{cy}.csv"] = post("loan-all-state", "csv", cropYear=cy, commodity=code, **common)
            files[f"{name}_maturity.csv"] = post("loan-maturity-state", "csv", cropYear="0000", commodity=code, **common)
            files[f"{name}_outstanding.csv"] = post("loan-outstanding-state", "csv", cropYear="0000", commodity=code, **common)
            time.sleep(1)
        for f, c in files.items():
            write_once(d / f, c)
        (d / "taken.txt").write_text(datetime.now(timezone.utc).isoformat() + "\n")
        n += 1
    print("weekly snapshots added:", n)


if __name__ == "__main__":
    for step in sys.argv[1:] or ["monthly", "weekly"]:
        try:
            {"monthly": monthly, "weekly": weekly}[step]()
        except Exception as e:
            print(step, "failed:", e)
