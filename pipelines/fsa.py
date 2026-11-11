#!/usr/bin/env python3
"""FSA Crop Acreage Data (acres reported to FSA; releases monthly from August through January).

Port of BMR-Com/cotton-crop-progress scripts/fetch_fsa.py: same listing page, same release picking (every release from
2014 on, crop year from the link label, release date from the "as of" label, else the workbook, else the file name),
same cotton aggregation (county_data rows whose Crop contains COTTON, summed by state, cotton type and irrigation
practice: planted, failed, prevented, volunteer, not-planted acres) and the same output file and columns.

Changes from the source, all in how files are fetched and read, not in the numbers:
  - every sheet whose name contains "county_data" is read and the rows added up (newer workbooks split the county
    table across sheets at Excel's row limit; the source read the first one only). data/fsa/files.csv lists the
    sheets read per file so the two can be compared;
  - the same pass also keeps Corn, Soybeans and Wheat (sweet corn, popcorn and buckwheat excluded) in data/fsa/fsa_grains_state.csv, by state, crop type, intended use and irrigation practice;
  - pauses between requests and retries with back-off (FSA answers 403 after many requests in a row), the stored
    release list is used when the listing page refuses, and a time budget (FSA_BUDGET_MIN, default 40) so a backfill
    runs in stages: each file is appended and recorded in data/fsa/processed.txt as soon as it is read (~30 s a file).
  - releases the models need first are read first: the current crop year, then past releases from the same month
    as the newest one (backtests), then the rest.

Outputs (data/fsa/):
  fsa_cotton_state.csv  crop_year, release, state, type, irr, planted, failed, prevented, volunteer, not_planted, file
  fsa_grains_state.csv  crop_year, release, state, crop, crop_raw, crop_type, intended_use, irr, planted, failed,
                        prevented, volunteer, not_planted, file
  crop_names.csv        every Crop / Crop Type text seen that mentions corn, soy, wheat or cotton, and whether kept
  files.csv             file, release, sheets read (name:rows), cotton rows, grain rows
  release_dates.csv     file -> release date (seeded from cotton-crop-progress's stored rows, so re-read files keep the
                        source's dates; FSA's page labels changed since and contain typos)
  links.txt, processed.txt, failures.json (failed attempts per file), status.json (releases pending)
"""
import io, json, os, random, re, sys, time, zipfile
from pathlib import Path

import pandas as pd
import requests

PAGE = "https://www.fsa.usda.gov/tools/informational/freedom-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data"
ROOT_URL = "https://www.fsa.usda.gov"
OUT = Path(__file__).resolve().parent.parent / "data" / "fsa"
H = {"User-Agent": "Mozilla/5.0 (BMR-Com research)"}        # the source's header; a browser-like UA drew 403s (desk attempt 0d378501)
FIRST_YEAR = 2014
COLS = {"planted acres": "planted", "failed acres": "failed", "prevented acres": "prevented",
        "volunteer acres": "volunteer", "not planted acres": "not_planted"}
GRAINS = {"CORN", "SOYBEANS", "WHEAT"}             # exchange-traded crops only (sorghum dropped, Ma 2026-11-11)
EXCLUDE = re.compile(r"SWEET|POP|FORAGE|BUCK|SUDAN", re.I)
BUDGET = float(os.environ.get("FSA_BUDGET_MIN", "40")) * 60
GAP = (4.0, 9.0)                                   # seconds between requests (random in this range)
T0 = time.time()


def get(url, timeout=300):
    """GET with a pause before every request and back-off on 403/429/5xx (FSA refuses bursts)."""
    err = None
    for i, wait in enumerate((0, 45, 120, 300)):
        if wait:
            print(f"  retry {i} in {wait}s: {err}", flush=True)
            time.sleep(wait)
        time.sleep(random.uniform(*GAP))
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code in (403, 429) or r.status_code >= 500:
                err = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            err = repr(e)
    raise RuntimeError(f"{url}: {err}")


def release_date(xb, fname):
    try:
        d = pd.read_excel(io.BytesIO(xb), sheet_name=0, header=None, nrows=4, engine="calamine")
        for v in d.values.ravel():
            t = pd.to_datetime(v, errors="coerce")
            if pd.notna(t) and 2000 < t.year < 2100:
                return t.date().isoformat()
    except Exception:
        pass
    m = re.search(r"(\d{2})(\d{2})(\d{2})(?!\d)", fname)          # e.g. ..._110921 -> 2021-11-09
    if m:
        return f"20{m.group(3)}-{m.group(1)}-{m.group(2)}"
    return None


