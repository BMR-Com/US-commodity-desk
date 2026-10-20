"""Dairy class price model.

1. Rebuild AMS monthly component and class prices from NDPSR product averages, with the formula
   regime in force each month, and check against the announced prices.
2. Month-to-date nowcast of Class III / IV from the weekly NDPSR (sales-weighted weeks whose
   week-ending Saturday falls in the month), plus the AMS monthly averages it is replicating.
3. Futures-implied Class III / IV per contract month from CME cheese, butter, NDM and dry whey
   settlements, compared with Class III / IV futures (from data/cme/, when present).

Outputs in data/dairy/derived/.
"""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "dairy" / "raw"
OUT = ROOT / "data" / "dairy" / "derived"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def regime(ym):
    """FMMO formula constants for a month (period like 2026-09)."""
    if ym >= pd.Period("2025-06", "M"):
        r = dict(ma_cheese=0.2519, ma_butter=0.2272, ma_ndm=0.2393, ma_whey=0.2668, bf_rec=0.91,
                 prot_yield=1.589, cheese="blocks")
    else:
        r = dict(ma_cheese=0.2003, ma_butter=0.1715, ma_ndm=0.1678, ma_whey=0.1991, bf_rec=0.90,
                 prot_yield=1.572, cheese="blend")
    if ym >= pd.Period("2025-12", "M"):
        r.update(protein=3.3, other=6.0, nfs=9.3)
    else:
        r.update(protein=3.1, other=5.9, nfs=9.0)
    return r


def components(cheese, butter, ndm, whey, r):
    bf = (butter - r["ma_butter"]) * 1.211
    nfs = (ndm - r["ma_ndm"]) * 0.99
    other = (whey - r["ma_whey"]) * 1.03
    a = cheese - r["ma_cheese"]
    protein = a * 1.383 + (a * r["prot_yield"] - r["bf_rec"] * bf) * 1.17
    c3_skim = protein * r["protein"] + other * r["other"]
    c4_skim = nfs * r["nfs"]
    return dict(butterfat=bf, nonfat_solids=nfs, other_solids=other, protein=protein,
                class3_skim=c3_skim, class4_skim=c4_skim,
                class3=0.965 * c3_skim + 3.5 * bf, class4=0.965 * c4_skim + 3.5 * bf)


def load_class_prices():
    d = pd.read_csv(RAW / "class_prices" / "detail.csv").dropna(subset=["class_3_Price"])
    d["month"] = [pd.Period(f"{y}-{MONTHS[m]:02d}", "M") for y, m in zip(d.report_year, d.report_month)]
    return d.sort_values("month").set_index("month")


def rebuild(cp):
    rows = []
    for m, x in cp.iterrows():
        r = regime(m)
        c = components(x.cheese_monthly_avg_Price, x.butter_monthly_avg_Price, x.nfdm_monthly_avg_Price,
                       x.whey_monthly_avg_Price, r)
        rows.append(dict(month=str(m), class3_ams=x.class_3_Price, class3_model=round(c["class3"], 2),
                         class4_ams=x.class_4_Price, class4_model=round(c["class4"], 2),
                         protein_ams=x.protein_Price, protein_model=round(c["protein"], 4),
                         butterfat_ams=x.butterfat_Price, butterfat_model=round(c["butterfat"], 4),
                         cheese=x.cheese_monthly_avg_Price, butter=x.butter_monthly_avg_Price,
                         ndm=x.nfdm_monthly_avg_Price, whey=x.whey_monthly_avg_Price))
    df = pd.DataFrame(rows)
    df["class3_err"] = (df.class3_model - df.class3_ams).round(2)
    df["class4_err"] = (df.class4_model - df.class4_ams).round(2)
    return df


def weekly_ndpsr():
    """Latest value per week for each product, from the weekly (revisable) NDPSR sections."""
    files = {"cheese": ("40_pound_block_cheddar_cheese_prices_and_sales.csv", "cheese_40_Price", "cheese_40_Sales"),
             "butter": ("butter_prices_and_sales.csv", "Butter_Price", "Butter_Sales"),
             "ndm": ("nonfat_dry_milk_prices_and_sales.csv", None, None),
             "whey": ("dry_whey_prices_and_sales.csv", None, None)}
    out = []
    for prod, (fn, pc, sc) in files.items():
        d = pd.read_csv(RAW / "ndpsr" / fn)
        pc = pc or next(c for c in d.columns if c.endswith("_Price") and "Wtd" not in c)
        sc = sc or next(c for c in d.columns if c.endswith("_Sales"))
        d = d.rename(columns={"Week Ending Date": "week", pc: "price", sc: "sales"})
        d["published"] = pd.to_datetime(d["published_date"])
        d["week"] = pd.to_datetime(d["week"])
        d = d.dropna(subset=["price"]).sort_values("published").groupby("week").tail(1)
        d["sales"] = pd.to_numeric(d["sales"].astype(str).str.replace(",", ""), errors="coerce")
        d["product"] = prod
        out.append(d[["week", "product", "price", "sales", "published"]])
    w = pd.concat(out)
    # Before June 2025 the Class III cheese price was the sales-weighted average of 40-lb blocks and
    # 500-lb barrels (moisture-adjusted) + $0.03; from June 2025 blocks only.
    b = pd.read_csv(RAW / "ndpsr" / "500_pound_barrel_cheddar_cheese_prices_sales_and_moisture_content.csv")
    b = b.rename(columns={"Week Ending Date": "week", "cheese_500_Wtd_Price": "bprice", "cheese_500_Sales": "bsales"})  # moisture-adjusted
    b["published"] = pd.to_datetime(b["published_date"])
    b["week"] = pd.to_datetime(b["week"])
    b = b.dropna(subset=["bprice"]).sort_values("published").groupby("week").tail(1)
    b["bsales"] = pd.to_numeric(b["bsales"].astype(str).str.replace(",", ""), errors="coerce")
    ch = w[w["product"] == "cheese"].merge(b[["week", "bprice", "bsales"]], on="week", how="left")
    old = (ch.week < "2025-06-01") & ch.bprice.notna() & ch.bsales.gt(0)
    ch.loc[old, "price"] = ((ch.price * ch.sales + (ch.bprice + 0.03) * ch.bsales) / (ch.sales + ch.bsales))[old]
    ch.loc[old, "sales"] = (ch.sales + ch.bsales)[old]
    w = pd.concat([w[w["product"] != "cheese"], ch[["week", "product", "price", "sales", "published"]]])
    return w.sort_values(["product", "week"])


