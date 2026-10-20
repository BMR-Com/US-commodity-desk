"""Dairy supply and demand.

- Monthly balances (ERS): milk on milk-fat and skim-solids bases; cheese (American, other),
  butter, dry skim milk (NDM/SMP), dry whey, WPC, lactose.
- Metrics per balance: production / disappearance / exports y/y, stocks vs 5-year same-month
  average, stocks in months of use.
- WASDE annual dairy balance and price forecasts with month-to-month revisions (read from the
  BMR-Com/wasde-analytics processed files).
- Price link: product stocks-to-use vs the NDPSR monthly product price.

Writes data/dairy/derived/sd.json (consumed by the site).
"""
import json
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "dairy" / "raw"
OUT = ROOT / "data" / "dairy" / "derived"
WASDE = "https://raw.githubusercontent.com/BMR-Com/wasde-analytics/main/data/{}.json"

MILK_TABLES = {"fat": "M.E. Milk-fat basis, monthly", "skim": "M.E. Skim-solids basis, monthly"}
PRODUCTS = {  # key: (ERS table, stock item names, production item, price column in class prices)
    "cheese_american": ("Amer cheese, monthly", "cold", "Production", "cheese_monthly_avg_Price"),
    "cheese_other": ("Other cheese, monthly", "cold", "Production", None),
    "butter": ("Butter, monthly", "cold", "Production", "butter_monthly_avg_Price"),
    "ndm_smp": ("Dry skim milk, monthly", "mfr", "Production, total", "nfdm_monthly_avg_Price"),
    "dry_whey": ("Dry whey, monthly", "mfr", None, "whey_monthly_avg_Price"),
    "wpc": ("WPC, monthly", "mfr", None, None),
    "lactose": ("Lactose, monthly", "mfr", None, None),
}
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def to_wide(df):
    df = df[df.Frequency == "Monthly"].copy()
    df["month"] = pd.PeriodIndex.from_fields(year=df.Year, month=df.Timeperiod_id, freq="M")
    return df.pivot_table(index="month", columns="Data_item", values="Quantity", aggfunc="sum").sort_index()


def pick(w, *names):
    for n in names:
        if n and n in w.columns:
            return w[n]
    return None


def metrics(w, prod, disp, exp, stocks):
    m = {}
    last = w.index.max()
    def yoy(s):
        if s is None or last - 12 not in s.index:
            return None
        return round(100 * (s[last] / s[last - 12] - 1), 1)
    def ytd_yoy(s):
        if s is None:
            return None
        cur = s[(s.index.year == last.year) & (s.index.month <= last.month)].sum()
        prev = s[(s.index.year == last.year - 1) & (s.index.month <= last.month)].sum()
        return round(100 * (cur / prev - 1), 1) if prev else None
    m["last_month"] = str(last)
    for nm, s in (("production", prod), ("disappearance", disp), ("exports", exp), ("ending_stocks", stocks)):
        if s is not None:
            m[nm] = {"value": round(float(s[last]), 1), "yoy_pct": yoy(s), "ytd_yoy_pct": ytd_yoy(s) if nm != "ending_stocks" else None}
    if stocks is not None:
        same = [stocks.get(last - 12 * k) for k in range(1, 6)]
        same = [x for x in same if x is not None and pd.notna(x)]
        if same:
            avg5 = sum(same) / len(same)
            m["ending_stocks"]["vs_5y_avg_pct"] = round(100 * (stocks[last] / avg5 - 1), 1)
        use = None
        if disp is not None:
            use = disp.rolling(3).mean() + (exp.rolling(3).mean() if exp is not None else 0)
            m["ending_stocks"]["months_of_use"] = round(float(stocks[last] / use[last]), 2)
    return m


def series(w, cols):
    out = {"month": [str(i) for i in w.index]}
    for k, s in cols.items():
        if s is not None:
            out[k] = [None if pd.isna(v) else round(float(v), 2) for v in s.reindex(w.index)]
    return out


def milk_balances():
    d = pd.read_csv(RAW / "ers" / "ers_milk_supply_use.csv")
    res = {}
    for key, tbl in MILK_TABLES.items():
        w = to_wide(d[d.Table == tbl])
        prod, disp, exp, st = (pick(w, "Production"), pick(w, "Domestic disappearance"),
                               pick(w, "Exports"), pick(w, "Ending stocks"))
        res[key] = {"metrics": metrics(w, prod, disp, exp, st),
                    "series": series(w, {"production": prod, "marketings": pick(w, "Marketings"),
                                         "imports": pick(w, "Imports"), "exports": exp,
                                         "domestic_disappearance": disp, "ending_stocks": st})}
    return res