def _excel(xb):
    for eng in ("calamine", None):
        try:
            return pd.ExcelFile(io.BytesIO(xb), engine=eng) if eng else pd.ExcelFile(io.BytesIO(xb))
        except Exception as e:
            err = e
    raise err


def county_table(xb):
    """All county_data sheets of a workbook, stacked. Returns (frame, 'sheet:rows;...') or (None, reason)."""
    xl = _excel(xb)
    names = [s for s in xl.sheet_names if "county_data" in s.lower()]
    if not names:
        return None, "no county_data sheet: " + ",".join(xl.sheet_names)
    parts, used, cols = [], [], None
    for name in names:
        d = xl.parse(name)
        if "crop" not in [str(c).strip().lower() for c in d.columns]:      # 2024+ files put a title row above the header
            for i in range(min(6, len(d))):
                row = [str(x).strip() for x in d.iloc[i].tolist()]
                if "Crop" in row and any("Planted" in x for x in row):
                    d.columns = row
                    d = d.iloc[i + 1:]
                    break
        if "crop" not in [str(c).strip().lower() for c in d.columns]:
            if cols is not None and d.shape[1] == len(cols):                 # continuation sheet without a header row
                first = pd.DataFrame([list(d.columns)], columns=cols)
                d.columns = cols
                d = pd.concat([first, d], ignore_index=True)
            else:
                used.append(f"{name}:skipped")
                continue
        d.columns = [str(c).strip() for c in d.columns]
        cols = cols or list(d.columns)
        parts.append(d)
        used.append(f"{name}:{len(d)}")
    others = [s for s in xl.sheet_names if s not in names]
    if others:
        used.append("other sheets: " + ",".join(others))
    if not parts:
        return None, ";".join(used)
    return pd.concat(parts, ignore_index=True), ";".join(used)


def _col(lc, *starts):
    norm = {re.sub(r"[^a-z]", "", k): v for k, v in lc.items()}
    for s in starts:
        for k, v in norm.items():
            if k.startswith(s):
                return v
    return None


def cotton_by_state(d):
    """Same as the source's cotton_by_state, on the stacked county table."""
    lc = {c.lower(): c for c in d.columns}
    crop = lc.get("crop")
    if not crop:
        return None
    d = d[d[crop].astype(str).str.upper().str.contains("COTTON", na=False)].copy()
    d["type"] = d[crop].astype(str).str.upper().str.replace(r"COTTON\s+", "", regex=True).str.strip()
    d["irr"] = d[lc["irrigation practice"]].astype(str).str.upper().str.strip() if "irrigation practice" in lc else "ALL"
    keep = {lc[k]: v for k, v in COLS.items() if k in lc}
    for c in keep:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    return d.groupby([lc["state"], "type", "irr"])[list(keep)].sum().reset_index().rename(columns={lc["state"]: "state", **keep})


def grains_by_state(d):
    """Corn, Soybeans, Wheat rows by state, crop type, intended use and irrigation; plus the crop-name audit."""
    lc = {c.lower(): c for c in d.columns}
    crop = lc.get("crop")
    if not crop:
        return None, None
    ct, iu = _col(lc, "croptype", "type"), _col(lc, "intendeduse")
    irr = lc.get("irrigation practice")
    cr = d[crop].astype(str).str.upper().str.strip()
    hit = cr.str.contains(r"CORN|SOY|WHEAT|COTTON", na=False)
    d = d[hit].copy()
    d["crop_raw"] = cr[hit]
    d["crop_type"] = d[ct].astype(str).str.upper().str.strip() if ct else ""
    d["intended_use"] = d[iu].astype(str).str.upper().str.strip() if iu else ""
    d["irr"] = d[irr].astype(str).str.upper().str.strip() if irr else "ALL"
    base = d.crop_raw.str.split(r"[,\-]", n=1, regex=True).str[0].str.strip()
    d["crop"] = base.where(base.isin(GRAINS))
    bad = d.crop_raw.str.contains(EXCLUDE)            # separate FSA crops (Sweet Corn, Popcorn, Sorghum Forage, Buckwheat)
    d.loc[bad, "crop"] = None
    keep = {lc[k]: v for k, v in COLS.items() if k in lc}
    for c in keep:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    audit = (d.groupby(["crop_raw", "crop_type"], dropna=False)[lc["planted acres"]].sum().reset_index()
             .rename(columns={lc["planted acres"]: "planted"}))
    audit["kept_as"] = [(b if b in GRAINS and not EXCLUDE.search(r) else "") for b, r, t in
                        zip(audit.crop_raw.str.split(r"[,\-]", n=1, regex=True).str[0].str.strip(), audit.crop_raw, audit.crop_type)]
    g = (d.dropna(subset=["crop"]).groupby([lc["state"], "crop", "crop_raw", "crop_type", "intended_use", "irr"])[list(keep)]
         .sum().reset_index().rename(columns={lc["state"]: "state", **keep}))
    return g, audit


