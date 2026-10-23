"""Merge browser-collected China data into data/china/raw/.

  python china/ingest.py known              -> prints {"cca": {...}, "gacc": {...}} to pass to the collectors
  python china/ingest.py cca  <payload>     -> china/collect_cca.js output (gzip+base64 JSON)
  python china/ingest.py gacc <payload>     -> china/collect_gacc.js output
A payload file may hold the base64 text alone or embedded in other text (the part starting "H4sI" is used).
"""
import base64, csv, gzip, io, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "china" / "raw"
TAB = RAW / "cca_tables.json"
ART = RAW / "cca_production_articles.json"
GACC = RAW / "gacc_major_commodities.csv"
GCOLS = ["flow", "year", "mon", "commodity", "unit", "m_qty", "m_val", "ytd_qty", "ytd_val", "pct_qty"]


def payload(path):
    t = Path(path).read_text()
    if t.lstrip().startswith("["):           # a saved tool result: [{"type":"text","text":...}]
        try:
            t = "".join(x.get("text", "") for x in json.loads(t))
        except Exception:
            pass
    m = re.search(r"H4sI[A-Za-z0-9+/=]+", t)
    if not m:
        sys.exit("no gzip+base64 payload found")
    return json.loads(gzip.decompress(base64.b64decode(m.group(0))))


def load(p, default):
    return json.loads(p.read_text()) if p.exists() else default


def known():
    T, A = load(TAB, {}), load(ART, {"list": [], "art": {}})
    cc = sorted(r[0] for r in T.get("ccindex", []) if r and re.match(r"\d{4}-\d\d-\d\d", r[0]))
    cl = sorted(r[0] for r in T.get("cotlook", []) if r and re.match(r"\d{4}-\d\d-\d\d", r[0]))
    have = []
    if GACC.exists():
        with GACC.open() as f:
            have = sorted({f"{r['flow']}|{r['year']}|{r['mon']}" for r in csv.DictReader(f)})
    print(json.dumps({"cca": {"cc_last": cc[-1] if cc else None, "cl_last": cl[-1] if cl else None, "urls": list(A["art"].keys())},
                      "gacc": {"have": have}}, ensure_ascii=False))


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def parse_quotes(t):
    q = {}
    pats = {"cc3128": r"CCIndex3128B\s*([\d.]+)元/吨\s*(\d{4}-\d\d-\d\d)", "fcindex_m": r"FCIndexM\s*([\d.]+)美分/磅\s*(\d{4}-\d\d-\d\d)",
            "zce_near": r"郑州棉花期货近期合约\s*([\d.]+)元/吨\s*(\d{4}-\d\d-\d\d)", "ice": r"ICE纽约棉花期货\s*([\d.]+)美分/磅\s*(\d{4}-\d\d-\d\d)",
            "cotlook_a": r"CotLookA指数\s*([\d.]+)美分/磅\s*(\d{4}-\d\d-\d\d)", "a_1pct_yuan": r"CotlookA指数折1%关税\s*([\d.]+)元/吨\s*(\d{4}-\d\d-\d\d)"}
    for k, p in pats.items():
        m = re.search(p, t or "")
        if m:
            q[k] = [float(m[1]), m[2]]
    return q


def parse_balance(t):
    rows = []
    for m in re.finditer(r"(20\d\d)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", re.sub(r"\s+", " ", t or "")):
        v = [float(x) for x in m.groups()[1:]]
        rows.append({"season": int(m[1]), "beg": v[0], "prod": v[1], "imp": v[2], "use": v[3], "exp": v[4], "end": v[5]})
    return rows


def merge_dated(old, new):
    d = {r[0]: r for r in old if r}
    for r in new:
        if r and re.match(r"\d{4}-\d\d-\d\d", r[0]):
            d[r[0]] = r
    return [d[k] for k in sorted(d, reverse=True)]


def ingest_cca(p):
    D = payload(p)
    T = load(TAB, {})
    if D.get("ccindex"):
        T["ccindex"] = merge_dated(T.get("ccindex", []), D["ccindex"])
    if D.get("cotlook"):
        T["cotlook"] = merge_dated(T.get("cotlook", []), D["cotlook"])
    q = parse_quotes(D.get("quotes_text"))
    if q:
        T["quotes"] = q
    b = parse_balance(D.get("balance_text"))
    if b:
        T["balance"] = b
    if D.get("nbs"):
        T["nbs"] = [{"year": int(r[0]), "area_kmu": num(r[1]) * 10, "prod_kt": num(r[2]) * 10} for r in D["nbs"] if len(r) >= 3 and r[0].isdigit() and num(r[1]) and num(r[2])]
    if D.get("cca_prod"):
        T["cca_final"] = [{"year": int(r[0]), "region": r[3], "area_kmu": num(r[1]) * 10, "prod_kt": num(r[2]) * 10} for r in D["cca_prod"] if len(r) >= 4 and r[0].isdigit() and num(r[2]) is not None]
    if D.get("imports_yearly"):
        old = {r["year"]: r for r in T.get("cotton_imports_yearly", [])}
        for r in D["imports_yearly"]:
            if len(r) >= 4 and r[0].isdigit():
                old[int(r[0])] = {"year": int(r[0]), "kt": num(r[1]) * 10, "yoy_pct": num(r[2]), "musd": num(r[3])}
        T["cotton_imports_yearly"] = [old[k] for k in sorted(old, reverse=True)]
    T["collected"] = D.get("collected_at", "")[:10]
    TAB.write_text(json.dumps(T, ensure_ascii=False))
    A = load(ART, {"list": [], "art": {}})
    new = 0
    for u, a in (D.get("art") or {}).items():
        if u not in A["art"]:
            new += 1
        A["art"][u] = a
    seen = {x[2] for x in A["list"]}
    A["list"] = [x for x in (D.get("list") or []) if x[2] not in seen] + A["list"]
    ART.write_text(json.dumps(A, ensure_ascii=False))
    print(f"cca: {len(D.get('ccindex') or [])} CCIndex rows read, {len(D.get('cotlook') or [])} Cotlook rows, {new} new articles; quotes {q.get('cc3128')}; errors {D.get('errors')}")


def ingest_gacc(p):
    D = payload(p)
    rows = []
    if GACC.exists():
        with GACC.open() as f:
            rows = list(csv.DictReader(f))
    key = lambda r: (r["flow"], str(r["year"]), r["mon"], r["commodity"])
    d = {key(r): r for r in rows}
    n = 0
    for r in D.get("rows", []):
        x = dict(zip(GCOLS, [str(v) for v in r]))
        if key(x) not in d:
            n += 1
        d[key(x)] = x
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=GCOLS)
    w.writeheader()
    for k in sorted(d, key=lambda k: (k[0], int(k[1]), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(k[2]) if k[2] in
                                      ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"] else 99, k[3])):
        w.writerow(d[k])
    GACC.write_text(buf.getvalue())
    print(f"gacc: {n} new rows; log {D.get('log', [])[-4:]}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "known"
    if cmd == "known":
        known()
    elif cmd == "cca":
        ingest_cca(sys.argv[2])
    elif cmd == "gacc":
        ingest_gacc(sys.argv[2])