def product_balances(cp):
    d = pd.read_csv(RAW / "ers" / "ers_product_supply_use.csv")
    res = {}
    for key, (tbl, stock_kind, prod_item, price_col) in PRODUCTS.items():
        w = to_wide(d[d.Table == tbl])
        if stock_kind == "cold":
            st = pick(w, "Ending cold-storage stocks")
        else:
            st = pick(w, "Ending manufacturers' stocks, total", "Ending manufacturers' stocks")
            if st is None:
                parts = [c for c in w.columns if c.startswith("Ending manufacturers' stocks")]
                st = w[parts].sum(axis=1) if parts else None
        prod = pick(w, prod_item, "Production, total", "Production")
        if prod is None:
            parts = [c for c in w.columns if c.startswith("Production")]
            prod = w[parts].sum(axis=1) if parts else None
        disp = pick(w, "Domestic disappearance", "Apparent domestic human use")
        exp = pick(w, "Exports")
        cols = {"production": prod, "imports": pick(w, "Imports"), "exports": exp,
                "domestic_disappearance": disp, "ending_stocks": st}
        entry = {"metrics": metrics(w, prod, disp, exp, st), "series": series(w, cols)}
        if price_col and price_col in cp.columns:
            px = cp[price_col].reindex(w.index)
            entry["series"]["price"] = [None if pd.isna(v) else round(float(v), 4) for v in px]
            # stocks-to-use vs price: months of use against the month's NDPSR price
            use = (disp.rolling(3).mean() + (exp.rolling(3).mean() if exp is not None else 0)) if disp is not None else None
            if use is not None and st is not None:
                mou = (st / use).reindex(w.index)
                entry["series"]["months_of_use"] = [None if pd.isna(v) else round(float(v), 3) for v in mou]
        res[key] = entry
    return res


def class_prices():
    d = pd.read_csv(RAW / "class_prices" / "detail.csv").dropna(subset=["class_3_Price"])
    d.index = pd.PeriodIndex([pd.Period(f"{y}-{MONTHS[m]:02d}", "M") for y, m in zip(d.report_year, d.report_month)])
    return d.sort_index()


def wasde():
    files = {"milk_fat": "Milk,_Fat_Basis", "milk_skim": "Milk,_Skim-Soild_Basis", "milk": "Milk",
             "class3": "Milk,_Class_III", "class4": "Milk,_Class_IV", "cheese": "Cheese", "butter": "Butter",
             "ndm": "Nonfat_Dry_Milk", "whey": "Dry_Whey"}
    keep = {"Marketings", "Production", "Imports", "Exports", "Commercial Exports", "Domestic Use",
            "Domestic Commercial Use", "Ending Stocks", "Ending Commercial Stocks", "Total Supply", "Prices"}
    out = {}
    for key, f in files.items():
        try:
            j = requests.get(WASDE.format(f), timeout=60).json()
        except Exception as e:
            print("wasde", f, e)
            continue
        latest_years = sorted({int(k.split("||")[2]) for k in j["data"]})[-3:]
        rows = {}
        for k, hist in j["data"].items():
            _, attr, yr = k.split("||")
            if attr not in keep or int(yr) not in latest_years or not hist:
                continue
            hist = sorted(hist, key=lambda h: h["wasdeNum"])
            cur = hist[-1]
            prev = hist[-2] if len(hist) > 1 else None
            rows.setdefault(attr, {})[yr] = {
                "value": cur["value"], "unit": cur["unit"], "report": cur["reportDate"],
                "change": None if prev is None else round(cur["value"] - prev["value"], 3),
                "history": [[h["reportDate"], h["value"]] for h in hist[-14:]]}
        out[key] = rows
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cp = class_prices()
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from esmis_parse import milk_production
        mp = milk_production()
        nass_milk = mp.tail(36).astype(object).where(mp.tail(36).notna(), None).to_dict(orient="list")
        nass_milk["released"] = [str(x) for x in nass_milk["released"]]
    except Exception as e:
        print("nass milk", e)
        nass_milk = None
    sd = {"generated": pd.Timestamp.now("UTC").isoformat(timespec="minutes"), "nass_milk": nass_milk,
          "milk": milk_balances(), "products": product_balances(cp), "wasde": wasde()}
    (OUT / "sd.json").write_text(json.dumps(sd, separators=(",", ":")))
    print("milk", json.dumps(sd["milk"]["fat"]["metrics"]))
    for k, v in sd["products"].items():
        print(k, json.dumps(v["metrics"]))
    for k, v in sd["wasde"].items():
        print("WASDE", k, {a: {y: (x["value"], x["change"]) for y, x in yrs.items()} for a, yrs in v.items()})
