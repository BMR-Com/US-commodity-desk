"""USDA WASDE reports into the desk's own store (data/wasde/raw/<WasdeNumber>.csv.gz), so the desk does not wait for
BMR-Com/wasde-analytics.

  python pipelines/wasde.py seed            one time: split wasde-analytics' master file (public release asset) into
                                            one gzipped CSV per report; existing reports are kept
  python pipelines/wasde.py fetch           check USDA for this month's and last month's report CSV; store it if new
  python pipelines/wasde.py fetch --wait 40 on report day: poll every 2 minutes for up to 40 minutes

USDA serves the report CSV at usda.gov/sites/default/files/documents/oce-wasde-report-data-YYYY-MM.csv. Plain requests
from GitHub runners are refused, so the download presents itself as a Chrome browser (curl_cffi), as wasde-analytics does.
Exit code 0 always; prints NEW=<number> when a new report was stored (the workflow reads it).
"""
import io, sys, time
from datetime import date
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "wasde" / "raw"
MASTER = "https://github.com/BMR-Com/wasde-analytics/releases/download/data-store/master_wasde.csv"
USDA = "https://www.usda.gov/sites/default/files/documents/oce-wasde-report-data-{}.csv"


def have():
    return {int(p.name.split(".")[0]) for p in RAW.glob("*.csv.gz") if p.name.split(".")[0].isdigit()}


def save(df, tag=None):
    RAW.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    if "Report Title" in df.columns:          # USDA's file includes a reliability table: not report data
        df = df[~df["Report Title"].astype(str).str.contains("Reliability", case=False, na=False)]
    if "ReportTitle" in df.columns:
        df = df[~df["ReportTitle"].astype(str).str.contains("Reliability", case=False, na=False)]
    df.columns = [c.replace(" ", "") for c in df.columns]          # "Report Title" -> "ReportTitle" (master's naming)
    if tag and "SourceReport" not in df.columns:
        df["SourceReport"] = tag
    df["WasdeNumber"] = pd.to_numeric(df["WasdeNumber"], errors="coerce")
    new = []
    for n, g in df.dropna(subset=["WasdeNumber"]).groupby("WasdeNumber"):
        p = RAW / f"{int(n)}.csv.gz"
        if p.exists():
            continue
        g.to_csv(p, index=False, compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
        new.append(int(n))
    return new


def seed():
    import requests
    r = requests.get(MASTER, timeout=300)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), low_memory=False, dtype={"MarketYear": str})
    new = save(df)
    print(f"seed: {len(df):,} rows; stored {len(new)} reports (#{min(new) if new else '-'}–#{max(new) if new else '-'})")


def get_usda(ym):
    from curl_cffi import requests as cf
    r = cf.get(USDA.format(ym), impersonate="chrome120", timeout=60)
    if r.status_code == 200 and len(r.content) > 5000 and b"WasdeNumber" in r.content[:2000]:
        return pd.read_csv(io.StringIO(r.content.decode("utf-8-sig")), low_memory=False, dtype={"MarketYear": str})
    print(f"  {ym}: HTTP {r.status_code}, {len(r.content)} bytes")
    return None


def fetch(wait_min=0):
    t_end = time.time() + 60 * wait_min
    today = date.today()
    months = [today.strftime("%Y-%m"), (today.replace(day=1) - pd.Timedelta(days=1)).strftime("%Y-%m")]
    last = max(have() or {0})
    while True:
        for ym in months:
            try:
                df = get_usda(ym)
            except Exception as e:
                print(f"  {ym}: error {str(e)[:120]}"); df = None
            if df is None:
                continue
            n = int(pd.to_numeric(df["WasdeNumber"], errors="coerce").max())
            if n > last:
                new = save(df, tag=ym)
                print(f"fetch: stored WASDE #{n} ({ym}), {len(df):,} rows")
                print(f"NEW={n}")
                return n
            print(f"  {ym}: latest is #{n}, already stored")
            break                                   # this month's file exists and is not newer: nothing to wait for
        else:
            if time.time() < t_end:
                time.sleep(120); continue
        if time.time() >= t_end or wait_min == 0:
            print(f"fetch: no new report (latest stored #{last})")
            return None
        time.sleep(120)


if __name__ == "__main__":
    a = sys.argv[1:] or ["fetch"]
    if a[0] == "seed":
        seed()
    else:
        w = int(a[a.index("--wait") + 1]) if "--wait" in a else 0
        fetch(w)
