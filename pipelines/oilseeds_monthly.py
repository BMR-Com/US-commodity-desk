"""Monthly soybean-complex data for the Grain summary balance sheets.

Steps (python pipelines/oilseeds_monthly.py nass magyp; default both):
- nass:  USDA NASS "Fats and Oils: Oilseed Crushings, Production, Consumption and Stocks" (monthly) via the QuickStats
         API (NASS_API_KEY). Every national monthly series whose description mentions soybean(s), for commodities
         SOYBEANS / OIL / CAKE & MEAL, 2010+ -> data/grains/raw/fats_oils/<commodity>.csv.gz, plus the list of
         descriptions found (short_desc.json) so the model can match them.
- magyp: Argentina agriculture ministry (MAGyP) monthly oilseed crush with oil/pellet/expeller output since 1965, and
         month-end stocks of grain, oil, pellets and expellers by province since 2015 (xlsx on magyp.gob.ar)
         -> data/south_america/ar_crush_monthly.csv, ar_stocks_monthly.csv.
         `python pipelines/oilseeds_monthly.py xlsx <molienda.xlsx> <existencias.xlsx>` parses files downloaded in a
         browser when magyp.gob.ar refuses the runner.
"""
import csv, gzip, io, json, os, sys, time
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)"}
QS = "https://quickstats.nass.usda.gov/api/"
NASS_OUT = ROOT / "data" / "grains" / "raw" / "fats_oils"
SA_OUT = ROOT / "data" / "south_america"
MAGYP = ("https://www.magyp.gob.ar/sitio/areas/ss_mercados_agropecuarios/areas/granos/_archivos/000058_Estadísticas/")
MOL = "000032_Evolucion de la Molienda (Cereales y Oleaginosas)/000002_Evolución de la Molienda Mensual - Oleaginosas/descarga_molienda_oleaginosas_historico.xlsx"
EXI = "000031_Existencias de Granos de Aceites y Subproductos por Provincia/descarga_existencias_por_provincia_historico.xlsx"
MONTHS = {m: i for i, m in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def qs(path, **p):
    key = os.environ.get("NASS_API_KEY", "")
    for i in range(4):
        try:
            r = requests.get(QS + path, params={"key": key, **p}, headers=H, timeout=180)
            if r.status_code == 200:
                return r.json()
            t = r.text.lower()
            if r.status_code == 413 or "exceeds" in t:
                return {"too_big": True}
            if r.status_code == 400:
                return {}
            print("  HTTP", r.status_code, r.text[:150])
        except Exception as e:
            print("  retry", e)
        time.sleep(4 * (i + 1))
    return {}


def nass():
    if not os.environ.get("NASS_API_KEY"):
        print("nass: NASS_API_KEY missing"); return
    NASS_OUT.mkdir(parents=True, exist_ok=True)
    found = {}
    for com in ["SOYBEANS", "OIL", "CAKE & MEAL"]:
        base = dict(commodity_desc=com, freq_desc="MONTHLY", agg_level_desc="NATIONAL", source_desc="SURVEY")
        sd = qs("get_param_values/", param="short_desc", **base).get("short_desc", [])
        sd = [s for s in sd if "SOYBEAN" in s.upper() and "PRICE" not in s.upper() and "PCT" not in s.upper()]
        found[com] = sd
        print(com, len(sd), "soybean series")
        rows = []
        for s in sd:
            d = qs("api_GET/", format="JSON", short_desc=s, year__GE="2010", **base)
            if d.get("too_big"):
                d = {"data": qs("api_GET/", format="JSON", short_desc=s, year__GE="2018", **base).get("data", [])}
            for r in d.get("data", []):
                m = MONTHS.get(str(r.get("reference_period_desc", ""))[:3].upper())
                v = str(r.get("Value", "")).replace(",", "").strip()
                if not m or not v or v.startswith("("):
                    continue
                rows.append([r["short_desc"], int(r["year"]), m, float(v), r.get("unit_desc", ""), r.get("load_time", "")[:10]])
            time.sleep(0.4)
        if rows:
            p = NASS_OUT / f"{com.split()[0].lower()}.csv.gz"
            with gzip.open(p, "wt", newline="") as f:
                w = csv.writer(f)
                w.writerow(["short_desc", "year", "month", "value", "unit", "load_time"])
                w.writerows(sorted(rows))
            print(" ->", p.name, len(rows), "rows")
    (NASS_OUT / "short_desc.json").write_text(json.dumps(found, indent=1))


def parse_molienda(raw):
    x = pd.read_excel(io.BytesIO(raw), header=None)
    hdr = x.index[x.iloc[:, 0].astype(str).str.upper().str.startswith("AÑO")][0]
    x = x.iloc[hdr + 1:].dropna(subset=[0, 1])
    # column blocks: grains (SOJA..CANOLA, 7), oils (7), pellets (from col 16), expellers; soy is the first of each
    names = [str(v).strip().upper() for v in pd.read_excel(io.BytesIO(raw), header=None).iloc[hdr]]
    soy = [i for i, n in enumerate(names) if "SOJA" in n]
    out = pd.DataFrame({"year": x[0].astype(int), "month": x[1].astype(int)})
    labels = ["crush", "oil", "pellets", "expellers"]
    for lab, i in zip(labels, soy):
        out[lab] = pd.to_numeric(x[i], errors="coerce")
    return out[out.crush.notna()]


def parse_existencias(raw):
    x = pd.read_excel(io.BytesIO(raw), header=None)
    hdr = x.index[x.iloc[:, 0].astype(str).str.upper().str.startswith("AÑO")][0]
    cols = [str(v).strip().upper() for v in x.iloc[hdr]]
    x = x.iloc[hdr + 1:].copy()
    x.columns = cols
    x = x.dropna(subset=["AÑO", "MES"])
    x["SOJA"] = pd.to_numeric(x["SOJA"], errors="coerce")
    g = x.groupby(["AÑO", "MES", "PRODUCCION"]).SOJA.sum().unstack("PRODUCCION")
    g.columns = [str(c).strip().lower() for c in g.columns]
    g = g.reset_index().rename(columns={"AÑO": "year", "MES": "month", "granos": "beans", "aceites": "oil", "aceite": "oil"})
    g["year"], g["month"] = g.year.astype(int), g.month.astype(int)
    return g


def write_ar(mol, exi):
    SA_OUT.mkdir(parents=True, exist_ok=True)
    if mol is not None:
        mol.to_csv(SA_OUT / "ar_crush_monthly.csv", index=False)
        print("ar_crush_monthly", len(mol), "rows to", mol.year.iloc[-1], mol.month.iloc[-1])
    if exi is not None:
        exi.to_csv(SA_OUT / "ar_stocks_monthly.csv", index=False)
        print("ar_stocks_monthly", len(exi), "rows to", exi.year.iloc[-1], exi.month.iloc[-1], list(exi.columns))


def magyp():
    got = {}
    for k, p in (("mol", MOL), ("exi", EXI)):
        try:
            r = requests.get(MAGYP + quote(p), headers=H, timeout=120)
            got[k] = r.content if r.status_code == 200 and r.content[:2] == b"PK" else None
            print("magyp", k, r.status_code, len(r.content))
        except Exception as e:
            print("magyp", k, "failed:", e)
            got[k] = None
    write_ar(parse_molienda(got["mol"]) if got.get("mol") else None,
             parse_existencias(got["exi"]) if got.get("exi") else None)


def conab():
    """CONAB supply & demand (Boletim da Safra de Grãos xlsx), found and downloaded with the open-source `agrobr`
    package. Every 'Suprimento' sheet is kept as a long table (sheet, row, label, safra column, value) so soybean
    crush ('processamento') stays separate; agrobr's own balanço frames for soja and milho are saved alongside."""
    import asyncio
    try:
        from agrobr import conab as ac
        from agrobr.conab import client
    except Exception as e:
        print("conab: agrobr not installed", e); return
    async def latest():
        # agrobr's full catalog walk breaks on a later (empty) gov.br page; the newest surveys are on page 1
        try:
            return await client.fetch_safra_xlsx()
        except Exception as e:
            print("conab: catalog walk failed, using page 1 only:", str(e)[:120])
        html = await client.fetch_boletim_page()
        levs = await client.list_levantamentos(html=html)
        t = dict(levs[0])
        return await client.download_xlsx(t["url"], metadata=t), t
    try:
        xlsx, meta = asyncio.run(latest())
    except Exception as e:
        print("conab: fetch failed", e); return
    print("conab:", meta.get("safra"), "levantamento", meta.get("levantamento"), meta.get("url", "")[:120])
    xl = pd.ExcelFile(xlsx)
    rows = []
    for sh in xl.sheet_names:
        if "suprimento" not in sh.lower() and "oferta" not in sh.lower():
            continue
        x = pd.read_excel(xl, sheet_name=sh, header=None)
        for i, r in x.iterrows():
            for j, v in enumerate(r.values[1:], 1):
                if pd.notna(v) and pd.notna(r.values[0]):
                    rows.append([sh, i, str(r.values[0]).strip(), j, v])
    SA_OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["sheet", "row", "label", "col", "value"]).to_csv(SA_OUT / "conab_supply_raw.csv", index=False)
    (SA_OUT / "conab_supply_meta.json").write_text(json.dumps({k: str(v) for k, v in meta.items()}, indent=1))
    print("conab supply sheets:", [s for s in xl.sheet_names if "suprimento" in s.lower() or "oferta" in s.lower()], len(rows), "cells")
    from agrobr.conab.parsers.v1 import ConabParserV1
    for prod in ("soja", "milho"):
        try:
            xlsx.seek(0)
            df = pd.DataFrame(ConabParserV1().parse_suprimento(xlsx=xlsx, produto=prod))
            df.to_csv(SA_OUT / f"conab_balanco_{prod}.csv", index=False)
            print("conab balanco", prod, len(df))
        except Exception as e:
            print("conab balanco", prod, "failed", e)


if __name__ == "__main__":
    a = sys.argv[1:] or ["nass", "magyp", "conab"]
    if a[0] == "xlsx":
        write_ar(parse_molienda(Path(a[1]).read_bytes()), parse_existencias(Path(a[2]).read_bytes()))
    else:
        if "nass" in a:
            nass()
        if "magyp" in a:
            magyp()
        if "conab" in a:
            conab()
