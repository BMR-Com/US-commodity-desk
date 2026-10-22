"""History of the CME daily cash (spot) dairy closes before MARS coverage (MARS report 1603 starts in 2021).

Source: USDA Dairy Market News 'CME Group - Weekly Recap/Trading' (MD_DA998) text releases on ESMIS, Nov 2018 on.
Parses the daily cash closes for 40-lb blocks, barrels, butter, nonfat dry milk and dry whey into
data/ams/cme_daily_dairy_hist/history.csv (date, product, close). Completed history only needs fetching once.
"""
import re, time
from pathlib import Path
import pandas as pd
import requests

OUT = Path(__file__).resolve().parent.parent / "data" / "ams" / "cme_daily_dairy_hist"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research; github actions)"}
B = "https://esmis.nal.usda.gov"
ROWS = {"BARRELS": "barrel", "40 POUND BLOCKS": "block", "GRADE AA": "butter", "GRADE A": "ndm", "EXTRA GRADE": "whey"}
MON = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def get(u):
    for i in range(3):
        try:
            r = requests.get(u, headers=H, timeout=90)
            if r.status_code == 200:
                return r
        except Exception as e:
            print("err", e)
        time.sleep(3 * (i + 1))
    return None


def parse(txt):
    out = []
    m = re.search(r"WEEK OF[^\n]*?(\d{4})", txt)
    if not m:
        return out
    year = int(m.group(1))
    days = None
    for line in txt.splitlines():
        found = re.findall(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{1,2})\b", line)
        if len(found) >= 3:
            days = found
            break
    if not days:
        return out
    last_m = MON[days[-1][0]]
    dates = [pd.Timestamp(year - (1 if MON[mo] > last_m else 0), MON[mo], int(d)) for mo, d in days]
    for line in txt.splitlines():
        s = line.strip()
        for label, prod in ROWS.items():
            if s.startswith(label + " ") and not (label == "GRADE A" and s.startswith("GRADE AA")):
                body = s[len(label):].split("::")[0]
                toks = re.findall(r"\$\d+\.\d+|No\b", body)
                for dt, tk in zip(dates, toks):
                    if tk.startswith("$"):
                        out.append((dt.date().isoformat(), prod, float(tk[1:])))
                break
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / "history.csv"
    have = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["date", "product", "close"])
    rows = []
    for page in range(0, 60):
        r = get(f"{B}/publication/cme-group-weekly-recaptrading?page={page}")
        if r is None:
            break
        files = sorted(set(re.findall(r'href="([^"]+\.txt)"', r.text, re.I)))
        if not files and page > 2:
            break
        for f in files:
            rr = get(B + f if f.startswith("/") else f)
            if rr is None:
                continue
            rows += parse(rr.text)
            time.sleep(0.2)
        print("page", page, len(files), "files", len(rows), "rows")
    new = pd.DataFrame(rows, columns=["date", "product", "close"])
    out = pd.concat([have, new]).drop_duplicates(["date", "product"], keep="last").sort_values(["date", "product"])
    out.to_csv(p, index=False)
    print("stored", len(out), out.date.min(), out.date.max())


if __name__ == "__main__":
    main()
