"""Brazil and Argentina soybeans, corn, wheat (runs in GitHub Actions).

- CONAB (Brazil): historical series by state (SerieHistoricaGraos) and every monthly survey since 2017/18
  (LevantamentoGraos) -> national estimates and the survey-by-survey revision path.
- CONAB weekly crop progress bulletin ("Acompanhamento das Lavouras"): newest file saved for parsing.
- USDA PSD (FAS API, FAS_API_KEY): Brazil, Argentina and China balances (area, production, crush, exports/imports,
  ending stocks), current and previous marketing year.
- Comex Stat (Brazil's Ministry of Development, open API): monthly export volumes of soybeans, corn, meal, oil.
- MAGyP (Argentina's agriculture ministry, open data): planted/harvested area and production by campaign.
Writes data/south_america/*.csv|json.
"""
import io, json, os, re, time
from pathlib import Path
from urllib.parse import quote
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "south_america"
H = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk)"}
CONAB = "https://portaldeinformacoes.conab.gov.br/downloads/arquivos/"
PRODUCTS = {"SOJA": "soybeans", "MILHO TOTAL": "corn_total", "MILHO 1A SAFRA": "corn_1st", "MILHO 2A SAFRA": "corn_2nd", "MILHO 3A SAFRA": "corn_3rd", "TRIGO": "wheat"}
NCM = {"soybeans": ["12019000"], "corn": ["10059010"], "meal": ["23040010", "23040090"], "oil": ["15071000"], "wheat_imports": ["10019900"]}
PSD = {"soybeans": "2222000", "meal": "0813100", "oil": "4232000", "corn": "0440000", "wheat": "0410000"}
PSD_ATTR = {4: "area_harvested", 20: "beg_stocks", 28: "production", 57: "imports", 88: "exports", 7: "crush", 125: "domestic", 176: "end_stocks", 149: "feed", 161: "food"}


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers={**H, **kw.pop("headers", {})}, timeout=180, **kw)
            if r.status_code == 200:
                return r
            print("HTTP", r.status_code, url[:120])
        except Exception as e:
            print("ERR", str(e)[:100], url[:100])
        time.sleep(5 * (i + 1))
    return None


def _conab_frame(raw, safra_col):
    d = pd.read_csv(io.StringIO(raw.decode("latin-1")), sep=";", on_bad_lines="skip")
    d.columns = [c.strip() for c in d.columns]
    for c in d.select_dtypes("object"):
        d[c] = d[c].astype(str).str.strip()
    P = d.produto.str.upper()
    d["product"] = None
    d.loc[P.str.startswith("SOJA"), "product"] = "soybeans"
    d.loc[P.str.startswith("MILHO"), "product"] = "corn"
    d.loc[P.str.startswith("TRIGO"), "product"] = "wheat"
    d = d[d["product"].notna()].copy()
    sf = d[safra_col].astype(str).str.upper() if safra_col in d else pd.Series("UNICA", index=d.index)
    crop = sf.str.extract(r"(\d)")[0]
    # corn: crop number from the safra column or from the product name (MILHO 2A SAFRA)
    crop = crop.fillna(P.str.extract(r"(\d)")[0])
    d.loc[d["product"] == "corn", "product"] = "corn_" + crop[d["product"] == "corn"].fillna("total").map(lambda x: {"1": "1st", "2": "2nd", "3": "3rd"}.get(x, x))
    for c in ("area_plantada_mil_ha", "producao_mil_t"):
        d[c] = pd.to_numeric(d[c].astype(str).str.replace(",", "."), errors="coerce")
    return d


def conab():
    out = {}
    r = get(CONAB + "SerieHistoricaGraos.txt")
    if r:
        d = _conab_frame(r.content, "dsc_safra_previsao")
        nat = d.groupby(["ano_agricola", "product"])[["area_plantada_mil_ha", "producao_mil_t"]].sum().reset_index()
        tot = nat[nat["product"].str.startswith("corn_")].groupby("ano_agricola")[["area_plantada_mil_ha", "producao_mil_t"]].sum().reset_index().assign(product="corn")
        nat = pd.concat([nat, tot])
        nat["yield_t_ha"] = (nat.producao_mil_t / nat.area_plantada_mil_ha).round(3)
        nat.to_csv(OUT / "conab_history.csv", index=False)
        d[d.ano_agricola == d.ano_agricola.max()].groupby(["uf", "product"])[["area_plantada_mil_ha", "producao_mil_t"]].sum().reset_index().to_csv(OUT / "conab_states_latest.csv", index=False)
        out["history_rows"] = len(nat)
        out["products_seen"] = sorted(d.produto.unique().tolist())[:20]
    r = get(CONAB + "LevantamentoGraos.txt")
    if r:
        d = _conab_frame(r.content, "safra")
        d["survey"] = pd.to_numeric(d.id_levantamento, errors="coerce")
        nat = d.groupby(["ano_agricola", "product", "survey"])[["area_plantada_mil_ha", "producao_mil_t"]].sum().reset_index()
        tot = nat[nat["product"].str.startswith("corn_")].groupby(["ano_agricola", "survey"])[["area_plantada_mil_ha", "producao_mil_t"]].sum().reset_index().assign(product="corn")
        pd.concat([nat, tot]).to_csv(OUT / "conab_surveys.csv", index=False)
        out["survey_rows"] = len(nat)
    # weekly progress bulletin: newest link on the progress page
    p = get("https://www.gov.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/progresso-de-safra")
    if p:
        links = re.findall(r'href="(https://www\.gov\.br/conab/pt-br/atuacao/informacoes-agropecuarias/safras/progresso-de-safra/acompanhamento[^"]+)"[^>]*>\s*([^<]+)<', p.text)
        if links:
            url, title = links[0]
            f = get(url)
            if f is not None:
                ct = f.headers.get("content-type", "")
                if "html" in ct:  # landing page: find the file
                    m = re.search(r'href="([^"]+\.(?:xlsx|xls|pdf)[^"]*)"', f.text, re.I) or re.search(r'href="([^"]+/@@download/file[^"]*)"', f.text)
                    if m:
                        f = get(m.group(1) if m.group(1).startswith("http") else "https://www.gov.br" + m.group(1))
                        ct = f.headers.get("content-type", "") if f else ""
                if f is not None:
                    ext = "xlsx" if "sheet" in ct or "excel" in ct else "pdf" if "pdf" in ct else "bin"
                    (OUT / "raw").mkdir(exist_ok=True)
                    (OUT / "raw" / f"conab_progress_latest.{ext}").write_bytes(f.content)
                    (OUT / "raw" / "conab_progress_latest.json").write_text(json.dumps({"title": title.strip(), "url": url, "content_type": ct, "bytes": len(f.content)}))
                    out["progress"] = title.strip()
    return out