def monthly_from_weekly(w):
    w = w.copy()
    w["month"] = w.week.dt.to_period("M")
    g = w.groupby(["month", "product"]).apply(
        lambda x: pd.Series({"price": (x.price * x.sales).sum() / x.sales.sum(), "weeks": len(x),
                             "last_week": x.week.max()}), include_groups=False)
    return g.reset_index()


def nowcast(w, cp):
    """Current and next-unannounced months: month-to-date Class III/IV from weekly NDPSR."""
    mw = monthly_from_weekly(w)
    last_announced = cp.index.max()
    res = []
    for m in sorted(mw.month.unique()):
        if m <= last_announced:
            continue
        x = mw[mw.month == m].set_index("product")
        if not {"cheese", "butter", "ndm", "whey"} <= set(x.index):
            continue
        c = components(x.price["cheese"], x.price["butter"], x.price["ndm"], x.price["whey"], regime(m))
        res.append(dict(month=str(m), weeks_in=int(x.weeks.min()), through=str(x.last_week.max().date()),
                        **{k: round(float(x.price[k]), 4) for k in ("cheese", "butter", "ndm", "whey")},
                        **{k: round(v, 4 if "class" not in k or "skim" in k else 2) for k, v in c.items()}))
    return res


def check_weighting(w, cp):
    """How well sales-weighted weekly averages reproduce AMS monthly product averages."""
    mw = monthly_from_weekly(w).pivot(index="month", columns="product", values="price")
    j = mw.join(cp[["cheese_monthly_avg_Price", "butter_monthly_avg_Price", "nfdm_monthly_avg_Price",
                    "whey_monthly_avg_Price"]], how="inner")
    j = j[j.index >= pd.Period("2025-06", "M")]  # blocks-only regime: cheese avg = block avg
    return {p: float((j[p] - j[c]).abs().max()) for p, c in
            [("cheese", "cheese_monthly_avg_Price"), ("butter", "butter_monthly_avg_Price"),
             ("ndm", "nfdm_monthly_avg_Price"), ("whey", "whey_monthly_avg_Price")]}


def futures_implied():
    """Implied Class III/IV from CME component futures settlements (latest CME trade date)."""
    cme = sorted((ROOT / "data" / "cme").glob("2*/fut_settlements.csv"))
    if not cme:
        return None
    s = pd.read_csv(cme[-1])
    s = s[s.sym.isin(["DC", "GDK", "CSC", "CB", "GNF", "DY"])].copy()
    s["settle"] = pd.to_numeric(s.settle.astype(str).str.replace(r"[AB]$", "", regex=True), errors="coerce")
    p = s.pivot_table(index="month", columns="sym", values="settle")
    p.index = [pd.Period(pd.to_datetime(i, format="%b %y"), "M") for i in p.index]
    p = p.sort_index()
    rows = []
    for m, x in p.iterrows():
        if x[["CSC", "CB", "GNF", "DY"]].isna().any():
            continue
        # cheese $/lb, butter and NDM and whey quoted in cents/lb
        c = components(x.CSC, x.CB / 100, x.GNF / 100, x.DY / 100, regime(m))
        rows.append(dict(month=str(m), trade_date=str(s.trade_date.iloc[0]),
                         class3_futures=x.get("DC"), class3_implied=round(c["class3"], 2),
                         class4_futures=x.get("GDK"), class4_implied=round(c["class4"], 2),
                         cheese=x.CSC, butter=x.CB, ndm=x.GNF, whey=x.DY))
    df = pd.DataFrame(rows)
    df["class3_gap"] = (df.class3_futures - df.class3_implied).round(2)
    df["class4_gap"] = (df.class4_futures - df.class4_implied).round(2)
    return df


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    cp = load_class_prices()
    rb = rebuild(cp)
    rb.to_csv(OUT / "class_rebuild.csv", index=False)
    w = weekly_ndpsr()
    w.to_csv(OUT / "ndpsr_weekly.csv", index=False)
    nc = nowcast(w, cp)
    fi = futures_implied()
    if fi is not None:
        fi.to_csv(OUT / "class_futures_implied.csv", index=False)
    summary = {
        "last_announced": str(cp.index.max()),
        "rebuild_max_abs_err_since_2025_06": {
            k: float(rb[rb.month >= "2025-06"][k].abs().max()) for k in ("class3_err", "class4_err")},
        "rebuild_max_abs_err_2013_2025_05": {
            k: float(rb[(rb.month >= "2013-01") & (rb.month < "2025-06")][k].abs().max()) for k in ("class3_err", "class4_err")},
        "weekly_to_monthly_max_abs_diff": check_weighting(w, cp),
        "nowcast": nc,
    }
    (OUT / "class_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    if fi is not None:
        print(fi.head(14).to_string())
