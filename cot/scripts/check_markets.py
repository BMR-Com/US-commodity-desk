#!/usr/bin/env python3
"""Diagnostic: which CFTC markets exist for each BCOM constituent, and how recent.
Writes data/diagnostics/market_check.json. Run via the 'CFTC Market Check' workflow."""
import json, requests, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_cot_data import BCOM

DATASETS = {"disagg_combined": "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json",
            "disagg_futures": "https://publicreporting.cftc.gov/resource/72hh-3qpy.json",
            "legacy_futures": "https://publicreporting.cftc.gov/resource/6dca-aqww.json"}
KEYWORDS = ["ALUMIN", "ZINC", "NICKEL", "LEAD", "GASOIL", "GAS OIL", "SULPHUR", "SULFUR",
            "BRENT", "CRUDE", "WTI", "NAT GAS", "NATURAL GAS", "RBOB", "GASOLINE", "ULSD", "HEATING", "COPPER"]

def q(url, params):
    r = requests.get(url, params=params, timeout=90); r.raise_for_status(); return r.json()

out = {"by_keyword": {}, "bcom_codes": {}}
for ds, url in DATASETS.items():
    where = " OR ".join(f"upper(market_and_exchange_names) like '%{k}%'" for k in KEYWORDS)
    try:
        rows = q(url, {"$select": "cftc_contract_market_code, market_and_exchange_names, max(report_date_as_yyyy_mm_dd) as last, count(*) as n",
                       "$where": where, "$group": "cftc_contract_market_code, market_and_exchange_names",
                       "$order": "last DESC", "$limit": 5000})
    except Exception as e:
        rows = [{"error": str(e)}]
    out["by_keyword"][ds] = rows
    codes = {}
    for name, m in BCOM.items():
        w = f"cftc_contract_market_code='{m['code']}'" if m.get("code") else f"market_and_exchange_names='{m['cftc']}'"
        try:
            r = q(url, {"$select": "max(report_date_as_yyyy_mm_dd) as last, min(report_date_as_yyyy_mm_dd) as first, count(*) as n", "$where": w})
            codes[name] = r[0] if r else None
        except Exception as e:
            codes[name] = {"error": str(e)}
    out["bcom_codes"][ds] = codes

p = Path(__file__).resolve().parent.parent / "data" / "diagnostics"; p.mkdir(parents=True, exist_ok=True)
(p / "market_check.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out["bcom_codes"]["disagg_combined"], indent=1))