def plausible(rd, year):
    """FSA's labels have typos (the 2015 August release reads 'as of August 1, 2014'): a release falls Jul–Mar of its season."""
    return pd.notna(rd) and pd.Timestamp(year, 7, 1) <= rd <= pd.Timestamp(year + 1, 3, 31)


DATES = OUT / "release_dates.csv"      # file -> release date; seeded from cotton-crop-progress so re-read files keep its dates
KNOWN = dict(pd.read_csv(DATES).values) if DATES.exists() else {}


def replace_rows(path, fname):
    """Drop a file's earlier rows before its re-read rows are appended (no duplicate releases)."""
    if path.exists():
        d = pd.read_csv(path, keep_default_na=False, na_values=[""])
        if (d.file.astype(str) == fname).any():
            d[d.file.astype(str) != fname].to_csv(path, index=False)


def append(path, g):
    g.to_csv(path, mode="a", header=not path.exists(), index=False)


def listing():
    """Release links from the listing page; the stored list when the page refuses."""
    try:
        html = get(PAGE, timeout=90).text
        links = re.findall(r'<a[^>]+href="([^"]+?\.(?:zip|xlsx)|/documents/[A-Za-z0-9_-]+)"[^>]*>(.*?)</a>', html, flags=re.S)
        links = [(h, t) for h, t in links if "acreage data" in re.sub("<[^>]+>", "", t).lower() or h.endswith((".zip", ".xlsx"))]
        if links:
            (OUT / "links.txt").write_text("\n".join(f"{h}\t{re.sub('<[^>]+>', '', t).strip()}" for h, t in links))
            return links
    except Exception as e:
        print("listing page failed:", e, flush=True)
    p = OUT / "links.txt"
    if p.exists():
        print("using the stored release list", flush=True)
        return [tuple(l.split("\t", 1)) for l in p.read_text().splitlines() if "\t" in l]
    return []


def label_date(label):
    lab = re.search(r"as of\s+([A-Za-z]+\.?\s+\d{1,2},?\s+20\d\d)", label)
    rd = pd.to_datetime(lab.group(1).replace(".", ""), errors="coerce") if lab else pd.NaT
    return rd


def order(links):
    """Current crop year first, then past releases from the newest release's month, then the rest (page order)."""
    rows = []
    for i, (href, text) in enumerate(links):
        label = re.sub("<[^>]+>", "", text)
        fname = href.rsplit("/", 1)[-1]
        m = re.match(r"\s*(20\d\d)", label) or re.match(r"(20\d\d)", fname)
        if not m or int(m.group(1)) < FIRST_YEAR:
            continue
        rows.append((i, href, label, fname, int(m.group(1)), label_date(label)))
    if not rows:
        return []
    cy = max(r[4] for r in rows)
    newest = max((r[5] for r in rows if r[4] == cy and pd.notna(r[5])), default=pd.NaT)
    mon = newest.month if pd.notna(newest) else None
    key = lambda r: (0 if r[4] == cy else 1 if (mon and pd.notna(r[5]) and r[5].month == mon) else 2, r[0])
    return sorted(rows, key=key)