def psd():
    key = (os.getenv("FAS_API_KEY") or "").strip()
    if not key:
        return {}
    rows = []
    yr = pd.Timestamp.now().year
    for com, code in PSD.items():
        for ctry in ("BR", "AR", "CH", "US"):
            if ctry == "CH" and com not in ("soybeans", "meal", "corn"):
                continue
            for y in range(yr - 6, yr + 1):
                r = get(f"https://api.fas.usda.gov/api/psd/commodity/{code}/country/{ctry}/year/{y}", headers={"X-Api-Key": key})
                if not r:
                    continue
                for x in r.json():
                    a = PSD_ATTR.get(x["attributeId"])
                    if a:
                        rows.append({"commodity": com, "country": ctry, "my": int(x["marketYear"]), "month": x.get("month"), "attr": a, "value": x["value"]})
                time.sleep(0.4)
    if rows:
        pd.DataFrame(rows).to_csv(OUT / "psd.csv", index=False)
    return {"psd_rows": len(rows)}


def comex():
    rows = []
    yr = pd.Timestamp.now().year
    for com, ncms in NCM.items():
        flow = 2 if com.endswith("imports") else 1
        for y0 in range(2015, yr + 1, 3):
            y1 = min(y0 + 2, yr)
            f = {"yearStart": str(y0), "yearEnd": str(y1), "typeForm": flow, "typeOrder": 1, "filterList": [{"id": "noNcmpt"}],
                 "filterArray": [{"item": ncms, "idInput": "noNcmpt"}], "detailDatabase": [{"id": "noNcmpt", "text": ""}], "monthDetail": True,
                 "metricFOB": True, "metricKG": True, "monthStart": "01", "monthEnd": "12", "formQueue": "general", "langDefault": "en"}
            r = get("https://api-comexstat.mdic.gov.br/general?filter=" + quote(json.dumps(f, separators=(",", ":"))))
            if not r:
                continue
            for x in r.json().get("data", {}).get("list", []):
                rows.append({"commodity": com, "year": int(x["coAno"]), "month": int(x["coMes"]), "ncm": x.get("coNcm"), "fob_usd": float(x.get("vlFob") or 0), "kg": float(x.get("kgLiquido") or 0)})
            time.sleep(2)
    if rows:
        d = pd.DataFrame(rows).groupby(["commodity", "year", "month"])[["fob_usd", "kg"]].sum().reset_index()
        d["kt"] = (d.kg / 1e6).round(1)
        d.to_csv(OUT / "brazil_exports.csv", index=False)
    return {"comex_rows": len(rows)}


def magyp():
    r = get("https://datos.magyp.gob.ar/api/3/action/package_show?id=estimaciones-agricolas")
    if not r:
        return {}
    res = [x for x in r.json()["result"]["resources"] if x.get("url", "").endswith(".csv") and "estimaciones-agricolas" in x["url"]]
    if not res:
        return {}
    f = get(res[0]["url"])
    if not f:
        return {}
    d = pd.read_csv(io.BytesIO(f.content), encoding="utf-8", low_memory=False)
    out_crops = sorted(d.cultivo.unique().tolist())
    d = d[d.cultivo.str.lower().str.contains(r"soja|ma[ií]z|trigo|girasol", regex=True)]
    for c in ("superficie_sembrada_ha", "superficie_cosechada_ha", "produccion_tm"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    nat = d.groupby(["cultivo", "campania"])[["superficie_sembrada_ha", "superficie_cosechada_ha", "produccion_tm"]].sum().reset_index()
    nat.to_csv(OUT / "argentina_estimates.csv", index=False)
    return {"magyp_file": res[0]["url"].rsplit("/", 1)[-1], "magyp_rows": len(nat), "crops_all": out_crops[:60]}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    log = {"generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d %H:%M UTC")}
    for name, fn in (("conab", conab), ("psd", psd), ("comex", comex), ("magyp", magyp)):
        try:
            log[name] = fn()
        except Exception as e:
            import traceback; traceback.print_exc()
            log[name] = {"error": str(e)[:200]}
        print(name, log[name])
    (OUT / "run_log.json").write_text(json.dumps(log, indent=1))
