"""FSA crop acreage data (acres reported to FSA by producers; monthly August-January for each crop year).

Source: https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data
Each release is a zip with an Excel workbook of planted, failed, prevented and not-planted acres by state/county/crop.
This keeps, for every release since 2016, state totals by crop, crop type and irrigation practice:
  data/fsa/raw/<crop year>_<as-of date>.csv.gz   (one file per release; a stored release is never re-read)
  data/fsa/index.json                            (release list: crop year, as-of date, label, url, rows)
Runs in GitHub Actions (FSA blocks the Claude workspace). Usage: python pipelines/fsa_acres.py [--max N]
"""
import csv, gzip, io, json, re, sys, time, zipfile
from datetime import datetime
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "fsa"
RAW = OUT / "raw"
PAGE = "https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MON = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}
FIELDS = ["planted", "volunteer", "failed", "prevented", "not_planted", "planted_and_failed"]


def releases():
    r = requests.get(PAGE, headers=H, timeout=90)
    r.raise_for_status()
    out = []
    for href, label in re.findall(r'href="([^"]+)"[^>]*>\s*([^<]{0,160}?)\s*<', r.text):
        label = re.sub(r"&nbsp;|\s+", " ", label).strip()
        m = re.match(r"(\d{4}) acreage data as of (\w+) (\d{1,2}),? (\d{4})", label, re.I)
        if not m or m.group(2).lower() not in MON:
            continue
        asof = datetime(int(m.group(4)), MON[m.group(2).lower()], int(m.group(3))).date().isoformat()
        out.append({"year": int(m.group(1)), "asof": asof, "label": label, "url": href if href.startswith("http") else "https://www.fsa.usda.gov" + href})
    return out


def norm(s):
    return re.sub(r"[^a-z]", "", str(s or "").lower())


def parse_book(content):
    import pandas as pd
    books = []
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
        names = z.namelist()
        if "[Content_Types].xml" in names:      # the download is the workbook itself
            books.append(content)
        else:                                    # a zip holding the workbook(s)
            books += [z.read(n) for n in names if n.lower().endswith((".xlsx", ".xls"))]
    except zipfile.BadZipFile:
        books.append(content)                    # old .xls
    agg = {}
    for b in books:
        xl = pd.ExcelFile(io.BytesIO(b))
        for sh in xl.sheet_names:
            raw = xl.parse(sh, header=None, nrows=15)
            hdr = None
            for i in range(len(raw)):
                vals = [norm(v) for v in raw.iloc[i].tolist()]
                if "crop" in vals and any(v.startswith("planted") for v in vals) and "state" in " ".join(vals):
                    hdr = i; break
            if hdr is None:
                continue
            df = xl.parse(sh, header=hdr)
            cols = {norm(c): c for c in df.columns}
            def col(*names):
                for n in names:
                    for k, c in cols.items():
                        if k == n:
                            return c
                for n in names:
                    for k, c in cols.items():
                        if k.startswith(n):
                            return c
            cs, cc, ct, ci = col("statename", "state"), col("crop"), col("croptype", "type"), col("irrigationpractice", "irrigation")
            fm = {"planted": col("plantedacres"), "volunteer": col("volunteeracres"), "failed": col("failedacres"), "prevented": col("preventedacres"),
                  "not_planted": col("notplantedacres"), "planted_and_failed": col("plantedandfailedacres", "plantedandfailed")}
            if not cs or not cc or not fm["planted"]:
                continue
            keep = {"state": df[cs].astype(str).str.strip(), "crop": df[cc].astype(str).str.strip(),
                    "crop_type": df[ct].astype(str).str.strip() if ct else "", "irrigation": df[ci].astype(str).str.strip() if ci else ""}
            for f, c in fm.items():
                keep[f] = pd.to_numeric(df[c], errors="coerce").fillna(0.0) if c is not None else 0.0
            t = pd.DataFrame(keep)
            t = t[(t["state"] != "") & (t["state"] != "nan") & (t["crop"] != "") & (t["crop"] != "nan") & ~t["state"].str.lower().str.startswith("total")]
            for c in ("state", "crop", "crop_type", "irrigation"):
                t[c] = t[c].astype(str).str.title()
            g = t.groupby(["state", "crop", "crop_type", "irrigation"], as_index=False)[FIELDS].sum()
            for r in g.itertuples(index=False):
                agg[(r.state, r.crop, r.crop_type, r.irrigation)] = {f: float(getattr(r, f)) for f in FIELDS}
            if agg:
                return agg, sh
    return agg, None


def main(maxn=99):
    OUT.mkdir(parents=True, exist_ok=True); RAW.mkdir(parents=True, exist_ok=True)
    idx_f = OUT / "index.json"
    idx = json.loads(idx_f.read_text()) if idx_f.exists() else {"releases": []}
    have = {(r["year"], r["asof"]) for r in idx["releases"] if r.get("rows")}
    rel = [r for r in releases() if r["year"] >= 2016]
    print("FSA releases on the page:", len(rel), "stored:", len(have))
    n = 0
    for r in sorted(rel, key=lambda x: x["asof"], reverse=True):
        if (r["year"], r["asof"]) in have or n >= maxn:
            continue
        try:
            x = requests.get(r["url"], headers=H, timeout=300)
            x.raise_for_status()
            agg, sheet = parse_book(x.content)
            if not agg:
                raise RuntimeError(f"no acreage table found ({len(x.content)} bytes, {x.headers.get('content-type')})")
            f = RAW / f"{r['year']}_{r['asof']}.csv.gz"
            with gzip.open(f, "wt", newline="") as g:
                w = csv.writer(g); w.writerow(["state", "crop", "crop_type", "irrigation"] + FIELDS)
                for k in sorted(agg):
                    w.writerow(list(k) + [round(agg[k][f2], 2) for f2 in FIELDS])
            r.update({"rows": len(agg), "sheet": sheet, "file": f.name, "fetched": datetime.utcnow().strftime("%Y-%m-%d")})
            cot = sum(v["planted"] + v["failed"] for k, v in agg.items() if "cotton" in k[1].lower())
            print(f"{r['label']}: {len(agg)} state rows, cotton planted+failed {cot:,.0f}")
            n += 1
        except Exception as e:
            r["err"] = repr(e)[:200]
            print("::warning::", r["label"], repr(e)[:200])
        idx["releases"] = [q for q in idx["releases"] if (q["year"], q["asof"]) != (r["year"], r["asof"])] + [r]
        idx_f.write_text(json.dumps(idx, indent=1))   # saved after every release, so a timeout keeps what was read
        time.sleep(2)
    idx["releases"].sort(key=lambda q: q["asof"])
    idx["updated"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    idx_f.write_text(json.dumps(idx, indent=1))


if __name__ == "__main__":
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 99
    main(mx)