def fetch_file(url, fname):
    resp = get(url)
    b = resp.content
    if "html" in (resp.headers.get("content-type") or ""):     # /documents/<id> is a landing page → follow its file link
        m2 = (re.search(r'href="([^"]+?\.(?:zip|xlsx))"', resp.text)
              or re.search(r'href="([^"]*/sites/default/files/[^"]+)"', resp.text))
        if not m2:
            raise RuntimeError(f"no file link on {url}")
        fu = m2.group(1)
        b = get(fu if fu.startswith("http") else ROOT_URL + fu).content
    try:
        z = zipfile.ZipFile(io.BytesIO(b))
        names = z.namelist()
        if any(n.startswith("xl/") for n in names):        # the download is itself an .xlsx
            return [(fname + ".xlsx", b)]
        return [(n, z.read(n)) for n in names if n.lower().endswith((".xlsx", ".xls"))]
    except zipfile.BadZipFile:
        return [(fname, b)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    done_path, cot_path, gr_path = OUT / "processed.txt", OUT / "fsa_cotton_state.csv", OUT / "fsa_grains_state.csv"
    aud_path, files_path = OUT / "crop_names.csv", OUT / "files.csv"
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    fp = OUT / "failures.json"
    fails = json.loads(fp.read_text()) if fp.exists() else {}
    todo = [r for r in order(listing()) if r[3] not in done]
    print(f"{len(todo)} releases to read", flush=True)
    for _, href, label, fname, year, rd in todo:
        if time.time() - T0 > BUDGET:
            print("time budget reached; the rest on the next run", flush=True)
            break
        url = href if href.startswith("http") else ROOT_URL + href
        try:
            files = fetch_file(url, fname)
            for p in (cot_path, gr_path):
                replace_rows(p, fname)
            n_c = n_g = 0
            sheets = []
            for n, xb in files:
                t0 = time.time()
                d, used = county_table(xb)
                sheets.append(f"{n}[{used}]")
                if d is None:
                    continue
                rel = KNOWN.get(fname) or (rd.date().isoformat() if plausible(rd, year) else None) \
                    or release_date(xb, n) or release_date(xb, fname)
                KNOWN[fname] = rel
                g = cotton_by_state(d)
                if g is not None and len(g):
                    g.insert(0, "release", rel)
                    g.insert(0, "crop_year", year)
                    g["file"] = fname
                    append(cot_path, g)
                    n_c += len(g)
                gg, audit = grains_by_state(d)
                if gg is not None and len(gg):
                    gg.insert(0, "release", rel)
                    gg.insert(0, "crop_year", year)
                    gg["file"] = fname
                    append(gr_path, gg)
                    n_g += len(gg)
                if audit is not None and len(audit):
                    audit.insert(0, "release", rel)
                    audit.insert(0, "crop_year", year)
                    append(aud_path, audit)
                print(f"  {n}: {used} read in {time.time() - t0:.0f}s", flush=True)
            append(files_path, pd.DataFrame([{"file": fname, "label": label.strip(), "sheets": " ".join(sheets),
                                              "cotton_rows": n_c, "grain_rows": n_g}]))
            print(f"{label.strip()[:60]} ({fname}): cotton {n_c} rows, grains {n_g} rows", flush=True)
            done.add(fname)
            done_path.write_text("\n".join(sorted(done)))
            fails.pop(fname, None)
        except Exception as e:
            print("skip", fname, e, flush=True)
            fails[fname] = fails.get(fname, 0) + 1
    (OUT / "failures.json").write_text(json.dumps(fails, indent=1, sort_keys=True))
    pd.DataFrame(sorted(KNOWN.items()), columns=["file", "release"]).to_csv(DATES, index=False)
    left = sum(1 for r in todo if r[3] not in done and fails.get(r[3], 0) < 3)
    from datetime import datetime, timezone
    (OUT / "status.json").write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                                 "pending": left, "read": len(done)}, indent=1))
    print(f"{left} releases still to read", flush=True)
    for p, k in ((cot_path, ["crop_year", "release", "state", "type", "irr"]),
                 (gr_path, ["crop_year", "release", "state", "crop", "crop_raw", "crop_type", "intended_use", "irr"])):
        if p.exists():
            d = pd.read_csv(p, keep_default_na=False, na_values=[""])
            d.drop_duplicates(k, keep="last").sort_values(k).to_csv(p, index=False)
    if aud_path.exists():
        a = pd.read_csv(aud_path, keep_default_na=False)
        a.drop_duplicates(["crop_year", "release", "crop_raw", "crop_type"], keep="last").to_csv(aud_path, index=False)
    if files_path.exists():
        pd.read_csv(files_path).drop_duplicates("file", keep="last").to_csv(files_path, index=False)


if __name__ == "__main__":
    sys.exit(main())
