"""USDA FAS daily export sales announcements ("flash sales", 100k MT+ reported by 9 am ET next day).

Collected in the Mac browser (fas.usda.gov blocks GitHub runners): cme/collect_flash.js returns gzip+base64 JSON
of newsroom cards [{t, title, href, text}]. This script merges them into data/grains/raw/flash/announcements.json
and parses each into rows: date, commodity, qty_mt, destination, my.
Usage: python pipelines/flash.py <b64 file>   (no argument = just re-parse)
"""
import base64, gzip, json, re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "grains" / "raw" / "flash"
COM = [  # (pattern, key) - most specific first
    (r"soybean cake and meal|soybean meal", "meal"), (r"soybean oil", "oil"), (r"soybeans?", "soybeans"),
    (r"hard red winter wheat", "wheat_hrw"), (r"soft red winter wheat", "wheat_srw"), (r"hard red spring wheat", "wheat_hrs"),
    (r"white wheat", "wheat_white"), (r"durum wheat", "wheat_durum"), (r"wheat", "wheat"),
    (r"(?:yellow |white )?corn", "corn"), (r"(?:grain )?sorghum", "sorghum"),
    (r"upland cotton|cotton", "cotton"), (r"pima cotton", "cotton_pima"), (r"barley", "barley"), (r"oats", "oats")]
CLAUSE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:metric tons|MT|tons)\s+of\s+([a-z ]+?)\s+(?:received in the reporting period\s+)?"
                    r"(?:(?:for delivery|to be delivered|for shipment)\s+)?to\s+(.+?)(?=\s+during|\s+for delivery|\s+in the|;|--|\.|\s+and\s+\d|,\s*\d|$)", re.I)
MYRE = re.compile(r"(?:MY\s*|the\s+)(\d{4})/(\d{2,4})", re.I)


def com_key(s):
    s = s.lower().strip()
    for pat, k in COM:
        if re.fullmatch(pat, s) or re.search(r"\b" + pat + r"\b", s):
            return k
    return s


def parse(rec):
    text = rec.get("text") or ""
    out = []
    mys = MYRE.findall(text)
    default_my = f"{mys[0][0]}/{mys[0][1][-2:]}" if mys else None
    for m in CLAUSE.finditer(text):
        qty = float(m.group(1).replace(",", ""))
        rest = text[m.end(): m.end() + 80]
        mm = MYRE.search(rest)
        my = f"{mm.group(1)}/{mm.group(2)[-2:]}" if mm and mm.start() < 40 else default_my
        out.append({"date": rec["t"][:10], "time": rec["t"][11:16], "commodity": com_key(m.group(2)), "qty_mt": qty,
                    "destination": re.sub(r"\s*[-–]+\s*[\d,].*$", "", m.group(3).strip()).rstrip(",").replace("unknown destinations", "Unknown").title(),
                    "my": my, "href": rec["href"]})
    return out


def main():
    D.mkdir(parents=True, exist_ok=True)
    p = D / "announcements.json"
    have = {r["href"]: r for r in json.loads(p.read_text())} if p.exists() else {}
    if len(sys.argv) > 1:
        new = json.loads(gzip.decompress(base64.b64decode(Path(sys.argv[1]).read_text().strip())))
        for r in new:
            old = have.get(r["href"])
            if old and old.get("full") and not r.get("full"):
                continue  # keep the full text already fetched
            have[r["href"]] = r
    recs = sorted(have.values(), key=lambda r: r["t"])
    p.write_text(json.dumps(recs, indent=0))
    rows = [x for r in recs for x in parse(r)]
    df = pd.DataFrame(rows)
    df.to_csv(D / "flash.csv", index=False)
    unparsed = [r for r in recs if not parse(r)]
    print(len(recs), "announcements,", len(df), "sales parsed,", len(unparsed), "unparsed")
    for r in unparsed[:5]:
        print("  UNPARSED", r["t"][:10], (r.get("text") or "")[:160])
    if len(df):
        print(df.groupby("commodity").qty_mt.agg(["count", "sum"]).sort_values("count", ascending=False).head(10))


if __name__ == "__main__":
    main()
